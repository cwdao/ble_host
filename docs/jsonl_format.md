# JSONL文件格式说明

本文档说明BLE Host应用程序（v3.6.0+）使用的JSONL日志文件格式，用于算法和后处理工作。

## 文件格式概述

- **文件扩展名**：`.jsonl` 或 `.ndjson`
- **编码**：UTF-8
- **格式**：每行一个完整的JSON对象（NDJSON/JSONL格式）
- **优势**：
  - 增量追加写入，避免内存峰值
  - 流式读取，支持大文件处理
  - 崩溃后仍可读取已写入的记录
  - 易于扩展新的记录类型

## 记录类型

每行记录必须包含 `record_type` 字段，用于标识记录类型。支持以下类型：

### 1. meta（元数据记录）

**位置**：文件第一行  
**说明**：会话元数据，记录采集会话的基本信息

**字段说明**：
```json
{
  "record_type": "meta",
  "app_version": "3.6.0",           // 应用程序版本
  "log_version": "1.0",             // 日志格式版本
  "frame_type": "direction_estimation",  // 帧类型：direction_estimation 或 channel_sounding
  "started_at_utc_ns": 1768033917747791700,  // 开始时间（UTC纳秒时间戳）
  "started_at_iso": "2026-01-10T16:31:57.747791",  // 开始时间（ISO格式）
  "file_version": "3.6.0",          // 文件版本（用于兼容性检查）
  "serial_port": "COM7",             // 串口端口（可选）
  "serial_baud": "230400"            // 串口波特率（可选）
}
```

### 2. frame（帧数据记录）

**位置**：文件主体，占绝大多数行  
**说明**：采集的帧数据

#### 方向估计帧（DF）格式

```json
{
  "record_type": "frame",
  "seq": 0,                          // 帧序号
  "t_dev_ms": 18482,                 // 设备相对时间戳（毫秒，从启动开始）
  "t_host_utc_ns": 1768033917750801000,  // 主机绝对时间戳（UTC纳秒）
  "ch": 3,                           // 信道号
  "amp": 132.56,                     // 幅值
  "frame_type": "direction_estimation",  // 帧类型（可选）
  "frame_version": 1                 // 帧版本（可选）
}
```

#### 信道探测帧（CS）格式

```json
{
  "record_type": "frame",
  "seq": 0,                          // 帧序号
  "t_dev_ms": 18482,                 // 设备相对时间戳（毫秒）
  "t_host_utc_ns": 1768033917750801000,  // 主机绝对时间戳（UTC纳秒）
  "channels": {                      // 多信道数据字典
    "0": {
      "amp": 391469.80,              // 幅值
      "phase": 2.1847,               // 相位（弧度）
      "I": 123.45,                   // I分量（可选）
      "Q": 67.89                     // Q分量（可选）
    },
    "4": {
      "amp": 402156.32,
      "phase": 2.2015,
      "I": 125.67,
      "Q": 68.12
    }
    // ... 更多信道
  },
  "frame_type": "channel_sounding"   // 帧类型（可选）
}
```

### 3. event（事件标记记录）

**位置**：任意位置（用户手动标记时写入）  
**说明**：手工标记的特殊事件

```json
{
  "record_type": "event",
  "label": "external_spike",         // 事件标签/名称
  "t_host_utc_ns": 1768033917750801000,  // 标记时间（UTC纳秒）
  "note": "外部干扰",                 // 用户备注（可选）
  "nearest_seq": 123,                // 最近帧序号（可选）
  "nearest_t_dev_ms": 18482          // 最近帧设备时间戳（可选）
}
```

### 4. end（结束记录）

**位置**：文件最后一行（可选）  
**说明**：会话结束统计信息

```json
{
  "record_type": "end",
  "ended_at_utc_ns": 1768033920000000000,  // 结束时间（UTC纳秒）
  "written_records": 10805,          // 写入的记录总数（包括meta、frame、event、end）
  "dropped_records": 0               // 丢弃的记录数（队列满时）
}
```

## 时间戳说明

