#!/bin/bash
# ── OpenClaw Mission Control — Mac/Linux Package Builder ────────────────────
# Produces: releases/openclaw-mission-control-vX.Y.Z.zip
# Version is read from the VERSION file and bumped manually per commit.
# Run from the mission-control/ directory.

set -e
cd "$(dirname "$0")"

VERSION=$(cat VERSION | tr -d '[:space:]')
PACKAGE_NAME="openclaw-mission-control-v${VERSION}"
STAGING="/tmp/${PACKAGE_NAME}"
OUT_DIR="$(pwd)/releases"
ZIP_OUT="${OUT_DIR}/${PACKAGE_NAME}.zip"

echo ""
echo " Building package: ${PACKAGE_NAME}"
echo ""

# Create staging directory
rm -rf "$STAGING"
mkdir -p "$STAGING"

# Copy launcher files
cp launch_agents.bat      "$STAGING/launch_agents.bat"
cp launch_agents.command  "$STAGING/launch_agents.command"
cp monitor_agents.bat     "$STAGING/monitor_agents.bat"
cp monitor_agents.command "$STAGING/monitor_agents.command"
cp SETUP-MAC.command      "$STAGING/SETUP-MAC.command"
cp VERSION                "$STAGING/VERSION"

# Make all Mac .command files executable inside the zip
chmod +x "$STAGING/"*.command

# Copy mission-control app code (exclude build artifacts)
rsync -a \
  --exclude='.venv' \
  --exclude='dist' \
  --exclude='build' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='*.spec' \
  --exclude='.git' \
  --exclude='releases' \
  ./ "$STAGING/mission-control/"

# Create releases directory
mkdir -p "$OUT_DIR"

# Create zip (preserve file permissions with -r)
rm -f "$ZIP_OUT"
cd /tmp
zip -r "$ZIP_OUT" "$PACKAGE_NAME" -x "*.DS_Store" -x "*__MACOSX*"
cd - > /dev/null

# Cleanup
rm -rf "$STAGING"

echo " [+] Package created: releases/${PACKAGE_NAME}.zip"
echo " Size: $(du -sh "$ZIP_OUT" | cut -f1)"
echo ""
