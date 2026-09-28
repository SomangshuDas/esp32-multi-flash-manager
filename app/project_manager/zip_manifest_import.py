"""
zip_manifest_import.py
========================
Zip + manifest bulk-flashing import (Devices -> Import Firmware Bundle
(.zip)...). Accepts a single .zip containing firmware binaries plus a
manifest.csv (device name/tag -> firmware+address mapping) and
materializes it into a full device list + firmware assignment in one
import step -- useful for shipping "everything needed for this
production run" as one file to a remote operator, instead of separately
distributing a firmware folder and a device CSV and asking the operator
to wire the two together by hand.

Conceptually an extension of csv_import.py (device rows, same
skip-bad-rows-not-whole-file error model) plus
firmware_manager/auto_detect.py's folder-to-firmware-list resolution
(recognized filenames still get their well-known address as a default,
though the manifest is expected to specify addresses explicitly).

MANIFEST FORMAT (manifest.csv, at the root of the .zip)
---------------------------------------------------------
One header row, then one data row per (device, firmware file) pair -- a
device with three firmware files assigned occupies three consecutive (or
not -- order doesn't matter) rows sharing the same device_name, mirroring
how a real production run's spreadsheet is usually laid out. Recognized
columns (case-insensitive; see ZIP_MANIFEST_COLUMNS in constants.py):

    device_name     - device display name (required, non-blank)
    tags            - semicolon-separated tags, e.g. "Line A;RFID Batch"
                       (optional; only needs to be set on one row per
                       device -- if set on more than one row for the same
                       device, the tag sets are merged)
    chip_type       - e.g. "esp32", "esp32s3" (optional, falls back to
                       DEFAULT_CHIP; only needs to be set on one row per
                       device -- first non-blank value wins)
    firmware_file   - filename of a .bin somewhere in the .zip (required,
                       non-blank, must resolve to a file that was
                       actually in the archive)
    address         - flash address for this file, e.g. "0x10000"
                       (optional -- falls back to the same well-known
                       KNOWN_FIRMWARE_ADDRESSES lookup auto_detect.py uses
                       for recognized filenames, or "0x0" if unrecognized)
    enabled         - "true"/"false" (optional, defaults to true)

Untrusted-input hardening: a .zip bundle can arrive from anywhere (email,
USB stick, a shared network folder) the same as a .emfm project file (see
docs/THREAT_MODEL.md), so this module bounds both the archive's total
uncompressed size (MAX_ZIP_BUNDLE_SIZE_BYTES) and the manifest's row count
(MAX_ZIP_MANIFEST_ROWS) before extracting/parsing anything, and rejects
any archive member whose path would resolve outside the extraction
directory ("zip slip") rather than silently ignoring or half-extracting
it.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.firmware_manager.auto_detect import resolve_bootloader_address
from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import (
    DEFAULT_CHIP,
    KNOWN_FIRMWARE_ADDRESSES,
    MAX_ZIP_BUNDLE_SIZE_BYTES,
    MAX_ZIP_MANIFEST_ROWS,
    ZIP_MANIFEST_FILENAME,
)
from app.utilities.helpers import get_app_data_dir, new_uuid

logger = get_logger(__name__)

_UNKNOWN_BIN_PLACEHOLDER_ADDRESS = "0x0"


@dataclass
class ZipManifestImportResult:
    devices: list[DeviceConfig] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    extracted_dir: str = ""

    @property
    def imported_count(self) -> int:
        return len(self.devices)


class ZipManifestImportError(Exception):
    """Archive-level failure (missing manifest, corrupt zip, oversized
    bundle, ...) as opposed to a per-row data-quality issue, which is
    instead reported via ZipManifestImportResult.errors so one bad row
    doesn't block the rest of a large bundle."""


