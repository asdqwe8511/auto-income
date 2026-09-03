@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GOOGLE SEARCH KEY
".venv\Scripts\python.exe" "scripts\set_cse.py"
echo.
pause
