"""
CalSci Flasher - Main Application
CalSci MicroPython file flasher with Git repository sync.
"""

import sys
import json
import shutil
import subprocess
import threading
import hashlib
from pathlib import Path
from queue import Queue, Empty
import time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QProgressBar, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QSplitter,
    QFrame, QStatusBar, QMessageBox, QPlainTextEdit, QTabWidget, QMenu,
    QDialog, QFileDialog, QComboBox
)
from PySide6.QtCore import Qt, QTimer, QSize, QEvent
from PySide6.QtGui import QColor, QFont, QAction, QTextCursor

# Import from modular files
from config import (
    ROOT,
    FIRMWARE_BIN,
    SYNC_SOURCES_FILE,
    TRIPLE_FIRMWARE_PATHS_FILE,
    TRIPLE_BOOTLOADER_OFFSET,
    TRIPLE_PARTITION_TABLE_OFFSET,
    TRIPLE_OTADATA_OFFSET,
    TRIPLE_MPY_OFFSET,
    TRIPLE_CPP_OFFSET,
    TRIPLE_RUST_OFFSET,
    TRIPLE_ARTIFACTS_DIR,
    TRIPLE_LOCAL_RUST_BIN,
    TRIPLE_BOOTLOADER_CANDIDATES,
    TRIPLE_PARTITION_TABLE_CANDIDATES,
    TRIPLE_OTADATA_CANDIDATES,
    TRIPLE_MPY_CANDIDATES,
    TRIPLE_CPP_CANDIDATES,
    TRIPLE_RUST_BIN_CANDIDATES,
    TRIPLE_RUST_ELF_CANDIDATES,
    TRIPLE_BOOTLOADER_SOURCE_CANDIDATES,
    TRIPLE_PARTITION_TABLE_SOURCE_CANDIDATES,
    TRIPLE_OTADATA_SOURCE_CANDIDATES,
    TRIPLE_MPY_SOURCE_CANDIDATES,
    TRIPLE_CPP_SOURCE_CANDIDATES,
    TRIPLE_RUST_BIN_SOURCE_CANDIDATES,
    TRIPLE_RUST_ELF_SOURCE_CANDIDATES,
)
from utils import find_esp32_ports, ensure_repo, delete_repo, repo_status, pull_repo, get_all_files
from flasher import (
    MicroPyFlasher,
    MicroPyError,
    flash_firmware,
    flash_triple_boot_firmware,
    generate_esp_image_from_elf,
    confirm_bootloader,
    wait_for_reset_signal,
)
from signal_bridge import SignalBridge
from dialogs import ESP32FileSelectionDialog
from filebrowser import ESP32FileBrowser

MAX_CUSTOM_SYNC_SOURCES = 3


