#!/bin/bash
# OpenClaw Mission Control — First-time Mac setup
# ─────────────────────────────────────────────────────────────────────────────
# macOS marks downloaded files as quarantined. This script removes that flag
# and sets correct permissions so you can double-click the launchers normally.
#
# HOW TO USE (first time only):
#   Right-click this file in Finder → Open → click Open in the dialog
#   After this runs, launch_agents.command and monitor_agents.command
#   will double-click normally forever.
# ─────────────────────────────────────────────────────────────────────────────

FOLDER="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo " =========================================="
echo "  OpenClaw Mission Control — Mac Setup"
echo " =========================================="
echo ""
echo " Removing macOS quarantine flag from:"
echo "   $FOLDER"
echo ""

xattr -cr "$FOLDER"
chmod +x "$FOLDER"/*.command

echo " [+] Done. You can now double-click:"
echo "     • launch_agents.command  — installer wizard"
echo "     • monitor_agents.command — live dashboard"
echo ""
read -p " Press Enter to close..."
