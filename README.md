# BLE Host 上位机程序

一个用于BLE嵌入式系统的Python上位机程序，支持串口数据采集、波形显示和数据处理。

## 功能特性

- ✅ **串口通信**: 支持自动检测串口，可配置波特率（9600~230400）
- ✅ **实时波形显示**: 多变量波形实时绘制，支持自动缩放
- ✅ **数据处理**: 
  - 频率计算（基于FFT，15秒数据窗口）
  - 统计分析（均值、最大值、最小值、标准差）
- ✅ **友好界面**: 基于Tkinter的GUI界面，操作简单
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

或者手动安装：

```bash
pip install pyserial matplotlib numpy
```

## 使用方法

### 方式1: 使用运行脚本（推荐）

```bash
python run.py
```

### 方式2: 直接运行Python脚本

```bash
cd src
python main_gui.py
```

### 方式3: 作为模块运行

```bash
python -m src.main_gui
```

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

### 使用批处理脚本（Windows）

```bash
build.bat
```

### 手动打包

1. 安装PyInstaller：
```bash
pip install pyinstaller
```

2. 执行打包：
```bash
pyinstaller --clean build.spec
```

3. 生成的可执行文件位于 `dist/BLEHost.exe`

### 打包选项说明

- `--clean`: 清理临时文件
- `console=False`: 不显示控制台窗口（GUI模式）
- 可以修改 `build.spec` 文件自定义打包选项

## 项目结构

```
ble_host/
├── src/                  # 源代码目录
│   ├── __init__.py
│   ├── main_gui.py      # 主GUI程序
│   ├── serial_reader.py # 串口读取模块
│   ├── data_parser.py   # 数据解析模块
│   ├── data_processor.py # 数据处理模块
│   └── plotter.py       # 波形绘制模块
├── data_exp/            # 数据实验目录
├── requirements.txt     # Python依赖
├── setup.py            # 安装脚本
├── build.spec          # PyInstaller配置文件
├── build.bat           # Windows打包脚本
└── README.md           # 本文档
```

## 使用说明

1. **连接串口**:
   - 点击"刷新串口"按钮更新可用串口列表
   - 选择正确的串口和波特率
   - 点击"连接"按钮

2. **查看波形**:
   - 连接成功后，数据会自动显示在左侧波形图
   - 支持多变量同时显示
   - 自动显示最近15秒的数据

3. **数据处理**:
   - **频率计算**: 选择变量后点击"计算频率"按钮（需要至少15秒数据）
   - **统计分析**: 点击"计算统计信息"查看各变量的统计信息

4. **清空数据**: 点击"清空数据"按钮清除所有已采集的数据

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

## 开发说明

### 添加新功能

- **新数据处理算法**: 在 `data_processor.py` 中添加方法
- **新绘图类型**: 在 `plotter.py` 中扩展
- **GUI改进**: 修改 `main_gui.py`

### 日志级别

可以在 `main_gui.py` 中修改日志级别：
```python
logging.basicConfig(level=logging.DEBUG)  # 改为DEBUG查看更多信息
```

## 许可证

本项目仅供学习和开发使用。

## 联系方式

如有问题或建议，请联系开发者。
