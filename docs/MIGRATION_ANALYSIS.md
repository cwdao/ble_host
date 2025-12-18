# PySide6 迁移详细分析

## 需要修改的文件和位置

### 1. 核心 GUI 文件（必须修改）

#### `src/main_gui.py` ⚠️ **大量修改**
**当前状态：** 2422 行，大量使用 Tkinter

**需要修改的部分：**

| 行数范围 | 功能 | 修改内容 |
|---------|------|---------|
| 6-7 | 导入语句 | `tkinter` → `PySide6.QtWidgets` |
| 42-2422 | `BLEHostGUI` 类 | 所有 Tkinter 控件替换为 PySide6 |
| 78 | `tk.BooleanVar` | `QCheckBox` 或 `QButtonGroup` |
| 532-538 | 状态栏 | `ttk.Frame` → `QStatusBar` |
| 541-548 | 配置选项卡 | `ttk.Notebook` → `QTabWidget` |
| 551-552 | 左右分栏 | `ttk.PanedWindow` → `QSplitter` |
| 563-650 | 滑动条区域 | `ttk.Scale` → `QSlider` |
| 653 | 绘图选项卡 | `ttk.Notebook` → `QTabWidget` |
| 667-673 | DPI 信息 | `ttk.LabelFrame` → `QGroupBox` |
| 683-717 | 数据处理区域 | `ttk.LabelFrame` → `QGroupBox` |
| 718-722 | 日志区域 | `ttk.LabelFrame` + `scrolledtext` → `QTextEdit` |
| 925 | 绘图器附加 | `plotter.attach_to_tkinter()` → `plotter.attach_to_qt()` |
| 977-980 | 呼吸估计画布 | `FigureCanvasTkAgg` → `FigureCanvasQTAgg` |

**修改量：** 约 2000+ 行需要修改

---

#### `src/plotter.py` ⚠️ **需要修改**
**当前状态：** 298 行，使用 matplotlib + TkAgg 后端

**需要修改的部分：**

| 行数 | 功能 | 修改内容 |
|------|------|---------|
| 7 | 后端设置 | `matplotlib.use('TkAgg')` → `matplotlib.use('QtAgg')` |
| 9 | 导入 | `FigureCanvasTkAgg` → `FigureCanvasQTAgg` |
| 44-48 | `attach_to_tkinter()` | 重命名为 `attach_to_qt()`，修改实现 |
| 69-73 | `draw_idle()` | Qt 后端支持，但 API 略有不同 |

**修改量：** 约 10-20 行

---

#### `src/gui/dpi_manager.py` ⚠️ **需要修改**
**当前状态：** 162 行，使用 `tkinter.font`

**需要修改的部分：**

| 行数 | 功能 | 修改内容 |
|------|------|---------|
| 10 | 导入 | `from tkinter import font` → `from PySide6.QtGui import QFont` |
| 84-91 | `apply_fonts()` | 使用 Qt 的字体系统 |

**修改量：** 约 20-30 行

---

### 2. 业务逻辑文件（无需修改）✅

以下文件**不需要修改**，可以继续使用：

- ✅ `src/serial_reader.py` - 串口读取（纯业务逻辑）
- ✅ `src/data_parser.py` - 数据解析（纯业务逻辑）
- ✅ `src/data_processor.py` - 数据处理（纯业务逻辑）
- ✅ `src/data_saver.py` - 数据保存（纯业务逻辑）
- ✅ `src/config.py` - 配置管理（纯业务逻辑）
- ✅ `src/breathing_estimator.py` - 呼吸估计（纯业务逻辑）
- ✅ `src/utils/signal_algrithom.py` - 信号算法（纯业务逻辑）

**原因：** 这些文件不依赖 GUI 框架，只处理数据和业务逻辑。

---

### 3. 入口文件（需要修改）

#### `run.py` ⚠️ **需要修改**
```python
# 当前
from src.main_gui import main

# 修改为
from src.main_gui_qt import main  # 或创建新的 run_qt.py
```

---

## GUI 控件替换对照表

### 基础控件

| Tkinter | PySide6 | 说明 |
|---------|---------|------|
| `tk.Tk()` | `QApplication` + `QMainWindow` | 主窗口 |
| `ttk.Frame` | `QWidget` / `QFrame` | 容器 |
| `ttk.Label` | `QLabel` | 标签 |
| `ttk.Button` | `QPushButton` | 按钮 |
| `ttk.Entry` | `QLineEdit` | 单行输入 |
| `ttk.Combobox` | `QComboBox` | 下拉框 |
| `ttk.Checkbutton` | `QCheckBox` | 复选框 |
| `ttk.Radiobutton` | `QRadioButton` | 单选按钮 |
| `ttk.Scale` | `QSlider` | 滑动条 |
| `ttk.Notebook` | `QTabWidget` | 选项卡 |
| `ttk.PanedWindow` | `QSplitter` | 分割窗口 |
| `ttk.LabelFrame` | `QGroupBox` | 分组框 |
| `scrolledtext.ScrolledText` | `QTextEdit` | 多行文本 |
| `tk.messagebox` | `QMessageBox` | 消息框 |
| `tk.filedialog` | `QFileDialog` | 文件对话框 |

