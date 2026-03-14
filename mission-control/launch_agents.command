#!/bin/bash
# OpenClaw Mission Control — Mac launcher
# Double-click this file in Finder to launch.
# The .command extension makes it double-clickable and runs in Terminal.

set -e

# Change to the directory containing this script
cd "$(dirname "$0")"

echo ""
echo " =========================================="
echo "  OpenClaw Mission Control"
echo " =========================================="
echo ""

# ── Step 1: Check for Python 3.10+ ─────────────────────────────────────────
find_python() {
    for cmd in python3.12 python3.11 python3.10 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON=$(find_python 2>/dev/null || true)

if [ -z "$PYTHON" ]; then
    echo " [!] Python 3.10+ not found."
    echo ""

    # Try Homebrew install
    if command -v brew &>/dev/null; then
        echo " [.] Installing Python via Homebrew..."
        brew install python@3.12
        PYTHON=$(find_python)
    else
        echo " [X] Python 3.10+ is required."
        echo ""
        echo " Option 1 — Install via Homebrew (recommended):"
        echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        echo "   brew install python@3.12"
        echo ""
        echo " Option 2 — Install from python.org:"
        echo "   https://www.python.org/downloads/"
        echo ""
        echo " Then double-click this file again."
        echo ""
        read -p "Press Enter to close..."
        exit 1
    fi
fi

echo " [+] Found Python: $($PYTHON --version)"

# ── Step 2: Create/activate virtual environment ─────────────────────────────
VENV_DIR="$(pwd)/.venv"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo " [.] Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
    echo " [+] Virtual environment created."
fi

source "$VENV_DIR/bin/activate"

# ── Step 3: Install/update dependencies ─────────────────────────────────────
echo " [.] Checking dependencies..."
pip install -q -r requirements.txt
echo " [+] Dependencies ready."
echo ""

# ── Step 4: Launch ───────────────────────────────────────────────────────────
echo " [+] Starting OpenClaw Mission Control..."
echo " [+] Browser will open automatically at http://localhost:8765"
echo ""
echo " Press Ctrl+C to stop the server."
echo ""

python -m openclaw install
