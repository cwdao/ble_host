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
from typing import Dict, List, Optional
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
        self.axes = {}  # {var_name: axis}
        self.data_lines = {}  # {var_name: line}
        self.max_points = 1000  # 每条曲线最大点数
        
    def attach_to_tkinter(self, parent):
        """将图形附加到Tkinter窗口"""
        self.canvas = FigureCanvasTkAgg(self.figure, parent)
        self.canvas.draw()
        return self.canvas.get_tk_widget()
    
    def add_variable(self, var_name: str, subplot_idx: int = None):
        """
        添加一个变量的绘图子图
        
        Args:
            var_name: 变量名
            subplot_idx: 子图索引，None则自动分配
        """
        if var_name in self.axes:
            return  # 已经存在
        
        if subplot_idx is None:
            # 自动计算子图位置
            num_plots = len(self.axes)
            rows = (num_plots + 1 + 1) // 2  # 向上取整
            cols = 2
            subplot_idx = num_plots + 1
        
        ax = self.figure.add_subplot(subplot_idx)
        ax.set_title(var_name)
        ax.set_xlabel('时间 (秒)')
        ax.set_ylabel('数值')
        ax.grid(True, alpha=0.3)
        
        line, = ax.plot([], [], label=var_name, linewidth=1.5)
        ax.legend()
        
        self.axes[var_name] = ax
        self.data_lines[var_name] = {'line': line, 'times': [], 'values': []}
    
    def remove_variable(self, var_name: str):
        """移除一个变量的绘图"""
        if var_name in self.axes:
            ax = self.axes[var_name]
            ax.remove()
            del self.axes[var_name]
            del self.data_lines[var_name]
            self.figure.canvas.draw_idle()
    
    def update_plot(self, var_name: str, times: np.ndarray, values: np.ndarray):
        """
        更新指定变量的波形
        
        Args:
            var_name: 变量名
            times: 时间数组
            values: 数值数组
        """
        if var_name not in self.data_lines:
            self.add_variable(var_name)
        
        # 限制数据点数，避免内存占用过大
        if len(times) > self.max_points:
            # 均匀采样
            indices = np.linspace(0, len(times) - 1, self.max_points, dtype=int)
            times = times[indices]
            values = values[indices]
        
        line_info = self.data_lines[var_name]
        line_info['times'] = times.tolist()
        line_info['values'] = values.tolist()
        
        # 更新绘图数据
        line_info['line'].set_data(times, values)
        
        # 自动调整坐标轴范围
        ax = self.axes[var_name]
        if len(times) > 0 and len(values) > 0:
            ax.set_xlim(min(times), max(times))
            y_min, y_max = min(values), max(values)
            y_range = y_max - y_min
            if y_range > 0:
                ax.set_ylim(y_min - y_range * 0.1, y_max + y_range * 0.1)
    
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
                self.data_lines[var_name]['times'] = []
                self.data_lines[var_name]['values'] = []
                self.data_lines[var_name]['line'].set_data([], [])
        else:
            for line_info in self.data_lines.values():
                line_info['times'] = []
                line_info['values'] = []
                line_info['line'].set_data([], [])

