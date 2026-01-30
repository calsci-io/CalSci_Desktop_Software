from pathlib import Path
import subprocess
import time
from serial.tools import list_ports



ESP32_KEYWORDS = (
    # "CP210",
    # "CH340",
    # "CH910",
    # "USB JTAG",
    # "Silicon Labs",
    "Espressif",
)

def find_esp32_ports():
    ports = []
    for p in list_ports.comports():
        text = f"{p.manufacturer} {p.description}".lower()
        if any(k.lower() in text for k in ESP32_KEYWORDS):
            ports.append(p.device)
    return ports


ports = find_esp32_ports()

if not ports:
    raise RuntimeError("No ESP32 detected")

print("Detected ESP32 ports:", ports)
PORT = ports[0]

# PORT = "/dev/ttyACM0"
ROOT = Path("./calsci_latest_itr_python")
CALIBRATION_FILES = 3  # first N files to estimate speed

# --------------------------------------------------
# Filters
# --------------------------------------------------

def should_skip(path: Path) -> bool:
    if any(part.startswith(".") for part in path.parts):
        return True
    if path.name in {".gitignore", ".gitattributes"}:
        return True
    if path.suffix == ".pyc":
        return True
    return False

# --------------------------------------------------
# ampy helpers
# --------------------------------------------------

def ampy_mkdir(path: str):
    subprocess.run(
        ["ampy", "-p", PORT, "mkdir", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def ensure_dirs(remote_path: str):
    parts = remote_path.split("/")[:-1]
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        ampy_mkdir(current)

def upload_file(local_path: Path, remote_path: str):
    subprocess.run(
        ["ampy", "-p", PORT, "put", str(local_path), remote_path],
        check=True,
    )

# --------------------------------------------------
# Collect files
# --------------------------------------------------

files = [
    path
    for path in ROOT.rglob("*")
    if path.is_file() and not should_skip(path)
]

total_files = len(files)
total_chars = sum(path.stat().st_size for path in files)

print(f"\nTotal files      : {total_files}")
print(f"Total characters : {total_chars}")
print("\nUploading files to ESP32...\n")

# --------------------------------------------------
# Upload with ETA
# --------------------------------------------------

uploaded_chars = 0
timings = []
calibrated_speed = None  # chars/sec

for index, path in enumerate(files, start=1):
    remote_path = path.relative_to(ROOT).as_posix()
    file_size = path.stat().st_size

    start = time.perf_counter()

    ensure_dirs(remote_path)
    upload_file(path, remote_path)

    elapsed = time.perf_counter() - start
    uploaded_chars += file_size

    # Calibration phase
    if index <= CALIBRATION_FILES:
        timings.append((file_size, elapsed))
        if index == CALIBRATION_FILES:
            total_c = sum(c for c, _ in timings)
            total_t = sum(t for _, t in timings)
            calibrated_speed = total_c / total_t

    remaining_chars = total_chars - uploaded_chars

    if calibrated_speed:
        eta_sec = remaining_chars / calibrated_speed
        eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_sec))
    else:
        eta_str = "calibrating..."

    percent = (uploaded_chars / total_chars) * 100
    remaining_files = total_files - index

    print(
        f"[{index}/{total_files}] File"
        f"{percent:6.2f}% | "
        f"Time Remaining: {eta_str} → {remote_path}"
    )

print("\nAll files uploaded successfully 🎉")
