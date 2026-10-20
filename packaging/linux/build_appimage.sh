#!/usr/bin/env bash
# build_appimage.sh
# ==================
# Builds ESP32MultiFlashManager with PyInstaller, then wraps it into a
# self-contained, distro-agnostic AppImage that also registers the
# .emfm file association (desktop entry + shared-mime-info XML) when the
# AppImage is integrated via appimaged/AppImageLauncher, or when the user
# runs the AppImage's own `--appimage-install`-style integration.
#
# Usage:
#   packaging/linux/build_appimage.sh [version]
#
# Requirements: Linux, Python + requirements.txt + pyinstaller installed,
# and `rsvg-convert` (package librsvg2-bin) to rasterize the app icon.
# appimagetool is downloaded automatically if not already on PATH.

set -euo pipefail

VERSION="${1:-1.1.0}"
ARCH="$(uname -m)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "==> Building ESP32MultiFlashManager with PyInstaller"
pyinstaller --noconfirm --onefile \
    --name ESP32MultiFlashManager \
    --add-data "resources:resources" \
    --collect-all esptool \
    --collect-all espsecure \
    --collect-all espefuse \
    run.py

BIN_PATH="dist/ESP32MultiFlashManager"
if [[ ! -f "$BIN_PATH" ]]; then
    echo "Expected build output not found at $BIN_PATH" >&2
    exit 1
fi

APPDIR="dist/ESP32MultiFlashManager.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
    "$APPDIR/usr/share/mime/packages" \
    "$APPDIR/usr/share/metainfo" \
    "$APPDIR/usr/share/doc/esp32-multi-flash-manager"

echo "==> Assembling AppDir (version $VERSION)"
cp "$BIN_PATH" "$APPDIR/usr/bin/ESP32MultiFlashManager"
cp "$SCRIPT_DIR/esp32-multi-flash-manager.desktop" "$APPDIR/usr/share/applications/"
cp "$SCRIPT_DIR/esp32-multi-flash-manager.desktop" "$APPDIR/"
cp "$SCRIPT_DIR/esp32-multi-flash-manager-emfm.xml" "$APPDIR/usr/share/mime/packages/"
sed "s/version=\"1.1.0\"/version=\"$VERSION\"/" \
    "$SCRIPT_DIR/com.somangshudas.esp32multiflashmanager.appdata.xml" \
    > "$APPDIR/usr/share/metainfo/com.somangshudas.esp32multiflashmanager.appdata.xml"
cp "$REPO_ROOT/README.md" "$APPDIR/usr/share/doc/esp32-multi-flash-manager/README.txt"
cp "$REPO_ROOT/LICENSE" "$APPDIR/usr/share/doc/esp32-multi-flash-manager/LICENSE"

ICON_PNG="$APPDIR/usr/share/icons/hicolor/256x256/apps/esp32-multi-flash-manager.png"
if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w 256 -h 256 resources/icons/app_icon.svg -o "$ICON_PNG"
else
    echo "rsvg-convert not found; install librsvg2-bin to get a proper icon." >&2
    echo "Falling back to copying the SVG directly (lower quality in some launchers)." >&2
    cp resources/icons/app_icon.svg "$APPDIR/usr/share/icons/hicolor/256x256/apps/esp32-multi-flash-manager.svg"
fi
cp "$ICON_PNG" "$APPDIR/esp32-multi-flash-manager.png" 2>/dev/null || true

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/ESP32MultiFlashManager" "$@"
EOF
chmod +x "$APPDIR/AppRun"

APPIMAGETOOL="$(command -v appimagetool || true)"
if [[ -z "$APPIMAGETOOL" ]]; then
    echo "==> Downloading appimagetool"
    TOOL_PATH="dist/appimagetool-${ARCH}.AppImage"
    curl -L -o "$TOOL_PATH" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$TOOL_PATH"
    if ! file "$TOOL_PATH" | grep -qi 'ELF\|executable'; then
        echo "Downloaded file doesn't look like a real appimagetool binary:" >&2
        head -c 200 "$TOOL_PATH" >&2
        exit 1
    fi
    APPIMAGETOOL="$TOOL_PATH"
fi

OUT_DIR="dist/installer"
mkdir -p "$OUT_DIR"
OUT_PATH="$OUT_DIR/ESP32MultiFlashManager-${VERSION}-${ARCH}.AppImage"

echo "==> Building AppImage"
# appimagetool is itself distributed as an AppImage, so running it needs
# FUSE to mount itself. CI runners (and some desktop distros) don't ship
# libfuse2 by default, which fails with "dlopen(): error loading
# libfuse.so.2". APPIMAGE_EXTRACT_AND_RUN makes it extract-and-run instead
# of mounting, which works with no FUSE dependency at all.
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$APPIMAGETOOL" "$APPDIR" "$OUT_PATH"

echo "==> AppImage ready: $OUT_PATH"
echo "    (.emfm association registers once the AppImage is integrated"
echo "     via appimaged/AppImageLauncher, or after 'xdg-mime install"
echo "     usr/share/mime/packages/esp32-multi-flash-manager-emfm.xml'"
echo "     is run manually from inside the AppImage's mounted AppDir.)"
echo "    To uninstall: delete the .AppImage file, and if you integrated it"
echo "    with AppImageLauncher, remove it from there too (Right-click the"
echo "    app in your launcher -> Remove, or 'appimagelauncher --remove')."
