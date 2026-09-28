"""
validator.py
=============
Pre-upload validation. Runs a battery of checks across the set of devices
that are about to be flashed and produces a structured ValidationReport
that the UI renders as a report dialog before allowing the upload to
proceed. Nothing here touches hardware — it is a pure, fast, offline
sanity check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.device_manager.port_scanner import get_port_device_names
from app.flash_engine.security_manager import validate_security_settings
from app.models.device_model import DeviceConfig
from app.utilities.constants import (
    BAUD_RATES,
    DEFAULT_BAUD,
    ESP32S3_BOOTLOADER_ADDRESS,
    ESP32S3_CHIP,
    SUPPORTED_CHIPS,
    FLASH_MODES,
)
from app.utilities.helpers import is_valid_hex_address, normalize_hex_address, validate_extra_esptool_args


class Severity(Enum):
    ERROR = "Error"
    WARNING = "Warning"


@dataclass
class ValidationIssue:
    severity: Severity
    device_name: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    # True when this report was produced by validate_devices(..., dry_run=True)
    # -- i.e. a "Validate Bench (Dry Run)" run rather than a real pre-upload
    # check. The UI (ValidationReportDialog) uses this to skip the
    # blocks-the-upload framing, since a dry run isn't gating anything.
    dry_run: bool = False

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    def add_error(self, device_name: str, message: str) -> None:
        self.issues.append(ValidationIssue(Severity.ERROR, device_name, message))

    def add_warning(self, device_name: str, message: str) -> None:
        self.issues.append(ValidationIssue(Severity.WARNING, device_name, message))


def validate_devices(
    devices: list[DeviceConfig],
    connected_ports: set[str] | None = None,
    monitor_ports: set[str] | None = None,
    supported_chips: list[str] | None = None,
    dry_run: bool = False,
) -> ValidationReport:
    """
    Validate a list of devices that are about to be flashed together.
    Returns a ValidationReport containing every issue found; the caller
    decides whether ERROR-level issues block the upload (they should).

    `connected_ports` is the set of serial ports currently visible to the
    OS (e.g. from PortWatcher's live scan). If omitted, a fresh scan is
    taken here so this function still works standalone/in tests. Passing
    it in lets the caller flag "port not connected" immediately when
    Upload is clicked, instead of only finding out ~10-30 seconds later
    when esptool's own connect-retry loop finally gives up.

    `monitor_ports` is the set of serial ports that currently have a
    connected Serial Monitor window open (see app/ui/serial_monitor.py).
    esptool cannot open a port that's already held open elsewhere, so any
    device whose port is in this set is flagged as an error telling the
    user to close that Serial Monitor before uploading.

    `supported_chips` is the dynamically-detected chip list from
    app.utilities.chip_detect (queried from the installed esptool at
    startup). If omitted, falls back to the hardcoded SUPPORTED_CHIPS
    constant so this function still works standalone/in tests.

    `dry_run` runs every other check exactly as normal but skips the
    live "is this port currently connected" check -- see ROADMAP.md's
    "Dry-run / pre-flight simulation mode" entry: this lets an operator
    validate a bench configuration (or review a project file someone else
    built) before any hardware is plugged in at all, or even connected to
    this machine. `connected_ports` is ignored when `dry_run` is True
    (every configured port is treated as "would be connected"); every
    other check (duplicate ports, chip/flash-mode/baud validity, firmware
    file presence, address overlaps, security settings, ...) still runs
    exactly as it would for a real upload.
    """
    report = ValidationReport(dry_run=dry_run)
    if dry_run:
        # A dry run cares about configuration correctness, not today's
        # live hardware state -- treat every device's configured port as
        # present so the "port not currently connected" check never fires
        # and doesn't drown out the checks that actually matter here.
        connected_ports = {d.com_port for d in devices if d.com_port}
    elif connected_ports is None:
        connected_ports = get_port_device_names()
    if monitor_ports is None:
        monitor_ports = set()
    if supported_chips is None:
        supported_chips = SUPPORTED_CHIPS

    # --- Duplicate port detection (only across devices being uploaded) ---
    port_usage: dict[str, list[str]] = {}
    for device in devices:
        if device.com_port:
            port_usage.setdefault(device.com_port, []).append(device.name)
    for port, names in port_usage.items():
        if len(names) > 1:
            for name in names:
                report.add_error(name, f"Port {port} is used by multiple devices: {', '.join(names)}")

    for device in devices:
        _validate_single_device(device, report, connected_ports, monitor_ports, supported_chips)
        _validate_single_device_security(device, report)

    return report


def _validate_single_device_security(device: DeviceConfig, report: ValidationReport) -> None:
    """
    Fold this device's flash-encryption/secure-boot foot-gun checks (see
    app/flash_engine/security_manager.py's validate_security_settings) into
    the same pre-upload report shown before Upload -- missing key files,
    no chip selected while security features are on, and flashing plaintext
    firmware to a device already read back as flash-encryption-enabled all
    surface here exactly like any other blocking pre-upload issue.
    """
    security_report = validate_security_settings(device)
    for issue in security_report.issues:
        if issue.is_error:
            report.add_error(device.name, issue.message)
        else:
            report.add_warning(device.name, issue.message)

    custom_efuse_error = validate_extra_esptool_args(device.security.custom_efuse_args)
    if custom_efuse_error:
        report.add_error(device.name, f"Custom eFuse arguments: {custom_efuse_error}")


_BAUD_RATE_MIN = 300
_BAUD_RATE_MAX = 5_000_000


def _validate_baud_rate(device: DeviceConfig, report: ValidationReport) -> None:
    """
    Baud rate was previously never checked here at all -- a corrupted,
    zero, or negative value (e.g. from a hand-edited or corrupted project
    file, or a stray empty edit in the baud rate combo box) only ever
    surfaced as an opaque esptool failure at flash time instead of a
    clear pre-upload error naming the actual bad field.

    The baud rate combo box is user-editable (not restricted to
    BAUD_RATES), so any positive value in a sane range is accepted as
    valid -- a value outside the standard preset list only gets a
    WARNING (it may simply be a custom baud a particular board/adapter
    needs), not an ERROR.
    """
    baud = device.baud_rate
    name = device.name
    if not isinstance(baud, int) or isinstance(baud, bool) or baud <= 0:
        report.add_error(name, f"Invalid baud rate: '{baud}'. Must be a positive whole number.")
        return
    if baud > _BAUD_RATE_MAX:
        report.add_error(
            name, f"Invalid baud rate: {baud}. That is larger than any real serial baud rate (max {_BAUD_RATE_MAX}).",
        )
        return
    if baud < _BAUD_RATE_MIN:
        report.add_error(
            name, f"Invalid baud rate: {baud}. That is too low for esptool to communicate reliably (min {_BAUD_RATE_MIN}).",
        )
        return
    if baud not in BAUD_RATES:
        report.add_warning(
            name,
            f"Baud rate {baud} is not one of the standard presets. If the upload fails to "
            f"connect, try a standard rate such as {DEFAULT_BAUD}.",
        )


def _validate_single_device(
    device: DeviceConfig,
    report: ValidationReport,
    connected_ports: set[str],
    monitor_ports: set[str],
    supported_chips: list[str],
) -> None:
    name = device.name

    if not device.com_port:
        report.add_error(name, "No port selected.")
    elif device.com_port not in connected_ports:
        report.add_error(
            name,
            f"Port {device.com_port} is not currently connected. Plug in the device, or "
            "select the correct port in Device Settings, then try again.",
        )
    elif device.com_port in monitor_ports:
        report.add_error(
            name,
            f"A Serial Monitor is currently open on port {device.com_port}. Close it before uploading.",
        )

    if device.chip_type not in supported_chips:
        report.add_error(
            name,
            f"Unsupported/invalid chip selection: '{device.chip_type}'. The installed esptool "
            f"does not report support for this chip -- supported chips: {', '.join(supported_chips)}.",
        )

    if device.flash_mode not in FLASH_MODES:
        report.add_error(name, f"Invalid flash mode: '{device.flash_mode}'.")

    _validate_baud_rate(device, report)

    custom_args_error = validate_extra_esptool_args(device.custom_flash_args)
    if custom_args_error:
        report.add_error(name, f"Custom flash arguments: {custom_args_error}")

    enabled = device.enabled_firmware()
    if not enabled:
        report.add_error(name, "No enabled firmware files to flash.")
        return

    # ESP32-S3 foot-gun: the bootloader must be flashed at 0x0 on this chip,
    # not the classic ESP32 0x1000 convention -- boards have been observed
    # to fail to boot (hang/reset loop) when it's left at 0x1000. Every
    # automatic assignment already routes through
    # auto_detect.resolve_bootloader_address() to get this right by
    # default; this only catches a manually-typed or imported 0x1000.
    if device.chip_type == ESP32S3_CHIP:
        for entry in enabled:
            if is_valid_hex_address(entry.address) and normalize_hex_address(entry.address) == "0x1000":
                report.add_warning(
                    name,
                    f"'{entry.file_name}' is assigned to 0x1000 on an ESP32-S3 device. ESP32-S3 "
                    f"boards can fail to boot with the bootloader at 0x1000 -- use "
                    f"{ESP32S3_BOOTLOADER_ADDRESS} instead.",
                )

    # Missing bootloader / partition table heuristic warnings (only relevant
    # for full-image flashing at address 0x1000 / 0x8000 conventions).
    # Addresses are compared by numeric value (normalize_hex_address), not
    # raw string, so e.g. an address typed/imported as "0x01000" is still
    # recognized as the conventional 0x1000 slot.
    addresses = {normalize_hex_address(e.address) for e in enabled if is_valid_hex_address(e.address)}
    has_low_address_image = any(int(a, 16) < 0x9000 for a in addresses)
    # A device can already carry a full merged image (bootloader +
    # partition table + app all baked into one .bin, typically flashed at
    # 0x0 via "Merge Bins") -- if any enabled, non-missing entry's byte
    # range already covers both the conventional bootloader (0x1000) and
    # partition-table (0x8000) addresses, it has already satisfied both,
    # and warning that neither has its own separate row would just be
    # redundant/confusing noise.
    has_merged_image = any(
        not e.missing
        and e.file_size > 0
        and is_valid_hex_address(e.address)
        and int(normalize_hex_address(e.address), 16) <= 0x1000
        and int(normalize_hex_address(e.address), 16) + e.file_size > 0x8000
        for e in enabled
    )
    if has_low_address_image and not has_merged_image:
        if "0x1000" not in addresses:
            report.add_warning(name, "No firmware assigned to 0x1000 (bootloader) — this may be intentional if flashing a merged image.")
        if "0x8000" not in addresses:
            report.add_warning(name, "No firmware assigned to 0x8000 (partition table) — this may be intentional if flashing a merged image.")

    # Per-file checks: missing files, invalid/duplicate addresses.
    seen_addresses: dict[str, str] = {}
    ranges: list[tuple[int, int, str]] = []  # (start, end_exclusive, file_name)
    for entry in enabled:
        if not entry.file_path:
            report.add_error(name, "A firmware row has no file selected.")
            continue
        if entry.missing:
            report.add_error(name, f"Firmware file missing on disk: {entry.file_path}")
        if not is_valid_hex_address(entry.address):
            report.add_error(name, f"Invalid flash address '{entry.address}' for {entry.file_name}.")
            continue
        norm = normalize_hex_address(entry.address)
        if norm in seen_addresses:
            report.add_error(
                name,
                f"Duplicate flash address {entry.address} used by both "
                f"'{seen_addresses[norm]}' and '{entry.file_name}'.",
            )
        else:
            seen_addresses[norm] = entry.file_name
        if not entry.missing and entry.file_size > 0:
            start = int(norm, 16)
            ranges.append((start, start + entry.file_size, entry.file_name))

    # Byte-range overlap detection. Two entries can use two different,
    # non-duplicate addresses and still stomp on each other once file size
    # is taken into account -- e.g. a full merged image (bootloader +
    # partition table + app already baked in) assigned to 0x0 alongside a
    # separate 'bootloader.bin' at the conventional 0x1000: 0x0's image is
    # almost always well past 4KB, so it swallows 0x1000 whole. esptool
    # itself refuses this at flash time ("Detected overlap at address...");
    # catching it here surfaces the same problem before anything is sent
    # to hardware, with enough context to explain *why* it overlaps.
    ranges.sort(key=lambda r: r[0])
    for (start_a, end_a, name_a), (start_b, end_b, name_b) in zip(ranges, ranges[1:]):
        if start_b < end_a:
            report.add_error(
                name,
                f"'{name_a}' (ends at 0x{end_a:x}) overlaps '{name_b}' (starts at "
                f"0x{start_b:x}). If '{name_a}' is a full merged image flashed at "
                "0x0, it already contains its own bootloader/partition table and "
                "should be the ONLY entry enabled for this device -- disable the "
                "separate bootloader.bin/partition-table.bin rows instead of "
                "flashing both.",
            )
