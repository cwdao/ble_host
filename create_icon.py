#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 PNG 图标转换为包含多个尺寸的 ICO 文件
Windows 缩略图需要包含多个尺寸的图标才能正确显示
"""
import os
import sys
from PIL import Image

def create_ico_from_png(png_path, ico_path):
    """
    从 PNG 文件创建包含多个尺寸的 ICO 文件
    
    Args:
        png_path: PNG 文件路径
        ico_path: 输出的 ICO 文件路径
    """
    if not os.path.exists(png_path):
        print(f"错误: PNG 文件不存在: {png_path}", file=sys.stderr)
        sys.exit(1)
    
    # 打开原始 PNG 图片
    img = Image.open(png_path)
    original_size = img.size
    print(f"原始 PNG 尺寸: {original_size[0]}x{original_size[1]} 像素")
    
    # Windows 图标需要的标准尺寸列表
    # 包含多个尺寸可以确保在不同场景下都能正确显示
    # 添加更多尺寸以支持高 DPI 显示器
    sizes = [
        (16, 16),     # 小图标
        (24, 24),     # 小图标（高 DPI）
        (32, 32),     # 标准图标
        (48, 48),     # 中等图标
        (64, 64),     # 大图标
        (96, 96),     # 大图标（高 DPI）
        (128, 128),   # 超大图标
        (256, 256),   # 缩略图（Windows 10+）
        (512, 512),   # 高分辨率缩略图（高 DPI 显示器）
    ]
    
    # 如果原始图片更大，添加原始尺寸或接近原始尺寸的版本
    # 这样可以确保在高 DPI 显示器上获得最佳质量
    max_size = max(original_size)
    if max_size > 512:
        # 添加一个接近原始尺寸但不超过 1024 的版本
        # ICO 格式理论上支持更大尺寸，但实际使用中 1024 已经足够
        target_size = min(1024, max_size)
        # 保持宽高比
        if original_size[0] > original_size[1]:
            sizes.append((target_size, int(target_size * original_size[1] / original_size[0])))
        else:
            sizes.append((int(target_size * original_size[0] / original_size[1]), target_size))
    
    # 去重并排序
    sizes = sorted(set(sizes))
    
    # 创建不同尺寸的图标列表
    icons = []
    for size in sizes:
        # 使用最高质量的重采样算法（LANCZOS）
        # 如果目标尺寸大于原始尺寸，使用 LANCZOS 进行高质量放大
        # 如果目标尺寸小于原始尺寸，使用 LANCZOS 进行高质量缩小
        resized = img.resize(size, Image.Resampling.LANCZOS)
        icons.append(resized)
    
    # 保存为 ICO 文件
    # 注意：ICO 格式可能不支持超过 256x256 的尺寸
    # 对于更大的尺寸，我们需要分别处理
    try:
        # 尝试保存包含所有尺寸的 ICO
        icons[0].save(
            ico_path,
            format='ICO',
            sizes=[(img.width, img.height) for img in icons],
            append_images=icons[1:] if len(icons) > 1 else []
        )
        print(f"成功创建 ICO 文件: {ico_path}")
        print(f"包含尺寸: {', '.join([f'{w}x{h}' for w, h in sizes])}")
    except Exception as e:
        # 如果失败，可能是某些尺寸太大，尝试只保存标准尺寸
        print(f"警告: 保存完整尺寸失败 ({e})，尝试只保存标准尺寸...")
        standard_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        standard_icons = []
        for size in standard_sizes:
            resized = img.resize(size, Image.Resampling.LANCZOS)
            standard_icons.append(resized)
        
        standard_icons[0].save(
            ico_path,
            format='ICO',
            sizes=[(img.width, img.height) for img in standard_icons],
            append_images=standard_icons[1:] if len(standard_icons) > 1 else []
        )
        print(f"成功创建 ICO 文件（标准尺寸）: {ico_path}")
        print(f"包含尺寸: {', '.join([f'{w}x{h}' for w, h in standard_sizes])}")

if __name__ == '__main__':
    # 获取项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(script_dir, 'assets', 'ico.png')
    ico_path = os.path.join(script_dir, 'assets', 'ico.ico')
    
    create_ico_from_png(png_path, ico_path)
    print("\n提示: 如果 Windows 缩略图仍未更新，请尝试以下方法:")
    print("1. 删除 dist 目录并重新打包")
    print("2. 清除 Windows 缩略图缓存:")
    print("   - 打开文件资源管理器")
    print("   - 查看 -> 选项 -> 查看 -> 取消勾选 '始终显示图标，从不显示缩略图'")
    print("   - 或者运行: del /a /q /s %LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\thumbcache_*.db")
    print("   - 然后重启文件资源管理器或重启电脑")

