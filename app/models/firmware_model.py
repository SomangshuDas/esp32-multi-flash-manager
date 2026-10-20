"""
firmware_model.py
==================
Data model for a single firmware binary (.bin) entry attached to a device.
Deliberately a plain dataclass (no QObject) so it can be freely
serialized to JSON for project files and copied/duplicated cheaply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.utilities.helpers import compute_md5, file_exists, human_readable_size, new_uuid


@dataclass
class FirmwareEntry:
    """A single BIN file plus the address it should be flashed to."""

    id: str = field(default_factory=new_uuid)
    file_path: str = ""
    address: str = "0x1000"
    enabled: bool = True

    # Derived fields (recomputed from disk via refresh(), see below) -- not
    # authoritative and NOT persisted to the project file (see
    # to_dict/from_dict): both the file size and the MD5 are always
    # recalculated from the actual BIN file whenever a project loads, so a
    # project file never carries a size or checksum that could silently go
    # stale if the BIN changes on disk between saves. Until refresh() has
    # run, they hold their empty defaults (0 / "").
    file_size: int = 0
    md5: str = ""
    missing: bool = False

    # Transient (never persisted): True if refresh() just found the file's
    # MD5 to be different from the last MD5 this entry knew about -- i.e.
    # the BIN file on disk was modified/replaced since it was added or the
    # project was last opened. Cleared back to False the next time refresh()
    # runs and finds no further change.
    md5_changed: bool = False

    @property
    def file_name(self) -> str:
        import os
        return os.path.basename(self.file_path) if self.file_path else "(no file)"

    @property
    def display_size(self) -> str:
        return human_readable_size(self.file_size) if self.file_size else "-"

    def refresh(self) -> None:
        """
        Recompute size/MD5/missing status from disk. Never raises.

        Size and MD5 are deliberately recalculated here every time rather
        than trusted from whatever was last stored (neither is written by
        to_dict) -- this is what lets a firmware file that was
        replaced/updated on disk between sessions be detected
        (md5_changed) instead of the app silently keeping stale, or
        now-incorrect, size/checksum info from a previous save.
        """
        previous_md5 = self.md5
        if not file_exists(self.file_path):
            self.missing = True
            self.file_size = 0
            self.md5 = ""
            self.md5_changed = False
            return
        try:
            import os
            self.missing = False
            self.file_size = os.path.getsize(self.file_path)
            self.md5 = compute_md5(self.file_path)
            self.md5_changed = bool(previous_md5) and previous_md5 != self.md5
        except OSError:
            self.missing = True
            self.file_size = 0
            self.md5 = ""
            self.md5_changed = False

    def duplicate(self) -> "FirmwareEntry":
        """Return a deep copy with a new unique id (used by 'Duplicate BIN')."""
        return FirmwareEntry(
            id=new_uuid(),
            file_path=self.file_path,
            address=self.address,
            enabled=self.enabled,
            file_size=self.file_size,
            md5=self.md5,
            missing=self.missing,
        )

    def to_dict(self) -> dict[str, Any]:
        # Neither the file size nor the MD5 is persisted (see refresh()'s
        # docstring) -- both are always recalculated from the actual BIN
        # file the next time this entry is loaded, so a project file never
        # carries a size or checksum that could silently go stale/incorrect
        # if the BIN changes on disk between saves.
        return {
            "id": self.id,
            "file_path": self.file_path,
            "address": self.address,
            "enabled": self.enabled,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FirmwareEntry":
        entry = FirmwareEntry(
            id=data.get("id", new_uuid()),
            file_path=data.get("file_path", ""),
            address=data.get("address", "0x1000"),
            enabled=data.get("enabled", True),
        )
        # Older project files (saved before dynamic MD5/size recalculation)
        # may still carry stored "md5" and "file_size" keys. "file_size" is
        # ignored outright -- refresh() below reads the real size from disk.
        # "md5" is read ONLY as a one-time baseline for change detection:
        # refresh() immediately recomputes the real, current MD5 from disk
        # and compares against this baseline to set md5_changed, then this
        # value is gone for good (never written back out by to_dict).
        entry.md5 = data.get("md5", "")
        entry.refresh()
        return entry
