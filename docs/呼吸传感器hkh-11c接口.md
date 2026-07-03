下面是一份**面向上位机开发的 HKH-11C 呼吸传感器接口开发文档**，我已根据你提供的说明书整理成可直接指导实现的版本。重点只围绕 **HKH-11C 呼吸传感器**，并补充了帧解析、校验、状态机、数据换算、异常处理等实现建议。

------

# HKH-11C 呼吸传感器上位机开发文档

## 1. 设备概述

### 1.1 设备名称

**HKH-11C 呼吸传感器**

### 1.2 功能

HKH-11C 呼吸传感器采用高分子压电材料，感应人体呼吸引起的腹部压力变化，经信号调理、幅度调整等电路处理后，输出呼吸波形数据。

上位机可通过串口读取呼吸波形幅值数据，并进一步计算：

- 呼吸波形
- 呼吸频率
- 呼吸周期
- 呼吸幅度
- 呼吸暂停或异常呼吸趋势

### 1.3 数据类型

传感器输出的是：

> 呼吸波形幅值相对量

也就是说，传感器上传的数据不是直接的压力单位、流量单位或标准医学单位，而是一个用于绘制波形和分析变化趋势的相对幅值。

------

## 2. 硬件接口

### 2.1 可用接口

该组合模块支持以下接口：

| 接口                 | 说明                                       |
| -------------------- | ------------------------------------------ |
| USB                  | 常用上位机连接方式，内部通常转换为虚拟串口 |
| RS232                | 可通过串口连接上位机                       |
| UART TTL             | 可连接单片机、嵌入式主控                   |
| 蓝牙 / WiFi / ZigBee | 可通过扩展模块实现无线传输                 |

上位机开发时通常使用 **USB 虚拟串口**。

------

### 2.2 供电

| 参数 | 值    |
| ---- | ----- |
| 电源 | 5 VDC |

USB 连接时由 USB 口供电。

------

## 3. 串口通信参数

通信方式为全双工串行通信。

| 参数     | 值             |
| -------- | -------------- |
| 波特率   | 115200 bps     |
| 数据位   | 8 bit          |
| 起始位   | 1 bit          |
| 停止位   | 1 bit          |
| 校验位   | 无             |
| 流控     | 无，通常不使用 |
| 通信模式 | 全双工         |

通常配置可表示为：

```text
115200, 8N1
```

------

## 4. 协议总体格式

### 4.1 通用数据帧格式

所有标准通信帧格式如下：

| 序号 | 字节 | 名称          | 说明                                 |
| ---- | ---- | ------------- | ------------------------------------ |
| 1    | 0    | 帧头          | 固定为 `0xFF`                        |
| 2    | 1    | 设备类别      | HKH-11C 为 `0xCC`                    |
| 3    | 2    | 长度          | 包含：长度、校验、命令、参数的字节数 |
| 4    | 3    | 校验和        | CKSUM                                |
| 5    | 4    | 命令 / 返回码 | 命令字或返回字                       |
| 6+   | 5... | 参数          | 数据参数                             |

即：

```text
0xFF SB LEN CKSUM CMD PARAM...
```

其中：

| 字段    | 含义                                        |
| ------- | ------------------------------------------- |
| `0xFF`  | 帧头                                        |
| `SB`    | Sensor Byte，设备类别                       |
| `LEN`   | 从 LEN 字节开始，到最后一个参数字节的总长度 |
| `CKSUM` | 校验和                                      |
| `CMD`   | 命令字                                      |
| `PARAM` | 参数区                                      |

------

## 5. HKH-11C 专用参数

### 5.1 设备类别码

HKH-11C 呼吸传感器的设备类别码为：

```text
0xCC
```

------

### 5.2 技术参数

| 参数     | 值                 |
| -------- | ------------------ |
| 电源     | 5 VDC              |
| 采样频率 | 50 Hz              |
| 采样精度 | 10 位              |
| 数据类型 | 呼吸波形幅值相对量 |

采样频率为 **50 Hz**，即理论上每秒上传 50 帧呼吸波形数据。

数据间隔约为：

```text
1000 ms / 50 = 20 ms
```

------

## 6. 校验和算法

### 6.1 校验范围

说明书定义：

