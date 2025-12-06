#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DPI管理模块
处理Windows高DPI支持和缩放计算
"""
import platform
import logging
from typing import Tuple, Optional
from tkinter import font

from ..config import config


# 在模块级别设置DPI感知（必须在创建任何窗口之前）
def _setup_dpi_awareness_early():
    """在模块导入时设置Windows DPI感知（必须在创建窗口之前）"""
    if platform.system() == 'Windows':
        try:
            from ctypes import windll
            # 设置进程 DPI 感知为系统级别（Windows 8.1+）
            windll.shcore.SetProcessDpiAwareness(1)
        except (ImportError, AttributeError, OSError):
            # 如果失败，尝试旧版 API（Windows Vista+）
            try:
                windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass

# 在模块导入时立即执行
_setup_dpi_awareness_early()


class DPIManager:
    """DPI管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.scale_factor = 1.0
        self.font_size = config.base_font_size
        self._calculate_scale_factor()
        self._adjust_fonts()
    
    def _calculate_scale_factor(self):
        """计算DPI缩放比例"""
        if platform.system() == 'Windows':
            try:
                from ctypes import windll
                # 获取系统 DPI 缩放比例
                hdc = windll.user32.GetDC(0)
                dpi = windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX = 88
                windll.user32.ReleaseDC(0, hdc)
                self.scale_factor = dpi / 96.0  # 96 是标准 DPI
            except (ImportError, AttributeError, OSError):
                self.scale_factor = 1.0
        else:
            self.scale_factor = 1.0
    
    def _adjust_fonts(self):
        """调整字体大小"""
        # 总是设置字体大小，确保控件使用正确的字体
        if platform.system() == 'Windows' and self.scale_factor > 1.0:
            # 使用更温和的缩放策略
            font_size = int(config.base_font_size + (self.scale_factor - 1.0) * 2)
            # 限制最大字体大小
            font_size = min(font_size, config.max_font_size)
            font_size = max(font_size, config.min_font_size)
        else:
            # 标准DPI或非Windows系统，使用基础字体大小
            font_size = config.base_font_size
        
        self.font_size = font_size
        
        # 注意：字体调整需要在Tkinter初始化后才能执行
        # 这个方法会在创建root窗口后调用apply_fonts()来实际应用字体
    
    def apply_fonts(self):
        """
        应用字体设置（需要在Tkinter初始化后调用）
        这个方法应该在创建root窗口后立即调用
        """
        try:
            # 配置默认字体（总是执行，确保字体被设置）
            default_font = font.nametofont("TkDefaultFont")
            default_font.configure(size=self.font_size)
            
            text_font = font.nametofont("TkTextFont")
            text_font.configure(size=self.font_size)
            
            fixed_font = font.nametofont("TkFixedFont")
            fixed_font.configure(size=self.font_size)
        except Exception as e:
            self.logger.warning(f"调整字体失败: {e}")
            self.font_size = config.base_font_size
    
    def get_window_size(self) -> Tuple[int, int]:
        """
        获取根据DPI缩放后的窗口大小
        
        Returns:
            (width, height) 窗口尺寸（像素）
        """
        width = int(config.base_window_width * self.scale_factor)
        height = int(config.base_window_height * self.scale_factor)
        return width, height
    
    def get_plot_size(self) -> Tuple[float, float]:
        """
        获取根据DPI缩放后的Plot初始大小（英寸）
        
        Returns:
            (width, height) Plot尺寸（英寸）
        """
        # 使用更温和的缩放策略
        scale_adjustment = 1.0 + (self.scale_factor - 1.0) * config.plot_scale_adjustment_factor
        
        width = config.base_plot_width_inch * scale_adjustment
        height = config.base_plot_height_inch * scale_adjustment
        
        # 限制最大尺寸
        width = min(width, config.max_plot_width_inch)
        height = min(height, config.max_plot_height_inch)
        
        return width, height
    
    def get_plot_dpi(self) -> int:
        """
        获取Plot的DPI值
        
        Returns:
            DPI值（限制在合理范围内）
        """
        dpi = int(100 * self.scale_factor)
        return max(config.plot_dpi_min, min(dpi, config.plot_dpi_max))
    
    def get_version_font_size(self) -> int:
        """
        获取版本信息的字体大小
        
        Returns:
            字体大小
        """
        return max(config.min_font_size, int(self.font_size - config.version_font_offset))
    
    def get_system_dpi(self) -> Optional[int]:
        """
        获取系统DPI值
        
        Returns:
            DPI值，如果无法获取则返回None
        """
        if platform.system() == 'Windows':
            try:
                from ctypes import windll
                hdc = windll.user32.GetDC(0)
                dpi = windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX = 88
                windll.user32.ReleaseDC(0, hdc)
                return dpi
            except (ImportError, AttributeError, OSError):
                return None
        return None

