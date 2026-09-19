# Build Instructions — ESP32 Multi Flash Manager

ESP32 Multi Flash Manager is a plain Python + PySide6 application with no
platform-specific code paths that matter at the source level — it runs
identically on **Windows, macOS, and Linux** via `python run.py`. This
document covers running it from source, verifying your environment, and
packaging it into a standalone executable on each of the three platforms.

The exact commands below are also run automatically on every push in
[`.github/workflows/build.yml`](../.github/workflows/build.yml), which
builds on `windows-latest`, `macos-latest`, and `ubuntu-latest` — that
workflow is the source of truth if this document ever drifts from it.
Tagged releases go further and produce an actual installer for each OS via
[`.github/workflows/release.yml`](../.github/workflows/release.yml) and
the scripts in [`packaging/`](../packaging) — see §4 below.

---

## 1. Run from source (recommended for development)

Requires Python 3.12+ on any of Windows, macOS, or Linux.

```bash
# From the project root
python -m venv .venv

# Windows (Command Prompt / PowerShell)
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```

To see debug-level console logging in addition to the rotating log files,
run:

```bash
python run.py --debug
```

## 2. Verify the environment before building

```bash
python -m esptool version
python -m espsecure version
python -m espefuse version
```

This should print the installed `esptool`/`espsecure`/`espefuse` versions
(all three ship inside the same `esptool` PyPI package). If any fail, fix
your Python environment before proceeding — the app calls all three exactly
this way (`python -m esptool ...` / `python -m espsecure ...` /
`python -m espefuse ...`) under the hood, on every platform. `espsecure` and
`espefuse` back the app's Flash Encryption / Secure Boot provisioning and
Read Flash / eFuse / Chip Info features (see `app/flash_engine/security_manager.py`).

## 3. Package as a standalone executable (PyInstaller)

```bash
pip install pyinstaller
```

The bundled icon assets are already in the right formats for each
platform's packager:

- `resources/icons/app_icon.ico` — multi-resolution (16/32/48/64/128/256)
  Windows icon, used directly.
- `resources/icons/app_icon.svg` — master vector source, used at runtime
  for the in-app window icon on every OS, and as the source for the macOS
  `.icns` conversion below.

### Windows

```powershell
pyinstaller --noconfirm --windowed --onefile ^
  --name ESP32MultiFlashManager ^
  --icon resources\icons\app_icon.ico ^
  --add-data "resources;resources" ^
  --collect-all esptool ^
  --collect-all espsecure ^
  --collect-all espefuse ^
  run.py
```

Output: `dist\ESP32MultiFlashManager.exe`

### macOS

PyInstaller wants a `.icns` file for the app bundle icon rather than the
`.ico`/`.svg`. Generate one from the bundled SVG once per release:

```bash
mkdir icon.iconset
for size in 16 32 128 256 512; do
  sips -z $size $size -s format png resources/icons/app_icon.svg \
    --out "icon.iconset/icon_${size}x${size}.png"
  double=$((size * 2))
  sips -z $double $double -s format png resources/icons/app_icon.svg \
    --out "icon.iconset/icon_${size}x${size}@2x.png"
done
iconutil -c icns icon.iconset -o resources/icons/app_icon.icns
rm -rf icon.iconset
```

(If `sips` can't rasterize SVG directly on your macOS version, export a
512×512 PNG from the SVG with any tool first and feed that to `sips`
instead.)

```bash
pyinstaller --noconfirm --windowed --onefile \
  --name ESP32MultiFlashManager \
  --icon resources/icons/app_icon.icns \
  --add-data "resources:resources" \
  --collect-all esptool \
  --collect-all espsecure \
  --collect-all espefuse \
  run.py
```

Output: `dist/ESP32MultiFlashManager.app`

Note the `:` separator for `--add-data` on macOS/Linux, versus `;` on
Windows.

### Linux

```bash
pyinstaller --noconfirm --onefile \
  --name ESP32MultiFlashManager \
  --add-data "resources:resources" \
  --collect-all esptool \
  --collect-all espsecure \
  --collect-all espefuse \
  run.py
```

Output: `dist/ESP32MultiFlashManager` (a self-contained ELF binary).

