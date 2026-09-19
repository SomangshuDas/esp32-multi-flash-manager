"""
Unit tests for the custom-args validation guard added to
app/flash_engine/esptool_wrapper.py's FlashCommandBuilder, and for
parse_progress_line()'s handling of every "Writing at..." line format
esptool/esp-pylib are known to emit.
"""

from __future__ import annotations

import pytest

from app.flash_engine.esptool_wrapper import FlashCommandBuilder, parse_progress_line
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import FLASH_MODES, SUPPORTED_CHIPS


def _device(custom_flash_args: str = "") -> DeviceConfig:
    device = DeviceConfig(
        name="Device", com_port="COM3",
        chip_type=SUPPORTED_CHIPS[0], flash_mode=FLASH_MODES[0],
        custom_flash_args=custom_flash_args,
    )
    entry = FirmwareEntry(file_path="/tmp/app.bin", address="0x10000", enabled=True)
    entry.file_size = 0x1000
    device.add_firmware(entry)
    return device


class TestCustomFlashArgsGuard:
    def test_empty_custom_args_build_normally(self):
        args = FlashCommandBuilder.build_write_flash_args(_device(""))
        assert "0x10000" in args

    def test_safe_custom_args_are_appended(self):
        args = FlashCommandBuilder.build_write_flash_args(_device("--no-progress"))
        assert "--no-progress" in args

    def test_quoted_custom_args_are_split_correctly(self):
        # shlex.split (not a naive .split()) so a quoted value with a
        # space in it stays as one token.
        args = FlashCommandBuilder.build_write_flash_args(_device('--extra-note "hard reset"'))
        assert "hard reset" in args

    def test_blocked_flag_raises_value_error(self):
        with pytest.raises(ValueError, match="custom flash arguments are invalid"):
            FlashCommandBuilder.build_write_flash_args(_device("--port /dev/ttyFAKE"))

    def test_path_like_token_raises_value_error(self):
        with pytest.raises(ValueError):
            FlashCommandBuilder.build_write_flash_args(_device("../../etc/passwd"))


class TestParseProgressLineWritingAt:
    """
    Regression coverage for every "Writing at..." format esptool/esp-pylib
    are known to emit. Before this fix, _RE_WRITING_AT_CURRENT required a
    literal "[...]" around the progress bar, which esp-pylib 1.1.5 (bundled
    with esptool 5.4+) never prints -- its bar is unbracketed block-glyph
    characters padded with spaces. Every "Writing at..." line from such an
    install fell through to kind="raw", so the UI never left the
    "Connecting"/"Preparing" stage and the progress bar never moved, even
    though esptool itself was actively (and successfully) writing.
    """

    def test_legacy_format(self):
        event = parse_progress_line("Writing at 0x00010000... (42 %)")
        assert event.kind == "writing"
        assert event.address == "0x00010000"
        assert event.percent == 42

    def test_bracketed_current_format(self):
        # esptool 5.0-5.3's rich-based bar.
        event = parse_progress_line(
            "Writing at 0x00005a30 [==============================] 100.0% 13104/13104 bytes..."
        )
        assert event.kind == "writing"
        assert event.address == "0x00005a30"
        assert event.percent == 100

    def test_unbracketed_esp_pylib_format(self):
        # esptool 5.4+ via esp-pylib's EspLog.progress_bar(): no brackets
        # around the bar, block-character glyphs padded with spaces, one
        # full line per update when stdout is piped (not a TTY) -- this is
        # the format that previously fell through to "raw" and left the
        # status badge stuck before the upload ever appeared to start.
        line = (
            "Writing at 0x00001000 "
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "                     38.2% 4.88kB/12.80kB [0s] "
        )
        event = parse_progress_line(line)
        assert event.kind == "writing"
        assert event.address == "0x00001000"
        assert event.percent == 38

    def test_unbracketed_esp_pylib_format_complete(self):
        line = (
            "Writing at 0x00003390 "
            + "\u2501" * 30
            + " 100.0% 12.80kB/12.80kB [0s] "
        )
        event = parse_progress_line(line)
        assert event.kind == "writing"
        assert event.address == "0x00003390"
        assert event.percent == 100

    def test_non_writing_lines_still_fall_through_to_raw(self):
        assert parse_progress_line("Some unrelated esptool banner line").kind == "raw"
