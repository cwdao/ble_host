#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BLE Host上位机主程序 - PySide6 版本
"""
import sys
import os
import threading
import time
import logging
import numpy as np
from typing import List, Optional, Dict
from datetime import datetime
import platform

# 在导入 Qt 之前设置 DPI 感知（Windows）
# 这必须在创建 QApplication 之前完成，以避免 Qt 的 DPI 感知警告
if platform.system() == 'Windows':
    try:
        from ctypes import windll
        # 尝试设置 DPI 感知上下文（Windows 10 1703+）
        # 使用 PER_MONITOR_AWARE_V2，这是 Qt 6 默认使用的
        try:
            # 首先尝试使用 SetProcessDpiAwarenessContext（Windows 10 1703+）
            # -4 = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            windll.user32.SetProcessDpiAwarenessContext(-4)
        except (AttributeError, OSError):
            # 如果失败，尝试使用 SetProcessDpiAwareness（Windows 8.1+）
            try:
                # 2 = PROCESS_PER_MONITOR_DPI_AWARE
                windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                # 最后尝试使用旧版 API（Windows Vista+）
                try:
                    windll.user32.SetProcessDPIAware()
                except (AttributeError, OSError):
                    pass  # 如果都失败，Qt 会使用默认设置
    except Exception:
        pass  # 忽略所有错误，让 Qt 使用默认设置

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit, QCheckBox,
    QRadioButton, QSlider, QTabWidget, QSplitter, QGroupBox, QMessageBox,
    QFileDialog, QButtonGroup, QFrame, QMenuBar, QMenu, QDialog, QDialogButtonBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QMetaObject
from PySide6.QtGui import QFont, QIcon, QAction, QActionGroup
from qfluentwidgets import SwitchButton, ProgressRing, ToolTipFilter, ToolTipPosition

# 业务逻辑模块（无需修改）
try:
    from .serial_reader import SerialReader
    from .data_parser import DataParser
    from .data_processor import DataProcessor
    from .data_saver import DataSaver
    from .config import config, user_settings
    from .breathing_estimator import BreathingEstimator
    from .plotter_qt_realtime import RealtimePlotter
    from .plotter_qt_matplotlib import MatplotlibPlotter
    from .gui.info_bar_helper import InfoBarHelper
except ImportError:
    # 直接运行时使用绝对导入
    from serial_reader import SerialReader
    from data_parser import DataParser
    from data_processor import DataProcessor
    from data_saver import DataSaver
    from config import config, user_settings
    from breathing_estimator import BreathingEstimator
    from plotter_qt_realtime import RealtimePlotter
    from plotter_qt_matplotlib import MatplotlibPlotter
    from gui.info_bar_helper import InfoBarHelper

# 版本信息
__version__ = config.version
__version_date__ = config.version_date
__version_author__ = config.version_author


class BLEHostGUI(QMainWindow):
    """主GUI应用程序 - PySide6 版本"""
    
    # 定义信号，用于从后台线程通知主线程更新UI
    save_status_update_signal = Signal(str, str)  # text, color_style
    save_success_signal = Signal(int, str)  # frame_count, filename
    save_error_signal = Signal(str)  # error_msg
    
    def __init__(self):
        super().__init__()
        
        # 连接信号到槽函数
        self.save_status_update_signal.connect(self._on_save_status_update)
        self.save_success_signal.connect(self._on_save_success)
        self.save_error_signal.connect(self._on_save_error)
        
        # 设置窗口标题
        self.setWindowTitle(f"BLE CS Host v{__version__}")
        
        # 设置窗口大小
        self.resize(config.base_window_width, config.base_window_height)
        
        # 设置日志
        self._setup_logging()
        
        # 初始化组件
        self.serial_reader = None
        self.data_parser = DataParser()
        self.data_processor = DataProcessor()
        self.data_saver = DataSaver()
        
        # 多个绘图器（用于不同选项卡）
        self.plotters = {}
        
        # 控制变量
        self.is_running = False
        self.update_thread = None
        self.stop_event = threading.Event()
        self.is_saving = False
        self.use_auto_save = user_settings.get_use_auto_save_path()
        
        # 绘图刷新节流控制
        self.last_plot_refresh_time = 0
        self.plot_refresh_interval = 0.2  # 最多每200ms刷新一次
        
        # 批量处理控制
        self.max_batch_size = 20  # 每次最多处理的数据条数
        self.last_queue_warning_time = 0
        self.queue_warning_interval = 5.0  # 队列警告间隔（秒）
        
        # 绘图更新优化：累积一定数量的帧后再更新
        self.pending_plot_update = False  # 是否有待更新的绘图
        self.frames_since_last_plot = 0  # 自上次绘图更新后处理的帧数
        self.min_frames_before_plot_update = 1  # 至少处理多少帧后才更新绘图（可调整）
        
        # 帧数据处理
        self.frame_type = config.default_frame_type
        self.frame_mode = (self.frame_type == "演示帧")
        # 使用默认配置解析显示信道列表（临时使用，稍后在_apply_frame_settings中会正确设置）
        self.display_channel_list = []
        self.display_max_frames = config.default_display_max_frames
        
        # 加载模式相关
        self.is_loaded_mode = False
        self.loaded_frames = []
        self.loaded_file_info = None
        self.current_window_start = 0
        self.breathing_estimator = BreathingEstimator()
        
        # 主题模式
        self.current_theme_mode = "light"  # auto, light, dark（默认浅色模式）
        
        # 实时呼吸估计相关
        self.breathing_update_interval = 2.0  # 默认2秒
        self.breathing_update_timer = None
        self.last_breathing_update_time = 0
        
        # 清除数据长按相关
        self.clear_data_hold_duration = 2.0  # 需要按住2秒
        self.clear_data_progress_timer = None
        self.clear_data_progress_value = 0
        self.is_holding_clear_btn = False
        
        # 创建界面
        self._create_widgets()
        
        # 应用默认设置（初始化显示信道）
        if self.frame_mode:
            # 先设置默认值
            self.display_channels_entry.setText(config.default_display_channels)
            self._apply_frame_settings(show_info=False)  # 初始化时不显示提示
        
        # 应用初始主题（跟随系统）- 初始化时不显示提示
        # 注意：这里不调用 _on_theme_mode_changed，因为界面还没创建完成
        # 主题会在 _create_settings_tab 中统一初始化
        
        # 定时刷新（使用 QTimer 替代 threading）
        self._start_update_loop()
        
        # 启动实时呼吸估计定时器
        self._start_realtime_breathing_estimation()
        
        # 监听系统主题变化（如果支持）
        try:
            from PySide6.QtGui import QGuiApplication
            app = QGuiApplication.instance()
            if app:
                # 监听系统主题变化
                app.paletteChanged.connect(self._on_system_theme_changed)
        except:
            pass
    
    def _setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def _create_widgets(self):
        """创建GUI组件"""
        # 创建菜单栏
        self._create_menu_bar()
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局（垂直）
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # 1. 连接状态栏（顶部）
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(5, 5, 5, 5)
        
        status_label = QLabel("连接状态:")
        status_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        self.status_label = QLabel("未连接")
        self.status_label.setStyleSheet("color: red;")
        self.status_label.setFont(QFont("Arial", 9))
        
        # 保存状态显示（在连接状态后面）
        self.save_status_label = QLabel("")
        self.save_status_label.setFont(QFont("Arial", 9))
        # 设置自动换行：当文本宽度超过可用空间时自动换行
        # setWordWrap(True) 会根据QLabel的可用宽度自动换行
        # 在QHBoxLayout中，可用宽度 = 布局总宽度 - 前面固定元素宽度 - 间距
        self.save_status_label.setWordWrap(True)  # 允许自动换行
        # 设置最大宽度，防止文本过长时占用过多空间
        self.save_status_label.setMaximumWidth(600)  # 最大宽度600px，超过会自动换行
        # 设置大小策略，允许在需要时缩小
        from PySide6.QtWidgets import QSizePolicy
        self.save_status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(QLabel(" | "))  # 分隔符
        status_layout.addWidget(self.save_status_label)
        status_layout.addStretch()
        
        main_layout.addWidget(status_frame)
        
        # 2. 配置选项卡区域
        self.config_tabs = QTabWidget()
        # 设置tab字体更大
        tab_font = QFont("Microsoft YaHei", 11)
        self.config_tabs.setFont(tab_font)
        self._create_connection_tab()
        self._create_channel_config_tab()
        self._create_data_and_save_tab()
        self._create_load_tab()
        self._create_settings_tab()
        
        main_layout.addWidget(self.config_tabs)
        
        # 3. 左右分栏（绘图区域 + 右侧面板）
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：绘图区域
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 绘图选项卡
        self.plot_tabs = QTabWidget()
        # 设置tab字体更大
        tab_font = QFont("Microsoft YaHei", 11)
        self.plot_tabs.setFont(tab_font)
        self._create_plot_tabs()
        left_layout.addWidget(self.plot_tabs)
        
        splitter.addWidget(left_widget)
        splitter.setStretchFactor(0, 2)  # 左侧占 2/3
        
        # 右侧：信息面板
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        # 呼吸估计控制区域（常驻显示）
        self.breathing_control_group = QGroupBox("Breathing Estimation Control")
        breathing_control_layout = QVBoxLayout(self.breathing_control_group)
        
        # 数据类型选择
        data_type_layout = QHBoxLayout()
        data_type_layout.addWidget(QLabel("Data Type:"))
        self.breathing_data_type_combo = QComboBox()
        self.breathing_data_type_combo.addItems(["amplitude", "local_amplitude", "remote_amplitude", "phase", "local_phase", "remote_phase"])
        data_type_layout.addWidget(self.breathing_data_type_combo)
        breathing_control_layout.addLayout(data_type_layout)
        
        # 信道选择
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Channel:"))
        self.breathing_channel_combo = QComboBox()
        channel_layout.addWidget(self.breathing_channel_combo)
        breathing_control_layout.addLayout(channel_layout)
        
        # 阈值输入
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Threshold:"))
        self.breathing_threshold_entry = QLineEdit("0.6")
        self.breathing_threshold_entry.setMaximumWidth(80)
        threshold_layout.addWidget(self.breathing_threshold_entry)
        breathing_control_layout.addLayout(threshold_layout)
        
        # 实时更新间隔（N秒）
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("更新间隔(秒):"))
        self.breathing_update_interval_entry = QLineEdit("2.0")
        self.breathing_update_interval_entry.setMaximumWidth(80)
        interval_layout.addWidget(self.breathing_update_interval_entry)
        breathing_control_layout.addLayout(interval_layout)
        
        # Update按钮（控制所有参数，放在更新间隔下面）
        update_layout = QHBoxLayout()
        self.update_all_btn = QPushButton("更新参数")
        self.update_all_btn.setStyleSheet("background-color: #2196F3; color: white;")
        self.update_all_btn.clicked.connect(self._on_update_all_breathing_params)
        update_layout.addWidget(self.update_all_btn)
        update_layout.addStretch()
        breathing_control_layout.addLayout(update_layout)
        
        # 呼吸估计结果显示
        result_label = QLabel("结果:")
        breathing_control_layout.addWidget(result_label)
        self.breathing_result_text = QTextEdit()
        self.breathing_result_text.setReadOnly(True)
        self.breathing_result_text.setFont(QFont("Consolas", 9))
        self.breathing_result_text.setMaximumHeight(120)
        self.breathing_result_text.setPlainText("等待数据积累...")
        breathing_control_layout.addWidget(self.breathing_result_text)
        
        right_layout.addWidget(self.breathing_control_group)
        
        # 数据处理区域（暂时隐藏）
        self.process_group = QGroupBox("数据处理")
        process_layout = QVBoxLayout(self.process_group)
        self._create_process_panel(process_layout)
        self.process_group.setVisible(False)  # 暂时隐藏
        right_layout.addWidget(self.process_group)
        
        # 日志区域
        self._create_log_panel(right_layout)
        
        # 版本信息
        self._create_version_info(right_layout)
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(1, 1)  # 右侧占 1/3
        
        main_layout.addWidget(splitter, stretch=1)
    
    def _create_menu_bar(self):
        """创建菜单栏（已移除，设置改为tab）"""
        # 菜单栏已移除，所有设置都在设置tab中
        pass
    
    def _on_theme_mode_changed(self, theme: str, show_info: bool = True):
        """主题模式改变时的回调"""
        # 如果主题没有实际改变，不执行任何操作
        if self.current_theme_mode == theme:
            # 即使主题相同，也强制应用一次，确保界面正确显示
            self._apply_theme(theme)
            return
        
        self.current_theme_mode = theme
        self._apply_theme(theme)
        
        # 只在用户主动切换时显示信息提示（初始化时不显示）
        if show_info:
            theme_names = {
                "auto": "跟随系统",
                "light": "浅色模式",
                "dark": "深色模式"
            }
            theme_name = theme_names.get(theme, theme)
            InfoBarHelper.information(
                self,
                title="主题已切换",
                content=f"当前主题: {theme_name}"
            )
    
    def _apply_theme(self, theme: str):
        """应用主题"""
        if theme == "auto":
            # 跟随系统主题
            self._apply_system_theme()
        elif theme == "light":
            # 强制浅色模式
            self._apply_light_theme()
        elif theme == "dark":
            # 强制深色模式
            self._apply_dark_theme()
    
    def _get_system_theme(self):
        """获取系统主题"""
        try:
            from PySide6.QtGui import QGuiApplication
            app = QGuiApplication.instance()
            if app:
                # 使用QStyleHints来检测系统主题（Qt 6.5+）
                style_hints = app.styleHints()
                if hasattr(style_hints, 'colorScheme'):
                    try:
                        color_scheme = style_hints.colorScheme()
                        if color_scheme == Qt.ColorScheme.Dark:
                            return "dark"
                        elif color_scheme == Qt.ColorScheme.Light:
                            return "light"
                    except:
                        pass
                # 备用方法：检查palette
                palette = app.palette()
                bg_color = palette.color(palette.ColorRole.Window)
                # 如果背景色较暗，则是深色模式
                lightness = bg_color.lightness()
                return "dark" if lightness < 128 else "light"
        except Exception as e:
            self.logger.warning(f"获取系统主题失败: {e}")
        return "light"  # 默认浅色
    
    def _apply_system_theme(self):
        """应用系统主题"""
        # 使用Qt的热切换主题API，设置为Unknown表示跟随系统
        try:
            app = QApplication.instance()
            if app:
                style_hints = app.styleHints()
                if hasattr(style_hints, 'setColorScheme'):
                    style_hints.setColorScheme(Qt.ColorScheme.Unknown)  # Unknown表示跟随系统
                    # 强制刷新整个应用程序
                    app.processEvents()
                    self.repaint()  # 重绘窗口
                    self.update()   # 更新窗口
        except Exception as e:
            self.logger.warning(f"设置系统主题失败: {e}")
        
        # 根据系统主题设置PyQtGraph背景
        system_theme = self._get_system_theme()
        if system_theme == "dark":
            # 只设置PyQtGraph背景，不改变系统主题
            self._apply_dark_theme_plot_only()
        else:
            # 只设置PyQtGraph背景，不改变系统主题
            self._apply_light_theme_plot_only()
    
    def _apply_light_theme(self):
        """应用浅色主题"""
        # 使用Qt的热切换主题API（Windows 11有效）
        try:
            app = QApplication.instance()
            if app:
                style_hints = app.styleHints()
                if hasattr(style_hints, 'setColorScheme'):
                    style_hints.setColorScheme(Qt.ColorScheme.Light)
                    # 强制刷新整个应用程序
                    app.processEvents()
                    self.repaint()  # 重绘窗口
                    self.update()   # 更新窗口
        except Exception as e:
            self.logger.warning(f"设置浅色主题失败: {e}")
        
        # 只设置PyQtGraph背景为白色（浅色模式）
        try:
            import pyqtgraph as pg
        except ImportError:
            pg = None
        
        if pg:
            for plotter_info in self.plotters.values():
                plotter = plotter_info.get('plotter')
                if plotter is not None:
                    # PyQtGraph背景设置为白色
                    plotter.plot_widget.setBackground('w')
                    # 设置网格和坐标轴颜色为深色（在浅色背景下）
                    plotter.plot_widget.getAxis('left').setPen(pg.mkPen(color='k'))
                    plotter.plot_widget.getAxis('bottom').setPen(pg.mkPen(color='k'))
                    # 设置文本颜色为深色
                    plotter.plot_widget.getAxis('left').setTextPen(pg.mkPen(color='k'))
                    plotter.plot_widget.getAxis('bottom').setTextPen(pg.mkPen(color='k'))
    
    def _apply_light_theme_plot_only(self):
        """只设置PyQtGraph背景为浅色（不改变系统主题）"""
        try:
            import pyqtgraph as pg
        except ImportError:
            pg = None
        
        if pg:
            for plotter_info in self.plotters.values():
                plotter = plotter_info.get('plotter')
                if plotter is not None:
                    plotter.plot_widget.setBackground('w')
                    plotter.plot_widget.getAxis('left').setPen(pg.mkPen(color='k'))
                    plotter.plot_widget.getAxis('bottom').setPen(pg.mkPen(color='k'))
                    plotter.plot_widget.getAxis('left').setTextPen(pg.mkPen(color='k'))
                    plotter.plot_widget.getAxis('bottom').setTextPen(pg.mkPen(color='k'))
    
    def _apply_dark_theme(self):
        """应用深色主题"""
        # 使用Qt的热切换主题API（Windows 11有效）
        try:
            app = QApplication.instance()
            if app:
                style_hints = app.styleHints()
                if hasattr(style_hints, 'setColorScheme'):
                    style_hints.setColorScheme(Qt.ColorScheme.Dark)
                    # 强制刷新整个应用程序
                    app.processEvents()
                    self.repaint()  # 重绘窗口
                    self.update()   # 更新窗口
        except Exception as e:
            self.logger.warning(f"设置深色主题失败: {e}")
        
        # 只设置PyQtGraph背景为深色
        try:
            import pyqtgraph as pg
        except ImportError:
            pg = None
        
        if pg:
            for plotter_info in self.plotters.values():
                plotter = plotter_info.get('plotter')
                if plotter is not None:
                    # PyQtGraph背景设置为深色
                    plotter.plot_widget.setBackground('#1e1e1e')
                    # 设置网格和坐标轴颜色为浅色（在深色背景下）
                    plotter.plot_widget.getAxis('left').setPen(pg.mkPen(color='w'))
                    plotter.plot_widget.getAxis('bottom').setPen(pg.mkPen(color='w'))
                    # 设置文本颜色为浅色
                    plotter.plot_widget.getAxis('left').setTextPen(pg.mkPen(color='w'))
                    plotter.plot_widget.getAxis('bottom').setTextPen(pg.mkPen(color='w'))
    
    def _apply_dark_theme_plot_only(self):
        """只设置PyQtGraph背景为深色（不改变系统主题）"""
        try:
            import pyqtgraph as pg
        except ImportError:
            pg = None
        
        if pg:
            for plotter_info in self.plotters.values():
                plotter = plotter_info.get('plotter')
                if plotter is not None:
                    plotter.plot_widget.setBackground('#1e1e1e')
                    plotter.plot_widget.getAxis('left').setPen(pg.mkPen(color='w'))
                    plotter.plot_widget.getAxis('bottom').setPen(pg.mkPen(color='w'))
                    plotter.plot_widget.getAxis('left').setTextPen(pg.mkPen(color='w'))
                    plotter.plot_widget.getAxis('bottom').setTextPen(pg.mkPen(color='w'))
    
    def _set_theme(self, theme: str):
        """设置主题（菜单栏用，已废弃，使用_on_theme_mode_changed）"""
        self._on_theme_mode_changed(theme)
    
    def _on_system_theme_changed(self):
        """系统主题变化时的回调"""
        if self.current_theme_mode == "auto":
            self._apply_system_theme()
    
    def _show_about(self):
        """显示关于对话框"""
        about_text = f"""
        <h2>BLE CS Host</h2>
        <p><b>版本:</b> {__version__}</p>
        <p><b>编译日期:</b> {__version_date__}</p>
        <p><b>作者:</b> {__version_author__}</p>
        <p>BLE Channel Sounding 上位机应用程序</p>
        <p>基于 PySide6 开发</p>
        """
        QMessageBox.about(self, "关于", about_text)
    
    def _create_connection_tab(self):
        """创建连接配置选项卡"""
        tab = QWidget()
        tab.setMinimumHeight(80)  # 设置最小高度，保持等高
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 串口选择
        layout.addWidget(QLabel("串口:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(150)
        layout.addWidget(self.port_combo)
        
        refresh_btn = QPushButton("刷新串口")
        refresh_btn.clicked.connect(self._refresh_ports)
        layout.addWidget(refresh_btn)
        
        # 波特率选择
        layout.addWidget(QLabel("波特率:"))
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(config.baudrate_options)
        self.baudrate_combo.setCurrentText(config.default_baudrate)
        layout.addWidget(self.baudrate_combo)
        
        # 连接按钮
        self.connect_btn = QPushButton("连接")
        self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.connect_btn.clicked.connect(self._toggle_connection)
        layout.addWidget(self.connect_btn)
        
        # 帧类型选择
        layout.addWidget(QLabel("帧类型:"))
        self.frame_type_combo = QComboBox()
        self.frame_type_combo.addItems(config.frame_type_options)
        self.frame_type_combo.setCurrentText(config.default_frame_type)
        self.frame_type_combo.currentTextChanged.connect(self._on_frame_type_changed)
        layout.addWidget(self.frame_type_combo)
        
        layout.addStretch()
        
        self.config_tabs.addTab(tab, "连接")
        
        # 初始化串口列表
        self._refresh_ports()
    
    def _create_channel_config_tab(self):
        """创建通道配置选项卡"""
        tab = QWidget()
        tab.setMinimumHeight(80)  # 设置最小高度，保持等高
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 第一行：信道选择模式
        layout.addWidget(QLabel("选择模式:"))
        self.channel_mode_combo = QComboBox()
        self.channel_mode_combo.addItems(["间隔X信道", "信道范围", "手动输入"])
        self.channel_mode_combo.setCurrentText("手动输入")
        self.channel_mode_combo.currentTextChanged.connect(self._on_channel_mode_changed)
        layout.addWidget(self.channel_mode_combo)
        
        # 输入框容器（根据模式显示不同的输入框）
        self.channel_input_widget = QWidget()
        self.channel_input_layout = QHBoxLayout(self.channel_input_widget)
        self.channel_input_layout.setContentsMargins(0, 0, 0, 0)
        
        # 间隔信道输入框
        self.interval_entry = QLineEdit("4")
        self.interval_entry.setMinimumWidth(100)
        self.interval_label = QLabel("(间隔数，如4表示0,4,8,12...)")
        self.interval_label.setStyleSheet("color: gray;")
        
        # 信道范围输入框
        self.range_entry = QLineEdit("0-9")
        self.range_entry.setMinimumWidth(150)
        self.range_label = QLabel("(如: 0-9 或 0-9,20-30)")
        self.range_label.setStyleSheet("color: gray;")
        
        # 手动输入框
        self.display_channels_entry = QLineEdit(config.default_display_channels)
        self.display_channels_entry.setMinimumWidth(200)
        self.manual_label = QLabel("(如: 0-9 或 0,2,4,6,8)")
        self.manual_label.setStyleSheet("color: gray;")
        
        # 初始显示手动输入模式
        self._show_channel_input_mode("手动输入")
        
        layout.addWidget(self.channel_input_widget)
        
        # 显示帧数
        layout.addWidget(QLabel("显示帧数:"))
        self.display_max_frames_entry = QLineEdit(str(config.default_display_max_frames))
        self.display_max_frames_entry.setMinimumWidth(80)
        layout.addWidget(self.display_max_frames_entry)
        layout.addWidget(QLabel("(plot和计算范围)"))
        
        # 应用按钮
        self.apply_settings_btn = QPushButton("应用")
        # 使用 lambda 确保传递 show_info=True（用户主动点击时显示提示）
        self.apply_settings_btn.clicked.connect(lambda: self._apply_frame_settings(show_info=True))
        layout.addWidget(self.apply_settings_btn)
        
        layout.addStretch()
        
        self.config_tabs.addTab(tab, "通道配置")
    
    def _create_data_and_save_tab(self):
        """创建数据和保存选项卡"""
        tab = QWidget()
        tab.setMinimumHeight(80)  # 设置最小高度，保持等高
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 第一行：三个组排三列，靠左
        top_row = QHBoxLayout()
        
        # 第一组：设置保存路径+自动保存开关+显示当前路径
        path_group = QGroupBox("路径设置")
        path_group.setStyleSheet("QGroupBox { font-size: 9pt; }")
        path_group.setMaximumWidth(300)
        path_layout = QVBoxLayout(path_group)
        
        set_path_btn = QPushButton("设置保存路径...")
        set_path_btn.clicked.connect(self._set_save_path)
        path_layout.addWidget(set_path_btn)
        
        # 使用 SwitchButton 替代 CheckBox
        auto_save_layout = QHBoxLayout()
        auto_save_layout.addWidget(QLabel("使用自动保存路径:"))
        self.auto_save_switch = SwitchButton(self)
        self.auto_save_switch.setChecked(self.use_auto_save)
        self.auto_save_switch.checkedChanged.connect(self._toggle_auto_save)
        auto_save_layout.addWidget(self.auto_save_switch)
        auto_save_layout.addStretch()
        path_layout.addLayout(auto_save_layout)
        
        # 显示当前保存路径
        current_path = user_settings.get_save_directory()
        display_path = current_path if len(current_path) <= 50 else "..." + current_path[-47:]
        self.path_label = QLabel(f"当前路径: {display_path}")
        self.path_label.setStyleSheet("color: gray;")
        path_layout.addWidget(self.path_label)
        
        path_layout.addStretch()
        top_row.addWidget(path_group)
        
        # 第二组：保存数据+全部保存/最近N帧
        save_group = QGroupBox("保存数据")
        save_group.setStyleSheet("QGroupBox { font-size: 9pt; }")
        save_layout = QVBoxLayout(save_group)
        
        self.save_btn = QPushButton("保存数据")
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.save_btn.clicked.connect(self._save_data)
        save_layout.addWidget(self.save_btn)
        
        # 保存选项（全部保存或最近N帧）
        self.save_option_group = QButtonGroup()
        self.save_all_radio = QRadioButton("全部保存")
        self.save_all_radio.setChecked(True)
        self.save_recent_radio = QRadioButton("最近N帧")
        self.save_option_group.addButton(self.save_all_radio, 0)
        self.save_option_group.addButton(self.save_recent_radio, 1)
        save_layout.addWidget(self.save_all_radio)
        save_layout.addWidget(self.save_recent_radio)
        
        save_layout.addStretch()
        top_row.addWidget(save_group)
        
        # 第三组：清空当前数据单独一个组
        clear_group = QGroupBox("清空数据")
        clear_group.setStyleSheet("QGroupBox { font-size: 9pt; }")
        clear_group.setMaximumWidth(200)
        clear_layout = QVBoxLayout(clear_group)
        
        # 清除数据按钮和进度环容器
        clear_data_container = QHBoxLayout()
        clear_data_container.setSpacing(5)
        clear_data_container.setContentsMargins(0, 0, 0, 0)  # 确保没有额外的边距
        
        # 创建一个自定义按钮类来处理长按事件
        class LongPressButton(QPushButton):
            def __init__(self, text, parent, press_callback, release_callback):
                super().__init__(text, parent)
                self.press_callback = press_callback
                self.release_callback = release_callback
            
            def mousePressEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton and self.press_callback:
                    self.press_callback(event)
                super().mousePressEvent(event)  # 调用父类方法保持默认行为
            
            def mouseReleaseEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton and self.release_callback:
                    self.release_callback(event)
                super().mouseReleaseEvent(event)  # 调用父类方法保持默认行为
        
        self.clear_data_btn = LongPressButton(
            "清空当前数据", 
            self,
            self._on_clear_data_btn_pressed,
            self._on_clear_data_btn_released
        )
        self.clear_data_btn.setStyleSheet("background-color: #f44336; color: white;")
        # 设置按钮大小策略，避免被拉伸
        from PySide6.QtWidgets import QSizePolicy
        self.clear_data_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # 使用 qfluentwidgets 的 ToolTip
        self.clear_data_btn.setToolTip("长按删除")
        self.clear_data_btn.installEventFilter(ToolTipFilter(self.clear_data_btn, 0, ToolTipPosition.TOP))
        clear_data_container.addWidget(self.clear_data_btn)
        
        # 进度环（始终占用空间，初始透明/不可见，避免布局变化）
        self.clear_data_progress_ring = ProgressRing(self)
        self.clear_data_progress_ring.setFixedSize(32, 32)  # 小尺寸，显示在按钮旁边
        self.clear_data_progress_ring.setTextVisible(False)  # 不显示文字
        self.clear_data_progress_ring.setValue(0)
        # 使用setStyleSheet让进度环初始透明，但保持占用空间
        self.clear_data_progress_ring.setStyleSheet("opacity: 0;")
        clear_data_container.addWidget(self.clear_data_progress_ring)
        
        clear_layout.addLayout(clear_data_container)
        clear_layout.addStretch()
        top_row.addWidget(clear_group)
        
        # 保存状态已移到顶部状态栏，这里不再显示
        
        top_row.addStretch()  # 让四个组靠左
        layout.addLayout(top_row)
        
        layout.addStretch()
        
        self.config_tabs.addTab(tab, "数据保存")
    
    def _create_load_tab(self):
        """创建加载选项卡"""
        tab = QWidget()
        layout = QHBoxLayout(tab)  # 改为三列横向布局
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 设置按钮字体
        btn_font = QFont("Microsoft YaHei", 10)
        
        # 第一列：文件读取（文件路径部分）
        path_group = QGroupBox("文件读取")
        # 设置组标题字体较小，但不影响内部控件
        path_group.setStyleSheet("QGroupBox { font-size: 9pt; }")
        path_layout = QVBoxLayout(path_group)
        path_group.setMaximumWidth(200)  # 保持左右宽度限制
        path_group.setMaximumHeight(100)
        
        path_input_layout = QHBoxLayout()
        self.load_file_entry = QLineEdit()
        path_input_layout.addWidget(self.load_file_entry)
        path_layout.addLayout(path_input_layout)
        
        button_layout = QHBoxLayout()
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setFont(btn_font)
        self.browse_btn.clicked.connect(self._browse_load_file)
        button_layout.addWidget(self.browse_btn)
        
        # 合并加载/取消加载按钮为一个按钮
        self.load_unload_btn = QPushButton("加载文件")
        self.load_unload_btn.setFont(btn_font)
        self.load_unload_btn.setStyleSheet("background-color: #2196F3; color: white;")  # 浅蓝色
        self.load_unload_btn.clicked.connect(self._toggle_load_file)
        button_layout.addWidget(self.load_unload_btn)
        path_layout.addLayout(button_layout)
        
        path_layout.addStretch()
        layout.addWidget(path_group)
        
        # 第二列：时间窗控制
        control_group = QGroupBox("时间窗控制")
        # 设置组标题字体较小，但不影响内部控件
        control_group.setStyleSheet("QGroupBox { font-size: 9pt; }")
        control_layout = QVBoxLayout(control_group)
        control_group.setMaximumHeight(100)
        
        # 创建滑动条容器
        slider_layout = QHBoxLayout()
        slider_layout.setContentsMargins(5, 5, 5, 5)
        
        slider_layout.addWidget(QLabel("时间窗起点:"))
        self.window_start_entry = QLineEdit("0")
        self.window_start_entry.setMaximumWidth(80)
        self.window_start_entry.setFont(btn_font)
        self.window_start_entry.returnPressed.connect(self._on_window_start_changed)
        self.window_start_entry.setEnabled(False)  # 初始禁用
        slider_layout.addWidget(self.window_start_entry)
        slider_layout.addWidget(QLabel("(帧)"))
        
        # 左箭头按钮
        self.slider_left_btn = QPushButton("◄")
        self.slider_left_btn.setMaximumWidth(40)
        self.slider_left_btn.setFont(btn_font)
        self.slider_left_btn.clicked.connect(self._on_slider_left_click)
        self.slider_left_btn.setEnabled(False)  # 初始禁用
        slider_layout.addWidget(self.slider_left_btn)
        
        # 滑动条（支持鼠标和键盘方向键控制）
        # 创建自定义滑动条类，支持键盘方向键控制
        class KeyboardSlider(QSlider):
            def __init__(self, orientation, parent=None, update_callback=None):
                super().__init__(orientation, parent)
                self.update_callback = update_callback
            
            def keyPressEvent(self, event):
                # 处理方向键
                if event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_Down:
                    # 左/下键：减少值
                    new_value = max(self.minimum(), self.value() - 1)
                    self.setValue(new_value)
                    if self.update_callback:
                        self.update_callback()
                    event.accept()
                elif event.key() == Qt.Key.Key_Right or event.key() == Qt.Key.Key_Up:
                    # 右/上键：增加值
                    new_value = min(self.maximum(), self.value() + 1)
                    self.setValue(new_value)
                    if self.update_callback:
                        self.update_callback()
                    event.accept()
                else:
                    # 其他键使用默认处理
                    super().keyPressEvent(event)
        
        self.time_window_slider = KeyboardSlider(Qt.Orientation.Horizontal, update_callback=self._on_slider_keyboard_changed)
        self.time_window_slider.setMinimum(0)
        self.time_window_slider.setMaximum(100)
        # 允许键盘焦点，以便响应方向键
        self.time_window_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # 连接sliderReleased，鼠标释放时更新
        self.time_window_slider.sliderReleased.connect(self._on_slider_released)
        # 鼠标点击时也更新
        self.time_window_slider.sliderPressed.connect(self._on_slider_pressed)
        self.time_window_slider.setEnabled(False)  # 初始禁用
        slider_layout.addWidget(self.time_window_slider)
        
        # 右箭头按钮
        self.slider_right_btn = QPushButton("►")
        self.slider_right_btn.setMaximumWidth(40)
        self.slider_right_btn.setFont(btn_font)
        self.slider_right_btn.clicked.connect(self._on_slider_right_click)
        self.slider_right_btn.setEnabled(False)  # 初始禁用
        slider_layout.addWidget(self.slider_right_btn)
        
        # 时间窗长度显示
        self.window_length_label = QLabel("时间窗长度: -- 秒")
        self.window_length_label.setFont(btn_font)
        slider_layout.addWidget(self.window_length_label)
        
        # 回到当前帧按钮
        self.reset_view_btn = QPushButton("回到当前帧")
        self.reset_view_btn.setMaximumWidth(100)
        self.reset_view_btn.setFont(btn_font)
        self.reset_view_btn.setToolTip("重置视图到当前时间窗范围（在手动拖动/缩放后使用）")
        self.reset_view_btn.installEventFilter(ToolTipFilter(self.reset_view_btn, 0, ToolTipPosition.TOP))
        self.reset_view_btn.clicked.connect(self._on_reset_view_clicked)
        self.reset_view_btn.setEnabled(False)  # 初始禁用
        # 保存按钮的默认样式（用于恢复）
        self.reset_view_btn_default_style = self.reset_view_btn.styleSheet()
        slider_layout.addWidget(self.reset_view_btn)
        
        control_layout.addLayout(slider_layout)
        control_layout.addStretch()
        layout.addWidget(control_group)
        
        # 第三列：文件信息
        info_group = QGroupBox("文件信息")
        # 设置组标题字体较小，但不影响内部控件
        info_group.setStyleSheet("QGroupBox { font-size: 9pt; }")
        info_layout = QVBoxLayout(info_group)
        info_group.setMaximumWidth(150)  # 保持左右宽度限制不变
        info_group.setMaximumHeight(100)
        self.load_file_info_text = QTextEdit()
        self.load_file_info_text.setReadOnly(True)
        self.load_file_info_text.setFont(QFont("Consolas", 8))
        info_layout.addWidget(self.load_file_info_text)
        
        layout.addWidget(info_group)
        
        self.config_tabs.addTab(tab, "文件加载")
    
    def _create_settings_tab(self):
        """创建设置选项卡"""
        tab = QWidget()
        tab.setMinimumHeight(80)  # 设置最小高度，保持等高
        layout = QHBoxLayout(tab)  # 两列横向布局，靠左排列
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 左列：主题设置
        theme_group = QGroupBox("主题设置")
        theme_group.setStyleSheet("QGroupBox { font-size: 9pt; }")
        theme_layout = QVBoxLayout(theme_group)
        theme_group.setMaximumHeight(100)
        theme_group.setMaximumWidth(200)
        # 主题模式选择
        self.theme_mode_group = QButtonGroup(self)
        self.theme_auto_radio = QRadioButton("跟随系统")
        # 使用 lambda 来只在选中时触发，避免取消选中时触发
        self.theme_auto_radio.toggled.connect(lambda checked: self._on_theme_mode_changed("auto") if checked else None)
        self.theme_mode_group.addButton(self.theme_auto_radio, 0)
        theme_layout.addWidget(self.theme_auto_radio)
        
        self.theme_light_radio = QRadioButton("浅色模式")
        self.theme_light_radio.setChecked(True)  # 默认浅色模式
        self.theme_light_radio.toggled.connect(lambda checked: self._on_theme_mode_changed("light") if checked else None)
        self.theme_mode_group.addButton(self.theme_light_radio, 1)
        theme_layout.addWidget(self.theme_light_radio)
        
        self.theme_dark_radio = QRadioButton("深色模式")
        self.theme_dark_radio.toggled.connect(lambda checked: self._on_theme_mode_changed("dark") if checked else None)
        self.theme_mode_group.addButton(self.theme_dark_radio, 2)
        theme_layout.addWidget(self.theme_dark_radio)
        
        layout.addWidget(theme_group)
        
        # 右列：关于信息
        about_group = QGroupBox("关于")
        about_group.setStyleSheet("QGroupBox { font-size: 9pt; }")
        about_layout = QVBoxLayout(about_group)
        about_text = QTextEdit()
        about_text.setReadOnly(True)
        # QTextEdit使用setHtml()来设置富文本，不需要setTextFormat()
        about_text.setHtml(f"""
        <h3>BLE CS Host</h3>
        <p><b>版本:</b> {__version__}</p>
        <p><b>编译日期:</b> {__version_date__}</p>
        <p><b>作者:</b> {__version_author__}</p>
        <p>BLE Channel Sounding 上位机应用程序</p>
        <p>基于 PySide6 开发</p>
        """)
        about_group.setMaximumHeight(100)  # 限制高度，内容可滚动
        about_group.setMaximumWidth(500)
        about_layout.addWidget(about_text)
        layout.addWidget(about_group)
        
        layout.addStretch()  # 添加stretch让内容靠左
        
        self.config_tabs.addTab(tab, "设置")
        
        # 初始化主题（浅色模式）- 不显示提示
        # 注意：这里设置主题，但实际应用会在窗口显示时（showEvent）再次确认
        self._on_theme_mode_changed("light", show_info=False)
        # 强制应用一次主题，确保界面正确显示
        self._apply_theme("light")
    
    def _create_plot_tabs(self):
        """创建绘图选项卡"""
        # 定义选项卡配置
        tab_configs = [
            ('amplitude', '幅值', 'Amplitude', 'amplitude'),
            ('phase', '相位', 'Phase (rad)', 'phase'),
            ('local_amplitude', 'Local观测Ref幅值', 'Local Amplitude', 'local_amplitude'),
            ('local_phase', 'Local观测Ref相位', 'Local Phase (rad)', 'local_phase'),
            ('remote_amplitude', 'Remote观测Ini幅值', 'Remote Amplitude', 'remote_amplitude'),
            ('remote_phase', 'Remote观测Ini相位', 'Remote Phase (rad)', 'remote_phase'),
        ]
        
        for tab_key, tab_name, y_label, data_type in tab_configs:
            # 创建实时绘图器（使用 PyQtGraph）
            plotter = RealtimePlotter(
                title=f'BLE Channel Sounding - {tab_name}',
                x_label='Frame Index',
                y_label=y_label
            )
            
            # 连接到视图变化信号，当检测到用户手动操作时立即更新按钮颜色
            # 注意：plotter 内部的 _on_view_changed 会先执行并设置 user_has_panned
            # 然后这个回调会延迟检查并更新按钮颜色
            plotter.plot_widget.sigRangeChanged.connect(self._on_plot_view_changed)
            
            # 添加到选项卡
            self.plot_tabs.addTab(plotter.get_widget(), tab_name)
            
            # 保存引用
            self.plotters[tab_key] = {
                'plotter': plotter,
                'data_type': data_type
            }
        
        # 创建呼吸估计选项卡（使用 Matplotlib）
        self._create_breathing_estimation_tab()
    
    def _create_process_panel(self, parent_layout):
        """创建数据处理面板"""
        # 频率计算
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("选择:"))
        self.freq_var_combo = QComboBox()
        self.freq_var_combo.setMinimumWidth(120)
        freq_layout.addWidget(self.freq_var_combo)
        
        calc_freq_btn = QPushButton("计算频率")
        calc_freq_btn.clicked.connect(self._calculate_frequency)
        freq_layout.addWidget(calc_freq_btn)
        parent_layout.addLayout(freq_layout)
        
        self.freq_result_label = QLabel("")
        self.freq_result_label.setStyleSheet("color: blue;")
        parent_layout.addWidget(self.freq_result_label)
        
        # 统计信息（自动更新）
        stats_group = QGroupBox("统计信息（自动更新）")
        stats_layout = QVBoxLayout(stats_group)
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setFont(QFont("Consolas", 9))
        stats_layout.addWidget(self.stats_text)
        parent_layout.addWidget(stats_group)
    
    def _create_log_panel(self, parent_layout):
        """创建日志面板"""
        group = QGroupBox("日志")
        layout = QVBoxLayout(group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        
        # 设置日志处理器
        text_handler = TextHandler(self.log_text)
        text_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(text_handler)
        
        parent_layout.addWidget(group, stretch=1)
    
    def _create_version_info(self, parent_layout):
        """创建版本信息"""
        version_label = QLabel(f"v{__version__}\n{__version_date__}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        version_label.setStyleSheet("color: gray; font-size: 8pt;")
        parent_layout.addWidget(version_label)
    
    def _refresh_ports(self):
        """刷新串口列表"""
        self.port_combo.clear()
        ports = SerialReader.list_ports()
        port_count = len(ports)
        for port_info in ports:
            self.port_combo.addItem(f"{port_info['port']} - {port_info['description']}", port_info['port'])
        
        # 显示InfoBar提示
        InfoBarHelper.information(
            self,
            title="串口列表已刷新",
            content=f"找到 {port_count} 个可用串口"
        )
    
    def _toggle_connection(self):
        """切换连接状态"""
        if not self.is_running:
            # 连接
            # 检查是否在加载模式（连接和加载互斥）
            if self.is_loaded_mode:
                InfoBarHelper.warning(
                    self,
                    title="无法连接",
                    content="加载文件状态下不能连接，请先取消加载"
                )
                return
            
            port_data = self.port_combo.currentData()
            if not port_data:
                InfoBarHelper.warning(
                    self,
                    title="参数错误",
                    content="请选择串口"
                )
                return
            
            port = port_data
            baudrate = int(self.baudrate_combo.currentText())
            
            self.serial_reader = SerialReader(port=port, baudrate=baudrate)
            if self.serial_reader.connect():
                self.is_running = True
                self.connect_btn.setText("断开")
                self.connect_btn.setStyleSheet("background-color: #f44336; color: white;")
                self.status_label.setText("已连接")
                self.status_label.setStyleSheet("color: green;")
                self.logger.info(f"串口连接成功: {port} @ {baudrate}")
                
                # 显示成功提示
                InfoBarHelper.success(
                    self,
                    title="连接成功",
                    content=f"串口连接成功: {port} @ {baudrate}"
                )
                
                # 清空呼吸估计结果显示
                if hasattr(self, 'breathing_result_text'):
                    self.breathing_result_text.setPlainText("等待数据积累...")
                
                # 禁用文件加载tab
                self._set_load_tab_enabled(False)
            else:
                InfoBarHelper.error(
                    self,
                    title="连接失败",
                    content="串口连接失败，请检查串口设置"
                )
        else:
            # 断开
            if self.serial_reader:
                self.serial_reader.disconnect()
            self.is_running = False
            self.connect_btn.setText("连接")
            self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white;")
            self.status_label.setText("未连接")
            self.status_label.setStyleSheet("color: red;")
            self.logger.info("串口已断开")
            
            # 显示警告提示
            InfoBarHelper.warning(
                self,
                title="已断开连接",
                content="串口连接已断开"
            )
            
            # 清空呼吸估计结果显示
            if hasattr(self, 'breathing_result_text'):
                self.breathing_result_text.setPlainText("未连接")
            
            # 启用文件加载tab（断开连接后，如果不在加载模式，加载tab可用）
            # 如果在加载模式，加载tab应该已经可用（因为加载时没有禁用）
            if not self.is_loaded_mode:
                self._set_load_tab_enabled(True)
    
    def _on_frame_type_changed(self, text):
        """帧类型改变"""
        self.frame_type = text
        self.frame_mode = (self.frame_type == "演示帧")
        self.logger.info(f"帧类型已设置为: {self.frame_type}")
    
    def _start_update_loop(self):
        """启动更新循环（使用 QTimer）"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_data)
        self.update_timer.start(int(config.update_interval_sec * 1000))  # 转换为毫秒
    
    def _update_data(self):
        """更新数据（在主线程中调用，批量处理队列数据）"""
        if not self.is_running or not self.serial_reader:
            return
        
        # 批量获取串口数据（每次最多处理max_batch_size条）
        data_batch = self.serial_reader.get_data_batch(max_count=self.max_batch_size)
        
        if not data_batch:
            # 没有数据时，检查是否有待更新的绘图（处理队列积压后的遗留更新）
            if self.pending_plot_update and self.frame_mode:
                self._update_frame_plots()
                self.frames_since_last_plot = 0
                self.pending_plot_update = False
            
            # 检查队列大小并发出警告（如果队列积压过多）
            queue_size = self.serial_reader.get_queue_size()
            if queue_size > 100:  # 队列积压超过100条
                current_time = time.time()
                if current_time - self.last_queue_warning_time >= self.queue_warning_interval:
                    self.last_queue_warning_time = current_time
                    self.logger.warning(
                        f"[性能警告] 数据队列积压: {queue_size}条数据待处理，"
                        f"可能导致显示延迟。建议检查数据处理性能。"
                    )
            return
        
        # 记录处理的帧数
        frames_processed = 0
        has_new_frame = False
        
        # 批量处理数据
        for data in data_batch:
            # 如果是帧模式，优先处理帧数据
            if self.frame_mode:
                # 解析数据（会更新内部状态，累积IQ数据）
                parsed = self.data_parser.parse(data['text'])
                
                # 如果parse返回了完成的帧（检测到帧尾时完成）
                if parsed and parsed.get('frame'):
                    frame_data = parsed
                    if len(frame_data.get('channels', {})) > 0:
                        # 只在处理第一批数据时打印详细信息，避免日志过多
                        if frames_processed == 0:
                            channels = sorted(frame_data['channels'].keys())
                            self.logger.info(
                                f"[帧完成] index={frame_data['index']}, "
                                f"timestamp={frame_data['timestamp_ms']}ms, "
                                f"通道数={len(channels)}, "
                                f"通道范围={channels[0]}-{channels[-1] if channels else 'N/A'}"
                            )
                        
                        self.data_processor.add_frame_data(frame_data)
                        frames_processed += 1
                        has_new_frame = True
                        
                        # 更新呼吸估计的信道列表（只在处理第一批数据时更新，避免频繁操作）
                        if frames_processed == 1 and hasattr(self, 'breathing_channel_combo'):
                            all_channels = self.data_processor.get_all_frame_channels()
                            if all_channels:
                                current_items = [self.breathing_channel_combo.itemText(i) 
                                               for i in range(self.breathing_channel_combo.count())]
                                channel_list = [str(ch) for ch in sorted(all_channels)]
                                if set(channel_list) != set(current_items):
                                    self.breathing_channel_combo.clear()
                                    self.breathing_channel_combo.addItems(channel_list)
                                    if channel_list and self.breathing_channel_combo.currentIndex() < 0:
                                        self.breathing_channel_combo.setCurrentIndex(0)
                
                # 帧模式下不处理其他数据
                continue
            
            # 非帧模式：解析简单数据
            parsed = self.data_parser.parse(data['text'])
            
            # 处理简单数据（向后兼容）
            if parsed and not parsed.get('frame'):
                self.data_processor.add_data(data['timestamp'], parsed)
                has_new_frame = True
        
        # 批量处理完成后，统一更新绘图（避免每处理一条数据就更新一次）
        if has_new_frame:
            if self.frame_mode:
                # 帧模式：累积帧数，达到阈值或队列积压较多时才更新绘图
                self.frames_since_last_plot += frames_processed
                queue_size = self.serial_reader.get_queue_size()
                
                # 如果累积了足够多的帧，或者队列积压较多，则更新绘图
                should_update_plot = (
                    self.frames_since_last_plot >= self.min_frames_before_plot_update or
                    queue_size > 50  # 队列积压超过50条时强制更新
                )
                
                if should_update_plot:
                    self._update_frame_plots()
                    self.frames_since_last_plot = 0
                    self.pending_plot_update = False
                else:
                    self.pending_plot_update = True
            else:
                # 非帧模式：更新绘图
                if 'amplitude' in self.plotters:
                    plotter = self.plotters['amplitude']['plotter']
                    vars_list = self.data_processor.get_all_variables()
                    for var_name in vars_list:
                        times, values = self.data_processor.get_data_range(
                            var_name, duration=config.default_frequency_duration
                        )
                        if len(times) > 0:
                            plotter.update_plot(var_name, times, values)
                    
                    # 更新变量列表
                    self.freq_var_combo.clear()
                    self.freq_var_combo.addItems(vars_list)
                    if vars_list and self.freq_var_combo.currentIndex() < 0:
                        self.freq_var_combo.setCurrentIndex(0)
            
            # 使用节流刷新，避免频繁刷新导致GUI卡顿
            self._refresh_plotters_throttled()
        
        # 如果批量处理了多条数据，记录日志
        if len(data_batch) > 1:
            queue_remaining = self.serial_reader.get_queue_size()
            if queue_remaining > 0:
                self.logger.debug(
                    f"[批量处理] 本次处理{len(data_batch)}条数据，"
                    f"队列剩余{queue_remaining}条"
                )
        
        # 定期更新频率列表和统计信息（使用单独的定时器）
        if not hasattr(self, 'freq_update_timer'):
            self.freq_update_timer = QTimer()
            self.freq_update_timer.timeout.connect(self._update_freq_list_and_stats)
            self.freq_update_timer.start(int(config.freq_list_update_interval_sec * 1000))
    
    def _on_channel_mode_changed(self, text):
        """信道选择模式变化时的回调"""
        self._show_channel_input_mode(text)
    
    def _show_channel_input_mode(self, mode: str):
        """根据模式显示对应的输入框"""
        # 清除所有输入框
        while self.channel_input_layout.count():
            item = self.channel_input_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                self.channel_input_layout.removeWidget(item.widget())
        
        # 显示对应模式的输入框和标签
        if mode == "间隔X信道":
            self.channel_input_layout.addWidget(self.interval_entry)
            self.channel_input_layout.addWidget(self.interval_label)
            self.interval_entry.show()
            self.interval_label.show()
        elif mode == "信道范围":
            self.channel_input_layout.addWidget(self.range_entry)
            self.channel_input_layout.addWidget(self.range_label)
            self.range_entry.show()
            self.range_label.show()
        else:  # 手动输入
            self.channel_input_layout.addWidget(self.display_channels_entry)
            self.channel_input_layout.addWidget(self.manual_label)
            self.display_channels_entry.show()
            self.manual_label.show()
    
    def _parse_interval_channels(self, interval_str: str) -> List[int]:
        """解析间隔信道模式"""
        try:
            interval = int(interval_str.strip())
            if interval <= 0:
                self.logger.warning(f"间隔数必须大于0，使用默认值4")
                interval = 4
            
            # 生成信道列表：0, interval, 2*interval, ... 直到不超过72
            channels = []
            ch = 0
            while ch <= 72:
                channels.append(ch)
                ch += interval
            
            return channels
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"解析间隔信道失败: {interval_str}, 错误: {e}, 使用默认值4")
            return list(range(0, 73, 4))
    
    def _parse_range_channels(self, range_str: str) -> List[int]:
        """解析信道范围模式"""
        channels = []
        range_str = range_str.strip()
        if not range_str:
            return list(range(10))
        
        try:
            # 按逗号分割
            parts = [p.strip() for p in range_str.split(',')]
            for part in parts:
                if '-' in part:
                    start, end = part.split('-', 1)
                    start = int(start.strip())
                    end = int(end.strip())
                    start = max(0, min(start, 72))
                    end = max(0, min(end, 72))
                    if start <= end:
                        channels.extend(range(start, end + 1))
                else:
                    ch = int(part.strip())
                    if 0 <= ch <= 72:
                        channels.append(ch)
            
            channels = sorted(list(set(channels)))
            return channels
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"解析信道范围失败: {range_str}, 错误: {e}, 使用默认值")
            return list(range(10))
    
    def _parse_display_channels(self, text: str) -> List[int]:
        """解析展示信道字符串（手动输入模式）"""
        channels = []
        text = text.strip()
        if not text:
            return list(range(10))
        
        try:
            parts = [p.strip() for p in text.split(',')]
            for part in parts:
                if '-' in part:
                    start, end = part.split('-', 1)
                    start = int(start.strip())
                    end = int(end.strip())
                    start = max(0, min(start, 72))
                    end = max(0, min(end, 72))
                    if start <= end:
                        channels.extend(range(start, end + 1))
                else:
                    ch = int(part.strip())
                    if 0 <= ch <= 72:
                        channels.append(ch)
            
            channels = sorted(list(set(channels)))
            return channels
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"解析展示信道失败: {text}, 错误: {e}, 使用默认值")
            return list(range(10))
    
    def _apply_frame_settings(self, show_info: bool = True):
        """应用帧模式设置"""
        # 解析展示帧数
        try:
            display_frames = int(self.display_max_frames_entry.text())
            if display_frames > 0:
                self.display_max_frames = min(display_frames, config.max_display_max_frames)
                self.logger.info(f"显示帧数设置为: {self.display_max_frames}")
            else:
                self.logger.warning(f"显示帧数必须大于0，使用默认值{config.default_display_max_frames}")
                self.display_max_frames = config.default_display_max_frames
                self.display_max_frames_entry.setText(str(config.default_display_max_frames))
        except ValueError:
            self.logger.warning(f"显示帧数无效，使用默认值{config.default_display_max_frames}")
            self.display_max_frames = config.default_display_max_frames
            self.display_max_frames_entry.setText(str(config.default_display_max_frames))
        
        # 根据选择的模式解析展示信道
        mode = self.channel_mode_combo.currentText()
        old_display_channel_list = self.display_channel_list.copy() if self.display_channel_list else []
        
        if mode == "间隔X信道":
            interval_str = self.interval_entry.text()
            new_display_channel_list = self._parse_interval_channels(interval_str)
        elif mode == "信道范围":
            range_str = self.range_entry.text()
            new_display_channel_list = self._parse_range_channels(range_str)
        else:  # 手动输入
            display_text = self.display_channels_entry.text()
            new_display_channel_list = self._parse_display_channels(display_text)
        
        # 清除不再需要的信道图例
        if self.frame_mode and old_display_channel_list:
            channels_to_remove = set(old_display_channel_list) - set(new_display_channel_list)
            if channels_to_remove:
                for plotter_info in self.plotters.values():
                    plotter = plotter_info.get('plotter')
                    if plotter is None:
                        continue
                    for ch in channels_to_remove:
                        var_name = f"ch{ch}"
                        if var_name in plotter.data_lines:
                            plotter.remove_line(var_name)
        
        self.display_channel_list = new_display_channel_list
        self.logger.info(f"展示信道设置为: {self.display_channel_list} (模式: {mode})")
        
        # 只在用户主动调整时显示信息提示（初始化时不显示）
        if show_info:
            channel_info = f"信道: {self.display_channel_list}, 显示帧数: {self.display_max_frames}"
            InfoBarHelper.information(
                self,
                title="信道配置已更新",
                content=channel_info
            )
        
        # 如果处于加载模式，更新滑动条范围
        if self.is_loaded_mode and self.loaded_frames:
            max_start = max(0, len(self.loaded_frames) - self.display_max_frames)
            if hasattr(self, 'time_window_slider'):
                self.time_window_slider.setMaximum(max_start)
                if self.current_window_start > max_start:
                    self.current_window_start = max_start
                    self.time_window_slider.setValue(max_start)
        
        # 立即更新绘图
        if self.frame_mode:
            if self.is_loaded_mode:
                # 加载模式下，更新所有plot tab
                self._update_loaded_mode_plots()
            else:
                # 连接模式下，更新实时绘图
                self._update_frame_plots()
    
    def _set_save_path(self):
        """设置保存路径"""
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录", user_settings.get_save_directory())
        if directory:
            user_settings.set_save_directory(directory)
            display_path = directory if len(directory) <= 50 else "..." + directory[-47:]
            self.path_label.setText(f"当前路径: {display_path}")
            self.logger.info(f"保存路径已设置为: {directory}")
            
            # 显示信息提示
            InfoBarHelper.information(
                self,
                title="保存路径已设置",
                content=f"保存路径: {display_path}"
            )
    
    def _toggle_auto_save(self, checked):
        """切换自动保存路径"""
        self.use_auto_save = checked
        user_settings.set_use_auto_save_path(checked)
        self.logger.info(f"自动保存路径: {'启用' if checked else '禁用'}")
    
    def _save_data(self):
        """统一的保存数据方法"""
        if self.save_all_radio.isChecked():
            self._save_all_frames()
        else:
            self._save_recent_frames()
    
    def _save_all_frames(self):
        """保存所有帧数据"""
        if not self.frame_mode:
            InfoBarHelper.warning(
                self,
                title="无法保存",
                content="当前不是帧模式，无法保存帧数据"
            )
            return
        
        if self.is_saving:
            InfoBarHelper.warning(
                self,
                title="操作进行中",
                content="保存操作正在进行中，请稍候..."
            )
            return
        
        frames = self.data_processor.raw_frames
        if not frames:
            InfoBarHelper.warning(
                self,
                title="无数据",
                content="没有可保存的帧数据"
            )
            return
        
        # 根据设置决定是否弹出对话框
        if self.use_auto_save:
            filepath = self.data_saver.get_auto_save_path(prefix="frames", save_all=True)
            self.logger.info(f"使用自动保存路径: {filepath}")
        else:
            default_filename = self.data_saver.get_default_filename(prefix="frames", save_all=True)
            filepath, _ = QFileDialog.getSaveFileName(
                self, "保存所有帧数据", default_filename,
                "JSON文件 (*.json);;所有文件 (*.*)"
            )
            if not filepath:
                return
        
        # 在后台线程中执行保存操作
        def save_in_thread():
            try:
                self.is_saving = True
                # 通过信号在主线程中更新状态
                self.save_status_update_signal.emit(f"正在保存 {len(frames)} 帧数据...", "color: black;")
                
                success = self.data_saver.save_frames(frames, filepath, max_frames=None)
                
                if success:
                    # 显示简洁的保存信息（只显示文件名）
                    filename = os.path.basename(filepath)
                    frame_count = len(frames)
                    # 通过信号在主线程中更新UI和显示InfoBar
                    self.save_success_signal.emit(frame_count, filename)
                else:
                    # 通过信号在主线程中显示错误提示
                    self.save_error_signal.emit("保存失败，请查看日志")
            except Exception as e:
                self.logger.error(f"保存数据时出错: {e}")
                error_msg = str(e)
                # 通过信号在主线程中显示错误提示
                self.save_error_signal.emit(f"保存失败: {error_msg}")
            finally:
                self.is_saving = False
        
        import threading
        save_thread = threading.Thread(target=save_in_thread, daemon=True)
        save_thread.start()
    
    def _on_save_status_update(self, text: str, color_style: str):
        """在主线程中更新保存状态（由信号触发）"""
        self.save_status_label.setText(text)
        self.save_status_label.setStyleSheet(color_style)
    
    def _on_save_success(self, frame_count: int, filename: str):
        """在主线程中显示保存成功（由信号触发）"""
        self.save_status_label.setText(f"✓ 已保存 {frame_count} 帧到: {filename}")
        self.save_status_label.setStyleSheet("color: green;")
        InfoBarHelper.success(
            self,
            title="保存成功",
            content=f"已保存 {frame_count} 帧"
        )
    
    def _on_save_error(self, error_msg: str):
        """在主线程中显示保存错误（由信号触发）"""
        self.save_status_label.setText(f"✗ {error_msg}")
        self.save_status_label.setStyleSheet("color: red;")
        InfoBarHelper.error(
            self,
            title="保存失败",
            content=error_msg
        )
    
    def _save_recent_frames(self):
        """保存最近N帧数据"""
        if not self.frame_mode:
            InfoBarHelper.warning(
                self,
                title="无法保存",
                content="当前不是帧模式，无法保存帧数据"
            )
            return
        
        if self.is_saving:
            InfoBarHelper.warning(
                self,
                title="操作进行中",
                content="保存操作正在进行中，请稍候..."
            )
            return
        
        frames = self.data_processor.raw_frames
        if not frames:
            InfoBarHelper.warning(
                self,
                title="无数据",
                content="没有可保存的帧数据"
            )
            return
        
        # 获取显示帧数参数
        try:
            max_frames = int(self.display_max_frames_entry.text())
            if max_frames <= 0:
                raise ValueError("显示帧数必须大于0")
        except ValueError:
            max_frames = config.default_display_max_frames
            self.logger.warning(f"显示帧数无效，使用默认值: {max_frames}")
        
        # 根据设置决定是否弹出对话框
        if self.use_auto_save:
            filepath = self.data_saver.get_auto_save_path(
                prefix="frames", save_all=False, max_frames=max_frames
            )
            self.logger.info(f"使用自动保存路径: {filepath}")
        else:
            default_filename = self.data_saver.get_default_filename(
                prefix="frames", save_all=False, max_frames=max_frames
            )
            filepath, _ = QFileDialog.getSaveFileName(
                self, f"保存最近{max_frames}帧数据", default_filename,
                "JSON文件 (*.json);;所有文件 (*.*)"
            )
            if not filepath:
                return
        
        saved_count = min(max_frames, len(frames))
        
        # 在后台线程中执行保存操作
        def save_in_thread():
            try:
                self.is_saving = True
                # 通过信号在主线程中更新状态
                self.save_status_update_signal.emit(f"正在保存最近 {saved_count} 帧数据...", "color: black;")
                
                success = self.data_saver.save_frames(frames, filepath, max_frames=max_frames)
                
                if success:
                    # 显示简洁的保存信息（只显示文件名）
                    filename = os.path.basename(filepath)
                    # 通过信号在主线程中更新UI和显示InfoBar
                    self.save_success_signal.emit(saved_count, filename)
                else:
                    # 通过信号在主线程中显示错误提示
                    self.save_error_signal.emit("保存失败，请查看日志")
            except Exception as e:
                self.logger.error(f"保存数据时出错: {e}")
                error_msg = str(e)
                # 通过信号在主线程中显示错误提示
                self.save_error_signal.emit(f"保存失败: {error_msg}")
            finally:
                self.is_saving = False
        
        import threading
        save_thread = threading.Thread(target=save_in_thread, daemon=True)
        save_thread.start()
    
    def _on_clear_data_btn_pressed(self, event):
        """清除数据按钮按下事件"""
        # 只响应左键按下
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_holding_clear_btn = True
            self.clear_data_progress_value = 0
            self.clear_data_progress_ring.setValue(0)
            self.clear_data_progress_ring.setStyleSheet("opacity: 1;")  # 显示进度环
            
            # 创建定时器来更新进度
            if self.clear_data_progress_timer is None:
                self.clear_data_progress_timer = QTimer()
                self.clear_data_progress_timer.timeout.connect(self._update_clear_data_progress)
            
            # 计算更新间隔（每20ms更新一次，2秒共100次，每次增加1%）
            update_interval = int((self.clear_data_hold_duration * 1000) / 100)  # 20ms，100次更新
            self.clear_data_progress_timer.start(update_interval)
        
    def _on_clear_data_btn_released(self, event):
        """清除数据按钮松开事件"""
        # 只响应左键松开
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_holding_clear_btn = False
            
            # 停止定时器
            if self.clear_data_progress_timer:
                self.clear_data_progress_timer.stop()
            
            # 如果进度未完成，隐藏进度环
            if self.clear_data_progress_value < 100:
                self.clear_data_progress_ring.setStyleSheet("opacity: 0;")  # 隐藏进度环但保持占用空间
                self.clear_data_progress_value = 0
                self.clear_data_progress_ring.setValue(0)
    
    def _update_clear_data_progress(self):
        """更新清除数据进度"""
        if not self.is_holding_clear_btn:
            # 如果已经松开，停止更新
            if self.clear_data_progress_timer:
                self.clear_data_progress_timer.stop()
                self.clear_data_progress_ring.setStyleSheet("opacity: 0;")  # 隐藏进度环但保持占用空间
                self.clear_data_progress_value = 0
                self.clear_data_progress_ring.setValue(0)
            return
        
        # 增加进度值（每次增加1%，100次达到100%）
        self.clear_data_progress_value += 1
        self.clear_data_progress_ring.setValue(self.clear_data_progress_value)
        
        # 如果达到100%，执行清除操作
        if self.clear_data_progress_value >= 100:
            if self.clear_data_progress_timer:
                self.clear_data_progress_timer.stop()
            self.is_holding_clear_btn = False
            self.clear_data_progress_ring.setStyleSheet("opacity: 0;")  # 隐藏进度环但保持占用空间
            self.clear_data_progress_value = 0
            self.clear_data_progress_ring.setValue(0)
            
            # 执行清除数据操作
            self._clear_data()
    
    def _clear_data(self):
        """清空数据"""
        # 显示警告提示
        InfoBarHelper.warning(
            self,
            title="数据已清空",
            content="所有数据已清空"
        )
        
        self.data_processor.clear_buffer(clear_frames=True)
        # 清空所有绘图器（包括实时绘图和呼吸估计）
        for plotter_info in self.plotters.values():
            plotter = plotter_info.get('plotter')
            if plotter is None:
                # 呼吸估计tab使用matplotlib，需要单独处理
                if 'breathing_estimation' in self.plotters and 'axes' in plotter_info:
                    axes = plotter_info['axes']
                    axes['top_left'].clear()
                    axes['top_right'].clear()
                    axes['bottom_left'].clear()
                    axes['bottom_right'].clear()
                    # 重置标题和标签
                    axes['top_left'].set_title('Raw Data', fontsize=10)
                    axes['top_left'].set_xlabel('Frame Index')
                    axes['top_left'].set_ylabel('Amplitude')
                    axes['top_left'].grid(True, alpha=0.3)
                    axes['top_right'].set_title('Median + Highpass Filter', fontsize=10)
                    axes['top_right'].set_xlabel('Frame Index')
                    axes['top_right'].set_ylabel('Amplitude')
                    axes['top_right'].grid(True, alpha=0.3)
                    axes['bottom_left'].set_title('FFT Spectrum: Before vs After Bandpass', fontsize=10)
                    axes['bottom_left'].set_xlabel('Frequency (Hz)')
                    axes['bottom_left'].set_ylabel('Power')
                    axes['bottom_left'].grid(True, alpha=0.3)
                    axes['bottom_right'].axis('off')
                    axes['bottom_right'].set_title('Breathing Detection Result', fontsize=10, pad=20)
                    # 刷新画布
                    if 'canvas' in plotter_info:
                        plotter_info['canvas'].draw_idle()
                continue
            plotter.clear_plot()
        self.data_parser.clear_buffer()
        
        # 清空呼吸估计结果显示
        if hasattr(self, 'breathing_result_text'):
            self.breathing_result_text.setPlainText("数据已清空")
        
        self.logger.info("数据已清空")
    
    def _browse_load_file(self):
        """浏览加载文件"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择要加载的文件", "",
            "JSON文件 (*.json);;所有文件 (*.*)"
        )
        if filepath:
            self.load_file_entry.setText(filepath)
    
    def _toggle_load_file(self):
        """切换加载/取消加载文件"""
        if self.is_loaded_mode:
            self._unload_file()
        else:
            self._load_file()
    
    def _load_file(self):
        """加载文件"""
        # 检查是否已连接（连接和加载互斥）
        if self.is_running:
            InfoBarHelper.warning(
                self,
                title="无法加载",
                content="连接状态下不能加载文件，请先断开连接"
            )
            return
        
        filepath = self.load_file_entry.text().strip()
        if not filepath:
            InfoBarHelper.warning(
                self,
                title="参数错误",
                content="请选择要加载的文件"
            )
            return
        
        try:
            data = self.data_saver.load_frames(filepath)
            if not data:
                InfoBarHelper.error(
                    self,
                    title="加载失败",
                    content="文件加载失败，请查看日志"
                )
                return
            
            self.loaded_frames = data.get('frames', [])
            self.loaded_file_info = data
            self.is_loaded_mode = True
            self.current_window_start = 0
            
            # 更新文件信息显示（完整信息）
            self._update_load_file_info()
            
            # 启用时间窗控制并更新范围
            max_start = max(0, len(self.loaded_frames) - self.display_max_frames)
            self.time_window_slider.setMaximum(max_start)
            self.time_window_slider.setValue(0)
            self.window_start_entry.setText("0")
            
            # 启用时间窗控制控件
            self._set_load_tab_enabled(True)
            
            # 禁用连接tab的功能（加载模式和连接态互斥）
            self._set_connection_tab_enabled(False)
            
            # 注意：不禁用文件加载tab，因为用户可以取消加载
            
            # 更新信道列表（用于呼吸估计）
            all_channels = set()
            for frame in self.loaded_frames[:10]:  # 只检查前10帧
                channels = frame.get('channels', {})
                for ch in channels.keys():
                    try:
                        ch_int = int(ch) if isinstance(ch, str) and str(ch).isdigit() else ch
                        all_channels.add(ch_int)
                    except:
                        all_channels.add(ch)
            channel_list = sorted(list(all_channels))
            self.breathing_channel_combo.clear()
            self.breathing_channel_combo.addItems([str(ch) for ch in channel_list])
            if channel_list:
                self.breathing_channel_combo.setCurrentIndex(0)
            
            # 呼吸估计控制面板已经常驻显示，不需要切换
            
            # 切换按钮为取消加载
            self.load_unload_btn.setText("取消加载")
            self.load_unload_btn.setStyleSheet("background-color: #f44336; color: white;")  # 红色
            
            # 加载数据到处理器
            self.data_processor.clear_buffer(clear_frames=True)
            for frame in self.loaded_frames:
                self.data_processor.add_frame_data(frame)
            
            # 更新加载模式的绘图
            self._update_loaded_mode_plots()
            
            # 初始化重置按钮状态（确保颜色正确）
            self._check_and_update_reset_button()
            
            self.logger.info(f"文件加载成功: {filepath}, 共 {len(self.loaded_frames)} 帧")
            InfoBarHelper.success(
                self, 
                title="加载成功", 
                content=f"文件加载成功，共 {len(self.loaded_frames)} 帧"
            )
        except Exception as e:
            self.logger.error(f"加载文件时出错: {e}")
            InfoBarHelper.error(
                self,
                title="加载失败",
                content=f"加载文件失败: {str(e)}"
            )
    
    def _update_load_file_info(self):
        """更新加载文件信息显示"""
        if not self.loaded_file_info:
            return

        info_lines = []
        info_lines.append(f"版本: {self.loaded_file_info.get('version', 'N/A')}")
        info_lines.append(f"保存时间: {self.loaded_file_info.get('saved_at', 'N/A')}")
        info_lines.append(f"原始总帧数: {self.loaded_file_info.get('total_frames', 0)}")
        info_lines.append(f"保存的帧数: {self.loaded_file_info.get('saved_frames', 0)}")

        max_frames_param = self.loaded_file_info.get('max_frames_param')
        if max_frames_param is None:
            info_lines.append(f"保存模式: 全部帧")
        else:
            info_lines.append(f"保存模式: 最近 {max_frames_param} 帧")

        if self.loaded_frames:
            info_lines.append(f"\n第一帧: index={self.loaded_frames[0]['index']}, timestamp={self.loaded_frames[0]['timestamp_ms']} ms")
            info_lines.append(f"最后一帧: index={self.loaded_frames[-1]['index']}, timestamp={self.loaded_frames[-1]['timestamp_ms']} ms")

            # 计算时间跨度
            time_span = (self.loaded_frames[-1]['timestamp_ms'] - self.loaded_frames[0]['timestamp_ms']) / 1000.0
            info_lines.append(f"时间跨度: {time_span:.2f} 秒")

            # 计算平均帧率
            if len(self.loaded_frames) > 1:
                intervals = []
                for i in range(1, min(100, len(self.loaded_frames))):  # 只计算前100帧的间隔
                    interval = (self.loaded_frames[i]['timestamp_ms'] - self.loaded_frames[i-1]['timestamp_ms']) / 1000.0
                    intervals.append(interval)
                if intervals:
                    avg_interval = np.mean(intervals)
                    info_lines.append(f"平均帧间隔: {avg_interval:.3f} 秒")
                    info_lines.append(f"平均帧率: {1.0/avg_interval:.2f} 帧/秒")

        self.load_file_info_text.setPlainText("\n".join(info_lines))
    
    def _unload_file(self):
        """取消加载文件"""
        self.is_loaded_mode = False
        self.loaded_frames = []
        self.loaded_file_info = None
        self.current_window_start = 0
        
        # 禁用时间窗控制控件
        self._set_load_tab_enabled(False)
        
        # 启用连接tab的功能
        self._set_connection_tab_enabled(True)
        
        # 呼吸估计控制面板已经常驻显示，不需要切换
        
        # 切换按钮为加载文件
        self.load_unload_btn.setText("加载文件")
        self.load_unload_btn.setStyleSheet("background-color: #2196F3; color: white;")  # 浅蓝色
        
        # 恢复重置按钮的默认样式（因为不再处于加载模式）
        self.reset_view_btn.setStyleSheet(self.reset_view_btn_default_style)
        
        # 清空文件信息
        self.load_file_info_text.clear()
        self.load_file_entry.clear()
        
        # 清空数据
        self.data_processor.clear_buffer(clear_frames=True)
        for plotter_info in self.plotters.values():
            plotter = plotter_info.get('plotter')
            if plotter is None:
                continue
            plotter.clear_plot()
        
        self.logger.info("已取消文件加载")
        InfoBarHelper.warning(
            self,
            title="已取消加载",
            content="已取消文件加载"
        )
    
    def _set_connection_tab_enabled(self, enabled: bool):
        """启用或禁用连接tab的功能"""
        self.port_combo.setEnabled(enabled)
        self.connect_btn.setEnabled(enabled)
        self.frame_type_combo.setEnabled(enabled)
        if hasattr(self, 'baudrate_combo'):
            self.baudrate_combo.setEnabled(enabled)
    
    def _set_load_tab_enabled(self, enabled: bool):
        """启用或禁用文件加载tab的功能（包括时间窗控制）"""
        # 文件路径相关控件（加载文件时应该禁用，避免重复加载）
        # 注意：这里的逻辑是反的，enabled=True表示已加载文件，应该禁用文件选择
        # 但时间窗控制应该启用
        if hasattr(self, 'load_file_entry'):
            self.load_file_entry.setEnabled(not enabled)  # 已加载时禁用文件选择
        if hasattr(self, 'load_unload_btn'):
            self.load_unload_btn.setEnabled(True)  # 加载/取消加载按钮始终启用
        if hasattr(self, 'browse_btn'):
            self.browse_btn.setEnabled(not enabled)  # 已加载时禁用浏览按钮
        
        # 时间窗控制控件（加载文件时启用，未加载时禁用）
        if hasattr(self, 'window_start_entry'):
            self.window_start_entry.setEnabled(enabled)
        if hasattr(self, 'time_window_slider'):
            self.time_window_slider.setEnabled(enabled)
        if hasattr(self, 'slider_left_btn'):
            self.slider_left_btn.setEnabled(enabled)
        if hasattr(self, 'slider_right_btn'):
            self.slider_right_btn.setEnabled(enabled)
        if hasattr(self, 'reset_view_btn'):
            self.reset_view_btn.setEnabled(enabled)
    
    def _calculate_frequency(self):
        """计算频率"""
        var_name = self.freq_var_combo.currentText()
        if not var_name:
            InfoBarHelper.warning(
                self,
                title="参数错误",
                content="请选择要计算的变量"
            )
            return
        
        try:
            if self.frame_mode:
                # 帧模式：计算通道频率
                if var_name.startswith('ch') and var_name[2:].isdigit():
                    channel = int(var_name[2:])
                    freq_info = self.data_processor.calculate_channel_frequency_detailed(
                        channel, max_frames=self.display_max_frames, data_type='amplitude'
                    )
                    if freq_info:
                        freq = freq_info['frequency']
                        self.freq_result_label.setText(f"{var_name} 频率: {freq:.4f} Hz")
                    else:
                        self.freq_result_label.setText(f"{var_name} 频率计算失败（数据不足）")
                else:
                    InfoBarHelper.warning(
                        self,
                        title="参数错误",
                        content="帧模式下请选择通道（ch0, ch1, ...）"
                    )
            else:
                # 非帧模式：计算变量频率
                freq = self.data_processor.calculate_frequency(var_name, duration=config.default_frequency_duration)
                if freq:
                    self.freq_result_label.setText(f"{var_name} 频率: {freq:.4f} Hz")
                else:
                    self.freq_result_label.setText(f"{var_name} 频率计算失败（数据不足）")
        except Exception as e:
            self.logger.error(f"计算频率时出错: {e}")
            InfoBarHelper.error(
                self,
                title="计算失败",
                content=f"计算频率失败: {str(e)}"
            )
    
    def _update_freq_list_and_stats(self):
        """更新频率列表和统计信息"""
        try:
            if self.frame_mode:
                # 帧模式：显示可用通道
                channels = self.data_processor.get_all_frame_channels()
                if channels:
                    channel_list = [f"ch{ch}" for ch in channels[:10]]  # 最多显示10个
                    current_items = [self.freq_var_combo.itemText(i) for i in range(self.freq_var_combo.count())]
                    if set(channel_list) != set(current_items):
                        self.freq_var_combo.clear()
                        self.freq_var_combo.addItems(channel_list)
                        if channel_list and self.freq_var_combo.currentIndex() < 0:
                            self.freq_var_combo.setCurrentIndex(0)
            else:
                # 非帧模式：显示变量列表
                vars_list = self.data_processor.get_all_variables()
                current_items = [self.freq_var_combo.itemText(i) for i in range(self.freq_var_combo.count())]
                if set(vars_list) != set(current_items):
                    self.freq_var_combo.clear()
                    self.freq_var_combo.addItems(vars_list)
                    if vars_list and self.freq_var_combo.currentIndex() < 0:
                        self.freq_var_combo.setCurrentIndex(0)
            
            # 更新统计信息
            self._update_statistics()
        except Exception as e:
            self.logger.error(f"更新频率列表和统计信息时出错: {e}")
    
    def _update_statistics(self):
        """更新统计信息"""
        try:
            var_name = self.freq_var_combo.currentText()
            if not var_name:
                self.stats_text.setPlainText("请选择变量")
                return
            
            if self.frame_mode:
                # 帧模式：显示通道统计信息
                if var_name.startswith('ch') and var_name[2:].isdigit():
                    channel = int(var_name[2:])
                    indices, amplitudes = self.data_processor.get_frame_data_range(
                        channel, max_frames=self.display_max_frames, data_type='amplitude'
                    )
                    if len(amplitudes) > 0:
                        stats = {
                            'mean': np.mean(amplitudes),
                            'std': np.std(amplitudes),
                            'max': np.max(amplitudes),
                            'min': np.min(amplitudes),
                            'count': len(amplitudes)
                        }
                        stats_text = f"{var_name} 统计信息:\n"
                        stats_text += f"均值: {stats['mean']:.4f}\n"
                        stats_text += f"标准差: {stats['std']:.4f}\n"
                        stats_text += f"最大值: {stats['max']:.4f}\n"
                        stats_text += f"最小值: {stats['min']:.4f}\n"
                        stats_text += f"数据点数: {stats['count']}"
                        self.stats_text.setPlainText(stats_text)
                    else:
                        self.stats_text.setPlainText(f"{var_name} 暂无数据")
                else:
                    self.stats_text.setPlainText("请选择通道（ch0, ch1, ...）")
            else:
                # 非帧模式：显示变量统计信息
                stats = self.data_processor.calculate_statistics(var_name, duration=config.default_frequency_duration)
                if stats:
                    stats_text = f"{var_name} 统计信息:\n"
                    stats_text += f"均值: {stats['mean']:.4f}\n"
                    stats_text += f"标准差: {stats['std']:.4f}\n"
                    stats_text += f"最大值: {stats['max']:.4f}\n"
                    stats_text += f"最小值: {stats['min']:.4f}\n"
                    stats_text += f"数据点数: {stats['count']}"
                    self.stats_text.setPlainText(stats_text)
                else:
                    self.stats_text.setPlainText(f"{var_name} 暂无数据")
        except Exception as e:
            self.logger.error(f"更新统计信息时出错: {e}")
    
    def _update_frame_plots(self, tab_key=None):
        """更新帧数据绘图"""
        all_channels = self.data_processor.get_all_frame_channels()
        
        if not all_channels:
            return
        
        # 根据设置的展示信道列表筛选
        display_channels = []
        for ch in self.display_channel_list:
            if ch in all_channels:
                display_channels.append(ch)
        
        if not display_channels:
            return
        
        # 确定要更新的tab列表
        if tab_key is None:
            # 只更新当前打开的tab（优化性能）
            current_tab_index = self.plot_tabs.currentIndex()
            tab_configs = [
                ('amplitude', '幅值'),
                ('phase', '相位'),
                ('local_amplitude', 'Local观测Ref幅值'),
                ('local_phase', 'Local观测Ref相位'),
                ('remote_amplitude', 'Remote观测Ini幅值'),
                ('remote_phase', 'Remote观测Ini相位'),
            ]
            if current_tab_index < len(tab_configs):
                tab_key = tab_configs[current_tab_index][0]
                tabs_to_update = [tab_key] if tab_key in self.plotters else []
            else:
                tabs_to_update = []
        else:
            tabs_to_update = [tab_key] if tab_key in self.plotters else []
        
        # 更新指定的选项卡的绘图
        for tab_key_to_update in tabs_to_update:
            plotter_info = self.plotters[tab_key_to_update]
            plotter = plotter_info.get('plotter')
            if plotter is None:
                continue
            data_type = plotter_info['data_type']
            
            # 准备该数据类型的所有通道数据
            channel_data = {}
            for ch in display_channels:
                indices, values = self.data_processor.get_frame_data_range(
                    ch, max_frames=self.display_max_frames, data_type=data_type
                )
                if len(indices) > 0 and len(values) > 0:
                    channel_data[ch] = (indices, values)
            
            # 更新绘图
            if channel_data:
                plotter.update_frame_data(channel_data, max_channels=len(display_channels))
    
    def _refresh_plotters_throttled(self):
        """节流刷新绘图器"""
        current_time = time.time()
        if current_time - self.last_plot_refresh_time >= self.plot_refresh_interval:
            self.last_plot_refresh_time = current_time
            # PyQtGraph 不需要手动刷新，数据更新后自动显示
    
    def _create_breathing_estimation_tab(self):
        """创建呼吸估计选项卡（2x2子图布局）"""
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建2x2子图的figure
        figure = Figure(figsize=(10, 6), dpi=100)
        
        # 创建4个子图
        ax1 = figure.add_subplot(2, 2, 1)  # 左上：原始数据
        ax2 = figure.add_subplot(2, 2, 2)  # 右上：高通滤波
        ax3 = figure.add_subplot(2, 2, 3)  # 左下：FFT频谱
        ax4 = figure.add_subplot(2, 2, 4)  # 右下：呼吸检测结果（文本）
        
        # 设置子图标题
        ax1.set_title('Raw Data', fontsize=10)
        ax1.set_xlabel('Frame Index')
        ax1.set_ylabel('Amplitude')
        ax1.grid(True, alpha=0.3)
        
        ax2.set_title('Median + Highpass Filter', fontsize=10)
        ax2.set_xlabel('Frame Index')
        ax2.set_ylabel('Amplitude')
        ax2.grid(True, alpha=0.3)
        
        ax3.set_title('FFT Spectrum: Before vs After Bandpass', fontsize=10)
        ax3.set_xlabel('Frequency (Hz)')
        ax3.set_ylabel('Power')
        ax3.grid(True, alpha=0.3)
        
        # 右下角不画图，只显示文本
        ax4.axis('off')
        ax4.set_title('Breathing Detection Result', fontsize=10, pad=20)
        
        # 附加到界面
        canvas = FigureCanvasQTAgg(figure)
        layout.addWidget(canvas)
        
        # 保存引用
        self.plotters['breathing_estimation'] = {
            'plotter': None,  # 不使用Plotter类
            'figure': figure,
            'canvas': canvas,
            'axes': {
                'top_left': ax1,
                'top_right': ax2,
                'bottom_left': ax3,
                'bottom_right': ax4
            },
            'widget': tab_widget
        }
        
        # 添加到选项卡
        self.plot_tabs.addTab(tab_widget, "呼吸估计")
        
        # 呼吸估计控制（在加载模式下显示）
        # TODO: 如果需要，可以添加呼吸估计控制面板
    
    def _on_slider_pressed(self):
        """滑动条鼠标按下时的回调（记录当前值）"""
        # 不做任何操作，只是记录按下事件
        pass
    
    def _on_slider_keyboard_changed(self):
        """滑动条键盘方向键改变时的回调"""
        value = self.time_window_slider.value()
        self.current_window_start = value
        self.window_start_entry.setText(str(value))
        if self.is_loaded_mode:
            self._update_loaded_mode_plots()

    def _on_slider_released(self):
        """滑动条鼠标释放时的回调（拖动结束后才更新绘图）"""
        value = self.time_window_slider.value()
        self.current_window_start = value
        self.window_start_entry.setText(str(value))
        if self.is_loaded_mode:
            self._update_loaded_mode_plots()
    
    def _on_slider_left_click(self):
        """左箭头按钮点击（单步减少）"""
        current = self.current_window_start
        new_value = max(0, current - 1)
        self.current_window_start = new_value
        self.window_start_entry.setText(str(new_value))
        self.time_window_slider.setValue(new_value)
        if self.is_loaded_mode:
            self._update_loaded_mode_plots()
    
    def _on_slider_right_click(self):
        """右箭头按钮点击（单步增加）"""
        current = self.current_window_start
        max_start = max(0, len(self.loaded_frames) - self.display_max_frames) if self.loaded_frames else 0
        new_value = min(max_start, current + 1)
        self.current_window_start = new_value
        self.window_start_entry.setText(str(new_value))
        self.time_window_slider.setValue(new_value)
        if self.is_loaded_mode:
            self._update_loaded_mode_plots()
    
    def _on_window_start_changed(self):
        """时间窗起点输入框变化时的回调"""
        try:
            start = int(self.window_start_entry.text())
            max_start = max(0, len(self.loaded_frames) - self.display_max_frames) if self.loaded_frames else 0
            start = max(0, min(start, max_start))
            self.current_window_start = start
            self.window_start_entry.setText(str(start))
            self.time_window_slider.setValue(start)
            if self.is_loaded_mode:
                self._update_loaded_mode_plots()
        except ValueError:
            # 如果输入无效，恢复为当前值
            self.window_start_entry.setText(str(self.current_window_start))
    
    def _on_reset_view_clicked(self):
        """回到当前帧按钮点击时的回调"""
        if not self.is_loaded_mode:
            return
        
        # 重置所有plot tab的视图到当前帧窗口
        reset_count = 0
        for tab_key, plotter_info in self.plotters.items():
            if tab_key == 'breathing_estimation':
                continue  # 呼吸估计tab使用matplotlib，单独处理
            
            plotter = plotter_info.get('plotter')
            if plotter is None:
                continue
            
            if hasattr(plotter, 'reset_to_current_frame'):
                if plotter.reset_to_current_frame():
                    reset_count += 1
        
        # 恢复按钮颜色（因为已经重置，不再需要提示）
        self._update_reset_button_style()
        
        if reset_count > 0:
            self.logger.info(f"已重置 {reset_count} 个plot tab的视图到当前帧窗口")
            InfoBarHelper.information(
                self,
                title="视图已重置",
                content=f"已重置 {reset_count} 个绘图窗口到当前时间窗范围"
            )
    
    def _on_plot_view_changed(self):
        """当plot视图变化时的回调（立即检查并更新按钮颜色）"""
        # 延迟一小段时间再检查，避免频繁更新（因为视图变化可能连续触发多次）
        # 使用 QTimer.singleShot 来延迟执行
        if hasattr(self, '_view_changed_timer'):
            self._view_changed_timer.stop()
        
        from PySide6.QtCore import QTimer
        self._view_changed_timer = QTimer()
        self._view_changed_timer.setSingleShot(True)
        self._view_changed_timer.timeout.connect(self._check_and_update_reset_button)
        self._view_changed_timer.start(100)  # 100ms后检查，避免频繁更新
    
    def _check_and_update_reset_button(self):
        """检查是否有plotter被用户手动操作过，并更新按钮颜色"""
        if not self.is_loaded_mode:
            return
        
        # 检查是否有任何plotter被用户手动操作过
        has_panned = False
        for tab_key, plotter_info in self.plotters.items():
            if tab_key == 'breathing_estimation':
                continue
            
            plotter = plotter_info.get('plotter')
            if plotter is None:
                continue
            
            if hasattr(plotter, 'user_has_panned') and plotter.user_has_panned:
                has_panned = True
                break
        
        # 更新按钮样式
        if has_panned:
            # 使用醒目的颜色提示（橙色/黄色系）
            self.reset_view_btn.setStyleSheet(
                "background-color: #ff9800; color: white; font-weight: bold;"
            )
        else:
            # 恢复默认样式
            self.reset_view_btn.setStyleSheet(self.reset_view_btn_default_style)
    
    def _update_reset_button_style(self):
        """更新重置按钮的样式（检查所有plotter状态）"""
        self._check_and_update_reset_button()
    
    def _on_breathing_control_changed(self):
        """呼吸估计控制参数变化时的回调（单个参数变化时）"""
        # 移除自动更新，改为手动Update按钮控制
        pass
    
    def _on_update_all_breathing_params(self):
        """Update按钮：提交所有参数"""
        # 更新更新间隔
        try:
            interval = float(self.breathing_update_interval_entry.text())
            if interval > 0:
                self.breathing_update_interval = interval
                # 重启定时器
                if self.breathing_update_timer:
                    self.breathing_update_timer.stop()
                    self.breathing_update_timer.start(int(interval * 1000))
                self.logger.info(f"呼吸估计更新间隔设置为: {interval}秒")
            else:
                InfoBarHelper.warning(
                    self,
                    title="参数错误",
                    content="更新间隔必须大于0"
                )
                self.breathing_update_interval_entry.setText(str(self.breathing_update_interval))
                return
        except ValueError:
            InfoBarHelper.warning(
                self,
                title="参数错误",
                content="更新间隔必须是数字"
            )
            self.breathing_update_interval_entry.setText(str(self.breathing_update_interval))
            return
        
        # 获取当前参数信息
        data_type = self.breathing_data_type_combo.currentText()
        channel = self.breathing_channel_combo.currentText()
        threshold = self.breathing_threshold_entry.text()
        
        # 显示信息提示
        params_info = f"数据类型: {data_type}, 信道: {channel}, 阈值: {threshold}, 更新间隔: {interval}秒"
        InfoBarHelper.information(
            self,
            title="呼吸估计参数已更新",
            content=params_info
        )
        
        # 更新呼吸估计（根据当前模式）
        if self.is_loaded_mode:
            self._update_loaded_mode_plots()
        else:
            # 实时模式下立即更新
            self._update_realtime_breathing_estimation()
    
    def _start_realtime_breathing_estimation(self):
        """启动实时呼吸估计定时器"""
        self.breathing_update_timer = QTimer()
        self.breathing_update_timer.timeout.connect(self._update_realtime_breathing_estimation)
        self.breathing_update_timer.start(int(self.breathing_update_interval * 1000))
    
    def _update_realtime_breathing_estimation(self):
        """更新实时呼吸估计（使用最近X帧数据）"""
        if not self.frame_mode or not self.is_running:
            return
        
        # 检查是否有足够的数据
        all_channels = self.data_processor.get_all_frame_channels()
        if not all_channels:
            self.breathing_result_text.setPlainText("等待数据积累...")
            return
        
        # 获取选择的信道和数据类型
        try:
            channel = int(self.breathing_channel_combo.currentText())
        except:
            # 如果没有选择，使用第一个可用信道
            if all_channels:
                channel = all_channels[0]
                self.breathing_channel_combo.clear()
                self.breathing_channel_combo.addItems([str(ch) for ch in sorted(all_channels)])
                self.breathing_channel_combo.setCurrentText(str(channel))
            else:
                self.breathing_result_text.setPlainText("等待数据积累...")
                return
        
        data_type = self.breathing_data_type_combo.currentText()
        
        # 获取最近X帧的数据
        indices, values = self.data_processor.get_frame_data_range(
            channel, max_frames=self.display_max_frames, data_type=data_type
        )
        
        if len(values) < self.display_max_frames:
            # 数据还未积累到X帧
            self.breathing_result_text.setPlainText(
                f"数据积累中: {len(values)}/{self.display_max_frames} 帧\n"
                f"需要积累到 {self.display_max_frames} 帧后开始分析"
            )
            return
        
        if len(values) == 0:
            self.breathing_result_text.setPlainText("无数据")
            return
        
        # 进行呼吸估计
        signal = np.array(values)
        
        try:
            # 处理信号
            processed = self.breathing_estimator.process_signal(signal, data_type)
            
            if 'highpass_filtered' not in processed:
                self.breathing_result_text.setPlainText("信号处理失败")
                return
            
            # 获取阈值
            try:
                threshold = float(self.breathing_threshold_entry.text())
            except:
                threshold = 0.6
            
            # 检测呼吸
            detection = self.breathing_estimator.detect_breathing(
                processed['highpass_filtered'], threshold=threshold
            )
            
            # 更新结果显示
            result_text = f"Energy Ratio: {detection['energy_ratio']:.4f}\n"
            result_text += f"Threshold: {threshold:.2f}\n"
            result_text += f"Detection: {'Breathing Detected' if detection['has_breathing'] else 'No Breathing'}\n"
            
            if detection['has_breathing'] and not np.isnan(detection['breathing_freq']):
                breathing_rate = self.breathing_estimator.estimate_breathing_rate(detection['breathing_freq'])
                result_text += f"Breathing Freq: {detection['breathing_freq']:.4f} Hz\n"
                result_text += f"Breathing Rate: {breathing_rate:.1f} /min"
            else:
                result_text += "Breathing Freq: --\n"
                result_text += "Breathing Rate: --"
            
            self.breathing_result_text.setPlainText(result_text)
            
            # 同时更新呼吸估计tab的绘图（如果tab存在）
            # 构造window_frames格式的数据
            window_frames = []
            for i, (idx, val) in enumerate(zip(indices, values)):
                frame = {
                    'index': int(idx),
                    'channels': {
                        channel: {
                            data_type: float(val)
                        }
                    }
                }
                window_frames.append(frame)
            
            if window_frames:
                self._update_breathing_estimation_plot(window_frames)
                
        except Exception as e:
            self.logger.error(f"实时呼吸估计出错: {e}")
            self.breathing_result_text.setPlainText(f"分析出错: {str(e)}")
    
    def _update_loaded_mode_plots(self):
        """更新加载模式下的绘图"""
        if not self.is_loaded_mode or not self.loaded_frames:
            return
        
        # 获取当前时间窗的数据
        window_start = self.current_window_start
        window_size = self.display_max_frames
        window_end = min(window_start + window_size, len(self.loaded_frames))
        
        if window_start >= window_end:
            return
        
        # 提取时间窗内的帧
        window_frames = self.loaded_frames[window_start:window_end]
        
        # 更新所有绘图tab
        self._update_loaded_plots_for_tabs(window_frames)
        
        # 更新呼吸估计tab
        self._update_breathing_estimation_plot(window_frames)
        
        # 更新时间窗长度显示
        if len(window_frames) > 1:
            time_span = (window_frames[-1]['timestamp_ms'] - window_frames[0]['timestamp_ms']) / 1000.0
            self.window_length_label.setText(f"时间窗长度: {time_span:.2f} 秒")
        else:
            self.window_length_label.setText("时间窗长度: -- 秒")
    
    def _update_loaded_plots_for_tabs(self, window_frames: List[Dict]):
        """更新加载模式下各个tab的绘图
        
        现在会显示所有加载的数据，而不仅仅是窗口内的帧。
        窗口范围用于确定当前视图焦点，但所有数据都会被绘制。
        """
        # 使用所有加载的帧，而不仅仅是窗口内的帧
        all_frames = self.loaded_frames if self.loaded_frames else []
        
        if not all_frames:
            return
        
        # 提取所有通道的数据（从所有帧中）
        all_channels = set()
        for frame in all_frames:
            channels = frame.get('channels', {})
            for ch in channels.keys():
                try:
                    ch_int = int(ch) if isinstance(ch, (int, str)) and str(ch).isdigit() else ch
                    all_channels.add(ch_int)
                except:
                    all_channels.add(ch)
        
        if not all_channels:
            return
        
        # 根据设置的展示信道列表筛选
        display_channels = []
        for ch in self.display_channel_list:
            if ch in all_channels:
                display_channels.append(ch)
        
        if not display_channels:
            return
        
        # 计算当前窗口范围（用于视图定位）
        window_start = self.current_window_start
        window_size = self.display_max_frames
        window_end = min(window_start + window_size, len(all_frames))
        
        # 确保窗口范围有效
        if window_start >= len(all_frames) or window_end <= window_start:
            view_range = None
        else:
            window_start_index = all_frames[window_start].get('index', window_start)
            window_end_index = all_frames[window_end - 1].get('index', window_end - 1)
            # 确保索引顺序正确
            if window_start_index > window_end_index:
                window_start_index, window_end_index = window_end_index, window_start_index
            view_range = (window_start_index, window_end_index)
        
        # 更新每个绘图tab
        tab_configs = [
            ('amplitude', 'amplitude'),
            ('phase', 'phase'),
            ('local_amplitude', 'local_amplitude'),
            ('local_phase', 'local_phase'),
            ('remote_amplitude', 'remote_amplitude'),
            ('remote_phase', 'remote_phase'),
        ]
        
        for tab_key, data_type in tab_configs:
            if tab_key not in self.plotters:
                continue
            
            plotter_info = self.plotters[tab_key]
            plotter = plotter_info.get('plotter')
            if plotter is None:
                continue
            
            # 准备该数据类型的所有通道数据（使用所有帧）
            channel_data = {}
            for ch in display_channels:
                indices = []
                values = []
                for frame in all_frames:
                    channels = frame.get('channels', {})
                    ch_data = None
                    if ch in channels:
                        ch_data = channels[ch]
                    elif str(ch) in channels:
                        ch_data = channels[str(ch)]
                    
                    if ch_data:
                        indices.append(frame.get('index', 0))
                        values.append(ch_data.get(data_type, 0.0))
                
                if len(indices) > 0 and len(values) > 0:
                    channel_data[ch] = (np.array(indices), np.array(values))
            
            # 更新绘图（传入窗口范围用于视图定位）
            if channel_data:
                plotter.update_frame_data(
                    channel_data, 
                    max_channels=len(display_channels),
                    view_range=view_range
                )
        
        # 注意：按钮颜色更新现在由视图变化信号自动触发（_on_plot_view_changed）
        # 这里不再需要手动检查，因为视图变化时会立即触发更新
    
    def _update_breathing_estimation_plot(self, window_frames: List[Dict]):
        """更新呼吸估计tab的绘图"""
        if 'breathing_estimation' not in self.plotters:
            return
        
        plot_info = self.plotters['breathing_estimation']
        axes = plot_info['axes']
        
        # 获取选择的信道和数据类型
        try:
            channel = int(self.breathing_channel_combo.currentText())
        except:
            channel = 0
        
        data_type = self.breathing_data_type_combo.currentText()
        
        # 提取该信道的数据
        signal_data = []
        indices = []
        for i, frame in enumerate(window_frames):
            channels = frame.get('channels', {})
            ch_data = None
            if channel in channels:
                ch_data = channels[channel]
            elif str(channel) in channels:
                ch_data = channels[str(channel)]
            
            if ch_data:
                signal_data.append(ch_data.get(data_type, 0.0))
                indices.append(frame.get('index', self.current_window_start + i))
        
        if len(signal_data) == 0:
            self.logger.warning(f"呼吸估计: 信道 {channel} 在时间窗内没有数据")
            return
        
        signal = np.array(signal_data)
        indices = np.array(indices)
        
        # 左上角：原始数据
        ax1 = axes['top_left']
        ax1.clear()
        ax1.plot(indices, signal, 'b-', linewidth=1.0, alpha=0.8)
        ax1.set_title('Raw Data', fontsize=10)
        ax1.set_xlabel('Frame Index')
        ax1.set_ylabel('Amplitude' if 'amplitude' in data_type else 'Phase')
        ax1.grid(True, alpha=0.3)
        
        # 右上角：中值滤波+高通滤波
        ax2 = axes['top_right']
        ax2.clear()
        processed = self.breathing_estimator.process_signal(signal, data_type)
        if 'highpass_filtered' in processed:
            ax2.plot(indices, processed['highpass_filtered'], 'r-', linewidth=1.0, alpha=0.8)
        ax2.set_title('Median + Highpass Filter', fontsize=10)
        ax2.set_xlabel('Frame Index')
        ax2.set_ylabel('Amplitude' if 'amplitude' in data_type else 'Phase')
        ax2.grid(True, alpha=0.3)
        
        # 左下角：FFT频谱（带通前后对比）
        ax3 = axes['bottom_left']
        ax3.clear()
        if 'highpass_filtered' in processed:
            analysis = self.breathing_estimator.analyze_window(processed['highpass_filtered'], apply_hanning=True)
            if 'fft_freq_before' in analysis and 'fft_power_before' in analysis:
                freq_mask = analysis['fft_freq_before'] <= 1.0
                ax3.plot(analysis['fft_freq_before'][freq_mask], analysis['fft_power_before'][freq_mask], 
                        'b-', linewidth=1.5, alpha=0.7, label='Before Bandpass')
            if 'fft_freq_after' in analysis and 'fft_power_after' in analysis:
                freq_mask = analysis['fft_freq_after'] <= 1.0
                ax3.plot(analysis['fft_freq_after'][freq_mask], analysis['fft_power_after'][freq_mask], 
                        'r-', linewidth=1.5, alpha=0.7, label='After Bandpass')
            ax3.axvspan(self.breathing_estimator.bandpass_lowcut, 
                       self.breathing_estimator.bandpass_highcut, 
                       alpha=0.2, color='yellow', label='Passband Range')
        ax3.set_title('FFT Spectrum: Before vs After Bandpass', fontsize=10)
        ax3.set_xlabel('Frequency (Hz)')
        ax3.set_ylabel('Power')
        ax3.set_xlim(0, 1.0)
        ax3.grid(True, alpha=0.3)
        ax3.legend(fontsize=8)
        
        # 右下角：呼吸检测结果
        ax4 = axes['bottom_right']
        ax4.clear()
        ax4.axis('off')
        ax4.set_title('Breathing Detection Result', fontsize=10, pad=20)
        
        if 'highpass_filtered' in processed:
            try:
                threshold = float(self.breathing_threshold_entry.text())
            except:
                threshold = 0.6
            detection = self.breathing_estimator.detect_breathing(processed['highpass_filtered'], threshold=threshold)
            
            # 判断是否检测到呼吸，决定背景颜色
            has_breathing = detection['has_breathing']
            bg_color = '#90EE90' if has_breathing else 'wheat'  # 浅绿色或棕色
            
            # 基础信息文本
            base_text = f"Energy Ratio: {detection['energy_ratio']:.4f}\n"
            base_text += f"Threshold: {threshold:.2f}\n"
            base_text += f"Detection: {'Breathing Detected' if has_breathing else 'No Breathing'}\n"
            
            if has_breathing and not np.isnan(detection['breathing_freq']):
                breathing_rate = self.breathing_estimator.estimate_breathing_rate(detection['breathing_freq'])
                
                # 使用多个text调用来实现不同格式
                # 绘制背景框
                from matplotlib.patches import FancyBboxPatch
                bbox = FancyBboxPatch((0.05, 0.05), 0.9, 0.9, 
                                     boxstyle='round,pad=0.02',
                                     facecolor=bg_color, alpha=0.5,
                                     transform=ax4.transAxes)
                ax4.add_patch(bbox)
                
                # 绘制文本（分多行）
                y_positions = [0.75, 0.6, 0.45, 0.3, 0.15]
                ax4.text(0.5, y_positions[0], f"Energy Ratio: {detection['energy_ratio']:.4f}", 
                        ha='center', va='center', fontsize=10, family='monospace',
                        transform=ax4.transAxes)
                ax4.text(0.5, y_positions[1], f"Threshold: {threshold:.2f}", 
                        ha='center', va='center', fontsize=10, family='monospace',
                        transform=ax4.transAxes)
                ax4.text(0.5, y_positions[2], f"Detection: {'Breathing Detected' if has_breathing else 'No Breathing'}", 
                        ha='center', va='center', fontsize=10, family='monospace',
                        transform=ax4.transAxes)
                ax4.text(0.5, y_positions[3], f"Breathing Freq: {detection['breathing_freq']:.4f} Hz", 
                        ha='center', va='center', fontsize=10, family='monospace',
                        transform=ax4.transAxes)
                # 呼吸次数用大字体和深绿色显示
                ax4.text(0.5, y_positions[4], f"Breathing Rate: {breathing_rate:.1f} /min", 
                        ha='center', va='center', fontsize=20, family='monospace',
                        color='#006400', weight='bold',  # 深绿色，加粗，大字体
                        transform=ax4.transAxes)
            else:
                base_text += "Breathing Freq: --\n"
                base_text += "Breathing Rate: --"
                
                ax4.text(0.5, 0.5, base_text, ha='center', va='center', 
                        fontsize=11, family='monospace',
                        bbox=dict(boxstyle='round', facecolor=bg_color, alpha=0.5),
                        transform=ax4.transAxes)
        
        # 刷新画布
        plot_info['canvas'].draw_idle()
    
    def showEvent(self, event):
        """窗口显示事件 - 确保主题正确应用"""
        super().showEvent(event)
        # 窗口显示后，根据当前选中的单选按钮强制应用一次主题
        # 这样可以确保界面主题与选项一致
        if hasattr(self, 'theme_light_radio') and self.theme_light_radio.isChecked():
            self._apply_theme("light")
        elif hasattr(self, 'theme_dark_radio') and self.theme_dark_radio.isChecked():
            self._apply_theme("dark")
        elif hasattr(self, 'theme_auto_radio') and self.theme_auto_radio.isChecked():
            self._apply_theme("auto")
        else:
            # 如果单选按钮还没创建，使用默认主题
            self._apply_theme(self.current_theme_mode)
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止所有定时器
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        if hasattr(self, 'breathing_update_timer') and self.breathing_update_timer:
            self.breathing_update_timer.stop()
        if hasattr(self, 'freq_update_timer') and self.freq_update_timer:
            self.freq_update_timer.stop()
        
        if self.is_running:
            if self.serial_reader:
                self.serial_reader.disconnect()
        event.accept()


class TextHandler(logging.Handler):
    """自定义日志处理器，输出到QTextEdit"""
    
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
    
    def emit(self, record):
        msg = self.format(record)
        self.text_widget.append(msg)  # QTextEdit 的 append 方法


def main():
    """主函数"""
    # 创建应用程序
    app = QApplication(sys.argv)
    
    # 设置全局字体为微软雅黑
    font = QFont("Microsoft YaHei", 10)  # 默认10号字体
    app.setFont(font)
    
    # 设置应用程序图标
    try:
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(__file__))
        
        icon_path = os.path.join(base_path, 'assets', 'ico.png')
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
    except Exception as e:
        logging.getLogger(__name__).warning(f"无法设置图标: {e}")
    
    # 创建主窗口
    window = BLEHostGUI()
    window.show()
    
    # 运行应用程序
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
