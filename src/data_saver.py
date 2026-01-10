#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据保存和加载模块
支持将帧数据保存为JSON格式，便于后续分析和加载
支持增量JSONL格式保存，解决大量数据保存时的内存问题
"""
import json
import os
import time
import threading
import queue
from datetime import datetime
from typing import List, Dict, Optional, Iterator, Generator
import logging

try:
    from .config import user_settings, config
except ImportError:
    from config import user_settings, config


class LogWriter:
    """
    日志写入器：支持后台线程+队列的增量JSONL写入
    解决大量数据保存时的内存和UI卡顿问题
    """
    
    def __init__(self, flush_interval: int = 100, queue_maxsize: int = 10000):
        """
        初始化日志写入器
        
        Args:
            flush_interval: 每写入N条记录后flush一次（默认100）
            queue_maxsize: 队列最大大小，超过后丢弃并计数（默认10000）
        """
        self.logger = logging.getLogger(__name__)
        self.flush_interval = flush_interval
        self.queue_maxsize = queue_maxsize
        
        # 写入状态
        self.file_handle = None
        self.file_path = None
        self.write_thread = None
        self.stop_event = threading.Event()
        self.record_queue = queue.Queue(maxsize=queue_maxsize)
        self.write_count = 0
        self.dropped_count = 0
        self.is_running = False
        
    def start_session(self, log_path: str, meta: Dict) -> bool:
        """
        开始新的会话，写入meta记录
        
        Args:
            log_path: 日志文件路径（.jsonl）
            meta: 元数据字典，必须包含record_type="meta"
        
        Returns:
            True if success, False otherwise
        """
        if self.is_running:
            self.logger.warning("日志写入器已在运行，先停止当前会话")
            self.stop_session()
        
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(log_path) if os.path.dirname(log_path) else '.', exist_ok=True)
            
            # 打开文件（追加模式，如果文件不存在则创建）
            self.file_handle = open(log_path, 'a', encoding='utf-8')
            self.file_path = log_path
            
            # 写入meta记录（第一行）
            meta['record_type'] = 'meta'
            json_line = json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
            self.file_handle.write(json_line + '\n')
            self.file_handle.flush()
            self.write_count = 1
            
            # 启动后台写入线程
            self.stop_event.clear()
            self.is_running = True
            self.write_thread = threading.Thread(target=self._write_worker, daemon=True, name="LogWriterThread")
            self.write_thread.start()
            
            self.logger.info(f"日志写入器已启动: {log_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"启动日志会话失败: {e}", exc_info=True)
            if self.file_handle:
                try:
                    self.file_handle.close()
                except:
                    pass
                self.file_handle = None
            return False
    
    def append_record(self, record: Dict) -> bool:
        """
        追加记录到队列（非阻塞）
        
        Args:
            record: 记录字典，必须包含record_type字段
        
        Returns:
            True if queued, False if queue full (dropped)
        """
        if not self.is_running:
            self.logger.warning("日志写入器未运行，无法追加记录")
            return False
        
        try:
            # 确保record_type存在
            if 'record_type' not in record:
                self.logger.warning("记录缺少record_type字段，已添加默认值'frame'")
                record['record_type'] = 'frame'
            
            # 尝试添加到队列（非阻塞）
            try:
                self.record_queue.put_nowait(record)
                return True
            except queue.Full:
                # 队列满，丢弃并计数
                self.dropped_count += 1
                if self.dropped_count % 1000 == 0:
                    self.logger.warning(f"队列已满，已丢弃 {self.dropped_count} 条记录")
                return False
                
        except Exception as e:
            self.logger.error(f"追加记录失败: {e}", exc_info=True)
            return False
    
    def _write_worker(self):
        """后台写入工作线程"""
        try:
            while not self.stop_event.is_set() or not self.record_queue.empty():
                try:
                    # 从队列获取记录（带超时，避免无限阻塞）
                    try:
                        record = self.record_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    
                    # 写入文件
                    if self.file_handle:
                        json_line = json.dumps(record, ensure_ascii=False, separators=(',', ':'))
                        self.file_handle.write(json_line + '\n')
                        self.write_count += 1
                        
                        # 定期flush
                        if self.write_count % self.flush_interval == 0:
                            self.file_handle.flush()
                    
                    self.record_queue.task_done()
                    
                except Exception as e:
                    self.logger.error(f"写入记录时出错: {e}", exc_info=True)
                    continue
                    
        except Exception as e:
            self.logger.error(f"写入工作线程异常: {e}", exc_info=True)
        finally:
            # 最后flush一次
            if self.file_handle:
                try:
                    self.file_handle.flush()
                except:
                    pass
    
    def stop_session(self) -> Dict:
        """
        停止会话，写入end记录（可选），关闭文件
        
        Returns:
            统计信息字典：{written_records, dropped_records}
        """
        if not self.is_running:
            return {'written_records': 0, 'dropped_records': 0}
        
        # 等待队列处理完成
        self.stop_event.set()
        if self.write_thread and self.write_thread.is_alive():
            # 等待最多5秒
            self.write_thread.join(timeout=5.0)
            if self.write_thread.is_alive():
                self.logger.warning("写入工作线程未在超时时间内完成")
        
        # 写入end记录（可选）
        if self.file_handle:
            try:
                end_record = {
                    'record_type': 'end',
                    'ended_at_utc_ns': int(time.time_ns()),
                    'written_records': self.write_count,
                    'dropped_records': self.dropped_count
                }
                json_line = json.dumps(end_record, ensure_ascii=False, separators=(',', ':'))
                self.file_handle.write(json_line + '\n')
                self.file_handle.flush()
            except Exception as e:
                self.logger.error(f"写入end记录失败: {e}", exc_info=True)
            
            # 关闭文件
            try:
                self.file_handle.close()
            except Exception as e:
                self.logger.error(f"关闭文件失败: {e}", exc_info=True)
            finally:
                self.file_handle = None
        
        stats = {
            'written_records': self.write_count,
            'dropped_records': self.dropped_count
        }
        
        self.logger.info(f"日志会话已停止: 写入 {self.write_count} 条记录，丢弃 {self.dropped_count} 条")
        
        # 重置状态
        self.is_running = False
        self.write_count = 0
        self.dropped_count = 0
        self.file_path = None
        
        return stats


class DataSaver:
    """数据保存和加载类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # 日志写入器实例（用于增量保存）
        self.log_writer = None
    
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
            
            # 对于大量数据，使用更小的批次大小以减少内存峰值
            # 根据数据量动态调整批次大小
            total_frames = len(frames_to_save)
            if total_frames > 5000:
                batch_size = 200  # 大量数据时使用更小的批次
            elif total_frames > 2000:
                batch_size = 500
            else:
                batch_size = 1000  # 少量数据时可以使用较大的批次
            
            self.logger.debug(f"使用批次大小: {batch_size}, 总帧数: {total_frames}")
            
            # 在保存时进行深拷贝，确保数据完整性（避免在保存过程中数据被修改）
            # 对于大文件，分批处理以减少内存峰值
            frames_copy = []
            
            try:
                for i in range(0, total_frames, batch_size):
                    batch_end = min(i + batch_size, total_frames)
                    batch = frames_to_save[i:batch_end]
                    
                    # 处理当前批次
                    batch_copy = []
                    for frame in batch:
                        try:
                            batch_copy.append(copy.deepcopy(frame))
                        except MemoryError as e:
                            self.logger.error(f"深拷贝第 {i + len(batch_copy)} 帧时内存不足: {e}")
                            # 清理已处理的数据，释放内存
                            frames_copy = None
                            batch_copy = None
                            raise
                        except Exception as e:
                            self.logger.error(f"深拷贝第 {i + len(batch_copy)} 帧时出错: {e}")
                            frames_copy = None
                            batch_copy = None
                            raise
                    
                    # 将批次添加到总列表
                    frames_copy.extend(batch_copy)
                    batch_copy = None  # 释放批次引用
                    
                    # 每批处理后记录进度（更频繁的进度更新）
                    progress_interval = max(batch_size * 5, 1000)  # 至少每1000帧更新一次
                    if i % progress_interval == 0 or batch_end == total_frames:
                        progress_pct = (batch_end / total_frames * 100) if total_frames > 0 else 0
                        self.logger.info(f"正在处理第 {batch_end}/{total_frames} 帧 ({progress_pct:.1f}%)...")
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
                file_version = config.version_data_save  # 最低兼容的APP版本
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
            
            # 保存为JSON
            # 对于大文件，使用更紧凑的格式以减少文件大小和写入时间
            self.logger.debug("开始写入JSON文件...")
            try:
                # 对于大文件（>5000帧），使用更紧凑的格式（无缩进）以减少内存和写入时间
                use_compact = len(frames_to_save) > 5000
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    if use_compact:
                        # 紧凑格式：无缩进，减少文件大小和写入时间
                        json.dump(save_data, f, separators=(',', ':'), ensure_ascii=False)
                    else:
                        # 可读格式：有缩进，便于查看
                        json.dump(save_data, f, indent=2, ensure_ascii=False)
                
                # 写入完成后立即释放save_data引用，帮助GC回收内存
                save_data = None
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
        从JSON或JSONL文件加载帧数据（自动检测格式）
        
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
            # 根据文件扩展名判断格式
            is_jsonl_by_ext = filepath.lower().endswith('.jsonl') or filepath.lower().endswith('.ndjson')
            
            if is_jsonl_by_ext:
                # JSONL格式加载
                return self._load_frames_from_jsonl(filepath)
            else:
                # 尝试检测文件格式：先尝试读取第一行判断是否为JSONL
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                        if first_line:
                            try:
                                first_record = json.loads(first_line)
                                # 如果第一行是有效的JSON且包含record_type字段，认为是JSONL格式
                                if isinstance(first_record, dict) and 'record_type' in first_record:
                                    self.logger.info(f"检测到JSONL格式（通过内容判断）: {filepath}")
                                    return self._load_frames_from_jsonl(filepath)
                            except json.JSONDecodeError:
                                pass  # 不是JSONL，继续尝试JSON格式
                except Exception as e:
                    self.logger.debug(f"检测文件格式时出错: {e}，继续尝试JSON格式")
                
                # JSON格式加载（向后兼容）
                return self._load_frames_from_json(filepath)
            
        except Exception as e:
            self.logger.error(f"加载帧数据失败: {e}", exc_info=True)
            return None
    
    def _load_frames_from_json(self, filepath: str) -> Optional[Dict]:
        """
        从JSON文件加载帧数据（旧格式，向后兼容）
        
        Args:
            filepath: 文件路径
        
        Returns:
            包含帧数据的字典
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
            
            self.logger.info(f"成功加载 {data.get('saved_frames', 0)} 帧数据从JSON: {filepath}, 文件版本: {file_version}")
            return data
            
        except Exception as e:
            self.logger.error(f"加载JSON文件失败: {e}", exc_info=True)
            return None
    
    def _load_frames_from_jsonl(self, filepath: str) -> Optional[Dict]:
        """
        从JSONL文件加载帧数据（新格式）
        
        Args:
            filepath: 文件路径
        
        Returns:
            包含帧数据的字典，格式与JSON格式兼容
        """
        try:
            # 读取meta记录
            meta = self.read_meta(filepath)
            if not meta:
                self.logger.error("无法读取JSONL文件的meta记录")
                return None
            
            # 检查版本兼容性
            file_version = meta.get('file_version', meta.get('app_version', '1.0'))
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
            
            # 收集所有frame记录并转换为原始格式
            frames = []
            frame_count = 0
            
            for record in self.iter_frames(filepath):
                # 将记录转换回原始帧格式
                frame = {
                    'index': record.get('seq', 0),
                    'timestamp_ms': record.get('t_dev_ms', 0),
                }
                
                # 添加帧类型和版本
                if 'frame_type' in record:
                    frame['frame_type'] = record['frame_type']
                if 'frame_version' in record:
                    frame['frame_version'] = record['frame_version']
                
                # 恢复channels数据
                if 'ch' in record and 'amp' in record:
                    # 单信道（方向估计帧）
                    amp = record['amp']
                    # DF帧只保存p_avg和amplitude，其他字段物理上不存在，设为默认值
                    ch_data = {
                        'amplitude': amp,
                        'p_avg': record.get('p_avg', amp * amp if amp > 0 else 0.0),  # 如果存在则使用，否则从amplitude计算
                        'phase': 0.0,  # DF帧没有相位信息
                        'local_amplitude': amp,  # 与amplitude相同
                        'local_phase': 0.0,
                        'remote_amplitude': 0.0,
                        'remote_phase': 0.0,
                        'I': 0.0,
                        'Q': 0.0,
                        'il': 0.0,
                        'ql': 0.0,
                        'ir': 0.0,
                        'qr': 0.0
                    }
                    frame['channels'] = {
                        record['ch']: ch_data
                    }
                elif 'channels' in record:
                    # 多信道（信道探测帧）
                    channels = {}
                    for ch_str, ch_data in record['channels'].items():
                        try:
                            ch = int(ch_str)
                        except:
                            ch = ch_str
                        channels[ch] = {
                            'amplitude': ch_data.get('amp', 0.0),
                            'phase': ch_data.get('phase', 0.0),
                            'I': ch_data.get('I', 0.0),
                            'Q': ch_data.get('Q', 0.0),
                            'local_amplitude': ch_data.get('local_amp', ch_data.get('amp', 0.0)),  # 如果不存在，使用amplitude
                            'local_phase': ch_data.get('local_phase', 0.0),
                            'remote_amplitude': ch_data.get('remote_amp', 0.0),
                            'remote_phase': ch_data.get('remote_phase', 0.0),
                            'il': ch_data.get('il', 0.0),
                            'ql': ch_data.get('ql', 0.0),
                            'ir': ch_data.get('ir', 0.0),
                            'qr': ch_data.get('qr', 0.0)
                        }
                    frame['channels'] = channels
                
                frames.append(frame)
                frame_count += 1
            
            # 读取end记录（如果有）获取统计信息
            end_record = None
            for record in self.iter_records(filepath):
                if record.get('record_type') == 'end':
                    end_record = record
                    break
            
            # 构建返回数据结构（与JSON格式兼容）
            result = {
                'version': file_version,
                'saved_at': meta.get('started_at_iso', meta.get('started_at_utc_ns', '')),
                'total_frames': frame_count,
                'saved_frames': frame_count,
                'max_frames_param': None,  # JSONL格式不限制帧数
                'frame_type': meta.get('frame_type'),
                'frames': frames
            }
            
            # 添加frame_version（从第一帧获取）
            if frames and 'frame_version' in frames[0]:
                result['frame_version'] = frames[0]['frame_version']
            
            # 如果有end记录，更新统计信息
            if end_record:
                result['total_frames'] = end_record.get('written_records', frame_count)
                result['saved_frames'] = end_record.get('written_records', frame_count)
            
            self.logger.info(f"成功加载 {frame_count} 帧数据从JSONL: {filepath}, 文件版本: {file_version}")
            return result
            
        except Exception as e:
            self.logger.error(f"加载JSONL文件失败: {e}", exc_info=True)
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
                           frame_type: Optional[str] = None,
                           use_jsonl: bool = True) -> str:
        """
        获取自动保存路径（基于用户设置的保存目录）
        
        Args:
            prefix: 文件名前缀
            save_all: 是否保存全部帧
            max_frames: 如果保存最近N帧，指定N
            frame_type: 帧类型，用于添加DF/CS前缀
            use_jsonl: 是否使用.jsonl扩展名（默认True，新格式）
        
        Returns:
            完整的保存路径
        """
        save_dir = user_settings.get_save_directory()
        # 确保目录存在
        os.makedirs(save_dir, exist_ok=True)
        
        filename = self.get_default_filename(prefix, save_all, max_frames, frame_type, use_jsonl)
        return os.path.join(save_dir, filename)
    
    # ========== JSONL格式保存和加载方法 ==========
    
    def start_log_session(self, log_path: str, frame_type: Optional[str] = None, 
                         serial_port: Optional[str] = None, 
                         serial_baud: Optional[str] = None) -> bool:
        """
        开始新的日志会话（JSONL格式）
        
        Args:
            log_path: 日志文件路径（.jsonl）
            frame_type: 帧类型，'direction_estimation' 或 'channel_sounding'
            serial_port: 串口端口（可选）
            serial_baud: 串口波特率（可选）
        
        Returns:
            True if success, False otherwise
        """
        try:
            # 确定文件版本
            if frame_type == 'direction_estimation':
                file_version = config.version_data_save
            else:
                file_version = '1.0.0'
            
            # 构建meta记录
            meta = {
                'app_version': config.version,
                'log_version': '1.0',
                'frame_type': frame_type or 'channel_sounding',
                'started_at_utc_ns': int(time.time_ns()),
                'started_at_iso': datetime.now().isoformat(),
                'file_version': file_version
            }
            
            if serial_port:
                meta['serial_port'] = serial_port
            if serial_baud:
                meta['serial_baud'] = serial_baud
            
            # 创建日志写入器并启动会话
            self.log_writer = LogWriter(flush_interval=100, queue_maxsize=10000)
            return self.log_writer.start_session(log_path, meta)
            
        except Exception as e:
            self.logger.error(f"启动日志会话失败: {e}", exc_info=True)
            return False
    
    def append_frame_to_log(self, frame: Dict) -> bool:
        """
        追加帧记录到日志（非阻塞）
        
        Args:
            frame: 帧数据字典
        
        Returns:
            True if queued, False if failed
        """
        if not self.log_writer or not self.log_writer.is_running:
            self.logger.warning("日志写入器未运行，无法追加帧")
            return False
        
        try:
            # 构建frame记录
            record = {
                'record_type': 'frame',
                'seq': frame.get('index', 0),
                't_dev_ms': frame.get('timestamp_ms', 0),
                't_host_utc_ns': int(time.time_ns()),
            }
            
            # 添加帧类型和版本
            if 'frame_type' in frame:
                record['frame_type'] = frame['frame_type']
            if 'frame_version' in frame:
                record['frame_version'] = frame['frame_version']
            
            # 添加信道数据
            channels = frame.get('channels', {})
            if channels:
                # 对于方向估计帧，通常只有一个信道
                if len(channels) == 1:
                    ch = list(channels.keys())[0]
                    ch_data = channels[ch]
                    record['ch'] = ch
                    record['amp'] = ch_data.get('amplitude', 0.0)
                    # DF帧只保存p_avg和amplitude，其他字段物理上不存在
                    if 'p_avg' in ch_data:
                        record['p_avg'] = ch_data['p_avg']
                else:
                    # 多个信道（信道探测帧），保存为字典
                    record['channels'] = {}
                    for ch, ch_data in channels.items():
                        ch_record = {
                            'amp': ch_data.get('amplitude', 0.0),
                            'phase': ch_data.get('phase'),
                            'I': ch_data.get('I'),
                            'Q': ch_data.get('Q')
                        }
                        # 保存CS帧的其他字段（如果存在）
                        if 'local_amplitude' in ch_data:
                            ch_record['local_amp'] = ch_data['local_amplitude']
                        if 'local_phase' in ch_data:
                            ch_record['local_phase'] = ch_data['local_phase']
                        if 'remote_amplitude' in ch_data:
                            ch_record['remote_amp'] = ch_data['remote_amplitude']
                        if 'remote_phase' in ch_data:
                            ch_record['remote_phase'] = ch_data['remote_phase']
                        if 'il' in ch_data:
                            ch_record['il'] = ch_data['il']
                        if 'ql' in ch_data:
                            ch_record['ql'] = ch_data['ql']
                        if 'ir' in ch_data:
                            ch_record['ir'] = ch_data['ir']
                        if 'qr' in ch_data:
                            ch_record['qr'] = ch_data['qr']
                        record['channels'][str(ch)] = ch_record
            
            return self.log_writer.append_record(record)
            
        except Exception as e:
            self.logger.error(f"追加帧记录失败: {e}", exc_info=True)
            return False
    
    def append_event_to_log(self, label: str, note: Optional[str] = None,
                           nearest_seq: Optional[int] = None,
                           nearest_t_dev_ms: Optional[int] = None) -> bool:
        """
        追加事件记录到日志（用于手工标记）
        
        Args:
            label: 事件标签/名称
            note: 用户备注（可选）
            nearest_seq: 最近帧序号（可选）
            nearest_t_dev_ms: 最近帧设备时间戳（可选）
        
        Returns:
            True if queued, False if failed
        """
        if not self.log_writer or not self.log_writer.is_running:
            self.logger.warning("日志写入器未运行，无法追加事件")
            return False
        
        try:
            record = {
                'record_type': 'event',
                'label': label,
                't_host_utc_ns': int(time.time_ns()),
            }
            
            if note:
                record['note'] = note
            if nearest_seq is not None:
                record['nearest_seq'] = nearest_seq
            if nearest_t_dev_ms is not None:
                record['nearest_t_dev_ms'] = nearest_t_dev_ms
            
            return self.log_writer.append_record(record)
            
        except Exception as e:
            self.logger.error(f"追加事件记录失败: {e}", exc_info=True)
            return False
    
    def stop_log_session(self) -> Dict:
        """
        停止日志会话
        
        Returns:
            统计信息字典
        """
        if self.log_writer:
            stats = self.log_writer.stop_session()
            self.log_writer = None
            return stats
        return {'written_records': 0, 'dropped_records': 0}
    
    # ========== JSONL格式加载方法 ==========
    
    def read_meta(self, log_path: str) -> Optional[Dict]:
        """
        读取日志文件的meta记录（第一行）
        
        Args:
            log_path: 日志文件路径
        
        Returns:
            meta字典，如果失败返回None
        """
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                first_line = f.readline()
                if first_line:
                    meta = json.loads(first_line.strip())
                    if meta.get('record_type') == 'meta':
                        return meta
            return None
        except Exception as e:
            self.logger.error(f"读取meta记录失败: {e}", exc_info=True)
            return None
    
    def iter_records(self, log_path: str) -> Generator[Dict, None, None]:
        """
        迭代读取日志文件中的所有记录（流式）
        
        Args:
            log_path: 日志文件路径
        
        Yields:
            记录字典（容错：坏行跳过）
        """
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if 'record_type' in record:
                            yield record
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"跳过第 {line_num} 行（JSON解析失败）: {e}")
                        continue
                    except Exception as e:
                        self.logger.warning(f"跳过第 {line_num} 行（处理失败）: {e}")
                        continue
        except Exception as e:
            self.logger.error(f"读取日志文件失败: {e}", exc_info=True)
    
    def iter_frames(self, log_path: str) -> Generator[Dict, None, None]:
        """
        迭代读取日志文件中的frame记录
        
        Args:
            log_path: 日志文件路径
        
        Yields:
            frame记录字典
        """
        for record in self.iter_records(log_path):
            if record.get('record_type') == 'frame':
                yield record
    
    def iter_events(self, log_path: str) -> Generator[Dict, None, None]:
        """
        迭代读取日志文件中的event记录
        
        Args:
            log_path: 日志文件路径
        
        Yields:
            event记录字典
        """
        for record in self.iter_records(log_path):
            if record.get('record_type') == 'event':
                yield record
    
    def export_log_to_json(self, log_path: str, out_json_path: str, 
                          max_frames: Optional[int] = None) -> bool:
        """
        将JSONL日志文件导出为旧格式JSON（兼容性）
        
        Args:
            log_path: 输入的JSONL文件路径
            out_json_path: 输出的JSON文件路径
            max_frames: 最多导出多少帧（None表示全部）
        
        Returns:
            True if success, False otherwise
        """
        try:
            # 读取meta
            meta = self.read_meta(log_path)
            if not meta:
                self.logger.error("无法读取meta记录")
                return False
            
            # 收集所有frame记录
            frames = []
            frame_count = 0
            for record in self.iter_frames(log_path):
                # 将记录转换回原始帧格式
                frame = {
                    'index': record.get('seq', 0),
                    'timestamp_ms': record.get('t_dev_ms', 0),
                }
                
                if 'frame_type' in record:
                    frame['frame_type'] = record['frame_type']
                if 'frame_version' in record:
                    frame['frame_version'] = record['frame_version']
                
                # 恢复channels数据
                if 'ch' in record and 'amp' in record:
                    # 单信道（方向估计帧）
                    amp = record['amp']
                    # DF帧只保存p_avg和amplitude，其他字段物理上不存在，设为默认值
                    ch_data = {
                        'amplitude': amp,
                        'p_avg': record.get('p_avg', amp * amp if amp > 0 else 0.0),  # 如果存在则使用，否则从amplitude计算
                        'phase': 0.0,  # DF帧没有相位信息
                        'local_amplitude': amp,  # 与amplitude相同
                        'local_phase': 0.0,
                        'remote_amplitude': 0.0,
                        'remote_phase': 0.0,
                        'I': 0.0,
                        'Q': 0.0,
                        'il': 0.0,
                        'ql': 0.0,
                        'ir': 0.0,
                        'qr': 0.0
                    }
                    frame['channels'] = {
                        record['ch']: ch_data
                    }
                elif 'channels' in record:
                    # 多信道（信道探测帧）
                    channels = {}
                    for ch_str, ch_data in record['channels'].items():
                        ch = int(ch_str)
                        channels[ch] = {
                            'amplitude': ch_data.get('amp', 0.0),
                            'phase': ch_data.get('phase', 0.0),
                            'I': ch_data.get('I', 0.0),
                            'Q': ch_data.get('Q', 0.0),
                            'local_amplitude': ch_data.get('local_amp', ch_data.get('amp', 0.0)),  # 如果不存在，使用amplitude
                            'local_phase': ch_data.get('local_phase', 0.0),
                            'remote_amplitude': ch_data.get('remote_amp', 0.0),
                            'remote_phase': ch_data.get('remote_phase', 0.0),
                            'il': ch_data.get('il', 0.0),
                            'ql': ch_data.get('ql', 0.0),
                            'ir': ch_data.get('ir', 0.0),
                            'qr': ch_data.get('qr', 0.0)
                        }
                    frame['channels'] = channels
                
                frames.append(frame)
                frame_count += 1
                
                if max_frames and frame_count >= max_frames:
                    break
            
            # 构建导出数据结构
            export_data = {
                'version': meta.get('file_version', '1.0.0'),
                'saved_at': datetime.now().isoformat(),
                'total_frames': frame_count,
                'saved_frames': frame_count,
                'max_frames_param': max_frames,
                'frame_type': meta.get('frame_type'),
                'frames': frames
            }
            
            if 'frame_version' in frames[0] if frames else {}:
                export_data['frame_version'] = frames[0]['frame_version']
            
            # 使用临时文件+原子替换
            temp_path = out_json_path + '.tmp'
            try:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                
                # 原子替换
                if os.path.exists(out_json_path):
                    os.replace(temp_path, out_json_path)
                else:
                    os.rename(temp_path, out_json_path)
                
                self.logger.info(f"成功导出 {frame_count} 帧到: {out_json_path}")
                return True
                
            except Exception as e:
                # 清理临时文件
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                raise
                
        except Exception as e:
            self.logger.error(f"导出JSONL到JSON失败: {e}", exc_info=True)
            return False
    
    def get_default_filename(self, prefix: str = "frames", 
                            save_all: bool = True, 
                            max_frames: Optional[int] = None,
                            frame_type: Optional[str] = None,
                            use_jsonl: bool = True) -> str:
        """
        生成默认文件名
        
        Args:
            prefix: 文件名前缀
            save_all: 是否保存全部帧
            max_frames: 如果保存最近N帧，指定N
            frame_type: 帧类型，'direction_estimation' 或 'channel_sounding'，用于添加DF/CS前缀
            use_jsonl: 是否使用.jsonl扩展名（默认True，新格式）
        
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
        
        # 扩展名
        ext = ".jsonl" if use_jsonl else ".json"
        
        if save_all:
            return f"{type_prefix}{prefix}_all_{timestamp}{ext}"
        else:
            return f"{type_prefix}{prefix}_recent{max_frames}_{timestamp}{ext}"

