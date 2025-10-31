#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口数据读取模块
"""
import serial
import serial.tools.list_ports
from threading import Thread, Event
from queue import Queue
import time
import logging


class SerialReader:
    """串口数据读取类"""
    
    def __init__(self, port=None, baudrate=115200, timeout=1.0):
        """
        初始化串口读取器
        
        Args:
            port: 串口名称，如 'COM3'，None则自动检测
            baudrate: 波特率，默认115200
            timeout: 超时时间，默认1.0秒
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self.is_running = False
        self.read_thread = None
        self.data_queue = Queue()
        self.stop_event = Event()
        self.logger = logging.getLogger(__name__)
        
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
        """断开串口连接"""
        self.is_running = False
        self.stop_event.set()
        
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=2.0)
        
        if self.serial and self.serial.is_open:
            self.serial.close()
        
        self.logger.info("串口已断开")
    
    def _read_loop(self):
        """串口读取循环（在单独线程中运行）"""
        buffer = b''
        
        while self.is_running and not self.stop_event.is_set():
            try:
                if self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting)
                    buffer += data
                    
                    # 假设数据以换行符结尾，可以自定义协议
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        try:
                            # 尝试解码为字符串
                            text = line.decode('utf-8').strip()
                            if text:
                                self.data_queue.put({
                                    'timestamp': time.time(),
                                    'raw': line,
                                    'text': text
                                })
                        except UnicodeDecodeError:
                            # 如果不是文本数据，可以按字节处理
                            self.data_queue.put({
                                'timestamp': time.time(),
                                'raw': line,
                                'text': None
                            })
                
                time.sleep(0.01)  # 避免CPU占用过高
                
            except Exception as e:
                if self.is_running:
                    self.logger.error(f"串口读取错误: {e}")
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
    
    def clear_queue(self):
        """清空数据队列"""
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except:
                break

