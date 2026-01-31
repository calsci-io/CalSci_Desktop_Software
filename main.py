import sys
import time
import threading
import subprocess
from pathlib import Path

import git
from serial.tools import list_ports
import serial

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


# ================= CONFIG =================

REPO_URL = "https://github.com/calsci-io/calsci_latest_itr"
BRANCH = "main"
ROOT = Path("./calsci_latest_itr")
CALIBRATION_FILES = 3

ESP32_KEYWORDS = ("Espressif",)

BAUDRATE = 115200
REPL_DELAY = 0.05

# =========================================


# ---------- LOGGING ----------

def log_append(widget: ScrolledText, text: str):
    widget.insert(tk.END, text + "\n")
    widget.see(tk.END)
    widget.update_idletasks()


def debug_ports(log):
    for p in list_ports.comports():
        log(
            f"{p.device} | "
            f"name={p.name} | "
            f"desc={p.description} | "
            f"mfg={p.manufacturer} | "
            f"hwid={p.hwid}"
        )


# ---------- ESP32 PORT DETECTION ----------
def find_esp32_ports():
    ports = []

    KEYWORDS = (
        "esp32",
        "espressif",
        "cp210",     # Silicon Labs
        "ch340",     # WCH
        "ch341",
        "ftdi",
        "usb serial",
        "uart",
    )

    for p in list_ports.comports():
        fields = [
            p.device or "",
            p.name or "",
            p.description or "",
            p.manufacturer or "",
            p.hwid or "",
        ]

        text = " ".join(fields).lower()

        if any(k in text for k in KEYWORDS):
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


# ---------- FILE FILTER ----------

def should_skip(path: Path) -> bool:
    if any(part.startswith(".") for part in path.parts):
        return True
    if path.name in {".gitignore", ".gitattributes"}:
        return True
    if path.suffix == ".pyc":
        return True
    return False


# ============================================================
# ================= MICRO-PY FLASHER =========================
# ============================================================

class MicroPyError(Exception):
    pass


class MicroPyFlasher:
    def __init__(self, port, baudrate=BAUDRATE):
        self.port = port
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(1)
        self._enter_repl()

    def close(self):
        self.ser.close()

    # def _enter_repl(self):
    #     self.ser.write(b"\r\x03\x03")
    #     time.sleep(REPL_DELAY)
    def _enter_repl(self):
        # Interrupt any running program
        self.ser.write(b"\x03\x03")
        time.sleep(0.2)

        # Enter RAW REPL ONLY
        self.ser.write(b"\x01")  # Ctrl+A
        time.sleep(0.2)

        self.ser.reset_input_buffer()

    def _exec(self, code: str):
        self.ser.write(code.encode() + b"\r")
        time.sleep(REPL_DELAY)

    def _exec_capture(self, code: str) -> str:
        self._exec("import sys")
        self._exec("sys.stdout.write('<<<')")

        for line in code.strip().splitlines():
            self._exec(line)

        self._exec("sys.stdout.write('>>>')")

        out = b""
        start = time.time()
        while time.time() - start < 2:
            if self.ser.in_waiting:
                out += self.ser.read(self.ser.in_waiting)
            if b">>>" in out:
                break

        data = out.decode(errors="ignore")
        if "Traceback" in data:
            raise MicroPyError(data)

        return data.split("<<<")[-1].split(">>>")[0]


    # ---------- FS OPS ----------

    def mkdir(self, path):
        self._exec_capture(f"""
import os
try:
    os.mkdir("{path}")
except OSError:
    pass
""")

    def put(self, local: Path, remote: str):
        data = local.read_bytes()
        self._exec_capture(f"""
f = open("{remote}", "wb")
""")
        for i in range(0, len(data), 512):
            chunk = data[i:i+512]
            self.ser.write(
                b"f.write(" + repr(chunk).encode() + b")\r"
            )
            time.sleep(REPL_DELAY)
        self._exec_capture("f.close()")

    def ensure_dirs(self, remote_path: str):
        parts = remote_path.split("/")[:-1]
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            self.mkdir(cur)

    def exit_raw_repl(self):
        # Leave RAW REPL, return to normal REPL
        self.ser.write(b"\x02")  # Ctrl+B
        time.sleep(0.1)



# ============================================================
# ======================= GUI APP ============================
# ============================================================

class CalSciApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("CalSci Tool")
        self.geometry("600x400")

        self.update_btn = ttk.Button(self, text="Download Updates", command=self.start_update)
        self.flash_btn = ttk.Button(self, text="Flash to CalSci", command=self.start_flash)

        self.log_box = ScrolledText(self, state="normal")
        self.log_box.configure(font=("Courier", 10))

        self.update_btn.pack(fill="x", padx=10, pady=5)
        self.flash_btn.pack(fill="x", padx=10, pady=5)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=5)

    # ---------- THREAD WRAPPERS ----------

    def start_update(self):
        threading.Thread(target=self.handle_update, daemon=True).start()

    def start_flash(self):
        threading.Thread(target=self.handle_flash, daemon=True).start()

    # ---------- BUTTON ACTIONS ----------

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

            flasher = MicroPyFlasher(port)

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
                flasher.ensure_dirs(remote_path)
                flasher.put(path, remote_path)
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
            flasher.exit_raw_repl()
            flasher.close()
            # flasher.close()
            log("🎉 Flashing complete!")

        except Exception as e:
            log(f"❌ Error: {e}")


# ---------- ENTRY POINT ----------

def main():
    app = CalSciApp()
    app.mainloop()


if __name__ == "__main__":
    main()
