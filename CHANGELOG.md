# CHANGELOG - GraphRAG Sheet Metal System

## Version 1.0.0 - 2026-01-02

### 🎉 Major Release: Production-Ready System

根据技术路线图 (`Project Roadmap Sheet Metal Inspection & Diagnosis System (Xizi Case).md`) 完成系统性升级，从MVP玩具数据迁移至真实生产数据支持。

---

## 📦 新增模块

### 1. `src/parse_process_card.py` - 工艺卡解析器
**功能**: 解析Excel工艺卡片，提取结构化工艺参数

**特性**:
- ✅ 支持Excel/CSV格式读取
- ✅ LLM驱动的参数提取（温度、时间、压力等）
- ✅ 正则表达式后备方案（无API时可用）
- ✅ 标准文档引用识别
- ✅ 设备信息提取

**使用**:
```bash
python -m src.parse_process_card --excel data/西子钣金件1工艺卡片.xlsx
```

**技术实现**:
- Pandas读取表格数据
- LLM提取自然语言描述的参数
- 正则匹配 `(495±5)℃` 等格式化参数

---

### 2. `src/inspection_planner.py` - 检验计划生成器 (Main Line A)
**功能**: 基于特征规格和质量标准生成检验任务

**工作流**:
1. 查询图谱获取特征规格 + 公差 + 标准
2. RAG检索标准要求（可选）
3. 生成结构化检验任务
4. **统一使用AP-SAM视觉检测系统** (个人研发设备)

**输出示例**:
```json
{
  "item_id": "INSP_Hole_01",
  "measurement_method": "Vision Inspection System (AP-SAM)",
  "equipment": "AP-SAM",
  "acceptance_criteria": "6.1 to 6.3 mm",
  "sample_size": "100% inspection for critical features"
}
```

**应用场景**:
- 首件检验计划生成
- 过程检验计划制定
- 最终检验清单生成
- **所有测量由AP-SAM视觉系统执行**

---

### 3. `src/process_diagnosis.py` - 工艺诊断引擎 (Main Line B)
**功能**: 质量缺陷根因分析与纠正措施推荐

**诊断流程**:
1. 识别特征超差
2. 追溯到生产工序
3. 分析工艺参数
4. 诊断根本原因
5. 生成纠正建议

**示例场景**:
- 孔径偏小 → 刀具磨损/刀补不足 → 建议增加刀补0.2mm
- 弯曲半径偏小 → 回弹补偿不足 → 建议增加冲程深度

**技术实现**:
- Cypher查询追溯特征→工序→参数链
- 基于规则的诊断引擎
- LLM增强诊断（可选）

---

### 4. 升级版 `src/main_agent.py` - 主编排引擎
**功能**: 完整端到端工作流编排

**新增子命令**:
- `ingest-drawing`: 解析并入库图纸
- `ingest-process`: 解析并入库工艺卡
- `link-features`: 关联特征与工序
- `inspection-plan`: 生成检验计划
- `diagnose`: 诊断质量缺陷
- `full-workflow`: 运行完整流程

**示例**:
```bash
python -m src.main_agent full-workflow \
  --drawing data/西子钣金件图纸1.PDF \
  --process-card data/西子钣金件1工艺卡片.xlsx \
  --feature-map examples/feature_process_map.json \
  --measurements examples/measurements.json
```

---

## 🔧 核心模块升级

### `src/graph_builder.py`
**新增节点类型**:
- `ProcessStep`: 工艺步骤 (step_id, step_number, name, description)
- `ProcessParam`: 工艺参数 (name, target_value, tolerance, unit)
- `Standard`: 标准文档 (standard_id, name)
- `Resource`: 设备资源 (resource_id, name)
- `Tolerance`: 公差规范 (tolerance_id, type, value)

**新增关系类型**:
- `HAS_PROCESS_STEP`: Part → ProcessStep
- `NEXT_STEP`: ProcessStep → ProcessStep (工艺流程链)
- `HAS_PARAM`: ProcessStep → ProcessParam
- `PRODUCES`: ProcessStep → GeoFeature (关键连接!)
- `REFERENCES`: ProcessStep → Standard
- `USES_RESOURCE`: ProcessStep → Resource

**新增方法**:
- `build_process_graph()`: 构建工艺流程图
- `link_feature_to_process()`: 关联特征到工序

**Schema图示**:
```
Part --HAS_PROCESS_STEP--> ProcessStep --PRODUCES--> GeoFeature
                               |                          |
                        HAS_PARAM                  LOCATED_AT
                               |                          |
                        ProcessParam                 ImageROI
                               
ProcessStep --NEXT_STEP--> ProcessStep
ProcessStep --REFERENCES--> Standard
ProcessStep --USES_RESOURCE--> Resource
```

---

### `src/extractor.py`
**新增功能**:
- 分区域提取: `extract_header_metadata()` - 提取标题栏
- GD&T识别: `extract_gdt_specifications()` - 几何公差
- 高级提取: `extract_features_advanced()` - 多阶段流水线

