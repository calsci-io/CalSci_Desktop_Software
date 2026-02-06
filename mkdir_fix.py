import ast
import textwrap
import sys
import time
import threading
import json
import hashlib
import shutil
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
    QHeaderView, QSplitter, QFrame, QStatusBar, QMessageBox,
    QPlainTextEdit, QTabWidget, QMenu
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QAction, QTextCursor

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


def delete_repo(log_func):
    """Delete the local repository if it exists."""
    if ROOT.exists():
        log_func("Deleting existing repository...", "info")
        shutil.rmtree(ROOT)
        log_func("Repository deleted", "success")
    else:
        log_func("No existing repository to delete", "info")


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
        self._keepalive_running = False
        self._keepalive_thread = None
        self._wait_ready(2.0)
        self._enter_repl()

    def _keepalive_worker(self):
        """Background worker that sends periodic keep-alive signals to prevent ESP32 sleep."""
        while self._keepalive_running:
            try:
                self._send_keepalive()
            except Exception:
                # If sending fails (e.g., device disconnected), stop the keep-alive
                break
            time.sleep(2.0)  # Send keep-alive every 2 seconds

    def _send_keepalive(self):
        """Send a simple command to keep the ESP32 awake."""
        # Send a simple print command that doesn't produce meaningful output
        # but keeps the ESP32 REPL active
        try:
            self.ser.write(b"print(1)\r")
            self._wait_ready(10)
            # Clear any response
            self.ser.reset_input_buffer()
        except Exception:
            pass

    def start_keepalive(self):
        """Start the keep-alive thread to prevent ESP32 from sleeping."""
        if not self._keepalive_running:
            self._keepalive_running = True
            self._keepalive_thread = threading.Thread(target=self._keepalive_worker, daemon=True)
            self._keepalive_thread.start()

    def stop_keepalive(self):
        """Stop the keep-alive thread."""
        self._keepalive_running = False
        if self._keepalive_thread is not None:
            self._keepalive_thread.join(timeout=1.0)
            self._keepalive_thread = None

    def close(self):
        self.stop_keepalive()
        self.ser.close()
    def _wait_ready(self, duration):
        end_time = time.perf_counter() + duration
        while time.perf_counter() < end_time:
            pass

    def _enter_repl(self):
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x02")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()

    def _exec(self, code: str):
        self.ser.write(code.encode() + b"\r")
        self._wait_ready(REPL_DELAY)

    def _exec_raw_and_read(self, code: str, timeout: float = 5.0) -> str:
        """
        Enter raw REPL, send code, execute with Ctrl+D, collect output,
        exit raw REPL, and return the decoded output string.
        """
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()

        self.ser.write(code.encode())
        self._wait_ready(0.1)

        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
            if b">>>" in output:
                break
            time.sleep(0.05)

        self.ser.write(b"\x02")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()

        result = output.decode(errors="ignore")

        if "Traceback" in result:
            raise MicroPyError(result)

        return result

    def mkdir(self, path):
        code = (
            "import os\r\n"
            "try:\r\n"
            f"    os.mkdir('{path}')\r\n"
            "except:\r\n"
            "    pass\r\n"
            "try:\r\n"
            f"    os.stat('{path}')\r\n"
            "    print('EXISTS')\r\n"
            "except:\r\n"
            "    print('MISSING')\r\n"
        )
        result = self._exec_raw_and_read(code, timeout=3.0)
        return "EXISTS" in result

    def ensure_dirs(self, remote_path: str):
        """Create each directory in the path sequentially."""
        parts = remote_path.split("/")[:-1]
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            self.mkdir(cur)

    def list_esp32_files(self):
        code = (
            "import os\r\n"
            "def list_all(path, files, dirs):\r\n"
            "    try:\r\n"
            "        for f in os.listdir(path):\r\n"
            "            full = path + '/' + f if path != '/' else '/' + f\r\n"
            "            try:\r\n"
            "                st = os.stat(full)\r\n"
            "                if st[0] & 0x4000:\r\n"
            "                    dirs.add(full)\r\n"
            "                    list_all(full, files, dirs)\r\n"
            "                else:\r\n"
            "                    files.add(full)\r\n"
            "            except:\r\n"
            "                pass\r\n"
            "    except:\r\n"
            "        pass\r\n"
            "files = set()\r\n"
            "dirs = set()\r\n"
            "list_all('/', files, dirs)\r\n"
            "print('FILES:' + repr(sorted(files)))\r\n"
            "print('DIRS:' + repr(sorted(dirs)))\r\n"
        )

        result = self._exec_raw_and_read(code, timeout=8.0)

        files = set()
        dirs = set()

        try:
            files_marker = "FILES:"
            files_start = result.find(files_marker)
            if files_start != -1:
                files_start += len(files_marker)
                bracket_depth = 0
                files_end = files_start
                for i in range(files_start, len(result)):
                    if result[i] == '[':
                        bracket_depth += 1
                    elif result[i] == ']':
                        bracket_depth -= 1
                        if bracket_depth == 0:
                            files_end = i + 1
                            break
                files_str = result[files_start:files_end].strip()
                if files_str:
                    files = set(ast.literal_eval(files_str))

            dirs_marker = "DIRS:"
            dirs_start = result.find(dirs_marker)
            if dirs_start != -1:
                dirs_start += len(dirs_marker)
                bracket_depth = 0
                dirs_end = dirs_start
                for i in range(dirs_start, len(result)):
                    if result[i] == '[':
                        bracket_depth += 1
                    elif result[i] == ']':
                        bracket_depth -= 1
                        if bracket_depth == 0:
                            dirs_end = i + 1
                            break
                dirs_str = result[dirs_start:dirs_end].strip()
                if dirs_str:
                    dirs = set(ast.literal_eval(dirs_str))
        except Exception as e:
            print(f"Parse error in list_esp32_files: {e}\nRaw output: {result}")

        return files, dirs

    def get_file_sizes(self):
        code = (
            "import os\r\n"
            "result = {}\r\n"
            "def scan(path):\r\n"
            "    try:\r\n"
            "        for f in os.listdir(path):\r\n"
            "            full = path + '/' + f if path != '/' else '/' + f\r\n"
            "            try:\r\n"
            "                st = os.stat(full)\r\n"
            "                if st[0] & 0x4000:\r\n"
            "                    scan(full)\r\n"
            "                else:\r\n"
            "                    result[full] = st[6]\r\n"
            "            except:\r\n"
            "                pass\r\n"
            "    except:\r\n"
            "        pass\r\n"
            "scan('/')\r\n"
            "print('SIZES:' + repr(result))\r\n"
        )
        raw = self._exec_raw_and_read(code, timeout=8.0)

        sizes = {}
        try:
            marker = "SIZES:"
            start = raw.find(marker)
            if start != -1:
                start += len(marker)
                depth = 0
                end = start
                for i in range(start, len(raw)):
                    if raw[i] == '{':
                        depth += 1
                    elif raw[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                sizes = ast.literal_eval(raw[start:end].strip())
        except Exception as e:
            print(f"Parse error in get_file_sizes: {e}\nRaw: {raw}")

        return sizes

    def get(self, remote_path: str) -> str:
        """Download file content from ESP32 as string."""
        code = (
            "try:\r\n"
            f"    f = open('{remote_path}', 'r')\r\n"
            "    content = f.read()\r\n"
            "    f.close()\r\n"
            "    print('CONTENT_START')\r\n"
            "    print(content)\r\n"
            "    print('CONTENT_END')\r\n"
            "except Exception as e:\r\n"
            "    print('ERROR:' + str(e))\r\n"
        )
        
        result = self._exec_raw_and_read(code, timeout=10.0)
        
        if "ERROR:" in result:
            raise MicroPyError(f"Failed to read {remote_path}: {result}")
        
        start_marker = "CONTENT_START"
        end_marker = "CONTENT_END"
        
        start_idx = result.find(start_marker)
        end_idx = result.find(end_marker)
        
        if start_idx == -1 or end_idx == -1:
            raise MicroPyError(f"Failed to parse file content for {remote_path}")
        
        start_idx = result.find('\n', start_idx) + 1
        content = result[start_idx:end_idx].rstrip('\r\n')
        
        return content

    def list_modules(self):
        """Get all available modules (frozen + user)."""
        code = (
            "import sys\r\n"
            "try:\r\n"
            "    import pkgutil\r\n"
            "    modules = sorted([m[0] if isinstance(m, tuple) else m.name for m in pkgutil.iter_modules()])\r\n"
            "except:\r\n"
            "    modules = sorted(sys.modules.keys())\r\n"
            "print('MODULES:' + repr(modules))\r\n"
        )
        
        result = self._exec_raw_and_read(code, timeout=5.0)
        
        modules = []
        try:
            marker = "MODULES:"
            start = result.find(marker)
            if start != -1:
                start += len(marker)
                bracket_depth = 0
                end = start
                for i in range(start, len(result)):
                    if result[i] == '[':
                        bracket_depth += 1
                    elif result[i] == ']':
                        bracket_depth -= 1
                        if bracket_depth == 0:
                            end = i + 1
                            break
                modules = ast.literal_eval(result[start:end].strip())
        except Exception as e:
            print(f"Parse error in list_modules: {e}\nRaw: {result}")
        
        return modules

    def put_content(self, remote: str, content: str):
        """Upload string content directly to device."""
        data = content.encode('utf-8')
        CHUNK_SIZE = 128
        total_len = len(data)
        num_chunks = (total_len + CHUNK_SIZE - 1) // CHUNK_SIZE

        self.ser.write(b"\x03\x03")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()

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

        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 5:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
            if b">>>" in output or (b">" in output and b"OK" in output):
                break
            time.sleep(0.05)

        ok_pos = output.find(b"OK")
        traceback_pos = output.find(b"Traceback")

        if traceback_pos != -1 and (ok_pos == -1 or traceback_pos < ok_pos):
            self.ser.write(b"\x02")
            self._wait_ready(0.1)
            raise MicroPyError(output.decode(errors="ignore"))

        if b"OK" not in output:
            self.ser.write(b"\x02")
            self._wait_ready(0.1)
            raise MicroPyError(f"No OK confirmation: {output[:200]}")

        self.ser.write(b"\x02")
        self._wait_ready(0.1)

    def delete_file(self, path):
        code = (
            "import os\r\n"
            "try:\r\n"
            f"    os.remove('{path}')\r\n"
            "    print('DELETED')\r\n"
            "except Exception as e:\r\n"
            "    print('ERROR:' + str(e))\r\n"
        )
        result = self._exec_raw_and_read(code, timeout=3.0)
        return "DELETED" in result

    def remove_dir(self, path):
        code = (
            "import os\r\n"
            "def rmdir(directory):\r\n"
            "    try:\r\n"
            "        os.chdir(directory)\r\n"
            "        for f in os.listdir():\r\n"
            "            try:\r\n"
            "                os.remove(f)\r\n"
            "            except:\r\n"
            "                pass\r\n"
            "        for f in os.listdir():\r\n"
            "            rmdir(f)\r\n"
            "        os.chdir('..')\r\n"
            "        os.rmdir(directory)\r\n"
            "    except Exception as e:\r\n"
            "        print('ERR:' + str(e))\r\n"
            f"rmdir('{path}')\r\n"
            "print('DELETED')\r\n"
        )
        result = self._exec_raw_and_read(code, timeout=5.0)
        return "DELETED" in result

    def sync_folder_structure(self, files, log_func):
        """Sync folder structure by creating required folders in order."""
        required_folders = set()
        for path in files:
            rel = path.relative_to(ROOT)
            parts = list(rel.parts)
            for i in range(len(parts) - 1):
                folder_parts = parts[:i + 1]
                folder_path = "/".join(folder_parts)
                required_folders.add(folder_path)

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

        self.ser.write(b"\x03\x03")
        self._wait_ready(0.3)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.5)
        self.ser.reset_input_buffer()

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

        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 5:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
            if b">>>" in output or (b">" in output and b"OK" in output):
                break
            time.sleep(0.05)

        ok_pos = output.find(b"OK")
        traceback_pos = output.find(b"Traceback")

        if traceback_pos != -1 and (ok_pos == -1 or traceback_pos < ok_pos):
            self.ser.write(b"\x02")
            self._wait_ready(0.1)
            raise MicroPyError(output.decode(errors="ignore"))

        if b"OK" not in output:
            self.ser.write(b"\x02")
            self._wait_ready(0.1)
            raise MicroPyError(f"No OK confirmation: {output[:200]}")

        self.ser.write(b"\x02")
        self._wait_ready(0.1)

    def exit_raw_repl(self):
        """Safety call — ensure we're back in normal REPL"""
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.1)
        self.ser.write(b"\x02")
        self._wait_ready(0.1)

    def clean_all(self, log_func=None):
        """Delete all files and folders from ESP32 root directory."""
        if log_func:
            log_func("⚠️  Starting ESP32 cleanup...", "warning")

        code = (
            "import os\r\n"
            "def rmtree(path):\r\n"
            "    try:\r\n"
            "        for entry in os.ilistdir(path):\r\n"
            "            name = entry[0]\r\n"
            "            full_path = path + '/' + name if path else name\r\n"
            "            if entry[1] == 0x4000:\r\n"
            "                rmtree(full_path)\r\n"
            "                try:\r\n"
            "                    os.rmdir(full_path)\r\n"
            "                    print('DIR_DEL:' + full_path)\r\n"
            "                except Exception as e:\r\n"
            "                    print('DIR_ERR:' + full_path + ' ' + str(e))\r\n"
            "            else:\r\n"
            "                try:\r\n"
            "                    os.remove(full_path)\r\n"
            "                    print('FILE_DEL:' + full_path)\r\n"
            "                except Exception as e:\r\n"
            "                    print('FILE_ERR:' + full_path + ' ' + str(e))\r\n"
            "    except Exception as e:\r\n"
            "        print('ERR:' + str(e))\r\n"
            "print('CLEANUP_START')\r\n"
            "rmtree('')\r\n"
            "print('CLEANUP_DONE')\r\n"
        )

        result = self._exec_raw_and_read(code, timeout=30.0)

        if log_func:
            for line in result.split('\n'):
                line = line.strip()
                if line.startswith("FILE_DEL:"):
                    log_func(f"  🗑️  {line.replace('FILE_DEL:', '').strip()}", "info")
                elif line.startswith("DIR_DEL:"):
                    log_func(f"  📁  {line.replace('DIR_DEL:', '').strip()}", "info")
                elif line.startswith("FILE_ERR:") or line.startswith("DIR_ERR:"):
                    log_func(f"  ⚠️  {line}", "warning")

        if "CLEANUP_DONE" not in result:
            raise MicroPyError("Cleanup timeout - operation may be incomplete")

        if log_func:
            log_func("✅ ESP32 cleanup complete", "success")

        return True