> 长度、命令、参数求和后取低字节

即：

```text
CKSUM = (LEN + CMD + PARAM1 + PARAM2 + ... + PARAMn) & 0xFF
```

注意：

- 不包含帧头 `0xFF`
- 不包含设备类别 `SB`
- 不包含校验和自身
- 包含长度 `LEN`
- 包含命令 `CMD`
- 包含所有参数

------

### 6.2 无参数命令校验示例

启动测量命令：

```text
FF CC 03 CKSUM A0
```

其中：

```text
LEN = 0x03
CMD = 0xA0
```

所以：

```text
CKSUM = 0x03 + 0xA0 = 0xA3
```

完整帧为：

```text
FF CC 03 A3 A0
```

------

### 6.3 停止测量命令校验示例

```text
FF CC 03 CKSUM A1
```

计算：

```text
CKSUM = 0x03 + 0xA1 = 0xA4
```

完整帧：

```text
FF CC 03 A4 A1
```

------

### 6.4 调整幅度命令校验示例

例如设置幅度级别为 `0x05`：

```text
FF CC 04 CKSUM A4 05
```

计算：

```text
CKSUM = 0x04 + 0xA4 + 0x05 = 0xAD
```

完整帧：

```text
FF CC 04 AD A4 05
```

------

## 7. 命令列表

HKH-11C 呼吸传感器主要使用以下命令。

| 命令         | 值      | 方向              | 说明               |
| ------------ | ------- | ----------------- | ------------------ |
| 点名         | `0xAA`  | 上位机 → 传感器   | 查询设备是否在线   |
| 启动测量     | `0xA0`  | 上位机 → 传感器   | 开始上传呼吸波数据 |
| 停止测量     | `0xA1`  | 上位机 → 传感器   | 停止上传呼吸波数据 |
| 读设备号     | `0xA2`  | 上位机 → 传感器   | 读取设备编号       |
| 读生产日期   | `0xA3`  | 上位机 → 传感器   | 读取生产日期       |
| 调整呼吸幅度 | `0xA4`  | 上位机 → 传感器   | 设置波形放大级别   |
| 复位         | `FF 00` | 上位机 → 所有设备 | 停止所有在线设备   |

------

## 8. 命令详解

------

# 8.1 点名 / 扫描设备

## 8.1.1 上位机发送

```text
FF CC 03 A? AA
```

按照校验规则：

```text
CKSUM = 0x03 + 0xAA = 0xAD
```

所以完整命令为：

```text
FF CC 03 AD AA
```

------

## 8.1.2 传感器应答

说明书格式：

```text
FF SB 03 CKSUM 5A
```

对于 HKH-11C：

```text
FF CC 03 5D 5A
```

校验计算：

```text
CKSUM = 0x03 + 0x5A = 0x5D
```

------

## 8.1.3 用途

用于判断设备是否在线。

上位机启动后可执行：

1. 枚举系统串口
2. 打开串口
3. 向 `0xCC` 发送点名命令
4. 等待应答
5. 收到 `FF CC 03 5D 5A` 表示 HKH-11C 在线

------

# 8.2 启动测量

## 8.2.1 上位机发送

说明书格式：

```text
FF CC 03 CKSUM A0
```

校验：

```text
CKSUM = 0x03 + 0xA0 = 0xA3
```

完整命令：

```text
FF CC 03 A3 A0
```

------

## 8.2.2 传感器应答 / 数据帧

说明书格式：

```text
FF CC 05 CKSUM A0 HXH HXL
```

其中：

| 字段  | 含义             |
| ----- | ---------------- |
| `HXH` | 呼吸波数据高字节 |
| `HXL` | 呼吸波数据低字节 |

长度 `0x05` 表示：

```text
LEN + CKSUM + CMD + HXH + HXL
```

共 5 个字节。

------

## 8.2.3 数据帧校验

数据帧校验计算：

```text
CKSUM = (0x05 + 0xA0 + HXH + HXL) & 0xFF
```

------

## 8.2.4 呼吸波数据解析

呼吸波数据由两个字节组成：

```text
raw = (HXH << 8) | HXL
```

由于说明书标注采样精度为 10 位，所以理论有效范围通常为：

```text
0 ~ 1023
```

