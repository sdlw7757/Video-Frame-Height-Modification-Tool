@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo      视频帧高度修改工具 v1.0
echo ==========================================
echo.
echo 正在初始化环境...

:: 检查FFmpeg文件是否存在
if not exist "bin\ffmpeg.exe" (
    echo ⚠ 错误: 找不到 bin\ffmpeg.exe
    echo 请确保 FFmpeg 工具文件存在于 bin 目录中
    goto :error
)

if not exist "bin\ffprobe.exe" (
    echo ⚠ 错误: 找不到 bin\ffprobe.exe
    echo 请确保 FFmpeg 工具文件存在于 bin 目录中
    goto :error
)

echo ✓ FFmpeg 工具文件检查通过
echo.

:: 添加FFmpeg到当前会话PATH
set "FFMPEG_PATH=%~dp0bin"
set "PATH=%FFMPEG_PATH%;%PATH%"
echo ✓ 已将 FFmpeg 添加到环境变量
echo.

echo 正在启动程序...
echo.
python main.py

echo.
echo 程序已退出。按任意键关闭窗口...
pause >nul
goto :eof

:error
echo.
echo 按任意键退出...
pause >nul