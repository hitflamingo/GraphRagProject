# GraphRAG Sheet Metal Inspection & Diagnosis System (Xizi Case)

基于知识图谱的钣金件质检与工艺诊断系统 - 西子实际案例实现

## 系统架构

本系统实现了从"图纸/工艺理解"到"质检计划生成"再到"工艺诊断"的完整闭环：

```
图纸解析 (VLM) → 工艺卡解析 (LLM) → 知识图谱构建 (Neo4j)
                                              ↓
                        检验计划生成 (Main Line A) ← → 工艺诊断 (Main Line B)
```

## 核心功能

### 1. 图纸解析 (Drawing Extraction)
- **基础功能**: 提取几何特征、尺寸、公差
- **高级功能**: 
  - 分区域解析（标题栏、GD&T、注释）
  - 支持复杂钣金图纸（如西子图纸）
  - 提取材料信息、标准引用

### 2. 工艺卡解析 (Process Card Parsing)
- 解析Excel工艺卡片
- 使用LLM提取非结构化参数
- 识别温度、时间、压力等工艺参数
- 提取标准引用和设备信息

### 3. 知识图谱构建 (Knowledge Graph)
- **节点类型**:
  - `Part`: 零件
  - `GeoFeature`: 几何特征（孔、边、弯曲）
  - `ProcessStep`: 工艺步骤
  - `ProcessParam`: 工艺参数
  - `Standard`: 标准文档
  - `Resource`: 设备资源
  - `Tolerance`: 公差规范

- **关系类型**:
  - `HAS_FEATURE`: Part → GeoFeature
  - `PRODUCES`: ProcessStep → GeoFeature (关键连接)
  - `HAS_PARAM`: ProcessStep → ProcessParam
  - `NEXT_STEP`: ProcessStep → ProcessStep
  - `REFERENCES`: ProcessStep → Standard

### 4. 检验计划生成 (Main Line A)
- 基于特征规格自动生成检验任务
- 关联质量标准要求
- **统一使用AP-SAM视觉检测系统** (个人研发设备，详见 [AP-SAM_INTEGRATION.md](AP-SAM_INTEGRATION.md))
- 定义抽样策略和接收准则

### 5. 工艺诊断 (Main Line B)
- 质量缺陷根因分析
- 追溯到具体工艺步骤
- 识别关键工艺参数偏差
- 生成纠正措施建议

## 安装

### 环境要求
- Python 3.8+
- Neo4j 5.x
- OpenAI兼容API (Qwen推荐)

### 安装依赖
```bash
pip install -r requirements.txt
```

**PDF支持（可选）**:
如果需要处理PDF图纸，额外安装：
```bash
pip install pdf2image Pillow

# Windows还需要安装Poppler
conda install -c conda-forge poppler
```

详见 [PDF_SUPPORT.md](PDF_SUPPORT.md)

### 配置环境变量
创建 `.env` 文件：
```bash
# OpenAI兼容API (Qwen)
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=qwen-vl-plus

# Neo4j数据库
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password

# 默认机器参数（可选）
DEFAULT_MACHINE_ID=Default_Machine
DEFAULT_MACHINE_MODEL=Unknown
DEFAULT_BASE_STROKE=100.0
DEFAULT_CORRECTION_FACTOR=1.0
```

## 使用指南

### 方式1: 完整工作流（推荐用于生产环境）

运行完整的端到端流程：

```bash
python -m src.main_agent full-workflow \
  --drawing data/西子钣金件图纸1.PDF \
  --process-card data/西子钣金件1工艺卡片.xlsx \
  --part-id E53234023200-01 \
  --feature-map examples/feature_process_map.json \
  --measurements examples/measurements.json \
  --output results/complete_workflow.json
```

**示例配置文件**:

`examples/feature_process_map.json` (特征-工序映射):
```json
{
  "Hole_01": "20",
  "Hole_02": "20",
  "BendRadius_01": "80",
  "Edge_01": "80"
}
```

