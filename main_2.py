
import sys
import time
import threading
import json
from pathlib import Path
from queue import Queue, Empty
from collections import deque

import git
from serial.tools import list_ports
import serial

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QProgressBar, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QDialog, QDialogButtonBox,
    QHeaderView, QSplitter, QFrame, QStatusBar
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QColor, QFont, QIcon, QPalette

# ================= CONFIG =================

REPO_URL = "https://github.com/calsci-io/calsci_latest_itr"
BRANCH = "main"
ROOT = Path("./calsci_latest_itr")
SELECTIONS_FILE = Path("./upload_selections.json")

ESP32_KEYWORDS = ("Espressif",)
BAUDRATE = 115200
REPL_DELAY = 0.1

# ================= SELECTION MEMORY MANAGER =================

class SelectionMemory:
    """Manages persistent storage of file selections"""

    @staticmethod
    def save_selections(selected_paths):
        try:
            paths_to_save = [str(p) for p in selected_paths]
            with open(SELECTIONS_FILE, 'w') as f:
                json.dump(paths_to_save, f, indent=2)
        except Exception as e:
            print(f"Error saving selections: {e}")

    @staticmethod
    def load_selections():
        try:
            if SELECTIONS_FILE.exists():
                with open(SELECTIONS_FILE, 'r') as f:
                    paths = json.load(f)
                    # Filter to only return paths that still exist
                    return [Path(p) for p in paths if Path(p).exists()]
        except Exception as e:
            print(f"Error loading selections: {e}")
        return []

    @staticmethod
    def clear_selections():
        try:
            if SELECTIONS_FILE.exists():
                SELECTIONS_FILE.unlink()
        except Exception as e:
            print(f"Error clearing selections: {e}")

    @staticmethod
    def has_selections():
        return SELECTIONS_FILE.exists() and SELECTIONS_FILE.stat().st_size > 0


# ================= ESP32 PORT DETECTION =================

def find_esp32_ports():
    ports = []
    for p in list_ports.comports():
        text = f"{p.manufacturer} {p.description}".lower()
        if any(k.lower() in text for k in ESP32_KEYWORDS):
            ports.append(p.device)
    return ports


# ================= GIT HELPERS =================

def ensure_repo(log_func):
    if not ROOT.exists():
        log_func("Cloning repository...", "info")
        git.Repo.clone_from(REPO_URL, ROOT, branch=BRANCH)
        log_func("Repository cloned successfully", "success")
    else:
        log_func("Repository found", "info")


def repo_status(log_func):
    repo = git.Repo(ROOT)
    repo.remotes.origin.fetch()
    behind = sum(1 for _ in repo.iter_commits(f"{BRANCH}..origin/{BRANCH}"))
    ahead = sum(1 for _ in repo.iter_commits(f"origin/{BRANCH}..{BRANCH}"))
    return ahead, behind


def pull_repo(log_func):
    repo = git.Repo(ROOT)
    repo.remotes.origin.pull()
    log_func("Repository updated", "success")


# ================= FILE FILTER =================

def should_skip(path: Path) -> bool:
    if any(part.startswith(".") for part in path.parts):
        return True
    if path.name in {".gitignore", ".gitattributes"}:
        return True
    if path.suffix == ".pyc":
        return True
    return False


def get_all_files(root_path):
    """Get all files from the root path, scanning fresh from disk each time."""
    return [p for p in root_path.rglob("*") if p.is_file() and not should_skip(p)]


# ============================================================
# ================= MICRO-PY FLASHER =========================
# ============================================================

class MicroPyError(Exception):
    pass