For a desktop-integrated launcher, create a `.desktop` entry pointing at
the built binary and `resources/icons/app_icon.svg` (most Linux desktop
environments accept SVG icons directly):

```ini
[Desktop Entry]
Type=Application
Name=ESP32 Multi Flash Manager
Exec=/path/to/dist/ESP32MultiFlashManager
Icon=/path/to/resources/icons/app_icon.svg
Categories=Development;Electronics;
```

Also make sure your user account can access serial devices:

```bash
sudo usermod -a -G dialout $USER
# log out and back in for the group change to take effect
```

### Notes common to all three platforms

- `--windowed` (Windows/macOS) suppresses the console window — the app has
  its own log files and error dialogs, so a console isn't needed for
  normal use. Linux `--onefile` builds don't take `--windowed`; the app
  still runs GUI-only.
- `--collect-all esptool --collect-all espsecure --collect-all espefuse` is
  important on every platform: all three ship data files (e.g. stub loader
  binaries) that PyInstaller's default analysis can miss; these flags force
  them to be bundled. `espsecure`/`espefuse` are separate top-level packages
  distributed alongside `esptool` inside the same PyPI package — collecting
  `esptool` alone does **not** pull them in, they need their own
  `--collect-all`. `--collect-all esptool` is also what makes dynamic
  chip-support detection work in a frozen build — at startup
  (`app/utilities/chip_detect.py`) the app does a plain in-process
  `from esptool.targets import CHIP_LIST` (separate from the
  `sys.executable -m esptool` subprocess used for actual flashing, see
  below) to build the Chip Type dropdown, which needs `esptool.targets`
  bundled the same as everything else `--collect-all` pulls in.
- Because `esptool`/`espsecure`/`espefuse` are each launched via
  `sys.executable -m <tool>` (see `app/flash_engine/esptool_wrapper.py` and
  `app/flash_engine/security_manager.py`), a PyInstaller `--onefile` build
  works correctly on every OS: `sys.executable` inside a frozen app points
  at the bundled executable itself, and all three packages are importable
  from inside it since they were collected into the bundle. `app/main.py`
  intercepts a hidden re-exec flag for each tool at startup and dispatches
  straight to that tool's own CLI `main()`, skipping Qt/GUI import overhead
  entirely.
- Icons and themes are resolved through `resource_path()` in
  `app/utilities/helpers.py`, which checks for PyInstaller's `sys._MEIPASS`
  first — this is what keeps the window icon working identically whether
  you run from source or from a frozen build, on any OS.

## 4. Building an installer

Real, tested scripts for this live under [`packaging/`](../packaging) —
see [`packaging/README.md`](../packaging/README.md) for the full
breakdown. They wrap the PyInstaller build above into a proper installer
for each OS, and register the **`.emfm` project file extension** with
the app in the process, so double-clicking a project file in the file
manager launches ESP32 Multi Flash Manager directly with that project
loaded (see `app/main.py::_project_path_from_argv` and
`ESPFlashApplication.event()` for how the app receives that path on each
OS).

