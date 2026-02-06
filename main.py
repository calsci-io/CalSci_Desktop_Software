"""
CalSci Flasher - Main Application
CalSci MicroPython file flasher with Git repository sync.
"""

import sys
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
    QDialog
)
from PySide6.QtCore import Qt, QTimer, QSize, QEvent
from PySide6.QtGui import QColor, QFont, QAction, QTextCursor

# Import from modular files
from config import ROOT, FIRMWARE_BIN
from utils import find_esp32_ports, ensure_repo, delete_repo, repo_status, pull_repo, get_all_files
from flasher import MicroPyFlasher, MicroPyError, flash_firmware, confirm_bootloader, wait_for_reset_signal
from signal_bridge import SignalBridge
from dialogs import ESP32FileSelectionDialog
from filebrowser import ESP32FileBrowser



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
        
        self._build_ui()
        self._apply_stylesheet()

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

        self.flash_fw_cb = QCheckBox("Reflash firmware before upload")
        self.flash_fw_cb.setChecked(False)
        self.flash_fw_cb.setObjectName("retryCheckbox")
        left_layout.addWidget(self.flash_fw_cb)

        self.delta_btn = QPushButton("Sync Files")
        self.delta_btn.setObjectName("btnSecondary")
        self.delta_btn.clicked.connect(self._handle_delta_sync)
        left_layout.addWidget(self.delta_btn)

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
        self.delta_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.simulator_btn.setEnabled(True)
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
        self.delta_btn.setEnabled(False)
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
        if not ROOT.exists():
            self._log("Repository not found. Click 'Download Updates' first.", "error")
            return

        local_files = get_all_files(ROOT)
        if not local_files:
            self._log("No local files found in repository", "error")
            return

        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No ESP32 device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")
                self.bridge.progress_signal.emit(0.05)

                flasher = MicroPyFlasher(port)
                # self._log("soft resetting device…", "info")
                # flasher.reset_soft_automated(auto_cd="/apps/installed_apps", log_func=self._log)

                self._log("Scanning CalSci file system…", "info")
                esp32_sizes = flasher.get_file_sizes()
                self._log(f"CalSci has {len(esp32_sizes)} file(s)", "info")
                self.bridge.progress_signal.emit(0.10)

                local_map = {}
                for p in local_files:
                    remote = "/" + p.relative_to(ROOT).as_posix()
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
                    flasher.sync_folder_structure(files_for_sync, self._log)
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

                flasher.sync_folder_structure(files, self._log)
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
