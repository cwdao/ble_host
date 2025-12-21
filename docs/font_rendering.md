# Qt 字体渲染优化指南

## 问题描述

在 Qt 应用中，即使指定了字体（如微软雅黑），字体显示仍然可能有锯齿，影响视觉效果。

## 原因分析

### 1. **字体抗锯齿未启用**
- Qt 默认可能不会为所有字体启用抗锯齿
- 需要显式设置字体渲染策略

### 2. **DPI 缩放导致的渲染问题**
- 高 DPI 显示器上，字体缩放可能导致渲染不清晰
- 需要正确设置 DPI 感知和字体平滑缩放

### 3. **字体文件未正确加载**
- 如果使用自定义 TTF 字体，需要正确加载字体文件
- 系统字体可能在不同系统上表现不一致

### 4. **字体渲染提示设置不当**
- 字体提示（hinting）影响小字体的清晰度
- 需要根据字体大小选择合适的提示策略

## 解决方案

### 方案 1：使用系统字体并启用抗锯齿（已实现）

代码中已经实现了 `setup_fonts()` 函数，会自动：
- 启用字体抗锯齿
- 设置字体渲染提示
- 启用平滑缩放

**使用方法：**
```python
# 在 main() 函数中
setup_fonts(app, font_name="Microsoft YaHei", font_size=10)
```

### 方案 2：使用自定义 TTF 字体文件

**步骤 1：准备 TTF 字体文件**
- 将 TTF 字体文件放在 `assets/` 目录下
- 例如：`assets/NotoSansCJK-Regular.ttf`

**步骤 2：在代码中加载字体**
```python
# 在 main() 函数中
setup_fonts(app, font_name="Noto Sans CJK", font_size=10, 
            ttf_path="NotoSansCJK-Regular.ttf")
```

**步骤 3：更新打包配置**
在 `build_qt.spec` 或 `build_qt_onedir.spec` 中，确保字体文件被打包：
```python
datas=[
    ('assets', 'assets'),  # 包含 assets 目录（包括字体文件）
],
```

### 方案 3：使用 QPainter 渲染提示（高级）

对于自定义绘制的控件，可以在 `paintEvent` 中设置渲染提示：

```python
from PySide6.QtGui import QPainter

def paintEvent(self, event):
    painter = QPainter(self)
    # 启用抗锯齿
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # 启用文本抗锯齿
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    # 启用平滑像素图变换
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    
    # 绘制文本
    painter.drawText(rect, text)
```

## 字体选择建议

### Windows 系统推荐字体
- **微软雅黑（Microsoft YaHei）**：中文字体，清晰度好
- **Segoe UI**：英文字体，Windows 默认 UI 字体
- **Consolas**：等宽字体，适合代码显示

### 跨平台推荐字体
- **Noto Sans CJK**：Google 开源字体，支持中日韩文字
- **Source Han Sans**：Adobe 开源字体，中文显示优秀
- **Roboto**：Google 设计，现代感强

### 使用自定义字体的优势
1. **一致性**：在所有系统上显示效果一致
2. **可控性**：可以精确控制字体渲染
3. **美观性**：可以选择更符合设计需求的字体

## 常见问题

### Q1: 为什么设置了字体还是有锯齿？

**可能原因：**
1. 字体抗锯齿未启用
2. DPI 缩放导致的问题
3. 字体文件本身质量不佳

**解决方法：**
- 使用 `setup_fonts()` 函数自动启用抗锯齿
- 检查系统 DPI 设置
- 使用高质量的字体文件

### Q2: 如何验证字体是否正确加载？

**检查方法：**
```python
from PySide6.QtGui import QFontDatabase

# 列出所有可用的字体
font_db = QFontDatabase()
families = font_db.families()
print("可用字体:", families)

# 检查特定字体是否存在
if "Microsoft YaHei" in families:
    print("微软雅黑可用")
```

### Q3: 打包后字体不显示怎么办？

**解决方法：**
1. 确保字体文件在 `datas` 中正确配置
2. 使用绝对路径或 `sys._MEIPASS` 访问字体文件
3. 检查字体文件是否真的被打包进 exe

### Q4: 如何为不同控件设置不同字体？

**示例：**
```python
# 设置全局默认字体
setup_fonts(app, font_name="Microsoft YaHei", font_size=10)

# 为特定控件设置字体
label = QLabel("文本")
label.setFont(QFont("Consolas", 9))  # 等宽字体用于代码

# 为特定控件设置带抗锯齿的字体
custom_font = QFont("Microsoft YaHei", 12)
custom_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
button.setFont(custom_font)
```

## 性能考虑

- **字体加载**：TTF 字体文件通常较大（几 MB），首次加载需要时间
- **内存占用**：加载的字体会占用内存，建议只加载必要的字体
- **渲染性能**：抗锯齿会略微影响渲染性能，但现代硬件影响很小

## 最佳实践

1. **优先使用系统字体**：减少打包体积，启动更快
2. **按需加载自定义字体**：只在必要时加载 TTF 文件
3. **统一字体管理**：使用 `setup_fonts()` 函数统一管理字体设置
4. **测试不同 DPI**：在不同 DPI 设置下测试字体显示效果
5. **提供字体回退**：如果加载自定义字体失败，使用系统字体作为回退

## 代码示例

### 完整示例：使用自定义 TTF 字体

```python
def main():
    app = QApplication(sys.argv)
    
    # 方式 1：使用系统字体（推荐）
    setup_fonts(app, font_name="Microsoft YaHei", font_size=10)
    
    # 方式 2：使用自定义 TTF 字体
    # setup_fonts(app, font_name="Noto Sans CJK", font_size=10, 
    #             ttf_path="NotoSansCJK-Regular.ttf")
    
    window = BLEHostGUI()
    window.show()
    sys.exit(app.exec())
```

### 在控件中设置字体

```python
# 创建带抗锯齿的字体
def create_font(family: str, size: int) -> QFont:
    font = QFont(family, size)
    try:
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    except:
        pass
    return font

# 使用
label.setFont(create_font("Microsoft YaHei", 10))
```

## 参考资源

- [Qt 字体文档](https://doc.qt.io/qt-6/qfont.html)
- [QFontDatabase 文档](https://doc.qt.io/qt-6/qfontdatabase.html)
- [字体渲染最佳实践](https://doc.qt.io/qt-6/qpainter.html#RenderHint-enum)

