@echo off
cd /d "%~dp0"
python build_chart.py
start index.html