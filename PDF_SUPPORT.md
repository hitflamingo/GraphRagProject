# PDF支持说明

## 问题

VLM (Qwen) API **不支持直接处理PDF文件**，只支持图像格式（PNG, JPG, WEBP等）。

当您尝试使用PDF文件时，会遇到此错误：
```
openai.BadRequestError: Error code: 400
The image format is illegal and cannot be opened
```

---

## 解决方案

### 方案1：自动PDF转换（推荐）✅

系统已升级支持自动将PDF转换为图像。

#### 1. 安装依赖

```bash
pip install pdf2image Pillow
```

**Windows额外要求**: 安装 Poppler
```bash
# 方法1: 使用conda (推荐)
conda install -c conda-forge poppler

# 方法2: 下载预编译版本
# 访问: https://github.com/oschwartz10612/poppler-windows/releases/
# 下载并解压，将bin目录添加到PATH环境变量
```

**Linux**:
```bash
sudo apt-get install poppler-utils
```

**macOS**:
```bash
brew install poppler
```

#### 2. 重新运行命令

```bash
python -m src.main_agent full-workflow \
  --drawing data/xizi_part_1.PDF \
  --process-card data/xizi_card_1.xlsx \
  --part-id E53234023200-01 \
  --feature-map examples/feature_process_map.json \
  --measurements examples/measurements.json \
  --output results/complete_workflow.json
```

系统会自动：
1. 检测到PDF文件
2. 转换第一页为PNG图像（200 DPI）
3. 发送给VLM API

---

### 方案2：手动转换PDF为图像

如果无法安装pdf2image依赖，可以手动转换：

#### 使用在线工具
- https://www.ilovepdf.com/pdf_to_jpg
- https://smallpdf.com/pdf-to-jpg

#### 使用命令行工具
```bash
# ImageMagick
convert -density 200 data/xizi_part_1.PDF data/xizi_part_1.png

# Ghostscript
gs -dNOPAUSE -sDEVICE=png16m -r200 -o data/xizi_part_1.png data/xizi_part_1.PDF
```

#### 然后使用PNG文件
```bash
python -m src.main_agent full-workflow \
  --drawing data/xizi_part_1.png \  # 使用PNG
  --process-card data/xizi_card_1.xlsx \
  ...
```

---

### 方案3：使用Mock数据（开发测试）

如果只是测试流程，可以暂时跳过VLM：

```bash
python -m src.main_agent full-workflow \
  --drawing data/D53918378200-02-B.png \  # 使用示例PNG
  --process-card data/xizi_card_1.xlsx \
  --part-id E53234023200-01 \
  ...
```

或者让系统自动使用Mock数据：
- 不设置 `OPENAI_API_KEY`
- 系统会自动降级到Mock extraction

---

## 技术细节

### 升级内容

**新增依赖** (`requirements.txt`):
```txt
pdf2image>=1.16.3
Pillow>=10.0.0
```

**代码增强** (`src/extractor.py`):
```python
# 可选导入
try:
    from pdf2image import convert_from_path
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# 自动转换
def _encode_image_to_base64(image_path: Path) -> str:
    if image_path.suffix.lower() == '.pdf':
        # 转换PDF第一页为PNG (200 DPI)
        images = convert_from_path(str(image_path), first_page=1, last_page=1, dpi=200)
        # 临时保存并编码
        ...
    # 正常图像处理
    ...
```

### 支持的格式

| 格式 | 直接支持 | 需要转换 |
|------|---------|---------|
| PNG | ✅ | - |
| JPG/JPEG | ✅ | - |
| WEBP | ✅ | - |
| GIF | ✅ | - |
| PDF | ⚠️ | ✅ (自动) |

### 转换参数

- **页数**: 仅转换第一页（大多数图纸只有一页）
- **DPI**: 200（平衡质量和文件大小）
- **格式**: PNG（无损压缩）
- **临时文件**: 自动清理

---

## 常见问题

### Q1: 安装pdf2image后仍报错

**错误**: `pdf2image.exceptions.PDFInfoNotInstalledError`

**原因**: 缺少Poppler工具

**解决**: 
```bash
# Windows (conda)
conda install -c conda-forge poppler

# 或下载预编译版本并添加到PATH
```

### Q2: 多页PDF如何处理？

**当前**: 只转换第一页

**如需处理多页**:
```python
# 修改 src/extractor.py 中的 _encode_image_to_base64
images = convert_from_path(str(image_path), dpi=200)  # 移除 first_page/last_page
# 处理 images[0], images[1], ... 分别提取
```

### Q3: PDF转换太慢？

**优化方案**:
1. 降低DPI: `dpi=150` 或 `dpi=100`
2. 预先批量转换PDF为PNG
3. 使用缓存机制

```python
# 缓存转换结果
cache_file = image_path.with_suffix('.png')
if not cache_file.exists():
    # 转换并保存
    images[0].save(cache_file, 'PNG')
return cache_file
```

### Q4: 没有安装pdf2image会怎样？

系统会自动降级：
1. 检测到PDF且缺少pdf2image
2. 打印警告信息
3. 自动使用Mock extraction

```
Warning: PDF support not available. Install with: pip install pdf2image Pillow
Falling back to mock extraction.
```

---

## 验证安装

### 测试PDF支持

```python
python -c "from pdf2image import convert_from_path; print('PDF support: OK')"
```

成功输出: `PDF support: OK`

### 测试完整流程

```bash
# 使用PDF文件
python -m src.main_agent ingest-drawing \
  --drawing data/xizi_part_1.PDF \
  --part-id E53234023200-01
```

**期望输出**:
```
[1/5] Extracting features from drawing: data/xizi_part_1.PDF
   Extracted 4 features
   Features stored in graph for part: E53234023200-01
```

---

## 性能对比

| 操作 | PNG文件 | PDF自动转换 |
|------|--------|------------|
| 文件大小 | ~1-5MB | ~10-50MB |
| 加载时间 | ~0.5s | ~2-3s |
| 转换时间 | 0s | ~2-5s |
| VLM调用 | ~10s | ~10s |
| **总时间** | **~10.5s** | **~17s** |

**建议**: 对于频繁使用的图纸，预先转换为PNG以提高性能。

---

## 批量转换脚本

创建 `scripts/convert_pdfs.py`:
```python
from pathlib import Path
from pdf2image import convert_from_path

data_dir = Path("data")
for pdf_file in data_dir.glob("*.PDF"):
    print(f"Converting {pdf_file.name}...")
    images = convert_from_path(str(pdf_file), dpi=200, first_page=1, last_page=1)
    png_file = pdf_file.with_suffix('.png')
    images[0].save(png_file, 'PNG')
    print(f"  → {png_file.name}")
```

运行:
```bash
python scripts/convert_pdfs.py
```

---

**最后更新**: 2026-01-02  
**适用版本**: v1.0.0+

