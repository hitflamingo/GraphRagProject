# 从 MainAgent 迁移到 Swarm Orchestrator 指南

## 概述

本指南帮助你从旧的 `MainAgent` 线性流水线迁移到新的 `SwarmOrchestrator` 多智能体系统。

## 兼容性说明

⚠️ **重要**: 两个系统可以共存，不需要强制迁移！

- ✅ 旧的 `MainAgent` 仍然可用
- ✅ 所有底层模块保持不变
- ✅ 可以逐步迁移，按需切换

## 快速对比

| 方面 | MainAgent (旧) | SwarmOrchestrator (新) |
|------|----------------|------------------------|
| 导入 | `from src.main_agent import MainAgent` | `from src.swarm import run_swarm_workflow` |
| 调用方式 | 类实例化 + 方法调用 | 单函数调用 |
| 执行模式 | 线性顺序执行 | 动态智能路由 |
| 错误处理 | 抛异常停止 | 降级 + 重试 |
| 自我修正 | ❌ 无 | ✅ Critic Loop |
| 结果格式 | 分散的多个 dict | 统一的 results dict |

## 代码迁移示例

### 旧代码 (MainAgent)

```python
from src.main_agent import MainAgent

# 创建 agent
agent = MainAgent()

try:
    # 运行完整工作流
    results = agent.run_complete_workflow(
        drawing_path="data/drawing.png",
        process_card_path="data/process.xlsx",
        part_id="PART-001"
    )
    
    # 访问结果
    extraction = results["extraction"]
    process_data = results["process_data"]
    inspection_plan = results["inspection_plan"]
    
finally:
    agent.close()
```

### 新代码 (SwarmOrchestrator)

```python
from src.swarm import run_swarm_workflow

# 直接运行（无需手动管理生命周期）
results = run_swarm_workflow(
    drawing_path="data/drawing.png",
    process_card_path="data/process.xlsx",
    part_id="PART-001",
    max_iterations=20,
    verbose=True
)

# 访问结果（更统一的结构）
drawing_data = results["drawing_data"]      # 对应旧的 extraction
process_data = results["process_data"]
inspection_plan = results["inspection_plan"]
risk_report = results["risk_report"]        # 新增：风险报告

# 新增功能
agent_reflections = results["agent_reflections"]  # 智能体反思
execution_metadata = results["execution_metadata"]  # 执行元数据
```

## 逐步迁移步骤

### 步骤 1: 并行运行测试

在你的现有代码中，先保持 `MainAgent`，添加 `SwarmOrchestrator` 测试：

```python
# 旧系统
from src.main_agent import MainAgent
old_agent = MainAgent()
old_results = old_agent.run_complete_workflow(...)
old_agent.close()

# 新系统
from src.swarm import run_swarm_workflow
new_results = run_swarm_workflow(...)

# 对比结果
compare_results(old_results, new_results)
```

### 步骤 2: 局部替换

选择一个低风险的模块先迁移：

```python
# 仅使用 GeoAnalyst 提取特征
from src.swarm.tools import extract_features_tool

result = extract_features_tool.invoke({
    "drawing_path": "data/drawing.png",
    "part_id": "PART-001"
})

if result["status"] == "SUCCESS":
    features = result["data"]
```

### 步骤 3: 完全迁移

当你确认新系统稳定后，替换所有调用点：

```python
# 替换前
from src.main_agent import MainAgent
agent = MainAgent()
results = agent.run_complete_workflow(...)
agent.close()

# 替换后
from src.swarm import run_swarm_workflow
results = run_swarm_workflow(...)
```

## 结果字段映射

### MainAgent 输出

```python
{
  "extraction": {
    "features": [...],
    "part_id": "...",
    ...
  },
  "process_data": {
    "process_steps": [...],
    ...
  },
  "inspection_plan": {
    "inspection_items": [...],
    ...
  }
}
```

### SwarmOrchestrator 输出

```python
{
  "success": true,
  "part_id": "...",
  
  # 映射到旧字段
  "drawing_data": {...},      # = extraction
  "process_data": {...},      # = process_data
  "inspection_plan": {...},   # = inspection_plan
  
  # 新增字段
  "risk_report": {
    "summary": {...},
    "needs_review": false
  },
  "agent_reflections": {
    "GeoAnalyst": "...",
    "KGLibrarian": "...",
    "RiskActuary": "..."
  },
  "supervisor_reasoning": "...",
  "errors": [],
  "execution_metadata": {
    "duration_seconds": 45.2,
    "iteration_count": 5,
    "force_strict": false
  }
}
```

## 功能对应关系

### MainAgent 方法 → Swarm 工具

| MainAgent 方法 | SwarmOrchestrator 等价物 |
|----------------|--------------------------|
| `ingest_drawing()` | 自动执行 (GeoAnalyst) |
| `ingest_process_card()` | 自动执行 (KGLibrarian) |
| `link_features_to_processes()` | 自动执行 (数据融合) |
| `generate_inspection_plan()` | 自动执行 (RiskActuary) |
| `diagnose_defect()` | ⚠️ 尚未迁移到 Swarm |