但实际通信中仍建议按 16 位无符号数接收，再根据实际数据范围处理。

------

## 8.2.5 示例

假设接收到：

```text
FF CC 05 3A A0 01 94
```

解析：

```text
HXH = 0x01
HXL = 0x94
raw = 0x0194 = 404
```

校验：

```text
CKSUM = 0x05 + 0xA0 + 0x01 + 0x94
      = 0x13A
取低字节 = 0x3A
```

校验通过。

最终得到：

```text
呼吸波形值 = 404
```

------

# 8.3 停止测量

## 8.3.1 上位机发送

说明书格式：

```text
FF CC 03 CKSUM A1
```

校验：

```text
CKSUM = 0x03 + 0xA1 = 0xA4
```

完整命令：

```text
FF CC 03 A4 A1
```

------

## 8.3.2 传感器应答

```text
FF CC 03 A4 A1
```

收到该帧说明已停止测量。

------

# 8.4 调整呼吸幅度

## 8.4.1 上位机发送

说明书格式：

```text
FF CC 04 CKSUM A4 FD
```

其中：

| 字段 | 含义         |
| ---- | ------------ |
| `FD` | 呼吸幅度级别 |

说明书中给出的幅度级别为：

```text
0 ~ 16 级
```

或：

```text
0 ~ 10 级
```

由于说明书写法存在两个版本范围，建议上位机提供配置项，默认按 `0~10` 使用，若设备支持更高范围再扩展到 `0~16`。

------

## 8.4.2 示例：设置幅度为 5

```text
FD = 0x05
CKSUM = 0x04 + 0xA4 + 0x05 = 0xAD
```

完整命令：

```text
FF CC 04 AD A4 05
```

------

## 8.4.3 传感器应答

说明书格式：

```text
FF CC 03 CKSUM A4
```

校验：

```text
CKSUM = 0x03 + 0xA4 = 0xA7
```

完整应答：

```text
FF CC 03 A7 A4
```

------

# 8.5 读设备号

## 8.5.1 上位机发送

```text
FF CC 03 A5 A2
```

校验：

```text
CKSUM = 0x03 + 0xA2 = 0xA5
```

------

## 8.5.2 传感器应答

```text
FF CC 07 CKSUM A2 SN0 SN1 SN2 SN3
```

校验：

```text
CKSUM = 0x07 + 0xA2 + SN0 + SN1 + SN2 + SN3
```

------

## 8.5.3 设备号解析

说明书未明确设备号编码方式，建议直接保存为 4 字节十六进制编号。

例如：

```text
SN0 SN1 SN2 SN3 = 12 34 56 78
```

可显示为：

```text
12345678
```

------

# 8.6 读生产日期

## 8.6.1 上位机发送

```text
FF CC 03 A6 A3
```

校验：

```text
CKSUM = 0x03 + 0xA3 = 0xA6
```

------

## 8.6.2 传感器应答

```text
FF CC 07 CKSUM A3 T0 T1 T2 T3
```

------

## 8.6.3 日期解析

说明书定义：

| 字段 | 含义     |
| ---- | -------- |
| `T0` | 日       |
| `T1` | 月       |
| `T2` | 年，0~99 |
| `T3` | 世纪     |

推荐解析方式：

```text
year = T3 * 100 + T2
month = T1
day = T0
```

例如：

```text
T0 = 0x15
T1 = 0x09
T2 = 0x16
T3 = 0x14
```

如果这些字段是十进制值，则表示：

```text
day = 21
month = 9
year = 20 * 100 + 22 = 2022
```

但这里要注意：说明书未说明日期字段是 BCD 还是普通二进制。建议开发时兼容两种解析方式，或者先抓取官方软件数据比对。

------

# 8.7 复位

## 8.7.1 上位机发送

```text
FF 00
```

------

## 8.7.2 说明

该命令用于让所有在线设备停止工作。

特点：

- 不带设备类别
- 不带长度
- 不带校验
- 不带应答
- 广播给所有在线设备

建议在以下场景使用：

1. 程序启动时初始化总线
2. 程序退出前停止所有设备
3. 串口异常后重新同步
4. 用户点击“全部停止”

------

## 9. HKH-11C 常用命令汇总

