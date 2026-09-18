"""
constants.py
============
Central location for every "magic value" used across the application.
Keeping these in one module avoids scattering literals across the codebase
and makes future firmware/chip support trivial to extend.
"""

from __future__ import annotations

APP_NAME = "ESP32 Multi Flash Manager"
APP_VERSION = "0.15.0"
ORG_NAME = "Somangshu Das"

# --------------------------------------------------------------------------
# Chip / flashing parameter choices (mirrors what esptool.py itself accepts)
# --------------------------------------------------------------------------
# This list is now only a LAST-RESORT FALLBACK. At startup the app queries
# the installed `esptool` package itself for the chips it actually supports
# (see app/utilities/chip_detect.py) so newly-released chip targets show up
# automatically without a code change here. This constant is only used if
# that dynamic detection fails for some reason (esptool missing/broken).
SUPPORTED_CHIPS = [
    "auto",
    "esp32",
    "esp32s2",
    "esp32s3",
    "esp32c3",
    "esp32c6",
    "esp32h2",
    "esp8266",
]

BAUD_RATES = [
    9600, 19200, 38400, 57600, 74880, 115200, 230400,
    460800, 512000, 921600, 1500000, 2000000,
]

FLASH_MODES = ["keep", "qio", "qout", "dio", "dout"]
FLASH_FREQUENCIES = ["keep", "40m", "26m", "20m", "80m"]
FLASH_SIZES = [
    "keep", "1MB", "2MB", "2MB-c1", "4MB", "4MB-c1",
    "8MB", "16MB", "32MB",
]
COMPRESSION_MODES = ["default (compressed)", "uncompressed (-u)"]

DEFAULT_BAUD = 115200
DEFAULT_FLASH_MODE = "keep"
DEFAULT_FLASH_FREQ = "keep"
DEFAULT_FLASH_SIZE = "keep"
DEFAULT_CHIP = "auto"

# --------------------------------------------------------------------------
# Theme (app/ui/theme.py)
# --------------------------------------------------------------------------
# "system" is not itself a stylesheet -- it means "resolve to dark/light by
# asking the OS", re-evaluated live whenever the OS scheme changes (see
# MainWindow._apply_theme / theme.resolve_theme). It is the default so a
# fresh install matches the user's OS preference from the very first launch
# instead of always opening in dark mode.
THEME_SYSTEM = "system"
THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_OPTIONS = [THEME_SYSTEM, THEME_DARK, THEME_LIGHT]
THEME_OPTION_LABELS = {
    THEME_SYSTEM: "System Default",
    THEME_DARK: "Dark",
    THEME_LIGHT: "Light",
}
DEFAULT_THEME = THEME_SYSTEM
SETTINGS_KEY_THEME = "theme"

# --------------------------------------------------------------------------
# Known firmware image name -> default flash address mapping.
# Used by the auto-detection engine when a firmware folder is imported.
# Addresses follow Espressif's standard ESP-IDF partition layout.
# --------------------------------------------------------------------------
KNOWN_FIRMWARE_ADDRESSES: dict[str, str] = {
    "bootloader.bin": "0x1000",
    "partition-table.bin": "0x8000",
    "partitions.bin": "0x8000",
    "ota_data_initial.bin": "0xd000",
    "boot_app0.bin": "0xe000",
    "firmware.bin": "0x10000",
    "app.bin": "0x10000",
}

# --------------------------------------------------------------------------
# Device status enum values (kept as plain strings for JSON-friendliness)
# --------------------------------------------------------------------------
STATUS_WAITING = "Waiting"
# A device sitting behind the parallel-flash cap (see
# MAX_PARALLEL_FLASHES / FlashController._queue below): eligible and about
# to run, but not yet handed a worker/subprocess.
STATUS_QUEUED = "Queued"
STATUS_PREPARING = "Preparing"
STATUS_CONNECTING = "Connecting"
STATUS_ERASING = "Erasing"
STATUS_UPLOADING = "Uploading"
STATUS_VERIFYING = "Verifying"
STATUS_COMPLETED = "Completed"
STATUS_CANCELLED = "Cancelled"
STATUS_FAILED = "Failed"

STATUS_COLORS = {
    STATUS_WAITING: "#8a8f98",
    STATUS_QUEUED: "#7048e8",
    STATUS_PREPARING: "#5b8def",
    STATUS_CONNECTING: "#5b8def",
    STATUS_ERASING: "#e0a300",
    STATUS_UPLOADING: "#2f9e44",
    STATUS_VERIFYING: "#1c7ed6",
    STATUS_COMPLETED: "#2f9e44",
    STATUS_CANCELLED: "#868e96",
    STATUS_FAILED: "#e03131",
}

ACTIVE_STATUSES = {
    STATUS_PREPARING, STATUS_CONNECTING, STATUS_ERASING,
    STATUS_UPLOADING, STATUS_VERIFYING,
}

