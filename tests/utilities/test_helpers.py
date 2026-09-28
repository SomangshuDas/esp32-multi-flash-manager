"""Unit tests for app/utilities/helpers.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.utilities import helpers


class TestNewUuid:
    def test_returns_string(self):
        assert isinstance(helpers.new_uuid(), str)

    def test_unique_across_calls(self):
        assert helpers.new_uuid() != helpers.new_uuid()


class TestComputeMd5:
    def test_known_content_matches_expected_digest(self, tmp_path):
        path = tmp_path / "sample.bin"
        path.write_bytes(b"hello world")
        import hashlib
        expected = hashlib.md5(b"hello world").hexdigest()
        assert helpers.compute_md5(str(path)) == expected

    def test_recompute_detects_content_change(self, tmp_path):
        path = tmp_path / "firmware.bin"
        path.write_bytes(b"version-1")
        first = helpers.compute_md5(str(path))
        path.write_bytes(b"version-2-totally-different-content")
        second = helpers.compute_md5(str(path))
        assert first != second

    def test_streams_large_file_in_chunks(self, tmp_path):
        path = tmp_path / "large.bin"
        path.write_bytes(b"\xAB" * (5 * 1024 * 1024))  # 5 MB, several chunks at 1 MB default
        digest = helpers.compute_md5(str(path))
        assert len(digest) == 32

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            helpers.compute_md5(str(tmp_path / "does-not-exist.bin"))


class TestHumanReadableSize:
    @pytest.mark.parametrize(
        "num_bytes, expected",
        [
            (0, "0 B"),
            (512, "512 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1024 * 1024, "1.0 MB"),
            (1024 * 1024 * 1024, "1.0 GB"),
        ],
    )
    def test_expected_units(self, num_bytes, expected):
        assert helpers.human_readable_size(num_bytes) == expected


class TestHumanReadableDuration:
    def test_seconds_only(self):
        assert helpers.human_readable_duration(45) == "00:45"

    def test_minutes_and_seconds(self):
        assert helpers.human_readable_duration(90) == "01:30"

    def test_hours_minutes_seconds(self):
        assert helpers.human_readable_duration(3725) == "01:02:05"

    def test_negative_clamped_to_zero(self):
        assert helpers.human_readable_duration(-5) == "00:00"

    def test_zero(self):
        assert helpers.human_readable_duration(0) == "00:00"


class TestIsValidHexAddress:
    @pytest.mark.parametrize("value", ["0x1000", "0X8000", "0xabcdef", "0x0"])
    def test_valid_addresses(self, value):
        assert helpers.is_valid_hex_address(value) is True

    @pytest.mark.parametrize("value", ["", None, "1000", "0xZZZZ", "0x", "  ", "0x10 00"])
    def test_invalid_addresses(self, value):
        assert helpers.is_valid_hex_address(value) is False

    def test_strips_surrounding_whitespace(self):
        assert helpers.is_valid_hex_address("  0x1000  ") is True


class TestNormalizeHexAddress:
    def test_lowercases_hex_digits(self):
        assert helpers.normalize_hex_address("0xABCDEF") == "0xabcdef"

    def test_adds_missing_prefix(self):
        assert helpers.normalize_hex_address("1000") == "0x1000"

    def test_strips_whitespace(self):
        assert helpers.normalize_hex_address("  0x1000  ") == "0x1000"

    def test_idempotent(self):
        once = helpers.normalize_hex_address("0X8000")
        twice = helpers.normalize_hex_address(once)
        assert once == twice == "0x8000"

    def test_strips_leading_zero_padding(self):
        assert helpers.normalize_hex_address("0x01000") == "0x1000"

    def test_zero_normalizes_regardless_of_padding(self):
        assert helpers.normalize_hex_address("0x0000") == "0x0"
        assert helpers.normalize_hex_address("0x0") == "0x0"

    def test_differently_padded_equal_addresses_compare_equal(self):
        assert helpers.normalize_hex_address("0x1000") == helpers.normalize_hex_address("0x001000")


class TestFileExists:
    def test_existing_file(self, tmp_path):
        path = tmp_path / "exists.bin"
        path.write_bytes(b"x")
        assert helpers.file_exists(str(path)) is True

    def test_missing_file(self, tmp_path):
        assert helpers.file_exists(str(tmp_path / "missing.bin")) is False

    def test_none_path(self):
        assert helpers.file_exists(None) is False

    def test_empty_string_path(self):
        assert helpers.file_exists("") is False

    def test_directory_is_not_a_file(self, tmp_path):
        assert helpers.file_exists(str(tmp_path)) is False


class TestTimestampNow:
    def test_format(self):
        stamp = helpers.timestamp_now()
        # "YYYY-MM-DD HH:MM:SS"
        date_part, time_part = stamp.split(" ")
        assert len(date_part.split("-")) == 3
        assert len(time_part.split(":")) == 3


class TestSafeFilename:
    def test_strips_windows_illegal_characters(self):
        assert helpers.safe_filename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"

    def test_leaves_normal_name_untouched(self):
        assert helpers.safe_filename("Bench 1 - Batch 7") == "Bench 1 - Batch 7"

    def test_empty_string_falls_back_to_unnamed(self):
        assert helpers.safe_filename("") == "unnamed"

    def test_whitespace_only_falls_back_to_unnamed(self):
        assert helpers.safe_filename("   ") == "unnamed"

    def test_illegal_characters_are_replaced_not_dropped(self):
        # Substitution -- doesn't fall back to "unnamed" just because every
        # character happened to be illegal, only when the result is empty.
        assert helpers.safe_filename("///???") == "______"

    def test_strips_surrounding_whitespace(self):
        assert helpers.safe_filename("  My Project  ") == "My Project"


class TestGetAppDataDir:
    def test_windows_uses_appdata_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
        result = helpers.get_app_data_dir()
        assert result == tmp_path / "roaming" / "ESP32MultiFlashManager"
        assert result.is_dir()

    def test_windows_falls_back_when_appdata_unset(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = helpers.get_app_data_dir()
        assert result == tmp_path / "AppData" / "Roaming" / "ESP32MultiFlashManager"

    def test_macos_uses_application_support(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = helpers.get_app_data_dir()
        assert result == tmp_path / "Library" / "Application Support" / "ESP32MultiFlashManager"
        assert result.is_dir()

    def test_linux_uses_xdg_data_home_when_set(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        result = helpers.get_app_data_dir()
        assert result == tmp_path / "xdg" / "ESP32MultiFlashManager"
        assert result.is_dir()

    def test_linux_falls_back_to_local_share_when_xdg_unset(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = helpers.get_app_data_dir()
        assert result == tmp_path / ".local" / "share" / "ESP32MultiFlashManager"

    def test_directory_is_created_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "fresh_xdg"))
        result = helpers.get_app_data_dir()
        assert result.exists()

    def test_is_idempotent_when_called_twice(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        first = helpers.get_app_data_dir()
        second = helpers.get_app_data_dir()
        assert first == second
        assert first.is_dir()


class TestResourcePath:
    def test_uses_project_root_when_not_frozen(self):
        assert not hasattr(sys, "_MEIPASS")
        result = helpers.resource_path("icons", "app.ico")
        # app/utilities/helpers.py -> app/utilities -> app -> project root
        expected_root = Path(helpers.__file__).resolve().parent.parent.parent
        assert result == expected_root / "resources" / "icons" / "app.ico"

    def test_uses_meipass_when_frozen_by_pyinstaller(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        result = helpers.resource_path("icons", "app.ico")
        assert result == tmp_path / "resources" / "icons" / "app.ico"
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    def test_no_extra_parts_returns_resources_root(self):
        result = helpers.resource_path()
        assert result.name == "resources"


class TestTimestampNow:
    def test_includes_utc_offset(self):
        ts = helpers.timestamp_now()
        # e.g. "2026-09-04 14:23:01+0530" or "...+0000" -- always ends
        # with a signed 4-digit offset, no colon.
        assert ts[-5] in "+-"
        assert ts[-4:].isdigit()

    def test_splits_into_date_and_time_parts(self):
        ts = helpers.timestamp_now()
        parts = ts.split(" ")
        assert len(parts) == 2
        date_part, time_part = parts
        assert len(date_part.split("-")) == 3
        assert len(time_part.split(":")) == 3  # HH:MM:SS+offset -- offset has no colon


class TestValidateExtraEsptoolArgs:
    def test_empty_string_is_valid(self):
        assert helpers.validate_extra_esptool_args("") is None
        assert helpers.validate_extra_esptool_args("   ") is None

    def test_simple_flag_is_valid(self):
        assert helpers.validate_extra_esptool_args("--no-progress") is None

    def test_flag_with_value_is_valid(self):
        assert helpers.validate_extra_esptool_args("--flash_freq 40m") is None

    def test_unbalanced_quotes_is_invalid(self):
        assert helpers.validate_extra_esptool_args('--foo "bar') is not None

    def test_too_long_is_invalid(self):
        assert helpers.validate_extra_esptool_args("-x " * 300) is not None

    @pytest.mark.parametrize("token", ["--port", "-p", "--chip", "write_flash", "erase_flash", "burn-key"])
    def test_blocked_tokens_are_invalid(self, token):
        assert helpers.validate_extra_esptool_args(token) is not None

    def test_path_like_bare_token_is_invalid(self):
        assert helpers.validate_extra_esptool_args("../../etc/passwd") is not None

    def test_bare_keyword_value_is_valid(self):
        assert helpers.validate_extra_esptool_args("--flash_mode dio") is None


class TestPropagateTraceHook:
    def test_noop_when_nothing_tracing(self, monkeypatch):
        import sys
        import threading

        monkeypatch.delattr(threading, "_trace_hook", raising=False)
        calls = []
        monkeypatch.setattr(sys, "settrace", lambda hook: calls.append(hook))
        helpers.propagate_trace_hook()
        assert calls == []

    def test_calls_settrace_with_hook_when_tracing(self, monkeypatch):
        import sys
        import threading

        sentinel = object()
        monkeypatch.setattr(threading, "_trace_hook", sentinel, raising=False)
        calls = []
        monkeypatch.setattr(sys, "settrace", lambda hook: calls.append(hook))
        helpers.propagate_trace_hook()
        assert calls == [sentinel]


class TestNormalizePathForComparison:
    """normalize_path_for_comparison() -- used to dedupe Recent Projects
    (and any other "is this the same path as that one" check) across
    forward-slash vs backslash spellings of the same location."""

    def test_forward_and_backslash_windows_paths_are_equal(self):
        forward = helpers.normalize_path_for_comparison("C:/Users/sample/project.emfm")
        backward = helpers.normalize_path_for_comparison("C:\\Users\\sample\\project.emfm")
        assert forward == backward

    def test_mixed_separators_equal_either_pure_style(self):
        mixed = helpers.normalize_path_for_comparison("C:/Users\\sample/project.emfm")
        forward = helpers.normalize_path_for_comparison("C:/Users/sample/project.emfm")
        assert mixed == forward

    def test_genuinely_different_paths_are_not_equal(self):
        a = helpers.normalize_path_for_comparison("C:/Users/sample/project_a.emfm")
        b = helpers.normalize_path_for_comparison("C:/Users/sample/project_b.emfm")
        assert a != b

    def test_redundant_slashes_are_collapsed(self):
        a = helpers.normalize_path_for_comparison("C:/Users//sample/project.emfm")
        b = helpers.normalize_path_for_comparison("C:/Users/sample/project.emfm")
        assert a == b
