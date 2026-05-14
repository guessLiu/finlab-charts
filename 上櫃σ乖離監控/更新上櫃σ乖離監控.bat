@echo off
cd /d "%~dp0"
call ..\..\venv\Scripts\activate.bat
python otc_sigma_monitor.py
start otc_sigma_monitor.html
