"""
project_controller.py
======================
Coordinates project lifecycle: new / open / save / save-as, plus
post-load checks for missing firmware files (never fatal — the project
still loads, offending rows are just flagged so the user can relink
them from the Firmware panel).

The legacy `.efmproj` format (the project's file extension prior to the
switch to `.emfm`) and its whole fallback-read/forced-migration
compatibility path were discontinued in 1.0.0 -- opening a project no
longer special-cases the file's extension at all; see this module's git
history for the old behavior.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.logging_setup.logger import get_logger
from app.models.firmware_model import FirmwareEntry
from app.models.project_model import ProjectModel
from app.project_manager.project_io import (
    ProjectLoadError,
    ProjectLockError,
    acquire_project_lock,
    discard_autosave_recovery,
    has_autosave_recovery,
    load_autosave_recovery,
    load_project,
    release_project_lock,
    save_autosave_recovery,
    save_project,
)

logger = get_logger(__name__)


class ProjectController(QObject):
    """
    Signals
    -------
    project_loaded(ProjectModel)
    project_saved(str)                      - file path
    missing_firmware_detected(list)         - list[FirmwareEntry] that are missing
    load_failed(str)                        - human-readable error message
    project_lock_warning(str)               - another holder appears to already have
                                               this project open (advisory only --
                                               the project still opens/loads normally)
    schema_version_warning(str)             - the loaded file's schema_version is
                                               newer than this build's own APP_VERSION
    """

    project_loaded = Signal(object)
    project_saved = Signal(str)
    missing_firmware_detected = Signal(list)
    load_failed = Signal(str)
    project_lock_warning = Signal(str)
    schema_version_warning = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.project = ProjectModel()
        self.current_file_path: str | None = None
        self.dirty: bool = False

    # ------------------------------------------------------------------
    def new_project(self) -> None:
        self._release_current_lock()
        self.project = ProjectModel()
        self.current_file_path = None
        self.dirty = False
        self.project_loaded.emit(self.project)
        logger.info("Created new blank project")

    def _release_current_lock(self) -> None:
        if self.current_file_path:
            release_project_lock(self.current_file_path)

    def open_project(self, file_path: str) -> bool:
        try:
            project = load_project(file_path)
        except ProjectLoadError as exc:
            logger.error("Project load failed: %s", exc)
            self.load_failed.emit(str(exc))
            return False

        self._release_current_lock()

        self.project = project
        self.current_file_path = file_path
        self.dirty = False
        self.project_loaded.emit(self.project)

        # Advisory only: a locked-by-someone-else project still opens
        # normally (this may be a stale lock from a crash, or the user
        # may legitimately want a read-only look) -- it's surfaced as
        # a warning the caller can show, not a hard block.
        try:
            acquire_project_lock(file_path)
        except ProjectLockError as exc:
            self.project_lock_warning.emit(str(exc))

        if project.schema_warning:
            self.schema_version_warning.emit(project.schema_warning)

        missing = self._collect_missing_firmware(project)
        if missing:
            self.missing_firmware_detected.emit(missing)
        return True

    def save_project(self, file_path: str | None = None) -> bool:
        target = file_path or self.current_file_path
        if not target:
            logger.warning("save_project called with no target path")
            return False
        try:
            save_project(self.project, target)
        except ProjectLoadError as exc:
            self.load_failed.emit(str(exc))
            return False
        if target != self.current_file_path:
            self._release_current_lock()
            try:
                acquire_project_lock(target)
            except ProjectLockError as exc:
                # Someone else already holds a lock on this exact target
                # path (Save As onto a project someone else has open) --
                # surfaced the same way as the open_project case, still
                # non-blocking since the save itself already succeeded.
                self.project_lock_warning.emit(str(exc))
        self.current_file_path = target
        self.dirty = False
        # A real save always supersedes whatever was sitting in the
        # crash-recovery slot for this session.
        discard_autosave_recovery()
        self.project_saved.emit(target)
        return True

    def autosave(self) -> None:
        """
        Periodic autosave tick (see MainWindow._on_autosave_timeout).

        Previously this only ever did anything when current_file_path was
        already set -- a brand-new, never-saved project had no
        destination to autosave to and was silently left completely
        unprotected until the user's first manual Save, so a crash/power
        loss before that point lost the whole session with nothing to
        recover. Routes to the crash-recovery slot instead in that case
        (see project_io.save_autosave_recovery) -- never treated as a
        real save (current_file_path/dirty are untouched), purely a
        safety net.
        """
        if self.current_file_path:
            self.save_project(self.current_file_path)
        elif self.dirty:
            save_autosave_recovery(self.project)

    def mark_dirty(self) -> None:
        self.dirty = True

    def release_lock(self) -> None:
        """Release this session's project lock (see project_io's
        advisory-locking module docstring). Call on app shutdown."""
        self._release_current_lock()

    @staticmethod
    def has_recoverable_autosave() -> bool:
        return has_autosave_recovery()

    def recover_autosaved_project(self) -> bool:
        """
        Load the crash-recovery slot as the current (still-unsaved)
        project, if one exists. Returns True if a project was recovered.
        Does not delete the recovery slot itself -- that only happens
        once the user either does a real Save (see save_project above)
        or explicitly discards it (see discard_recovered_autosave).
        """
        recovered = load_autosave_recovery()
        if recovered is None:
            return False
        self.project = recovered
        self.current_file_path = None
        self.dirty = True
        self.project_loaded.emit(self.project)
        logger.info("Recovered project from crash-protection autosave slot")
        return True

    @staticmethod
    def discard_recovered_autosave() -> None:
        discard_autosave_recovery()

    @staticmethod
    def _collect_missing_firmware(project: ProjectModel) -> list[FirmwareEntry]:
        missing: list[FirmwareEntry] = []
        for device in project.devices:
            for entry in device.firmware:
                if entry.missing:
                    missing.append(entry)
        return missing
