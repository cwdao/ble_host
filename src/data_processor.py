#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据处理模块
包含频率计算等数据处理功能
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging


class DataProcessor:
    """数据处理类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.data_buffer = {}  # {var_name: [(timestamp, value), ...]}
    
    def add_data(self, timestamp: float, data: Dict[str, float]):
        """
        添加数据点到缓冲区
        
        Args:
            timestamp: 时间戳
            data: 数据字典 {var_name: value}
        """
        for var_name, value in data.items():
            if var_name not in self.data_buffer:
                self.data_buffer[var_name] = []
            self.data_buffer[var_name].append((timestamp, value))
    
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
    
    def clear_buffer(self, var_name: str = None):
        """
        清空数据缓冲区
        
        Args:
            var_name: 变量名，None表示清空所有
        """
        if var_name:
            if var_name in self.data_buffer:
                self.data_buffer[var_name] = []
        else:
            self.data_buffer.clear()
    
    def get_all_variables(self) -> List[str]:
        """获取所有变量名"""
        return list(self.data_buffer.keys())

