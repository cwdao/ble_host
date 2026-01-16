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
from typing import List, Optional, Dict, Tuple
from datetime import datetime
import platform

# 在导入 Qt 之前设置 DPI 感知（Windows）
# 这必须在创建 QApplication 之前完成，以避免 Qt 的 DPI 感知警告
# 注意：如果设置失败（如权限问题），Qt 6 默认已经处理了 DPI 感知，所以可以安全忽略错误
if platform.system() == 'Windows':
    try:
        from ctypes import windll
        # 尝试设置 DPI 感知上下文（Windows 10 1703+）
        # 使用 PER_MONITOR_AWARE_V2，这是 Qt 6 默认使用的
        try:
            # 首先尝试使用 SetProcessDpiAwarenessContext（Windows 10 1703+）
            # -4 = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            result = windll.user32.SetProcessDpiAwarenessContext(-4)
            # 如果返回 False，说明设置失败（可能是权限问题或已设置）
            if not result:
                pass  # 忽略失败，Qt 会使用默认设置
        except (AttributeError, OSError) as e:
            # 如果失败（可能是权限问题），尝试使用 SetProcessDpiAwareness（Windows 8.1+）
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
            # 忽略所有其他错误（包括权限错误），让 Qt 使用默认设置
            pass
    except Exception:
        pass  # 忽略所有错误，让 Qt 使用默认设置

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit, QCheckBox,
    QRadioButton, QSlider, QTabWidget, QSplitter, QGroupBox, QMessageBox,
    QFileDialog, QButtonGroup, QFrame, QMenuBar, QMenu, QDialog, QDialogButtonBox,
    QSizePolicy, QSpinBox, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QMetaObject, QCoreApplication
from PySide6.QtGui import QFont, QIcon, QAction, QActionGroup, QFontDatabase, QPainter
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
    from .command_interface import CommandSender
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
    from command_interface import CommandSender

# 版本信息
__version__ = config.version
__version_date__ = config.version_date
__version_author__ = config.version_author

