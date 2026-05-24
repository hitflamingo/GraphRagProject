# GraphRAG Sheet Metal Inspection & Diagnosis System

面向钣金零件质检与工艺诊断的 GraphRAG 原型系统。项目以“西子”案例数据为样例，把图纸解析、工艺卡解析、知识图谱、视觉测量、风险评估、检验计划生成和缺陷诊断串成一条可验证的工业质量分析流程。

当前推荐入口是基于 LangGraph 的多智能体 Swarm 工作流；旧版 `MainAgent` 管线仍保留，适合需要连接 Neo4j 并验证完整知识图谱写入的场景。

## 核心能力

- 图纸解析：从 PDF/PNG/JPG 技术图纸中提取几何特征、尺寸、公差、材料和 GD&T 信息。
- 工艺卡解析：读取 Excel 工艺卡，抽取工序、设备、标准、温度、时间、压力等工艺参数。
- 知识图谱：围绕 `Part`、`GeoFeature`、`ProcessStep`、`ProcessParam`、`Standard`、`Resource` 建立追溯关系。
- 多智能体协同：通过 Supervisor 调度 `GeoAnalyst`、`KGLibrarian`、`VisionInspector`、`RiskActuary` 等角色完成端到端分析。
- 离线验证：Swarm CLI 默认使用离线 mock 图谱、LLM 和 AP-SAM 测量边界，方便无 API key、无 Neo4j 时跑通流程。
- 缺陷诊断：基于测量值、公差、工序映射和历史缺陷记录生成风险结论、根因分析和纠正建议。

## 项目结构

```text
src/
  config.py                  # 环境变量与客户端配置
  extractor.py               # 图纸特征提取
  parse_process_card.py      # 工艺卡解析
  graph_builder.py           # Neo4j 知识图谱构建
  inspection_planner.py      # 检验计划生成
  process_diagnosis.py       # 缺陷诊断
  main_agent.py              # 旧版完整管线 CLI
  swarm/
    cli.py                   # 推荐的 Swarm CLI
    orchestrator.py          # 多智能体编排器
    workflow.py              # LangGraph 状态机
    offline_graph.py         # 离线图谱仓储
    agents/                  # Supervisor / Worker 节点

data/
  xizi_part_1.png            # 示例图纸
  xizi_part_1.PDF            # 示例 PDF 图纸
  xizi_card_1.xlsx           # 示例工艺卡
  process_steps.json         # 预处理工艺数据

examples/
  quick_start_swarm.py       # Swarm 快速启动脚本
  quick_start.py             # 旧版 MainAgent 快速启动脚本
  offline_measurements_pass.json
  offline_measurements_anomaly.json
  feature_process_map.json
  measurements.json

tests/
  test_offline_swarm_workflow.py
  test_graph_cot.py
  test_imports.py
```

## 环境要求

- Python 3.8+
- 可选：Neo4j 5.x，用于旧版 `MainAgent` 或真实图谱写入
- 可选：OpenAI 兼容 API，默认配置偏向 Qwen/DashScope
- 可选：Poppler，用于 PDF 图纸转图像

## 安装

建议先创建虚拟环境：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Linux/macOS 激活命令：

```bash
source .venv/bin/activate
```

如果需要处理 PDF 图纸，请确保已安装 Poppler。Windows 可使用 Conda：

```bash
conda install -c conda-forge poppler
```

## 配置

只跑离线 Swarm 示例时，可以不创建 `.env`。如果要使用真实 LLM 或 Neo4j，创建 `.env`：

```env
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=qwen-vl-plus
OPENAI_EMBEDDING_MODEL=text-embedding-v4

NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password

DEFAULT_MACHINE_ID=Default_Machine
DEFAULT_MACHINE_MODEL=Unknown
DEFAULT_BASE_STROKE=100.0
DEFAULT_CORRECTION_FACTOR=1.0

RISK_TOP_K=5
RISK_SIMILARITY_THRESHOLD=0.85
RISK_TIME_DECAY=0.95
```

## 使用指南

### 1. 推荐：离线跑通 Swarm 工作流

这是最适合首次验证的方式，不需要 Neo4j 和 API key：

```bash
python -m src.swarm.cli ^
  --drawing data/xizi_part_1.png ^
  --process-card data/xizi_card_1.xlsx ^
  --measurements examples/offline_measurements_pass.json ^
  --output results/swarm_pass.json ^
  --quiet
```

异常测量示例：

```bash
python -m src.swarm.cli ^
  --drawing data/xizi_part_1.png ^
  --process-card data/xizi_card_1.xlsx ^
  --measurements examples/offline_measurements_anomaly.json ^
  --output results/swarm_anomaly.json ^
  --quiet
```

运行成功后，结果会写入 `results/`。异常示例会额外产生 anomaly、defect record 和 Graph-CoT 报告相关字段。

也可以直接运行示例脚本：

```bash
python examples/quick_start_swarm.py
```

### 2. 查看 Swarm CLI 参数

```bash
python -m src.swarm.cli --help
```

常用参数：

- `--drawing`：图纸文件路径，支持 PDF/PNG/JPG。
- `--process-card`：工艺卡 Excel 文件路径。
- `--part-id`：零件 ID；不传时由图纸文件名推断。
- `--measurements`：测量值 JSON fixture。
- `--max-iterations`：多智能体最大迭代次数，默认 `20`。
- `--output` / `-o`：结果 JSON 输出路径。
- `--quiet` / `-q`：只输出最少运行日志。

### 3. 使用旧版 MainAgent 完整流程

