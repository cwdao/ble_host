#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令接口模块
负责UART命令的定义、生成、验证、解析等功能
提供统一的命令接口，支持GUI和命令行使用
"""
import re
from typing import Dict, Optional, List, Tuple


class CommandSender:
    """
    命令接口类，负责UART命令的完整生命周期管理
    
    功能包括：
    - 命令类型定义和参数规范
    - 命令字符串生成
    - 参数验证和格式转换
    - 响应解析
    - 默认参数管理
    """
    
    # 命令类型定义
    COMMAND_TYPES = {
        'PING': {
            'name': 'PING',
            'description': '连通性测试',
            'params': []
        },
        'BLE_SCAN': {
            'name': 'BLE_SCAN',
            'description': '控制扫描',
            'params': [
                {
                    'key': 'action',
                    'label': '操作',
                    'type': 'select',
                    'options': ['start', 'stop'],
                    'required': True,
                    'tooltip': 'start: 开始扫描\nstop: 停止扫描'
                }
            ]
        },
        'BLE_CONN': {
            'name': 'BLE_CONN',
            'description': '连接控制',
            'params': [
                {
                    'key': 'action',
                    'label': '操作',
                    'type': 'select',
                    'options': ['disconnect'],
                    'required': True,
                    'tooltip': 'disconnect: 断开连接'
                }
            ]
        },
        'DF_START': {
            'name': 'DF_START',
            'description': '配置DF参数并启动',
            'params': [
                {
                    'key': 'channels',
                    'label': '信道列表',
                    'type': 'text',
                    'required': False,
                    'tooltip': '自定义数据信道列表，用|分隔，每个信道0..36\n例如: 3|10|25'
                },
                {
                    'key': 'interval_ms',
                    'label': '连接间隔(ms)',
                    'type': 'number',
                    'required': False,
                    'tooltip': '连接间隔（毫秒），必须可换算成1.25ms units\n范围: 7.5ms..4s\n例如: 25'
                },
                {
                    'key': 'cte_len',
                    'label': 'CTE长度',
                    'type': 'number',
                    'required': False,
                    'tooltip': 'CTE长度（单位8us），范围0..255\n例如: 2'
                },
                {
                    'key': 'cte_type',
                    'label': 'CTE类型',
                    'type': 'select',
                    'options': ['aod1', 'aod2', 'aoa'],
                    'required': False,
                    'tooltip': 'CTE类型:\naod1: AOD类型1\naod2: AOD类型2\naoa: AOA类型（需编译启用）'
                }
            ]
        },
        'DF_CONFIG': {
            'name': 'DF_CONFIG',
            'description': '动态修改DF参数',
            'params': [
                {
                    'key': 'channels',
                    'label': '信道列表',
                    'type': 'text',
                    'required': False,
                    'tooltip': '自定义数据信道列表，用|分隔，每个信道0..36\n例如: 3|10|25'
                },
                {
                    'key': 'interval_ms',
                    'label': '连接间隔(ms)',
                    'type': 'number',
                    'required': False,
                    'tooltip': '连接间隔（毫秒），必须可换算成1.25ms units\n范围: 7.5ms..4s\n下次连接生效'
                },
                {
                    'key': 'cte_len',
                    'label': 'CTE长度',
                    'type': 'number',
                    'required': False,
                    'tooltip': 'CTE长度（单位8us），范围0..255\n需要DF_START生效'
                },
                {
                    'key': 'cte_type',
                    'label': 'CTE类型',
                    'type': 'select',
                    'options': ['aod1', 'aod2', 'aoa'],
                    'required': False,
                    'tooltip': 'CTE类型:\naod1: AOD类型1\naod2: AOD类型2\naoa: AOA类型\n需要DF_START生效'
                }
            ]
        },
        'DF_STOP': {
            'name': 'DF_STOP',
            'description': '停止/禁用CTE',
            'params': []
        }
    }
    
    # 转义字符映射
    ESCAPE_MAP = {
        '\\n': '\n',      # 换行符 (LF, 0x0A)
        '\\r': '\r',      # 回车符 (CR, 0x0D)
        '\\t': '\t',      # 制表符 (TAB, 0x09)
        '\\\\': '\\',     # 反斜杠
    }
    
    def __init__(self):
        """初始化命令发送器"""
        pass
    
    def generate_command(self, cmd_type: str, params: Dict[str, str] = None, 
                        enable_escape: bool = True, always_include_newline: bool = False) -> str:
        """
        生成命令字符串
        
        Args:
            cmd_type: 命令类型（如 'PING', 'DF_START' 等）
            params: 参数字典，键为参数名，值为参数值
            enable_escape: 是否启用转义字符处理（已废弃，保留兼容性）
            always_include_newline: 是否总是包含换行符（用于显示）
        
        Returns:
            生成的命令字符串（如果always_include_newline=True，总是包含\n）
        """
        if cmd_type not in self.COMMAND_TYPES:
            raise ValueError(f"未知的命令类型: {cmd_type}")
        
        cmd_def = self.COMMAND_TYPES[cmd_type]
        cmd_name = cmd_def['name']
        
        # 构建命令：$CMD,<cmd>[,<k>=<v>...]
        parts = ['$CMD', cmd_name]
        
        # 添加参数
        if params:
            for param_key, param_value in params.items():
                if param_value and param_value.strip():  # 只添加非空参数
                    parts.append(f"{param_key}={param_value}")
        
        command = ','.join(parts)
        
        # 如果always_include_newline为True，总是添加换行符（用于显示）
        if always_include_newline:
            command += '\n'
        
        return command
    
    def process_escape_chars(self, text: str) -> str:
        """
        处理转义字符
        
        Args:
            text: 输入文本
        
        Returns:
            处理后的文本
        """
        result = text
        # 按顺序处理转义字符（先处理\\，避免重复转义）
        for escape_seq, char in sorted(self.ESCAPE_MAP.items(), 
                                      key=lambda x: len(x[0]), reverse=True):
            result = result.replace(escape_seq, char)
        return result
    
    def validate_params(self, cmd_type: str, params: Dict[str, str]) -> Tuple[bool, Optional[str]]:
        """
        验证参数
        
        Args:
            cmd_type: 命令类型
            params: 参数字典
        
        Returns:
            (是否有效, 错误信息)
        """
        if cmd_type not in self.COMMAND_TYPES:
            return False, f"未知的命令类型: {cmd_type}"
        
        cmd_def = self.COMMAND_TYPES[cmd_type]
        
        # 检查必填参数
        for param_def in cmd_def['params']:
            if param_def.get('required', False):
                param_key = param_def['key']
                if param_key not in params or not params[param_key] or not params[param_key].strip():
                    return False, f"缺少必填参数: {param_def['label']}"
        
        # 验证interval_ms格式（如果提供）
        if 'interval_ms' in params and params['interval_ms']:
            try:
                interval_ms = float(params['interval_ms'])
                # 检查是否能换算成1.25ms units
                units = interval_ms * 100 / 125
                if units != int(units):
                    return False, f"interval_ms={interval_ms} 不能整除换算到1.25ms units"
                # 检查范围
                if interval_ms < 7.5 or interval_ms > 4000:
                    return False, f"interval_ms={interval_ms} 超出范围 (7.5ms..4s)"
            except ValueError:
                return False, f"interval_ms 格式无效: {params['interval_ms']}"
        
        # 验证cte_len范围（如果提供）
        if 'cte_len' in params and params['cte_len']:
            try:
                cte_len = int(params['cte_len'])
                if cte_len < 0 or cte_len > 255:
                    return False, f"cte_len={cte_len} 超出范围 (0..255)"
            except ValueError:
                return False, f"cte_len 格式无效: {params['cte_len']}"
        
        # 验证channels格式（如果提供）
        if 'channels' in params and params['channels']:
            channels_str = params['channels'].strip()
            if channels_str:
                # 先转换为标准格式（支持友好格式）
                normalized_channels = self.parse_channels_input(channels_str)
                if not normalized_channels:
                    return False, f"channels 格式无效: {channels_str}"
                try:
                    channels = normalized_channels.split('|')
                    for ch in channels:
                        ch_num = int(ch.strip())
                        if ch_num < 0 or ch_num > 36:
                            return False, f"信道号 {ch_num} 超出范围 (0..36)"
                except ValueError:
                    return False, f"channels 格式无效: {channels_str}"
        
        return True, None
    
    @staticmethod
    def parse_channels_input(channels_str: str) -> str:
        """
        解析信道输入字符串，支持友好格式，转换为命令需要的|分隔格式
        
        支持的输入格式：
        - "3,4,10" -> "3|4|10"
        - "5-7" -> "5|6|7"
        - "3,5-7,10" -> "3|5|6|7|10"
        - "3|10|25" -> "3|10|25" (旧格式，直接返回)
        
        Args:
            channels_str: 用户输入的信道字符串
            
        Returns:
            转换后的|分隔格式字符串，如果解析失败返回空字符串
        """
        if not channels_str or not channels_str.strip():
            return ""
        
        channels_str = channels_str.strip()
        
        # 如果已经是|分隔格式，直接返回（兼容旧格式）
        if '|' in channels_str and ',' not in channels_str and '-' not in channels_str:
            return channels_str
        
        # 解析友好格式
        channels = []
        try:
            # 先按逗号分割
            parts = [p.strip() for p in channels_str.split(',')]
            for part in parts:
                if '-' in part:
                    # 范围格式 "5-7"
                    start, end = part.split('-', 1)
                    start = int(start.strip())
                    end = int(end.strip())
                    # 限制范围在0-36之间（BLE信道范围）
                    start = max(0, min(start, 36))
                    end = max(0, min(end, 36))
                    if start <= end:
                        channels.extend(range(start, end + 1))
                else:
                    # 单个数字
                    ch = int(part.strip())
                    if 0 <= ch <= 36:
                        channels.append(ch)
            
            # 去重并排序
            channels = sorted(list(set(channels)))
            
            # 转换为|分隔格式
            return '|'.join(str(ch) for ch in channels)
        except (ValueError, AttributeError):
            # 如果解析失败，返回空字符串（让调用者知道格式无效）
            return ""
    
    @staticmethod
    def get_default_params() -> Dict[str, str]:
        """
        获取命令参数的默认值
        
        Returns:
            默认参数字典，键为参数名，值为默认值
        """
        # 延迟导入config实例，避免循环依赖
        try:
            from .config import config
        except ImportError:
            from config import config
        
        return {
            'cte_type': config.command_default_cte_type,
            'channels': config.command_default_channels,
            'cte_len': config.command_default_cte_len,
            'interval_ms': config.command_default_interval_ms,
        }
    
    @staticmethod
    def parse_response(text: str) -> Optional[Dict]:
        """
        解析下位机反馈
        
        Args:
            text: 接收到的文本
        
        Returns:
            解析结果字典，格式：
            {
                'type': 'OK'|'ERR'|'EVT',
                'cmd': str,  # 命令名（OK/ERR时）
                'topic': str,  # 事件主题（EVT时）
                'code': int,  # 错误码（ERR时）
                'msg': str,  # 消息内容
                'raw': str   # 原始文本
            }
            如果无法解析则返回None
        """
        if not text:
            return None
        
        text = text.strip()
        
        # 匹配成功应答：$OK,<cmd>[,<msg>]
        ok_match = re.match(r'\$OK,([^,]+)(?:,(.+))?', text)
        if ok_match:
            cmd = ok_match.group(1)
            msg = ok_match.group(2) if ok_match.group(2) else ''
            return {
                'type': 'OK',
                'cmd': cmd,
                'msg': msg,
                'raw': text
            }
        
        # 匹配错误应答：$ERR,<cmd>,<code>,<msg>
        err_match = re.match(r'\$ERR,([^,]+),(\d+)(?:,(.+))?', text)
        if err_match:
            cmd = err_match.group(1)
            code = int(err_match.group(2))
            msg = err_match.group(3) if err_match.group(3) else ''
            return {
                'type': 'ERR',
                'cmd': cmd,
                'code': code,
                'msg': msg,
                'raw': text
            }
        
        # 匹配事件上报：$EVT,<topic>[,<msg>]
        evt_match = re.match(r'\$EVT,([^,]+)(?:,(.+))?', text)
        if evt_match:
            topic = evt_match.group(1)
            msg = evt_match.group(2) if evt_match.group(2) else ''
            return {
                'type': 'EVT',
                'topic': topic,
                'msg': msg,
                'raw': text
            }
        
        return None

