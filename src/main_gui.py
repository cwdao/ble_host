#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BLE Host上位机主程序
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import time
import logging
import os
import numpy as np
from typing import List, Optional, Dict
from datetime import datetime

try:
    from .serial_reader import SerialReader
    from .data_parser import DataParser
    from .data_processor import DataProcessor
    from .plotter import Plotter
    from .config import config, user_settings
    from .gui.dpi_manager import DPIManager
    from .data_saver import DataSaver
    from .breathing_estimator import BreathingEstimator
except ImportError:
    # 直接运行时使用绝对导入
    from serial_reader import SerialReader
    from data_parser import DataParser
    from data_processor import DataProcessor
    from plotter import Plotter
    from config import config, user_settings
    from gui.dpi_manager import DPIManager
    from data_saver import DataSaver
    from breathing_estimator import BreathingEstimator

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
        
        # 加载模式相关
        self.is_loaded_mode = False  # 是否处于加载模式
        self.loaded_frames = []  # 加载的帧数据
        self.loaded_file_info = None  # 加载的文件信息
        self.current_window_start = 0  # 当前时间窗起点（帧索引）
        self.breathing_estimator = BreathingEstimator()  # 呼吸估计器
        
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
    
    def _browse_load_file(self):
        """浏览加载文件"""
        filepath = filedialog.askopenfilename(
            title="选择要加载的文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if filepath:
            self.load_file_path_var.set(filepath)
    
    def _load_file(self):
        """加载文件"""
        filepath = self.load_file_path_var.get()
        if not filepath:
            messagebox.showwarning("警告", "请选择要加载的文件")
            return
        
        if not os.path.exists(filepath):
            messagebox.showerror("错误", f"文件不存在: {filepath}")
            return
        
        # 加载数据
        data = self.data_saver.load_frames(filepath)
        if data is None:
            messagebox.showerror("错误", "加载文件失败，请查看日志")
            return
        
        # 保存加载的数据
        self.loaded_frames = data.get('frames', [])
        self.loaded_file_info = data
        
        if len(self.loaded_frames) == 0:
            messagebox.showwarning("警告", "文件中没有帧数据")
            return
        
        # 进入加载模式
        self.is_loaded_mode = True
        
        # 更新文件信息显示
        self._update_load_file_info()
        
        # 显示滑动条并更新范围
        self.slider_frame.pack(fill=tk.X, padx=5, pady=5, before=self.notebook)
        max_start = max(0, len(self.loaded_frames) - self.display_max_frames)
        self.time_window_slider.config(from_=0, to=max_start)
        self.window_start_var.set(0)
        self.current_window_start = 0
        
        # 禁用连接和数据保存tab
        self._set_tabs_enabled(False)
        
        # 更新信道列表
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
        self.breathing_channel_combo['values'] = [str(ch) for ch in channel_list]
        if channel_list:
            self.breathing_channel_combo.current(0)
            self.breathing_channel_var.set(str(channel_list[0]))
        
        # 隐藏DPI和数据处理，显示呼吸估计控制
        self._update_right_panel_for_loaded_mode()
        
        # 更新绘图
        self._update_loaded_mode_plots()
        
        messagebox.showinfo("成功", f"成功加载 {len(self.loaded_frames)} 帧数据")
        self.logger.info(f"进入加载模式，共 {len(self.loaded_frames)} 帧")
    
    def _update_load_file_info(self):
        """更新加载文件信息显示"""
        if not self.loaded_file_info:
            return
        
        self.load_file_info_text.config(state=tk.NORMAL)
        self.load_file_info_text.delete(1.0, tk.END)
        
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
        
        self.load_file_info_text.insert(tk.END, "\n".join(info_lines))
        self.load_file_info_text.config(state=tk.DISABLED)
    
    def _on_slider_changed(self, value):
        """滑动条变化时的回调"""
        try:
            start = int(float(value))
            self.current_window_start = start
            self.window_start_var.set(start)
            self._update_loaded_mode_plots()
        except:
            pass
    
    def _on_window_start_changed(self):
        """时间窗起点输入框变化时的回调"""
        try:
            start = int(self.window_start_var.get())
            max_start = max(0, len(self.loaded_frames) - self.display_max_frames) if self.loaded_frames else 0
            start = max(0, min(start, max_start))
            self.current_window_start = start
            self.window_start_var.set(start)
            self.time_window_slider.set(start)
            self._update_loaded_mode_plots()
        except:
            pass
    
    def _set_tabs_enabled(self, enabled: bool):
        """启用或禁用连接和数据保存tab"""
        # 禁用/启用连接tab的控件
        if hasattr(self, 'port_combo'):
            state = 'normal' if enabled else 'disabled'
            self.port_combo.config(state=state)
            self.connect_btn.config(state=state)
            self.frame_type_combo.config(state=state)
        
        # 禁用/启用数据保存tab的控件
        if hasattr(self, 'save_btn'):
            state = 'normal' if enabled else 'disabled'
            self.save_btn.config(state=state)
            self.clear_data_btn.config(state=state)
    
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
        
        # 连接/断开按钮（使用tk.Button以便设置颜色）
        self.connect_btn = tk.Button(connection_frame, text="连接", command=self._toggle_connection,
                                     bg="#4CAF50", fg="white", activebackground="#45a049",
                                     activeforeground="white", relief=tk.RAISED, bd=2)
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
        
        # 第一行：信道选择模式
        ttk.Label(channel_frame, text="选择模式:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.channel_mode_var = tk.StringVar(value="手动输入")
        self.channel_mode_combo = ttk.Combobox(
            channel_frame, 
            textvariable=self.channel_mode_var,
            values=["间隔X信道", "信道范围", "手动输入"],
            width=12,
            state="readonly"
        )
        self.channel_mode_combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.channel_mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_channel_mode_changed())
        
        # 输入框容器（根据模式显示不同的输入框）
        self.channel_input_frame = ttk.Frame(channel_frame)
        self.channel_input_frame.grid(row=0, column=2, columnspan=3, padx=5, pady=5, sticky="w")
        
        # 间隔信道输入框
        self.interval_input_var = tk.StringVar(value="4")
        self.interval_entry = ttk.Entry(self.channel_input_frame, textvariable=self.interval_input_var, width=10)
        self.interval_entry.grid(row=0, column=0, padx=2, sticky="w")
        self.interval_label = ttk.Label(self.channel_input_frame, text="(间隔数，如4表示0,4,8,12...)", foreground="gray")
        self.interval_label.grid(row=0, column=1, padx=2, sticky="w")
        
        # 信道范围输入框
        self.range_input_var = tk.StringVar(value="0-9")
        self.range_entry = ttk.Entry(self.channel_input_frame, textvariable=self.range_input_var, width=20)
        self.range_entry.grid(row=0, column=0, padx=2, sticky="w")
        self.range_label = ttk.Label(self.channel_input_frame, text="(如: 0-9 或 0-9,20-30)", foreground="gray")
        self.range_label.grid(row=0, column=1, padx=2, sticky="w")
        
        # 手动输入框
        self.display_channels_var = tk.StringVar(value=config.default_display_channels)
        self.display_channels_entry = ttk.Entry(self.channel_input_frame, textvariable=self.display_channels_var, width=20)
        self.display_channels_entry.grid(row=0, column=0, padx=2, sticky="w")
        self.manual_label = ttk.Label(self.channel_input_frame, text="(如: 0-9 或 0,2,4,6,8)", foreground="gray")
        self.manual_label.grid(row=0, column=1, padx=2, sticky="w")
        
        # 初始显示手动输入模式
        self._show_channel_input_mode("手动输入")
        
        # 显示帧数（用于plot和计算）
        ttk.Label(channel_frame, text="显示帧数:").grid(row=0, column=5, padx=5, pady=5, sticky="w")
        self.display_max_frames_var = tk.StringVar(value=str(config.default_display_max_frames))
        self.display_frames_entry = ttk.Entry(channel_frame, textvariable=self.display_max_frames_var, width=10)
        self.display_frames_entry.grid(row=0, column=6, padx=5, pady=5, sticky="w")
        ttk.Label(channel_frame, text="(plot和计算范围)").grid(row=0, column=7, padx=2, pady=5, sticky="w")
        
        # 应用按钮
        self.apply_settings_btn = ttk.Button(channel_frame, text="应用", command=self._apply_frame_settings)
        self.apply_settings_btn.grid(row=0, column=8, padx=5, pady=5, sticky="w")
        
        # 保存控件引用以便在连接/断开时启用/禁用
        self.channel_config_widgets = [
            self.channel_mode_combo,
            self.interval_entry,
            self.range_entry,
            self.display_channels_entry,
            self.display_frames_entry,
            self.apply_settings_btn
        ]
    
    def _create_load_tab(self, notebook):
        """创建加载选项卡"""
        load_frame = ttk.Frame(notebook, padding="10")
        notebook.add(load_frame, text="加载")
        
        # 文件路径选择
        path_frame = ttk.Frame(load_frame)
        path_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(path_frame, text="文件路径:").pack(side=tk.LEFT, padx=5)
        self.load_file_path_var = tk.StringVar()
        self.load_file_entry = ttk.Entry(path_frame, textvariable=self.load_file_path_var, width=50)
        self.load_file_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        ttk.Button(path_frame, text="浏览...", command=self._browse_load_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(path_frame, text="加载文件", command=self._load_file).pack(side=tk.LEFT, padx=5)
        
        # 文件信息显示
        info_frame = ttk.LabelFrame(load_frame, text="文件信息", padding="5")
        info_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.load_file_info_text = scrolledtext.ScrolledText(info_frame, height=8, width=50, font=("Courier", 9))
        self.load_file_info_text.pack(fill=tk.BOTH, expand=True)
        self.load_file_info_text.config(state=tk.DISABLED)  # 只读
        
        # 保存控件引用以便在加载模式下禁用/启用
        self.load_tab_widgets = {
            'load_file_entry': self.load_file_entry,
            'load_file_path_var': self.load_file_path_var
        }
    
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
        self.save_btn = tk.Button(data_frame, text="保存数据", command=self._save_data, 
                                  bg="#4CAF50", fg="white", activebackground="#45a049", 
                                  activeforeground="white", relief=tk.RAISED, bd=2)
        self.save_btn.grid(row=1, column=0, padx=5, pady=5)
        
        # 保存选项（全部保存或最近N帧）
        self.save_option_var = tk.StringVar(value="全部保存")
        save_option_frame = ttk.Frame(data_frame)
        save_option_frame.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        ttk.Radiobutton(save_option_frame, text="全部保存", variable=self.save_option_var, 
                       value="全部保存").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(save_option_frame, text="最近N帧", variable=self.save_option_var, 
                       value="最近N帧").pack(side=tk.LEFT, padx=2)
        
        self.clear_data_btn = tk.Button(data_frame, text="清空当前数据", command=self._clear_data,
                                        bg="#f44336", fg="white", activebackground="#da190b",
                                        activeforeground="white", relief=tk.RAISED, bd=2)
        self.clear_data_btn.grid(row=1, column=2, padx=5, pady=5)
        
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
        self._create_load_tab(config_notebook)
        
        # 左右分栏
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧：多选项卡绘图区域（包含滑动条）
        left_container = ttk.Frame(paned)
        paned.add(left_container, weight=2)
        
        # 滑动条容器（在绘图区域上方，初始隐藏）
        self.slider_frame = ttk.Frame(left_container)
        # 初始不显示，加载模式下才显示
        
        # 滑动条和输入框
        slider_inner = ttk.Frame(self.slider_frame)
        slider_inner.pack(fill=tk.X)
        
        ttk.Label(slider_inner, text="时间窗起点:").pack(side=tk.LEFT, padx=5)
        self.window_start_var = tk.IntVar(value=0)
        self.window_start_entry = ttk.Entry(slider_inner, textvariable=self.window_start_var, width=10)
        self.window_start_entry.pack(side=tk.LEFT, padx=5)
        self.window_start_entry.bind('<Return>', lambda e: self._on_window_start_changed())
        
        ttk.Label(slider_inner, text="(帧)").pack(side=tk.LEFT, padx=2)
        
        # 滑动条
        self.time_window_slider = ttk.Scale(slider_inner, from_=0, to=100, orient=tk.HORIZONTAL, 
                                             length=400, command=self._on_slider_changed)
        self.time_window_slider.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 时间窗长度显示
        self.window_length_label = ttk.Label(slider_inner, text="时间窗长度: -- 秒")
        self.window_length_label.pack(side=tk.LEFT, padx=5)
        
        # 绘图区域
        self.notebook = ttk.Notebook(left_container)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # 创建多个选项卡
        self._create_plot_tabs()
        
        # 延迟调整plot尺寸（等待窗口完全初始化）
        self.root.after_idle(self._adjust_plot_sizes)
        
        # 右侧：控制面板
        self.right_frame = ttk.Frame(paned, width=300)
        paned.add(self.right_frame, weight=1)
        
        # DPI信息显示区域（调试用）
        self.dpi_info_frame = ttk.LabelFrame(self.right_frame, text="DPI缩放信息", padding="5")
        self.dpi_info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 创建DPI信息显示文本区域
        self.dpi_info_text = scrolledtext.ScrolledText(self.dpi_info_frame, height=6, width=30, font=("Courier", 8))
        self.dpi_info_text.pack(fill=tk.BOTH, expand=True)
        self.dpi_info_text.config(state=tk.DISABLED)  # 只读
        
        # 绑定窗口大小变化事件和tab切换事件
        self.root.bind('<Configure>', self._on_window_configure)
        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)
        
        # 延迟初始化DPI信息显示（等待窗口完全初始化）
        self.root.after(100, self._update_dpi_info)
        
        # 数据处理区域
        self.process_frame = ttk.LabelFrame(self.right_frame, text="数据处理", padding="10")
        self.process_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 呼吸估计控制区域（加载模式下显示）
        self.breathing_control_frame = ttk.LabelFrame(self.right_frame, text="Breathing Estimation Control", padding="10")
        # 初始不显示，加载模式下才显示
        
        # 创建呼吸估计控制控件
        self._create_breathing_control_widgets()
        
        # 频率计算（帧模式：通道频率，非帧模式：变量频率）
        freq_frame = ttk.Frame(self.process_frame)
        freq_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(freq_frame, text="选择:").pack(side=tk.LEFT, padx=5)
        self.freq_var_var = tk.StringVar()
        self.freq_var_combo = ttk.Combobox(freq_frame, textvariable=self.freq_var_var, width=15)
        self.freq_var_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(freq_frame, text="计算频率", command=self._calculate_frequency).pack(side=tk.LEFT, padx=5)
        
        self.freq_result_var = tk.StringVar(value="")
        ttk.Label(self.process_frame, textvariable=self.freq_result_var, foreground="blue").pack(pady=5)
        
        # 统计信息（自动更新）
        stats_label_frame = ttk.LabelFrame(self.process_frame, text="统计信息（自动更新）", padding="5")
        stats_label_frame.pack(fill=tk.X, pady=5)
        
        self.stats_text = scrolledtext.ScrolledText(stats_label_frame, height=8, width=30)
        self.stats_text.pack(fill=tk.BOTH, expand=True)
        
        # 绑定频率变量选择变化事件
        self.freq_var_var.trace_add('write', self._on_freq_var_changed)
        
        # 日志显示区域
        self.log_frame = ttk.LabelFrame(self.right_frame, text="日志", padding="10")
        self.log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=15, width=30)
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
        
        # 创建呼吸估计tab（2x2布局）
        self._create_breathing_estimation_tab()
    
    def _create_breathing_estimation_tab(self):
        """创建呼吸估计选项卡（2x2子图布局）"""
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        
        tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(tab_frame, text="呼吸估计")
        
        # 创建2x2子图的figure
        plot_width_inch, plot_height_inch = self.dpi_manager.get_plot_size()
        figure = Figure(figsize=(plot_width_inch, plot_height_inch), dpi=100)
        
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
        canvas = FigureCanvasTkAgg(figure, tab_frame)
        canvas.draw()
        widget = canvas.get_tk_widget()
        widget.pack(fill=tk.BOTH, expand=True)
        
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
                    plotter_info = self.plotters[tab_key]
                    plotter = plotter_info.get('plotter')
                    if plotter is not None:
                        # 只调整当前可见的plot尺寸
                        plotter.resize_figure(plot_width_px, plot_height_px, dpi=plot_dpi)
                        self.logger.debug(f"调整了当前tab ({tab_key}) 的plot尺寸: {plot_width_px}x{plot_height_px}px @ {plot_dpi}DPI")
                    elif 'figure' in plotter_info:
                        # 呼吸估计tab使用figure
                        figure = plotter_info['figure']
                        width_inch = plot_width_px / plot_dpi
                        height_inch = plot_height_px / plot_dpi
                        figure.set_size_inches(width_inch, height_inch)
                        figure.set_dpi(plot_dpi)
                        if 'canvas' in plotter_info:
                            plotter_info['canvas'].draw_idle()
            elif current_tab_index == len(tab_configs):
                # 可能是呼吸估计tab
                if 'breathing_estimation' in self.plotters:
                    plotter_info = self.plotters['breathing_estimation']
                    if 'figure' in plotter_info:
                        figure = plotter_info['figure']
                        width_inch = plot_width_px / plot_dpi
                        height_inch = plot_height_px / plot_dpi
                        figure.set_size_inches(width_inch, height_inch)
                        figure.set_dpi(plot_dpi)
                        if 'canvas' in plotter_info:
                            plotter_info['canvas'].draw_idle()
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
                plotter = plotter_info.get('plotter')
                # 跳过呼吸估计tab（plotter为None，使用figure）
                if plotter is None:
                    # 呼吸估计tab使用figure，需要单独处理
                    if 'figure' in plotter_info:
                        figure = plotter_info['figure']
                        width_inch = plot_width_px / plot_dpi
                        height_inch = plot_height_px / plot_dpi
                        figure.set_size_inches(width_inch, height_inch)
                        figure.set_dpi(plot_dpi)
                        if 'canvas' in plotter_info:
                            plotter_info['canvas'].draw_idle()
                    adjusted_count += 1
                    continue
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
            # 更新连接按钮为红色（断开状态）
            self.connect_btn.config(text="断开", bg="#f44336", activebackground="#da190b")
            self.status_var.set(f"已连接: {port}")
            # 禁用信道配置tab的所有控件
            self._set_channel_config_enabled(False)
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
        # 恢复连接按钮为绿色（连接状态）
        self.connect_btn.config(text="连接", state="normal", bg="#4CAF50", activebackground="#45a049")
        self.status_var.set("未连接")
        # 启用信道配置tab的所有控件
        self._set_channel_config_enabled(True)
        self.logger.info("串口已断开")
    
    def _clear_data(self):
        """清空数据"""
        self.data_processor.clear_buffer(clear_frames=True)
        # 清空所有绘图器（包括图例）
        for plotter_info in self.plotters.values():
            plotter = plotter_info.get('plotter')
            # 跳过呼吸估计tab（plotter为None）
            if plotter is None:
                continue
            # 清除所有数据线
            plotter.clear_plot()
            # 清除图例
            if plotter.ax.get_legend():
                plotter.ax.get_legend().remove()
            plotter.refresh()
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
    
    def _parse_interval_channels(self, interval_str: str) -> List[int]:
        """
        解析间隔信道模式
        例如：输入4 -> [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 68, 72]
        
        Args:
            interval_str: 间隔数（字符串）
        
        Returns:
            信道号列表
        """
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
            return list(range(0, 73, 4))  # 默认间隔4
    
    def _parse_range_channels(self, range_str: str) -> List[int]:
        """
        解析信道范围模式
        支持格式：
        - "0-9" -> [0,1,2,3,4,5,6,7,8,9]
        - "0-9,20-30" -> [0,1,2,...,9,20,21,...,30]
        
        Args:
            range_str: 范围字符串
        
        Returns:
            信道号列表
        """
        channels = []
        range_str = range_str.strip()
        if not range_str:
            return list(range(10))  # 默认前10个
        
        try:
            # 按逗号分割
            parts = [p.strip() for p in range_str.split(',')]
            for part in parts:
                if '-' in part:
                    # 范围格式 "0-9"
                    start, end = part.split('-', 1)
                    start = int(start.strip())
                    end = int(end.strip())
                    # 限制范围在0-72之间
                    start = max(0, min(start, 72))
                    end = max(0, min(end, 72))
                    if start <= end:
                        channels.extend(range(start, end + 1))
                else:
                    # 单个数字
                    ch = int(part.strip())
                    if 0 <= ch <= 72:
                        channels.append(ch)
            
            # 去重并排序
            channels = sorted(list(set(channels)))
            return channels
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"解析信道范围失败: {range_str}, 错误: {e}, 使用默认值")
            return list(range(10))
    
    def _parse_display_channels(self, text: str) -> List[int]:
        """
        解析展示信道字符串（手动输入模式）
        支持格式：
        - "0-9" -> [0,1,2,3,4,5,6,7,8,9]
        - "0,2,4,6,8" -> [0,2,4,6,8]
        - "0-5,10,15-20" -> [0,1,2,3,4,5,10,15,16,17,18,19,20]
        
        Returns:
            信道号列表（限制在0-72之间）
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
                    # 限制范围在0-72之间
                    start = max(0, min(start, 72))
                    end = max(0, min(end, 72))
                    if start <= end:
                        channels.extend(range(start, end + 1))
                else:
                    # 单个数字
                    ch = int(part.strip())
                    if 0 <= ch <= 72:
                        channels.append(ch)
            
            # 去重并排序
            channels = sorted(list(set(channels)))
            return channels
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"解析展示信道失败: {text}, 错误: {e}, 使用默认值")
            return list(range(10))
    
    def _on_channel_mode_changed(self):
        """信道选择模式变化时的回调"""
        mode = self.channel_mode_var.get()
        self._show_channel_input_mode(mode)
    
    def _show_channel_input_mode(self, mode: str):
        """根据模式显示对应的输入框"""
        # 隐藏所有输入框和标签
        self.interval_entry.grid_remove()
        self.interval_label.grid_remove()
        self.range_entry.grid_remove()
        self.range_label.grid_remove()
        self.display_channels_entry.grid_remove()
        self.manual_label.grid_remove()
        
        # 显示对应模式的输入框和标签
        if mode == "间隔X信道":
            self.interval_entry.grid(row=0, column=0, padx=2, sticky="w")
            self.interval_label.grid(row=0, column=1, padx=2, sticky="w")
        elif mode == "信道范围":
            self.range_entry.grid(row=0, column=0, padx=2, sticky="w")
            self.range_label.grid(row=0, column=1, padx=2, sticky="w")
        else:  # 手动输入
            self.display_channels_entry.grid(row=0, column=0, padx=2, sticky="w")
            self.manual_label.grid(row=0, column=1, padx=2, sticky="w")
    
    def _set_channel_config_enabled(self, enabled: bool):
        """启用或禁用信道配置tab的所有控件"""
        if hasattr(self, 'channel_config_widgets'):
            state = 'normal' if enabled else 'disabled'
            for widget in self.channel_config_widgets:
                try:
                    widget.config(state=state)
                except:
                    pass  # 某些控件可能不支持state参数
    
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
        
        # 根据选择的模式解析展示信道
        mode = self.channel_mode_var.get()
        old_display_channel_list = self.display_channel_list.copy() if hasattr(self, 'display_channel_list') and self.display_channel_list else []
        
        if mode == "间隔X信道":
            interval_str = self.interval_input_var.get()
            new_display_channel_list = self._parse_interval_channels(interval_str)
        elif mode == "信道范围":
            range_str = self.range_input_var.get()
            new_display_channel_list = self._parse_range_channels(range_str)
        else:  # 手动输入
            display_text = self.display_channels_var.get()
            new_display_channel_list = self._parse_display_channels(display_text)
        
        # 清除不再需要的信道图例（在更新之前清除，避免图例残留）
        if self.frame_mode and old_display_channel_list:
            # 找出需要移除的信道（在old中但不在new中）
            channels_to_remove = set(old_display_channel_list) - set(new_display_channel_list)
            if channels_to_remove:
                for plotter_info in self.plotters.values():
                    plotter = plotter_info.get('plotter')
                    # 跳过呼吸估计tab（plotter为None）
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
            self.time_window_slider.config(from_=0, to=max_start)
            # 确保当前起点不超过最大值
            if self.current_window_start > max_start:
                self.current_window_start = max_start
                self.window_start_var.set(max_start)
                self.time_window_slider.set(max_start)
        
        # 立即更新绘图（如果有数据）
        if self.frame_mode:
            self._update_frame_plots()
            # 同时更新统计信息（因为使用了新的帧数范围）
            self._update_statistics()
        
        # 如果在加载模式，更新加载模式的绘图
        if self.is_loaded_mode:
            self._update_loaded_mode_plots()
    
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
                    plotter = plotter_info.get('plotter')
                    if plotter is not None:
                        plotter.clear_plot()
                # 清空解析器状态
                self.data_parser.clear_buffer()
                # 应用当前设置
                self._apply_frame_settings()
            else:
                self.logger.info(f"切换到帧类型: {self.frame_type} - 清空帧数据")
                # 切换到非帧模式时，清空帧数据
                self.data_processor.clear_buffer(clear_frames=True)
                for plotter_info in self.plotters.values():
                    plotter = plotter_info.get('plotter')
                    if plotter is not None:
                        plotter.clear_plot()
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
            plotter = plotter_info.get('plotter')
            # 跳过呼吸估计tab（plotter为None）
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
        
        self.logger.debug(f"[绘图调试] 更新帧数据绘图: {len(display_channels)} 个通道, 更新了 {len(tabs_to_update)} 个tab")
    
    def _refresh_all_plotters(self):
        """刷新所有绘图器（立即刷新，用于tab切换等场景）"""
        for plotter_info in self.plotters.values():
            plotter = plotter_info.get('plotter')
            if plotter is not None:
                plotter.refresh()
            elif 'canvas' in plotter_info:
                # 呼吸估计tab使用canvas
                plotter_info['canvas'].draw_idle()
    
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
    
    def _create_breathing_control_widgets(self):
        """创建呼吸估计控制控件"""
        # 数据类型选择
        data_type_frame = ttk.Frame(self.breathing_control_frame)
        data_type_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(data_type_frame, text="Data Type:").pack(side=tk.LEFT, padx=5)
        self.breathing_data_type_var = tk.StringVar(value="amplitude")
        data_type_combo = ttk.Combobox(
            data_type_frame, 
            textvariable=self.breathing_data_type_var,
            values=["amplitude", "local_amplitude", "remote_amplitude", "phase", "local_phase", "remote_phase"],
            width=15,
            state="readonly"
        )
        data_type_combo.pack(side=tk.LEFT, padx=5)
        data_type_combo.bind("<<ComboboxSelected>>", lambda e: self._update_loaded_mode_plots())
        
        # 信道选择
        channel_frame = ttk.Frame(self.breathing_control_frame)
        channel_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(channel_frame, text="Channel:").pack(side=tk.LEFT, padx=5)
        self.breathing_channel_var = tk.StringVar(value="0")
        self.breathing_channel_combo = ttk.Combobox(channel_frame, textvariable=self.breathing_channel_var, width=15)
        self.breathing_channel_combo.pack(side=tk.LEFT, padx=5)
        self.breathing_channel_combo.bind("<<ComboboxSelected>>", lambda e: self._update_loaded_mode_plots())
        
        # 阈值输入
        threshold_frame = ttk.Frame(self.breathing_control_frame)
        threshold_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(threshold_frame, text="Threshold:").pack(side=tk.LEFT, padx=5)
        self.breathing_threshold_var = tk.StringVar(value="0.6")
        threshold_entry = ttk.Entry(threshold_frame, textvariable=self.breathing_threshold_var, width=10)
        threshold_entry.pack(side=tk.LEFT, padx=5)
        threshold_entry.bind('<Return>', lambda e: self._update_loaded_mode_plots())
        
        ttk.Button(threshold_frame, text="Update", command=self._update_loaded_mode_plots).pack(side=tk.LEFT, padx=5)
    
    def _update_right_panel_for_loaded_mode(self):
        """更新右侧面板：加载模式下隐藏DPI和数据处理，显示呼吸估计控制"""
        if self.is_loaded_mode:
            # 隐藏DPI和数据处理
            self.dpi_info_frame.pack_forget()
            self.process_frame.pack_forget()
            # 显示呼吸估计控制
            self.breathing_control_frame.pack(fill=tk.X, padx=5, pady=5, before=self.log_frame)
        else:
            # 显示DPI和数据处理
            self.dpi_info_frame.pack(fill=tk.X, padx=5, pady=5)
            self.process_frame.pack(fill=tk.X, padx=5, pady=5)
            # 隐藏呼吸估计控制
            self.breathing_control_frame.pack_forget()
    
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
            # 计算时间跨度
            time_span = (window_frames[-1]['timestamp_ms'] - window_frames[0]['timestamp_ms']) / 1000.0
            self.window_length_label.config(text=f"时间窗长度: {time_span:.2f} 秒")
        else:
            self.window_length_label.config(text="时间窗长度: -- 秒")
    
    def _update_loaded_plots_for_tabs(self, window_frames: List[Dict]):
        """更新加载模式下各个tab的绘图"""
        # 提取所有通道的数据
        all_channels = set()
        for frame in window_frames:
            all_channels.update(frame.get('channels', {}).keys())
        
        # 根据设置的展示信道列表筛选
        display_channels = []
        for ch in self.display_channel_list:
            ch_key = ch if ch in all_channels else (str(ch) if str(ch) in all_channels else None)
            if ch_key is not None:
                display_channels.append(ch_key)
        
        if not display_channels:
            return
        
        # 为每个tab更新数据
        for tab_key, plotter_info in self.plotters.items():
            if tab_key == 'breathing_estimation':
                continue  # 呼吸估计tab单独处理
            
            plotter = plotter_info['plotter']
            data_type = plotter_info['data_type']
            
            # 准备该数据类型的所有通道数据
            channel_data = {}
            for ch in display_channels:
                indices = []
                values = []
                for i, frame in enumerate(window_frames):
                    channels = frame.get('channels', {})
                    ch_data = channels.get(ch) or channels.get(str(ch)) or channels.get(int(ch)) if ch else None
                    if ch_data:
                        indices.append(frame.get('index', self.current_window_start + i))
                        values.append(ch_data.get(data_type, 0.0))
                
                if len(indices) > 0 and len(values) > 0:
                    # 确保ch是整数类型
                    ch_int = int(ch) if isinstance(ch, (int, str)) and str(ch).isdigit() else ch
                    channel_data[ch_int] = (np.array(indices), np.array(values))
            
            # 更新绘图
            if channel_data:
                plotter.update_frame_data(channel_data, max_channels=len(display_channels))
                plotter.refresh()
    
    def _update_breathing_estimation_plot(self, window_frames: List[Dict]):
        """更新呼吸估计tab的绘图"""
        if 'breathing_estimation' not in self.plotters:
            return
        
        plot_info = self.plotters['breathing_estimation']
        axes = plot_info['axes']
        figure = plot_info['figure']
        
        # 获取选择的信道和数据类型
        try:
            channel = int(self.breathing_channel_var.get())
        except:
            channel = 0
        
        data_type = self.breathing_data_type_var.get()
        
        # 提取该信道的数据
        signal_data = []
        indices = []
        for i, frame in enumerate(window_frames):
            channels = frame.get('channels', {})
            # 尝试多种方式匹配信道
            ch_data = None
            if channel in channels:
                ch_data = channels[channel]
            elif str(channel) in channels:
                ch_data = channels[str(channel)]
            elif int(channel) in channels:
                ch_data = channels[int(channel)]
            
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
            # 分析时间窗
            analysis = self.breathing_estimator.analyze_window(processed['highpass_filtered'], apply_hanning=True)
            if 'fft_freq_before' in analysis and 'fft_power_before' in analysis:
                # 只显示0-1Hz范围
                freq_mask = analysis['fft_freq_before'] <= 1.0
                ax3.plot(analysis['fft_freq_before'][freq_mask], analysis['fft_power_before'][freq_mask], 
                        'b-', linewidth=1.5, alpha=0.7, label='Before Bandpass')
            if 'fft_freq_after' in analysis and 'fft_power_after' in analysis:
                freq_mask = analysis['fft_freq_after'] <= 1.0
                ax3.plot(analysis['fft_freq_after'][freq_mask], analysis['fft_power_after'][freq_mask], 
                        'r-', linewidth=1.5, alpha=0.7, label='After Bandpass')
            # 标记通带范围
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
                threshold = float(self.breathing_threshold_var.get())
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

