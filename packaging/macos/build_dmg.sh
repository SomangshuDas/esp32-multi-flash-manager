#!/usr/bin/env bash
# build_dmg.sh
# ============
# Builds ESP32MultiFlashManager.app (via the spec in this folder, which wires
# up the .emfm file association) and packages it into a drag-to-Applications
# .dmg. Run from anywhere; paths are resolved relative to this script.
#
# Usage:
#   packaging/macos/build_dmg.sh [version]
#
# Requirements: macOS, Python + requirements.txt + pyinstaller installed.

set -euo pipefail

VERSION="${1:-1.1.0}"
export APP_VERSION="$VERSION"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f resources/icons/app_icon.icns ]]; then
    echo "==> resources/icons/app_icon.icns not found, generating it first"
    "$SCRIPT_DIR/make_icns.sh"
fi

echo "==> Building ESP32MultiFlashManager.app (version $VERSION) with PyInstaller"
pyinstaller --noconfirm "$SCRIPT_DIR/ESP32MultiFlashManager.spec"

APP_PATH="dist/ESP32MultiFlashManager.app"
if [[ ! -d "$APP_PATH" ]]; then
    echo "Expected build output not found at $APP_PATH" >&2
    exit 1
fi

echo "==> Staging DMG contents"
STAGING_DIR="$(mktemp -d)/dmg"
mkdir -p "$STAGING_DIR"
cp -R "$APP_PATH" "$STAGING_DIR/"
cp "$REPO_ROOT/README.md" "$STAGING_DIR/README.txt"
cp "$REPO_ROOT/LICENSE" "$STAGING_DIR/LICENSE.txt"
ln -s /Applications "$STAGING_DIR/Applications"

DMG_DIR="dist/installer"
mkdir -p "$DMG_DIR"
DMG_PATH="$DMG_DIR/ESP32MultiFlashManager-${VERSION}.dmg"
rm -f "$DMG_PATH"

echo "==> Creating $DMG_PATH"
hdiutil create -volname "ESP32 Multi Flash Manager ${VERSION}" \
    -srcfolder "$STAGING_DIR" \
    -ov -format UDZO \
    "$DMG_PATH"

rm -rf "$(dirname "$STAGING_DIR")"

echo "==> DMG ready: $DMG_PATH"
echo "    Contains: ESP32MultiFlashManager.app, README.txt, LICENSE.txt,"
echo "    and an Applications symlink for drag-to-install."
echo "    Note: this build is not code-signed/notarized, so first launch"
echo "    requires right-click -> Open (or System Settings -> Privacy &"
echo "    Security -> 'Open Anyway') to bypass Gatekeeper once."
