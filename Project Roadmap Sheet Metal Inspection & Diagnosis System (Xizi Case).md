# Project Roadmap: Sheet Metal Inspection & Diagnosis System (Xizi Case)

## 1. 项目当前状态 (Current Context)

- **目标**: 构建从“图纸/工艺理解”到“质检计划生成”再到“工艺诊断”的闭环系统 。
- **进度**:
  - [x] Neo4j 实例已启动。
  - [x] VLM 识别简单图纸并录入 Graph (MVP 跑通)。
- **当前挑战**:
  - 目前的 MVP 基于玩具数据（Toy Data）。
  - 需要迁移至 **真实生产数据**，处理高复杂度图纸（`西子钣金件图纸1.PDF`）和非结构化工艺文档（`西子钣金件1工艺卡片.xlsx`）。

------

## 2. 核心任务架构 (Core Architecture)

本阶段开发需围绕两条主线的数据对齐与逻辑构建进行。

### 2.1 实体关系图谱设计 (Target Graph Schema)

基于 PPT  和真实 Excel 数据，需将 Schema 扩展以支持工艺推理。

```cypher
// 核心节点定义 (基于 Neo4j)

// 1. 物理对象 (来自 PDF 图纸)
(:Part {part_no: "E53234023200-01", name: "CLEAT ST22-25 FR29"}) 
(:Feature {id: "F_01", type: "Hole", nominal_size: 6.2, unit: "mm"}) 
(:Tolerance {type: "Position", value: 0.1, datum_refs: ["A", "B"]})

// 2. 工艺过程 (来自 Excel 工艺卡)
(:ProcessStep {step_id: "20", name: "NC Routing", description: "Milling profile and hole..."}) 
(:ProcessStep {step_id: "60", name: "Solution", description: "Heat treatment..."}) [cite: 296]

// 3. 工艺参数 (从 Excel 文本中抽取)
(:ProcessParam {name: "Soaking Temperature", target_value: 495, tolerance: 5, unit: "C"}) 
(:Resource {name: "Machine", model: "NC Routing Machine"})

// 核心关系定义
(Feature)-[:DEFINED_IN]->(Drawing)
(Feature)-[:PRODUCED_BY]->(ProcessStep) // 关键连接：孔 F_01 是由工序 20 制造的
(ProcessStep)-[:HAS_PARAM]->(ProcessParam)
(ProcessStep)-[:NEXT_STEP]->(ProcessStep) // 20 -> 30 -> 40
```

------

## 3. 具体实施路径 (Implementation Steps)

### Phase 1: 复杂数据解析 (Data Ingestion & Parsing)

此阶段目标是将非结构化的 PDF 和 Excel 转换为上述 Graph Schema。

#### Task 1.1: 工艺卡片结构化 (Excel Processing)

- **输入**: `西子钣金件1工艺卡片.xlsx` (CSV 格式)

- **难点**: "工作内容" (Description) 列包含自然语言描述的参数 。

- **Action**: 编写 Python 脚本 (`process_card_parser.py`)。

  - 使用 Pandas 读取 CSV。

  - 利用 LLM (Qwen) 解析文本描述。

  - **Prompt 示例**:

    > "Extract process parameters from this text: 'Temperature is (495±5)℃, soaking time is(35±5)min'. Output JSON: `[{'param': 'Temperature', 'val': 495, 'tol': 5, 'unit': 'C'}, ...]`"

- **目标数据**: 提取工序 20 (下料)、60 (固溶)、80 (液压成型) 的关键参数。

#### Task 1.2: 复杂图纸分区域解析 (Advanced Drawing Parsing)

- **输入**: `西子钣金件图纸1.PDF`
- **策略**: 不要全图输入 VLM，需分而治之。
  - **Header/Table**: 使用 OCR 提取右上角表格  (Unfolded L/W values) 和标题栏 (Part No, Material `2024-O` )。
  - **GD&T**: 针对视图区域，识别几何特征及标注。
    - 重点识别: `Φ6.2` (Tooling Holes) , `R=4` (Bend Radius) 。
  - **Notes**: 提取标准引用，如 `ABD0003` ，作为 `StandardClause` 节点存入图谱。

### Phase 2: 知识图谱构建 (Graph Construction)

#### Task 2.1: 节点与关系录入

- 编写 `graph_builder.py`。

- **关键逻辑**:

  - 创建 `Part` 节点。

  - 创建所有 `ProcessStep` 链表 (10->20->...->170)。

  - **手动/半自动对齐**: 将图纸识别到的 `Feature (Hole Φ6.2)` 连接到 `ProcessStep (20 NC Routing)` 。

  - *注意*: 图纸上的 `Marking` 位置  需关联到 `ProcessStep (150 Marking)`。

    

### Phase 3: 逻辑闭环验证 (Logic Verification)

#### Task 3.1: 检验计划生成 (Main Line A)

- **目标**: 针对 `Feature (Hole Φ6.2)` 生成检验条目。
- **逻辑**:
  - 查询 Graph: 获取该特征的公差 + 引用标准 (`XA-QI-0314` )。
  - RAG 检索: 检索 `XA-QI-0314` 的具体检验要求（需模拟该文档内容）。
  - 输出: JSON 格式的任务列表。

#### Task 3.2: 工艺诊断模拟 (Main Line B)

- **目标**: 模拟“孔径偏小”的归因。
- **输入**: 观测到 Φ6.2 实测为 6.0。
- **查询逻辑**:
  1. 找到生成 Φ6.2 的工序 -> 返回 `Step 20 (NC Routing)`。
  2. 找到 Step 20 的参数 -> 返回 `Cutter Compensation` (需从领域知识库补全)。
  3. LLM 输出诊断: "建议检查工序 20 的刀补设置" 。

------

## 4. 待办事项清单 (Checklist)

- [ ] **数据清洗**: 清洗 Excel 转出的 CSV，去除无关的 header 行。
- [ ] **Schema 升级**: 在 Neo4j Browser 中运行新的 Constraint/Index 创建语句。
- [ ] **垂直切片测试**: 只针对 **工序 20 (NC Routing)** 和 **工序 60 (Solution)** 跑通 "解析 -> 入库 -> 查询" 的完整流程。
- [ ] **规则校验**: 编写代码检查图纸单位 (mm) 与 Excel 参数单位 (℃, min) 的解析正确性。