| 功能        | 十六进制命令        |
| ----------- | ------------------- |
| 点名        | `FF CC 03 AD AA`    |
| 启动测量    | `FF CC 03 A3 A0`    |
| 停止测量    | `FF CC 03 A4 A1`    |
| 设置幅度 0  | `FF CC 04 A8 A4 00` |
| 设置幅度 1  | `FF CC 04 A9 A4 01` |
| 设置幅度 5  | `FF CC 04 AD A4 05` |
| 设置幅度 10 | `FF CC 04 B2 A4 0A` |
| 读设备号    | `FF CC 03 A5 A2`    |
| 读生产日期  | `FF CC 03 A6 A3`    |
| 复位        | `FF 00`             |

------

## 10. 上位机推荐工作流程

### 10.1 程序启动流程

```text
启动程序
  ↓
枚举串口
  ↓
打开串口，115200 8N1
  ↓
发送复位命令 FF 00
  ↓
等待 100~300 ms
  ↓
发送点名命令 FF CC 03 AD AA
  ↓
等待应答
  ↓
识别 HKH-11C
  ↓
读取设备号，可选
  ↓
读取生产日期，可选
  ↓
进入待测量状态
```

------

### 10.2 开始测量流程

```text
用户点击开始
  ↓
可选：设置幅度
  ↓
发送启动测量 FF CC 03 A3 A0
  ↓
进入连续接收状态
  ↓
解析呼吸数据帧
  ↓
刷新波形
  ↓
保存数据，可选
  ↓
计算呼吸频率，可选
```

------

### 10.3 停止测量流程

```text
用户点击停止
  ↓
发送停止测量 FF CC 03 A4 A1
  ↓
等待停止应答
  ↓
停止绘图和保存
  ↓
进入待测量状态
```

------

### 10.4 程序退出流程

```text
用户退出程序
  ↓
发送停止测量
  ↓
发送复位 FF 00
  ↓
关闭串口
  ↓
退出程序
```

------

## 11. 串口接收与帧解析设计

### 11.1 为什么需要流式解析

串口接收到的数据不一定刚好一帧一帧返回，可能出现：

```text
一次收到半帧
一次收到多帧
帧头前有脏数据
中间丢字节
校验失败
```

因此不建议写成：

```text
每次 read 7 个字节
```

而应使用缓存区做流式帧解析。

------

### 11.2 HKH-11C 数据帧长度

启动测量后，常见数据帧为：

```text
FF CC 05 CKSUM A0 HXH HXL
```

总长度为：

```text
2 + LEN = 2 + 5 = 7 字节
```

其中：

- 前 2 字节：`FF CC`
- 后面 `LEN` 个字节：`LEN CKSUM CMD PARAM...`

------

### 11.3 通用解析规则

1. 在缓存中寻找 `0xFF`
2. 判断下一个字节是否为 `0xCC`
3. 读取第三字节 `LEN`
4. 总帧长为：

```text
frame_len = 2 + LEN
```

1. 判断缓存是否足够
2. 计算校验
3. 校验通过则解析
4. 校验失败则丢弃当前 `0xFF`，继续找下一帧

------

### 11.4 伪代码

```pseudo
buffer.append(serial.read())

while buffer.length >= 5:
    index = buffer.find(0xFF)

    if index < 0:
        buffer.clear()
        break

    if index > 0:
        buffer.remove_before(index)

    if buffer.length < 3:
        break

    device = buffer[1]

    if device != 0xCC:
        buffer.remove_first_byte()
        continue

    len = buffer[2]
    frame_len = 2 + len

    if buffer.length < frame_len:
        break

    frame = buffer.take(frame_len)

    if verify_checksum(frame):
        handle_frame(frame)
        buffer.remove_first(frame_len)
    else:
        buffer.remove_first_byte()
```

------

## 12. 数据解析

### 12.1 呼吸数据帧

```text
FF CC 05 CKSUM A0 HXH HXL
```

------

### 12.2 字段位置

| 字节下标 | 字段    | 说明                      |
| -------- | ------- | ------------------------- |
| 0        | `0xFF`  | 帧头                      |
| 1        | `0xCC`  | HKH-11C 设备码            |
| 2        | `0x05`  | 长度                      |
| 3        | `CKSUM` | 校验                      |
| 4        | `0xA0`  | 启动测量返回 / 数据帧标识 |
| 5        | `HXH`   | 呼吸数据高字节            |
| 6        | `HXL`   | 呼吸数据低字节            |

