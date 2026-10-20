"""
project_io.py
==============
Handles saving and loading .emfm project files (plain JSON), plus the
"recent projects" list persisted via AppSettings. Designed to never raise
an uncaught exception into the UI layer — callers get either a valid
ProjectModel or a ProjectLoadError with a human-readable message.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.logging_setup.logger import get_logger
from app.models.project_model import ProjectModel
from app.utilities.app_settings import get_project_lock_stale_seconds, get_settings
from app.utilities.constants import (
    APP_VERSION,
    AUTOSAVE_RECOVERY_DIRNAME,
    AUTOSAVE_RECOVERY_FILENAME,
    MAX_DEVICES_PER_PROJECT,
    MAX_FIRMWARE_ENTRIES_PER_DEVICE,
    MAX_PROJECT_FILE_SIZE_BYTES,
    MAX_RECENT_PROJECTS,
    PROJECT_LOCK_FILE_SUFFIX,
)
from app.utilities.helpers import (
    clear_file_hidden,
    get_app_data_dir,
    mark_file_hidden,
    normalize_path_for_comparison,
)

logger = get_logger(__name__)


class ProjectLoadError(Exception):
    """Raised when a project file cannot be parsed or is structurally invalid."""


class ProjectLockError(Exception):
    """Raised by acquire_project_lock() when another holder's lock on this
    project looks active (see ProjectLockInfo)."""


def _atomic_write_json(path: Path, data: dict, *, create_parents: bool = False) -> None:
    """
    Write `data` as JSON to `path` atomically: serialize to a temp file
    in the same directory, flush + fsync it, then os.replace() it over
    the real path (atomic on both POSIX and Windows).

    Previously save_project() wrote directly to the target path with a
    plain ``path.open("w")`` -- a crash, power loss, or the process being
    killed partway through that write left a truncated/corrupt .emfm
    file, discovered only the next time someone tried to open it (with
    no backup, since the truncated file *is* what got left on disk).

    `create_parents` is off by default for a user-chosen save location
    (a real Save/Save As dialog only ever offers an existing directory,
    so a missing parent here means something is actually wrong -- e.g.
    the folder was deleted/unmounted after the dialog was shown -- and
    that should surface as an error, not silently create an unrelated
    directory tree). App-managed locations (settings.json, the autosave
    recovery slot) pass True since their directory is expected to be
    created on first use.
    """
    if create_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.parent.is_dir():
        raise OSError(f"Directory does not exist: {path.parent}")
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    # Dotfile-hidden on Linux/macOS already just by its name; also set
    # the real Windows "hidden" attribute, since a leading dot means
    # nothing to Explorer -- see mark_file_hidden()'s docstring.
    mark_file_hidden(tmp_path)
    os.replace(tmp_path, path)
    # os.replace()/MoveFileExW on Windows carries the temp file's hidden
    # attribute over onto `path` -- this is the real, user-facing file
    # being saved, so it must never end up invisible in Explorer.
    clear_file_hidden(path)


# --------------------------------------------------------------------------
# Firmware path relativization: firmware entries are stored relative to
# the .emfm file's own directory whenever possible, instead of as an
# absolute path baked in at save time. An absolute path only ever
# resolves correctly on the machine (and exact directory layout) it was
# saved from -- moving/renaming the project folder, or handing the
# project to a coworker whose checkout lives at a different absolute
# location, silently broke every firmware reference even though the
# project file and its firmware were moved/copied together and their
# *relative* layout to each other never changed.
#
# Both helpers are deliberately defensive about `data`'s actual shape:
# they are also run (via load_project) on arbitrary/untrusted/corrupted
# JSON before ProjectModel.from_dict ever gets a chance to validate
# anything, so a "devices"/"firmware" key holding the wrong type (a
# string, a bool, a list of non-dicts, ...) must be skipped over rather
# than raising -- ProjectModel.from_dict is what turns that into a
# clean ProjectLoadError, not this step.
# --------------------------------------------------------------------------
def _relativize_firmware_paths(data: dict, base_dir: Path) -> dict:
    devices = data.get("devices")
    if not isinstance(devices, list):
        return data
    for device in devices:
        if not isinstance(device, dict):
            continue
        firmware = device.get("firmware")
        if not isinstance(firmware, list):
            continue
        for entry in firmware:
            if not isinstance(entry, dict):
                continue
            file_path = entry.get("file_path")
            if not file_path or not isinstance(file_path, str):
                continue
            abs_path = Path(file_path)
            if not abs_path.is_absolute():
                continue  # already relative (e.g. round-tripped without ever being resolved)
            try:
                entry["file_path"] = os.path.relpath(abs_path, base_dir)
            except ValueError:
                # Different drive on Windows -- no relative path exists;
                # keep the absolute path as the only option available.
                pass
    return data


def _validate_project_shape(raw: object) -> None:
    """Cheap, pre-ProjectModel structural sanity checks on parsed JSON
    from an untrusted .emfm file -- see docs/THREAT_MODEL.md. Bounds the
    number of devices and firmware entries per device before any
    DeviceConfig/FirmwareEntry objects are constructed or the UI tries to
    render them, so a hostile/corrupted file with e.g. a million-entry
    "devices" array fails fast with a clear message instead of hanging
    the UI thread or exhausting memory building objects for it.

    Deliberately permissive about *type* mismatches here (e.g. "devices"
    being a string instead of a list) -- that's ProjectModel.from_dict's
    job to catch and report as a structure error; this function only
    guards against a shape that is technically valid JSON but
    pathologically large.
    """
    if not isinstance(raw, dict):
        return
    devices = raw.get("devices")
    if not isinstance(devices, list):
        return
    if len(devices) > MAX_DEVICES_PER_PROJECT:
        raise ProjectLoadError(
            f"This project file lists {len(devices)} devices, which is more than the "
            f"{MAX_DEVICES_PER_PROJECT} supported. It may be corrupted, or not actually a "
            "project file."
        )
    for device in devices:
        if not isinstance(device, dict):
            continue
        firmware = device.get("firmware")
        if isinstance(firmware, list) and len(firmware) > MAX_FIRMWARE_ENTRIES_PER_DEVICE:
            raise ProjectLoadError(
                f"A device in this project file lists {len(firmware)} firmware entries, which is "
                f"more than the {MAX_FIRMWARE_ENTRIES_PER_DEVICE} supported per device. It may be "
                "corrupted, or not actually a project file."
            )


def _absolutize_firmware_paths(data: dict, base_dir: Path) -> dict:
    devices = data.get("devices")
    if not isinstance(devices, list):
        return data
    for device in devices:
        if not isinstance(device, dict):
            continue
        firmware = device.get("firmware")
        if not isinstance(firmware, list):
            continue
        for entry in firmware:
            if not isinstance(entry, dict):
                continue
            file_path = entry.get("file_path")
            if not file_path or not isinstance(file_path, str):
                continue
            candidate = Path(file_path)
            if candidate.is_absolute():
                continue  # legacy file saved before this fix -- use as-is
            entry["file_path"] = str((base_dir / candidate).resolve())
    return data


def save_project(project: ProjectModel, file_path: str) -> None:
    """Serialize `project` to `file_path` as pretty-printed JSON,
    atomically, with firmware paths stored relative to `file_path`'s own
    directory wherever possible.

    A real Save/Save As always stamps the CURRENT app's schema_version
    onto the in-memory project before writing, regardless of what it was
    loaded with. ProjectModel.from_dict() deliberately *preserves* an
    older file's original schema_version string (see its own docstring
    and tests/models/test_project_model.py) so that value is only ever
    a record of what last wrote the file on disk -- without this, a
    project opened from an old 1.0.0-era file kept reporting itself as
    schema_version "1.0.0" forever, on every subsequent save, even
    though this build had already migrated its in-memory structure to
    the current schema on load. Every real save is this build actually
    writing the file in its own current schema, so the file's own
    schema_version must say so too.
    """
    project.schema_version = APP_VERSION
    path = Path(file_path).resolve()
    try:
        data = _relativize_firmware_paths(project.to_dict(), path.parent)
        _atomic_write_json(path, data)
        logger.info("Project saved to %s (%d devices)", file_path, len(project.devices))
        add_recent_project(file_path)
    except OSError as exc:
        logger.exception("Failed to save project to %s", file_path)
        raise ProjectLoadError(f"Could not write project file:\n{exc}") from exc


def load_project(file_path: str) -> ProjectModel:
    """
    Load a .emfm file. Missing firmware files are NOT treated as fatal —
    the caller (controller) is responsible for validating firmware paths
    afterwards and surfacing warnings; a corrupt/unreadable JSON file *is*
    fatal and raises ProjectLoadError.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise ProjectLoadError(f"Project file not found:\n{file_path}")

    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise ProjectLoadError(f"Could not read project file:\n{exc}") from exc
    if file_size > MAX_PROJECT_FILE_SIZE_BYTES:
        # Rejected before json.load() ever runs -- deliberately checked on
        # the raw file size, not after parsing, so a hostile/corrupted
        # multi-gigabyte file can't consume memory or CPU parsing it just
        # to be rejected afterwards. See docs/THREAT_MODEL.md.
        raise ProjectLoadError(
            f"This project file is {file_size / (1024 * 1024):.1f} MB, which is larger than the "
            f"{MAX_PROJECT_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB expected for a project file. "
            "It may be corrupted, or not actually a project file."
        )

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        # ValueError covers json.JSONDecodeError as well as
        # UnicodeDecodeError -- a binary or non-UTF-8 file (e.g. a
        # corrupted save, or someone pointing "Open Project" at an
        # unrelated .bin file renamed to .emfm) must be reported the
        # same friendly way as malformed JSON, never leak a raw traceback.
        logger.exception("Failed to parse project file %s", file_path)
        raise ProjectLoadError(
            f"This project file is corrupted or not valid JSON:\n{exc}"
        ) from exc

    _validate_project_shape(raw)

    if isinstance(raw, dict):
        raw = _absolutize_firmware_paths(raw, path.parent)

    try:
        project = ProjectModel.from_dict(raw)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, never crash UI
        logger.exception("Failed to build ProjectModel from %s", file_path)
        raise ProjectLoadError(
            f"This project file's structure is not recognized:\n{exc}"
        ) from exc

    # Recalculate firmware metadata (size/MD5/missing) from disk for every
    # device -- none of it is stored in the project file.
    for device in project.devices:
        for entry in device.firmware:
            entry.refresh()

    logger.info("Project loaded from %s (%d devices)", file_path, len(project.devices))
    add_recent_project(file_path)
    return project


