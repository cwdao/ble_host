#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口数据读取模块

支持两种入队格式：
- **文本模式**（默认）：按 ``\\n`` 分行，队列项含 ``text`` 字段，供 ASCII CS/DF 解析。
- **UART 二进制模式**（``binary_frame_mode=True``）：由 ``UartBinaryFrameReader`` 搜
  ``0x55 0xAA`` 组帧，队列项含 ``binary=True`` 与完整 ``raw`` 帧字节。
  支持 type ``0x01``（DIP）与 ``0x02``（CS 双端）；详见 ``dip_binary_parser``。
"""
import serial
import serial.tools.list_ports
from threading import Thread, Event
from queue import Queue
import time
import logging

try:
    from .dip_binary_parser import UartBinaryFrameReader
except ImportError:
    from dip_binary_parser import UartBinaryFrameReader


class SerialReader:
    """串口数据读取类"""
    
    def __init__(self, port=None, baudrate=115200, timeout=1.0, binary_frame_mode=False):
        """
        初始化串口读取器
        
        Args:
            port: 串口名称，如 'COM3'，None则自动检测
            baudrate: 波特率，默认115200
            timeout: 超时时间，默认1.0秒
            binary_frame_mode: True 时走 UART 二进制组帧（见 UartBinaryFrameReader），
                False 时按行切分 UTF-8 文本（ASCII 信道探测/方向估计帧）
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        # 与 GUI 二进制帧类型联动；连接/切换类型时由 main_gui 设置
        self.binary_frame_mode = binary_frame_mode
        self.serial = None
        self.is_running = False
        self.read_thread = None
        self.data_queue = Queue()
        self.stop_event = Event()
        self.logger = logging.getLogger(__name__)
        # 二进制模式下复用同一 reader，避免切换类型时丢失半帧
        self._binary_frame_reader = UartBinaryFrameReader()
        
    @staticmethod
    def list_ports():
        """列出所有可用串口"""
        ports = serial.tools.list_ports.comports()
        return [{'port': p.device, 'description': p.description} for p in ports]
    
    def connect(self):
        """连接串口"""
        try:
            if self.port is None:
                # 自动选择第一个可用串口
                ports = self.list_ports()
                if not ports:
                    raise Exception("未找到可用串口")
                self.port = ports[0]['port']
                self.logger.info(f"自动选择串口: {self.port}")
            
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            
            # 清空缓冲区
            self.serial.reset_input_buffer()
            
            self.is_running = True
            self.stop_event.clear()
            self.read_thread = Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            
            self.logger.info(f"串口连接成功: {self.port} @ {self.baudrate}")
            return True
            
        except Exception as e:
            self.logger.error(f"串口连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开串口连接（改进版本，避免阻塞）"""
        self.is_running = False
        self.stop_event.set()
        
        # 先尝试关闭串口（可能会中断阻塞的read操作）
        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except Exception as e:
                self.logger.warning(f"关闭串口时出错: {e}")
        
        # 等待读取线程结束（设置较短的超时，避免长时间阻塞）
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=0.5)  # 减少超时时间到0.5秒
        
        # 清空队列
        self.clear_queue()
        
        self.logger.info("串口已断开")
    
    def set_binary_frame_mode(self, enabled: bool):
        """
        切换 UART 二进制帧模式（会清空 UartBinaryFrameReader 内部缓冲）。

        在已连接状态下切换二进制帧类型 ↔ 文本帧类型时由 GUI 调用，
        防止上一模式的残留字节造成错帧。
        """
        self.binary_frame_mode = enabled
        self._binary_frame_reader.clear()

    def _read_loop(self):
        """串口读取循环（在单独线程中运行）"""
        buffer = b''
        
        while self.is_running and not self.stop_event.is_set():
            try:
                # 检查串口是否打开
                if not self.serial or not self.serial.is_open:
                    break
                
                # 使用try-except包装，避免in_waiting或read()阻塞
                try:
                    if self.serial.in_waiting > 0:
                        data = self.serial.read(self.serial.in_waiting)
                        if self.binary_frame_mode:
                            # chunk 可能含半帧或日志噪声，由 feed 返回 0..n 个完整帧
                            for frame in self._binary_frame_reader.feed(data):
                                self.data_queue.put({
                                    'timestamp': time.time(),
                                    'raw': frame,       # 完整二进制帧 bytes
                                    'binary': True,     # 供 main_gui 走 parse_raw_frame
                                    'text': None,
                                })
                        else:
                            # ASCII：按行入队，DataParser.parse(text) 处理 CS/DF
                            buffer += data
                            while b'\n' in buffer:
                                line, buffer = buffer.split(b'\n', 1)
                                try:
                                    text = line.decode('utf-8').strip()
                                    if text:
                                        self.data_queue.put({
                                            'timestamp': time.time(),
                                            'raw': line,
                                            'text': text
                                        })
                                except UnicodeDecodeError:
                                    self.data_queue.put({
                                        'timestamp': time.time(),
                                        'raw': line,
                                        'text': None
                                    })
                except (serial.SerialException, OSError, ValueError) as e:
                    # 串口操作异常（可能是设备断开）
                    if self.is_running:
                        self.logger.error(f"串口读取错误: {e}")
                    break
                
                time.sleep(0.01)  # 避免CPU占用过高
                
            except Exception as e:
                if self.is_running:
                    self.logger.error(f"串口读取循环错误: {e}")
                break
    
    def get_data(self, block=False, timeout=None):
        """
        获取接收到的数据
        
        Args:
            block: 是否阻塞等待
            timeout: 超时时间（秒）
        
        Returns:
            数据字典，如果没有数据则返回None
        """
        try:
            if block:
                return self.data_queue.get(timeout=timeout)
            else:
                return self.data_queue.get_nowait()
        except:
            return None
    
    def get_data_batch(self, max_count=20):
        """
        批量获取接收到的数据
        
        Args:
            max_count: 最多获取的数据条数
        
        Returns:
            数据列表，如果没有数据则返回空列表
        """
        batch = []
        for _ in range(max_count):
            try:
                data = self.data_queue.get_nowait()
                batch.append(data)
            except:
                break
        return batch
    
    def get_queue_size(self):
        """获取队列当前大小"""
        return self.data_queue.qsize()
    
    def clear_queue(self):
        """清空数据队列"""
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except:
                break
    
    def write(self, data):
        """
        向串口发送数据
        
        Args:
            data: 要发送的数据，可以是字符串或字节
        
        Returns:
            bool: 发送是否成功
        """
        if not self.serial or not self.serial.is_open:
            self.logger.warning("串口未连接，无法发送数据")
            return False
        
        try:
            if isinstance(data, str):
                # 如果是字符串，编码为字节
                data = data.encode('utf-8')
            
            # 发送数据
            bytes_written = self.serial.write(data)
            self.serial.flush()  # 确保数据立即发送
            
            self.logger.info(f"已发送 {bytes_written} 字节数据: {data}")
            return True
            
        except Exception as e:
            self.logger.error(f"发送数据失败: {e}")
            return False