class MicroPyFlasher:
    def __init__(self, port, baudrate=BAUDRATE):
        self.port = port
        self.ser = serial.Serial(port, baudrate, timeout=0.1)
        self._wait_ready(2.0)
        self._enter_repl()

    def close(self):
        self.ser.close()

    def _wait_ready(self, duration):
        end_time = time.perf_counter() + duration
        while time.perf_counter() < end_time:
            pass

    def _enter_repl(self):
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.3)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.3)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x02")
        self._wait_ready(0.3)
        self.ser.reset_input_buffer()

    def _exec(self, code: str):
        self.ser.write(code.encode() + b"\r")
        self._wait_ready(REPL_DELAY)

    def _exec_raw(self, code):
        """Execute code in RAW REPL mode - sends code then Ctrl+D to execute."""
        self.ser.write(code.encode() + b"\r")
        self._wait_ready(0.05)
        self.ser.write(b"\x04")  # Ctrl+D = execute
        self._wait_ready(0.1)

    def _exec_capture(self, code: str) -> str:
        self._exec("import sys")
        self._exec("sys.stdout.write('<<<')")
        for line in code.strip().splitlines():
            self._exec(line)
        self._exec("sys.stdout.write('>>>')")

        out = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 2:
            if self.ser.in_waiting:
                out += self.ser.read(self.ser.in_waiting)
            if b">>>" in out:
                break

        data = out.decode(errors="ignore")
        if "Traceback" in data:
            raise MicroPyError(data)
        return data.split("<<<")[-1].split(">>>")[0]

    def mkdir(self, path):
        """Create a single directory on ESP32 with verification."""
        # Enter RAW REPL
        self.ser.write(b"\x01")
        self._wait_ready(0.2)
        self.ser.reset_input_buffer()
        
        # Create directory using _exec_raw (sends code then Ctrl+D to execute)
        self._exec_raw(f"try:\n    os.mkdir('{path}')\nexcept:\n    pass")
        
        # Verify directory exists
        self.ser.reset_input_buffer()
        self._exec_raw(f"try:\n    os.stat('{path}')\n    print('EXISTS')\nexcept:\n    print('MISSING')")
        
        # Read response and check for EXISTS
        response = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 1:
            if self.ser.in_waiting:
                response += self.ser.read(self.ser.in_waiting)
            if b">>>" in response:
                break
        
        result = response.decode(errors="ignore")
        return "EXISTS" in result


    def ensure_dirs(self, remote_path: str):
        """Create each directory in the path sequentially."""
        parts = remote_path.split("/")[:-1]  # exclude filename
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            self.mkdir(cur)

    def list_esp32_dirs(self):
        """Get list of all directories on ESP32."""
        # Enter RAW REPL
        self.ser.write(b"\x01")
        self._wait_ready(0.2)
        self.ser.reset_input_buffer()
        
        # List all directories recursively in a single exec block
        self._exec("""import os
import json
def list_dirs(path, depth=0, max_depth=5):
    if depth > max_depth:
        return []
    result = []
    try:
        for entry in os.ilistdir(path):
            if entry[1] == 0x4000:
                full_path = path + '/' + entry[0] if path else entry[0]
                result.append(full_path)
                result.extend(list_dirs(full_path, depth + 1, max_depth))
    except:
        pass
    return result
print(json.dumps(list_dirs('')))""")
        self._wait_ready(0.5)
        
        # Read response
        response = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 2:
            if self.ser.in_waiting:
                response += self.ser.read(self.ser.in_waiting)
            if b">>>" in response:
                break
        
        try:
            result = response.decode(errors="ignore")
            # Find JSON in response
            start_idx = result.find("[")
            end_idx = result.rfind("]")
            if start_idx != -1 and end_idx != -1:
                json_str = result[start_idx:end_idx + 1]
                return set(json.loads(json_str))
        except:
            pass
        return set()

    def list_esp32_files(self):
        """Get list of all files on ESP32 (returns set of file paths)."""
        # Enter RAW REPL
        self.ser.write(b"\x01")
        self._wait_ready(0.2)
        self.ser.reset_input_buffer()
        
        # List all files recursively in a single exec block
        self._exec("""import os
import json
def list_files(path, depth=0, max_depth=10):
    if depth > max_depth:
        return []
    result = []
    try:
        for entry in os.ilistdir(path):
            if entry[1] == 0x8000:  # File type
                full_path = path + '/' + entry[0] if path else entry[0]
                result.append(full_path)
            elif entry[1] == 0x4000:  # Directory type
                full_path = path + '/' + entry[0] if path else entry[0]
                result.extend(list_files(full_path, depth + 1, max_depth))
    except:
        pass
    return result
print(json.dumps(list_files('')))""")
        self._wait_ready(0.5)
        
        # Read response
        response = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 2:
            if self.ser.in_waiting:
                response += self.ser.read(self.ser.in_waiting)
            if b">>>" in response:
                break
        
        try:
            result = response.decode(errors="ignore")
            # Find JSON in response
            start_idx = result.find("[")
            end_idx = result.rfind("]")
            if start_idx != -1 and end_idx != -1:
                json_str = result[start_idx:end_idx + 1]
                return set(json.loads(json_str))
        except:
            pass
        return set()

    def delete_file(self, path):
        """Delete a single file from ESP32."""
        # Enter RAW REPL
        self.ser.write(b"\x01")
        self._wait_ready(0.2)
        self.ser.reset_input_buffer()
        
        # Delete the file
        self._exec(f"""import os
try:
    os.remove('{path}')
    print('DELETED')
except Exception as e:
    print('ERROR: ' + str(e))""")
        self._wait_ready(0.2)
        
        # Read response
        response = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 1:
            if self.ser.in_waiting:
                response += self.ser.read(self.ser.in_waiting)
            if b">>>" in response:
                break
        
        result = response.decode(errors="ignore")
        return "DELETED" in result

    def sync_cleanup(self, local_files, log_func):
        """Delete files AND directories from ESP32 that don't exist in local software folder.
        
        Args:
            local_files: List of Path objects for local files
            log_func: Function to call for logging
        """
        log_func("Checking for orphaned files/folders on ESP32...", "info")
        
        # Get all files and directories from ESP32
        esp_files = self.list_esp32_files()
        esp_dirs = self.list_esp32_dirs()
        
        # Convert local files to relative paths (as posix strings for comparison)
        local_file_set = set()
        local_dir_set = set()
        for path in local_files:
            rel_path = path.relative_to(ROOT).as_posix()
            local_file_set.add(rel_path)
            # Add parent directories
            parts = rel_path.split("/")
            for i in range(len(parts) - 1):
                local_dir_set.add("/".join(parts[:i + 1]))
        
        # Find files to delete (exist on ESP32 but not in local)
        files_to_delete = []
        for esp_file in esp_files:
            # Remove leading slash for comparison
            esp_file_rel = esp_file.lstrip("/")
            if esp_file_rel not in local_file_set:
                files_to_delete.append(esp_file)
        
        # Find directories to delete (exist on ESP32 but not in local)
        # Only delete if the directory is empty or all its contents are also being deleted
        dirs_to_delete = []
        for esp_dir in esp_dirs:
            esp_dir_rel = esp_dir.lstrip("/")
            if esp_dir_rel not in local_dir_set:
                dirs_to_delete.append(esp_dir)
        
        if not files_to_delete and not dirs_to_delete:
            log_func("No orphaned files/folders found ✓", "success")
            return
        
        log_func(f"Found {len(files_to_delete)} orphaned file(s) and {len(dirs_to_delete)} orphaned folder(s) to delete", "info")
        
        # Delete files first (in reverse order to handle nested paths correctly)
        files_to_delete.sort(reverse=True)
        deleted_count = 0
        
        for file_path in files_to_delete:
            file_rel = file_path.lstrip("/")
            if self.delete_file(file_path):
                log_func(f"  - Deleted file: {file_rel}", "info")
                deleted_count += 1
            else:
                log_func(f"  ! Failed to delete file: {file_rel}", "warning")
        
        # Then delete empty directories (in reverse order - deepest first)
        # Only delete if the directory is actually empty
        dirs_to_delete.sort(reverse=True)
        for dir_path in dirs_to_delete:
            dir_rel = dir_path.lstrip("/")
            # Try to remove directory (will fail if not empty)
            if self.remove_empty_dir(dir_rel):
                log_func(f"  - Deleted folder: {dir_rel}", "info")
            else:
                # Directory might not be empty, try recursive delete
                if self.remove_dir(dir_rel):
                    log_func(f"  - Deleted folder (with contents): {dir_rel}", "info")
        
        log_func(f"Cleanup complete: {deleted_count} file(s) removed ✓", "success")

    def remove_empty_dir(self, path):
        """Remove an empty directory on ESP32."""
        # Enter RAW REPL
        self.ser.write(b"\x01")
        self._wait_ready(0.2)
        self.ser.reset_input_buffer()
        
        # Remove directory (will only work if empty)
        self._exec(f"""import os
try:
    os.rmdir('{path}')
    print('DELETED')
except Exception as e:
    print('ERROR: ' + str(e))""")
        self._wait_ready(0.2)
        
        # Read response
        response = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 1:
            if self.ser.in_waiting:
                response += self.ser.read(self.ser.in_waiting)
            if b">>>" in response:
                break
        
        result = response.decode(errors="ignore")
        return "DELETED" in result

    def remove_dir(self, path):
        """Remove a directory recursively on ESP32."""
        # Enter RAW REPL
        self.ser.write(b"\x01")
        self._wait_ready(0.2)
        self.ser.reset_input_buffer()
        
        # Remove directory recursively in a single exec block
        self._exec(f"""import os
def rm(path):
    try:
        for entry in os.ilistdir(path):
            full = path + '/' + entry[0] if path else entry[0]
            if entry[1] == 0x4000:
                rm(full)
            else:
                os.remove(full)
        os.rmdir(path)
    except:
        pass
rm('{path}')""")
        self._wait_ready(0.2)
        return True

    def sync_folder_structure(self, files, log_func):
        """Sync folder structure by creating required folders in order."""
        # Collect all required folders from the file list
        required_folders = set()
        for path in files:
            rel = path.relative_to(ROOT)
            parts = list(rel.parts)
            # Add all parent folders
            for i in range(len(parts) - 1):
                folder_parts = parts[:i + 1]
                folder_path = "/".join(folder_parts)
                required_folders.add(folder_path)
        
        # Sort by slash count ascending (parent folders first)
        sorted_folders = sorted(required_folders, key=lambda f: len(f.split("/")))
        
        log_func("Creating folder structure…", "info")
        
        for folder in sorted_folders:
            success = self.mkdir(folder)
            if success:
                log_func(f"  + {folder}", "info")
            else:
                log_func(f"  ! {folder} (failed)", "warning")
        
        log_func("Folder structure synced ✓", "success")

    def put(self, local: Path, remote: str):
        """Upload a file to the device using chunked writes in raw REPL."""
        CHUNK_SIZE = 128
        data = local.read_bytes()
        total_len = len(data)
        num_chunks = (total_len + CHUNK_SIZE - 1) // CHUNK_SIZE

        # Enter raw REPL cleanly
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.3)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.5)
        self.ser.reset_input_buffer()

        # Build the full file-write script
        lines = []
        lines.append('import os')
        lines.append('try:')
        lines.append(f'    os.remove("{remote}")')
        lines.append('except OSError:')
        lines.append('    pass')
        lines.append(f'f = open("{remote}", "wb")')
        for i in range(num_chunks):
            chunk = data[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
            lines.append(f'f.write({repr(chunk)})')
        lines.append('f.close()')
        lines.append('print("OK")')

        code = "\r\n".join(lines) + "\r\n"
        self.ser.write(code.encode())
        self._wait_ready(0.1)

        # Execute
        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 5:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
            if b">>>" in output or (b">" in output and b"OK" in output):
                break
            time.sleep(0.05)

        # Check for errors - if Traceback appears BEFORE OK, it's a real error
        # If OK appears before Traceback, the upload succeeded but there might be other issues
        ok_pos = output.find(b"OK")
        traceback_pos = output.find(b"Traceback")

        if traceback_pos != -1 and (ok_pos == -1 or traceback_pos < ok_pos):
            # Traceback appeared before or without OK - real error
            self._log(f"Upload error detected", "error")
            self.ser.write(b"\x02")
            self._wait_ready(0.2)
            raise MicroPyError(output.decode(errors="ignore"))

        if b"OK" not in output:
            # No OK received at all
            self._log(f"Missing OK confirmation", "error")
            self._log(f"Output: {output[:200]}", "error")
            self.ser.write(b"\x02")
            self._wait_ready(0.2)
            raise MicroPyError(f"No OK confirmation")

        # Exit raw REPL
        self.ser.write(b"\x02")
        self._wait_ready(0.2)

    def exit_raw_repl(self):
        """Safety call — ensure we're back in normal REPL"""
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.1)
        self.ser.write(b"\x02")
        self._wait_ready(0.1)

    def clean_all(self, log_func=None):
        """Delete all files and folders from ESP32 root directory.
        This is equivalent to the clean.sh script but done natively without ampy.
        """
        if log_func:
            log_func("⚠️  Starting ESP32 cleanup...", "warning")
        
        # Ensure we're in normal REPL mode
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.3)
        self.ser.reset_input_buffer()
        
        # Define the recursive removal function
        cleanup_code = """
import os

def rmtree(path):
    try:
        for entry in os.ilistdir(path):
            name = entry[0]
            full_path = path + "/" + name if path else name
            if entry[1] == 0x4000:  # directory
                rmtree(full_path)
                try:
                    os.rmdir(full_path)
                    print("DIR_DEL:", full_path)
                except Exception as e:
                    print("DIR_ERR:", full_path, str(e))
            else:  # file
                try:
                    os.remove(full_path)
                    print("FILE_DEL:", full_path)
                except Exception as e:
                    print("FILE_ERR:", full_path, str(e))
    except Exception as e:
        print("ERR:", str(e))

print("CLEANUP_START")
rmtree("")
print("CLEANUP_DONE")
"""
        
        # Send the cleanup code line by line
        for line in cleanup_code.strip().split('\n'):
            self.ser.write(line.encode() + b'\r')
            self._wait_ready(0.05)
        
        # Wait for completion and collect output
        output = b""
        start = time.perf_counter()
        timeout = 30  # 30 seconds timeout for cleanup
        
        while time.perf_counter() - start < timeout:
            if self.ser.in_waiting:
                chunk = self.ser.read(self.ser.in_waiting)
                output += chunk
                
                # Log deletions in real-time if log function provided
                if log_func and chunk:
                    decoded = chunk.decode(errors="ignore")
                    for line in decoded.split('\n'):
                        line = line.strip()
                        if line.startswith("FILE_DEL:"):
                            log_func(f"  🗑️  {line.replace('FILE_DEL:', '').strip()}", "info")
                        elif line.startswith("DIR_DEL:"):
                            log_func(f"  📁  {line.replace('DIR_DEL:', '').strip()}", "info")
                        elif line.startswith("FILE_ERR:") or line.startswith("DIR_ERR:"):
                            log_func(f"  ⚠️  {line}", "warning")
            
            # Check if cleanup is done
            if b"CLEANUP_DONE" in output:
                if log_func:
                    log_func("✅ ESP32 cleanup complete", "success")
                break
            
            time.sleep(0.1)
        
        # Reset to normal REPL
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.2)
        self.ser.reset_input_buffer()
        
        if b"CLEANUP_DONE" not in output:
            raise MicroPyError("Cleanup timeout - operation may be incomplete")
        
        return True
