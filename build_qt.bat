@echo off
REM Windows打包脚本 - Qt版本
REM 使用方法: build_qt.bat

echo 检查 Python 环境...
python --version
if errorlevel 1 (
    echo 错误: 未找到 Python，请确保 Python 已安装并添加到 PATH
    exit /b 1
)

echo 正在安装依赖...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo 错误: 依赖安装失败
    exit /b 1
)

echo 验证 PySide6 安装...
python -c "import PySide6; print('PySide6 版本:', PySide6.__version__)"
if errorlevel 1 (
    echo 错误: PySide6 未正确安装
    exit /b 1
)

echo 验证 pyqtgraph 安装...
python -c "import pyqtgraph; print('pyqtgraph 版本:', pyqtgraph.__version__)"
if errorlevel 1 (
    echo 错误: pyqtgraph 未正确安装
    exit /b 1
)

echo 正在安装PyInstaller...
python -m pip install pyinstaller

echo 正在读取版本号...
for /f %%a in ('python get_version.py') do set VERSION=%%a
echo 版本号: %VERSION%

echo 正在生成 ICO 图标文件...
python create_icon.py
if errorlevel 1 (
    echo 警告: ICO 文件生成失败，将使用 PNG 文件
)

echo 正在打包 Qt 版本...
python -m PyInstaller --clean build_qt.spec

if errorlevel 1 (
    echo 打包失败！请检查错误信息
    exit /b 1
)

echo 打包完成！可执行文件位于 dist\BLEHost-Qt-v%VERSION%.exe
