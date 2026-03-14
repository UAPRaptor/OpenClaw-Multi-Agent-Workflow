#!/bin/bash
# Build openclaw-mac binary using PyInstaller
# Run from the mission-control/ directory

set -e

echo "Building OpenClaw Mission Control for macOS..."

# Install dependencies if needed
pip install -r requirements.txt

# Build single-file binary
pyinstaller \
  --onefile \
  --name openclaw-mac \
  --add-data "openclaw/web/static:openclaw/web/static" \
  --add-data "openclaw/corpus:openclaw/corpus" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops \
  --hidden-import uvicorn.loops.asyncio \
  --hidden-import uvicorn.protocols \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import watchdog.observers.fsevents \
  openclaw/__main__.py

echo ""
echo "Done! Binary at: dist/openclaw-mac"
echo ""
echo "To run:"
echo "  chmod +x dist/openclaw-mac"
echo "  ./dist/openclaw-mac install"
echo "  ./dist/openclaw-mac monitor --workspace ~/openclaw-workspace"
