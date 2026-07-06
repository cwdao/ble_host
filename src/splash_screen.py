#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启动画面：应用加载时显示进度与状态文字"""

import os
import sys

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication, QPixmap, QIcon


def resolve_asset_path(filename: str) -> str:
    """解析 assets 目录下资源路径（开发环境与 PyInstaller 均适用）"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, 'assets', filename)


def _load_app_icon_pixmap(size: int = 64) -> QPixmap:
    """加载应用图标，优先 png，回退 ico"""
    for name in ('ico.png', 'ico.ico'):
        path = resolve_asset_path(name)
        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                return pixmap.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
    return QPixmap()


class StartupSplash(QWidget):
    """简单启动窗口：图标 + 标题 + 进度条 + 状态文字"""

    def __init__(self, title: str = "BLE Sensing Host", subtitle: str = ""):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
        )
        self.setFixedSize(480, 168)
        self.setStyleSheet(
            "StartupSplash, QWidget#StartupSplashRoot {"
            "  background-color: #f5f7fa;"
            "  border: 1px solid #c8d0dc;"
            "  border-radius: 8px;"
            "}"
            "QLabel#SplashTitle {"
            "  color: #1a2b4b;"
            "  font-size: 16px;"
            "  font-weight: bold;"
            "}"
            "QLabel#SplashSubtitle {"
            "  color: #5c6b82;"
            "  font-size: 11px;"
            "}"
            "QLabel#SplashStatus {"
            "  color: #3d4f68;"
            "  font-size: 10px;"
            "}"
            "QProgressBar {"
            "  border: 1px solid #b8c4d4;"
            "  border-radius: 4px;"
            "  background: #e8edf3;"
            "  height: 14px;"
            "  text-align: center;"
            "}"
            "QProgressBar::chunk {"
            "  background-color: #3b7ddd;"
            "  border-radius: 3px;"
            "}"
        )
        self.setObjectName("StartupSplashRoot")

        icon_path = resolve_asset_path('ico.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(14)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(64, 64)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_pixmap = _load_app_icon_pixmap(64)
        if not icon_pixmap.isNull():
            self.icon_label.setPixmap(icon_pixmap)
        else:
            self.icon_label.setVisible(False)
        header.addWidget(self.icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SplashTitle")
        self.title_label.setFont(
            QFont(self.title_label.font().family(), 14, QFont.Weight.Bold)
        )
        text_col.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("SplashSubtitle")
        self.subtitle_label.setVisible(bool(subtitle))
        text_col.addWidget(self.subtitle_label)
        text_col.addStretch()
        header.addLayout(text_col, stretch=1)
        layout.addLayout(header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("正在启动...")
        self.status_label.setObjectName("SplashStatus")
        layout.addWidget(self.status_label)

    def set_progress(self, value: int, message: str):
        """更新进度条与状态文字，并刷新界面"""
        self.progress_bar.setValue(max(0, min(100, value)))
        self.status_label.setText(message)
        QApplication.processEvents()

    def finish(self, main_window: QWidget):
        """关闭启动画面并显示主窗口"""
        self.set_progress(100, "加载完成")
        main_window.show()
        self.close()

    def center_on_screen(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)


def create_startup_splash(app: QApplication, title: str, subtitle: str = "") -> StartupSplash:
    """创建并显示启动画面"""
    splash = StartupSplash(title=title, subtitle=subtitle)
    splash.center_on_screen()
    splash.show()
    app.processEvents()
    return splash
