#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
统一管理应用程序的配置项
"""
import os
import sys
import json
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class AppConfig:
    """应用程序配置"""
    # 版本信息
    version: str = "3.7.0"
    version_date: str = "2026-01-17"
    version_author: str = "chwn@outlook.ie, HKUST(GZ); Auto (Cursor AI Assistant)"
    # 所保存的文件最低兼容版本，类似minimum API
    version_data_save:str = "3.6.0"
    
    # 窗口配置
    base_window_width: int = 1280
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
    default_frame_type: str = "信道探测帧"  # 默认帧类型
    frame_type_options: List[str] = None  # 帧类型列表
    default_display_channels: str = "0,4,8,12,16,20,24,28,32,36,40,44,48,52,56,60,64,68,72"
    default_display_max_frames: int = 50
    max_display_max_frames: int = 100
    # DF模式专用配置
    df_default_display_max_frames: int = 1000  # DF模式默认显示帧数（50Hz下约20秒）
    df_max_display_max_frames: int = 5000  # DF模式最大显示帧数
    
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
    
    # 数据保存配置
    default_save_directory: str = "./saveData"  # 默认保存目录
    use_auto_save_path: bool = True  # 是否使用自动保存路径（不弹出对话框）
    auto_start_recording: bool = False  # 是否自动开始记录（连接后自动开始JSONL记录）
    
    # 呼吸估计默认参数配置
    # 基础设置默认值（所有帧类型共用）
    breathing_default_threshold: float = 0.6  # 呼吸检测阈值
    breathing_default_update_interval: float = 2.0  # 呼吸估计更新间隔（秒）
    
    # 可视化设置默认值
    breathing_default_show_median: bool = False  # 默认显示中值滤波
    breathing_default_show_highpass: bool = False  # 默认不显示中值+高通滤波
    breathing_default_show_bandpass: bool = False  # 默认不显示中值+高通+带通滤波
    
    # 呼吸信道自适应默认参数
    breathing_adaptive_enabled: bool = False  # 是否启用最佳呼吸信道选取
    breathing_adaptive_top_n: int = 1  # 选择前N个最佳信道
    breathing_adaptive_highlight: str = "none"  # 高亮模式："none"（不高亮）、"current"（高亮当前使用的信道）、"best"（高亮最佳信道）、"both"（同时高亮）
    breathing_adaptive_auto_switch: bool = False  # 是否自动在最佳信道上执行呼吸检测
    breathing_adaptive_only_display_channels: bool = False  # 是否只在显示信道范围内选取
    breathing_adaptive_low_energy_threshold: float = 5.0  # 低能量持续时间阈值（秒）
    
    # 信道探测帧的默认参数
    breathing_cs_sampling_rate: float = 2.0  # Hz
    breathing_cs_median_filter_window: int = 3
    breathing_cs_highpass_cutoff: float = 0.05  # Hz
    breathing_cs_highpass_order: int = 2
    breathing_cs_bandpass_lowcut: float = 0.1  # Hz
    breathing_cs_bandpass_highcut: float = 0.35  # Hz
    breathing_cs_bandpass_order: int = 2
    breathing_cs_breath_freq_low: float = 0.1  # Hz
    breathing_cs_breath_freq_high: float = 0.35  # Hz
    breathing_cs_total_freq_low: float = 0.05  # Hz
    breathing_cs_total_freq_high: float = 0.8  # Hz
    
    # 方向估计帧的默认参数
    breathing_df_sampling_rate: float = 50.0  # Hz
    breathing_df_median_filter_window: int = 10
    breathing_df_highpass_cutoff: float = 0.05  # Hz
    breathing_df_highpass_order: int = 2
    breathing_df_bandpass_lowcut: float = 0.1  # Hz
    breathing_df_bandpass_highcut: float = 0.35  # Hz
    breathing_df_bandpass_order: int = 2
    breathing_df_breath_freq_low: float = 0.1  # Hz
    breathing_df_breath_freq_high: float = 0.35  # Hz
    breathing_df_total_freq_low: float = 0.05  # Hz
    breathing_df_total_freq_high: float = 0.8  # Hz
    
    # 命令发送默认参数
    command_default_cte_type: str = "aoa"  # 默认CTE类型
    command_default_channels: str = "3"  # 默认信道列表
    command_default_cte_len: str = "2"  # 默认CTE长度
    command_default_interval_ms: str = "10"  # 默认连接间隔（毫秒）
    
    def __post_init__(self):
        """初始化后处理"""
        if self.baudrate_options is None:
            self.baudrate_options = ["9600", "19200", "38400", "57600", "115200", "230400"]
        if self.frame_type_options is None:
            # 帧类型列表：信道探测帧对应原来的帧模式，其他选项可以后续添加（目前先留空）
            self.frame_type_options = ["信道探测帧","方向估计帧"]


class UserSettings:
    """用户设置管理类（保存到文件）"""
    
    def __init__(self, config_file: str = "user_settings.json"):
        """
        初始化用户设置
        
        Args:
            config_file: 配置文件路径（相对于程序运行目录）
        """
        self.config_file = config_file
        self.settings = {
            'save_directory': config.default_save_directory,
            'use_auto_save_path': config.use_auto_save_path,
            'auto_start_recording': config.auto_start_recording
        }
        self.load()
    
    def get_config_path(self) -> str:
        """获取配置文件完整路径"""
        # 获取程序运行目录
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后的程序
            base_path = os.path.dirname(sys.executable)
        else:
            # 开发环境，使用脚本所在目录
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, self.config_file)
    
    def load(self):
        """从文件加载用户设置"""
        config_path = self.get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 更新设置，保留默认值
                    self.settings.update(loaded)
            except Exception as e:
                print(f"加载用户设置失败: {e}，使用默认设置")
    
    def save(self):
        """保存用户设置到文件"""
        config_path = self.get_config_path()
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(config_path) if os.path.dirname(config_path) else '.', exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存用户设置失败: {e}")
    
    def get_save_directory(self) -> str:
        """获取保存目录"""
        return self.settings.get('save_directory', config.default_save_directory)
    
    def set_save_directory(self, directory: str):
        """设置保存目录"""
        self.settings['save_directory'] = directory
        self.save()
    
    def get_use_auto_save_path(self) -> bool:
        """获取是否使用自动保存路径"""
        return self.settings.get('use_auto_save_path', config.use_auto_save_path)
    
    def set_use_auto_save_path(self, use_auto: bool):
        """设置是否使用自动保存路径"""
        self.settings['use_auto_save_path'] = use_auto
        self.save()
    
    def get_auto_start_recording(self) -> bool:
        """获取是否自动开始记录"""
        return self.settings.get('auto_start_recording', config.auto_start_recording)
    
    def set_auto_start_recording(self, auto_start: bool):
        """设置是否自动开始记录"""
        self.settings['auto_start_recording'] = auto_start
        self.save()


# 全局配置实例
config = AppConfig()

# 全局用户设置实例
user_settings = UserSettings()

