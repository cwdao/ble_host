#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据处理模块
包含频率计算等数据处理功能，支持多通道帧数据
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import OrderedDict, defaultdict
import logging


class DataProcessor:
    """数据处理类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # 简单变量数据缓冲区：{var_name: [(timestamp, value), ...]}
        self.data_buffer = {}
        
        # 帧数据缓冲区：{channel: [(timestamp, amplitude), ...]}
        self.frame_buffer = {}  # {channel: [(index_or_timestamp, amplitude), ...]}
        self.frame_metadata = []  # [(index, timestamp_ms), ...] 保持顺序
    
    def add_data(self, timestamp: float, data: Dict[str, float]):
        """
        添加简单数据点到缓冲区（向后兼容）
        
        Args:
            timestamp: 时间戳
            data: 数据字典 {var_name: value}
        """
        for var_name, value in data.items():
            if var_name not in self.data_buffer:
                self.data_buffer[var_name] = []
            self.data_buffer[var_name].append((timestamp, value))
    
    def add_frame_data(self, frame_data: Dict):
        """
        添加帧数据
        
        Args:
            frame_data: 帧数据字典，格式：
                {
                    'frame': True,
                    'index': int,
                    'timestamp_ms': int,
                    'channels': {ch: {'amplitude': float, 'phase': float, ...}}
                }
        """
        if not frame_data.get('frame'):
            return
        
        index = frame_data['index']
        timestamp_ms = frame_data['timestamp_ms']
        channels = frame_data.get('channels', {})
        
        self.logger.debug(f"[数据存储] 添加帧 index={index}, 通道数={len(channels)}")
        
        # 保存元数据
        self.frame_metadata.append((index, timestamp_ms))
        
        # 为每个通道添加数据点
        for ch, channel_data in channels.items():
            amplitude = channel_data.get('amplitude', 0.0)
            
            # 确保ch是整数类型
            if not isinstance(ch, int):
                try:
                    ch = int(ch)
                except (ValueError, TypeError):
                    self.logger.warning(f"[数据存储] 通道号类型错误: {ch}, type={type(ch)}")
                    continue
            
            # 使用index作为x轴（也可以使用timestamp_ms）
            if ch not in self.frame_buffer:
                self.frame_buffer[ch] = []
            
            # 存储为 (index, amplitude) 或 (timestamp_ms, amplitude)
            self.frame_buffer[ch].append((index, amplitude))
            self.logger.debug(f"[数据存储] 通道{ch}: index={index}, amplitude={amplitude:.2f}")
    
    def get_data_range(self, var_name: str, duration: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        获取指定变量最近duration秒的数据
        
        Args:
            var_name: 变量名
            duration: 时间长度（秒）
        
        Returns:
            (时间数组, 数值数组)
        """
        if var_name not in self.data_buffer:
            return np.array([]), np.array([])
        
        current_time = self.data_buffer[var_name][-1][0] if self.data_buffer[var_name] else 0
        start_time = current_time - duration
        
        # 筛选时间范围内的数据
        data_points = [
            (t, v) for t, v in self.data_buffer[var_name]
            if t >= start_time
        ]
        
        if not data_points:
            return np.array([]), np.array([])
        
        times = np.array([t for t, _ in data_points])
        values = np.array([v for _, v in data_points])
        
        # 相对时间（从0开始）
        times = times - times[0]
        
        return times, values
    
    def get_frame_data_range(self, channel: int, max_frames: int = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        获取指定通道的帧数据
        
        Args:
            channel: 通道号
            max_frames: 最多返回多少帧，None表示返回全部
        
        Returns:
            (index数组, amplitude数组) 或 (timestamp数组, amplitude数组)
        """
        if channel not in self.frame_buffer:
            return np.array([]), np.array([])
        
        data_points = self.frame_buffer[channel]
        
        if max_frames and len(data_points) > max_frames:
            data_points = data_points[-max_frames:]
        
        if not data_points:
            return np.array([]), np.array([])
        
        indices = np.array([idx for idx, _ in data_points])
        amplitudes = np.array([amp for _, amp in data_points])
        
        return indices, amplitudes
    
    def get_all_frame_channels(self) -> List[int]:
        """获取所有有数据的通道号"""
        return sorted(self.frame_buffer.keys())
    
    def calculate_frequency(self, var_name: str, duration: float = 15.0) -> Optional[float]:
        """
        计算指定变量的频率（基于FFT）
        
        Args:
            var_name: 变量名
            duration: 分析的时间长度（秒），默认15秒
        
        Returns:
            主频率（Hz），如果计算失败返回None
        """
        times, values = self.get_data_range(var_name, duration)
        
        if len(values) < 4:
            self.logger.warning(f"数据点数不足，无法计算频率: {var_name}")
            return None
        
        try:
            # 计算采样率
            if len(times) > 1:
                dt = np.mean(np.diff(times))
                if dt <= 0:
                    return None
                sample_rate = 1.0 / dt
            else:
                return None
            
            # FFT计算频率
            n = len(values)
            fft_vals = np.fft.rfft(values)
            fft_freq = np.fft.rfftfreq(n, dt)
            
            # 找到主频率（排除DC分量）
            power = np.abs(fft_vals)
            if len(power) > 1:
                # 跳过DC分量（索引0）
                main_freq_idx = np.argmax(power[1:]) + 1
                main_freq = fft_freq[main_freq_idx]
                return main_freq
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"频率计算错误: {e}")
            return None
    
    def calculate_statistics(self, var_name: str, duration: float = None) -> Optional[Dict]:
        """
        计算统计信息（均值、最大值、最小值、标准差）
        
        Args:
            var_name: 变量名
            duration: 时间范围，None表示使用所有数据
        
        Returns:
            统计信息字典
        """
        if var_name not in self.data_buffer:
            return None
        
        if duration is None:
            values = np.array([v for _, v in self.data_buffer[var_name]])
        else:
            _, values = self.get_data_range(var_name, duration)
        
        if len(values) == 0:
            return None
        
        return {
            'mean': np.mean(values),
            'max': np.max(values),
            'min': np.min(values),
            'std': np.std(values),
            'count': len(values)
        }
    
    def get_channel_statistics(self, channel: int, max_frames: int = None) -> Optional[Dict]:
        """
        计算指定通道的统计信息
        
        Args:
            channel: 通道号
            max_frames: 最多使用多少帧，None表示全部
        
        Returns:
            统计信息字典
        """
        _, amplitudes = self.get_frame_data_range(channel, max_frames)
        
        if len(amplitudes) == 0:
            return None
        
        return {
            'mean': np.mean(amplitudes),
            'max': np.max(amplitudes),
            'min': np.min(amplitudes),
            'std': np.std(amplitudes),
            'count': len(amplitudes)
        }
    
    def clear_buffer(self, var_name: str = None, clear_frames: bool = False):
        """
        清空数据缓冲区
        
        Args:
            var_name: 变量名，None表示清空所有简单数据
            clear_frames: 是否清空帧数据
        """
        if var_name:
            if var_name in self.data_buffer:
                self.data_buffer[var_name] = []
        else:
            self.data_buffer.clear()
        
        if clear_frames:
            self.frame_buffer.clear()
            self.frame_metadata.clear()
    
    def get_all_variables(self) -> List[str]:
        """获取所有简单变量名"""
        return list(self.data_buffer.keys())
    
    def get_frame_count(self) -> int:
        """获取已接收的帧数"""
        return len(self.frame_metadata)