# --------------------------------------------------------------------------
# Recent projects (persisted via AppSettings, a single settings.json file
# under the per-user roaming app-data folder — no registry involvement on
# any platform).
# --------------------------------------------------------------------------
def add_recent_project(file_path: str) -> None:
    settings = get_settings()
    recents: list[str] = settings.value("recent_projects", [], type=list) or []
    # Two spellings of the same path (different slash style, e.g.
    # "C:/Users/sample.emfm" vs "C:\Users\sample.emfm") must dedupe to a
    # single Recent Projects entry -- see
    # helpers.normalize_path_for_comparison's docstring. The stored/
    # displayed value stays whatever `file_path` was actually given as
    # this time (most-recently-used spelling wins), only the comparison
    # used for dedup is normalized.
    normalized_new = normalize_path_for_comparison(file_path)
    recents = [p for p in recents if normalize_path_for_comparison(p) != normalized_new]
    recents.insert(0, file_path)
    recents = recents[:MAX_RECENT_PROJECTS]
    settings.setValue("recent_projects", recents)


def get_recent_projects() -> list[str]:
    settings = get_settings()
    recents: list[str] = settings.value("recent_projects", [], type=list) or []
    # Filter out projects that no longer exist on disk.
    return [p for p in recents if Path(p).is_file()]