# --------------------------------------------------------------------------
# How long FlashWorker waits for a new line of esptool output before
# deciding the subprocess is hung rather than merely slow (e.g. a device
# that disconnects mid-write, leaving the OS serial driver blocked in an
# uninterruptible I/O wait that esptool itself never times out on). Past
# this many seconds of total silence, the worker kills the subprocess and
# fails the device instead of leaving its status stuck on "Uploading"
# forever (which also permanently blocked that port's Serial Monitor).
# --------------------------------------------------------------------------
FLASH_STALL_TIMEOUT_SECONDS = 45.0

# settings.json key letting the user tune FLASH_STALL_TIMEOUT_SECONDS from
# Settings -> General without editing source code / rebuilding (see
# app/ui/settings_dialog.py). The constant above remains the documented
# factory default and the fallback used by app.utilities.app_settings.
# get_flash_stall_timeout_seconds() whenever nothing has been customized.
SETTINGS_KEY_FLASH_STALL_TIMEOUT_SECONDS = "flash_stall_timeout_seconds"
FLASH_STALL_TIMEOUT_MIN_SECONDS = 10.0
FLASH_STALL_TIMEOUT_MAX_SECONDS = 600.0

# --------------------------------------------------------------------------
# Reliability: cap on how many devices FlashController.start_batch() will
# run concurrently. Previously unbounded -- a very large batch (dozens or
# more devices) launched one QThread + one esptool subprocess per device
# all at once, risking OS thread, file-descriptor, or USB-bandwidth
# exhaustion. Devices beyond this cap are queued (STATUS_QUEUED) and
# launched one-for-one as running workers finish. Configurable from
# Settings -> General; see app.utilities.app_settings.get_max_parallel_flashes.
# --------------------------------------------------------------------------
MAX_PARALLEL_FLASHES = 8
SETTINGS_KEY_MAX_PARALLEL_FLASHES = "max_parallel_flashes"
MAX_PARALLEL_FLASHES_MIN = 1
MAX_PARALLEL_FLASHES_MAX = 64

# Same idea as FLASH_STALL_TIMEOUT_SECONDS above but for the read-only
# eFuse-burning/provisioning subprocess (app/workers/security_worker.py) --
# kept as its own named constant (rather than reusing
# FLASH_STALL_TIMEOUT_SECONDS) because burning/reading eFuses is a
# different operation with a different expected duration, even though the
# current default happens to be a round number too. Previously this was a
# bare literal (60.0) hardcoded directly in security_worker.py.
PROVISION_STALL_TIMEOUT_SECONDS = 60.0

# settings.json key letting the user tune PROVISION_STALL_TIMEOUT_SECONDS
# from Settings -> Provisioning, mirroring
# SETTINGS_KEY_FLASH_STALL_TIMEOUT_SECONDS above -- previously this value
# had no user-facing override at all.
SETTINGS_KEY_PROVISION_STALL_TIMEOUT_SECONDS = "provision_stall_timeout_seconds"
PROVISION_STALL_TIMEOUT_MIN_SECONDS = 10.0
PROVISION_STALL_TIMEOUT_MAX_SECONDS = 600.0

# --------------------------------------------------------------------------
# Batch provisioning (eFuse burning across multiple devices at once -- see
# app/controllers/provision_controller.py). Mirrors MAX_PARALLEL_FLASHES:
# provisioning previously only ever ran one device at a time (one
# ProvisionDialog per device, opened manually), so a production batch with
# security enabled meant repeating the whole confirm-and-burn flow by hand
# for every device. Devices beyond this cap are queued (STATUS_QUEUED) and
# launched one-for-one as running provisioning workers finish, for the same
# OS-thread / USB-bandwidth reasons as parallel flashing. Aligned with
# MAX_PARALLEL_FLASHES's default (both 8) so a bench sized for parallel
# flashing doesn't unexpectedly bottleneck on provisioning throughput --
# the per-batch irreversible-burn confirmation gate (PROVISION_CONFIRM_PHRASE)
# is what actually limits blast radius, not a lower concurrency cap.
# --------------------------------------------------------------------------
MAX_PARALLEL_PROVISIONS = 8
SETTINGS_KEY_MAX_PARALLEL_PROVISIONS = "max_parallel_provisions"
MAX_PARALLEL_PROVISIONS_MIN = 1
MAX_PARALLEL_PROVISIONS_MAX = 32

