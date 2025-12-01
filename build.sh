#!/bin/bash
# Linux/Git Bash打包脚本
# 使用方法: bash build.sh 或 chmod +x build.sh && ./build.sh

echo "正在安装依赖..."
pip install -r requirements.txt

echo "正在安装PyInstaller..."
pip install pyinstaller

echo "正在读取版本号..."
VERSION=$(python get_version.py)
echo "版本号: $VERSION"

echo "正在更新 build.spec 文件..."
python update_spec_version.py "$VERSION"

echo "正在打包..."
python -m PyInstaller --clean build.spec

if [ $? -eq 0 ]; then
    echo "打包完成！可执行文件位于 dist/BLEHost-v${VERSION}"
else
    echo "打包失败！请检查错误信息"
    exit 1
fi

