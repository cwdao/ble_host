#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
波形绘制模块
"""
import matplotlib
matplotlib.use('TkAgg')  # 使用TkAgg后端，适合GUI应用
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging


class Plotter:
    """波形绘制类"""
    
    def __init__(self, figure_size=(10, 6)):
        """
        初始化绘图器
        
        Args:
            figure_size: 图形大小 (width, height)
        """
        self.logger = logging.getLogger(__name__)
        self.figure = Figure(figsize=figure_size, dpi=100)
        self.canvas = None
        # 使用单个axes显示所有数据
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title('通道幅值波形图')
        self.ax.set_xlabel('Frame Index')
        self.ax.set_ylabel('Amplitude')
        self.ax.grid(True, alpha=0.3)
        # 启用自动缩放
        self.ax.autoscale(enable=True, axis='both', tight=False)
        
        # 存储数据线：{var_name: line对象}
        self.data_lines = {}  # {var_name: line}
        self.max_points = 1000  # 每条曲线最大点数
        
    def attach_to_tkinter(self, parent):
        """将图形附加到Tkinter窗口"""
        self.canvas = FigureCanvasTkAgg(self.figure, parent)
        self.canvas.draw()
        return self.canvas.get_tk_widget()
    
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
            # 如果是通道格式 ch0, ch1, ...，显示为 Channel 0, Channel 1
            if var_name.startswith('ch') and var_name[2:].isdigit():
                label = f"Channel {var_name[2:]}"
            else:
                label = var_name
        
        # 如果没有指定颜色，使用默认颜色序列
        line, = self.ax.plot([], [], label=label, linewidth=1.5)
        
        self.data_lines[var_name] = {
            'line': line,
            'x_data': [],
            'y_data': []
        }
        
        # 更新图例
        self.ax.legend(loc='upper right', fontsize=8)
    
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
        
        # 更新绘图数据
        line_info['line'].set_data(x_data, y_data)
        
        # 更新坐标轴范围（针对单条线）
        if len(x_data) > 0 and len(y_data) > 0:
            # 获取所有线的数据范围
            self._auto_scale_axes()
    
    def update_frame_data(self, channel_data: Dict[int, Tuple[np.ndarray, np.ndarray]], 
                         max_channels: int = 10):
        """
        更新帧数据（一次更新多条线）
        
        Args:
            channel_data: {channel: (indices, amplitudes), ...}
            max_channels: 最多显示的通道数
        """
        # 移除所有非通道的线（只保留通道数据）
        lines_to_remove = []
        for var_name in self.data_lines.keys():
            if not (var_name.startswith('ch') and var_name[2:].isdigit()):
                lines_to_remove.append(var_name)
        for var_name in lines_to_remove:
            self.remove_line(var_name)
        
        # 只显示前max_channels个通道
        sorted_channels = sorted(channel_data.keys())[:max_channels]
        
        # 更新每条线
        all_x = []
        all_y = []
        
        for ch in sorted_channels:
            indices, amplitudes = channel_data[ch]
            var_name = f"ch{ch}"
            
            if len(indices) > 0 and len(amplitudes) > 0:
                self.update_line(var_name, indices, amplitudes)
                all_x.extend(indices)
                all_y.extend(amplitudes)
        
        # 更新坐标轴范围（自动缩放）
        self._auto_scale_axes()
    
    def refresh(self):
        """刷新画布"""
        if self.canvas:
            self.canvas.draw_idle()
    
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
                self.data_lines[var_name]['line'].set_data([], [])
        else:
            for line_info in self.data_lines.values():
                line_info['x_data'] = []
                line_info['y_data'] = []
                line_info['line'].set_data([], [])
            
            # 重置坐标轴
            self.ax.set_xlim(0, 1)
            self.ax.set_ylim(0, 1)
    
    def _auto_scale_axes(self):
        """
        自动缩放坐标轴，基于所有数据线的范围
        """
        if not self.data_lines:
            return
        
        all_x = []
        all_y = []
        
        # 收集所有线的数据范围
        for line_info in self.data_lines.values():
            x_data = line_info.get('x_data', [])
            y_data = line_info.get('y_data', [])
            
            if x_data and y_data:
                all_x.extend(x_data)
                all_y.extend(y_data)
        
        if all_x and all_y:
            all_x = np.array(all_x)
            all_y = np.array(all_y)
            
            if len(all_x) > 0 and len(all_y) > 0:
                x_min, x_max = np.min(all_x), np.max(all_x)
                y_min, y_max = np.min(all_y), np.max(all_y)
                
                x_range = x_max - x_min
                y_range = y_max - y_min
                
                # 设置x轴范围（留5%边距）
                if x_range > 0:
                    self.ax.set_xlim(x_min - x_range * 0.05, x_max + x_range * 0.05)
                elif x_min == x_max:
                    # 如果只有一个点，设置一个合理的范围
                    self.ax.set_xlim(x_min - 0.5, x_max + 0.5)
                else:
                    self.ax.set_xlim(x_min - 1, x_max + 1)
                
                # 设置y轴范围（留10%边距）
                if y_range > 0:
                    self.ax.set_ylim(y_min - y_range * 0.1, y_max + y_range * 0.1)
                elif y_min == y_max:
                    # 如果只有一个值，设置一个合理的范围
                    if abs(y_min) < 1e-6:
                        self.ax.set_ylim(-1, 1)
                    else:
                        self.ax.set_ylim(y_min * 0.9, y_max * 1.1)
                else:
                    self.ax.set_ylim(y_min - 1, y_max + 1)
    
    def remove_line(self, var_name: str):
        """移除一条数据线"""
        if var_name in self.data_lines:
            self.data_lines[var_name]['line'].remove()
            del self.data_lines[var_name]
            # 更新图例
            self.ax.legend(loc='upper right', fontsize=8)
            # 重新自动缩放（因为移除了数据）
            self._auto_scale_axes()
    
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
        添加变量（向后兼容方法，现在统一使用单图）
        """
        self.add_line(var_name)