# --------------------------------------------------------------------------
# File / project extensions
# --------------------------------------------------------------------------
PROJECT_FILE_EXTENSION = "emfm"
PROJECT_FILE_FILTER = "ESP32 Multi Flash Manager Project (*.emfm)"
# Pre-rename extension. Files saved by releases before the .emfm switch
# can still be opened (see ProjectController.open_project's legacy
# handling) so nobody's old projects are stranded, but the Save dialog
# filter above only ever offers/writes the current .emfm extension --
# opening a .efmproj file always forces a Save As, never a silent
# overwrite in the old format.
#
# Legacy (.efmproj) compatibility notice: this fallback-read support may be
# discontinued in a future major release. Projects opened in this format
# are never silently re-saved in it (see ProjectController.open_project) --
# Save/Save As always writes the current .emfm format instead.
PROJECT_FILE_EXTENSION_LEGACY = "efmproj"
PROJECT_FILE_FILTER_OPEN = "ESP32 Multi Flash Manager Project (*.emfm *.efmproj)"
FIRMWARE_FILE_FILTER = "Firmware Binary (*.bin)"
FIRMWARE_PROFILE_FILE_FILTER = "Firmware Profile (*.json)"

# --------------------------------------------------------------------------
# Crash-protection auto-save "recovery slot" for brand-new, never-saved
# projects (app/controllers/project_controller.py,
# app/project_manager/project_io.py). A project that has never been saved
# to disk has no real destination for auto-save to write to, but leaving
# it completely unprotected until the user's first manual Save means a
# crash/power-loss before that point loses everything -- this recovery
# slot exists purely so periodic auto-save has *somewhere* safe to put a
# copy in that window. It is never treated as the project's real save
# location: saving here does not set current_file_path or clear the
# dirty flag, and the file is deleted as soon as either a real Save
# succeeds or the recovered project is intentionally discarded.
# --------------------------------------------------------------------------
AUTOSAVE_RECOVERY_DIRNAME = "autosave_recovery"
AUTOSAVE_RECOVERY_FILENAME = "unsaved_project_recovery.emfm"

# --------------------------------------------------------------------------
# Advisory cross-process/cross-machine lock sidecar for .emfm project files
# (app/project_manager/project_io.py). Guards against two people/instances
# editing the same project on a shared network drive and silently
# clobbering each other's work -- see project_io.acquire_project_lock().
# --------------------------------------------------------------------------
PROJECT_LOCK_FILE_SUFFIX = ".lock"
PROJECT_LOCK_STALE_SECONDS = 24 * 60 * 60  # a lock this old is assumed abandoned

# --------------------------------------------------------------------------
# Internal flag used to re-invoke this same executable as an esptool runner.
#
# esptool is launched as a subprocess via `sys.executable`. When running
# from source that's a real Python interpreter, so `-m esptool` works. But
# in a PyInstaller --onefile build, `sys.executable` IS this app's own .exe
# -- there is no separate Python on the target machine. main.py intercepts
# this flag at startup: if present, it runs esptool's CLI directly (esptool
# is bundled in via `--collect-all esptool`) and exits immediately instead
# of opening the GUI. Without this, a frozen build's "Upload" would instead
# relaunch a second blank instance of the app and never actually flash.
# --------------------------------------------------------------------------
ESPTOOL_REEXEC_FLAG = "--_run-esptool"

# Same fast-path re-exec trick as ESPTOOL_REEXEC_FLAG above, but for the two
# sibling console tools that ship inside the `esptool` PyPI distribution:
# `espsecure` (key generation / image signing for flash encryption + secure
# boot) and `espefuse` (burning/reading eFuses). Security provisioning is
# built entirely on these two official tools -- this app never implements
# any cryptographic or eFuse-protocol logic itself (see
# app/flash_engine/security_manager.py). See main.py for the interception.
ESPSECURE_REEXEC_FLAG = "--_run-espsecure"
ESPEFUSE_REEXEC_FLAG = "--_run-espefuse"

# --------------------------------------------------------------------------
# Misc UI constants
# --------------------------------------------------------------------------
MAX_RECENT_PROJECTS = 10
PORT_SCAN_INTERVAL_MS = 2000
LIVE_LOG_MAX_LINES = 10000

# --------------------------------------------------------------------------
# Advanced settings (Settings -> Advanced). These were previously bare
# module-level constants with no user-facing override -- exposed here so a
# bench with unusual hardware (e.g. a USB hub that enumerates slowly, or a
# very long-running batch that wants a smaller live-log footprint) can tune
# them without editing source and rebuilding. Each getter in app_settings.py
# falls back to the literal below and clamps to its MIN/MAX pair, mirroring
# the existing get_flash_stall_timeout_seconds()/get_max_parallel_flashes()
# pattern.
# --------------------------------------------------------------------------
SETTINGS_KEY_PORT_SCAN_INTERVAL_MS = "port_scan_interval_ms"
PORT_SCAN_INTERVAL_MS_MIN = 250
PORT_SCAN_INTERVAL_MS_MAX = 30000

SETTINGS_KEY_LIVE_LOG_MAX_LINES = "live_log_max_lines"
LIVE_LOG_MAX_LINES_MIN = 500
LIVE_LOG_MAX_LINES_MAX = 200000

SETTINGS_KEY_PROJECT_LOCK_STALE_SECONDS = "project_lock_stale_seconds"
PROJECT_LOCK_STALE_SECONDS_MIN = 5 * 60
PROJECT_LOCK_STALE_SECONDS_MAX = 30 * 24 * 60 * 60

