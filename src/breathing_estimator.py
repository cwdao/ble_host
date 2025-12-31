#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
呼吸估计算法模块
包含中值滤波、高通滤波、带通滤波、FFT分析等功能
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

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