------

### 12.3 原始值

```text
raw = HXH * 256 + HXL
```

或：

```text
raw = (HXH << 8) | HXL
```

------

### 12.4 归一化值，可选

由于采样精度为 10 位，可归一化到 `0~1`：

```text
normalized = raw / 1023.0
```

也可归一化到 `-1~1`：

```text
centered = (raw - baseline) / amplitude
```

其中 `baseline` 可用滑动平均计算。

------

### 12.5 时间戳

HKH-11C 没有在数据帧内提供时间戳。

上位机应在接收时自行添加时间戳。

推荐方式：

```text
timestamp = 当前高精度时间
```

或者按采样率生成：

```text
sample_index += 1
timestamp = sample_index / 50.0
```

如果做实时显示，建议同时保存：

| 字段             | 说明         |
| ---------------- | ------------ |
| `recv_timestamp` | 实际接收时间 |
| `sample_index`   | 样本序号     |
| `raw`            | 原始呼吸波值 |

------

## 13. 数据保存格式建议

### 13.1 CSV 格式

建议保存为：

```csv
timestamp_ms,sample_index,raw,normalized
0,0,512,0.5005
20,1,514,0.5024
40,2,516,0.5044
```

------

### 13.2 原始十六进制日志

用于调试时建议同时支持保存原始数据：

```text
2026-07-03 10:00:00.001 RX FF CC 05 3A A0 01 94
2026-07-03 10:00:00.021 RX FF CC 05 3C A0 01 96
```

这样方便和官方软件的“16进制原始数据”对比。

------

## 14. 呼吸频率计算建议

说明书只提供呼吸波形数据，没有直接输出呼吸频率。

因此上位机需要自己算法计算。

------

### 14.1 基本思路

呼吸频率单位通常为：

```text
次 / 分钟
```

可通过波峰检测或周期检测计算。

基本公式：

```text
呼吸频率 = 60 / 平均呼吸周期
```

如果用采样点数计算：

```text
周期秒数 = 相邻呼吸峰之间的采样点数 / 50
呼吸频率 = 60 / 周期秒数
```

等价于：

```text
呼吸频率 = 60 * 50 / 峰间采样点数
```

------

### 14.2 推荐算法流程

```text
原始数据
  ↓
去直流 / 基线漂移
  ↓
低通滤波
  ↓
平滑
  ↓
波峰或零交叉检测
  ↓
计算峰间距
  ↓
异常周期剔除
  ↓
滑动平均
  ↓
输出呼吸频率
```

------

### 14.3 简化版算法

适合初版开发：

1. 保留最近 10~30 秒数据
2. 对数据做滑动平均
3. 找局部最大峰
4. 峰间距限制在合理范围

成人静息呼吸通常可以先设置检测范围：

```text
6 ~ 40 次 / 分钟
```

对应周期范围：

```text
1.5 ~ 10 秒
```

对应采样点：

```text
75 ~ 500 点
```

因此两个有效波峰之间的间隔应大致在：

```text
75 ~ 500 samples
```

------

### 14.4 呼吸暂停检测

可选功能：

如果连续一段时间波形变化幅度很小，可以判断为疑似呼吸暂停或传感器脱落。

例如：

```text
最近 10 秒峰峰值 < 阈值
```

提示：

```text
呼吸信号弱 / 传感器松动 / 疑似无呼吸
```

注意：该传感器输出是相对波形，不能仅靠一个固定阈值适配所有人，建议阈值支持自适应。

------

## 15. 上位机界面功能建议

### 15.1 基础功能

建议至少实现：

- 串口选择
- 波特率固定为 115200
- 打开 / 关闭串口
- 扫描设备
- 显示设备在线状态
- 开始测量
- 停止测量
- 设置幅度
- 实时波形显示
- 原始值显示
- 数据保存
- 原始十六进制日志保存

------

### 15.2 推荐界面布局

