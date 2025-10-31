@echo off
REM Windows打包脚本
REM 使用方法: build.bat

echo 正在安装依赖...
pip install -r requirements.txt

echo 正在安装PyInstaller...
pip install pyinstaller

echo 正在打包...
python -m PyInstaller --clean build.spec

echo 打包完成！可执行文件位于 dist\BLEHost.exe

