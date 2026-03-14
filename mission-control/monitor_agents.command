#!/bin/bash
# OpenClaw Mission Control — Monitor (Mac)
# Double-click to open the live agent dashboard.

# Resolve directories
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
APP_DIR="$SCRIPT_DIR/mission-control"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo " [!] No environment found. Run launch_agents.command first to set up."
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

source "$VENV_DIR/bin/activate"

echo ""
echo " OpenClaw Mission Control — Monitor"
echo " Browser will open at http://localhost:8765"
echo " Press Ctrl+C to stop."
echo ""

cd "$APP_DIR"
python -m openclaw monitor