# ============================================================
# ================= SIGNAL BRIDGE (Thread → UI) ==============
# ============================================================

class SignalBridge(QObject):
    log_signal = Signal(str, str)           # message, type
    progress_signal = Signal(float)         # 0.0 → 1.0
    operation_done_signal = Signal()        # unlock buttons
    device_status_signal = Signal(bool)     # device connected status


# ============================================================
# ================= FILE SELECTION DIALOG =====================
# ============================================================

class FileSelectionDialog(QDialog):
    def __init__(self, all_files, root_path, pre_selected_files=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Files to Upload")
        self.setMinimumSize(720, 560)
        self.root_path = root_path
        self.all_files = all_files
        self.pre_selected = set(str(p) for p in (pre_selected_files or []))

        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ─── Header info ──────────────────────
        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        layout.addWidget(self.info_label)

        # ─── Tree widget ──────────────────────
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(22)
        self.tree.setExpandsOnDoubleClick(False)  # Single-click expand/collapse
        self.tree.itemClicked.connect(self._on_item_clicked)  # Handle single-click
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #2d2d2d;
                color: #e8e8e8;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                font-size: 13px;
            }
            QTreeWidget::item {
                padding: 5px 4px;
                border-bottom: 1px solid #333333;
            }
            QTreeWidget::item:hover {
                background-color: #383838;
            }
            QTreeWidget::item:selected {
                background-color: #3a4a5a;
                color: #ffffff;
            }
            QTreeWidget::branch:has-siblings:!adjoins-item {
                border-image: none;
                border-left: 1px solid #4a4a4a;
            }
            QTreeWidget::branch:!has-siblings:!adjoins-item {
                border-image: none;
            }
            QHeaderView::section {
                background-color: #1e1e1e;
                color: #a0a0a0;
                border: none;
                border-bottom: 1px solid #3a3a3a;
                padding: 6px 8px;
                font-weight: 500;
                font-size: 12px;
            }
        """)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        # ─── Bottom buttons ───────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.select_all_btn = QPushButton("☑  Select All")
        self.deselect_all_btn = QPushButton("☐  Deselect All")
        self.upload_btn = QPushButton("⬆  Upload")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.select_all_btn, self.deselect_all_btn, self.cancel_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    color: #e0e0e0;
                    border: 1px solid #4a4a4a;
                    border-radius: 5px;
                    padding: 8px 18px;
                    font-size: 13px;
                }
                QPushButton:hover { background-color: #4a4a4a; }
                QPushButton:pressed { background-color: #333333; }
            """)

        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: #e95420;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 8px 22px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #fd6834; }
            QPushButton:pressed { background-color: #d54c0c; }
            QPushButton:disabled { background-color: #555555; color: #777777; }
        """)

        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.upload_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # ─── Connect buttons ──────────────────
        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.upload_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self._update_upload_btn_text()

    def _populate_tree(self):
        """Build a hierarchical QTreeWidget from the flat file list."""
        self.tree.setUpdatesEnabled(False)
        folder_map = {}  # path_str → QTreeWidgetItem (folder)

        # Sort: folders first, then files, alphabetically
        sorted_files = sorted(self.all_files, key=lambda p: (str(p.parent), p.name))

        for file_path in sorted_files:
            rel = file_path.relative_to(self.root_path)
            parts = list(rel.parts)

            parent_item = None  # top-level if None

            # Ensure all parent folders exist in the tree
            for i in range(len(parts) - 1):
                folder_key = str(Path(*parts[: i + 1]))
                if folder_key not in folder_map:
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, parts[i])
                    folder_item.setText(1, "")
                    folder_item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsAutoTristate
                    )
                    folder_item.setCheckState(0, Qt.CheckState.Unchecked)
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, None)  # None = folder

                    # Folder icon color
                    folder_item.setForeground(0, QColor("#e95420"))

                    if parent_item is None:
                        self.tree.addTopLevelItem(folder_item)
                    else:
                        parent_item.addChild(folder_item)
                        parent_item.setExpanded(False)  # Ensure parent stays collapsed

                    folder_map[folder_key] = folder_item
                    folder_item.setExpanded(False)  # Start collapsed

                parent_item = folder_map[folder_key]

            # Add the file itself
            file_item = QTreeWidgetItem()
            file_item.setText(0, parts[-1])

            size_bytes = file_path.stat().st_size
            file_item.setText(1, self._format_size(size_bytes))

            file_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )

            # Pre-select if in saved selections
            if str(file_path) in self.pre_selected:
                file_item.setCheckState(0, Qt.CheckState.Checked)
            else:
                file_item.setCheckState(0, Qt.CheckState.Unchecked)

            file_item.setData(0, Qt.ItemDataRole.UserRole, str(file_path))  # store path
            file_item.setForeground(0, QColor("#d0d0d0"))

            if parent_item is None:
                self.tree.addTopLevelItem(file_item)
            else:
                parent_item.addChild(file_item)

        # Don't expand all - start collapsed
        self.tree.collapseAll()
        self.tree.setUpdatesEnabled(True)
        self._update_upload_btn_text()

    # ─── Tree interaction helpers ─────────────────────────
    def _on_item_clicked(self, item, column):
        """Toggle folder expansion/collapse on single-click."""
        if item.childCount() > 0:  # It's a folder
            if item.isExpanded():
                item.setExpanded(False)
            else:
                item.setExpanded(True)

    def _on_item_changed(self, item, column):
        if column == 0:
            self._update_upload_btn_text()

    def _select_all(self):
        self._set_all_check(Qt.CheckState.Checked)

    def _deselect_all(self):
        self._set_all_check(Qt.CheckState.Unchecked)

    def _set_all_check(self, state):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            self._set_recursive(item, state)
        self.tree.blockSignals(False)
        self._update_upload_btn_text()

    def _set_recursive(self, item, state):
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_recursive(item.child(i), state)

    def _update_upload_btn_text(self):
        count = len(self.get_selected_files())
        if count > 0:
            self.upload_btn.setText(f"⬆  Upload ({count})")
            self.upload_btn.setEnabled(True)
        else:
            self.upload_btn.setText("⬆  Upload")
            self.upload_btn.setEnabled(False)
        self.info_label.setText(f"{count} / {len(self.all_files)} files selected")

    # ─── Public API ───────────────────────────────────────
    def get_selected_files(self):
        """Return list of Path objects for every checked file."""
        selected = []
        self._collect_checked(self.tree.invisibleRootItem(), selected)
        return selected

    def _collect_checked(self, item, result):
        for i in range(item.childCount()):
            child = item.child(i)
            path_str = child.data(0, Qt.ItemDataRole.UserRole)
            if path_str is not None:  # it's a file
                if child.checkState(0) == Qt.CheckState.Checked:
                    result.append(Path(path_str))
            self._collect_checked(child, result)  # recurse into folders

    @staticmethod
    def _format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"


# ============================================================
# ================= MAIN APPLICATION ==========================
# ============================================================

class CalSciApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CalSci Flasher")
        self.setMinimumSize(820, 660)

        self.bridge = SignalBridge()
        self.bridge.log_signal.connect(self._on_log)
        self.bridge.progress_signal.connect(self._on_progress)
        self.bridge.operation_done_signal.connect(self._on_operation_done)
        self.bridge.device_status_signal.connect(self._update_device_status)

        self.operation_in_progress = False
        self._build_ui()
        self._apply_stylesheet()
        
        # Start device detection timer
        self.device_timer = QTimer()
        self.device_timer.timeout.connect(self._check_device_status)
        self.device_timer.start(2000)  # Check every 2 seconds
        self._check_device_status()  # Initial check

    # ─── UI Construction ──────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ─── Header bar ─────────────────────────────────
        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 14, 20, 14)

        title_label = QLabel("CalSci Flasher")
        title_label.setObjectName("titleLabel")
        header_layout.addWidget(title_label)

        subtitle_label = QLabel("ESP32 MicroPython Uploader")
        subtitle_label.setObjectName("subtitleLabel")
        header_layout.addWidget(subtitle_label)

        header_layout.addStretch()

        # ESP32 status indicator
        self.esp_status_label = QLabel("● No device")
        self.esp_status_label.setObjectName("espStatusDisconnected")
        header_layout.addWidget(self.esp_status_label)

        main_layout.addWidget(header)

        # ─── Body ───────────────────────────────────────
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(16)

        # ── Left column: buttons ────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.update_btn = QPushButton("⬇  Download Updates")
        self.update_btn.setObjectName("btnSecondary")
        self.update_btn.clicked.connect(self._handle_update)
        left_layout.addWidget(self.update_btn)

        self.flash_btn = QPushButton("⚡  Flash All Files")
        self.flash_btn.setObjectName("btnPrimary")
        self.flash_btn.clicked.connect(self._handle_flash)
        left_layout.addWidget(self.flash_btn)

        self.upload_btn = QPushButton("📂  Upload Selected…")
        self.upload_btn.setObjectName("btnSecondary")
        self.upload_btn.clicked.connect(self._handle_upload_selected)
        left_layout.addWidget(self.upload_btn)

        # Auto-retry checkbox
        self.auto_retry_cb = QCheckBox("Auto-retry on failure\n(hard reset + 5s wait)")
        self.auto_retry_cb.setChecked(True)
        self.auto_retry_cb.setObjectName("retryCheckbox")
        left_layout.addWidget(self.auto_retry_cb)

        left_layout.addStretch()

        # ── Right column: progress + log ────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setObjectName("progressBar")
        right_layout.addWidget(self.progress_bar)

        # Current file label
        self.current_file_label = QLabel("Idle")
        self.current_file_label.setObjectName("currentFileLabel")
        right_layout.addWidget(self.current_file_label)

        # Log panel
        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setObjectName("logPanel")
        right_layout.addWidget(self.log_panel)

        body_layout.addWidget(left_panel, stretch=1)
        body_layout.addWidget(right_panel, stretch=3)
        main_layout.addWidget(body)

        # ─── Status bar ─────────────────────────────────
        status_bar = QStatusBar()
        status_bar.showMessage("Ready")
        self.setStatusBar(status_bar)

    # ─── Stylesheet ───────────────────────────────────────
    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }

            /* Header */
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

            /* Buttons */
            QPushButton#btnPrimary {
                background-color: #e95420;
                color: #fff;
                border: none;
                border-radius: 6px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: 600;
                min-width: 200px;
            }
            QPushButton#btnPrimary:hover { background-color: #fd6834; }
            QPushButton#btnPrimary:pressed { background-color: #d54c0c; }
            QPushButton#btnPrimary:disabled { background-color: #444; color: #666; }

            QPushButton#btnSecondary {
                background-color: #2a2a2a;
                color: #d0d0d0;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 12px 20px;
                font-size: 14px;
                min-width: 200px;
            }
            QPushButton#btnSecondary:hover { background-color: #363636; }
            QPushButton#btnSecondary:pressed { background-color: #222; }
            QPushButton#btnSecondary:disabled { background-color: #222; color: #555; }

            /* Checkbox */
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

            /* Progress bar */
            QProgressBar#progressBar {
                height: 18px;
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

            /* Current file label */
            QLabel#currentFileLabel {
                color: #777;
                font-size: 12px;
                font-style: italic;
            }

            /* Log panel */
            QTextEdit#logPanel {
                background-color: #161616;
                border: 1px solid #2e2e2e;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                color: #c0c0c0;
            }

            /* Status bar */
            QStatusBar {
                background-color: #141414;
                border-top: 1px solid #333;
                color: #666;
                font-size: 11px;
                padding: 4px 12px;
            }
        """)

    # ─── Device status monitoring ─────────────────────────
    def _check_device_status(self):
        """Check if ESP32 is connected and update UI"""
        if not self.operation_in_progress:
            ports = find_esp32_ports()
            self.bridge.device_status_signal.emit(len(ports) > 0)

    def _update_device_status(self, connected):
        """Update device status indicator"""
        if connected:
            self.esp_status_label.setText("● Device connected")
            self.esp_status_label.setObjectName("espStatusConnected")
        else:
            self.esp_status_label.setText("● No device")
            self.esp_status_label.setObjectName("espStatusDisconnected")
        # Reapply stylesheet to update colors
        self.esp_status_label.style().unpolish(self.esp_status_label)
        self.esp_status_label.style().polish(self.esp_status_label)

    # ─── Log helper (called from threads via signal) ──────
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
        self.log_panel.insertHtml(html)
        self.log_panel.moveCursor(self.log_panel.textCursor().MoveOperation.End)
        self.current_file_label.setText(message)

    def _on_progress(self, value):
        self.progress_bar.setValue(int(value * 100))

    def _on_operation_done(self):
        self.operation_in_progress = False
        self.update_btn.setEnabled(True)
        self.flash_btn.setEnabled(True)
        self.upload_btn.setEnabled(True)
        self._check_device_status()  # Refresh device status

    # ─── Lock / unlock buttons during operations ─────────
    def _lock_buttons(self):
        self.operation_in_progress = True
        self.update_btn.setEnabled(False)
        self.flash_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        self.progress_bar.setValue(0)

    # ─── Thread-safe log wrapper ──────────────────────────
    def _log(self, message, msg_type="info"):
        self.bridge.log_signal.emit(message, msg_type)

    # ============================================================
    # ================== DOWNLOAD UPDATES =========================
    # ============================================================
    def _handle_update(self):
        self._lock_buttons()

        def run():
            try:
                self._log("Checking repository…", "info")
                self.bridge.progress_signal.emit(0.1)
                ensure_repo(self._log)

                self._log("Fetching updates…", "info")
                self.bridge.progress_signal.emit(0.3)
                ahead, behind = repo_status(self._log)

                if behind > 0:
                    self._log(f"Downloading {behind} new commits…", "info")
                    self.bridge.progress_signal.emit(0.6)
                    pull_repo(self._log)
                    self._log("Update complete ✓", "success")
                else:
                    self._log("Already up to date ✓", "success")

                self.bridge.progress_signal.emit(1.0)
            except Exception as e:
                self._log(f"Error: {e}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    # ============================================================
    # ================== FLASH ALL FILES ==========================
    # ============================================================
    def _handle_flash(self):
        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No ESP32 device detected")

                port = ports[0]
                self._log(f"ESP32 found: {port}", "success")
                self.bridge.progress_signal.emit(0.05)
                flasher = MicroPyFlasher(port)
                self._log("cleaning all files")
                flasher.clean_all()
                self._log("cleaned all files")
                files = get_all_files(ROOT)  # Fresh scan from disk
                
                if not files:
                    self._log("No files to upload", "info")
                    return

                # Step 1: Sync folder structure first
                flasher.sync_folder_structure(files, self._log)
                self.bridge.progress_signal.emit(0.05)

                # Step 1.5: Cleanup orphaned files from ESP32
                flasher.sync_cleanup(files, self._log)
                self.bridge.progress_signal.emit(0.1)

                # Step 2: Upload files
                total_size = max(sum(p.stat().st_size for p in files), 1)  # Avoid division by zero
                uploaded = 0
                failed_files = []
                auto_retry = self.auto_retry_cb.isChecked()

                self._log(f"Uploading {len(files)} files…", "info")

                for i, path in enumerate(files, 1):
                    remote_path = path.relative_to(ROOT).as_posix()

                    flasher, success = self._upload_single_file(
                        flasher, port, path, remote_path, auto_retry
                    )

                    if success:
                        uploaded += max(path.stat().st_size, 1)  # Avoid division by zero
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

    # ============================================================
    # ================== UPLOAD SELECTED ==========================
    # ============================================================
    def _handle_upload_selected(self):
        if not ROOT.exists():
            self._log("Repository not found. Click 'Download Updates' first.", "error")
            return

        files = get_all_files(ROOT)  # Fresh scan from disk
        if not files:
            self._log("No files found in repository", "error")
            return

        pre_selected = SelectionMemory.load_selections()

        dialog = FileSelectionDialog(files, ROOT, pre_selected, parent=self)
        result = dialog.exec()

        if result != QDialog.DialogCode.Accepted:
            self._log("Upload cancelled", "info")
            return

        selected_files = dialog.get_selected_files()
        if not selected_files:
            self._log("No files selected", "info")
            return

        self._log(f"Selected {len(selected_files)} file(s)", "info")
        SelectionMemory.save_selections(selected_files)

        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No ESP32 device detected")

                port = ports[0]
                self._log(f"ESP32 found: {port}", "success")

                flasher = MicroPyFlasher(port)
                
                if not selected_files:
                    self._log("No files selected", "info")
                    return

                # Step 1: Sync folder structure first
                flasher.sync_folder_structure(selected_files, self._log)
                self.bridge.progress_signal.emit(0.1)

                # Step 1.5: Cleanup orphaned files from ESP32
                flasher.sync_cleanup(selected_files, self._log)
                self.bridge.progress_signal.emit(0.2)

                # Step 2: Upload files
                total_size = max(sum(p.stat().st_size for p in selected_files), 1)  # Avoid division by zero
                uploaded = 0
                failed_files = []
                auto_retry = self.auto_retry_cb.isChecked()

                self._log(f"Uploading {len(selected_files)} file(s)…", "info")

                for i, path in enumerate(selected_files, 1):
                    remote_path = path.relative_to(ROOT).as_posix()

                    flasher, success = self._upload_single_file(
                        flasher, port, path, remote_path, auto_retry
                    )

                    if success:
                        uploaded += max(path.stat().st_size, 1)  # Avoid division by zero
                        self.bridge.progress_signal.emit(0.1 + (uploaded / total_size) * 0.9)
                        self._log(f"[{i}/{len(selected_files)}] {path.name}", "info")
                    else:
                        failed_files.append(path.name)
                        self._log(f"⚠ Skipped: {path.name}", "warning")

                flasher.exit_raw_repl()
                flasher.close()

                if failed_files:
                    self._log(f"Done with {len(failed_files)} failure(s)", "warning")
                else:
                    self._log("Upload complete ✓", "success")
                    self.bridge.progress_signal.emit(1.0)

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    # ============================================================
    # ========== SINGLE FILE UPLOAD WITH AUTO-RETRY ===============
    # ============================================================
    def _upload_single_file(self, flasher, port, path, remote_path, auto_retry):
        """
        Upload one file using ensure_dirs for directories and put() for the file.
        Returns (flasher, success_bool).  flasher may be a new instance after retry.
        """
        for attempt in range(2):
            try:
                # Create directories if needed using ensure_dirs (sequential mkdir with verification)
                flasher.ensure_dirs(remote_path)
                
                # Upload file using put method
                flasher.put(path, remote_path)
                return flasher, True
            except Exception as e:
                if attempt == 0 and auto_retry:
                    self._log(f"Retry → {path.name} (hard reset…)", "warning")
                    try:
                        flasher.ser.dtr = False
                        flasher.ser.rts = True
                        time.sleep(0.1)
                        flasher.ser.dtr = True
                        flasher.ser.rts = False
                        time.sleep(0.1)
                        flasher.ser.close()
                    except Exception:
                        pass
                    time.sleep(5)
                    flasher = MicroPyFlasher(port)
                else:
                    self._log(f"Failed: {path.name} — {str(e)[:50]}", "error")
                    return flasher, False
        return flasher, False


# ============================================================
# ===================== ENTRY POINT ==========================
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # consistent cross-platform look
    window = CalSciApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()