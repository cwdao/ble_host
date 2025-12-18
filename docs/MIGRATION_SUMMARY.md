# PySide6 迁移总结

## 快速回答

### 1. 哪些地方需要修改？

**必须修改的文件：**
- ✅ `src/main_gui.py` - 2422 行，大量 Tkinter 控件需要替换
- ✅ `src/plotter.py` - 后端从 TkAgg 改为 QtAgg
- ✅ `src/gui/dpi_manager.py` - 字体系统改为 Qt
- ✅ `run.py` - 入口文件

**无需修改的文件（业务逻辑）：**
- ✅ `src/serial_reader.py`
- ✅ `src/data_parser.py`
- ✅ `src/data_processor.py`
- ✅ `src/data_saver.py`
- ✅ `src/config.py`
- ✅ `src/breathing_estimator.py`
- ✅ `src/utils/signal_algrithom.py`

**修改量估算：**
- GUI 控件：约 2000+ 行
- 绘图后端：约 10-20 行
- DPI 管理：约 20-30 行
- **总计：约 2030-2050 行需要修改**

---

### 2. GUI 控件和 Plot 绘图

**GUI 控件：**
- ✅ **容易替换**：Tkinter → PySide6 有明确的对应关系
- ✅ **工作量可控**：主要是语法转换，逻辑不变
- ✅ **参考文档丰富**：Qt 文档齐全

**Plot 绘图：**
- ⚠️ **需要仔细考虑**：有两种方案可选
- ⚠️ **性能差异大**：不同方案性能差异 5-10 倍

---

### 3. PySide6 是否有类似 matplotlib 的功能？

**答案：PySide6 本身没有绘图库，但可以通过以下方式实现：**

#### 方案 A：Matplotlib + QtAgg 后端 ✅
```python
import matplotlib
matplotlib.use('QtAgg')  # 自动检测 PySide6
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
```
- ✅ 功能完整（所有 matplotlib 功能）
- ✅ 只需改后端，代码几乎不变
- ⚠️ 实时性能一般（适合 <5Hz 更新）

#### 方案 B：PyQtGraph ✅
```python
import pyqtgraph as pg
plot_widget = pg.PlotWidget()
```
- ✅ 实时性能极佳（适合 >10Hz 更新）
- ✅ 专为 Qt 设计
- ⚠️ 功能相对简单，需要学习新 API

#### 方案 C：混合方案 ⭐⭐⭐⭐⭐（推荐）
- **实时波形** → PyQtGraph
- **信号处理展示** → Matplotlib

---

### 4. 实时波形 vs 信号处理后的展示

#### 实时波形显示（高频更新）

**特点：**
- 更新频率：>5Hz（每 200ms 或更快）
- 数据量：持续增长，可能达到数万点
- 需求：流畅、不卡顿

**推荐：PyQtGraph** ⭐⭐⭐⭐⭐
- 性能提升 **5-10 倍**
- 支持滚动窗口
- 可处理百万级数据点

**你的项目中的应用：**
- 6 个实时数据选项卡（幅值、相位等）
- 持续更新，需要流畅体验

---

#### 信号处理后的展示（低频更新）

**特点：**
- 更新频率：低频（用户触发或计算结果）
- 数据量：相对固定
- 需求：功能完整、图表美观

**推荐：Matplotlib + QtAgg** ⭐⭐⭐⭐⭐
- 功能完整（FFT、频谱、子图等）
- 图表美观
- 更新频率低，性能不是问题

**你的项目中的应用：**
- 呼吸估计选项卡（2x2 子图）
- FFT 频谱分析
- 滤波结果展示

---

## 最终推荐方案

### 混合方案 ⭐⭐⭐⭐⭐

**实时波形显示** → **PyQtGraph**
- 6 个实时数据选项卡
- 高频更新，需要流畅

**信号处理展示** → **Matplotlib + QtAgg**
- 呼吸估计选项卡（2x2 子图）
- FFT、频谱分析
- 低频更新

**优势：**
- ✅ 实时性能最佳
- ✅ 功能完整
- ✅ 各取所长

---

## 迁移工作量

### 总工作量：9-14 天（约 2 周）

| 阶段 | 内容 | 时间 |
|------|------|------|
| 阶段 1 | GUI 控件迁移 | 5-7 天 |
| 阶段 2 | 绘图迁移 | 3-5 天 |
| 阶段 3 | DPI 和字体 | 1-2 天 |

---

## 依赖更新

```txt
PySide6>=6.6.0          # GUI 框架
pyqtgraph>=0.13.0        # 实时绘图
matplotlib>=3.7.0        # 分析绘图（已有）
```

---

## 下一步

1. **查看详细分析**：`docs/MIGRATION_ANALYSIS.md`
2. **开始迁移**：从 GUI 控件开始
3. **测试验证**：实时性能和功能完整性

---

## 关键要点

1. ✅ **GUI 控件容易替换**：有明确的对应关系
2. ✅ **绘图需要选择**：实时用 PyQtGraph，分析用 Matplotlib
3. ✅ **业务逻辑无需修改**：模块化设计的好处
4. ✅ **混合方案最佳**：各取所长，最佳体验
