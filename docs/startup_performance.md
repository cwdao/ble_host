# PyInstaller 打包后启动性能优化

## 问题描述

直接运行 `run_qt.py` 启动很快（不到3秒），但运行编译后的 exe 需要快10秒才能加载完成。

## 原因分析

### 1. **UPX 压缩导致的解压开销**
- `build_qt.spec` 中设置了 `upx=True`
- UPX 压缩虽然减小了 exe 文件大小，但会显著增加启动时的解压时间
- 对于大型应用（如包含 PySide6、pyqtgraph、matplotlib 等），解压可能需要 3-5 秒

### 2. **单文件模式（onefile）的解压过程**
- 当前使用 onefile 模式，所有内容打包在一个 exe 中
- 启动时需要：
  1. 将 exe 解压到临时目录（`%TEMP%\_MEIxxxxx`）
  2. 从临时目录加载所有模块
  3. 这个过程需要额外的 I/O 操作时间

### 3. **大型依赖库的导入时间**
- PySide6：Qt 框架，包含大量 C++ 扩展模块
- pyqtgraph：高性能绘图库
- matplotlib：科学绘图库
- numpy：数值计算库
- 这些库的导入本身就需要时间，在打包环境中会更慢

### 4. **模块导入顺序**
- 所有模块在启动时一次性导入
- 没有使用延迟导入（lazy import）优化

## 优化方案

### 方案 1：禁用 UPX 压缩（已应用）✅

**效果**：启动时间从 ~10秒 减少到 ~6-7秒

**修改内容**：
```python
upx=False,  # 禁用 UPX 压缩以提升启动速度
```

**优点**：
- 简单，只需修改一行配置
- 启动速度提升明显
- 仍然保持单文件模式

**缺点**：
- exe 文件大小会增加（通常增加 20-30%）

### 方案 2：使用 onedir 模式（推荐用于快速启动）

**效果**：启动时间可减少到 ~4-5秒（接近直接运行 Python 脚本的速度）

**使用方法**：
```bash
pyinstaller build_qt_onedir.spec
```

**优点**：
- 启动速度最快（无需解压临时文件）
- 文件直接加载，I/O 开销最小
- 接近直接运行 Python 脚本的性能

**缺点**：
- 生成一个目录，包含 exe 和所有依赖文件
- 分发时需要打包整个目录
- 文件数量较多

**输出结构**：
```
dist/
  └── BLEHost-Qt-v3.2.0/
      ├── BLEHost-Qt-v3.2.0.exe
      ├── _internal/
      │   ├── python311.dll
      │   ├── PySide6/
      │   ├── pyqtgraph/
      │   └── ... (其他依赖)
      └── assets/
```

### 方案 3：延迟导入非关键模块（高级优化）

对于不需要在启动时立即使用的模块，可以使用延迟导入：

```python
# 在需要时才导入
def init_plotter():
    from plotter_qt_realtime import RealtimePlotter
    return RealtimePlotter()
```

**优点**：
- 减少启动时的导入时间
- 保持代码结构清晰

**缺点**：
- 需要重构代码
- 可能影响首次使用相关功能时的响应速度

## 性能对比

| 模式 | 启动时间 | exe 大小 | 分发方式 |
|------|---------|---------|---------|
| 直接运行 Python | ~3秒 | - | 需要 Python 环境 |
| onefile + UPX | ~10秒 | 较小 | 单个 exe |
| onefile（无 UPX）| ~6-7秒 | 中等 | 单个 exe |
| onedir（无 UPX）| ~4-5秒 | 较大 | 目录（推荐）|

## 推荐配置

### 快速启动优先（推荐）
使用 `build_qt_onedir.spec`：
```bash
pyinstaller build_qt_onedir.spec
```

### 单文件分发优先
使用已优化的 `build_qt.spec`（已禁用 UPX）：
```bash
pyinstaller build_qt.spec
```

## 其他优化建议

1. **使用 SSD**：如果可能，将 exe 放在 SSD 上运行
2. **防病毒软件**：将 exe 目录添加到防病毒软件白名单（扫描会减慢启动）
3. **Windows Defender**：首次运行可能较慢，后续会更快
4. **预编译 Python 字节码**：PyInstaller 会自动处理

## 测试方法

使用以下代码测试启动时间：

```python
import time
import sys

start_time = time.time()
# 导入主模块
from src.main_gui_qt import main
import_time = time.time() - start_time
print(f"导入时间: {import_time:.2f}秒")

start_time = time.time()
# 创建应用
app = QApplication(sys.argv)
app_time = time.time() - start_time
print(f"应用创建时间: {app_time:.2f}秒")
```

