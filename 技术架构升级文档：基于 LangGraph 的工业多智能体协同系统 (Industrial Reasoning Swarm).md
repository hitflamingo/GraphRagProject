# 技术架构升级文档：基于 LangGraph 的工业多智能体协同系统 (Industrial Reasoning Swarm)

## 1. 架构范式转移 (Architectural Paradigm Shift)

### 1.1 现状分析 (AS-IS)

目前的 `MainAgent` (`main_agent.py`) 采用的是**线性流水线 (Linear Pipeline)** 模式：

> ```
> Ingest Drawing` -> `Ingest Process` -> `Build Graph` -> `Risk Mining` -> `Inspection Planning
> ```

- **局限性**：
  - **缺乏反馈回路**：如果 `Risk Miner` 发现数据缺失，无法自动触发 `Graph Builder` 重新检索。
  - **上下文丢失**：各个模块之间仅传递数据字典，缺乏对任务意图的整体理解。
  - **静态执行**：无法根据风险等级动态调整执行路径（例如：高风险时增加额外的诊断步骤）。

### 1.2 目标架构 (TO-BE)

我们将采用 **分层多智能体系统 (Hierarchical Multi-Agent System, HMAS)**，基于 **LangGraph** 实现状态机管理。

- **核心模式**：**Supervisor-Worker Pattern (监督者-工入模式)**。
- **全局状态 (`AgentState`)**：在智能体之间共享，包含图纸数据、图谱连接、当前计划和错误日志。

------

## 2. 智能体角色定义与代码映射 (Agent Roles & Code Mapping)

我们将原有的 Python 类重构为智能体（Agents）或其持有的工具（Tools）。

| **智能体名称 (Agent)**        | **对应论文角色**    | **核心职能**                       | **关联现有代码模块**                             |
| ----------------------------- | ------------------- | ---------------------------------- | ------------------------------------------------ |
| **Supervisor (指挥官)**       | The Orchestrator    | 任务分解、路由分发、最终决策、反思 | `MainAgent` (逻辑重构)                           |
| **Geo-Analyst (几何分析师)**  | Geometric Analyst   | 图纸解析、特征提取、视觉对齐       | `extractor.py` (VLM), `MainAgent.ingest_drawing` |
| **KG-Librarian (图书管理员)** | Knowledge Librarian | 图谱构建、Cypher查询、关联挖掘     | `graph_builder.py`, `parse_process_card.py`      |
| **Risk-Actuary (精算师)**     | The Risk Actuary    | 风险检索、贝叶斯更新、规划生成     | `risk_miner.py`, `cognitive_planner.py`          |

------

## 3. LangGraph 状态图设计 (Graph Schema Design)

### 3.1 全局状态定义 (`State Definition`)

我们需要定义一个 `TypedDict` 来在智能体之间传递上下文。

```python
from typing import TypedDict, Annotated, List, Union
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    # 消息历史，用于 LLM 理解上下文
    messages: Annotated[List[BaseMessage], operator.add]
    
    # 结构化数据存储 (来自现有代码的输出)
    part_id: str
    drawing_data: dict      # 来自 extractor.py 的输出
    process_data: dict      # 来自 parse_process_card.py 的输出
    risk_report: dict       # 来自 risk_miner.py 的输出
    inspection_plan: dict   # 来自 inspection_planner.py 的输出
    
    # 控制流状态
    next_agent: str         # 下一个执行的智能体名称
    errors: List[str]       # 错误日志，用于触发自愈机制
```

### 3.2 节点流转逻辑 (Workflow Logic)

```
graph TD
    Start --> Supervisor
    Supervisor -- "Need Parsing" --> GeoAnalyst
    Supervisor -- "Need Knowledge" --> KGLibrarian
    Supervisor -- "Need Risk/Plan" --> RiskActuary
    
    GeoAnalyst --> Supervisor
    KGLibrarian --> Supervisor
    RiskActuary --> Supervisor
    
    Supervisor -- "FINISH" --> End
```

------

## 4. 详细实现方案 (Implementation Plan)

### 4.1 几何视觉分析师 (Geo-Analyst Agent)

**目标**：将 `extractor.py` 的功能包装为具备“再看一眼”能力的智能体。

- **工具封装**：

  ```python
  @tool
  def extract_features_tool(drawing_path: str, focus_area: Optional[List[int]] = None):
      """调用 extractor.py 进行特征提取。支持 focus_area 进行局部裁剪分析。"""
      # 调用 extractor.extract_features_advanced
      pass
  ```

- **创新点逻辑**：如果初次提取的置信度低（例如 JSON 解析失败），Agent 会自动调用 `crop_image` 工具（需新增）对特定区域进行重试，而不是直接报错。

### 4.2 本体图书管理员 (KG-Librarian Agent)

**目标**：将 `parse_process_card.py` 和 `graph_builder.py` 整合，并增加 Schema 感知。

- **工具封装**：
  - `ingest_process_card_tool`: 调用 `parse_excel_process_card`。
  - `build_knowledge_graph_tool`: 调用 `GraphBuilder.build_fused_graph`。
