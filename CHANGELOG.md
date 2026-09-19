<!-- APP_VERSION: 0.15.1 -->
# Changelog

All notable changes to ESP32 Multi Flash Manager are documented here,
newest first. This file was introduced in 0.13.0; for the history of
earlier releases (v0.1.0 through v0.12.0), see the repository's
[GitHub Releases](https://github.com/SomangshuDas/esp32-multi-flash-manager/releases)
page or `git log`/`git tag`.

The `<!-- APP_VERSION: X.Y.Z -->` comment at the top of this file (and of
README.md) is machine-checked: `.github/workflows/version_check.yml`
fails a tagged-release build if either marker's version doesn't match
`APP_VERSION` in `app/utilities/constants.py`. Bump both when you bump
that constant.

## [0.15.1] - 2026-09-18

### Fixed
- **Upload status/progress bar stuck on "Connecting"/"Preparing" for the
  whole flash**: esptool 5.4+ (via `esp-pylib` 1.1.5) renders its
  `Writing at 0x...` progress line without the `[...]`-bracketed bar the
  parser required, e.g. `Writing at 0x00001000 ━━━━━━━━━━━     38.2%
  4.88kB/12.80kB [0s]` instead of the older `Writing at 0x00001000 [   ]
  0.0% 0/13104 bytes...`. Every such line fell through to the generic
  "raw" event, so the status badge and per-device progress bar never
  advanced past the pre-upload stage even though esptool was actively
  (and successfully) writing to the device -- the flash itself was
  unaffected, only the UI's visibility into it. `_RE_WRITING_AT_CURRENT`
  in `app/flash_engine/esptool_wrapper.py` now matches the bar contents
  with a non-greedy wildcard instead of requiring literal brackets, so
  it recognizes the bar in either format.

### Internal
- Added `TestParseProgressLineWritingAt` (`tests/flash_engine/
  test_esptool_wrapper.py`) covering the legacy, bracketed-current, and
  unbracketed-current `Writing at...` line formats so a future esptool/
  esp-pylib rendering change is caught here instead of in the field.
- Updated `about-dialog.png` to reflect the new version number.
- APP_VERSION bumped to 0.15.1 in app/utilities/constants.py.

## [0.15.0] - 2026-09-09

### Added
- **Dry-run / pre-flight simulation mode**: `Tools → Validate Bench (Dry
  Run)...` runs the exact same checks Upload would run against every
  device in the current project, without requiring any hardware to
  actually be plugged in. Useful for validating a bench configuration --
  or reviewing a project file someone else built -- before the ports it
  references even exist on this machine. `validate_devices()` gained a
  `dry_run` parameter that skips only the live "is this port currently
  connected" check; every other check (duplicate ports, chip/flash-mode/
  baud validity, firmware file presence, security settings, ...) still
  runs exactly as it would for a real upload.
- **Diff / preview step for Batch Edit and Assign Firmware Set**: both
  now show a "N device(s) will change" before/after table (new
  `ChangePreviewDialog`) after their own dialog is confirmed, listing
  only the devices that would actually change and what changes for each
  -- Apply to proceed, Cancel to make no changes. New
  `DeviceController.preview_field_change()` / `preview_tag_addition()` /
  `preview_firmware_assignment()` compute these diffs read-only.
- **Undo/redo, covering every device-mutating action**: `Edit → Undo`
  (Ctrl+Z) / `Edit → Redo` (Ctrl+Shift+Z) -- `Edit` now sits right after
  `File` in the menu bar, matching the conventional File/Edit/...
  ordering. Every action that changes a device is now one undo step:
  Add Device, single or bulk device removal, Duplicate Device, Batch
  Edit, Assign Firmware Set to Devices, CSV/firmware-bundle import, *and*
  per-device edits made directly in the Device Settings, Firmware, and
  Security panels (rename, port/chip/baud/flash-setting changes, adding/
  removing/reordering firmware entries, security/provisioning settings)
  -- each field-group commit (e.g. one `editingFinished`) is its own undo
  step. Implemented as a bounded stack of whole-device-list snapshots
  (new `app/controllers/undo_stack.py`) rather than field-level diffing,
  deliberately trading a little memory for a much simpler, easier-to-
  verify implementation; per-device panel edits (which mutate their
  `DeviceConfig` object in place rather than going through a
  `DeviceController` method) are captured via a before/after snapshot
  taken around each panel commit (`DeviceController.push_device_edit_undo`,
  `MainWindow._capture_pre_edit_snapshot`/`_push_device_edit_undo`). New
  **Undo History Depth** setting (Settings → Advanced, default 25,
  adjustable 1–200) controls how many steps are kept.
