"""Tests for FirmwareEntry's disk-derived (never persisted) size/MD5 fields."""

from __future__ import annotations

from app.models.firmware_model import FirmwareEntry


class TestDynamicFileSize:
    def test_to_dict_omits_file_size_and_md5(self, tmp_path):
        bin_path = tmp_path / "app.bin"
        bin_path.write_bytes(b"\x00" * 32)
        entry = FirmwareEntry(file_path=str(bin_path), address="0x10000")
        entry.refresh()
        assert entry.file_size == 32

        data = entry.to_dict()
        assert "file_size" not in data
        assert "md5" not in data

    def test_from_dict_ignores_stored_file_size(self, tmp_path):
        bin_path = tmp_path / "app.bin"
        bin_path.write_bytes(b"\x00" * 32)
        entry = FirmwareEntry.from_dict(
            {"file_path": str(bin_path), "address": "0x10000", "file_size": 123456}
        )
        assert entry.file_size == 32

    def test_refresh_picks_up_size_change_on_disk(self, tmp_path):
        bin_path = tmp_path / "app.bin"
        bin_path.write_bytes(b"\x00" * 10)
        entry = FirmwareEntry(file_path=str(bin_path), address="0x10000")
        entry.refresh()
        assert entry.file_size == 10

        bin_path.write_bytes(b"\x00" * 20)
        entry.refresh()
        assert entry.file_size == 20

    def test_missing_file_has_zero_size(self, tmp_path):
        entry = FirmwareEntry.from_dict(
            {"file_path": str(tmp_path / "ghost.bin"), "address": "0x1000", "file_size": 777}
        )
        assert entry.missing is True
        assert entry.file_size == 0
