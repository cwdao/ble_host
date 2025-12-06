#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
统一管理应用程序的配置项
"""
from dataclasses import dataclass
from typing import List


@dataclass
class AppConfig:
    """应用程序配置"""
    # 版本信息
    version: str = "2.1.0"
    version_date: str = "2025-12-06"
    version_author: str = "chwn@outlook.ie, HKUST(GZ)"
    
    # 窗口配置
    base_window_width: int = 1200
    base_window_height: int = 800
    
    # 字体配置
    base_font_size: int = 9
    min_font_size: int = 7
    max_font_size: int = 12
    version_font_offset: int = 1  # 版本信息字体比主字体小多少
    
    # Plot配置
    base_plot_width_inch: float = 12.0
    base_plot_height_inch: float = 6.3
    max_plot_width_inch: float = 16.0
    max_plot_height_inch: float = 10.0
    plot_scale_adjustment_factor: float = 0.5  # DPI缩放调整因子（50%）
    plot_dpi_min: int = 100
    plot_dpi_max: int = 200
    plot_margin_px: int = 20  # Plot边距（像素）
    
    # 数据更新配置
    update_interval_sec: float = 0.05  # 数据更新间隔（秒）
    freq_list_update_interval_sec: float = 1.0  # 频率列表更新间隔（秒）
    
    # 帧模式默认配置
    default_frame_mode: bool = True  # 保留用于向后兼容，但不再使用
    default_frame_type: str = "演示帧"  # 默认帧类型
    frame_type_options: List[str] = None  # 帧类型列表
    default_display_channels: str = "0-9"
    default_display_max_frames: int = 50
    max_display_max_frames: int = 100
    
    # 串口配置
    default_baudrate: str = "230400"
    baudrate_options: List[str] = None
    
    # 数据处理配置
    default_frequency_duration: float = 15.0  # 默认频率计算时间窗口（秒）
    max_freq_list_channels: int = 20  # 频率列表最多显示的通道数
    
    # DPI信息更新延迟（毫秒）
    dpi_info_update_delay_ms: int = 200
    plot_resize_delay_ms: int = 300
    tab_changed_delay_ms: int = 50
    
    def __post_init__(self):
        """初始化后处理"""
        if self.baudrate_options is None:
            self.baudrate_options = ["9600", "19200", "38400", "57600", "115200", "230400"]
        if self.frame_type_options is None:
            # 帧类型列表：演示帧对应原来的帧模式，其他选项可以后续添加（目前先留空）
            self.frame_type_options = ["演示帧"]


# 全局配置实例
config = AppConfig()

