# BLE Host 数据流文档

本文档详细说明从帧数据输入到显示的完整数据流程，包括各个模块的输入输出接口、数据存储位置和格式。

## 目录
1. [数据流概览](#数据流概览)
2. [模块详细说明](#模块详细说明)
3. [数据结构定义](#数据结构定义)
4. [关键变量存储位置](#关键变量存储位置)
5. [DF模式信道切换检测流程](#df模式信道切换检测流程)

---

## 数据流概览

```
串口原始数据 (字节流)
    ↓
[SerialReader] 读取并解码
    ↓
文本数据 {'timestamp': float, 'text': str}
    ↓
[DataParser] 解析帧格式
    ↓
帧数据字典 {'frame': True, 'index': int, 'channels': {...}}
    ↓
[DataProcessor] 存储和处理
    ↓
处理后的数据 (numpy数组)
    ↓
[Plotter] 绘制图表
    ↓
GUI显示 (多选项卡)
```

---

## 模块详细说明

### 1. SerialReader (串口读取模块)

**文件位置**: `src/serial_reader.py`

**功能**: 从串口读取原始字节数据，解码为文本，放入队列

#### 输入
- **串口配置**: `port` (串口名), `baudrate` (波特率)
- **原始数据**: 通过 `serial.Serial` 从硬件串口读取的字节流

#### 输出
- **方法**: `get_data(block=False, timeout=None)`
- **返回格式**:
```python
{
    'timestamp': float,  # 接收时间戳（秒）
    'raw': bytes,        # 原始字节数据
    'text': str          # 解码后的文本（UTF-8）
}
```

#### 内部存储
- **变量**: `self.data_queue` (Queue)
- **存储内容**: 上述格式的数据字典队列

#### 关键方法
- `connect()`: 连接串口，启动读取线程
- `get_data()`: 从队列获取数据（非阻塞）
- `_read_loop()`: 后台线程，持续读取串口数据

---

### 2. DataParser (数据解析模块)

**文件位置**: `src/data_parser.py`

**功能**: 解析BLE CS Report帧格式或DF帧格式，将IQ数据转换为幅值、相位等

#### 输入
- **方法**: `parse(text: str)`
- **输入格式**: 文本字符串，包含：
  - **CS模式**: 
    - 帧头: `== Basic Report == index:123, timestamp:456789`
    - IQ数据: `IQ: ch:0:il,ql,ir,qr;ch:1:...;`
    - 帧尾: `== End Report ==`
  - **DF模式**: 
    - 单行: `$DF,<版本>,<通道>,<序号>,<时间戳>,<功率值>`

#### 输出
- **返回格式** (帧模式):
```python
{
    'frame': True,
    'frame_type': 'direction_estimation' | 'channel_sounding',
    'index': int,              # 帧索引
    'timestamp_ms': int,       # 时间戳（毫秒）
    'channels': {
        channel_index: {
            'amplitude': float,  # 幅值: sqrt(I^2 + Q^2) 或 sqrt(p_avg)
            'phase': float,      # 相位（弧度）: atan2(Q, I)
            'I': float,         # I分量: ir*il - qr*ql (CS模式)
            'Q': float,         # Q分量: ir*ql + il*qr (CS模式)
            'p_avg': float,     # 功率值 (DF模式)
            # ... 其他字段
        },
        ...
    }
}
```

#### 内部存储
- **变量**: `self.current_frame` (Dict)
- **存储内容**: 正在累积的帧数据
  ```python
  {
      'index': int,
      'timestamp_ms': int,
      'iq_data': OrderedDict({ch: [il, ql, ir, qr], ...})  # CS模式
      或
      'channels': {ch: {'amplitude': ..., 'p_avg': ...}}  # DF模式
  }
  ```

#### 关键方法
- `parse_frame_header()`: 解析帧头（CS模式）
- `parse_direction_frame()`: 解析DF帧（DF模式）
- `parse_iq_data()`: 解析IQ数据行（CS模式）
- `iq_to_amplitude_phase()`: IQ转幅值相位（CS模式）
- `finalize_frame()`: 完成帧解析，转换为最终格式（CS模式）

#### 数据转换流程
```
原始IQ数据 (il, ql, ir, qr)  # CS模式
    ↓
combine_iq() → (I, Q)
    ↓
iq_to_amplitude_phase() → (amplitude, phase)
    ↓
存储到 channels[ch] 字典

或

DF帧数据 ($DF,ver,ch,seq,ts,p_avg)  # DF模式
    ↓
parse_direction_frame() → amplitude = sqrt(p_avg)
    ↓
存储到 channels[ch] 字典
```

---

### 3. DataProcessor (数据处理模块)

**文件位置**: `src/data_processor.py`

**功能**: 存储帧数据，提供查询、统计、频率计算等功能，支持DF模式信道切换检测

#### 输入
- **方法**: `add_frame_data(frame_data: Dict, detect_channel_change: bool = False)`
- **输入格式**: DataParser输出的帧数据字典
- **参数**:
  - `detect_channel_change`: 是否检测信道变化（DF模式使用）

#### 输出
- **方法**: `get_frame_data_range(channel, max_frames, data_type)`
- **返回格式**: `(indices: np.ndarray, values: np.ndarray)`
  - `indices`: 帧索引数组
  - `values`: 数据值数组（根据data_type）

- **方法**: `add_frame_data()` (当检测到信道变化时)
- **返回格式**: `(old_channels: List[int], new_channels: List[int])` 或 `None`

#### 内部存储

##### 帧数据缓冲区
- **变量**: `self.frame_buffer` (Dict)
- **存储格式**:
```python
{
    channel_index: {
        'amplitude': [(frame_index, amplitude), ...],
        'phase': [(frame_index, phase), ...],
        'I': [(frame_index, I_value), ...],
        'Q': [(frame_index, Q_value), ...],
        'p_avg': [(frame_index, p_avg), ...]  # DF模式
    },
    ...
}
```

##### 帧元数据
- **变量**: `self.frame_metadata` (List)
- **存储格式**: `[(frame_index, timestamp_ms), ...]`
- **用途**: 保持帧的顺序，用于时间戳查找

##### 信道切换检测（DF模式）
- **变量**: `self.last_frame_channels` (Set)
- **存储格式**: `{channel_index, ...}` (上一个帧的信道集合)
- **用途**: 用于检测信道变化

##### 简单数据缓冲区（向后兼容）
- **变量**: `self.data_buffer` (Dict)
- **存储格式**: `{var_name: [(timestamp, value), ...]}`

#### 关键方法

##### 数据存储
- `add_frame_data()`: 添加帧数据到缓冲区
  - 从 `frame_data['channels']` 提取每个通道的数据
  - 存储到 `self.frame_buffer[ch][data_type]`
  - 同时保存元数据到 `self.frame_metadata`
  - **DF模式**: 检测信道变化，清空新信道的累积数据

- `clear_channel_data()`: 清空指定信道的累积数据
  - 用于信道切换时重新开始累积
  - 如果信道不在frame_buffer中，先创建空的数据结构

##### 数据查询
- `get_frame_data_range(channel, max_frames, data_type)`:
  - 从 `self.frame_buffer[channel][data_type]` 获取数据
  - 支持限制帧数（`max_frames`）
  - 返回 `(indices, values)` numpy数组

- `get_all_frame_channels()`: 返回所有有数据的通道号列表

##### 数据分析
- `calculate_channel_frequency()`: 基于FFT计算通道频率
- `get_channel_statistics()`: 计算统计信息（均值、最大值等）

---

### 4. Plotter (绘图模块)

**文件位置**: `src/plotter_qt_realtime.py` (实时绘图), `src/plotter_qt_matplotlib.py` (分析绘图)

**功能**: 使用PyQtGraph或Matplotlib绘制实时波形图

#### 输入
- **方法**: `update_frame_data(channel_data, max_channels)`
- **输入格式**:
```python
{
    channel_index: (indices: np.ndarray, values: np.ndarray),
    ...
}
```

#### 输出
- **方法**: `attach_to_qt(parent)` → 返回Qt widget
- **显示**: PyQtGraph或Matplotlib图表（嵌入到GUI中）

#### 内部存储
- **变量**: `self.data_lines` (Dict)
- **存储格式**:
```python
{
    'ch0': {
        'line': Line2D对象,
        'x_data': [frame_index, ...],
        'y_data': [value, ...]
    },
    ...
}
```

#### 关键方法
- `update_line()`: 更新单条数据线
- `update_frame_data()`: 批量更新多个通道的数据
- `refresh()`: 刷新画布显示
- `_auto_scale_axes()`: 自动调整坐标轴范围

---

### 5. BLEHostGUI (主界面模块)

**文件位置**: `src/main_gui_qt.py`

**功能**: 协调所有模块，实现GUI界面

#### 数据流控制

##### 更新循环 (`_update_data()`)
```python
while True:
    # 1. 从串口获取数据
    data = serial_reader.get_data(block=False)
    
    # 2. 解析数据
    parsed = data_parser.parse(data['text'])
    
    # 3. 如果是完整帧，存储到处理器
    if parsed and parsed.get('frame'):
        # DF模式：检测信道变化
        cleared_channels = data_processor.add_frame_data(
            parsed, 
            detect_channel_change=is_direction_estimation_mode
        )
        
        # 如果检测到信道变化，处理状态重置
        if cleared_channels and is_direction_estimation_mode:
            # 重置呼吸估计状态
            # 更新last_breathing_channel
            # 显示提示信息
        
        _update_frame_plots()  # 更新所有选项卡
    
    # 4. 刷新显示
    _refresh_all_plotters()
```

##### 绘图更新 (`_update_frame_plots()`)
```python
# 对每个选项卡（幅值、相位、I、Q）
for tab_key, plotter_info in self.plotters.items():
    data_type = plotter_info['data_type']
    plotter = plotter_info['plotter']
    
    # 获取该类型的数据
    channel_data = {}
    for ch in display_channels:
        indices, values = data_processor.get_frame_data_range(
            ch, max_frames, data_type
        )
        channel_data[ch] = (indices, values)
    
    # 更新绘图
    plotter.update_frame_data(channel_data)
```

##### 呼吸估计更新 (`_update_realtime_breathing_estimation()`)
```python
# DF模式：使用data_processor.last_frame_channels获取当前最新信道
if is_direction_estimation_mode:
    channel = list(data_processor.last_frame_channels)[0]
    
    # 获取数据
    indices, values = data_processor.get_frame_data_range(
        channel, max_frames=display_max_frames, data_type=data_type
    )
    
    # 检查数据是否积累到足够的帧数
    if len(values) < display_max_frames:
        # 显示积累进度
        return
    
    # 执行呼吸估计
    processed = breathing_estimator.process_signal(values)
    detection = breathing_estimator.detect_breathing(processed['highpass_filtered'])
    # 显示结果
```

#### 多选项卡结构
- **变量**: `self.plotters` (Dict)
- **存储格式**:
```python
{
    'amplitude': {
        'plotter': Plotter实例,
        'data_type': 'amplitude',
        'frame': QWidget
    },
    'phase': {...},
    'I': {...},
    'Q': {...}
}
```

---

## 数据结构定义

### 帧数据完整格式

```python
frame_data = {
    'frame': True,                    # 标识为帧数据
    'frame_type': 'direction_estimation' | 'channel_sounding',
    'index': 123,                     # 帧索引（从0开始）
    'timestamp_ms': 456789,          # 时间戳（毫秒）
    'channels': {
        0: {
            'amplitude': 1234.56,     # 幅值
            'phase': 0.785,           # 相位（弧度，CS模式）
            'I': 1000.0,              # I分量（CS模式）
            'Q': 500.0,               # Q分量（CS模式）
            'p_avg': 1234.56,         # 功率值（DF模式）
            # ... 其他字段
        },
        1: {...},
        ...
    }
}
```

### 数据处理器存储格式

```python
# frame_buffer 结构
frame_buffer = {
    0: {
        'amplitude': [(0, 1234.56), (1, 1235.12), ...],
        'phase': [(0, 0.785), (1, 0.790), ...],
        'I': [(0, 1000.0), (1, 1001.0), ...],
        'Q': [(0, 500.0), (1, 501.0), ...],
        'p_avg': [(0, 1234.56), (1, 1235.12), ...]  # DF模式
    },
    1: {...},
    ...
}

# frame_metadata 结构
frame_metadata = [
    (0, 456789),  # (frame_index, timestamp_ms)
    (1, 457239),
    ...
]

# last_frame_channels 结构（DF模式）
last_frame_channels = {37}  # 上一个帧的信道集合
```

---

## 关键变量存储位置

### 原始数据
- **位置**: `SerialReader.data_queue` (Queue)
- **格式**: `{'timestamp': float, 'text': str}`

### 解析中的帧数据
- **位置**: `DataParser.current_frame` (Dict)
- **格式**: `{'index': int, 'timestamp_ms': int, 'iq_data': OrderedDict}` (CS模式)
  或 `{'index': int, 'timestamp_ms': int, 'channels': {...}}` (DF模式)

### 已完成的帧数据
- **位置**: `DataProcessor.frame_buffer` (Dict)
- **格式**: `{channel: {'amplitude': [...], 'phase': [...], ...}}`

### 帧元数据
- **位置**: `DataProcessor.frame_metadata` (List)
- **格式**: `[(index, timestamp_ms), ...]`

### 信道切换检测（DF模式）
- **位置**: `DataProcessor.last_frame_channels` (Set)
- **格式**: `{channel_index, ...}` (上一个帧的信道集合)

### 呼吸估计信道跟踪
- **位置**: `BLEHostGUI.last_breathing_channel` (int | None)
- **格式**: 上一次呼吸估计使用的信道

### 绘图数据
- **位置**: `Plotter.data_lines` (Dict)
- **格式**: `{'ch0': {'line': Line2D, 'x_data': [...], 'y_data': [...]}}`

### GUI绘图器
- **位置**: `BLEHostGUI.plotters` (Dict)
- **格式**: `{'amplitude': {'plotter': Plotter, 'data_type': 'amplitude', ...}}`

---

## DF模式信道切换检测流程

### 检测流程

```
接收新帧
    ↓
DataProcessor.add_frame_data(detect_channel_change=True)
    ↓
提取当前帧的信道: current_channels = set(channels.keys())
    ↓
比较: current_channels != last_frame_channels?
    ├─ 是 → 信道发生变化
    │       ↓
    │   清空新信道的累积数据
    │   clear_channel_data(ch) for ch in current_channels
    │       ↓
    │   返回 (old_channels, new_channels)
    │       ↓
    │   BLEHostGUI._update_data() 处理
    │       ↓
    │   重置呼吸估计状态
    │   breathing_estimator.reset_adaptive_state()
    │       ↓
    │   更新 last_breathing_channel = new_channel
    │       ↓
    │   显示提示信息
    │   "⚠️ 信道已切换: old -> new"
    │   "等待数据积累: 0/1000 帧"
    │
    └─ 否 → 正常累积数据
            ↓
        更新 last_frame_channels = current_channels
```

### 呼吸估计流程（DF模式）

```
_update_realtime_breathing_estimation()
    ↓
获取当前最新信道: channel = list(data_processor.last_frame_channels)[0]
    ↓
获取数据: indices, values = get_frame_data_range(channel, display_max_frames, 'amplitude')
    ↓
检查数据是否积累到足够的帧数: len(values) < display_max_frames?
    ├─ 是 → 显示积累进度，返回
    │   "数据积累中: X/1000 帧"
    │
    └─ 否 → 执行呼吸估计
            ↓
        BreathingEstimator.process_signal(values)
            ↓
        中值滤波 + 高通滤波
            ↓
        BreathingEstimator.detect_breathing(processed['highpass_filtered'])
            ↓
        汉宁窗 + FFT + 能量比例计算
            ↓
        显示呼吸估计结果
```

### 关键点

1. **信道切换检测时机**: 在 `add_frame_data()` 中，每次添加新帧时检测
2. **数据清空**: 检测到信道变化时，立即清空新信道的所有累积数据
3. **状态重置**: 重置呼吸估计状态，确保重新开始累积
4. **显示更新**: 使用 `data_processor.last_frame_channels` 获取当前最新信道，而不是 `all_channels[0]`
5. **数据积累**: 必须积累到 `display_max_frames` 帧（默认1000帧）后才能开始呼吸估计

---

## 数据查询示例

### 获取通道0的最近50帧幅值数据
```python
indices, amplitudes = data_processor.get_frame_data_range(
    channel=0,
    max_frames=50,
    data_type='amplitude'
)
```

### 获取通道5的相位数据
```python
indices, phases = data_processor.get_frame_data_range(
    channel=5,
    max_frames=None,  # 全部数据
    data_type='phase'
)
```

### 计算通道3的频率
```python
freq = data_processor.calculate_channel_frequency(
    channel=3,
    max_frames=100,
    data_type='amplitude'
)
```

---

## 数据流时序图

```
时间轴 →
┌─────────┐
│ 串口硬件 │ → 字节流
└────┬────┘
     │
┌────▼─────────┐
│ SerialReader │ → {'timestamp': t, 'text': "..."}
└────┬─────────┘
     │
┌────▼─────────┐
│  DataParser  │ → 累积IQ数据到 current_frame (CS模式)
│              │ → 直接解析为帧数据 (DF模式)
└────┬─────────┘
     │ (帧完成时)
┌────▼─────────┐
│ DataProcessor│ → 存储到 frame_buffer[ch][data_type]
│              │ → 检测信道变化 (DF模式)
│              │ → 清空新信道数据 (如果信道变化)
└────┬─────────┘
     │
┌────▼─────────┐
│   Plotter    │ → 更新 data_lines，绘制图表
└────┬─────────┘
     │
┌────▼─────────┐
│     GUI      │ → 显示在选项卡中
└──────────────┘
```

---

## 注意事项

1. **帧完成条件**:
   - **CS模式**: 检测到新帧头时，自动完成上一帧；或检测到帧尾时完成
   - **DF模式**: 单行格式，每行都是一个完整的帧
   - 超时（500ms无新数据）时，完成当前帧（CS模式）

2. **数据同步**:
   - 所有选项卡共享同一个 `DataProcessor` 实例
   - 每个选项卡有独立的 `Plotter` 实例
   - 更新时同时刷新所有选项卡

3. **内存管理**:
   - `Plotter` 限制每条线最多1000个点（`max_points`）
   - 可通过 `display_max_frames` 限制显示的帧数

4. **数据类型**:
   - `amplitude`: 幅值（总是正数）
   - `phase`: 相位（弧度，范围 -π 到 π，CS模式）
   - `I`, `Q`: I/Q分量（可正可负，CS模式）
   - `p_avg`: 功率值（DF模式）

5. **模式隔离**:
   - CS模式和DF模式完全隔离，不会互相影响
   - CS模式：`detect_channel_change=False`，手动检测信道变化
   - DF模式：`detect_channel_change=True`，自动检测信道变化

---

## 扩展说明

### 添加新的数据类型
1. 在 `DataParser.finalize_frame()` 中添加计算逻辑
2. 在 `DataProcessor.add_frame_data()` 中添加存储逻辑
3. 在 `BLEHostGUI._create_plot_tabs()` 中添加新选项卡

### 修改显示通道
- 通过GUI界面修改 `display_channel_list`
- 调用 `_apply_frame_settings()` 应用设置
- **注意**: `display_channel_list` 仅用于显示，不影响实际的信道切换检测

### 修改显示帧数
- 通过GUI界面修改 `display_max_frames`
- 调用 `_apply_frame_settings()` 应用设置
- **DF模式**: 默认1000帧，可在通道配置中修改
