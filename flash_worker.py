# import sys
# from pathlib import Path
# import subprocess
# from serial.tools import list_ports

# ROOT = Path("./calsci_latest_itr_python")
# ESP32_KEYWORDS = ("Espressif",)

# import sys
# sys.stdout.reconfigure(line_buffering=True)


# def find_esp32():
#     for p in list_ports.comports():
#         text = f"{p.manufacturer} {p.description}".lower()
#         if any(k.lower() in text for k in ESP32_KEYWORDS):
#             return p.device
#     raise RuntimeError("No ESP32 found")

# port = find_esp32()

# files = [p for p in ROOT.rglob("*") if p.is_file()]

# for i, path in enumerate(files, 1):
#     remote = path.relative_to(ROOT).as_posix()
#     # print(f"[{i}/{len(files)}] {remote}", flush=True)
#     print(f"[{i}/{len(files)}] {remote}", flush=True)

#     subprocess.run(
#         ["ampy", "-p", port, "put", str(path), remote],
#         stdout=subprocess.DEVNULL,
#         stderr=subprocess.DEVNULL,
#         check=True,
#     )


import sys
import io
import contextlib
from pathlib import Path
from serial.tools import list_ports

# Ensure output is sent to the GUI immediately
sys.stdout.reconfigure(line_buffering=True)

# Import mpremote logic
try:
    from mpremote.main import main as mpremote_main
except ImportError:
    print("Error: mpremote not installed. Run 'pip install mpremote'")
    sys.exit(1)

# ================= CONFIG =================
ROOT = Path("./calsci_latest_itr_python")
ESP32_KEYWORDS = ("Espressif", "CP210", "CH340")

def find_esp32():
    for p in list_ports.comports():
        text = f"{p.manufacturer} {p.description} {p.hwid}".lower()
        if any(k.lower() in text for k in ESP32_KEYWORDS):
            return p.device
    return None

def should_skip(path: Path) -> bool:
    """Filter out git files and python cache."""
    if any(part.startswith(".") for part in path.parts):
        return True
    if path.suffix == ".pyc":
        return True
    return False

def run_flash():
    port = find_esp32()
    if not port:
        print("❌ Error: No ESP32 detected. Check USB connection.")
        sys.exit(1)

    print(f"📡 Connected to device on {port}")

    # Gather files
    files = [p for p in ROOT.rglob("*") if p.is_file() and not should_skip(p)]
    total = len(files)

    if total == 0:
        print(f"⚠️ No files found in {ROOT}")
        return

    print(f"📦 Found {total} files to upload.")

    for i, path in enumerate(files, 1):
        # MicroPython uses '/' as root. mpremote needs ':' prefix for remote paths
        remote_path = ":" + path.relative_to(ROOT).as_posix()
        
        print(f"[{i}/{total}] Uploading: {remote_path}")

        # Execute mpremote command
        # mpremote fs cp <local> <remote>
        args = ["connect", port, "fs", "cp", str(path), remote_path]
        
        try:
            # Silence mpremote's internal prints so they don't clutter your GUI
            with contextlib.redirect_stdout(io.StringIO()):
                mpremote_main(args)
        except Exception as e:
            print(f"❌ Failed to upload {path.name}: {e}")
            sys.exit(1)

    print("⚡ Soft resetting device...")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mpremote_main(["connect", port, "exec", "import machine; machine.reset()"])
    except:
        pass

    print("🎉 All files uploaded successfully!")

if __name__ == "__main__":
    try:
        run_flash()
    except Exception as e:
        print(f"❌ Critical Error: {e}")
        sys.exit(1)