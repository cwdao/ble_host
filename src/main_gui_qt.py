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
    QFileDialog, QButtonGroup, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import QFont, QIcon

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
        self.display_channel_list = list(range(10))
        self.display_max_frames = config.default_display_max_frames
        
        # 加载模式相关
        self.is_loaded_mode = False
        self.loaded_frames = []
        self.loaded_file_info = None
        self.current_window_start = 0
        self.breathing_estimator = BreathingEstimator()
        
        # 创建界面
        self._create_widgets()
        
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
        
        # 数据处理区域
        self._create_process_panel(right_layout)
        
        # 日志区域
        self._create_log_panel(right_layout)
        
        # 版本信息
        self._create_version_info(right_layout)
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(1, 1)  # 右侧占 1/3
        
        main_layout.addWidget(splitter, stretch=1)
    
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
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # TODO: 实现通道配置界面
        layout.addWidget(QLabel("通道配置（待实现）"))
        
        self.config_tabs.addTab(tab, "通道配置")
    
    def _create_data_and_save_tab(self):
        """创建数据和保存选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # TODO: 实现数据保存界面
        layout.addWidget(QLabel("数据保存（待实现）"))
        
        self.config_tabs.addTab(tab, "数据保存")
    
    def _create_load_tab(self):
        """创建加载选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # TODO: 实现文件加载界面
        layout.addWidget(QLabel("文件加载（待实现）"))
        
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
        
        # TODO: 创建呼吸估计选项卡（使用 Matplotlib）
        # self._create_breathing_estimation_tab()
    
    def _create_process_panel(self, parent_layout):
        """创建数据处理面板"""
        group = QGroupBox("数据处理")
        layout = QVBoxLayout(group)
        
        # TODO: 实现数据处理界面
        layout.addWidget(QLabel("数据处理（待实现）"))
        
        parent_layout.addWidget(group)
    
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
            # 解析数据
            parsed = self.data_parser.parse(data['text'])
            if parsed:
                # TODO: 处理数据并更新绘图
                self.logger.debug(f"收到数据: {parsed}")
    
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
