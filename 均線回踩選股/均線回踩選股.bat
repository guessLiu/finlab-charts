@echo off
call "%~dp0..\..\venv\Scripts\activate.bat"
python ma_pullback_stocks.py
if errorlevel 1 pause
