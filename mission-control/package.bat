@echo off
setlocal

REM ── OpenClaw Mission Control — Windows Package Builder ────────────────────
REM Produces: releases/openclaw-mission-control-vX.Y.Z.zip
REM Run from the mission-control\ directory.

cd /d "%~dp0"

REM Read current version
set /p CURRENT_VERSION=<VERSION
echo.
echo  Current version: %CURRENT_VERSION%
echo.
echo  Bump type:
echo    [1] patch  (%CURRENT_VERSION% -^> x.y.Z+1)
echo    [2] minor  (%CURRENT_VERSION% -^> x.Y+1.0)
echo    [3] major  (%CURRENT_VERSION% -^> X+1.0.0)
echo    [4] keep current version
echo.
set /p BUMP_TYPE=  Enter choice (1-4):

REM Calculate new version using PowerShell
if "%BUMP_TYPE%"=="4" (
    set VERSION=%CURRENT_VERSION%
    echo  Keeping version: %CURRENT_VERSION%
) else (
    for /f %%i in ('powershell -NoProfile -Command ^
        "$v='%CURRENT_VERSION%' -split '\.'; $ma=[int]$v[0]; $mi=[int]$v[1]; $pa=[int]$v[2]; ^
        if ('%BUMP_TYPE%' -eq '1') { $pa++ } ^
        elseif ('%BUMP_TYPE%' -eq '2') { $mi++; $pa=0 } ^
        elseif ('%BUMP_TYPE%' -eq '3') { $ma++; $mi=0; $pa=0 }; ^
        Write-Output ""$ma.$mi.$pa"""') do set VERSION=%%i

    echo  New version: %VERSION%
    echo %VERSION%>VERSION
)

echo.

set PACKAGE_NAME=openclaw-mission-control-v%VERSION%
set STAGING=%TEMP%\%PACKAGE_NAME%
set OUT_DIR=%~dp0releases
set ZIP_OUT=%OUT_DIR%\%PACKAGE_NAME%.zip

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
