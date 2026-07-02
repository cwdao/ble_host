#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UART 二进制帧解析（DIP v2 / CS 双端 IQ）

下位机经 console UART 输出的本地或双端 IQ 帧，共用 0x55 0xAA 帧头：
- type ``0x01``：DIP 本地 IQ（4 B/信道）
- type ``0x02``：全功能 CS 双端 IQ（8 B/信道）

帧头 version：
- ``0x02``（当前）：30 字节固定头，含 ``timestamp_ms``（uint64 LE，k_uptime_get 毫秒）
- ``0x01``（旧版）：22 字节固定头，无 ``timestamp_ms``

本模块负责：同步搜帧、CRC 校验、bitmap 展开信道、转为上位机统一帧结构。

协议与固件对齐：
- ``dip_bin_*`` / ``cs_bin_*`` / ``cs_uart_bin_crc16_ccitt``
- 参考文档：下位机 ``doc/DIP_binary_protocol.md``、``doc/CS_binary_protocol.md``
- 参考脚本：下位机 ``doc/cs_parse_uart.py``

数据流（上位机侧）::

    SerialReader(binary_frame_mode=True)
        -> UartBinaryFrameReader.feed(chunk)
        -> parse_raw_frame(frame_bytes)
        -> 与 DataParser.finalize_frame 相同结构的 dict
        -> DataProcessor / Plotter（无需改绘图逻辑）