`examples/measurements.json` (测量数据):
```json
{
  "Hole_01": 6.0,
  "Hole_02": 6.3,
  "BendRadius_01": 3.8
}
```

### 方式2: 分步执行（推荐用于开发调试）

#### 步骤1: 解析图纸
```bash
python -m src.main_agent ingest-drawing \
  --drawing data/西子钣金件图纸1.PDF \
  --part-id E53234023200-01
```

#### 步骤2: 解析工艺卡
```bash
python -m src.main_agent ingest-process \
  --excel data/西子钣金件1工艺卡片.xlsx
```

#### 步骤3: 关联特征与工序
```bash
python -m src.main_agent link-features \
  --part-id E53234023200-01 \
  --map examples/feature_process_map.json
```

#### 步骤4: 生成检验计划
```bash
python -m src.main_agent inspection-plan \
  --part-id E53234023200-01 \
  --output results/inspection_plan.json
```

#### 步骤5: 诊断缺陷
```bash
python -m src.main_agent diagnose \
  --part-id E53234023200-01 \
  --feature-id Hole_01 \
  --measured 6.0 \
  --output results/diagnosis_hole01.json
```

### 方式3: 使用独立模块

#### 仅解析工艺卡
```bash
python -m src.parse_process_card \
  --excel data/西子钣金件1工艺卡片.xlsx \
  --output results/process_steps.json \
  --no-llm  # 使用基于正则的后备方案
```

#### 仅生成检验计划
```bash
python -m src.inspection_planner \
  --part-id E53234023200-01 \
  --features Hole_01 Hole_02 \
  --output results/inspection_plan.json
```

#### 仅诊断缺陷
```bash
python -m src.process_diagnosis \
  --part-id E53234023200-01 \
  --feature-id Hole_01 \
  --measured 6.0 \
  --output results/diagnosis.json
```

## 代码结构

```
src/
├── config.py                   # 配置管理
├── extractor.py                # 图纸特征提取 (VLM)
├── parse_process_card.py       # 工艺卡解析 (LLM + Regex)
├── graph_builder.py            # 知识图谱构建
├── inspection_planner.py       # 检验计划生成 (Main Line A)
├── process_diagnosis.py        # 工艺诊断 (Main Line B)
└── main_agent.py              # 主编排引擎

data/
├── 西子钣金件图纸1.PDF         # 真实图纸数据
├── 西子钣金件1工艺卡片.xlsx    # 真实工艺卡
├── process_steps.json          # 预处理的工艺数据
└── mock_vision/                # 测试数据

examples/
├── feature_process_map.json    # 特征-工序映射示例
└── measurements.json           # 测量数据示例
```

## 技术实现要点

### 1. 图纸解析策略
- **多阶段提取**: 标题栏 → 主特征 → GD&T规范
- **提示工程**: 针对钣金图纸优化的VLM提示词
- **后备机制**: API失败时使用mock数据

### 2. 工艺参数提取
- **LLM解析**: 处理自然语言描述的参数
- **正则表达式**: 提取结构化参数（温度、时间等）
- **标准识别**: 自动识别工艺标准引用

### 3. 知识图谱设计
- **语义关系**: `PRODUCES`关系连接工序与特征
- **参数追踪**: 完整的工艺参数可追溯性
- **标准关联**: 检验标准与工艺标准的关联

### 4. 诊断逻辑
- **图查询**: Cypher查询追溯特征到工序
- **规则引擎**: 基于特征类型的诊断规则
- **LLM增强**: 复杂场景的智能诊断

## 示例应用场景

### 场景1: 孔径偏小诊断
**问题**: Φ6.2mm的孔实测为6.0mm

**系统操作**:
1. 识别特征: Hole_01, 目标6.2mm, 公差±0.1mm
2. 查询图谱: 发现由工序20 (NC Routing) 生成
3. 分析参数: 刀补、转速、进给
4. 诊断结论: "刀具磨损或刀补设置偏小"
5. 纠正建议: "增加刀补0.2mm"