# ============================================================
# ================= SIGNAL BRIDGE (Thread → UI) ==============
# ============================================================

class SignalBridge(QObject):
    log_signal = Signal(str, str)
    progress_signal = Signal(float)
    operation_done_signal = Signal()
    device_status_signal = Signal(bool)
    
    # File browser signals
    file_tree_loaded_signal = Signal(object, object, object)
    file_content_loaded_signal = Signal(str, str, str)
    file_upload_complete_signal = Signal(str, bool)


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

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        layout.addWidget(self.info_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(22)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.itemClicked.connect(self._on_item_clicked)
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

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.select_all_btn = QPushButton("☑  Select All")
        self.deselect_all_btn = QPushButton("☐  Deselect All")
        self.upload_btn = QPushButton("⬆  Upload")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.select_all_btn, self.deselect_all_btn, self.cancel_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(233, 84, 32, 0.5);
                    color: #ffffff;
                    border: 1px solid rgba(233, 84, 32, 0.8);
                    border-radius: 5px;
                    padding: 8px 18px;
                    font-size: 13px;
                }
                QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
                QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
            """)

        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 5px;
                padding: 8px 22px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }
        """)

        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.upload_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.upload_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self._update_upload_btn_text()

    def _populate_tree(self):
        self.tree.setUpdatesEnabled(False)
        folder_map = {}

        sorted_files = sorted(self.all_files, key=lambda p: (str(p.parent), p.name))

        for file_path in sorted_files:
            rel = file_path.relative_to(self.root_path)
            parts = list(rel.parts)

            parent_item = None

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
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, None)
                    folder_item.setForeground(0, QColor("#e95420"))

                    if parent_item is None:
                        self.tree.addTopLevelItem(folder_item)
                    else:
                        parent_item.addChild(folder_item)
                        parent_item.setExpanded(False)

                    folder_map[folder_key] = folder_item
                    folder_item.setExpanded(False)

                parent_item = folder_map[folder_key]

            file_item = QTreeWidgetItem()
            file_item.setText(0, parts[-1])

            size_bytes = file_path.stat().st_size
            file_item.setText(1, self._format_size(size_bytes))

            file_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )

            if str(file_path) in self.pre_selected:
                file_item.setCheckState(0, Qt.CheckState.Checked)
            else:
                file_item.setCheckState(0, Qt.CheckState.Unchecked)

            file_item.setData(0, Qt.ItemDataRole.UserRole, str(file_path))
            file_item.setForeground(0, QColor("#d0d0d0"))

            if parent_item is None:
                self.tree.addTopLevelItem(file_item)
            else:
                parent_item.addChild(file_item)

        self.tree.collapseAll()
        self.tree.setUpdatesEnabled(True)
        self._update_upload_btn_text()

    def _on_item_clicked(self, item, column):
        if item.childCount() > 0:
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

    def get_selected_files(self):
        selected = []
        self._collect_checked(self.tree.invisibleRootItem(), selected)
        return selected

    def _collect_checked(self, item, result):
        for i in range(item.childCount()):
            child = item.child(i)
            path_str = child.data(0, Qt.ItemDataRole.UserRole)
            if path_str is not None:
                if child.checkState(0) == Qt.CheckState.Checked:
                    result.append(Path(path_str))
            self._collect_checked(child, result)

    @staticmethod
    def _format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"