```text
┌────────────────────────────────────┐
│ 串口: COM3     [扫描] [打开串口]   │
│ 设备: HKH-11C  状态: 在线          │
├────────────────────────────────────┤
│ 幅度: [0~10] [设置]                │
│ [开始测量] [停止测量] [保存CSV]    │
├────────────────────────────────────┤
│ 实时呼吸波形图                     │
│                                    │
├────────────────────────────────────┤
│ 原始值: 512                        │
│ 呼吸频率: 16 次/分钟               │
│ 信号状态: 正常                     │
└────────────────────────────────────┘
```

------

## 16. 推荐状态机

```text
CLOSED
  串口关闭

OPENED
  串口已打开，未确认设备

READY
  已识别 HKH-11C，等待测量

MEASURING
  正在接收呼吸数据

STOPPING
  已发送停止命令，等待停止应答

ERROR
  通信异常或设备异常
```

------

### 16.1 状态转换

```text
CLOSED --打开串口--> OPENED
OPENED --点名成功--> READY
READY --启动测量--> MEASURING
MEASURING --停止测量--> STOPPING
STOPPING --停止应答--> READY
任意状态 --串口异常--> ERROR
ERROR --重新初始化--> OPENED / CLOSED
```

------

## 17. 实现注意事项

### 17.1 不要阻塞 UI 线程

串口接收应放在：

- 独立线程
- 异步任务
- 事件回调
- 后台服务

避免实时波形刷新时卡顿。

------

### 17.2 绘图频率不必等于采样频率

传感器 50 Hz 上传数据。

UI 可每秒刷新 20~30 次即可，不必每收到一帧就重绘一次。

建议：

```text
数据采集：50 Hz
界面刷新：20~30 FPS
```

------

### 17.3 处理粘包和半包

串口数据可能出现：

```text
FF CC 05 3A
A0 01 94 FF CC 05 ...
```

或者：

```text
FF CC 05 3A A0 01 94 FF CC 05 3B A0 01 95
```

所以必须使用缓冲区解析，不要假设一次读取就是一帧。

------

### 17.4 校验失败处理

校验失败时：

1. 丢弃当前帧头
2. 继续寻找下一个 `0xFF`
3. 记录错误计数
4. 错误过多时提示通信质量异常

------

### 17.5 启动前最好先复位

建议打开串口后发送：

```text
FF 00
```

然后延时 100~300 ms，再发送点名。

这样可以清理设备之前可能残留的测量状态。

------

## 18. Python 示例

下面是一个最小可用的 Python 解析示例，使用 `pyserial`。

### 18.1 安装依赖

```bash
pip install pyserial
```

------

### 18.2 示例代码

