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

try:
    from .config import user_settings, config
except ImportError:
    from config import user_settings, config


class DataSaver:
    """数据保存和加载类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def save_frames(self, frames: List[Dict], filepath: str, 
                   max_frames: Optional[int] = None,
                   frame_type: Optional[str] = None) -> bool:
        """
        保存帧数据到JSON文件
        
        Args:
            frames: 帧数据列表，每个元素是完整的帧数据字典
            filepath: 保存路径
            max_frames: 如果指定，只保存最近的max_frames帧；None表示保存全部
            frame_type: 帧类型，'direction_estimation' 或 'channel_sounding'，用于确定文件版本
        
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
            # 对于大文件，分批处理以减少内存峰值
            frames_copy = []
            batch_size = 1000  # 每批处理1000帧
            total_frames = len(frames_to_save)
            
            try:
                for i in range(0, total_frames, batch_size):
                    batch_end = min(i + batch_size, total_frames)
                    batch = frames_to_save[i:batch_end]
                    
                    # 处理当前批次
                    for frame in batch:
                        frames_copy.append(copy.deepcopy(frame))
                    
                    # 每批处理后记录进度
                    if i % (batch_size * 10) == 0 or batch_end == total_frames:
                        self.logger.debug(f"正在处理第 {batch_end}/{total_frames} 帧...")
            except MemoryError as e:
                self.logger.error(f"保存时内存不足: {e}")
                # 清理已处理的数据，释放内存
                frames_copy = None
                raise
            except Exception as e:
                self.logger.error(f"深拷贝数据时出错: {e}")
                # 清理已处理的数据，释放内存
                frames_copy = None
                raise
            
            # 确定帧类型和版本号
            # 优先使用传入的frame_type（根据当前模式），如果没有则从帧数据中判断
            frame_version = None
            file_version = None
            
            if frame_type is None and frames_to_save:
                # 如果没有传入frame_type，从帧数据中判断（向后兼容）
                first_frame = frames_to_save[0]
                if first_frame.get('frame_type') == 'direction_estimation':
                    frame_type = 'direction_estimation'
                else:
                    frame_type = 'channel_sounding'
            
            if frame_type == 'direction_estimation':
                # 方向估计帧
                if frames_to_save:
                    frame_version = frames_to_save[0].get('frame_version', 1)
                file_version = config.version  # 使用APP版本号 3.4.0
            elif frame_type == 'channel_sounding':
                # 信道探测帧
                file_version = '1.0.0'  # 信道探测帧保持1.0.0版本
            else:
                # 默认情况（向后兼容）
                file_version = '1.0.0'
            
            
            # 准备保存的数据结构
            save_data = {
                'version': file_version,
                'saved_at': datetime.now().isoformat(),
                'total_frames': len(frames),
                'saved_frames': len(frames_to_save),
                'max_frames_param': max_frames,
                'frame_type': frame_type,
                'frame_version': frame_version,
                'frames': frames_copy
            }
            
            # 确保目录存在
            os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
            
            # 保存为JSON（使用更紧凑的格式以减少文件大小和写入时间）
            # 对于大文件，可以考虑使用json.dump的separators参数
            self.logger.debug("开始写入JSON文件...")
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)
            except IOError as e:
                self.logger.error(f"写入文件失败: {e}")
                raise
            except MemoryError as e:
                self.logger.error(f"写入文件时内存不足: {e}")
                raise
            except Exception as e:
                self.logger.error(f"保存JSON文件时出错: {e}")
                raise
            
            # 检查文件是否成功创建
            if not os.path.exists(filepath):
                self.logger.error(f"文件保存后不存在: {filepath}")
                return False
            
            file_size_mb = os.path.getsize(filepath) / 1024 / 1024
            self.logger.info(f"成功保存 {len(frames_to_save)} 帧数据到: {filepath} (文件大小: {file_size_mb:.2f} MB)")
            return True
            
        except MemoryError as e:
            self.logger.error(f"保存帧数据时内存不足: {e}", exc_info=True)
            return False
        except IOError as e:
            self.logger.error(f"保存帧数据时IO错误: {e}", exc_info=True)
            return False
        except KeyboardInterrupt:
            # 用户中断，不应该发生在这里，但为了安全起见
            self.logger.warning("保存操作被用户中断")
            return False
        except SystemExit:
            # 不应该捕获SystemExit，让它正常退出
            raise
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
                'frame_type': str or None,
                'frame_version': int or None,
                'frames': [frame_data, ...]
            }
            如果加载失败返回None
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查版本兼容性
            file_version = data.get('version', '1.0')
            app_version = config.version
            
            # 如果文件版本高于APP版本，返回错误信息
            if self._compare_versions(file_version, app_version) > 0:
                self.logger.error(f"文件版本 {file_version} 高于APP版本 {app_version}，无法加载")
                return {
                    'error': 'version_incompatible',
                    'file_version': file_version,
                    'app_version': app_version,
                    'message': f'文件版本 {file_version} 高于APP版本 {app_version}，请升级APP'
                }
            
            self.logger.info(f"成功加载 {data.get('saved_frames', 0)} 帧数据从: {filepath}, 文件版本: {file_version}")
            return data
            
        except Exception as e:
            self.logger.error(f"加载帧数据失败: {e}")
            return None
    
    def _compare_versions(self, version1: str, version2: str) -> int:
        """
        比较两个版本号
        
        Args:
            version1: 版本号字符串，如 "3.4.0"
            version2: 版本号字符串，如 "3.4.0"
        
        Returns:
            -1 if version1 < version2
            0 if version1 == version2
            1 if version1 > version2
        """
        try:
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]
            
            # 补齐长度
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))
            
            for v1, v2 in zip(v1_parts, v2_parts):
                if v1 < v2:
                    return -1
                elif v1 > v2:
                    return 1
            return 0
        except Exception as e:
            self.logger.warning(f"版本号比较失败: {e}, version1={version1}, version2={version2}")
            return 0  # 如果比较失败，认为版本相同
    
    def get_default_filename(self, prefix: str = "frames", 
                            save_all: bool = True, 
                            max_frames: Optional[int] = None,
                            frame_type: Optional[str] = None) -> str:
        """
        生成默认文件名
        
        Args:
            prefix: 文件名前缀
            save_all: 是否保存全部帧
            max_frames: 如果保存最近N帧，指定N
            frame_type: 帧类型，'direction_estimation' 或 'channel_sounding'，用于添加DF/CS前缀
        
        Returns:
            默认文件名（不含路径）
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 根据帧类型添加前缀
        type_prefix = ""
        if frame_type == 'direction_estimation':
            type_prefix = "DF_"
        elif frame_type == 'channel_sounding':
            type_prefix = "CS_"
        
        if save_all:
            return f"{type_prefix}{prefix}_all_{timestamp}.json"
        else:
            return f"{type_prefix}{prefix}_recent{max_frames}_{timestamp}.json"
    
    def get_auto_save_path(self, prefix: str = "frames",
                           save_all: bool = True,
                           max_frames: Optional[int] = None,
                           frame_type: Optional[str] = None) -> str:
        """
        获取自动保存路径（基于用户设置的保存目录）
        
        Args:
            prefix: 文件名前缀
            save_all: 是否保存全部帧
            max_frames: 如果保存最近N帧，指定N
            frame_type: 帧类型，用于添加DF/CS前缀
        
        Returns:
            完整的保存路径
        """
        save_dir = user_settings.get_save_directory()
        # 确保目录存在
        os.makedirs(save_dir, exist_ok=True)
        
        filename = self.get_default_filename(prefix, save_all, max_frames, frame_type)
        return os.path.join(save_dir, filename)