- **Windows** —
  [`packaging/windows/build_installer.ps1`](../packaging/windows/build_installer.ps1)
  runs PyInstaller, then compiles
  [`packaging/windows/installer.iss`](../packaging/windows/installer.iss)
  with [Inno Setup 6](https://jrsoftware.org/isinfo.php) into
  `dist/installer/ESP32MultiFlashManagerSetup-<version>.exe` — a Setup.exe
  with Start Menu/Desktop shortcuts, an uninstaller, an opt-out
  `.emfm` file association written to `HKCU\Software\Classes`, and a
  post-install "View what's new" checkbox that opens the GitHub Releases
  page (there's no bundled changelog file, so this is always the current
  one). It also drops `install_marker.txt` next to the exe so
  `app/utilities/update_checker.py` can tell this was an installed build
  rather than a portable one the next time it checks for updates.

  ```powershell
  .\packaging\windows\build_installer.ps1 -Version 0.15.1
  ```

- **macOS** —
  [`packaging/macos/build_dmg.sh`](../packaging/macos/build_dmg.sh) builds
  `.app` via
  [`packaging/macos/ESP32MultiFlashManager.spec`](../packaging/macos/ESP32MultiFlashManager.spec)
  (which declares `CFBundleDocumentTypes`/`UTExportedTypeDeclarations` for
  `.emfm` in `Info.plist`), generating `app_icon.icns` first via
  [`packaging/macos/make_icns.sh`](../packaging/macos/make_icns.sh) if it
  doesn't already exist, then packages a drag-to-Applications
  `dist/installer/ESP32MultiFlashManager-<version>.dmg`.

  ```bash
  packaging/macos/build_dmg.sh 0.15.1
  ```

- **Linux** —
  [`packaging/linux/build_appimage.sh`](../packaging/linux/build_appimage.sh)
  builds the onefile binary, assembles an AppDir with the bundled
  [`.desktop`](../packaging/linux/esp32-multi-flash-manager.desktop) entry
  (`MimeType=application/x-emfm;application/x-efmproj;`) and
  [shared-mime-info XML](../packaging/linux/esp32-multi-flash-manager-emfm.xml),
  and wraps it into
  `dist/installer/ESP32MultiFlashManager-<version>-<arch>.AppImage` with
  `appimagetool` (downloaded automatically if not already on `PATH`).

  ```bash
  packaging/linux/build_appimage.sh 0.15.1
  ```

## 5. Continuous Integration

[`.github/workflows/build.yml`](../.github/workflows/build.yml) runs on
every push and pull request to `main` (and can be triggered manually via
`workflow_dispatch`). For each of `windows-latest`, `macos-latest`, and
`ubuntu-latest` it:

1. Installs Python 3.12 and the project's dependencies plus PyInstaller.
2. Byte-compiles the whole `app` package (`python -m compileall app`) so a
   syntax error fails fast.
3. Imports `app.main` headlessly (`QT_QPA_PLATFORM=offscreen`) as a smoke
   test that the app's import graph and Qt wiring are sound.
4. Runs the exact PyInstaller command documented above for that OS.
5. Uploads the resulting executable/bundle as a build artifact
   (`ESP32MultiFlashManager-windows` / `-macos` / `-linux`), downloadable
   from the workflow run's **Summary** page.

This means every commit gets an actual cross-platform build verification,
not just a "should work on Linux/macOS" assumption — a build that fails on
Windows or macOS fails CI, the same as a failing build on Linux would. On
Linux it additionally validates the packaging `.desktop` entry and MIME XML
with `desktop-file-validate`/`xmllint`, so a typo there fails CI too instead
of only surfacing when someone tries to cut a release.

[`.github/workflows/release.yml`](../.github/workflows/release.yml) runs
whenever a `v*.*.*` tag is pushed. For each OS it does the raw PyInstaller
build above (as before), then also runs that OS's `packaging/` script and
attaches **both** the raw executable/bundle *and* the installer
(`Setup.exe` / `.dmg` / `.AppImage`) to the GitHub Release, so users who
just want a portable binary and users who want proper OS integration
(Start Menu entry, `.emfm` file association, uninstaller, etc.) both
get what they need from the same release.

## 6. Verifying a build manually

1. Launch the built executable/bundle on a clean machine (or VM) that has
   never had the Python source environment on it.
2. Confirm `File → New Project`, `Devices → Add Device`, and
   `Firmware → Auto-Detect Folder...` (pointed at `examples/firmware`) all
   work.
3. Plug in a real ESP32 board, set its port, and try
   `Flash → Upload Selected` against a known-good firmware image to
   confirm the bundled `esptool` launches correctly from inside the frozen
   executable.
4. If testing the Security tab, try Tools → Read Flash / eFuse / Chip
   Info... against a real board to confirm the bundled `espefuse` also
   launches correctly from inside the frozen executable (this is a
   read-only check — it does not burn anything).
5. Confirm the app's log directory is being written to — see
   `docs/DEVELOPER_DOCUMENTATION.md` → **Logging** for the exact path on
   your OS.

## 7. Directory layout expected at runtime

The app does not require write access to its own install directory — all
persistent data (settings, recent projects, firmware profiles, logs) is
written under the per-OS application-data directory (see
`app/utilities/helpers.py::get_app_data_dir`), so it's safe to install
into `Program Files`, `/Applications`, or `/opt` on locked-down
manufacturing PCs on any platform.

---

Author: Somangshu Das — [github.com/SomangshuDas](https://github.com/SomangshuDas)
