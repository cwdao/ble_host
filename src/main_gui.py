#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BLE Host上位机主程序
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import logging
import os
from typing import List

try:
    from .serial_reader import SerialReader
    from .data_parser import DataParser
    from .data_processor import DataProcessor
    from .plotter import Plotter
    from .config import config, user_settings
    from .gui.dpi_manager import DPIManager
    from .data_saver import DataSaver
except ImportError:
    # 直接运行时使用绝对导入
    from serial_reader import SerialReader
    from data_parser import DataParser
    from data_processor import DataProcessor
    from plotter import Plotter
    from config import config, user_settings
    from gui.dpi_manager import DPIManager
    from data_saver import DataSaver

# 版本信息（从config导入）
__version__ = config.version
__version_date__ = config.version_date
__version_author__ = config.version_author


class BLEHostGUI:
    """主GUI应用程序"""
    
    def __init__(self, root):
        self.root = root
        # 标题栏显示版本号
        self.root.title(f"BLE CS Host v{__version__}")
        
        # DPI管理器应该在main()函数中创建（在创建root之前）
        # 如果没有传入，则创建一个（向后兼容）
        if not hasattr(self, 'dpi_manager'):
            self.dpi_manager = DPIManager()
        
        # 根据DPI缩放比例调整窗口大小
        window_width, window_height = self.dpi_manager.get_window_size()
        self.root.geometry(f"{window_width}x{window_height}")
        
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
        self.freq_list_thread = None
        self.stop_event = threading.Event()  # 用于通知线程停止
        self.is_saving = False  # 保存操作进行中标志
        self.use_auto_save = user_settings.get_use_auto_save_path()  # 自动保存模式
        self.auto_save_var = tk.BooleanVar(value=self.use_auto_save)  # 菜单checkbutton变量
        
        # 绘图刷新节流控制（避免频繁刷新导致GUI卡顿）
        self.last_plot_refresh_time = 0
        self.plot_refresh_interval = 0.2  # 最多每200ms刷新一次绘图
        
        # 帧数据处理
        self.frame_type = config.default_frame_type  # 当前选择的帧类型（字符串）
        self.frame_mode = (self.frame_type == "演示帧")  # 兼容性：是否启用帧模式（演示帧对应原来的帧模式）
        self.display_channel_list = list(range(10))  # 展示的信道列表，默认0-9
        self.display_max_frames = config.default_display_max_frames  # 显示和计算使用的最大帧数
        
        # 创建界面
        self._create_widgets()
        
        # 同步帧类型状态（确保self.frame_type与GUI下拉框一致）
        self.frame_type = self.frame_type_var.get()
        self.frame_mode = (self.frame_type == "演示帧")  # 更新兼容性变量
        if self.frame_mode:
            # 如果默认启用帧模式，应用设置（但不清空缓冲区，因为这是初始化阶段）
            self._apply_frame_settings()
            self.logger.info(f"帧类型已设置为: {self.frame_type}")
        
        # 定时刷新
        self._start_update_loop()
    
    def _setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def _set_save_path(self):
        """设置保存路径"""
        from tkinter import filedialog
        current_path = user_settings.get_save_directory()
        
        # 选择目录
        new_path = filedialog.askdirectory(
            title="选择保存目录",
            initialdir=current_path if os.path.exists(current_path) else "."
        )
        
        if new_path:
            user_settings.set_save_directory(new_path)
            self.logger.info(f"保存路径已设置为: {new_path}")
            messagebox.showinfo("成功", f"保存路径已设置为:\n{new_path}")
            # 更新文件选项卡中的路径显示
            self._update_path_display()
    
    def _toggle_auto_save(self):
        """切换自动保存模式"""
        # 从变量获取当前状态
        self.use_auto_save = self.auto_save_var.get()
        user_settings.set_use_auto_save_path(self.use_auto_save)
        mode_text = "启用" if self.use_auto_save else "禁用"
        self.logger.info(f"自动保存路径模式已{mode_text}")
    
    def _update_path_display(self):
        """更新文件选项卡中的路径显示"""
        if hasattr(self, 'path_label'):
            current_path = user_settings.get_save_directory()
            # 如果路径太长，截断显示
            display_path = current_path if len(current_path) <= 50 else "..." + current_path[-47:]
            self.path_label.config(text=f"当前路径: {display_path}")
    
    def _create_connection_tab(self, notebook):
        """创建连接配置选项卡"""
        connection_frame = ttk.Frame(notebook, padding="10")
        notebook.add(connection_frame, text="连接")
        
        # 串口选择
        ttk.Label(connection_frame, text="串口:").grid(row=0, column=0, padx=5, pady=5)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(connection_frame, textvariable=self.port_var, width=15)
        self.port_combo.grid(row=0, column=1, padx=5, pady=5)
        
        # 刷新串口按钮
        ttk.Button(connection_frame, text="刷新串口", command=self._refresh_ports).grid(row=0, column=2, padx=5, pady=5)
        
        # 波特率
        ttk.Label(connection_frame, text="波特率:").grid(row=0, column=3, padx=5, pady=5)
        self.baudrate_var = tk.StringVar(value=config.default_baudrate)
        baudrate_combo = ttk.Combobox(connection_frame, textvariable=self.baudrate_var, 
                                      values=config.baudrate_options, width=10)
        baudrate_combo.grid(row=0, column=4, padx=5, pady=5)
        
        # 连接/断开按钮
        self.connect_btn = ttk.Button(connection_frame, text="连接", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=5, padx=5, pady=5)
        
        # 帧类型选择（下拉列表，决定帧的解析方式）
        ttk.Label(connection_frame, text="帧类型:").grid(row=0, column=6, padx=5, pady=5)
        self.frame_type_var = tk.StringVar(value=config.default_frame_type)
        self.frame_type_combo = ttk.Combobox(connection_frame, textvariable=self.frame_type_var, 
                                            values=config.frame_type_options, width=12, state="readonly")
        self.frame_type_combo.grid(row=0, column=7, padx=5, pady=5)
        self.frame_type_combo.bind("<<ComboboxSelected>>", lambda e: self._on_frame_type_changed())
    
    def _create_channel_config_tab(self, notebook):
        """创建信道配置选项卡"""
        channel_frame = ttk.Frame(notebook, padding="10")
        notebook.add(channel_frame, text="信道配置")
        
        # 展示信道选择
        ttk.Label(channel_frame, text="展示信道:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.display_channels_var = tk.StringVar(value=config.default_display_channels)
        display_channels_entry = ttk.Entry(channel_frame, textvariable=self.display_channels_var, width=20)
        display_channels_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(channel_frame, text="(如: 0-9 或 0,2,4,6,8)").grid(row=0, column=2, padx=2, pady=5, sticky="w")
        
        # 显示帧数（用于plot和计算）
        ttk.Label(channel_frame, text="显示帧数:").grid(row=0, column=3, padx=5, pady=5, sticky="w")
        self.display_max_frames_var = tk.StringVar(value=str(config.default_display_max_frames))
        display_frames_entry = ttk.Entry(channel_frame, textvariable=self.display_max_frames_var, width=10)
        display_frames_entry.grid(row=0, column=4, padx=5, pady=5, sticky="w")
        ttk.Label(channel_frame, text="(plot和计算范围)").grid(row=0, column=5, padx=2, pady=5, sticky="w")
        
        # 应用按钮
        ttk.Button(channel_frame, text="应用", command=self._apply_frame_settings).grid(row=0, column=6, padx=5, pady=5, sticky="w")
    
    def _create_data_and_save_tab(self, notebook):
        """创建数据与保存选项卡（合并了文件和数据操作功能）"""
        data_frame = ttk.Frame(notebook, padding="10")
        notebook.add(data_frame, text="数据与保存")
        
        # 第一行：设置保存路径、自动保存路径复选框、当前路径显示
        ttk.Button(data_frame, text="设置保存路径...", command=self._set_save_path).grid(row=0, column=0, padx=5, pady=5)
        
        auto_save_check = ttk.Checkbutton(
            data_frame,
            text="使用自动保存路径",
            variable=self.auto_save_var,
            command=self._toggle_auto_save
        )
        auto_save_check.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # 显示当前保存路径（只读）
        current_path = user_settings.get_save_directory()
        # 如果路径太长，截断显示
        display_path = current_path if len(current_path) <= 50 else "..." + current_path[-47:]
        path_label = ttk.Label(data_frame, text=f"当前路径: {display_path}", foreground="gray")
        path_label.grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.path_label = path_label  # 保存引用以便更新
        
        # 第二行：保存数据按钮、保存选项、清空数据按钮
        self.save_btn = ttk.Button(data_frame, text="保存数据", command=self._save_data)
        self.save_btn.grid(row=1, column=0, padx=5, pady=5)
        
        # 保存选项（全部保存或最近N帧）
        self.save_option_var = tk.StringVar(value="全部保存")
        save_option_frame = ttk.Frame(data_frame)
        save_option_frame.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        ttk.Radiobutton(save_option_frame, text="全部保存", variable=self.save_option_var, 
                       value="全部保存").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(save_option_frame, text="最近N帧", variable=self.save_option_var, 
                       value="最近N帧").pack(side=tk.LEFT, padx=2)
        
        ttk.Button(data_frame, text="清空当前数据", command=self._clear_data).grid(row=1, column=2, padx=5, pady=5)
        
        # 第三行：保存状态显示
        ttk.Label(data_frame, text="保存状态:", font=("TkDefaultFont", 9, "bold")).grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.save_status_var = tk.StringVar(value="")
        self.save_status_label = ttk.Label(data_frame, textvariable=self.save_status_var, font=("TkDefaultFont", 9))
        self.save_status_label.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky="w")
    
    def _create_widgets(self):
        """创建GUI组件"""
        # 连接状态显示（在主界面上，不在tab中）
        status_frame = ttk.Frame(self.root, padding="5")
        status_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        ttk.Label(status_frame, text="连接状态:", font=("TkDefaultFont", 9, "bold")).pack(side=tk.LEFT, padx=5)
        self.status_var = tk.StringVar(value="未连接")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="red", font=("TkDefaultFont", 9))
        status_label.pack(side=tk.LEFT, padx=5)
        
        # 顶部配置选项卡区域（类似Office 2007的Ribbon风格）
        config_notebook = ttk.Notebook(self.root)
        config_notebook.pack(fill=tk.X, padx=5, pady=5)
        
        # 创建各个配置选项卡（按使用频率排序）
        self._create_connection_tab(config_notebook)
        self._create_channel_config_tab(config_notebook)
        self._create_data_and_save_tab(config_notebook)
        
        # 左右分栏
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧：多选项卡绘图区域
        self.notebook = ttk.Notebook(paned)
        paned.add(self.notebook, weight=2)
        
        # 创建多个选项卡
        self._create_plot_tabs()
        
        # 延迟调整plot尺寸（等待窗口完全初始化）
        self.root.after_idle(self._adjust_plot_sizes)
        
        # 右侧：控制面板
        self.right_frame = ttk.Frame(paned, width=300)
        paned.add(self.right_frame, weight=1)
        
        # DPI信息显示区域（调试用）
        dpi_info_frame = ttk.LabelFrame(self.right_frame, text="DPI缩放信息", padding="5")
        dpi_info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 创建DPI信息显示文本区域
        self.dpi_info_text = scrolledtext.ScrolledText(dpi_info_frame, height=6, width=30, font=("Courier", 8))
        self.dpi_info_text.pack(fill=tk.BOTH, expand=True)
        self.dpi_info_text.config(state=tk.DISABLED)  # 只读
        
        # 绑定窗口大小变化事件和tab切换事件
        self.root.bind('<Configure>', self._on_window_configure)
        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)
        
        # 延迟初始化DPI信息显示（等待窗口完全初始化）
        self.root.after(100, self._update_dpi_info)
        
        # 数据处理区域
        process_frame = ttk.LabelFrame(self.right_frame, text="数据处理", padding="10")
        process_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 频率计算（帧模式：通道频率，非帧模式：变量频率）
        freq_frame = ttk.Frame(process_frame)
        freq_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(freq_frame, text="选择:").pack(side=tk.LEFT, padx=5)
        self.freq_var_var = tk.StringVar()
        self.freq_var_combo = ttk.Combobox(freq_frame, textvariable=self.freq_var_var, width=15)
        self.freq_var_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(freq_frame, text="计算频率", command=self._calculate_frequency).pack(side=tk.LEFT, padx=5)
        
        self.freq_result_var = tk.StringVar(value="")
        ttk.Label(process_frame, textvariable=self.freq_result_var, foreground="blue").pack(pady=5)
        
        # 统计信息（自动更新）
        stats_label_frame = ttk.LabelFrame(process_frame, text="统计信息（自动更新）", padding="5")
        stats_label_frame.pack(fill=tk.X, pady=5)
        
        self.stats_text = scrolledtext.ScrolledText(stats_label_frame, height=8, width=30)
        self.stats_text.pack(fill=tk.BOTH, expand=True)
        
        # 绑定频率变量选择变化事件
        self.freq_var_var.trace_add('write', self._on_freq_var_changed)
        
        # 日志显示区域
        log_frame = ttk.LabelFrame(self.right_frame, text="日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=30)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 添加日志处理器
        text_handler = TextHandler(self.log_text)
        text_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        text_handler.setFormatter(formatter)
        logging.getLogger().addHandler(text_handler)
        
        # 版本信息显示（右下角，分两行显示）
        version_frame = ttk.Frame(self.right_frame)
        version_frame.pack(fill=tk.X, padx=5, pady=2)
        
        # 创建一个内部Frame用于垂直排列，然后整体右对齐
        version_inner = ttk.Frame(version_frame)
        version_inner.pack(side=tk.RIGHT, anchor=tk.E)
        
        # 第一行：版本号和日期
        # 版本信息使用较小的字体，但也根据DPI适度调整
        version_font_size = self.dpi_manager.get_version_font_size()
        version_line1 = ttk.Label(
            version_inner, 
            text=f"版本 v{__version__} | {__version_date__}",
            font=("TkDefaultFont", version_font_size),
            foreground="gray"
        )
        version_line1.pack(anchor=tk.E)
        
        # 第二行：作者信息
        version_line2 = ttk.Label(
            version_inner, 
            text=f"{__version_author__}",
            font=("TkDefaultFont", version_font_size),
            foreground="gray"
        )
        version_line2.pack(anchor=tk.E)
        
        # 初始化串口列表
        self._refresh_ports()
    
    def _update_dpi_info(self):
        """更新DPI信息显示"""
        self.dpi_info_text.config(state=tk.NORMAL)
        self.dpi_info_text.delete(1.0, tk.END)
        
        # 获取系统DPI信息
        info_lines = []
        info_lines.append(f"系统DPI缩放: {self.dpi_manager.scale_factor:.2f}x")
        
        # 获取实际DPI值
        system_dpi = self.dpi_manager.get_system_dpi()
        if system_dpi:
            info_lines.append(f"系统DPI: {system_dpi} (标准96)")
        else:
            import platform
            if platform.system() == 'Windows':
                info_lines.append(f"系统DPI: 无法获取")
            else:
                info_lines.append(f"系统DPI: N/A (非Windows)")
        
        info_lines.append(f"字体大小: {self.dpi_manager.font_size}pt")
        info_lines.append("")
        
        # 获取窗口尺寸
        window_width = self.root.winfo_width()
        window_height = self.root.winfo_height()
        if window_width > 1 and window_height > 1:  # 避免显示初始值1x1
            info_lines.append(f"窗口尺寸: {window_width}x{window_height}px")
        else:
            info_lines.append(f"窗口尺寸: 初始化中...")
        
        # 获取当前选中的tab
        try:
            current_tab_index = self.notebook.index(self.notebook.select())
            current_tab_text = self.notebook.tab(current_tab_index, "text")
            info_lines.append(f"当前Tab: {current_tab_text} (#{current_tab_index})")
        except:
            info_lines.append(f"当前Tab: 无")
        
        # 获取notebook尺寸
        try:
            nb_width = self.notebook.winfo_width()
            nb_height = self.notebook.winfo_height()
            if nb_width > 1 and nb_height > 1:  # 避免显示初始值1x1
                info_lines.append(f"Tab区域: {nb_width}x{nb_height}px")
            else:
                info_lines.append(f"Tab区域: 计算中...")
        except:
            info_lines.append(f"Tab区域: 计算中...")
        
        # 获取右侧面板尺寸
        try:
            if hasattr(self, 'right_frame'):
                rf_width = self.right_frame.winfo_width()
                rf_height = self.right_frame.winfo_height()
                if rf_width > 1 and rf_height > 1:  # 避免显示初始值1x1
                    info_lines.append(f"右侧面板: {rf_width}x{rf_height}px")
        except:
            pass
        
        # 获取当前plot的尺寸信息
        try:
            if hasattr(self, 'plotters') and self.plotters:
                # 获取当前tab对应的plotter信息
                current_tab_index = None
                try:
                    current_tab_index = self.notebook.index(self.notebook.select())
                    current_tab_text = self.notebook.tab(current_tab_index, "text")
                except:
                    pass
                
                # 根据tab名称找到对应的plotter
                plotter = None
                if current_tab_index is not None:
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
                        if tab_key in self.plotters:
                            plotter = self.plotters[tab_key]['plotter']
                
                # 如果没找到，使用第一个plotter
                if plotter is None:
                    plotter = list(self.plotters.values())[0]['plotter']
                
                fig_width = plotter.figure.get_figwidth()
                fig_height = plotter.figure.get_figheight()
                fig_dpi = plotter.figure.dpi
                # 计算实际像素尺寸
                plot_px_width = int(fig_width * fig_dpi)
                plot_px_height = int(fig_height * fig_dpi)
                info_lines.append("")
                info_lines.append(f"Plot尺寸: {fig_width:.2f}\"x{fig_height:.2f}\"")
                info_lines.append(f"Plot像素: {plot_px_width}x{plot_px_height}px")
                info_lines.append(f"Plot DPI: {fig_dpi}")
                # 添加说明：英寸尺寸看起来大是因为DPI=100，但像素尺寸是正确的
                if fig_dpi == 100:
                    info_lines.append("(英寸×100=像素)")
        except:
            pass
        
        # 写入信息
        self.dpi_info_text.insert(tk.END, "\n".join(info_lines))
        self.dpi_info_text.config(state=tk.DISABLED)
    
    def _on_window_configure(self, event):
        """窗口大小变化时的回调"""
        # 只响应主窗口的大小变化
        if event.widget == self.root:
            # 延迟更新，避免频繁刷新
            if hasattr(self, '_dpi_info_update_scheduled'):
                self.root.after_cancel(self._dpi_info_update_scheduled)
            self._dpi_info_update_scheduled = self.root.after(
                config.dpi_info_update_delay_ms, self._update_dpi_info
            )
            
            # 同时调整plot尺寸
            if hasattr(self, '_plot_resize_scheduled'):
                self.root.after_cancel(self._plot_resize_scheduled)
            self._plot_resize_scheduled = self.root.after(
                config.plot_resize_delay_ms, self._adjust_plot_sizes
            )
    
    def _on_tab_changed(self, event):
        """Tab切换时的回调"""
        # Tab切换时只调整当前可见tab的plot尺寸（优化性能）
        self.root.after(config.tab_changed_delay_ms, self._adjust_current_plot_size)
        # 延迟更新DPI信息，避免阻塞
        self.root.after(config.tab_changed_delay_ms + 50, self._update_dpi_info)
        # 切换tab时，更新新打开的tab的plot数据（使用保存的数据快速绘制）
        self.root.after(config.tab_changed_delay_ms, self._update_current_tab_plot)
    
    def _create_plot_tabs(self):
        """创建多选项卡绘图区域"""
        # 根据窗口大小计算plot的初始大小（使用DPI管理器）
        plot_width_inch, plot_height_inch = self.dpi_manager.get_plot_size()
        
        # 定义选项卡配置：(tab_key, tab_name, y_label, data_type)
        tab_configs = [
            ('amplitude', '幅值', 'Amplitude', 'amplitude'),
            ('phase', '相位', 'Phase (rad)', 'phase'),
            ('local_amplitude', 'Local观测Ref幅值', 'Local Amplitude', 'local_amplitude'),
            ('local_phase', 'Local观测Ref相位', 'Local Phase (rad)', 'local_phase'),
            ('remote_amplitude', 'Remote观测Ini幅值', 'Remote Amplitude', 'remote_amplitude'),
            ('remote_phase', 'Remote观测Ini相位', 'Remote Phase (rad)', 'remote_phase'),
        ]
        
        for tab_key, tab_name, y_label, data_type in tab_configs:
            # 创建选项卡页面
            tab_frame = ttk.Frame(self.notebook)
            self.notebook.add(tab_frame, text=tab_name)
            
            # 创建绘图器（根据窗口大小计算合适的初始大小）
            plotter = Plotter(figure_size=(plot_width_inch, plot_height_inch))
            plotter.ax.set_ylabel(y_label)
            
            # 附加到界面
            widget = plotter.attach_to_tkinter(tab_frame)
            widget.pack(fill=tk.BOTH, expand=True)
            
            # 保存引用
            self.plotters[tab_key] = {
                'plotter': plotter,
                'data_type': data_type,
                'frame': tab_frame
            }
    
    def _adjust_current_plot_size(self):
        """只调整当前可见tab的plot尺寸（优化性能）"""
        try:
            # 获取当前选中的tab
            try:
                current_tab_index = self.notebook.index(self.notebook.select())
            except:
                return  # 没有选中的tab
            
            # 获取notebook的实际尺寸
            self.root.update_idletasks()  # 确保窗口已经布局完成
            nb_width = self.notebook.winfo_width()
            nb_height = self.notebook.winfo_height()
            
            # 如果尺寸还不可用，延迟重试
            if nb_width <= 1 or nb_height <= 1:
                self.root.after(100, self._adjust_current_plot_size)
                return
            
            # 减去一些边距
            plot_width_px = max(100, nb_width - config.plot_margin_px)
            plot_height_px = max(100, nb_height - config.plot_margin_px)
            
            # 根据系统DPI缩放比例调整DPI，使字体和元素更大更清晰
            plot_dpi = self.dpi_manager.get_plot_dpi()
            
            # 根据tab索引找到对应的plotter
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
                if tab_key in self.plotters:
                    plotter = self.plotters[tab_key]['plotter']
                    # 只调整当前可见的plot尺寸
                    plotter.resize_figure(plot_width_px, plot_height_px, dpi=plot_dpi)
                    self.logger.debug(f"调整了当前tab ({tab_key}) 的plot尺寸: {plot_width_px}x{plot_height_px}px @ {plot_dpi}DPI")
        except Exception as e:
            self.logger.warning(f"调整当前plot尺寸时出错: {e}")
    
    def _adjust_plot_sizes(self):
        """根据实际容器大小调整所有plot尺寸（用于窗口大小变化时）"""
        try:
            # 获取notebook的实际尺寸
            self.root.update_idletasks()  # 确保窗口已经布局完成
            nb_width = self.notebook.winfo_width()
            nb_height = self.notebook.winfo_height()
            
            # 如果尺寸还不可用，延迟重试
            if nb_width <= 1 or nb_height <= 1:
                self.root.after(100, self._adjust_plot_sizes)
                return
            
            # 减去一些边距
            plot_width_px = max(100, nb_width - config.plot_margin_px)
            plot_height_px = max(100, nb_height - config.plot_margin_px)
            
            # 根据系统DPI缩放比例调整DPI，使字体和元素更大更清晰
            plot_dpi = self.dpi_manager.get_plot_dpi()
            
            # 根据DPI计算英寸尺寸，确保像素尺寸与容器匹配
            plot_width_inch = plot_width_px / plot_dpi
            plot_height_inch = plot_height_px / plot_dpi
            
            # 调整所有plot的尺寸（窗口大小变化时需要调整所有）
            adjusted_count = 0
            for tab_key, plotter_info in self.plotters.items():
                plotter = plotter_info['plotter']
                # 使用调整后的DPI，使字体和元素更大更清晰
                plotter.resize_figure(plot_width_px, plot_height_px, dpi=plot_dpi)
                adjusted_count += 1
            
            self.logger.debug(f"调整了{adjusted_count}个plot尺寸: {plot_width_inch:.2f}\"x{plot_height_inch:.2f}\" ({plot_width_px}x{plot_height_px}px @ {plot_dpi}DPI)")
            
            # 更新DPI信息显示
            self._update_dpi_info()
        except Exception as e:
            self.logger.warning(f"调整plot尺寸时出错: {e}")
    
    def _refresh_ports(self):
        """刷新串口列表"""
        ports = SerialReader.list_ports()
        port_list = [f"{p['port']} ({p['description']})" for p in ports]
        self.port_combo['values'] = port_list
        if port_list:
            self.port_combo.current(0)
    
    def _toggle_connection(self):
        """切换连接状态"""
        if self.is_running:
            self._disconnect()
        else:
            self._connect()
    
    def _connect(self):
        """连接串口"""
        port_str = self.port_var.get()
        if not port_str:
            messagebox.showerror("错误", "请选择串口")
            return
        
        # 提取端口名（去掉描述）
        port = port_str.split(' ')[0]
        
        try:
            baudrate = int(self.baudrate_var.get())
        except ValueError:
            messagebox.showerror("错误", "波特率无效")
            return
        
        self.serial_reader = SerialReader(port=port, baudrate=baudrate)
        
        if self.serial_reader.connect():
            self.is_running = True
            self.connect_btn.config(text="断开")
            self.status_var.set(f"已连接: {port}")
            self.logger.info(f"串口连接成功: {port} @ {baudrate}")
        else:
            messagebox.showerror("错误", "串口连接失败")
            self.logger.error("串口连接失败")
    
    def _disconnect(self):
        """断开串口（改进版本，避免GUI阻塞）"""
        # 先设置标志，停止数据处理
        self.is_running = False
        
        # 立即更新UI状态
        self.connect_btn.config(text="连接", state="disabled")  # 暂时禁用按钮，防止重复点击
        self.status_var.set("断开中...")
        self.logger.info("正在断开串口...")
        
        # 在后台线程中断开串口，避免阻塞GUI
        def disconnect_in_thread():
            try:
                if self.serial_reader:
                    self.serial_reader.disconnect()
                    self.serial_reader = None
            except Exception as e:
                self.logger.error(f"断开串口时出错: {e}")
            finally:
                # 在主线程中更新UI（使用after确保在主线程执行）
                self.root.after(0, self._update_disconnect_ui)
        
        # 启动后台线程执行断开操作
        disconnect_thread = threading.Thread(target=disconnect_in_thread, daemon=True)
        disconnect_thread.start()
    
    def _update_disconnect_ui(self):
        """更新断开连接后的UI状态（在主线程中执行）"""
        self.connect_btn.config(text="连接", state="normal")  # 恢复按钮
        self.status_var.set("未连接")
        self.logger.info("串口已断开")
    
    def _clear_data(self):
        """清空数据"""
        self.data_processor.clear_buffer(clear_frames=True)
        # 清空所有绘图器
        for plotter_info in self.plotters.values():
            plotter_info['plotter'].clear_plot()
            plotter_info['plotter'].refresh()
        self.data_parser.clear_buffer()
        self.logger.info("数据已清空")
    
    def _save_data(self):
        """统一的保存数据方法，根据选项执行相应的保存操作"""
        option = self.save_option_var.get()
        if option == "全部保存":
            self._save_all_frames()
        elif option == "最近N帧":
            self._save_recent_frames()
    
    def _save_all_frames(self):
        """保存所有帧数据（在后台线程中执行）"""
        if not self.frame_mode:
            messagebox.showwarning("警告", "当前不是帧模式，无法保存帧数据")
            return
        
        if self.is_saving:
            messagebox.showwarning("警告", "保存操作正在进行中，请稍候...")
            return
        
        frames = self.data_processor.raw_frames
        if not frames:
            messagebox.showwarning("警告", "没有可保存的帧数据")
            return
        
        # 根据设置决定是否弹出对话框
        if self.use_auto_save:
            # 使用自动保存路径
            filepath = self.data_saver.get_auto_save_path(prefix="frames", save_all=True)
            self.logger.info(f"使用自动保存路径: {filepath}")
        else:
            # 弹出对话框让用户选择路径
            from tkinter import filedialog
            default_filename = self.data_saver.get_default_filename(prefix="frames", save_all=True)
            filepath = filedialog.asksaveasfilename(
                title="保存所有帧数据",
                defaultextension=".json",
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                initialfile=default_filename
            )
            
            if not filepath:
                return  # 用户取消了保存
        
        # 在后台线程中执行保存操作
        def save_in_thread():
            try:
                self.is_saving = True
                # 更新UI状态
                def show_progress():
                    self.save_btn.config(state="disabled")
                    self.save_status_var.set(f"正在保存 {len(frames)} 帧数据...")
                    self.save_status_label.config(foreground="black")
                self.root.after(0, show_progress)
                
                # 执行保存（在后台线程中）
                success = self.data_saver.save_frames(frames, filepath, max_frames=None)
                
                # 在主线程中更新UI
                if success:
                    # 显示成功消息（绿色文字）
                    def show_success():
                        self.save_status_var.set(f"✓ 已保存 {len(frames)} 帧数据到: {filepath}")
                        self.save_status_label.config(foreground="green")
                    self.root.after(0, show_success)
                else:
                    def show_error():
                        self.save_status_var.set("✗ 保存失败，请查看日志")
                        self.save_status_label.config(foreground="red")
                    self.root.after(0, show_error)
            except Exception as e:
                self.logger.error(f"保存数据时出错: {e}")
                def show_exception():
                    self.save_status_var.set(f"✗ 保存失败: {str(e)}")
                    self.save_status_label.config(foreground="red")
                self.root.after(0, show_exception)
            finally:
                self.is_saving = False
                # 恢复UI状态
                self.root.after(0, lambda: self.save_btn.config(state="normal"))
        
        # 启动后台线程
        save_thread = threading.Thread(target=save_in_thread, daemon=True)
        save_thread.start()
    
    def _save_recent_frames(self):
        """保存最近N帧数据（在后台线程中执行）"""
        if not self.frame_mode:
            messagebox.showwarning("警告", "当前不是帧模式，无法保存帧数据")
            return
        
        if self.is_saving:
            messagebox.showwarning("警告", "保存操作正在进行中，请稍候...")
            return
        
        frames = self.data_processor.raw_frames
        if not frames:
            messagebox.showwarning("警告", "没有可保存的帧数据")
            return
        
        # 获取显示帧数参数
        try:
            max_frames = int(self.display_max_frames_var.get())
            if max_frames <= 0:
                raise ValueError("显示帧数必须大于0")
        except ValueError:
            max_frames = config.default_display_max_frames
            self.logger.warning(f"显示帧数无效，使用默认值: {max_frames}")
        
        # 根据设置决定是否弹出对话框
        if self.use_auto_save:
            # 使用自动保存路径
            filepath = self.data_saver.get_auto_save_path(
                prefix="frames", save_all=False, max_frames=max_frames
            )
            self.logger.info(f"使用自动保存路径: {filepath}")
        else:
            # 弹出对话框让用户选择路径
            from tkinter import filedialog
            default_filename = self.data_saver.get_default_filename(
                prefix="frames", save_all=False, max_frames=max_frames
            )
            filepath = filedialog.asksaveasfilename(
                title=f"保存最近{max_frames}帧数据",
                defaultextension=".json",
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                initialfile=default_filename
            )
            
            if not filepath:
                return  # 用户取消了保存
        
        saved_count = min(max_frames, len(frames))
        
        # 在后台线程中执行保存操作
        def save_in_thread():
            try:
                self.is_saving = True
                # 更新UI状态
                def show_progress():
                    self.save_btn.config(state="disabled")
                    self.save_status_var.set(f"正在保存最近 {saved_count} 帧数据...")
                    self.save_status_label.config(foreground="black")
                self.root.after(0, show_progress)
                
                # 执行保存（在后台线程中）
                success = self.data_saver.save_frames(frames, filepath, max_frames=max_frames)
                
                # 在主线程中更新UI
                if success:
                    # 显示成功消息（绿色文字）
                    def show_success():
                        self.save_status_var.set(f"✓ 已保存最近 {saved_count} 帧数据到: {filepath}")
                        self.save_status_label.config(foreground="green")
                    self.root.after(0, show_success)
                else:
                    def show_error():
                        self.save_status_var.set("✗ 保存失败，请查看日志")
                        self.save_status_label.config(foreground="red")
                    self.root.after(0, show_error)
            except Exception as e:
                self.logger.error(f"保存数据时出错: {e}")
                def show_exception():
                    self.save_status_var.set(f"✗ 保存失败: {str(e)}")
                    self.save_status_label.config(foreground="red")
                self.root.after(0, show_exception)
            finally:
                self.is_saving = False
                # 恢复UI状态
                self.root.after(0, lambda: self.save_btn.config(state="normal"))
        
        # 启动后台线程
        save_thread = threading.Thread(target=save_in_thread, daemon=True)
        save_thread.start()
    
    def _parse_display_channels(self, text: str) -> List[int]:
        """
        解析展示信道字符串
        支持格式：
        - "0-9" -> [0,1,2,3,4,5,6,7,8,9]
        - "0,2,4,6,8" -> [0,2,4,6,8]
        - "0-5,10,15-20" -> [0,1,2,3,4,5,10,15,16,17,18,19,20]
        
        Returns:
            信道号列表
        """
        channels = []
        text = text.strip()
        if not text:
            return list(range(10))  # 默认前10个
        
        try:
            # 按逗号分割
            parts = [p.strip() for p in text.split(',')]
            for part in parts:
                if '-' in part:
                    # 范围格式 "0-9"
                    start, end = part.split('-', 1)
                    start = int(start.strip())
                    end = int(end.strip())
                    if start <= end:
                        channels.extend(range(start, end + 1))
                else:
                    # 单个数字
                    channels.append(int(part.strip()))
            
            # 去重并排序
            channels = sorted(list(set(channels)))
            return channels
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"解析展示信道失败: {text}, 错误: {e}, 使用默认值")
            return list(range(10))
    
    def _apply_frame_settings(self):
        """应用帧模式设置"""
        # 解析展示帧数
        try:
            display_frames = int(self.display_max_frames_var.get())
            if display_frames > 0:
                self.display_max_frames = min(display_frames, config.max_display_max_frames)
                self.logger.info(f"显示帧数设置为: {self.display_max_frames}（用于plot和计算）")
            else:
                self.logger.warning(f"显示帧数必须大于0，使用默认值{config.default_display_max_frames}")
                self.display_max_frames = config.default_display_max_frames
                self.display_max_frames_var.set(str(config.default_display_max_frames))
        except ValueError:
            self.logger.warning(f"显示帧数无效，使用默认值{config.default_display_max_frames}")
            self.display_max_frames = config.default_display_max_frames
            self.display_max_frames_var.set(str(config.default_display_max_frames))
        
        # 解析展示信道
        display_text = self.display_channels_var.get()
        self.display_channel_list = self._parse_display_channels(display_text)
        self.logger.info(f"展示信道设置为: {self.display_channel_list}")
        
        # 立即更新绘图（如果有数据）
        if self.frame_mode:
            self._update_frame_plots()
            # 同时更新统计信息（因为使用了新的帧数范围）
            self._update_statistics()
    
    def _on_frame_type_changed(self):
        """帧类型选择变化时的回调"""
        old_frame_type = self.frame_type
        self.frame_type = self.frame_type_var.get()
        old_frame_mode = self.frame_mode
        self.frame_mode = (self.frame_type == "演示帧")  # 更新兼容性变量
        
        # 如果从非演示帧切换到演示帧，或从演示帧切换到非演示帧，需要清空数据
        if old_frame_mode != self.frame_mode:
            if self.frame_mode:
                self.logger.info(f"切换到帧类型: {self.frame_type} - 清空之前的非帧数据")
                # 切换到帧模式时，清空之前的非帧数据（只保留帧数据）
                self.data_processor.clear_buffer(clear_frames=False)  # 不清空帧数据
                # 清空所有绘图，只显示帧数据
                for plotter_info in self.plotters.values():
                    plotter_info['plotter'].clear_plot()
                # 清空解析器状态
                self.data_parser.clear_buffer()
                # 应用当前设置
                self._apply_frame_settings()
            else:
                self.logger.info(f"切换到帧类型: {self.frame_type} - 清空帧数据")
                # 切换到非帧模式时，清空帧数据
                self.data_processor.clear_buffer(clear_frames=True)
                for plotter_info in self.plotters.values():
                    plotter_info['plotter'].clear_plot()
        else:
            # 帧模式状态没有变化，只是类型变化（比如从演示帧切换到快速帧）
            self.logger.info(f"帧类型从 {old_frame_type} 切换到 {self.frame_type}")
            # 这里可以添加特定类型的处理逻辑
    
    def _calculate_frequency(self):
        """计算频率"""
        selected = self.freq_var_var.get()
        if not selected:
            messagebox.showerror("错误", "请选择变量或通道")
            return
        
        # 判断是帧模式还是非帧模式
        if self.frame_mode:
            # 帧模式：计算通道频率
            # 解析选择的值，可能是"ch0", "ch1"或"0", "1"
            try:
                if selected.startswith("ch"):
                    channel = int(selected[2:])
                else:
                    channel = int(selected)
                
                freq = self.data_processor.calculate_channel_frequency(channel, max_frames=self.display_max_frames)
                
                if freq is not None:
                    self.freq_result_var.set(f"通道{channel}频率: {freq:.4f} Hz")
                    # 详细日志已在 data_processor 中记录
                else:
                    self.freq_result_var.set("频率计算失败")
                    messagebox.showwarning("警告", f"通道{channel}频率计算失败，可能需要更多数据")
            except ValueError:
                messagebox.showerror("错误", f"无效的通道号: {selected}")
        else:
            # 非帧模式：计算变量频率
            freq = self.data_processor.calculate_frequency(selected, duration=config.default_frequency_duration)
            
            if freq is not None:
                self.freq_result_var.set(f"频率: {freq:.2f} Hz")
                # 详细日志已在 data_processor 中记录
            else:
                self.freq_result_var.set("频率计算失败")
                messagebox.showwarning("警告", "频率计算失败，可能需要更多数据")
    
    def _on_freq_var_changed(self, *args):
        """频率变量选择变化时的回调"""
        # 延迟更新，避免频繁刷新
        if hasattr(self, '_stats_update_scheduled'):
            self.root.after_cancel(self._stats_update_scheduled)
        self._stats_update_scheduled = self.root.after(100, self._update_statistics)
    
    def _update_statistics(self):
        """自动更新统计信息（基于当前选择的通道/变量）"""
        self.stats_text.delete(1.0, tk.END)
        
        selected = self.freq_var_var.get()
        if not selected:
            self.stats_text.insert(tk.END, "请选择通道或变量\n")
            return
        
        # 判断是帧模式还是非帧模式
        if self.frame_mode:
            # 帧模式：显示通道统计信息和频率
            try:
                # 解析选择的值，可能是"ch0", "ch1"或"0", "1"
                if selected.startswith("ch"):
                    channel = int(selected[2:])
                else:
                    channel = int(selected)
                
                # 使用设置的显示帧数
                max_frames = self.display_max_frames
                
                # 计算统计信息
                stats = self.data_processor.get_channel_statistics(channel, max_frames=max_frames)
                
                # 计算频率（基于当前plot显示的数据范围）- 获取详细信息
                freq_info = self.data_processor.calculate_channel_frequency_detailed(channel, max_frames=max_frames)

                if freq_info is not None:
                    freq = freq_info['frequency']
                    freq_min = 60 * freq  # 转换为次/分钟
                    self.stats_text.insert(tk.END, f"频率估计值（基于{stats['count'] if stats else 0}帧）:\n")
                    self.stats_text.insert(tk.END, f"  主频率: {freq_min:.1f}次/分钟 - ({freq:.4f} Hz)\n")
                    self.stats_text.insert(tk.END, f"  振幅: {freq_info['amplitude']:.2f}\n")
                    self.stats_text.insert(tk.END, f"  原始帧数: {freq_info['n_original']}, FFT点数: {freq_info['n_fft']} ({freq_info['fft_size_info']})\n")
                    self.stats_text.insert(tk.END, f"  采样间隔: {freq_info['dt']:.3f}秒, 均匀采样: {'是' if freq_info['is_uniform'] else '否'}\n")
                    self.stats_text.insert(tk.END, f"  已应用汉明窗: {'是' if freq_info['window_applied'] else '否'}\n")
                else:
                    self.stats_text.insert(tk.END, "频率估计值: 计算失败（数据不足）\n")

                if stats:
                    self.stats_text.insert(tk.END, f"通道 {channel} 统计信息（最近{stats['count']}帧，范围={max_frames}）:\n")
                    self.stats_text.insert(tk.END, f"  均值: {stats['mean']:.4f}\n")
                    # self.stats_text.insert(tk.END, f"  最大值: {stats['max']:.4f}\n")
                    # self.stats_text.insert(tk.END, f"  最小值: {stats['min']:.4f}\n")
                    # self.stats_text.insert(tk.END, f"  标准差: {stats['std']:.4f}\n")
                    self.stats_text.insert(tk.END, f"  数据点数: {stats['count']}\n")
                    self.stats_text.insert(tk.END, "\n")
                
            except ValueError:
                self.stats_text.insert(tk.END, f"无效的通道号: {selected}\n")
        else:
            # 非帧模式：显示变量统计信息和频率
            vars_list = self.data_processor.get_all_variables()
            if selected not in vars_list:
                self.stats_text.insert(tk.END, f"变量 '{selected}' 不存在\n")
                return
            
            # 计算统计信息
            duration = config.default_frequency_duration
            stats = self.data_processor.calculate_statistics(selected, duration=duration)
            
            if stats:
                self.stats_text.insert(tk.END, f"{selected} 统计信息（最近{duration}秒）:\n")
                self.stats_text.insert(tk.END, f"  均值: {stats['mean']:.4f}\n")
                self.stats_text.insert(tk.END, f"  最大值: {stats['max']:.4f}\n")
                self.stats_text.insert(tk.END, f"  最小值: {stats['min']:.4f}\n")
                self.stats_text.insert(tk.END, f"  标准差: {stats['std']:.4f}\n")
                self.stats_text.insert(tk.END, f"  数据点数: {stats['count']}\n")
                self.stats_text.insert(tk.END, "\n")
            
            # 计算频率 - 获取详细信息
            freq_info = self.data_processor.calculate_frequency_detailed(selected, duration=duration)
            
            if freq_info is not None:
                freq = freq_info['frequency']
                self.stats_text.insert(tk.END, f"频率估计值（基于{stats['count'] if stats else 0}个数据点）:\n")
                self.stats_text.insert(tk.END, f"  主频率: {freq:.4f} Hz\n")
                self.stats_text.insert(tk.END, f"  原始点数: {freq_info['n_original']}, FFT点数: {freq_info['n_fft']} ({freq_info['fft_size_info']})\n")
                self.stats_text.insert(tk.END, f"  采样间隔: {freq_info['dt']:.6f}秒, 均匀采样: {'是' if freq_info['is_uniform'] else '否'}\n")
                self.stats_text.insert(tk.END, f"  已应用汉明窗: {'是' if freq_info['window_applied'] else '否'}\n")
            else:
                self.stats_text.insert(tk.END, "频率估计值: 计算失败（数据不足）\n")
    
    def _start_update_loop(self):
        """启动数据更新循环"""
        def update_loop():
            while not self.stop_event.is_set():
                try:
                    if self.is_running and self.serial_reader:
                        # 获取串口数据
                        data = self.serial_reader.get_data(block=False)
                        
                        if data:
                            current_time = time.time()
                            
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
                                continue
                            
                            # 非帧模式：解析简单数据
                            parsed = self.data_parser.parse(data['text'])
                            
                            # 处理简单数据（向后兼容）
                            if parsed and not parsed.get('frame'):
                                self.data_processor.add_data(data['timestamp'], parsed)
                                
                                # 更新绘图 - 使用第一个绘图器
                                plotter = self.plotters['amplitude']['plotter']
                                for var_name, value in parsed.items():
                                    times, values = self.data_processor.get_data_range(
                                        var_name, duration=config.default_frequency_duration
                                    )
                                    if len(times) > 0:
                                        plotter.update_plot(var_name, times, values)
                                
                                # 更新变量列表（非帧模式）
                                vars_list = self.data_processor.get_all_variables()
                                self.freq_var_combo['values'] = vars_list
                                if vars_list and not self.freq_var_var.get():
                                    self.freq_var_combo.current(0)
                                    self.freq_var_var.set(vars_list[0])
                                
                                # 使用节流刷新，避免频繁刷新导致GUI卡顿
                                self._refresh_plotters_throttled()
                    
                    time.sleep(config.update_interval_sec)
                    
                except Exception as e:
                    if not self.stop_event.is_set():
                        self.logger.error(f"更新循环错误: {e}")
                    else:
                        break  # 如果正在停止，直接退出
        
        self.update_thread = threading.Thread(target=update_loop, daemon=True)
        self.update_thread.start()
        
        # 启动频率列表更新线程和统计信息自动更新
        def update_freq_list_and_stats():
            while not self.stop_event.is_set():
                try:
                    if self.frame_mode:
                        # 帧模式：显示可用通道
                        channels = self.data_processor.get_all_frame_channels()
                        if channels:
                            # 格式化为 "ch0", "ch1"
                            channel_list = [f"ch{ch}" for ch in channels[:config.max_freq_list_channels]]
                            # 获取当前选项列表（使用字典访问方式）
                            current_values = list(self.freq_var_combo['values'] or [])
                            if set(channel_list) != set(current_values):
                                self.freq_var_combo['values'] = channel_list
                                if channel_list and not self.freq_var_var.get():
                                    self.freq_var_combo.current(0)
                                    self.freq_var_var.set(channel_list[0])
                    else:
                        # 非帧模式：显示变量列表
                        vars_list = self.data_processor.get_all_variables()
                        # 获取当前选项列表（使用字典访问方式）
                        current_values = list(self.freq_var_combo['values'] or [])
                        if set(vars_list) != set(current_values):
                            self.freq_var_combo['values'] = vars_list
                            if vars_list and not self.freq_var_var.get():
                                self.freq_var_combo.current(0)
                                self.freq_var_var.set(vars_list[0])
                    
                    # 定期自动更新统计信息（即使选择没有变化，数据可能更新了）
                    self.root.after(0, self._update_statistics)
                    
                    time.sleep(config.freq_list_update_interval_sec)
                except Exception as e:
                    if not self.stop_event.is_set():
                        self.logger.error(f"更新频率列表错误: {e}")
                        time.sleep(1.0)
                    else:
                        break  # 如果正在停止，直接退出
        
        self.freq_list_thread = threading.Thread(target=update_freq_list_and_stats, daemon=True)
        self.freq_list_thread.start()
    
    def _update_frame_plots(self, tab_key=None):
        """
        更新帧数据绘图 - 根据设置显示指定通道的数据
        
        Args:
            tab_key: 要更新的tab键，None表示只更新当前打开的tab（优化性能）
        """
        all_channels = self.data_processor.get_all_frame_channels()
        
        self.logger.debug(f"[绘图调试] 所有可用通道: {all_channels}, 通道数: {len(all_channels)}")
        
        if not all_channels:
            self.logger.warning("[绘图调试] 没有找到任何通道数据")
            return
        
        # 根据设置的展示信道列表筛选
        display_channels = []
        for ch in self.display_channel_list:
            if ch in all_channels:
                display_channels.append(ch)
            else:
                self.logger.debug(f"[绘图调试] 通道{ch}不存在，跳过")
        
        self.logger.debug(f"[绘图调试] 显示通道: {display_channels}")
        
        if not display_channels:
            self.logger.warning(f"[绘图调试] 设置的展示信道 {self.display_channel_list} 中没有可用数据")
            return
        
        # 确定要更新的tab列表
        if tab_key is None:
            # 只更新当前打开的tab（优化性能）
            try:
                current_tab_index = self.notebook.index(self.notebook.select())
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
            except:
                # 如果获取当前tab失败，不更新任何tab
                tabs_to_update = []
        else:
            # 更新指定的tab
            tabs_to_update = [tab_key] if tab_key in self.plotters else []
        
        # 更新指定的选项卡的绘图
        for tab_key_to_update in tabs_to_update:
            plotter_info = self.plotters[tab_key_to_update]
            plotter = plotter_info['plotter']
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
        
        self.logger.debug(f"[绘图调试] 更新帧数据绘图: {len(display_channels)} 个通道, 更新了 {len(tabs_to_update)} 个tab")
    
    def _refresh_all_plotters(self):
        """刷新所有绘图器（立即刷新，用于tab切换等场景）"""
        for plotter_info in self.plotters.values():
            plotter_info['plotter'].refresh()
    
    def _refresh_plotters_throttled(self):
        """节流刷新绘图器（限制刷新频率，避免GUI卡顿）"""
        current_time = time.time()
        # 如果距离上次刷新时间超过间隔，才执行刷新
        if current_time - self.last_plot_refresh_time >= self.plot_refresh_interval:
            self.last_plot_refresh_time = current_time
            # 只刷新当前可见的plot，而不是所有plot（进一步优化性能）
            self._refresh_current_plotter()
    
    def _refresh_current_plotter(self):
        """只刷新当前可见的绘图器"""
        try:
            # 获取当前选中的绘图tab
            current_tab_index = self.notebook.index(self.notebook.select())
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
                if tab_key in self.plotters:
                    # 只刷新当前可见的plot
                    self.plotters[tab_key]['plotter'].refresh()
        except:
            # 如果获取当前tab失败，刷新所有plot（兜底）
            self._refresh_all_plotters()
    
    def _update_current_tab_plot(self):
        """更新当前打开的tab的plot数据（用于tab切换时快速绘制）"""
        try:
            current_tab_index = self.notebook.index(self.notebook.select())
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
                # 只更新当前打开的tab
                self._update_frame_plots(tab_key=tab_key)
                # 刷新显示
                if tab_key in self.plotters:
                    self.plotters[tab_key]['plotter'].refresh()
        except Exception as e:
            self.logger.warning(f"更新当前tab plot时出错: {e}")
    
    def on_closing(self):
        """窗口关闭事件"""
        self.logger.info("正在关闭程序...")
        
        # 设置停止事件，通知所有线程退出
        self.stop_event.set()
        
        # 断开串口连接
        if self.is_running:
            self.is_running = False
            if self.serial_reader:
                try:
                    # 快速断开，不等待线程
                    self.serial_reader.is_running = False
                    self.serial_reader.stop_event.set()
                    if self.serial_reader.serial and self.serial_reader.serial.is_open:
                        self.serial_reader.serial.close()
                except Exception as e:
                    self.logger.error(f"关闭串口时出错: {e}")
        
        # 等待更新线程结束（最多等待1秒）
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=1.0)
        
        if self.freq_list_thread and self.freq_list_thread.is_alive():
            self.freq_list_thread.join(timeout=1.0)
        
        self.logger.info("程序已关闭")
        self.root.destroy()


