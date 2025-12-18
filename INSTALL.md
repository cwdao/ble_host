# PySide6 迁移 - 安装指南

## 需要安装的包

### 1. 核心 GUI 框架

```bash
pip install PySide6>=6.6.0
```

**说明：**
- PySide6 是 Qt 官方的 Python 绑定
- LGPL 许可证，商业友好
- 包含所有 Qt 组件（QWidget、QMainWindow 等）

---

### 2. 实时绘图库

```bash
pip install pyqtgraph>=0.13.0
```

**说明：**
- 专为 Qt 设计的实时绘图库
- 性能极佳，适合高频数据更新
- 用于实时波形显示

---

### 3. 现有依赖（已安装可跳过）

```bash
# 数据处理
pip install numpy>=1.24.0

# 串口通信
pip install pyserial>=3.5

# 分析绘图（信号处理展示）
pip install matplotlib>=3.7.0

# 图像处理（图标等）
pip install Pillow>=9.0.0

# 打包工具（可选）
pip install pyinstaller>=5.13.0
```

---

## 一键安装

### 方式 1：使用 requirements.txt（推荐）

```bash
pip install -r requirements.txt
```

### 方式 2：手动安装

```bash
# 核心依赖
pip install PySide6>=6.6.0
pip install pyqtgraph>=0.13.0

# 现有依赖（如果还没安装）
pip install pyserial>=3.5
pip install matplotlib>=3.7.0
pip install numpy>=1.24.0
pip install Pillow>=9.0.0
```

---

## 验证安装

### 测试 PySide6

```python
from PySide6.QtWidgets import QApplication, QLabel
import sys

app = QApplication(sys.argv)
label = QLabel("PySide6 安装成功！")
label.show()
sys.exit(app.exec())
```

保存为 `test_pyside6.py`，运行：
```bash
python test_pyside6.py
```

如果看到窗口显示 "PySide6 安装成功！"，说明安装正确。

---

### 测试 PyQtGraph

```python
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
plot_widget = pg.PlotWidget()
plot_widget.plot([1, 2, 3, 4, 5], [1, 4, 9, 16, 25])
plot_widget.show()
sys.exit(app.exec())
```

保存为 `test_pyqtgraph.py`，运行：
```bash
python test_pyqtgraph.py
```

如果看到绘图窗口，说明安装正确。

---

## 安装问题排查

### 问题 1：PySide6 安装失败

**Windows：**
```bash
# 确保使用最新 pip
python -m pip install --upgrade pip
pip install PySide6
```

**如果还是失败，尝试：**
```bash
pip install --only-binary :all: PySide6
```

---

### 问题 2：PyQtGraph 导入错误

```bash
# 确保版本兼容
pip install pyqtgraph>=0.13.0

# 检查依赖
pip install numpy  # PyQtGraph 需要 numpy
```

---

### 问题 3：matplotlib 后端问题

如果 matplotlib 无法使用 Qt 后端：

```bash
# 确保安装了 PySide6
pip install PySide6

# 设置环境变量（可选）
# Windows:
set QT_API=PySide6

# Linux/Mac:
export QT_API=PySide6
```

---

## 版本要求

- **Python**: 3.6+（推荐 3.8+）
- **PySide6**: 6.6.0+
- **PyQtGraph**: 0.13.0+
- **Matplotlib**: 3.7.0+（支持 QtAgg 后端）

---

## 完整安装命令（复制粘贴）

```bash
# 升级 pip
python -m pip install --upgrade pip

# 安装所有依赖
pip install PySide6>=6.6.0 pyqtgraph>=0.13.0 pyserial>=3.5 matplotlib>=3.7.0 numpy>=1.24.0 Pillow>=9.0.0

# 验证安装
python -c "from PySide6.QtWidgets import QApplication; import pyqtgraph; print('安装成功！')"
```

---

## 下一步

安装完成后，可以：

1. **运行测试**：`python run_qt.py`（创建后）
2. **查看文档**：`docs/MIGRATION_ANALYSIS.md`
3. **开始开发**：从 GUI 控件迁移开始
