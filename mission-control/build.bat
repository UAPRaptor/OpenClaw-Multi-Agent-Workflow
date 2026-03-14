@echo off
REM Build openclaw-windows.exe using PyInstaller
REM Run from the mission-control\ directory

echo Building OpenClaw Mission Control for Windows...

REM Install dependencies if needed
pip install -r requirements.txt

REM Build single-file executable
pyinstaller ^
  --onefile ^
  --name openclaw-windows ^
  --add-data "openclaw\web\static;openclaw\web\static" ^
  --add-data "openclaw\corpus;openclaw\corpus" ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops ^
  --hidden-import uvicorn.loops.asyncio ^
  --hidden-import uvicorn.protocols ^
  --hidden-import uvicorn.protocols.http ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import watchdog.observers.winapi ^
  openclaw\__main__.py

echo.
echo Done! Binary at: dist\openclaw-windows.exe
echo.
echo To run:
echo   dist\openclaw-windows.exe install
echo   dist\openclaw-windows.exe monitor --workspace C:\Users\You\openclaw-workspace
