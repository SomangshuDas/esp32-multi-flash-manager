# Packaging scripts

> **Testing status:** the Windows installer (`windows/build_installer.ps1`
> + `installer.iss`) has been tested and confirmed working. The macOS and
> Linux installers have **not** been tested on real hardware/VMs yet — if
> you build and run either and hit a problem, please open an issue on the
> repo.

Scripts here turn the PyInstaller build documented in
[`docs/BUILD_INSTRUCTIONS.md`](../docs/BUILD_INSTRUCTIONS.md) into a
proper, double-click installer for each OS — and register the `.emfm`
project file extension with the app in the process, so opening a project
file from the file manager (Explorer/Finder/Nautilus, etc.) launches
ESP32 Multi Flash Manager directly with that project loaded. (The older
pre-rename `.efmproj` extension and its whole fallback-read/forced-
migration compatibility path were discontinued in 1.0.0 — only `.emfm`
is recognized anywhere now.)

This is driven by `.github/workflows/release.yml`, which runs the
matching script for each OS whenever a `v*.*.*` tag is pushed and attaches
the results to the GitHub Release. You can also run any of them locally.

| OS      | Script                                | Output                                      |
|---------|----------------------------------------|----------------------------------------------|
| Windows | `windows/build_installer.ps1`          | `dist/installer/ESP32MultiFlashManagerSetup-<version>.exe` |
| macOS   | `macos/build_dmg.sh [version]`         | `dist/installer/ESP32MultiFlashManager-<version>.dmg`      |
| Linux   | `linux/build_appimage.sh [version]`    | `dist/installer/ESP32MultiFlashManager-<version>-<arch>.AppImage` |

## How the `.emfm` association works on each OS

- **Windows** (`windows/installer.iss`): the installer writes an
  `HKCU\Software\Classes\.emfm` registry entry pointing at a
  `ESP32MultiFlashManager.Project` ProgID, with its own icon and an
  `shell\open\command` of `ESP32MultiFlashManager.exe "%1"`. This is
  opt-out via the "Open .emfm project files with..." checkbox on the
  installer's task selection page (checked by default), and is fully
  removed by the generated uninstaller.
- **macOS** (`macos/ESP32MultiFlashManager.spec`): the `.app` bundle's
  `Info.plist` declares a `CFBundleDocumentTypes`/`UTExportedTypeDeclarations`
  pair for the `emfm` extension, so LaunchServices associates it with the
  app the first time the `.app` is launched or Spotlight re-indexes it.
- **Linux** (`linux/esp32-multi-flash-manager.desktop` +
  `linux/esp32-multi-flash-manager-emfm.xml`): a standard
  freedesktop.org `.desktop` entry (`MimeType=application/x-emfm;`)
  plus a shared-mime-info XML definition for the extension. These are
  bundled inside the AppImage and take effect once the AppImage is
  integrated with the desktop (e.g. via `appimaged`/AppImageLauncher), or
  can be installed system-wide by hand with `xdg-desktop-menu install` /
  `xdg-mime install`.

On every platform, the actual "open this file on startup" behavior lives
in `app/main.py`: `_project_path_from_argv()` handles the Windows/Linux
case (the OS launches the exe with the file path as an argument), and
`ESPFlashApplication.event()` handles the macOS case (delivered as a
`QFileOpenEvent` instead of an argv entry).

## What each installer includes

Beyond just "double-click to install," each one aims to behave like a
normal, professional installer for that OS:

| Feature | Windows | macOS | Linux |
|---|---|---|---|
| License agreement shown before install | ✅ (LICENSE, MIT) | — (shown in Applications window instead) | — (shown in AppStream metadata) |
| Per-user install, no admin needed | ✅ (default) | ✅ (always, `.app` in `/Applications` or `~/Applications`) | ✅ (always, single file) |
| "Install for all users" (admin) option | ✅ (opt-in on Select Destination page) | n/a | n/a |
| Clean, named entry in Add/Remove Programs / Launchpad / app menu | ✅ | ✅ | ✅ (via `.desktop` + AppStream metadata) |
| Start Menu / Applications shortcuts | ✅ (app, uninstall, README, LICENSE, GitHub link) | ✅ (drag-install `.app`) | ✅ (`.desktop` entry) |
| Bundled README + LICENSE | ✅ | ✅ (alongside `.app` in the `.dmg`) | ✅ (`usr/share/doc/`) |
| `.emfm` file association | ✅ | ✅ | ✅ (after desktop integration — see below) |
| Closes a running instance before upgrade | ✅ | — | — |
| Clean uninstall (removes shortcuts + association) | ✅ (Add/Remove Programs) | ✅ (drag `.app` to Trash) | ✅ (delete the `.AppImage`) |
| Post-install "View what's new" checkbox (opens GitHub Releases) | ✅ | — | — |
| Marks itself as an installed build for the in-app updater | ✅ (`install_marker.txt`) | — (always treated as portable) | — (always treated as portable) |

## Prerequisites

- **Windows**: [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`ISCC.exe`
  on `PATH`, or installed at its default location).
- **macOS**: Xcode command line tools (for `sips`/`iconutil`, already
  present on GitHub's `macos-latest` runners).
- **Linux**: `librsvg2-bin` (for `rsvg-convert`, used to rasterize the app
  icon). `appimagetool` is downloaded automatically if not already on
  `PATH`.

All three scripts also expect `pyinstaller` and everything in
`requirements.txt` to already be installed in the active Python
environment.

## Uninstalling

- **Windows**: Settings → Apps → *ESP32 Multi Flash Manager* → Uninstall
  (or the "Uninstall ESP32 Multi Flash Manager" Start Menu shortcut). This
  removes the app files, shortcuts, and the `.emfm` file association.
- **macOS**: drag `ESP32MultiFlashManager.app` from `/Applications` to the
  Trash. (No separate uninstaller — this is standard macOS app behavior.)
- **Linux**: delete the `.AppImage` file. If you integrated it with
  AppImageLauncher, also remove it from there (right-click the app in your
  launcher → Remove).

## Portable vs. installed updates

`Tools → Check for Updates...` inside the app fetches the latest GitHub
Release and offers a download link, but it needs to know which *kind* of
build it's running as to offer the right asset:

- The **Windows installer** drops `install_marker.txt` next to the exe at
  install time, so a future "Check for Updates" run on that machine
  offers the installer asset (`ESP32MultiFlashManagerSetup-x.y.z.exe`)
  from the newer release, not the raw portable exe.
- Anything else — the raw portable exe, the macOS `.dmg`/`.app`, the
  Linux `.AppImage`, or running straight from source — has no marker
  file, so it's treated as portable and offered the portable asset for
  that platform instead.

## Known limitations, honestly

- **None of these installers are code-signed.** Windows SmartScreen and
  macOS Gatekeeper will both show an "unknown publisher" warning on first
  run — this is expected for an unsigned build, not a bug. Getting rid of
  it requires a paid code-signing certificate (Windows) or an Apple
  Developer account + notarization (macOS), which isn't set up here.
- **The macOS and Linux installers have not been run/tested on real
  hardware or a VM** — see the testing status note above.
