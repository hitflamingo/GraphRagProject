# Swarm Orchestrator Usage Guide

## 概述 (Overview)

基于 LangGraph 的多智能体协同系统，实现了从线性流水线到 Supervisor-Worker 架构的转变。

## 架构 (Architecture)

```
┌─────────────────────────────────────────────────────────────┐
│                      SUPERVISOR                             │
│          (Orchestrator & Decision Maker)                    │
└────────┬──────────────┬──────────────┬─────────────────────┘
         │              │              │
         ▼              ▼              ▼
   ┌──────────┐  ┌──────────┐  ┌──────────────┐
   │   Geo    │  │    KG    │  │     Risk     │
   │ Analyst  │  │Librarian │  │   Actuary    │
   └──────────┘  └──────────┘  └──────────────┘
        │              │              │
        └──────────────┴──────────────┘
                       │
                       ▼
                   FINISH
```

### 智能体角色 (Agent Roles)

1. **Supervisor (指挥官)**
   - 任务分解与路由
   - 结果验证与反思
   - Critic Loop (自我修正)

2. **GeoAnalyst (几何分析师)**
   - 图纸解析 (VLM)
   - 特征提取
   - 公差识别

3. **KGLibrarian (图书管理员)**
   - 工艺卡片解析
   - 知识图谱构建
   - 数据融合 (Logic B.1 & B.2)

4. **RiskActuary (精算师)**
   - 拓扑感知风险检索
   - 贝叶斯风险聚合
   - 自适应检验计划生成

## 安装 (Installation)

```bash
# 依赖已在 requirements.txt 中
pip install -r requirements.txt
```

## 使用方法 (Usage)

### 方法 1: Python API

```python
from src.swarm import run_swarm_workflow

# 运行完整工作流
results = run_swarm_workflow(
    drawing_path="data/xizi_part_1.png",
    process_card_path="data/xizi_card_1.xlsx",
    part_id="PART-001",           # 可选
    max_iterations=20,            # 最大迭代次数
    output_path="results/output.json",  # 可选
    verbose=True                  # 显示详细日志
)

# 访问结果
print(f"成功: {results['success']}")
print(f"零件ID: {results['part_id']}")
print(f"检验计划: {results['inspection_plan']}")
print(f"风险报告: {results['risk_report']}")
```

### 方法 2: 命令行 (CLI)

```bash
# 基本用法
python -m src.swarm.cli \
  --drawing data/xizi_part_1.png \
  --process-card data/xizi_card_1.xlsx \
  --output results/swarm_output.json

# 指定 Part ID
python -m src.swarm.cli \
  --drawing data/drawing.pdf \
  --process-card data/process.xlsx \
  --part-id "PART-001"

# 静默模式
python -m src.swarm.cli \
  --drawing data/drawing.png \
  --process-card data/process.xlsx \
  --quiet
```

### 方法 3: 直接使用 Orchestrator

```python
from src.swarm import SwarmOrchestrator

# 创建编排器
orchestrator = SwarmOrchestrator(verbose=True)

# 运行工作流
results = orchestrator.run(
    drawing_path="data/xizi_part_1.png",
    process_card_path="data/xizi_card_1.xlsx",
    part_id="PART-001",
    max_iterations=20
)
```

## 输出结果 (Output)

```python
{
  "success": true,
  "part_id": "PART-001",
  
  # 图纸提取数据
  "drawing_data": {
    "features": [...],
    "material": "2024-O",
    "general_tolerance_standard": "ABD0001-1"
  },
  
  # 工艺卡片数据
  "process_data": {
    "process_steps": [...],
    "tolerance_rules": {...}
  },
  
  # 风险报告
  "risk_report": {
    "summary": {
      "critical_count": 2,
      "high_count": 5,
      "low_count": 10,
      "max_risk_score": 0.85
    },
    "needs_review": true
  },
  
  # 检验计划
  "inspection_plan": {
    "total_items": 17,
    "overall_risk_level": "HIGH",
    "inspection_items": [
      {
        "feature_id": "Hole_01",
        "risk_level": "CRITICAL",
        "risk_score": 0.85,
        "inspection_method": "CMM",
        "sampling_rate": "100%",
        "reasoning": "High historical defect rate..."
      },
      ...
    ],
    "recommendations": [...]
  },
  
  # 智能体反思
  "agent_reflections": {
    "GeoAnalyst": "Successfully extracted 17 features...",
    "KGLibrarian": "Built graph with 17 features and 8 steps...",
    "RiskActuary": "Assessed 17 features. Risk: 2 CRITICAL, 5 HIGH..."
  },
  
  # 执行元数据
  "execution_metadata": {
    "duration_seconds": 45.2,
    "iteration_count": 5,
    "force_strict": true
  }
}
```

