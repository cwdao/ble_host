#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HKH-11C 呼吸传感器 UART 帧解析

协议同步字 0xFF，设备码 0xCC；流式组帧 + 校验，波形转上位机统一帧结构。
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Dict, List, Optional

try:
    from .hkh11c_commands import (
        CMD_PING,
        CMD_READ_DATE,
        CMD_READ_SN,
        CMD_SET_GAIN,
        CMD_START,
        CMD_STOP,
        DEVICE_HKH11C,
        FRAME_HEAD,
        RESP_PING,
        checksum,
        verify_frame,
    )
except ImportError:
    from hkh11c_commands import (
        CMD_PING,
        CMD_READ_DATE,
        CMD_READ_SN,
        CMD_SET_GAIN,
        CMD_START,
        CMD_STOP,
        DEVICE_HKH11C,
        FRAME_HEAD,
        RESP_PING,
        checksum,
        verify_frame,
    )

RAW_MAX = 1023
SAMPLE_INTERVAL_MS = 20  # 50 Hz


def parse_frame(frame: bytes) -> Optional[Dict]:
    """
    解析并校验一整帧，返回结构化结果（含事件类型）。

    Returns:
        None 若校验失败；否则含 type、cmd、params、raw 等字段的字典。
    """
    if not verify_frame(frame):
        return None

    if len(frame) == 2 and frame[1] == 0x00:
        return {"type": "reset", "raw": frame}

    device = frame[1]
    length = frame[2]
    cmd = frame[4]
    params = list(frame[5:])

    if device != DEVICE_HKH11C:
        return {"type": "unknown", "device": device, "cmd": cmd, "params": params, "raw": frame}

    if cmd == RESP_PING and length == 0x03:
        return {"type": "ping_ack", "raw": frame}

    if cmd == CMD_START and length == 0x05 and len(params) == 2:
        raw = (params[0] << 8) | params[1]
        return {
            "type": "resp_wave",
            "raw": raw,
            "normalized": raw / float(RAW_MAX),
            "cmd": cmd,
            "params": params,
            "raw_frame": frame,
        }

    if cmd == CMD_STOP and length == 0x03:
        return {"type": "stop_ack", "raw": frame}

    if cmd == CMD_SET_GAIN and length == 0x03:
        return {"type": "set_gain_ack", "raw": frame}

    if cmd == CMD_READ_SN and length == 0x07 and len(params) == 4:
        sn = "".join(f"{b:02X}" for b in params)
        return {"type": "serial_number", "sn": sn, "params": params, "raw": frame}

    if cmd == CMD_READ_DATE and length == 0x07 and len(params) == 4:
        t0, t1, t2, t3 = params
        return {
            "type": "production_date",
            "day": t0,
            "month": t1,
            "year": t3 * 100 + t2,
            "params": params,
            "raw": frame,
        }

    return {"type": "unknown", "device": device, "cmd": cmd, "params": params, "raw": frame}


class HKH11CFrameReader:
    """串口字节流 → 完整 HKH-11C 帧（0xFF 同步，设备码 0xCC）。"""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.logger = logging.getLogger(__name__)

    def clear(self) -> None:
        self._buf.clear()

    def feed(self, data: bytes) -> List[bytes]:
        self._buf.extend(data)
        frames: List[bytes] = []

        while True:
            try:
                idx = self._buf.index(FRAME_HEAD)
            except ValueError:
                self._buf.clear()
                break

            if idx > 0:
                del self._buf[:idx]

            if len(self._buf) < 3:
                break

            # 广播复位 FF 00
            if self._buf[1] == 0x00:
                if len(self._buf) >= 2:
                    frames.append(bytes(self._buf[:2]))
                    del self._buf[:2]
                continue

            device = self._buf[1]
            if device != DEVICE_HKH11C:
                del self._buf[0]
                continue

            length = self._buf[2]
            frame_len = 2 + length
            if frame_len < 5 or length > 32:
                del self._buf[0]
                continue

            if len(self._buf) < frame_len:
                break

            frame = bytes(self._buf[:frame_len])
            if verify_frame(frame):
                frames.append(frame)
                del self._buf[:frame_len]
            else:
                del self._buf[0]

        return frames


class HKH11CSampleCounter:
    """上位机侧样本序号与时间戳（设备波形帧不含时间戳）。"""

    def __init__(self) -> None:
        self._index = 0
        self._t0: Optional[float] = None

    def reset(self) -> None:
        self._index = 0
        self._t0 = None

    def next(self) -> tuple[int, int]:
        if self._t0 is None:
            self._t0 = time.time()
        idx = self._index
        self._index += 1
        timestamp_ms = idx * SAMPLE_INTERVAL_MS
        return idx, timestamp_ms


_sample_counter = HKH11CSampleCounter()


def reset_sample_counter() -> None:
    _sample_counter.reset()


def hkh11c_wave_to_app_frame(parsed: Dict, index: Optional[int] = None,
                              timestamp_ms: Optional[int] = None) -> Optional[Dict]:
    """将 resp_wave 解析结果转为上位机统一帧字典。"""
    if not parsed or parsed.get("type") != "resp_wave":
        return None

    if index is None or timestamp_ms is None:
        index, timestamp_ms = _sample_counter.next()

    raw = int(parsed["raw"])
    normalized = parsed.get("normalized", raw / float(RAW_MAX))

    return {
        "frame": True,
        "frame_type": "hkh11c_resp",
        "index": index,
        "timestamp_ms": timestamp_ms,
        "channels": OrderedDict({
            0: {
                "amplitude": float(raw),
                "raw": raw,
                "normalized": float(normalized),
            },
        }),
    }


def parse_raw_wave_frame(frame: bytes) -> Optional[Dict]:
    """一步完成：原始字节 → 上位机波形帧字典（供 GUI _update_data 调用）。"""
    parsed = parse_frame(frame)
    if parsed is None or parsed.get("type") != "resp_wave":
        return None
    return hkh11c_wave_to_app_frame(parsed)
