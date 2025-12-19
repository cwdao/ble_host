# coding:utf-8
"""
InfoBar 工具模块
提供统一的 InfoBar 提示功能，用于替代 QMessageBox
"""
from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition


class InfoBarHelper:
    """InfoBar 辅助类，提供统一的提示方法"""
    
    # 默认配置
    DEFAULT_POSITION = InfoBarPosition.TOP_RIGHT
    DEFAULT_DURATION = 2000  # 2秒后自动消失
    DEFAULT_IS_CLOSABLE = True
    
    @staticmethod
    def success(parent, title: str, content: str, 
                position: InfoBarPosition = None,
                duration: int = None,
                is_closable: bool = None):
        """
        显示成功提示
        
        Args:
            parent: 父窗口
            title: 标题
            content: 内容
            position: 位置（默认 TOP_RIGHT）
            duration: 持续时间（毫秒，默认 2000，-1 表示不自动消失）
            is_closable: 是否可关闭（默认 True）
        """
        position = position or InfoBarHelper.DEFAULT_POSITION
        duration = duration if duration is not None else InfoBarHelper.DEFAULT_DURATION
        is_closable = is_closable if is_closable is not None else InfoBarHelper.DEFAULT_IS_CLOSABLE
        
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=is_closable,
            position=position,
            duration=duration,
            parent=parent
        )
    
    @staticmethod
    def warning(parent, title: str, content: str,
                position: InfoBarPosition = None,
                duration: int = None,
                is_closable: bool = None):
        """
        显示警告提示
        
        Args:
            parent: 父窗口
            title: 标题
            content: 内容
            position: 位置（默认 TOP_RIGHT）
            duration: 持续时间（毫秒，默认 2000，-1 表示不自动消失）
            is_closable: 是否可关闭（默认 True）
        """
        position = position or InfoBarHelper.DEFAULT_POSITION
        duration = duration if duration is not None else InfoBarHelper.DEFAULT_DURATION
        is_closable = is_closable if is_closable is not None else InfoBarHelper.DEFAULT_IS_CLOSABLE
        
        InfoBar.warning(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=is_closable,
            position=position,
            duration=duration,
            parent=parent
        )
    
    @staticmethod
    def error(parent, title: str, content: str,
              position: InfoBarPosition = None,
              duration: int = None,
              is_closable: bool = None):
        """
        显示错误提示
        
        Args:
            parent: 父窗口
            title: 标题
            content: 内容
            position: 位置（默认 TOP_RIGHT）
            duration: 持续时间（毫秒，默认 2000，-1 表示不自动消失）
            is_closable: 是否可关闭（默认 True）
        """
        position = position or InfoBarHelper.DEFAULT_POSITION
        duration = duration if duration is not None else InfoBarHelper.DEFAULT_DURATION
        is_closable = is_closable if is_closable is not None else InfoBarHelper.DEFAULT_IS_CLOSABLE
        
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=is_closable,
            position=position,
            duration=duration,
            parent=parent
        )
    
    @staticmethod
    def information(parent, title: str, content: str,
                    position: InfoBarPosition = None,
                    duration: int = None,
                    is_closable: bool = None):
        """
        显示信息提示
        
        Args:
            parent: 父窗口
            title: 标题
            content: 内容
            position: 位置（默认 TOP_RIGHT）
            duration: 持续时间（毫秒，默认 2000，-1 表示不自动消失）
            is_closable: 是否可关闭（默认 True）
        """
        position = position or InfoBarHelper.DEFAULT_POSITION
        duration = duration if duration is not None else InfoBarHelper.DEFAULT_DURATION
        is_closable = is_closable if is_closable is not None else InfoBarHelper.DEFAULT_IS_CLOSABLE
        
        InfoBar.info(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=is_closable,
            position=position,
            duration=duration,
            parent=parent
        )
