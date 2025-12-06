#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新 build.spec 文件中的版本号
"""
import sys
import re
from pathlib import Path

def update_spec_version(version):
    """更新 build.spec 文件中的 name 字段"""
    spec_file = Path('build.spec')
    
    if not spec_file.exists():
        print(f"错误: {spec_file} 文件不存在", file=sys.stderr)
        sys.exit(1)
    
    # 读取文件内容
    content = spec_file.read_text(encoding='utf-8')
    
    # 替换 name='BLEHost' 为 name='BLEHost-v{version}'
    pattern = r"name\s*=\s*['\"]BLEHost[^'\"]*['\"]"
    replacement = f"name='BLEHost-v{version}'"
    
    new_content = re.sub(pattern, replacement, content)
    
    if new_content == content:
        print(f"警告: 未找到 name 字段，尝试添加", file=sys.stderr)
        # 如果没找到，尝试在 EXE 部分添加
        pattern2 = r"(exe\s*=\s*EXE\([^)]*name\s*=\s*)['\"][^'\"]*['\"]"
        replacement2 = f"\\1'BLEHost-v{version}'"
        new_content = re.sub(pattern2, replacement2, content)
    
    # 写回文件
    spec_file.write_text(new_content, encoding='utf-8')
    print(f"已更新 build.spec: name='BLEHost-v{version}'")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        # 如果没有提供版本号，尝试从 config.py 读取
        sys.path.insert(0, str(Path(__file__).parent / 'src'))
        try:
            from config import config
            version = config.version
        except Exception as e:
            print(f"错误: 无法读取版本号: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        version = sys.argv[1]
    
    update_spec_version(version)
