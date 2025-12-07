@echo off
REM Windows打包脚本
REM 使用方法: build.bat

echo 正在安装依赖...
pip install -r requirements.txt

echo 正在安装PyInstaller...
pip install pyinstaller

echo 正在读取版本号...
for /f %%a in ('python get_version.py') do set VERSION=%%a
echo 版本号: %VERSION%

echo 正在生成 ICO 图标文件...
python create_icon.py
if errorlevel 1 (
    echo 警告: ICO 文件生成失败，将使用 PNG 文件
)

echo 正在更新 build.spec 文件...
python update_spec_version.py %VERSION%

echo 正在打包...
python -m PyInstaller --clean build.spec

echo 打包完成！可执行文件位于 dist\BLEHost-v%VERSION%.exe

