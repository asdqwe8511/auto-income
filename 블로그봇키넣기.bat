@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BLOG BOT TOKEN
".venv\Scripts\python.exe" "scripts\set_blog_token.py"
echo.
pause