# ============================================================
# ================= ESP32 FILE SELECTION DIALOG ==============
# ============================================================

class ESP32FileSelectionDialog(QDialog):
    """Dialog for selecting files/folders from ESP32 to delete."""

    def __init__(self, esp32_files, esp32_dirs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Files/Folders to Delete")
        self.setMinimumSize(720, 560)
        self.esp32_files = esp32_files
        self.esp32_dirs = esp32_dirs

        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("color: #e74c3c; font-size: 13px; font-weight: 600;")
        layout.addWidget(self.info_label)

        warning_label = QLabel("⚠️ Selected items will be PERMANENTLY DELETED from ESP32")
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning_label.setStyleSheet("color: #f39c12; font-size: 12px; margin-bottom: 8px;")
        layout.addWidget(warning_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Type"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(22)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.itemClicked.connect(self._on_item_clicked)
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
                background-color: #5a3a3a;
                color: #ffffff;
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

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.select_all_btn = QPushButton("☑  Select All")
        self.deselect_all_btn = QPushButton("☐  Deselect All")
        self.delete_btn = QPushButton("🗑️  Delete Selected")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.select_all_btn, self.deselect_all_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(233, 84, 32, 0.5);
                    color: #ffffff;
                    border: 1px solid rgba(233, 84, 32, 0.8);
                    border-radius: 5px;
                    padding: 8px 18px;
                    font-size: 13px;
                }
                QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
                QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
            """)

        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 5px;
                padding: 8px 22px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }
        """)

        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 5px;
                padding: 8px 18px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
        """)

        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.delete_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self._update_delete_btn_text()

    def _populate_tree(self):
        """Build tree matching the upload dialog structure exactly."""
        self.tree.setUpdatesEnabled(False)
        folder_map = {}

        for file_path in sorted(self.esp32_files):
            parts = file_path.strip("/").split("/")
            parent_item = None

            for i in range(len(parts) - 1):
                folder_key = "/".join(parts[: i + 1])
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
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, ("/" + folder_key, "folder"))
                    folder_item.setForeground(0, QColor("#e95420"))

                    if parent_item is None:
                        self.tree.addTopLevelItem(folder_item)
                    else:
                        parent_item.addChild(folder_item)

                    folder_map[folder_key] = folder_item
                    folder_item.setExpanded(False)

                parent_item = folder_map[folder_key]

            file_item = QTreeWidgetItem()
            file_item.setText(0, parts[-1])
            file_item.setText(1, "")
            file_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            file_item.setCheckState(0, Qt.CheckState.Unchecked)
            file_item.setData(0, Qt.ItemDataRole.UserRole, (file_path, "file"))
            file_item.setForeground(0, QColor("#d0d0d0"))

            if parent_item is None:
                self.tree.addTopLevelItem(file_item)
            else:
                parent_item.addChild(file_item)

        self._sort_children(self.tree.invisibleRootItem())

        self.tree.collapseAll()
        self.tree.setUpdatesEnabled(True)
        self._update_delete_btn_text()

    def _sort_children(self, parent_item):
        """Recursively sort children: files on top, folders on bottom, alphabetical each."""
        child_count = parent_item.childCount()
        if child_count == 0:
            return

        children = []
        for i in range(child_count):
            children.append(parent_item.takeChild(0))

        files   = [c for c in children if c.childCount() == 0]
        folders = [c for c in children if c.childCount() > 0]

        files.sort(key=lambda c: c.text(0).lower())
        folders.sort(key=lambda c: c.text(0).lower())

        for item in files + folders:
            if isinstance(parent_item, QTreeWidget):
                parent_item.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

        for folder in folders:
            self._sort_children(folder)

    def _on_item_clicked(self, item, column):
        if item.childCount() > 0:
            if item.isExpanded():
                item.setExpanded(False)
            else:
                item.setExpanded(True)

    def _on_item_changed(self, item, column):
        if column == 0:
            self._update_delete_btn_text()

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
        self._update_delete_btn_text()

    def _set_recursive(self, item, state):
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_recursive(item.child(i), state)

    def _update_delete_btn_text(self):
        count = len(self.get_selected_items())
        if count > 0:
            self.delete_btn.setText(f"🗑️  Delete ({count})")
            self.delete_btn.setEnabled(True)
        else:
            self.delete_btn.setText("🗑️  Delete Selected")
            self.delete_btn.setEnabled(False)
        self.info_label.setText(f"{count} item(s) selected for deletion")

    def get_selected_items(self):
        """Return list of (path, type) tuples for every checked item."""
        selected = []
        self._collect_checked(self.tree.invisibleRootItem(), selected)
        return selected

    def _collect_checked(self, item, result):
        for i in range(item.childCount()):
            child = item.child(i)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            if data is not None:
                path_str, item_type = data
                if child.checkState(0) == Qt.CheckState.Checked:
                    result.append((path_str, item_type))
            self._collect_checked(child, result)


# ============================================================
# =================== END OF PART 1 ==========================
# ============================================================
# CONTINUE WITH PART 2 for:
# - ESP32FileBrowser class (complete)
# - CalSciApp class (modified)
# - main() function




















# ============================================================
# =================== PART 2 STARTS HERE =====================
# ============================================================
# PASTE THIS AFTER PART 1

# ============================================================
# ================= ESP32 FILE BROWSER =======================
# ============================================================

class ESP32FileBrowser(QMainWindow):
    """VSCode-style file browser for ESP32 with integrated editor."""
    
    def __init__(self, port, bridge, parent=None):
        super().__init__(parent)
        self.port = port
        self.bridge = bridge
        self.flasher = None
        
        self.open_files = {}
        
        self.setWindowTitle("ESP32 File Browser")
        self.setMinimumSize(1100, 700)
        
        self._build_ui()
        self._apply_stylesheet()
        
        self.bridge.file_tree_loaded_signal.connect(self._on_tree_loaded)
        self.bridge.file_content_loaded_signal.connect(self._on_file_content_loaded)
        self.bridge.file_upload_complete_signal.connect(self._on_upload_complete)
        
        self._scan_device()
    
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Compact header with device status
        header = QFrame()
        header.setFixedHeight(28)
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 2, 4, 2)

        self.device_label = QLabel(f"● Connected to {self.port}")
        self.device_label.setObjectName("deviceLabel")
        header_layout.addWidget(self.device_label)

        header_layout.addStretch()

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setObjectName("refreshBtn")
        self.refresh_btn.setFixedSize(20, 20)
        self.refresh_btn.clicked.connect(self._scan_device)
        header_layout.addWidget(self.refresh_btn)

        main_layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        tree_label = QLabel("EXPLORER")
        tree_label.setObjectName("sectionLabel")
        left_layout.addWidget(tree_label)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setObjectName("fileTree")
        self.file_tree.setAnimated(True)
        self.file_tree.setIndentation(16)
        self.file_tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        left_layout.addWidget(self.file_tree)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("editorTabs")
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        right_layout.addWidget(self.tab_widget)

        action_bar = QFrame()
        action_bar.setObjectName("actionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(12, 8, 12, 8)
        action_layout.setSpacing(8)

        self.status_label = QLabel("No file open")
        self.status_label.setObjectName("statusLabel")
        action_layout.addWidget(self.status_label)

        action_layout.addStretch()

        self.save_upload_btn = QPushButton("💾 Save & Upload")
        self.save_upload_btn.setObjectName("saveBtn")
        self.save_upload_btn.setEnabled(False)
        self.save_upload_btn.clicked.connect(self._save_and_upload)
        action_layout.addWidget(self.save_upload_btn)

        self.revert_btn = QPushButton("↶ Revert")
        self.revert_btn.setObjectName("revertBtn")
        self.revert_btn.setEnabled(False)
        self.revert_btn.clicked.connect(self._revert_current)
        action_layout.addWidget(self.revert_btn)

        right_layout.addWidget(action_bar)

        splitter.addWidget(right_panel)
        splitter.setSizes([250, 850])

        main_layout.addWidget(splitter)

        self.statusBar().showMessage("Ready")
    
    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }

            QFrame#header {
                background-color: #2d2d2d;
                border-bottom: 1px solid #3a3a3a;
            }

            QLabel#deviceLabel {
                color: #77b255;
                font-size: 12px;
                font-weight: 600;
            }

            QLabel#sectionLabel {
                background-color: #252525;
                color: #888;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }

            QTreeWidget#fileTree {
                background-color: #252525;
                color: #cccccc;
                border: none;
                font-size: 13px;
                outline: none;
            }
            QTreeWidget#fileTree::item {
                padding: 4px 0px;
            }
            QTreeWidget#fileTree::item:hover {
                background-color: #2a2a2a;
            }
            QTreeWidget#fileTree::item:selected {
                background-color: #37373d;
                color: #ffffff;
            }

            QPushButton#refreshBtn {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 2px;
            }
            QPushButton#refreshBtn:hover {
                background-color: rgba(233, 84, 32, 0.7);
            }
            QPushButton#refreshBtn:pressed {
                background-color: rgba(233, 84, 32, 0.9);
            }

            QTabWidget#editorTabs::pane {
                border: none;
                background-color: #1e1e1e;
            }
            QTabWidget#editorTabs QTabBar::tab {
                background-color: #2d2d2d;
                color: #969696;
                padding: 8px 16px;
                border: none;
                border-right: 1px solid #1e1e1e;
                font-size: 12px;
            }
            QTabWidget#editorTabs QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QTabWidget#editorTabs QTabBar::tab:hover {
                background-color: #323232;
            }

            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                selection-background-color: #264f78;
            }

            QFrame#actionBar {
                background-color: #2d2d2d;
                border-top: 1px solid #3a3a3a;
            }

            QLabel#statusLabel {
                color: #888;
                font-size: 11px;
            }

            QPushButton#saveBtn {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#saveBtn:hover {
                background-color: rgba(233, 84, 32, 0.7);
            }
            QPushButton#saveBtn:disabled {
                background-color: rgba(85, 85, 85, 0.3);
                color: #555;
                border-color: rgba(85, 85, 85, 0.5);
            }

            QPushButton#revertBtn {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton#revertBtn:hover {
                background-color: rgba(233, 84, 32, 0.7);
            }
            QPushButton#revertBtn:disabled {
                background-color: rgba(85, 85, 85, 0.3);
                color: #555;
                border-color: rgba(85, 85, 85, 0.5);
            }

            QStatusBar {
                background-color: #007acc;
                color: #ffffff;
                font-size: 11px;
                padding: 2px 8px;
            }
        """)
    
    def _scan_device(self):
        self.statusBar().showMessage("Scanning device...")
        self.refresh_btn.setEnabled(False)
        
        def run():
            try:
                flasher = MicroPyFlasher(self.port)
                files, dirs = flasher.list_esp32_files()
                modules = flasher.list_modules()
                flasher.close()
                
                self.bridge.file_tree_loaded_signal.emit(files, dirs, modules)
            except Exception as e:
                self.statusBar().showMessage(f"Error scanning: {str(e)[:50]}")
                self.refresh_btn.setEnabled(True)
        
        threading.Thread(target=run, daemon=True).start()
    
    def _on_tree_loaded(self, files, dirs, modules):
        self.file_tree.clear()

        user_files_root = QTreeWidgetItem(self.file_tree)
        user_files_root.setText(0, "📁 User Files")
        user_files_root.setForeground(0, QColor("#e95420"))
        user_files_root.setData(0, Qt.ItemDataRole.UserRole, None)
        user_files_root.setExpanded(True)

        folder_map = {}

        # First pass: create all folder structure
        for file_path in sorted(files):
            parts = file_path.strip("/").split("/")
            parent_item = user_files_root

            for i in range(len(parts) - 1):
                folder_key = "/".join(parts[: i + 1])
                if folder_key not in folder_map:
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, parts[i])
                    folder_item.setForeground(0, QColor("#e95420"))
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, None)
                    parent_item.addChild(folder_item)
                    folder_map[folder_key] = folder_item

                parent_item = folder_map[folder_key]

        # Second pass: add files and folders in correct order (files first, then folders)
        def add_items_sorted(parent_path, parent_item):
            # Normalize parent_path (remove trailing slash for comparison)
            normalized_parent = parent_path.rstrip("/") + "/"
            # Collect files and folders at this level
            level_files = []
            level_folders = []

            for file_path in files:
                if file_path.startswith(normalized_parent) and file_path != normalized_parent.rstrip("/"):
                    remaining = file_path[len(normalized_parent):]
                    if "/" not in remaining:  # Direct child file
                        level_files.append((remaining, file_path))

            for folder_key in folder_map:
                # Normalize folder_key for comparison
                normalized_folder = "/" + folder_key if not folder_key.startswith("/") else folder_key
                if normalized_folder.startswith(normalized_parent) and normalized_folder != normalized_parent.rstrip("/"):
                    remaining = normalized_folder[len(normalized_parent):]
                    if "/" not in remaining:  # Direct child folder
                        level_folders.append((remaining, folder_key))

            # Add files first (sorted alphabetically)
            for filename, filepath in sorted(level_files):
                file_item = QTreeWidgetItem()
                file_item.setText(0, filename)
                file_item.setForeground(0, QColor("#d0d0d0"))
                file_item.setData(0, Qt.ItemDataRole.UserRole, filepath)
                file_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                parent_item.addChild(file_item)

            # Add folders after files (sorted alphabetically)
            for foldername, folderpath in sorted(level_folders):
                folder_item = folder_map[folderpath]
                parent_item.addChild(folder_item)
                # Recursively add items to this folder
                add_items_sorted("/" + folderpath + "/", folder_item)

        # Start with root level
        add_items_sorted("/", user_files_root)

        modules_root = QTreeWidgetItem(self.file_tree)
        modules_root.setText(0, "📦 Built-in Modules")
        modules_root.setForeground(0, QColor("#888"))
        modules_root.setData(0, Qt.ItemDataRole.UserRole, None)
        modules_root.setExpanded(False)

        for module in sorted(modules):
            module_item = QTreeWidgetItem()
            module_item.setText(0, module)
            module_item.setForeground(0, QColor("#666"))
            module_item.setData(0, Qt.ItemDataRole.UserRole, f"builtin:{module}")
            modules_root.addChild(module_item)

        self.statusBar().showMessage(f"Found {len(files)} files, {len(modules)} modules")
        self.refresh_btn.setEnabled(True)
    
    def _on_tree_double_click(self, item, column):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        
        if not path:
            item.setExpanded(not item.isExpanded())
            return
        
        if path.startswith("builtin:"):
            module_name = path.replace("builtin:", "")
            QMessageBox.information(
                self,
                "Built-in Module",
                f"'{module_name}' is a built-in firmware module.\n\n"
                f"These modules are compiled into the firmware and cannot be edited."
            )
            return
        
        self._open_file(path)
    
    def _open_file(self, path):
        if path in self.open_files:
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) == self.open_files[path]["widget"]:
                    self.tab_widget.setCurrentIndex(i)
                    return
        
        self.statusBar().showMessage(f"Loading {path}...")
        
        def run():
            try:
                flasher = MicroPyFlasher(self.port)
                content = flasher.get(path)
                content_hash = hashlib.md5(content.encode()).hexdigest()
                flasher.close()
                
                self.bridge.file_content_loaded_signal.emit(path, content, content_hash)
            except Exception as e:
                self.statusBar().showMessage(f"Error loading {path}: {str(e)[:50]}")
        
        threading.Thread(target=run, daemon=True).start()
    
    def _on_file_content_loaded(self, path, content, content_hash):
        editor = QPlainTextEdit()
        editor.setPlainText(content)
        editor.textChanged.connect(lambda: self._on_editor_changed(path))
        editor.cursorPositionChanged.connect(self._update_cursor_position)
        
        filename = path.split("/")[-1]
        tab_index = self.tab_widget.addTab(editor, filename)
        self.tab_widget.setCurrentIndex(tab_index)
        
        self.open_files[path] = {
            "content": content,
            "hash": content_hash,
            "modified": False,
            "widget": editor
        }
        
        self._update_status(path)
        self.statusBar().showMessage(f"Loaded {path}")
    
    def _on_editor_changed(self, path):
        if path not in self.open_files:
            return
        
        editor = self.open_files[path]["widget"]
        current_content = editor.toPlainText()
        current_hash = hashlib.md5(current_content.encode()).hexdigest()
        original_hash = self.open_files[path]["hash"]
        
        is_modified = current_hash != original_hash
        
        if is_modified != self.open_files[path]["modified"]:
            self.open_files[path]["modified"] = is_modified
            self._update_tab_title(path)
            self._update_buttons()
    
    def _update_tab_title(self, path):
        filename = path.split("/")[-1]
        editor = self.open_files[path]["widget"]
        
        for i in range(self.tab_widget.count()):
            if self.tab_widget.widget(i) == editor:
                if self.open_files[path]["modified"]:
                    self.tab_widget.setTabText(i, "● " + filename)
                else:
                    self.tab_widget.setTabText(i, filename)
                break
    
    def _update_buttons(self):
        current_path = self._get_current_path()
        
        if current_path and current_path in self.open_files:
            is_modified = self.open_files[current_path]["modified"]
            self.save_upload_btn.setEnabled(is_modified)
            self.revert_btn.setEnabled(is_modified)
        else:
            self.save_upload_btn.setEnabled(False)
            self.revert_btn.setEnabled(False)
    
    def _update_status(self, path=None):
        if not path:
            path = self._get_current_path()
        
        if path and path in self.open_files:
            editor = self.open_files[path]["widget"]
            cursor = editor.textCursor()
            line = cursor.blockNumber() + 1
            col = cursor.columnNumber() + 1
            
            size = len(editor.toPlainText().encode('utf-8'))
            size_str = f"{size} bytes" if size < 1024 else f"{size/1024:.1f} KB"
            
            self.status_label.setText(f"{path}  •  {size_str}  •  Ln {line}, Col {col}  •  UTF-8")
        else:
            self.status_label.setText("No file open")
    
    def _update_cursor_position(self):
        self._update_status()
    
    def _get_current_path(self):
        current_widget = self.tab_widget.currentWidget()
        if not current_widget:
            return None
        
        for path, data in self.open_files.items():
            if data["widget"] == current_widget:
                return path
        
        return None
    
    def _on_tab_changed(self, index):
        self._update_status()
        self._update_buttons()
    
    def _close_tab(self, index):
        widget = self.tab_widget.widget(index)
        
        path = None
        for p, data in self.open_files.items():
            if data["widget"] == widget:
                path = p
                break
        
        if not path:
            self.tab_widget.removeTab(index)
            return
        
        if self.open_files[path]["modified"]:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"'{path.split('/')[-1]}' has unsaved changes.\n\nClose anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        self.tab_widget.removeTab(index)
        del self.open_files[path]
        
        if self.tab_widget.count() == 0:
            self._update_status()
            self._update_buttons()
    
    def _save_and_upload(self):
        path = self._get_current_path()
        if not path or path not in self.open_files:
            return
        
        editor = self.open_files[path]["widget"]
        content = editor.toPlainText()
        
        self.statusBar().showMessage(f"Uploading {path}...")
        self.save_upload_btn.setEnabled(False)
        
        def run():
            try:
                flasher = MicroPyFlasher(self.port)
                flasher.ensure_dirs(path.lstrip("/"))
                flasher.put_content(path.lstrip("/"), content)
                flasher.close()
                
                self.bridge.file_upload_complete_signal.emit(path, True)
            except Exception as e:
                self.statusBar().showMessage(f"Upload failed: {str(e)[:50]}")
                self.save_upload_btn.setEnabled(True)
        
        threading.Thread(target=run, daemon=True).start()
    
    def _on_upload_complete(self, path, success):
        if success:
            editor = self.open_files[path]["widget"]
            content = editor.toPlainText()
            new_hash = hashlib.md5(content.encode()).hexdigest()
            
            self.open_files[path]["hash"] = new_hash
            self.open_files[path]["modified"] = False
            
            self._update_tab_title(path)
            self._update_buttons()
            
            self.statusBar().showMessage(f"✓ Uploaded {path}")
        else:
            self.statusBar().showMessage(f"✗ Upload failed")
            self.save_upload_btn.setEnabled(True)
    
    def _revert_current(self):
        path = self._get_current_path()
        if not path or path not in self.open_files:
            return
        
        reply = QMessageBox.question(
            self,
            "Revert Changes",
            f"Revert '{path.split('/')[-1]}' to last saved version?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        original_content = self.open_files[path]["content"]
        editor = self.open_files[path]["widget"]
        
        editor.blockSignals(True)
        editor.setPlainText(original_content)
        editor.blockSignals(False)
        
        self.open_files[path]["modified"] = False
        self._update_tab_title(path)
        self._update_buttons()
        
        self.statusBar().showMessage(f"Reverted {path}")
    


    def _show_tree_context_menu(self, position):
        item = self.file_tree.itemAt(position)
        if not item:
            return

        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path or path.startswith("builtin:"):
            return

        menu = QMenu(self)

        open_action = menu.addAction("Open")
        delete_action = menu.addAction("Delete from ESP32")

        action = menu.exec(self.file_tree.mapToGlobal(position))

        if action == open_action:
            self._open_file(path)
        elif action == delete_action:
            self._delete_file_from_tree(path)
    
    def _delete_file_from_tree(self, path):
        reply = QMessageBox.question(
            self,
            "Delete File",
            f"Permanently delete '{path}' from ESP32?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self.statusBar().showMessage(f"Deleting {path}...")
        
        def run():
            try:
                flasher = MicroPyFlasher(self.port)
                success = flasher.delete_file(path)
                flasher.close()
                
                if success:
                    if path in self.open_files:
                        editor = self.open_files[path]["widget"]
                        for i in range(self.tab_widget.count()):
                            if self.tab_widget.widget(i) == editor:
                                self.tab_widget.removeTab(i)
                                break
                        del self.open_files[path]
                    
                    self.statusBar().showMessage(f"✓ Deleted {path}")
                    self._scan_device()
                else:
                    self.statusBar().showMessage(f"✗ Delete failed")
            except Exception as e:
                self.statusBar().showMessage(f"Error: {str(e)[:50]}")
        
        threading.Thread(target=run, daemon=True).start()
    
    def closeEvent(self, event):
        unsaved = [path for path, data in self.open_files.items() if data["modified"]]
        
        if unsaved:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"{len(unsaved)} file(s) have unsaved changes.\n\nClose anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        
        event.accept()


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
        self.file_browser = None
        self._flasher = None  # Keep-alive flasher instance
        self._device_connected = False
        
        self._build_ui()
        self._apply_stylesheet()

        self.device_timer = QTimer()
        self.device_timer.timeout.connect(self._check_device_status)
        self.device_timer.start(2000)
        self._check_device_status()

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

        subtitle_label = QLabel("ESP32 MicroPython Uploader")
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

        self.update_btn = QPushButton("⬇  Download Updates")
        self.update_btn.setObjectName("btnSecondary")
        self.update_btn.clicked.connect(self._handle_update)
        left_layout.addWidget(self.update_btn)

        self.flash_btn = QPushButton("⚡  Flash All Files")
        self.flash_btn.setObjectName("btnPrimary")
        self.flash_btn.clicked.connect(self._handle_flash)
        left_layout.addWidget(self.flash_btn)

        self.delta_btn = QPushButton("🔄  Sync (Delta)")
        self.delta_btn.setObjectName("btnSecondary")
        self.delta_btn.clicked.connect(self._handle_delta_sync)
        left_layout.addWidget(self.delta_btn)

        self.upload_btn = QPushButton("📂  Upload Selected…")
        self.upload_btn.setObjectName("btnSecondary")
        self.upload_btn.clicked.connect(self._handle_upload_selected)
        left_layout.addWidget(self.upload_btn)

        self.browse_btn = QPushButton("📂  Browse ESP32 Files…")
        self.browse_btn.setObjectName("btnSecondary")
        self.browse_btn.clicked.connect(self._open_file_browser)
        left_layout.addWidget(self.browse_btn)

        self.clear_btn = QPushButton("🗑️  Clear All Files")
        self.clear_btn.setObjectName("btnDanger")
        self.clear_btn.clicked.connect(self._handle_clear_all)
        left_layout.addWidget(self.clear_btn)

        self.auto_retry_cb = QCheckBox("Auto-retry on failure)")
        self.auto_retry_cb.setChecked(True)
        self.auto_retry_cb.setObjectName("retryCheckbox")
        left_layout.addWidget(self.auto_retry_cb)

        self.prevent_sleep_cb = QCheckBox("Prevent sleep (keep device awake)")
        self.prevent_sleep_cb.setChecked(True)
        self.prevent_sleep_cb.setObjectName("preventSleepCheckbox")
        self.prevent_sleep_cb.stateChanged.connect(self._on_prevent_sleep_changed)
        left_layout.addWidget(self.prevent_sleep_cb)

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

            # Handle keep-alive based on connection state
            if is_connected and not was_connected:
                # Device just connected - start keep-alive if enabled
                if hasattr(self, 'prevent_sleep_cb') and self.prevent_sleep_cb.isChecked():
                    self._start_keepalive(ports[0])
            elif not is_connected and was_connected:
                # Device just disconnected - stop keep-alive
                self._stop_keepalive()

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

    def _start_keepalive(self, port):
        """Start keep-alive thread to prevent ESP32 from sleeping."""
        try:
            self._stop_keepalive()  # Clean up any existing instance
            self._flasher = MicroPyFlasher(port)
            self._flasher.start_keepalive()
            self._log(f"Keep-alive started (device awake)", "info")
        except Exception as e:
            self._log(f"Could not start keep-alive: {e}", "warning")

    def _stop_keepalive(self):
        """Stop keep-alive thread and close flasher."""
        if self._flasher is not None:
            try:
                self._flasher.close()
            except Exception:
                pass
            self._flasher = None

    def _on_prevent_sleep_changed(self, state):
        """Handle checkbox state change to enable/disable keep-alive."""
        if self._device_connected:
            if state == Qt.CheckState.Checked.value:
                ports = find_esp32_ports()
                if ports:
                    self._start_keepalive(ports[0])
            else:
                self._stop_keepalive()
                self._log("Keep-alive disabled", "info")

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
        self.delta_btn.setEnabled(True)
        self.upload_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self._check_device_status()

    def _lock_buttons(self):
        self.operation_in_progress = True
        self.update_btn.setEnabled(False)
        self.flash_btn.setEnabled(False)
        self.delta_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.progress_bar.setValue(0)

    def _log(self, message, msg_type="info"):
        self.bridge.log_signal.emit(message, msg_type)

    def _open_file_browser(self):
        ports = find_esp32_ports()
        if not ports:
            QMessageBox.warning(
                self,
                "No Device",
                "No ESP32 device detected.\n\nPlease connect your ESP32 and try again."
            )
            return
        
        port = ports[0]
        
        if self.file_browser is None or not self.file_browser.isVisible():
            self.file_browser = ESP32FileBrowser(port, self.bridge, parent=self)
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
                self._log(f"ESP32 found: {port}", "success")
                self.bridge.progress_signal.emit(0.05)

                flasher = MicroPyFlasher(port)

                self._log("Scanning ESP32 file system…", "info")
                esp32_sizes = flasher.get_file_sizes()
                self._log(f"ESP32 has {len(esp32_sizes)} file(s)", "info")
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
                            self._log(f"  [{i}/{len(to_delete)}] 🗑️  {remote}", "info")
                        else:
                            self._log(f"  [{i}/{len(to_delete)}] ⚠️  failed: {remote}", "warning")
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
                            flasher, port, local_path, remote_rel, auto_retry
                        )

                        if success:
                            uploaded_size += max(local_path.stat().st_size, 1)
                            progress = 0.35 + (uploaded_size / total_size) * 0.65
                            self.bridge.progress_signal.emit(progress)
                            self._log(f"  [{i}/{len(to_upload)}] ⬆  {remote}  ({local_path.stat().st_size} bytes)", "info")
                        else:
                            failed.append(remote)
                            self._log(f"  [{i}/{len(to_upload)}] ⚠️  failed: {remote}", "warning")

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
                    raise RuntimeError("No ESP32 device detected")

                port = ports[0]
                self._log(f"ESP32 found: {port}", "success")
                self.bridge.progress_signal.emit(0.05)
                flasher = MicroPyFlasher(port)
                self._log("Clearing all files from ESP32...", "warning")
                flasher.clean_all(self._log)
                self._log("All files cleared", "success")
                
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
                        flasher, port, path, remote_path, auto_retry
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

    def _handle_upload_selected(self):
        if not ROOT.exists():
            self._log("Repository not found. Click 'Download Updates' first.", "error")
            return

        files = get_all_files(ROOT)
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

                flasher.sync_folder_structure(selected_files, self._log)
                self.bridge.progress_signal.emit(0.1)

                total_size = max(sum(p.stat().st_size for p in selected_files), 1)
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
                        uploaded += max(path.stat().st_size, 1)
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

    def _handle_clear_all(self):
        confirm = QMessageBox.question(
            self,
            "Confirm Clear All",
            "Are you sure you want to DELETE ALL FILES from the ESP32?",
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
                    raise RuntimeError("No ESP32 device detected")

                port = ports[0]
                self._log(f"ESP32 found: {port}", "success")

                flasher = MicroPyFlasher(port)
                self._log("Clearing all files from ESP32...", "warning")
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

    def _handle_delete_selected(self):
        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No ESP32 device detected")

                port = ports[0]
                self._log(f"ESP32 found: {port}", "success")

                flasher = MicroPyFlasher(port)

                self._log("Reading ESP32 file system...", "info")
                esp_files, esp_dirs = flasher.list_esp32_files()
                flasher.close()

                if not esp_files and not esp_dirs:
                    self._log("ESP32 is empty — nothing to delete", "info")
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
                        self._log(f"  🗑️  Deleted: {path}", "info")
                        deleted += 1
                    else:
                        self._log(f"  ⚠️  Failed: {path}", "warning")
                        failed += 1
                    self.bridge.progress_signal.emit(deleted / max(total, 1))

                dirs_to_delete.sort(key=lambda x: x[0].count("/"), reverse=True)
                for path, _ in dirs_to_delete:
                    if flasher.remove_dir(path):
                        self._log(f"  📁  Deleted folder: {path}", "info")
                        deleted += 1
                    else:
                        self._log(f"  ⚠️  Failed folder: {path}", "warning")
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

    def _upload_single_file(self, flasher, port, path, remote_path, auto_retry):
        for attempt in range(2):
            try:
                flasher.ensure_dirs(remote_path)
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
    app.setStyle("Fusion")
    window = CalSciApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