### 布局管理器

| Tkinter | PySide6 | 说明 |
|---------|---------|------|
| `.pack()` | `QVBoxLayout` / `QHBoxLayout` | 布局 |
| `.grid()` | `QGridLayout` | 网格布局 |
| `.place()` | 绝对定位（不推荐） | 绝对定位 |

### 变量绑定

| Tkinter | PySide6 | 说明 |
|---------|---------|------|
| `tk.StringVar()` | `QLineEdit.text()` / 信号槽 | 字符串变量 |
| `tk.IntVar()` | `QSpinBox.value()` / 信号槽 | 整数变量 |
| `tk.BooleanVar()` | `QCheckBox.isChecked()` / 信号槽 | 布尔变量 |

---

## 绘图方案分析

### 方案对比

#### 方案 1：Matplotlib + QtAgg 后端 ⭐⭐⭐⭐

**优点：**
- ✅ **无需修改绘图逻辑**：只需改后端，API 几乎相同
- ✅ **功能完整**：支持所有 matplotlib 功能
- ✅ **信号处理友好**：适合 FFT、频谱分析等
- ✅ **子图支持好**：2x2 布局等容易实现
- ✅ **文档丰富**：matplotlib 文档齐全

**缺点：**
- ⚠️ **实时性能一般**：对于高频更新（>10Hz）可能卡顿
- ⚠️ **内存占用较大**：matplotlib 较重

**适用场景：**
- ✅ **信号处理后的展示**（FFT、频谱、滤波结果）
- ✅ **静态或低频更新**（<5Hz）
- ✅ **需要复杂图表**（多子图、3D 等）

**代码示例：**
```python
import matplotlib
matplotlib.use('QtAgg')  # 自动检测 PySide6
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

class Plotter:
    def __init__(self):
        self.figure = Figure(figsize=(10, 6))
        self.ax = self.figure.add_subplot(111)
    
    def attach_to_qt(self, parent):
        canvas = FigureCanvasQTAgg(self.figure)
        parent.addWidget(canvas)
        return canvas
```

---

#### 方案 2：PyQtGraph ⭐⭐⭐⭐⭐（实时性能最佳）

**优点：**
- ✅ **实时性能极佳**：专为实时绘图设计
- ✅ **GPU 加速**：支持 OpenGL，可处理百万级数据点
- ✅ **内存占用小**：比 matplotlib 轻量
- ✅ **API 简洁**：专门为实时数据设计

**缺点：**
- ⚠️ **功能相对简单**：不如 matplotlib 功能丰富
- ⚠️ **需要学习新 API**：与 matplotlib 不同
- ⚠️ **子图支持一般**：多子图布局不如 matplotlib 灵活

**适用场景：**
- ✅ **实时波形显示**（高频更新，>10Hz）
- ✅ **大容量数据**（>10万点）
- ✅ **需要流畅动画**

**代码示例：**
```python
import pyqtgraph as pg

class RealTimePlotter:
    def __init__(self):
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setLabel('bottom', 'Frame Index')
        self.curve = self.plot_widget.plot([], [])
    
    def update_data(self, x_data, y_data):
        self.curve.setData(x_data, y_data)  # 非常快！
```

---

#### 方案 3：混合方案 ⭐⭐⭐⭐⭐（推荐）

**策略：**
- **实时波形显示** → 使用 **PyQtGraph**
- **信号处理后的展示** → 使用 **Matplotlib + QtAgg**

**优点：**
- ✅ **各取所长**：实时性能 + 丰富功能
- ✅ **灵活切换**：不同场景用不同库
- ✅ **最佳体验**：实时流畅 + 分析详细

**实现方式：**
```python
# 实时波形选项卡 - 使用 PyQtGraph
from pyqtgraph import PlotWidget

class RealTimePlotTab:
    def __init__(self):
        self.plot_widget = PlotWidget()  # PyQtGraph
        # ... 实时更新逻辑

# 信号处理选项卡 - 使用 Matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

class SignalAnalysisTab:
    def __init__(self):
        self.figure = Figure()
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.figure)
        # ... FFT、频谱分析等
```

---

## 具体场景分析

### 场景 1：实时波形显示（高频更新）

**当前实现：**
- 使用 `Plotter.update_line()` 更新数据
- 刷新频率：约 5Hz（每 200ms 一次）
- 数据量：最多 1000 点/线

**问题：**
- matplotlib 在高频更新时可能卡顿
- `draw_idle()` 虽然非阻塞，但性能有限

**推荐方案：PyQtGraph** ⭐⭐⭐⭐⭐

**原因：**
- 专为实时设计，性能提升 **5-10 倍**
- 支持滚动窗口（自动滚动显示最新数据）
- 可以轻松处理 10 万+ 数据点

**迁移工作量：**
- 需要重写 `Plotter` 类（约 200 行）
- 但 API 更简洁，代码可能更少

---

### 场景 2：信号处理后的展示（FFT、频谱、滤波）