# --------------------------------------------------------------------------
# Structured JSON logging (app/logging_setup/logger.py, Settings -> Diagnostics)
# --------------------------------------------------------------------------
# Off by default: the four existing rotating text logs remain the primary,
# always-on format. When enabled, a fifth rotating file (events.jsonl) mirrors
# every log record as one JSON object per line, alongside (never instead of)
# the text logs, for anyone piping logs into a log-aggregation/SIEM tool that
# expects structured records rather than parsing the human-readable format.
SETTINGS_KEY_JSON_LOGGING_ENABLED = "json_logging_enabled"
DEFAULT_JSON_LOGGING_ENABLED = False
JSON_LOG_FILENAME = "events.jsonl"

# --------------------------------------------------------------------------
# Opt-in anonymous usage/crash telemetry (app/utilities/telemetry.py,
# Settings -> Privacy)
# --------------------------------------------------------------------------
# Off by default, per-install anonymous random id (no username/hostname/
# device serials/firmware paths -- see telemetry.py's module docstring for
# exactly what is and is not recorded). Recorded events are written locally
# to telemetry_events.jsonl under the app-data folder; nothing is
# transmitted over the network by this build (see telemetry.py docstring
# and DEVELOPER_DOCUMENTATION.md for the documented extension point a
# future release would use to actually upload them to a collection
# endpoint).
SETTINGS_KEY_TELEMETRY_ENABLED = "telemetry_enabled"
DEFAULT_ENABLED_TELEMETRY = False
SETTINGS_KEY_TELEMETRY_CLIENT_ID = "telemetry_client_id"
TELEMETRY_LOG_FILENAME = "telemetry_events.jsonl"

# --------------------------------------------------------------------------
# Default Device Profile (app/controllers/device_controller.py,
# Settings -> General)
# --------------------------------------------------------------------------
# Name of a saved FirmwareProfile (app/firmware_manager/profiles.py) that is
# automatically applied to every newly-added device, so a bench that always
# flashes the same handful of chip/firmware combinations doesn't need to
# re-pick settings by hand on every "Add Device". Blank (the default) means
# "no default -- new devices keep the app's ordinary built-in defaults",
# preserving previous behavior for anyone who hasn't set one.
SETTINGS_KEY_DEFAULT_DEVICE_PROFILE = "default_device_profile"
DEFAULT_DEVICE_PROFILE_NONE = ""

# --------------------------------------------------------------------------
# Update checking (GitHub Releases)
# --------------------------------------------------------------------------
GITHUB_REPO = "SomangshuDas/esp32-multi-flash-manager"

# Help -> User Manual opens this file straight from GitHub so it's always
# in sync with the branch, rather than bundling (and going stale against)
# a local copy inside the packaged app.
USER_MANUAL_URL = f"https://github.com/{GITHUB_REPO}/blob/main/docs/USER_MANUAL.md"

# Dropped next to the executable by an OS installer (Windows Setup.exe) so
# a frozen build can tell "installed" apart from "portable" at runtime.
# Its presence is what lets update_checker.py offer an installer asset to
# installed users and a portable asset to portable users instead of always
# guessing. See update_checker.py's module docstring for the full picture.
INSTALL_MARKER_FILENAME = "install_marker.txt"

# --------------------------------------------------------------------------
# Bin Merge (app/firmware_manager/bin_merge.py, app/ui/merge_bin_dialog.py)
# --------------------------------------------------------------------------
# Merging turns a device's separate firmware images (bootloader, partition
# table, app, ...) into one flashable image via `esptool merge-bin`.
DEFAULT_MERGED_BIN_FILENAME = "merged-firmware.bin"

# settings.json keys for the app-wide defaults configured in Settings...
SETTINGS_KEY_MERGE_DEFAULT_FILENAME = "merge_default_filename"
SETTINGS_KEY_MERGE_DEFAULT_LOCATION = "merge_default_location"
SETTINGS_KEY_MERGE_POST_ACTION = "merge_post_action"

# ...and what a device's merge output defaults to when Settings hasn't been
# customized: same file name as the fallback above, and the SAME FOLDER AS
# firmware.bin (i.e. blank -- resolved at merge time from the device's own
# firmware list, never a fixed path baked in here).
DEFAULT_MERGE_OUTPUT_LOCATION = ""  # blank == "same folder as firmware.bin"

# What happens to the source BIN rows in Firmware Settings after a
# successful merge. The dialog always lets the user pick one of these for
# that specific merge; MERGE_POST_ACTION_DEFAULT is only what's pre-selected
# when the dialog opens (itself overridable in Settings).
MERGE_POST_ACTION_ADD_DESELECT = "add_deselect"  # add merged bin, de-select (but keep) the source bins
MERGE_POST_ACTION_ADD_REMOVE = "add_remove"      # add merged bin, remove the source bins entirely
MERGE_POST_ACTION_ADD_ONLY = "add_only"          # add merged bin, leave source bins untouched
MERGE_POST_ACTION_NONE = "none"                  # just write the file, don't touch Firmware Settings

