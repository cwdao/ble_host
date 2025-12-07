#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据保存和加载模块
支持将帧数据保存为JSON格式，便于后续分析和加载
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import logging


class DataSaver:
    """数据保存和加载类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def save_frames(self, frames: List[Dict], filepath: str, 
                   max_frames: Optional[int] = None) -> bool:
        """
        保存帧数据到JSON文件
        
        Args:
            frames: 帧数据列表，每个元素是完整的帧数据字典
            filepath: 保存路径
            max_frames: 如果指定，只保存最近的max_frames帧；None表示保存全部
        
        Returns:
            True if success, False otherwise
        """
        import copy
        try:
            # 如果指定了max_frames，只保存最近的帧
            if max_frames is not None and max_frames > 0:
                frames_to_save = frames[-max_frames:] if len(frames) > max_frames else frames
            else:
                frames_to_save = frames
            
            self.logger.info(f"开始保存 {len(frames_to_save)} 帧数据到: {filepath}")
            
            # 在保存时进行深拷贝，确保数据完整性（避免在保存过程中数据被修改）
            # 使用生成器表达式逐帧处理，减少内存占用
            frames_copy = []
            for i, frame in enumerate(frames_to_save):
                if i % 100 == 0 and i > 0:
                    self.logger.debug(f"正在处理第 {i}/{len(frames_to_save)} 帧...")
                frames_copy.append(copy.deepcopy(frame))
            
            # 准备保存的数据结构
            save_data = {
                'version': '1.0',
                'saved_at': datetime.now().isoformat(),
                'total_frames': len(frames),
                'saved_frames': len(frames_to_save),
                'max_frames_param': max_frames,
                'frames': frames_copy
            }
            
            # 确保目录存在
            os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
            
            # 保存为JSON（使用更紧凑的格式以减少文件大小和写入时间）
            # 对于大文件，可以考虑使用json.dump的separators参数
            self.logger.debug("开始写入JSON文件...")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            
            file_size_mb = os.path.getsize(filepath) / 1024 / 1024
            self.logger.info(f"成功保存 {len(frames_to_save)} 帧数据到: {filepath} (文件大小: {file_size_mb:.2f} MB)")
            return True
            
        except Exception as e:
            self.logger.error(f"保存帧数据失败: {e}", exc_info=True)
            return False
    
    def load_frames(self, filepath: str) -> Optional[Dict]:
        """
        从JSON文件加载帧数据
        
        Args:
            filepath: 文件路径
        
        Returns:
            包含帧数据的字典，格式：
            {
                'version': str,
                'saved_at': str,
                'total_frames': int,
                'saved_frames': int,
                'max_frames_param': int or None,
                'frames': [frame_data, ...]
            }
            如果加载失败返回None
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.logger.info(f"成功加载 {data.get('saved_frames', 0)} 帧数据从: {filepath}")
            return data
            
        except Exception as e:
            self.logger.error(f"加载帧数据失败: {e}")
            return None
    
    def get_default_filename(self, prefix: str = "frames", 
                            save_all: bool = True, 
                            max_frames: Optional[int] = None) -> str:
        """
        生成默认文件名
        
        Args:
            prefix: 文件名前缀
            save_all: 是否保存全部帧
            max_frames: 如果保存最近N帧，指定N
        
        Returns:
            默认文件名（不含路径）
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if save_all:
            return f"{prefix}_all_{timestamp}.json"
        else:
            return f"{prefix}_recent{max_frames}_{timestamp}.json"

