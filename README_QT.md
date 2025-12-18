# PySide6 版本使用说明

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或者参考 `INSTALL.md` 进行详细安装。

### 2. 运行程序

```bash
python run_qt.py
```

---

## 项目结构

### 新增文件

- `src/main_gui_qt.py` - PySide6 主界面（基础框架）
- `src/plotter_qt_realtime.py` - PyQtGraph 实时绘图
- `src/plotter_qt_matplotlib.py` - Matplotlib 分析绘图
- `run_qt.py` - PySide6 版本入口文件

### 保留文件（无需修改）

- `src/serial_reader.py` - 串口读取
- `src/data_parser.py` - 数据解析
- `src/data_processor.py` - 数据处理
- `src/data_saver.py` - 数据保存
- `src/config.py` - 配置管理
- `src/breathing_estimator.py` - 呼吸估计

---

## 当前状态

### ✅ 已完成

- [x] 基础窗口框架
- [x] 连接配置选项卡（基础功能）
- [x] 实时绘图选项卡（6个，使用 PyQtGraph）
- [x] 日志面板
- [x] 版本信息显示

### 🚧 待实现

- [ ] 通道配置选项卡（完整功能）
- [ ] 数据保存选项卡（完整功能）
- [ ] 文件加载选项卡（完整功能）
- [ ] 数据处理面板（频率计算、统计信息等）
- [ ] 呼吸估计选项卡（2x2 子图，使用 Matplotlib）
- [ ] 数据更新逻辑（串口数据 → 绘图）
- [ ] 滑动条（时间窗选择）
- [ ] DPI 管理（Qt 版本）

---

## 开发进度

**当前阶段：** 基础框架搭建完成

**下一步：**
1. 实现数据更新逻辑
2. 完善各个选项卡功能
3. 添加 DPI 支持
4. 性能优化

---

## 测试

### 测试基础功能

```bash
# 运行程序
python run_qt.py

# 应该看到：
# - 主窗口显示
# - 连接配置选项卡
# - 6个实时绘图选项卡（空图表）
# - 日志面板
```

### 测试串口连接

1. 选择串口
2. 选择波特率
3. 点击"连接"按钮
4. 查看日志输出

---

## 与 Tkinter 版本对比

| 功能 | Tkinter 版本 | PySide6 版本 |
|------|-------------|-------------|
| 基础窗口 | ✅ | ✅ |
| 连接配置 | ✅ | ✅（基础） |
| 实时绘图 | ✅ | ✅（PyQtGraph） |
| 数据保存 | ✅ | 🚧 |
| 文件加载 | ✅ | 🚧 |
| 数据处理 | ✅ | 🚧 |
| 呼吸估计 | ✅ | 🚧 |

---

## 注意事项

1. **并行开发**：PySide6 版本在 `feature/pyqt-migration` 分支
2. **不影响原版**：Tkinter 版本（`main` 分支）不受影响
3. **逐步迁移**：功能逐步完善，不急于一次性完成

---

## 问题反馈

如有问题，请查看：
- `docs/MIGRATION_ANALYSIS.md` - 详细分析
- `docs/MIGRATION_SUMMARY.md` - 快速总结
- `INSTALL.md` - 安装指南