**当前实现：**
- 呼吸估计 tab：2x2 子图布局
- 显示原始数据、滤波结果、FFT 频谱
- 更新频率：低频（用户触发或计算结果）

**推荐方案：Matplotlib + QtAgg** ⭐⭐⭐⭐⭐

**原因：**
- 功能完整，支持复杂图表
- 子图布局灵活（2x2、3x1 等）
- FFT、频谱分析等 matplotlib 有现成函数
- 更新频率低，性能不是问题

**迁移工作量：**
- 只需改后端（`TkAgg` → `QtAgg`）
- 代码几乎不变（约 10 行修改）

---

### 场景 3：多选项卡绘图

**当前实现：**
- 6 个选项卡：幅值、相位、Local/Remote 等
- 每个选项卡一个 `Plotter` 实例
- 使用 `ttk.Notebook` 管理

**推荐方案：混合方案** ⭐⭐⭐⭐⭐

**策略：**
- **实时数据选项卡**（幅值、相位等）→ PyQtGraph
- **分析选项卡**（呼吸估计等）→ Matplotlib

**实现：**
```python
class BLEHostGUI:
    def __init__(self):
        # 实时绘图选项卡 - PyQtGraph
        self.realtime_plotters = {}  # PyQtGraph PlotWidget
        
        # 分析绘图选项卡 - Matplotlib
        self.analysis_plotters = {}  # Matplotlib Figure
        
    def _create_realtime_tab(self, name):
        plot_widget = pg.PlotWidget()  # PyQtGraph
        # ...
    
    def _create_analysis_tab(self, name):
        figure = Figure()  # Matplotlib
        canvas = FigureCanvasQTAgg(figure)
        # ...
```

---

## PySide6 绘图功能总结

### PySide6 本身没有绘图库

**重要：** PySide6 本身**不包含**类似 matplotlib 的绘图功能。

**但可以通过以下方式实现：**

1. **Matplotlib + QtAgg 后端** ✅
   - matplotlib 支持 Qt 后端
   - 自动检测 PySide6
   - 功能完整

2. **PyQtGraph** ✅
   - 专为 Qt 设计
   - 实时性能极佳
   - 需要单独安装

3. **QPainter（Qt 原生）** ⚠️
   - Qt 自带的绘图 API
   - 功能强大但 API 复杂
   - 适合自定义绘图，不适合数据可视化

---

## 推荐方案

### 最终推荐：混合方案 ⭐⭐⭐⭐⭐

**实时波形显示** → **PyQtGraph**
- 6 个实时数据选项卡（幅值、相位等）
- 高频更新（>5Hz）
- 需要流畅体验

**信号处理展示** → **Matplotlib + QtAgg**
- 呼吸估计选项卡（2x2 子图）
- FFT、频谱分析
- 低频更新（用户触发）

**优势：**
- ✅ 实时性能最佳（PyQtGraph）
- ✅ 功能完整（Matplotlib）
- ✅ 各取所长，最佳体验

---

## 迁移工作量估算

### 阶段 1：GUI 控件迁移（5-7 天）

| 模块 | 工作量 | 难度 |
|------|--------|------|
| 主窗口布局 | 1 天 | 中 |
| 配置选项卡 | 1 天 | 中 |
| 数据处理区域 | 1 天 | 中 |
| 日志区域 | 0.5 天 | 低 |
| 文件对话框 | 0.5 天 | 低 |
| 消息框 | 0.5 天 | 低 |
| 滑动条 | 1 天 | 中 |
| 测试调试 | 1.5 天 | 中 |

### 阶段 2：绘图迁移（3-5 天）

| 模块 | 工作量 | 难度 |
|------|--------|------|
| Matplotlib 后端切换 | 0.5 天 | 低 |
| PyQtGraph 实时绘图 | 2 天 | 中 |
| 呼吸估计子图 | 1 天 | 中 |
| 测试调试 | 1.5 天 | 中 |

### 阶段 3：DPI 和字体（1-2 天）

| 模块 | 工作量 | 难度 |
|------|--------|------|
| DPI 管理器迁移 | 1 天 | 中 |
| 字体系统 | 0.5 天 | 低 |
| 测试调试 | 0.5 天 | 低 |

**总工作量：9-14 天（约 2 周）**

---

## 依赖更新

### requirements.txt

```txt
# 现有依赖
pyserial>=3.5
matplotlib>=3.7.0
numpy>=1.24.0
pyinstaller>=5.13.0
Pillow>=9.0.0

# 新增 PySide6
PySide6>=6.6.0

# 新增 PyQtGraph（用于实时绘图）
pyqtgraph>=0.13.0
```

---

## 下一步行动

1. **创建基础结构**
   - `src/main_gui_qt.py` - PySide6 主界面
   - `src/plotter_qt.py` - PyQtGraph 实时绘图
   - `src/plotter_matplotlib.py` - Matplotlib 分析绘图（可选，或复用现有）

2. **逐步迁移**
   - 先迁移 GUI 控件
   - 再迁移绘图功能
   - 最后优化和测试

3. **测试验证**
   - 实时性能测试
   - 功能完整性测试
   - 兼容性测试
