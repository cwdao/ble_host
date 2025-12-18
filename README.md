# BLE Host 上位机程序

一个用于BLE嵌入式系统的Python上位机程序，支持串口数据采集、波形显示和数据处理。

**主版本：PySide6 (Qt) 版本** - 现代化的界面，更好的性能和用户体验。

## 功能特性

- ✅ **串口通信**: 支持自动检测串口，可配置波特率（9600~230400）
- ✅ **实时波形显示**: 多变量波形实时绘制，支持自动缩放（基于PyQtGraph，高性能）
- ✅ **数据处理**: 
  - 频率计算（基于FFT，15秒数据窗口）
  - 统计分析（均值、最大值、最小值、标准差）
  - 实时呼吸估计（可配置更新间隔）
- ✅ **文件加载**: 支持加载保存的数据文件，离线分析
- ✅ **友好界面**: 基于PySide6的现代化GUI界面，支持主题切换
- ✅ **日志记录**: 实时日志显示，方便调试
- ✅ **可执行文件**: 支持打包成独立的Windows可执行文件

## 系统要求

- Python 3.7+
- Windows 10/11
- 串口设备（USB转串口适配器或COM端口）

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包括：

- PySide6 - Qt GUI框架
- pyqtgraph - 高性能实时绘图
- matplotlib - 数据分析绘图
- pyserial - 串口通信
- numpy - 数值计算

## 使用方法

### 主版本（PySide6/Qt，推荐）

```bash
python run_qt.py
```

### 旧版本（Tkinter，已弃用）

Tkinter版本仍可使用，但不再维护新功能：

```bash
python run.py
```

> **注意**: 新功能仅在Qt版本中开发，建议使用Qt版本。

---

## 数据协议格式

程序支持两种数据格式：

### 1. JSON格式（推荐）
```
{"var1": 1.23, "var2": 4.56, "var3": 7.89}
```

### 2. 键值对格式
```
VAR1:1.23,VAR2:4.56,VAR3:7.89
```

每条数据应以换行符（`\n`）结尾。

## 打包为可执行文件

### Qt版本打包（推荐）

#### Windows

```bash
build_qt.bat
```

#### Linux/Mac

```bash
chmod +x build_qt.sh
./build_qt.sh
```

生成的可执行文件位于 `dist/BLEHost-Qt-v{版本号}.exe`（Windows）或 `dist/BLEHost-Qt-v{版本号}`（Linux/Mac）

### Tkinter版本打包（旧版）

```bash
build.bat  # Windows
```

### 打包选项说明

- `--clean`: 清理临时文件
- `console=False`: 不显示控制台窗口（GUI模式）
- 可以修改 `build_qt.spec` 文件自定义打包选项
- 版本号会自动从 `config.py` 读取并更新到可执行文件名

## 项目结构

```
ble_host/
├── src/                      # 源代码目录
│   ├── __init__.py
│   ├── main_gui_qt.py        # 主GUI程序（Qt版本，主版本）
│   ├── main_gui.py           # 主GUI程序（Tkinter版本，旧版）
│   ├── serial_reader.py      # 串口读取模块
│   ├── data_parser.py        # 数据解析模块
│   ├── data_processor.py     # 数据处理模块
│   ├── data_saver.py         # 数据保存模块
│   ├── breathing_estimator.py # 呼吸估计模块
│   ├── plotter_qt_realtime.py # Qt实时绘图（PyQtGraph）
│   ├── plotter_qt_matplotlib.py # Qt分析绘图（Matplotlib）
│   └── plotter.py            # Tkinter绘图模块（旧版）
├── run_qt.py                 # Qt版本入口（推荐）
├── run.py                     # Tkinter版本入口（旧版）
├── requirements.txt           # Python依赖
├── build_qt.spec             # Qt版本PyInstaller配置
├── build_qt.bat              # Qt版本Windows打包脚本
├── build_qt.sh               # Qt版本Linux/Mac打包脚本
├── build.spec                # Tkinter版本PyInstaller配置（旧版）
├── build.bat                 # Tkinter版本打包脚本（旧版）
├── README.md                 # 本文档
└── README_QT.md              # Qt版本详细说明
```

