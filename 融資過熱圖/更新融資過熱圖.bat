@echo off
cd /d "%~dp0"
python margin_heat.py
start margin_heat_analysis.html
