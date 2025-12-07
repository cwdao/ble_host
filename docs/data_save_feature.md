# 数据保存功能说明

## 功能概述

本功能允许您将应用程序接收到的帧数据保存到JSON文件中，支持两种保存模式：

1. **保存所有帧**：保存自连接串口以来接收到的所有帧数据
2. **保存最近N帧**：保存最近的N帧数据，N为"显示帧数"参数的值

## 使用方法

### 在GUI中保存数据

1. 确保应用程序处于**帧模式**（帧类型选择为"演示帧"）
2. 连接串口并接收数据
3. 点击顶部控制栏的**"保存数据"**按钮
4. 选择保存模式：
   - **保存所有帧**：保存所有接收到的帧
   - **保存最近N帧**：保存最近的N帧（N为当前"显示帧数"设置）

5. 选择保存路径和文件名
6. 数据将保存为JSON格式

### 保存的文件格式

保存的JSON文件包含以下信息：

```json
{
  "version": "1.0",
  "saved_at": "2023-12-06T12:00:00",
  "total_frames": 100,
  "saved_frames": 50,
  "max_frames_param": 50,
  "frames": [
    {
      "frame": true,
      "index": 0,
      "timestamp_ms": 123456,
      "channels": {
        "0": {
          "amplitude": 1234.56,
          "phase": 0.785,
          "I": 1000.0,
          "Q": 500.0,
          "local_amplitude": 100.0,
          "local_phase": 0.5,
          "remote_amplitude": 200.0,
          "remote_phase": 0.3,
          "il": 1.0,
          "ql": 0.5,
          "ir": 1000.0,
          "qr": 500.0
        },
        ...
      }
    },
    ...
  ]
}
```

### 加载保存的数据

#### 方法1：使用提供的示例脚本

```bash
python examples/load_saved_frames.py <saved_file.json>
```

#### 方法2：在Python脚本中加载

```python
import sys
sys.path.insert(0, 'src')
from data_saver import DataSaver

# 创建保存器实例
saver = DataSaver()

# 加载数据
data = saver.load_frames('frames_all_20231206_120000.json')

if data:
    # 获取帧数据
    frames = data['frames']
    
    # 访问文件信息
    print(f"保存时间: {data['saved_at']}")
    print(f"总帧数: {data['saved_frames']}")
    
    # 遍历帧数据
    for frame in frames:
        index = frame['index']
        timestamp_ms = frame['timestamp_ms']
        channels = frame['channels']
        
        # 遍历通道数据
        for ch, ch_data in channels.items():
            amplitude = ch_data['amplitude']
            phase = ch_data['phase']
            local_amplitude = ch_data['local_amplitude']
            remote_amplitude = ch_data['remote_amplitude']
            # ... 进行您的分析
```

#### 方法3：直接使用JSON

由于保存的是标准JSON格式，您也可以直接使用Python的`json`模块加载：

```python
import json

with open('frames_all_20231206_120000.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

frames = data['frames']
# ... 进行分析
```

## 数据字段说明

### 帧级别字段

- `frame`: 布尔值，标识为帧数据（始终为`true`）
- `index`: 整数，帧索引（从0开始）
- `timestamp_ms`: 整数，时间戳（毫秒）
- `channels`: 字典，包含所有通道的数据

### 通道数据字段

每个通道包含以下字段：

- `amplitude`: 总幅值（合成后的幅值）
- `phase`: 总相位（弧度）
- `I`: I分量（合成后的I）
- `Q`: Q分量（合成后的Q）
- `local_amplitude`: Local幅值
- `local_phase`: Local相位（弧度）
- `remote_amplitude`: Remote幅值
- `remote_phase`: Remote相位（弧度）
- `il`, `ql`, `ir`, `qr`: 原始IQ数据

## 注意事项

1. **帧模式要求**：保存功能仅在帧模式下可用（帧类型为"演示帧"）
2. **内存使用**：保存所有帧会占用更多内存，如果帧数很多，建议使用"保存最近N帧"模式
3. **文件大小**：保存的JSON文件可能较大，特别是保存所有帧时
4. **数据完整性**：保存的数据包含完整的帧信息，可以完全重建原始数据

## 示例：数据分析

以下是一个简单的数据分析示例：

```python
import sys
sys.path.insert(0, 'src')
from data_saver import DataSaver
import numpy as np

# 加载数据
saver = DataSaver()
data = saver.load_frames('frames_all_20231206_120000.json')

if data:
    frames = data['frames']
    
    # 提取某个通道的所有幅值数据
    channel = 0
    amplitudes = []
    indices = []
    
    for frame in frames:
        if channel in frame['channels']:
            ch_data = frame['channels'][channel]
            amplitudes.append(ch_data['amplitude'])
            indices.append(frame['index'])
    
    # 转换为numpy数组进行分析
    amplitudes = np.array(amplitudes)
    indices = np.array(indices)
    
    # 计算统计信息
    print(f"通道{channel}统计:")
    print(f"  均值: {np.mean(amplitudes):.2f}")
    print(f"  标准差: {np.std(amplitudes):.2f}")
    print(f"  最大值: {np.max(amplitudes):.2f}")
    print(f"  最小值: {np.min(amplitudes):.2f}")
```

## 技术实现

- **保存模块**：`src/data_saver.py`
- **数据存储**：`DataProcessor.raw_frames` 列表保存所有原始帧数据
- **文件格式**：JSON（UTF-8编码，带缩进便于阅读）

