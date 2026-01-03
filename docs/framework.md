# BLE Host 系统架构图

## 模块关系图

```
┌─────────────────────────────────────────────────────────────┐
│                      BLEHostGUI (主控制器)                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  _start_update_loop() - 主循环                         │  │
│  │  _update_frame_plots() - 更新所有选项卡                │  │
│  │  _update_realtime_breathing_estimation() - 呼吸估计   │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         │              │              │              │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │Serial   │    │Data     │    │Data     │    │Plotter  │
    │Reader   │    │Parser   │    │Processor│    │(×4)     │
    └─────────┘    └─────────┘    └─────────┘    └─────────┘
                            │
                    ┌───────▼────────┐
                    │Breathing       │
                    │Estimator       │
                    └────────────────┘
```

## 数据流向

```
┌──────────────┐
│  串口硬件     │
└──────┬───────┘
       │ 字节流
       ▼
┌─────────────────┐
│  SerialReader   │  data_queue: Queue
│  - get_data()   │  └─> {'timestamp': t, 'text': str}
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│   DataParser    │  current_frame: Dict
│   - parse()     │  └─> {'index': i, 'channels': {...}}
│   - finalize()  │
└──────┬──────────┘
       │ 完整帧数据
       ▼
┌─────────────────┐
│ DataProcessor   │  frame_buffer: Dict
│ - add_frame()   │  └─> {ch: {'amplitude': [...], 'phase': [...]}}
│ - get_range()   │  frame_metadata: List
│                 │  └─> [(index, timestamp_ms), ...]
│                 │  last_frame_channels: Set (DF模式信道切换检测)
└──────┬──────────┘
       │ 查询数据
       ▼
┌─────────────────┐
│    Plotter      │  data_lines: Dict
│  (×4个实例)     │  └─> {'ch0': {line, x_data, y_data}}
│  - update()     │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│  GUI选项卡      │
│  - 幅值         │
│  - 相位         │
│  - I分量        │
│  - Q分量        │
└─────────────────┘
```

## 关键变量位置速查

| 变量名 | 位置 | 类型 | 说明 |
|--------|------|------|------|
| `data_queue` | `SerialReader` | `Queue` | 串口数据队列 |
| `current_frame` | `DataParser` | `Dict` | 正在累积的帧 |
| `frame_buffer` | `DataProcessor` | `Dict` | 已完成的帧数据 |
| `frame_metadata` | `DataProcessor` | `List` | 帧索引和时间戳 |
| `last_frame_channels` | `DataProcessor` | `Set` | 上一个帧的信道集合（用于DF模式信道切换检测） |
| `last_breathing_channel` | `BLEHostGUI` | `int\|None` | 上一次呼吸估计使用的信道（用于检测信道变化） |
| `data_lines` | `Plotter` | `Dict` | 绘图数据线 |
| `plotters` | `BLEHostGUI` | `Dict` | 所有绘图器实例 |

## 数据格式转换链

```
串口文本
  "== Basic Report == index:123, timestamp:456789"  (CS模式)
  或
  "$DF,1,37,123,456789,1234.56"  (DF模式)
    ↓
DataParser.parse()
    ↓
current_frame = {
    'index': 123,
    'channels': {ch: {'amplitude': ..., 'phase': ..., ...}}
}
    ↓
DataProcessor.add_frame_data()
    ↓
frame_buffer[ch]['amplitude'].append((index, amplitude))
frame_buffer[ch]['phase'].append((index, phase))
    ↓
DataProcessor.get_frame_data_range(ch, max_frames, data_type)
    ↓
(indices: [123, 124, ...], values: [1234.56, 1235.12, ...])
    ↓
Plotter.update_frame_data()
    ↓
data_lines['ch0'] = {
    'line': Line2D对象,
    'x_data': [123, 124, ...],
    'y_data': [1234.56, 1235.12, ...]
}
    ↓
GUI显示
```

## DF模式信道切换检测流程

