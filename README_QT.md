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
- [x] 连接配置选项卡（完整功能）
- [x] 通道配置选项卡（完整功能：间隔X信道、信道范围、手动输入模式）
- [x] 数据保存选项卡（完整功能：设置保存路径、自动保存、保存数据、清空数据）
- [x] 文件加载选项卡（完整功能：文件选择、加载、信息显示）
- [x] 实时绘图选项卡（6个，使用 PyQtGraph）
- [x] 呼吸估计选项卡（2x2 子图，使用 Matplotlib）
- [x] 数据处理面板（频率计算、统计信息自动更新）
- [x] 数据更新逻辑（串口数据 → 绘图，包括帧模式和非帧模式）
- [x] 日志面板
- [x] 版本信息显示
- [x] Qt版本的打包脚本（build_qt.spec, build_qt.bat, build_qt.sh）

### 🚧 待实现

- [ ] 滑动条（时间窗选择，加载模式下显示）
- [ ] 呼吸估计控制面板（通道选择、数据类型选择、阈值设置等）

---

## 开发进度

**当前阶段：** 核心功能已完成

**已完成：**
1. ✅ 所有主要界面功能已迁移
2. ✅ 数据更新逻辑已实现
3. ✅ 实时绘图功能正常
4. ✅ 打包脚本已创建

**待完善：**
1. 滑动条功能（加载模式下的时间窗选择）
2. 呼吸估计控制面板（可选功能）

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
| 连接配置 | ✅ | ✅ |
| 通道配置 | ✅ | ✅ |
| 实时绘图 | ✅ | ✅（PyQtGraph） |
| 数据保存 | ✅ | ✅ |
| 文件加载 | ✅ | ✅ |
| 数据处理 | ✅ | ✅ |
| 呼吸估计 | ✅ | ✅（Matplotlib） |
| 打包脚本 | ✅ | ✅ |

---

## 打包

### Windows 打包

```bash
build_qt.bat
```

### Linux/Mac 打包

```bash
chmod +x build_qt.sh
./build_qt.sh
```

打包后的可执行文件位于 `dist/` 目录。

## 注意事项

1. **并行开发**：PySide6 版本在 `feature/pyqt-migration` 分支
2. **不影响原版**：Tkinter 版本（`main` 分支）不受影响
3. **功能完整**：核心功能已全部迁移完成
4. **DPI管理**：现代Qt界面自动管理DPI，无需手动处理

---

## 问题反馈

如有问题，请查看：
- `docs/MIGRATION_ANALYSIS.md` - 详细分析
- `docs/MIGRATION_SUMMARY.md` - 快速总结
- `INSTALL.md` - 安装指南