- **Zip + manifest bulk-flashing import**: `Devices → Import Firmware
  Bundle (.zip)...` accepts a single `.zip` containing firmware binaries
  plus a `manifest.csv` (device name/tags/chip type → firmware+address
  mapping) and materializes it into a full device list with firmware
  already assigned, in one step -- see `docs/USER_MANUAL.md` for the
  manifest format. Bounds both the archive's uncompressed size and the
  manifest's row count before extracting/parsing anything, and refuses
  any archive entry whose path would resolve outside the extraction
  folder ("zip slip").

### Changed
- `DeviceController.remove_device()` gained a bulk sibling,
  `remove_devices()`, used by the Devices panel's multi-select Remove so
  that removing several devices at once is a single undo step instead of
  one per device.
- **Recent Projects now dedupes across path-separator style.** Two
  spellings of the same location (`C:/Users/sample.emfm` vs
  `C:\Users\sample.emfm`) previously showed up as two separate Recent
  Projects entries; new `helpers.normalize_path_for_comparison()` is now
  used wherever the app needs to ask "is this the same path as that
  one" (currently: `project_io.add_recent_project`'s dedup check --
  audited for other raw path-equality comparisons elsewhere in the app;
  this was the only one).
- **Settings → General** no longer has its own "Open Logs Folder"
  button -- it duplicated the one already on the **Diagnostics** tab.
- **Project renamed to `esp32-multi-flash-manager`**: the GitHub
  repository slug (and, correspondingly, its GitHub Pages URL) moved
  from `esp32_multi_flash_manager` to the hyphenated
  `esp32-multi-flash-manager`, matching the naming already used for the
  Linux packaging artifacts (desktop entry, MIME XML, AppStream
  metadata). Every in-repo reference -- README/CONTRIBUTING/SECURITY
  links, badge URLs, clone instructions, the `GITHUB_REPO` constant,
  and the Windows installer's URLs -- has been updated to match. The
  application's display name (`APP_NAME`, "ESP32 Multi Flash Manager")
  is unchanged.
- Refreshed all README and User Manual screenshots to reflect the
  current UI.

### Internal
- New `UndoStack`/`UndoEntry` (`app/controllers/undo_stack.py`) and
  `zip_manifest_import` (`app/project_manager/zip_manifest_import.py`)
  modules, each covered by dedicated unit tests; `DeviceController`'s
  bulk-mutation and single-device methods, the new
  `push_device_edit_undo()`, `MainWindow`'s Batch Edit / Assign Firmware
  Set handlers, and the per-device panel undo-tracking wiring all gained
  test coverage.
- APP_VERSION bumped to 0.15.0 in app/utilities/constants.py.

## [0.14.0] - 2026-09-09

### Added
- **Batch/multi-device provisioning**: `Tools → Provision Devices
  (Batch)...` burns eFuses (Flash Encryption / Secure Boot) across every
  selected device in one pass instead of requiring the single-device
  Provision dialog to be opened and confirmed once per device. Runs
  pre-flight validation on every candidate, skips (with a reason) any
  device that isn't configured for provisioning or fails validation, and
  gates the whole batch behind one explicit irreversible-burn
  confirmation. New `ProvisionController` applies the same
  parallel-cap/queue design as parallel flashing.
- **Max Parallel Provisions** setting (Settings → General → Provisioning,
  default 8, adjustable 1–32, matching **Max Parallel Flashes** so a
  bench sized for parallel flashing doesn't unexpectedly bottleneck on
  batch provisioning throughput): caps how many devices
  `ProvisionController` burns eFuses on concurrently; devices beyond the
  cap queue and launch automatically as running ones finish. The
  irreversible-burn confirmation gate — not the concurrency cap — is
  what actually limits blast radius for eFuse burning.
