@echo off
REM AI 创作运行平台 CLI 启动器（Windows）
REM 用法：platform.bat <cmd> [args]
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
python "%~dp0cli\platform.py" %*
