@echo off
chcp 65001 >nul
cd /d "%~dp0"
title KEY SETUP
".venv\Scripts\python.exe" "scripts\set_key.py"
echo.
pause