```python
import serial
import time
from collections import deque

DEVICE_HKH11C = 0xCC

CMD_START = 0xA0
CMD_STOP = 0xA1
CMD_READ_SN = 0xA2
CMD_READ_DATE = 0xA3
CMD_SET_GAIN = 0xA4
CMD_PING = 0xAA

def checksum(length, cmd, params=None):
    if params is None:
        params = []
    return (length + cmd + sum(params)) & 0xFF

def build_frame(device, cmd, params=None):
    if params is None:
        params = []

    length = 3 + len(params)
    cksum = checksum(length, cmd, params)

    return bytes([0xFF, device, length, cksum, cmd] + params)

def build_reset():
    return bytes([0xFF, 0x00])

def verify_frame(frame):
    if len(frame) < 5:
        return False

    if frame[0] != 0xFF:
        return False

    length = frame[2]
    expected_len = 2 + length

    if len(frame) != expected_len:
        return False

    cksum = frame[3]
    cmd = frame[4]
    params = list(frame[5:])

    calc = checksum(length, cmd, params)
    return cksum == calc

class HKH11CParser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []

        while len(self.buffer) >= 5:
            try:
                idx = self.buffer.index(0xFF)
            except ValueError:
                self.buffer.clear()
                break

            if idx > 0:
                del self.buffer[:idx]

            if len(self.buffer) < 3:
                break

            device = self.buffer[1]

            # 只解析 HKH-11C
            if device != DEVICE_HKH11C:
                del self.buffer[0]
                continue

            length = self.buffer[2]
            frame_len = 2 + length

            if len(self.buffer) < frame_len:
                break

            frame = bytes(self.buffer[:frame_len])

            if verify_frame(frame):
                frames.append(frame)
                del self.buffer[:frame_len]
            else:
                # 校验失败，丢弃当前帧头，继续同步
                del self.buffer[0]

        return frames

def parse_hkh11c_frame(frame):
    device = frame[1]
    length = frame[2]
    cmd = frame[4]
    params = list(frame[5:])

    if device != DEVICE_HKH11C:
        return None

    if cmd == CMD_PING and length == 0x03:
        return {
            "type": "ping_ack"
        }

    if cmd == CMD_START and length == 0x05 and len(params) == 2:
        raw = (params[0] << 8) | params[1]
        return {
            "type": "resp_wave",
            "raw": raw,
            "normalized": raw / 1023.0
        }

    if cmd == CMD_STOP and length == 0x03:
        return {
            "type": "stop_ack"
        }

    if cmd == CMD_SET_GAIN and length == 0x03:
        return {
            "type": "set_gain_ack"
        }

    if cmd == CMD_READ_SN and length == 0x07 and len(params) == 4:
        sn = ''.join(f'{b:02X}' for b in params)
        return {
            "type": "serial_number",
            "sn": sn
        }

    if cmd == CMD_READ_DATE and length == 0x07 and len(params) == 4:
        t0, t1, t2, t3 = params
        return {
            "type": "production_date",
            "day": t0,
            "month": t1,
            "year": t3 * 100 + t2,
            "raw": params
        }

    return {
        "type": "unknown",
        "frame": frame.hex(" ").upper()
    }

def main():
    port = "COM3"

    ser = serial.Serial(
        port=port,
        baudrate=115200,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=0.05
    )

    parser = HKH11CParser()

    # 复位
    ser.write(build_reset())
    time.sleep(0.2)

    # 点名
    ping = build_frame(DEVICE_HKH11C, CMD_PING)
    print("TX:", ping.hex(" ").upper())
    ser.write(ping)

    time.sleep(0.2)

    data = ser.read(1024)
    frames = parser.feed(data)

    online = False

    for frame in frames:
        result = parse_hkh11c_frame(frame)
        print("RX:", frame.hex(" ").upper(), result)

        if result and result["type"] == "ping_ack":
            online = True

    if not online:
        print("未发现 HKH-11C 设备")
        ser.close()
        return

    print("HKH-11C 在线")

    # 设置幅度为 5，可选
    set_gain = build_frame(DEVICE_HKH11C, CMD_SET_GAIN, [5])
    print("TX:", set_gain.hex(" ").upper())
    ser.write(set_gain)
    time.sleep(0.1)

    # 启动测量
    start = build_frame(DEVICE_HKH11C, CMD_START)
    print("TX:", start.hex(" ").upper())
    ser.write(start)

    sample_index = 0

    try:
        while True:
            data = ser.read(1024)
            if not data:
                continue

            frames = parser.feed(data)

            for frame in frames:
                result = parse_hkh11c_frame(frame)

                if result and result["type"] == "resp_wave":
                    raw = result["raw"]
                    normalized = result["normalized"]
                    timestamp = time.time()

                    print(
                        f"sample={sample_index}, "
                        f"time={timestamp:.3f}, "
                        f"raw={raw}, "
                        f"norm={normalized:.4f}"
                    )

                    sample_index += 1

    except KeyboardInterrupt:
        print("停止测量")

    finally:
        stop = build_frame(DEVICE_HKH11C, CMD_STOP)
        print("TX:", stop.hex(" ").upper())
        ser.write(stop)
        time.sleep(0.1)

        ser.write(build_reset())
        ser.close()

if __name__ == "__main__":
    main()
```

------

## 19. C# 实现要点

如果你用 C# 写 Windows 上位机，可使用：

```csharp
System.IO.Ports.SerialPort
```

关键参数：

```csharp
SerialPort serial = new SerialPort();
serial.PortName = "COM3";
serial.BaudRate = 115200;
serial.DataBits = 8;
serial.Parity = Parity.None;
serial.StopBits = StopBits.One;
serial.Open();
```

接收数据建议用：

```csharp
serial.DataReceived += Serial_DataReceived;
```

但要注意：

