#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据处理模块
包含频率计算等数据处理功能，支持多通道帧数据
"""
import numpy as np
import copy
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
        
        # 原始帧数据列表：用于保存功能，保存完整的帧数据
        self.raw_frames = []  # [frame_data, ...] 按接收顺序保存
        
        # 记录上一个帧的信道（用于检测信道变化）
        self.last_frame_channels = set()  # 上一个帧的信道集合
    
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
    
    def clear_channel_data(self, channel: int):
        """
        清空指定信道的累积数据（用于信道切换时重新开始累积）
        
        Args:
            channel: 信道号
        """
        if channel in self.frame_buffer:
            # 清空该信道的所有数据类型
            for data_type in self.frame_buffer[channel]:
                self.frame_buffer[channel][data_type] = []
            self.logger.info(f"[信道切换] 已清空信道 {channel} 的累积数据，重新开始累积")
    
    def add_frame_data(self, frame_data: Dict, detect_channel_change: bool = False) -> Optional[Tuple[List[int], List[int]]]:
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
            detect_channel_change: 是否检测信道变化（DF模式使用）
        
        Returns:
            如果检测到信道变化并清空了数据，返回 (旧信道列表, 新信道列表) 元组；否则返回None
        """
        if not frame_data.get('frame'):
            return None
        
        index = frame_data['index']
        timestamp_ms = frame_data['timestamp_ms']
        channels = frame_data.get('channels', {})
        current_channels = set(channels.keys())
        
        # 检测信道变化（DF模式：每个帧只有一个信道）
        channel_changed = False
        old_channels = None
        cleared_channels = None
        
        if detect_channel_change and self.last_frame_channels:
            # 检查信道是否发生变化（当前帧的信道与上一个帧不同）
            if current_channels != self.last_frame_channels:
                # 信道发生变化，清空当前帧所有信道的累积数据（重新开始累积）
                cleared_channels = []
                old_channels = list(self.last_frame_channels)  # 保存旧信道用于返回
                channel_changed = True
                
                for ch in current_channels:
                    # 总是清空新信道的累积数据（无论是否有数据），确保重新开始累积
                    if ch in self.frame_buffer:
                        self.clear_channel_data(ch)
                    cleared_channels.append(ch)
                
                if cleared_channels:
                    self.logger.info(
                        f"[信道切换] 检测到信道变化: {old_channels} -> {current_channels}，"
                        f"已清空信道 {cleared_channels} 的累积数据，重新开始累积"
                    )
        
        # 更新上一个帧的信道（无论是否变化都要更新，避免重复检测）
        self.last_frame_channels = current_channels.copy()
        
        # 如果检测到信道变化，返回信息（在更新last_frame_channels之后）
        if channel_changed and cleared_channels:
            return (old_channels, cleared_channels)
        
        self.logger.debug(f"[数据存储] 添加帧 index={index}, 通道数={len(channels)}")
        
        # 保存原始帧数据
        # 使用浅拷贝+channels的浅拷贝，因为frame_data在解析后不会被修改
        # 深拷贝会在保存时进行，避免每次添加时的性能开销
        frame_copy = {
            'frame': frame_data.get('frame'),
            'index': frame_data.get('index'),
            'timestamp_ms': frame_data.get('timestamp_ms'),
            'channels': {ch: ch_data.copy() for ch, ch_data in channels.items()}
        }
        self.raw_frames.append(frame_copy)
        
        # 保存元数据
        self.frame_metadata.append((index, timestamp_ms))
        
        # 为每个通道添加数据点
        for ch, channel_data in channels.items():
            amplitude = channel_data.get('amplitude', 0.0)
            phase = channel_data.get('phase', 0.0)
            local_amplitude = channel_data.get('local_amplitude', 0.0)
            local_phase = channel_data.get('local_phase', 0.0)
            remote_amplitude = channel_data.get('remote_amplitude', 0.0)
            remote_phase = channel_data.get('remote_phase', 0.0)
            
            # 确保ch是整数类型
            if not isinstance(ch, int):
                try:
                    ch = int(ch)
                except (ValueError, TypeError):
                    self.logger.warning(f"[数据存储] 通道号类型错误: {ch}, type={type(ch)}")
                    continue
            
            # 使用index作为x轴（也可以使用timestamp_ms）
            if ch not in self.frame_buffer:
                self.frame_buffer[ch] = {
                    'amplitude': [], 'phase': [],
                    'local_amplitude': [], 'local_phase': [],
                    'remote_amplitude': [], 'remote_phase': [],
                    'p_avg': []  # DF模式：功率值
                }
            
            # 存储所有数据类型
            self.frame_buffer[ch]['amplitude'].append((index, amplitude))
            self.frame_buffer[ch]['phase'].append((index, phase))
            self.frame_buffer[ch]['local_amplitude'].append((index, local_amplitude))
            self.frame_buffer[ch]['local_phase'].append((index, local_phase))
            self.frame_buffer[ch]['remote_amplitude'].append((index, remote_amplitude))
            self.frame_buffer[ch]['remote_phase'].append((index, remote_phase))
            
            # DF模式：存储功率值（p_avg）
            p_avg = channel_data.get('p_avg', 0.0)
            self.frame_buffer[ch]['p_avg'].append((index, p_avg))
            self.logger.debug(
                f"[数据存储] 通道{ch}: index={index}, "
                f"amplitude={amplitude:.2f}, phase={phase:.4f}, "
                f"local_amp={local_amplitude:.2f}, remote_amp={remote_amplitude:.2f}"
            )
        
        # 如果没有检测到信道变化，返回None
        return None
    
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
    
    def get_frame_data_range(self, channel: int, max_frames: int = None, 
                              data_type: str = 'amplitude') -> Tuple[np.ndarray, np.ndarray]:
        """
        获取指定通道的帧数据
        
        Args:
            channel: 通道号
            max_frames: 最多返回多少帧，None表示返回全部
            data_type: 数据类型，支持：
                - 'amplitude': 总幅值
                - 'phase': 总相位
                - 'local_amplitude': Local幅值
                - 'local_phase': Local相位
                - 'remote_amplitude': Remote幅值
                - 'remote_phase': Remote相位
                - 'p_avg': 功率值（DF模式）
        
        Returns:
            (index数组, 数据数组)
        """
        if channel not in self.frame_buffer:
            return np.array([]), np.array([])
        
        channel_data = self.frame_buffer[channel]
        
        # 兼容旧格式（列表）和新格式（字典）
        if isinstance(channel_data, list):
            # 旧格式：[(index, amplitude), ...]
            data_points = channel_data
        elif isinstance(channel_data, dict):
            # 新格式：{'amplitude': [...], 'phase': [...], ...}
            data_points = channel_data.get(data_type, [])
        else:
            return np.array([]), np.array([])
        
        # 应用max_frames限制（确保新增信道也遵循此规则）
        original_count = len(data_points)
        if max_frames and len(data_points) > max_frames:
            data_points = data_points[-max_frames:]
            self.logger.debug(
                f"[数据限制] 通道{channel} ({data_type}): "
                f"原始数据点={original_count}, 限制后={len(data_points)} (max_frames={max_frames})"
            )
        
        if not data_points:
            return np.array([]), np.array([])
        
        indices = np.array([idx for idx, _ in data_points])
        values = np.array([val for _, val in data_points])
        
        return indices, values
    
    def get_all_frame_channels(self) -> List[int]:
        """获取所有有数据的通道号"""
        channels = []
        for ch in self.frame_buffer.keys():
            # 检查是否有有效数据
            ch_data = self.frame_buffer[ch]
            if isinstance(ch_data, dict):
                if ch_data.get('amplitude'):
                    channels.append(ch)
            elif isinstance(ch_data, list) and ch_data:
                channels.append(ch)
        return sorted(channels)
    
    def _check_sampling_uniformity(self, times: np.ndarray, threshold: float = 0.1) -> Tuple[bool, float]:
        """
        检查采样是否均匀
        
        Args:
            times: 时间戳数组
            threshold: 相对变化阈值，如果采样间隔的相对标准差超过此值，认为非均匀
        
        Returns:
            (是否均匀, 平均采样间隔)
        """
        if len(times) < 2:
            return False, 0.0
        
        intervals = np.diff(times)
        mean_interval = np.mean(intervals)
        
        if mean_interval <= 0:
            return False, 0.0
        
        # 计算相对标准差（变异系数）
        relative_std = np.std(intervals) / mean_interval
        
        is_uniform = relative_std < threshold
        
        return is_uniform, mean_interval
    
    def _resample_to_uniform(self, times: np.ndarray, values: np.ndarray, 
                             target_dt: float = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        将非均匀采样数据重采样到均匀网格
        
        Args:
            times: 原始时间戳数组
            values: 原始数值数组
            target_dt: 目标采样间隔，None表示使用平均间隔
        
        Returns:
            (均匀时间数组, 重采样后的数值数组)
        """
        if target_dt is None:
            target_dt = np.mean(np.diff(times))
        
        if target_dt <= 0:
            return times, values
        
        # 创建均匀时间网格
        t_start = times[0]
        t_end = times[-1]
        uniform_times = np.arange(t_start, t_end + target_dt, target_dt)
        
        # 使用numpy的线性插值重采样
        if len(times) > 1:
            # numpy.interp 进行线性插值
            # 对于超出范围的值，使用边界值填充
            uniform_values = np.interp(
                uniform_times, 
                times, 
                values,
                left=values[0],
                right=values[-1]
            )
        else:
            uniform_values = np.full_like(uniform_times, values[0])
        
        return uniform_times, uniform_values
    
    def _prepare_fft_data(self, values: np.ndarray, apply_window: bool = True) -> Tuple[np.ndarray, int]:
        """
        准备FFT数据：调整长度为2的幂次方，应用窗函数
        
        Args:
            values: 原始数据数组
            apply_window: 是否应用汉明窗
        
        Returns:
            (处理后的数据数组, 原始数据长度)
        """
        n_original = len(values)
        
        if n_original < 4:
            return values, n_original
        
        # 将长度调整为2的幂次方（向下取整，避免增加数据）
        # 如果已经是2的幂次方，直接使用
        is_power2 = (n_original & (n_original - 1)) == 0 and n_original > 0
        
        if is_power2:
            n_fft = n_original
        else:
            # 找到小于等于n_original的最大2的幂次方
            n_power2 = 2 ** int(np.log2(n_original))
            
            # 如果长度差异太大（超过50%），使用原始长度
            # 否则截取到2的幂次方长度
            if n_power2 < n_original * 0.5:
                n_fft = n_original
            else:
                n_fft = n_power2
        
        # 截取数据到目标长度（从末尾取，使用最新数据）
        values_fft = values[-n_fft:].copy() if n_fft < n_original else values.copy()
        
        # 应用汉明窗以减少频谱泄漏
        if apply_window and len(values_fft) > 1:
            window = np.hamming(len(values_fft))
            values_fft = values_fft * window
        
        return values_fft, n_original
    
    def calculate_frequency_detailed(self, var_name: str, duration: float = 15.0) -> Optional[Dict]:
        """
        计算指定变量的频率（基于FFT），返回详细信息
        
        Args:
            var_name: 变量名
            duration: 分析的时间长度（秒），默认15秒
        
        Returns:
            包含频率和详细信息的字典，如果计算失败返回None
            {
                'frequency': float,  # 主频率（Hz）
                'n_original': int,   # 原始数据点数
                'n_fft': int,        # FFT点数
                'fft_size_info': str, # FFT点数信息（如 "2^9"）
                'dt': float,         # 采样间隔（秒）
                'is_uniform': bool,   # 是否均匀采样
                'window_applied': bool # 是否应用了窗函数
            }
        """
        times, values = self.get_data_range(var_name, duration)
        
        if len(values) < 4:
            return None
        
        try:
            # 检查采样是否均匀
            is_uniform, mean_dt = self._check_sampling_uniformity(times)
            
            if not is_uniform:
                times, values = self._resample_to_uniform(times, values, mean_dt)
                dt = mean_dt
            else:
                dt = mean_dt
            
            if dt <= 0:
                return None
            
            # 去除直流成分
            values_dc_removed = values - np.mean(values)
            
            # 准备FFT数据
            values_fft, n_original = self._prepare_fft_data(values_dc_removed, apply_window=True)
            n_fft = len(values_fft)
            
            # FFT计算频率
            fft_vals = np.fft.rfft(values_fft)
            fft_freq = np.fft.rfftfreq(n_fft, dt)
            
            # 找到主频率
            power = np.abs(fft_vals)
            if len(power) > 1:
                main_freq_idx = np.argmax(power[1:]) + 1
                main_freq = fft_freq[main_freq_idx]
                
                # 检查是否是2的幂次方
                is_power2 = (n_fft & (n_fft - 1)) == 0 and n_fft > 0
                fft_size_info = f"2^{int(np.log2(n_fft))}" if is_power2 else str(n_fft)
                
                return {
                    'frequency': main_freq,
                    'n_original': n_original,
                    'n_fft': n_fft,
                    'fft_size_info': fft_size_info,
                    'dt': dt,
                    'is_uniform': is_uniform,
                    'window_applied': True
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"频率计算错误: {e}")
            return None
    
    def calculate_frequency(self, var_name: str, duration: float = 15.0) -> Optional[float]:
        """
        计算指定变量的频率（基于FFT）
        支持非均匀采样：自动检测采样均匀性，必要时进行重采样
        
        Args:
            var_name: 变量名
            duration: 分析的时间长度（秒），默认15秒
        
        Returns:
            主频率（Hz），如果计算失败返回None
        """
        freq_info = self.calculate_frequency_detailed(var_name, duration)
        if freq_info is None:
            self.logger.warning(f"数据点数不足，无法计算频率: {var_name}")
            return None
        
        # 简化日志输出
        self.logger.info(f"{var_name}频率计算: {freq_info['frequency']:.4f} Hz")
        
        return freq_info['frequency']
    
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
    
    def calculate_channel_frequency_detailed(self, channel: int, max_frames: int = None, 
                                             data_type: str = 'amplitude') -> Optional[Dict]:
        """
        计算指定通道的频率（基于FFT），返回详细信息
        
        Args:
            channel: 通道号
            max_frames: 最多使用多少帧，None表示全部
            data_type: 数据类型
        
        Returns:
            包含频率和详细信息的字典，如果计算失败返回None
            {
                'frequency': float,  # 主频率（Hz）
                'amplitude': float,  # 主频率的振幅
                'n_original': int,   # 原始帧数
                'n_fft': int,       # FFT点数
                'fft_size_info': str, # FFT点数信息（如 "2^9"）
                'dt': float,         # 采样间隔（秒）
                'is_uniform': bool,   # 是否均匀采样
                'window_applied': bool # 是否应用了窗函数
            }
        """
        indices, amplitudes = self.get_frame_data_range(channel, max_frames, data_type)
        
        if len(amplitudes) < 4:
            return None
        
        try:
            # 去除直流成分
            amplitudes_dc_removed = amplitudes - np.mean(amplitudes)
            
            # 计算采样率（基于timestamp_ms）
            idx_to_ts = {frame_idx: ts_ms for frame_idx, ts_ms in self.frame_metadata}
            timestamps_ms = []
            for idx in indices:
                if idx in idx_to_ts:
                    timestamps_ms.append(idx_to_ts[idx] / 1000.0)
                else:
                    break
            
            # 如果找到了时间戳，使用真实采样率
            if len(timestamps_ms) == len(indices) and len(timestamps_ms) > 1:
                timestamps = np.array(timestamps_ms)
                is_uniform, mean_dt = self._check_sampling_uniformity(timestamps)
                
                if not is_uniform:
                    timestamps, amplitudes_dc_removed = self._resample_to_uniform(
                        timestamps, amplitudes_dc_removed, mean_dt
                    )
                    dt = mean_dt
                else:
                    dt = mean_dt
                
                if dt <= 0:
                    di = np.mean(np.diff(indices)) if len(indices) > 1 else 1.0
                    dt = di
            else:
                if len(indices) > 1:
                    di = np.mean(np.diff(indices))
                    if di <= 0:
                        return None
                    dt = 0.45  # 默认帧间隔
                    is_uniform = False  # 使用默认值，认为非均匀
                else:
                    return None
            
            # 准备FFT数据
            amplitudes_fft, n_original = self._prepare_fft_data(amplitudes_dc_removed, apply_window=True)
            n_fft = len(amplitudes_fft)
            
            # FFT计算频率
            fft_vals = np.fft.rfft(amplitudes_fft)
            fft_freq = np.fft.rfftfreq(n_fft, dt)
            
            # 计算功率谱
            power = np.abs(fft_vals)
            
            if len(power) > 1:
                main_freq_idx = np.argmax(power[1:]) + 1
                main_freq = fft_freq[main_freq_idx]
                main_amplitude = power[main_freq_idx]
                
                # 检查是否是2的幂次方
                is_power2 = (n_fft & (n_fft - 1)) == 0 and n_fft > 0
                fft_size_info = f"2^{int(np.log2(n_fft))}" if is_power2 else str(n_fft)
                
                return {
                    'frequency': main_freq,
                    'amplitude': main_amplitude,
                    'n_original': n_original,
                    'n_fft': n_fft,
                    'fft_size_info': fft_size_info,
                    'dt': dt,
                    'is_uniform': is_uniform,
                    'window_applied': True
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"通道{channel}频率计算错误: {e}")
            return None
    
    def calculate_channel_frequency(self, channel: int, max_frames: int = None, 
                                      data_type: str = 'amplitude') -> Optional[float]:
        """
        计算指定通道的频率（基于FFT，去掉直流成分，选择振幅最大的频率）
        支持非均匀采样：自动检测采样均匀性，必要时进行重采样
        
        Args:
            channel: 通道号
            max_frames: 最多使用多少帧，None表示全部
            data_type: 数据类型，支持：
                - 'amplitude': 总幅值
                - 'phase': 总相位
                - 'local_amplitude': Local幅值
                - 'local_phase': Local相位
                - 'remote_amplitude': Remote幅值
                - 'remote_phase': Remote相位
                - 'p_avg': 功率值（DF模式）
        
        Returns:
            主频率（Hz），如果计算失败返回None
        """
        freq_info = self.calculate_channel_frequency_detailed(channel, max_frames, data_type)
        if freq_info is None:
            self.logger.warning(f"通道{channel}数据点数不足，无法计算频率")
            return None
        
        # 简化日志输出
        self.logger.info(f"通道{channel}频率计算: {freq_info['frequency']:.4f} Hz")
        
        return freq_info['frequency']
    
    def get_channel_statistics(self, channel: int, max_frames: int = None, 
                                data_type: str = 'amplitude') -> Optional[Dict]:
        """
        计算指定通道的统计信息
        
        Args:
            channel: 通道号
            max_frames: 最多使用多少帧，None表示全部
            data_type: 数据类型，支持：
                - 'amplitude': 总幅值
                - 'phase': 总相位
                - 'local_amplitude': Local幅值
                - 'local_phase': Local相位
                - 'remote_amplitude': Remote幅值
                - 'remote_phase': Remote相位
                - 'p_avg': 功率值（DF模式）
        
        Returns:
            统计信息字典
        """
        _, values = self.get_frame_data_range(channel, max_frames, data_type)
        
        if len(values) == 0:
            return None
        
        return {
            'mean': np.mean(values),
            'max': np.max(values),
            'min': np.min(values),
            'std': np.std(values),
            'count': len(values)
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
            self.raw_frames.clear()
    
    def get_all_variables(self) -> List[str]:
        """获取所有简单变量名"""
        return list(self.data_buffer.keys())
    
    def get_frame_count(self) -> int:
        """获取已接收的帧数"""
        return len(self.frame_metadata)
