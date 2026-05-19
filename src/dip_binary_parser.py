#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIP 二进制 UART 帧解析（协议 v2）

下位机在 ``DIP_REPORT_BINARY_OUTPUT=1`` 时经 console UART 输出的本地 IQ 帧。
本模块负责：同步搜帧、CRC 校验、bitmap 展开信道、转为上位机统一帧结构。

协议与固件对齐：
- ``dip_bin_build_frame`` / ``dip_crc16_ccitt``（nRF Connect SDK 工程 main.c）
- 参考文档：下位机 ``doc/DIP_binary_protocol.md``、``doc/DIP_binary_pc_parser.md``
- 参考脚本：下位机 ``doc/dip_parse_uart.py``

数据流（上位机侧）::

    SerialReader(binary_frame_mode=True)
        -> DipBinaryFrameReader.feed(chunk)
        -> parse_raw_frame(frame_bytes)
        -> 与 CS finalize_frame 相同结构的 dict
        -> DataProcessor / Plotter（无需改绘图逻辑）

与 ASCII「信道探测帧」的差异：
- 下位机一次 subevent 发 **整帧二进制**，非 ``== Basic Report ==`` 多行文本
- IQ 为 **本地** int16 I/Q（PCT 转 int16），无 peer il/ql/ir/qr 四元组
- 有效信道由 **10 字节 channel_bitmap** 描述，IQ 区按 ch 升序排列
"""
from __future__ import annotations

import logging
import math
import struct
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 协议常量（与固件 dip_bin_header / DIP_MAX_FFT_CHANNELS 一致）
# ---------------------------------------------------------------------------

SYNC1 = 0x55  # 帧同步字节 1
SYNC2 = 0xAA  # 帧同步字节 2
HEADER_SIZE = 22  # 固定头长度（含 10 字节 bitmap），sizeof(dip_bin_header)
DIP_MAX_FFT_CHANNELS = 75  # FFT 信道下标 0..74
DIP_FRAME_TYPE_IQ = 0x01  # type 字段：DIP IQ 帧（当前固件仅此类）


def crc16_ccitt(data: bytes) -> int:
    """
    CRC16-CCITT，与固件 ``dip_crc16_ccitt()`` 一致。

    多项式 0x1021，初值 0xFFFF；按字节 MSB 先处理。
    覆盖范围：从 sync1 到 IQ 区最后一字节（不含帧尾 2 字节 CRC）。
    """
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
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

    Args:
        bitmap: 长度必须为 10

    Returns:
        有效信道下标列表，如 [3, 10, 15]
    """
    chs: List[int] = []
    for ch in range(DIP_MAX_FFT_CHANNELS):
        if bitmap[ch // 8] & (1 << (ch % 8)):
            chs.append(ch)
    return chs


def parse_frame(frame: bytes) -> Optional[Dict]:
    """
    校验并解析**一整帧**二进制数据（调用方需已按长度切好）。

    帧布局（little-endian）::

        [0:2]   sync1, sync2
        [2]     version (0x01)
        [3]     type (0x01 = IQ)
        [4:6]   payload_len  — 从 procedure_counter 起到 IQ 末字节，不含 CRC
        [6:8]   procedure_counter
        [8]     ap
        [9]     iq_format (0 = int16 I/Q)
        [10]    channel_count N
        [11]    reserved
        [12:22] channel_bitmap[10]
        [22:22+4N]  IQ: 每信道 int16 i, int16 q（按 ch 升序）
        [22+4N:22+4N+2] crc16

    ``payload_len = 16 + 4*N``，整帧长度 ``22 + 4*N + 2``。

    Returns:
        解析成功时返回中间结构（含 iq 字典）；失败返回 None（CRC/长度/一致性错误）。
    """
    if len(frame) < HEADER_SIZE + 2:
        return None
    if frame[0] != SYNC1 or frame[1] != SYNC2:
        return None

    version, ftype = frame[2], frame[3]
    payload_len, pc = struct.unpack_from("<HH", frame, 4)
    ap, iq_format, ch_count, _reserved = struct.unpack_from("<BBBB", frame, 8)
    bitmap = frame[12:22]

    # payload_len 含 procedure_counter(2) + ap/iq_format/ch/res(4) + bitmap(10) + IQ(4N)
    iq_len = payload_len - 16
    if iq_len < 0 or iq_len % 4 != 0:
        return None

    expected = HEADER_SIZE + iq_len + 2
    if len(frame) != expected:
        return None

    body = frame[: HEADER_SIZE + iq_len]
    crc_rx = struct.unpack_from("<H", frame, HEADER_SIZE + iq_len)[0]
    if crc16_ccitt(body) != crc_rx:
        return None

    chs = channels_from_bitmap(bitmap)
    if len(chs) != ch_count or ch_count * 4 != iq_len:
        return None

    iq_bytes = frame[HEADER_SIZE : HEADER_SIZE + iq_len]
    iq_map: Dict[int, Tuple[int, int]] = {}
    off = 0
    for ch in chs:
        i, q = struct.unpack_from("<hh", iq_bytes, off)
        off += 4
        iq_map[ch] = (i, q)

    return {
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


class DipBinaryFrameReader:
    """
    串口字节流 → 完整 DIP 帧（带同步字搜索的状态机）。

    用于 ``SerialReader`` 在 ``binary_frame_mode=True`` 时：
    每次 ``read()`` 到的 chunk 可能不完整、可能含日志 ASCII 噪声，
    需在缓冲区内搜 ``0x55 0xAA`` 再按 ``payload_len`` 定长取帧。

    错位恢复：若按长度取出的帧 CRC 失败，丢弃 1 字节后继续搜同步（与参考脚本一致）。
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

        Args:
            data: 串口本次 read 的原始字节

        Returns:
            通过 ``parse_frame`` 校验的完整帧 bytes 列表
        """
        self._buf.extend(data)
        frames: List[bytes] = []

        while True:
            # --- 1. 在缓冲中搜索同步字 ---
            idx = -1
            for i in range(len(self._buf) - 1):
                if self._buf[i] == SYNC1 and self._buf[i + 1] == SYNC2:
                    idx = i
                    break
            if idx < 0:
                # 保留最后 1 字节，防止 0x55 被拆到两次 read 之间
                if len(self._buf) > 1:
                    self._buf = self._buf[-1:]
                break
            if idx > 0:
                del self._buf[:idx]

            if len(self._buf) < 6:
                break

            # --- 2. 先读 payload_len 计算整帧长度（至少要有头前 6 字节）---
            payload_len = struct.unpack_from("<H", self._buf, 4)[0]
            iq_len = payload_len - 16
            # 单帧 IQ 最大 75 信道 * 4 = 300 字节；异常值则滑窗 1 字节
            if iq_len < 0 or iq_len > 300 or iq_len % 4 != 0:
                del self._buf[0]
                continue

            total = HEADER_SIZE + iq_len + 2
            if len(self._buf) < total:
                break

            frame = bytes(self._buf[:total])
            if parse_frame(frame) is not None:
                frames.append(frame)
                del self._buf[:total]
            else:
                del self._buf[0]

        return frames


def dip_binary_to_app_frame(parsed: Dict) -> Optional[Dict]:
    """
    将 ``parse_frame`` 结果转为上位机**统一帧字典**（与 ``DataParser.finalize_frame`` 输出兼容）。

    字段映射：
    - ``procedure_counter`` → ``index`` / ``timestamp_ms``（DIP 无独立设备时间戳）
    - 每信道 int16 (i,q) → ``channels[ch]`` 含 amplitude/phase/I/Q/local_* 等
    - ``frame_type`` 固定为 ``dip_direct_iq``（保存/加载时识别）

    与 ASCII CS 帧的差异处理：
    - 仅本地 IQ：``il=ql=i,q``，``ir=qr=0``，remote 幅相为 0
    - 总幅值/相位按本地 ``hypot(i,q)`` / ``atan2(q,i)`` 计算（非 il/ql/ir/qr 组合）

    Args:
        parsed: ``parse_frame`` 的返回值

    Returns:
        含 ``frame: True`` 的字典；无有效信道时返回 None
    """
    if not parsed or not parsed.get("iq"):
        return None

    pc = int(parsed["procedure_counter"])
    result = {
        "frame": True,
        "frame_type": "dip_direct_iq",
        "index": pc,
        "timestamp_ms": pc,
        "ap": parsed.get("ap", 0),
        "channels": OrderedDict(),
    }

    for ch in sorted(parsed["iq"].keys()):
        i, q = parsed["iq"][ch]
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


def parse_raw_frame(frame: bytes) -> Optional[Dict]:
    """
    一步完成：原始字节 → 上位机帧字典（供 GUI ``_update_data`` 调用）。

    Args:
        frame: 完整二进制帧

    Returns:
        与 ``dip_binary_to_app_frame`` 相同；解析或校验失败返回 None
    """
    parsed = parse_frame(frame)
    if parsed is None:
        return None
    return dip_binary_to_app_frame(parsed)