## 使用说明

### Qt版本（主版本）

1. **连接串口**:
   - 在"连接配置"选项卡中选择串口和波特率
   - 点击"连接"按钮

2. **配置通道**:
   - 在"通道配置"选项卡中设置要显示的通道
   - 支持间隔选择、范围选择或手动输入

3. **查看波形**:
   - 连接成功后，数据会自动显示在波形选项卡中
   - 支持多个波形选项卡（幅值、相位等）
   - 自动显示最近N帧的数据（可配置）

4. **文件加载**:
   - 在"文件加载"选项卡中选择保存的数据文件
   - 加载后可以使用滑动条选择时间窗口进行分析

5. **呼吸估计**:
   - 在"呼吸估计"选项卡中查看信号处理结果
   - 在右侧控制面板配置参数并点击"Update"
   - 实时模式下会自动定期更新估计结果

6. **数据保存**:
   - 在"数据保存"选项卡中设置保存路径
   - 可以手动保存或启用自动保存

### Tkinter版本（旧版）

参考上述说明，功能类似但界面较旧。

## 帧数据模式

程序支持BLE CS Report帧格式解析：

1. **启用帧模式**：在GUI界面勾选"帧模式"复选框
2. **数据格式**：
   - 帧头：`== Basic Report == index:X, timestamp:Y`
   - IQ数据：`IQ: ch:0:il,ql,ir,qr;ch:1:...` （可能分布在多行）
3. **自动处理**：
   - 程序会自动识别帧头并开始新帧
   - 累积多行的IQ数据
   - 当检测到70个通道或超时500ms时，自动完成帧并转换为幅值
   - 显示各通道的幅值波形（横轴：index，纵轴：amplitude）

## 自定义数据协议

如果需要自定义数据解析格式，修改 `src/data_parser.py` 中的 `parse()` 方法：

```python
def parse(self, text: str) -> Optional[Dict[str, float]]:
    # 在这里实现你的解析逻辑
    # 返回格式: {"变量名": 数值}
    pass
```

## 故障排除

### 串口连接失败
- 检查串口是否被其他程序占用
- 确认波特率设置正确
- 检查串口驱动是否安装

### 数据无法显示
- 检查数据格式是否符合协议要求
- 查看日志窗口的错误信息
- 确认串口数据传输正常

### 打包失败
- 确认已安装所有依赖
- 检查Python版本（需要3.7+）
- 查看PyInstaller的错误信息

## 版本说明

### Qt版本（主版本，推荐）

- **框架**: PySide6
- **绘图**: PyQtGraph（实时）+ Matplotlib（分析）
- **特点**: 现代化界面、高性能、主题支持、完整功能
- **入口**: `run_qt.py`
- **详细说明**: 参见 `README_QT.md`

### Tkinter版本（旧版，已弃用）

- **框架**: Tkinter
- **绘图**: Matplotlib
- **状态**: 不再添加新功能，仅维护基本功能
- **入口**: `run.py`

## 开发说明

### 添加新功能

- **新数据处理算法**: 在 `data_processor.py` 中添加方法
- **新绘图类型**: 
  - 实时绘图：在 `plotter_qt_realtime.py` 中扩展
  - 分析绘图：在 `plotter_qt_matplotlib.py` 中扩展
- **GUI改进**: 修改 `main_gui_qt.py`（Qt版本）

### 日志级别

可以在 `main_gui_qt.py` 中修改日志级别：
```python
logging.basicConfig(level=logging.DEBUG)  # 改为DEBUG查看更多信息
```

## 许可证

本项目仅供学习和开发使用。

## 联系方式

如有问题或建议，请联系开发者。
