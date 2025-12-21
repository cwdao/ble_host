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
from PySide6.QtWidgets import QToolTip
from PySide6.QtCore import Qt


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
        # 默认背景色（浅色模式）
        self.plot_widget.setBackground('w')
        
        # 存储数据线：{var_name: PlotDataItem}
        self.data_lines = {}  # {var_name: PlotDataItem}
        self.max_points = 10000  # 每条曲线最大点数（PyQtGraph 可以处理更多）
        
        # 扩展的颜色列表（支持更多通道，使用更易区分的颜色）
        self.colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
            '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
            '#c49c94', '#f7b6d3', '#c7c7c7', '#dbdb8d', '#9edae5',
            '#393b79', '#5254a3', '#6b6ecf', '#9c9ede', '#637939',
            '#8ca252', '#b5cf6b', '#cedb9c', '#8c6d31', '#bd9e39',
            '#e7ba52', '#e7cb94', '#843c39', '#ad494a', '#d6616b',
            '#e7969c', '#7b4173', '#a55194', '#ce6dbd', '#de9ed6'
        ]
        self.color_index = 0
        
        # 鼠标悬停相关
        self.hovered_line = None  # 当前悬停的线条
        self.hover_pen_width = 3.5  # 悬停时的线条宽度
        self.normal_pen_width = 2.5  # 正常线条宽度（从1.5增加到2.5）
        self.hover_distance_threshold = 10  # 鼠标到线条的距离阈值（像素）
        
        # 工具提示文本项
        self.tooltip_text = None
        
        # 启用鼠标跟踪
        self.plot_widget.setMouseTracking(True)
        
        # 连接鼠标移动事件
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)
        
        # 视图状态跟踪
        self.current_view_range = None  # 当前应该显示的视图范围 (x_min, x_max)
        self.user_has_panned = False  # 用户是否手动拖动/缩放过视图
        self.auto_fit_enabled = True  # 是否自动适应视图
        
        # 连接视图变化信号，检测用户手动操作
        self.plot_widget.sigRangeChanged.connect(self._on_view_changed)
    
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
        
        # 创建空的 PlotDataItem，使用更粗的线条
        pen = pg.mkPen(color=color, width=self.normal_pen_width)
        curve = self.plot_widget.plot([], [], name=label, pen=pen)
        
        self.data_lines[var_name] = {
            'curve': curve,
            'x_data': [],
            'y_data': [],
            'label': label,
            'color': color
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
                         max_channels: int = 10, view_range: Optional[Tuple[float, float]] = None):
        """
        更新帧数据（一次更新多条线）
        
        Args:
            channel_data: {channel: (indices, amplitudes), ...}
            max_channels: 最多显示的通道数
            view_range: 可选的视图范围 (x_min, x_max)，用于自动定位视图
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
        
        # 更新视图范围（如果提供了且用户没有手动操作）
        if view_range is not None and not self.user_has_panned:
            self.current_view_range = view_range
            self._apply_view_range()
        elif view_range is not None:
            # 即使用户手动操作过，也更新当前视图范围（用于重置功能）
            self.current_view_range = view_range
    
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
            # 如果移除的是当前悬停的线条，清除悬停状态
            if self.hovered_line == var_name:
                self.hovered_line = None
                QToolTip.hideText()
    
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
    
    def _on_view_changed(self):
        """视图变化时的回调（检测用户手动操作）"""
        # 这个方法会在视图范围改变时被调用
        # 如果当前视图范围与设定的范围不一致，说明用户手动操作了
        if self.current_view_range is not None:
            current_range = self.plot_widget.viewRange()[0]  # (x_min, x_max)
            expected_range = self.current_view_range
            
            # 允许一定的误差（因为浮点数比较）
            tolerance = (expected_range[1] - expected_range[0]) * 0.01
            if (abs(current_range[0] - expected_range[0]) > tolerance or 
                abs(current_range[1] - expected_range[1]) > tolerance):
                self.user_has_panned = True
    
    def _apply_view_range(self):
        """应用视图范围"""
        if self.current_view_range is None:
            return
        
        x_min, x_max = self.current_view_range
        
        # 临时断开信号，避免触发 user_has_panned
        self.plot_widget.sigRangeChanged.disconnect(self._on_view_changed)
        
        # 设置X轴范围，Y轴自动适应
        self.plot_widget.setXRange(x_min, x_max, padding=0.05)
        
        # 重新连接信号
        self.plot_widget.sigRangeChanged.connect(self._on_view_changed)
    
    def reset_to_current_frame(self):
        """重置视图到当前帧窗口（包括X轴和Y轴）"""
        if self.current_view_range is not None:
            self.user_has_panned = False
            
            x_min, x_max = self.current_view_range
            
            # 临时断开信号，避免触发 user_has_panned
            self.plot_widget.sigRangeChanged.disconnect(self._on_view_changed)
            
            # 设置X轴范围
            self.plot_widget.setXRange(x_min, x_max, padding=0.05)
            
            # 计算当前X轴范围内的Y值范围，用于Y轴自适应
            y_min = None
            y_max = None
            
            for line_info in self.data_lines.values():
                if not line_info['x_data'] or not line_info['y_data']:
                    continue
                
                # 找到在当前X范围内的数据点
                x_data = np.array(line_info['x_data'])
                y_data = np.array(line_info['y_data'])
                
                # 筛选在X范围内的点
                mask = (x_data >= x_min) & (x_data <= x_max)
                if np.any(mask):
                    y_values = y_data[mask]
                    if len(y_values) > 0:
                        line_y_min = np.min(y_values)
                        line_y_max = np.max(y_values)
                        
                        if y_min is None or line_y_min < y_min:
                            y_min = line_y_min
                        if y_max is None or line_y_max > y_max:
                            y_max = line_y_max
            
            # 设置Y轴范围（如果有数据）
            if y_min is not None and y_max is not None:
                # 添加一些padding，让图形更美观
                y_padding = (y_max - y_min) * 0.1
                if y_padding == 0:
                    y_padding = abs(y_max) * 0.1 if y_max != 0 else 0.1
                self.plot_widget.setYRange(y_min - y_padding, y_max + y_padding, padding=0)
            else:
                # 如果没有数据，使用自动适应
                self.plot_widget.enableAutoRange(axis='y')
                self.plot_widget.autoRange()
            
            # 重新连接信号
            self.plot_widget.sigRangeChanged.connect(self._on_view_changed)
            
            return True
        return False
    
    def auto_fit_all(self):
        """自动适应所有数据"""
        # 收集所有数据的X范围
        all_x_data = []
        for line_info in self.data_lines.values():
            if line_info['x_data']:
                all_x_data.extend(line_info['x_data'])
        
        if not all_x_data:
            return
        
        x_min = min(all_x_data)
        x_max = max(all_x_data)
        
        if x_min < x_max:
            # 临时断开信号
            self.plot_widget.sigRangeChanged.disconnect(self._on_view_changed)
            
            # 设置范围
            self.plot_widget.setXRange(x_min, x_max, padding=0.05)
            
            # 重新连接信号
            self.plot_widget.sigRangeChanged.connect(self._on_view_changed)
            
            # 更新当前视图范围
            self.current_view_range = (x_min, x_max)
            self.user_has_panned = False
    
    def _on_mouse_moved(self, pos):
        """
        鼠标移动事件处理，用于检测鼠标是否悬停在线条上
        
        Args:
            pos: 鼠标在场景中的位置 (QPointF)
        """
        # 将场景坐标转换为视图坐标
        view_pos = self.plot_widget.plotItem.vb.mapSceneToView(pos)
        
        # 获取视图范围，用于归一化距离计算
        view_range = self.plot_widget.plotItem.vb.viewRange()
        x_range = view_range[0]
        y_range = view_range[1]
        x_span = x_range[1] - x_range[0] if x_range[1] > x_range[0] else 1.0
        y_span = y_range[1] - y_range[0] if y_range[1] > y_range[0] else 1.0
        
        # 找到距离鼠标最近的线条
        closest_line = None
        min_distance = float('inf')
        
        for var_name, line_info in self.data_lines.items():
            x_data = line_info['x_data']
            y_data = line_info['y_data']
            
            if not x_data or not y_data or len(x_data) == 0:
                continue
            
            # 计算鼠标到线条的距离
            x_array = np.array(x_data)
            y_array = np.array(y_data)
            
            # 找到最接近鼠标X坐标的数据点
            x_diff = np.abs(x_array - view_pos.x())
            if len(x_diff) == 0:
                continue
                
            closest_idx = np.argmin(x_diff)
            closest_x = x_array[closest_idx]
            closest_y = y_array[closest_idx]
            
            # 计算归一化的距离（考虑X和Y轴的范围）
            dx = (closest_x - view_pos.x()) / x_span
            dy = (closest_y - view_pos.y()) / y_span
            # 使用归一化距离，并考虑Y轴通常范围较小，给予更高权重
            normalized_distance = np.sqrt(dx**2 + (dy * 2)**2) * 100  # 乘以100转换为百分比距离
            
            # 将归一化距离转换为近似像素距离（假设视图高度约为400-800像素）
            # 使用一个启发式值：10%的归一化距离约等于10像素
            pixel_distance = normalized_distance * 0.1
            
            if pixel_distance < min_distance and pixel_distance < self.hover_distance_threshold:
                min_distance = pixel_distance
                closest_line = (var_name, line_info, closest_x, closest_y)
        
        # 更新悬停状态
        if closest_line is not None:
            var_name, line_info, x_val, y_val = closest_line
            if self.hovered_line != var_name:
                # 取消之前线条的高亮
                if self.hovered_line and self.hovered_line in self.data_lines:
                    old_pen = pg.mkPen(
                        color=self.data_lines[self.hovered_line]['color'],
                        width=self.normal_pen_width
                    )
                    self.data_lines[self.hovered_line]['curve'].setPen(old_pen)
                
                # 高亮当前线条
                hover_pen = pg.mkPen(
                    color=line_info['color'],
                    width=self.hover_pen_width
                )
                line_info['curve'].setPen(hover_pen)
                self.hovered_line = var_name
                
                # 显示工具提示
                tooltip_text = f"{line_info['label']}\nX: {x_val:.2f}, Y: {y_val:.4f}"
                # 将场景坐标转换为widget坐标，再转换为全局坐标
                widget_pos = self.plot_widget.plotItem.mapFromScene(pos)
                if hasattr(widget_pos, 'toPoint'):
                    widget_point = widget_pos.toPoint()
                else:
                    from PySide6.QtCore import QPoint
                    widget_point = QPoint(int(widget_pos.x()), int(widget_pos.y()))
                global_pos = self.plot_widget.mapToGlobal(widget_point)
                QToolTip.showText(global_pos, tooltip_text, self.plot_widget)
        else:
            # 鼠标不在任何线条附近
            if self.hovered_line and self.hovered_line in self.data_lines:
                # 恢复正常显示
                line_info = self.data_lines[self.hovered_line]
                normal_pen = pg.mkPen(
                    color=line_info['color'],
                    width=self.normal_pen_width
                )
                line_info['curve'].setPen(normal_pen)
                self.hovered_line = None
                QToolTip.hideText()
