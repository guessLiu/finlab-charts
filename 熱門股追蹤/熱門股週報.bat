@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0..\..\venv\Scripts\activate.bat"
python hot_stocks_weekly.py
set EXITCODE=%ERRORLEVEL%
echo.
if /i "%~1" neq "--no-pause" pause
exit /b %EXITCODE%
