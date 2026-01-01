#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
呼吸估计算法模块
包含中值滤波、高通滤波、带通滤波、FFT分析、信道自适应等功能
"""
import numpy as np
from typing import Dict, List, Tuple, Optional, Callable
import logging
import time

try:
    from .utils.signal_algrithom import (
        median_filter_1d, 
        highpass_filter_zero_phase, 
        bandpass_filter_zero_phase
    )
    from .config import config
except ImportError:
    from utils.signal_algrithom import (
        median_filter_1d, 
        highpass_filter_zero_phase, 
        bandpass_filter_zero_phase
    )
    from config import config


class BreathingEstimator:
    """呼吸估计类"""
    
    def __init__(self, frame_type: str = "信道探测帧"):
        """
        初始化呼吸估计器
        
        Args:
            frame_type: 帧类型字符串，如 "方向估计帧" 或 "信道探测帧"
        """
        self.logger = logging.getLogger(__name__)
        
        # 从config加载默认参数（根据帧类型）
        self.set_default_params_for_frame_type(frame_type)
        
        # 信道自适应相关状态（从config加载默认值）
        self.adaptive_enabled = config.breathing_adaptive_enabled
        self.adaptive_top_n = config.breathing_adaptive_top_n
        self.adaptive_only_display_channels = config.breathing_adaptive_only_display_channels
        self.adaptive_low_energy_threshold = config.breathing_adaptive_low_energy_threshold
        
        # 自适应状态
        self.adaptive_selected_channel: Optional[int] = None  # 自适应选择的信道
        self.current_best_channels: List[Tuple[int, float]] = []  # 当前时间窗口的最佳信道列表（按能量排序）
        self.adaptive_low_energy_start_time: Optional[float] = None  # 低能量开始时间（用于超时检测）
        
        # 数据访问接口（由外部设置）
        self.data_accessor: Optional[Callable] = None  # 数据访问回调函数
    
    def set_default_params_for_frame_type(self, frame_type: str):
        """
        根据帧类型从config加载默认参数
        
        Args:
            frame_type: 帧类型字符串，如 "方向估计帧" 或 "信道探测帧"
        """
        if frame_type == "方向估计帧":
            # 从config加载方向估计帧的默认参数
            self.sampling_rate = config.breathing_df_sampling_rate
            self.median_filter_window = config.breathing_df_median_filter_window
            self.highpass_cutoff = config.breathing_df_highpass_cutoff
            self.highpass_order = config.breathing_df_highpass_order
            self.bandpass_lowcut = config.breathing_df_bandpass_lowcut
            self.bandpass_highcut = config.breathing_df_bandpass_highcut
            self.bandpass_order = config.breathing_df_bandpass_order
            self.breath_freq_low = config.breathing_df_breath_freq_low
            self.breath_freq_high = config.breathing_df_breath_freq_high
            self.total_freq_low = config.breathing_df_total_freq_low
            self.total_freq_high = config.breathing_df_total_freq_high
        else:
            # 从config加载信道探测帧的默认参数
            self.sampling_rate = config.breathing_cs_sampling_rate
            self.median_filter_window = config.breathing_cs_median_filter_window
            self.highpass_cutoff = config.breathing_cs_highpass_cutoff
            self.highpass_order = config.breathing_cs_highpass_order
            self.bandpass_lowcut = config.breathing_cs_bandpass_lowcut
            self.bandpass_highcut = config.breathing_cs_bandpass_highcut
            self.bandpass_order = config.breathing_cs_bandpass_order
            self.breath_freq_low = config.breathing_cs_breath_freq_low
            self.breath_freq_high = config.breathing_cs_breath_freq_high
            self.total_freq_low = config.breathing_cs_total_freq_low
            self.total_freq_high = config.breathing_cs_total_freq_high
        
        self.logger.info(
            f"已从config加载帧类型 '{frame_type}' 的默认参数: "
            f"采样率={self.sampling_rate}Hz, 中值滤波窗口={self.median_filter_window}"
        )
    
    def process_signal(self, signal: np.ndarray, data_type: str = 'amplitude') -> Dict:
        """
        处理信号：中值滤波 + 高通滤波
        
        Args:
            signal: 输入信号数组
            data_type: 数据类型（用于日志）
        
        Returns:
            处理后的数据字典
        """
        if len(signal) == 0:
            return {}
        
        # 中值滤波
        median_filtered = median_filter_1d(signal, window_size=self.median_filter_window)
        
        # 高通滤波（去直流和趋势）
        highpass_filtered = highpass_filter_zero_phase(
            median_filtered,
            cutoff_freq=self.highpass_cutoff,
            sampling_rate=self.sampling_rate,
            order=self.highpass_order
        )
        
        return {
            'original': signal,
            'median_filtered': median_filtered,
            'highpass_filtered': highpass_filtered
        }
    
    def analyze_window(self, window_data: np.ndarray, apply_hanning: bool = True) -> Dict:
        """
        分析单个时间窗：汉宁窗 + 带通滤波 + FFT
        
        Args:
            window_data: 时间窗数据（已经过中值+高通滤波）
            apply_hanning: 是否应用汉宁窗
        
        Returns:
            分析结果字典，包含：
            - windowed_data: 加窗后的数据
            - bandpass_filtered: 带通滤波后的数据
            - fft_freq_before: 带通前的频率轴
            - fft_power_before: 带通前的功率谱
            - fft_freq_after: 带通后的频率轴
            - fft_power_after: 带通后的功率谱
            - breathing_freq: 估计的呼吸频率（Hz）
        """
        if len(window_data) == 0:
            return {}
        
        # 应用汉宁窗
        if apply_hanning:
            hanning_window = np.hanning(len(window_data))
            windowed_data = window_data * hanning_window
        else:
            windowed_data = window_data.copy()
        
        # 计算带通前的FFT
        fft_before = np.fft.rfft(windowed_data)
        fft_freq_before = np.fft.rfftfreq(len(windowed_data), 1.0 / self.sampling_rate)
        fft_power_before = np.abs(fft_before) ** 2
        
        # 带通滤波
        bandpass_filtered = bandpass_filter_zero_phase(
            windowed_data,
            lowcut=self.bandpass_lowcut,
            highcut=self.bandpass_highcut,
            sampling_rate=self.sampling_rate,
            order=self.bandpass_order
        )
        
        # 计算带通后的FFT
        fft_after = np.fft.rfft(bandpass_filtered)
        fft_freq_after = np.fft.rfftfreq(len(bandpass_filtered), 1.0 / self.sampling_rate)
        fft_power_after = np.abs(fft_after) ** 2
        
        # 估计呼吸频率（在带通范围内找最大功率对应的频率）
        freq_mask = (fft_freq_after >= self.bandpass_lowcut) & (fft_freq_after <= self.bandpass_highcut)
        if np.any(freq_mask):
            max_power_idx = np.argmax(fft_power_after[freq_mask])
            freq_indices = np.where(freq_mask)[0]
            max_freq_idx = freq_indices[max_power_idx]
            breathing_freq = fft_freq_after[max_freq_idx]
        else:
            breathing_freq = np.nan
        
        return {
            'windowed_data': windowed_data,
            'bandpass_filtered': bandpass_filtered,
            'fft_freq_before': fft_freq_before,
            'fft_power_before': fft_power_before,
            'fft_freq_after': fft_freq_after,
            'fft_power_after': fft_power_after,
            'breathing_freq': breathing_freq
        }
    
    def detect_breathing(self, window_data: np.ndarray, threshold: float = 0.6) -> Dict:
        """
        检测时间窗内是否有呼吸
        
        Args:
            window_data: 时间窗数据（已经过中值+高通滤波）
            threshold: 能量比例阈值
        
        Returns:
            检测结果字典，包含：
            - has_breathing: 是否有呼吸
            - energy_ratio: 呼吸频率能量占比
            - breathing_freq: 估计的呼吸频率（Hz），如果没有呼吸则为NaN
        """
        if len(window_data) == 0:
            return {
                'has_breathing': False,
                'energy_ratio': 0.0,
                'breathing_freq': np.nan
            }
        
        # 应用汉宁窗
        hanning_window = np.hanning(len(window_data))
        windowed_data = window_data * hanning_window
        
        # 计算FFT
        fft_values = np.fft.rfft(windowed_data)
        fft_power = np.abs(fft_values) ** 2
        fft_freq = np.fft.rfftfreq(len(windowed_data), 1.0 / self.sampling_rate)
        
        # 计算能量比例
        breath_mask = (fft_freq >= self.breath_freq_low) & (fft_freq <= self.breath_freq_high)
        total_mask = (fft_freq >= self.total_freq_low) & (fft_freq <= self.total_freq_high)
        
        breath_energy = np.sum(fft_power[breath_mask])
        total_energy = np.sum(fft_power[total_mask])
        
        energy_ratio = breath_energy / total_energy if total_energy > 0 else 0.0
        
        # 判断是否有呼吸
        has_breathing = energy_ratio >= threshold
        
        # 如果有呼吸，估计频率
        if has_breathing:
            # 带通滤波后估计频率
            analysis = self.analyze_window(window_data, apply_hanning=True)
            breathing_freq = analysis.get('breathing_freq', np.nan)
        else:
            breathing_freq = np.nan
        
        return {
            'has_breathing': has_breathing,
            'energy_ratio': energy_ratio,
            'breathing_freq': breathing_freq
        }
    
    def estimate_breathing_rate(self, breathing_freq: float) -> float:
        """
        将呼吸频率（Hz）转换为呼吸次数（次/分钟）
        
        Args:
            breathing_freq: 呼吸频率（Hz）
        
        Returns:
            呼吸次数（次/分钟）
        """
        if np.isnan(breathing_freq) or breathing_freq <= 0:
            return np.nan
        return breathing_freq * 60.0
    
    def set_data_accessor(self, data_accessor: Callable):
        """
        设置数据访问接口
        
        Args:
            data_accessor: 数据访问回调函数，需要提供以下接口：
                - get_all_channels() -> List[int]: 获取所有可用信道
                - get_channel_data(channel: int, max_frames: int, data_type: str) -> Tuple[np.ndarray, np.ndarray]: 
                  获取指定信道的数据，返回 (indices, values)
        """
        self.data_accessor = data_accessor
    
    def set_adaptive_config(self, enabled: bool = None, top_n: int = None, 
                           only_display_channels: bool = None, 
                           low_energy_threshold: float = None):
        """
        设置信道自适应配置
        
        Args:
            enabled: 是否启用最佳呼吸信道选取
            top_n: 选择前N个最佳信道
            only_display_channels: 是否只在显示信道范围内选取
            low_energy_threshold: 低能量持续时间阈值（秒）
        """
        if enabled is not None:
            self.adaptive_enabled = enabled
        if top_n is not None:
            self.adaptive_top_n = top_n
        if only_display_channels is not None:
            self.adaptive_only_display_channels = only_display_channels
        if low_energy_threshold is not None:
            self.adaptive_low_energy_threshold = low_energy_threshold
    
    def calculate_all_channels_energy_ratios(self, data_type: str, threshold: float, 
                                            max_frames: int,
                                            display_channels: Optional[List[int]] = None) -> List[Tuple[int, float]]:
        """
        计算所有可用信道的呼吸频段能量占比
        
        Args:
            data_type: 数据类型
            threshold: 能量占比阈值
            max_frames: 最大帧数
            display_channels: 显示的信道列表（如果启用"只在显示信道范围内选取"）
            
        Returns:
            按能量占比降序排列的信道列表，格式为 [(channel, energy_ratio), ...]
        """
        if self.data_accessor is None:
            self.logger.warning("数据访问接口未设置，无法计算信道能量占比")
            return []
        
        # 获取所有可用信道
        all_channels = self.data_accessor('get_all_channels')()
        if not all_channels:
            return []
        
        # 如果启用了"只在显示信道范围内选取"，则只计算显示的信道
        channels_to_check = all_channels
        if self.adaptive_only_display_channels and display_channels is not None:
            channels_to_check = [ch for ch in all_channels if ch in display_channels]
        
        channel_energy_ratios = []
        
        for ch in channels_to_check:
            # 获取该信道最近X帧的数据
            indices, values = self.data_accessor('get_channel_data')(ch, max_frames, data_type)
            
            if len(values) < max_frames:
                continue
            
            if len(values) == 0:
                continue
            
            # 处理信号
            signal = np.array(values)
            processed = self.process_signal(signal, data_type)
            
            if 'highpass_filtered' not in processed:
                continue
            
            # 检测呼吸并获取能量占比
            detection = self.detect_breathing(
                processed['highpass_filtered'], threshold=threshold
            )
            
            channel_energy_ratios.append((ch, detection['energy_ratio']))
        
        # 按能量占比降序排序
        channel_energy_ratios.sort(key=lambda x: x[1], reverse=True)
        
        return channel_energy_ratios
    
    def select_adaptive_channel(self, data_type: str, threshold: float, max_frames: int,
                               display_channels: Optional[List[int]] = None,
                               manual_channel: Optional[int] = None) -> Dict:
        """
        选择自适应信道（核心逻辑）
        
        Args:
            data_type: 数据类型
            threshold: 能量占比阈值
            max_frames: 最大帧数
            display_channels: 显示的信道列表
            manual_channel: 手动选择的信道（作为fallback）
            
        Returns:
            包含以下字段的字典：
            - selected_channel: 选中的信道（int或None）
            - best_channels: 最佳信道列表 [(channel, energy_ratio), ...]
            - need_reselect: 是否需要重新选择（bool）
        """
        if not self.adaptive_enabled:
            return {
                'selected_channel': manual_channel,
                'best_channels': [],
                'need_reselect': False
            }
        
        # 如果已经选出了最佳信道，检查是否需要重新选择
        if self.adaptive_selected_channel is not None:
            # 只检查当前信道的能量占比
            if self.data_accessor is None:
                return {
                    'selected_channel': self.adaptive_selected_channel,
                    'best_channels': self.current_best_channels,
                    'need_reselect': False
                }
            
            indices_check, values_check = self.data_accessor('get_channel_data')(
                self.adaptive_selected_channel, max_frames, data_type
            )
            
            # 只检查当前信道的能量占比
            if len(values_check) >= max_frames and len(values_check) > 0:
                signal_check = np.array(values_check)
                processed_check = self.process_signal(signal_check, data_type)
                
                if 'highpass_filtered' in processed_check:
                    detection_check = self.detect_breathing(
                        processed_check['highpass_filtered'], threshold=threshold
                    )
                    current_ch_ratio = detection_check['energy_ratio']
                    
                    # 如果当前信道的能量占比低于阈值，开始计时
                    if current_ch_ratio < threshold:
                        if self.adaptive_low_energy_start_time is None:
                            self.adaptive_low_energy_start_time = time.time()
                        else:
                            # 检查是否超过超时时长
                            elapsed = time.time() - self.adaptive_low_energy_start_time
                            if elapsed >= self.adaptive_low_energy_threshold:
                                # 超过超时时长，需要重新选择
                                self.adaptive_selected_channel = None
                                self.adaptive_low_energy_start_time = None
                                # 继续执行下面的逻辑，重新计算所有信道
                            else:
                                # 还在超时时间内，继续在当前信道上执行
                                self.current_best_channels = [(self.adaptive_selected_channel, current_ch_ratio)]
                                return {
                                    'selected_channel': self.adaptive_selected_channel,
                                    'best_channels': self.current_best_channels,
                                    'need_reselect': False
                                }
                    else:
                        # 能量占比高于阈值，重置计时，继续在当前信道上执行
                        self.adaptive_low_energy_start_time = None
                        self.current_best_channels = [(self.adaptive_selected_channel, current_ch_ratio)]
                        return {
                            'selected_channel': self.adaptive_selected_channel,
                            'best_channels': self.current_best_channels,
                            'need_reselect': False
                        }
            
            # 数据不足或处理失败，继续在当前信道上执行
            self.current_best_channels = [(self.adaptive_selected_channel, 0.0)]
            return {
                'selected_channel': self.adaptive_selected_channel,
                'best_channels': self.current_best_channels,
                'need_reselect': False
            }
        
        # 如果还没有选择信道，或者需要重新选择（超时后）
        # 计算所有信道的能量占比
        channel_energy_ratios = self.calculate_all_channels_energy_ratios(
            data_type, threshold, max_frames, display_channels
        )
        
        if channel_energy_ratios:
            # 选择前N个最佳信道
            top_n = min(self.adaptive_top_n, len(channel_energy_ratios))
            self.current_best_channels = channel_energy_ratios[:top_n]
            
            # 选择能量占比最高且高于阈值的信道
            best_ch = None
            for ch, ratio in self.current_best_channels:
                if ratio >= threshold:
                    best_ch = ch
                    break
            
            if best_ch is not None:
                # 选出了最佳信道，设置并停止计算所有信道
                self.adaptive_selected_channel = best_ch
                self.adaptive_low_energy_start_time = None
                return {
                    'selected_channel': best_ch,
                    'best_channels': self.current_best_channels,
                    'need_reselect': False
                }
            else:
                # 没有找到能量占比高于阈值的信道
                return {
                    'selected_channel': manual_channel,
                    'best_channels': self.current_best_channels,
                    'need_reselect': False
                }
        else:
            # 没有有效信道
            return {
                'selected_channel': manual_channel,
                'best_channels': [],
                'need_reselect': False
            }
    
    def reset_adaptive_state(self):
        """重置自适应状态"""
        self.adaptive_selected_channel = None
        self.adaptive_low_energy_start_time = None
        self.current_best_channels = []
    
    def get_adaptive_state(self) -> Dict:
        """
        获取自适应状态
        
        Returns:
            包含自适应状态的字典
        """
        return {
            'selected_channel': self.adaptive_selected_channel,
            'best_channels': self.current_best_channels,
            'enabled': self.adaptive_enabled
        }
