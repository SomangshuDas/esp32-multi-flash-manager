"""
esptool_wrapper.py
===================
The single point of contact with the official `esptool` package.

Design decision: esptool is invoked as an OUT-OF-PROCESS subprocess
(``python -m esptool ...``) rather than calling ``esptool.main()``
in-process. Reasons:

  1. esptool writes progress using carriage-return ("\\r") updates and
     calls sys.exit() internally on failure — none of that plays nicely
     with a Qt GUI thread or with running many devices in parallel.
  2. A crashed/hung esptool subprocess can be killed cleanly (Cancel
     button) without taking down the whole application.
  3. Raw, unmodified esptool console output can be shown verbatim in the
     "Live Output" console, which is an explicit requirement.

FlashCommandBuilder turns a DeviceConfig into the exact esptool argument
list. FlashProcess wraps subprocess.Popen and exposes a line-by-line
iterator plus a parser that extracts structured progress events from
esptool's stdout.
"""

from __future__ import annotations

import queue
import re
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Iterator

from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.utilities.constants import ESPEFUSE_REEXEC_FLAG, ESPSECURE_REEXEC_FLAG, ESPTOOL_REEXEC_FLAG
from app.utilities.helpers import validate_extra_esptool_args

logger = get_logger(__name__)

# --------------------------------------------------------------------------
# Regexes used to turn raw esptool stdout lines into structured progress.
#
# esptool's own progress-line format has changed across major versions, and
# several are seen in the wild depending on which esptool build a machine
# has:
#
#   legacy (esptool < 5):
#     "Writing at 0x00010000... (42 %)"
#   esptool 5.0-5.3 (rich-based progress bar, bracketed, plain-text when
#   piped):
#     "Writing at 0x00001000 [ ] 0.0% 0/13104 bytes..."
#     "Writing at 0x00005a30 [==============================] 100.0% 13104/13104 bytes..."
#   current (esptool 5.4+, delegates rendering to esp-pylib's EspLog --
#   the bar itself is unbracketed block-character glyphs padded with
#   spaces, one full line per update when stdout isn't a TTY):
#     "Writing at 0x00001000 \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501                     38.2% 4.88kB/12.80kB [0s] "
#
# _RE_WRITING_AT_CURRENT previously required a literal "[...]" around the
# bar, which matched the 5.0-5.3 format but not esp-pylib's unbracketed
# one -- every "Writing at..." line from a 5.4+ install fell through to
# "raw", so no progress updates were ever emitted and the status badge
# never advanced past "Connecting"/"Preparing" even though esptool was
# actively writing (the write itself, and its eventual success/failure,
# were unaffected -- only the UI's visibility into it). The bar's
# contents are now matched with a non-greedy ".*?" instead of an exact
# delimiter, which tolerates brackets, unbracketed glyphs, or anything
# else esptool/esp-pylib render between the address and the percentage,
# so this keeps working regardless of which esptool version is
# bundled/installed. The legacy pattern is also still matched here so
# both keep working; see the "writing" branch in FlashWorker._run_impl
# for why every match (not just the first) has to re-assert the
# "Uploading" status.
# --------------------------------------------------------------------------
_RE_WRITING_AT_LEGACY = re.compile(r"Writing at (0x[0-9a-fA-F]+)\.\.\.\s*\((\d+(?:\.\d+)?)\s*%\)")
_RE_WRITING_AT_CURRENT = re.compile(r"Writing at (0x[0-9a-fA-F]+)\s.*?(\d+(?:\.\d+)?)\s*%")
_RE_CONNECTING = re.compile(r"Connecting\.\.\.|Serial port")
_RE_ERASING = re.compile(r"Erasing flash|Chip erase")
_RE_HASH_VERIFIED = re.compile(r"Hash of data verified")
_RE_HARD_RESET = re.compile(r"Hard resetting|Leaving\.\.\.")
# Every phrasing esptool is known to use, across versions, for "this board
# isn't answering on the selected port" -- whether it was never there, was
# unplugged mid-flash, or never sent back anything at all. These are
# EXPECTED hardware/cabling failures, not bugs in this app, so they are
# recognized here and turned into a clear, actionable message in
# FlashWorker._finish() instead of a raw "esptool exited with code N" (or,
# worse, ever reaching the global exception handler -- see that module's
# docstring for the full "no expected upload error should look like an app
# crash" rationale).
_RE_PORT_LOST = re.compile(
    r"could not open port"
    r"|port is busy or doesn't exist"
    r"|no serial data received"
    r"|failed to connect"
    r"|timed out waiting for packet"
    r"|a fatal error occurred.*serial",
    re.IGNORECASE,
)
# esptool's own catch-all failure line, e.g. "A fatal error occurred: No
# serial data received." Captured so its message text (usually the single
# most useful sentence in the whole log) can be surfaced directly in the
# Failed status/history entry instead of just an exit code.
_RE_FATAL_ERROR = re.compile(r"A fatal error occurred:\s*(.+)", re.IGNORECASE)