### 场景2: 弯曲半径超差
**问题**: R=4的弯曲半径实测为3.8mm

**系统操作**:
1. 识别特征: BendRadius_01, 目标4.0mm
2. 查询图谱: 发现由工序80 (液压成型) 生成
3. 分析参数: 冲程、保压时间
4. 诊断结论: "回弹补偿不足或模具磨损"
5. 纠正建议: "增加冲程深度0.24mm以补偿回弹"

### 场景3: 固溶温度偏差
**问题**: 检验发现材料硬度不达标

**系统操作**:
1. 查询工序60 (固溶处理)
2. 提取参数: 温度(495±5)℃, 时间(35±5)min
3. 关联标准: XA-OI-0401, AIPI04-01-001
4. 生成检验项: 温度记录检查、保温时间验证
5. 诊断提示: 检查炉温均匀性和淬火转移时间

## 垂直切片测试

针对工序20 (NC Routing) 和工序60 (Solution) 的完整测试：

```bash
# 创建测试数据
mkdir -p tests/integration

# 运行集成测试
python tests/test_vertical_slice.py
```

测试覆盖:
- [x] Excel解析 → 提取工序20和60
- [x] 参数提取 → 温度(495±5)℃, 时间(35±5)min
- [x] 图谱构建 → 创建ProcessStep和ProcessParam节点
- [x] 检验计划 → 针对这两道工序生成检验项
- [x] 诊断模拟 → 孔径偏小归因到工序20

## Neo4j查询示例

### 查询所有工艺步骤
```cypher
MATCH (p:Part {part_id: 'E53234023200-01'})-[:HAS_PROCESS_STEP]->(ps:ProcessStep)
RETURN ps.step_number, ps.name
ORDER BY ps.step_number
```

### 查询特征的生产工序
```cypher
MATCH (f:GeoFeature {feature_uid: 'E53234023200-01::Hole_01'})
      <-[:PRODUCES]-(ps:ProcessStep)
RETURN ps.name, ps.step_number
```

### 查询工序的参数
```cypher
MATCH (ps:ProcessStep {step_id: 'E53234023200-01_Step60'})-[:HAS_PARAM]->(pp:ProcessParam)
RETURN pp.name, pp.target_value, pp.tolerance, pp.unit
```

### 查询完整的特征→工序→参数链
```cypher
MATCH (f:GeoFeature {feature_uid: 'E53234023200-01::Hole_01'})
      <-[:PRODUCES]-(ps:ProcessStep)
      -[:HAS_PARAM]->(pp:ProcessParam)
RETURN f.feature_id, ps.name, collect({param: pp.name, value: pp.target_value, unit: pp.unit})
```

## 开发路线图

- [x] MVP: 玩具数据验证基本流程
- [x] Phase 1: 复杂数据解析 (真实PDF + Excel)
- [x] Phase 2: 知识图谱构建 (完整Schema)
- [x] Phase 3: 逻辑闭环验证 (Main Line A & B)
- [ ] Phase 4: RAG增强 (标准文档检索)
- [ ] Phase 5: 可视化界面 (Web Dashboard)
- [ ] Phase 6: 批量处理 (多零件管理)

## 常见问题

### Q: 如何处理没有API密钥的情况？
A: 系统会自动降级到基于规则的方法。图纸解析使用mock数据，工艺参数使用正则表达式提取。

### Q: 如何添加新的特征类型？
A: 在`extractor.py`的`SYSTEM_PROMPT`中添加特征类型，在`process_diagnosis.py`的`_diagnose_rule_based`中添加诊断规则。

### Q: 如何自定义检验标准？
A: 修改`inspection_planner.py`的`_generate_inspection_task_rule_based`函数，或提供自定义的LLM提示词。

### Q: 图谱数据如何清理？
```cypher
// 删除所有节点和关系
MATCH (n) DETACH DELETE n
```

## 许可证

MIT License

## 联系方式

如有问题或建议，请通过Issue反馈。
