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
from pathlib import Path

try:
    from .serial_reader import SerialReader
    from .data_parser import DataParser
    from .data_processor import DataProcessor
    from .plotter import Plotter
except ImportError:
    # 直接运行时使用绝对导入
    from serial_reader import SerialReader
    from data_parser import DataParser
    from data_processor import DataProcessor
    from plotter import Plotter


class BLEHostGUI:
    """主GUI应用程序"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("BLE Host 上位机")
        self.root.geometry("1200x800")
        
        # 设置日志
        self._setup_logging()
        
        # 初始化组件
        self.serial_reader = None
        self.data_parser = DataParser()
        self.data_processor = DataProcessor()
        self.plotter = Plotter(figure_size=(12, 8))
        
        # 控制变量
        self.is_running = False
        self.update_thread = None
        self.stop_event = threading.Event()
        
        # 帧数据处理
        self.last_frame_time = time.time()
        self.frame_timeout = 0.5  # 500ms超时，如果500ms没有新数据，认为帧完成
        self.frame_mode = False  # 是否启用帧模式
        
        # 创建界面
        self._create_widgets()
        
        # 定时刷新
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
        # 顶部控制面板
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X)
        
        # 串口选择
        ttk.Label(control_frame, text="串口:").grid(row=0, column=0, padx=5, pady=5)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(control_frame, textvariable=self.port_var, width=15)
        self.port_combo.grid(row=0, column=1, padx=5, pady=5)
        
        # 刷新串口按钮
        ttk.Button(control_frame, text="刷新串口", command=self._refresh_ports).grid(row=0, column=2, padx=5, pady=5)
        
        # 波特率
        ttk.Label(control_frame, text="波特率:").grid(row=0, column=3, padx=5, pady=5)
        self.baudrate_var = tk.StringVar(value="115200")
        baudrate_combo = ttk.Combobox(control_frame, textvariable=self.baudrate_var, 
                                      values=["9600", "19200", "38400", "57600", "115200", "230400"], width=10)
        baudrate_combo.grid(row=0, column=4, padx=5, pady=5)
        
        # 连接/断开按钮
        self.connect_btn = ttk.Button(control_frame, text="连接", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=5, padx=5, pady=5)
        
        # 状态显示
        self.status_var = tk.StringVar(value="未连接")
        status_label = ttk.Label(control_frame, textvariable=self.status_var, foreground="red")
        status_label.grid(row=0, column=6, padx=5, pady=5)
        
        # 清空数据按钮
        ttk.Button(control_frame, text="清空数据", command=self._clear_data).grid(row=0, column=7, padx=5, pady=5)
        
        # 帧模式开关
        self.frame_mode_var = tk.BooleanVar(value=False)
        frame_mode_check = ttk.Checkbutton(control_frame, text="帧模式", variable=self.frame_mode_var,
                                           command=self._toggle_frame_mode)
        frame_mode_check.grid(row=0, column=8, padx=5, pady=5)
        
        # 左右分栏
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧：绘图区域
        plot_frame = ttk.Frame(paned)
        paned.add(plot_frame, weight=2)
        
        # 绘图画布
        self.plot_widget = self.plotter.attach_to_tkinter(plot_frame)
        self.plot_widget.pack(fill=tk.BOTH, expand=True)
        
        # 右侧：控制面板
        right_frame = ttk.Frame(paned, width=300)
        paned.add(right_frame, weight=1)
        
        # 数据处理区域
        process_frame = ttk.LabelFrame(right_frame, text="数据处理", padding="10")
        process_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 频率计算
        freq_frame = ttk.Frame(process_frame)
        freq_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(freq_frame, text="变量:").pack(side=tk.LEFT, padx=5)
        self.freq_var_var = tk.StringVar()
        self.freq_var_combo = ttk.Combobox(freq_frame, textvariable=self.freq_var_var, width=15)
        self.freq_var_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(freq_frame, text="计算频率", command=self._calculate_frequency).pack(side=tk.LEFT, padx=5)
        
        self.freq_result_var = tk.StringVar(value="")
        ttk.Label(process_frame, textvariable=self.freq_result_var, foreground="blue").pack(pady=5)
        
        # 统计信息
        stats_frame = ttk.Frame(process_frame)
        stats_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(stats_frame, text="计算统计信息", command=self._calculate_statistics).pack(pady=5)
        
        self.stats_text = scrolledtext.ScrolledText(process_frame, height=8, width=30)
        self.stats_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 日志显示区域
        log_frame = ttk.LabelFrame(right_frame, text="日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=30)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 添加日志处理器
        text_handler = TextHandler(self.log_text)
        text_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        text_handler.setFormatter(formatter)
        logging.getLogger().addHandler(text_handler)
        
        # 初始化串口列表
        self._refresh_ports()
    
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
        """断开串口"""
        if self.serial_reader:
            self.serial_reader.disconnect()
            self.serial_reader = None
        
        self.is_running = False
        self.connect_btn.config(text="连接")
        self.status_var.set("未连接")
        self.logger.info("串口已断开")
    
    def _clear_data(self):
        """清空数据"""
        self.data_processor.clear_buffer(clear_frames=True)
        self.plotter.clear_plot()
        self.data_parser.clear_buffer()
        self.plotter.refresh()
        self.logger.info("数据已清空")
    
    def _toggle_frame_mode(self):
        """切换帧模式"""
        self.frame_mode = self.frame_mode_var.get()
        if self.frame_mode:
            self.logger.info("启用帧模式 - 清空之前的非帧数据")
            # 切换到帧模式时，清空之前的非帧数据（只保留帧数据）
            self.data_processor.clear_buffer(clear_frames=False)  # 不清空帧数据
            # 清空所有绘图，只显示帧数据
            self.plotter.clear_plot()
            # 清空解析器状态
            self.data_parser.clear_buffer()
        else:
            self.logger.info("禁用帧模式")
            # 切换到非帧模式时，清空帧数据
            self.data_processor.clear_buffer(clear_frames=True)
            self.plotter.clear_plot()
    
    def _calculate_frequency(self):
        """计算频率"""
        var_name = self.freq_var_var.get()
        if not var_name:
            messagebox.showerror("错误", "请选择变量")
            return
        
        freq = self.data_processor.calculate_frequency(var_name, duration=15.0)
        
        if freq is not None:
            self.freq_result_var.set(f"频率: {freq:.2f} Hz")
            self.logger.info(f"{var_name} 频率: {freq:.2f} Hz")
        else:
            self.freq_result_var.set("频率计算失败")
            messagebox.showwarning("警告", "频率计算失败，可能需要更多数据")
    
    def _calculate_statistics(self):
        """计算统计信息"""
        self.stats_text.delete(1.0, tk.END)
        
        vars_list = self.data_processor.get_all_variables()
        if not vars_list:
            self.stats_text.insert(tk.END, "暂无数据\n")
            return
        
        for var_name in vars_list:
            stats = self.data_processor.calculate_statistics(var_name)
            if stats:
                self.stats_text.insert(tk.END, f"\n{var_name}:\n")
                self.stats_text.insert(tk.END, f"  均值: {stats['mean']:.4f}\n")
                self.stats_text.insert(tk.END, f"  最大值: {stats['max']:.4f}\n")
                self.stats_text.insert(tk.END, f"  最小值: {stats['min']:.4f}\n")
                self.stats_text.insert(tk.END, f"  标准差: {stats['std']:.4f}\n")
                self.stats_text.insert(tk.END, f"  数据点数: {stats['count']}\n")
    
    def _start_update_loop(self):
        """启动数据更新循环"""
        def update_loop():
            while True:
                try:
                    if self.is_running and self.serial_reader:
                        # 获取串口数据
                        data = self.serial_reader.get_data(block=False)
                        
                        if data:
                            current_time = time.time()
                            
                            # 如果是帧模式，优先处理帧数据
                            if self.frame_mode:
                                # 解析数据（会更新内部状态）
                                parsed = self.data_parser.parse(data['text'])
                                
                                # 如果parse返回了完成的帧（检测到新帧头时自动完成旧帧）
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
                                    
                                    # 初始化时间戳（新帧开始）
                                    self.last_frame_time = current_time
                                # 如果正在累积帧数据，更新时间戳
                                elif self.data_parser.current_frame is not None:
                                    # 检查是否有IQ数据
                                    has_iq = bool(self.data_parser.parse_iq_data(data['text']))
                                    if has_iq:
                                        self.last_frame_time = current_time
                                        iq_data = self.data_parser.current_frame.get('iq_data', {})
                                        self.logger.debug(
                                            f"[帧累积] index={self.data_parser.current_frame['index']}, "
                                            f"当前通道数={len(iq_data)}"
                                        )
                                
                                # 检查是否应该完成当前帧（超时判断，作为备份）
                                if self.data_parser.current_frame is not None:
                                    if current_time - self.last_frame_time > self.frame_timeout:
                                        # 超时完成帧
                                        frame_data = self.data_parser.flush_frame()
                                        if frame_data and len(frame_data.get('channels', {})) > 0:
                                            channels = sorted(frame_data['channels'].keys())
                                            self.logger.info(
                                                f"[帧完成-超时] index={frame_data['index']}, "
                                                f"timestamp={frame_data['timestamp_ms']}ms, "
                                                f"通道数={len(channels)}"
                                            )
                                            self.data_processor.add_frame_data(frame_data)
                                            self._update_frame_plots()
                                
                                # 帧模式下不处理其他数据
                                continue
                            
                            # 非帧模式：解析简单数据
                            parsed = self.data_parser.parse(data['text'])
                            
                            # 处理简单数据（向后兼容）
                            if parsed and not parsed.get('frame'):
                                self.data_processor.add_data(data['timestamp'], parsed)
                                
                                # 更新绘图（最近15秒的数据）
                                for var_name, value in parsed.items():
                                    times, values = self.data_processor.get_data_range(var_name, duration=15.0)
                                    if len(times) > 0:
                                        self.plotter.update_plot(var_name, times, values)
                                
                                # 更新变量列表
                                vars_list = self.data_processor.get_all_variables()
                                self.freq_var_combo['values'] = vars_list
                                if vars_list and not self.freq_var_var.get():
                                    self.freq_var_combo.current(0)
                                    self.freq_var_var.set(vars_list[0])
                        
                        # 定期刷新绘图
                        self.plotter.refresh()
                    
                    time.sleep(0.05)  # 50ms更新间隔，更快响应
                    
                except Exception as e:
                    self.logger.error(f"更新循环错误: {e}")
        
        self.update_thread = threading.Thread(target=update_loop, daemon=True)
        self.update_thread.start()
    
    def _update_frame_plots(self):
        """更新帧数据绘图 - 在一个图中显示前10个通道的幅值"""
        channels = self.data_processor.get_all_frame_channels()
        
        if not channels:
            return
        
        # 只显示前10个通道
        max_channels = 10
        display_channels = sorted(channels)[:max_channels]
        
        # 准备所有通道的数据
        channel_data = {}
        for ch in display_channels:
            indices, amplitudes = self.data_processor.get_frame_data_range(ch, max_frames=100)
            if len(indices) > 0 and len(amplitudes) > 0:
                channel_data[ch] = (indices, amplitudes)
        
        # 一次更新所有通道（在一个图中显示多条线）
        if channel_data:
            self.plotter.update_frame_data(channel_data, max_channels=max_channels)
            self.logger.debug(f"更新帧数据绘图: {len(channel_data)} 个通道")
    
    def on_closing(self):
        """窗口关闭事件"""
        if self.is_running:
            self._disconnect()
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
    root = tk.Tk()
    app = BLEHostGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()

