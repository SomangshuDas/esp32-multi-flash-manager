"""Unit tests for app/project_manager/project_io.py (non-fuzz cases)."""

from __future__ import annotations

import json

import pytest

from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.models.project_model import ProjectModel
from app.project_manager import project_io
from app.project_manager.project_io import ProjectLoadError, load_project, save_project
from app.utilities.constants import APP_VERSION


class TestSaveProject:
    def test_writes_readable_json_file(self, tmp_path):
        project = ProjectModel(project_name="My Project")
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        assert path.is_file()
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        assert data["project_name"] == "My Project"

    def test_save_stamps_current_schema_version_on_legacy_project(self, tmp_path):
        """An old 1.0.0-era (or any older) project must have its
        schema_version bumped to this build's APP_VERSION as soon as it
        goes through a real Save/Save As -- see save_project()'s
        docstring. Without this, a project that was last written by an
        old release kept reporting schema_version "1.0.0" forever on
        every subsequent save, even after this build had already loaded
        and migrated it in memory."""
        project = ProjectModel.from_dict({"schema_version": "1.0.0", "project_name": "Old"})
        assert project.schema_version == "1.0.0"

        path = tmp_path / "project.emfm"
        save_project(project, str(path))

        assert project.schema_version == APP_VERSION
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        assert data["schema_version"] == APP_VERSION

    def test_save_as_onto_new_path_also_stamps_current_schema_version(self, tmp_path):
        project = ProjectModel.from_dict({"schema_version": "1.0.0", "project_name": "Old"})
        original_path = tmp_path / "project.emfm"
        save_project(project, str(original_path))

        new_path = tmp_path / "save_as_copy.emfm"
        save_project(project, str(new_path))

        with new_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        assert data["schema_version"] == APP_VERSION

    def test_adds_to_recent_projects(self, tmp_path):
        project = ProjectModel()
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        assert str(path) in project_io.get_recent_projects()

    def test_unwritable_location_raises_project_load_error(self, tmp_path):
        project = ProjectModel()
        bad_path = tmp_path / "no_such_dir" / "project.emfm"
        with pytest.raises(ProjectLoadError):
            save_project(project, str(bad_path))


class TestLoadProject:
    def test_roundtrip_with_devices_and_firmware(self, tmp_path):
        project = ProjectModel(project_name="Line A")
        device = DeviceConfig(name="Bench 1", com_port="COM3")
        firmware_path = tmp_path / "firmware.bin"
        firmware_path.write_bytes(b"\x00" * 128)
        device.add_firmware(FirmwareEntry(file_path=str(firmware_path), address="0x10000"))
        project.add_device(device)

        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        restored = load_project(str(path))

        assert restored.project_name == "Line A"
        assert len(restored.devices) == 1
        assert restored.devices[0].name == "Bench 1"
        assert restored.devices[0].firmware[0].missing is False
        assert restored.devices[0].firmware[0].file_size == 128

    def test_file_size_and_md5_are_not_persisted_and_recalculated_on_load(self, tmp_path):
        project = ProjectModel()
        device = DeviceConfig(name="Bench 1")
        firmware_path = tmp_path / "firmware.bin"
        firmware_path.write_bytes(b"\x00" * 128)
        device.add_firmware(FirmwareEntry(file_path=str(firmware_path), address="0x10000"))
        project.add_device(device)

        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        with path.open(encoding="utf-8") as handle:
            saved_entry = json.load(handle)["devices"][0]["firmware"][0]
        assert "file_size" not in saved_entry
        assert "md5" not in saved_entry

        # The BIN changes on disk between sessions: load must see the new size.
        firmware_path.write_bytes(b"\x01" * 300)
        restored = load_project(str(path))
        assert restored.devices[0].firmware[0].file_size == 300

    def test_stale_stored_file_size_in_legacy_file_is_ignored(self, tmp_path):
        firmware_path = tmp_path / "firmware.bin"
        firmware_path.write_bytes(b"\x00" * 64)
        path = tmp_path / "project.emfm"
        path.write_text(json.dumps({
            "schema_version": "1.0.0",
            "project_name": "Legacy",
            "devices": [{
                "name": "Bench 1",
                "firmware": [{
                    "file_path": str(firmware_path), "address": "0x10000",
                    "file_size": 999999, "md5": "0" * 32,
                }],
            }],
        }), encoding="utf-8")

        entry = load_project(str(path)).devices[0].firmware[0]
        assert entry.file_size == 64

    def test_missing_firmware_is_not_fatal_but_flagged(self, tmp_path):
        project = ProjectModel()
        device = DeviceConfig(name="Bench 1")
        device.add_firmware(FirmwareEntry(file_path=str(tmp_path / "ghost.bin"), address="0x1000"))
        project.add_device(device)

        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        restored = load_project(str(path))

        assert restored.devices[0].firmware[0].missing is True

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(ProjectLoadError):
            load_project(str(tmp_path / "nope.emfm"))

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.emfm"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ProjectLoadError):
            load_project(str(path))

    def test_load_adds_to_recent_projects(self, tmp_path):
        project = ProjectModel()
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        project_io.clear_recent_projects()
        assert project_io.get_recent_projects() == []
        load_project(str(path))
        assert str(path) in project_io.get_recent_projects()