### CLI 对比

```bash
# 旧 CLI
python -m src.main_agent full-workflow \
  --drawing data/drawing.png \
  --process-card data/process.xlsx \
  --output results/output.json

# 新 CLI
python -m src.swarm.cli \
  --drawing data/drawing.png \
  --process-card data/process.xlsx \
  --output results/output.json
```

## 新功能说明

### 1. Critic Loop（在旧系统中不存在）

```python
# 新系统自动执行:
# 如果风险 = CRITICAL 但计划不够严格
# → Supervisor 自动拒绝计划
# → 设置 force_strict=True
# → 重新生成严格计划（100% CMM）

# 你无需手动干预，系统会自动处理
```

### 2. 迭代控制

```python
# 新系统可以设置最大迭代次数
results = run_swarm_workflow(
    ...,
    max_iterations=30  # 防止无限循环
)
```

### 3. 详细日志

```python
# 新系统提供完整的执行日志
for step in results["execution_log"]:
    print(f"Step {step['step']}: {step['agent']} at {step['timestamp']}")
```

## 常见问题

### Q1: 我能否只使用部分新功能？

✅ 可以！你可以单独使用工具，不需要完整的 Swarm：

```python
from src.swarm.tools import extract_features_tool, build_knowledge_graph_tool

# 只用提取工具
result = extract_features_tool.invoke({"drawing_path": "..."})
```

### Q2: 性能差异如何？

- **首次调用**: 新系统稍慢（需要编译 LangGraph 工作流）
- **后续调用**: 相近（都调用相同的底层模块）
- **优势**: 新系统在错误场景下更健壮（自动重试）

### Q3: 如何调试？

```python
# 旧系统
agent = MainAgent()
agent.ingest_drawing(...)  # 单步执行

# 新系统
results = run_swarm_workflow(..., verbose=True)  # 查看详细日志

# 或使用单独的工具
from src.swarm.tools import extract_features_tool
result = extract_features_tool.invoke({...})
print(result)  # 查看工具输出
```

### Q4: 我的自定义代码怎么办？

如果你扩展了 `MainAgent`：

```python
class MyCustomAgent(MainAgent):
    def custom_method(self):
        # 自定义逻辑
        pass
```

你有两个选择：

**选项 1**: 继续使用旧系统（完全兼容）

```python
agent = MyCustomAgent()
agent.custom_method()
```

**选项 2**: 扩展新系统

```python
# 创建自定义工具
from langchain_core.tools import tool

@tool
def my_custom_tool(...):
    """你的自定义逻辑"""
    pass

# 添加到 Agent
from src.swarm.agents.geo_analyst import GEO_ANALYST_TOOLS
GEO_ANALYST_TOOLS.append(my_custom_tool)
```

### Q5: 出现问题怎么办？

1. **先尝试旧系统验证**: 如果旧系统也失败，说明是数据问题
2. **查看执行日志**: `verbose=True` 会显示详细过程
3. **检查错误列表**: `results["errors"]` 包含所有错误信息
4. **降级到规则路由**: 如果 LLM 失败，系统会自动降级

## 回滚方案

如果新系统不稳定，随时可以回滚：

```python
# 方案 1: 直接换回旧代码
from src.main_agent import MainAgent
agent = MainAgent()
results = agent.run_complete_workflow(...)
agent.close()

# 方案 2: 使用旧 CLI
python -m src.main_agent full-workflow ...
```

**不需要卸载任何依赖**，两个系统可以共存。

## 推荐迁移路径

```
阶段 1 (1-2周): 熟悉新系统
  - 运行 tests/validate_swarm.py
  - 阅读 SWARM_USAGE.md
  - 运行 examples/quick_start_swarm.py

阶段 2 (2-4周): 并行测试
  - 在测试环境同时运行两个系统
  - 对比结果差异
  - 调整配置（max_iterations 等）

阶段 3 (4-6周): 逐步替换
  - 先替换非关键路径
  - 保留旧系统作为备用
  - 监控错误率和性能

阶段 4 (6周后): 完全迁移
  - 所有新代码使用新系统
  - 旧代码保持不变（兼容性）
  - 考虑弃用旧 API（可选）
```

## 技术支持

- 📖 使用指南: [SWARM_USAGE.md](SWARM_USAGE.md)
- 📋 完成总结: [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md)
- 📐 技术架构: [技术架构升级文档.md](技术架构升级文档：基于%20LangGraph%20的工业多智能体协同系统%20(Industrial%20Reasoning%20Swarm).md)
- 💻 示例代码: [examples/quick_start_swarm.py](examples/quick_start_swarm.py)

## 总结

- ✅ **无需强制迁移**: 两个系统可以共存
- ✅ **逐步过渡**: 从测试到生产，稳妥推进
- ✅ **随时回滚**: 出现问题可以立即切回旧系统
- ✅ **向后兼容**: 所有现有代码继续工作

新系统带来的优势（Critic Loop、自适应、自愈）在复杂场景下会更明显。建议先在测试环境验证，确认稳定后再迁移生产代码。