**新增提示词**:
- `HEADER_EXTRACTION_PROMPT`: 针对标题栏优化
- `GDT_EXTRACTION_PROMPT`: 针对几何公差优化
- 升级版 `SYSTEM_PROMPT`: 支持更多特征类型

**支持的特征类型扩展**:
- ✅ BendAngle (弯曲角度)
- ✅ BendRadius (弯曲半径)
- ✅ 材料信息 (material, material_state)
- ✅ GD&T callouts (位置度、垂直度等)

---

## 📚 文档与示例

### 新增文档
1. **README.md** (完全重写)
   - 系统架构说明
   - 完整使用指南
   - Neo4j查询示例
   - 故障排查指南

2. **USAGE_GUIDE.md** (新增)
   - 分场景使用说明
   - 高级功能介绍
   - 性能优化建议

3. **CHANGELOG.md** (本文件)
   - 详细变更记录

### 新增示例
1. **examples/quick_start.py**
   - 5分钟快速演示完整流程
   
2. **examples/feature_process_map.json**
   - 特征-工序映射模板

3. **examples/measurements.json**
   - 测量数据格式示例

4. **tests/test_vertical_slice.py**
   - 垂直切片集成测试
   - 覆盖工序20和60

---

## 🔄 Breaking Changes

### 1. Graph Schema 扩展
**影响**: 需要清空或迁移现有图谱数据

**迁移方案**:
```cypher
// 清空旧数据
MATCH (n) DETACH DELETE n

// 重新运行导入
python -m src.main_agent full-workflow ...
```

### 2. `main_agent.py` 接口变更
**旧接口** (已弃用):
```python
run_pipeline(image_path, part_id)
```

**新接口**:
```python
agent = MainAgent()
agent.ingest_drawing(drawing_path)
agent.ingest_process_card(excel_path)
agent.link_features_to_processes(part_id, feature_map)
agent.generate_inspection_plan(part_id)
agent.diagnose_defect(part_id, feature_id, measured_value)
```

---

## 🐛 Bug Fixes

1. **特征唯一性问题**: 使用 `feature_uid = part_id::feature_id` 避免跨零件冲突
2. **公差解析**: 正确处理负公差 `tol_lower = -0.1`
3. **CSV编码**: 支持UTF-8-BOM Excel导出格式

---

## ⚡ 性能优化

1. **批量导入**: 使用事务批处理降低Neo4j写入开销
2. **索引优化**: 新增约束和索引加速查询
3. **LLM调用**: 支持降级到规则引擎避免API依赖

---

## 📊 测试覆盖

### 新增测试
- ✅ `tests/test_vertical_slice.py`: 端到端集成测试
- ✅ `examples/quick_start.py`: 用户接受测试

### 测试的工序
- ✅ 工序20 (NC Routing): 孔加工
- ✅ 工序60 (Solution): 固溶热处理

### 测试场景
- ✅ 工艺卡解析
- ✅ 参数提取（温度、时间）
- ✅ 图谱构建
- ✅ 特征-工序关联
- ✅ 检验计划生成
- ✅ 缺陷诊断

---

## 🎯 技术路线图完成情况

参考: `Project Roadmap Sheet Metal Inspection & Diagnosis System (Xizi Case).md`

### ✅ Phase 1: 复杂数据解析
- [x] Task 1.1: 工艺卡结构化 (`parse_process_card.py`)
- [x] Task 1.2: 复杂图纸分区域解析 (`extractor.py` 升级)

### ✅ Phase 2: 知识图谱构建
- [x] Task 2.1: 节点与关系录入 (`graph_builder.py` 升级)
- [x] 手动对齐: `link_feature_to_process()` 方法

### ✅ Phase 3: 逻辑闭环验证
- [x] Task 3.1: 检验计划生成 (`inspection_planner.py`)
- [x] Task 3.2: 工艺诊断模拟 (`process_diagnosis.py`)

### ✅ Checklist
- [x] Schema升级: 新增5种节点类型，6种关系类型
- [x] 垂直切片测试: 工序20和60端到端流程
- [x] 规则校验: 单位解析、参数验证

### 🚧 Future Work
- [ ] Phase 4: RAG增强 (嵌入标准文档检索)
- [ ] Phase 5: Web界面 (可视化Dashboard)
- [ ] Phase 6: 批量管理 (多零件跟踪)

---

## 📦 依赖更新

### requirements.txt
```diff
  openai>=1.52.0
  neo4j>=5.23.0
  python-dotenv>=1.0.1
  pandas>=2.2.3
+ openpyxl>=3.1.2
```

---

## 🙏 致谢

本次升级基于真实工业场景需求（西子钣金案例），感谢：
- 技术路线图的详细规划
- 真实数据样本（PDF图纸 + Excel工艺卡）
- Neo4j图谱设计最佳实践

---

## 📞 支持

- **文档**: 查看 `README.md` 和 `USAGE_GUIDE.md`
- **问题**: 提交GitHub Issue
- **示例**: 运行 `python examples/quick_start.py`

---

**升级建议**: 
1. 备份现有Neo4j数据
2. 运行 `pip install -r requirements.txt`
3. 更新 `.env` 配置
4. 运行快速测试: `python examples/quick_start.py`
5. 迁移现有数据到新Schema