def clear_recent_projects() -> None:
    get_settings().setValue("recent_projects", [])


# --------------------------------------------------------------------------
# Advisory cross-process/cross-machine locking for .emfm project files.
#
# This is deliberately a *sidecar* lock file (project.emfm.lock next to
# project.emfm), not a real OS-level file lock (flock()/LockFileEx) --
# those are unreliable or entirely unsupported on common network
# filesystems (SMB/NFS), which is exactly the scenario this guards
# (two people opening the same project off a shared drive). It cannot
# stop a second process from ignoring it, but it does turn the common
# "my coworker already has this open" case into a clear warning instead
# of two independent, silent edits that clobber whichever save happens
# to land last -- which was previously not detected at all.
# --------------------------------------------------------------------------
@dataclass
class ProjectLockInfo:
    holder: str  # "user@hostname"
    pid: int
    acquired_at: str  # ISO-8601 timestamp
    lock_path: Path


def _lock_path_for(file_path: str) -> Path:
    # Dot-prefix the sidecar's own filename (not just append a suffix to
    # the full path) so it reads as a hidden dotfile on Linux/macOS --
    # e.g. "project.emfm" -> ".project.emfm.lock" next to it, not the
    # previous "project.emfm.lock", which had no leading dot at all and
    # was exactly as visible as the project file itself in every file
    # browser. mark_file_hidden() (see acquire_project_lock) additionally
    # sets the real Windows hidden attribute, since Explorer doesn't
    # treat a leading dot as meaningful.
    p = Path(file_path)
    return p.with_name(f".{p.name}{PROJECT_LOCK_FILE_SUFFIX}")


def _current_holder() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - getpass can fail in odd environments (no controlling tty, etc.)
        user = "unknown"
    return f"{user}@{socket.gethostname()}"


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists, just owned by someone else
    except OSError:
        return False
    return True


