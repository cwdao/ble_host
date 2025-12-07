@echo off
REM 清除 Windows 缩略图缓存
REM 使用方法: clear_thumbnail_cache.bat

echo 正在清除 Windows 缩略图缓存...
echo.

REM 停止 Windows 资源管理器进程（需要重启才能清除缓存）
taskkill /f /im explorer.exe >nul 2>&1

REM 删除缩略图缓存文件
if exist "%LOCALAPPDATA%\Microsoft\Windows\Explorer\thumbcache_*.db" (
    del /a /q /s "%LOCALAPPDATA%\Microsoft\Windows\Explorer\thumbcache_*.db" 2>nul
    echo 已删除缩略图缓存文件
) else (
    echo 未找到缩略图缓存文件
)

REM 删除图标缓存
if exist "%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db" (
    del /a /q /s "%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db" 2>nul
    echo 已删除图标缓存文件
)

REM 重启 Windows 资源管理器
start explorer.exe

echo.
echo 缩略图缓存已清除！
echo 提示: 如果图标仍未更新，请尝试:
echo 1. 重新打包程序（删除 dist 目录后运行 build.bat）
echo 2. 重启电脑
echo 3. 在文件资源管理器中，查看 -> 选项 -> 查看 -> 取消勾选 "始终显示图标，从不显示缩略图"
pause

