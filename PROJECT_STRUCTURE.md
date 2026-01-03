# GraphRAG 钣金质检与诊断系统 - 项目结构

```
GraphRagProject/
│
├── 📁 src/                              # 核心源代码
│   ├── __init__.py                      # Python包初始化
│   ├── config.py                        # 配置管理 (Settings, OpenAI, Neo4j)
│   ├── extractor.py                     # 图纸特征提取 (VLM) [升级]
│   ├── graph_builder.py                 # 知识图谱构建 [升级]
│   ├── main_agent.py                    # 主编排引擎 [重写]
│   ├── parse_process_card.py            # 工艺卡解析 [新增]
│   ├── inspection_planner.py            # 检验计划生成 (Main Line A) [新增]
│   └── process_diagnosis.py             # 工艺诊断 (Main Line B) [新增]
│
├── 📁 data/                             # 数据文件
│   ├── 西子钣金件图纸1.PDF              # 真实图纸数据
│   ├── 西子钣金件1工艺卡片.xlsx         # 真实工艺卡
│   ├── process_steps.json               # 预处理的工艺数据
│   ├── D53918378200-02-B.png            # 示例图片
│   └── mock_vision/                     # Mock测试数据
│       └── mock_vision_data.json
│
├── 📁 examples/                         # 示例与快速开始
│   ├── quick_start.py                   # 5分钟快速演示脚本 [新增]
│   ├── feature_process_map.json         # 特征-工序映射模板 [新增]
│   └── measurements.json                # 测量数据示例 [新增]
│
├── 📁 tests/                            # 测试文件
│   ├── __init__.py                      # 测试包初始化 [新增]
│   ├── test_vertical_slice.py           # 垂直切片集成测试 [新增]
│   └── integration/                     # 集成测试目录
│
├── 📁 results/                          # 输出结果目录 [新增]
│   └── (运行时生成的JSON结果)
│
├── 📄 README.md                         # 完整系统文档 [重写]
├── 📄 USAGE_GUIDE.md                    # 使用指南 [新增]
├── 📄 CHANGELOG.md                      # 变更日志 [新增]
├── 📄 UPGRADE_SUMMARY.md                # 升级总结 [新增]
├── 📄 PROJECT_STRUCTURE.md              # 本文件 [新增]
│
├── 📄 requirements.txt                  # Python依赖 [更新]
├── 📄 .env.example                      # 环境变量模板 [新增]
│
└── 📄 Project Roadmap ... (Xizi Case).md  # 技术路线图 [参考]
```

---

## 核心模块说明

### 🔷 src/config.py
**功能**: 统一配置管理  
**内容**:
- OpenAI API配置 (Qwen兼容)
- Neo4j数据库配置
- 默认机器参数

**配置来源**: 
```python
load_dotenv()  # 从.env加载
settings = load_settings()
```

---

### 🔷 src/extractor.py [升级]
**功能**: 图纸特征提取  
**新增**:
- `extract_header_metadata()`: 标题栏解析
- `extract_gdt_specifications()`: GD&T提取
- `extract_features_advanced()`: 多阶段流水线

**技术栈**:
- VLM (Vision Language Model)
- Base64图像编码
- JSON结构化输出

**支持特征**:
- HoleRadius, EdgeLength, BendRadius, BendAngle
- GD&T公差 (位置度、垂直度)
- 材料信息 (material, material_state)

---

### 🔷 src/graph_builder.py [升级]
**功能**: Neo4j知识图谱构建  
**新增节点**:
- `ProcessStep`: 工艺步骤
- `ProcessParam`: 工艺参数
- `Standard`: 标准文档
- `Resource`: 设备资源
- `Tolerance`: 公差规范

**新增关系**:
- `HAS_PROCESS_STEP`: Part → ProcessStep
- `PRODUCES`: ProcessStep → GeoFeature (关键!)
- `NEXT_STEP`: ProcessStep → ProcessStep
- `HAS_PARAM`: ProcessStep → ProcessParam

**核心方法**:
```python
builder.build_graph(extraction)           # 构建特征图
builder.build_process_graph(process_data) # 构建工艺图
builder.link_feature_to_process(...)      # 关联特征-工序
```

---

### 🔷 src/parse_process_card.py [新增]
**功能**: Excel工艺卡解析  
**输入**: Excel/CSV工艺文档  
**输出**: 结构化工艺数据 + 参数

**提取能力**:
- 温度: `(495±5)℃`
- 时间: `(35±5)min`
- 范围: `15℃～32℃`
- 标准: `AIPS03-11-001`, `XA-OI-0310-01`
- 设备: `NC Routing Machine`

**双模式**:
1. **LLM模式**: Qwen智能提取
2. **Regex模式**: 正则表达式后备

---

### 🔷 src/inspection_planner.py [新增]
**功能**: 检验计划生成 (Main Line A)  
**工作流**:
```
特征规格 → 查询图谱 → RAG检索标准 → 生成检验任务
```

**重要**: 所有测量统一使用 **AP-SAM 视觉检测系统** (个人研发设备)

**输出示例**:
```json
{
  "item_id": "INSP_Hole_01",
  "measurement_method": "Vision Inspection System (AP-SAM)",
  "equipment": "AP-SAM",
  "acceptance_criteria": "6.1 to 6.3 mm",
  "sample_size": "100% inspection"
}
```

**适用场景**:
- 首件检验
- 过程检验
- 最终检验
- 所有测量由AP-SAM执行

