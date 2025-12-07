#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例脚本：加载保存的帧数据进行分析

使用方法:
    python examples/load_saved_frames.py <saved_file.json>

或者:
    import sys
    sys.path.insert(0, 'src')
    from data_saver import DataSaver
    
    saver = DataSaver()
    data = saver.load_frames('frames_all_20231206_120000.json')
    if data:
        frames = data['frames']
        # 进行分析...
"""
import sys
import os
import json

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from data_saver import DataSaver
except ImportError:
    print("错误: 无法导入data_saver模块")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)


def analyze_frames(frames):
    """
    分析帧数据的示例函数
    
    Args:
        frames: 帧数据列表
    """
    if not frames:
        print("没有帧数据可分析")
        return
    
    print(f"\n=== 帧数据分析 ===")
    print(f"总帧数: {len(frames)}")
    
    # 分析第一帧
    if frames:
        first_frame = frames[0]
        print(f"\n第一帧信息:")
        print(f"  索引: {first_frame.get('index')}")
        print(f"  时间戳: {first_frame.get('timestamp_ms')} ms")
        print(f"  通道数: {len(first_frame.get('channels', {}))}")
        
        # 显示前几个通道的数据
        channels = first_frame.get('channels', {})
        if channels:
            print(f"\n前5个通道的数据示例:")
            for i, (ch, ch_data) in enumerate(sorted(channels.items())[:5]):
                print(f"  通道{ch}:")
                print(f"    幅值: {ch_data.get('amplitude', 0):.2f}")
                print(f"    相位: {ch_data.get('phase', 0):.4f} rad")
                print(f"    Local幅值: {ch_data.get('local_amplitude', 0):.2f}")
                print(f"    Remote幅值: {ch_data.get('remote_amplitude', 0):.2f}")
    
    # 分析所有帧的统计信息
    if len(frames) > 1:
        print(f"\n帧索引范围: {frames[0]['index']} - {frames[-1]['index']}")
        print(f"时间戳范围: {frames[0]['timestamp_ms']} - {frames[-1]['timestamp_ms']} ms")
        time_span = (frames[-1]['timestamp_ms'] - frames[0]['timestamp_ms']) / 1000.0
        print(f"时间跨度: {time_span:.2f} 秒")
        
        # 计算平均帧间隔
        if len(frames) > 1:
            intervals = []
            for i in range(1, len(frames)):
                interval = (frames[i]['timestamp_ms'] - frames[i-1]['timestamp_ms']) / 1000.0
                intervals.append(interval)
            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                print(f"平均帧间隔: {avg_interval:.3f} 秒")
                print(f"平均帧率: {1.0/avg_interval:.2f} 帧/秒")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python load_saved_frames.py <saved_file.json>")
        print("\n示例:")
        print("  python load_saved_frames.py frames_all_20231206_120000.json")
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    if not os.path.exists(filepath):
        print(f"错误: 文件不存在: {filepath}")
        sys.exit(1)
    
    # 加载数据
    saver = DataSaver()
    print(f"正在加载: {filepath}")
    data = saver.load_frames(filepath)
    
    if data is None:
        print("加载失败")
        sys.exit(1)
    
    # 显示文件信息
    print(f"\n=== 文件信息 ===")
    print(f"版本: {data.get('version', 'N/A')}")
    print(f"保存时间: {data.get('saved_at', 'N/A')}")
    print(f"原始总帧数: {data.get('total_frames', 0)}")
    print(f"保存的帧数: {data.get('saved_frames', 0)}")
    print(f"保存模式: {'全部帧' if data.get('max_frames_param') is None else f'最近{data.get(\"max_frames_param\")}帧'}")
    
    # 分析帧数据
    frames = data.get('frames', [])
    analyze_frames(frames)
    
    # 提示如何进一步使用
    print(f"\n=== 使用提示 ===")
    print("您可以使用以下方式访问帧数据:")
    print("  frames = data['frames']")
    print("  for frame in frames:")
    print("      index = frame['index']")
    print("      timestamp = frame['timestamp_ms']")
    print("      channels = frame['channels']")
    print("      for ch, ch_data in channels.items():")
    print("          amplitude = ch_data['amplitude']")
    print("          phase = ch_data['phase']")
    print("          # ... 进行您的分析")


if __name__ == "__main__":
    main()