@dataclass
class ProgressEvent:
    kind: str  # "connecting" | "erasing" | "writing" | "verifying" | "resetting" | "port_lost" | "fatal_error" | "raw"
    address: str = ""
    percent: int | None = None
    raw_line: str = ""
    detail: str = ""  # human-readable failure text, set for "fatal_error"


def parse_progress_line(line: str) -> ProgressEvent:
    """Turn a single line of esptool stdout into a structured ProgressEvent."""
    match = _RE_WRITING_AT_CURRENT.search(line) or _RE_WRITING_AT_LEGACY.search(line)
    if match:
        percent = int(round(float(match.group(2))))
        return ProgressEvent(kind="writing", address=match.group(1), percent=percent, raw_line=line)
    if _RE_ERASING.search(line):
        return ProgressEvent(kind="erasing", raw_line=line)
    if _RE_HASH_VERIFIED.search(line):
        return ProgressEvent(kind="verifying", raw_line=line)
    fatal_match = _RE_FATAL_ERROR.search(line)
    if fatal_match:
        return ProgressEvent(kind="fatal_error", raw_line=line, detail=fatal_match.group(1).strip())
    if _RE_PORT_LOST.search(line):
        return ProgressEvent(kind="port_lost", raw_line=line)
    if _RE_CONNECTING.search(line):
        return ProgressEvent(kind="connecting", raw_line=line)
    if _RE_HARD_RESET.search(line):
        return ProgressEvent(kind="resetting", raw_line=line)
    return ProgressEvent(kind="raw", raw_line=line)


