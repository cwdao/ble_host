#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取版本号的辅助脚本
"""
import sys
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent / 'src'))

try:
    from main_gui import __version__
    print(__version__)
except Exception as e:
    print("1.0.0", file=sys.stderr)  # 默认版本号
    sys.exit(1)
