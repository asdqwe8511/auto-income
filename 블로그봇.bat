@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BLOG BOT
".venv\Scripts\python.exe" "scripts\blog_bot.py"
echo.
pause
