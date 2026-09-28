"""Shared fixtures for tests/ui -- all run headless (QT_QPA_PLATFORM=offscreen,
set globally in tests/conftest.py)."""

from __future__ import annotations

import pytest

from app.ui.main_window import MainWindow


@pytest.fixture
def main_window(qtbot):
    """A real MainWindow, built and torn down cleanly for each test.

    Deliberately NOT registered via qtbot.addWidget(): pytest-qt would
    then call .close() on it a second time during its own teardown,
    which re-enters MainWindow.closeEvent() and can pop a REAL, un-mocked
    QMessageBox.question() if anything about the window's state changed
    between our own explicit close() below and pytest-qt's -- and that
    blocks forever under the offscreen platform. We manage this window's
    lifecycle entirely ourselves instead.
    """
    window = MainWindow()
    window.show()
    qtbot.waitExposed(window)
    yield window
    # Force a clean, "nothing to confirm" state before closing: tests
    # deliberately leave dirty=True (adding devices) or fake busy workers
    # in place, and MainWindow.closeEvent() pops a real confirmation
    # dialog for any of those conditions.
    window.port_watcher.stop()
    window.autosave_timer.stop()
    window.flash_controller._workers.clear()
    window.project_controller.dirty = False
    if window.lock_overlay.isVisible():
        window._set_factory_mode_locked(False)
        window.lock_overlay.hide()
    window.close()
    window.deleteLater()
