import sys
import time
import subprocess
from pathlib import Path

import git
from serial.tools import list_ports

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QTextEdit,
)
from PySide6.QtCore import Qt


# ================= CONFIG =================

REPO_URL = "https://github.com/calsci-io/calsci_latest_itr"
BRANCH = "main"
ROOT = Path("./calsci_latest_itr_python")
CALIBRATION_FILES = 3

ESP32_KEYWORDS = ("Espressif",)

# =========================================


def log_append(widget: QTextEdit, text: str):
    widget.append(text)
    widget.verticalScrollBar().setValue(
        widget.verticalScrollBar().maximum()
    )
    QApplication.processEvents()



# ---------- ESP32 PORT DETECTION ----------

def find_esp32_ports():
    ports = []
    for p in list_ports.comports():
        text = f"{p.manufacturer} {p.description}".lower()
        if any(k.lower() in text for k in ESP32_KEYWORDS):
            ports.append(p.device)
    return ports


# ---------- GIT HELPERS ----------

def ensure_repo(log):
    if not ROOT.exists():
        log(f"Cloning repo into {ROOT} ...")
        git.Repo.clone_from(REPO_URL, ROOT, branch=BRANCH)
        log("Clone complete.")
    else:
        log("Repo already exists.")


def repo_status(log):
    repo = git.Repo(ROOT)
    repo.remotes.origin.fetch()

    behind = sum(1 for _ in repo.iter_commits(f"{BRANCH}..origin/{BRANCH}"))
    ahead = sum(1 for _ in repo.iter_commits(f"origin/{BRANCH}..{BRANCH}"))

    return ahead, behind


def pull_repo(log):
    repo = git.Repo(ROOT)
    repo.remotes.origin.pull()
    log("Repo updated successfully.")


# ---------- AMPY HELPERS ----------

def should_skip(path: Path) -> bool:
    if any(part.startswith(".") for part in path.parts):
        return True
    if path.name in {".gitignore", ".gitattributes"}:
        return True
    if path.suffix == ".pyc":
        return True
    return False


def ampy_mkdir(port, path: str):
    subprocess.run(
        ["ampy", "-p", port, "mkdir", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ensure_dirs(port, remote_path: str):
    parts = remote_path.split("/")[:-1]
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        ampy_mkdir(port, current)


def upload_file(port, local_path: Path, remote_path: str):
    subprocess.run(
        ["ampy", "-p", port, "put", str(local_path), remote_path],
        check=True,
    )


# ---------- GUI APP ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("CalSci Tool")
        self.resize(600, 400)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        self.update_btn = QPushButton("Download Updates")
        self.flash_btn = QPushButton("Flash to CalSci")

        self.update_btn.clicked.connect(self.handle_update)
        self.flash_btn.clicked.connect(self.handle_flash)

        layout = QVBoxLayout()
        layout.addWidget(self.update_btn)
        layout.addWidget(self.flash_btn)
        layout.addWidget(self.log_box)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    # -------- BUTTON ACTIONS --------

    def handle_update(self):
        def log(msg): log_append(self.log_box, msg)

        try:
            ensure_repo(log)
            ahead, behind = repo_status(log)

            if behind > 0:
                log(f"Update available ({behind} commits). Pulling...")
                pull_repo(log)
            elif ahead > 0:
                log(f"Local repo ahead by {ahead} commits.")
            else:
                log("Repo already in sync.")

        except Exception as e:
            log(f"❌ Error: {e}")

    def handle_flash(self):
        def log(msg): log_append(self.log_box, msg)

        try:
            ports = find_esp32_ports()
            if not ports:
                raise RuntimeError("No ESP32 detected")

            port = ports[0]
            log(f"Detected ESP32 on {port}")

            files = [
                p for p in ROOT.rglob("*")
                if p.is_file() and not should_skip(p)
            ]

            total_files = len(files)
            total_chars = sum(p.stat().st_size for p in files)

            log(f"Uploading {total_files} files...")

            uploaded_chars = 0
            timings = []
            speed = None

            for i, path in enumerate(files, start=1):
                remote_path = path.relative_to(ROOT).as_posix()
                size = path.stat().st_size

                start = time.perf_counter()
                ensure_dirs(port, remote_path)
                upload_file(port, path, remote_path)
                elapsed = time.perf_counter() - start

                uploaded_chars += size

                if i <= CALIBRATION_FILES:
                    timings.append((size, elapsed))
                    if i == CALIBRATION_FILES:
                        speed = sum(c for c, _ in timings) / sum(t for _, t in timings)

                remaining = total_chars - uploaded_chars
                eta = (
                    time.strftime("%H:%M:%S", time.gmtime(remaining / speed))
                    if speed else "calibrating..."
                )

                percent = (uploaded_chars / total_chars) * 100

                log(f"[{i}/{total_files}] {percent:5.1f}% | ETA {eta} → {remote_path}")

            log("🎉 Flashing complete!")

        except Exception as e:
            log(f"❌ Error: {e}")


# ---------- ENTRY POINT ----------

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