MERGE_POST_ACTIONS = [
    MERGE_POST_ACTION_ADD_DESELECT,
    MERGE_POST_ACTION_ADD_REMOVE,
    MERGE_POST_ACTION_ADD_ONLY,
    MERGE_POST_ACTION_NONE,
]
MERGE_POST_ACTION_LABELS: dict[str, str] = {
    MERGE_POST_ACTION_ADD_DESELECT: "Add merged bin, de-select source bins",
    MERGE_POST_ACTION_ADD_REMOVE: "Add merged bin, remove source bins",
    MERGE_POST_ACTION_ADD_ONLY: "Add merged bin only (leave source bins as-is)",
    MERGE_POST_ACTION_NONE: "Do nothing to Firmware Settings",
}
DEFAULT_MERGE_POST_ACTION = MERGE_POST_ACTION_ADD_DESELECT

# --------------------------------------------------------------------------
# Interface Lock (app/ui/main_window.py)
# --------------------------------------------------------------------------
# Two independent lock modes, grouped under the Tools -> Lock Interface
# submenu, both gated behind the same unlock-key hash
# (SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH) set via Tools -> Set Interface
# Lock Key...:
#
#   Settings Lock -- the window stays fully usable (uploads, Serial
#   Monitor, viewing logs, adding/duplicating devices all keep working)
#   but editing anything that changes what gets flashed and to where --
#   ports, chip/flash settings, the firmware list, Batch Edit, Assign
#   Firmware Set, Firmware Profiles, and deleting devices -- is disabled.
#   Meant for a bench that's handed to less-trusted operators who should
#   only be able to run the flashing job already configured for them, not
#   reconfigure it.
#
#   Full Lock -- freezes the ENTIRE window behind an opaque overlay (see
#   app/ui/lock_overlay.py); nothing is reachable, including Upload/
#   Cancel, until the same key is re-entered. Meant for walking away from
#   a running batch on a bench PC.
ASSIGN_FIRMWARE_SET_SHORTCUT = "Ctrl+Shift+A"
INTERFACE_LOCK_SHORTCUT = "Ctrl+Shift+L"
FACTORY_MODE_LOCK_SHORTCUT = "Ctrl+Shift+F"

SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH = "interface_lock_key_hash"

# --------------------------------------------------------------------------
# User-customisable keyboard shortcuts (app/utilities/shortcuts.py)
# --------------------------------------------------------------------------
# Every entry the user is allowed to remap, keyed by a stable action id, with
# its default key sequence and a human-readable label for the Shortcuts
# dialog. Anything NOT listed here (e.g. a toolbar-only duplicate action)
# keeps a fixed, non-customisable shortcut.
DEFAULT_SHORTCUTS: dict[str, str] = {
    "new_project": "Ctrl+N",
    "open_project": "Ctrl+O",
    "save_project": "Ctrl+S",
    "save_project_as": "Ctrl+Shift+S",
    "exit_app": "Ctrl+Q",
    "add_device": "Ctrl+D",
    "batch_edit": "Ctrl+B",
    "assign_firmware_set": ASSIGN_FIRMWARE_SET_SHORTCUT,
    "upload_selected": "F5",
    "upload_all": "Ctrl+F5",
    "cancel_all": "Esc",
    "toggle_theme": "Ctrl+T",
    "lock_interface": INTERFACE_LOCK_SHORTCUT,
    "factory_mode_lock": FACTORY_MODE_LOCK_SHORTCUT,
    "open_serial_monitor": "Ctrl+M",
}

SHORTCUT_LABELS: dict[str, str] = {
    "new_project": "New Project",
    "open_project": "Open Project...",
    "save_project": "Save Project",
    "save_project_as": "Save Project As...",
    "exit_app": "Exit",
    "add_device": "Add Device",
    "batch_edit": "Batch Edit...",
    "assign_firmware_set": "Assign Firmware Set to Devices...",
    "upload_selected": "Upload Selected",
    "upload_all": "Upload All",
    "cancel_all": "Cancel All",
    "toggle_theme": "Toggle Dark/Light Theme",
    "lock_interface": "Full Lock",
    "factory_mode_lock": "Settings Lock",
    "open_serial_monitor": "Open Serial Monitor...",
}

SETTINGS_KEY_CUSTOM_SHORTCUTS = "custom_shortcuts"

# --------------------------------------------------------------------------
# Serial Monitor (app/ui/serial_monitor.py)
# --------------------------------------------------------------------------
DEFAULT_SERIAL_MONITOR_BAUD = 115200
SERIAL_MONITOR_LINE_ENDINGS = ["None", "\\n (LF)", "\\r\\n (CRLF)", "\\r (CR)"]

