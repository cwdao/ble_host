# PyQt 迁移快速开始指南

## 已完成的准备工作

✅ **Git 分支已创建**：`feature/pyqt-migration`
✅ **技术选型文档**：`docs/GUI_FRAMEWORK_COMPARISON.md`
✅ **迁移计划**：`MIGRATION_PLAN.md`

## 推荐方案：PySide6

### 为什么选择 PySide6？

1. ✅ **Qt 官方维护**：比 PyQt6 更"官方"
2. ✅ **LGPL 许可证**：商业项目更友好（PyQt6 是 GPL/商业）
3. ✅ **API 相同**：与 PyQt6 几乎完全一样
4. ✅ **性能相同**：基于相同的 Qt6 引擎

### 安装

```bash
pip install -r requirements.txt
```

或者单独安装：
```bash
pip install PySide6>=6.6.0
```

## PyQt5 vs PyQt6 vs PySide6 快速对比

| 框架 | 许可证 | 维护者 | 推荐度 |
|------|--------|--------|--------|
| **PySide6** | LGPL | Qt 官方 | ⭐⭐⭐⭐⭐ |
| PyQt6 | GPL/商业 | Riverbank | ⭐⭐⭐⭐ |
| PyQt5 | GPL/商业 | Riverbank | ⭐⭐⭐ |

**结论：推荐 PySide6**

## Web UI 方案总结

### 可行性：✅ 完全可行

**优势：**
- 跨平台（任何设备有浏览器）
- 现代化 UI（React/Vue）
- 可以远程访问
- 丰富的图表库（ECharts、Plotly.js）

**劣势：**
- 需要浏览器运行
- 打包体积大（Electron）
- 本地性能略低于原生 GUI

**推荐场景：**
- 需要远程访问
- 需要多设备访问
- 团队熟悉 Web 技术栈

**不推荐场景（你的项目）：**
- 本地桌面应用
- 追求最佳性能
- 需要小体积打包

## 下一步行动

### 如果选择 PySide6（推荐）

1. **安装依赖**
   ```bash
   pip install PySide6 matplotlib numpy pyserial
   ```

2. **创建基础文件**
   - `src/main_gui_qt.py` - PyQt 主界面
   - `src/plotter_qt.py` - PyQt 绘图后端
   - `run_qt.py` - PyQt 入口文件

3. **开始迁移**
   - 参考 `src/main_gui.py` 的功能
   - 逐步迁移各个模块

### 如果选择 Web UI

1. **创建新分支**
   ```bash
   git checkout -b feature/web-ui
   ```

2. **技术栈**
   - 后端：FastAPI + WebSocket
   - 前端：Vue 3 + ECharts
   - 打包：Electron（可选）

3. **架构设计**
   ```
   串口数据 → FastAPI 后端 → WebSocket → Vue 前端 → ECharts 图表
   ```

## 代码示例

### PySide6 基础结构

```python
# main_gui_qt.py
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QThread, Signal

class BLEHostGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BLE CS Host")
        # ... 初始化界面
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BLEHostGUI()
    window.show()
    sys.exit(app.exec())
```

### Web UI 基础结构（FastAPI）

```python
# backend.py
from fastapi import FastAPI, WebSocket
import asyncio

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # 串口数据 → WebSocket → 前端
    while True:
        data = await get_serial_data()  # 你的串口读取逻辑
        await websocket.send_json(data)
```

## 建议

**对于你的项目（实时串口数据 + 波形显示）：**

1. **首选：PySide6** ⭐⭐⭐⭐⭐
   - 性能最佳
   - 原生桌面体验
   - 打包简单

2. **备选：Web UI** ⭐⭐⭐⭐
   - 如果需要远程访问
   - 如果团队更熟悉 Web 技术

3. **不推荐：继续 Tkinter** ⭐⭐
   - 性能不足

## 需要帮助？

- 查看 `docs/GUI_FRAMEWORK_COMPARISON.md` 了解详细对比
- 查看 `MIGRATION_PLAN.md` 了解迁移步骤
- 可以让我帮你创建初始的 PySide6 代码结构
