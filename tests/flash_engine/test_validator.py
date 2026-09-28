"""
Unit tests for app/flash_engine/validator.py.

`validate_devices()` is a pure function once `connected_ports`,
`monitor_ports`, and `supported_chips` are supplied explicitly, so every
test here passes them in rather than depending on a real serial port scan
or the installed esptool's chip list.
"""

from __future__ import annotations

from app.flash_engine.validator import Severity, validate_devices
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import FLASH_MODES, SUPPORTED_CHIPS

CHIPS = list(SUPPORTED_CHIPS)
MODE = FLASH_MODES[0]


def _firmware(address: str, size: int = 0x1000, missing: bool = False, enabled: bool = True) -> FirmwareEntry:
    entry = FirmwareEntry(file_path=f"/tmp/{address}.bin", address=address, enabled=enabled)
    entry.file_size = size
    entry.missing = missing
    return entry


def _device(name="Device", com_port="COM3", chip_type=None, flash_mode=None, firmware=None) -> DeviceConfig:
    device = DeviceConfig(
        name=name, com_port=com_port,
        chip_type=chip_type or CHIPS[0], flash_mode=flash_mode or MODE,
    )
    for entry in firmware or []:
        device.add_firmware(entry)
    return device


def _errors_for(report, device_name: str) -> list[str]:
    return [i.message for i in report.issues if i.severity == Severity.ERROR and i.device_name == device_name]


def _warnings_for(report, device_name: str) -> list[str]:
    return [i.message for i in report.issues if i.severity == Severity.WARNING and i.device_name == device_name]