# --------------------------------------------------------------------------
# Flash Encryption / Secure Boot provisioning
# (app/flash_engine/security_manager.py, app/ui/security_settings_widget.py)
# --------------------------------------------------------------------------
# Everything here is a thin passthrough to `espsecure`/`espefuse` (both part
# of the official `esptool` PyPI package) -- no cryptographic or eFuse
# protocol logic lives in this app. See security_manager.py's module
# docstring for the full command mapping.

KEY_SOURCE_GENERATE = "generate"
KEY_SOURCE_EXISTING = "existing"
KEY_SOURCE_OPTIONS = [KEY_SOURCE_GENERATE, KEY_SOURCE_EXISTING]
KEY_SOURCE_LABELS = {
    KEY_SOURCE_GENERATE: "Generate a new key",
    KEY_SOURCE_EXISTING: "Use an existing key file",
}
DEFAULT_KEY_SOURCE = KEY_SOURCE_GENERATE

SECURE_BOOT_VERSIONS = ["1", "2"]
DEFAULT_SECURE_BOOT_VERSION = "2"
SECURE_BOOT_SCHEMES = ["rsa3072", "ecdsa192", "ecdsa256", "ecdsa384"]
DEFAULT_SECURE_BOOT_SCHEME = "rsa3072"

# Chips using the legacy (pre-"unified eFuse table") espefuse command shape,
# where `burn-key <BLOCK> <KEYFILE>` takes a fixed purpose name baked into
# the block itself (flash_encryption / secure_boot_v1 / secure_boot_v2)
# rather than a separate --keypurpose argument. Every other chip esptool
# supports uses the newer BLOCK_KEYn + explicit key-purpose scheme. Kept as
# a simple set here (not queried dynamically like SUPPORTED_CHIPS) because
# espefuse itself -- not esptool -- draws this line, and it has been stable
# across every 5.x release; SecurityCommandBuilder falls back to the
# unified-scheme shape for any chip not listed here, which is also correct
# for brand-new chip targets a newer esptool/espefuse adds.
LEGACY_EFUSE_CHIPS = {"esp32"}

# espefuse burn-key purposes for chips on the unified eFuse table scheme.
UNIFIED_KEY_PURPOSE_FLASH_ENCRYPTION = "XTS_AES_256_KEY"
UNIFIED_KEY_PURPOSE_SECURE_BOOT_V2 = "SECURE_BOOT_DIGEST0"
# espefuse block names, legacy scheme (ESP32 only).
LEGACY_BLOCK_FLASH_ENCRYPTION = "flash_encryption"
LEGACY_BLOCK_SECURE_BOOT_V1 = "secure_boot_v1"
LEGACY_BLOCK_SECURE_BOOT_V2 = "secure_boot_v2"
# Default unified-scheme key block. Devices that already used BLOCK_KEY0 for
# something else need a different block -- exposed as an editable field, not
# hardcoded further than this default.
DEFAULT_UNIFIED_KEY_BLOCK = "BLOCK_KEY0"

FLASH_ENCRYPTION_MODE_DEVELOPMENT = "development"
FLASH_ENCRYPTION_MODE_RELEASE = "release"
FLASH_ENCRYPTION_MODES = [FLASH_ENCRYPTION_MODE_DEVELOPMENT, FLASH_ENCRYPTION_MODE_RELEASE]
FLASH_ENCRYPTION_MODE_LABELS = {
    FLASH_ENCRYPTION_MODE_DEVELOPMENT: "Development (re-flashing plaintext images stays possible)",
    FLASH_ENCRYPTION_MODE_RELEASE: "Release (locks down re-flashing -- irreversible)",
}
DEFAULT_FLASH_ENCRYPTION_MODE = FLASH_ENCRYPTION_MODE_DEVELOPMENT

# Typed confirmation phrase required (in addition to a checkbox) before any
# eFuse-burning operation is allowed to run, since burning eFuses on real
# hardware is a one-way, irreversible operation -- see
# app/ui/provision_confirm_dialog.py.
PROVISION_CONFIRM_PHRASE = "BURN EFUSES"

STATUS_GENERATING_KEY = "Generating Key"
STATUS_SIGNING = "Signing"
STATUS_BURNING = "Burning eFuses"
STATUS_READING = "Reading"

STATUS_COLORS.update({
    STATUS_GENERATING_KEY: "#5b8def",
    STATUS_SIGNING: "#5b8def",
    STATUS_BURNING: "#e03131",
    STATUS_READING: "#5b8def",
})

# settings.json keys for Read Flash / eFuse / Chip Info output defaults --
# mirrors SETTINGS_KEY_MERGE_DEFAULT_LOCATION's "blank == ask every time /
# same folder as last used" pattern rather than a fixed baked-in path.
SETTINGS_KEY_READ_DEFAULT_LOCATION = "read_default_location"