```
接收新帧
    ↓
DataProcessor.add_frame_data(detect_channel_change=True)
    ↓
比较 current_channels 与 last_frame_channels
    ↓
[信道变化?]
    ├─ 是 → 清空新信道的累积数据
    │       ↓
    │   重置呼吸估计状态
    │       ↓
    │   返回 (old_channels, new_channels)
    │       ↓
    │   BLEHostGUI._update_data() 处理
    │       ↓
    │   更新 last_breathing_channel
    │       ↓
    │   显示提示信息
    │       ↓
    │   等待新信道累积足够数据
    │
    └─ 否 → 正常累积数据
            ↓
        更新 last_frame_channels
```

## 多选项卡数据流

```
DataProcessor.frame_buffer
    │
    ├─> get_frame_data_range(ch, max_frames, 'amplitude')
    │   └─> Plotter['amplitude'].update_frame_data()
    │
    ├─> get_frame_data_range(ch, max_frames, 'phase')
    │   └─> Plotter['phase'].update_frame_data()
    │
    ├─> get_frame_data_range(ch, max_frames, 'I')
    │   └─> Plotter['I'].update_frame_data()
    │
    └─> get_frame_data_range(ch, max_frames, 'Q')
        └─> Plotter['Q'].update_frame_data()
```

## 呼吸估计数据流（DF模式）

```
DataProcessor.frame_buffer[channel]
    │
    ├─> get_frame_data_range(channel, display_max_frames, 'amplitude')
    │   ↓
    │   检查数据是否积累到 display_max_frames 帧
    │   ├─ 否 → 显示积累进度，返回
    │   └─ 是 → 继续处理
    │       ↓
    │   BreathingEstimator.process_signal()
    │       ↓
    │   中值滤波 + 高通滤波
    │       ↓
    │   BreathingEstimator.detect_breathing()
    │       ↓
    │   汉宁窗 + FFT + 能量比例计算
    │       ↓
    │   显示呼吸估计结果
```

## 模块职责说明

### SerialReader
- 从串口读取原始字节数据
- 解码为UTF-8文本
- 放入队列供主线程消费

### DataParser
- 解析CS帧格式（多行，包含帧头、IQ数据、帧尾）
- 解析DF帧格式（单行，`$DF,ver,ch,seq,ts,p_avg`）
- 将IQ数据转换为幅值、相位等信息
- 支持帧类型自动识别

### DataProcessor
- 存储帧数据到缓冲区
- 提供数据查询接口
- **DF模式信道切换检测**：
  - 通过 `last_frame_channels` 跟踪上一个帧的信道
  - 检测到信道变化时，清空新信道的累积数据
  - 返回信道变化信息供上层处理
- 提供频率计算、统计分析等功能

### BreathingEstimator
- 信号处理（中值滤波、高通滤波、带通滤波）
- FFT分析和频率估计
- 呼吸检测（能量比例计算）
- 支持CS和DF两种模式的参数配置
- 支持自适应信道选择（CS模式）

### BLEHostGUI
- 协调所有模块
- 实现GUI界面
- 处理用户交互
- **DF模式信道切换处理**：
  - 在 `_update_data()` 中检测信道变化
  - 重置呼吸估计状态
  - 更新 `last_breathing_channel`
  - 显示提示信息
- 在 `_update_realtime_breathing_estimation()` 中：
  - 使用 `data_processor.last_frame_channels` 获取当前最新信道
  - 检查数据是否积累到足够的帧数
  - 执行呼吸估计

### Plotter
- 实时绘图（PyQtGraph）
- 分析绘图（Matplotlib）
- 支持多通道数据显示
- 自动缩放和刷新

## 模式隔离机制

### CS模式（信道探测帧）
- `detect_channel_change=False`
- 在 `_update_realtime_breathing_estimation()` 中手动检测信道变化
- 支持多通道选择
- 支持自适应信道选择

### DF模式（方向估计帧）
- `detect_channel_change=True`
- 在 `add_frame_data()` 中自动检测信道变化
- 自动使用当前帧的实际信道
- 信道切换时自动清空累积数据

两种模式完全隔离，不会互相影响。
