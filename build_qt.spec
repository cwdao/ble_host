# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller打包配置文件 - Qt版本
使用命令: pyinstaller build_qt.spec
"""

block_cipher = None

a = Analysis(
    ['run_qt.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),  # 包含 assets 目录，用于图标文件
    ],
    hiddenimports=[
        'src.serial_reader',
        'src.data_parser',
        'src.data_processor',
        'src.data_saver',
        'src.config',
        'src.breathing_estimator',
        'src.plotter_qt_realtime',
        'src.plotter_qt_matplotlib',
        'src.main_gui_qt',
        'src.utils.signal_algrithom',
        # PySide6 相关模块
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # PyQtGraph 相关模块
        'pyqtgraph',
        # Matplotlib 相关模块
        'matplotlib',
        'matplotlib.backends.backend_qtagg',
        'matplotlib.figure',
        # pyserial 相关模块（解决打包后无法连接串口的问题）
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'serial.serialutil',
        'serial.win32',  # Windows 平台特定模块
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BLEHost-Qt-v3.7.1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用 UPX 压缩以提升启动速度（UPX 压缩会增加启动时的解压时间）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/ico.ico',  # 设置 .exe 文件的图标（使用包含多尺寸的 ICO 文件以支持 Windows 缩略图）
)
