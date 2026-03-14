#!/bin/bash
# OpenClaw Mission Control — Monitor (Mac)
# Double-click to open the live agent dashboard.

cd "$(dirname "$0")"

VENV_DIR="$(pwd)/.venv"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo " [!] No environment found. Running setup first..."
    bash "$(dirname "$0")/launch.command"
    exit 0
fi

source "$VENV_DIR/bin/activate"

echo ""
echo " OpenClaw Mission Control — Monitor"
echo " Browser will open at http://localhost:8765"
echo " Press Ctrl+C to stop."
echo ""

python -m openclaw monitor
