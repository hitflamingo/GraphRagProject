# 使用指南 - GraphRAG 钣金质检与诊断系统

## 快速开始（推荐新用户）

### 1. 环境配置

复制环境变量模板：
```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

编辑 `.env` 文件，填入实际配置：
```bash
# 必填项
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password

# 可选项（有API密钥时填写，否则使用规则引擎）
OPENAI_API_KEY=sk-your-key-here
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动Neo4j

确保Neo4j数据库正在运行：
```bash
# Docker方式
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5.23

# 或使用Neo4j Desktop
# 启动后访问 http://localhost:7474 验证
```

### 4. 运行快速示例

```bash
python examples/quick_start.py
```

这会：
- ✓ 解析示例工艺数据
- ✓ 构建知识图谱
- ✓ 生成检验计划
- ✓ 模拟缺陷诊断

结果保存在 `results/` 目录。

---

## 完整工作流程

### 场景1: 处理新的钣金件

假设你有：
- 图纸: `data/西子钣金件图纸1.PDF`
- 工艺卡: `data/西子钣金件1工艺卡片.xlsx`

#### 步骤1: 创建特征-工序映射文件

创建 `my_part_map.json`:
```json
{
  "Hole_01": "20",
  "Hole_02": "20",
  "BendRadius_01": "80",
  "Edge_01": "80"
}
```

说明:
- `Hole_01`, `Hole_02`: 由工序20 (NC Routing) 加工的孔
- `BendRadius_01`: 由工序80 (液压成型) 形成的弯曲半径
- `Edge_01`: 由工序80形成的边

#### 步骤2: 运行完整流程

```bash
python -m src.main_agent full-workflow \
  --drawing data/西子钣金件图纸1.PDF \
  --process-card data/西子钣金件1工艺卡片.xlsx \
  --part-id E53234023200-01 \
  --feature-map my_part_map.json \
  --output results/my_workflow_result.json
```

#### 步骤3: 查看结果

```bash
# 查看检验计划
cat results/my_workflow_result.json | grep -A 20 "inspection_plan"

# 在Neo4j Browser中查看图谱
# 访问 http://localhost:7474
# 运行查询:
MATCH (p:Part {part_id: 'E53234023200-01'})-[*]-(n)
RETURN p, n
LIMIT 50
```

---

## 场景2: 质量缺陷诊断

### 问题描述
生产中发现孔径不合格：
- 特征: Hole_01
- 目标: Φ6.2mm (公差 ±0.1mm)
- 实测: 6.0mm

### 诊断步骤

```bash
python -m src.main_agent diagnose \
  --part-id E53234023200-01 \
  --feature-id Hole_01 \
  --measured 6.0 \
  --output results/hole01_diagnosis.json
```

### 输出示例

```json
{
  "status": "FAIL",
  "deviation": -0.2,
  "defect_type": "Undersized",
  "diagnosis": {
    "root_cause": "Cutting tool wear or incorrect tool compensation",
    "confidence": "Medium",
    "affected_process_step": "NC Routing",
    "affected_parameters": ["Tool diameter or cutter compensation"]
  },
  "recommendations": [
    {
      "action": "Increase cutter compensation by 0.20mm",
      "parameter": "Tool diameter or cutter compensation",
      "priority": "High"
    }
  ]
}
```

---

## 场景3: 分步操作（开发/调试模式）

### 步骤1: 仅解析工艺卡

```bash
python -m src.parse_process_card \
  --excel data/西子钣金件1工艺卡片.xlsx \
  --output results/parsed_process.json
```

检查输出：
```bash
cat results/parsed_process.json | python -m json.tool
```

### 步骤2: 仅解析图纸

```bash
python -m src.main_agent ingest-drawing \
  --drawing data/西子钣金件图纸1.PDF \
  --part-id E53234023200-01
```

### 步骤3: 入库工艺数据

```bash
python -m src.main_agent ingest-process \
  --excel data/西子钣金件1工艺卡片.xlsx
```

### 步骤4: 关联特征与工序

```bash
python -m src.main_agent link-features \
  --part-id E53234023200-01 \
  --map my_part_map.json
```

### 步骤5: 生成检验计划

```bash
python -m src.main_agent inspection-plan \
  --part-id E53234023200-01 \
  --output results/inspection_plan.json
```

---

## Neo4j 查询示例

### 查看所有工艺步骤

```cypher
MATCH (p:Part {part_id: 'E53234023200-01'})-[:HAS_PROCESS_STEP]->(ps:ProcessStep)
RETURN ps.step_number AS step, ps.name AS name
ORDER BY toInteger(ps.step_number)
```

### 查看工序的参数

```cypher
MATCH (ps:ProcessStep {step_id: 'E53234023200-01_Step60'})-[:HAS_PARAM]->(pp:ProcessParam)
RETURN pp.name AS parameter,
       pp.target_value AS target,
       pp.tolerance AS tolerance,
       pp.unit AS unit
```

### 查看特征的生产工序

```cypher
MATCH (f:GeoFeature {feature_uid: 'E53234023200-01::Hole_01'})
      <-[:PRODUCES]-(ps:ProcessStep)
RETURN f.feature_id AS feature,
       ps.step_number AS step,
       ps.name AS process_name
```

