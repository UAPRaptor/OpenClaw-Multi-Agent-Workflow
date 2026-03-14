@echo off
setlocal enabledelayedexpansion
title OpenClaw Mission Control

echo.
echo  ==========================================
echo   OpenClaw Mission Control
echo  ==========================================
echo.

REM ── Step 1: Check for Python 3.10+ ────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] Python not found. Attempting to install via winget...
    echo.
    winget --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [X] winget is not available on this machine.
        echo.
        echo  Please install Python 3.10 or later manually:
        echo  https://www.python.org/downloads/
        echo.
        echo  Then run this file again.
        pause
        exit /b 1
    )
    winget install --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo.
        echo  [X] Python installation failed.
        echo  Please install Python manually: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo.
    echo  [+] Python installed. Restarting...
    echo.
    REM Refresh PATH and re-run
    call "%~f0"
    exit /b
)

REM ── Step 2: Verify Python version is 3.10+ ────────────────────────────────
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set PYMAJ=%%a
    set PYMIN=%%b
)
if !PYMAJ! lss 3 (
    echo  [X] Python !PYVER! found, but 3.10 or later is required.
    echo  Please install a newer version: https://www.python.org/downloads/
    pause
    exit /b 1
)
if !PYMAJ! equ 3 if !PYMIN! lss 10 (
    echo  [X] Python !PYVER! found, but 3.10 or later is required.
    echo  Please install a newer version: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo  [+] Python !PYVER! found.

REM ── Step 3: Create/activate virtual environment ────────────────────────────
set VENV_DIR=%~dp0.venv
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo  [.] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo  [X] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [+] Virtual environment created.
)

call "%VENV_DIR%\Scripts\activate.bat"

REM ── Step 4: Install/update dependencies ───────────────────────────────────
echo  [.] Checking dependencies...
pip install -q -r "%~dp0requirements.txt"
if %errorlevel% neq 0 (
    echo.
    echo  [X] Failed to install dependencies.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)
echo  [+] Dependencies ready.
echo.

REM ── Step 5: Launch ─────────────────────────────────────────────────────────
echo  [+] Starting OpenClaw Mission Control...
echo  [+] Browser will open automatically at http://localhost:8765
echo.
echo  Press Ctrl+C to stop the server.
echo.

python -m openclaw install

endlocal
