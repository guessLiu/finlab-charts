@echo off
cd /d "%~dp0"
set "PY=%~dp0..\..\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" market_drop_theme_scan.py --sort performance
if errorlevel 1 (
    echo.
    echo Run failed. Check the error message above.
    pause
    exit /b 1
)

for /f "delims=" %%F in ('dir /b /a:-d /o:-d "market_drop_theme_scan_*.html" 2^>nul') do (
    start "" "%~dp0%%F"
    goto done
)

echo.
echo HTML report not found.

:done
echo.
pause
