# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller打包配置文件 - Qt版本（onedir 模式，启动更快）
使用命令: pyinstaller build_qt_onedir.spec

onedir 模式说明：
- 启动速度比 onefile 模式快 2-3 倍（无需解压临时文件）
- 生成一个目录，包含 exe 和所有依赖文件
- 适合需要快速启动的应用
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
    [],
    exclude_binaries=True,  # onedir 模式：不将二进制文件打包进 exe
    name='BLEHost-Qt-v3.2.1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用 UPX 压缩以提升启动速度
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/ico.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='BLEHost-Qt-v3.2.1',
)