- **自愈机制 (Self-Healing)**：
  - 现有 `GraphBuilder` 如果遇到 Neo4j 约束错误会抛出异常。
  - 在 Agent 中捕获该异常，让 LLM 分析错误日志（例如 "Constraint Validation Failed"），然后自动修正输入数据（例如生成唯一的 `feature_uid`）并重试。

### 4.3 贝叶斯精算师 (Risk-Actuary Agent)

**目标**：将 `risk_miner.py` 和 `cognitive_planner.py` 串联。

- **工具封装**：
  - `assess_topology_risk`: 调用 `RiskMiner.assess_feature_risk`。
  - `generate_adaptive_plan`: 调用 `CognitivePlanner.plan_inspection`。
- **推理链增强**：
  - Agent 不再只是被动接收请求。它会先调用 `assess_topology_risk`，如果发现 `risk_score > 0.8` (HIGH)，它会主动生成一份“警告报告”返回给 Supervisor，建议增加额外的检查步骤，体现“主动性”。

### 4.4 全维指挥官 (The Orchestrator / Supervisor)

**目标**：基于 LLM 的路由决策。

- **实现代码概览 (基于 LangGraph)**：

```python
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.output_parsers.openai_functions import JsonOutputFunctionsParser

# 1. 定义 Supervisor 的系统提示词
system_prompt = (
    "You are the supervisor of an industrial quality inspection system."
    "Your goal is to orchestrate the following workers: "
    "{members}."
    "Given the user request (e.g., 'Analyze this part drawing and generate a plan'), "
    "decide which worker should act next."
    "Each worker will perform a task and respond with their results and status."
    "When the entire workflow is complete (Drawing -> Graph -> Risk -> Plan), respond with FINISH."
)

# 2. 定义 Supervisor 节点
def supervisor_node(state: AgentState):
    messages = [
        {"role": "system", "content": system_prompt},
    ] + state["messages"]
    
    # 使用 OpenAI Function Calling 选择下一个 Agent
    response = llm.bind_functions(
        functions=[route_schema], 
        function_call="route"
    ).invoke(messages)
    
    return {"next_agent": response["next"], "messages": [response]}

# 3. 构建图
workflow = StateGraph(AgentState)
workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("GeoAnalyst", geo_analyst_agent)
workflow.add_node("KGLibrarian", kg_librarian_agent)
workflow.add_node("RiskActuary", risk_actuary_agent)

# 4. 添加边 (Edges)
for member in ["GeoAnalyst", "KGLibrarian", "RiskActuary"]:
    workflow.add_edge(member, "Supervisor")

# 5. 条件边 (Conditional Edges) - 动态路由的核心
workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next_agent"],
    {
        "GeoAnalyst": "GeoAnalyst",
        "KGLibrarian": "KGLibrarian",
        "RiskActuary": "RiskActuary",
        "FINISH": END
    }
)
```

------

## 5. 关键创新点落地 (Key Innovation Implementation)

### 5.1 引入 "Critic Loop" (批评家回路)

为了满足论文中提到的“闭环验证”，我们在 `RiskActuary` 生成计划后，不直接结束，而是增加一个简单的 **Self-Correction** 步骤。

- **逻辑**：
  1. Actuary 生成 `inspection_plan`。
  2. Supervisor 检查 `risk_report`。
  3. 如果 `risk_report` 为 HIGH，但 `inspection_plan` 仅仅是 "AQL 4.0" (常规抽样)。
  4. Supervisor 拒绝结束，发送指令："Risk is HIGH but sampling is standard. Please revise plan to 100% inspection."
  5. Actuary 重新调用 `cognitive_planner` 并强制参数 `force_strict=True`。

### 5.2 结构化输出 (Structured Outputs)

利用 Pydantic 确保 Agent 之间的通信不是自然语言，而是强类型的对象。

```python
from pydantic import BaseModel, Field

class InspectionTask(BaseModel):
    feature_id: str
    method: str = Field(..., description="CMM or Vision")
    sampling: str
    
class AgentResponse(BaseModel):
    status: str = "SUCCESS" | "FAILURE"
    data: dict
    reflection: str = Field(..., description="Self-reflection on the task execution")
```

------

## 6. 迁移步骤 (Migration Steps)

1. **环境准备**：安装 `langgraph`, `langchain`, `langchain_openai`.
2. **工具化改造**：
   - 修改 `extractor.py`，将 `extract_features_advanced` 封装为 `LangChain Tool`。
   - 修改 `risk_miner.py`，将 `assess_feature_risk` 封装为 `LangChain Tool`。
3. **构建 Agent 类**：为每个角色创建一个 Python 文件，定义其 Prompt 和可用工具。
4. **编写 Supervisor**：创建 `swarm_orchestrator.py` 替代 `main_agent.py`。
5. **测试反馈回路**：构造一个“缺少公差信息”的图纸案例，验证 Geo-Analyst 是否会报告缺失，Supervisor 是否会指示 KGLibrarian 去工艺卡片中查找（即目前的 Logic B.1 数据融合逻辑，但由 Agent 自主决策触发）。