# --------------------------------------------------------------------------
# Read Flash / Read eFuse / Chip Info (app/ui/read_device_dialog.py)
# --------------------------------------------------------------------------
READ_MODE_CHIP_INFO = "chip_info"
READ_MODE_FLASH_ID = "flash_id"
READ_MODE_EFUSE_SUMMARY = "efuse_summary"
READ_MODE_SECURITY_INFO = "security_info"
READ_MODE_READ_FLASH = "read_flash"

READ_MODE_LABELS = {
    READ_MODE_CHIP_INFO: "Chip Info",
    READ_MODE_FLASH_ID: "Flash ID",
    READ_MODE_EFUSE_SUMMARY: "eFuse Summary",
    READ_MODE_SECURITY_INFO: "Security Info (encryption / secure boot state)",
    READ_MODE_READ_FLASH: "Read Flash Region...",
}

# Default region read back by "Read Flash Region..." when the user hasn't
# entered their own address/size -- the first 4KB, covering the bootloader
# on chips that place it at the conventional 0x1000 address.
DEFAULT_READ_FLASH_ADDRESS = "0x0"
DEFAULT_READ_FLASH_SIZE = "0x1000"

# --------------------------------------------------------------------------
# Auto-Save (app/ui/settings_dialog.py, app/ui/main_window.py)
# --------------------------------------------------------------------------
# Minutes between automatic saves; 0 means "Disabled". A brand-new project
# that has never been saved to disk (no current_file_path yet) is always
# skipped -- there is nowhere to auto-save it to yet, and silently picking
# a location on the user's behalf would be surprising.
AUTOSAVE_INTERVAL_DISABLED = 0
AUTOSAVE_INTERVAL_OPTIONS = [0, 1, 2, 5, 10, 15, 30]
AUTOSAVE_INTERVAL_LABELS = {
    0: "Disabled",
    1: "Every 1 minute",
    2: "Every 2 minutes",
    5: "Every 5 minutes",
    10: "Every 10 minutes",
    15: "Every 15 minutes",
    30: "Every 30 minutes",
}
DEFAULT_AUTOSAVE_INTERVAL_MINUTES = 10
SETTINGS_KEY_AUTOSAVE_INTERVAL = "autosave_interval_minutes"

# --------------------------------------------------------------------------
# QC Verification (app/models/history_model.py, app/ui/history_panel.py)
# --------------------------------------------------------------------------
# Distinct wording from the flash-result strings (STATUS_COMPLETED /
# STATUS_FAILED above) since QC verification is a separate, manual step a
# human performs on the physical board *after* a flash already succeeded --
# conflating the two would make a "Failed" QC result indistinguishable from
# a flash that never completed in the first place.
QC_STATUS_NOT_TESTED = "Not Tested"
QC_STATUS_PASS = "Pass"
QC_STATUS_FAIL = "Fail"
QC_STATUS_OPTIONS = [QC_STATUS_NOT_TESTED, QC_STATUS_PASS, QC_STATUS_FAIL]
QC_STATUS_COLORS = {
    QC_STATUS_NOT_TESTED: "#8a8f98",
    QC_STATUS_PASS: "#2f9e44",
    QC_STATUS_FAIL: "#e03131",
}

# --------------------------------------------------------------------------
# Sounds & Notifications (app/utilities/sound_player.py, Settings -> Sounds)
# --------------------------------------------------------------------------
SOUND_EVENT_FLASH_SUCCESS = "flash_success"
SOUND_EVENT_FLASH_FAILURE = "flash_failure"
SOUND_EVENT_BATCH_COMPLETE = "batch_complete"
SOUND_EVENT_DEVICE_CONNECTED = "device_connected"
SOUND_EVENT_DEVICE_DISCONNECTED = "device_disconnected"
SOUND_EVENTS = [
    SOUND_EVENT_FLASH_SUCCESS,
    SOUND_EVENT_FLASH_FAILURE,
    SOUND_EVENT_BATCH_COMPLETE,
    SOUND_EVENT_DEVICE_CONNECTED,
    SOUND_EVENT_DEVICE_DISCONNECTED,
]
SOUND_EVENT_LABELS = {
    SOUND_EVENT_FLASH_SUCCESS: "Device flash succeeded",
    SOUND_EVENT_FLASH_FAILURE: "Device flash failed",
    SOUND_EVENT_BATCH_COMPLETE: "Whole batch finished",
    SOUND_EVENT_DEVICE_CONNECTED: "Device connected (USB)",
    SOUND_EVENT_DEVICE_DISCONNECTED: "Device disconnected (USB)",
}
SETTINGS_KEY_SOUNDS_ENABLED = "sounds_enabled"
DEFAULT_SOUNDS_ENABLED = True
# Per-event settings.json keys are built as f"{prefix}{event}".
SETTINGS_KEY_SOUND_EVENT_ENABLED_PREFIX = "sound_enabled_"
SETTINGS_KEY_SOUND_EVENT_PATH_PREFIX = "sound_path_"
# Events that are ON by default even before the user visits the Sounds tab.
DEFAULT_ENABLED_SOUND_EVENTS = {SOUND_EVENT_FLASH_FAILURE, SOUND_EVENT_BATCH_COMPLETE}