# 全局变量：保存实际加载的应用程序字体族名
_app_font_family = None
_app_font_size = 10


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
        self.command_sender = CommandSender()
        
        # 多个绘图器（用于不同选项卡）
        self.plotters = {}
        
        # 控制变量
        self.is_running = False
        self.update_thread = None
        self.stop_event = threading.Event()
        self.is_saving = False
        self.use_auto_save = user_settings.get_use_auto_save_path()
        
        # 记录相关变量
        self.is_recording = False  # 是否正在记录JSONL
        self.current_log_path = None  # 当前日志文件路径
        self.auto_start_recording_enabled = user_settings.get_auto_start_recording()
        
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
        
        # 呼吸信道列表初始化标志
        self.breathing_channels_initialized = False  # 是否已初始化呼吸信道列表
        self.last_breathing_channel = None  # 上一次呼吸估计使用的信道（用于检测信道变化）
        
        # 帧数据处理
        self.frame_type = config.default_frame_type
        self.frame_mode = (self.frame_type == "信道探测帧" or self.frame_type == "方向估计帧")
        self.is_direction_estimation_mode = (self.frame_type == "方向估计帧")
        # 使用默认配置解析显示信道列表（临时使用，稍后在_apply_frame_settings中会正确设置）
        self.display_channel_list = []
        # 根据帧类型设置默认显示帧数
        if self.is_direction_estimation_mode:
            self.display_max_frames = config.df_default_display_max_frames
        else:
            self.display_max_frames = config.default_display_max_frames
        
        # 加载模式相关
        self.is_loaded_mode = False
        self.loaded_frames = []
        self.loaded_file_info = None
        self.current_window_start = 0
        # 根据当前帧类型初始化呼吸估计器（从config加载默认参数）
        self.breathing_estimator = BreathingEstimator(frame_type=self.frame_type)
        
        # 设置数据访问接口
        self.breathing_estimator.set_data_accessor(self._breathing_data_accessor)
        
        # 主题模式
        self.current_theme_mode = "light"  # auto, light, dark（默认浅色模式）
        
        # 实时呼吸估计相关
        self.breathing_update_interval = config.breathing_default_update_interval  # 从config加载默认值
        self.breathing_update_timer = None
        self.last_breathing_update_time = 0
        
        # 信道呼吸能量计算相关（从config加载默认值）
        # 注意：breathing_adaptive_enabled从config加载，但"自适应"checkbox和"手动切换到最佳信道"按钮
        # 在一开始上电时都默认禁用，只有用户手动开启了"启用信道的呼吸能量计算"后才启用
        self.breathing_adaptive_enabled = config.breathing_adaptive_enabled
        self.breathing_adaptive_top_n = config.breathing_adaptive_top_n
        self.breathing_adaptive_highlight = config.breathing_adaptive_highlight
        self.breathing_adaptive_auto_switch = config.breathing_adaptive_auto_switch
        self.breathing_adaptive_only_display_channels = config.breathing_adaptive_only_display_channels
        self.breathing_adaptive_manual_control = False  # 是否启用自适应（在channel旁边）
        self.manual_select_triggered = False  # 是否手动触发了信道切换（临时标志，用于单次调用）
        self.manual_select_mode = False  # 是否处于手动选择模式（持续标志，用于后续调用）
        self.manual_selected_channel = None  # 手动选择的信道（用于防止自动切换）
        # 注意：adaptive_selected_channel、current_best_channels、adaptive_low_energy_start_time
        # 现在由BreathingEstimator管理，这里只保留引用以便GUI访问
        self.adaptive_low_energy_threshold = config.breathing_adaptive_low_energy_threshold
        
        # 清除数据长按相关
        self.clear_data_hold_duration = 2.0  # 需要按住2秒
        self.clear_data_progress_timer = None
        self.clear_data_progress_value = 0
        self.is_holding_clear_btn = False
        
        # 停止记录长按相关
        self.stop_recording_hold_duration = 1.0  # 需要按住1秒
        self.stop_recording_progress_timer = None
        self.stop_recording_progress_value = 0
        self.is_holding_stop_recording_btn = False
        
        # 显示控制相关（默认都显示）
        self.show_log = True
        self.show_version_info = True
        self.show_toolbar = True
        self.show_breathing_control = True
        self.show_send_command = True
        
        # 时间窗滑动条按钮长按相关
        self.slider_button_timer = None
        self.is_holding_slider_btn = False
        self.slider_button_direction = None  # 'left' or 'right'
        
        # 创建界面
        self._create_widgets()
        
        # 应用默认设置（初始化显示信道）
        if self.frame_mode:
            # 先设置默认值
            self.display_channels_entry.setText(config.default_display_channels)
            self._apply_frame_settings(show_info=False)  # 初始化时不显示提示
        
        # 根据帧类型初始化呼吸估计器的默认参数（在UI创建完成后）
        if hasattr(self, 'breathing_estimator') and hasattr(self, 'breathing_sampling_rate_entry'):
            self._update_breathing_params_from_frame_type()
        
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
        
        # 初始化文件加载tab的状态（确保初始状态正确）
        self._update_load_tab_state()
    
    def _setup_logging(self):
        """设置日志"""
        import sys
        
        # 创建日志目录
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # 日志文件名（带时间戳）
        log_filename = os.path.join(log_dir, f'ble_host_{datetime.now().strftime("%Y%m%d")}.log')
        
        # 配置日志格式
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'
        
        # 配置日志：同时输出到控制台和文件
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            datefmt=date_format,
            handlers=[
                logging.StreamHandler(sys.stdout),  # 控制台输出
                logging.FileHandler(log_filename, encoding='utf-8', mode='a')  # 文件输出
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"日志文件: {log_filename}")
    
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
        status_label.setFont(get_app_font(9, bold=True))
        self.status_label = QLabel("未连接")
        self.status_label.setStyleSheet("color: red;")
        self.status_label.setFont(get_app_font(9))
        
        # 保存状态显示（在连接状态后面）
        self.save_status_label = QLabel("")
        self.save_status_label.setFont(get_app_font(9))
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
        tab_font = get_app_font(11)
        self.config_tabs.setFont(tab_font)
        # 设置最小高度，防止被挤压
        self.config_tabs.setMinimumHeight(150)
        self._create_connection_tab()
        self._create_channel_config_tab()
        self._create_data_and_save_tab()
        self._create_load_tab()
        self._create_special_features_tab()
        self._create_settings_tab()
        
        main_layout.addWidget(self.config_tabs)
        
        # 3. 左右分栏（绘图区域 + 右侧面板）
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：绘图区域
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 绘图选项卡
        self.plot_tabs = QTabWidget()
        # 设置tab字体更大
        tab_font = get_app_font(11)
        self.plot_tabs.setFont(tab_font)
        self._create_plot_tabs()
        left_layout.addWidget(self.plot_tabs)
        # 设置工具栏最大宽度，确保靠右排列
        # self.plot_tabs.setMaximumWidth(1000)
        self.plot_tabs.setMinimumHeight(400)
        self.plot_tabs.setMaximumHeight(800)
        
        self.main_splitter.addWidget(left_widget)
        # 左侧绘图区域设置为可扩展，当右侧工具栏未占满宽度时会扩充
        self.main_splitter.setStretchFactor(0, 1)  # 左侧可扩展
        
        # 右侧：信息面板（使用垂直QSplitter以便调整大小）
        self.right_widget = QWidget()
        # 设置右侧面板的大小策略为Maximum，使其只占据实际需要的空间
        self.right_widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setChildrenCollapsible(False)  # 防止完全折叠
        # 设置右侧分割器的最大宽度，确保它不会占据过多空间
        # 工具栏最大宽度300 + 边距，设置为稍大一点以容纳所有内容
        self.right_splitter.setMaximumWidth(320)
        
        # 工具栏（包含呼吸控制和发送指令）
        self.toolbar_group = QGroupBox("工具栏")
        toolbar_layout = QVBoxLayout(self.toolbar_group)
        # 设置工具栏最大宽度，确保靠右排列
        self.toolbar_group.setMaximumWidth(300)
        self.toolbar_group.setMinimumHeight(300)
        self.toolbar_group.setMaximumHeight(800)
        # 设置大小策略，确保工具栏不会扩展，保持靠右
        self.toolbar_group.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        
        # 创建工具栏Tab Widget
        self.toolbar_tabs = QTabWidget()
        tab_font = get_app_font(9)
        self.toolbar_tabs.setFont(tab_font)
        
        # 创建呼吸控制tab（包含原有的三个子tab）
        self._create_breathing_control_tab(toolbar_layout)
        
        # 创建发送指令tab
        self._create_send_command_tab(toolbar_layout)
        
        toolbar_layout.addWidget(self.toolbar_tabs)
        self.right_splitter.addWidget(self.toolbar_group)
        
        # 数据处理区域（暂时隐藏）
        self.process_group = QGroupBox("数据处理")
        process_layout = QVBoxLayout(self.process_group)
        self._create_process_panel(process_layout)
        self.process_group.setVisible(False)  # 暂时隐藏
        self.right_splitter.addWidget(self.process_group)
        
        # 日志区域
        self._create_log_panel(self.right_splitter)
        
        # 版本信息（不添加到splitter，直接添加到right_widget的底部）
        self.right_widget_layout = QVBoxLayout(self.right_widget)
        self.right_widget_layout.setContentsMargins(5, 5, 5, 5)
        # 右侧面板布局：使用水平布局，让右侧内容靠右对齐
        right_horizontal_layout = QHBoxLayout()
        right_horizontal_layout.setContentsMargins(0, 0, 0, 0)
        right_horizontal_layout.addStretch()  # 左侧添加弹性空间，推动右侧内容靠右
        right_horizontal_layout.addWidget(self.right_splitter)
        # 将水平布局添加到垂直布局
        self.right_widget_layout.addLayout(right_horizontal_layout, stretch=1)
        # 版本信息也靠右对齐
        version_horizontal_layout = QHBoxLayout()
        version_horizontal_layout.addStretch()
        self._create_version_info(version_horizontal_layout)
        self.right_widget_layout.addLayout(version_horizontal_layout)
        
        self.main_splitter.addWidget(self.right_widget)
        # 右侧设置为不扩展（Maximum策略），这样当工具栏宽度小于最大值时，左侧绘图区域会自动扩充
        self.main_splitter.setStretchFactor(1, 0)  # 右侧不扩展
        self.main_splitter.setChildrenCollapsible(False)  # 防止完全折叠
        
        main_layout.addWidget(self.main_splitter, stretch=1)
    
    def _create_breathing_control_tab(self, parent_layout):
        """创建呼吸控制tab（包含基本、进阶、可视化三个子tab）"""
        breathing_control_widget = QWidget()
        breathing_control_layout = QVBoxLayout(breathing_control_widget)
        breathing_control_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建Tab Widget
        self.breathing_control_tabs = QTabWidget()
        # tab_font = get_app_font(10)
        # self.breathing_control_tabs.setFont(tab_font)
        
        # Basic Tab
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        basic_layout.setContentsMargins(5, 5, 5, 5)
        basic_layout.setSpacing(5)
        
        # 数据类型选择
        data_type_layout = QHBoxLayout()
        data_type_label = QLabel("Data Type:")
        data_type_label.setToolTip("选择用于呼吸估计的数据类型")
        data_type_label.installEventFilter(ToolTipFilter(data_type_label, 0, ToolTipPosition.TOP))
        data_type_layout.addWidget(data_type_label)
        self.breathing_data_type_combo = QComboBox()
        # 初始添加所有选项，方向估计模式下会限制选项
        self.breathing_data_type_combo.addItems(["amplitude", "local_amplitude", "remote_amplitude", "phase", "local_phase", "remote_phase"])
        # 设置字体和最大宽度，使其与文本框一样可以变小
        self.breathing_data_type_combo.setFont(get_app_font(9))
        self.breathing_data_type_combo.setMaximumWidth(150)
        data_type_layout.addWidget(self.breathing_data_type_combo)
        basic_layout.addLayout(data_type_layout)
        
        # 信道选择
        channel_layout = QHBoxLayout()
        channel_label = QLabel("Channel:")
        channel_label.setToolTip("选择用于呼吸估计的信道（方向估计帧模式下自动使用当前帧的信道）")
        channel_label.installEventFilter(ToolTipFilter(channel_label, 0, ToolTipPosition.TOP))
        channel_layout.addWidget(channel_label)
        self.breathing_channel_combo = QComboBox()
        # 设置字体和最大宽度，使其与文本框一样可以变小
        self.breathing_channel_combo.setFont(get_app_font(9))
        self.breathing_channel_combo.setMaximumWidth(80)
        channel_layout.addWidget(self.breathing_channel_combo)
        # 自适应checkbox（方向估计帧模式下禁用）
        self.breathing_adaptive_manual_checkbox = QCheckBox("自适应")
        self.breathing_adaptive_manual_checkbox.setToolTip("启用后，信道呼吸能量计算功能将接管信道选择（方向估计帧模式下不可用）")
        self.breathing_adaptive_manual_checkbox.setChecked(self.breathing_adaptive_manual_control)
        # 默认禁用，只有在开启"启用信道的呼吸能量计算"后才启用（一开始上电时强制禁用）
        # 注意：即使config中breathing_adaptive_enabled为True，一开始也要禁用，只有用户手动开启后才启用
        self.breathing_adaptive_manual_checkbox.setEnabled(False)
        self.breathing_adaptive_manual_checkbox.stateChanged.connect(self._on_adaptive_manual_changed)
        channel_layout.addWidget(self.breathing_adaptive_manual_checkbox)
        basic_layout.addLayout(channel_layout)
        
        # 手动切换到最佳信道按钮
        manual_select_layout = QHBoxLayout()
        self.breathing_manual_select_btn = QPushButton("手动切换到最佳信道")
        self.breathing_manual_select_btn.setToolTip("手动触发一次信道切换。需要先启用'启用信道的呼吸能量计算'，且未勾选'自适应'和'在最高能量信道上执行呼吸监测'。点击后会切换到能量最高的信道并驻留，即使低能量超时也不会自动切换。")
        self.breathing_manual_select_btn.clicked.connect(self._on_manual_select_best_channel)
        # 默认禁用，只有在开启"启用信道的呼吸能量计算"后才按原有逻辑启用
        self._update_manual_select_btn_state()
        manual_select_layout.addWidget(self.breathing_manual_select_btn)
        basic_layout.addLayout(manual_select_layout)
        
        # 阈值输入
        threshold_layout = QHBoxLayout()
        threshold_label = QLabel("Threshold:")
        threshold_label.setToolTip("呼吸频段能量最低占比")
        threshold_label.installEventFilter(ToolTipFilter(threshold_label, 0, ToolTipPosition.TOP))
        threshold_layout.addWidget(threshold_label)
        self.breathing_threshold_entry = QLineEdit(str(config.breathing_default_threshold))
        self.breathing_threshold_entry.setMaximumWidth(80)
        self.breathing_threshold_entry.setToolTip("输入0~1之间的值")
        self.breathing_threshold_entry.installEventFilter(ToolTipFilter(self.breathing_threshold_entry, 0, ToolTipPosition.TOP))
        threshold_layout.addWidget(self.breathing_threshold_entry)
        basic_layout.addLayout(threshold_layout)
        
        # 实时更新间隔（N秒）
        interval_layout = QHBoxLayout()
        interval_label = QLabel("更新间隔(秒):")
        interval_label.setToolTip("呼吸估计结果的更新间隔时间（秒），也称作时间窗步长")
        interval_label.installEventFilter(ToolTipFilter(interval_label, 0, ToolTipPosition.TOP))
        interval_layout.addWidget(interval_label)
        self.breathing_update_interval_entry = QLineEdit(str(config.breathing_default_update_interval))
        self.breathing_update_interval_entry.setMaximumWidth(80)
        self.breathing_update_interval_entry.setToolTip("输入大于0的值（秒）")
        self.breathing_update_interval_entry.installEventFilter(ToolTipFilter(self.breathing_update_interval_entry, 0, ToolTipPosition.TOP))
        interval_layout.addWidget(self.breathing_update_interval_entry)
        basic_layout.addLayout(interval_layout)
        
        basic_layout.addStretch()
        self.breathing_control_tabs.addTab(basic_tab, "基本")
        
        # Advanced Tab
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_layout.setContentsMargins(5, 5, 5, 5)
        advanced_layout.setSpacing(5)
        
        # 采样率
        sampling_rate_layout = QHBoxLayout()
        sampling_rate_label = QLabel("采样率 (Hz):")
        sampling_rate_label.setToolTip("信号采样率，方向估计帧为50Hz，信道探测帧为2Hz")
        sampling_rate_label.installEventFilter(ToolTipFilter(sampling_rate_label, 0, ToolTipPosition.TOP))
        sampling_rate_layout.addWidget(sampling_rate_label)
        # 初始值根据当前帧类型设置（稍后会在_update_breathing_params_from_frame_type中更新）
        initial_sampling_rate = config.breathing_df_sampling_rate if self.frame_type == "方向估计帧" else config.breathing_cs_sampling_rate
        self.breathing_sampling_rate_entry = QLineEdit(str(initial_sampling_rate))
        self.breathing_sampling_rate_entry.setMaximumWidth(100)
        self.breathing_sampling_rate_entry.setToolTip("输入大于0的值（Hz）")
        self.breathing_sampling_rate_entry.installEventFilter(ToolTipFilter(self.breathing_sampling_rate_entry, 0, ToolTipPosition.TOP))
        sampling_rate_layout.addWidget(self.breathing_sampling_rate_entry)
        advanced_layout.addLayout(sampling_rate_layout)
        
        # 中值滤波窗口
        median_filter_layout = QHBoxLayout()
        median_filter_label = QLabel("中值滤波窗口:")
        median_filter_label.setToolTip("单位为帧数，方向估计帧为10，信道探测帧为3，通常不超过0.2s")
        median_filter_label.installEventFilter(ToolTipFilter(median_filter_label, 0, ToolTipPosition.TOP))
        median_filter_layout.addWidget(median_filter_label)
        # 初始值根据当前帧类型设置
        initial_median_window = config.breathing_df_median_filter_window if self.frame_type == "方向估计帧" else config.breathing_cs_median_filter_window
        self.breathing_median_filter_entry = QLineEdit(str(initial_median_window))
        self.breathing_median_filter_entry.setMaximumWidth(100)
        self.breathing_median_filter_entry.setToolTip("输入大于0的整数")
        self.breathing_median_filter_entry.installEventFilter(ToolTipFilter(self.breathing_median_filter_entry, 0, ToolTipPosition.TOP))
        median_filter_layout.addWidget(self.breathing_median_filter_entry)
        advanced_layout.addLayout(median_filter_layout)
        
        # 高通滤波器参数
        highpass_cutoff_layout = QHBoxLayout()
        highpass_cutoff_label = QLabel("高通截止频率 (Hz):")
        highpass_cutoff_label.setToolTip("高通滤波器截止频率，用于去除直流和低频趋势")
        highpass_cutoff_label.installEventFilter(ToolTipFilter(highpass_cutoff_label, 0, ToolTipPosition.TOP))
        highpass_cutoff_layout.addWidget(highpass_cutoff_label)
        # 初始值使用信道探测帧的默认值（两种帧类型的高通参数相同）
        self.breathing_highpass_cutoff_entry = QLineEdit(str(config.breathing_cs_highpass_cutoff))
        self.breathing_highpass_cutoff_entry.setMaximumWidth(100)
        self.breathing_highpass_cutoff_entry.setToolTip("输入大于0的值（Hz）")
        self.breathing_highpass_cutoff_entry.installEventFilter(ToolTipFilter(self.breathing_highpass_cutoff_entry, 0, ToolTipPosition.TOP))
        highpass_cutoff_layout.addWidget(self.breathing_highpass_cutoff_entry)
        advanced_layout.addLayout(highpass_cutoff_layout)
        
        highpass_order_layout = QHBoxLayout()
        highpass_order_label = QLabel("高通滤波器阶数:")
        highpass_order_label.setToolTip("高通滤波器的阶数")
        highpass_order_label.installEventFilter(ToolTipFilter(highpass_order_label, 0, ToolTipPosition.TOP))
        highpass_order_layout.addWidget(highpass_order_label)
        self.breathing_highpass_order_entry = QLineEdit(str(config.breathing_cs_highpass_order))
        self.breathing_highpass_order_entry.setMaximumWidth(100)
        self.breathing_highpass_order_entry.setToolTip("输入大于0的整数")
        self.breathing_highpass_order_entry.installEventFilter(ToolTipFilter(self.breathing_highpass_order_entry, 0, ToolTipPosition.TOP))
        highpass_order_layout.addWidget(self.breathing_highpass_order_entry)
        advanced_layout.addLayout(highpass_order_layout)
        
        # 带通滤波器参数
        bandpass_lowcut_layout = QHBoxLayout()
        bandpass_lowcut_label = QLabel("带通低截止频率 (Hz):")
        bandpass_lowcut_label.setToolTip("带通滤波器的低截止频率")
        bandpass_lowcut_label.installEventFilter(ToolTipFilter(bandpass_lowcut_label, 0, ToolTipPosition.TOP))
        bandpass_lowcut_layout.addWidget(bandpass_lowcut_label)
        self.breathing_bandpass_lowcut_entry = QLineEdit(str(config.breathing_cs_bandpass_lowcut))
        self.breathing_bandpass_lowcut_entry.setMaximumWidth(100)
        self.breathing_bandpass_lowcut_entry.setToolTip("输入大于0的值（Hz）")
        self.breathing_bandpass_lowcut_entry.installEventFilter(ToolTipFilter(self.breathing_bandpass_lowcut_entry, 0, ToolTipPosition.TOP))
        bandpass_lowcut_layout.addWidget(self.breathing_bandpass_lowcut_entry)
        advanced_layout.addLayout(bandpass_lowcut_layout)
        
        bandpass_highcut_layout = QHBoxLayout()
        bandpass_highcut_label = QLabel("带通高截止频率 (Hz):")
        bandpass_highcut_label.setToolTip("带通滤波器的高截止频率")
        bandpass_highcut_label.installEventFilter(ToolTipFilter(bandpass_highcut_label, 0, ToolTipPosition.TOP))
        bandpass_highcut_layout.addWidget(bandpass_highcut_label)
        self.breathing_bandpass_highcut_entry = QLineEdit(str(config.breathing_cs_bandpass_highcut))
        self.breathing_bandpass_highcut_entry.setMaximumWidth(100)
        self.breathing_bandpass_highcut_entry.setToolTip("输入大于0的值（Hz），应大于低截止频率")
        self.breathing_bandpass_highcut_entry.installEventFilter(ToolTipFilter(self.breathing_bandpass_highcut_entry, 0, ToolTipPosition.TOP))
        bandpass_highcut_layout.addWidget(self.breathing_bandpass_highcut_entry)
        advanced_layout.addLayout(bandpass_highcut_layout)
        
        bandpass_order_layout = QHBoxLayout()
        bandpass_order_label = QLabel("带通滤波器阶数:")
        bandpass_order_label.setToolTip("带通滤波器的阶数")
        bandpass_order_label.installEventFilter(ToolTipFilter(bandpass_order_label, 0, ToolTipPosition.TOP))
        bandpass_order_layout.addWidget(bandpass_order_label)
        self.breathing_bandpass_order_entry = QLineEdit(str(config.breathing_cs_bandpass_order))
        self.breathing_bandpass_order_entry.setMaximumWidth(100)
        self.breathing_bandpass_order_entry.setToolTip("输入大于0的整数")
        self.breathing_bandpass_order_entry.installEventFilter(ToolTipFilter(self.breathing_bandpass_order_entry, 0, ToolTipPosition.TOP))
        bandpass_order_layout.addWidget(self.breathing_bandpass_order_entry)
        advanced_layout.addLayout(bandpass_order_layout)
        
        advanced_layout.addStretch()
        self.breathing_control_tabs.addTab(advanced_tab, "进阶")
        
        # Visualization Tab（可视化设置）
        visualization_tab = QWidget()
        visualization_tab_layout = QVBoxLayout(visualization_tab)
        visualization_tab_layout.setContentsMargins(5, 5, 5, 5)
        visualization_tab_layout.setSpacing(10)
        
        visualization_info_label = QLabel("选择在滤波波形tab中显示的滤波阶段：")
        visualization_info_label.setToolTip("可以任意组合选择显示哪些滤波阶段的波形")
        visualization_info_label.installEventFilter(ToolTipFilter(visualization_info_label, 0, ToolTipPosition.TOP))
        visualization_tab_layout.addWidget(visualization_info_label)
        
        # 中值滤波复选框
        self.breathing_show_median_checkbox = QCheckBox("显示中值滤波")
        self.breathing_show_median_checkbox.setChecked(config.breathing_default_show_median)
        self.breathing_show_median_checkbox.setToolTip("显示中值滤波后的信号波形")
        self.breathing_show_median_checkbox.installEventFilter(ToolTipFilter(self.breathing_show_median_checkbox, 0, ToolTipPosition.TOP))
        self.breathing_show_median_checkbox.stateChanged.connect(self._on_visualization_checkbox_changed)
        visualization_tab_layout.addWidget(self.breathing_show_median_checkbox)
        
        # 高通滤波复选框
        self.breathing_show_highpass_checkbox = QCheckBox("显示中值+高通滤波")
        self.breathing_show_highpass_checkbox.setChecked(config.breathing_default_show_highpass)
        self.breathing_show_highpass_checkbox.setToolTip("显示中值滤波+高通滤波后的信号波形")
        self.breathing_show_highpass_checkbox.installEventFilter(ToolTipFilter(self.breathing_show_highpass_checkbox, 0, ToolTipPosition.TOP))
        self.breathing_show_highpass_checkbox.stateChanged.connect(self._on_visualization_checkbox_changed)
        visualization_tab_layout.addWidget(self.breathing_show_highpass_checkbox)
        
        # 带通滤波复选框
        self.breathing_show_bandpass_checkbox = QCheckBox("显示中值+高通+带通滤波")
        self.breathing_show_bandpass_checkbox.setChecked(config.breathing_default_show_bandpass)
        self.breathing_show_bandpass_checkbox.setToolTip("显示中值滤波+高通滤波+带通滤波后的信号波形")
        self.breathing_show_bandpass_checkbox.installEventFilter(ToolTipFilter(self.breathing_show_bandpass_checkbox, 0, ToolTipPosition.TOP))
        self.breathing_show_bandpass_checkbox.stateChanged.connect(self._on_visualization_checkbox_changed)
        visualization_tab_layout.addWidget(self.breathing_show_bandpass_checkbox)
        
        visualization_tab_layout.addStretch()
        self.breathing_control_tabs.addTab(visualization_tab, "滤波可视化")
        
        breathing_control_layout.addWidget(self.breathing_control_tabs)
        
        # Update按钮和恢复默认按钮（控制所有参数，放在tab下面）
        update_layout = QHBoxLayout()
        self.update_all_btn = QPushButton("应用参数")
        self.update_all_btn.setStyleSheet(self._get_button_style("#2196F3"))
        self.update_all_btn.clicked.connect(self._on_update_all_breathing_params)
        update_layout.addWidget(self.update_all_btn)
        
        self.reset_defaults_btn = QPushButton("恢复默认")
        self.reset_defaults_btn.setStyleSheet(self._get_button_style("#FF9800"))
        self.reset_defaults_btn.clicked.connect(self._on_reset_breathing_defaults)
        update_layout.addWidget(self.reset_defaults_btn)
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
        
        # 将呼吸控制widget添加到工具栏tab
        self.toolbar_tabs.addTab(breathing_control_widget, "呼吸控制")
    
    def _create_send_command_tab(self, parent_layout):
        """创建发送指令tab"""
        send_command_widget = QWidget()
        send_command_layout = QVBoxLayout(send_command_widget)
        send_command_layout.setContentsMargins(5, 5, 5, 5)
        send_command_layout.setSpacing(10)
        
        # 命令类型选择区域
        type_label = QLabel("命令类型:")
        send_command_layout.addWidget(type_label)
        
        self.command_type_combo = QComboBox()
        # 添加所有命令类型
        for cmd_type, cmd_def in self.command_sender.COMMAND_TYPES.items():
            self.command_type_combo.addItem(f"{cmd_type} - {cmd_def['description']}", cmd_type)
        self.command_type_combo.currentIndexChanged.connect(self._on_command_type_changed)
        send_command_layout.addWidget(self.command_type_combo)
        
        # 参数输入区域（固定创建所有参数框）
        self.param_widgets = {}  # 存储参数控件
        self.param_container = QWidget()
        self.param_layout = QVBoxLayout(self.param_container)
        self.param_layout.setContentsMargins(0, 0, 0, 0)
        self.param_layout.setSpacing(5)
        # self.param_layout.addStretch()
        send_command_layout.addWidget(self.param_container)
        
        # 固定创建所有可能的参数框（避免重复创建）
        self._create_fixed_param_widgets()
        
        # 转义字符选项
        escape_layout = QHBoxLayout()
        self.escape_checkbox = QCheckBox("启用转义字符")
        self.escape_checkbox.setChecked(True)  # 默认勾选
        self.escape_checkbox.stateChanged.connect(self._on_escape_checkbox_changed)
        escape_layout.addWidget(self.escape_checkbox)
        # escape_layout.addStretch()
        send_command_layout.addLayout(escape_layout)
        
        send_command_layout.addStretch()
        # 命令生成和发送区域
        generate_layout = QHBoxLayout()
        self.generate_command_btn = QPushButton("生成命令")
        self.generate_command_btn.setStyleSheet(self._get_button_style("#2196F3"))
        self.generate_command_btn.clicked.connect(self._on_generate_command)
        generate_layout.addWidget(self.generate_command_btn)
        
        # 恢复默认参数按钮
        self.reset_params_btn = QPushButton("恢复默认")
        self.reset_params_btn.setStyleSheet(self._get_button_style("#9E9E9E"))
        self.reset_params_btn.clicked.connect(self._on_reset_command_params)
        generate_layout.addWidget(self.reset_params_btn)
        
        generate_layout.addStretch()
        send_command_layout.addLayout(generate_layout)

        # send_command_layout.addStretch()
        
        # 指令输入区域（显示生成的命令，也可以手动编辑）
        input_label = QLabel("指令内容:")
        send_command_layout.addWidget(input_label)
        
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("输入要发送的指令或使用上方生成命令...")
        self.command_input.returnPressed.connect(self._on_send_command)  # 按回车发送
        send_command_layout.addWidget(self.command_input)

        # send_command_layout.addStretch()
        
        # 发送按钮
        send_btn_layout = QHBoxLayout()
        self.send_command_btn = QPushButton("发送指令")
        self.send_command_btn.setStyleSheet(self._get_button_style("#4CAF50"))
        self.send_command_btn.clicked.connect(self._on_send_command)
        send_btn_layout.addWidget(self.send_command_btn)
        # send_btn_layout.addStretch()
        send_command_layout.addLayout(send_btn_layout)
        
        # 交互历史区域（显示发送和反馈）
        history_label = QLabel("交互历史:")
        send_command_layout.addWidget(history_label)
        
        self.command_history = QTextEdit()
        self.command_history.setReadOnly(True)
        # self.command_history.setFont(QFont("Consolas", 9))
        self.command_history.setMaximumHeight(150)
        send_command_layout.addWidget(self.command_history)

        # send_command_layout.addStretch()
        
        # 清空历史按钮
        clear_history_btn = QPushButton("清空历史")
        clear_history_btn.setStyleSheet(self._get_button_style("#9E9E9E"))
        clear_history_btn.clicked.connect(self._on_clear_command_history)
        send_command_layout.addWidget(clear_history_btn)
        
        # send_command_layout.addStretch()
        
        # 初始化参数输入区域（根据当前命令类型启用/禁用参数框）
        self._on_command_type_changed()
        
        # 将发送指令widget添加到工具栏tab
        self.toolbar_tabs.addTab(send_command_widget, "发送指令")
    
    def _create_menu_bar(self):
        """创建菜单栏（已移除，设置改为tab）"""
        # 菜单栏已移除，所有设置都在设置tab中
        pass
    
    @staticmethod
    def _get_button_style(bg_color: str, text_color: str = "white") -> str:
        """
        生成带悬停和按下状态的按钮样式表
        
        Args:
            bg_color: 背景颜色（十六进制，如 "#4CAF50"）
            text_color: 文字颜色（默认白色）
        
        Returns:
            完整的样式表字符串，包含normal、hover、pressed状态
        """
        # 将十六进制颜色转换为RGB
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        # 将RGB转换为十六进制
        def rgb_to_hex(rgb):
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        
        # 计算更深的颜色（按下状态，亮度降低25%）
        def darken_color(rgb, factor=0.75):
            return tuple(int(c * factor) for c in rgb)
        
        # 计算稍亮的颜色（悬停状态，亮度增加10%）
        def lighten_color(rgb, factor=1.1):
            return tuple(min(255, int(c * factor)) for c in rgb)
        
        rgb = hex_to_rgb(bg_color)
        hover_rgb = lighten_color(rgb)
        pressed_rgb = darken_color(rgb)
        
        hover_color = rgb_to_hex(hover_rgb)
        pressed_color = rgb_to_hex(pressed_rgb)
        
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                padding: 5px 15px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
                color: #666666;
            }}
        """
    
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
        self.connect_btn.setStyleSheet(self._get_button_style("#4CAF50"))
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
        
        # DF模式：功率P/RMS幅值选择
        self.df_amplitude_type_combo = QComboBox()
        self.df_amplitude_type_combo.addItems(["RMS幅值 (√P)", "功率P"])
        self.df_amplitude_type_combo.setCurrentText("RMS幅值 (√P)")
        self.df_amplitude_type_combo.currentTextChanged.connect(self._on_df_amplitude_type_changed)
        self.df_amplitude_type_label = QLabel("幅值类型:")
        layout.addWidget(self.df_amplitude_type_label)
        layout.addWidget(self.df_amplitude_type_combo)
        
        # 初始状态：DF模式下启用，其他模式下禁用
        self._update_df_amplitude_type_enabled()
        
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
        # 使用setFont设置字体大小，而不是样式表，以保持主题响应
        path_group.setFont(get_app_font(9))
        path_group.setMaximumWidth(300)
        path_group.setMaximumHeight(120)
        path_layout = QVBoxLayout(path_group)
        
        set_path_btn = QPushButton("设置保存路径...")
        set_path_btn.clicked.connect(self._set_save_path)
        path_layout.addWidget(set_path_btn)
        
        # 使用 SwitchButton 替代 CheckBox
        auto_save_layout = QHBoxLayout()
        auto_save_layout.addWidget(QLabel("记住保存路径:"))
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
        
        # 第二组：保存与导出（两列布局）
        save_group = QGroupBox("保存与导出")
        # 使用setFont设置字体大小，而不是样式表，以保持主题响应
        save_group.setFont(get_app_font(9))
        save_group.setMaximumHeight(180)
        save_group.setMinimumWidth(400)  # 增加最小宽度以容纳两列
        save_layout = QHBoxLayout(save_group)  # 改为水平布局
        
        # 第一列：开始记录相关
        left_column = QVBoxLayout()
        
        # 自动开始记录复选框
        self.auto_start_recording_checkbox = QCheckBox("自动开始记录")
        self.auto_start_recording_checkbox.setToolTip("勾选后，连接串口且有数据后自动开始记录JSONL")
        self.auto_start_recording_checkbox.setChecked(user_settings.get_auto_start_recording())
        self.auto_start_recording_checkbox.stateChanged.connect(self._on_auto_start_recording_changed)
        left_column.addWidget(self.auto_start_recording_checkbox)
        
        # 开始记录按钮
        self.start_recording_btn = QPushButton("开始记录")
        self.start_recording_btn.setStyleSheet(self._get_button_style("#4CAF50"))
        self.start_recording_btn.setToolTip("开始记录JSONL日志文件")
        self.start_recording_btn.clicked.connect(self._start_recording)
        left_column.addWidget(self.start_recording_btn)
        
        left_column.addStretch()
        
        # 第二列：停止记录和标记事件
        right_column = QVBoxLayout()
        
        # 停止记录按钮和进度环容器
        stop_recording_container = QHBoxLayout()
        stop_recording_container.setSpacing(5)
        stop_recording_container.setContentsMargins(0, 0, 0, 0)
        
        # 停止记录按钮将在LongPressButton类定义后创建（在清空数据按钮处）
        # 这里先添加占位，稍后会被替换
        # 进度环先添加
        self.stop_recording_progress_ring = ProgressRing(self)
        self.stop_recording_progress_ring.setFixedSize(32, 32)
        self.stop_recording_progress_ring.setTextVisible(False)
        self.stop_recording_progress_ring.setValue(0)
        self.stop_recording_progress_ring.setStyleSheet("opacity: 0;")
        stop_recording_container.addWidget(self.stop_recording_progress_ring)
        
        # 保存容器引用以便后续插入按钮
        self._stop_recording_container = stop_recording_container
        
        right_column.addLayout(stop_recording_container)
        
        # 标记事件按钮
        self.mark_event_btn = QPushButton("标记事件")
        self.mark_event_btn.setStyleSheet(self._get_button_style("#FF9800"))
        self.mark_event_btn.setToolTip("标记当前时刻的特殊事件（如外部干扰、异常等）")
        self.mark_event_btn.clicked.connect(self._mark_event)
        self.mark_event_btn.setEnabled(False)  # 初始状态禁用，只有在记录时才启用
        right_column.addWidget(self.mark_event_btn)
        
        right_column.addStretch()
        
        # 将两列添加到主布局
        save_layout.addLayout(left_column)
        save_layout.addLayout(right_column)
        
        top_row.addWidget(save_group)
        
        # 第三组：清空当前数据单独一个组
        clear_group = QGroupBox("清空数据")
        # 使用setFont设置字体大小，而不是样式表，以保持主题响应
        clear_group.setFont(get_app_font(9))
        clear_group.setMaximumWidth(200)
        clear_group.setMaximumHeight(120)
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
        
        # 保存LongPressButton类以便停止记录按钮使用
        self._LongPressButtonClass = LongPressButton
        
        # 现在创建停止记录按钮为长按按钮
        self.stop_recording_btn = LongPressButton(
            "停止记录/导出",
            self,
            self._on_stop_recording_btn_pressed,
            self._on_stop_recording_btn_released
        )
        self.stop_recording_btn.setStyleSheet(self._get_button_style("#F44336"))
        self.stop_recording_btn.setToolTip("长按1秒停止记录并可选导出为JSON格式")
        self.stop_recording_btn.setEnabled(False)
        # 局部导入QSizePolicy以避免作用域问题
        from PySide6.QtWidgets import QSizePolicy
        self.stop_recording_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.stop_recording_btn.installEventFilter(ToolTipFilter(self.stop_recording_btn, 0, ToolTipPosition.TOP))
        # 插入到容器的最前面（在进度环之前）
        if hasattr(self, '_stop_recording_container'):
            self._stop_recording_container.insertWidget(0, self.stop_recording_btn)
        
        self.clear_data_btn = LongPressButton(
            "清空当前数据", 
            self,
            self._on_clear_data_btn_pressed,
            self._on_clear_data_btn_released
        )
        self.clear_data_btn.setStyleSheet(self._get_button_style("#f44336"))
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
        btn_font = get_app_font(10)
        
        # 第一列：文件读取（文件路径部分）
        path_group = QGroupBox("文件读取")
        # 使用setFont设置字体大小，而不是样式表，以保持主题响应
        path_group.setFont(get_app_font(9))
        path_layout = QVBoxLayout(path_group)
        path_group.setMaximumWidth(200)  # 保持左右宽度限制
        path_group.setMaximumHeight(120)
        
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
        self.load_unload_btn.setStyleSheet(self._get_button_style("#2196F3"))  # 浅蓝色
        self.load_unload_btn.clicked.connect(self._toggle_load_file)
        button_layout.addWidget(self.load_unload_btn)
        path_layout.addLayout(button_layout)
        
        path_layout.addStretch()
        layout.addWidget(path_group)
        
        # 第二列：时间窗控制
        control_group = QGroupBox("时间窗控制")
        # 使用setFont设置字体大小，而不是样式表，以保持主题响应
        control_group.setFont(get_app_font(9))
        control_layout = QVBoxLayout(control_group)
        control_group.setMaximumHeight(150)
        control_group.setMaximumWidth(1000)
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(5)
        
        # 第一行：时间窗起点输入框 + 时间窗长度显示 + 回到当前帧按钮
        first_row = QHBoxLayout()
        first_row.addWidget(QLabel("时间窗起点:"))
        self.window_start_entry = QLineEdit("0")
        self.window_start_entry.setMaximumWidth(80)
        self.window_start_entry.setFont(btn_font)
        self.window_start_entry.returnPressed.connect(self._on_window_start_changed)
        self.window_start_entry.setEnabled(False)  # 初始禁用
        first_row.addWidget(self.window_start_entry)
        first_row.addWidget(QLabel("(帧)"))
        first_row.addStretch()
        
        # 时间窗长度显示
        self.window_length_label = QLabel("时间窗长度: -- 秒")
        first_row.addWidget(self.window_length_label)
        first_row.addStretch()
        
        # 回到当前帧按钮
        self.reset_view_btn = QPushButton("回到当前帧")
        self.reset_view_btn.setMaximumWidth(100)
        self.reset_view_btn.setFont(btn_font)
        self.reset_view_btn.setToolTip("重置视图到当前时间窗范围")
        self.reset_view_btn.installEventFilter(ToolTipFilter(self.reset_view_btn, 0, ToolTipPosition.TOP))
        self.reset_view_btn.clicked.connect(self._on_reset_view_clicked)
        self.reset_view_btn.setEnabled(False)  # 初始禁用
        # 保存按钮的默认样式（用于恢复）
        self.reset_view_btn_default_style = self.reset_view_btn.styleSheet()
        first_row.addWidget(self.reset_view_btn)
        
        control_layout.addLayout(first_row)
        
        # 第二行：左按钮 + 滑动条 + 右按钮
        second_row = QHBoxLayout()
        
        # 左箭头按钮（支持长按）
        self.slider_left_btn = QPushButton("◄")
        self.slider_left_btn.setMaximumWidth(40)
        self.slider_left_btn.setFont(btn_font)
        self.slider_left_btn.pressed.connect(lambda: self._on_slider_button_pressed('left'))
        self.slider_left_btn.released.connect(self._on_slider_button_released)
        self.slider_left_btn.setEnabled(False)  # 初始禁用
        second_row.addWidget(self.slider_left_btn)
        
        # 滑动条（支持鼠标和键盘方向键控制，拖动时显示tooltip）
        # 创建自定义滑动条类，支持键盘方向键控制和拖动时显示tooltip
        class KeyboardSliderWithTooltip(QSlider):
            def __init__(self, orientation, parent=None, update_callback=None):
                super().__init__(orientation, parent)
                self.update_callback = update_callback
                # 连接sliderMoved信号，在拖动时显示tooltip（传递value）
                self.sliderMoved.connect(self._show_tooltip)
                # sliderPressed不传递value，需要手动获取
                self.sliderPressed.connect(self._on_slider_pressed_for_tooltip)
                self.sliderReleased.connect(self._hide_tooltip)
            
            def _on_slider_pressed_for_tooltip(self):
                """滑动条按下时的回调，显示tooltip"""
                self._show_tooltip(self.value())
            
            def _show_tooltip(self, value):
                """显示tooltip显示当前位置，显示在滑动条正上方中心"""
                from PySide6.QtCore import QPoint
                
                # 计算滑动条的中心位置（局部坐标）
                slider_rect = self.rect()
                slider_center_x = slider_rect.center().x()
                slider_top_y = slider_rect.top()
                
                # 转换为全局坐标
                local_pos = QPoint(slider_center_x, slider_top_y)
                global_pos = self.mapToGlobal(local_pos)
                
                # 在滑动条正上方显示tooltip（上方70像素）
                tooltip_pos = QPoint(global_pos.x(), global_pos.y() - 70)
                from PySide6.QtWidgets import QToolTip
                QToolTip.showText(tooltip_pos, f"帧: {value}", self)
            
            # 备用方案：使用qfluentwidgets的ToolTip（注释掉，需要时可以启用）
            # def _show_tooltip_fluent(self, value):
            #     """备用方案：使用qfluentwidgets的ToolTip显示在滑动条正上方中心"""
            #     from qfluentwidgets import ToolTip
            #     from PySide6.QtCore import QPoint
            #     from PySide6.QtWidgets import QWidget
            #     
            #     # 关闭之前的tooltip
            #     if hasattr(self, '_fluent_tooltip') and self._fluent_tooltip:
            #         self._fluent_tooltip.close()
            #         self._fluent_tooltip = None
            #     
            #     # 计算滑动条的中心位置（局部坐标）
            #     slider_rect = self.rect()
            #     slider_center_x = slider_rect.center().x()
            #     slider_top_y = slider_rect.top()
            #     
            #     # 转换为全局坐标
            #     local_pos = QPoint(slider_center_x, slider_top_y)
            #     global_pos = self.mapToGlobal(local_pos)
            #     
            #     # 创建一个临时的QWidget作为tooltip的target
            #     # 注意：qfluentwidgets的ToolTip需要target widget，但位置控制有限
            #     # 这里我们使用滑动条本身作为target
            #     self._fluent_tooltip = ToolTip(
            #         text=f"帧: {value}",
            #         target=self,
            #         duration=-1  # 不自动消失
            #     )
            #     self._fluent_tooltip.show()
            #     
            #     # 尝试移动tooltip到正确位置（如果支持）
            #     # 注意：qfluentwidgets的ToolTip可能不支持直接设置位置
            #     # 如果ToolTip不支持move，可能需要使用其他方法
            #     tooltip_x = global_pos.x() - (self._fluent_tooltip.width() // 2 if hasattr(self._fluent_tooltip, 'width') else 30)
            #     tooltip_y = global_pos.y() - 40
            #     if hasattr(self._fluent_tooltip, 'move'):
            #         self._fluent_tooltip.move(tooltip_x, tooltip_y)
            
            def _hide_tooltip(self):
                """隐藏tooltip"""
                from PySide6.QtWidgets import QToolTip
                QToolTip.hideText()
            
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
            
            def wheelEvent(self, event):
                """处理鼠标滚轮事件，滚轮改变滑块值时立即更新"""
                # 先调用父类方法，让滑块值改变
                super().wheelEvent(event)
                # 滚轮改变后立即调用更新回调
                if self.update_callback:
                    self.update_callback()
                event.accept()
        
        self.time_window_slider = KeyboardSliderWithTooltip(Qt.Orientation.Horizontal, update_callback=self._on_slider_keyboard_changed)
        self.time_window_slider.setMinimum(0)
        self.time_window_slider.setMaximum(100)
        # 允许键盘焦点，以便响应方向键
        self.time_window_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # 连接sliderReleased，鼠标释放时更新
        self.time_window_slider.sliderReleased.connect(self._on_slider_released)
        # 鼠标点击时也更新
        self.time_window_slider.sliderPressed.connect(self._on_slider_pressed)
        self.time_window_slider.setEnabled(False)  # 初始禁用
        second_row.addWidget(self.time_window_slider)
        
        # 右箭头按钮（支持长按）
        self.slider_right_btn = QPushButton("►")
        self.slider_right_btn.setMaximumWidth(40)
        self.slider_right_btn.setFont(btn_font)
        self.slider_right_btn.pressed.connect(lambda: self._on_slider_button_pressed('right'))
        self.slider_right_btn.released.connect(self._on_slider_button_released)
        self.slider_right_btn.setEnabled(False)  # 初始禁用
        second_row.addWidget(self.slider_right_btn)
        
        control_layout.addLayout(second_row)
        control_layout.addStretch()
        layout.addWidget(control_group)
        
        # 第三列：文件信息
        info_group = QGroupBox("文件信息")
        # 使用setFont设置字体大小，而不是样式表，以保持主题响应
        info_group.setFont(get_app_font(9))
        info_layout = QVBoxLayout(info_group)
        info_group.setMaximumWidth(150)  # 保持左右宽度限制不变
        info_group.setMaximumHeight(120)
        self.load_file_info_text = QTextEdit()
        self.load_file_info_text.setReadOnly(True)
        self.load_file_info_text.setFont(QFont("Consolas", 8))
        info_layout.addWidget(self.load_file_info_text)
        
        layout.addWidget(info_group)
        
        layout.addStretch()  # 添加stretch让三个group靠左排列
        
        self.config_tabs.addTab(tab, "文件加载")
    
    def _create_special_features_tab(self):
        """创建特殊功能选项卡"""
        tab = QWidget()
        tab.setMinimumHeight(80)
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 信道呼吸能量计算按钮
        breathing_adaptive_group = QGroupBox("呼吸估计")
        breathing_adaptive_group.setFont(get_app_font(9))
        breathing_adaptive_layout = QVBoxLayout(breathing_adaptive_group)
        breathing_adaptive_group.setMaximumHeight(100)
        breathing_adaptive_group.setMaximumWidth(250)
        
        self.breathing_adaptive_btn = QPushButton("信道呼吸能量计算")
        self.breathing_adaptive_btn.setToolTip("配置信道呼吸能量计算功能")
        self.breathing_adaptive_btn.clicked.connect(self._open_breathing_adaptive_dialog)
        breathing_adaptive_layout.addWidget(self.breathing_adaptive_btn)
        
        layout.addWidget(breathing_adaptive_group)
        layout.addStretch()
        
        self.config_tabs.addTab(tab, "特殊功能")
    
    def _open_breathing_adaptive_dialog(self):
        """打开信道呼吸能量计算设置对话框"""
        # 在文件加载模式下禁用
        if self.is_loaded_mode:
            QMessageBox.information(
                self,
                "功能不可用",
                "信道呼吸能量计算功能在文件加载模式下暂时不可用。\n请切换到实时模式使用此功能。"
            )
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("信道呼吸能量计算设置")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(400)
        
        layout = QVBoxLayout(dialog)
        
        # 启用信道的呼吸能量计算
        enable_layout = QHBoxLayout()
        self.breathing_adaptive_enable_checkbox = QCheckBox("启用信道的呼吸能量计算")
        self.breathing_adaptive_enable_checkbox.setChecked(self.breathing_adaptive_enabled)
        self.breathing_adaptive_enable_checkbox.stateChanged.connect(self._on_adaptive_enable_changed)
        enable_layout.addWidget(self.breathing_adaptive_enable_checkbox)
        layout.addLayout(enable_layout)
        
        # 选择前N个信道
        top_n_layout = QHBoxLayout()
        top_n_label = QLabel("选择前N个最高能量信道:")
        top_n_layout.addWidget(top_n_label)
        self.breathing_adaptive_top_n_spinbox = QSpinBox()
        self.breathing_adaptive_top_n_spinbox.setMinimum(1)
        self.breathing_adaptive_top_n_spinbox.setMaximum(10)
        self.breathing_adaptive_top_n_spinbox.setValue(self.breathing_adaptive_top_n)
        self.breathing_adaptive_top_n_spinbox.setEnabled(self.breathing_adaptive_enabled)
        top_n_layout.addWidget(self.breathing_adaptive_top_n_spinbox)
        top_n_layout.addStretch()
        layout.addLayout(top_n_layout)
        
        # 高亮最高能量波形
        highlight_layout = QHBoxLayout()
        self.breathing_adaptive_highlight_checkbox = QCheckBox("高亮最高能量波形")
        self.breathing_adaptive_highlight_checkbox.setChecked(self.breathing_adaptive_highlight)
        self.breathing_adaptive_highlight_checkbox.setEnabled(self.breathing_adaptive_enabled)
        highlight_layout.addWidget(self.breathing_adaptive_highlight_checkbox)
        layout.addLayout(highlight_layout)
        
        # 在最高能量信道上执行呼吸监测
        auto_switch_layout = QHBoxLayout()
        self.breathing_adaptive_auto_switch_checkbox = QCheckBox("在最高能量信道上执行呼吸监测")
        self.breathing_adaptive_auto_switch_checkbox.setChecked(self.breathing_adaptive_auto_switch)
        # 在手动模式下禁用此checkbox
        self.breathing_adaptive_auto_switch_checkbox.setEnabled(self.breathing_adaptive_enabled and not self.breathing_adaptive_manual_control)
        self.breathing_adaptive_auto_switch_checkbox.stateChanged.connect(self._on_adaptive_auto_switch_changed)
        auto_switch_layout.addWidget(self.breathing_adaptive_auto_switch_checkbox)
        layout.addLayout(auto_switch_layout)
        
        # 只在显示信道范围内选取
        only_display_layout = QHBoxLayout()
        self.breathing_adaptive_only_display_checkbox = QCheckBox("只在显示信道范围内选取")
        self.breathing_adaptive_only_display_checkbox.setToolTip("勾选后，只在当前显示的信道中选取最高能量信道；未勾选时，如果最高能量信道不在显示范围内，会自动添加到显示中")
        self.breathing_adaptive_only_display_checkbox.setChecked(self.breathing_adaptive_only_display_channels)
        self.breathing_adaptive_only_display_checkbox.setEnabled(self.breathing_adaptive_enabled)
        only_display_layout.addWidget(self.breathing_adaptive_only_display_checkbox)
        layout.addLayout(only_display_layout)
        
        # 低能量超时时长
        timeout_layout = QHBoxLayout()
        timeout_label = QLabel("低能量超时时长(秒):")
        timeout_label.setToolTip("当信道能量占比连续低于阈值达到此时长后，将重新选择最高能量信道")
        timeout_layout.addWidget(timeout_label)
        self.breathing_adaptive_timeout_spinbox = QSpinBox()
        self.breathing_adaptive_timeout_spinbox.setMinimum(1)
        self.breathing_adaptive_timeout_spinbox.setMaximum(60)
        self.breathing_adaptive_timeout_spinbox.setValue(int(self.adaptive_low_energy_threshold))
        self.breathing_adaptive_timeout_spinbox.setEnabled(self.breathing_adaptive_enabled)
        self.breathing_adaptive_timeout_spinbox.setSuffix(" 秒")
        timeout_layout.addWidget(self.breathing_adaptive_timeout_spinbox)
        timeout_layout.addStretch()
        layout.addLayout(timeout_layout)
        
        # 提示信息（文件加载模式下不可用）
        if self.is_loaded_mode:
            info_label = QLabel("注意：此功能在文件加载模式下暂时不可用")
            info_label.setStyleSheet("color: orange; font-weight: bold;")
            layout.addWidget(info_label)
        
        layout.addStretch()
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.breathing_adaptive_enabled = self.breathing_adaptive_enable_checkbox.isChecked()
            self.breathing_adaptive_top_n = self.breathing_adaptive_top_n_spinbox.value()
            self.breathing_adaptive_highlight = self.breathing_adaptive_highlight_checkbox.isChecked()
            self.breathing_adaptive_auto_switch = self.breathing_adaptive_auto_switch_checkbox.isChecked()
            self.breathing_adaptive_only_display_channels = self.breathing_adaptive_only_display_checkbox.isChecked()
            self.adaptive_low_energy_threshold = float(self.breathing_adaptive_timeout_spinbox.value())
            
            # 更新BreathingEstimator的配置
            self.breathing_estimator.set_adaptive_config(
                enabled=self.breathing_adaptive_enabled,
                top_n=self.breathing_adaptive_top_n,
                only_display_channels=self.breathing_adaptive_only_display_channels,
                low_energy_threshold=self.adaptive_low_energy_threshold
            )
            
            # 如果禁用了自适应，重置相关状态
            if not self.breathing_adaptive_enabled:
                self.breathing_estimator.reset_adaptive_state()
                # 清除高亮
                self._clear_adaptive_highlight()
            
            # 更新channel combo的启用状态
            self._update_channel_combo_enabled()
            # 更新"在最高能量信道上执行呼吸监测"checkbox的启用状态（在手动模式下禁用）
            # 注意：只在对话框打开时更新，对话框关闭后不访问对话框内的控件
            try:
                if hasattr(self, 'breathing_adaptive_auto_switch_checkbox') and self.breathing_adaptive_auto_switch_checkbox is not None:
                    # 检查对象是否仍然有效（通过尝试访问一个属性）
                    _ = self.breathing_adaptive_auto_switch_checkbox.isEnabled()
                    self.breathing_adaptive_auto_switch_checkbox.setEnabled(
                        self.breathing_adaptive_enabled and not self.breathing_adaptive_manual_control
                    )
            except (RuntimeError, AttributeError):
                # 对话框已关闭，checkbox已被销毁，忽略错误
                pass
            # 更新手动选择按钮的状态
            self._update_manual_select_btn_state()
    
    def _on_adaptive_enable_changed(self, state):
        """当启用信道的呼吸能量计算checkbox状态改变时"""
        enabled = (state == Qt.CheckState.Checked.value)
        # 更新内部状态（对话框内的checkbox状态改变时，也需要更新内部状态）
        self.breathing_adaptive_enabled = enabled
        # 注意：只在对话框打开时更新对话框内的控件，对话框关闭后不访问
        try:
            self.breathing_adaptive_top_n_spinbox.setEnabled(enabled)
            self.breathing_adaptive_highlight_checkbox.setEnabled(enabled)
            # "在最高能量信道上执行呼吸监测"checkbox在手动模式下禁用
            if hasattr(self, 'breathing_adaptive_auto_switch_checkbox') and self.breathing_adaptive_auto_switch_checkbox is not None:
                _ = self.breathing_adaptive_auto_switch_checkbox.isEnabled()
                self.breathing_adaptive_auto_switch_checkbox.setEnabled(enabled and not self.breathing_adaptive_manual_control)
            self.breathing_adaptive_only_display_checkbox.setEnabled(enabled)
            if hasattr(self, 'breathing_adaptive_timeout_spinbox'):
                if self.breathing_adaptive_timeout_spinbox is not None:
                    _ = self.breathing_adaptive_timeout_spinbox.isEnabled()
                    self.breathing_adaptive_timeout_spinbox.setEnabled(enabled)
        except (RuntimeError, AttributeError):
            # 对话框已关闭，控件已被销毁，忽略错误
            pass
        # 更新"自适应"checkbox的启用状态（只有在开启能量计算后才启用）
        if hasattr(self, 'breathing_adaptive_manual_checkbox'):
            self.breathing_adaptive_manual_checkbox.setEnabled(
                enabled and not self.is_direction_estimation_mode
            )
        # 更新手动选择按钮的状态
        self._update_manual_select_btn_state()
    
    def _on_adaptive_auto_switch_changed(self, state):
        """当在最高能量信道上执行呼吸监测checkbox状态改变时"""
        self.breathing_adaptive_auto_switch = (state == Qt.CheckState.Checked.value)
        # 如果启用了在最高能量信道上执行呼吸监测，自动勾选工具栏的自适应
        if self.breathing_adaptive_auto_switch:
            if not self.breathing_adaptive_manual_control:
                self.breathing_adaptive_manual_control = True
                if hasattr(self, 'breathing_adaptive_manual_checkbox'):
                    self.breathing_adaptive_manual_checkbox.setChecked(True)
            # 退出手动选择模式
            self.manual_select_mode = False
            self.manual_selected_channel = None
        # 更新手动选择按钮的状态
        self._update_manual_select_btn_state()
    
    def _clear_adaptive_highlight(self):
        """清除自适应高亮"""
        for tab_key, plotter_info in self.plotters.items():
            plotter = plotter_info.get('plotter')
            if plotter and hasattr(plotter, 'highlight_best_channels'):
                plotter.highlight_best_channels([], False)
    
    def _create_settings_tab(self):
        """创建设置选项卡"""
        tab = QWidget()
        tab.setMinimumHeight(80)  # 设置最小高度，保持等高
        layout = QHBoxLayout(tab)  # 两列横向布局，靠左排列
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 左列：主题设置
        theme_group = QGroupBox("主题设置")
        # 使用setFont设置字体大小，而不是样式表，以保持主题响应
        theme_group.setFont(get_app_font(9))
        theme_layout = QVBoxLayout(theme_group)
        theme_group.setMaximumHeight(120)
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
        
        # 中列：显示控制（分成两列）
        display_group = QGroupBox("显示控制")
        display_group.setFont(get_app_font(9))
        display_group.setMaximumHeight(120)
        display_group.setMaximumWidth(500)  # 增加宽度以容纳两列
        
        display_main_layout = QHBoxLayout(display_group)  # 主布局为水平布局
        display_main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 左列
        display_left_layout = QVBoxLayout()
        
        # 日志显示控制
        self.show_log_checkbox = QCheckBox("日志")
        self.show_log_checkbox.setChecked(self.show_log)
        self.show_log_checkbox.stateChanged.connect(self._on_show_log_changed)
        display_left_layout.addWidget(self.show_log_checkbox)
        
        # 版本信息显示控制
        self.show_version_info_checkbox = QCheckBox("版本信息")
        self.show_version_info_checkbox.setChecked(self.show_version_info)
        self.show_version_info_checkbox.stateChanged.connect(self._on_show_version_info_changed)
        display_left_layout.addWidget(self.show_version_info_checkbox)
        
        display_left_layout.addStretch()
        display_main_layout.addLayout(display_left_layout)
        
        # 右列：工具栏显示控制
        display_right_layout = QVBoxLayout()
        
        # 工具栏显示控制（三态checkbox，可以显示部分选中状态）
        self.show_toolbar_checkbox = QCheckBox("工具栏")
        self.show_toolbar_checkbox.setTristate(True)  # 启用三态模式
        self.show_toolbar_checkbox.setChecked(self.show_toolbar)
        self.show_toolbar_checkbox.stateChanged.connect(self._on_show_toolbar_changed)
        display_right_layout.addWidget(self.show_toolbar_checkbox)
        
        # 工具栏子项控制（嵌套在工具栏控制下）
        toolbar_sub_layout = QVBoxLayout()
        toolbar_sub_layout.setContentsMargins(20, 0, 0, 0)  # 缩进显示
        
        self.show_breathing_control_checkbox = QCheckBox("呼吸控制")
        self.show_breathing_control_checkbox.setFont(get_app_font(8))
        # 使用样式表缩小checkbox框的尺寸，使其与字体大小匹配
        self.show_breathing_control_checkbox.setStyleSheet(
            "QCheckBox::indicator { width: 12px; height: 12px; }"
        )
        self.show_breathing_control_checkbox.setChecked(self.show_breathing_control)
        self.show_breathing_control_checkbox.stateChanged.connect(self._on_show_breathing_control_changed)
        # 子项状态改变时，更新父checkbox的状态
        self.show_breathing_control_checkbox.stateChanged.connect(self._update_toolbar_checkbox_state)
        self.show_breathing_control_checkbox.setEnabled(self.show_toolbar)  # 只有工具栏显示时才启用
        toolbar_sub_layout.addWidget(self.show_breathing_control_checkbox)
        
        self.show_send_command_checkbox = QCheckBox("发送指令")
        self.show_send_command_checkbox.setFont(get_app_font(8))
        # 使用样式表缩小checkbox框的尺寸，使其与字体大小匹配
        self.show_send_command_checkbox.setStyleSheet(
            "QCheckBox::indicator { width: 12px; height: 12px; }"
        )
        self.show_send_command_checkbox.setChecked(self.show_send_command)
        self.show_send_command_checkbox.stateChanged.connect(self._on_show_send_command_changed)
        # 子项状态改变时，更新父checkbox的状态
        self.show_send_command_checkbox.stateChanged.connect(self._update_toolbar_checkbox_state)
        self.show_send_command_checkbox.setEnabled(self.show_toolbar)  # 只有工具栏显示时才启用
        toolbar_sub_layout.addWidget(self.show_send_command_checkbox)
        
        display_right_layout.addLayout(toolbar_sub_layout)
        display_right_layout.addStretch()
        display_main_layout.addLayout(display_right_layout)
        
        layout.addWidget(display_group)
        
        # 右列：关于信息
        about_group = QGroupBox("关于")
        # 使用setFont设置字体大小，而不是样式表，以保持主题响应
        about_group.setFont(get_app_font(9))
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
        about_group.setMaximumHeight(120)  # 限制高度，内容可滚动
        about_group.setMaximumWidth(350)  # 减小宽度以容纳显示控制
        about_layout.addWidget(about_text)
        layout.addWidget(about_group)
        
        layout.addStretch()  # 添加stretch让内容靠左
        
        # 初始化工具栏checkbox的状态（根据子项的初始状态）
        if hasattr(self, 'show_toolbar_checkbox'):
            self._update_toolbar_checkbox_state()
        
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
            tab_index = self.plot_tabs.addTab(plotter.get_widget(), tab_name)
            
            # 为特定tab设置tooltip
            if tab_key == 'amplitude' or tab_key == 'phase':
                self.plot_tabs.setTabToolTip(tab_index, "合并双方的测量结果，显示合并后的幅值和相位")
            if tab_key == 'local_amplitude' or tab_key == 'local_phase':
                self.plot_tabs.setTabToolTip(tab_index, "reflector向initiator发射信号，并由后者对信号采样")
            if tab_key == 'remote_amplitude' or tab_key == 'remote_phase':
                self.plot_tabs.setTabToolTip(tab_index, "initiator向reflector发射信号，并由前者对信号采样")

            # 保存引用
            self.plotters[tab_key] = {
                'plotter': plotter,
                'data_type': data_type
            }
        
        # 创建滤波波形选项卡（使用 PyQtGraph，用于显示滤波后的信号）
        plotter = RealtimePlotter(
            title='BLE Channel Sounding - 滤波波形',
            x_label='Frame Index',
            y_label='Filtered Signal'
        )
        plotter.plot_widget.sigRangeChanged.connect(self._on_plot_view_changed)
        tab_index = self.plot_tabs.addTab(plotter.get_widget(), "滤波波形")
        self.plot_tabs.setTabToolTip(tab_index, "显示中值滤波、高通滤波、带通滤波后的信号波形")
        self.plotters['filtered_signal'] = {
            'plotter': plotter,
            'data_type': 'filtered_signal'  # 特殊类型，不直接从data_processor获取
        }
        
        # 创建呼吸估计选项卡（使用 Matplotlib）
        self._create_breathing_estimation_tab()
        
        # 根据当前帧类型初始化tab的启用状态
        self._update_plot_tabs_enabled_state()
        
        # 初始化DF模式幅值类型选项状态
        if hasattr(self, 'df_amplitude_type_combo'):
            self._update_df_amplitude_type_enabled()
    
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
    
    def _create_log_panel(self, parent_splitter):
        """创建日志面板"""
        self.log_group = QGroupBox("日志")
        layout = QVBoxLayout(self.log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        
        # 设置日志处理器
        text_handler = TextHandler(self.log_text)
        text_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(text_handler)
        
        parent_splitter.addWidget(self.log_group)
    
    def _create_version_info(self, parent_layout):
        """创建版本信息"""
        self.version_label = QLabel(f"v{__version__} build.{__version_date__}")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.version_label.setStyleSheet("color: gray; font-size: 8pt;")
        parent_layout.addWidget(self.version_label)
    
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
                self.connect_btn.setStyleSheet(self._get_button_style("#f44336"))
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
                
                # 更新文件加载tab状态（连接时禁用文件加载功能）
                self._update_load_tab_state()
                
                # 如果启用了自动开始记录，等待有数据后自动开始
                if self.auto_start_recording_enabled and self.frame_mode:
                    # 延迟检查，等待第一帧数据到达
                    QTimer.singleShot(1000, self._check_and_auto_start_recording)
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
            self.connect_btn.setStyleSheet(self._get_button_style("#4CAF50"))
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
            
            # 重置呼吸信道列表初始化标志，以便下次连接时重新初始化
            self.breathing_channels_initialized = False
            
            # 更新文件加载tab状态（断开连接后，如果未加载文件，则启用文件加载功能）
            self._update_load_tab_state()
            
            # 如果正在记录，停止记录
            if self.is_recording:
                self._stop_recording()
    
    def _on_frame_type_changed(self, text):
        """帧类型改变"""
        old_frame_type = self.frame_type
        self.frame_type = text
        old_frame_mode = self.frame_mode
        old_is_direction_mode = self.is_direction_estimation_mode
        
        self.frame_mode = (self.frame_type == "信道探测帧" or self.frame_type == "方向估计帧")
        self.is_direction_estimation_mode = (self.frame_type == "方向估计帧")
        
        self.logger.info(f"帧类型已设置为: {self.frame_type}, 方向估计模式: {self.is_direction_estimation_mode}")
        
        # 根据帧类型更新呼吸估计器的默认参数
        if hasattr(self, 'breathing_estimator'):
            self._update_breathing_params_from_frame_type()
        
        # 如果切换到方向估计帧模式，需要更新tab的启用状态
        if old_is_direction_mode != self.is_direction_estimation_mode:
            self._update_plot_tabs_enabled_state()
            
            # 更新显示帧数设置
            if self.is_direction_estimation_mode:
                # DF模式：设置默认显示帧数为1000
                self.display_max_frames = config.df_default_display_max_frames
                if hasattr(self, 'display_max_frames_entry'):
                    self.display_max_frames_entry.setText(str(config.df_default_display_max_frames))
                self.logger.info("切换到方向估计帧模式 - 清空之前的数据，显示帧数设置为1000")
            else:
                # CS模式：恢复默认显示帧数
                self.display_max_frames = config.default_display_max_frames
                if hasattr(self, 'display_max_frames_entry'):
                    self.display_max_frames_entry.setText(str(config.default_display_max_frames))
                self.logger.info("切换到非方向估计帧模式 - 清空之前的数据，显示帧数恢复为50")
            
            # 清空数据
            if self.is_direction_estimation_mode:
                self.data_processor.clear_buffer(clear_frames=True)
                for plotter_info in self.plotters.values():
                    plotter = plotter_info.get('plotter')
                    if plotter is not None:
                        plotter.clear_plot()
                self.data_parser.clear_buffer()
            elif old_is_direction_mode:
                self.data_processor.clear_buffer(clear_frames=True)
                for plotter_info in self.plotters.values():
                    plotter = plotter_info.get('plotter')
                    if plotter is not None:
                        plotter.clear_plot()
                self.data_parser.clear_buffer()
    
    def _update_plot_tabs_enabled_state(self):
        """根据帧类型更新plot tabs的启用状态"""
        # 在方向估计帧模式下，只启用幅值tab，禁用其他tab
        tab_configs = [
            ('amplitude', 0),
            ('phase', 1),
            ('local_amplitude', 2),
            ('local_phase', 3),
            ('remote_amplitude', 4),
            ('remote_phase', 5),
        ]
        
        for tab_key, tab_index in tab_configs:
            if tab_key in self.plotters:
                # 方向估计帧模式下，只启用幅值tab
                enabled = not self.is_direction_estimation_mode or (tab_key == 'amplitude')
                self.plot_tabs.setTabEnabled(tab_index, enabled)
                
                # 如果当前tab被禁用，切换到幅值tab
                if not enabled and self.plot_tabs.currentIndex() == tab_index:
                    self.plot_tabs.setCurrentIndex(0)  # 切换到幅值tab
        
        # 更新plot tab标题
        self._update_plot_tab_titles()
        
        # 更新DF模式幅值类型选项状态
        if hasattr(self, 'df_amplitude_type_combo'):
            self._update_df_amplitude_type_enabled()
    
    def _update_plot_tab_titles(self):
        """根据帧类型更新plot tab标题"""
        if 'amplitude' in self.plotters:
            plotter = self.plotters['amplitude']['plotter']
            if plotter:
                if self.is_direction_estimation_mode:
                    plotter.set_title('BLE Direction Finding - 幅值')
                else:
                    plotter.set_title('BLE Channel Sounding - 幅值')
    
    def _update_df_amplitude_type_enabled(self):
        """更新DF模式幅值类型选项的启用状态"""
        if hasattr(self, 'df_amplitude_type_combo') and hasattr(self, 'df_amplitude_type_label'):
            enabled = self.is_direction_estimation_mode
            self.df_amplitude_type_combo.setEnabled(enabled)
            self.df_amplitude_type_label.setEnabled(enabled)
    
    def _on_df_amplitude_type_changed(self, text):
        """DF模式幅值类型改变时的回调"""
        if not self.is_direction_estimation_mode:
            return
        
        self.logger.info(f"DF模式幅值类型已设置为: {text}")
        
        # 更新y轴标签
        if 'amplitude' in self.plotters:
            plotter = self.plotters['amplitude']['plotter']
            if plotter:
                if text == "功率P":
                    plotter.plot_widget.setLabel('left', 'Power (P)')
                else:
                    plotter.plot_widget.setLabel('left', 'Amplitude (√P)')
        
        # 触发绘图更新
        if self.frame_mode:
            self._update_frame_plots('amplitude')
    
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
            # 检查是否是命令反馈（$OK, $ERR, $EVT）
            # 在帧数据解析之前检查，但反馈识别不影响帧数据处理
            if data.get('text'):
                response = self.command_sender.parse_response(data['text'])
                if response:
                    # 是命令反馈，添加到交互历史
                    if hasattr(self, 'command_history'):
                        self._add_response_to_history(response)
                    # 反馈识别后继续处理其他数据（如帧数据）
            
            # 如果是帧模式，优先处理帧数据
            if self.frame_mode:
                # 解析数据（会更新内部状态，累积IQ数据）
                parsed = self.data_parser.parse(data['text'])
                
                # 如果parse返回了完成的帧（检测到帧尾时完成，或方向估计帧单行完成）
                if parsed and parsed.get('frame'):
                    frame_data = parsed
                    if len(frame_data.get('channels', {})) > 0:
                        # 只在处理第一批数据时打印详细信息，避免日志过多
                        if frames_processed == 0:
                            channels = sorted(frame_data['channels'].keys())
                            if self.is_direction_estimation_mode:
                                self.logger.info(
                                    f"[方向估计帧] seq={frame_data['index']}, "
                                    f"timestamp={frame_data['timestamp_ms']}ms, "
                                    f"信道={channels[0] if channels else 'N/A'}, "
                                    f"幅值={list(frame_data['channels'].values())[0].get('amplitude', 0):.2f}"
                                )
                            else:
                                self.logger.info(
                                    f"[帧完成] index={frame_data['index']}, "
                                    f"timestamp={frame_data['timestamp_ms']}ms, "
                                    f"通道数={len(channels)}, "
                                    f"通道范围={channels[0]}-{channels[-1] if channels else 'N/A'}"
                                )
                        
                        # 添加帧数据，DF模式需要检测信道变化
                        cleared_channels = self.data_processor.add_frame_data(
                            frame_data, 
                            detect_channel_change=self.is_direction_estimation_mode
                        )
                        
                        # 如果正在记录，自动追加帧到日志
                        if self.is_recording and self.data_saver.log_writer and self.data_saver.log_writer.is_running:
                            self.data_saver.append_frame_to_log(frame_data)
                        
                        # 如果检测到信道变化并清空了数据，需要重置呼吸估计状态
                        if cleared_channels and self.is_direction_estimation_mode:
                            # cleared_channels 是 (old_channels, new_channels) 元组
                            if isinstance(cleared_channels, tuple) and len(cleared_channels) == 2:
                                old_channels_list, new_channels_list = cleared_channels
                                old_channel = old_channels_list[0] if old_channels_list else None
                                new_channel = new_channels_list[0] if new_channels_list else None
                            else:
                                # 兼容旧格式（如果返回的是列表）
                                new_channel = cleared_channels[0] if cleared_channels else None
                                old_channel = self.last_breathing_channel
                            
                            # 如果新信道存在，更新状态
                            if new_channel is not None:
                                # 重置呼吸估计状态
                                self.breathing_estimator.reset_adaptive_state()
                                
                                # 在结果框中显示提示
                                if hasattr(self, 'breathing_result_text'):
                                    old_channel_display = old_channel if old_channel is not None else 'N/A'
                                    self.breathing_result_text.setPlainText(
                                        f"⚠️ 信道已切换: {old_channel_display} -> {new_channel}\n"
                                        f"已清空累积数据，重新开始累积时间窗\n"
                                        f"当前信道: {new_channel}\n"
                                        f"等待数据积累: 0/{self.display_max_frames} 帧"
                                    )
                                
                                # 更新上次使用的信道（设置为新信道，用于后续检测）
                                self.last_breathing_channel = new_channel
                                
                                self.logger.info(
                                    f"[呼吸估计] 检测到信道变化: {old_channel_display} -> {new_channel}，"
                                    f"已重置呼吸估计状态，等待新信道数据积累到 {self.display_max_frames} 帧"
                                )
                        
                        frames_processed += 1
                        has_new_frame = True
                        
                        # 方向估计帧模式下，自动更新display_channel_list为实际接收到的信道
                        # 注意：这仅用于显示，不影响实际的信道切换检测（信道切换检测在add_frame_data中完成）
                        if self.is_direction_estimation_mode:
                            channels = sorted(frame_data['channels'].keys())
                            if channels and (not self.display_channel_list or self.display_channel_list != channels):
                                self.display_channel_list = channels
                                # 更新显示信道输入框（仅用于显示，不影响信道切换检测）
                                if hasattr(self, 'display_channels_entry'):
                                    self.display_channels_entry.setText(','.join(str(ch) for ch in channels))
                                self.logger.debug(f"[方向估计帧] 自动更新显示信道列表: {channels}（仅用于显示）")
                            
                            # 方向估计帧模式下，更新呼吸估计的信道显示
                            # 注意：这里只更新显示，不触发信道变化检测（信道变化检测已在add_frame_data中完成）
                            if channels and hasattr(self, 'breathing_channel_combo'):
                                current_channel = channels[0]  # 方向估计帧只有一个信道
                                current_text = self.breathing_channel_combo.currentText()
                                if current_text != str(current_channel):
                                    self.breathing_channel_combo.clear()
                                    self.breathing_channel_combo.addItem(str(current_channel))
                                    self.breathing_channel_combo.setCurrentText(str(current_channel))
                        
                        # 更新呼吸估计的信道列表（只在第一次收到帧数据时更新，避免频繁操作）
                        # 方向估计帧模式下已在上面处理
                        if not self.is_direction_estimation_mode and not self.breathing_channels_initialized and hasattr(self, 'breathing_channel_combo'):
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
                                self.breathing_channels_initialized = True
                
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
                # 实时更新滤波波形（不需要等待时间窗）
                self._update_realtime_filtered_signal()
                
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
        """
        应用帧模式设置
        
        注意：
        - display_channel_list 仅用于控制显示哪些信道，不影响实际的信道切换检测
        - 信道切换检测基于实际接收到的帧数据中的信道（在data_processor.add_frame_data中完成）
        - display_max_frames 用于控制呼吸估计需要累积的帧数（可配置）
        """
        # 根据帧类型确定最大帧数限制和默认值
        if self.is_direction_estimation_mode:
            max_frames_limit = config.df_max_display_max_frames
            default_frames = config.df_default_display_max_frames
        else:
            max_frames_limit = config.max_display_max_frames
            default_frames = config.default_display_max_frames
        
        # 解析展示帧数（用于呼吸估计需要累积的帧数）
        try:
            display_frames = int(self.display_max_frames_entry.text())
            if display_frames > 0:
                self.display_max_frames = min(display_frames, max_frames_limit)
                self.logger.info(f"显示帧数设置为: {self.display_max_frames}（呼吸估计需要累积的帧数）")
            else:
                self.logger.warning(f"显示帧数必须大于0，使用默认值{default_frames}")
                self.display_max_frames = default_frames
                self.display_max_frames_entry.setText(str(default_frames))
        except ValueError:
            self.logger.warning(f"显示帧数无效，使用默认值{default_frames}")
            self.display_max_frames = default_frames
            self.display_max_frames_entry.setText(str(default_frames))
        
        # 根据选择的模式解析展示信道（仅用于显示，不影响信道切换检测）
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
        self.logger.info(f"展示信道设置为: {self.display_channel_list} (模式: {mode})（仅用于显示，不影响信道切换检测）")
        
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
        
        # 确定帧类型（用于文件名前缀）- 根据当前模式判断，而不是帧数据
        # 这样可以确保切换模式后保存的文件名正确
        if self.is_direction_estimation_mode:
            frame_type = 'direction_estimation'
        else:
            frame_type = 'channel_sounding'
        
        # 在保存前获取frames的引用（不复制，避免大文件时占用过多内存）
        # 注意：在后台线程中保存时，会进行深拷贝，所以这里不需要复制
        
        # 根据设置决定是否弹出对话框（使用JSONL格式）
        if self.use_auto_save:
            filepath = self.data_saver.get_auto_save_path(prefix="frames", save_all=True, frame_type=frame_type, use_jsonl=True)
            self.logger.info(f"使用自动保存路径: {filepath}")
        else:
            default_filename = self.data_saver.get_default_filename(prefix="frames", save_all=True, frame_type=frame_type, use_jsonl=True)
            filepath, _ = QFileDialog.getSaveFileName(
                self, "保存所有帧数据", default_filename,
                "JSONL文件 (*.jsonl);;JSON文件 (*.json);;所有文件 (*.*)"
            )
            if not filepath:
                return
            # 如果用户选择了.json文件，自动改为.jsonl
            if filepath.endswith('.json'):
                filepath = filepath[:-5] + '.jsonl'
        
        # 获取串口信息（用于meta记录）
        serial_port = None
        serial_baud = None
        if hasattr(self, 'port_combo') and self.port_combo.currentData():
            serial_port = self.port_combo.currentData()
        if hasattr(self, 'baudrate_combo'):
            serial_baud = self.baudrate_combo.currentText()
        
        # 在后台线程中执行保存操作（使用新的JSONL增量写入方式）
        def save_in_thread():
            try:
                self.is_saving = True
                # 通过信号在主线程中更新状态
                self.save_status_update_signal.emit(f"正在保存 {len(frames)} 帧数据...", "color: black;")
                
                # 启动日志会话
                if not self.data_saver.start_log_session(filepath, frame_type, serial_port, serial_baud):
                    self.save_error_signal.emit("启动日志会话失败")
                    return
                
                # 增量写入所有帧
                saved_count = 0
                total_frames = len(frames)
                for i, frame in enumerate(frames):
                    if self.data_saver.append_frame_to_log(frame):
                        saved_count += 1
                    # 每1000帧更新一次进度
                    if (i + 1) % 1000 == 0 or (i + 1) == total_frames:
                        progress_pct = ((i + 1) / total_frames * 100) if total_frames > 0 else 0
                        self.save_status_update_signal.emit(
                            f"正在保存 {i + 1}/{total_frames} 帧 ({progress_pct:.1f}%)...", 
                            "color: black;"
                        )
                
                # 停止会话
                stats = self.data_saver.stop_log_session()
                
                if saved_count > 0:
                    # 显示简洁的保存信息（只显示文件名）
                    filename = os.path.basename(filepath)
                    # 通过信号在主线程中更新UI和显示InfoBar
                    self.save_success_signal.emit(saved_count, filename)
                else:
                    # 通过信号在主线程中显示错误提示
                    self.save_error_signal.emit("保存失败：没有成功写入任何帧")
            except MemoryError as e:
                self.logger.error(f"保存数据时内存不足: {e}", exc_info=True)
                error_msg = f"保存失败: 内存不足，请尝试保存更少的数据或关闭其他程序"
                self.save_error_signal.emit(error_msg)
                # 确保停止会话
                try:
                    self.data_saver.stop_log_session()
                except:
                    pass
            except IOError as e:
                self.logger.error(f"保存数据时IO错误: {e}", exc_info=True)
                error_msg = f"保存失败: 文件写入错误 - {str(e)}"
                self.save_error_signal.emit(error_msg)
                # 确保停止会话
                try:
                    self.data_saver.stop_log_session()
                except:
                    pass
            except Exception as e:
                self.logger.error(f"保存数据时出错: {e}", exc_info=True)
                error_msg = f"保存失败: {str(e)}"
                # 通过信号在主线程中显示错误提示
                self.save_error_signal.emit(error_msg)
                # 确保停止会话
                try:
                    self.data_saver.stop_log_session()
                except:
                    pass
            finally:
                self.is_saving = False
        
        import threading
        # 使用非daemon线程，确保保存操作完成
        # 但设置较短的超时时间，避免阻塞主程序
        save_thread = threading.Thread(target=save_in_thread, daemon=False, name="SaveThread")
        save_thread.start()
        
        # 保存线程引用，防止被垃圾回收
        if not hasattr(self, '_save_threads'):
            self._save_threads = []
        self._save_threads.append(save_thread)
        
        # 清理旧的已完成线程（避免内存泄漏）
        self._save_threads = [t for t in self._save_threads if t.is_alive()]
        
        # 限制保存线程数量，避免创建过多线程
        if len(self._save_threads) > 5:
            # 等待最旧的线程完成
            oldest_thread = self._save_threads[0]
            if oldest_thread.is_alive():
                oldest_thread.join(timeout=1.0)  # 最多等待1秒
            self._save_threads = [t for t in self._save_threads if t.is_alive()]
    
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
    
    def _check_and_auto_start_recording(self):
        """检查并自动开始记录（在有数据后）"""
        if not self.is_running or not self.frame_mode:
            return
        
        if not self.auto_start_recording_enabled:
            return
        
        if self.is_recording:
            return
        
        # 检查是否有数据
        frames = self.data_processor.raw_frames
        if not frames or len(frames) == 0:
            # 如果还没有数据，再等一会儿
            QTimer.singleShot(1000, self._check_and_auto_start_recording)
            return
        
        # 有数据了，自动开始记录
        self.logger.info("自动开始记录（检测到数据）")
        self._start_recording()
    
    def _on_auto_start_recording_changed(self, state):
        """自动开始记录复选框变化"""
        checked = (state == Qt.CheckState.Checked.value)
        self.auto_start_recording_enabled = checked
        user_settings.set_auto_start_recording(checked)
        self.logger.info(f"自动开始记录: {'启用' if checked else '禁用'}")
    
    def _start_recording(self):
        """开始记录JSONL"""
        if not self.frame_mode:
            InfoBarHelper.warning(
                self,
                title="无法记录",
                content="当前不是帧模式，无法记录帧数据"
            )
            return
        
        if self.is_recording:
            InfoBarHelper.warning(
                self,
                title="已在记录",
                content="记录已在进行中"
            )
            return
        
        # 确定帧类型
        if self.is_direction_estimation_mode:
            frame_type = 'direction_estimation'
        else:
            frame_type = 'channel_sounding'
        
        # 生成日志文件路径
        if self.use_auto_save:
            log_path = self.data_saver.get_auto_save_path(prefix="frames", save_all=True, frame_type=frame_type, use_jsonl=True)
        else:
            default_filename = self.data_saver.get_default_filename(prefix="frames", save_all=True, frame_type=frame_type, use_jsonl=True)
            log_path, _ = QFileDialog.getSaveFileName(
                self, "开始记录JSONL", default_filename,
                "JSONL文件 (*.jsonl);;所有文件 (*.*)"
            )
            if not log_path:
                return
            # 确保是.jsonl扩展名
            if not log_path.endswith('.jsonl'):
                log_path = log_path + '.jsonl'
        
        # 获取串口信息
        serial_port = None
        serial_baud = None
        if hasattr(self, 'port_combo') and self.port_combo.currentData():
            serial_port = self.port_combo.currentData()
        if hasattr(self, 'baudrate_combo'):
            serial_baud = self.baudrate_combo.currentText()
        
        # 启动日志会话
        if self.data_saver.start_log_session(log_path, frame_type, serial_port, serial_baud):
            self.is_recording = True
            self.current_log_path = log_path
            
            # 更新UI
            self.start_recording_btn.setEnabled(False)
            self.stop_recording_btn.setEnabled(True)
            self.mark_event_btn.setEnabled(True)
            
            filename = os.path.basename(log_path)
            
            # 更新状态栏显示正在记录
            self.save_status_label.setText(f"● 正在记录: {filename}")
            self.save_status_label.setStyleSheet("color: green;")
            
            self.logger.info(f"开始记录JSONL: {log_path}")
            
            # 将已有的帧数据追加到日志（如果有）
            frames = self.data_processor.raw_frames
            if frames:
                self.logger.info(f"将已有的 {len(frames)} 帧追加到日志")
                for frame in frames:
                    self.data_saver.append_frame_to_log(frame)
        else:
            # 更新状态栏显示错误
            self.save_status_label.setText("✗ 启动记录失败")
            self.save_status_label.setStyleSheet("color: red;")
            InfoBarHelper.error(
                self,
                title="启动失败",
                content="无法启动日志会话，请查看日志"
            )
    
    def _stop_recording(self):
        """停止记录JSONL"""
        if not self.is_recording:
            InfoBarHelper.warning(
                self,
                title="未在记录",
                content="当前没有正在进行的记录"
            )
            return
        
        # 停止日志会话
        stats = self.data_saver.stop_log_session()
        written_count = stats.get('written_records', 0)
        dropped_count = stats.get('dropped_records', 0)
        
        log_path = self.current_log_path
        filename = os.path.basename(log_path) if log_path else "未知文件"
        
        # 更新状态
        self.is_recording = False
        self.current_log_path = None
        
        # 更新UI
        self.start_recording_btn.setEnabled(True)
        self.stop_recording_btn.setEnabled(False)
        self.mark_event_btn.setEnabled(False)
        
        # 更新状态栏显示停止记录信息
        # written_count包括meta（1条）和frame记录
        # end记录不计算在write_count中（因为它是直接写入的，不通过队列）
        # 所以frame_count = written_count - 1（减去meta记录）
        if written_count > 1:
            frame_count = written_count - 1  # 减去meta记录
            self.save_status_label.setText(f"✓ 已停止向 {filename} 记录，累计 {frame_count} 帧")
        else:
            # 只有meta记录，没有frame记录
            self.save_status_label.setText(f"✓ 已停止向 {filename} 记录")
        self.save_status_label.setStyleSheet("color: green;")
        
        # 计算实际帧数用于日志
        frame_count = max(0, written_count - 1) if written_count > 1 else 0
        self.logger.info(f"停止记录JSONL: {log_path}, 写入 {written_count} 条记录（其中 {frame_count} 帧）")
    
    def _mark_event(self):
        """标记特殊事件"""
        # 检查是否正在记录
        if not self.is_recording or not self.data_saver.log_writer or not self.data_saver.log_writer.is_running:
            InfoBarHelper.warning(
                self,
                title="无法标记事件",
                content="请先开始记录，然后再标记事件"
            )
            return
        
        # 获取当前最近的帧信息（用于关联）
        nearest_seq = None
        nearest_t_dev_ms = None
        frames = self.data_processor.raw_frames
        if frames:
            last_frame = frames[-1]
            nearest_seq = last_frame.get('index', None)
            nearest_t_dev_ms = last_frame.get('timestamp_ms', None)
        
        # 追加事件记录（使用默认标签"external_spike"，用户可以在未来扩展时添加输入框）
        label = "external_spike"  # 默认事件标签
        success = self.data_saver.append_event_to_log(
            label=label,
            note=None,  # 未来可以添加输入框让用户输入备注
            nearest_seq=nearest_seq,
            nearest_t_dev_ms=nearest_t_dev_ms
        )
        
        if success:
            InfoBarHelper.success(
                self,
                title="事件已标记",
                content=f"已标记事件: {label}"
            )
            self.logger.info(f"已标记事件: {label}, 最近帧: seq={nearest_seq}, t={nearest_t_dev_ms}ms")
        else:
            InfoBarHelper.error(
                self,
                title="标记失败",
                content="事件队列已满，无法标记事件"
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
        
        # 确定帧类型（用于文件名前缀）- 根据当前模式判断，而不是帧数据
        if self.is_direction_estimation_mode:
            frame_type = 'direction_estimation'
        else:
            frame_type = 'channel_sounding'
        
        # 根据设置决定是否弹出对话框（使用JSONL格式）
        if self.use_auto_save:
            filepath = self.data_saver.get_auto_save_path(
                prefix="frames", save_all=False, max_frames=max_frames, frame_type=frame_type, use_jsonl=True
            )
            self.logger.info(f"使用自动保存路径: {filepath}")
        else:
            default_filename = self.data_saver.get_default_filename(
                prefix="frames", save_all=False, max_frames=max_frames, frame_type=frame_type, use_jsonl=True
            )
            filepath, _ = QFileDialog.getSaveFileName(
                self, f"保存最近{max_frames}帧数据", default_filename,
                "JSONL文件 (*.jsonl);;JSON文件 (*.json);;所有文件 (*.*)"
            )
            if not filepath:
                return
            # 如果用户选择了.json文件，自动改为.jsonl
            if filepath.endswith('.json'):
                filepath = filepath[:-5] + '.jsonl'
        
        # 只保存最近的max_frames帧
        frames_to_save = frames[-max_frames:] if len(frames) > max_frames else frames
        saved_count = len(frames_to_save)
        
        # 获取串口信息（用于meta记录）
        serial_port = None
        serial_baud = None
        if hasattr(self, 'port_combo') and self.port_combo.currentData():
            serial_port = self.port_combo.currentData()
        if hasattr(self, 'baudrate_combo'):
            serial_baud = self.baudrate_combo.currentText()
        
        # 在后台线程中执行保存操作（使用新的JSONL增量写入方式）
        def save_in_thread():
            try:
                self.is_saving = True
                # 通过信号在主线程中更新状态
                self.save_status_update_signal.emit(f"正在保存最近 {saved_count} 帧数据...", "color: black;")
                
                # 启动日志会话
                if not self.data_saver.start_log_session(filepath, frame_type, serial_port, serial_baud):
                    self.save_error_signal.emit("启动日志会话失败")
                    return
                
                # 增量写入帧
                actual_saved = 0
                total_frames = len(frames_to_save)
                for i, frame in enumerate(frames_to_save):
                    if self.data_saver.append_frame_to_log(frame):
                        actual_saved += 1
                    # 每1000帧更新一次进度
                    if (i + 1) % 1000 == 0 or (i + 1) == total_frames:
                        progress_pct = ((i + 1) / total_frames * 100) if total_frames > 0 else 0
                        self.save_status_update_signal.emit(
                            f"正在保存 {i + 1}/{total_frames} 帧 ({progress_pct:.1f}%)...", 
                            "color: black;"
                        )
                
                # 停止会话
                stats = self.data_saver.stop_log_session()
                
                if actual_saved > 0:
                    # 显示简洁的保存信息（只显示文件名）
                    filename = os.path.basename(filepath)
                    # 通过信号在主线程中更新UI和显示InfoBar
                    self.save_success_signal.emit(actual_saved, filename)
                else:
                    # 通过信号在主线程中显示错误提示
                    self.save_error_signal.emit("保存失败：没有成功写入任何帧")
            except MemoryError as e:
                self.logger.error(f"保存数据时内存不足: {e}", exc_info=True)
                error_msg = f"保存失败: 内存不足，请尝试保存更少的数据或关闭其他程序"
                self.save_error_signal.emit(error_msg)
                # 确保停止会话
                try:
                    self.data_saver.stop_log_session()
                except:
                    pass
            except IOError as e:
                self.logger.error(f"保存数据时IO错误: {e}", exc_info=True)
                error_msg = f"保存失败: 文件写入错误 - {str(e)}"
                self.save_error_signal.emit(error_msg)
                # 确保停止会话
                try:
                    self.data_saver.stop_log_session()
                except:
                    pass
            except Exception as e:
                self.logger.error(f"保存数据时出错: {e}", exc_info=True)
                error_msg = f"保存失败: {str(e)}"
                # 通过信号在主线程中显示错误提示
                self.save_error_signal.emit(error_msg)
                # 确保停止会话
                try:
                    self.data_saver.stop_log_session()
                except:
                    pass
            finally:
                self.is_saving = False
        
        import threading
        # 使用非daemon线程，确保保存操作完成
        # 但设置较短的超时时间，避免阻塞主程序
        save_thread = threading.Thread(target=save_in_thread, daemon=False, name="SaveThread")
        save_thread.start()
        
        # 保存线程引用，防止被垃圾回收
        if not hasattr(self, '_save_threads'):
            self._save_threads = []
        self._save_threads.append(save_thread)
        
        # 清理旧的已完成线程（避免内存泄漏）
        self._save_threads = [t for t in self._save_threads if t.is_alive()]
        
        # 限制保存线程数量，避免创建过多线程
        if len(self._save_threads) > 5:
            # 等待最旧的线程完成
            oldest_thread = self._save_threads[0]
            if oldest_thread.is_alive():
                oldest_thread.join(timeout=1.0)  # 最多等待1秒
            self._save_threads = [t for t in self._save_threads if t.is_alive()]
    
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
    
    def _on_stop_recording_btn_pressed(self, event):
        """停止记录按钮按下事件"""
        # 只响应左键按下
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_holding_stop_recording_btn = True
            self.stop_recording_progress_value = 0
            self.stop_recording_progress_ring.setValue(0)
            self.stop_recording_progress_ring.setStyleSheet("opacity: 1;")  # 显示进度环
            
            # 创建定时器来更新进度
            if self.stop_recording_progress_timer is None:
                self.stop_recording_progress_timer = QTimer()
                self.stop_recording_progress_timer.timeout.connect(self._update_stop_recording_progress)
            
            # 计算更新间隔（每10ms更新一次，1秒共100次，每次增加1%）
            update_interval = int((self.stop_recording_hold_duration * 1000) / 100)  # 10ms，100次更新
            self.stop_recording_progress_timer.start(update_interval)
    
    def _on_stop_recording_btn_released(self, event):
        """停止记录按钮松开事件"""
        # 只响应左键松开
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_holding_stop_recording_btn = False
            
            # 停止定时器
            if self.stop_recording_progress_timer:
                self.stop_recording_progress_timer.stop()
            
            # 如果进度未完成，隐藏进度环
            if self.stop_recording_progress_value < 100:
                self.stop_recording_progress_ring.setStyleSheet("opacity: 0;")  # 隐藏进度环但保持占用空间
                self.stop_recording_progress_value = 0
                self.stop_recording_progress_ring.setValue(0)
    
    def _update_stop_recording_progress(self):
        """更新停止记录进度"""
        if not self.is_holding_stop_recording_btn:
            # 如果已经松开，停止更新
            if self.stop_recording_progress_timer:
                self.stop_recording_progress_timer.stop()
                self.stop_recording_progress_ring.setStyleSheet("opacity: 0;")  # 隐藏进度环但保持占用空间
                self.stop_recording_progress_value = 0
                self.stop_recording_progress_ring.setValue(0)
            return
        
        # 增加进度值（每次增加1%，100次达到100%）
        self.stop_recording_progress_value += 1
        self.stop_recording_progress_ring.setValue(self.stop_recording_progress_value)
        
        # 如果达到100%，执行停止记录操作
        if self.stop_recording_progress_value >= 100:
            if self.stop_recording_progress_timer:
                self.stop_recording_progress_timer.stop()
            self.is_holding_stop_recording_btn = False
            self.stop_recording_progress_ring.setStyleSheet("opacity: 0;")  # 隐藏进度环但保持占用空间
            self.stop_recording_progress_value = 0
            self.stop_recording_progress_ring.setValue(0)
            
            # 执行停止记录操作
            self._stop_recording()
    
    def _clear_data(self):
        """清空数据"""
        # 显示警告提示
        InfoBarHelper.warning(
            self,
            title="数据已清空",
            content="所有数据已清空"
        )
        
        self.data_processor.clear_buffer(clear_frames=True)
        # 重置呼吸信道列表初始化标志，以便下次收到数据时重新初始化
        self.breathing_channels_initialized = False
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
            "JSONL文件 (*.jsonl);;JSON文件 (*.json);;所有文件 (*.*)"
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
            
            # 检查版本兼容性错误
            if data.get('error') == 'version_incompatible':
                file_version = data.get('file_version', 'unknown')
                app_version = data.get('app_version', 'unknown')
                error_msg = data.get('message', f'文件版本 {file_version} 高于APP版本 {app_version}')
                InfoBarHelper.error(
                    self,
                    title="版本不兼容",
                    content=error_msg
                )
                self.logger.error(f"版本不兼容: {error_msg}")
                return
            
            self.loaded_frames = data.get('frames', [])
            self.loaded_file_info = data
            self.is_loaded_mode = True
            self.current_window_start = 0
            
            # 在文件加载模式下禁用自适应功能
            if hasattr(self, 'breathing_adaptive_btn'):
                self.breathing_adaptive_btn.setEnabled(False)
            if hasattr(self, 'breathing_adaptive_manual_checkbox'):
                self.breathing_adaptive_manual_checkbox.setEnabled(False)
            # 禁用自适应功能
            self.breathing_adaptive_enabled = False
            self.breathing_adaptive_manual_control = False
            self._update_channel_combo_enabled()
            
            # 根据文件中的frame_type自动设置模式
            file_frame_type = data.get('frame_type')
            if file_frame_type:
                if file_frame_type == 'direction_estimation':
                    # 设置为方向估计帧模式
                    self.frame_type = "方向估计帧"
                    self.is_direction_estimation_mode = True
                    self.frame_mode = True
                    # 更新UI中的帧类型选择
                    if hasattr(self, 'frame_type_combo'):
                        self.frame_type_combo.setCurrentText("方向估计帧")
                    # 设置DF模式的默认显示帧数
                    self.display_max_frames = config.df_default_display_max_frames
                    if hasattr(self, 'display_max_frames_entry'):
                        self.display_max_frames_entry.setText(str(config.df_default_display_max_frames))
                    self.logger.info(f"根据文件内容自动设置为方向估计帧模式")
                elif file_frame_type == 'channel_sounding':
                    # 设置为信道探测帧模式
                    self.frame_type = "信道探测帧"
                    self.is_direction_estimation_mode = False
                    self.frame_mode = True
                    # 更新UI中的帧类型选择
                    if hasattr(self, 'frame_type_combo'):
                        self.frame_type_combo.setCurrentText("信道探测帧")
                    # 设置CS模式的默认显示帧数
                    self.display_max_frames = config.default_display_max_frames
                    if hasattr(self, 'display_max_frames_entry'):
                        self.display_max_frames_entry.setText(str(config.default_display_max_frames))
                    self.logger.info(f"根据文件内容自动设置为信道探测帧模式")
            
            # 根据帧类型更新呼吸估计器的默认参数
            if hasattr(self, 'breathing_estimator'):
                self._update_breathing_params_from_frame_type()
            
            # 更新文件信息显示（完整信息）
            self._update_load_file_info()
            
            # 更新tab的启用状态（根据帧类型）
            self._update_plot_tabs_enabled_state()
            
            # 启用时间窗控制并更新范围
            max_start = max(0, len(self.loaded_frames) - self.display_max_frames)
            self.time_window_slider.setMaximum(max_start)
            self.time_window_slider.setValue(0)
            self.window_start_entry.setText("0")
            
            # 更新文件加载tab状态（加载文件后，禁用文件选择，启用时间窗控制）
            self._update_load_tab_state()
            
            # 禁用连接tab的功能（加载模式和连接态互斥）
            self._set_connection_tab_enabled(False)
            
            # 注意：不禁用文件加载tab，因为用户可以取消加载
            
            # 更新信道列表（用于呼吸估计和显示）
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
            
            # 更新呼吸估计的信道列表
            self.breathing_channel_combo.clear()
            self.breathing_channel_combo.addItems([str(ch) for ch in channel_list])
            if channel_list:
                self.breathing_channel_combo.setCurrentIndex(0)
            
            # 更新显示信道列表（特别是DF模式需要自动设置）
            if self.is_direction_estimation_mode and channel_list:
                # DF模式：自动设置为实际接收到的信道
                self.display_channel_list = channel_list
                if hasattr(self, 'display_channels_entry'):
                    self.display_channels_entry.setText(','.join(str(ch) for ch in channel_list))
                self.logger.info(f"[加载DF文件] 自动设置显示信道列表: {channel_list}")
            elif not self.display_channel_list and channel_list:
                # 如果当前没有设置显示信道列表，使用文件中的信道
                self.display_channel_list = channel_list
                if hasattr(self, 'display_channels_entry'):
                    self.display_channels_entry.setText(','.join(str(ch) for ch in channel_list))
                self.logger.info(f"[加载文件] 设置显示信道列表: {channel_list}")
            
            # 呼吸估计控制面板已经常驻显示，不需要切换
            
            # 切换按钮为取消加载
            self.load_unload_btn.setText("取消加载")
            self.load_unload_btn.setStyleSheet(self._get_button_style("#f44336"))  # 红色
            
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
        # 显示文件版本（从loaded_file_info中获取，而不是默认值）
        file_version = self.loaded_file_info.get('version', 'N/A')
        info_lines.append(f"版本: {file_version}")
        
        # 显示帧类型和帧版本（如果有）
        frame_type = self.loaded_file_info.get('frame_type')
        if frame_type:
            frame_type_name = "方向估计帧" if frame_type == 'direction_estimation' else "信道探测帧"
            info_lines.append(f"帧类型: {frame_type_name}")
            frame_version = self.loaded_file_info.get('frame_version')
            if frame_version:
                info_lines.append(f"帧版本: {frame_version}")
        
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
        
        # 恢复自适应功能按钮的启用状态
        if hasattr(self, 'breathing_adaptive_btn'):
            self.breathing_adaptive_btn.setEnabled(True)
        if hasattr(self, 'breathing_adaptive_manual_checkbox'):
            self.breathing_adaptive_manual_checkbox.setEnabled(True)
        
        # 更新文件加载tab状态（取消加载后，启用文件选择，禁用时间窗控制）
        self._update_load_tab_state()
        
        # 启用连接tab的功能
        self._set_connection_tab_enabled(True)
        
        # 呼吸估计控制面板已经常驻显示，不需要切换
        
        # 切换按钮为加载文件
        self.load_unload_btn.setText("加载文件")
        self.load_unload_btn.setStyleSheet(self._get_button_style("#2196F3"))  # 浅蓝色
        
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
    
    def _update_load_tab_state(self):
        """
        更新文件加载tab的状态（综合考虑连接状态和文件加载状态）
        
        状态机逻辑：
        - 文件选择控件（浏览按钮、文件输入框）：未连接 AND 未加载文件 时启用
        - 时间窗控制控件：已加载文件 时启用
        - 加载/取消加载按钮：始终启用
        """
        # 文件选择控件：只有在未连接且未加载文件时才启用
        file_selection_enabled = not self.is_running and not self.is_loaded_mode
        
        if hasattr(self, 'load_file_entry'):
            self.load_file_entry.setEnabled(file_selection_enabled)
        if hasattr(self, 'browse_btn'):
            self.browse_btn.setEnabled(file_selection_enabled)
        
        # 加载/取消加载按钮始终启用
        if hasattr(self, 'load_unload_btn'):
            self.load_unload_btn.setEnabled(True)
        
        # 时间窗控制控件：只有在已加载文件时才启用
        time_window_enabled = self.is_loaded_mode
        if hasattr(self, 'window_start_entry'):
            self.window_start_entry.setEnabled(time_window_enabled)
        if hasattr(self, 'time_window_slider'):
            self.time_window_slider.setEnabled(time_window_enabled)
        if hasattr(self, 'slider_left_btn'):
            self.slider_left_btn.setEnabled(time_window_enabled)
        if hasattr(self, 'slider_right_btn'):
            self.slider_right_btn.setEnabled(time_window_enabled)
        if hasattr(self, 'reset_view_btn'):
            self.reset_view_btn.setEnabled(time_window_enabled)
    
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
                # DF模式下，根据选择的幅值类型决定使用哪个数据
                if self.is_direction_estimation_mode and data_type == 'amplitude':
                    if hasattr(self, 'df_amplitude_type_combo'):
                        amplitude_type = self.df_amplitude_type_combo.currentText()
                        if amplitude_type == "功率P":
                            # 使用功率P（p_avg）
                            actual_data_type = 'p_avg'
                        else:
                            # 使用RMS幅值（amplitude，即sqrt(p_avg)）
                            actual_data_type = 'amplitude'
                    else:
                        actual_data_type = 'amplitude'
                else:
                    actual_data_type = data_type
                
                indices, values = self.data_processor.get_frame_data_range(
                    ch, max_frames=self.display_max_frames, data_type=actual_data_type
                )
                if len(indices) > 0 and len(values) > 0:
                    channel_data[ch] = (indices, values)
            
            # 更新绘图
            if channel_data:
                plotter.update_frame_data(channel_data, max_channels=len(display_channels))
                
                # 如果启用了高亮最高能量波形，应用高亮（只有当能量占比高于阈值时才高亮）
                # 从BreathingEstimator获取最新状态
                adaptive_state = self.breathing_estimator.get_adaptive_state()
                current_best_channels = adaptive_state.get('best_channels', [])
                adaptive_selected = adaptive_state.get('selected_channel')
                
                if (self.breathing_adaptive_highlight and 
                    self.breathing_adaptive_enabled and
                    current_best_channels):
                    # 高亮前N个最高能量信道
                    best_channels_to_highlight = [ch for ch, ratio in current_best_channels[:self.breathing_adaptive_top_n]]
                    
                    # 应用高亮（如果plotter支持）
                    if hasattr(plotter, 'highlight_best_channels'):
                        plotter.highlight_best_channels(best_channels_to_highlight, True)
                else:
                    # 清除高亮
                    if hasattr(plotter, 'highlight_best_channels'):
                        plotter.highlight_best_channels([], False)
    
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
        
        # 调整子图间距，避免上下重叠
        # hspace: 上下间距（相对于子图高度），wspace: 左右间距（相对于子图宽度）
        figure.subplots_adjust(hspace=0.4, wspace=0.3)
        
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
    
    def _on_slider_button_pressed(self, direction):
        """滑动条按钮按下时的回调（支持长按）"""
        self.slider_button_direction = direction
        self.is_holding_slider_btn = True
        
        # 立即执行一次点击
        if direction == 'left':
            self._on_slider_left_click()
        else:
            self._on_slider_right_click()
        
        # 启动定时器，实现长按持续滑动
        if self.slider_button_timer is None:
            self.slider_button_timer = QTimer()
            self.slider_button_timer.timeout.connect(self._on_slider_button_timer_timeout)
        
        # 初始延迟300ms，然后每100ms执行一次
        self.slider_button_timer.setSingleShot(False)
        self.slider_button_timer.start(100)  # 100ms间隔
    
    def _on_slider_button_released(self):
        """滑动条按钮释放时的回调"""
        self.is_holding_slider_btn = False
        self.slider_button_direction = None
        
        # 停止定时器
        if self.slider_button_timer:
            self.slider_button_timer.stop()
    
    def _on_slider_button_timer_timeout(self):
        """滑动条按钮长按定时器回调"""
        if not self.is_holding_slider_btn:
            return
        
        if self.slider_button_direction == 'left':
            self._on_slider_left_click()
        elif self.slider_button_direction == 'right':
            self._on_slider_right_click()
    
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
    
    def _update_breathing_params_from_frame_type(self):
        """根据帧类型更新呼吸估计器的默认参数，并更新UI显示"""
        # 根据帧类型设置默认参数
        self.breathing_estimator.set_default_params_for_frame_type(self.frame_type)
        
        # 更新UI中的参数显示
        if hasattr(self, 'breathing_sampling_rate_entry'):
            self.breathing_sampling_rate_entry.setText(str(self.breathing_estimator.sampling_rate))
        if hasattr(self, 'breathing_median_filter_entry'):
            self.breathing_median_filter_entry.setText(str(self.breathing_estimator.median_filter_window))
        if hasattr(self, 'breathing_highpass_cutoff_entry'):
            self.breathing_highpass_cutoff_entry.setText(str(self.breathing_estimator.highpass_cutoff))
        if hasattr(self, 'breathing_highpass_order_entry'):
            self.breathing_highpass_order_entry.setText(str(self.breathing_estimator.highpass_order))
        if hasattr(self, 'breathing_bandpass_lowcut_entry'):
            self.breathing_bandpass_lowcut_entry.setText(str(self.breathing_estimator.bandpass_lowcut))
        if hasattr(self, 'breathing_bandpass_highcut_entry'):
            self.breathing_bandpass_highcut_entry.setText(str(self.breathing_estimator.bandpass_highcut))
        if hasattr(self, 'breathing_bandpass_order_entry'):
            self.breathing_bandpass_order_entry.setText(str(self.breathing_estimator.bandpass_order))
        
        # 方向估计帧模式下的特殊处理
        if self.is_direction_estimation_mode:
            # 限制data_type选项为amplitude和local_amplitude
            if hasattr(self, 'breathing_data_type_combo'):
                current_text = self.breathing_data_type_combo.currentText()
                self.breathing_data_type_combo.clear()
                self.breathing_data_type_combo.addItems(["amplitude", "local_amplitude"])
                # 如果当前选项不在新列表中，使用amplitude
                if current_text not in ["amplitude", "local_amplitude"]:
                    self.breathing_data_type_combo.setCurrentText("amplitude")
            
            # 禁用信道选择和自适应功能
            if hasattr(self, 'breathing_channel_combo'):
                self.breathing_channel_combo.setEnabled(False)
            if hasattr(self, 'breathing_adaptive_manual_checkbox'):
                self.breathing_adaptive_manual_checkbox.setEnabled(False)
        else:
            # 信道探测帧模式：恢复所有选项和功能
            if hasattr(self, 'breathing_data_type_combo'):
                current_text = self.breathing_data_type_combo.currentText()
                self.breathing_data_type_combo.clear()
                self.breathing_data_type_combo.addItems(["amplitude", "local_amplitude", "remote_amplitude", "phase", "local_phase", "remote_phase"])
                # 如果当前选项不在新列表中，使用amplitude
                if current_text not in ["amplitude", "local_amplitude", "remote_amplitude", "phase", "local_phase", "remote_phase"]:
                    self.breathing_data_type_combo.setCurrentText("amplitude")
            
            # 启用信道选择和自适应功能
            if hasattr(self, 'breathing_channel_combo'):
                self.breathing_channel_combo.setEnabled(True)
            if hasattr(self, 'breathing_adaptive_manual_checkbox'):
                self.breathing_adaptive_manual_checkbox.setEnabled(True)
        
        self.logger.info(f"已根据帧类型 '{self.frame_type}' 更新呼吸估计参数UI")
    
    def _on_reset_breathing_defaults(self):
        """恢复默认配置按钮的回调（从config加载所有默认值）"""
        # 1. 恢复基础设置的默认值（从config）
        if hasattr(self, 'breathing_threshold_entry'):
            self.breathing_threshold_entry.setText(str(config.breathing_default_threshold))
        
        if hasattr(self, 'breathing_update_interval_entry'):
            default_interval = str(config.breathing_default_update_interval)
            self.breathing_update_interval_entry.setText(default_interval)
            self.breathing_update_interval = config.breathing_default_update_interval
        
        # 2. 恢复进阶设置的默认值（根据帧类型从config加载）
        self._update_breathing_params_from_frame_type()
        
        # 3. 恢复可视化设置的默认值（从config）
        if hasattr(self, 'breathing_show_median_checkbox'):
            self.breathing_show_median_checkbox.setChecked(config.breathing_default_show_median)
        if hasattr(self, 'breathing_show_highpass_checkbox'):
            self.breathing_show_highpass_checkbox.setChecked(config.breathing_default_show_highpass)
        if hasattr(self, 'breathing_show_bandpass_checkbox'):
            self.breathing_show_bandpass_checkbox.setChecked(config.breathing_default_show_bandpass)
        
        # 4. 显示提示信息
        InfoBarHelper.information(
            self,
            title="已恢复默认配置",
            content="所有参数已恢复为默认值，请点击'应用参数'使配置生效"
        )
        
        self.logger.info("已从config恢复呼吸估计的默认配置")
    
    def _create_fixed_param_widgets(self):
        """固定创建所有可能的参数输入框（一直显示，通过启用/禁用控制）"""
        # 定义所有可能的参数
        all_params = [
            {'key': 'action', 'label': '操作', 'type': 'select', 'options': ['start', 'stop', 'disconnect'], 
             'tooltip': '操作类型:\nstart: 开始扫描\nstop: 停止扫描\ndisconnect: 断开连接'},
            {'key': 'channels', 'label': '信道列表', 'type': 'text',
             'tooltip': '自定义数据信道列表，支持多种格式：\n• 逗号分隔: 3,4,10\n• 范围格式: 5-7 (表示5,6,7)\n• 混合格式: 3,5-7,10\n• 管道分隔: 3|10|25 (旧格式，仍支持)\n每个信道范围: 0..36'},
            {'key': 'interval_ms', 'label': '连接间隔(ms)', 'type': 'number',
             'tooltip': '必须可被1.25ms整除\n范围: 7.5ms..4s\n默认:10ms(8units)'},
            {'key': 'cte_len', 'label': 'CTE长度', 'type': 'number',
             'tooltip': '1unit=8us,范围2-20units(16-160us)'},
            {'key': 'cte_type', 'label': 'CTE类型', 'type': 'select', 'options': ['aod1', 'aod2', 'aoa'],
             'tooltip': 'CTE类型:\nAOA类型(默认):aoa\nAOD类型:aod1,aod2'},
        ]
        
        # 为每个参数创建输入控件
        for param_def in all_params:
            param_key = param_def['key']
            param_label = param_def['label']
            param_type = param_def.get('type', 'text')
            param_tooltip = param_def.get('tooltip', '')
            
            # 创建行容器widget（一直显示）
            row_widget = QWidget()
            param_row = QHBoxLayout(row_widget)
            param_row.setContentsMargins(0, 0, 0, 0)
            
            label = QLabel(f"{param_label}:")
            if param_tooltip:
                label.setToolTip(param_tooltip)
                label.installEventFilter(ToolTipFilter(label, 0, ToolTipPosition.TOP))
            param_row.addWidget(label)
            
            # 添加弹性空间，使输入框靠右对齐
            param_row.addStretch()
            
            if param_type == 'select':
                # 下拉选择框
                combo = QComboBox()
                # 根据参数key设置选项
                if param_key == 'action':
                    # action参数需要根据命令类型动态设置选项，初始为空
                    pass  # 选项会在命令类型改变时设置
                else:
                    combo.addItems(param_def.get('options', []))
                # 设置固定宽度，与呼吸控制进阶tab一致
                combo.setMaximumWidth(100)
                param_row.addWidget(combo)
                widget = combo
            elif param_type == 'number':
                # 数字输入框（使用QLineEdit以支持小数）
                line_edit = QLineEdit()
                line_edit.setPlaceholderText(f"输入{param_label}")
                # 设置固定宽度，与呼吸控制进阶tab一致
                line_edit.setMaximumWidth(100)
                param_row.addWidget(line_edit)
                widget = line_edit
            else:
                # 文本输入框
                line_edit = QLineEdit()
                line_edit.setPlaceholderText(f"输入{param_label}")
                # 设置固定宽度，与呼吸控制进阶tab一致
                line_edit.setMaximumWidth(100)
                param_row.addWidget(line_edit)
                widget = line_edit
            
            if param_tooltip and hasattr(widget, 'setToolTip'):
                widget.setToolTip(param_tooltip)
                if hasattr(widget, 'installEventFilter'):
                    widget.installEventFilter(ToolTipFilter(widget, 0, ToolTipPosition.TOP))
            
            self.param_layout.addWidget(row_widget)
            
            # 保存控件引用（包含整个行widget和label，用于启用/禁用）
            self.param_widgets[param_key] = {
                'widget': widget,
                'label': label,
                'row_widget': row_widget,
                'type': param_type,
                'def': param_def
            }
        
        # 创建"无需参数"提示标签（始终显示，但内容根据情况变化）
        self.no_params_label = QLabel(" ")  # 初始显示空格，保持布局稳定
        self.no_params_label.setStyleSheet("color: green;font-size: 9px;font-style: italic;")
        self.param_layout.addWidget(self.no_params_label)
        
        # 初始化参数默认值（使用config.py中的默认值）
        self._init_command_params_defaults()
    
    def _on_command_type_changed(self):
        """命令类型改变时的回调"""
        # 获取当前选中的命令类型
        current_index = self.command_type_combo.currentIndex()
        if current_index < 0:
            return
        
        cmd_type = self.command_type_combo.itemData(current_index)
        if not cmd_type:
            return
        
        cmd_def = self.command_sender.COMMAND_TYPES.get(cmd_type)
        if not cmd_def:
            return
        
        # 获取当前命令需要的参数key列表
        required_param_keys = {param['key'] for param in cmd_def['params']}
        
        # 更新action下拉框的选项（根据命令类型）
        if 'action' in self.param_widgets:
            action_widget = self.param_widgets['action']['widget']
            if isinstance(action_widget, QComboBox):
                action_widget.clear()
                if cmd_type == 'BLE_SCAN':
                    action_widget.addItems(['start', 'stop'])
                elif cmd_type == 'BLE_CONN':
                    action_widget.addItems(['disconnect'])
                else:
                    # 其他命令类型不需要action参数
                    pass
        
        # 启用/禁用参数框（所有框都显示，但根据命令类型启用/禁用）
        for param_key, param_info in self.param_widgets.items():
            widget = param_info['widget']
            label = param_info['label']
            
            if param_key in required_param_keys:
                # 启用该参数框
                widget.setEnabled(True)
                label.setEnabled(True)
                # 设置标签样式为正常
                label.setStyleSheet("")
                
                # 如果是action参数且当前命令不需要，清空并重置
                # if param_key == 'action' and cmd_type not in ['BLE_SCAN', 'BLE_CONN']:
                #     if isinstance(widget, QComboBox):
                #         widget.clear()
                # 如果不是action参数，清空输入框（切换命令时清空旧值）
                # elif param_key != 'action':
                #     if isinstance(widget, QLineEdit):
                #         widget.clear()
                #     elif isinstance(widget, QComboBox):
                #         widget.setCurrentIndex(0)
            else:
                # 禁用该参数框
                widget.setEnabled(False)
                label.setEnabled(False)
                # 设置标签样式为灰色（表示禁用）
                label.setStyleSheet("color: gray;")
                # 清空输入框
                # if isinstance(widget, QLineEdit):
                #     widget.clear()
                # elif isinstance(widget, QComboBox):
                #     widget.clear()
        
        # 显示/隐藏"无需参数"提示（通过改变文本内容，而不是显示/隐藏）
        if not cmd_def['params']:
            self.no_params_label.setText("此命令无需参数")
        else:
            self.no_params_label.setText(" ")  # 显示空格，保持布局稳定
    
    def _on_escape_checkbox_changed(self, state):
        """转义字符checkbox改变时的回调"""
        if state != Qt.CheckState.Checked.value:
            # 取消勾选时显示警告
            InfoBarHelper.warning(
                self,
                title="转义字符已禁用",
                content="发送命令时\\n将按字符发送，而不是<LF>，请注意",
                duration=3000
            )
    
    def _on_reset_command_params(self):
        """恢复默认参数按钮的回调"""
        # 恢复默认参数值（使用CommandSender中的默认值）
        default_params = self.command_sender.get_default_params()
        
        if 'cte_type' in self.param_widgets and 'cte_type' in default_params:
            widget = self.param_widgets['cte_type']['widget']
            if isinstance(widget, QComboBox):
                index = widget.findText(default_params['cte_type'])
                if index >= 0:
                    widget.setCurrentIndex(index)
        
        if 'channels' in self.param_widgets and 'channels' in default_params:
            widget = self.param_widgets['channels']['widget']
            if isinstance(widget, QLineEdit):
                widget.setText(default_params['channels'])
        
        if 'cte_len' in self.param_widgets and 'cte_len' in default_params:
            widget = self.param_widgets['cte_len']['widget']
            if isinstance(widget, QLineEdit):
                widget.setText(default_params['cte_len'])
        
        if 'interval_ms' in self.param_widgets and 'interval_ms' in default_params:
            widget = self.param_widgets['interval_ms']['widget']
            if isinstance(widget, QLineEdit):
                widget.setText(default_params['interval_ms'])
        
        InfoBarHelper.success(
            self,
            title="已恢复默认参数",
            content="命令参数已恢复为默认值"
        )
        
        self.logger.info("已恢复命令发送的默认参数")
    
    def _init_command_params_defaults(self):
        """初始化命令参数的默认值（使用CommandSender中的默认值）"""
        default_params = self.command_sender.get_default_params()
        
        # 设置CTE类型默认值
        if 'cte_type' in self.param_widgets and 'cte_type' in default_params:
            widget = self.param_widgets['cte_type']['widget']
            if isinstance(widget, QComboBox):
                index = widget.findText(default_params['cte_type'])
                if index >= 0:
                    widget.setCurrentIndex(index)
        
        # 设置信道列表默认值
        if 'channels' in self.param_widgets and 'channels' in default_params:
            widget = self.param_widgets['channels']['widget']
            if isinstance(widget, QLineEdit):
                widget.setText(default_params['channels'])
        
        # 设置CTE长度默认值
        if 'cte_len' in self.param_widgets and 'cte_len' in default_params:
            widget = self.param_widgets['cte_len']['widget']
            if isinstance(widget, QLineEdit):
                widget.setText(default_params['cte_len'])
        
        # 设置连接间隔默认值
        if 'interval_ms' in self.param_widgets and 'interval_ms' in default_params:
            widget = self.param_widgets['interval_ms']['widget']
            if isinstance(widget, QLineEdit):
                widget.setText(default_params['interval_ms'])
    
    
    def _on_generate_command(self):
        """生成命令按钮的回调"""
        # 获取当前选中的命令类型
        current_index = self.command_type_combo.currentIndex()
        if current_index < 0:
            InfoBarHelper.warning(
                self,
                title="无法生成",
                content="请选择命令类型"
            )
            return
        
        cmd_type = self.command_type_combo.itemData(current_index)
        if not cmd_type:
            return
        
        # 收集参数值（只收集启用的参数）
        params = {}
        for param_key, param_info in self.param_widgets.items():
            widget = param_info['widget']
            
            # 只收集启用的参数
            if not widget.isEnabled():
                continue
            
            param_type = param_info['type']
            
            if param_type == 'select':
                # 下拉框
                if isinstance(widget, QComboBox):
                    value = widget.currentText()
                    if value:
                        params[param_key] = value
            elif param_type == 'number':
                # 数字输入框（QLineEdit）
                if isinstance(widget, QLineEdit):
                    value = widget.text().strip()
                    if value:
                        params[param_key] = value
            else:
                # 文本输入框
                if isinstance(widget, QLineEdit):
                    value = widget.text().strip()
                    if value:
                        # 如果是channels参数，需要转换格式
                        if param_key == 'channels':
                            value = self.command_sender.parse_channels_input(value)
                        params[param_key] = value
        
        # 验证参数
        enable_escape = self.escape_checkbox.isChecked()
        is_valid, error_msg = self.command_sender.validate_params(cmd_type, params)
        
        if not is_valid:
            InfoBarHelper.error(
                self,
                title="参数验证失败",
                content=error_msg or "参数格式不正确"
            )
            return
        
        # 生成命令（总是包含\n作为字符串，用于显示）
        try:
            # 生成命令（不包含换行符）
            command = self.command_sender.generate_command(cmd_type, params, always_include_newline=False)
            
            # 在命令末尾添加\n作为字符串（用于显示）
            command_with_newline = command + '\\n'
            
            # 显示在输入框中（用户可以看到完整命令，包括\n）
            self.command_input.setText(command_with_newline)
            
            InfoBarHelper.success(
                self,
                title="命令已生成",
                content="命令已生成并填入输入框，可以编辑或直接发送"
            )
        except Exception as e:
            InfoBarHelper.error(
                self,
                title="生成失败",
                content=f"生成命令时出错: {str(e)}"
            )
    
    def _on_send_command(self):
        """发送指令按钮的回调"""
        if not self.is_running or not self.serial_reader:
            InfoBarHelper.warning(
                self,
                title="无法发送",
                content="请先连接串口"
            )
            return
        
        command_text = self.command_input.text()
        if not command_text.strip():
            InfoBarHelper.warning(
                self,
                title="指令为空",
                content="请输入要发送的指令"
            )
            return
        
        # 处理转义字符
        enable_escape = self.escape_checkbox.isChecked()
        if enable_escape:
            # 启用转义：处理转义字符（将\n等转换为实际字符）
            # 例如：输入框中的\n会被转换为实际的换行符<LF>
            command = self.command_sender.process_escape_chars(command_text)
        else:
            # 不启用转义：\n按正常字符发送（两个字符：反斜杠和n）
            # 输入框中的\n已经是字符串形式，直接发送即可
            command = command_text
        
        # 发送指令
        success = self.serial_reader.write(command)
        
        if success:
            # 添加到交互历史（显示发送的命令）
            timestamp = datetime.now().strftime("%H:%M:%S")
            # 显示时转义换行符以便阅读
            display_cmd = command.replace('\n', '\\n').replace('\r', '\\r')
            history_text = f"[{timestamp}] 发送: {display_cmd}\n"
            self.command_history.append(history_text.rstrip())
            
            # 清空输入框
            self.command_input.clear()
            
            self.logger.info(f"已发送指令: {display_cmd}")
        else:
            InfoBarHelper.error(
                self,
                title="发送失败",
                content="指令发送失败，请检查串口连接"
            )
    
    def _on_clear_command_history(self):
        """清空指令历史"""
        self.command_history.clear()
        self.logger.info("已清空交互历史")
    
    def _add_response_to_history(self, response_data: Dict):
        """添加反馈到交互历史"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        resp_type = response_data.get('type', 'UNKNOWN')
        
        if resp_type == 'OK':
            cmd = response_data.get('cmd', '')
            msg = response_data.get('msg', '')
            history_text = f"[{timestamp}] 反馈: $OK,{cmd}" + (f",{msg}" if msg else "") + "\n"
            self.command_history.append(history_text.rstrip())
        elif resp_type == 'ERR':
            cmd = response_data.get('cmd', '')
            code = response_data.get('code', 0)
            msg = response_data.get('msg', '')
            history_text = f"[{timestamp}] 错误: $ERR,{cmd},{code}" + (f",{msg}" if msg else "") + "\n"
            self.command_history.append(history_text.rstrip())
        elif resp_type == 'EVT':
            topic = response_data.get('topic', '')
            msg = response_data.get('msg', '')
            history_text = f"[{timestamp}] 事件: $EVT,{topic}" + (f",{msg}" if msg else "") + "\n"
            self.command_history.append(history_text.rstrip())
    
    def _on_show_log_changed(self, state):
        """日志显示控制改变"""
        self.show_log = (state == Qt.CheckState.Checked.value)
        if hasattr(self, 'log_group'):
            self.log_group.setVisible(self.show_log)
        self._update_right_panel_layout()
    
    def _on_show_version_info_changed(self, state):
        """版本信息显示控制改变"""
        self.show_version_info = (state == Qt.CheckState.Checked.value)
        if hasattr(self, 'version_label'):
            self.version_label.setVisible(self.show_version_info)
        self._update_right_panel_layout()
    
    def _on_show_toolbar_changed(self, state):
        """工具栏显示控制改变（支持三态）"""
        # 处理三态checkbox的逻辑
        # 注意：PartiallyChecked状态通常由系统根据子项状态自动设置，
        # 但当用户点击PartiallyChecked时，应该选中所有子项
        if state == Qt.CheckState.Checked.value:
            # 选中状态：选中所有子项
            self.show_toolbar = True
            if hasattr(self, 'show_breathing_control_checkbox'):
                self.show_breathing_control_checkbox.setChecked(True)
            if hasattr(self, 'show_send_command_checkbox'):
                self.show_send_command_checkbox.setChecked(True)
        elif state == Qt.CheckState.Unchecked.value:
            # 未选中状态：取消所有子项并隐藏工具栏
            self.show_toolbar = False
            if hasattr(self, 'show_breathing_control_checkbox'):
                self.show_breathing_control_checkbox.setChecked(False)
            if hasattr(self, 'show_send_command_checkbox'):
                self.show_send_command_checkbox.setChecked(False)
        elif state == Qt.CheckState.PartiallyChecked.value:
            # 部分选中状态：用户点击时，选中所有子项（常见行为）
            # 这样用户可以通过点击来快速选中所有子项
            self.show_toolbar = True
            if hasattr(self, 'show_breathing_control_checkbox'):
                self.show_breathing_control_checkbox.setChecked(True)
            if hasattr(self, 'show_send_command_checkbox'):
                self.show_send_command_checkbox.setChecked(True)
            # 注意：子项状态改变后会触发_update_toolbar_checkbox_state，
            # 它会将父checkbox状态更新为Checked
        
        if hasattr(self, 'toolbar_group'):
            self.toolbar_group.setVisible(self.show_toolbar)
        
        # 更新子项checkbox的启用状态
        if hasattr(self, 'show_breathing_control_checkbox'):
            self.show_breathing_control_checkbox.setEnabled(self.show_toolbar)
        if hasattr(self, 'show_send_command_checkbox'):
            self.show_send_command_checkbox.setEnabled(self.show_toolbar)
        
        self._update_toolbar_tabs_visibility()
        self._update_right_panel_layout()
    
    def _update_toolbar_checkbox_state(self):
        """根据子项的选中状态更新工具栏checkbox的状态"""
        if not hasattr(self, 'show_toolbar_checkbox'):
            return
        
        # 临时断开信号，避免触发循环更新
        self.show_toolbar_checkbox.blockSignals(True)
        
        # 检查子项的选中状态
        breathing_checked = False
        send_command_checked = False
        
        if hasattr(self, 'show_breathing_control_checkbox'):
            breathing_checked = self.show_breathing_control_checkbox.isChecked()
        if hasattr(self, 'show_send_command_checkbox'):
            send_command_checked = self.show_send_command_checkbox.isChecked()
        
        # 根据子项状态设置父checkbox状态
        if breathing_checked and send_command_checked:
            # 所有子项都选中
            self.show_toolbar_checkbox.setCheckState(Qt.CheckState.Checked)
            self.show_toolbar = True
        elif not breathing_checked and not send_command_checked:
            # 所有子项都未选中
            self.show_toolbar_checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.show_toolbar = False
        else:
            # 部分子项选中
            self.show_toolbar_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
            # 如果至少有一个子项被选中，工具栏应该显示
            self.show_toolbar = True
        
        # 更新工具栏的可见性
        if hasattr(self, 'toolbar_group'):
            self.toolbar_group.setVisible(self.show_toolbar)
        
        # 恢复信号连接
        self.show_toolbar_checkbox.blockSignals(False)
        
        # 更新子项的启用状态
        if hasattr(self, 'show_breathing_control_checkbox'):
            self.show_breathing_control_checkbox.setEnabled(self.show_toolbar)
        if hasattr(self, 'show_send_command_checkbox'):
            self.show_send_command_checkbox.setEnabled(self.show_toolbar)
        
        self._update_toolbar_tabs_visibility()
        self._update_right_panel_layout()
    
    def _on_show_breathing_control_changed(self, state):
        """呼吸控制显示控制改变"""
        self.show_breathing_control = (state == Qt.CheckState.Checked.value)
        self._update_toolbar_tabs_visibility()
    
    def _on_show_send_command_changed(self, state):
        """发送指令显示控制改变"""
        self.show_send_command = (state == Qt.CheckState.Checked.value)
        self._update_toolbar_tabs_visibility()
    
    def _update_toolbar_tabs_visibility(self):
        """更新工具栏tab的显示/隐藏"""
        if not hasattr(self, 'toolbar_tabs'):
            return
        
        # 如果工具栏本身不显示，直接返回
        if not self.show_toolbar:
            return
        
        # 控制各个tab的显示
        for i in range(self.toolbar_tabs.count()):
            tab_text = self.toolbar_tabs.tabText(i)
            if tab_text == "呼吸控制":
                self.toolbar_tabs.setTabVisible(i, self.show_breathing_control)
            elif tab_text == "发送指令":
                self.toolbar_tabs.setTabVisible(i, self.show_send_command)
        
        # 如果两个tab都不显示，隐藏整个工具栏
        if not self.show_breathing_control and not self.show_send_command:
            if hasattr(self, 'toolbar_group'):
                self.toolbar_group.setVisible(False)
        else:
            if hasattr(self, 'toolbar_group'):
                self.toolbar_group.setVisible(True)
                
            # 如果当前显示的tab被隐藏了，切换到第一个可见的tab
            current_index = self.toolbar_tabs.currentIndex()
            if current_index >= 0 and not self.toolbar_tabs.isTabVisible(current_index):
                # 找到第一个可见的tab
                for i in range(self.toolbar_tabs.count()):
                    if self.toolbar_tabs.isTabVisible(i):
                        self.toolbar_tabs.setCurrentIndex(i)
                        break
    
    def _update_right_panel_layout(self):
        """更新右侧面板布局（当显示项改变时）"""
        # 使用QTimer延迟更新，确保窗口完全渲染后再调整
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self._do_update_right_panel_layout)
    
    def _do_update_right_panel_layout(self):
        """实际执行右侧面板布局更新"""
        # 检查是否所有右侧面板都不显示
        all_hidden = (not self.show_toolbar and not self.show_log and not self.show_version_info)
        
        if all_hidden:
            # 隐藏整个右侧面板，让plot tab占据全部空间
            if hasattr(self, 'right_widget'):
                self.right_widget.setVisible(False)
            # 设置splitter让左侧占据全部空间
            if hasattr(self, 'main_splitter'):
                # 获取splitter的总宽度
                total_width = self.main_splitter.width()
                if total_width > 0:
                    # 设置左侧占据全部宽度
                    self.main_splitter.setSizes([total_width, 0])
                else:
                    # 如果宽度为0，使用一个很大的值
                    self.main_splitter.setSizes([999999, 0])
        else:
            # 显示右侧面板
            if hasattr(self, 'right_widget'):
                self.right_widget.setVisible(True)
            # 不设置固定比例，让右侧面板根据内容自动调整大小（Maximum策略）
            # 由于right_splitter已设置最大宽度320，右侧面板只会占据实际需要的空间
            # 这样绘图区域会自动占满剩余空间
            if hasattr(self, 'main_splitter'):
                total_width = self.main_splitter.width()
                if total_width > 0:
                    # 根据实际显示的组件计算右侧面板需要的宽度
                    # right_splitter的最大宽度已设置为320，所以右侧面板最多占据320像素
                    right_width = 0
                    if self.show_toolbar and hasattr(self, 'toolbar_group') and self.toolbar_group.isVisible():
                        # 工具栏最大宽度300 + 边距
                        right_width = max(right_width, 320)
                    if self.show_log and hasattr(self, 'log_text') and self.log_text.isVisible():
                        # 日志区域也需要一些宽度（通常和工具栏差不多）
                        right_width = max(right_width, 320)
                    # 如果没有任何内容显示，右侧宽度为0
                    if right_width == 0:
                        right_width = 0
                    
                    # 让左侧占据剩余的所有空间
                    left_width = max(0, total_width - right_width)
                    self.main_splitter.setSizes([left_width, right_width])
                else:
                    # 如果宽度为0，使用默认比例
                    self.main_splitter.setSizes([2, 1])
    
    def _on_update_all_breathing_params(self):
        """应用按钮：提交所有参数（包括基础设置和进阶设置）"""
        # 1. 验证并更新更新间隔
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
        
        # 2. 验证并更新进阶设置中的滤波器参数
        try:
            # 采样率
            sampling_rate = float(self.breathing_sampling_rate_entry.text())
            if sampling_rate <= 0:
                raise ValueError("采样率必须大于0")
            self.breathing_estimator.sampling_rate = sampling_rate
            
            # 中值滤波窗口
            median_filter_window = int(float(self.breathing_median_filter_entry.text()))
            if median_filter_window <= 0:
                raise ValueError("中值滤波窗口必须大于0")
            self.breathing_estimator.median_filter_window = median_filter_window
            
            # 高通滤波器参数
            highpass_cutoff = float(self.breathing_highpass_cutoff_entry.text())
            if highpass_cutoff <= 0:
                raise ValueError("高通截止频率必须大于0")
            self.breathing_estimator.highpass_cutoff = highpass_cutoff
            
            highpass_order = int(float(self.breathing_highpass_order_entry.text()))
            if highpass_order <= 0:
                raise ValueError("高通滤波器阶数必须大于0")
            self.breathing_estimator.highpass_order = highpass_order
            
            # 带通滤波器参数
            bandpass_lowcut = float(self.breathing_bandpass_lowcut_entry.text())
            if bandpass_lowcut <= 0:
                raise ValueError("带通低截止频率必须大于0")
            self.breathing_estimator.bandpass_lowcut = bandpass_lowcut
            
            bandpass_highcut = float(self.breathing_bandpass_highcut_entry.text())
            if bandpass_highcut <= 0:
                raise ValueError("带通高截止频率必须大于0")
            if bandpass_highcut <= bandpass_lowcut:
                raise ValueError("带通高截止频率必须大于低截止频率")
            self.breathing_estimator.bandpass_highcut = bandpass_highcut
            
            bandpass_order = int(float(self.breathing_bandpass_order_entry.text()))
            if bandpass_order <= 0:
                raise ValueError("带通滤波器阶数必须大于0")
            self.breathing_estimator.bandpass_order = bandpass_order
            
        except ValueError as e:
            InfoBarHelper.warning(
                self,
                title="参数错误",
                content=f"滤波器参数错误: {str(e)}"
            )
            # 恢复为当前estimator的值
            self._update_breathing_params_from_frame_type()
            return
        
        # 3. 获取当前参数信息
        data_type = self.breathing_data_type_combo.currentText()
        channel = self.breathing_channel_combo.currentText()
        threshold = self.breathing_threshold_entry.text()
        
        # 4. 显示信息提示
        params_info = (
            f"数据类型: {data_type}, 信道: {channel}, 阈值: {threshold}, "
            f"更新间隔: {interval}秒\n"
            f"采样率: {sampling_rate}Hz, 中值滤波窗口: {median_filter_window}"
        )
        InfoBarHelper.success(
            self,
            title="参数已应用",
            content=params_info
        )
        
        # 5. 更新呼吸估计（根据当前模式）
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
    
    def _update_realtime_filtered_signal(self):
        """实时更新滤波波形（使用时间窗大小限制显示帧数，与其他tab保持一致）"""
        if not self.frame_mode or not self.is_running:
            return
        
        # 检查是否有滤波波形tab
        if 'filtered_signal' not in self.plotters:
            return
        
        # 获取选择的信道和数据类型
        try:
            channel = int(self.breathing_channel_combo.currentText())
        except:
            # 如果没有选择，尝试获取第一个可用信道
            all_channels = self.data_processor.get_all_frame_channels()
            if not all_channels:
                return
            channel = all_channels[0]
        
        data_type = self.breathing_data_type_combo.currentText()
        
        # 获取最近N帧的数据（使用display_max_frames限制，与其他tab保持一致）
        indices, values = self.data_processor.get_frame_data_range(
            channel, max_frames=self.display_max_frames, data_type=data_type
        )
        
        if len(values) == 0:
            return
        
        # 检查是否有任何可视化选项被选中，如果没有则跳过滤波计算
        has_any_checked = (
            (hasattr(self, 'breathing_show_median_checkbox') and self.breathing_show_median_checkbox.isChecked()) or
            (hasattr(self, 'breathing_show_highpass_checkbox') and self.breathing_show_highpass_checkbox.isChecked()) or
            (hasattr(self, 'breathing_show_bandpass_checkbox') and self.breathing_show_bandpass_checkbox.isChecked())
        )
        
        if not has_any_checked:
            # 如果没有任何选项被选中，清空显示并返回，不执行滤波计算
            if 'filtered_signal' in self.plotters:
                plotter_info = self.plotters['filtered_signal']
                plotter = plotter_info.get('plotter')
                if plotter:
                    plotter.clear_plot()
            return
        
        # 进行滤波处理（只有至少有一个选项被选中时才执行）
        signal = np.array(values)
        try:
            processed = self.breathing_estimator.process_signal(signal, data_type)
            if processed:
                # 更新滤波波形tab
                self._update_filtered_signal_plot(indices, values, processed)
        except Exception as e:
            self.logger.warning(f"实时滤波处理出错: {e}")
    
    def _breathing_data_accessor(self, method: str):
        """
        数据访问接口，供BreathingEstimator使用
        
        Args:
            method: 方法名，支持：
                - 'get_all_channels': 获取所有可用信道
                - 'get_channel_data': 获取指定信道的数据
        """
        if method == 'get_all_channels':
            def get_all_channels():
                return self.data_processor.get_all_frame_channels()
            return get_all_channels
        elif method == 'get_channel_data':
            def get_channel_data(channel: int, max_frames: int, data_type: str):
                return self.data_processor.get_frame_data_range(
                    channel, max_frames=max_frames, data_type=data_type
                )
            return get_channel_data
        else:
            raise ValueError(f"Unknown method: {method}")
    
    def _on_adaptive_manual_changed(self, state):
        """当自适应checkbox状态改变时"""
        is_checked = (state == Qt.CheckState.Checked.value)
        
        # 如果勾选"自适应"，需要检查是否开启了"启用信道的呼吸能量计算"
        # 注意：由于checkbox默认禁用，只有在开启能量计算后才能勾选，所以这里理论上不会进入
        # 但为了安全起见，还是保留检查
        if is_checked:
            if not self.breathing_adaptive_enabled:
                # 没有开启"启用信道的呼吸能量计算"，阻止勾选并显示提示
                # 临时断开信号，避免递归调用
                self.breathing_adaptive_manual_checkbox.stateChanged.disconnect(self._on_adaptive_manual_changed)
                self.breathing_adaptive_manual_checkbox.setChecked(False)
                self.breathing_adaptive_manual_checkbox.stateChanged.connect(self._on_adaptive_manual_changed)
                self.breathing_adaptive_manual_control = False
                InfoBarHelper.warning(
                    self,
                    title="无法启用自适应",
                    content="请先启用'启用信道的呼吸能量计算'功能。\n可在'特殊功能' -> '信道呼吸能量计算'中开启。"
                )
                return
        
        # 更新状态
        self.breathing_adaptive_manual_control = is_checked
        
        # 如果取消勾选自适应，只取消勾选"在最高能量信道上执行呼吸监测"，不关闭其他功能
        if not self.breathing_adaptive_manual_control:
            if self.breathing_adaptive_auto_switch:
                self.breathing_adaptive_auto_switch = False
                # 注意：不在这里操作对话框内的checkbox，因为对话框可能已经关闭
                # checkbox状态会在下次打开对话框时根据内部状态自动设置
            # 重置相关状态
            self.breathing_estimator.reset_adaptive_state()
            # 清除高亮
            self._clear_adaptive_highlight()
        else:
            # 如果启用自适应，退出手动选择模式
            self.manual_select_mode = False
            self.manual_selected_channel = None
        
        # 更新"在最高能量信道上执行呼吸监测"checkbox的启用状态（在手动模式下禁用）
        # 注意：只在对话框打开时更新，对话框关闭后不访问对话框内的控件
        # 使用try-except来安全地检查，因为对话框可能已经关闭
        try:
            if hasattr(self, 'breathing_adaptive_auto_switch_checkbox') and self.breathing_adaptive_auto_switch_checkbox is not None:
                # 检查对象是否仍然有效（通过尝试访问一个属性）
                _ = self.breathing_adaptive_auto_switch_checkbox.isEnabled()
                self.breathing_adaptive_auto_switch_checkbox.setEnabled(
                    self.breathing_adaptive_enabled and not self.breathing_adaptive_manual_control
                )
        except (RuntimeError, AttributeError):
            # 对话框已关闭，checkbox已被销毁，忽略错误
            pass
        # 更新channel combo的启用状态
        self._update_channel_combo_enabled()
        # 更新手动选择按钮的状态
        self._update_manual_select_btn_state()
    
    def _update_manual_select_btn_state(self):
        """更新手动切换到最佳信道按钮的启用状态"""
        if not hasattr(self, 'breathing_manual_select_btn'):
            return
        
        # 按钮启用条件：
        # 1. 启用了"启用信道的呼吸能量计算"
        # 2. 未勾选"自适应"checkbox
        # 3. 未勾选"在最高能量信道上执行呼吸监测"
        # 4. 不是方向估计帧模式
        enabled = (self.breathing_adaptive_enabled and 
                  not self.breathing_adaptive_manual_control and
                  not self.breathing_adaptive_auto_switch and
                  not self.is_direction_estimation_mode)
        self.breathing_manual_select_btn.setEnabled(enabled)
    
    def _on_manual_select_best_channel(self):
        """手动切换到最佳信道"""
        if not self.breathing_adaptive_enabled:
            QMessageBox.warning(
                self,
                "功能不可用",
                "请先启用'启用信道的呼吸能量计算'功能。"
            )
            return
        
        if self.breathing_adaptive_manual_control:
            QMessageBox.warning(
                self,
                "功能不可用",
                "手动切换功能在'自适应'模式下不可用。\n请先取消勾选'自适应'checkbox。"
            )
            return
        
        if self.breathing_adaptive_auto_switch:
            QMessageBox.warning(
                self,
                "功能不可用",
                "手动切换功能在'在最高能量信道上执行呼吸监测'模式下不可用。\n请先取消勾选'在最高能量信道上执行呼吸监测'。"
            )
            return
        
        # 手动触发切换：强制重新选择最高能量信道（忽略当前已选择的信道）
        # 设置标志，表示这是手动触发的，并进入手动选择模式
        self.manual_select_triggered = True
        self.manual_select_mode = True
        # 重置自适应状态，强制重新选择
        self.breathing_estimator.reset_adaptive_state()
        # 立即触发一次呼吸估计更新，以执行信道选择
        self._update_realtime_breathing_estimation()
        # 清除临时标志（但保持manual_select_mode，以便后续调用时也使用手动模式）
        self.manual_select_triggered = False
    
    def _update_channel_combo_enabled(self):
        """更新channel combo的启用状态"""
        # 方向估计帧模式下，channel combo始终禁用（自动使用实际接收的信道）
        if self.is_direction_estimation_mode:
            if hasattr(self, 'breathing_channel_combo'):
                self.breathing_channel_combo.setEnabled(False)
            return
        
        # 信道探测帧模式：如果启用了自适应且启用了自动切换，则禁用channel选择
        if (self.breathing_adaptive_manual_control and 
            self.breathing_adaptive_enabled and 
            self.breathing_adaptive_auto_switch):
            self.breathing_channel_combo.setEnabled(False)
        else:
            self.breathing_channel_combo.setEnabled(True)
    
    def _update_realtime_breathing_estimation(self):
        """更新实时呼吸估计（使用最近X帧数据）"""
        if not self.frame_mode or not self.is_running:
            return
        
        # 检查是否有足够的数据
        all_channels = self.data_processor.get_all_frame_channels()
        if not all_channels:
            self.breathing_result_text.setPlainText("等待数据积累...")
            return
        
        data_type = self.breathing_data_type_combo.currentText()
        
        # 获取阈值
        try:
            threshold = float(self.breathing_threshold_entry.text())
        except:
            threshold = 0.6
        
        # 方向估计帧模式：自动使用当前帧的实际信道
        if self.is_direction_estimation_mode:
            # 方向估计帧只有一个信道，使用data_processor中记录的最新信道
            # 注意：使用last_frame_channels而不是all_channels，因为all_channels可能包含历史信道
            if self.data_processor.last_frame_channels:
                # last_frame_channels是一个set，方向估计帧只有一个信道
                channel = list(self.data_processor.last_frame_channels)[0]
                
                # 更新channel combo显示当前信道
                if hasattr(self, 'breathing_channel_combo'):
                    current_text = self.breathing_channel_combo.currentText()
                    if current_text != str(channel):
                        self.breathing_channel_combo.clear()
                        self.breathing_channel_combo.addItem(str(channel))
                        self.breathing_channel_combo.setCurrentText(str(channel))
                
                # 注意：信道变化的检测和状态重置已在_update_data中处理
                # 这里只需要确保last_breathing_channel与当前信道一致
                if self.last_breathing_channel != channel:
                    self.last_breathing_channel = channel
            else:
                # 如果还没有收到任何帧，尝试从all_channels获取
                if len(all_channels) > 0:
                    channel = all_channels[0]
                    if hasattr(self, 'breathing_channel_combo'):
                        current_text = self.breathing_channel_combo.currentText()
                        if current_text != str(channel):
                            self.breathing_channel_combo.clear()
                            self.breathing_channel_combo.addItem(str(channel))
                            self.breathing_channel_combo.setCurrentText(str(channel))
                    if self.last_breathing_channel != channel:
                        self.last_breathing_channel = channel
                else:
                    self.breathing_result_text.setPlainText("等待数据积累...")
                    return
        # 信道探测帧模式：支持自适应和手动选择
        # 如果启用了"启用信道的呼吸能量计算"，需要计算最高能量信道（无论是否勾选"自适应"checkbox）
        adaptive_result = None
        if self.breathing_adaptive_enabled:
            # 更新BreathingEstimator的配置
            self.breathing_estimator.set_adaptive_config(
                enabled=True,
                top_n=self.breathing_adaptive_top_n,
                only_display_channels=self.breathing_adaptive_only_display_channels,
                low_energy_threshold=self.adaptive_low_energy_threshold
            )
            
            # 获取手动选择的信道（作为fallback）
            try:
                manual_channel = int(self.breathing_channel_combo.currentText())
            except:
                manual_channel = all_channels[0] if all_channels else None
            
            # 调用BreathingEstimator的信道选择逻辑
            # 注意：即使没有勾选"自适应"checkbox，也要计算最高能量信道用于显示
            # 如果是手动触发模式，传入manual_trigger=True，这样即使低能量超时也驻留
            adaptive_result = self.breathing_estimator.select_adaptive_channel(
                data_type=data_type,
                threshold=threshold,
                max_frames=self.display_max_frames,
                display_channels=self.display_channel_list if self.breathing_adaptive_only_display_channels else None,
                manual_channel=manual_channel,
                manual_trigger=self.manual_select_triggered or self.manual_select_mode
            )
        
        # 如果勾选了"自适应"checkbox且启用了"在最高能量信道上执行呼吸监测"，使用自适应选择的信道
        if (self.breathing_adaptive_enabled and 
            self.breathing_adaptive_manual_control and
            self.breathing_adaptive_auto_switch and
            adaptive_result and
            adaptive_result['selected_channel'] is not None):
            # 使用自适应选择的信道
            channel = adaptive_result['selected_channel']
        # 如果是手动触发模式，使用手动选择的信道（只在首次触发时选择，之后保持不变）
        elif self.manual_select_mode:
            # 如果是首次手动触发，选择能量最高的信道
            if self.manual_select_triggered and adaptive_result and adaptive_result['best_channels']:
                # 选择能量最高的信道
                if len(adaptive_result['best_channels']) > 0:
                    # 选择第一个（能量最高的）
                    self.manual_selected_channel = adaptive_result['best_channels'][0][0]
                    self.logger.info(f"[呼吸估计] 手动切换到最佳信道: {self.manual_selected_channel}")
            
            # 使用手动选择的信道
            if self.manual_selected_channel is not None:
                channel = self.manual_selected_channel
                # 如果数据不足，显示等待提示
                indices_check, values_check = self.data_processor.get_frame_data_range(
                    channel, max_frames=self.display_max_frames, data_type=data_type
                )
                if len(values_check) < self.display_max_frames:
                    self.breathing_result_text.setPlainText(
                        f"手动切换到最佳信道\n"
                        f"已选择信道: {channel}\n"
                        f"数据积累中: {len(values_check)}/{self.display_max_frames} 帧\n"
                        f"需要积累到 {self.display_max_frames} 帧后开始分析"
                    )
                    return
            else:
                # 如果还没有选择信道，使用手动选择的信道（fallback）
                channel = manual_channel
                if channel is None:
                    self.breathing_result_text.setPlainText("等待数据积累...")
                    return
            
            # 如果未勾选"只在显示信道范围内选取"，且最高能量信道不在显示范围内，则添加到显示
            if (not self.breathing_adaptive_only_display_channels and 
                adaptive_result['best_channels']):
                best_channels_to_add = []
                top_n = min(self.breathing_adaptive_top_n, len(adaptive_result['best_channels']))
                for ch, ratio in adaptive_result['best_channels'][:top_n]:
                    if ch not in self.display_channel_list:
                        best_channels_to_add.append(ch)
                
                if best_channels_to_add:
                    # 添加最高能量信道到显示列表
                    self.display_channel_list.extend(best_channels_to_add)
                    self.display_channel_list = sorted(list(set(self.display_channel_list)))  # 去重并排序
                    # 更新显示信道输入框
                    if hasattr(self, 'display_channels_entry'):
                        self.display_channels_entry.setText(','.join(map(str, self.display_channel_list)))
                    # 应用设置（不显示提示）
                    self._apply_frame_settings(show_info=False)
            
            # 更新channel combo
            if channel is not None:
                self.breathing_channel_combo.setCurrentText(str(channel))
        else:
            # 未启用自适应或未勾选"自适应"checkbox，使用手动选择的信道
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
        
        # 获取最近X帧的数据
        indices, values = self.data_processor.get_frame_data_range(
            channel, max_frames=self.display_max_frames, data_type=data_type
        )
        
        # 检查信道是否发生变化（通过比较当前信道和上次使用的信道）
        # 注意：方向估计帧模式下的信道变化已在_update_data中处理，这里只处理信道探测帧模式
        # 注意：在自动切换模式下，信道变化是由自适应功能控制的，不应该触发"信道已切换"提示和重置
        if not self.is_direction_estimation_mode:
            # 判断是否是自动切换导致的信道变化
            is_auto_switch_change = (self.breathing_adaptive_enabled and 
                                    self.breathing_adaptive_manual_control and
                                    self.breathing_adaptive_auto_switch and
                                    adaptive_result and
                                    adaptive_result['selected_channel'] is not None)
            # 判断是否是手动选择导致的信道变化
            is_manual_select_change = (self.manual_select_mode and 
                                      self.manual_select_triggered and
                                      self.manual_selected_channel is not None)
            
            if self.last_breathing_channel is not None and self.last_breathing_channel != channel:
                if is_auto_switch_change:
                    # 自动切换导致的信道变化，只更新last_breathing_channel，不重置状态
                    # 这是自适应功能的正常行为，不应该触发"信道已切换"提示
                    old_channel_for_log = self.last_breathing_channel
                    self.last_breathing_channel = channel
                    self.logger.info(f"[呼吸估计] 自适应功能切换信道: {old_channel_for_log} -> {channel}")
                elif is_manual_select_change:
                    # 手动选择导致的信道变化，只更新last_breathing_channel，不重置状态
                    # 这是手动触发的正常行为，不应该触发"信道已切换"提示
                    old_channel_for_log = self.last_breathing_channel
                    self.last_breathing_channel = channel
                    self.logger.info(f"[呼吸估计] 手动选择切换信道: {old_channel_for_log} -> {channel}")
                else:
                    # 手动切换或其他原因导致的信道变化，重置状态并显示提示
                    old_channel = self.last_breathing_channel
                    self.last_breathing_channel = channel
                    
                    # 清空新信道的累积数据（如果还没有被清空）
                    # 注意：在信道探测帧模式下，信道切换不会自动清空数据，需要手动清空
                    self.data_processor.clear_channel_data(channel)
                    
                    self.breathing_result_text.setPlainText(
                        f"⚠️ 信道已切换: {old_channel} -> {channel}\n"
                        f"已清空累积数据，重新开始累积时间窗\n"
                        f"当前信道: {channel}\n"
                        f"等待数据积累: 0/{self.display_max_frames} 帧"
                    )
                    # 重置呼吸估计状态
                    self.breathing_estimator.reset_adaptive_state()
                    self.logger.info(f"[呼吸估计] 检测到信道变化: {old_channel} -> {channel}，已重置状态，等待新信道数据积累到 {self.display_max_frames} 帧")
                    return
            
            # 更新上次使用的信道
            if self.last_breathing_channel != channel:
                self.last_breathing_channel = channel
        
        # 检查数据是否积累到足够的帧数（方向估计帧需要1000帧）
        if len(values) < self.display_max_frames:
            # 数据还未积累到X帧，显示积累进度
            if self.is_direction_estimation_mode:
                self.breathing_result_text.setPlainText(
                    f"Current Channel: {channel}\n"
                    f"数据积累中: {len(values)}/{self.display_max_frames} 帧\n"
                    f"需要积累到 {self.display_max_frames} 帧后开始分析"
                )
            else:
                self.breathing_result_text.setPlainText(
                    f"Channel: {channel}\n"
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
            
            # 检测呼吸
            detection = self.breathing_estimator.detect_breathing(
                processed['highpass_filtered'], threshold=threshold
            )
            
            # 更新结果显示
            # 如果启用了"启用信道的呼吸能量计算"，显示前N个最高能量信道信息
            # 从BreathingEstimator获取最新状态
            adaptive_state = self.breathing_estimator.get_adaptive_state()
            current_best_channels = adaptive_state.get('best_channels', [])
            
            if self.breathing_adaptive_enabled and current_best_channels:
                # 显示前N个最高能量信道信息
                result_text = f"Threshold: {threshold:.2f}\n"
                # 如果是手动触发模式，添加提示
                if self.manual_select_mode:
                    result_text += "[手动选择模式] 即使低能量超时也驻留\n"
                result_text += f"前{self.breathing_adaptive_top_n}个最高能量信道（按能量排序）:\n"
                adaptive_selected = adaptive_state.get('selected_channel')
                for i, (ch, ratio) in enumerate(current_best_channels[:self.breathing_adaptive_top_n]):
                    marker = " ← 当前" if ((self.breathing_adaptive_auto_switch and 
                                         self.breathing_adaptive_manual_control) or
                                         (self.manual_select_mode and adaptive_selected == ch)) else ""
                    has_breathing_marker = " ✓" if ratio >= threshold else " ✗"
                    # 如果是手动选择模式且当前信道能量低于阈值，添加低能量提示
                    low_energy_warning = ""
                    if self.manual_select_mode and adaptive_selected == ch and ratio < threshold:
                        low_energy_warning = " (低能量，手动模式下仍驻留)"
                    result_text += f"  {i+1}. Channel {ch}: {ratio:.4f}{marker}{has_breathing_marker}{low_energy_warning}\n"
                
                # 如果启用了自动切换且当前选中的信道有呼吸，显示详细信息
                if (self.breathing_adaptive_auto_switch and 
                    self.breathing_adaptive_manual_control and
                    adaptive_selected is not None and
                    adaptive_selected == channel):
                    if detection['has_breathing'] and not np.isnan(detection['breathing_freq']):
                        breathing_rate = self.breathing_estimator.estimate_breathing_rate(detection['breathing_freq'])
                        result_text += f"\n当前信道 (Channel {channel}):\n"
                        result_text += f"  Energy Ratio: {detection['energy_ratio']:.4f}\n"
                        result_text += f"  Breathing Freq: {detection['breathing_freq']:.4f} Hz\n"
                        result_text += f"  Breathing Rate: {breathing_rate:.1f} /min"
                    else:
                        result_text += f"\n当前信道 (Channel {channel}):\n"
                        result_text += f"  Energy Ratio: {detection['energy_ratio']:.4f}\n"
                        result_text += "  No Breathing Detected"
                elif not self.breathing_adaptive_auto_switch or not self.breathing_adaptive_manual_control:
                    # 如果未启用自动切换，显示当前手动选择信道的详细信息
                    if self.is_direction_estimation_mode:
                        result_text += f"\n当前信道 (Channel {channel}):\n"
                    else:
                        result_text += f"\n当前信道 (Channel {channel}):\n"
                    result_text += f"  Energy Ratio: {detection['energy_ratio']:.4f}\n"
                    result_text += f"  Detection: {'Breathing Detected' if detection['has_breathing'] else 'No Breathing'}\n"
                    if detection['has_breathing'] and not np.isnan(detection['breathing_freq']):
                        breathing_rate = self.breathing_estimator.estimate_breathing_rate(detection['breathing_freq'])
                        result_text += f"  Breathing Freq: {detection['breathing_freq']:.4f} Hz\n"
                        result_text += f"  Breathing Rate: {breathing_rate:.1f} /min"
                    else:
                        result_text += "  Breathing Freq: --\n"
                        result_text += "  Breathing Rate: --"
            else:
                # 未启用自适应，显示默认信道的完整信息
                # 方向估计帧模式下，显示当前信道
                if self.is_direction_estimation_mode:
                    result_text = f"Current Channel: {channel}\n"
                else:
                    result_text = f"Channel: {channel}\n"
                
                result_text += f"Energy Ratio: {detection['energy_ratio']:.4f}\n"
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
                
            # 更新滤波波形tab（如果存在）
            if 'filtered_signal' in self.plotters:
                self._update_filtered_signal_plot(indices, values, processed)
                
        except Exception as e:
            self.logger.error(f"实时呼吸估计出错: {e}")
            self.breathing_result_text.setPlainText(f"分析出错: {str(e)}")
    
    def _update_filtered_signal_plot(self, indices: np.ndarray, values: np.ndarray, processed: Dict):
        """
        更新滤波波形tab的显示
        
        Args:
            indices: 帧索引数组
            values: 原始信号值数组
            processed: process_signal返回的处理结果字典
        """
        if 'filtered_signal' not in self.plotters:
            return
        
        plotter_info = self.plotters['filtered_signal']
        plotter = plotter_info.get('plotter')
        if plotter is None:
            return
        
        # 定义不同滤波阶段的颜色和标签
        filter_colors = {
            'median': '#1f77b4',      # 蓝色 - 中值滤波
            'highpass': '#ff7f0e',     # 橙色 - 高通滤波
            'bandpass': '#2ca02c'      # 绿色 - 带通滤波
        }
        filter_labels = {
            'median': '中值滤波',
            'highpass': '中值+高通滤波',
            'bandpass': '中值+高通+带通滤波'
        }
        
        # 根据复选框状态显示/隐藏对应的线条
        # 中值滤波
        if hasattr(self, 'breathing_show_median_checkbox') and self.breathing_show_median_checkbox.isChecked():
            if 'median_filtered' in processed:
                if 'median' not in plotter.data_lines:
                    plotter.add_line('median', color=filter_colors['median'], label=filter_labels['median'])
                plotter.update_line('median', indices, processed['median_filtered'])
            elif 'median' in plotter.data_lines:
                plotter.remove_line('median')
        else:
            if 'median' in plotter.data_lines:
                plotter.remove_line('median')
        
        # 高通滤波
        if hasattr(self, 'breathing_show_highpass_checkbox') and self.breathing_show_highpass_checkbox.isChecked():
            if 'highpass_filtered' in processed:
                if 'highpass' not in plotter.data_lines:
                    plotter.add_line('highpass', color=filter_colors['highpass'], label=filter_labels['highpass'])
                plotter.update_line('highpass', indices, processed['highpass_filtered'])
            elif 'highpass' in plotter.data_lines:
                plotter.remove_line('highpass')
        else:
            if 'highpass' in plotter.data_lines:
                plotter.remove_line('highpass')
        
        # 带通滤波（需要计算）
        if hasattr(self, 'breathing_show_bandpass_checkbox') and self.breathing_show_bandpass_checkbox.isChecked():
            if 'highpass_filtered' in processed and len(processed['highpass_filtered']) > 0:
                try:
                    analysis = self.breathing_estimator.analyze_window(
                        processed['highpass_filtered'], 
                        apply_hanning=True
                    )
                    if 'bandpass_filtered' in analysis:
                        if 'bandpass' not in plotter.data_lines:
                            plotter.add_line('bandpass', color=filter_colors['bandpass'], label=filter_labels['bandpass'])
                        plotter.update_line('bandpass', indices, analysis['bandpass_filtered'])
                    elif 'bandpass' in plotter.data_lines:
                        plotter.remove_line('bandpass')
                except Exception as e:
                    self.logger.warning(f"计算带通滤波结果时出错: {e}")
                    if 'bandpass' in plotter.data_lines:
                        plotter.remove_line('bandpass')
            elif 'bandpass' in plotter.data_lines:
                plotter.remove_line('bandpass')
        else:
            if 'bandpass' in plotter.data_lines:
                plotter.remove_line('bandpass')
        
        # 设置Y轴标签
        plotter.plot_widget.setLabel('left', 'Filtered Signal')
    
    def _on_visualization_checkbox_changed(self):
        """可视化设置复选框改变时的回调"""
        # 如果当前有数据，立即更新滤波波形tab
        if self.is_loaded_mode:
            # 加载模式下，重新更新呼吸估计plot（会同时更新滤波波形）
            if self.loaded_frames:
                window_start = self.current_window_start
                window_size = self.display_max_frames
                window_end = min(window_start + window_size, len(self.loaded_frames))
                if window_start < window_end:
                    window_frames = self.loaded_frames[window_start:window_end]
                    self._update_breathing_estimation_plot(window_frames)
        elif self.is_running and self.frame_mode:
            # 实时模式下，触发实时滤波波形更新
            self._update_realtime_filtered_signal()
    
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
                # DF模式下，根据选择的幅值类型决定使用哪个数据（与实时模式保持一致）
                if self.is_direction_estimation_mode and data_type == 'amplitude':
                    if hasattr(self, 'df_amplitude_type_combo'):
                        amplitude_type = self.df_amplitude_type_combo.currentText()
                        if amplitude_type == "功率P":
                            # 使用功率P（p_avg）
                            actual_data_type = 'p_avg'
                        else:
                            # 使用RMS幅值（amplitude，即sqrt(p_avg)）
                            actual_data_type = 'amplitude'
                    else:
                        actual_data_type = 'amplitude'
                else:
                    actual_data_type = data_type
                
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
                        values.append(ch_data.get(actual_data_type, 0.0))
                
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
        # 如果启用了自适应且自动切换，使用自适应选择的信道（仅在实时模式下）
        if (not self.is_loaded_mode and
            self.breathing_adaptive_enabled and 
            self.breathing_adaptive_manual_control and
            self.breathing_adaptive_auto_switch):
            adaptive_state = self.breathing_estimator.get_adaptive_state()
            adaptive_selected = adaptive_state.get('selected_channel')
            if adaptive_selected is not None:
                channel = adaptive_selected
            else:
                try:
                    channel = int(self.breathing_channel_combo.currentText())
                except:
                    channel = 0
        else:
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
        
        # 更新滤波波形tab（如果存在）
        if 'filtered_signal' in self.plotters:
            self._update_filtered_signal_plot(indices, signal, processed)
        
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
        
        # 调整子图间距，避免上下重叠（在更新后重新调整）
        figure = plot_info['figure']
        figure.subplots_adjust(hspace=0.4, wspace=0.3)
        
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
        self.logger.info("=" * 60)
        self.logger.info("程序开始退出...")
        self.logger.info(f"退出原因: 用户关闭窗口")
        self.logger.info(f"当前状态 - 运行中: {self.is_running}, 保存中: {self.is_saving}")
        
        # 停止所有定时器
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
            self.logger.debug("已停止更新定时器")
        if hasattr(self, 'breathing_update_timer') and self.breathing_update_timer:
            self.breathing_update_timer.stop()
            self.logger.debug("已停止呼吸估计定时器")
        if hasattr(self, 'freq_update_timer') and self.freq_update_timer:
            self.freq_update_timer.stop()
            self.logger.debug("已停止频率更新定时器")
        
        # 断开串口连接
        if self.is_running:
            if self.serial_reader:
                self.logger.info("正在断开串口连接...")
                self.serial_reader.disconnect()
                self.logger.info("串口已断开")
        
        # 等待保存线程完成（最多等待30秒）
        if hasattr(self, '_save_threads') and self._save_threads:
            alive_threads = [t for t in self._save_threads if t.is_alive()]
            if alive_threads:
                self.logger.info(f"检测到 {len(alive_threads)} 个保存线程仍在运行，等待完成...")
                max_wait_time = 30.0  # 最多等待30秒
                start_time = time.time()
                
                for thread in alive_threads:
                    remaining_time = max_wait_time - (time.time() - start_time)
                    if remaining_time <= 0:
                        self.logger.warning("等待保存线程超时，强制退出")
                        break
                    
                    self.logger.info(f"等待保存线程 '{thread.name}' 完成（剩余时间: {remaining_time:.1f}秒）...")
                    thread.join(timeout=min(remaining_time, 10.0))  # 每次最多等待10秒
                    
                    if thread.is_alive():
                        self.logger.warning(f"保存线程 '{thread.name}' 仍在运行，但已超时")
                    else:
                        self.logger.info(f"保存线程 '{thread.name}' 已完成")
        
        # 记录退出信息
        self.logger.info("程序正常退出")
        self.logger.info("=" * 60)
        
        # 确保日志刷新到文件
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                handler.flush()
        
        event.accept()


class TextHandler(logging.Handler):
    """自定义日志处理器，输出到QTextEdit"""
    
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
    
    def emit(self, record):
        msg = self.format(record)
        self.text_widget.append(msg)  # QTextEdit 的 append 方法


def setup_fonts(app: QApplication, font_name: str = "PingFang Regular", font_size: int = 10, 
                ttf_path: Optional[str] = None, bold: bool = False) -> QFont:
    """
    设置应用程序字体，启用抗锯齿和优化渲染
    
    Args:
        app: QApplication 实例
        font_name: 字体名称（如果加载了 TTF 文件，使用 TTF 中的字体族名）
        font_size: 字体大小
        ttf_path: 可选的 TTF 字体文件路径（相对于 assets 目录或绝对路径）
        bold: 是否使用粗体（默认 False）
    
    Returns:
        配置好的 QFont 对象
    """
    # 声明全局变量
    global _app_font_family, _app_font_size
    
    # 如果提供了 TTF 文件路径，尝试加载
    if ttf_path:
        try:
            # 获取资源路径
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.dirname(__file__))
            
            # 如果是相对路径，从 assets 目录查找
            if not os.path.isabs(ttf_path):
                ttf_full_path = os.path.join(base_path, 'assets', ttf_path)
            else:
                ttf_full_path = ttf_path
            
            if os.path.exists(ttf_full_path):
                # 使用 QFontDatabase 加载 TTF 字体
                font_id = QFontDatabase.addApplicationFont(ttf_full_path)
                if font_id != -1:
                    # 获取加载的字体族名
                    font_families = QFontDatabase.applicationFontFamilies(font_id)
                    if font_families:
                        font_name = font_families[0]  # 使用 TTF 文件中的第一个字体族
                        # 保存到全局变量
                        _app_font_family = font_name
                        _app_font_size = font_size
                        logging.getLogger(__name__).info(f"成功加载 TTF 字体: {font_name} from {ttf_full_path}")
                    else:
                        logging.getLogger(__name__).warning(f"TTF 字体文件未包含有效的字体族: {ttf_full_path}")
                else:
                    logging.getLogger(__name__).warning(f"无法加载 TTF 字体文件: {ttf_full_path}")
            else:
                logging.getLogger(__name__).warning(f"TTF 字体文件不存在: {ttf_full_path}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"加载 TTF 字体时出错: {e}")
    
    # 创建字体对象
    # 如果使用粗体，在创建时指定 Weight
    if bold:
        font = QFont(font_name, font_size, QFont.Weight.Bold)
    else:
        font = QFont(font_name, font_size)
    
    # 设置字体渲染提示 - 使用 PreferNoHinting 以获得柔和的边缘
    # 这是唯一有效的字体渲染控制参数
    try:
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    except (AttributeError, TypeError):
        # 如果 API 不可用，使用系统默认
        pass
    
    # 保存字体族名和大小到全局变量（如果没有通过TTF加载，使用传入的font_name）
    _app_font_family = font_name
    _app_font_size = font_size
    
    # 设置应用程序默认字体
    app.setFont(font)
    
    return font


def get_app_font(size: Optional[int] = None, bold: bool = False) -> QFont:
    """
    获取应用程序字体，可以指定大小和是否粗体
    
    Args:
        size: 字体大小，如果为None则使用应用程序默认大小
        bold: 是否使用粗体
    
    Returns:
        QFont对象
    """
    global _app_font_family, _app_font_size
    
    # 如果字体族名未设置，尝试从应用程序获取
    if _app_font_family is None:
        app = QApplication.instance()
        if app:
            app_font = app.font()
            _app_font_family = app_font.family()
            _app_font_size = app_font.pointSize()
        else:
            # 如果应用程序未创建，使用默认值
            _app_font_family = "PingFang Regular"
            _app_font_size = 10
    
    # 使用保存的字体族名和指定的大小
    font_size = size if size is not None else _app_font_size
    
    if bold:
        font = QFont(_app_font_family, font_size, QFont.Weight.Bold)
    else:
        font = QFont(_app_font_family, font_size)
    
    # 应用相同的渲染优化 - 使用 PreferNoHinting 以获得柔和的边缘
    try:
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    except (AttributeError, TypeError):
        pass
    
    return font


def main():
    """主函数"""
    # 设置全局异常处理
    def exception_handler(exc_type, exc_value, exc_traceback):
        """全局异常处理器"""
        if issubclass(exc_type, KeyboardInterrupt):
            # 用户中断，正常退出
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        # 记录未捕获的异常
        logger = logging.getLogger(__name__)
        logger.critical(
            "=" * 60,
            exc_info=(exc_type, exc_value, exc_traceback)
        )
        logger.critical("程序因未捕获的异常而退出")
        logger.critical(f"异常类型: {exc_type.__name__}")
        logger.critical(f"异常信息: {exc_value}")
        logger.critical("=" * 60)
        
        # 确保日志刷新到文件
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                handler.flush()
        
        # 调用默认异常处理器
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    
    # 安装全局异常处理器
    sys.excepthook = exception_handler
    
    # 在创建 QApplication 之前设置全局属性
    # 这可以确保整个应用程序使用高质量的字体渲染
    try:
        # 设置高DPI缩放策略（Windows）
        # 这有助于在高DPI显示器上获得清晰的字体渲染
        if platform.system() == 'Windows':
            # 设置环境变量，告诉Qt使用系统DPI感知
            # 这些环境变量必须在创建 QApplication 之前设置
            os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
            os.environ['QT_SCALE_FACTOR_ROUNDING_POLICY'] = 'Round'
            
            # 尝试通过 QCoreApplication 设置高DPI缩放策略（如果支持）
            # 注意：这必须在创建 QApplication 之前调用
            try:
                from PySide6.QtCore import QCoreApplication, Qt
                # Qt 6 中，可以通过 setAttribute 设置，但 HighDpiScaleFactorRoundingPolicy 
                # 需要通过环境变量或 setHighDpiScaleFactorRoundingPolicy 设置
                # 由于必须在创建实例之前调用，我们使用环境变量方式
                pass
            except (ImportError, AttributeError):
                pass
    except Exception:
        pass
    
    # 创建应用程序
    # 注意：Qt 6 默认已经启用了高DPI支持，环境变量只是进一步优化
    app = QApplication(sys.argv)
    
    # 设置全局文本渲染优化（柔和的边缘）
    # 这会影响所有使用 QPainter 绘制的文本
    try:
        # 通过设置应用程序属性来优化文本渲染
        # 注意：Qt 6 默认已启用抗锯齿，这里主要是确保使用柔和的渲染模式
        pass  # Qt 6 的默认设置已经很好了
    except Exception:
        pass
    
    # 设置全局字体，启用抗锯齿和优化渲染（柔和的边缘）
    # 方式 1：使用系统自带的微软雅黑粗体（推荐）
    # setup_fonts(app, font_name="Microsoft YaHei", font_size=10, bold=False)
    
    # 方式 2：使用系统自带的微软雅黑（普通）
    # setup_fonts(app, font_name="Microsoft YaHei", font_size=10)
    
    # 方式 3：使用自定义 TTF 字体文件
    setup_fonts(app, font_name="PingFang Regular", font_size=10, ttf_path="PingFang Bold_0.ttf")
    
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
    try:
        window = BLEHostGUI()
        window.show()
        
        # 运行应用程序
        exit_code = app.exec()
        
        # 记录正常退出
        logger = logging.getLogger(__name__)
        logger.info(f"应用程序正常退出，退出代码: {exit_code}")
        
        # 确保日志刷新到文件
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                handler.flush()
        
        sys.exit(exit_code)
    except Exception as e:
        # 捕获创建窗口时的异常
        logger = logging.getLogger(__name__)
        logger.critical(f"创建主窗口时发生异常: {e}", exc_info=True)
        logger.critical("程序异常退出")
        
        # 确保日志刷新到文件
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                handler.flush()
        
        sys.exit(1)


if __name__ == "__main__":
    main()
