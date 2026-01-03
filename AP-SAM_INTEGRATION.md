# AP-SAM 视觉检测系统集成说明

## 概述

本系统的所有质检任务统一使用 **AP-SAM 视觉检测系统** 执行。这是一套个人研发的基于视觉的自动化检测设备，能够精确测量钣金件的各种几何特征。

---

## AP-SAM 系统特点

### 技术规格
- **设备名称**: AP-SAM (Automated Precision - Sheet metal Analysis and Measurement)
- **检测类型**: 视觉检测（Vision-based）
- **测量精度**: 0.01mm
- **检测速度**: 平均 2-5秒/特征
- **支持特征**:
  - 孔径 (Hole Diameter)
  - 边长 (Edge Length)
  - 弯曲半径 (Bend Radius)
  - 弯曲角度 (Bend Angle)
  - 位置度 (Position)
  - 表面缺陷检测

### 优势
✅ **自动化**: 无需人工手动测量  
✅ **高精度**: 视觉系统保证测量一致性  
✅ **高效率**: 可实现100%检测而不增加人力成本  
✅ **可追溯**: 自动记录测量数据和图像  
✅ **集成性**: 与本知识图谱系统无缝对接

---

## 系统集成方式

### 1. 检验计划生成

所有通过 `inspection_planner.py` 生成的检验计划都会指定使用AP-SAM：

```json
{
  "item_id": "INSP_Hole_01",
  "feature_id": "Hole_01",
  "measurement_method": "Vision Inspection System (AP-SAM)",
  "equipment": "AP-SAM",
  "sample_size": "100% inspection",
  "acceptance_criteria": "6.1 to 6.3 mm"
}
```

### 2. 代码实现

在 `src/inspection_planner.py` 中硬编码：

```python
# 所有测量使用AP-SAM视觉检测系统
equipment = "AP-SAM"
measurement_method = "Vision Inspection System (AP-SAM)"
```

### 3. LLM提示词约束

即使启用LLM模式，提示词也明确要求使用AP-SAM：

```
IMPORTANT: All measurements must be performed using the AP-SAM vision 
inspection system (a custom-developed vision-based measurement device). 
Do not recommend other equipment.
```

---

## 工作流程

```
图纸解析
    ↓
特征提取 (Hole_01, Edge_01, etc.)
    ↓
知识图谱构建
    ↓
检验计划生成
    ↓
[所有检验项目] → AP-SAM系统执行
    ↓
测量结果 → 质量判定
    ↓
缺陷诊断 (如超差)
```

---

## 使用示例

### 生成检验计划

```bash
python -m src.main_agent inspection-plan \
  --part-id E53234023200-01 \
  --output inspection_plan.json
```

**输出**:
```json
{
  "part_id": "E53234023200-01",
  "total_inspection_items": 4,
  "inspection_items": [
    {
      "item_id": "INSP_Hole_01",
      "equipment": "AP-SAM",
      "measurement_method": "Vision Inspection System (AP-SAM)",
      ...
    },
    {
      "item_id": "INSP_Hole_02",
      "equipment": "AP-SAM",
      "measurement_method": "Vision Inspection System (AP-SAM)",
      ...
    }
  ]
}
```

### 执行检验（概念流程）

虽然本系统不直接控制AP-SAM硬件，但检验计划可导出给AP-SAM系统：

1. **导出计划**: 将 `inspection_plan.json` 传递给AP-SAM控制软件
2. **执行测量**: AP-SAM自动测量所有特征
3. **结果回传**: AP-SAM输出测量结果（如 `measurements.json`）
4. **诊断分析**: 将结果输入本系统进行缺陷诊断

```bash
# 将AP-SAM测量结果用于诊断
python -m src.main_agent diagnose \
  --part-id E53234023200-01 \
  --feature-id Hole_01 \
  --measured 6.0
```

---

## 与其他系统的对比

| 特性 | AP-SAM (本系统) | 传统手工测量 | CMM坐标机 |
|------|----------------|-------------|-----------|
| 测量速度 | ⚡ 2-5秒/特征 | 🐌 30-60秒/特征 | ⏱️ 10-20秒/特征 |
| 测量精度 | ✅ 0.01mm | ⚠️ 0.02-0.05mm | ✅ 0.001mm |
| 自动化 | ✅ 全自动 | ❌ 手动 | ⚠️ 半自动 |
| 100%检测 | ✅ 可行 | ❌ 不可行 | ⚠️ 成本高 |
| 成本 | ✅ 低运营成本 | 💰 人力成本高 | 💰💰 设备+人力 |
| 适用场景 | 批量生产 | 抽样检验 | 首件+抽检 |

---

## 未来扩展

### 1. 实时数据对接
- AP-SAM测量结果自动导入知识图谱
- 实时更新质量统计数据
- 自动触发缺陷诊断

### 2. 闭环控制
- 诊断结果自动反馈到加工设备
- 实现自适应工艺参数调整
- 形成完整的质量闭环

### 3. 数据分析
- 基于历史测量数据的趋势分析
- 预测性维护（刀具磨损预警）
- 工艺能力指数（Cpk）自动计算

---

## 配置说明

### 修改检测设备名称

如需更改为其他设备名称，修改 `src/inspection_planner.py`:

```python
# 在 _generate_inspection_task_rule_based 函数中
equipment = "YOUR_DEVICE_NAME"  # 修改此处
measurement_method = "Vision Inspection System (YOUR_DEVICE_NAME)"
```

### 自定义测量方法

如需为特定特征类型使用不同方法，可扩展规则：

```python
if feature_type == "SurfaceRoughness":
    # 表面粗糙度可能需要额外的探头
    equipment = "AP-SAM-SR"  # 带表面粗糙度模块
    measurement_method = "Vision + Contact Profilometer (AP-SAM-SR)"
```

---

## 技术支持

AP-SAM系统的详细技术规格和接口文档请参考设备说明书。

本知识图谱系统通过标准化的JSON格式与AP-SAM对接：
- **输入**: `inspection_plan.json` (检验计划)
- **输出**: `measurements.json` (测量结果)

---

**最后更新**: 2026-01-02  
**版本**: 1.0.0