# --------------------------------------------------------------------------
# Device Groups & Tags (app/models/device_model.py, app/ui/device_panel.py)
# --------------------------------------------------------------------------
# Free-text labels (e.g. "Line A", "RFID Batch") a device can carry any
# number of, used purely for filtering/sorting/at-a-glance grouping in the
# UI -- they never affect flashing behaviour itself.
TAG_FILTER_ALL = "All Tags"
DEVICE_SORT_ORDER_ADDED = "order_added"
DEVICE_SORT_NAME = "name"
DEVICE_SORT_TAG = "tag"
DEVICE_SORT_OPTIONS = [DEVICE_SORT_ORDER_ADDED, DEVICE_SORT_NAME, DEVICE_SORT_TAG]
DEVICE_SORT_LABELS = {
    DEVICE_SORT_ORDER_ADDED: "Sort: Order Added",
    DEVICE_SORT_NAME: "Sort: Name",
    DEVICE_SORT_TAG: "Sort: Tag",
}

# --------------------------------------------------------------------------
# .emfm project-file input validation (app/project_manager/project_io.py) --
# see docs/THREAT_MODEL.md for the full writeup. A .emfm file is treated as
# untrusted input: it can arrive by email, USB stick, or a shared network
# folder, and "Open Project" will parse whatever is pointed at it. These
# caps exist purely to bound the cost of parsing/rendering a hostile or
# corrupted file (a JSON bomb via deep nesting, or a "devices"/"firmware"
# array with millions of entries) to something that fails fast with a
# clear error instead of hanging the UI thread or exhausting memory. They
# are deliberately generous relative to any real bench (the app's own
# tooling doesn't get anywhere near these numbers) so no legitimate
# project is ever rejected.
# --------------------------------------------------------------------------
MAX_PROJECT_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MiB of JSON is enormous for this schema
MAX_DEVICES_PER_PROJECT = 2000
MAX_FIRMWARE_ENTRIES_PER_DEVICE = 200

# --------------------------------------------------------------------------
# Undo/Redo (app/controllers/undo_stack.py, app/controllers/device_controller.py)
# --------------------------------------------------------------------------
# Ctrl+Z / Ctrl+Y coverage for the four bulk device-mutation operations:
# Batch Edit, bulk device removal, Assign Firmware Set to Devices, and CSV
# import. Implemented as a bounded stack of whole-device-list snapshots
# (see undo_stack.py's module docstring for why whole-snapshot rather than
# field-level diffing was chosen) -- this constant caps how many snapshots
# are kept in memory at once. Exposed in Settings -> Advanced since a bench
# doing very large batch operations repeatedly may want a smaller depth to
# bound memory use, while most users never need to touch it.
UNDO_STACK_DEPTH = 25
SETTINGS_KEY_UNDO_STACK_DEPTH = "undo_stack_depth"
UNDO_STACK_DEPTH_MIN = 1
UNDO_STACK_DEPTH_MAX = 200
UNDO_SHORTCUT = "Ctrl+Z"
REDO_SHORTCUT = "Ctrl+Shift+Z"

# --------------------------------------------------------------------------
# Zip + Manifest bulk-flashing import (app/project_manager/zip_manifest_import.py)
# --------------------------------------------------------------------------
# Accepts a single .zip containing firmware binaries plus a manifest file
# (device name/tag -> firmware+address mapping) and materializes it into a
# full device list + firmware assignment in one import step. Conceptually
# an extension of csv_import.py (device rows) plus
# firmware_manager/auto_detect.py (folder-to-firmware-list resolution).
# The manifest itself is plain CSV with a fixed column layout below, kept
# deliberately simple (no JSON manifest format yet -- see ROADMAP.md) so it
# can be hand-edited or generated by any spreadsheet tool.
ZIP_MANIFEST_FILENAME = "manifest.csv"
ZIP_MANIFEST_FILE_FILTER = "Firmware Bundle (*.zip)"
# Manifest columns: device_name,tags,chip_type,firmware_file,address[,enabled]
# One row per (device, firmware file) pair -- a device with three firmware
# files assigned occupies three rows sharing the same device_name, mirroring
# how a real production run's spreadsheet is usually laid out.
ZIP_MANIFEST_COLUMNS = ["device_name", "tags", "chip_type", "firmware_file", "address", "enabled"]
# Safety caps mirroring MAX_PROJECT_FILE_SIZE_BYTES/MAX_DEVICES_PER_PROJECT
# above -- a .zip is also untrusted input (see docs/THREAT_MODEL.md) that
# could arrive from anywhere, so bound the cost of extracting a hostile or
# corrupted archive before any of it is parsed.
MAX_ZIP_BUNDLE_SIZE_BYTES = 200 * 1024 * 1024  # 200 MiB of firmware binaries is already a lot
MAX_ZIP_MANIFEST_ROWS = 5000