- `DataReceived` 不在 UI 线程
- 不要直接操作 WinForms / WPF 控件
- 使用 `BeginInvoke` 或消息队列刷新 UI
- 接收回调中只做数据入队和解析，不要做重绘等耗时操作

------

## 20. 关键协议常量

```text
FRAME_HEAD     = 0xFF
DEVICE_HKH11C  = 0xCC

CMD_START      = 0xA0
CMD_STOP       = 0xA1
CMD_READ_SN    = 0xA2
CMD_READ_DATE  = 0xA3
CMD_SET_GAIN   = 0xA4
CMD_PING       = 0xAA
```

------

## 21. 最小闭环测试步骤

你实现上位机时，可以按以下顺序验证。

### 第一步：打开串口

确认设备管理器里有 CP210x 或对应虚拟串口。

------

### 第二步：发送点名

发送：

```text
FF CC 03 AD AA
```

期望收到：

```text
FF CC 03 5D 5A
```

------

### 第三步：启动测量

发送：

```text
FF CC 03 A3 A0
```

期望持续收到类似数据：

```text
FF CC 05 ?? A0 HXH HXL
```

例如：

```text
FF CC 05 3A A0 01 94
FF CC 05 3C A0 01 96
FF CC 05 3D A0 01 97
```

------

### 第四步：解析波形值

```text
raw = HXH * 256 + HXL
```

将 raw 作为 Y 轴，时间作为 X 轴绘制曲线。

------

### 第五步：停止测量

发送：

```text
FF CC 03 A4 A1
```

期望收到：

```text
FF CC 03 A4 A1
```

------

## 22. 常见问题排查

### 22.1 扫描不到设备

检查：

1. USB 驱动是否安装
2. 设备管理器是否出现 COM 口
3. COM 口是否被官方软件占用
4. 波特率是否为 115200
5. 串口参数是否为 8N1
6. 是否发送了正确点名命令
7. 是否选错设备码，HKH-11C 是 `0xCC`

------

### 22.2 收到数据但校验失败

检查：

1. 校验是否包含 `LEN`
2. 校验是否包含 `CMD`
3. 校验是否包含参数
4. 是否错误地把 `0xFF` 或 `0xCC` 加入校验
5. 是否正确处理粘包、半包
6. 是否按无符号字节计算

正确算法：

```text
CKSUM = (LEN + CMD + PARAMS...) & 0xFF
```

------

### 22.3 波形不明显

检查：

1. 传感器是否贴在肚脐上方或下方
2. 感应面是否朝向内侧
3. 腰带力度是否适中
4. 是否设置了合适幅度
5. 被测者是否保持平稳呼吸
6. 是否有较大体动干扰

------

### 22.4 数据频率不稳定

可能原因：

1. 串口读取线程被阻塞
2. UI 绘图太频繁
3. 使用了阻塞式保存文件
4. 系统调度导致读取时间抖动

建议：

- 接收线程只负责收数据
- 绘图线程按固定 FPS 刷新
- 文件保存放到后台队列
- 时间戳使用高精度计时器

------

## 23. 开发建议总结

上位机实现时，核心只需完成以下几个模块：

```text
串口管理模块
  - 枚举串口
  - 打开/关闭串口
  - 发送命令
  - 异步接收

协议解析模块
  - 帧同步
  - 长度判断
  - 校验验证
  - 命令分发

数据处理模块
  - raw 解析
  - 时间戳
  - 滤波
  - 呼吸频率计算

界面显示模块
  - 实时曲线
  - 原始值
  - 设备状态
  - 呼吸频率

数据存储模块
  - CSV 保存
  - 原始 HEX 保存
```

------

## 24. 最重要的几个结论

HKH-11C 的核心协议可以简化理解为：

```text
设备码：0xCC
串口：115200, 8N1
采样率：50 Hz
启动：FF CC 03 A3 A0
停止：FF CC 03 A4 A1
数据：FF CC 05 CKSUM A0 HXH HXL
呼吸值：(HXH << 8) | HXL
校验：(LEN + CMD + PARAMS...) & 0xFF
```

你后续实现上位机时，只要先把这条链路跑通：

```text
打开串口 → 点名 → 启动 → 接收数据 → 校验 → 解析 raw → 绘图 → 停止
```

基本就完成了 HKH-11C 呼吸传感器的核心采集功能。