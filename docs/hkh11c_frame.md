# HKH-11C 呼吸传感器帧（上位机接入说明）

本文档说明 BLE Host 上位机如何接收、解析、控制并可视化 **HKH-11C 呼吸传感器** UART 协议。  
传感器协议原文见 [`呼吸传感器hkh-11c接口.md`](./呼吸传感器hkh-11c接口.md)。

---

## 1. 功能概述

| 项目 | 说明 |
|------|------|
| GUI 帧类型名称 | **HKH-11C呼吸波形** |
| 内部 `frame_type` | `hkh11c_resp` |
| 保存文件前缀 | `HKH_`（如 `HKH_frames_all_20260703_120000.jsonl`） |
| 与 BLE 帧的关系 | **独立协议**（`0xFF 0xCC` 同步），与 `0x55 0xAA` / ASCII `$CMD` 互斥 |
| 命令入口 | 工具栏专用 Tab「HKH-11C」（不复用「发送指令」`$CMD` 面板） |
| 波形语义 | 单信道 `ch0`，`amplitude` = 呼吸波形 raw（0~1023 有效） |

---

## 2. 数据流架构（方案 D）

```
HKH-11C 传感器 (USB 虚拟串口 / RS232)
    │ 115200 8N1，需上位机发命令启动测量
    ▼
SerialReader (uart_frame_mode='hkh11c')
    │ HKH11CFrameReader.feed(chunk)
    ▼
hkh11c_parser.parse_raw_wave_frame(frame_bytes)  → 波形帧
hkh11c_parser.parse_frame(frame_bytes)           → 控制应答 / 设备信息
    ▼
统一帧 dict { frame, frame_type: hkh11c_resp, index, channels{0: {amplitude: raw}} }
    ▼
DataProcessor → Plotter（幅值 Tab）/ DataSaver
```

帧类型切换联动：

1. 连接配置 → 帧类型选 **HKH-11C呼吸波形**
2. 串口模式自动切为 `hkh11c`；建议波特率 **115200**
3. 工具栏自动切换到 **HKH-11C** Tab
4. 绘图区仅启用「幅值」Tab，默认显示信道 `0`

相关源码：

| 文件 | 职责 |
|------|------|
| `src/hkh11c_commands.py` | 命令常量、组帧、校验、复位 |
| `src/hkh11c_parser.py` | 流式组帧、解析、转统一帧结构 |
| `src/serial_reader.py` | `uart_frame_mode` 三分支（text / ble_binary / hkh11c） |
| `src/main_gui_qt.py` | 帧类型、HKH Tab、`_update_data` 分支 |
| `src/data_saver.py` | `HKH_` 前缀、`hkh11c_resp` 元数据 |

---

## 3. 协议摘要

### 3.1 帧格式

```text
0xFF  SB  LEN  CKSUM  CMD  PARAM...
```

- `SB`：HKH-11C 设备码 `0xCC`
- `LEN`：从 LEN 字节起到最后一个参数字节的总长度（含 LEN、CKSUM、CMD、PARAM）
- `CKSUM = (LEN + CMD + PARAM...) & 0xFF`（不含帧头、设备码、校验自身）

### 3.2 波形数据帧（测量中持续上报，50 Hz）

```text
FF CC 05 CKSUM A0 HXH HXL
```

- 总长度：`2 + LEN = 7` 字节
- `raw = (HXH << 8) | HXL`

### 3.3 常用命令（上位机 → 传感器）

| 功能 | 十六进制 |
|------|----------|
| 复位（广播） | `FF 00` |
| 点名 | `FF CC 03 AD AA` |
| 启动测量 | `FF CC 03 A3 A0` |
| 停止测量 | `FF CC 03 A4 A1` |
| 设置幅度 n | `FF CC 04 CKSUM A4 n` |
| 读设备号 | `FF CC 03 A5 A2` |
| 读生产日期 | `FF CC 03 A6 A3` |

### 3.4 点名应答

```text
FF CC 03 5D 5A    （CMD = 0x5A，非 0xAA）
```

---

## 4. 上位机使用步骤

### 4.1 操作

