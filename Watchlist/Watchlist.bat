@echo off
cd /d "%~dp0"

:: --- Find Python ---
:find_python
set "PY="
if exist "%~dp0venv\Scripts\python.exe" (
    set "PY=%~dp0venv\Scripts\python.exe"
    goto run
)
if exist "%~dp0python\python.exe" (
    set "PY=%~dp0python\python.exe"
    goto run
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto run
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto run
)
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    goto run
)
python -c "" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto run
py -c "" >nul 2>&1
if not errorlevel 1 set "PY=py"

:run
if not defined PY (
    goto install_python
)

echo [1/3] Updating stock names...
"%PY%" "%~dp0update_names.py"
if errorlevel 1 echo [WARN] Name update failed, continuing...

:open
echo.
echo [2/3] Backing up watchlist data on server startup...
echo Starting watchlist server...
"%PY%" "%~dp0watchlist_server.py"

echo.
echo Server stopped. Press any key to close.
:end
pause > nul
exit /b

:install_python
echo [WARN] Python not found.
echo        Trying to install Python automatically with winget...
echo.

winget --version >nul 2>&1
if errorlevel 1 goto install_failed

winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto install_failed

echo.
echo [OK] Python install finished. Starting Watchlist...
goto find_python

:install_failed
echo.
echo [ERROR] Could not install Python automatically.
echo        Please install Python 3.12 from:
echo        https://www.python.org/downloads/
echo.
echo        After installation, run this bat again.
goto end
