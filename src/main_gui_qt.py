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

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit, QCheckBox,
    QRadioButton, QSlider, QTabWidget, QSplitter, QGroupBox, QMessageBox,
    QFileDialog, QButtonGroup, QFrame, QMenuBar, QMenu, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import QFont, QIcon, QAction, QActionGroup

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

# 版本信息
__version__ = config.version
__version_date__ = config.version_date
__version_author__ = config.version_author


class BLEHostGUI(QMainWindow):
    """主GUI应用程序 - PySide6 版本"""
    
    def __init__(self):
        super().__init__()
        
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
        
        # 创建界面
        self._create_widgets()
        
        # 应用默认设置（初始化显示信道）
        if self.frame_mode:
            # 先设置默认值
            self.display_channels_entry.setText(config.default_display_channels)
            self._apply_frame_settings()
        
        # 定时刷新（使用 QTimer 替代 threading）
        self._start_update_loop()
    
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
        
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        
        main_layout.addWidget(status_frame)
        
        # 2. 配置选项卡区域
        self.config_tabs = QTabWidget()
        self._create_connection_tab()
        self._create_channel_config_tab()
        self._create_data_and_save_tab()
        self._create_load_tab()
        
        main_layout.addWidget(self.config_tabs)
        
        # 3. 滑动条容器（加载模式下显示）
        self.slider_frame = QFrame()
        self.slider_frame.setVisible(False)  # 初始隐藏
        slider_layout = QHBoxLayout(self.slider_frame)
        slider_layout.setContentsMargins(5, 5, 5, 5)
        
        slider_layout.addWidget(QLabel("时间窗起点:"))
        self.window_start_entry = QLineEdit("0")
        self.window_start_entry.setMaximumWidth(80)
        self.window_start_entry.returnPressed.connect(self._on_window_start_changed)
        slider_layout.addWidget(self.window_start_entry)
        slider_layout.addWidget(QLabel("(帧)"))
        
        # 左箭头按钮
        self.slider_left_btn = QPushButton("◄")
        self.slider_left_btn.setMaximumWidth(40)
        self.slider_left_btn.clicked.connect(self._on_slider_left_click)
        slider_layout.addWidget(self.slider_left_btn)
        
        # 滑动条
        self.time_window_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_window_slider.setMinimum(0)
        self.time_window_slider.setMaximum(100)
        self.time_window_slider.valueChanged.connect(self._on_slider_value_changed)
        self.time_window_slider.sliderReleased.connect(self._on_slider_released)
        slider_layout.addWidget(self.time_window_slider)
        
        # 右箭头按钮
        self.slider_right_btn = QPushButton("►")
        self.slider_right_btn.setMaximumWidth(40)
        self.slider_right_btn.clicked.connect(self._on_slider_right_click)
        slider_layout.addWidget(self.slider_right_btn)
        
        # 时间窗长度显示
        self.window_length_label = QLabel("时间窗长度: -- 秒")
        slider_layout.addWidget(self.window_length_label)
        slider_layout.addStretch()
        
        main_layout.addWidget(self.slider_frame)
        
        # 3. 左右分栏（绘图区域 + 右侧面板）
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：绘图区域
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 绘图选项卡
        self.plot_tabs = QTabWidget()
        self._create_plot_tabs()
        left_layout.addWidget(self.plot_tabs)
        
        splitter.addWidget(left_widget)
        splitter.setStretchFactor(0, 2)  # 左侧占 2/3
        
        # 右侧：信息面板
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        # 呼吸估计控制区域（加载模式下显示）
        self.breathing_control_group = QGroupBox("Breathing Estimation Control")
        self.breathing_control_group.setVisible(False)  # 初始隐藏
        breathing_control_layout = QVBoxLayout(self.breathing_control_group)
        
        # 数据类型选择
        data_type_layout = QHBoxLayout()
        data_type_layout.addWidget(QLabel("Data Type:"))
        self.breathing_data_type_combo = QComboBox()
        self.breathing_data_type_combo.addItems(["amplitude", "local_amplitude", "remote_amplitude", "phase", "local_phase", "remote_phase"])
        self.breathing_data_type_combo.currentTextChanged.connect(self._on_breathing_control_changed)
        data_type_layout.addWidget(self.breathing_data_type_combo)
        breathing_control_layout.addLayout(data_type_layout)
        
        # 信道选择
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Channel:"))
        self.breathing_channel_combo = QComboBox()
        self.breathing_channel_combo.currentTextChanged.connect(self._on_breathing_control_changed)
        channel_layout.addWidget(self.breathing_channel_combo)
        breathing_control_layout.addLayout(channel_layout)
        
        # 阈值输入
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Threshold:"))
        self.breathing_threshold_entry = QLineEdit("0.6")
        self.breathing_threshold_entry.setMaximumWidth(80)
        self.breathing_threshold_entry.returnPressed.connect(self._on_breathing_control_changed)
        threshold_layout.addWidget(self.breathing_threshold_entry)
        update_btn = QPushButton("Update")
        update_btn.clicked.connect(self._on_breathing_control_changed)
        threshold_layout.addWidget(update_btn)
        breathing_control_layout.addLayout(threshold_layout)
        
        right_layout.addWidget(self.breathing_control_group)
        
        # 数据处理区域
        self.process_group = QGroupBox("数据处理")
        process_layout = QVBoxLayout(self.process_group)
        self._create_process_panel(process_layout)
        right_layout.addWidget(self.process_group)
        
        # 日志区域
        self._create_log_panel(right_layout)
        
        # 版本信息
        self._create_version_info(right_layout)
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(1, 1)  # 右侧占 1/3
        
        main_layout.addWidget(splitter, stretch=1)
    
    def _create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 设置菜单
        settings_menu = menubar.addMenu("设置")
        
        # 主题模式
        theme_menu = settings_menu.addMenu("主题模式")
        self.theme_light_action = QAction("浅色模式", self)
        self.theme_light_action.setCheckable(True)
        self.theme_light_action.triggered.connect(lambda: self._set_theme("light"))
        theme_menu.addAction(self.theme_light_action)
        
        self.theme_dark_action = QAction("深色模式", self)
        self.theme_dark_action.setCheckable(True)
        self.theme_dark_action.triggered.connect(lambda: self._set_theme("dark"))
        theme_menu.addAction(self.theme_dark_action)
        
        self.theme_auto_action = QAction("跟随系统", self)
        self.theme_auto_action.setCheckable(True)
        self.theme_auto_action.setChecked(True)  # 默认跟随系统
        self.theme_auto_action.triggered.connect(lambda: self._set_theme("auto"))
        theme_menu.addAction(self.theme_auto_action)
        
        # 创建动作组，确保只能选择一个
        theme_group = QActionGroup(self)
        theme_group.addAction(self.theme_light_action)
        theme_group.addAction(self.theme_dark_action)
        theme_group.addAction(self.theme_auto_action)
        theme_group.setExclusive(True)
        
        settings_menu.addSeparator()
        
        # About
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        settings_menu.addAction(about_action)
    
    def _set_theme(self, theme: str):
        """设置主题"""
        if theme == "light":
            self.setStyleSheet("")
            # 可以添加浅色主题的样式
        elif theme == "dark":
            # 深色主题样式
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QWidget {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QGroupBox {
                    border: 1px solid #555555;
                    border-radius: 3px;
                    margin-top: 10px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #4c4c4c;
                }
                QPushButton:pressed {
                    background-color: #2c2c2c;
                }
                QLineEdit, QTextEdit, QComboBox {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 3px;
                    color: #ffffff;
                }
                QTabWidget::pane {
                    border: 1px solid #555555;
                    background-color: #2b2b2b;
                }
                QTabBar::tab {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    padding: 5px 10px;
                    border: 1px solid #555555;
                }
                QTabBar::tab:selected {
                    background-color: #4c4c4c;
                }
            """)
        else:  # auto
            self.setStyleSheet("")  # 使用系统默认主题
    
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
        self.apply_settings_btn.clicked.connect(self._apply_frame_settings)
        layout.addWidget(self.apply_settings_btn)
        
        layout.addStretch()
        
        self.config_tabs.addTab(tab, "通道配置")
    
    def _create_data_and_save_tab(self):
        """创建数据和保存选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 第一行：设置保存路径、自动保存路径复选框、当前路径显示
        row1 = QHBoxLayout()
        set_path_btn = QPushButton("设置保存路径...")
        set_path_btn.clicked.connect(self._set_save_path)
        row1.addWidget(set_path_btn)
        
        self.auto_save_check = QCheckBox("使用自动保存路径")
        self.auto_save_check.setChecked(self.use_auto_save)
        self.auto_save_check.toggled.connect(self._toggle_auto_save)
        row1.addWidget(self.auto_save_check)
        
        # 显示当前保存路径
        current_path = user_settings.get_save_directory()
        display_path = current_path if len(current_path) <= 50 else "..." + current_path[-47:]
        self.path_label = QLabel(f"当前路径: {display_path}")
        self.path_label.setStyleSheet("color: gray;")
        row1.addWidget(self.path_label)
        row1.addStretch()
        layout.addLayout(row1)
        
        # 第二行：保存数据按钮、保存选项、清空数据按钮
        row2 = QHBoxLayout()
        self.save_btn = QPushButton("保存数据")
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.save_btn.clicked.connect(self._save_data)
        row2.addWidget(self.save_btn)
        
        # 保存选项（全部保存或最近N帧）
        self.save_option_group = QButtonGroup()
        self.save_all_radio = QRadioButton("全部保存")
        self.save_all_radio.setChecked(True)
        self.save_recent_radio = QRadioButton("最近N帧")
        self.save_option_group.addButton(self.save_all_radio, 0)
        self.save_option_group.addButton(self.save_recent_radio, 1)
        row2.addWidget(self.save_all_radio)
        row2.addWidget(self.save_recent_radio)
        
        self.clear_data_btn = QPushButton("清空当前数据")
        self.clear_data_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.clear_data_btn.clicked.connect(self._clear_data)
        row2.addWidget(self.clear_data_btn)
        row2.addStretch()
        layout.addLayout(row2)
        
        # 第三行：保存状态显示
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("保存状态:"))
        self.save_status_label = QLabel("")
        row3.addWidget(self.save_status_label)
        row3.addStretch()
        layout.addLayout(row3)
        
        layout.addStretch()
        
        self.config_tabs.addTab(tab, "数据保存")
    
    def _create_load_tab(self):
        """创建加载选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 文件路径选择
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("文件路径:"))
        self.load_file_entry = QLineEdit()
        self.load_file_entry.setMaximumWidth(300)  # 缩减一半宽度
        path_layout.addWidget(self.load_file_entry)
        
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_load_file)
        path_layout.addWidget(browse_btn)
        
        load_btn = QPushButton("加载文件")
        load_btn.clicked.connect(self._load_file)
        path_layout.addWidget(load_btn)
        
        self.unload_btn = QPushButton("取消加载")
        self.unload_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.unload_btn.clicked.connect(self._unload_file)
        self.unload_btn.setVisible(False)  # 初始隐藏
        path_layout.addWidget(self.unload_btn)
        
        path_layout.addStretch()
        layout.addLayout(path_layout)
        
        # 文件信息显示
        info_group = QGroupBox("文件信息")
        info_layout = QVBoxLayout(info_group)
        self.load_file_info_text = QTextEdit()
        self.load_file_info_text.setReadOnly(True)
        self.load_file_info_text.setFont(QFont("Consolas", 9))
        self.load_file_info_text.setMaximumHeight(100)  # 缩减高度
        self.load_file_info_text.setMaximumWidth(400)  # 缩减宽度
        info_layout.addWidget(self.load_file_info_text)
        layout.addWidget(info_group)
        
        layout.addStretch()
        
        self.config_tabs.addTab(tab, "文件加载")
    
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
        for port_info in ports:
            self.port_combo.addItem(f"{port_info['port']} - {port_info['description']}", port_info['port'])
    
    def _toggle_connection(self):
        """切换连接状态"""
        if not self.is_running:
            # 连接
            port_data = self.port_combo.currentData()
            if not port_data:
                QMessageBox.warning(self, "警告", "请选择串口")
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
            else:
                QMessageBox.critical(self, "错误", "串口连接失败")
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
        """更新数据（在主线程中调用）"""
        if not self.is_running or not self.serial_reader:
            return
        
        # 获取串口数据
        data = self.serial_reader.get_data(block=False)
        if data:
            # 如果是帧模式，优先处理帧数据
            if self.frame_mode:
                # 解析数据（会更新内部状态，累积IQ数据）
                parsed = self.data_parser.parse(data['text'])
                
                # 如果parse返回了完成的帧（检测到帧尾时完成）
                if parsed and parsed.get('frame'):
                    frame_data = parsed
                    if len(frame_data.get('channels', {})) > 0:
                        # 打印帧详细信息
                        channels = sorted(frame_data['channels'].keys())
                        self.logger.info(
                            f"[帧完成] index={frame_data['index']}, "
                            f"timestamp={frame_data['timestamp_ms']}ms, "
                            f"通道数={len(channels)}, "
                            f"通道范围={channels[0]}-{channels[-1] if channels else 'N/A'}"
                        )
                        
                        self.data_processor.add_frame_data(frame_data)
                        self._update_frame_plots()
                        # 使用节流刷新，避免频繁刷新导致GUI卡顿
                        self._refresh_plotters_throttled()
                
                # 帧模式下不处理其他数据
                return
            
            # 非帧模式：解析简单数据
            parsed = self.data_parser.parse(data['text'])
            
            # 处理简单数据（向后兼容）
            if parsed and not parsed.get('frame'):
                self.data_processor.add_data(data['timestamp'], parsed)
                
                # 更新绘图 - 使用第一个绘图器
                if 'amplitude' in self.plotters:
                    plotter = self.plotters['amplitude']['plotter']
                    for var_name, value in parsed.items():
                        times, values = self.data_processor.get_data_range(
                            var_name, duration=config.default_frequency_duration
                        )
                        if len(times) > 0:
                            plotter.update_plot(var_name, times, values)
                    
                    # 更新变量列表（非帧模式）
                    vars_list = self.data_processor.get_all_variables()
                    self.freq_var_combo.clear()
                    self.freq_var_combo.addItems(vars_list)
                    if vars_list and self.freq_var_combo.currentIndex() < 0:
                        self.freq_var_combo.setCurrentIndex(0)
                    
                    # 使用节流刷新，避免频繁刷新导致GUI卡顿
                    self._refresh_plotters_throttled()
        
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
    
    def _apply_frame_settings(self):
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
            self._update_frame_plots()
    
    def _set_save_path(self):
        """设置保存路径"""
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录", user_settings.get_save_directory())
        if directory:
            user_settings.set_save_directory(directory)
            display_path = directory if len(directory) <= 50 else "..." + directory[-47:]
            self.path_label.setText(f"当前路径: {display_path}")
            self.logger.info(f"保存路径已设置为: {directory}")
    
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
            QMessageBox.warning(self, "警告", "当前不是帧模式，无法保存帧数据")
            return
        
        if self.is_saving:
            QMessageBox.warning(self, "警告", "保存操作正在进行中，请稍候...")
            return
        
        frames = self.data_processor.raw_frames
        if not frames:
            QMessageBox.warning(self, "警告", "没有可保存的帧数据")
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
                self.save_status_label.setText(f"正在保存 {len(frames)} 帧数据...")
                self.save_status_label.setStyleSheet("color: black;")
                
                success = self.data_saver.save_frames(frames, filepath, max_frames=None)
                
                if success:
                    self.save_status_label.setText(f"✓ 已保存 {len(frames)} 帧数据到: {filepath}")
                    self.save_status_label.setStyleSheet("color: green;")
                else:
                    self.save_status_label.setText("✗ 保存失败，请查看日志")
                    self.save_status_label.setStyleSheet("color: red;")
            except Exception as e:
                self.logger.error(f"保存数据时出错: {e}")
                self.save_status_label.setText(f"✗ 保存失败: {str(e)}")
                self.save_status_label.setStyleSheet("color: red;")
            finally:
                self.is_saving = False
        
        import threading
        save_thread = threading.Thread(target=save_in_thread, daemon=True)
        save_thread.start()
    
    def _save_recent_frames(self):
        """保存最近N帧数据"""
        if not self.frame_mode:
            QMessageBox.warning(self, "警告", "当前不是帧模式，无法保存帧数据")
            return
        
        if self.is_saving:
            QMessageBox.warning(self, "警告", "保存操作正在进行中，请稍候...")
            return
        
        frames = self.data_processor.raw_frames
        if not frames:
            QMessageBox.warning(self, "警告", "没有可保存的帧数据")
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
                self.save_status_label.setText(f"正在保存最近 {saved_count} 帧数据...")
                self.save_status_label.setStyleSheet("color: black;")
                
                success = self.data_saver.save_frames(frames, filepath, max_frames=max_frames)
                
                if success:
                    self.save_status_label.setText(f"✓ 已保存最近 {saved_count} 帧数据到: {filepath}")
                    self.save_status_label.setStyleSheet("color: green;")
                else:
                    self.save_status_label.setText("✗ 保存失败，请查看日志")
                    self.save_status_label.setStyleSheet("color: red;")
            except Exception as e:
                self.logger.error(f"保存数据时出错: {e}")
                self.save_status_label.setText(f"✗ 保存失败: {str(e)}")
                self.save_status_label.setStyleSheet("color: red;")
            finally:
                self.is_saving = False
        
        import threading
        save_thread = threading.Thread(target=save_in_thread, daemon=True)
        save_thread.start()
    
    def _clear_data(self):
        """清空数据"""
        self.data_processor.clear_buffer(clear_frames=True)
        # 清空所有绘图器
        for plotter_info in self.plotters.values():
            plotter = plotter_info.get('plotter')
            if plotter is None:
                continue
            plotter.clear_plot()
        self.data_parser.clear_buffer()
        self.logger.info("数据已清空")
    
    def _browse_load_file(self):
        """浏览加载文件"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择要加载的文件", "",
            "JSON文件 (*.json);;所有文件 (*.*)"
        )
        if filepath:
            self.load_file_entry.setText(filepath)
    
    def _load_file(self):
        """加载文件"""
        filepath = self.load_file_entry.text().strip()
        if not filepath:
            QMessageBox.warning(self, "警告", "请选择要加载的文件")
            return
        
        try:
            data = self.data_saver.load_frames(filepath)
            if not data:
                QMessageBox.critical(self, "错误", "文件加载失败")
                return
            
            self.loaded_frames = data.get('frames', [])
            self.loaded_file_info = data
            self.is_loaded_mode = True
            self.current_window_start = 0
            
            # 更新文件信息显示（完整信息）
            self._update_load_file_info()
            
            # 显示滑动条并更新范围
            self.slider_frame.setVisible(True)
            max_start = max(0, len(self.loaded_frames) - self.display_max_frames)
            self.time_window_slider.setMaximum(max_start)
            self.time_window_slider.setValue(0)
            self.window_start_entry.setText("0")
            
            # 禁用连接tab的功能
            self._set_connection_tab_enabled(False)
            
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
            
            # 显示呼吸估计控制面板，隐藏数据处理面板
            self.breathing_control_group.setVisible(True)
            self.process_group.setVisible(False)
            
            # 显示取消加载按钮
            self.unload_btn.setVisible(True)
            
            # 加载数据到处理器
            self.data_processor.clear_buffer(clear_frames=True)
            for frame in self.loaded_frames:
                self.data_processor.add_frame_data(frame)
            
            # 更新加载模式的绘图
            self._update_loaded_mode_plots()
            
            self.logger.info(f"文件加载成功: {filepath}, 共 {len(self.loaded_frames)} 帧")
            QMessageBox.information(self, "成功", f"文件加载成功，共 {len(self.loaded_frames)} 帧")
        except Exception as e:
            self.logger.error(f"加载文件时出错: {e}")
            QMessageBox.critical(self, "错误", f"加载文件失败: {str(e)}")
    
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
        
        self.load_file_info_text.setPlainText("\n".join(info_lines))
    
    def _unload_file(self):
        """取消加载文件"""
        self.is_loaded_mode = False
        self.loaded_frames = []
        self.loaded_file_info = None
        self.current_window_start = 0
        
        # 隐藏滑动条
        self.slider_frame.setVisible(False)
        
        # 启用连接tab的功能
        self._set_connection_tab_enabled(True)
        
        # 隐藏呼吸估计控制面板，显示数据处理面板
        self.breathing_control_group.setVisible(False)
        self.process_group.setVisible(True)
        
        # 隐藏取消加载按钮
        self.unload_btn.setVisible(False)
        
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
        QMessageBox.information(self, "提示", "已取消文件加载")
    
    def _set_connection_tab_enabled(self, enabled: bool):
        """启用或禁用连接tab的功能"""
        state = Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked
        self.port_combo.setEnabled(enabled)
        self.connect_btn.setEnabled(enabled)
        self.frame_type_combo.setEnabled(enabled)
        if hasattr(self, 'baudrate_combo'):
            self.baudrate_combo.setEnabled(enabled)
    
    def _calculate_frequency(self):
        """计算频率"""
        var_name = self.freq_var_combo.currentText()
        if not var_name:
            QMessageBox.warning(self, "警告", "请选择要计算的变量")
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
                    QMessageBox.warning(self, "警告", "帧模式下请选择通道（ch0, ch1, ...）")
            else:
                # 非帧模式：计算变量频率
                freq = self.data_processor.calculate_frequency(var_name, duration=config.default_frequency_duration)
                if freq:
                    self.freq_result_label.setText(f"{var_name} 频率: {freq:.4f} Hz")
                else:
                    self.freq_result_label.setText(f"{var_name} 频率计算失败（数据不足）")
        except Exception as e:
            self.logger.error(f"计算频率时出错: {e}")
            QMessageBox.critical(self, "错误", f"计算频率失败: {str(e)}")
    
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
    
    def _on_slider_value_changed(self, value):
        """滑动条值变化时的回调（拖动时只更新输入框，不绘图）"""
        self.window_start_entry.setText(str(value))
    
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
    
    def _on_breathing_control_changed(self):
        """呼吸估计控制参数变化时的回调"""
        if self.is_loaded_mode:
            self._update_loaded_mode_plots()
    
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
        """更新加载模式下各个tab的绘图"""
        # 提取所有通道的数据
        all_channels = set()
        for frame in window_frames:
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
            
            # 准备该数据类型的所有通道数据
            channel_data = {}
            for ch in display_channels:
                indices = []
                values = []
                for i, frame in enumerate(window_frames):
                    channels = frame.get('channels', {})
                    ch_data = None
                    if ch in channels:
                        ch_data = channels[ch]
                    elif str(ch) in channels:
                        ch_data = channels[str(ch)]
                    
                    if ch_data:
                        indices.append(frame.get('index', self.current_window_start + i))
                        values.append(ch_data.get(data_type, 0.0))
                
                if len(indices) > 0 and len(values) > 0:
                    channel_data[ch] = (np.array(indices), np.array(values))
            
            # 更新绘图
            if channel_data:
                plotter.update_frame_data(channel_data, max_channels=len(display_channels))
    
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
            
            ax4.text(0.5, 0.5, result_text, ha='center', va='center', 
                    fontsize=11, family='monospace',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        # 刷新画布
        plot_info['canvas'].draw_idle()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
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
