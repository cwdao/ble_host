# DIP 直接 IQ 二进制帧（上位机接入说明）

本文档说明 BLE Host 上位机如何接收、解析并可视化下位机 **DIP 二进制 UART 帧（协议 v2）**。  
下位机协议原文见 nRF 工程目录中的 `doc/DIP_binary_protocol.md`、`doc/DIP_binary_pc_parser.md`。

---

## 1. 功能概述

| 项目 | 说明 |
|------|------|
| GUI 帧类型名称 | **DIP-直接IQ输出** |
| 内部 `frame_type` | `dip_direct_iq` |
| 保存文件前缀 | `DIP_`（如 `DIP_frames_all_20260519_120000.jsonl`） |
| 与 CS 的关系 | 帧内为多信道 IQ，**后续绘图、呼吸估计、JSONL 记录与「信道探测帧」共用流程** |
| 与 ASCII CS 的差异 | 串口为**纯二进制**（`0x55 0xAA` 同步），非 `== Basic Report ==` 文本 |

---

## 2. 数据流架构

```
下位机 (DIP_REPORT_BINARY_OUTPUT=1)
    │ uart_poll_out / dip_uart_tx 线程
    ▼
PC 串口 (8N1, 通常 115200)
    ▼
SerialReader (binary_frame_mode=True)
    │ DipBinaryFrameReader.feed(chunk)
    ▼
dip_binary_parser.parse_raw_frame(frame_bytes)
    ▼
统一帧 dict { frame, frame_type, index, channels{...} }
    ▼
DataProcessor → Plotter / BreathingEstimator / DataSaver
```

相关源码：

| 文件 | 职责 |
|------|------|
| `src/dip_binary_parser.py` | 协议解析、CRC、bitmap、转统一帧结构 |
| `src/serial_reader.py` | 二进制模式下组帧入队 |
| `src/main_gui_qt.py` | 帧类型选择、`_update_data` 分支、保存/加载 |
| `src/data_saver.py` | `DIP_` 前缀、`dip_direct_iq` 元数据 |

---

## 3. 协议摘要（v2）

### 3.1 帧结构

```
偏移   长度    字段
0      1       sync1 = 0x55
1      1       sync2 = 0xAA
2      1       version = 0x01
3      1       type = 0x01 (DIP IQ)
4      2       payload_len (LE)
6      2       procedure_counter (LE)
8      1       ap
9      1       iq_format (0 = int16)
10     1       channel_count N
11     1       reserved
12     10      channel_bitmap[10]
22     4×N     IQ: 按 ch 升序，每信道 int16 i + int16 q
22+4N  2       crc16 (LE, CRC16-CCITT)
```

- 整帧长度：`22 + 4×N + 2` 字节  
- `payload_len = 16 + 4×N`（从 `procedure_counter` 起到 IQ 末字节，**不含** sync 与 CRC）  
- CRC 覆盖：从 **sync1** 到 IQ 区最后一字节  

### 3.2 信道位图

- 10 字节 = 80 bit，有效 FFT 信道 `ch ∈ [0, 74]`  
- `channel_bitmap[ch/8]` 的 bit `(ch%8)` 为 1 表示该信道有 IQ  
- `channel_count` 必须等于位图中 1 的个数  

### 3.3 与 HCI 信道

固件侧：`fft_ch = hci_channel - 2`（`DIP_CS_CHANNEL_INDEX_OFFSET`）。  
上位机按 **bitmap 中的 fft 下标** 作为 `channels` 字典的 key，与旧版 CS 显示信道编号一致。

---

## 4. 上位机使用步骤

### 4.1 固件建议配置

```c
#define DIP_REPORT_BINARY_OUTPUT  1
#define DIP_BINARY_USE_THREAD     1
#define DIP_REPORT_LOG_VERBOSE    0   // 减少 ASCII 日志，避免干扰 0x55 0xAA
```

并在 `prj.conf` 中适当降低 `CONFIG_LOG` 级别。

### 4.2 上位机操作

1. 运行 `python run_qt.py`  
2. **连接配置** → 帧类型选择 **DIP-直接IQ输出**  
3. 波特率与固件一致（DK 默认 console 多为 **115200**）  
4. 连接串口 → 幅值/相位等 Tab 与 CS 模式相同  

### 4.3 保存与加载

- 记录/保存时 meta 中 `frame_type` 为 `dip_direct_iq`  
- 加载此类文件会自动切回 **DIP-直接IQ输出** 模式  
- 旧版 `channel_sounding` / `direction_estimation` 文件不受影响  

---

## 5. 统一帧字段说明（`dip_direct_iq`）

解析后每帧示例：

```python
{
    "frame": True,
    "frame_type": "dip_direct_iq",
    "index": 100,           # procedure_counter
    "timestamp_ms": 100,    # 同 index（DIP 无独立 ms 时间戳）
    "ap": 0,
    "channels": {
        3: {
            "amplitude": 111.8,
            "phase": -0.46,
            "I": 100.0, "Q": -50.0,
            "local_amplitude": 111.8,
            "local_phase": -0.46,
            "remote_amplitude": 0.0,
            "remote_phase": 0.0,
            "il": 100.0, "ql": -50.0, "ir": 0.0, "qr": 0.0,
        },
        ...
    },
}
```

说明：

- DIP 仅下发**本地** IQ，故 `ir/qr` 与 remote 幅相为 0  
- 呼吸估计默认参数与 **信道探测帧** 相同（采样率 2 Hz 等）  

---

## 6. 故障排除

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| 无波形 | 帧类型未选 DIP；波特率错误 | 确认 GUI 与 `prj.conf` 波特率 |
| 偶发无帧 | 串口混有 `LOG_INF` ASCII | `DIP_REPORT_LOG_VERBOSE=0`，降低日志级别 |
| CRC 失败 / 搜不到帧 | 帧边界错位 | 重连；检查是否有其他工具占用串口 |
| 队列积压 | 固件发送快于 PC 处理 | 增大固件 `DIP_BIN_MSGQ_DEPTH` 或降低 procedure 率 |

独立验证可用下位机脚本：

```bash
python doc/dip_parse_uart.py COM3
```

---

## 7. 版本与兼容性

- 协议 `version = 0x01`，`type = 0x01`  
- 上位机自 **v4.0.0** 起正式支持；与 ASCII CS/DF 帧类型**互斥**（同一串口连接只应选一种帧类型）  
- 切换「DIP-直接IQ输出」↔ 文本帧类型时会清空 `DataParser` 缓冲并切换 `SerialReader` 行/二进制模式  

---

## 8. 参考

- 下位机：`DIP_binary_protocol.md`、`DIP_binary_pc_parser.md`、`dip_parse_uart.py`  
- 上位机：`src/dip_binary_parser.py`、`README.md` 中「DIP 直接 IQ 输出」章节  