## 核心功能 (Key Features)

### 1. Critic Loop (批评家回路)

系统会自动检测高风险场景并触发自我修正：

```python
# 自动触发场景:
# - 风险等级 = CRITICAL
# - 检验计划不够严格 (非 100% CMM)

# Supervisor 会：
# 1. 拒绝当前计划
# 2. 设置 force_strict = True
# 3. 将任务路由回 RiskActuary
# 4. RiskActuary 生成严格计划 (100% CMM)
```

### 2. 数据融合 (Data Fusion)

自动融合图纸和工艺卡片的公差信息：

**优先级**: 工艺卡片 > 图纸明确标注 > 通用标准

```python
# KGLibrarian 自动执行:
# 1. 解析工艺卡片公差规则
# 2. 与图纸特征匹配
# 3. 应用融合逻辑
# 4. 构建知识图谱
```

### 3. 拓扑感知风险检索

使用向量搜索和图谱遍历：

```python
# RiskActuary 执行:
# 1. 为当前特征生成嵌入向量
# 2. 向量搜索历史相似特征
# 3. 遍历图谱获取缺陷历史
# 4. 贝叶斯聚合 + 时间衰减
```

## 与旧系统对比 (vs. Legacy System)

| 特性 | 旧系统 (MainAgent) | 新系统 (Swarm) |
|------|-------------------|---------------|
| 架构 | 线性流水线 | Supervisor-Worker |
| 反馈回路 | ❌ 无 | ✅ Critic Loop |
| 上下文理解 | ❌ 数据字典传递 | ✅ 消息历史 + 状态 |
| 动态路由 | ❌ 固定顺序 | ✅ LLM 决策 |
| 自我修正 | ❌ 无 | ✅ 风险触发重试 |
| 错误恢复 | ❌ 抛出异常 | ✅ 降级处理 |

## 环境变量 (Environment)

```bash
# .env 文件
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选
OPENAI_MODEL=gpt-4o

NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
```

## 测试 (Testing)

```bash
# 运行测试套件
python tests/test_swarm.py

# 或使用 pytest
pytest tests/test_swarm.py -v
```

## 故障排查 (Troubleshooting)

### 1. 达到最大迭代次数

```python
# 增加 max_iterations
results = run_swarm_workflow(
    ...,
    max_iterations=30  # 默认 20
)
```

### 2. LLM 决策失败

系统会自动降级到基于规则的路由：

```
⚠️  Falling back to rule-based routing...
```

### 3. 工具调用失败

每个工具都有错误处理和状态返回：

```python
{
  "status": "FAILURE",
  "message": "Feature extraction failed: ...",
  "data": {}
}
```

## 性能优化 (Performance)

1. **并行工具调用**: 考虑将多个特征的风险评估并行化
2. **嵌入缓存**: 重复使用已计算的特征嵌入
3. **LLM 调用优化**: 使用更快的模型进行路由决策

## 未来增强 (Future Enhancements)

- [ ] 支持人工介入 (Human-in-the-Loop)
- [ ] 多部件批量处理
- [ ] 实时监控仪表板
- [ ] 更细粒度的工具 (如局部裁剪重分析)
- [ ] 支持更多文件格式

## 技术架构文档

详见: `技术架构升级文档：基于 LangGraph 的工业多智能体协同系统 (Industrial Reasoning Swarm).md`

