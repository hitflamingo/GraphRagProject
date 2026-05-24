# LangGraph 状态机与路由逻辑文档

## 目录

1. [概览](#概览)
2. [State 逻辑详解](#state-逻辑详解)
3. [Supervisor 路由逻辑](#supervisor-路由逻辑)
4. [状态转移图](#状态转移图)
5. [节点实现细节](#节点实现细节)
6. [工作流执行流程](#工作流执行流程)

---

## 概览

本系统基于 **LangGraph** 构建了一个多智能体协同的工业质检系统，采用 **Supervisor-Worker** 架构模式。系统通过状态机管理整个工作流的执行，Supervisor 负责智能路由决策，Worker 节点执行具体任务。

### 核心组件

- **Supervisor（监督节点）**: 工作流协调器，负责路由决策和状态管理
- **GeoAnalyst（几何分析师）**: 技术图纸特征提取
- **KGLibrarian（知识图谱管理员）**: 工艺卡片解析和知识图谱构建
- **RiskActuary（风险评估师）**: 风险评估和自适应检验计划生成

---

## State 逻辑详解

### AgentState 结构定义

`AgentState` 是 LangGraph 中的全局共享状态，使用 `TypedDict` 定义，在节点间传递和更新。

```python
class AgentState(TypedDict):
    # 消息历史（用于 LLM 上下文和通信）
    messages: Annotated[List[BaseMessage], operator.add]
    
    # 结构化数据存储（各模块输出）
    part_id: str
    drawing_data: Optional[Dict[str, Any]]      # GeoAnalyst 输出
    process_data: Optional[Dict[str, Any]]      # KGLibrarian 输出
    risk_report: Optional[Dict[str, Any]]       # RiskActuary 输出
    inspection_plan: Optional[Dict[str, Any]]   # RiskActuary 输出
    
    # 控制流状态
    next_agent: str                              # 下一个执行的 agent
    errors: List[str]                            # 错误日志（用于自愈）
    
    # 执行元数据
    iteration_count: int                         # 迭代次数追踪
    max_iterations: int                          # 最大迭代次数（防止死循环）
    force_strict: bool                           # 强制严格检验模式（来自 Critic Loop）
    
    # 用户输入路径（用于工具调用）
    drawing_path: Optional[str]
    process_card_path: Optional[str]
    
    # 反思和推理
    supervisor_reasoning: Optional[str]          # Supervisor 的决策推理
    agent_reflections: Dict[str, str]            # 各 agent 的自我反思
```

### State 的关键特性

#### 1. 消息累加器 (`messages`)

```python
messages: Annotated[List[BaseMessage], operator.add]
```

- 使用 `operator.add` 实现消息的**累加式更新**
- 每次节点返回的消息会**追加**到现有消息列表，而不是替换
- 保证完整的对话历史和上下文

#### 2. 数据字段的更新规则

- **覆盖式更新**: `drawing_data`, `process_data`, `risk_report`, `inspection_plan` 等字段在节点执行后会被**完全替换**
- **增量更新**: `errors` 列表通过列表合并（`[*existing, new]`）实现增量追加
- **字典合并**: `agent_reflections` 通过字典展开（`{**existing, "Agent": reflection}`）实现合并

#### 3. 控制流字段

- `next_agent`: **核心路由字段**，Supervisor 根据此字段决定下一个执行的节点
- `iteration_count`: 每经过一次 Supervisor 节点自增，用于防止无限循环
- `force_strict`: 由 Critic Loop 设置，触发严格检验模式

### 初始状态创建

```python
def create_initial_state(
    drawing_path: str,
    process_card_path: str,
    part_id: Optional[str] = None,
    max_iterations: int = 20
) -> AgentState:
    return AgentState(
        messages=[],
        part_id=part_id or Path(drawing_path).stem,
        drawing_data=None,
        process_data=None,
        risk_report=None,
        inspection_plan=None,
        next_agent="Supervisor",  # 始终从 Supervisor 开始
        errors=[],
        iteration_count=0,
        max_iterations=max_iterations,
        force_strict=False,
        drawing_path=drawing_path,
        process_card_path=process_card_path,
        supervisor_reasoning=None,
        agent_reflections={}
    )
```

**关键点**:
- 所有数据字段初始化为 `None`
- `next_agent` 初始化为 `"Supervisor"`，确保工作流从监督节点开始
- `iteration_count` 从 0 开始，在 Supervisor 节点中自增

---

## Supervisor 路由逻辑

### 路由决策流程

Supervisor 是工作流的**核心决策节点**，负责分析当前状态并决定下一步执行路径。

#### 1. 路由决策 Schema

```python
class RouteDecision(BaseModel):
    next_agent: Literal["GeoAnalyst", "KGLibrarian", "RiskActuary", "FINISH"]
    reasoning: str
    force_strict: bool = False
```

**可路由目标**:
- `GeoAnalyst`: 图纸特征提取
- `KGLibrarian`: 工艺卡片解析和知识图谱构建
- `RiskActuary`: 风险评估和检验计划生成
- `FINISH`: 工作流完成

#### 2. 路由决策逻辑（Rule-Based + LLM）

Supervisor 使用 **LLM + 规则回退** 的混合决策机制：

##### 步骤 1: 迭代限制检查

```python
if iteration_count > max_iterations:
    return {
        "next_agent": "FINISH",
        "supervisor_reasoning": f"Forced completion due to iteration limit ({max_iterations})"
    }
```

**保护机制**: 防止死循环，达到最大迭代次数强制结束。

##### 步骤 2: 状态信息收集

Supervisor 分析当前状态的完整情况：

```python
has_drawing_data = state.get("drawing_data") is not None
has_process_data = state.get("process_data") is not None
has_risk_report = state.get("risk_report") is not None
has_inspection_plan = state.get("inspection_plan") is not None
error_count = len(state.get("errors", []))
force_strict = state.get("force_strict", False)
```

##### 步骤 3: LLM 决策生成

Supervisor 构建包含以下信息的 Prompt：

- **当前状态摘要**: 各数据字段的存在性、错误数量、迭代次数
- **Agent 反思**: 各 Worker 节点的自我反思
- **最近消息**: 最后 5 条消息
- **路由规则**: 明确的状态-路由映射规则

LLM 根据 Prompt 生成 `RouteDecision` 对象。

##### 步骤 4: Critic Loop（自我纠正机制）

**关键特性**: Supervisor 具有自我纠正能力，可以**拒绝** RiskActuary 的输出并要求重新生成。

```python
# 检查是否需要触发 Critic Loop
if has_risk_report and has_inspection_plan and not force_strict:
    risk_report = state.get("risk_report", {})
    needs_review = risk_report.get("needs_review", False)
    
    if needs_review and next_agent == "FINISH":
        # 触发 Critic Loop
        return {
            "next_agent": "RiskActuary",      # 重新路由到 RiskActuary
            "force_strict": True,              # 强制严格模式
            "supervisor_reasoning": (
                "Critic Loop: Risk is CRITICAL but plan not strict. "
                "Enforcing strict inspection (100% CMM)."
            )
        }
```

**Critic Loop 触发条件**:
1. `risk_report.needs_review == True` (RiskActuary 标记需要审查)
2. `inspection_plan` 已生成
3. `force_strict == False` (尚未启用严格模式)
4. LLM 决策为 `FINISH` (准备结束)

**Critic Loop 行为**:
- 拒绝当前检验计划
- 设置 `force_strict = True`
- 重新路由到 `RiskActuary`，要求生成严格检验计划（100% CMM 检验）

##### 步骤 5: 错误回退机制

如果 LLM 调用失败，Supervisor 使用**规则基础的路由逻辑**：

```python
# 规则基础回退路由
if not has_drawing_data:
    next_agent = "GeoAnalyst"
elif not has_process_data:
    next_agent = "KGLibrarian"
elif not has_inspection_plan:
    next_agent = "RiskActuary"
else:
    next_agent = "FINISH"
```

### 路由决策矩阵

| 状态条件 | 路由目标 | 说明 |
|---------|---------|------|
| `iteration_count > max_iterations` | `FINISH` | 迭代限制保护 |
| `!has_drawing_data` | `GeoAnalyst` | 需要提取图纸特征 |
| `has_drawing_data && !has_process_data` | `KGLibrarian` | 需要解析工艺卡片 |
| `has_drawing_data && has_process_data && !has_inspection_plan` | `RiskActuary` | 需要生成检验计划 |
| `has_inspection_plan && risk_report.needs_review && !force_strict` | `RiskActuary` (Critic Loop) | 需要严格检验模式 |
| `has_inspection_plan && (!needs_review || force_strict)` | `FINISH` | 工作流完成 |

### Supervisor Prompt 结构

Supervisor 使用的系统 Prompt 包含以下部分：

1. **团队介绍**: 各 Worker 节点的职责
2. **路由规则**: 明确的状态-路由映射规则
3. **Critic Loop 说明**: 何时触发自我纠正
4. **当前状态**: 格式化的状态摘要
5. **Agent 反思**: 各节点的自我反思
6. **最近消息**: 对话历史摘要

---

## 状态转移图

### 工作流图结构

```
                    START
                     ↓
              [Supervisor]
                     ↓
         ┌───────────┼───────────┐
         ↓           ↓           ↓
   [GeoAnalyst] [KGLibrarian] [RiskActuary]
         ↓           ↓           ↓
         └───────────┼───────────┘
                     ↓
              [Supervisor]
                     ↓
            ┌────────┴────────┐
            ↓                 ↓
        [FINISH]      [RiskActuary] (Critic Loop)
            ↓                 ↓
         [END]          [Supervisor]
                              ↓
                           [FINISH]
                              ↓
                            [END]
```

### 详细状态转移

#### 正常执行路径

```
1. START
   ↓
2. Supervisor (iteration_count=1)
   - 分析状态: 无数据
   - 决策: 路由到 GeoAnalyst
   ↓
3. GeoAnalyst
   - 执行: 提取图纸特征
   - 更新: drawing_data
   - 返回: next_agent = "Supervisor"
   ↓
4. Supervisor (iteration_count=2)
   - 分析状态: has_drawing_data = True, has_process_data = False
   - 决策: 路由到 KGLibrarian
   ↓
5. KGLibrarian
   - 执行: 解析工艺卡片 + 构建知识图谱
   - 更新: process_data
   - 返回: next_agent = "Supervisor"
   ↓
6. Supervisor (iteration_count=3)
   - 分析状态: has_drawing_data = True, has_process_data = True, has_inspection_plan = False
   - 决策: 路由到 RiskActuary
   ↓
7. RiskActuary
   - 执行: 风险评估 + 生成检验计划
   - 更新: risk_report, inspection_plan
   - 返回: next_agent = "Supervisor"
   ↓
8. Supervisor (iteration_count=4)
   - 分析状态: 所有数据完整
   - 检查: risk_report.needs_review = False (或 force_strict = True)
   - 决策: 路由到 FINISH
   ↓
9. END
```

#### Critic Loop 路径（自我纠正）

```
6. Supervisor (iteration_count=3)
   - 分析状态: 所有数据完整
   - 检查: risk_report.needs_review = True, force_strict = False
   - 决策: 触发 Critic Loop，路由到 RiskActuary (force_strict=True)
   ↓
7. RiskActuary (force_strict=True)
   - 执行: 重新生成严格检验计划 (100% CMM)
   - 更新: inspection_plan (严格模式)
   - 返回: next_agent = "Supervisor"
   ↓
8. Supervisor (iteration_count=4)
   - 分析状态: 所有数据完整，force_strict = True
   - 检查: Critic Loop 条件不满足（force_strict = True）
   - 决策: 路由到 FINISH
   ↓
9. END
```

#### 错误处理路径

```
任意节点发生错误:
   ↓
节点更新: errors.append(error_msg)
   ↓
节点返回: next_agent = "Supervisor"
   ↓
Supervisor
   - 分析: errors 列表非空
   - 决策: 
     * 如果错误可恢复 → 重试或继续
     * 如果错误严重 → FINISH（记录错误）
   ↓
FINISH 或 继续工作流
```

### 状态转换表

| 当前状态 | 触发事件 | 下一状态 | 状态更新 |
|---------|---------|---------|---------|
| `Supervisor` | `!has_drawing_data` | `GeoAnalyst` | `iteration_count++` |
| `GeoAnalyst` | 执行完成 | `Supervisor` | `drawing_data = result` |
| `Supervisor` | `has_drawing_data && !has_process_data` | `KGLibrarian` | `iteration_count++` |
| `KGLibrarian` | 执行完成 | `Supervisor` | `process_data = result` |
| `Supervisor` | `has_process_data && !has_inspection_plan` | `RiskActuary` | `iteration_count++` |
| `RiskActuary` | 执行完成 | `Supervisor` | `risk_report, inspection_plan = result` |
| `Supervisor` | `needs_review && !force_strict` | `RiskActuary` (Critic Loop) | `force_strict = True` |
| `Supervisor` | `has_inspection_plan && (force_strict \|\| !needs_review)` | `FINISH` | - |
| `任意节点` | `iteration_count > max_iterations` | `FINISH` | - |
| `FINISH` | - | `END` | - |

---

## 节点实现细节

### 1. Supervisor 节点

**文件**: `src/swarm/agents/supervisor.py`

**核心函数**: `supervisor_node(state: AgentState) -> Dict[str, Any]`

**职责**:
- 分析当前状态
- 生成路由决策
- 执行 Critic Loop 检查
- 更新 `iteration_count`
- 记录决策推理

**返回状态更新**:
```python
{
    "next_agent": str,              # 路由目标
    "iteration_count": int,          # 自增迭代计数
    "force_strict": bool,            # 可能启用严格模式
    "supervisor_reasoning": str,     # 决策推理
    "messages": [AIMessage(...)]     # 决策消息
}
```

### 2. GeoAnalyst 节点

**文件**: `src/swarm/agents/geo_analyst.py`

**核心函数**: `geo_analyst_node(state: AgentState) -> Dict[str, Any]`

**职责**:
- 使用 VLM 提取图纸特征
- 提取公差和 GD&T 信息
- 生成自我反思

**输入**: `drawing_path`, `part_id`

**输出状态更新**:
```python
{
    "drawing_data": Dict[str, Any],   # 提取的特征数据
    "part_id": str,                    # 更新后的零件ID
    "next_agent": "Supervisor",        # 固定返回 Supervisor
    "agent_reflections": {...},        # 自我反思
    "messages": [AIMessage(...)]
}
```

### 3. KGLibrarian 节点

**文件**: `src/swarm/agents/kg_librarian.py`

**核心函数**: `kg_librarian_node(state: AgentState) -> Dict[str, Any]`

**职责**:
- 解析工艺卡片 Excel
- 构建融合知识图谱（数据融合逻辑）
- 生成特征嵌入向量
- 链接特征到工艺步骤

**输入**: `process_card_path`, `drawing_data`

**输出状态更新**:
```python
{
    "process_data": Dict[str, Any],    # 解析的工艺数据
    "next_agent": "Supervisor",         # 固定返回 Supervisor
    "agent_reflections": {...},         # 自我反思
    "messages": [AIMessage(...)]
}
```

### 4. RiskActuary 节点

**文件**: `src/swarm/agents/risk_actuary.py`

**核心函数**: `risk_actuary_node(state: AgentState) -> Dict[str, Any]`

**职责**:
- 拓扑感知风险检索
- 向量搜索历史缺陷
- 贝叶斯风险聚合
- 生成自适应检验计划

**输入**: `drawing_data`, `process_data`, `force_strict`

**输出状态更新**:
```python
{
    "risk_report": {
        "summary": {...},              # 风险摘要
        "needs_review": bool           # 是否需要审查
    },
    "inspection_plan": {
        "inspection_items": [...],     # 检验项列表
        "risk_summary": {...},         # 风险分布
        "overall_risk_level": str,     # 总体风险级别
        "recommendations": [...]       # 建议
    },
    "next_agent": "Supervisor",         # 固定返回 Supervisor
    "agent_reflections": {...},         # 自我反思
    "messages": [AIMessage(...)]
}
```

**Critic Loop 触发条件**:
- `risk_report.needs_review == True`
- 或 `max_risk_score > 0.8 && !force_strict`

---

## 工作流执行流程

### 完整执行流程

#### 阶段 1: 初始化

```python
orchestrator = SwarmOrchestrator(verbose=True)
initial_state = create_initial_state(
    drawing_path="data/drawing.pdf",
    process_card_path="data/process_card.xlsx",
    part_id="PART-001",
    max_iterations=20
)
```

#### 阶段 2: 工作流执行

```python
config = {"configurable": {"thread_id": initial_state['part_id']}}

for i, state in enumerate(workflow.stream(initial_state, config), 1):
    # 状态流式输出
    agent_name = list(state.keys())[0]
    print(f"Step {i}: {agent_name}")
```

**LangGraph 执行机制**:
- `workflow.stream()` 返回状态更新流
- 每个 yield 对应一个节点的执行结果
- 状态自动在节点间传递

#### 阶段 3: 状态检查点 (Checkpointing)

```python
memory = MemorySaver()
compiled = workflow.compile(checkpointer=memory)
```

**功能**:
- 状态持久化（支持断点续传）
- 线程隔离（通过 `thread_id`）
- 支持状态恢复和重放

#### 阶段 4: 结果编译

```python
results = {
    "success": len(errors) == 0,
    "part_id": final_state["part_id"],
    "drawing_data": final_state["drawing_data"],
    "process_data": final_state["process_data"],
    "risk_report": final_state["risk_report"],
    "inspection_plan": final_state["inspection_plan"],
    "agent_reflections": final_state["agent_reflections"],
    "supervisor_reasoning": final_state["supervisor_reasoning"],
    "errors": final_state["errors"],
    "execution_metadata": {
        "duration_seconds": duration,
        "iteration_count": final_state["iteration_count"],
        "total_steps": len(execution_log)
    },
    "execution_log": execution_log
}
```

### 条件边路由实现

在 `workflow.py` 中，Supervisor 到 Worker 节点的路由通过**条件边**实现：

```python
def route_supervisor(state: AgentState) -> Literal["GeoAnalyst", "KGLibrarian", "RiskActuary", "FINISH"]:
    next_agent = state.get("next_agent", "FINISH")
    
    if next_agent == "FINISH":
        return "FINISH"
    
    valid_agents = ["GeoAnalyst", "KGLibrarian", "RiskActuary", "FINISH"]
    if next_agent not in valid_agents:
        return "FINISH"  # 默认回退
    
    return next_agent

workflow.add_conditional_edges(
    "Supervisor",
    route_supervisor,
    {
        "GeoAnalyst": "GeoAnalyst",
        "KGLibrarian": "KGLibrarian",
        "RiskActuary": "RiskActuary",
        "FINISH": END,
    },
)
```

**关键点**:
- `route_supervisor` 函数从 `state.next_agent` 读取路由决策
- 路由映射将返回值映射到对应的节点名称
- `"FINISH"` 映射到 `END`（LangGraph 的结束节点）

### Worker 节点返回 Supervisor

所有 Worker 节点执行完成后，通过**固定边**返回到 Supervisor：

```python
workflow.add_edge("GeoAnalyst", "Supervisor")
workflow.add_edge("KGLibrarian", "Supervisor")
workflow.add_edge("RiskActuary", "Supervisor")
```

这确保了工作流的**循环结构**：Supervisor → Worker → Supervisor → ...

---

## 总结

### 核心设计模式

1. **Supervisor-Worker 模式**: Supervisor 负责协调，Worker 执行具体任务
2. **状态机模式**: 使用 LangGraph 管理状态转换
3. **Critic Loop 模式**: Supervisor 具备自我纠正能力
4. **工具调用模式**: Worker 节点通过 LangChain Tools 调用底层功能

### 关键特性

1. **智能路由**: LLM + 规则回退的混合决策
2. **自我纠正**: Critic Loop 机制确保高风险场景下的严格检验
3. **错误恢复**: 错误记录和状态追踪，支持工作流继续
4. **迭代保护**: 最大迭代次数限制防止死循环
5. **状态持久化**: Checkpointing 支持断点续传

### 状态流转规律

- **单向数据流**: 数据从上游节点流向下游节点（GeoAnalyst → KGLibrarian → RiskActuary）
- **控制流循环**: 控制流在 Supervisor 和 Worker 之间循环
- **状态累加**: 消息和历史通过累加方式保留完整上下文
- **数据覆盖**: 结构化数据字段通过覆盖方式更新

---

**文档版本**: 1.0  
**最后更新**: 2024  
**相关文件**:
- `src/swarm/state.py` - State 定义
- `src/swarm/workflow.py` - 工作流构建
- `src/swarm/agents/supervisor.py` - Supervisor 路由逻辑
- `src/swarm/orchestrator.py` - 工作流执行器


