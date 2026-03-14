@echo off
setlocal

REM ── OpenClaw Mission Control — Windows Package Builder ────────────────────
REM Produces: releases/openclaw-mission-control-vX.Y.Z.zip
REM Version is read from the VERSION file and bumped manually per commit.
REM Run from the mission-control\ directory.

cd /d "%~dp0"

REM Read version
set /p VERSION=<VERSION
set PACKAGE_NAME=openclaw-mission-control-v%VERSION%
set STAGING=%TEMP%\%PACKAGE_NAME%
set OUT_DIR=%~dp0releases
set ZIP_OUT=%OUT_DIR%\%PACKAGE_NAME%.zip

echo.
echo  Building package: %PACKAGE_NAME%
echo.

REM Create staging directory
if exist "%STAGING%" rmdir /s /q "%STAGING%"
mkdir "%STAGING%"

REM Copy launcher files
copy /y launch_agents.bat    "%STAGING%\launch_agents.bat"    >nul
copy /y launch_agents.command "%STAGING%\launch_agents.command" >nul
copy /y monitor_agents.bat   "%STAGING%\monitor_agents.bat"   >nul
copy /y monitor_agents.command "%STAGING%\monitor_agents.command" >nul
copy /y VERSION              "%STAGING%\VERSION"              >nul

REM Copy mission-control app code (exclude build artifacts)
robocopy "%~dp0" "%STAGING%\mission-control" ^
  /E /XD .venv dist build __pycache__ .git releases ^
  /XF *.pyc *.pyo *.spec >nul

REM Create releases directory
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

REM Zip using PowerShell (built into Windows 10+)
if exist "%ZIP_OUT%" del "%ZIP_OUT%"
powershell -NoProfile -Command "Compress-Archive -Path '%STAGING%' -DestinationPath '%ZIP_OUT%' -Force"

if %errorlevel% neq 0 (
    echo  [X] Zip failed.
    pause
    exit /b 1
)

REM Cleanup staging
rmdir /s /q "%STAGING%"

echo  [+] Package created: releases\%PACKAGE_NAME%.zip
echo.

REM Show file size
for %%F in ("%ZIP_OUT%") do echo  Size: %%~zF bytes

echo.
endlocal
