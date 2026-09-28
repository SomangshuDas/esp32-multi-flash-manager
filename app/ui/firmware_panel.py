"""
firmware_panel.py
==================
Editor for the firmware (.bin) list of whichever device is currently
selected in the DevicePanel. Supports add/remove/duplicate/reorder,
drag-and-drop of files/folders from Explorer, and folder-based
auto-detection via firmware_manager.auto_detect.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.firmware_manager.auto_detect import scan_firmware_folder
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.ui.merge_bin_dialog import MergeBinDialog
from app.ui.widgets import fit_table_columns, make_scrollable, prepare_table_for_full_content
from app.utilities.constants import (
    FIRMWARE_FILE_FILTER,
    MERGE_POST_ACTION_ADD_DESELECT,
    MERGE_POST_ACTION_ADD_REMOVE,
    MERGE_POST_ACTION_NONE,
    SUPPORTED_CHIPS,
)
from app.utilities.helpers import is_valid_hex_address, normalize_hex_address

COL_ENABLED = 0
COL_FILE = 1
COL_ADDRESS = 2
COL_SIZE = 3
COL_MD5 = 4
COL_STATUS = 5


class FirmwarePanel(QWidget):
    """
    Signals
    -------
    firmware_changed(device_id) - emitted whenever the firmware list of the
                                   active device is modified in any way.
    """

    firmware_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._device: DeviceConfig | None = None
        self._factory_locked = False
        # Populated by MainWindow at startup from dynamic chip detection
        # (app/utilities/chip_detect.py); falls back to the hardcoded list
        # until then so this widget still works standalone/in tests.
        self._supported_chips: list[str] = list(SUPPORTED_CHIPS)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        layout = QVBoxLayout(content)

        header = QHBoxLayout()
        self.title_label = QLabel("Firmware — (no device selected)")
        self.title_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        layout.addLayout(header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["On", "File", "Address", "Size", "MD5", "Status"]
        )
        # Columns are never stretched/shrunk to fit the viewport - long file
        # names, addresses, and MD5 hashes always get their full width, and
        # the table's own horizontal scrollbar takes over once that's wider
        # than the panel instead of Qt eliding any cell's text.
        prepare_table_for_full_content(self.table)
        self._min_col_widths = {COL_FILE: 160, COL_MD5: 220}
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(120)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Add BIN...")
        self.remove_button = QPushButton("Remove")
        self.duplicate_button = QPushButton("Duplicate")
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")
        self.import_folder_button = QPushButton("Auto-Detect Folder...")
        self.merge_button = QPushButton("Merge Bins...")

        self.add_button.clicked.connect(self._add_bin)
        self.remove_button.clicked.connect(self._remove_selected)
        self.duplicate_button.clicked.connect(self._duplicate_selected)
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        self.import_folder_button.clicked.connect(self._import_folder)
        self.merge_button.clicked.connect(self._open_merge_dialog)

        for button in (
            self.add_button, self.remove_button, self.duplicate_button,
            self.move_up_button, self.move_down_button, self.import_folder_button,
            self.merge_button,
        ):
            button_row.addWidget(button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        hint = QLabel("Tip: drag & drop .bin files or a firmware folder here to add them automatically.")
        hint.setStyleSheet("color: #9a9ca3; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        outer_layout.addWidget(make_scrollable(content))

        self._set_controls_enabled(False)

    # ------------------------------------------------------------------
    def set_device(self, device: DeviceConfig | None) -> None:
        self._device = device
        self.title_label.setText(
            f"Firmware — {device.name}" if device else "Firmware — (no device selected)"
        )
        self._set_controls_enabled(device is not None)
        self._reload_table()

    def _set_controls_enabled(self, enabled: bool) -> None:
        # Settings Lock disables editing the firmware list
        # regardless of the per-device "enabled" state passed in here, so
        # it wins over a normal device selection.
        enabled = enabled and not self._factory_locked
        for widget in (
            self.add_button, self.remove_button, self.duplicate_button,
            self.move_up_button, self.move_down_button, self.import_folder_button,
            self.merge_button, self.table,
        ):
            widget.setEnabled(enabled)

    def set_factory_locked(self, locked: bool) -> None:
        """Settings Lock: disable every firmware-editing
        control (including Merge Bins) without losing the current
        device's displayed firmware list."""
        self._factory_locked = locked
        self._set_controls_enabled(self._device is not None)

    def set_supported_chips(self, chips: list[str]) -> None:
        """Called by MainWindow once at startup with the dynamically
        detected chip list (see app/utilities/chip_detect.py), passed
        through to MergeBinDialog so its Target Chip dropdown matches
        what esptool can actually flash."""
        self._supported_chips = list(chips)

    # ------------------------------------------------------------------
    def _reload_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if self._device:
            for entry in self._device.firmware:
                self._append_row(entry)
        self.table.blockSignals(False)
        fit_table_columns(self.table, self._min_col_widths)

    def _append_row(self, entry: FirmwareEntry) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        checkbox_item.setCheckState(Qt.CheckState.Checked if entry.enabled else Qt.CheckState.Unchecked)
        checkbox_item.setData(Qt.ItemDataRole.UserRole, entry.id)
        self.table.setItem(row, COL_ENABLED, checkbox_item)

        file_item = QTableWidgetItem(entry.file_name)
        file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        file_item.setToolTip(entry.file_path)
        self.table.setItem(row, COL_FILE, file_item)

        address_item = QTableWidgetItem(entry.address)
        self.table.setItem(row, COL_ADDRESS, address_item)

        size_item = QTableWidgetItem(entry.display_size)
        size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, COL_SIZE, size_item)

        # MD5 is always freshly recalculated from disk (see
        # FirmwareEntry.refresh()) rather than trusted from the project
        # file -- if it just changed since the entry was added/last loaded,
        # that's flagged here rather than silently shown as if nothing
        # happened, since it usually means the BIN was rebuilt/replaced.
        md5_text = entry.md5 or "-"
        md5_item = QTableWidgetItem(f"{md5_text} (changed!)" if entry.md5_changed else md5_text)
        md5_item.setFlags(md5_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if entry.md5_changed:
            md5_item.setForeground(Qt.GlobalColor.darkYellow)
            md5_item.setToolTip(
                "This BIN file's MD5 changed since it was added or the project was last "
                "opened -- it was recalculated fresh from disk just now, not read from "
                "the project file."
            )
        self.table.setItem(row, COL_MD5, md5_item)

        status_item = QTableWidgetItem("Missing!" if entry.missing else "OK")
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if entry.missing:
            status_item.setForeground(Qt.GlobalColor.red)
        self.table.setItem(row, COL_STATUS, status_item)

    def _entry_id_for_row(self, row: int) -> str | None:
        item = self.table.item(row, COL_ENABLED)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_entry_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._entry_id_for_row(rows[0].row())

    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._device is None:
            return
        entry_id = self._entry_id_for_row(item.row())
        entry = next((f for f in self._device.firmware if f.id == entry_id), None)
        if entry is None:
            return

        if item.column() == COL_ENABLED:
            entry.enabled = item.checkState() == Qt.CheckState.Checked
        elif item.column() == COL_ADDRESS:
            candidate = item.text().strip()
            if is_valid_hex_address(candidate):
                entry.address = normalize_hex_address(candidate)
            else:
                QMessageBox.warning(self, "Invalid Address", f"'{candidate}' is not a valid hex address (e.g. 0x10000).")
                self.table.blockSignals(True)
                item.setText(entry.address)
                self.table.blockSignals(False)
                return

        fit_table_columns(self.table, self._min_col_widths)
        self.firmware_changed.emit(self._device.id)

    # ------------------------------------------------------------------
    def _add_bin(self) -> None:
        if self._device is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Firmware BIN File(s)", "", FIRMWARE_FILE_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        for path in paths:
            entry = FirmwareEntry(file_path=path, address="0x10000")
            entry.refresh()
            self._device.add_firmware(entry)
        if paths:
            self._reload_table()
            self.firmware_changed.emit(self._device.id)

    def _remove_selected(self) -> None:
        if self._device is None:
            return
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        self._device.remove_firmware(entry_id)
        self._reload_table()
        self.firmware_changed.emit(self._device.id)

    def _duplicate_selected(self) -> None:
        if self._device is None:
            return
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        self._device.duplicate_firmware(entry_id)
        self._reload_table()
        self.firmware_changed.emit(self._device.id)

    def _move_selected(self, direction: int) -> None:
        if self._device is None:
            return
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        self._device.move_firmware(entry_id, direction)
        self._reload_table()
        self.firmware_changed.emit(self._device.id)

    def _import_folder(self) -> None:
        if self._device is None:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Select Firmware Folder", "",
            QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.ShowDirsOnly,
        )
        if not folder:
            return
        entries = scan_firmware_folder(folder, self._device.chip_type)
        if not entries:
            QMessageBox.information(self, "No Firmware Found", "No .bin files were found in that folder.")
            return
        self._device.firmware.extend(entries)
        self._reload_table()
        self.firmware_changed.emit(self._device.id)

    # ------------------------------------------------------------------
    # Bin Merge
    # ------------------------------------------------------------------
    def _open_merge_dialog(self) -> None:
        if self._device is None:
            return
        if not self._device.firmware:
            QMessageBox.information(self, "Merge Bins", "Add firmware files to this device first.")
            return

        dialog = MergeBinDialog(self._device, self._supported_chips, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        merged_entry = dialog.merged_entry()
        if merged_entry is None:
            return

        action = dialog.post_action()
        source_ids = set(dialog.source_entry_ids())

        if action == MERGE_POST_ACTION_NONE:
            # Just wrote the file to disk -- Firmware Settings untouched.
            return

        self._device.add_firmware(merged_entry)

        if action == MERGE_POST_ACTION_ADD_REMOVE:
            self._device.firmware = [e for e in self._device.firmware if e.id not in source_ids]
        elif action == MERGE_POST_ACTION_ADD_DESELECT:
            for entry in self._device.firmware:
                if entry.id in source_ids:
                    entry.enabled = False
        # MERGE_POST_ACTION_ADD_ONLY: merged bin added, source bins left as-is.

        self._reload_table()
        self.firmware_changed.emit(self._device.id)

    # ------------------------------------------------------------------
    # Drag & drop support
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._device is None:
            return
        added_any = False
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if not local_path:
                continue
            if os.path.isdir(local_path):
                for entry in scan_firmware_folder(local_path, self._device.chip_type):
                    self._device.add_firmware(entry)
                    added_any = True
            elif local_path.lower().endswith(".bin"):
                entry = FirmwareEntry(file_path=local_path, address="0x10000")
                entry.refresh()
                self._device.add_firmware(entry)
                added_any = True
        if added_any:
            self._reload_table()
            self.firmware_changed.emit(self._device.id)
        event.acceptProposedAction()