def _esptool_command_prefix() -> list[str]:
    """
    Base argv used to launch esptool as a subprocess.

    Running from source: `sys.executable` is a real Python interpreter, so
    `-m esptool` works exactly as expected.

    Running as a frozen PyInstaller build: `sys.executable` is this app's
    OWN .exe, not a Python interpreter -- there is nothing on the target
    machine to run `-m esptool` with. esptool is instead bundled directly
    into the exe, so we re-invoke this same exe with a hidden internal flag
    that main.py intercepts to run esptool's CLI in-process and exit,
    rather than launching a second copy of the GUI (which is what silently
    happened before this fix: Upload would open a second blank app window
    instead of ever actually flashing).
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, ESPTOOL_REEXEC_FLAG]
    return [sys.executable, "-m", "esptool"]


def espsecure_command_prefix() -> list[str]:
    """Same re-exec trick as _esptool_command_prefix(), for `espsecure`
    (key generation / image signing). Used by security_manager.py."""
    if getattr(sys, "frozen", False):
        return [sys.executable, ESPSECURE_REEXEC_FLAG]
    return [sys.executable, "-m", "espsecure"]


def espefuse_command_prefix() -> list[str]:
    """Same re-exec trick as _esptool_command_prefix(), for `espefuse`
    (burning/reading eFuses). Used by security_manager.py."""
    if getattr(sys, "frozen", False):
        return [sys.executable, ESPEFUSE_REEXEC_FLAG]
    return [sys.executable, "-m", "espefuse"]


class FlashCommandBuilder:
    """Builds the exact `esptool` CLI argument list for a given device."""

    @staticmethod
    def build_write_flash_args(device: DeviceConfig) -> list[str]:
        """
        Build the full command line (as a list, suitable for subprocess.Popen)
        to flash every ENABLED firmware entry on `device`.
        """
        args: list[str] = _esptool_command_prefix()

        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]

        args += ["--port", device.com_port]
        args += ["--baud", str(device.baud_rate)]

        if not device.stub_loader:
            args += ["--no-stub"]

        args += ["write-flash"]

        if device.flash_mode and device.flash_mode != "keep":
            args += ["--flash-mode", device.flash_mode]
        if device.flash_frequency and device.flash_frequency != "keep":
            args += ["--flash-freq", device.flash_frequency]
        if device.flash_size and device.flash_size != "keep":
            args += ["--flash-size", device.flash_size]

        if device.erase_before_upload:
            args += ["--erase-all"]

        if not device.compression:
            args += ["--no-compress"]

        if not device.reset_after_upload:
            args += ["--after", "no-reset"]

        # Flash encryption: on-the-fly encryption during write-flash itself
        # (esptool's own `--encrypt` flag). This is "development mode"
        # behaviour -- it requires the flash-encryption eFuse key to already
        # be burned (see security_manager.py's provisioning flow) and only
        # works while the device hasn't been locked into release mode.
        # Nothing here implements the encryption -- esptool/the chip's own
        # hardware AES engine does it.
        if device.security.enable_flash_encryption and device.security.encrypt_on_write:
            args += ["--encrypt"]

        if device.custom_flash_args.strip():
            # Allow power users to append raw extra arguments (e.g. --no-progress).
            # validate_extra_esptool_args() is also run pre-upload by
            # validator.py (so the user sees a clear error before anything
            # runs) -- this is a second, defense-in-depth check right at
            # the point the argv is actually assembled, since a project
            # file can be hand-edited or come from a shared/untrusted
            # source without ever passing through the pre-upload
            # validator first (e.g. a script driving this module
            # directly).
            error = validate_extra_esptool_args(device.custom_flash_args)
            if error:
                raise ValueError(f"Refusing to build flash command: custom flash arguments are invalid: {error}")
            args += shlex.split(device.custom_flash_args.strip())

        for entry in device.enabled_firmware():
            args += [entry.address, entry.file_path]

        return args

    @staticmethod
    def build_erase_flash_args(device: DeviceConfig) -> list[str]:
        """Build a command line to fully erase the chip's flash (no writing)."""
        args: list[str] = _esptool_command_prefix()
        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]
        args += ["--port", device.com_port, "--baud", str(device.baud_rate), "erase-flash"]
        return args

    @staticmethod
    def build_chip_id_args(device: DeviceConfig) -> list[str]:
        """Build a lightweight command used to probe/identify a connected chip."""
        args: list[str] = _esptool_command_prefix()
        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]
        args += ["--port", device.com_port, "--baud", str(device.baud_rate), "chip-id"]
        return args

    @staticmethod
    def build_flash_id_args(device: DeviceConfig) -> list[str]:
        """Build a command that prints SPI flash manufacturer/device ID and size."""
        args: list[str] = _esptool_command_prefix()
        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]
        args += ["--port", device.com_port, "--baud", str(device.baud_rate), "flash-id"]
        return args

    @staticmethod
    def build_security_info_args(device: DeviceConfig) -> list[str]:
        """
        Build `esptool get-security-info` -- prints a report of the chip's
        current flash-encryption/secure-boot eFuse state. Only supported on
        chips with the unified eFuse table (everything except the original
        ESP32 and ESP8266); the Read panel falls back to an eFuse summary
        read (build_efuse_summary_args in security_manager.py) for those.
        """
        args: list[str] = _esptool_command_prefix()
        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]
        args += ["--port", device.com_port, "--baud", str(device.baud_rate), "get-security-info"]
        return args

    @staticmethod
    def build_read_flash_args(device: DeviceConfig, address: str, size: str, output_path: str) -> list[str]:
        """
        Build `esptool read-flash <address> <size> <output>` -- reads back
        raw flash content to a local file. Read-only; makes no changes to
        the device. `address`/`size` accept the same hex/decimal forms
        esptool itself accepts (e.g. "0x1000" or "4096").
        """
        args: list[str] = _esptool_command_prefix()
        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]
        args += ["--port", device.com_port, "--baud", str(device.baud_rate)]
        args += ["read-flash", address, size, output_path]
        return args

    @staticmethod
    def build_merge_bin_args(
        chip: str,
        entries: list[tuple[str, str]],
        output_path: str,
        flash_mode: str = "keep",
        flash_frequency: str = "keep",
        flash_size: str = "keep",
    ) -> list[str]:
        """
        Build the `esptool --chip <chip> merge-bin ...` command line that
        combines several (address, file_path) pairs into one flashable
        image. Unlike write-flash, merge-bin is entirely OFFLINE -- no
        `--port`/`--baud` and no connected board required, since it only
        reads the input files and writes one output file.

        `chip` MUST be a concrete chip (not "auto") -- esptool itself
        refuses merge-bin without one, since the merged image's layout
        (and flash-size padding) depends on knowing which chip it's for.
        """
        args: list[str] = _esptool_command_prefix()
        args += ["--chip", chip, "merge-bin", "--output", output_path]

        if flash_mode and flash_mode != "keep":
            args += ["--flash-mode", flash_mode]
        if flash_frequency and flash_frequency != "keep":
            args += ["--flash-freq", flash_frequency]
        if flash_size and flash_size != "keep":
            args += ["--flash-size", flash_size]

        for address, file_path in entries:
            args += [address, file_path]

        return args