class TestPortValidation:
    def test_no_port_selected_is_error(self):
        device = _device(com_port="", firmware=[_firmware("0x1000")])
        report = validate_devices([device], connected_ports=set(), monitor_ports=set(), supported_chips=CHIPS)
        assert any("No port selected" in m for m in _errors_for(report, "Device"))

    def test_port_not_connected_is_error(self):
        device = _device(com_port="COM9", firmware=[_firmware("0x1000")])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("not currently connected" in m for m in _errors_for(report, "Device"))

    def test_connected_port_produces_no_port_error(self):
        device = _device(com_port="COM3", firmware=[_firmware("0x1000")])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not any("not currently connected" in m or "No port selected" in m for m in _errors_for(report, "Device"))

    def test_port_open_in_serial_monitor_is_error(self):
        device = _device(com_port="COM3", firmware=[_firmware("0x1000")])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports={"COM3"}, supported_chips=CHIPS)
        assert any("Serial Monitor" in m for m in _errors_for(report, "Device"))

    def test_duplicate_ports_across_devices_flagged_on_both(self):
        a = _device(name="A", com_port="COM3", firmware=[_firmware("0x1000")])
        b = _device(name="B", com_port="COM3", firmware=[_firmware("0x1000")])
        report = validate_devices([a, b], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("used by multiple devices" in m for m in _errors_for(report, "A"))
        assert any("used by multiple devices" in m for m in _errors_for(report, "B"))

    def test_distinct_ports_not_flagged_as_duplicate(self):
        a = _device(name="A", com_port="COM3", firmware=[_firmware("0x1000")])
        b = _device(name="B", com_port="COM4", firmware=[_firmware("0x1000")])
        report = validate_devices([a, b], connected_ports={"COM3", "COM4"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not any("used by multiple devices" in m for m in _errors_for(report, "A"))
        assert not any("used by multiple devices" in m for m in _errors_for(report, "B"))

    def test_two_devices_with_no_port_are_not_treated_as_duplicates(self):
        """Empty-string ports must not be lumped together as 'the same
        port' since neither device actually has one selected."""
        a = _device(name="A", com_port="", firmware=[_firmware("0x1000")])
        b = _device(name="B", com_port="", firmware=[_firmware("0x1000")])
        report = validate_devices([a, b], connected_ports=set(), monitor_ports=set(), supported_chips=CHIPS)
        assert not any("used by multiple devices" in m for m in _errors_for(report, "A"))


class TestChipAndModeValidation:
    def test_unsupported_chip_is_error(self):
        device = _device(chip_type="esp99-imaginary", firmware=[_firmware("0x1000")])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Unsupported/invalid chip" in m for m in _errors_for(report, "Device"))

    def test_supported_chip_produces_no_chip_error(self):
        device = _device(chip_type=CHIPS[0], firmware=[_firmware("0x1000")])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not any("Unsupported/invalid chip" in m for m in _errors_for(report, "Device"))

    def test_invalid_flash_mode_is_error(self):
        device = _device(flash_mode="bogus-mode", firmware=[_firmware("0x1000")])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Invalid flash mode" in m for m in _errors_for(report, "Device"))


class TestFirmwareValidation:
    def test_no_enabled_firmware_is_error(self):
        device = _device(firmware=[])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("No enabled firmware" in m for m in _errors_for(report, "Device"))

    def test_all_firmware_disabled_counts_as_none_enabled(self):
        device = _device(firmware=[_firmware("0x1000", enabled=False)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("No enabled firmware" in m for m in _errors_for(report, "Device"))

    def test_missing_firmware_file_is_error(self):
        device = _device(firmware=[_firmware("0x1000", missing=True)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("missing on disk" in m for m in _errors_for(report, "Device"))

    def test_firmware_row_without_file_path_is_error(self):
        device = _device()
        entry = FirmwareEntry(file_path="", address="0x1000")
        device.add_firmware(entry)
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("no file selected" in m for m in _errors_for(report, "Device"))

    def test_invalid_address_is_error(self):
        device = _device(firmware=[_firmware("not-an-address")])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Invalid flash address" in m for m in _errors_for(report, "Device"))

    def test_duplicate_addresses_flagged(self):
        device = _device(firmware=[_firmware("0x10000", size=0x1000), _firmware("0x10000", size=0x1000)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Duplicate flash address" in m for m in _errors_for(report, "Device"))

    def test_duplicate_address_case_insensitive(self):
        device = _device(firmware=[_firmware("0x10000"), _firmware("0X10000")])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Duplicate flash address" in m for m in _errors_for(report, "Device"))

    def test_distinct_non_overlapping_addresses_are_fine(self):
        device = _device(firmware=[
            _firmware("0x1000", size=0x1000),
            _firmware("0x8000", size=0x1000),
            _firmware("0x10000", size=0x1000),
        ])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not report.has_errors

    def test_overlapping_regions_flagged(self):
        # A "merged" image at 0x0 that is larger than the gap to 0x1000
        # swallows the conventional bootloader address whole.
        device = _device(firmware=[
            _firmware("0x0", size=0x4000),
            _firmware("0x1000", size=0x1000),
        ])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("overlaps" in m for m in _errors_for(report, "Device"))

    def test_exactly_adjacent_regions_do_not_overlap(self):
        device = _device(firmware=[
            _firmware("0x1000", size=0x7000),  # ends exactly at 0x8000
            _firmware("0x8000", size=0x1000),
        ])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not any("overlaps" in m for m in _errors_for(report, "Device"))

    def test_missing_bootloader_and_partition_table_warn_when_low_address_present(self):
        device = _device(firmware=[_firmware("0x2000", size=0x1000)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert any("0x1000 (bootloader)" in m for m in warnings)
        assert any("0x8000 (partition table)" in m for m in warnings)

    def test_no_warning_when_bootloader_and_partition_table_present(self):
        device = _device(firmware=[
            _firmware("0x1000", size=0x1000),
            _firmware("0x8000", size=0x1000),
        ])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert not any("bootloader" in m or "partition table" in m for m in warnings)

    def test_no_bootloader_warning_when_only_high_addresses_used(self):
        """A merged-image-only device (single entry at e.g. 0x10000, no
        addresses below 0x9000) shouldn't get the 'no bootloader at
        0x1000' warning -- that heuristic only applies when there IS a
        low-address image implying a non-merged layout."""
        device = _device(firmware=[_firmware("0x10000", size=0x1000)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert not any("bootloader" in m or "partition table" in m for m in warnings)

    def test_no_bootloader_warning_when_merged_bin_covers_the_region(self):
        """A full merged image (e.g. from Merge Bins) flashed at 0x0, large
        enough to cover both the conventional bootloader and partition
        table addresses, already satisfies both -- warning that neither
        has its own separate row would just be redundant noise."""
        device = _device(firmware=[_firmware("0x0", size=0x9000)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert not any("bootloader" in m or "partition table" in m for m in warnings)

    def test_bootloader_warning_still_fires_when_merged_bin_too_small(self):
        """A small file at a low address that does NOT actually cover the
        bootloader/partition-table region should not be treated as a
        merged image -- the warning should still fire."""
        device = _device(firmware=[_firmware("0x0", size=0x100)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert any("0x1000 (bootloader)" in m for m in warnings)
        assert any("0x8000 (partition table)" in m for m in warnings)

    def test_address_comparisons_ignore_leading_zero_padding(self):
        """An address typed/imported with extra leading zeros (e.g.
        '0x01000') must still be recognized as the conventional 0x1000
        bootloader slot, not flagged as if nothing were assigned there."""
        device = _device(firmware=[
            _firmware("0x01000", size=0x1000),
            _firmware("0x8000", size=0x1000),
        ])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert not any("bootloader" in m or "partition table" in m for m in warnings)

    def test_duplicate_address_ignores_leading_zero_padding(self):
        device = _device(firmware=[_firmware("0x1000"), _firmware("0x001000")])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Duplicate flash address" in m for m in _errors_for(report, "Device"))


class TestEsp32S3BootloaderAddressWarning:
    def test_warns_when_bootloader_at_0x1000_on_esp32s3(self):
        device = _device(chip_type="esp32s3", firmware=[_firmware("0x1000", size=0x1000)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert any("0x1000" in m and "ESP32-S3" in m for m in warnings)

    def test_no_warning_when_bootloader_at_0x0_on_esp32s3(self):
        device = _device(chip_type="esp32s3", firmware=[_firmware("0x0", size=0x1000)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert not any("ESP32-S3" in m for m in warnings)

    def test_no_warning_for_0x1000_on_non_s3_chip(self):
        device = _device(chip_type="esp32", firmware=[_firmware("0x1000", size=0x1000)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert not any("ESP32-S3" in m for m in warnings)

    def test_warns_regardless_of_address_padding(self):
        device = _device(chip_type="esp32s3", firmware=[_firmware("0x01000", size=0x1000)])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        warnings = _warnings_for(report, "Device")
        assert any("ESP32-S3" in m for m in warnings)


class TestBaudRateValidation:
    def test_zero_baud_is_error(self):
        device = _device(firmware=[_firmware("0x1000")])
        device.baud_rate = 0
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Invalid baud rate" in m for m in _errors_for(report, "Device"))

    def test_negative_baud_is_error(self):
        device = _device(firmware=[_firmware("0x1000")])
        device.baud_rate = -115200
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Invalid baud rate" in m for m in _errors_for(report, "Device"))

    def test_absurdly_large_baud_is_error(self):
        device = _device(firmware=[_firmware("0x1000")])
        device.baud_rate = 999_999_999
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Invalid baud rate" in m for m in _errors_for(report, "Device"))

    def test_standard_baud_has_no_error_or_warning(self):
        device = _device(firmware=[_firmware("0x1000")])
        device.baud_rate = 115200
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not _errors_for(report, "Device")
        assert not any("baud" in m.lower() for m in _warnings_for(report, "Device"))

    def test_nonstandard_baud_is_warning_not_error(self):
        device = _device(firmware=[_firmware("0x1000")])
        device.baud_rate = 123456
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not any("Invalid baud rate" in m for m in _errors_for(report, "Device"))
        assert any("baud" in m.lower() for m in _warnings_for(report, "Device"))


class TestCustomFlashArgsValidation:
    def test_safe_custom_args_produce_no_error(self):
        device = _device(firmware=[_firmware("0x1000")])
        device.custom_flash_args = "--no-progress"
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not any("Custom flash arguments" in m for m in _errors_for(report, "Device"))

    def test_blocked_flag_in_custom_args_is_error(self):
        device = _device(firmware=[_firmware("0x1000")])
        device.custom_flash_args = "--port /dev/ttyFAKE"
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert any("Custom flash arguments" in m for m in _errors_for(report, "Device"))

    def test_empty_custom_args_produce_no_error(self):
        device = _device(firmware=[_firmware("0x1000")])
        device.custom_flash_args = ""
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not any("Custom flash arguments" in m for m in _errors_for(report, "Device"))


class TestFullyValidDevice:
    def test_clean_device_has_no_errors_or_warnings(self):
        device = _device(firmware=[
            _firmware("0x1000", size=0x1000),
            _firmware("0x8000", size=0x1000),
            _firmware("0x10000", size=0x1000),
        ])
        report = validate_devices([device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS)
        assert not report.has_errors
        assert not report.has_warnings

    def test_empty_device_list_produces_empty_report(self):
        report = validate_devices([], connected_ports=set(), monitor_ports=set(), supported_chips=CHIPS)
        assert report.issues == []
        assert not report.has_errors
        assert not report.has_warnings


class TestDryRun:
    """Dry-run / pre-flight simulation mode (Tools -> Validate Bench (Dry
    Run)...) -- see ROADMAP.md's corresponding entry. dry_run=True must
    skip only the live "is this port currently connected" check; every
    other check still runs exactly as it would for a real upload."""

    def test_dry_run_ignores_disconnected_port(self):
        device = _device(com_port="COM9", firmware=[_firmware("0x1000")])
        report = validate_devices(
            [device], connected_ports=set(), monitor_ports=set(), supported_chips=CHIPS, dry_run=True,
        )
        assert _errors_for(report, "Device") == []

    def test_non_dry_run_still_flags_disconnected_port(self):
        device = _device(com_port="COM9", firmware=[_firmware("0x1000")])
        report = validate_devices(
            [device], connected_ports=set(), monitor_ports=set(), supported_chips=CHIPS, dry_run=False,
        )
        assert any("not currently connected" in m.lower() or "not connected" in m.lower() for m in
                    _errors_for(report, "Device")) or report.has_errors

    def test_dry_run_report_carries_dry_run_flag(self):
        device = _device(firmware=[_firmware("0x1000")])
        report = validate_devices([device], monitor_ports=set(), supported_chips=CHIPS, dry_run=True)
        assert report.dry_run is True

    def test_non_dry_run_report_flag_defaults_false(self):
        device = _device(firmware=[_firmware("0x1000")])
        report = validate_devices(
            [device], connected_ports={"COM3"}, monitor_ports=set(), supported_chips=CHIPS,
        )
        assert report.dry_run is False

    def test_dry_run_still_catches_duplicate_ports(self):
        a = _device(name="A", com_port="COM3", firmware=[_firmware("0x1000")])
        b = _device(name="B", com_port="COM3", firmware=[_firmware("0x1000")])
        report = validate_devices([a, b], monitor_ports=set(), supported_chips=CHIPS, dry_run=True)
        assert any("multiple devices" in m for m in _errors_for(report, "A"))

    def test_dry_run_still_catches_missing_firmware_file(self):
        device = _device(firmware=[_firmware("0x1000", missing=True)])
        report = validate_devices([device], monitor_ports=set(), supported_chips=CHIPS, dry_run=True)
        assert report.has_errors

    def test_dry_run_still_catches_unsupported_chip(self):
        device = _device(chip_type="not_a_real_chip", firmware=[_firmware("0x1000")])
        report = validate_devices([device], monitor_ports=set(), supported_chips=CHIPS, dry_run=True)
        assert report.has_errors

    def test_dry_run_with_no_configured_port_is_still_an_error(self):
        # dry_run only skips the "is this port CURRENTLY connected" check
        # -- a device with no port configured at all is still invalid.
        device = _device(com_port="", firmware=[_firmware("0x1000")])
        report = validate_devices([device], monitor_ports=set(), supported_chips=CHIPS, dry_run=True)
        assert any("No port selected" in m for m in _errors_for(report, "Device"))

    def test_dry_run_still_respects_monitor_port_conflict(self):
        device = _device(com_port="COM3", firmware=[_firmware("0x1000")])
        report = validate_devices(
            [device], monitor_ports={"COM3"}, supported_chips=CHIPS, dry_run=True,
        )
        assert report.has_errors
