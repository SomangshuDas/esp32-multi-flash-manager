"""
auto_detect.py
===============
Scans a firmware folder and builds a list of FirmwareEntry objects,
automatically assigning well-known addresses to recognized filenames
(bootloader.bin, partition-table.bin, firmware.bin, ...) while leaving
unknown .bin files present but with an editable placeholder address so
the user can assign one manually.
"""

from __future__ import annotations

from pathlib import Path

from app.logging_setup.logger import get_logger
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import ESP32S3_BOOTLOADER_ADDRESS, ESP32S3_CHIP, KNOWN_FIRMWARE_ADDRESSES

logger = get_logger(__name__)

# Fallback address offered to unrecognized .bin files so the field is never
# blank; the user is expected to edit it before flashing (validator will
# flag duplicate/blank addresses).
UNKNOWN_BIN_PLACEHOLDER_ADDRESS = "0x0"

_BOOTLOADER_BIN_NAME = "bootloader.bin"


def resolve_bootloader_address(chip_type: str | None) -> str:
    """
    Return the correct default bootloader flash address for `chip_type`.

    Every chip except ESP32-S3 uses the classic 0x1000 convention. ESP32-S3
    boards have been observed to fail to boot (hang/reset loop) when the
    bootloader is flashed at 0x1000 -- flashing it at 0x0 instead fixes it,
    so that's what's offered by default whenever the chip is known to be an
    ESP32-S3 at the point a bootloader.bin is added/auto-detected.
    """
    if chip_type and chip_type.strip().lower() == ESP32S3_CHIP:
        return ESP32S3_BOOTLOADER_ADDRESS
    return KNOWN_FIRMWARE_ADDRESSES[_BOOTLOADER_BIN_NAME]


def scan_firmware_folder(folder_path: str, chip_type: str | None = None) -> list[FirmwareEntry]:
    """
    Scan `folder_path` (non-recursive) for .bin files and return a list of
    FirmwareEntry objects with addresses pre-assigned for recognized names.
    Recognized files are ordered by their flash address; unknown files are
    appended afterwards in alphabetical order.

    `chip_type` is the target device's chip (e.g. "esp32s3"), if known at
    scan time -- see resolve_bootloader_address(): it only changes the
    default address offered for a recognized `bootloader.bin`, nothing
    else. Pass None (the default) when no specific device/chip is known
    yet (e.g. Assign Firmware Set to Devices, which applies one imported
    set across possibly-mixed-chip devices) and every chip keeps the
    classic 0x1000 default.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        logger.warning("scan_firmware_folder called on non-directory: %s", folder_path)
        return []

    bin_files = sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".bin"],
        key=lambda f: f.name.lower(),
    )

    known: list[FirmwareEntry] = []
    unknown: list[FirmwareEntry] = []

    for bin_file in bin_files:
        lower_name = bin_file.name.lower()
        if lower_name == _BOOTLOADER_BIN_NAME:
            address = resolve_bootloader_address(chip_type)
        else:
            address = KNOWN_FIRMWARE_ADDRESSES.get(lower_name)
        entry = FirmwareEntry(file_path=str(bin_file), address=address or UNKNOWN_BIN_PLACEHOLDER_ADDRESS)
        entry.refresh()
        if address:
            known.append(entry)
        else:
            unknown.append(entry)

    # Sort known entries by their numeric address so bootloader comes first.
    known.sort(key=lambda e: int(e.address, 16))

    result = known + unknown
    logger.info(
        "Auto-detected %d firmware file(s) in %s (%d recognized, %d unknown)",
        len(result), folder_path, len(known), len(unknown),
    )
    return result
