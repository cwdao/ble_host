# 数据保存功能说明

## 功能概述

本功能允许您将应用程序接收到的帧数据保存到文件中。**v3.6.0+版本**采用JSONL格式（增量写入），支持实时记录和长时间采集。

### 保存模式

1. **增量记录（推荐，v3.6.0+）**：采用JSONL格式，实时追加写入，支持长时间记录
   - 手动控制：点击"开始记录"启动，长按"停止记录"停止
   - 自动模式：勾选"自动开始记录"，连接后自动开始记录
   - 事件标记：记录过程中可随时标记特殊事件
   
2. **批量保存（兼容模式）**：保存所有帧或最近N帧数据到JSON文件
   - 保存所有帧：保存自连接串口以来接收到的所有帧数据
   - 保存最近N帧：保存最近的N帧数据，N为"显示帧数"参数的值

## 使用方法

### 增量记录（JSONL格式，v3.6.0+，推荐）

1. 确保应用程序处于**帧模式**（帧类型选择为"信道探测帧"或"方向估计帧"）
2. 连接串口并接收数据
3. **开始记录**：
   - 点击"开始记录"按钮启动JSONL日志记录
   - 或勾选"自动开始记录"，连接后自动开始记录
4. **记录过程**：
   - 数据实时追加到JSONL文件
   - 可随时点击"标记事件"按钮标记特殊事件（如外部干扰、异常等）
   - 状态栏显示记录状态：`● 正在记录: {文件名}`
5. **停止记录**：
   - 长按"停止记录"按钮1秒（带进度提示）停止记录
   - 停止后状态栏显示：`✓ 已停止向 {文件名} 记录，累计 {帧数} 帧`

### 批量保存（已弃用）

> **注意**：v3.7.0+版本已不再支持批量保存为JSON格式。如需保存数据，请使用增量记录（JSONL格式）功能。

### 文件格式

#### JSONL格式（v3.6.0+，推荐）

JSONL格式采用增量写入，每行一个JSON对象（NDJSON格式）。详细格式说明请参见 `docs/jsonl_format.md`。

**主要特点**：
- 增量追加写入，避免内存峰值
- 支持实时记录，采集过程中自动追加帧到日志
- 流式读取，支持大文件处理
- 崩溃后仍可读取已写入的记录

**记录类型**：
- `meta`：元数据记录（文件第一行）
- `frame`：帧数据记录（占绝大多数行）
- `event`：事件标记记录（用户手动标记）
- `end`：结束记录（文件最后一行，可选）

**示例**：
```jsonl
{"record_type":"meta","app_version":"3.7.0","log_version":"1.0","frame_type":"channel_sounding","started_at_utc_ns":1768033917747791700,"started_at_iso":"2026-01-10T16:31:57.747791","file_version":"3.6.0"}
{"record_type":"frame","seq":0,"t_dev_ms":18482,"t_host_utc_ns":1768033917750801000,"channels":{"0":{"amp":391469.80,"phase":2.1847,"I":123.45,"Q":67.89}},"frame_type":"channel_sounding"}
{"record_type":"frame","seq":1,"t_dev_ms":18502,"t_host_utc_ns":1768033917751002000,"channels":{"0":{"amp":391500.12,"phase":2.1850,"I":123.50,"Q":67.90}},"frame_type":"channel_sounding"}
```

#### JSON格式（旧格式，仅支持加载）

> **注意**：v3.7.0+版本已不再支持新保存JSON格式文件。以下格式说明仅用于加载旧版JSON文件。

旧版JSON文件格式（仅用于加载）：

```json
{
  "version": "3.6.0",
  "saved_at": "2026-01-10T12:00:00",
  "total_frames": 100,
  "saved_frames": 50,
  "max_frames_param": 50,
  "frame_type": "channel_sounding",
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

程序支持自动格式检测，可以加载JSONL和JSON两种格式的文件。

#### 方法1：使用DataSaver类（推荐）

```python
import sys
sys.path.insert(0, 'src')
from data_saver import DataSaver

# 创建保存器实例
saver = DataSaver()

# 加载数据（自动检测格式：JSONL或JSON）
data = saver.load_frames('CS_frames_all_20260110_163157.jsonl')  # 或 .json

if data:
    # 获取帧数据
    frames = data['frames']
    
    # 访问文件信息
    print(f"保存时间: {data['saved_at']}")
    print(f"总帧数: {data['saved_frames']}")
    print(f"帧类型: {data.get('frame_type')}")
    
    # 遍历帧数据
    for frame in frames:
        index = frame['index']
        timestamp_ms = frame['timestamp_ms']
        channels = frame['channels']
        
        # 遍历通道数据
        for ch, ch_data in channels.items():
            amplitude = ch_data['amplitude']
            phase = ch_data.get('phase', 0.0)  # DF模式可能没有phase
            # ... 进行您的分析
```

#### 方法2：直接读取JSONL文件（流式处理）

```python
import json
from data_saver import DataSaver

saver = DataSaver()

# 读取meta记录
meta = saver.read_meta('log.jsonl')
print(f"帧类型: {meta['frame_type']}")
print(f"开始时间: {meta['started_at_iso']}")

# 迭代所有frame记录（流式，内存占用低）
for frame_record in saver.iter_frames('log.jsonl'):
    seq = frame_record.get('seq', 0)
    t_dev_ms = frame_record.get('t_dev_ms', 0)
    # 处理帧数据...
    if 'channels' in frame_record:
        # CS模式：多信道
        for ch_str, ch_data in frame_record['channels'].items():
            amp = ch_data.get('amp', 0.0)
            phase = ch_data.get('phase', 0.0)
    elif 'ch' in frame_record:
        # DF模式：单信道
        ch = frame_record['ch']
        amp = frame_record.get('amp', 0.0)
```

#### 方法3：直接使用JSON（仅适用于旧格式JSON文件）

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

### JSONL格式（v3.6.0+）

1. **增量写入**：采用增量追加写入，避免内存峰值，支持长时间记录（>10000帧）
2. **后台线程**：使用后台线程+队列机制，避免阻塞UI
3. **队列缓冲**：默认队列大小10000，队列满时丢弃记录并计数
4. **文件完整性**：如果程序异常退出，end记录可能缺失，但已写入的frame记录仍然有效
5. **流式读取**：支持大文件流式读取，内存占用低

### JSON格式（已弃用，仅支持加载）

1. **不再支持新保存**：v3.7.0+版本已移除JSON格式的保存功能
2. **仅支持加载**：仍支持加载旧版JSON格式文件，用于分析历史数据
3. **建议迁移**：建议将旧版JSON文件转换为JSONL格式，以获得更好的性能和功能

### 通用注意事项

1. **帧模式要求**：保存功能仅在帧模式下可用（帧类型为"信道探测帧"或"方向估计帧"）
2. **数据完整性**：保存的数据包含完整的帧信息，可以完全重建原始数据
3. **文件命名**：文件自动添加帧类型前缀（DF_/CS_）
4. **版本兼容性**：文件版本不能高于APP版本，否则无法加载

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
- **JSONL写入器**：`LogWriter` 类，支持后台线程+队列的增量写入
- **数据存储**：
  - JSONL格式：实时追加写入，不占用内存
  - JSON格式（已弃用）：不再支持新保存，仅支持加载
- **文件格式**：
  - JSONL：UTF-8编码，每行一个JSON对象（NDJSON格式），v3.6.0+使用
  - JSON：UTF-8编码，带缩进便于阅读（旧格式，仅支持加载）
- **格式检测**：自动检测文件格式（通过扩展名或内容判断）

