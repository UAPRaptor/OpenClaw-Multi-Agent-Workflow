@echo off
setlocal enabledelayedexpansion
title OpenClaw Mission Control — Monitor

set VENV_DIR=%~dp0.venv

REM If venv doesn't exist yet, run the installer first
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo  [!] No environment found. Running setup first...
    call "%~dp0launch.bat"
    exit /b
)

call "%VENV_DIR%\Scripts\activate.bat"

echo.
echo  OpenClaw Mission Control — Monitor
echo  Browser will open at http://localhost:8765
echo  Press Ctrl+C to stop.
echo.

python -m openclaw monitor

endlocal