### 查看完整的工艺流程链

```cypher
MATCH path = (ps1:ProcessStep)-[:NEXT_STEP*]->(ps2:ProcessStep)
WHERE ps1.step_id STARTS WITH 'E53234023200-01'
RETURN path
LIMIT 1
```

### 查找所有引用特定标准的工序

```cypher
MATCH (ps:ProcessStep)-[:REFERENCES]->(s:Standard)
WHERE s.standard_id = 'XA-QI-0314'
RETURN ps.step_number, ps.name
```

---

## 高级功能

### 1. 批量诊断

创建测量数据文件 `batch_measurements.json`:
```json
{
  "Hole_01": 6.0,
  "Hole_02": 6.3,
  "BendRadius_01": 3.8,
  "Edge_01": 50.2
}
```

运行：
```bash
python -m src.main_agent full-workflow \
  --drawing data/西子钣金件图纸1.PDF \
  --process-card data/西子钣金件1工艺卡片.xlsx \
  --measurements batch_measurements.json \
  --output results/batch_diagnosis.json
```

### 2. 自定义检验标准

修改 `src/inspection_planner.py` 中的规则：

```python
# 在 _generate_inspection_task_rule_based 函数中
if "critical" in feature_type.lower():
    sample_size = "100% inspection"
elif "XA-QI-0314" in standards:
    sample_size = "First + 10% ongoing"
else:
    sample_size = "First article only"
```

### 3. 扩展诊断规则

在 `src/process_diagnosis.py` 中添加新规则：

```python
# 在 _diagnose_rule_based 函数中
elif "Surface" in feature_type:
    if "Roughness" in process_name:
        root_cause = "Surface finish out of spec"
        parameter = "Feed rate or tool condition"
        adjustment = "Reduce feed rate by 20%"
```

---

## 故障排查

### 问题1: Neo4j连接失败

```
Error: Could not connect to Neo4j
```

**解决方案**:
1. 确认Neo4j正在运行: `docker ps` 或检查Neo4j Desktop
2. 检查 `.env` 中的 `NEO4J_URI` 是否正确
3. 验证用户名密码: `NEO4J_USERNAME` 和 `NEO4J_PASSWORD`

### 问题2: API密钥无效

```
Warning: Could not initialize LLM client
```

**解决方案**:
- 这是正常的！系统会自动切换到规则引擎模式
- 如果需要VLM功能，请配置有效的API密钥

### 问题3: 特征未找到

```
Feature Hole_01 not found for part E53234023200-01
```

**解决方案**:
1. 确认已运行 `ingest-drawing` 步骤
2. 检查特征ID是否正确（区分大小写）
3. 在Neo4j中验证:
   ```cypher
   MATCH (f:GeoFeature)
   WHERE f.feature_uid CONTAINS 'E53234023200-01'
   RETURN f.feature_id
   ```

### 问题4: 工序未关联

```
No manufacturing process found for Hole_01
```

**解决方案**:
1. 确认已运行 `link-features` 步骤
2. 检查映射文件格式
3. 验证关系:
   ```cypher
   MATCH (f:GeoFeature)<-[:PRODUCES]-(ps:ProcessStep)
   WHERE f.feature_uid = 'E53234023200-01::Hole_01'
   RETURN ps.step_number
   ```

---

## 性能优化

### 1. 批量导入优化

对于大量零件，使用批处理：
```python
from src.main_agent import MainAgent

agent = MainAgent()
for part_data in part_list:
    agent.ingest_drawing(part_data['drawing'])
    agent.ingest_process_card(part_data['process_card'])
agent.close()
```

### 2. 图谱查询优化

创建索引：
```cypher
CREATE INDEX feature_type_idx IF NOT EXISTS FOR (f:GeoFeature) ON (f.type);
CREATE INDEX process_step_number_idx IF NOT EXISTS FOR (ps:ProcessStep) ON (ps.step_number);
```

### 3. 缓存提取结果

```python
import pickle

# 缓存提取结果
with open('extraction_cache.pkl', 'wb') as f:
    pickle.dump(extraction_result, f)

# 重用缓存
with open('extraction_cache.pkl', 'rb') as f:
    extraction_result = pickle.load(f)
```

---

## 数据清理

### 清空整个图谱

```cypher
MATCH (n) DETACH DELETE n
```

### 仅删除特定零件

```cypher
MATCH (p:Part {part_id: 'E53234023200-01'})-[*]-(n)
DETACH DELETE p, n
```

### 仅删除工艺数据

```cypher
MATCH (ps:ProcessStep)-[*]-(n)
WHERE ps.step_id STARTS WITH 'E53234023200-01'
DETACH DELETE ps, n
```

---

## 下一步

1. ✓ 运行 `examples/quick_start.py` 验证系统
2. ✓ 使用真实数据测试完整流程
3. ✓ 在Neo4j Browser中探索知识图谱
4. 根据需求定制诊断规则
5. 集成到生产系统

**需要帮助？** 查看 `README.md` 或提交Issue。

