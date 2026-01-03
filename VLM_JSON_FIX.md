# VLM JSON解析失败问题解决方案

## 问题描述

```
Warning: VLM extraction failed: Expecting property name enclosed in double quotes: line 1364 column 8 (char 28387)
```

**根本原因**: VLM (Qwen) 返回的JSON格式不规范，Python的标准 `json.loads()` 无法解析。

---

## ✅ 已实施的解决方案

### 1. 多策略JSON解析器

系统现在使用 **5层解析策略**，依次尝试：

#### Strategy 1: 标准JSON解析
```python
json.loads(json_str)
```

#### Strategy 2: 清理后解析
- 移除 C风格注释 (`// comment`)
- 移除多行注释 (`/* comment */`)
- 移除尾随逗号 (`{"key": "value",}` → `{"key": "value"}`)

#### Strategy 3: JSON5解析（如已安装）
- 支持单引号
- 支持尾随逗号
- 支持注释
- 支持更宽松的语法

#### Strategy 4: Markdown代码块提取
```
```json
{"key": "value"}
```
↓ 提取中间的JSON
```

#### Strategy 5: 部分JSON提取
- 从响应中查找最大的有效JSON对象
- 尝试解析找到的每个片段

---

## 🔧 使用方法

### 安装增强依赖（推荐）

```bash
pip install -r requirements.txt
```

这会安装 `json5`，提供更好的JSON兼容性。

或单独安装：
```bash
pip install json5
```

### 无需额外操作

代码已自动集成，会在JSON解析失败时自动尝试多种策略。

---

## 📊 效果对比

### 修复前
```
Error: Expecting property name enclosed in double quotes
→ 立即失败，降级到Mock数据
```

### 修复后
```
Strategy 1 failed: Expecting property name...
Strategy 2 trying...
Strategy 3 trying...
✓ Success with Strategy 3 (json5)
→ 成功解析VLM输出
```

---

## 🎯 解决的常见问题

### 问题1: 尾随逗号
```json
{
  "features": [
    {"id": "Hole_01"},  ← 这里有逗号
  ]  ← 这里不应该有逗号
}
```
**解决**: Strategy 2 自动清理

### 问题2: 注释
```json
{
  // This is a feature
  "feature_id": "Hole_01"
}
```
**解决**: Strategy 2 移除注释

### 问题3: 单引号
```json
{'feature_id': 'Hole_01'}
```
**解决**: Strategy 3 (json5) 支持

### 问题4: Markdown包装
````
Here's the JSON:
```json
{"feature_id": "Hole_01"}
```
````
**解决**: Strategy 4 提取代码块

### 问题5: 混合内容
```
Some text before
{"feature_id": "Hole_01"}
Some text after
```
**解决**: Strategy 5 提取JSON片段

---

## 🔍 调试信息

当JSON解析失败时，系统会输出详细信息：

```
Warning: JSON parsing failed: Expecting property name...
Raw response length: 28387 chars
Raw response preview: {"part_id": "aa", "features": [... (first 500 chars)
  Standard JSON parse failed: ...
  Cleaned JSON parse failed: ...
  JSON5 parse succeeded ✓
```

---

## 📝 提示词优化（可选）

虽然代码已支持多种格式，但仍建议优化提示词减少问题：

### 当前提示词
```python
SYSTEM_PROMPT = """...
Return JSON with:
{
  "part_id": "string",
  "features": [...]
}
"""
```

### 优化建议
```python
SYSTEM_PROMPT = """...
CRITICAL: Return ONLY valid JSON. No comments, no trailing commas, no markdown.

Example:
{
  "part_id": "E53234023200-01",
  "features": [
    {
      "feature_id": "Hole_01",
      "type": "HoleRadius"
    }
  ]
}

Do not wrap in code blocks. Return raw JSON only.
"""
```

---

## 🧪 测试方法

### 测试1: 标准JSON
```bash
python -c "from src.extractor import _parse_json_robust; print(_parse_json_robust('{\"key\": \"value\"}'))"
```

### 测试2: 带注释
```bash
python -c "from src.extractor import _parse_json_robust; print(_parse_json_robust('{\"key\": \"value\" /* comment */}'))"
```

### 测试3: 尾随逗号
```bash
python -c "from src.extractor import _parse_json_robust; print(_parse_json_robust('{\"key\": \"value\",}'))"
```

---

## 🚨 仍然失败？

如果所有策略都失败：

### 方案1: 检查VLM输出
```python
# 在 src/extractor.py 中临时添加
print(f"=== VLM RAW OUTPUT ===")
print(content)
print(f"=== END OUTPUT ===")
```

### 方案2: 降低复杂度
- 使用更简单的图片
- 减少特征数量
- 使用标准格式的图纸

### 方案3: 切换模型
```bash
# .env
OPENAI_MODEL=qwen-vl-max  # 尝试更高级的模型
```

### 方案4: 使用Mock数据
系统会自动降级，确保流程继续：
```python
# 自动触发
except Exception as e:
    print(f"Warning: VLM extraction failed: {e}")
    print("Falling back to mock extraction.")
    return _mock_extraction(resolved_part_id)
```

---

## 📦 相关文件

| 文件 | 修改内容 |
|------|---------|
| `src/extractor.py` | 新增 `_parse_json_robust()` 和 `_clean_json_string()` |
| `requirements.txt` | 新增 `json5>=0.9.14` |

---

## 💡 最佳实践

1. ✅ **安装json5**: `pip install json5`
2. ✅ **使用高质量图片**: 清晰、标准格式
3. ✅ **监控日志**: 查看哪个策略成功
4. ✅ **优化提示词**: 明确要求纯JSON
5. ✅ **接受降级**: Mock数据也能完成流程测试

---

## 📞 技术支持

如果问题持续，请提供：
1. VLM原始输出（前1000字符）
2. 使用的图片类型和大小
3. 完整错误信息

---

**最后更新**: 2026-01-02  
**版本**: v1.0.1

