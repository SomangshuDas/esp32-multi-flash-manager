"""
helpers.py
==========
Small, dependency-free utility functions shared across the application.
Nothing in this module should import from ``app.ui`` — it must stay usable
from headless contexts (workers, tests, CLI tools).
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path


def new_uuid() -> str:
    """Return a fresh unique identifier string used for devices/firmware rows."""
    return str(uuid.uuid4())


def compute_md5(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    """
    Compute the MD5 checksum of a file, streaming it in chunks so that even
    large firmware images (multi-MB) do not blow up memory usage.

    Raises FileNotFoundError / OSError if the file cannot be read; callers
    are expected to handle that (e.g. to mark firmware rows as "missing").
    """
    md5 = hashlib.md5()
    with open(file_path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            md5.update(chunk)
    return md5.hexdigest()


def human_readable_size(num_bytes: int) -> str:
    """Convert a byte count into a human friendly string, e.g. '1.4 MB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def human_readable_duration(seconds: float) -> str:
    """Convert a duration in seconds into 'HH:MM:SS' or 'MM:SS' string form."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def is_valid_hex_address(value: str) -> bool:
    """Return True if `value` looks like a valid flash address, e.g. '0x10000'."""
    if not value:
        return False
    return bool(re.fullmatch(r"0[xX][0-9a-fA-F]+", value.strip()))


def normalize_hex_address(value: str) -> str:
    """Normalize a hex address string to a canonical lowercase '0x...' form,
    based on its numeric value rather than its literal digits.

    This is what makes '0x0', '0x00', and '0x0000' compare equal, and
    likewise '0x1000' and '0x01000' -- two spellings of the exact same
    flash offset shouldn't be treated as different addresses just because
    one has extra leading zeros (or a different case) than the other.
    Callers that key a dict/set on an address (duplicate-address
    detection, "is 0x1000 present" checks, ...) should normalize both
    sides with this function rather than comparing raw strings.
    """
    value = value.strip()
    if not value.lower().startswith("0x"):
        value = "0x" + value
    digits = value[2:].lower().lstrip("x") or "0"
    return f"0x{int(digits, 16):x}"


def normalize_path_for_comparison(path: str) -> str:
    """Return a form of `path` suitable for **equality comparison only**
    -- never for display or for actually opening a file. Two spellings
    of the same location (`C:/Users/sample.emfm` vs
    `C:\\Users\\sample.emfm`, or a path with a redundant `./`/`../`
    segment) must compare equal wherever the app treats "is this the
    same project/file as that one" as a question, e.g. deduplicating the
    Recent Projects list (see project_io.add_recent_project) --
    otherwise the same file typed or dropped in with a different
    separator style ends up as two separate entries.

    `os.path.normpath()` collapses separator style and redundant
    segments (mixed `/`/`\\` both become the OS's native separator, and
    `normpath` also folds e.g. `..` where possible); `os.path.normcase()`
    additionally lowercases and further normalizes separators on
    case-insensitive filesystems (Windows) while being a no-op on
    case-sensitive ones (Linux/macOS), matching each OS's own notion of
    "same path". This does NOT resolve symlinks or relative-to-cwd
    paths -- callers needing that should use `Path.resolve()` instead;
    this function is specifically for the common "cosmetic slash-style
    difference" case, which is what actually happens when the same path
    is typed by hand vs produced by a file picker vs read back from a
    project someone else saved.

    Backslashes are always treated as path separators here, even when
    this process is running on a POSIX system where `os.path` would
    otherwise treat `\\` as a literal filename character. A project file
    referencing a Windows-style path (the overwhelmingly common case for
    an ESP32 flashing bench) needs the same C:/Users/... vs
    C:\\Users\\... equivalence honored consistently regardless of which
    platform this app happens to be running on right now, and a literal
    backslash in a real filename is vanishingly rare by comparison.
    """
    unified_separators = path.replace("\\", "/")
    return os.path.normcase(os.path.normpath(unified_separators))


def file_exists(path: str | None) -> bool:
    """Safe existence check that tolerates None / empty strings."""
    if not path:
        return False
    return Path(path).is_file()


def timestamp_now() -> str:
    """
    Return the current timestamp formatted for logs and history entries,
    as local time with an explicit UTC offset (e.g.
    "2026-09-04 14:23:01+0530").

    A UTC offset is included specifically so that flash-history CSV
    exports aggregated from machines in different time zones/sites can be
    reliably correlated and sorted -- a bare naive local timestamp (the
    previous behaviour) is ambiguous once entries from more than one time
    zone are mixed together. Still splits cleanly into (date_part,
    time_part) via `.split(" ", 1)` exactly like before, since the offset
    has no embedded space.
    """
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z")


def validate_extra_esptool_args(raw: str) -> str | None:
    """
    Validate a power-user "custom arguments" passthrough string (e.g.
    DeviceConfig.custom_flash_args / SecurityConfig.custom_efuse_args)
    before it is ever appended to a real esptool/espsecure/espefuse
    subprocess argv.

    These fields exist so advanced users can pass flags this app doesn't
    have dedicated UI for, but a shared or untrusted .emfm/project file
    could otherwise smuggle arbitrary extra flags/positional arguments
    into the real command line run against real hardware (e.g. pointing
    an output/keyfile flag at an arbitrary path, or appending an entirely
    different subcommand). This performs a conservative allowlist-style
    sanity check -- NOT a full CLI grammar parser -- and returns a short
    human-readable error string if the value looks unsafe, or None if it
    passes.

    Returns None (valid) for an empty/blank string.
    """
    text = (raw or "").strip()
    if not text:
        return None

    if len(text) > 500:
        return "Custom arguments are too long (500 character limit)."

    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        return f"Could not parse custom arguments (unbalanced quotes?): {exc}"

    if not tokens:
        return None

    # Subcommands/flags that would let a "just pass extra flags" field
    # silently replace or extend WHAT operation actually runs, rather than
    # just how it runs -- e.g. sneaking in a second write/erase/burn
    # command, or overriding the port/chip this app already set explicitly
    # a few tokens earlier in the real argv. Matched case-insensitively
    # since esptool accepts some of these in more than one casing.
    _BLOCKED_TOKENS = {
        "write_flash", "write-flash", "erase_flash", "erase-flash",
        "erase_region", "erase-region", "write_flash_status",
        "burn-key", "burn-key-digest", "burn-efuse", "burn_efuse",
        "burn-bit", "burn_bit", "burn-block-data", "burn_block_data",
        "--port", "-p", "--chip", "-c", "--before", "--after",
    }
    for token in tokens:
        lowered = token.lower()
        if lowered in _BLOCKED_TOKENS:
            return f"Argument '{token}' is not allowed in custom arguments (already controlled by this app)."
        if token.startswith("-"):
            continue
        # A bare (non-flag) token is only ever a *value* for the flag that
        # precedes it in valid esptool usage -- never a bare path. Reject
        # anything that looks like it is trying to reference a filesystem
        # path (potential path traversal / arbitrary file access) since a
        # legitimate custom flag value here is expected to be a short
        # keyword/number (e.g. a flash mode, a block name, an integer).
        if "/" in token or "\\" in token or ".." in token:
            return f"Argument '{token}' looks like a file path, which is not allowed in custom arguments."
    return None


def mark_file_hidden(path: str | Path) -> None:
    """
    Best-effort: hide a purely internal/sidecar file (advisory lock
    sidecars, atomic-write temp files, ...) from normal file-browser
    view.

    A leading dot in the filename (the convention already used
    throughout this app for such files, e.g. ``.project.emfm.tmp-1234``)
    is enough to hide a file on Linux and in macOS Finder, but Windows
    Explorer does NOT treat a leading dot as significant at all -- a
    dotfile is exactly as visible there as any other file, so on that
    platform hiding it requires actually setting the Win32 "hidden" file
    attribute. This is a no-op (and never raises) on every other
    platform, and swallows any error on Windows too (e.g. a filesystem
    that doesn't support the attribute) since this is cosmetic, never
    something a save/lock operation should fail over.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - purely cosmetic, never fatal
        pass


def clear_file_hidden(path: str | Path) -> None:
    """
    Best-effort counterpart to mark_file_hidden(): strip the Windows
    "hidden" attribute back off a path. Used after an atomic write
    replaces a hidden temp file onto its real, user-facing destination
    (os.replace()/MoveFileExW on Windows carries the source file's
    attributes over to the destination name), so the real deliverable
    file a user asked to save is never left invisible in Explorer.
    No-op everywhere except Windows; never raises.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        FILE_ATTRIBUTE_NORMAL = 0x80
        ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_NORMAL)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - purely cosmetic, never fatal
        pass


def safe_filename(name: str) -> str:
    """Strip characters that are illegal in filenames on Windows (a superset
    of what's illegal on macOS/Linux), so a safe name works on every OS."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "unnamed"


def get_app_data_dir() -> Path:
    """
    Return (and create if needed) the per-user application data directory,
    following each platform's own convention rather than a single
    Windows-shaped fallback:

        Windows -> %APPDATA%\\ESP32MultiFlashManager
        macOS   -> ~/Library/Application Support/ESP32MultiFlashManager
        Linux   -> $XDG_DATA_HOME/ESP32MultiFlashManager
                   (or ~/.local/share/ESP32MultiFlashManager if XDG_DATA_HOME
                   is not set, per the XDG Base Directory spec)

    This is what stores settings, recent projects, firmware profiles, and
    the rotating log files — never the application's own install directory,
    so the app never needs write access to wherever it's installed.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"

    target = base / "ESP32MultiFlashManager"
    target.mkdir(parents=True, exist_ok=True)
    return target


def resource_path(*parts: str) -> Path:
    """
    Resolve a path under the ``resources/`` directory that works identically:

      - running from source (``python run.py`` from the project root)
      - packaged with PyInstaller in ``--onefile`` mode, where bundled data
        is unpacked to a temporary directory exposed as ``sys._MEIPASS``
      - packaged with PyInstaller in ``--onedir`` mode, where bundled data
        sits next to the executable

    Always use this instead of hardcoding ``"resources/..."`` so icons and
    themes keep working after packaging on every OS.
    """
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # app/utilities/helpers.py -> app/utilities -> app -> project root
        base = Path(__file__).resolve().parent.parent.parent
    return base.joinpath("resources", *parts)


def propagate_trace_hook() -> None:
    """Re-arm coverage/profiler tracing on the calling thread.

    QThread (used by FlashWorker/ReadWorker/ProvisionWorker) spawns a
    genuine OS thread on the C++ side via QThread.start(), bypassing
    Python's ``threading`` module entirely -- so coverage.py's tracer,
    which only auto-attaches inside ``threading.Thread._bootstrap_inner``,
    never sees it. Call this as the very first line of ``run()``, then
    immediately delegate to a separate method (e.g. ``_run_impl()``):
    ``sys.settrace`` only traces frames created *after* it is called, so
    the body of ``run()`` itself would stay untraced otherwise.

    A no-op when nothing is tracing (e.g. not running under coverage).
    """
    hook = getattr(threading, "_trace_hook", None)
    if hook is not None:
        sys.settrace(hook)
