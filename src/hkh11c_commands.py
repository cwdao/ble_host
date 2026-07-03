#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HKH-11C 呼吸传感器 UART 命令组帧

协议：FF SB LEN CKSUM CMD PARAM...
校验：CKSUM = (LEN + CMD + PARAM...) & 0xFF
"""
from __future__ import annotations

from typing import Iterable, List, Optional

FRAME_HEAD = 0xFF
DEVICE_HKH11C = 0xCC

CMD_START = 0xA0
CMD_STOP = 0xA1
CMD_READ_SN = 0xA2
CMD_READ_DATE = 0xA3
CMD_SET_GAIN = 0xA4
CMD_PING = 0xAA

RESP_PING = 0x5A


def checksum(length: int, cmd: int, params: Optional[Iterable[int]] = None) -> int:
    total = length + cmd
    if params:
        total += sum(params)
    return total & 0xFF


def build_frame(device: int, cmd: int, params: Optional[List[int]] = None) -> bytes:
    """构建标准 HKH 命令帧（含校验）。"""
    if params is None:
        params = []
    length = 3 + len(params)
    cksum = checksum(length, cmd, params)
    return bytes([FRAME_HEAD, device, length, cksum, cmd] + params)


def build_hkh11c_frame(cmd: int, params: Optional[List[int]] = None) -> bytes:
    """构建 HKH-11C 设备命令帧。"""
    return build_frame(DEVICE_HKH11C, cmd, params)


def build_reset() -> bytes:
    """广播复位：FF 00（无设备码、无校验）。"""
    return bytes([FRAME_HEAD, 0x00])


def verify_frame(frame: bytes) -> bool:
    """校验完整帧。"""
    if len(frame) < 5:
        return False
    if frame[0] != FRAME_HEAD:
        return False
    if frame[1] == 0x00 and len(frame) == 2:
        return True
    length = frame[2]
    expected_len = 2 + length
    if len(frame) != expected_len:
        return False
    cksum = frame[3]
    cmd = frame[4]
    params = list(frame[5:])
    return cksum == checksum(length, cmd, params)


def format_hex(data: bytes) -> str:
    """格式化为大写十六进制字符串，便于日志显示。"""
    return data.hex(" ").upper()
