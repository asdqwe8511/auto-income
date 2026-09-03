@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TEST MODE - telegram live
".venv\Scripts\python.exe" "scripts\watch.py"
echo.
pause