---

### 🔷 src/process_diagnosis.py [新增]
**功能**: 工艺诊断 (Main Line B)  
**工作流**:
```
测量值 → 判断超差 → 追溯工序 → 分析参数 → 诊断根因 → 生成建议
```

**诊断逻辑**:
- 孔径偏小 → 刀补不足
- 孔径偏大 → 进给过快
- 弯曲偏小 → 回弹补偿不足
- 热处理不达标 → 温度/时间偏差

**输出示例**:
```json
{
  "root_cause": "Cutting tool wear or incorrect tool compensation",
  "recommendations": [
    {
      "action": "Increase cutter compensation by 0.20mm",
      "priority": "High"
    }
  ]
}
```

---

### 🔷 src/main_agent.py [重写]
**功能**: 主编排引擎  
**子命令**:

| 命令 | 功能 | 示例 |
|------|------|------|
| `ingest-drawing` | 解析图纸 | `--drawing data/图纸.PDF` |
| `ingest-process` | 解析工艺卡 | `--excel data/工艺卡.xlsx` |
| `link-features` | 关联特征-工序 | `--map map.json` |
| `inspection-plan` | 生成检验计划 | `--part-id E53...` |
| `diagnose` | 诊断缺陷 | `--feature-id Hole_01 --measured 6.0` |
| `full-workflow` | 完整流程 | `--drawing ... --process-card ...` |

**使用示例**:
```bash
# 完整流程
python -m src.main_agent full-workflow \
  --drawing data/西子钣金件图纸1.PDF \
  --process-card data/西子钣金件1工艺卡片.xlsx \
  --feature-map examples/feature_process_map.json \
  --measurements examples/measurements.json \
  --output results/complete.json
```

---

## 示例与测试

### 📄 examples/quick_start.py
**用途**: 5分钟快速演示  
**内容**:
1. 加载预处理数据
2. 构建图谱
3. 生成检验计划
4. 模拟缺陷诊断

**运行**:
```bash
python examples/quick_start.py
```

---

### 📄 tests/test_vertical_slice.py
**用途**: 端到端集成测试  
**覆盖**:
- 工序20 (NC Routing)
- 工序60 (Solution)
- 参数提取验证
- 诊断逻辑验证

**运行**:
```bash
python tests/test_vertical_slice.py
```

---

## 文档说明

### 📘 README.md
- 系统架构说明
- 完整使用指南
- Neo4j查询示例
- 故障排查

### 📗 USAGE_GUIDE.md
- 分场景使用说明
- 高级功能介绍
- 性能优化建议
- 常见问题FAQ

### 📙 CHANGELOG.md
- 详细变更记录
- Breaking Changes
- 依赖更新
- 技术路线图对照

### 📕 UPGRADE_SUMMARY.md
- 升级总结
- 代码统计
- 功能对照表
- 下一步计划

---

## 数据流图

```
┌─────────────┐
│  图纸 PDF   │
└──────┬──────┘
       │ VLM提取
       ↓
┌─────────────┐     ┌──────────────┐
│ GeoFeature  │────→│   Neo4j DB   │
└─────────────┘     │              │
                    │  Knowledge   │
┌─────────────┐     │    Graph     │
│ 工艺卡Excel  │     │              │
└──────┬──────┘     └──────┬───────┘
       │ LLM/Regex         │
       ↓                   │
┌─────────────┐            │
│ ProcessStep │────────────┘
│ProcessParam │
└─────────────┘
       │
       ↓
┌─────────────────────┐
│  PRODUCES 关系建立   │
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    ↓           ↓
┌────────┐  ┌────────┐
│检验计划│  │工艺诊断│
│Main A  │  │Main B  │
└────────┘  └────────┘
```

---

## 技术栈

| 层次 | 技术 | 用途 |
|------|------|------|
| **LLM** | Qwen (通过OpenAI API) | VLM图纸识别, 参数提取 |
| **图数据库** | Neo4j 5.x | 知识图谱存储 |
| **后端** | Python 3.8+ | 核心逻辑 |
| **数据处理** | Pandas, OpenPyXL | Excel解析 |
| **API客户端** | OpenAI Python SDK | LLM调用 |
| **配置** | python-dotenv | 环境变量管理 |

---

## 依赖项

```txt
openai>=1.52.0        # OpenAI兼容API客户端
neo4j>=5.23.0         # Neo4j Python驱动
python-dotenv>=1.0.1  # 环境变量加载
pandas>=2.2.3         # 数据处理
openpyxl>=3.1.2       # Excel读写
```

---

## 环境配置

创建 `.env` 文件：
```bash
# 必填
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password

# 可选 (有API时填写)
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=qwen-vl-plus
```

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env
# 编辑 .env 填入实际配置

# 3. 启动Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.23

# 4. 运行快速演示
python examples/quick_start.py

# 5. 查看结果
ls results/
```

---

## 扩展指南

### 添加新的特征类型

1. 在 `src/extractor.py` 中更新 `SYSTEM_PROMPT`
2. 在 `src/process_diagnosis.py` 中添加诊断规则

### 添加新的工艺参数

1. 在 `src/parse_process_card.py` 中扩展正则表达式
2. 更新LLM提示词

### 自定义检验标准

修改 `src/inspection_planner.py` 的 `_generate_inspection_task_rule_based`

---

## 许可证

MIT License

---

**最后更新**: 2026-01-02  
**版本**: 1.0.0

