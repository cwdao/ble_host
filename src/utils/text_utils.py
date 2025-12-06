#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文本处理工具函数
"""
import re
from typing import Optional


# ANSI转义序列正则表达式（编译一次，多处使用）
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def remove_ansi_escape(text: str) -> str:
    """
    移除文本中的ANSI转义序列
    
    Args:
        text: 原始文本
        
    Returns:
        移除ANSI转义序列后的文本
    """
    if not text:
        return text
    return ANSI_ESCAPE_PATTERN.sub("", text).strip()


def safe_float(value: str, default: float = float('nan')) -> float:
    """
    安全地将字符串转换为浮点数
    
    Args:
        value: 要转换的字符串
        default: 转换失败时的默认值，默认为NaN
        
    Returns:
        转换后的浮点数，失败时返回default
    """
    try:
        return float(value)
    except (ValueError, TypeError, AttributeError):
        return default