class FlashProcess:
    """
    Thin wrapper around subprocess.Popen for running an esptool command and
    streaming its stdout line-by-line. Used from within FlashWorker
    (a QThread), never from the GUI thread directly.
    """

    def __init__(self, command: list[str]) -> None:
        self.command = command
        self._process: subprocess.Popen | None = None
        self._line_queue: "queue.Queue[str | None]" = queue.Queue()
        self._reader_thread: threading.Thread | None = None

    def start(self) -> None:
        logger.debug("Launching esptool subprocess: %s", " ".join(self.command))
        creationflags = 0
        if sys.platform == "win32":
            # Prevent a flashing console window from popping up per device.
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self._process = subprocess.Popen(
            self.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=creationflags,
        )
        # stdout is drained on a dedicated daemon thread into a queue rather
        # than iterated directly, so the caller can poll with a timeout (see
        # iter_lines) instead of blocking forever. This matters because a
        # device that disconnects mid-write can leave the OS serial driver
        # parked in an uninterruptible I/O wait that esptool has no timeout
        # for -- without this, a plain `for line in process.stdout` never
        # returns, and the FlashWorker QThread reading it never finishes.
        self._reader_thread = threading.Thread(target=self._drain_stdout, daemon=True)
        self._reader_thread.start()

    def _drain_stdout(self) -> None:
        if self._process is not None and self._process.stdout is not None:
            for raw_line in self._process.stdout:
                line = raw_line.rstrip("\r\n")
                if line:
                    self._line_queue.put(line)
        self._line_queue.put(None)  # sentinel: stdout closed / process exited

    def iter_lines(self, stall_timeout: float | None = None) -> Iterator[str | None]:
        """
        Yield decoded stdout lines as they arrive, until the process exits.

        If `stall_timeout` is given (seconds) and no line -- nor the
        end-of-stream sentinel -- arrives within that window, yields `None`
        once per timeout window instead of blocking forever. Callers use a
        `None` to detect a genuinely unresponsive/hung subprocess and abort,
        rather than leaving the worker parked indefinitely (see start()).
        """
        if self._process is None:
            return
        while True:
            try:
                line = self._line_queue.get(timeout=stall_timeout)
            except queue.Empty:
                yield None
                continue
            if line is None:
                return
            yield line

    def wait(self, timeout: float | None = None) -> int:
        if self._process is None:
            return -1
        return self._process.wait(timeout=timeout)

    @property
    def return_code(self) -> int | None:
        if self._process is None:
            return None
        return self._process.poll()

    def terminate(self) -> None:
        """Attempt a graceful terminate, escalating to kill if needed."""
        if self._process is None or self._process.poll() is not None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logger.warning("esptool subprocess did not terminate gracefully; killing")
            self._process.kill()
        except Exception:  # noqa: BLE001
            logger.exception("Error while terminating esptool subprocess")