旧版入口会初始化 Neo4j driver，因此需要先配置并启动 Neo4j：

```bash
python -m src.main_agent full-workflow ^
  --drawing data/xizi_part_1.PDF ^
  --process-card data/xizi_card_1.xlsx ^
  --part-id XIZI_PART_001 ^
  --feature-map examples/feature_process_map.json ^
  --measurements examples/measurements.json ^
  --output results/complete_workflow.json
```

只做数据融合并生成检验计划：

```bash
python -m src.main_agent fusion-plan ^
  --drawing data/xizi_part_1.PDF ^
  --process-card data/xizi_card_1.xlsx ^
  --part-id XIZI_PART_001 ^
  --output results/fusion_plan.json
```

禁用 LLM，仅使用规则和本地逻辑：

```bash
python -m src.main_agent ingest-fusion ^
  --drawing data/xizi_part_1.PDF ^
  --process-card data/xizi_card_1.xlsx ^
  --part-id XIZI_PART_001 ^
  --no-llm ^
  --output results/fusion_no_llm.json
```

### 4. 分步运行旧版管线

解析图纸：

```bash
python -m src.main_agent ingest-drawing ^
  --drawing data/xizi_part_1.PDF ^
  --part-id XIZI_PART_001
```

解析工艺卡：

```bash
python -m src.main_agent ingest-process ^
  --excel data/xizi_card_1.xlsx ^
  --no-llm
```

关联特征与工序：

```bash
python -m src.main_agent link-features ^
  --part-id XIZI_PART_001 ^
  --map examples/feature_process_map.json
```

生成检验计划：

```bash
python -m src.main_agent inspection-plan ^
  --part-id XIZI_PART_001 ^
  --output results/inspection_plan.json
```

诊断单个缺陷：

```bash
python -m src.main_agent diagnose ^
  --part-id XIZI_PART_001 ^
  --feature-id Hole_01 ^
  --measured 6.0 ^
  --output results/diagnosis_hole01.json
```

### 5. 输入数据格式

`examples/feature_process_map.json` 用于手动指定“特征 -> 工序”映射：

```json
{
  "Hole_01": "20",
  "Hole_02": "20",
  "BendRadius_01": "80",
  "Edge_01": "80"
}
```

`examples/measurements.json` 或离线测量 fixture 用于传入检测结果：

```json
{
  "Hole_01": 6.0,
  "Hole_02": 6.3,
  "BendRadius_01": 3.8
}
```

### 6. 运行测试

```bash
pytest
```

只验证离线 Swarm 主流程：

```bash
pytest tests/test_offline_swarm_workflow.py
```

## Neo4j 查询示例

查询零件的全部工序：

```cypher
MATCH (p:Part {part_id: 'XIZI_PART_001'})-[:HAS_PROCESS_STEP]->(ps:ProcessStep)
RETURN ps.step_number, ps.name
ORDER BY ps.step_number
```

查询某个特征对应的生产工序：

```cypher
MATCH (f:GeoFeature {feature_uid: 'XIZI_PART_001::Hole_01'})
      <-[:PRODUCES]-(ps:ProcessStep)
RETURN ps.name, ps.step_number
```

查询工序参数：

```cypher
MATCH (ps:ProcessStep {step_id: 'XIZI_PART_001_Step60'})-[:HAS_PARAM]->(pp:ProcessParam)
RETURN pp.name, pp.target_value, pp.tolerance, pp.unit
```

清空本地测试图谱：

```cypher
MATCH (n) DETACH DELETE n
```

## 常见问题

### 没有 API key 能跑吗？

可以。优先使用 `python -m src.swarm.cli ... --quiet` 的离线工作流。旧版 `MainAgent` 的部分 LLM 能力可以通过 `--no-llm` 禁用，但它仍需要 Neo4j 配置。

### 没有 Neo4j 能跑吗？

可以跑 Swarm 离线流程。需要真实图谱写入、Cypher 查询或旧版 `MainAgent` 时才需要 Neo4j。

### PDF 图纸处理失败怎么办？

确认已安装 `pdf2image`、`Pillow` 和 Poppler，并且 Poppler 命令在系统 PATH 中。也可以先使用 `data/xizi_part_1.png` 这类 PNG 图纸验证流程。

### 如何加入新的特征类型？

通常需要同步更新图纸提取提示词或解析逻辑、特征到工序的映射策略、检验计划规则，以及缺陷诊断规则。相关入口主要在 `src/extractor.py`、`src/inspection_planner.py`、`src/process_diagnosis.py` 和 `src/swarm/agents/`。

## 相关文档

- [SWARM_USAGE.md](SWARM_USAGE.md)：多智能体工作流使用说明。
- [AEROGUARDIAN_OFFLINE.md](AEROGUARDIAN_OFFLINE.md)：离线工程对齐说明。
- [DATA_FUSION_USAGE.md](DATA_FUSION_USAGE.md)：数据融合使用说明。
- [PDF_SUPPORT.md](PDF_SUPPORT.md)：PDF 图纸支持说明。
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)：项目结构说明。
- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)：架构迁移说明。

## 开发路线

- 已完成：MVP 数据链路、复杂图纸/工艺卡解析、知识图谱 Schema、Main Line A/B、LangGraph 多智能体 Swarm、离线测试链路。
- 进行中：Graph-CoT 报告、视觉测量异常闭环、风险检索增强。
- 后续：标准文档 RAG、Web Dashboard、批量零件管理、真实 AP-SAM 服务集成。

## 许可证

MIT License