- **Provision Stall Timeout** setting (Settings → General → Provisioning,
  default 60s, adjustable 10–600s): now user-configurable, mirroring the
  existing Flash Stall Timeout setting. Previously this value was a
  hardcoded constant with no way to tune it from the UI.
- **CSV bulk device import** (`Devices → Import Devices from CSV...`,
  `app/project_manager/csv_import.py`): populate the device list in one
  step from a spreadsheet. Only a `name` column is required;
  `com_port`, `chip_type`, `baud_rate`, and semicolon-separated `tags`
  are recognized if present. A row with a missing name or invalid
  baud rate is skipped and reported after import, rather than aborting
  the whole file.
- **Default Device Profile** setting (Settings → General): optionally
  applies a saved Firmware Profile's chip/flash settings and firmware
  list to every newly-added device (via "Add Device" or CSV import),
  instead of the app's built-in defaults.
- **Diagnostics bundle export** (`Help → Export Diagnostics Bundle...`,
  also in Settings → Diagnostics, `app/utilities/diagnostics.py`): saves
  a single `.zip` containing all current log files plus app/OS/Python/
  `esptool` version information, for attaching to a bug report.
- **Optional structured JSON logging** (Settings → Diagnostics → "Enable
  structured JSON logging"), off by default: mirrors every log record as
  one JSON object per line to a new `events.jsonl` file, alongside
  (never instead of) the four existing rotating text logs, for anyone
  piping logs into a log-aggregation tool.
- **Opt-in, local-only anonymous usage/crash telemetry** (Settings →
  Privacy, `app/utilities/telemetry.py`), off by default. Recorded
  events use a fixed, reviewed event set and a random per-install
  client ID; never include device serials, COM port names, firmware
  file names/paths, or project names. This build stores events locally
  only — nothing is transmitted over the network regardless of the
  setting. See `docs/PRIVACY.md` for the full disclosure and
  `ROADMAP.md` for the (deliberately deferred) collection-backend work.
- **New Settings tabs**: **Advanced** (Port Scan Interval, Live Log Max
  Lines, Project Lock Stale After — previously hardcoded constants, now
  user-configurable with the same defaults as before), **Diagnostics**,
  and **Privacy** (see above).
- **`.emfm` project-file input-validation hardening**
  (`app/project_manager/project_io.py`): a file-size cap (25 MiB),
  checked before parsing, plus post-parse caps on device count (2000)
  and firmware entries per device (200), so a corrupted or hostile
  project file fails fast with a clear message instead of risking a UI
  hang or excessive memory use. See new `docs/THREAT_MODEL.md` for the
  full writeup, including why firmware file-path traversal is
  deliberately *not* restricted.
- `docs/THREAT_MODEL.md`, `docs/FAQ.md`, and `ROADMAP.md` (design
  sketches for dry-run validation, a Batch Edit/Assign Firmware Set diff
  preview, undo/redo, an in-app firmware-repository browser, a
  zip+manifest bulk-flashing workflow, and a real telemetry collection
  backend — all deliberately scoped out of this release, see that file
  for why).
- An architecture diagram and a concurrency/scale-limits table in
  `docs/DEVELOPER_DOCUMENTATION.md` §2a/§2b.
- Explicit `setAccessibleName()` calls on the new Settings controls
  above, plus a status-update in `docs/ACCESSIBILITY.md` on the current
  audit scope.

### Changed
- `docs/PRIVACY.md` rewritten to describe the new opt-in telemetry
  setting in full (previously stated flatly that no telemetry code
  existed at all).

### Fixed
- The single-instance lock file in the app-data folder is now actually
  hidden on Windows (previously named `app.lock` with no leading dot and
  never passed through the app's hide-file helper, so it sat visibly in
  the app-data folder for the entire time the app was running). Renamed
  to `.app.lock` and hidden via the same mechanism every other internal
  sidecar file already uses.
- Fixed a rare but real CI crash (`Fatal Python error: Aborted`, process
  core-dumped) around `FlashController`/`ProvisionController` finishing a
  worker: `finished_flash`/`finished_provision` is emitted from inside
  the `FlashWorker`/`ProvisionWorker` `QThread`'s `run()` a few
  instructions *before* the underlying OS thread actually exits, so the
  queued cross-thread slot that receives it could start running on the
  main thread while that thread was still finishing its teardown. With
  nothing else keeping the worker alive past that point, the
  still-finishing `QThread` could be raced by whatever ran next — the
  same class of `os.environ` race already fixed once for stall-timeout
  reads (see `FlashWorker.__init__`'s docstring), just from the
  "leftover thread" angle instead of the "read during `run()`" angle.
  Both controllers now call `worker.wait()` before continuing once a
  worker reports it's finished, closing the window by construction
  instead of relying on timing. Bounded to 5s with a logged warning (not
  a raised error) if that's ever exceeded, so a slow teardown can never
  hang the UI.

### Internal
- 57 new automated tests across the settings getters, structured JSON
  logging, diagnostics bundle export, telemetry recording, `.emfm`
  input-validation hardening, CSV import, and default-device-profile
  application — see `tests/utilities/`, `tests/project_manager/`, and
  `tests/controllers/test_device_controller.py`.
- APP_VERSION bumped to 0.14.0 in app/utilities/constants.py.

## [0.13.0] - 2026-09-07

### Added
- **Max Parallel Flashes** setting (Settings → General, default 8,
  adjustable 1–64): caps how many devices `FlashController.start_batch()`
  runs concurrently. Devices beyond the cap show a new *Queued* status
  and launch automatically as running devices finish, instead of every
  device in a batch firing its own subprocess at once.
- **Cancel Merge** button and background-thread execution for Merge
  Bins: a large or slow merge no longer freezes the application.
- `.github/workflows/version_check.yml`: fails a tagged-release build if
  `APP_VERSION` doesn't match the version markers in README.md and this
  file.
- This `CHANGELOG.md` file itself.
- `docs/PRIVACY.md` — a one-paragraph statement confirming no telemetry
  currently leaves the device.
- `docs/ACCESSIBILITY.md` — current screen-reader/accessibility
  conformance and known gaps.
- `docs/MAINTENANCE_POLICY.md` — a bus-factor/succession policy for the
  project's single-maintainer status.
- A `.emfm`/`.efmproj` deprecation notice, shown in-app and in
  `docs/USER_MANUAL.md`, stating that legacy `.efmproj` compatibility may
  be discontinued in a future release.
- A forced-save-before-risky-operation mechanism for legacy `.efmproj`
  projects, so a project opened from that format is saved back to disk
  before any operation that could otherwise lose data or leave the file
  out of sync (e.g. before closing, before switching projects).

### Changed
- `DeviceController.apply_to_all` / `apply_to_selected` /
  `apply_firmware_to_devices` now skip any device
  `FlashController.is_busy()` reports as mid-flash, instead of mutating
  it regardless. Fixes a traceability bug where renaming a device or
  reassigning its port mid-flash via Batch Edit could make the resulting
  history entry reflect the new values rather than what was actually
  flashed.
- README.md, `docs/DEVELOPER_DOCUMENTATION.md`, and
  `docs/USER_MANUAL.md` no longer describe parallel flashing as
  "unlimited" — updated to describe the new configurable cap and queue.

### Fixed
- `bin_merge`-driven merges no longer block the GUI thread for up to
  `MERGE_TIMEOUT_SECONDS` (180s) with no way to cancel.

### Internal
- Added `MergeWorker` (`app/workers/merge_worker.py`), reusing
  `FlashProcess` the same way `FlashWorker` does, so Merge Bins gets
  streamed output, cancellation, and a timeout without duplicating the
  esptool-subprocess-handling logic.
- Added test coverage for the parallel-flash cap/queue (controller-level
  and mocked-serial end-to-end), the `DeviceController` busy-device
  guard, and `MergeWorker` (success, failure, cancel, and timeout paths).
- APP_VERSION bumped to 0.13.0 in app/utilities/constants.py.