class StickyPopupComboBox(QComboBox):
    """QComboBox popup that closes only when explicitly requested."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._allow_hide_popup = False

    def hidePopup(self):
        if self._allow_hide_popup:
            self._allow_hide_popup = False
            super().hidePopup()

    def close_popup_explicitly(self):
        self._allow_hide_popup = True
        super().hidePopup()



# ============================================================
# ================= MAIN APPLICATION ==========================
# ============================================================

class CalSciApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CalSci Flasher")
        self._normal_size = QSize(940, 660)
        self._lock_resize = False
        self.setMinimumSize(self._normal_size)
        self.resize(self._normal_size)

        self.bridge = SignalBridge()
        self.bridge.log_signal.connect(self._on_log)
        self.bridge.progress_signal.connect(self._on_progress)
        self.bridge.operation_done_signal.connect(self._on_operation_done)
        self.bridge.device_status_signal.connect(self._update_device_status)

        self.operation_in_progress = False
        self.file_browser = None
        self._device_connected = False
        self.simulator_process = None
        self._sync_sources = []
        self._selected_sync_source = None
        self._sync_action_add = "__sync_action_add__"
        self._sync_action_remove = "__sync_action_remove__"
        self._sync_action_separator = "__sync_action_separator__"
        self._triple_fw_paths = {"mpy": "", "cpp": "", "rust": ""}
        self._triple_fw_key_by_index = {}
        self._selected_triple_flash_keys = set()
        self._triple_combo_summary_key = "__summary__"
        self._triple_combo_separator_key = "__separator__"
        self._triple_action_set_path = {
            "mpy": "__set_path_mpy__",
            "cpp": "__set_path_cpp__",
            "rust": "__set_path_rust__",
        }
        self._triple_action_clear_targets = "__clear_targets__"
        self._triple_action_close_menu = "__close_menu__"
        
        self._build_ui()
        self._apply_stylesheet()
        self._load_sync_sources()
        self._load_triple_firmware_paths()
        self._update_triple_flash_button_state()

        self.device_timer = QTimer()
        self.device_timer.timeout.connect(self._check_device_status)
        self.device_timer.start(2000)
        self._check_device_status()

    def resizeEvent(self, event):
        if not self.isMaximized() and not self.isFullScreen():
            if not self._lock_resize and self.size() != self._normal_size:
                self._lock_resize = True
                self.resize(self._normal_size)
                self._lock_resize = False
                return
        super().resizeEvent(event)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 14, 20, 14)

        title_label = QLabel("CalSci Flasher")
        title_label.setObjectName("titleLabel")
        header_layout.addWidget(title_label)

        subtitle_label = QLabel("CalSci MicroPython Uploader")
        subtitle_label.setObjectName("subtitleLabel")
        header_layout.addWidget(subtitle_label)

        header_layout.addStretch()

        self.esp_status_label = QLabel("● No device")
        self.esp_status_label.setObjectName("espStatusDisconnected")
        header_layout.addWidget(self.esp_status_label)

        main_layout.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(16)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.update_btn = QPushButton("Download Updates")
        self.update_btn.setObjectName("btnSecondary")
        self.update_btn.clicked.connect(self._handle_update)
        left_layout.addWidget(self.update_btn)

        self.flash_btn = QPushButton("Flash All Files")
        self.flash_btn.setObjectName("btnPrimary")
        self.flash_btn.clicked.connect(self._handle_flash)
        left_layout.addWidget(self.flash_btn)

        triple_row = QWidget()
        triple_row_layout = QHBoxLayout(triple_row)
        triple_row_layout.setContentsMargins(0, 0, 0, 0)
        triple_row_layout.setSpacing(8)

        self.flash_triple_btn = QPushButton("Flash Triple Boot")
        self.flash_triple_btn.setObjectName("btnSecondaryCompact")
        self.flash_triple_btn.clicked.connect(self._handle_flash_tripleboot)
        triple_row_layout.addWidget(self.flash_triple_btn, 1)

        self.triple_fw_combo = StickyPopupComboBox()
        self.triple_fw_combo.setObjectName("syncSourceCombo")
        self.triple_fw_combo.activated.connect(self._on_triple_firmware_option_activated)
        triple_row_layout.addWidget(self.triple_fw_combo, 1)

        left_layout.addWidget(triple_row)

        self.flash_fw_cb = QCheckBox("Reflash firmware before upload")
        self.flash_fw_cb.setChecked(False)
        self.flash_fw_cb.setObjectName("retryCheckbox")
        left_layout.addWidget(self.flash_fw_cb)

        sync_row = QWidget()
        sync_row_layout = QHBoxLayout(sync_row)
        sync_row_layout.setContentsMargins(0, 0, 0, 0)
        sync_row_layout.setSpacing(8)

        self.delta_btn = QPushButton("Sync Files")
        self.delta_btn.setObjectName("btnSecondaryCompact")
        self.delta_btn.clicked.connect(self._handle_delta_sync)
        sync_row_layout.addWidget(self.delta_btn, 1)

        self.sync_source_combo = QComboBox()
        self.sync_source_combo.setObjectName("syncSourceCombo")
        self.sync_source_combo.currentIndexChanged.connect(self._on_sync_source_changed)
        sync_row_layout.addWidget(self.sync_source_combo, 1)

        left_layout.addWidget(sync_row)

        self.upload_custom_btn = QPushButton("Upload Custom Folder")
        self.upload_custom_btn.setObjectName("btnSecondary")
        self.upload_custom_btn.clicked.connect(self._handle_upload_custom_folder)
        left_layout.addWidget(self.upload_custom_btn)

        self.browse_btn = QPushButton("Code Editor")
        self.browse_btn.setObjectName("btnSecondary")
        self.browse_btn.clicked.connect(self._open_file_browser)
        left_layout.addWidget(self.browse_btn)

        self.clear_btn = QPushButton("Clear All Files")
        self.clear_btn.setObjectName("btnDanger")
        self.clear_btn.clicked.connect(self._handle_clear_all)
        left_layout.addWidget(self.clear_btn)

        self.simulator_btn = QPushButton("Launch Simulator")
        self.simulator_btn.setObjectName("btnSecondary")
        self.simulator_btn.clicked.connect(self._handle_launch_simulator)
        left_layout.addWidget(self.simulator_btn)

        self.auto_retry_cb = QCheckBox("Auto-retry on failure)")
        self.auto_retry_cb.setChecked(True)
        self.auto_retry_cb.setObjectName("retryCheckbox")
        left_layout.addWidget(self.auto_retry_cb)

        left_layout.addStretch()

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setObjectName("progressBar")
        right_layout.addWidget(self.progress_bar)

        self.current_file_label = QLabel("Idle")
        self.current_file_label.setObjectName("currentFileLabel")
        right_layout.addWidget(self.current_file_label)

        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setObjectName("logPanel")
        right_layout.addWidget(self.log_panel)

        body_layout.addWidget(left_panel, stretch=1)
        body_layout.addWidget(right_panel, stretch=3)
        main_layout.addWidget(body)

        status_bar = QStatusBar()
        status_bar.showMessage("Ready")
        self.setStatusBar(status_bar)

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }

            QFrame#header {
                background-color: #141414;
                border-bottom: 1px solid #333;
            }
            QLabel#titleLabel {
                font-size: 18px;
                font-weight: 700;
                color: #f0f0f0;
                margin-right: 14px;
            }
            QLabel#subtitleLabel {
                font-size: 12px;
                color: #666;
            }
            QLabel#espStatusDisconnected {
                color: #e74c3c;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#espStatusConnected {
                color: #77b255;
                font-size: 12px;
                font-weight: 600;
            }

            QPushButton#btnPrimary {
                background-color: rgba(233, 84, 32, 0.5);
                color: #fff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 6px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: 600;
                min-width: 200px;
            }
            QPushButton#btnPrimary:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton#btnPrimary:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton#btnPrimary:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }

            QPushButton#btnSecondary {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 6px;
                padding: 12px 20px;
                font-size: 14px;
                min-width: 200px;
            }
            QPushButton#btnSecondary:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton#btnSecondary:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton#btnSecondary:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }

            QPushButton#btnSecondaryCompact {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 6px;
                padding: 10px 10px;
                font-size: 13px;
                min-width: 0px;
            }
            QPushButton#btnSecondaryCompact:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton#btnSecondaryCompact:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton#btnSecondaryCompact:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }

            QPushButton#btnDanger {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 6px;
                padding: 12px 20px;
                font-size: 14px;
                min-width: 200px;
            }
            QPushButton#btnDanger:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton#btnDanger:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton#btnDanger:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }

            QCheckBox#retryCheckbox {
                color: #a0a0a0;
                font-size: 12px;
                spacing: 8px;
                margin-top: 10px;
            }
            QCheckBox#retryCheckbox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #555;
                border-radius: 4px;
                background: #2a2a2a;
            }
            QCheckBox#retryCheckbox::indicator:hover {
                border-color: #777;
                background: #333;
            }
            QCheckBox#retryCheckbox::indicator:checked {
                background-color: #e95420;
                border-color: #e95420;
            }

            QComboBox#syncSourceCombo {
                background-color: #2a2a2a;
                color: #dddddd;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px 8px;
                min-width: 0px;
            }
            QComboBox#syncSourceCombo:hover {
                border-color: #666;
            }
            QComboBox#syncSourceCombo QAbstractItemView {
                background-color: #1f1f1f;
                color: #dddddd;
                border: 1px solid #444;
                selection-background-color: #e95420;
                selection-color: #ffffff;
            }

            QCheckBox#preventSleepCheckbox {
                color: #a0a0a0;
                font-size: 12px;
                spacing: 8px;
                margin-top: 6px;
            }
            QCheckBox#preventSleepCheckbox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #555;
                border-radius: 4px;
                background: #2a2a2a;
            }
            QCheckBox#preventSleepCheckbox::indicator:hover {
                border-color: #777;
                background: #333;
            }
            QCheckBox#preventSleepCheckbox::indicator:checked {
                background-color: #e95420;
                border-color: #e95420;
            }

            QProgressBar#progressBar {
                height: 18px;bbbbbbbbbbbb
                border-radius: 4px;
                border: 1px solid #3a3a3a;
                background-color: #2a2a2a;
                text-align: center;
                color: #fff;
                font-size: 11px;
            }
            QProgressBar#progressBar::chunk {
                background-color: #e95420;
                border-radius: 3px;
            }

            QLabel#currentFileLabel {
                color: #777;
                font-size: 12px;
                font-style: italic;
            }

            QTextEdit#logPanel {
                background-color: #161616;
                border: 1px solid #2e2e2e;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                color: #c0c0c0;
            }

            QStatusBar {
                background-color: #141414;
                border-top: 1px solid #333;
                color: #666;
                font-size: 11px;
                padding: 4px 12px;
            }
        """)

    def _default_sync_source_path(self):
        return str(Path(ROOT).resolve())

    def _normalize_sync_source_path(self, path_str):
        return str(Path(path_str).expanduser().resolve())

    def _sync_source_display_name(self, path_str):
        if path_str == self._default_sync_source_path():
            return f"{path_str} (default)"
        if not Path(path_str).exists():
            return f"{path_str} (missing)"
        return path_str

    def _save_sync_sources(self):
        payload = {
            "sources": self._sync_sources,
            "selected": self._selected_sync_source,
        }
        try:
            SYNC_SOURCES_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            self._log(f"Failed to save sync source settings: {e}", "warning")

    def _refresh_sync_source_combo(self):
        self.sync_source_combo.blockSignals(True)
        self.sync_source_combo.clear()

        for path_str in self._sync_sources:
            self.sync_source_combo.addItem(self._sync_source_display_name(path_str), path_str)

        if self._selected_sync_source in self._sync_sources:
            idx = self._sync_sources.index(self._selected_sync_source)
        else:
            idx = 0
            self._selected_sync_source = self._sync_sources[0] if self._sync_sources else None

        sep_index = self.sync_source_combo.count()
        self.sync_source_combo.addItem("──────────", self._sync_action_separator)
        self.sync_source_combo.addItem("Add Local Folder...", self._sync_action_add)
        self.sync_source_combo.addItem("Remove Current Folder...", self._sync_action_remove)

        model = self.sync_source_combo.model()
        sep_item = model.item(sep_index)
        if sep_item is not None:
            sep_item.setEnabled(False)

        if idx >= 0 and self.sync_source_combo.count() > 0:
            self.sync_source_combo.setCurrentIndex(idx)
            selected = self.sync_source_combo.itemData(idx)
            self.sync_source_combo.setToolTip(selected if selected else "")

        self.sync_source_combo.blockSignals(False)
        self._update_sync_source_controls()

    def _load_sync_sources(self):
        default_path = self._default_sync_source_path()
        sources = [default_path]
        selected = default_path
        custom_count = 0

        if SYNC_SOURCES_FILE.exists():
            try:
                raw = json.loads(SYNC_SOURCES_FILE.read_text(encoding="utf-8"))
                raw_sources = raw.get("sources", [])
                raw_selected = raw.get("selected", "")

                if isinstance(raw_sources, list):
                    for item in raw_sources:
                        if not isinstance(item, str) or not item.strip():
                            continue
                        try:
                            normalized = self._normalize_sync_source_path(item)
                        except Exception:
                            continue
                        if normalized == default_path:
                            continue
                        if custom_count >= MAX_CUSTOM_SYNC_SOURCES:
                            continue
                        if normalized not in sources:
                            sources.append(normalized)
                            custom_count += 1

                if isinstance(raw_selected, str) and raw_selected.strip():
                    try:
                        selected = self._normalize_sync_source_path(raw_selected)
                    except Exception:
                        selected = default_path
            except Exception:
                selected = default_path

        if default_path not in sources:
            sources.insert(0, default_path)
        if selected not in sources:
            selected = default_path

        self._sync_sources = sources
        self._selected_sync_source = selected
        self._refresh_sync_source_combo()
        self._save_sync_sources()

    def _update_sync_source_controls(self):
        if self.operation_in_progress:
            return

        default_path = self._default_sync_source_path()
        current = self._selected_sync_source or default_path
        custom_count = len([p for p in self._sync_sources if p != default_path])
        can_add = custom_count < MAX_CUSTOM_SYNC_SOURCES
        can_remove = current != default_path

        model = self.sync_source_combo.model()
        if model is None:
            return

        for i in range(self.sync_source_combo.count()):
            data = self.sync_source_combo.itemData(i)
            item = model.item(i)
            if item is None:
                continue
            if data == self._sync_action_add:
                label = "Add Local Folder..."
                if not can_add:
                    label = f"Add Local Folder... (max {MAX_CUSTOM_SYNC_SOURCES})"
                self.sync_source_combo.setItemText(i, label)
                item.setEnabled(can_add)
            elif data == self._sync_action_remove:
                item.setEnabled(can_remove)

    def _on_sync_source_changed(self, index):
        if index < 0:
            return
        selected = self.sync_source_combo.itemData(index)
        if selected == self._sync_action_add:
            self._handle_add_sync_source()
            return
        if selected == self._sync_action_remove:
            self._handle_remove_sync_source()
            return
        if selected == self._sync_action_separator:
            self._refresh_sync_source_combo()
            return
        if not selected:
            return
        self._selected_sync_source = selected
        self.sync_source_combo.setToolTip(selected)
        self._save_sync_sources()
        self._update_sync_source_controls()

    def _handle_add_sync_source(self):
        default_path = self._default_sync_source_path()
        custom_count = len([p for p in self._sync_sources if p != default_path])
        if custom_count >= MAX_CUSTOM_SYNC_SOURCES:
            self._log(
                f"Only {MAX_CUSTOM_SYNC_SOURCES} custom sync folders are allowed. Remove one to add another.",
                "warning",
            )
            self._refresh_sync_source_combo()
            return

        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Sync Source Folder",
            str(Path.home())
        )
        if not selected:
            self._refresh_sync_source_combo()
            return

        try:
            normalized = self._normalize_sync_source_path(selected)
        except Exception as e:
            self._log(f"Invalid folder: {e}", "error")
            self._refresh_sync_source_combo()
            return

        if normalized not in self._sync_sources:
            self._sync_sources.append(normalized)
            self._log(f"Added sync folder: {normalized}", "success")
        else:
            self._log(f"Sync folder already exists: {normalized}", "info")

        self._selected_sync_source = normalized
        self._refresh_sync_source_combo()
        self._save_sync_sources()

    def _handle_remove_sync_source(self):
        current = self._selected_sync_source or self._default_sync_source_path()
        default_path = self._default_sync_source_path()

        if current == default_path:
            self._log("Default sync folder cannot be removed", "warning")
            self._refresh_sync_source_combo()
            return

        if current in self._sync_sources:
            self._sync_sources.remove(current)
            self._selected_sync_source = default_path
            self._refresh_sync_source_combo()
            self._save_sync_sources()
            self._log(f"Removed sync folder: {current}", "info")
            return

        self._refresh_sync_source_combo()

    def _get_selected_sync_root(self):
        selected = self._selected_sync_source or self._default_sync_source_path()
        root = Path(selected)
        if not root.exists():
            self._log(f"Selected sync folder not found: {root}", "error")
            return None
        if not root.is_dir():
            self._log(f"Selected sync path is not a folder: {root}", "error")
            return None
        return root

    def _normalize_firmware_path(self, path_str):
        return str(Path(path_str).expanduser().resolve())

    def _triple_firmware_option_text(self, key):
        names = {"mpy": "MicroPython", "cpp": "C++", "rust": "Rust"}
        return names[key]

    def _triple_firmware_path_display_name(self, key):
        labels = {"mpy": "mpy", "cpp": "cpp", "rust": "rust"}
        current = self._triple_fw_paths.get(key, "")
        if not current:
            return f"{labels[key]} path:"
        return f"{labels[key]} path: {current}"

    def _triple_flash_targets_summary(self):
        names = {"mpy": "MicroPython", "cpp": "C++", "rust": "Rust"}
        active = [names[k] for k in ("mpy", "cpp", "rust") if k in self._selected_triple_flash_keys]
        if not active:
            return "Targets: None (Full Triple Boot)"
        return "Targets: " + ", ".join(active)

    def _update_triple_flash_button_state(self):
        names = {"mpy": "MicroPython", "cpp": "C++", "rust": "Rust"}
        active = [names[k] for k in ("mpy", "cpp", "rust") if k in self._selected_triple_flash_keys]
        if active:
            self.flash_triple_btn.setText("Flash")
            self.flash_triple_btn.setToolTip(
                f"Flash selected firmware only (no erase): {', '.join(active)}"
            )
        else:
            self.flash_triple_btn.setText("Flash Triple Boot")
            self.flash_triple_btn.setToolTip(
                "Erase + flash bootloader/partition/ota data + all 3 firmware images"
            )

    def _save_triple_firmware_paths(self):
        payload = {k: self._triple_fw_paths.get(k, "") for k in ("mpy", "cpp", "rust")}
        try:
            TRIPLE_FIRMWARE_PATHS_FILE.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            self._log(f"Failed to save triple firmware paths: {e}", "warning")

    def _refresh_triple_firmware_combo(self):
        self.triple_fw_combo.blockSignals(True)
        self.triple_fw_combo.clear()
        self._triple_fw_key_by_index = {}

        # Summary row (non-selectable)
        self.triple_fw_combo.addItem(self._triple_flash_targets_summary(), self._triple_combo_summary_key)
        self._triple_fw_key_by_index[0] = self._triple_combo_summary_key

        # Checkable target rows
        for idx, key in enumerate(("mpy", "cpp", "rust"), start=1):
            self.triple_fw_combo.addItem(self._triple_firmware_option_text(key), key)
            self._triple_fw_key_by_index[idx] = key
            checked = key in self._selected_triple_flash_keys
            self.triple_fw_combo.setItemData(
                idx,
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked,
                Qt.ItemDataRole.CheckStateRole,
            )
            model = self.triple_fw_combo.model()
            item = model.item(idx) if hasattr(model, "item") else None
            if item is not None:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)

        # Separator row
        sep_idx = self.triple_fw_combo.count()
        self.triple_fw_combo.addItem("──────────", self._triple_combo_separator_key)
        self._triple_fw_key_by_index[sep_idx] = self._triple_combo_separator_key

        # Path actions + clear action
        model = self.triple_fw_combo.model()
        path_action_rows = []
        for key in ("mpy", "cpp", "rust"):
            label = self._triple_firmware_path_display_name(key)
            path_action_rows.append((label, self._triple_action_set_path[key], key))

        action_rows = path_action_rows + [
            ("Clear Firmware Targets (all unchecked)", self._triple_action_clear_targets, None),
            ("Close Menu (X)", self._triple_action_close_menu, None),
        ]
        has_selection = bool(self._selected_triple_flash_keys)
        for label, action_key, target_key in action_rows:
            idx = self.triple_fw_combo.count()
            self.triple_fw_combo.addItem(label, action_key)
            self._triple_fw_key_by_index[idx] = action_key
            item = model.item(idx) if hasattr(model, "item") else None
            if item is not None and target_key is not None:
                flags = item.flags() | Qt.ItemFlag.ItemIsSelectable
                is_active = (not has_selection) or (target_key in self._selected_triple_flash_keys)
                if is_active:
                    flags |= Qt.ItemFlag.ItemIsEnabled
                else:
                    flags &= ~Qt.ItemFlag.ItemIsEnabled
                item.setFlags(flags)

                active_color = QColor("#dddddd")
                disabled_color = QColor("#dddddd")
                disabled_color.setAlphaF(0.90)
                self.triple_fw_combo.setItemData(
                    idx,
                    active_color if is_active else disabled_color,
                    Qt.ItemDataRole.ForegroundRole,
                )

        summary_item = model.item(0) if hasattr(model, "item") else None
        if summary_item is not None:
            summary_item.setEnabled(False)
        sep_item = model.item(sep_idx) if hasattr(model, "item") else None
        if sep_item is not None:
            sep_item.setEnabled(False)

        self.triple_fw_combo.setCurrentIndex(0)

        names = {"mpy": "MicroPython", "cpp": "C++", "rust": "Rust"}
        tooltip_lines = []
        for key in ("mpy", "cpp", "rust"):
            value = self._triple_fw_paths.get(key, "")
            if value:
                tooltip_lines.append(f"{names[key]}: {value}")
            else:
                tooltip_lines.append(f"{names[key]}: auto")
        active = [names[k] for k in ("mpy", "cpp", "rust") if k in self._selected_triple_flash_keys]
        if active:
            tooltip_lines.append(f"Flash mode: selected only ({', '.join(active)})")
        else:
            tooltip_lines.append("Flash mode: full triple-boot")
        tooltip_lines.append("Use checkbox rows to select firmware targets")
        self.triple_fw_combo.setToolTip("\n".join(tooltip_lines))
        self.triple_fw_combo.blockSignals(False)
        self._update_triple_flash_button_state()

    def _load_triple_firmware_paths(self):
        loaded = {"mpy": "", "cpp": "", "rust": ""}
        if TRIPLE_FIRMWARE_PATHS_FILE.exists():
            try:
                raw = json.loads(TRIPLE_FIRMWARE_PATHS_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for key in loaded:
                        value = raw.get(key, "")
                        if isinstance(value, str) and value.strip():
                            try:
                                loaded[key] = self._normalize_firmware_path(value)
                            except Exception:
                                loaded[key] = value
            except Exception:
                pass
        self._triple_fw_paths = loaded
        self._selected_triple_flash_keys = set()
        self._refresh_triple_firmware_combo()
        self._save_triple_firmware_paths()

    def _keep_triple_firmware_popup_open(self):
        if self.triple_fw_combo.isEnabled():
            QTimer.singleShot(0, self.triple_fw_combo.showPopup)

    def _on_triple_firmware_option_activated(self, index):
        key = self._triple_fw_key_by_index.get(index)
        if key in {self._triple_combo_summary_key, self._triple_combo_separator_key, None}:
            return

        if key in {"mpy", "cpp", "rust"}:
            if key in self._selected_triple_flash_keys:
                self._selected_triple_flash_keys.remove(key)
            else:
                self._selected_triple_flash_keys.add(key)
            self._refresh_triple_firmware_combo()
            self._keep_triple_firmware_popup_open()
            if self._selected_triple_flash_keys:
                active = [k.upper() for k in ("mpy", "cpp", "rust") if k in self._selected_triple_flash_keys]
                self._log(f"Selected firmware targets: {', '.join(active)}", "info")
            else:
                self._log("No firmware target selected: full Triple Boot mode", "info")
            return

        if key == self._triple_action_clear_targets:
            self._selected_triple_flash_keys = set()
            self._refresh_triple_firmware_combo()
            self._keep_triple_firmware_popup_open()
            self._log("Firmware targets cleared (full Triple Boot mode)", "info")
            return

        if key == self._triple_action_close_menu:
            self.triple_fw_combo.close_popup_explicitly()
            self._log("Firmware menu closed", "info")
            return

        names = {"mpy": "MicroPython", "cpp": "C++", "rust": "Rust"}
        filters = {
            "mpy": "Firmware files (*.bin);;All files (*)",
            "cpp": "Firmware files (*.bin);;All files (*)",
            "rust": "Firmware files (*.bin *.elf);;All files (*)",
        }
        action_to_key = {v: k for k, v in self._triple_action_set_path.items()}
        target_key = action_to_key.get(key)
        if target_key not in {"mpy", "cpp", "rust"}:
            return
        if self._selected_triple_flash_keys and target_key not in self._selected_triple_flash_keys:
            self._keep_triple_firmware_popup_open()
            self._log(
                f"{names[target_key]} path is locked while other target(s) are selected.",
                "warning",
            )
            return

        current = self._triple_fw_paths.get(target_key, "")
        if current:
            start = Path(current)
            start_dir = str(start.parent if start.exists() else start.parent)
        else:
            start_dir = str(TRIPLE_ARTIFACTS_DIR)

        selected, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {names[target_key]} Firmware",
            start_dir,
            filters[target_key],
        )
        if not selected:
            self._refresh_triple_firmware_combo()
            self._keep_triple_firmware_popup_open()
            self._log(f"Path selection cancelled for {names[target_key]}", "info")
            return

        normalized = self._normalize_firmware_path(selected)
        self._triple_fw_paths[target_key] = normalized
        self._save_triple_firmware_paths()
        self._refresh_triple_firmware_combo()
        self._keep_triple_firmware_popup_open()
        self._log(f"Custom {names[target_key]} firmware path set: {normalized}", "success")

    def _resolve_candidate_path(self, label, candidates, log_found=True):
        checked = []
        for candidate in candidates:
            path = Path(candidate)
            checked.append(str(path))
            if path.exists():
                if log_found:
                    self._log(f"{label}: {path}", "info")
                return path
        raise MicroPyError(f"{label} not found. Checked: {' | '.join(checked)}")

    def _sync_local_artifact_from_sources(self, label, local_path, source_candidates):
        local_path = Path(local_path)
        src = None
        for candidate in source_candidates:
            path = Path(candidate)
            if path.exists():
                src = path
                break
        if src is None:
            if not local_path.exists():
                self._log(f"{label} source not found and local copy missing: {local_path}", "warning")
            return
        if local_path.resolve() == src.resolve():
            return
        needs_copy = (
            not local_path.exists()
            or local_path.stat().st_size != src.stat().st_size
            or local_path.stat().st_mtime < src.stat().st_mtime
        )
        if needs_copy:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, local_path)
            self._log(f"Updated local {label}: {local_path.name}", "info")

    def _refresh_local_triple_boot_artifacts(self):
        TRIPLE_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        self._sync_local_artifact_from_sources(
            "bootloader",
            TRIPLE_BOOTLOADER_CANDIDATES[0],
            TRIPLE_BOOTLOADER_SOURCE_CANDIDATES,
        )
        self._sync_local_artifact_from_sources(
            "partition table",
            TRIPLE_PARTITION_TABLE_CANDIDATES[0],
            TRIPLE_PARTITION_TABLE_SOURCE_CANDIDATES,
        )
        self._sync_local_artifact_from_sources(
            "ota data",
            TRIPLE_OTADATA_CANDIDATES[0],
            TRIPLE_OTADATA_SOURCE_CANDIDATES,
        )
        self._sync_local_artifact_from_sources(
            "MicroPython firmware",
            TRIPLE_MPY_CANDIDATES[0],
            TRIPLE_MPY_SOURCE_CANDIDATES,
        )
        self._sync_local_artifact_from_sources(
            "C++ firmware",
            TRIPLE_CPP_CANDIDATES[0],
            TRIPLE_CPP_SOURCE_CANDIDATES,
        )
        self._sync_local_artifact_from_sources(
            "Rust firmware bin",
            TRIPLE_RUST_BIN_CANDIDATES[0],
            TRIPLE_RUST_BIN_SOURCE_CANDIDATES,
        )
        self._sync_local_artifact_from_sources(
            "Rust ELF",
            TRIPLE_RUST_ELF_CANDIDATES[0],
            TRIPLE_RUST_ELF_SOURCE_CANDIDATES,
        )

    def _resolve_triple_boot_images(self):
        self._refresh_local_triple_boot_artifacts()
        bootloader = self._resolve_candidate_path("Bootloader image", TRIPLE_BOOTLOADER_CANDIDATES)
        partition_table = self._resolve_candidate_path(
            "Partition table image",
            TRIPLE_PARTITION_TABLE_CANDIDATES,
        )
        otadata = self._resolve_candidate_path("OTA data image", TRIPLE_OTADATA_CANDIDATES)
        custom_mpy = self._triple_fw_paths.get("mpy", "").strip()
        custom_cpp = self._triple_fw_paths.get("cpp", "").strip()
        custom_rust = self._triple_fw_paths.get("rust", "").strip()

        if custom_mpy:
            micropython = Path(custom_mpy)
            if not micropython.exists():
                raise MicroPyError(f"Custom MicroPython image not found: {micropython}")
            self._log(f"MicroPython image (custom): {micropython}", "info")
        else:
            micropython = self._resolve_candidate_path("MicroPython image", TRIPLE_MPY_CANDIDATES)

        if custom_cpp:
            cpp = Path(custom_cpp)
            if not cpp.exists():
                raise MicroPyError(f"Custom C++ image not found: {cpp}")
            self._log(f"C++ image (custom): {cpp}", "info")
        else:
            cpp = self._resolve_candidate_path("C++ image", TRIPLE_CPP_CANDIDATES)

        if custom_rust:
            rust_custom_path = Path(custom_rust)
            if not rust_custom_path.exists():
                raise MicroPyError(f"Custom Rust image not found: {rust_custom_path}")
            if rust_custom_path.suffix.lower() == ".bin":
                rust_bin = rust_custom_path
                self._log(f"Rust image (custom bin): {rust_bin}", "info")
            else:
                self._log("Custom Rust image is not .bin. Generating .bin from custom ELF…", "warning")
                rust_bin = Path(TRIPLE_LOCAL_RUST_BIN)
                generate_esp_image_from_elf(rust_custom_path, rust_bin, log_func=self._log)
        else:
            try:
                rust_bin = self._resolve_candidate_path("Rust image", TRIPLE_RUST_BIN_CANDIDATES)
            except MicroPyError:
                rust_elf = self._resolve_candidate_path("Rust ELF", TRIPLE_RUST_ELF_CANDIDATES)
                self._log("Rust BIN not found. Generating from ELF…", "warning")
                rust_bin = Path(TRIPLE_LOCAL_RUST_BIN)
                generate_esp_image_from_elf(rust_elf, rust_bin, log_func=self._log)

        return {
            "bootloader": bootloader,
            "partition_table": partition_table,
            "otadata": otadata,
            "micropython": micropython,
            "cpp": cpp,
            "rust": rust_bin,
        }

    def _check_device_status(self):
        if not self.operation_in_progress:
            ports = find_esp32_ports()
            was_connected = self._device_connected
            is_connected = len(ports) > 0
            self._device_connected = is_connected

            self.bridge.device_status_signal.emit(is_connected)

    def _update_device_status(self, connected):
        if connected:
            self.esp_status_label.setText("● Device connected")
            self.esp_status_label.setObjectName("espStatusConnected")
        else:
            self.esp_status_label.setText("● No device")
            self.esp_status_label.setObjectName("espStatusDisconnected")
        self.esp_status_label.style().unpolish(self.esp_status_label)
        self.esp_status_label.style().polish(self.esp_status_label)

    def _on_log(self, message, msg_type):
        color_map = {
            "info":    "#c0c0c0",
            "success": "#77b255",
            "error":   "#eb4d4b",
            "warning": "#f2a93b",
        }
        color = color_map.get(msg_type, "#c0c0c0")
        timestamp = time.strftime("%H:%M:%S")
        html = (
            f'<span style="color:#555;">[{timestamp}]</span> '
            f'<span style="color:{color};">{message}</span><br>'
        )

        # Save current selection if any
        cursor = self.log_panel.textCursor()
        had_selection = cursor.hasSelection()
        if had_selection:
            selection_start = cursor.selectionStart()
            selection_end = cursor.selectionEnd()

        # Always insert at the end
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_panel.setTextCursor(cursor)
        self.log_panel.insertHtml(html)

        # Restore selection or auto-scroll
        if had_selection:
            # Restore the previous selection
            cursor.setPosition(selection_start)
            cursor.setPosition(selection_end, QTextCursor.MoveMode.KeepAnchor)
            self.log_panel.setTextCursor(cursor)
        else:
            # Auto-scroll to end
            self.log_panel.moveCursor(QTextCursor.MoveOperation.End)

        self.current_file_label.setText(message)

    def _on_progress(self, value):
        self.progress_bar.setValue(int(value * 100))

    def _on_operation_done(self):
        self.operation_in_progress = False
        self.update_btn.setEnabled(True)
        self.flash_btn.setEnabled(True)
        self.flash_triple_btn.setEnabled(True)
        self.triple_fw_combo.setEnabled(True)
        self.delta_btn.setEnabled(True)
        self.sync_source_combo.setEnabled(True)
        self.upload_custom_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.simulator_btn.setEnabled(True)
        self._update_sync_source_controls()
        self._check_device_status()

    def _ensure_window_sequence(self, action_label):
        if self.file_browser and self.file_browser.isVisible():
            self.file_browser.close()
            if self.file_browser.isVisible():
                self.file_browser.raise_()
                self.file_browser.activateWindow()
                self._log(f"Close the File Browser before {action_label}.", "warning")
                return False
            self.file_browser = None
        return True

    def _on_file_browser_closed(self, _obj=None):
        self.file_browser = None

    def _lock_buttons(self):
        self.operation_in_progress = True
        self.update_btn.setEnabled(False)
        self.flash_btn.setEnabled(False)
        self.flash_triple_btn.setEnabled(False)
        self.triple_fw_combo.setEnabled(False)
        self.delta_btn.setEnabled(False)
        self.sync_source_combo.setEnabled(False)
        self.upload_custom_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.simulator_btn.setEnabled(False)
        self.progress_bar.setValue(0)

    def _log(self, message, msg_type="info"):
        self.bridge.log_signal.emit(message, msg_type)

    def _open_file_browser(self):
        ports = find_esp32_ports()
        if not ports:
            QMessageBox.warning(
                self,
                "No Device",
                "No CalSci device detected.\n\nPlease connect your CalSci and try again."
            )
            return
        
        port = ports[0]
        
        if self.file_browser is None or not self.file_browser.isVisible():
            self.file_browser = ESP32FileBrowser(port, self.bridge, parent=self)
            self.file_browser.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self.file_browser.destroyed.connect(self._on_file_browser_closed)
            self.file_browser.show()
        else:
            self.file_browser.raise_()
            self.file_browser.activateWindow()

    def _handle_update(self):
        self._lock_buttons()

        def run():
            try:
                # First, delete the existing repository
                self._log("Deleting existing repository…", "info")
                self.bridge.progress_signal.emit(0.1)
                delete_repo(self._log)

                # Then clone fresh from remote
                self._log("Cloning repository fresh…", "info")
                self.bridge.progress_signal.emit(0.4)
                ensure_repo(self._log)

                self._log("Repository updated successfully ✓", "success")
                self.bridge.progress_signal.emit(1.0)
            except Exception as e:
                self._log(f"Error: {e}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _handle_delta_sync(self):
        sync_root = self._get_selected_sync_root()
        if sync_root is None:
            return

        local_files = get_all_files(sync_root)
        if not local_files:
            self._log(f"No local files found in sync folder: {sync_root}", "error")
            return

        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No ESP32 device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")
                self._log(f"Sync source: {sync_root}", "info")
                self.bridge.progress_signal.emit(0.05)

                flasher = MicroPyFlasher(port)
                # self._log("soft resetting device…", "info")
                # flasher.reset_soft_automated(auto_cd="/apps/installed_apps", log_func=self._log)

                self._log("Scanning CalSci file system…", "info")
                esp32_sizes = flasher.get_file_sizes(timeout=25.0)
                self._log(f"CalSci has {len(esp32_sizes)} file(s)", "info")
                self.bridge.progress_signal.emit(0.10)

                local_map = {}
                for p in local_files:
                    remote = "/" + p.relative_to(sync_root).as_posix()
                    local_map[remote] = p

                to_upload   = []
                to_delete   = []
                unchanged   = []

                for remote, local_path in local_map.items():
                    local_size = local_path.stat().st_size
                    if remote in esp32_sizes:
                        if esp32_sizes[remote] == local_size:
                            unchanged.append(remote)
                        else:
                            to_upload.append((remote, local_path))
                    else:
                        to_upload.append((remote, local_path))

                for remote in esp32_sizes:
                    if remote not in local_map:
                        to_delete.append(remote)

                self._log("─── Sync comparison ───", "info")
                self._log(f"  Unchanged : {len(unchanged)} file(s)", "info")
                self._log(f"  To upload : {len(to_upload)} file(s)", "info")
                self._log(f"  To delete : {len(to_delete)} file(s)", "info")
                self.bridge.progress_signal.emit(0.15)

                if unchanged:
                    self._log("  ─ Unchanged (skipped):", "info")
                    for r in sorted(unchanged):
                        self._log(f"      ✓ {r}", "info")

                if to_upload:
                    self._log("  ─ To upload:", "info")
                    for remote, local_path in sorted(to_upload, key=lambda x: x[0]):
                        local_size = local_path.stat().st_size
                        if remote in esp32_sizes:
                            self._log(f"      ↻ {remote}  ({esp32_sizes[remote]} → {local_size} bytes, changed)", "warning")
                        else:
                            self._log(f"      + {remote}  ({local_size} bytes, new)", "warning")

                if to_delete:
                    self._log("  ─ To delete (not in local repo):", "info")
                    for r in sorted(to_delete):
                        self._log(f"      - {r}  ({esp32_sizes[r]} bytes)", "warning")

                self._log("───────────────────────", "info")

                if not to_upload and not to_delete:
                    self._log("Everything is in sync ✓", "success")
                    self.bridge.progress_signal.emit(1.0)
                    flasher.close()
                    return

                if to_delete:
                    self._log(f"Deleting {len(to_delete)} stale file(s)…", "warning")
                    for i, remote in enumerate(sorted(to_delete), 1):
                        if flasher.delete_file(remote):
                            self._log(f"  [{i}/{len(to_delete)}] Deleted: {remote}", "info")
                        else:
                            self._log(f"  [{i}/{len(to_delete)}] Failed: {remote}", "warning")
                    self.bridge.progress_signal.emit(0.30)

                if to_upload:
                    files_for_sync = [lp for _, lp in to_upload]
                    flasher.sync_folder_structure(files_for_sync, self._log, root_path=sync_root)
                    self.bridge.progress_signal.emit(0.35)

                    total_size = max(sum(lp.stat().st_size for _, lp in to_upload), 1)
                    uploaded_size = 0
                    failed = []
                    auto_retry = self.auto_retry_cb.isChecked()

                    self._log(f"Uploading {len(to_upload)} file(s)…", "info")

                    for i, (remote, local_path) in enumerate(sorted(to_upload, key=lambda x: x[0]), 1):
                        remote_rel = remote.lstrip("/")

                        flasher, success = self._upload_single_file(
                            flasher, port, local_path, remote_rel, auto_retry,
                            ensure_dirs=False, use_raw=True
                        )

                        if success:
                            uploaded_size += max(local_path.stat().st_size, 1)
                            progress = 0.35 + (uploaded_size / total_size) * 0.65
                            self.bridge.progress_signal.emit(progress)
                            self._log(f"  [{i}/{len(to_upload)}] ⬆  {remote}  ({local_path.stat().st_size} bytes)", "info")
                        else:
                            failed.append(remote)
                            self._log(f"  [{i}/{len(to_upload)}] Failed: {remote}", "warning")

                    if failed:
                        self._log(f"Sync done with {len(failed)} upload failure(s)", "warning")
                    else:
                        self._log("Sync complete ✓", "success")
                        self.bridge.progress_signal.emit(1.0)
                else:
                    self._log("Sync complete ✓", "success")
                    self.bridge.progress_signal.emit(1.0)

                flasher.exit_raw_repl()
                flasher.close()

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _handle_flash(self):
        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No CalSci device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")
                self.bridge.progress_signal.emit(0.05)

                if self.flash_fw_cb.isChecked():
                    self._log("Press and hold BOOT, then tap RESET to enter bootloader mode.", "warning")
                    port = confirm_bootloader(port, log_func=self._log)
                    self._log("Starting erase + flash in 3 seconds…", "info")
                    for remaining in range(3, 0, -1):
                        self._log(f"  Starting erase/flash in {remaining}s", "info")
                        time.sleep(1)
                    self._log(f"Erasing + flashing firmware: {FIRMWARE_BIN.name}", "info")
                    port = flash_firmware(port, FIRMWARE_BIN, log_func=self._log, enter_bootloader=False)
                    self._log("Reset CalSci now.", "warning")
                    port = wait_for_reset_signal(port, log_func=self._log)
                    self._log("Starting upload in 3 seconds…", "info")
                    for remaining in range(3, 0, -1):
                        self._log(f"  Starting upload in {remaining}s", "info")
                        time.sleep(1)

                flasher = MicroPyFlasher(port)
                # self._log("Clearing all files from ESP32...", "warning")
                # flasher.clean_all(self._log)
                # self._log("All files cleared", "success")
                
                files = get_all_files(ROOT)

                if not files:
                    self._log("No files to upload", "info")
                    return

                flasher.sync_folder_structure(files, self._log, root_path=ROOT)
                self.bridge.progress_signal.emit(0.05)

                total_size = max(sum(p.stat().st_size for p in files), 1)
                uploaded = 0
                failed_files = []
                auto_retry = self.auto_retry_cb.isChecked()

                self._log(f"Uploading {len(files)} files…", "info")

                for i, path in enumerate(files, 1):
                    remote_path = path.relative_to(ROOT).as_posix()

                    flasher, success = self._upload_single_file(
                        flasher, port, path, remote_path, auto_retry,
                        ensure_dirs=False, use_raw=True
                    )

                    if success:
                        uploaded += max(path.stat().st_size, 1)
                        self.bridge.progress_signal.emit(0.1 + (uploaded / total_size) * 0.9)
                        self._log(f"[{i}/{len(files)}] {path.name}", "info")
                    else:
                        failed_files.append(path.name)
                        self._log(f"⚠ Skipped: {path.name}", "warning")

                flasher.exit_raw_repl()
                flasher.close()

                if failed_files:
                    self._log(f"Done with {len(failed_files)} failure(s)", "warning")
                else:
                    self._log("Flash complete ✓", "success")
                    self.bridge.progress_signal.emit(1.0)

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _handle_flash_tripleboot(self):
        if not self._ensure_window_sequence("flashing triple-boot firmware"):
            return
        selected_keys = [k for k in ("mpy", "cpp", "rust") if k in self._selected_triple_flash_keys]
        selected_name = {"mpy": "MicroPython", "cpp": "C++", "rust": "Rust"}
        selected_offset = {
            "mpy": TRIPLE_MPY_OFFSET,
            "cpp": TRIPLE_CPP_OFFSET,
            "rust": TRIPLE_RUST_OFFSET,
        }
        selected_image_key = {
            "mpy": "micropython",
            "cpp": "cpp",
            "rust": "rust",
        }

        if not selected_keys:
            confirm_title = "Confirm Triple-Boot Flash"
            confirm_msg = (
                "This will erase the full chip and flash:\n"
                "- bootloader\n"
                "- partition table\n"
                "- ota data\n"
                "- MicroPython (ota_0)\n"
                "- C++ (ota_1)\n"
                "- Rust (ota_2)\n\n"
                "Continue?"
            )
        else:
            confirm_title = "Confirm Selected Firmware Flash"
            lines = []
            for key in selected_keys:
                lines.append(f"- {selected_name[key]} ({selected_offset[key]})")
            confirm_msg = (
                "This will flash selected firmware only:\n"
                + "\n".join(lines) + "\n\n"
                "No full-chip erase will be done.\n"
                "Bootloader and partition table will not be reflashed.\n\n"
                "Continue?"
            )

        confirm = QMessageBox.question(
            self,
            confirm_title,
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            self._log("Triple-boot flash cancelled", "info")
            return

        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No CalSci device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")
                images = self._resolve_triple_boot_images()
                self.bridge.progress_signal.emit(0.20)

                if not selected_keys:
                    self._log("Starting full triple-boot flash (automatic reset mode)…", "warning")
                    self.bridge.progress_signal.emit(0.30)
                    port = flash_triple_boot_firmware(
                        port=port,
                        bootloader_path=images["bootloader"],
                        partition_table_path=images["partition_table"],
                        otadata_path=images["otadata"],
                        micropython_path=images["micropython"],
                        cpp_path=images["cpp"],
                        rust_path=images["rust"],
                        bootloader_offset=TRIPLE_BOOTLOADER_OFFSET,
                        partition_offset=TRIPLE_PARTITION_TABLE_OFFSET,
                        otadata_offset=TRIPLE_OTADATA_OFFSET,
                        micropython_offset=TRIPLE_MPY_OFFSET,
                        cpp_offset=TRIPLE_CPP_OFFSET,
                        rust_offset=TRIPLE_RUST_OFFSET,
                        erase_before=True,
                        run_after=True,
                        log_func=self._log,
                    )
                    self._log(f"Triple-boot flash done on {port}", "success")
                else:
                    self._log(
                        "Starting selected firmware flash (no erase): "
                        + ", ".join(selected_name[k] for k in selected_keys),
                        "warning",
                    )
                    total_targets = len(selected_keys)
                    for idx, key in enumerate(selected_keys, start=1):
                        image_key = selected_image_key[key]
                        image_path = images[image_key]
                        target_offset = selected_offset[key]
                        target_name = selected_name[key]
                        self._log(
                            f"[{idx}/{total_targets}] Flashing {target_name} @ {target_offset} (no erase)…",
                            "info",
                        )
                        # Run only after the last selected target to avoid extra resets.
                        run_after = idx == total_targets
                        port = flash_firmware(
                            port=port,
                            firmware_path=image_path,
                            offset=target_offset,
                            erase_before=False,
                            run_after=run_after,
                            enter_bootloader=False,
                            log_func=self._log,
                        )
                        self.bridge.progress_signal.emit(0.20 + (0.75 * idx / total_targets))
                    self._log(f"Selected firmware flash done on {port}", "success")

                self.bridge.progress_signal.emit(1.0)

            except Exception as e:
                self._log(f"Error: {str(e)[:120]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _handle_upload_custom_folder(self):
        if not self._ensure_window_sequence("uploading a custom folder"):
            return

        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Upload",
            str(Path.home())
        )
        if not selected:
            self._log("Custom folder upload cancelled", "info")
            return

        local_root = Path(selected)
        files = sorted(get_all_files(local_root))
        if not files:
            self._log("Selected folder has no uploadable files", "warning")
            return

        # If package looks like a filesystem root (contains boot/main),
        # upload contents directly to "/" instead of nesting under folder name.
        has_root_entry = any((local_root / name).is_file() for name in ("boot.py", "main.py"))
        remote_root = "" if has_root_entry else (local_root.name.strip() or "custom_upload")
        target_root = "/" if not remote_root else f"/{remote_root}"
        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No CalSci device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")
                if has_root_entry:
                    self._log("Detected boot/main package; uploading directly to '/'", "info")
                self._log(
                    f"Uploading '{local_root}' to '{target_root}' ({len(files)} file(s))…",
                    "info"
                )
                self.bridge.progress_signal.emit(0.05)

                flasher = MicroPyFlasher(port)
                auto_retry = self.auto_retry_cb.isChecked()

                required_dirs = {remote_root} if remote_root else set()
                for local_path in files:
                    rel_parent = local_path.relative_to(local_root).parent
                    if rel_parent == Path("."):
                        continue
                    cur = remote_root
                    for part in rel_parent.parts:
                        cur = f"{cur}/{part}" if cur else part
                        required_dirs.add(cur)

                if required_dirs:
                    self._log("Creating folder structure…", "info")
                    for folder in sorted(required_dirs, key=lambda d: len(d.split("/"))):
                        if flasher.mkdir(folder):
                            self._log(f"  + {folder}", "info")
                        else:
                            self._log(f"  ! {folder} (failed)", "warning")
                self._log("Folder structure synced ✓", "success")
                self.bridge.progress_signal.emit(0.10)

                total_size = max(sum(p.stat().st_size for p in files), 1)
                uploaded = 0
                failed_files = []
                self._log(f"Uploading {len(files)} files…", "info")

                for i, local_path in enumerate(files, 1):
                    rel = local_path.relative_to(local_root).as_posix()
                    remote_path = f"{remote_root}/{rel}" if remote_root else rel
                    flasher, success = self._upload_single_file(
                        flasher, port, local_path, remote_path, auto_retry,
                        ensure_dirs=False, use_raw=True
                    )

                    if success:
                        uploaded += max(local_path.stat().st_size, 1)
                        self.bridge.progress_signal.emit(0.1 + (uploaded / total_size) * 0.9)
                        self._log(f"[{i}/{len(files)}] {local_path.name}", "info")
                    else:
                        failed_files.append(local_path.name)
                        self._log(f"⚠ Skipped: {local_path.name}", "warning")

                flasher.exit_raw_repl()
                flasher.close()

                if failed_files:
                    self._log(f"Custom upload done with {len(failed_files)} failure(s)", "warning")
                else:
                    self._log("Custom folder upload complete ✓", "success")
                    self.bridge.progress_signal.emit(1.0)

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _handle_clear_all(self):
        if not self._ensure_window_sequence("clearing all files"):
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Clear All",
            "Are you sure you want to DELETE ALL FILES from CalSci?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )

        if confirm != QMessageBox.StandardButton.Yes:
            self._log("Clear cancelled", "info")
            return

        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No CalSci device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")

                flasher = MicroPyFlasher(port)
                self._log("Clearing all files from CalSci...", "warning")
                flasher.clean_all(self._log)
                flasher.close()

                self._log("All files cleared ✓", "success")
                self.bridge.progress_signal.emit(1.0)

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()
        
        threading.Thread(target=run, daemon=True).start()

    def _handle_launch_simulator(self):
        if not self._ensure_window_sequence("launching the simulator"):
            return

        if self.simulator_process and self.simulator_process.poll() is None:
            self._log("Simulator already running. Close it before launching another.", "warning")
            if self.statusBar():
                self.statusBar().showMessage("Simulator already running. Close it before launching another.")
            return

        try:
            # Launch the simulator in a separate process
            simulator_dir = Path(__file__).parent / "calsci_simulator"
            simulator_path = simulator_dir / "main.py"
            if not simulator_path.exists():
                raise FileNotFoundError(f"Simulator entry not found: {simulator_path}")

            python_exe = sys.executable
            if getattr(sys, "frozen", False):
                python_exe = shutil.which("python") or shutil.which("python3")
                if not python_exe:
                    raise RuntimeError("Python interpreter not found to launch simulator")

            self.simulator_process = subprocess.Popen(
                [python_exe, str(simulator_path)],
                cwd=str(simulator_dir)
            )
            self._log("Simulator launched ✓", "success")
        except Exception as e:
            self.simulator_process = None
            self._log(f"Failed to launch simulator: {e}", "error")

    def _handle_delete_selected(self):
        if not self._ensure_window_sequence("opening the delete dialog"):
            return

        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No CalSci device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")

                flasher = MicroPyFlasher(port)

                self._log("Reading CalSci file system...", "info")
                esp_files, esp_dirs = flasher.list_esp32_files()
                flasher.close()

                if not esp_files and not esp_dirs:
                    self._log("CalSci is empty — nothing to delete", "info")
                    self.bridge.operation_done_signal.emit()
                    return

                self._log(f"Found {len(esp_files)} file(s), {len(esp_dirs)} folder(s)", "info")

                self.bridge.show_delete_dialog_signal.emit(esp_files, esp_dirs, port)

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _show_delete_dialog(self, esp_files, esp_dirs, port):
        if not self._ensure_window_sequence("opening the delete dialog"):
            self.bridge.operation_done_signal.emit()
            return

        dialog = ESP32FileSelectionDialog(esp_files, esp_dirs, parent=self)
        result = dialog.exec()

        if result != QDialog.DialogCode.Accepted:
            self._log("Delete cancelled", "info")
            self.bridge.operation_done_signal.emit()
            return

        selected_items = dialog.get_selected_items()
        if not selected_items:
            self._log("No items selected", "info")
            self.bridge.operation_done_signal.emit()
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to DELETE {len(selected_items)} item(s)?\n\nThis cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )

        if confirm != QMessageBox.StandardButton.Yes:
            self._log("Delete cancelled", "info")
            self.bridge.operation_done_signal.emit()
            return

        self._log(f"Deleting {len(selected_items)} item(s)...", "warning")
        self._perform_deletion(selected_items, port)

    def _perform_deletion(self, selected_items, port):
        def run():
            try:
                flasher = MicroPyFlasher(port)

                total = len(selected_items)
                deleted = 0
                failed = 0

                files_to_delete = [(p, t) for p, t in selected_items if t == "file"]
                dirs_to_delete  = [(p, t) for p, t in selected_items if t == "folder"]

                for path, _ in files_to_delete:
                    if flasher.delete_file(path):
                        self._log(f"  Deleted: {path}", "info")
                        deleted += 1
                    else:
                        self._log(f"  Failed: {path}", "warning")
                        failed += 1
                    self.bridge.progress_signal.emit(deleted / max(total, 1))

                dirs_to_delete.sort(key=lambda x: x[0].count("/"), reverse=True)
                for path, _ in dirs_to_delete:
                    if flasher.remove_dir(path):
                        self._log(f"  📁  Deleted folder: {path}", "info")
                        deleted += 1
                    else:
                        self._log(f"  Failed folder: {path}", "warning")
                        failed += 1
                    self.bridge.progress_signal.emit(deleted / max(total, 1))

                flasher.close()

                if failed > 0:
                    self._log(f"Deletion done with {failed} failure(s)", "warning")
                else:
                    self._log(f"Successfully deleted {deleted} item(s) ✓", "success")
                    self.bridge.progress_signal.emit(1.0)

            except Exception as e:
                self._log(f"Error during deletion: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _upload_single_file(self, flasher, port, path, remote_path, auto_retry, ensure_dirs=True, use_raw=False):
        for attempt in range(2):
            try:
                if ensure_dirs:
                    flasher.ensure_dirs(remote_path)
                if use_raw:
                    if not flasher.is_raw_repl():
                        flasher.enter_raw_repl()
                    flasher.put_raw(path, remote_path)
                else:
                    flasher.put(path, remote_path)
                return flasher, True
            except Exception as e:
                if attempt == 0 and auto_retry:
                    self._log(f"Retry → {path.name} ( )", "warning")
                    try:
                        flasher.ser.dtr = False
                        flasher.ser.rts = True
                        # time.sleep(0.1)
                        flasher.ser.dtr = True
                        flasher.ser.rts = False
                        # time.sleep(0.1)
                        flasher.ser.close()
                    except Exception:
                        pass
                    time.sleep(3)
                    flasher = MicroPyFlasher(port)
                    if use_raw:
                        flasher.enter_raw_repl()
                else:
                    self._log(f"Failed: {path.name} — {str(e)[:50]}", "error")
                    return flasher, False
        return flasher, False

    def closeEvent(self, event):
        if self.simulator_process and self.simulator_process.poll() is None:
            self._log("Simulator running. Close it before exiting.", "warning")
            if self.statusBar():
                self.statusBar().showMessage("Simulator running. Close it before exiting.")
            event.ignore()
            return

        event.accept()


# ============================================================
# ===================== ENTRY POINT ==========================
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = CalSciApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