def import_devices_from_zip_bundle(zip_path: str | Path) -> ZipManifestImportResult:
    """Extract `zip_path` under the app data folder and return the
    devices its manifest describes, plus any per-row errors. Raises
    ZipManifestImportError for archive-level problems (bad zip, missing
    manifest, bundle too large); per-row problems are reported in the
    returned result instead."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise ZipManifestImportError(f"File not found: {zip_path}")

    try:
        with zipfile.ZipFile(zip_path) as archive:
            total_uncompressed = sum(info.file_size for info in archive.infolist())
            if total_uncompressed > MAX_ZIP_BUNDLE_SIZE_BYTES:
                raise ZipManifestImportError(
                    f"Bundle is too large ({total_uncompressed:,} bytes uncompressed, "
                    f"limit is {MAX_ZIP_BUNDLE_SIZE_BYTES:,})."
                )

            extract_dir = _new_extraction_dir(zip_path.stem)
            _safe_extract_all(archive, extract_dir)
    except zipfile.BadZipFile as exc:
        raise ZipManifestImportError(f"Not a valid .zip file: {exc}") from exc

    manifest_path = _find_manifest(extract_dir)
    if manifest_path is None:
        raise ZipManifestImportError(
            f'No "{ZIP_MANIFEST_FILENAME}" found in the bundle. '
            "Every firmware bundle must include a manifest CSV at its root "
            "(or in a single top-level folder)."
        )

    file_index = _index_bin_files(extract_dir)
    result = ZipManifestImportResult(extracted_dir=str(extract_dir))
    _parse_manifest(manifest_path, file_index, result)
    logger.info(
        "Zip bundle import of %s: %d device(s) imported, %d error(s)",
        zip_path, result.imported_count, len(result.errors),
    )
    return result


# ------------------------------------------------------------------
def _new_extraction_dir(bundle_stem: str) -> Path:
    safe_stem = "".join(c for c in bundle_stem if c.isalnum() or c in ("-", "_")) or "bundle"
    extract_dir = get_app_data_dir() / "imported_firmware_bundles" / f"{safe_stem}_{new_uuid()[:8]}"
    extract_dir.mkdir(parents=True, exist_ok=True)
    return extract_dir


def _safe_extract_all(archive: zipfile.ZipFile, extract_dir: Path) -> None:
    """Extract every member of `archive` into `extract_dir`, refusing any
    member whose resolved path would land outside `extract_dir` (a
    maliciously-crafted "zip slip" entry using "../" or an absolute path)
    rather than silently skipping or half-trusting it."""
    extract_dir = extract_dir.resolve()
    for member in archive.infolist():
        if member.is_dir():
            continue
        target = (extract_dir / member.filename).resolve()
        if extract_dir not in target.parents and target != extract_dir:
            raise ZipManifestImportError(
                f"Refusing to extract unsafe archive entry outside the bundle: {member.filename}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, open(target, "wb") as dest:
            dest.write(source.read())


def _find_manifest(extract_dir: Path) -> Path | None:
    matches = [p for p in extract_dir.rglob("*") if p.is_file() and p.name.lower() == ZIP_MANIFEST_FILENAME]
    return matches[0] if matches else None


def _index_bin_files(extract_dir: Path) -> dict[str, Path]:
    """filename (lowercase) -> path, for every .bin anywhere in the
    extracted tree. A manifest referencing a duplicate filename that
    appears in more than one subfolder resolves to whichever was indexed
    last -- rare enough in a real bundle that a warning (not an error) is
    sufficient."""
    index: dict[str, Path] = {}
    duplicates = set()
    for path in extract_dir.rglob("*.bin"):
        key = path.name.lower()
        if key in index and index[key] != path:
            duplicates.add(key)
        index[key] = path
    if duplicates:
        logger.warning(
            "Zip bundle contains firmware files with duplicate names in different "
            "subfolders: %s (using the last one found for each)",
            ", ".join(sorted(duplicates)),
        )
    return index


class _RowError(ValueError):
    pass


def _parse_manifest(manifest_path: Path, file_index: dict[str, Path], result: ZipManifestImportResult) -> None:
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            result.errors.append("Manifest CSV has no header row.")
            return
        header_map = {h.strip().lower(): h for h in reader.fieldnames if h}
        if "device_name" not in header_map or "firmware_file" not in header_map:
            result.errors.append('Manifest CSV must have "device_name" and "firmware_file" columns.')
            return

        devices_by_name: dict[str, DeviceConfig] = {}
        order: list[str] = []
        row_count = 0
        for row_number, row in enumerate(reader, start=1):
            row_count += 1
            if row_count > MAX_ZIP_MANIFEST_ROWS:
                result.errors.append(
                    f"Manifest exceeds the maximum of {MAX_ZIP_MANIFEST_ROWS} rows; "
                    "remaining rows were ignored."
                )
                break
            try:
                _apply_row(row, header_map, file_index, devices_by_name, order)
            except _RowError as exc:
                result.errors.append(f"Row {row_number}: {exc}")

        result.devices = [devices_by_name[name] for name in order]


def _apply_row(
    row: dict,
    header_map: dict[str, str],
    file_index: dict[str, Path],
    devices_by_name: dict[str, DeviceConfig],
    order: list[str],
) -> None:
    def get(column: str) -> str:
        header = header_map.get(column)
        if header is None:
            return ""
        return (row.get(header) or "").strip()

    device_name = get("device_name")
    if not device_name:
        raise _RowError('missing required "device_name" value')

    firmware_file = get("firmware_file")
    if not firmware_file:
        raise _RowError('missing required "firmware_file" value')

    resolved = file_index.get(Path(firmware_file).name.lower())
    if resolved is None:
        raise _RowError(f'firmware file "{firmware_file}" was not found anywhere in the bundle')

    device = devices_by_name.get(device_name)
    if device is None:
        device = DeviceConfig(name=device_name, chip_type=get("chip_type") or DEFAULT_CHIP)
        devices_by_name[device_name] = device
        order.append(device_name)
    else:
        chip_type = get("chip_type")
        if chip_type and device.chip_type == DEFAULT_CHIP:
            device.chip_type = chip_type

    tags_raw = get("tags")
    if tags_raw:
        for tag in (t.strip() for t in tags_raw.split(";")):
            if tag and tag not in device.tags:
                device.tags.append(tag)

    if resolved.name.lower() == "bootloader.bin":
        # See resolve_bootloader_address(): ESP32-S3 needs 0x0, not the
        # classic 0x1000 -- this device's chip_type is already known by
        # now (set above, from this row or an earlier one for the same
        # device_name).
        default_address = resolve_bootloader_address(device.chip_type)
    else:
        default_address = KNOWN_FIRMWARE_ADDRESSES.get(resolved.name.lower(), _UNKNOWN_BIN_PLACEHOLDER_ADDRESS)
    address = get("address") or default_address
    enabled_raw = get("enabled")
    enabled = enabled_raw.strip().lower() not in ("false", "0", "no") if enabled_raw else True

    entry = FirmwareEntry(file_path=str(resolved), address=address, enabled=enabled)
    entry.refresh()
    device.add_firmware(entry)
