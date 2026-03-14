#!/bin/bash
# ── OpenClaw Mission Control — Mac/Linux Package Builder ────────────────────
# Produces: releases/openclaw-mission-control-vX.Y.Z.zip
# Run from the mission-control/ directory.

set -e
cd "$(dirname "$0")"

CURRENT_VERSION=$(cat VERSION | tr -d '[:space:]')

echo ""
echo " Current version: ${CURRENT_VERSION}"
echo ""
echo " Bump type:"
echo "   [1] patch  (x.y.Z -> x.y.Z+1)"
echo "   [2] minor  (x.Y.z -> x.Y+1.0)"
echo "   [3] major  (X.y.z -> X+1.0.0)"
echo "   [4] keep current version"
echo ""
read -p "  Enter choice (1-4): " BUMP_TYPE

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

case "$BUMP_TYPE" in
  1) PATCH=$((PATCH + 1)) ;;
  2) MINOR=$((MINOR + 1)); PATCH=0 ;;
  3) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  4) ;;
  *) echo " Invalid choice. Keeping current version." ;;
esac

VERSION="${MAJOR}.${MINOR}.${PATCH}"

if [ "$VERSION" != "$CURRENT_VERSION" ]; then
  echo " New version: ${VERSION}"
  echo -n "$VERSION" > VERSION
else
  echo " Keeping version: ${VERSION}"
fi

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
cp launch_agents.bat     "$STAGING/launch_agents.bat"
cp launch_agents.command "$STAGING/launch_agents.command"
cp monitor_agents.bat    "$STAGING/monitor_agents.bat"
cp monitor_agents.command "$STAGING/monitor_agents.command"
cp VERSION               "$STAGING/VERSION"

# Make Mac launchers executable inside the zip
chmod +x "$STAGING/launch_agents.command" "$STAGING/monitor_agents.command"

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