1. 运行 `python run_qt.py`
2. **连接配置** → 帧类型 **HKH-11C呼吸波形**，波特率 **115200**
3. 连接串口
4. 工具栏 **HKH-11C** Tab：**复位** → **点名** →（可选设置幅度）→ **开始测量**
5. 幅值 Tab 查看 `ch0` 呼吸波形
6. **停止测量**；断开前建议停止并复位

### 4.2 推荐状态机

```text
CLOSED → OPENED → READY → MEASURING → STOPPING → READY
```

| 状态 | 含义 |
|------|------|
| CLOSED | 串口未连接 |
| OPENED | 已连接，未确认设备 |
| READY | 点名成功 |
| MEASURING | 已发启动命令，接收波形 |
| STOPPING | 已发停止，等待应答 |

### 4.3 保存与加载

- 记录 meta 中 `frame_type` 为 `hkh11c_resp`
- 加载此类文件自动切回 **HKH-11C呼吸波形**
- 与 BLE CS/DF/DIP 文件互不影响

---

## 5. 统一帧字段说明（`hkh11c_resp`）

```python
{
    "frame": True,
    "frame_type": "hkh11c_resp",
    "index": 42,              # 上位机侧样本序号（设备帧内无时间戳）
    "timestamp_ms": 840,      # 本地累计毫秒（index * 20）或接收时间推导
    "channels": {
        0: {
            "amplitude": 404.0,   # raw，供绘图
            "raw": 404,
            "normalized": 0.395,
        }
    },
}
```

说明：

- **不经过** RF 版 `BreathingEstimator`（该模块用于 IQ 幅值反推呼吸）
- HKH 波形可直接绘图；呼吸频率等可作为二期在 HKH Tab 内实现

---

## 6. 与现有模块的边界

| 模块 | HKH 模式行为 |
|------|----------------|
| 「发送指令」Tab | 仍可见（设置控制），但 BLE `$CMD` 与 HKH 二进制命令无关 |
| 「呼吸控制」Tab | RF 呼吸估计；HKH 直连波形时通常不需要 |
| `CommandSender` | 不扩展 HKH 命令（避免文本/二进制混用） |
| `DataParser` | 不走 ASCII 路径 |
| `dip_binary_parser` | 帧头不同，互不干扰 |

---

## 7. 故障排除

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| 无波形 | 未发启动测量 | 点名 → 开始测量 |
| 点名无应答 | 波特率非 115200；串口占用 | 检查设备管理器 COM 口 |
| 校验失败 | 半包/粘包未流式解析 | 重连；查看 HKH Tab 十六进制历史 |
| 波形平坦 | 幅度过低；传感器未贴紧 | 调整幅度 0~10；检查佩戴 |
| 与 BLE 帧混淆 | 帧类型选错 | 确认选 **HKH-11C呼吸波形** |

---

## 8. 版本与兼容性

- 上位机自 **v4.2.0** 起支持 HKH-11C（方案 D：帧类型 + 专用工具栏 Tab）
- 切换 HKH ↔ BLE 帧类型时会清空解析缓冲并切换 `SerialReader` 组帧模式
- 采样率固定 **50 Hz**；UI 刷新仍走主循环节流（不必 50 FPS 重绘）

---

## 9. 实现检查清单

- [x] `hkh11c_parser.py`：流式组帧、校验、波形转 app frame
- [x] `hkh11c_commands.py`：build_frame / build_reset
- [x] `serial_reader.py`：`uart_frame_mode='hkh11c'`
- [x] `config.frame_type_options` 含 HKH-11C
- [x] GUI：HKH-11C 工具栏 Tab（复位/点名/启停/幅度/读信息）
- [x] `_update_data`：HKH 波形与控制应答分支
- [x] `data_saver`：`HKH_` 前缀与加载识别
- [x] 帧类型切换：波特率提示、工具栏 Tab 联动、仅幅值 Tab
- [ ] 呼吸频率计算（二期，可在 HKH Tab 内实现）

---

## 10. 参考

- 传感器接口：[`呼吸传感器hkh-11c接口.md`](./呼吸传感器hkh-11c接口.md)
- 类似接入模式：[`dip_binary_frame.md`](./dip_binary_frame.md)
- 源码：`src/hkh11c_parser.py`、`src/hkh11c_commands.py`