class TextHandler(logging.Handler):
    """自定义日志处理器，输出到Text组件"""
    
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
    
    def emit(self, record):
        msg = self.format(record)
        self.text_widget.insert(tk.END, msg + '\n')
        self.text_widget.see(tk.END)


def main():
    """主函数"""
    # 在创建root窗口之前初始化DPI管理器（计算缩放比例）
    dpi_manager = DPIManager()
    
    root = tk.Tk()
    # 在创建root后立即应用字体设置
    dpi_manager.apply_fonts()
    
    # 设置窗口图标
    try:
        import os
        import sys
        from PIL import Image, ImageTk
        
        # 获取图标文件路径
        # PyInstaller 打包后的程序使用 sys._MEIPASS 获取临时目录
        if getattr(sys, 'frozen', False):
            # 打包后的环境
            base_path = sys._MEIPASS
        else:
            # 开发环境
            base_path = os.path.dirname(os.path.dirname(__file__))
        
        # 图标文件路径
        icon_path_ico = os.path.join(base_path, 'assets', 'ico.ico')
        icon_path_png = os.path.join(base_path, 'assets', 'ico.png')
        
        icon_set = False
        
        # 优先使用高分辨率的 PNG 文件（用于窗口和任务栏图标，获得最佳清晰度）
        # ICO 文件主要用于 .exe 文件的图标，运行时窗口图标使用 PNG 可以获得更好的质量
        if os.path.exists(icon_path_png):
            try:
                # 直接使用 PNG 文件，保持原始高分辨率以获得最佳质量
                # iconphoto 方法支持 PNG，并且会自动缩放以适应不同场景
                img = Image.open(icon_path_png)
                photo = ImageTk.PhotoImage(img)
                root.iconphoto(True, photo)
                root._icon_photo = photo
                icon_set = True
            except Exception as e:
                logging.getLogger(__name__).debug(f"无法加载 PNG 图标: {e}")
        
        # 如果 PNG 不存在或加载失败，尝试使用 .ico 文件
        if not icon_set and os.path.exists(icon_path_ico):
            try:
                # 使用 iconbitmap 方法（直接支持 .ico 文件，Windows 会自动选择最佳尺寸）
                root.iconbitmap(icon_path_ico)
                icon_set = True
            except Exception:
                # 如果 iconbitmap 失败，尝试用 PIL 加载
                try:
                    img = Image.open(icon_path_ico)
                    photo = ImageTk.PhotoImage(img)
                    root.iconphoto(True, photo)
                    root._icon_photo = photo
                    icon_set = True
                except Exception as e:
                    logging.getLogger(__name__).debug(f"无法加载 ICO 文件: {e}")
        
        if not icon_set:
            logging.getLogger(__name__).warning(f"未找到图标文件: {icon_path_ico} 或 {icon_path_png}")
            
    except ImportError:
        # Pillow未安装，只能尝试使用 iconbitmap（仅支持.ico文件）
        try:
            import os
            import sys
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.dirname(__file__))
            icon_path = os.path.join(base_path, 'assets', 'ico.ico')
            if os.path.exists(icon_path):
                root.iconbitmap(icon_path)
        except Exception as e:
            logging.getLogger(__name__).warning(f"无法设置图标: {e}")
    except Exception as e:
        logging.getLogger(__name__).warning(f"设置图标时出错: {e}")
    
    app = BLEHostGUI(root)
    # 将DPI管理器传递给应用
    app.dpi_manager = dpi_manager
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()