def read_project_lock(file_path: str) -> ProjectLockInfo | None:
    """Return the current lock sidecar's contents for `file_path`, or
    None if there isn't one / it can't be read."""
    lock_path = _lock_path_for(file_path)
    if not lock_path.is_file():
        return None
    try:
        with lock_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return ProjectLockInfo(
            holder=str(data.get("holder", "unknown")),
            pid=int(data.get("pid", 0)),
            acquired_at=str(data.get("acquired_at", "")),
            lock_path=lock_path,
        )
    except (OSError, ValueError, TypeError):
        return None


def _lock_is_stale(info: ProjectLockInfo) -> bool:
    try:
        acquired = datetime.fromisoformat(info.acquired_at)
    except ValueError:
        return True
    age_seconds = (datetime.now().astimezone() - acquired).total_seconds()
    if age_seconds > get_project_lock_stale_seconds():
        return True
    # PIDs are only meaningfully comparable on the same host as the one
    # that created the lock -- a lock from a different host is left
    # alone (age is the only staleness signal available for it).
    if info.holder == _current_holder():
        return not _pid_is_running(info.pid)
    return False


def acquire_project_lock(file_path: str) -> ProjectLockInfo | None:
    """
    Write this process's lock sidecar for `file_path` and return it, or
    raise ProjectLockError if a non-stale lock held by someone else
    already exists. Always best-effort: an OSError writing the sidecar
    (e.g. a read-only share) is logged and swallowed rather than blocking
    the project from opening over something purely advisory.
    """
    existing = read_project_lock(file_path)
    if existing is not None and existing.holder != _current_holder() and not _lock_is_stale(existing):
        raise ProjectLockError(
            f"This project appears to already be open by {existing.holder} "
            f"(since {existing.acquired_at})."
        )
    if existing is not None and existing.pid == os.getpid() and existing.holder == _current_holder():
        return existing  # already ours (e.g. re-saving to the same path)

    lock_path = _lock_path_for(file_path)
    info = ProjectLockInfo(
        holder=_current_holder(), pid=os.getpid(),
        acquired_at=datetime.now().astimezone().isoformat(), lock_path=lock_path,
    )
    try:
        with lock_path.open("w", encoding="utf-8") as handle:
            json.dump({"holder": info.holder, "pid": info.pid, "acquired_at": info.acquired_at}, handle)
        mark_file_hidden(lock_path)
    except OSError:
        logger.warning("Could not write project lock sidecar for %s (continuing without one)", file_path)
    return info


def release_project_lock(file_path: str) -> None:
    """Remove this process's own lock sidecar for `file_path`, if any.
    Never removes a lock held by a different process/host."""
    info = read_project_lock(file_path)
    if info is not None and info.pid == os.getpid() and info.holder == _current_holder():
        with suppress(OSError):
            info.lock_path.unlink()


# --------------------------------------------------------------------------
# Crash-protection auto-save "recovery slot" for brand-new, never-saved
# projects. See AUTOSAVE_RECOVERY_DIRNAME's docstring in constants.py for
# why this exists and what it deliberately does NOT do (it never becomes
# the project's real save location).
# --------------------------------------------------------------------------
def _autosave_recovery_path() -> Path:
    return get_app_data_dir() / AUTOSAVE_RECOVERY_DIRNAME / AUTOSAVE_RECOVERY_FILENAME


def save_autosave_recovery(project: ProjectModel) -> None:
    """Write `project` to the crash-recovery slot. Best-effort/never
    raises -- a failure here should never interrupt the user's session,
    it just means the crash-protection safety net didn't get updated
    this cycle."""
    try:
        path = _autosave_recovery_path()
        data = _relativize_firmware_paths(project.to_dict(), path.parent)
        _atomic_write_json(path, data, create_parents=True)
    except OSError:
        logger.exception("Failed to write autosave recovery slot")


def load_autosave_recovery() -> ProjectModel | None:
    """Return the project sitting in the crash-recovery slot, or None if
    there isn't one / it can't be read."""
    path = _autosave_recovery_path()
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict):
            raw = _absolutize_firmware_paths(raw, path.parent)
        project = ProjectModel.from_dict(raw)
        for device in project.devices:
            for entry in device.firmware:
                entry.refresh()
        return project
    except (OSError, ValueError, TypeError):
        logger.exception("Failed to read autosave recovery slot")
        return None


def has_autosave_recovery() -> bool:
    return _autosave_recovery_path().is_file()


def discard_autosave_recovery() -> None:
    """Delete the crash-recovery slot -- called once its contents have
    either been recovered into a real project, or the user explicitly
    declined to recover it."""
    with suppress(OSError):
        _autosave_recovery_path().unlink()
