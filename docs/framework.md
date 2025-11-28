# BLE Host 系统架构图

## 模块关系图

```
┌─────────────────────────────────────────────────────────────┐
│                      BLEHostGUI (主控制器)                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  _start_update_loop() - 主循环                         │  │
│  │  _update_frame_plots() - 更新所有选项卡                │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         │              │              │              │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │Serial   │    │Data     │    │Data     │    │Plotter  │
    │Reader   │    │Parser   │    │Processor│    │(×4)     │
    └─────────┘    └─────────┘    └─────────┘    └─────────┘
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
│   - parse()     │  └─> {'index': i, 'iq_data': {...}}
│   - finalize()  │
└──────┬──────────┘
       │ 完整帧数据
       ▼
┌─────────────────┐
│ DataProcessor   │  frame_buffer: Dict
│ - add_frame()   │  └─> {ch: {'amplitude': [...], 'phase': [...]}}
│ - get_range()   │  frame_metadata: List
│                 │  └─> [(index, timestamp_ms), ...]
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
| `data_lines` | `Plotter` | `Dict` | 绘图数据线 |
| `plotters` | `BLEHostGUI` | `Dict` | 所有绘图器实例 |

## 数据格式转换链

```
串口文本
  "== Basic Report == index:123, timestamp:456789"
  "IQ: ch:0:1.0,0.5,1000.0,500.0;ch:1:..."
    ↓
DataParser.parse()
    ↓
current_frame = {
    'index': 123,
    'iq_data': {0: [1.0, 0.5, 1000.0, 500.0], ...}
}
    ↓
DataParser.finalize_frame()
    ↓
frame_data = {
    'frame': True,
    'index': 123,
    'channels': {
        0: {
            'amplitude': 1234.56,  # sqrt(I²+Q²)
            'phase': 0.785,        # atan2(Q, I)
            'I': 1000.0,           # ir*il - qr*ql
            'Q': 500.0             # ir*ql + il*qr
        }
    }
}
    ↓
DataProcessor.add_frame_data()
    ↓
frame_buffer[0]['amplitude'].append((123, 1234.56))
frame_buffer[0]['phase'].append((123, 0.785))
    ↓
DataProcessor.get_frame_data_range(0, 50, 'amplitude')
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

