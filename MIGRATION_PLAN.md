# Tkinter → PyQt 迁移计划

## 项目结构规划

### 方案：使用 Git 分支 + 模块化设计

```
ble_host/
├── src/
│   ├── main_gui.py          # Tkinter 版本（保留）
│   ├── main_gui_qt.py       # PyQt 版本（新建）
│   ├── plotter.py           # Tkinter 后端（保留）
│   ├── plotter_qt.py        # PyQt 后端（新建）
│   ├── serial_reader.py     # 共享（无需修改）
│   ├── data_parser.py       # 共享（无需修改）
│   ├── data_processor.py    # 共享（无需修改）
│   └── ...
├── run.py                   # 入口（可切换）
├── run_qt.py                # PyQt 入口（新建）
└── requirements.txt         # 添加 PyQt5/PyQt6
```

## Git 分支策略

### 1. 创建开发分支
```bash
# 从 main 分支创建 PyQt 开发分支
git checkout -b feature/pyqt-migration

# 或者创建独立的开发分支
git checkout -b develop/pyqt
```

### 2. 分支命名建议
- `main` - 当前稳定的 Tkinter 版本
- `feature/pyqt-migration` - PyQt 迁移开发分支
- `develop` - 通用开发分支（可选）

### 3. 工作流程
1. 在 `feature/pyqt-migration` 分支开发 PyQt 版本
2. 定期合并 `main` 分支的业务逻辑更新
3. 测试完成后合并回 `main` 或创建新分支 `pyqt-stable`

## 迁移步骤

### 阶段 1：环境准备（1-2 天）
- [ ] 创建 Git 分支
- [ ] 安装 PyQt5/PyQt6
- [ ] 更新 requirements.txt
- [ ] 创建新的入口文件 `run_qt.py`

### 阶段 2：核心模块迁移（3-5 天）
- [ ] 创建 `plotter_qt.py`（使用 matplotlib + PyQt 后端）
- [ ] 创建 `main_gui_qt.py`（迁移 GUI 布局）
- [ ] 实现串口连接界面
- [ ] 实现数据展示界面

### 阶段 3：功能迁移（5-7 天）
- [ ] 迁移所有选项卡功能
- [ ] 迁移数据处理功能
- [ ] 迁移保存/加载功能
- [ ] 迁移配置管理

### 阶段 4：优化与测试（3-5 天）
- [ ] 性能优化（实时性测试）
- [ ] UI/UX 优化
- [ ] 兼容性测试
- [ ] 文档更新

## 技术要点

### 1. 绘图后端切换
```python
# plotter.py (Tkinter)
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# plotter_qt.py (PyQt)
matplotlib.use('Qt5Agg')  # 或 'Qt6Agg'
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
```

### 2. 线程处理
- PyQt 使用 `QThread` 和信号槽机制
- 比 Tkinter 的 `threading` 更高效
- 避免 GUI 阻塞

### 3. 事件循环
- Tkinter: `root.mainloop()`
- PyQt: `app.exec()` 或 `app.exec_()`

## 依赖管理

### requirements.txt 更新
```txt
# 现有依赖
pyserial>=3.5
matplotlib>=3.7.0
numpy>=1.24.0
pyinstaller>=5.13.0
Pillow>=9.0.0

# 新增 PyQt 依赖（选择其一）
PyQt5>=5.15.0
# 或
PyQt6>=6.4.0
```

## 兼容性考虑

### 1. 双版本共存
- 保留 `main_gui.py` 和 `run.py`（Tkinter 版本）
- 新建 `main_gui_qt.py` 和 `run_qt.py`（PyQt 版本）
- 用户可以选择运行哪个版本

### 2. 配置文件共享
- `config.py` 和 `user_settings.json` 两个版本共用
- 确保数据格式兼容

### 3. 打包配置
- 可以创建两个 `build.spec` 文件
- `build.spec` - Tkinter 版本
- `build_qt.spec` - PyQt 版本

## 风险评估

### 低风险 ✅
- 业务逻辑模块无需修改
- 可以逐步迁移，不影响现有版本

### 中风险 ⚠️
- PyQt 学习曲线（如果团队不熟悉）
- 打包体积可能增大（PyQt 库较大）

### 缓解措施
- 先在分支中开发，不影响主分支
- 保留 Tkinter 版本作为备份
- 充分测试后再合并

## 时间估算

- **总时间**: 12-19 天（约 2-3 周）
- **并行开发**: 可以同时维护两个版本
- **渐进式迁移**: 不需要一次性完成

## 后续计划

1. **短期**（1-2 周）：完成核心功能迁移
2. **中期**（1 个月）：功能完善和优化
3. **长期**（2-3 个月）：根据使用情况决定是否完全替换 Tkinter 版本
