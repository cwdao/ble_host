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
    version: str = "3.3.1"
    version_date: str = "2025-12-22"
    version_author: str = "chwn@outlook.ie, HKUST(GZ); Auto (Cursor AI Assistant)"
    
    # 窗口配置
    base_window_width: int = 1200
    base_window_height: int = 900
    
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
    default_display_channels: str = "0,4,8,12,16,20,24,28,32,36,40,44,48,52,56,60,64,68,72"
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
    
    # 数据保存配置
    default_save_directory: str = "./saveData"  # 默认保存目录
    use_auto_save_path: bool = True  # 是否使用自动保存路径（不弹出对话框）
    
    def __post_init__(self):
        """初始化后处理"""
        if self.baudrate_options is None:
            self.baudrate_options = ["9600", "19200", "38400", "57600", "115200", "230400"]
        if self.frame_type_options is None:
            # 帧类型列表：演示帧对应原来的帧模式，其他选项可以后续添加（目前先留空）
            self.frame_type_options = ["演示帧"]


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
            'use_auto_save_path': config.use_auto_save_path
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


# 全局配置实例
config = AppConfig()

# 全局用户设置实例
user_settings = UserSettings()

