# Technical Spec: KG-Enhanced Cognitive Inspection System (Phase 2 Upgrade)

Version: 2.1 (Deep Tech Implementation)

Objective: Upgrade the current rule-based MVP to a knowledge-driven, adaptive system.

Academic Theme: "Topology-Aware Graph RAG & Bayesian Risk-Adaptive Decision Making in Manufacturing Quality Control."

------

## 1. 系统架构概览 (System Architecture)

我们将现有的线性流程升级为 **"检索-推理-决策" (Retrieve-Reason-Decide)** 闭环架构。

- **Current (Level 1)**: `VLM -> Feature -> Static Rules -> Plan`
- **Target (Level 3)**: `VLM -> Feature -> [Risk Miner] -> [Cognitive Planner] -> Adaptive Plan`

核心新增组件：

1. **Risk Miner (风险挖掘器)**: 负责 `拓扑感知风险检索`。
2. **Cognitive Planner (认知规划器)**: 负责 `动态公差决策与策略优化`。

------

## 2. 核心模块一：拓扑感知风险检索 (Topology-Aware Risk Retrieval)

**学术定义**: 利用高维语义向量锚定图谱节点，并通过 K-Hop 邻域聚合算法提取因果风险特征。

### 2.1 技术选型：Embedding 模型

为了匹配 "Qwen's most advanced" 的要求，并确保对中文工艺语义（"铣削"、"位置度"、"刀纹"）的最佳理解，我们选用 **Alibaba-NLP/gte-Qwen2** 系列。

- **Model Selection**: `text-embedding-v4`
- **Implementation**: 按如下代码示例

```python
import os
from openai import OpenAI

input_text = "衣服的质量杠杠的"

client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),  
    # 以下是北京地域base-url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

completion = client.embeddings.create(
    model="text-embedding-v4",
    input=input_text
)

print(completion.model_dump_json())
```

### 2.2 子图匹配实现 (Subgraph Matching Mechanism)

我们不使用单纯的图同构（太慢），而是采用 **"Vector-Anchored K-Hop Traversal" (向量锚定 + K跳遍历)**。

**逻辑流程**:

1. **Anchor Generation (锚点生成)**:
   - 将当前特征描述序列化：`text = "Step: NC Routing, Feature: Hole, Size: 6.2mm, Tol: ±0.1"`
   - 计算 Query Vector: $V_q = Embed(text)$
2. **Vector Search (向量检索)**:
   - 在 Neo4j 中检索 Top-K 最相似的**历史特征节点** $\{F_{hist}\}$。
   - *Similarity Metric*: Cosine Similarity > 0.85。
3. **Topology Traversal (拓扑遍历)**:
   - 从检索到的每个 $F_{hist}$ 出发，沿 `HAS_DEFECT_HISTORY` 边进行 1-Hop 遍历，找到关联的缺陷节点 $D$。

**Cypher 实现模板**:

```cypher
// 1. Vector Search to find similar historical features
CALL db.index.vector.queryNodes('feature_embeddings', 5, $query_vector)
YIELD node AS hist_feature, score

// 2. Traversal: Find associated defects (Topology Awareness)
MATCH (hist_feature)-[:PRODUCED_BY]->(step:ProcessStep)
MATCH (step)-[r:HAS_DEFECT_HISTORY]->(defect:DefectRecord)
WHERE abs(defect.feature_size - $current_size) < 1.0 // 几何参数过滤

// 3. Return Subgraph Context
RETURN 
    hist_feature.id, 
    step.name, 
    defect.type, 
    defect.severity, 
    defect.description, 
    score AS similarity
```

### 2.3 风险聚合算法 (Risk Aggregation Logic)

**学术定义**: 基于加权频率的后验风险估计 (Weighted Frequency Posterior Estimation)。

计算公式:

对于当前特征 $F_{new}$，其风险分数 $R$ 计算如下：

$$R(F_{new}) = \frac{1}{N} \sum_{i=1}^{K} (Sim(F_{new}, F_{i}) \times Severity(D_i) \times Decay(t))$$

- $Sim$: 向量相似度（由 Vector Search 提供）。
- $Severity$: 历史缺陷严重度（0.0 - 1.0，存储在 Defect 节点）。
- $Decay(t)$: 时间衰减因子（越近发生的缺陷权重越大，例如 $0.95^{\Delta months}$）。

**Python 实现逻辑**:

```python
def calculate_risk_context(retrieved_subgraph):
    total_risk_score = 0
    risk_descriptions = []
    
    for record in retrieved_subgraph:
        # 简单加权累加
        weight = record['similarity']
        severity = record['defect.severity'] # Normalized 0-1
        total_risk_score += weight * severity
        
        risk_descriptions.append(f"{record['defect.type']} (Severity: {severity})")
    
    # 归一化风险等级
    if total_risk_score > 0.8: level = "CRITICAL"
    elif total_risk_score > 0.4: level = "HIGH"
    else: level = "LOW"
    
    return {"level": level, "score": total_risk_score, "evidence": risk_descriptions}
```

------

## 3. 核心模块二：动态公差决策与策略优化 (Dynamic Tolerance & Strategy Optimization)

**学术定义**: 基于大语言模型（LLM）的贝叶斯风险决策代理 (Bayesian Risk Decision Agent)。

### 3.1 实现原理 (Implementation Logic)

我们将决策过程建模为一个 **Prompt Engineering** 任务。LLM 扮演“资深质量工程师”，它接收三个输入，输出一个 JSON 决策。

**Input Context**:

1. **Engineering Spec**: 只有图纸公差（例如 ±0.1mm）。
2. **Risk Prior (From Module 1)**: "High Risk, Score 0.85. History shows frequent tool wear causing undersize holes."
3. **Cost Constraints**: "CMM inspection costs $10/min, Vision costs $0.5/min."

**Optimization Goal**: Find the inspection plan that minimizes `Expected_Total_Cost = Inspection_Cost + (Prob_Defect * Failure_Cost)`.

### 3.2 具体实现：Prompt Template

这是本模块的核心，直接决定了“智能”程度。

```python
PROMPT_TEMPLATE = """
You are an Intelligent Quality Control Decision Agent.

# Context
- Feature: {feature_type} (Nominal: {nominal}, Explicit Tol: {tolerance})
- Process Step: {process_step}

# Risk Intelligence (Retrieved from Knowledge Graph)
- Risk Level: {risk_level}
- Historical Evidence: {risk_evidence}

# Standard Rules
- Rule 1: Use Vision System if Tol > 0.05mm.
- Rule 2: Use AQL 4.0 sampling for stable processes.

# Decision Task
Your goal is to optimize the inspection plan. 
IF risk is HIGH, you MUST override Standard Rules to reduce failure risk.
IF risk is LOW, you should prioritize cost efficiency.

# Output Format (JSON)
{{
  "method": "string (CMM | Vision System | Manual)",
  "sampling_rate": "string (100% | AQL 2.5 | AQL 4.0)",
  "dynamic_tolerance_adjustment": "string (e.g., 'Tighten to ±0.05mm due to history')",
  "reasoning_chain": "string (Explain why you deviated from standard rules based on risk)"
}}
"""
```