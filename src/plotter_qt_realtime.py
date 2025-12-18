#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时波形绘制模块（使用 PyQtGraph）
专为高频数据更新设计，性能极佳
"""
import pyqtgraph as pg
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging


class RealtimePlotter:
    """实时波形绘制类（使用 PyQtGraph）"""
    
    def __init__(self, title: str = "BLE Channel Sounding", 
                 x_label: str = "Frame Index", 
                 y_label: str = "Amplitude"):
        """
        初始化实时绘图器
        
        Args:
            title: 图表标题
            x_label: X轴标签
            y_label: Y轴标签
        """
        self.logger = logging.getLogger(__name__)
        
        # 创建 PyQtGraph PlotWidget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setTitle(title)
        self.plot_widget.setLabel('left', y_label)
        self.plot_widget.setLabel('bottom', x_label)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()
        
        # 存储数据线：{var_name: PlotDataItem}
        self.data_lines = {}  # {var_name: PlotDataItem}
        self.max_points = 10000  # 每条曲线最大点数（PyQtGraph 可以处理更多）
        
        # 颜色列表（自动分配）
        self.colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
        ]
        self.color_index = 0
    
    def get_widget(self):
        """获取 Qt Widget（用于添加到布局）"""
        return self.plot_widget
    
    def add_line(self, var_name: str, color=None, label=None):
        """
        添加一条数据线（如果不存在）
        
        Args:
            var_name: 变量名
            color: 线条颜色，None则自动分配
            label: 图例标签，None则使用var_name
        """
        if var_name in self.data_lines:
            return  # 已经存在
        
        # 生成友好的标签名称
        if label is None:
            if var_name.startswith('ch') and var_name[2:].isdigit():
                label = f"Channel {var_name[2:]}"
            else:
                label = var_name
        
        # 分配颜色
        if color is None:
            color = self.colors[self.color_index % len(self.colors)]
            self.color_index += 1
        
        # 创建空的 PlotDataItem
        pen = pg.mkPen(color=color, width=1.5)
        curve = self.plot_widget.plot([], [], name=label, pen=pen)
        
        self.data_lines[var_name] = {
            'curve': curve,
            'x_data': [],
            'y_data': []
        }
    
    def update_line(self, var_name: str, x_data: np.ndarray, y_data: np.ndarray):
        """
        更新指定变量的数据线
        
        Args:
            var_name: 变量名
            x_data: x轴数据（通常是frame index）
            y_data: y轴数据（通常是amplitude）
        """
        if var_name not in self.data_lines:
            self.add_line(var_name)
        
        # 限制数据点数，避免内存占用过大
        if len(x_data) > self.max_points:
            # 均匀采样
            indices = np.linspace(0, len(x_data) - 1, self.max_points, dtype=int)
            x_data = x_data[indices]
            y_data = y_data[indices]
        
        line_info = self.data_lines[var_name]
        line_info['x_data'] = x_data.tolist()
        line_info['y_data'] = y_data.tolist()
        
        # 更新绘图数据（PyQtGraph 的 setData 非常快）
        line_info['curve'].setData(x_data, y_data)
    
    def update_frame_data(self, channel_data: Dict[int, Tuple[np.ndarray, np.ndarray]], 
                         max_channels: int = 10):
        """
        更新帧数据（一次更新多条线）
        
        Args:
            channel_data: {channel: (indices, amplitudes), ...}
            max_channels: 最多显示的通道数
        """
        # 获取要显示的通道列表
        sorted_channels = sorted(channel_data.keys())[:max_channels]
        channels_to_keep = set(sorted_channels)
        
        # 移除所有不在新列表中的通道线
        lines_to_remove = []
        for var_name in self.data_lines.keys():
            if var_name.startswith('ch') and var_name[2:].isdigit():
                try:
                    ch = int(var_name[2:])
                    if ch not in channels_to_keep:
                        lines_to_remove.append(var_name)
                except ValueError:
                    lines_to_remove.append(var_name)
            else:
                lines_to_remove.append(var_name)
        
        for var_name in lines_to_remove:
            self.remove_line(var_name)
        
        # 更新每条线
        for ch in sorted_channels:
            indices, amplitudes = channel_data[ch]
            var_name = f"ch{ch}"
            
            if len(indices) > 0 and len(amplitudes) > 0:
                self.update_line(var_name, indices, amplitudes)
    
    def clear_plot(self, var_name: str = None):
        """
        清空绘图数据
        
        Args:
            var_name: 变量名，None表示清空所有
        """
        if var_name:
            if var_name in self.data_lines:
                self.data_lines[var_name]['x_data'] = []
                self.data_lines[var_name]['y_data'] = []
                self.data_lines[var_name]['curve'].setData([], [])
        else:
            for line_info in self.data_lines.values():
                line_info['x_data'] = []
                line_info['y_data'] = []
                line_info['curve'].setData([], [])
    
    def remove_line(self, var_name: str):
        """移除一条数据线"""
        if var_name in self.data_lines:
            self.plot_widget.removeItem(self.data_lines[var_name]['curve'])
            del self.data_lines[var_name]
    
    def set_ylabel(self, label: str):
        """设置Y轴标签"""
        self.plot_widget.setLabel('left', label)
    
    def set_xlabel(self, label: str):
        """设置X轴标签"""
        self.plot_widget.setLabel('bottom', label)
    
    def set_title(self, title: str):
        """设置图表标题"""
        self.plot_widget.setTitle(title)
    
    # 向后兼容的方法
    def update_plot(self, var_name: str, times: np.ndarray, values: np.ndarray):
        """
        更新绘图（向后兼容方法）
        
        Args:
            var_name: 变量名
            times: 时间数组
            values: 数值数组
        """
        self.update_line(var_name, times, values)
    
    def add_variable(self, var_name: str, subplot_idx: int = None):
        """
        添加变量（向后兼容方法）
        """
        self.add_line(var_name)
