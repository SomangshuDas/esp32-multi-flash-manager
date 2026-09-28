# ESP32MultiFlashManager.spec
# ============================
# macOS-only PyInstaller spec. Building via this spec (instead of the plain
# CLI flags in docs/BUILD_INSTRUCTIONS.md) is what makes double-clicking a
# .emfm file in Finder, or dragging one onto the Dock icon, launch the
# app with that project pre-loaded: Info.plist's CFBundleDocumentTypes below
# is what tells LaunchServices "this app opens .emfm files", and Qt/main.py
# picks the resulting QFileOpenEvent up on the ESPFlashApplication subclass.
#
# Run from the repo root:
#   pyinstaller --noconfirm packaging/macos/ESP32MultiFlashManager.spec
#
# (packaging/macos/build_dmg.sh does this for you, plus the .icns generation
# and DMG packaging step.)

# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).resolve().parent.parent

# build_dmg.sh exports APP_VERSION before invoking PyInstaller so the
# .app's version metadata always matches the release tag / -Version arg
# instead of silently staying at a hardcoded default.
app_version = os.environ.get("APP_VERSION", "1.0.0")

# Equivalent of --collect-all esptool/espsecure/espefuse on the CLI: pull in
# their data files (stub loaders etc.) that static analysis alone would
# miss. espsecure and espefuse are separate top-level packages bundled
# alongside esptool inside the same `esptool` PyPI distribution -- they
# need their own collect_all() calls, not just esptool's.
# NOTE: these must be passed into Analysis() below, not appended to
# a.datas/a.binaries/a.hiddenimports afterward. collect_all() returns raw,
# un-normalized (src, dest) tuples, while a.datas etc. are already
# normalized to 3-item (dest, src, typecode) TOC entries once Analysis()
# runs. Mixing the two shapes in one list makes PyInstaller's internal
# normalize_toc() crash with "not enough values to unpack (expected 3,
# got 2)" during the later build stages.
from PyInstaller.utils.hooks import collect_all

esptool_datas, esptool_binaries, esptool_hiddenimports = collect_all("esptool")
espsecure_datas, espsecure_binaries, espsecure_hiddenimports = collect_all("espsecure")
espefuse_datas, espefuse_binaries, espefuse_hiddenimports = collect_all("espefuse")

a = Analysis(
    [str(repo_root / "run.py")],
    pathex=[str(repo_root)],
    binaries=esptool_binaries + espsecure_binaries + espefuse_binaries,
    datas=[(str(repo_root / "resources"), "resources")] + esptool_datas + espsecure_datas + espefuse_datas,
    hiddenimports=esptool_hiddenimports + espsecure_hiddenimports + espefuse_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ESP32MultiFlashManager",
    debug=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="ESP32MultiFlashManager",
)

app = BUNDLE(
    coll,
    name="ESP32MultiFlashManager.app",
    icon=str(repo_root / "resources" / "icons" / "app_icon.icns"),
    bundle_identifier="com.somangshudas.esp32multiflashmanager",
    info_plist={
        "CFBundleName": "ESP32 Multi Flash Manager",
        "CFBundleDisplayName": "ESP32 Multi Flash Manager",
        "CFBundleShortVersionString": app_version,
        "CFBundleVersion": app_version,
        "NSHumanReadableCopyright": "Copyright (C) Somangshu Das. MIT License.",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.developer-tools",
        "LSMinimumSystemVersion": "10.15",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "ESP32 Multi Flash Manager Project",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": ["com.somangshudas.esp32multiflashmanager.emfm"],
                "CFBundleTypeIconFile": "app_icon.icns",
            },
        ],
        "UTExportedTypeDeclarations": [
            {
                "UTTypeIdentifier": "com.somangshudas.esp32multiflashmanager.emfm",
                "UTTypeDescription": "ESP32 Multi Flash Manager Project",
                "UTTypeConformsTo": ["public.json", "public.data"],
                "UTTypeTagSpecification": {"public.filename-extension": ["emfm"]},
            },
        ],
    },
)
