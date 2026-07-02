# CS 二进制双端 IQ 帧（上位机接入说明）

本文说明 BLE Host 上位机如何接收、解析并可视化下位机 **全功能 CS 二进制 UART 帧（type `0x02`）**。  
下位机协议原文见 nRF 工程 `doc/CS_binary_protocol.md`、`doc/host_acquisition_guide.md`。

---

## 1. 功能概述

| 项目 | 说明 |
|------|------|
| GUI 帧类型名称 | **CS-二进制双端IQ** |
| 内部 `frame_type` | `channel_sounding`（与 ASCII CS 相同，下游共用） |
| 保存文件前缀 | `CS_`（与文本 CS 相同） |
| 与 ASCII CS 的关系 | 帧内 IQ 语义相同（il/ql/ir/qr + 合成幅相），仅串口编码更快 |
| 与 DIP 二进制的关系 | 共用 `0x55 0xAA` 帧头；type `0x01`=DIP 本地 4B/信道，`0x02`=CS 双端 8B/信道 |

---

## 2. 数据流架构

```
下位机 (CS_REPORT_BINARY_OUTPUT=1, APP_CS_DIP_BYPASS_RAS=0)
    │ cs_uart_tx 线程
    ▼
PC 串口 (8N1, 通常 115200)
    ▼
SerialReader (binary_frame_mode=True)
    │ UartBinaryFrameReader.feed(chunk)
    ▼
dip_binary_parser.parse_raw_frame(frame_bytes)  → type 0x02 分支
    ▼
统一帧 dict { frame, frame_type: channel_sounding, index, channels{...} }
    ▼
DataProcessor → Plotter / BreathingEstimator / DataSaver
```

相关源码：

| 文件 | 职责 |
|------|------|
| `src/dip_binary_parser.py` | 通用 UART 二进制解析（type 0x01/0x02）、`cs_binary_to_app_frame` |
| `src/serial_reader.py` | 二进制模式下组帧入队 |
| `src/main_gui_qt.py` | 帧类型「CS-二进制双端IQ」、串口模式联动 |
| `src/data_parser.py` | `combine_iq` / 幅相计算（二进制 CS 复用同一逻辑） |

---

## 3. 协议摘要（type = 0x02）

帧头与 DIP v2 **完全相同**（version 0x02 为 30 字节），差异仅在 `type` 与 IQ 载荷宽度：

```
偏移   长度    字段
0      1       sync1 = 0x55
1      1       sync2 = 0xAA
2      1       version = 0x02
3      1       type = 0x02 (CS 双端 IQ)
4      2       payload_len (LE)
6      2       procedure_counter (LE) — RAS ranging_counter
8      8       timestamp_ms (LE, uint64, k_uptime_get 毫秒)
16     1       ap
17     1       iq_format (0 = int16)
18     1       channel_count N
19     1       reserved
20     10      channel_bitmap[10]
30     8×N     IQ: 按 ch 升序，每信道 int16 i_local, q_local, i_remote, q_remote
30+8N  2       crc16 (LE, CRC16-CCITT)
```

- 整帧长度：`30 + 8×N + 2` 字节  
- `payload_len = 24 + 8×N`  
- CRC 覆盖：从 **sync1** 到 IQ 区最后一字节  

**version 0x01（旧版）**：固定头 22 字节，无 `timestamp_ms`；上位机解析器仍兼容。

---

## 4. 上位机 IQ 转换

每信道四个 int16（小端）映射为与 ASCII CS 相同的字段：

| 二进制字段 | 统一帧字段 | 说明 |
|-----------|-----------|------|
| i_local, q_local | il, ql | 本地 IQ |
| i_remote, q_remote | ir, qr | 远端 IQ |
| — | I, Q | `DataParser.combine_iq(il, ql, ir, qr)` |
| — | amplitude, phase | 合成复数幅相 |

v0x02 帧含 `timestamp_ms`（设备 `k_uptime_get()` 毫秒）；上位机将其映射为统一帧的 `timestamp_ms`，`procedure_counter` 仍作为 `index`。v0x01 旧帧无该字段，回退为用 `procedure_counter` 填充 `timestamp_ms`。

---

## 5. 使用步骤

1. **固件**：`APP_CS_DIP_BYPASS_RAS=0`，`CS_REPORT_BINARY_OUTPUT=1`，`ENABLE_DIRECT_PRINT=1`；建议降低 `CONFIG_LOG` 级别。  
2. **上位机**：连接配置 → 帧类型选择 **CS-二进制双端IQ** → 连接串口。  
3. **验证**：日志出现 `[CS二进制帧] pc=...`；绘图/呼吸估计与「信道探测帧」行为一致。  

---

## 6. 与 DIP / ASCII 切换

- 切换「CS-二进制双端IQ」↔ 文本帧类型时会清空 `DataParser` 缓冲并切换 `SerialReader` 行/二进制模式。  
- 「CS-二进制双端IQ」与「DIP-直接IQ输出」均为二进制 UART，解析器按帧内 `type` 自动分支，但 GUI 仍建议按实际固件模式选择对应帧类型以便日志与排障。

---

## 7. 相关文档

- 下位机：`doc/host_acquisition_guide.md`、`doc/CS_binary_protocol.md`  
- 上位机 DIP 二进制：`docs/dip_binary_frame.md`  
- 参考脚本：下位机 `doc/cs_parse_uart.py`
