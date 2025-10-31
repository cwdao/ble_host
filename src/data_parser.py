#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据解析模块
根据实际协议格式修改解析逻辑
"""
import re
import json
import logging
from typing import Dict, List, Optional, Tuple


class DataParser:
    """数据解析类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # 可以根据实际协议格式配置解析规则
        # 示例：假设数据格式为 "VAR1:value1,VAR2:value2,..."
        # 或者JSON格式: {"var1": value1, "var2": value2}
    
    def parse(self, text: str) -> Optional[Dict[str, float]]:
        """
        解析接收到的文本数据
        
        Args:
            text: 从串口接收的文本字符串
        
        Returns:
            解析后的数据字典，key为变量名，value为数值
            如果解析失败返回None
        """
        if not text:
            return None
        
        try:
            # 方法1: 尝试解析JSON格式
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    # 将值转换为浮点数
                    result = {}
                    for k, v in data.items():
                        try:
                            result[k] = float(v)
                        except (ValueError, TypeError):
                            pass
                    return result if result else None
            except json.JSONDecodeError:
                pass
            
            # 方法2: 解析键值对格式 "VAR1:value1,VAR2:value2"
            pattern = r'(\w+):([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)'
            matches = re.findall(pattern, text)
            if matches:
                result = {}
                for key, value in matches:
                    try:
                        result[key] = float(value)
                    except ValueError:
                        pass
                return result if result else None
            
            # 方法3: 简单的空格或逗号分隔数值
            # 可以根据实际协议格式调整
            
        except Exception as e:
            self.logger.debug(f"数据解析失败: {e}, 原始数据: {text}")
        
        return None
    
    def parse_csv_line(self, text: str) -> Optional[Dict[str, float]]:
        """
        解析CSV格式的数据
        
        Args:
            text: CSV格式的文本行
        
        Returns:
            解析后的数据字典
        """
        if not text:
            return None
        
        try:
            parts = text.split(',')
            result = {}
            for i, part in enumerate(parts):
                key = f"var{i+1}"  # 默认变量名
                try:
                    value = float(part.strip())
                    result[key] = value
                except ValueError:
                    pass
            return result if result else None
        except Exception as e:
            self.logger.debug(f"CSV解析失败: {e}")
            return None

