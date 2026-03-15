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
set OUT_DIR=%~dp0releases
set ZIP_OUT=%OUT_DIR%\%PACKAGE_NAME%.zip
set APP_DIR=%~dp0

echo.
echo  Building package: %PACKAGE_NAME%
echo.

REM Delegate everything to PowerShell — avoids cmd.exe robocopy/redirect issues
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$appDir = '%APP_DIR%'.TrimEnd('\');" ^
  "$staging = [System.IO.Path]::Combine($env:TEMP, '%PACKAGE_NAME%');" ^
  "$outDir  = '%OUT_DIR%';" ^
  "$zipOut  = '%ZIP_OUT%';" ^
  "if (Test-Path $staging) { Remove-Item $staging -Recurse -Force };" ^
  "New-Item -ItemType Directory $staging | Out-Null;" ^
  "$launchers = @('launch_agents.bat','launch_agents.command','monitor_agents.bat','monitor_agents.command','SETUP-MAC.command','VERSION');" ^
  "foreach ($f in $launchers) { Copy-Item (Join-Path $appDir $f) (Join-Path $staging $f) };" ^
  "$mcDst = Join-Path $staging 'mission-control';" ^
  "Copy-Item $appDir $mcDst -Recurse -Force;" ^
  "$excludeDirs = @('.venv','dist','build','__pycache__','.git','releases');" ^
  "foreach ($d in $excludeDirs) { $p = Join-Path $mcDst $d; if (Test-Path $p) { Remove-Item $p -Recurse -Force } };" ^
  "Get-ChildItem $mcDst -Recurse -Include '*.pyc','*.pyo','*.spec' | Remove-Item -Force;" ^
  "if (-not (Test-Path $outDir)) { New-Item -ItemType Directory $outDir | Out-Null };" ^
  "if (Test-Path $zipOut) { Remove-Item $zipOut -Force };" ^
  "Compress-Archive -Path $staging -DestinationPath $zipOut -Force;" ^
  "Remove-Item $staging -Recurse -Force;" ^
  "Write-Host ' [+] Package created: releases\%PACKAGE_NAME%.zip';" ^
  "$size = (Get-Item $zipOut).Length; Write-Host (' Size: ' + $size + ' bytes')"

if %errorlevel% neq 0 (
    echo  [X] Build failed. See error above.
    pause
    exit /b 1
)

echo.
endlocal
