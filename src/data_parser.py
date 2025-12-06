#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据解析模块
支持BLE CS Report帧格式解析
"""
import re
import json
import math
import logging
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict

try:
    from .utils.text_utils import remove_ansi_escape, safe_float
except ImportError:
    from utils.text_utils import remove_ansi_escape, safe_float


class DataParser:
    """数据解析类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 正则表达式：匹配帧头和数据
        self.re_basic = re.compile(r"== Basic Report == index:(\d+), timestamp:(\d+)")
        self.re_end_report = re.compile(r"== End Report ==")
        
        # IQ数据格式：ch:<idx>:<il>,<ql>,<ir>,<qr>;
        self.NUM = r"[+-]?(?:\d+(?:\.\d+)?|nan|inf|-inf)"
        self.re_iq_line_has_prefix = re.compile(r"\bIQ:\s*(.*)")
        self.re_iq_tokens = re.compile(rf"ch:(\d+):({self.NUM}),({self.NUM}),({self.NUM}),({self.NUM});")
        
        # 缓冲区：用于存储多行的帧数据
        self.frame_buffer = {}  # {index: {'timestamp': ts, 'iq_data': {ch: [il,ql,ir,qr]}}}
        self.current_frame = None
    
    def combine_iq(self, il: float, ql: float, ir: float, qr: float) -> Tuple[float, float]:
        """
        组合IQ数据
        对应 calculate_vec_cmac_f 的单点版
        
        Returns:
            (I, Q) 合成后的复数分量
        """
        I = ir * il - qr * ql
        Q = ir * ql + il * qr
        return I, Q
    
    def iq_to_amplitude_phase(self, il: float, ql: float, ir: float, qr: float) -> Tuple[float, float]:
        """
        将IQ数据转换为幅值和相位
        
        Args:
            il, ql: local I/Q
            ir, qr: peer I/Q
        
        Returns:
            (amplitude, phase_rad) 幅值和相位（弧度）
        """
        I, Q = self.combine_iq(il, ql, ir, qr)
        amplitude = math.hypot(I, Q)  # sqrt(I^2 + Q^2)
        phase = math.atan2(Q, I)  # 相位（弧度）
        return amplitude, phase
    
    def parse_frame_header(self, text: str) -> Optional[Dict]:
        """
        解析帧头：== Basic Report == index:X, timestamp:Y
        
        Returns:
            {'index': int, 'timestamp_ms': int} 或 None
        """
        line = remove_ansi_escape(text)
        m = self.re_basic.search(line)
        if m:
            return {
                'index': int(m.group(1)),
                'timestamp_ms': int(m.group(2))
            }
        return None
    
    def parse_frame_footer(self, text: str) -> bool:
        """
        解析帧尾：== End Report ==
        
        Returns:
            True 如果检测到帧尾，否则 False
        """
        line = remove_ansi_escape(text)
        return bool(self.re_end_report.search(line))
    
    def parse_iq_data(self, text: str) -> Dict[int, List[float]]:
        """
        解析IQ数据行
        
        Args:
            text: 包含IQ数据的文本行，格式如 "IQ: ch:0:il,ql,ir,qr;ch:1:..."
        
        Returns:
            {channel_index: [il, ql, ir, qr], ...}
        """
        iq_data = {}
        line = remove_ansi_escape(text)
        
        # 尝试匹配 "IQ: ..." 格式
        payload = None
        m = self.re_iq_line_has_prefix.search(line)
        if m:
            payload = m.group(1)
        elif "ch:" in line:
            # 如果直接包含ch:，也尝试解析
            payload = line
        
        if payload:
            for match in self.re_iq_tokens.finditer(payload):
                ch = int(match.group(1))
                il = safe_float(match.group(2))
                ql = safe_float(match.group(3))
                ir = safe_float(match.group(4))
                qr = safe_float(match.group(5))
                iq_data[ch] = [il, ql, ir, qr]
        
        return iq_data
    
    def parse(self, text: str) -> Optional[Dict]:
        """
        解析接收到的文本数据
        支持两种模式：
        1. 帧模式：解析BLE CS Report帧格式
           - 帧头：== Basic Report == index:X, timestamp:Y
           - 帧尾：== End Report ==（检测到帧尾时完成当前帧）
           - IQ数据：ch:0:il,ql,ir,qr;ch:1:...
        2. 简单模式：解析JSON或键值对格式（向后兼容）
        
        Args:
            text: 从串口接收的文本字符串
        
        Returns:
            解析后的数据字典：
            - 帧模式：{'frame': True, 'index': int, 'timestamp_ms': int, 'channels': {ch: {'amplitude': float, 'phase': float, 'I': float, 'Q': float}}}
            - 简单模式：{'var_name': value, ...}
            如果解析失败返回None
        """
        if not text:
            return None
        
        # 优先尝试解析帧头
        frame_header = self.parse_frame_header(text)
        if frame_header:
            # 开始新帧
            index = frame_header['index']
            timestamp_ms = frame_header['timestamp_ms']
            
            # 如果之前有未完成的帧，记录警告（正常情况下应该已经通过帧尾完成）
            if self.current_frame is not None:
                old_index = self.current_frame['index']
                self.logger.warning(f"[帧解析] 检测到新帧头，但上一帧未完成（缺少帧尾）: index={old_index}")
                # 清空未完成的帧
                self.current_frame = None
            
            # 创建新帧
            self.current_frame = {
                'index': index,
                'timestamp_ms': timestamp_ms,
                'iq_data': OrderedDict()
            }
            self.logger.info(f"[帧解析] 开始新帧: index={index}, timestamp={timestamp_ms}")
            
            # 新帧头不返回数据，等待帧尾
            return None
        
        # 尝试解析帧尾（在解析IQ数据之前）
        if self.current_frame is not None:
            if self.parse_frame_footer(text):
                # 检测到帧尾，立即完成当前帧
                completed_frame = self.finalize_frame()
                if completed_frame:
                    self.logger.info(f"[帧解析] 检测到帧尾，完成当前帧: index={completed_frame['index']}, 通道数={len(completed_frame.get('channels', {}))}")
                else:
                    self.logger.warning(f"[帧解析] 检测到帧尾，但当前帧无法完成")
                return completed_frame
        
        # 尝试解析IQ数据
        if self.current_frame is not None:
            iq_data = self.parse_iq_data(text)
            if iq_data:
                # 合并IQ数据到当前帧
                self.current_frame['iq_data'].update(iq_data)
                # 继续累积数据，等待帧尾标记
                return None
        
        # 如果既不是帧头也不是IQ数据，尝试向后兼容的简单格式
        try:
            # 尝试JSON格式
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    result = {}
                    for k, v in data.items():
                        try:
                            result[k] = float(v)
                        except (ValueError, TypeError):
                            pass
                    return result if result else None
            except json.JSONDecodeError:
                pass
            
            # 尝试键值对格式
            pattern = r'(\w+):([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)'
            matches = re.findall(pattern, text)
            if matches:
                result = {}
                for key, value in matches:
                    try:
                        result[key] = float(value)
                    except ValueError:
                        pass
                return result if result else None
                
        except Exception as e:
            self.logger.debug(f"数据解析失败: {e}, 原始数据: {text}")
        
        return None
    
    def finalize_frame(self, index: int = None) -> Optional[Dict]:
        """
        完成当前帧的解析，将IQ数据转换为幅值和相位
        
        Args:
            index: 指定要完成的帧索引，None则完成当前帧
        
        Returns:
            完成后的帧数据，格式：
            {
                'frame': True,
                'index': int,
                'timestamp_ms': int,
                'channels': {
                    ch: {
                        'amplitude': float,
                        'phase': float,  # 弧度
                        'I': float,
                        'Q': float,
                        'il': float, 'ql': float, 'ir': float, 'qr': float
                    }
                }
            }
        """
        if index is None:
            if self.current_frame is None:
                return None
            frame = self.current_frame
            self.current_frame = None
        else:
            if index not in self.frame_buffer:
                return None
            frame = self.frame_buffer.pop(index)
        
        if not frame or not frame.get('iq_data'):
            return None
        
        # 转换IQ数据为幅值和相位
        result = {
            'frame': True,
            'index': frame['index'],
            'timestamp_ms': frame['timestamp_ms'],
            'channels': OrderedDict()
        }
        
        # 按通道顺序处理
        for ch in sorted(frame['iq_data'].keys()):
            il, ql, ir, qr = frame['iq_data'][ch]
            
            # 跳过无效数据（全0或NaN）
            if any(math.isnan(x) for x in [il, ql, ir, qr]):
                continue
            
            if all(abs(x) < 1e-6 for x in [il, ql, ir, qr]):
                continue  # 全0数据
            
            # 转换为总幅值和相位（使用组合后的IQ）
            I, Q = self.combine_iq(il, ql, ir, qr)
            amplitude, phase = self.iq_to_amplitude_phase(il, ql, ir, qr)
            
            # 计算Local幅值和相位（只用il, ql）
            local_amplitude = math.hypot(il, ql)  # sqrt(il^2 + ql^2)
            local_phase = math.atan2(ql, il)  # 相位（弧度）
            
            # 计算Remote幅值和相位（只用ir, qr）
            remote_amplitude = math.hypot(ir, qr)  # sqrt(ir^2 + qr^2)
            remote_phase = math.atan2(qr, ir)  # 相位（弧度）
            
            result['channels'][ch] = {
                'amplitude': amplitude,      # 总幅值
                'phase': phase,            # 总相位（弧度）
                'I': I,
                'Q': Q,
                'local_amplitude': local_amplitude,    # Local幅值
                'local_phase': local_phase,           # Local相位（弧度）
                'remote_amplitude': remote_amplitude, # Remote幅值
                'remote_phase': remote_phase,        # Remote相位（弧度）
                'il': il, 'ql': ql, 'ir': ir, 'qr': qr
            }
        
        return result
    
    def flush_frame(self) -> Optional[Dict]:
        """强制完成并返回当前帧"""
        return self.finalize_frame()
    
    def clear_buffer(self):
        """清空缓冲区"""
        self.frame_buffer.clear()
        self.current_frame = None
