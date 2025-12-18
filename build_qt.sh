#!/bin/bash
# Linux/Git Bash打包脚本 - Qt版本
# 使用方法: bash build_qt.sh 或 chmod +x build_qt.sh && ./build_qt.sh

echo "正在安装依赖..."
pip install -r requirements.txt

echo "验证 PySide6 安装..."
python -c "import PySide6; print('PySide6 版本:', PySide6.__version__)"
if [ $? -ne 0 ]; then
    echo "错误: PySide6 未正确安装"
    exit 1
fi

echo "验证 pyqtgraph 安装..."
python -c "import pyqtgraph; print('pyqtgraph 版本:', pyqtgraph.__version__)"
if [ $? -ne 0 ]; then
    echo "错误: pyqtgraph 未正确安装"
    exit 1
fi

echo "正在安装PyInstaller..."
pip install pyinstaller

echo "正在读取版本号..."
VERSION=$(python get_version.py)
echo "版本号: $VERSION"

echo "正在生成 ICO 图标文件..."
python create_icon.py
if [ $? -ne 0 ]; then
    echo "警告: ICO 文件生成失败，将使用 PNG 文件"
fi

echo "正在更新 build_qt.spec 文件..."
python update_spec_version.py "$VERSION" build_qt.spec

echo "正在打包 Qt 版本..."
python -m PyInstaller --clean build_qt.spec

if [ $? -eq 0 ]; then
    echo "打包完成！可执行文件位于 dist/BLEHost-Qt-v${VERSION}"
else
    echo "打包失败！请检查错误信息"
    exit 1
fi