- **t_dev_ms**：设备相对时间戳，从设备启动开始计算的毫秒数
- **t_host_utc_ns**：主机绝对时间戳，UTC纳秒时间戳，可用于跨设备对齐
- **started_at_utc_ns / ended_at_utc_ns**：会话开始/结束的UTC纳秒时间戳

## 数据读取示例

### Python示例

```python
import json

# 读取meta记录
with open('log.jsonl', 'r', encoding='utf-8') as f:
    first_line = f.readline()
    meta = json.loads(first_line.strip())
    print(f"帧类型: {meta['frame_type']}")
    print(f"开始时间: {meta['started_at_iso']}")

# 流式读取所有frame记录
with open('log.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        record = json.loads(line.strip())
        if record.get('record_type') == 'frame':
            seq = record.get('seq')
            t_dev_ms = record.get('t_dev_ms')
            # 处理帧数据...
```

### 使用DataSaver类（推荐）

```python
from src.data_saver import DataSaver

saver = DataSaver()

# 读取meta
meta = saver.read_meta('log.jsonl')

# 迭代所有记录
for record in saver.iter_records('log.jsonl'):
    if record['record_type'] == 'frame':
        # 处理帧数据
        pass

# 只迭代frame记录
for frame in saver.iter_frames('log.jsonl'):
    seq = frame['seq']
    # 处理帧数据...

# 只迭代event记录
for event in saver.iter_events('log.jsonl'):
    label = event['label']
    # 处理事件...
```

## 字段映射（JSONL → 原始格式）

加载JSONL文件时，程序会自动将记录转换为与旧版JSON格式兼容的结构：

### 方向估计帧（DF）

```python
# JSONL记录
{
  "record_type": "frame",
  "seq": 0,
  "t_dev_ms": 18482,
  "ch": 3,
  "amp": 132.56
}

# 转换为原始格式
{
  "index": 0,              # 从 seq 映射
  "timestamp_ms": 18482,   # 从 t_dev_ms 映射
  "channels": {
    3: {
      "amplitude": 132.56  # 从 amp 映射
    }
  }
}
```

### 信道探测帧（CS）

```python
# JSONL记录
{
  "record_type": "frame",
  "seq": 0,
  "t_dev_ms": 18482,
  "channels": {
    "0": {"amp": 391.47, "phase": 2.18, "I": 123.45, "Q": 67.89}
  }
}

# 转换为原始格式
{
  "index": 0,
  "timestamp_ms": 18482,
  "channels": {
    0: {  # 字符串键转换为整数
      "amplitude": 391.47,
      "phase": 2.18,
      "I": 123.45,
      "Q": 67.89
    }
  }
}
```

## 文件命名规则

- **方向估计帧**：`DF_frames_all_YYYYMMDD_HHMMSS.jsonl`
- **信道探测帧**：`CS_frames_all_YYYYMMDD_HHMMSS.jsonl`
- **最近N帧**：`DF_frames_recent{N}_YYYYMMDD_HHMMSS.jsonl`

## 版本兼容性

- **v3.7.0+**：仅使用JSONL格式保存，支持加载JSONL和JSON格式（JSON仅用于加载旧文件）
- **v3.6.0**：使用JSONL格式保存，支持加载JSONL和JSON格式
- **v3.5.0及以下**：使用JSON格式保存，仍可被新版本加载

## 性能特性

- **增量写入**：每100条记录flush一次（可配置）
- **队列缓冲**：后台线程+队列，避免阻塞UI
- **队列满策略**：队列满时丢弃记录并计数（默认队列大小10000）
- **流式读取**：支持大文件流式读取，内存占用低

## 注意事项

1. **文件完整性**：如果程序异常退出，end记录可能缺失，但已写入的frame记录仍然有效
2. **时间戳对齐**：使用 `t_host_utc_ns` 进行跨设备时间对齐
3. **记录顺序**：记录按写入顺序排列，frame记录的seq字段可能不连续（如果中间有event记录）
4. **容错性**：读取时自动跳过格式错误的行，继续处理后续记录

