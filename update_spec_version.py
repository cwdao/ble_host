#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新 build.spec 或 build_qt.spec 文件中的版本号
使用方法: python update_spec_version.py [version] [spec_file]
"""
import sys
import re
from pathlib import Path

def update_spec_version(version, spec_file_path='build.spec'):
    """更新 spec 文件中的 name 字段"""
    spec_file = Path(spec_file_path)
    
    if not spec_file.exists():
        print(f"错误: {spec_file} 文件不存在", file=sys.stderr)
        sys.exit(1)
    
    # 读取文件内容
    content = spec_file.read_text(encoding='utf-8')
    
    # 根据文件名确定前缀
    if 'qt' in spec_file_path.lower():
        name_prefix = 'BLEHost-Qt-v'
    else:
        name_prefix = 'BLEHost-v'
    
    # 替换 name='BLEHost' 或 name='BLEHost-Qt-v...' 为新的版本号
    pattern = r"name\s*=\s*['\"]BLEHost[^'\"]*['\"]"
    replacement = f"name='{name_prefix}{version}'"
    
    new_content = re.sub(pattern, replacement, content)
    
    if new_content == content:
        print(f"警告: 未找到 name 字段，尝试添加", file=sys.stderr)
        # 如果没找到，尝试在 EXE 部分添加
        pattern2 = r"(exe\s*=\s*EXE\([^)]*name\s*=\s*)['\"][^'\"]*['\"]"
        replacement2 = f"\\1'{name_prefix}{version}'"
        new_content = re.sub(pattern2, replacement2, content)
    
    # 写回文件
    spec_file.write_text(new_content, encoding='utf-8')
    print(f"已更新 {spec_file_path}: name='{name_prefix}{version}'")

if __name__ == '__main__':
    # 解析参数
    version = None
    spec_file = 'build.spec'
    
    for arg in sys.argv[1:]:
        if arg.endswith('.spec'):
            spec_file = arg
        else:
            version = arg
    
    # 如果没有提供版本号，尝试从 config.py 读取
    if not version:
        sys.path.insert(0, str(Path(__file__).parent / 'src'))
        try:
            from config import config
            version = config.version
        except Exception as e:
            print(f"错误: 无法读取版本号: {e}", file=sys.stderr)
            sys.exit(1)
    
    update_spec_version(version, spec_file)