class TestRecentProjects:
    def test_clear_recent_projects(self, tmp_path):
        project = ProjectModel()
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        project_io.clear_recent_projects()
        assert project_io.get_recent_projects() == []

    def test_recent_projects_filters_deleted_files(self, tmp_path):
        project = ProjectModel()
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        path.unlink()
        assert str(path) not in project_io.get_recent_projects()

    def test_recent_projects_most_recent_first_and_deduplicated(self, tmp_path):
        project = ProjectModel()
        project_io.clear_recent_projects()
        path_a = tmp_path / "a.emfm"
        path_b = tmp_path / "b.emfm"
        save_project(project, str(path_a))
        save_project(project, str(path_b))
        save_project(project, str(path_a))  # re-saving A should move it back to the front

        recents = project_io.get_recent_projects()
        assert recents[0] == str(path_a)
        assert recents.count(str(path_a)) == 1

    def test_recent_projects_capped_at_max(self, tmp_path):
        from app.utilities.constants import MAX_RECENT_PROJECTS

        project = ProjectModel()
        project_io.clear_recent_projects()
        for i in range(MAX_RECENT_PROJECTS + 5):
            path = tmp_path / f"project_{i}.emfm"
            save_project(project, str(path))
        assert len(project_io.get_recent_projects()) <= MAX_RECENT_PROJECTS

    def test_recent_projects_dedupe_across_slash_style(self, tmp_path):
        """C:/Users/sample.emfm and C:\\Users\\sample.emfm (or, portably,
        the same path saved once with forward slashes and once with
        backslashes) must be treated as the same Recent Projects entry --
        not two. Checked against the raw stored list (not
        get_recent_projects(), which also filters out paths that don't
        exist on disk with this OS's separator convention -- irrelevant
        to the dedup logic itself, which this test targets directly)."""
        from app.utilities.app_settings import get_settings

        project_io.clear_recent_projects()
        forward = "C:/Users/sample/project.emfm"
        backward = "C:\\Users\\sample\\project.emfm"

        project_io.add_recent_project(forward)
        project_io.add_recent_project(backward)

        stored = get_settings().value("recent_projects", [], type=list)
        assert len(stored) == 1

    def test_recent_projects_dedupe_keeps_most_recent_spelling_on_top(self, tmp_path):
        from app.utilities.app_settings import get_settings

        project_io.clear_recent_projects()
        forward = "C:/Users/sample/project.emfm"
        backward = "C:\\Users\\sample\\project.emfm"
        other = "C:/Users/sample/other.emfm"

        project_io.add_recent_project(forward)
        project_io.add_recent_project(other)
        project_io.add_recent_project(backward)  # re-"opening" the first path, spelled differently

        stored = get_settings().value("recent_projects", [], type=list)
        assert stored[0] == backward
        assert len(stored) == 2
