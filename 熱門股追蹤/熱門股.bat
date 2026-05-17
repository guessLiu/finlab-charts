@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0..\..\venv\Scripts\activate.bat"
python hot_stocks.py
echo.
pause
