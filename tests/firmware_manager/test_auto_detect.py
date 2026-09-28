"""Unit tests for app/firmware_manager/auto_detect.py."""

from __future__ import annotations

from app.firmware_manager.auto_detect import (
    UNKNOWN_BIN_PLACEHOLDER_ADDRESS,
    resolve_bootloader_address,
    scan_firmware_folder,
)
from app.utilities.constants import ESP32S3_BOOTLOADER_ADDRESS, KNOWN_FIRMWARE_ADDRESSES


def _write(tmp_path, name: str, content: bytes = b"\x00" * 16):
    (tmp_path / name).write_bytes(content)


class TestScanFirmwareFolder:
    def test_nonexistent_directory_returns_empty_list(self, tmp_path):
        assert scan_firmware_folder(str(tmp_path / "does-not-exist")) == []

    def test_file_path_instead_of_directory_returns_empty_list(self, tmp_path):
        file_path = tmp_path / "not_a_dir.bin"
        file_path.write_bytes(b"\x00")
        assert scan_firmware_folder(str(file_path)) == []

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert scan_firmware_folder(str(tmp_path)) == []

    def test_non_bin_files_are_ignored(self, tmp_path):
        _write(tmp_path, "readme.txt")
        _write(tmp_path, "notes.md")
        assert scan_firmware_folder(str(tmp_path)) == []

    def test_recognizes_bootloader_bin(self, tmp_path):
        _write(tmp_path, "bootloader.bin")
        result = scan_firmware_folder(str(tmp_path))
        assert len(result) == 1
        assert result[0].address == KNOWN_FIRMWARE_ADDRESSES["bootloader.bin"]

    def test_recognizes_partition_table_bin(self, tmp_path):
        _write(tmp_path, "partition-table.bin")
        result = scan_firmware_folder(str(tmp_path))
        assert result[0].address == KNOWN_FIRMWARE_ADDRESSES["partition-table.bin"]

    def test_recognizes_ota_data_initial_bin(self, tmp_path):
        _write(tmp_path, "ota_data_initial.bin")
        result = scan_firmware_folder(str(tmp_path))
        assert result[0].address == KNOWN_FIRMWARE_ADDRESSES["ota_data_initial.bin"]

    def test_recognizes_firmware_bin(self, tmp_path):
        _write(tmp_path, "firmware.bin")
        result = scan_firmware_folder(str(tmp_path))
        assert result[0].address == KNOWN_FIRMWARE_ADDRESSES["firmware.bin"]

    def test_recognition_is_case_insensitive(self, tmp_path):
        _write(tmp_path, "BootLoader.BIN")
        result = scan_firmware_folder(str(tmp_path))
        assert result[0].address == KNOWN_FIRMWARE_ADDRESSES["bootloader.bin"]

    def test_unknown_bin_gets_placeholder_address(self, tmp_path):
        _write(tmp_path, "my_custom_app.bin")
        result = scan_firmware_folder(str(tmp_path))
        assert len(result) == 1
        assert result[0].address == UNKNOWN_BIN_PLACEHOLDER_ADDRESS

    def test_known_entries_sorted_by_address_bootloader_first(self, tmp_path):
        # Write in reverse address order to prove sorting, not just filename order.
        _write(tmp_path, "firmware.bin")
        _write(tmp_path, "partition-table.bin")
        _write(tmp_path, "bootloader.bin")
        result = scan_firmware_folder(str(tmp_path))
        addresses = [int(e.address, 16) for e in result]
        assert addresses == sorted(addresses)
        assert result[0].file_name == "bootloader.bin"

    def test_known_entries_come_before_unknown_entries(self, tmp_path):
        _write(tmp_path, "z_unknown.bin")
        _write(tmp_path, "firmware.bin")
        result = scan_firmware_folder(str(tmp_path))
        assert result[0].file_name == "firmware.bin"
        assert result[1].file_name == "z_unknown.bin"

    def test_multiple_unknown_files_sorted_alphabetically(self, tmp_path):
        _write(tmp_path, "zzz.bin")
        _write(tmp_path, "aaa.bin")
        _write(tmp_path, "mmm.bin")
        result = scan_firmware_folder(str(tmp_path))
        names = [e.file_name for e in result]
        assert names == ["aaa.bin", "mmm.bin", "zzz.bin"]

    def test_entries_are_refreshed_with_real_file_size(self, tmp_path):
        _write(tmp_path, "firmware.bin", content=b"\xAB" * 128)
        result = scan_firmware_folder(str(tmp_path))
        assert result[0].file_size == 128
        assert result[0].missing is False

    def test_subdirectories_are_not_recursed_into(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        _write(sub, "firmware.bin")
        result = scan_firmware_folder(str(tmp_path))
        assert result == []

    def test_bootloader_uses_classic_address_by_default(self, tmp_path):
        _write(tmp_path, "bootloader.bin")
        result = scan_firmware_folder(str(tmp_path))
        assert result[0].address == "0x1000"

    def test_bootloader_uses_classic_address_for_non_s3_chip(self, tmp_path):
        _write(tmp_path, "bootloader.bin")
        result = scan_firmware_folder(str(tmp_path), chip_type="esp32")
        assert result[0].address == "0x1000"

    def test_bootloader_uses_0x0_for_esp32s3(self, tmp_path):
        _write(tmp_path, "bootloader.bin")
        result = scan_firmware_folder(str(tmp_path), chip_type="esp32s3")
        assert result[0].address == ESP32S3_BOOTLOADER_ADDRESS

    def test_bootloader_chip_match_is_case_insensitive(self, tmp_path):
        _write(tmp_path, "bootloader.bin")
        result = scan_firmware_folder(str(tmp_path), chip_type="ESP32S3")
        assert result[0].address == ESP32S3_BOOTLOADER_ADDRESS

    def test_esp32s3_only_affects_bootloader_address(self, tmp_path):
        _write(tmp_path, "bootloader.bin")
        _write(tmp_path, "partition-table.bin")
        _write(tmp_path, "firmware.bin")
        result = scan_firmware_folder(str(tmp_path), chip_type="esp32s3")
        by_name = {e.file_name: e.address for e in result}
        assert by_name["bootloader.bin"] == ESP32S3_BOOTLOADER_ADDRESS
        assert by_name["partition-table.bin"] == KNOWN_FIRMWARE_ADDRESSES["partition-table.bin"]
        assert by_name["firmware.bin"] == KNOWN_FIRMWARE_ADDRESSES["firmware.bin"]


class TestResolveBootloaderAddress:
    def test_none_chip_type_returns_classic_address(self):
        assert resolve_bootloader_address(None) == "0x1000"

    def test_empty_chip_type_returns_classic_address(self):
        assert resolve_bootloader_address("") == "0x1000"

    def test_esp32_returns_classic_address(self):
        assert resolve_bootloader_address("esp32") == "0x1000"

    def test_esp32s3_returns_0x0(self):
        assert resolve_bootloader_address("esp32s3") == ESP32S3_BOOTLOADER_ADDRESS

    def test_esp32s3_is_case_and_whitespace_insensitive(self):
        assert resolve_bootloader_address("  ESP32S3  ") == ESP32S3_BOOTLOADER_ADDRESS