"""
from __future__ import annotations

import logging
import math
import struct
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, Union

try:
    from .data_parser import DataParser
except ImportError:
    from data_parser import DataParser

# ---------------------------------------------------------------------------
# 协议常量（与固件 cs_uart_bin_header 一致）
# ---------------------------------------------------------------------------

SYNC1 = 0x55
SYNC2 = 0xAA
HEADER_SIZE_V1 = 22
HEADER_SIZE_V2 = 30
PAYLOAD_FIXED_V1 = 16
PAYLOAD_FIXED_V2 = 24
MAX_FFT_CHANNELS = 75

TYPE_DIP_LOCAL = 0x01
TYPE_CS_DUAL = 0x02

# 向后兼容旧名称
HEADER_SIZE = HEADER_SIZE_V2
DIP_MAX_FFT_CHANNELS = MAX_FFT_CHANNELS
DIP_FRAME_TYPE_IQ = TYPE_DIP_LOCAL

_iq_helper = DataParser()


def header_layout(version: int) -> Tuple[int, int, int, int]:
    """返回 (header_size, payload_fixed, ap_offset, bitmap_offset)。"""
    if version == 0x01:
        return HEADER_SIZE_V1, PAYLOAD_FIXED_V1, 8, 12
    return HEADER_SIZE_V2, PAYLOAD_FIXED_V2, 16, 20


def iq_bytes_per_channel(ftype: int) -> Optional[int]:
    """每有效信道 IQ 区字节数；未知 type 返回 None。"""
    if ftype == TYPE_DIP_LOCAL:
        return 4
    if ftype == TYPE_CS_DUAL:
        return 8
    return None


def crc16_ccitt(data: bytes) -> int:
    """
    CRC16-CCITT，与固件 ``cs_uart_bin_crc16_ccitt()`` 一致。

    多项式 0x1021，初值 0xFFFF；按字节 MSB 先处理。
    覆盖范围：从 sync1 到 IQ 区最后一字节（不含帧尾 2 字节 CRC）。
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def channels_from_bitmap(bitmap: bytes) -> List[int]:
    """
    从 10 字节位图解析有效 FFT 信道列表（升序）。

    编码：``bitmap[ch // 8]`` 的 bit ``(ch % 8)`` 为 1 表示信道 ch 有效；
    bit0 为 LSB（ch=0 对应 bitmap[0] bit0）。
    """
    chs: List[int] = []
    for ch in range(MAX_FFT_CHANNELS):
        if bitmap[ch // 8] & (1 << (ch % 8)):
            chs.append(ch)
    return chs


def parse_frame(frame: bytes) -> Optional[Dict]:
    """
    校验并解析**一整帧**二进制数据（调用方需已按长度切好）。

    帧布局 v0x02（little-endian，30 字节头）::

        [0:2]   sync1, sync2
        [2]     version (0x02)
        [3]     type (0x01=DIP / 0x02=CS 双端)
        [4:6]   payload_len  — 从 procedure_counter 起到 IQ 末字节，不含 CRC
        [6:8]   procedure_counter
        [8:16]  timestamp_ms (uint64 LE，v0x02 起)
        [16]    ap
        [17]    iq_format (0 = int16 I/Q)
        [18]    channel_count N
        [19]    reserved
        [20:30] channel_bitmap[10]
        [30:...] IQ 载荷（type 0x01: 4N；type 0x02: 8N）
        [...]   crc16

    v0x01 固定头 22 字节，无 timestamp_ms，``payload_fixed=16``。

    v0x02 ``payload_len = 24 + bpc×N``，整帧长度 ``30 + bpc×N + 2``。

    Returns:
        解析成功时返回中间结构（含 iq 字典）；失败返回 None。
    """
    if len(frame) < HEADER_SIZE_V1 + 2:
        return None
    if frame[0] != SYNC1 or frame[1] != SYNC2:
        return None

    version, ftype = frame[2], frame[3]
    hdr_size, payload_fixed, ap_off, bitmap_off = header_layout(version)

    if len(frame) < hdr_size + 2:
        return None

    bpc = iq_bytes_per_channel(ftype)
    if bpc is None:
        return None

    payload_len, pc = struct.unpack_from("<HH", frame, 4)
    timestamp_ms: Optional[int] = None
    if version >= 0x02:
        timestamp_ms = struct.unpack_from("<Q", frame, 8)[0]

    ap, iq_format, ch_count, _reserved = struct.unpack_from("<BBBB", frame, ap_off)
    bitmap = frame[bitmap_off : bitmap_off + 10]

    iq_len = payload_len - payload_fixed
    if iq_len < 0 or iq_len % bpc != 0:
        return None

    expected = hdr_size + iq_len + 2
    if len(frame) != expected:
        return None

    body = frame[: hdr_size + iq_len]
    crc_rx = struct.unpack_from("<H", frame, hdr_size + iq_len)[0]
    if crc16_ccitt(body) != crc_rx:
        return None

    chs = channels_from_bitmap(bitmap)
    if len(chs) != ch_count or ch_count * bpc != iq_len:
        return None

    iq_bytes = frame[hdr_size : hdr_size + iq_len]
    iq_map: Dict[int, Union[Tuple[int, int], Tuple[int, int, int, int]]] = {}
    off = 0
    for ch in chs:
        if ftype == TYPE_DIP_LOCAL:
            i, q = struct.unpack_from("<hh", iq_bytes, off)
            off += 4
            iq_map[ch] = (i, q)
        else:
            il, ql, ir, qr = struct.unpack_from("<hhhh", iq_bytes, off)
            off += 8
            iq_map[ch] = (il, ql, ir, qr)

    result: Dict = {
        "version": version,
        "type": ftype,
        "procedure_counter": pc,
        "ap": ap,
        "iq_format": iq_format,
        "channel_count": ch_count,
        "channels": chs,
        "iq": iq_map,
        "raw": frame,
    }
    if timestamp_ms is not None:
        result["timestamp_ms"] = timestamp_ms
    return result


class UartBinaryFrameReader:
    """
    串口字节流 → 完整 UART 二进制帧（带同步字搜索的状态机）。

    同时支持 type 0x01（DIP）与 0x02（CS 双端）；根据帧内 type 与 version 定头长与 IQ 区宽度。
    错位恢复：CRC 失败时丢弃 1 字节后继续搜同步。
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.logger = logging.getLogger(__name__)

    def clear(self) -> None:
        """清空内部缓冲（切换帧类型或重连时调用）。"""
        self._buf.clear()

    def feed(self, data: bytes) -> List[bytes]:
        """
        喂入新收到的字节，返回本轮解析出的完整帧列表（可能为空）。
        """
        self._buf.extend(data)
        frames: List[bytes] = []

        while True:
            idx = -1
            for i in range(len(self._buf) - 1):
                if self._buf[i] == SYNC1 and self._buf[i + 1] == SYNC2:
                    idx = i
                    break
            if idx < 0:
                if len(self._buf) > 1:
                    self._buf = self._buf[-1:]
                break
            if idx > 0:
                del self._buf[:idx]

            if len(self._buf) < 6:
                break

            version = self._buf[2]
            ftype = self._buf[3]
            bpc = iq_bytes_per_channel(ftype)
            if bpc is None:
                del self._buf[0]
                continue

            hdr_size, payload_fixed, _, _ = header_layout(version)
            payload_len = struct.unpack_from("<H", self._buf, 4)[0]
            iq_len = payload_len - payload_fixed
            max_iq = MAX_FFT_CHANNELS * bpc
            if iq_len < 0 or iq_len > max_iq or iq_len % bpc != 0:
                del self._buf[0]
                continue

            total = hdr_size + iq_len + 2
            if len(self._buf) < total:
                break

            frame = bytes(self._buf[:total])
            if parse_frame(frame) is not None:
                frames.append(frame)
                del self._buf[:total]
            else:
                del self._buf[0]

        return frames


# 向后兼容
DipBinaryFrameReader = UartBinaryFrameReader


def _device_timestamp_ms(parsed: Dict) -> int:
    """v0x02 使用设备毫秒时间戳；v0x01 回退为 procedure_counter。"""
    ts = parsed.get("timestamp_ms")
    if ts is not None:
        return int(ts)
    return int(parsed["procedure_counter"])


def dip_binary_to_app_frame(parsed: Dict) -> Optional[Dict]:
    """
    将 type 0x01 解析结果转为上位机统一帧字典。

    - ``procedure_counter`` → ``index``
    - ``timestamp_ms``（v0x02）→ ``timestamp_ms``；v0x01 回退为 ``procedure_counter``
    - 每信道 int16 (i,q) → ``channels[ch]`` 含 amplitude/phase/I/Q/local_* 等
    - ``frame_type`` 固定为 ``dip_direct_iq``
    """
    if not parsed or not parsed.get("iq"):
        return None

    pc = int(parsed["procedure_counter"])
    result = {
        "frame": True,
        "frame_type": "dip_direct_iq",
        "index": pc,
        "timestamp_ms": _device_timestamp_ms(parsed),
        "ap": parsed.get("ap", 0),
        "channels": OrderedDict(),
    }

    for ch in sorted(parsed["iq"].keys()):
        i, q = parsed["iq"][ch]  # type: ignore[misc]
        il, ql = float(i), float(q)
        ir, qr = 0.0, 0.0
        amplitude = math.hypot(il, ql)
        phase = math.atan2(ql, il)

        result["channels"][ch] = {
            "amplitude": amplitude,
            "phase": phase,
            "I": il,
            "Q": ql,
            "local_amplitude": amplitude,
            "local_phase": phase,
            "remote_amplitude": 0.0,
            "remote_phase": 0.0,
            "il": il,
            "ql": ql,
            "ir": ir,
            "qr": qr,
        }

    return result if result["channels"] else None


def cs_binary_to_app_frame(parsed: Dict) -> Optional[Dict]:
    """
    将 type 0x02 解析结果转为上位机统一帧字典（与 ASCII CS ``finalize_frame`` 兼容）。

    - ``procedure_counter``（RAS ranging_counter）→ ``index``
    - ``timestamp_ms``（v0x02）→ ``timestamp_ms``；v0x01 回退为 ``procedure_counter``
    - 双端 int16 → il/ql/ir/qr，幅相按 ``DataParser.combine_iq`` 合成
    - ``frame_type`` 为 ``channel_sounding``，后续绘图/呼吸/保存与文本 CS 共用
    """
    if not parsed or not parsed.get("iq"):
        return None

    pc = int(parsed["procedure_counter"])
    result = {
        "frame": True,
        "frame_type": "channel_sounding",
        "index": pc,
        "timestamp_ms": _device_timestamp_ms(parsed),
        "ap": parsed.get("ap", 0),
        "channels": OrderedDict(),
    }

    for ch in sorted(parsed["iq"].keys()):
        il, ql, ir, qr = parsed["iq"][ch]  # type: ignore[misc]
        il, ql, ir, qr = float(il), float(ql), float(ir), float(qr)

        if any(math.isnan(x) for x in (il, ql, ir, qr)):
            continue
        if all(abs(x) < 1e-6 for x in (il, ql, ir, qr)):
            continue

        I, Q = _iq_helper.combine_iq(il, ql, ir, qr)
        amplitude, phase = _iq_helper.iq_to_amplitude_phase(il, ql, ir, qr)
        local_amplitude = math.hypot(il, ql)
        local_phase = math.atan2(ql, il)
        remote_amplitude = math.hypot(ir, qr)
        remote_phase = math.atan2(qr, ir)

        result["channels"][ch] = {
            "amplitude": amplitude,
            "phase": phase,
            "I": I,
            "Q": Q,
            "local_amplitude": local_amplitude,
            "local_phase": local_phase,
            "remote_amplitude": remote_amplitude,
            "remote_phase": remote_phase,
            "il": il,
            "ql": ql,
            "ir": ir,
            "qr": qr,
        }

    return result if result["channels"] else None


def binary_to_app_frame(parsed: Dict) -> Optional[Dict]:
    """按帧 type 分支转为上位机统一帧结构。"""
    ftype = parsed.get("type")
    if ftype == TYPE_DIP_LOCAL:
        return dip_binary_to_app_frame(parsed)
    if ftype == TYPE_CS_DUAL:
        return cs_binary_to_app_frame(parsed)
    return None


def parse_raw_frame(frame: bytes) -> Optional[Dict]:
    """
    一步完成：原始字节 → 上位机帧字典（供 GUI ``_update_data`` 调用）。

    自动识别 type 0x01（DIP）与 0x02（CS 双端）。
    """
    parsed = parse_frame(frame)
    if parsed is None:
        return None
    return binary_to_app_frame(parsed)
