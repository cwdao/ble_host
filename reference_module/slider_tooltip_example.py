# coding:utf-8
"""
滑动条ToolTip备用方案示例
展示如何使用qfluentwidgets的ToolTip在滑动条上方显示tooltip
"""
import sys
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QSlider, QLabel
from qfluentwidgets import ToolTip, ToolTipFilter, ToolTipPosition


class SliderWithFluentTooltip(QSlider):
    """使用qfluentwidgets ToolTip的滑动条"""
    
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.fluent_tooltip = None
        # 连接信号
        self.sliderMoved.connect(self._show_fluent_tooltip)
        self.sliderPressed.connect(self._on_pressed)
        self.sliderReleased.connect(self._hide_fluent_tooltip)
    
    def _on_pressed(self):
        """按下时显示tooltip"""
        self._show_fluent_tooltip(self.value())
    
    def _show_fluent_tooltip(self, value):
        """使用qfluentwidgets ToolTip显示tooltip"""
        # 关闭之前的tooltip
        if self.fluent_tooltip:
            self.fluent_tooltip.close()
            self.fluent_tooltip = None
        
        # 方法1：使用ToolTipFilter（推荐，但位置控制有限）
        # 设置tooltip文本
        self.setToolTip(f"帧: {value}")
        self.setToolTipDuration(-1)  # 不自动消失
        
        # 安装ToolTipFilter，位置在上方
        if not hasattr(self, '_tooltip_filter_installed'):
            ToolTipFilter(self, 0, ToolTipPosition.TOP).installEventFilter(self)
            self._tooltip_filter_installed = True
        
        # 方法2：手动创建ToolTip窗口（如果需要精确控制位置）
        # 注意：qfluentwidgets的ToolTip API可能不支持直接设置位置
        # 如果需要精确位置控制，建议使用方法1或使用Qt的QToolTip
        
        # 方法3：使用自定义QLabel作为tooltip（完全控制位置）
        # 这需要手动管理tooltip的显示和隐藏
        # 可以参考下面的_custom_tooltip方法
    
    def _hide_fluent_tooltip(self):
        """隐藏tooltip"""
        if self.fluent_tooltip:
            self.fluent_tooltip.close()
            self.fluent_tooltip = None
        self.setToolTip("")  # 清除tooltip文本


class SliderWithCustomTooltip(QSlider):
    """使用自定义QLabel作为tooltip的滑动条（完全控制位置）"""
    
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.custom_tooltip = None
        # 连接信号
        self.sliderMoved.connect(self._show_custom_tooltip)
        self.sliderPressed.connect(self._on_pressed)
        self.sliderReleased.connect(self._hide_custom_tooltip)
    
    def _on_pressed(self):
        """按下时显示tooltip"""
        self._show_custom_tooltip(self.value())
    
    def _show_custom_tooltip(self, value):
        """使用自定义QLabel显示tooltip（完全控制位置）"""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import QTimer
        
        # 关闭之前的tooltip
        if self.custom_tooltip:
            self.custom_tooltip.close()
            self.custom_tooltip = None
        
        # 创建tooltip label
        self.custom_tooltip = QLabel(f"帧: {value}", self.window())
        self.custom_tooltip.setStyleSheet("""
            QLabel {
                background-color: rgba(50, 50, 50, 240);
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
        """)
        self.custom_tooltip.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.custom_tooltip.setWindowFlags(
            Qt.WindowType.ToolTip | 
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        
        # 计算位置
        slider_rect = self.rect()
        slider_center_x = slider_rect.center().x()
        slider_top_y = slider_rect.top()
        local_pos = QPoint(slider_center_x, slider_top_y)
        global_pos = self.mapToGlobal(local_pos)
        
        # 调整tooltip大小
        self.custom_tooltip.adjustSize()
        tooltip_width = self.custom_tooltip.width()
        tooltip_height = self.custom_tooltip.height()
        
        # 计算tooltip位置（在滑动条正上方中心）
        tooltip_x = global_pos.x() - tooltip_width // 2
        tooltip_y = global_pos.y() - tooltip_height - 10
        
        # 显示tooltip
        self.custom_tooltip.move(tooltip_x, tooltip_y)
        self.custom_tooltip.show()
    
    def _hide_custom_tooltip(self):
        """隐藏tooltip"""
        if self.custom_tooltip:
            self.custom_tooltip.close()
            self.custom_tooltip = None


class Demo(QWidget):
    """演示窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("滑动条ToolTip示例")
        self.resize(600, 200)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # 方法1：使用ToolTipFilter
        layout.addWidget(QLabel("方法1：使用qfluentwidgets ToolTipFilter"))
        slider1 = SliderWithFluentTooltip(Qt.Orientation.Horizontal, self)
        slider1.setMinimum(0)
        slider1.setMaximum(100)
        layout.addWidget(slider1)
        
        # 方法2：使用自定义QLabel（完全控制位置）
        layout.addWidget(QLabel("方法2：使用自定义QLabel（完全控制位置）"))
        slider2 = SliderWithCustomTooltip(Qt.Orientation.Horizontal, self)
        slider2.setMinimum(0)
        slider2.setMaximum(100)
        layout.addWidget(slider2)
        
        layout.addStretch()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = Demo()
    w.show()
    app.exec()

