"""
CalSci Flasher - MicroPython Flasher Module
Core CalSci communication and file transfer functionality.
"""

import ast
import time
import threading
import sys
import subprocess
import importlib.util
from pathlib import Path
import serial

from config import (
    BAUDRATE, REPL_DELAY, ROOT, CHUNK_SIZE, FIRMWARE_BIN, ESP_CHIP,
    ESP_BEFORE, ESP_AFTER, ESP_BOOTLOADER_AFTER, ESP_CONNECT_ATTEMPTS,
    ESP_AFTER_ERASE, ESP_AFTER_FLASH, ESP_AFTER_RUN,
    ESP_PORT_RESCAN_TIMEOUT, ESP_PORT_RESCAN_INTERVAL, ESP32_KEYWORDS,
)


# ================= EXCEPTIONS =================

class MicroPyError(Exception):
    """Custom exception for MicroPython operations."""
    pass


def _build_esptool_cmd(port: str, firmware_path: Path, baudrate: int, offset: str, chip: str,
                       before: str = ESP_BEFORE, after: str = ESP_AFTER,
                       connect_attempts: int = ESP_CONNECT_ATTEMPTS) -> list:
    """Build esptool command using current Python env if possible."""
    if importlib.util.find_spec("esptool") is not None:
        return [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "--port", port,
            "--baud", str(baudrate),
            "--connect-attempts", str(connect_attempts),
            "--before", before,
            "--after", after,
            "write-flash", offset, str(firmware_path),
        ]
    return [
        "esptool",
        "--chip", chip,
        "--port", port,
        "--baud", str(baudrate),
        "--connect-attempts", str(connect_attempts),
        "--before", before,
        "--after", after,
        "write-flash", offset, str(firmware_path),
    ]


def _build_esptool_erase_cmd(port: str, baudrate: int, chip: str,
                             before: str = ESP_BEFORE, after: str = ESP_AFTER,
                             connect_attempts: int = ESP_CONNECT_ATTEMPTS):
    if importlib.util.find_spec("esptool") is not None:
        return [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "--port", port,
            "--baud", str(baudrate),
            "--connect-attempts", str(connect_attempts),
            "--before", before,
            "--after", after,
            "erase-flash",
        ]
    return [
        "esptool",
        "--chip", chip,
        "--port", port,
        "--baud", str(baudrate),
        "--connect-attempts", str(connect_attempts),
        "--before", before,
        "--after", after,
        "erase-flash",
    ]


def _build_esptool_run_cmd(port: str, baudrate: int, chip: str,
                           before: str = ESP_BEFORE, after: str = ESP_AFTER,
                           connect_attempts: int = ESP_CONNECT_ATTEMPTS):
    if importlib.util.find_spec("esptool") is not None:
        return [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "--port", port,
            "--baud", str(baudrate),
            "--connect-attempts", str(connect_attempts),
            "--before", before,
            "--after", after,
            "run",
        ]
    return [
        "esptool",
        "--chip", chip,
        "--port", port,
        "--baud", str(baudrate),
        "--connect-attempts", str(connect_attempts),
        "--before", before,
        "--after", after,
        "run",
    ]


def _build_esptool_boot_cmd(port: str, baudrate: int, chip: str,
                            before: str = ESP_BEFORE, after: str = ESP_BOOTLOADER_AFTER,
                            connect_attempts: int = ESP_CONNECT_ATTEMPTS):
    if importlib.util.find_spec("esptool") is not None:
        return [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "--port", port,
            "--baud", str(baudrate),
            "--connect-attempts", str(connect_attempts),
            "--before", before,
            "--after", after,
            "chip-id",
        ]
    return [
        "esptool",
        "--chip", chip,
        "--port", port,
        "--baud", str(baudrate),
        "--connect-attempts", str(connect_attempts),
        "--before", before,
        "--after", after,
        "chip-id",
    ]


def _build_esptool_multi_write_cmd(port: str, image_pairs, baudrate: int, chip: str,
                                   before: str = ESP_BEFORE, after: str = ESP_AFTER,
                                   connect_attempts: int = ESP_CONNECT_ATTEMPTS):
    """Build esptool write-flash command with multiple offset/image pairs."""
    if importlib.util.find_spec("esptool") is not None:
        cmd = [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "--port", port,
            "--baud", str(baudrate),
            "--connect-attempts", str(connect_attempts),
            "--before", before,
            "--after", after,
            "write-flash",
        ]
    else:
        cmd = [
            "esptool",
            "--chip", chip,
            "--port", port,
            "--baud", str(baudrate),
            "--connect-attempts", str(connect_attempts),
            "--before", before,
            "--after", after,
            "write-flash",
        ]
    for offset, image_path in image_pairs:
        cmd.extend([str(offset), str(image_path)])
    return cmd


def _build_esptool_elf2image_cmd(elf_path: Path, output_path: Path, chip: str = ESP_CHIP):
    if importlib.util.find_spec("esptool") is not None:
        return [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "elf2image",
            "--flash_size", "16MB",
            "--flash_mode", "dio",
            str(elf_path),
            "-o", str(output_path),
        ]
    return [
        "esptool",
        "--chip", chip,
        "elf2image",
        "--flash_size", "16MB",
        "--flash_mode", "dio",
        str(elf_path),
        "-o", str(output_path),
    ]


def _run_esptool(cmd, log_func=None):
    if log_func:
        log_func(f"Running: {' '.join(cmd)}", "info")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError as e:
        raise MicroPyError(f"esptool not found: {e}") from e

    output_lines = []
    if proc.stdout:
        for line in proc.stdout:
            line = line.rstrip()
            output_lines.append(line)
            if log_func:
                log_func(line, "info")

    ret = proc.wait()
    if ret != 0:
        tail = "\n".join(output_lines[-10:]) if output_lines else "No output"
        raise MicroPyError(f"esptool failed (exit {ret}).\n{tail}")


def _is_esptool_connect_error(error_text: str) -> bool:
    msg = (error_text or "").lower()
    needles = (
        "write timeout",
        "failed to connect",
        "timed out waiting for packet header",
        "serial exception",
        "could not open port",
        "device not found",
        "no serial data received",
    )
    return any(n in msg for n in needles)


def _retry_baud_candidates(primary_baud: int):
    bauds = []
    for baud in (460800, primary_baud, 230400, 115200):
        try:
            val = int(baud)
        except Exception:
            continue
        if val > 0 and val not in bauds:
            bauds.append(val)
    return bauds


def _run_esptool_with_connect_retries(
    build_cmd,
    *,
    port: str,
    chip: str,
    baudrate: int,
    after: str,
    stage_name: str,
    log_func=None,
    before_modes=None,
) -> str:
    """Run esptool command with automatic retries for transient serial/connect errors."""
    if before_modes is None:
        ordered_modes = []
        for mode in ("default-reset", ESP_BEFORE, "usb-reset"):
            if mode and mode not in ordered_modes:
                ordered_modes.append(mode)
        before_modes = tuple(ordered_modes)

    last_error = None
    attempt = 0
    for before_mode in before_modes:
        for baud in _retry_baud_candidates(baudrate):
            attempt += 1
            if attempt > 1 and log_func:
                log_func(
                    f"{stage_name}: retry with --before {before_mode}, --baud {baud}",
                    "warning",
                )
            try:
                cmd = build_cmd(
                    port=port,
                    baudrate=baud,
                    chip=chip,
                    before=before_mode,
                    after=after,
                )
                _run_esptool(cmd, log_func=log_func)
                return _wait_for_port(port, log_func=log_func)
            except MicroPyError as e:
                last_error = e
                if not _is_esptool_connect_error(str(e)):
                    raise
                time.sleep(0.5)
                port = _wait_for_port(port, log_func=log_func)
    if last_error is None:
        raise MicroPyError(f"{stage_name}: unknown esptool failure")
    raise last_error


def _scan_esp_ports():
    from serial.tools import list_ports
    strict_ports = []
    fallback_ports = []
    for p in list_ports.comports():
        device = str(p.device or "")
        text = f"{p.manufacturer} {p.description}".lower()
        vid = getattr(p, "vid", None)
        if any(k.lower() in text for k in ESP32_KEYWORDS) or vid == 0x303A:
            if device:
                strict_ports.append(device)
            continue
        if device.startswith("/dev/ttyACM") or device.startswith("/dev/ttyUSB"):
            fallback_ports.append(device)

    ordered = []
    seen = set()
    for dev in strict_ports + fallback_ports:
        if dev not in seen:
            seen.add(dev)
            ordered.append(dev)
    return ordered


def _wait_for_port(preferred: str, log_func=None):
    """Wait for CalSci port to appear (native USB can re-enumerate)."""
    end = time.time() + ESP_PORT_RESCAN_TIMEOUT
    while time.time() < end:
        ports = _scan_esp_ports()
        if preferred in ports:
            return preferred
        if ports:
            if log_func:
                log_func(f"Port changed: {preferred} → {ports[0]}", "warning")
            return ports[0]
        time.sleep(ESP_PORT_RESCAN_INTERVAL)
    return preferred


def confirm_bootloader(port: str, baudrate: int = BAUDRATE, chip: str = ESP_CHIP,
                       timeout: float = 60.0, log_func=None) -> str:
    """Confirm CalSci is in bootloader mode without auto-reset (manual BOOT+RESET)."""
    end = time.time() + timeout
    last_err = ""
    if log_func:
        log_func("Waiting for bootloader confirmation (BOOT+RESET)…", "info")

    # Require a real reset/reenumeration signal before confirming
    missing_seen = False
    while time.time() < end:
        ports = _scan_esp_ports()
        if port not in ports:
            missing_seen = True
        if missing_seen and ports:
            if port not in ports:
                if log_func:
                    log_func(f"Port changed: {port} → {ports[0]}", "warning")
                port = ports[0]
            break
        time.sleep(0.5)

    if not missing_seen:
        raise MicroPyError("Bootloader signal not detected (port did not reset)")

    while time.time() < end:
        try:
            boot_cmd = _build_esptool_boot_cmd(
                port, baudrate, chip, before="no-reset", after="no-reset"
            )
            _run_esptool(boot_cmd, log_func=None)
            if log_func:
                log_func("Bootloader confirmed ✓", "success")
            return _wait_for_port(port, log_func=log_func)
        except MicroPyError as e:
            last_err = str(e)
        time.sleep(0.5)

    raise MicroPyError(f"Bootloader confirmation timeout. {last_err[:80]}")


def wait_for_reset_signal(port: str, baudrate: int = BAUDRATE, chip: str = ESP_CHIP,
                          timeout: float = 30.0, log_func=None) -> str:
    """Wait for device to leave bootloader (manual RESET)."""
    end = time.time() + timeout
    missing_seen = False
    last_probe = 0.0
    if log_func:
        log_func("Waiting for reset signal…", "info")
    while time.time() < end:
        ports = _scan_esp_ports()
        if port not in ports:
            missing_seen = True
            time.sleep(0.5)
            continue

        if missing_seen:
            if log_func:
                log_func("Reset detected ✓", "success")
            return port

        # Port still present; probe bootloader without resetting (every 2s)
        now = time.time()
        if now - last_probe >= 2.0:
            last_probe = now
            try:
                boot_cmd = _build_esptool_boot_cmd(
                    port, baudrate, chip, before="no-reset", after="no-reset"
                )
                _run_esptool(boot_cmd, log_func=None)
                # Still in bootloader → keep waiting
            except MicroPyError:
                if log_func:
                    log_func("Reset detected ✓", "success")
                return port

        time.sleep(0.5)

    if log_func:
        log_func("Reset not detected (timeout) — continuing.", "warning")
    return _wait_for_port(port, log_func=log_func)


def generate_esp_image_from_elf(elf_path: Path, output_path: Path, chip: str = ESP_CHIP, log_func=None) -> Path:
    """Generate ESP app image from ELF using esptool elf2image."""
    elf_path = Path(elf_path)
    output_path = Path(output_path)
    if not elf_path.exists():
        raise MicroPyError(f"ELF not found: {elf_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = _build_esptool_elf2image_cmd(elf_path, output_path, chip=chip)
    _run_esptool(cmd, log_func=log_func)
    if not output_path.exists():
        raise MicroPyError(f"Failed to create image: {output_path}")
    if log_func:
        log_func(f"Generated image: {output_path}", "success")
    return output_path


def flash_triple_boot_firmware(
    port: str,
    bootloader_path: Path,
    partition_table_path: Path,
    otadata_path: Path,
    micropython_path: Path,
    cpp_path: Path,
    rust_path: Path,
    *,
    bootloader_offset: str = "0x0",
    partition_offset: str = "0x8000",
    otadata_offset: str = "0xF000",
    micropython_offset: str = "0x20000",
    cpp_offset: str = "0x420000",
    rust_offset: str = "0x820000",
    baudrate: int = BAUDRATE,
    chip: str = ESP_CHIP,
    erase_before: bool = True,
    run_after: bool = True,
    log_func=None,
) -> str:
    """Full-chip triple-boot flash: boot assets + all app slots."""
    images = {
        "bootloader": Path(bootloader_path),
        "partition_table": Path(partition_table_path),
        "otadata": Path(otadata_path),
        "micropython": Path(micropython_path),
        "cpp": Path(cpp_path),
        "rust": Path(rust_path),
    }
    for label, path in images.items():
        if not path.exists():
            raise MicroPyError(f"{label} image not found: {path}")

    if log_func:
        log_func("Using automatic USB reset mode (no manual BOOT/RESET needed).", "info")

    if erase_before:
        if log_func:
            log_func("Erasing full flash…", "warning")
        port = _run_esptool_with_connect_retries(
            _build_esptool_erase_cmd,
            port=port,
            chip=chip,
            baudrate=baudrate,
            after=ESP_AFTER_ERASE,
            stage_name="erase-flash",
            log_func=log_func,
        )

    stages = [
        (
            "Flashing bootloader + partition table + ota data",
            [
                (bootloader_offset, images["bootloader"]),
                (partition_offset, images["partition_table"]),
                (otadata_offset, images["otadata"]),
            ],
        ),
        (
            "Flashing MicroPython (ota_0)",
            [(micropython_offset, images["micropython"])],
        ),
        (
            "Flashing C++ (ota_1)",
            [(cpp_offset, images["cpp"])],
        ),
        (
            "Flashing Rust (ota_2)",
            [(rust_offset, images["rust"])],
        ),
    ]

    for stage_name, pairs in stages:
        if log_func:
            log_func(stage_name, "info")
        port = _run_esptool_with_connect_retries(
            lambda port, baudrate, chip, before, after: _build_esptool_multi_write_cmd(
                port,
                pairs,
                baudrate,
                chip,
                before=before,
                after=after,
            ),
            port=port,
            chip=chip,
            baudrate=baudrate,
            after=ESP_AFTER_FLASH,
            stage_name=stage_name,
            log_func=log_func,
        )

    if log_func:
        log_func("Triple-boot flash complete ✓", "success")
        log_func("Device booted automatically (hard-reset mode).", "info")
    return port


def flash_firmware(port: str, firmware_path: Path = FIRMWARE_BIN, baudrate: int = BAUDRATE,
                   offset: str = "0x0", chip: str = ESP_CHIP, erase_before: bool = True,
                   run_after: bool = False, enter_bootloader: bool = False, log_func=None) -> str:
    """Flash firmware.bin using esptool with automatic retry on connection issues."""
    firmware_path = Path(firmware_path)
    if not firmware_path.exists():
        raise MicroPyError(f"Firmware not found: {firmware_path}")

    if log_func:
        log_func("Using automatic USB reset mode (no manual BOOT/RESET needed).", "info")

    if erase_before:
        if log_func:
            log_func("Erasing flash…", "warning")
        port = _run_esptool_with_connect_retries(
            _build_esptool_erase_cmd,
            port=port,
            chip=chip,
            baudrate=baudrate,
            after=ESP_AFTER_ERASE,
            stage_name="erase-flash",
            log_func=log_func,
        )

    if log_func:
        log_func("Flashing firmware…", "info")
    port = _run_esptool_with_connect_retries(
        lambda port, baudrate, chip, before, after: _build_esptool_cmd(
            port, firmware_path, baudrate, offset, chip, before=before, after=after
        ),
        port=port,
        chip=chip,
        baudrate=baudrate,
        after=ESP_AFTER_FLASH,
        stage_name="flash-firmware",
        log_func=log_func,
    )

    if log_func:
        log_func("Firmware flash complete ✓", "success")
        log_func("Device booted automatically (hard-reset mode).", "info")
    return port


def reset_serial(port: str, baudrate: int = BAUDRATE, log_func=None):
    """Toggle DTR/RTS to reset the board."""
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        ser.dtr = False
        ser.rts = True
        time.sleep(0.1)
        ser.dtr = True
        ser.rts = False
        time.sleep(0.1)
        ser.close()
        if log_func:
            log_func("Device reset via DTR/RTS", "info")
    except Exception as e:
        if log_func:
            log_func(f"Reset failed: {str(e)[:80]}", "warning")

# ================= MICRO-PY FLASHER =================

class MicroPyFlasher:
    """Handles all communication and file operations with CalSci."""
    
    def __init__(self, port, baudrate=BAUDRATE):
        self.port = port
        # Use blocking writes to avoid write timeouts on large transfers
        self.ser = serial.Serial(port, baudrate, timeout=1)
        self._keepalive_running = False
        self._keepalive_thread = None
        self._raw_repl = False
        # self._wait_ready(2.0)
        self._enter_repl()


    def close(self):
        """Close serial connection and stop keep-alive."""
        self.ser.close()

    def _wait_ready(self, duration):
        """Wait for a specified duration."""
        end_time = time.perf_counter() + duration
        while time.perf_counter() < end_time:
            pass

    def _enter_repl(self):
        """Enter REPL mode on CalSci."""
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x02")
        self._wait_ready(0.1)
        self.ser.reset_input_buffer()
        self._raw_repl = False

    def enter_raw_repl(self):
        """Enter raw REPL and keep it open for faster transfers."""
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.01)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.01)
        self.ser.reset_input_buffer()
        self._raw_repl = True

    def is_raw_repl(self):
        return self._raw_repl

    def _exec(self, code: str):
        """Execute code in REPL."""
        self.ser.write(code.encode() + b"\r")
        self._wait_ready(REPL_DELAY)

    def _exec_raw_and_read(self, code: str, timeout: float = 5.0) -> str:
        """Enter raw REPL, send code, execute with Ctrl+D, collect output, exit raw REPL."""
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.001)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.001)
        self.ser.reset_input_buffer()
        self._raw_repl = True

        self.ser.write(code.encode())
        self._wait_ready(0.001)

        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
                if b"\x04" in output:
                    break
            time.sleep(0.0001)  # Reduced from 0.005 to 0.0001 for 50x speed improvement

        # Always exit raw REPL after the command
        self.exit_raw_repl()

        if b"\x04" not in output:
            raise MicroPyError("Timeout waiting for raw REPL output")

        output = output.split(b"\x04")[0]

        result = output.decode(errors="ignore")

        if "Traceback" in result:
            raise MicroPyError(result)

        return result

    def mkdir(self, path):
        """Create a directory on CalSci."""
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
        result = self._exec_raw_and_read(code, timeout=1)
        return "EXISTS" in result

    def ensure_dirs(self, remote_path: str):
        """Create each directory in the path sequentially."""
        parts = remote_path.split("/")[:-1]
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            self.mkdir(cur)

    def list_esp32_files(self):
        """List all files and directories on CalSci."""
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

    def get_file_sizes(self, timeout: float = 20.0):
        """Get file sizes of all files on CalSci."""
        code = (
            "import os\r\n"
            "result = {}\r\n"
            "def scan(path):\r\n"
            "    try:\r\n"
            "        for entry in os.ilistdir(path):\r\n"
            "            f = entry[0]\r\n"
            "            typ = entry[1]\r\n"
            "            full = path + '/' + f if path != '/' else '/' + f\r\n"
            "            try:\r\n"
            "                if typ & 0x4000:\r\n"
            "                    scan(full)\r\n"
            "                else:\r\n"
            "                    if len(entry) > 3 and isinstance(entry[3], int):\r\n"
            "                        result[full] = entry[3]\r\n"
            "                    else:\r\n"
            "                        result[full] = os.stat(full)[6]\r\n"
            "            except:\r\n"
            "                pass\r\n"
            "    except:\r\n"
            "        pass\r\n"
            "scan('/')\r\n"
            "print('SIZES:' + repr(result))\r\n"
        )
        raw = ""
        last_error = None
        for attempt in range(2):
            try:
                raw = self._exec_raw_and_read(code, timeout=timeout)
                last_error = None
                break
            except MicroPyError as e:
                last_error = e
                if attempt == 0 and "Timeout waiting for raw REPL output" in str(e):
                    # Recover from transient REPL stalls (busy startup threads / serial noise)
                    self._enter_repl()
                    continue
                raise
        if last_error is not None:
            raise last_error

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
        """Download file content from CalSci as string."""
        if self.is_raw_repl():
            return self.get_raw(remote_path)
        self.enter_raw_repl()
        try:
            return self.get_raw(remote_path)
        finally:
            self.exit_raw_repl()

    def get_raw(self, remote_path: str, timeout: float = 10.0) -> str:
        """Download file content assuming raw REPL is active."""
        code = (
            "import sys\r\n"
            "try:\r\n"
            f"    f = open('{remote_path}', 'r')\r\n"
            "    print('CONTENT_START')\r\n"
            "    while True:\r\n"
            "        data = f.read(256)\r\n"
            "        if not data:\r\n"
            "            break\r\n"
            "        sys.stdout.write(data)\r\n"
            "    f.close()\r\n"
            "    print('CONTENT_END')\r\n"
            "except Exception as e:\r\n"
            "    print('ERROR:' + str(e))\r\n"
        )

        self.ser.reset_input_buffer()
        self.ser.write(code.encode())
        self._wait_ready(0.001)
        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
                if b"\x04" in output:
                    break
            # time.sleep(0.0005)

        if b"\x04" in output:
            output = output.split(b"\x04")[0]
        else:
            raise MicroPyError(f"Timeout listing {path}")

        result = output.decode(errors="ignore")

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

    def scan_device_fast(self):
        """Fast scan: get files and dirs only (skip sizes/modules)."""
        if self.is_raw_repl():
            return self.scan_device_fast_raw()
        self.enter_raw_repl()
        try:
            return self.scan_device_fast_raw()
        finally:
            self.exit_raw_repl()

    def scan_device_fast_raw(self, timeout: float = 30.0, stall_timeout: float = 5.0):
        """Fast scan assuming raw REPL is active (streamed output)."""
        code = (
            "import os, sys\r\n"
            "def scan(path):\r\n"
            "    try:\r\n"
            "        for entry in os.ilistdir(path):\r\n"
            "            name = entry[0]\r\n"
            "            full = path + '/' + name if path != '/' else '/' + name\r\n"
            "            if entry[1] & 0x4000:\r\n"
            "                sys.stdout.write('DIR:' + full + '\\n')\r\n"
            "                scan(full)\r\n"
            "            else:\r\n"
            "                sys.stdout.write('FILE:' + full + '\\n')\r\n"
            "    except Exception as e:\r\n"
            "        sys.stdout.write('ERROR:' + path + ':' + str(e) + '\\n')\r\n"
            "scan('/')\r\n"
        )

        self.ser.reset_input_buffer()
        self.ser.write(code.encode())
        self._wait_ready(0.001)
        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        last_data = start
        while time.perf_counter() - start < timeout:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
                last_data = time.perf_counter()
                if b"\x04" in output:
                    break
            else:
                if time.perf_counter() - last_data > stall_timeout:
                    break
            time.sleep(0.0005)

        if b"\x04" not in output:
            raise MicroPyError("Timeout waiting for raw REPL output")

        output = output.split(b"\x04")[0]
        result = output.decode(errors="ignore")

        files = set()
        dirs = set()
        modules = []
        errors = []

        for line in result.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("FILE:"):
                files.add(line[5:])
            elif line.startswith("DIR:"):
                dirs.add(line[4:])
            elif line.startswith("ERROR:"):
                errors.append(line[6:])

        if not files and not dirs and errors:
            raise MicroPyError(errors[0])

        return files, dirs, modules

    def list_dir(self, path: str = "/"):
        """List files and dirs in a single directory."""
        if self.is_raw_repl():
            try:
                return self.list_dir_raw(path)
            except MicroPyError:
                self.exit_raw_repl()
                return self.list_dir_exec(path)
        self.enter_raw_repl()
        try:
            return self.list_dir_raw(path)
        except MicroPyError:
            self.exit_raw_repl()
            return self.list_dir_exec(path)
        finally:
            if self.is_raw_repl():
                self.exit_raw_repl()

    def list_dir_raw(self, path: str = "/", timeout: float = 20.0, stall_timeout: float = 3.0):
        """List files and dirs in a directory assuming raw REPL is active."""
        if not path:
            path = "/"
        code = (
            "import os, sys\r\n"
            f"path = '{path}'\r\n"
            "try:\r\n"
            "    for entry in os.ilistdir(path):\r\n"
            "        name = entry[0]\r\n"
            "        if entry[1] & 0x4000:\r\n"
            "            sys.stdout.write('DIR:' + name + '\\n')\r\n"
            "        else:\r\n"
            "            sys.stdout.write('FILE:' + name + '\\n')\r\n"
            "except Exception as e:\r\n"
            "    print('ERROR:' + str(e))\r\n"
        )

        self.ser.reset_input_buffer()
        self.ser.write(code.encode())
        self._wait_ready(0.001)
        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        last_data = start
        while time.perf_counter() - start < timeout:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
                last_data = time.perf_counter()
                if b"\x04" in output:
                    break
            else:
                if time.perf_counter() - last_data > stall_timeout:
                    break
            time.sleep(0.0005)

        if b"\x04" in output:
            output = output.split(b"\x04")[0]
        else:
            raise MicroPyError(f"Timeout listing {path}")

        result = output.decode(errors="ignore")
        return self._parse_list_dir_lines(result, path)

    def list_dir_exec(self, path: str = "/", timeout: float = 20.0):
        """List files and dirs using _exec_raw_and_read (more reliable, slower)."""
        if not path:
            path = "/"
        code = (
            "import os, sys\r\n"
            f"path = '{path}'\r\n"
            "try:\r\n"
            "    for entry in os.ilistdir(path):\r\n"
            "        name = entry[0]\r\n"
            "        if entry[1] & 0x4000:\r\n"
            "            sys.stdout.write('DIR:' + name + '\\n')\r\n"
            "        else:\r\n"
            "            sys.stdout.write('FILE:' + name + '\\n')\r\n"
            "except Exception as e:\r\n"
            "    print('ERROR:' + str(e))\r\n"
        )

        result = self._exec_raw_and_read(code, timeout=timeout)
        return self._parse_list_dir_lines(result, path)

    def _parse_list_dir_lines(self, result: str, path: str):
        files = []
        dirs = []
        error = None
        for line in result.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("FILE:"):
                files.append(line[5:])
            elif line.startswith("DIR:"):
                dirs.append(line[4:])
            elif line.startswith("ERROR:"):
                error = line[6:].strip()
        if error:
            raise MicroPyError(f"Failed to list {path}: {error}")
        return sorted(files), sorted(dirs)

    def _parse_list_dir_result(self, result: str):
        files = []
        dirs = []
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
                files = ast.literal_eval(result[files_start:files_end].strip())

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
                dirs = ast.literal_eval(result[dirs_start:dirs_end].strip())
        except Exception as e:
            raise MicroPyError(f"Parse error in list_dir: {e}")

        return files, dirs

    def put_content(self, remote: str, content: str):
        """Upload string content directly to device."""
        data = content.encode('utf-8')
        chunk_size = CHUNK_SIZE
        total_len = len(data)
        num_chunks = (total_len + chunk_size - 1) // chunk_size

        self.ser.write(b"\x03\x03")
        self._wait_ready(0.01)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")
        self._wait_ready(0.01)
        self.ser.reset_input_buffer()

        lines = []
        lines.append('import os')
        lines.append('try:')
        lines.append(f'    os.remove("{remote}")')
        lines.append('except OSError:')
        lines.append('    pass')
        lines.append(f'f = open("{remote}", "wb")')
        for i in range(num_chunks):
            chunk = data[i * chunk_size:(i + 1) * chunk_size]
            lines.append(f'f.write({repr(chunk)})')
        lines.append('f.close()')
        lines.append('print("OK")')

        code = "\r\n".join(lines) + "\r\n"
        self.ser.write(code.encode())
        # self._wait_ready(0.1)

        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 5:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
            if b">>>" in output or (b">" in output and b"OK" in output):
                break
            time.sleep(0.0001)  # Optimized from 0.01 for faster response

        ok_pos = output.find(b"OK")
        traceback_pos = output.find(b"Traceback")

        if traceback_pos != -1 and (ok_pos == -1 or traceback_pos < ok_pos):
            self.ser.write(b"\x02")
            self._wait_ready(0.01)
            raise MicroPyError(output.decode(errors="ignore"))

        if b"OK" not in output:
            self.ser.write(b"\x02")
            self._wait_ready(0.01)
            raise MicroPyError(f"No OK confirmation: {output[:200]}")

        self.ser.write(b"\x02")
        self._wait_ready(0.01)
        self._raw_repl = False

    def delete_file(self, path):
        """Delete a file from CalSci."""
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
        """Recursively remove a directory from CalSci."""
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

    def sync_folder_structure(self, files, log_func, root_path=ROOT):
        """Sync folder structure by creating required folders in order."""
        root_path = Path(root_path)
        required_folders = set()
        for path in files:
            local_path = Path(path)
            try:
                rel = local_path.relative_to(root_path)
            except ValueError:
                log_func(f"  ! {local_path} (outside sync root, skipped)", "warning")
                continue
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

    def put_raw(self, local: Path, remote: str):
        """Upload a file assuming raw REPL is already active."""
        chunk_size = CHUNK_SIZE
        data = local.read_bytes()
        total_len = len(data)
        num_chunks = (total_len + chunk_size - 1) // chunk_size

        self.ser.reset_input_buffer()

        lines = []
        lines.append('import os')
        lines.append('try:')
        lines.append(f'    os.remove("{remote}")')
        lines.append('except OSError:')
        lines.append('    pass')
        lines.append(f'f = open("{remote}", "wb")')
        for i in range(num_chunks):
            chunk = data[i * chunk_size:(i + 1) * chunk_size]
            lines.append(f'f.write({repr(chunk)})')
        lines.append('f.close()')
        lines.append('print("OK")')

        code = "\r\n".join(lines) + "\r\n"
        self.ser.write(code.encode())
        self._wait_ready(0.001)

        self.ser.write(b"\x04")

        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 5:
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
            if b">>>" in output or (b">" in output and b"OK" in output):
                break
            time.sleep(0.0001)

        ok_pos = output.find(b"OK")
        traceback_pos = output.find(b"Traceback")

        if traceback_pos != -1 and (ok_pos == -1 or traceback_pos < ok_pos):
            raise MicroPyError(output.decode(errors="ignore"))

        if b"OK" not in output:
            raise MicroPyError(f"No OK confirmation: {output[:200]}")

    def put(self, local: Path, remote: str):
        """Upload a file to the device using chunked writes in raw REPL."""
        self.enter_raw_repl()
        try:
            self.put_raw(local, remote)
        finally:
            self.exit_raw_repl()

    def exit_raw_repl(self):
        """Safety call — ensure we're back in normal REPL"""
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.01)
        self.ser.write(b"\x02")
        self._wait_ready(0.01)
        self.ser.reset_input_buffer()
        self._raw_repl = False

    def clean_all(self, log_func=None):
        """Delete all files and folders from CalSci root directory."""
        if log_func:
            log_func("⚠️  Starting CalSci cleanup...", "warning")

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
            log_func("✅ CalSci cleanup complete", "success")

        # Add empty boot.py file
        if log_func:
            log_func("📄 Creating empty boot.py...", "info")
        self.put_content("boot.py", "")
        if log_func:
            log_func("✓ Empty boot.py created", "success")

        return True

    def reset_soft_with_output(self, timeout=3.0, log_func=None, auto_cd=None, enter_repl=True):
        """Soft reset and capture boot output.
        
        Args:
            timeout: How long to wait for boot output
            log_func: Optional logging function
            auto_cd: Optional directory to navigate to after reset
            enter_repl: If True, enters REPL mode after reset. If False, stays in raw mode.
        """
        try:
            self.ser.write(b"\x03\x03")
            time.sleep(0.1)
            self.ser.reset_input_buffer()
            self.ser.write(b"\x04")
            
            output = b""
            start = time.perf_counter()
            while time.perf_counter() - start < timeout:
                if self.ser.in_waiting:
                    output += self.ser.read(self.ser.in_waiting)
                time.sleep(0.01)
            
            result = output.decode(errors="ignore")
            
            # Auto-log if log function provided
            if log_func:
                if "Traceback" in result or "Error" in result:
                    log_func("⚠️  BOOT ERROR:", "error")
                    log_func(result, "error")
                else:
                    log_func("✓ Soft reset complete", "success")
            
            # Enter REPL if requested
            if enter_repl:
                self._enter_repl()
                if log_func:
                    log_func("✓ REPL mode ready", "info")
            else:
                if log_func:
                    log_func("⚠️  Staying in raw mode (no REPL)", "warning")
            
            # Auto-navigate to directory after reset (only if in REPL mode)
            if auto_cd and enter_repl:
                self._auto_navigate(auto_cd, log_func)
            
            return result
            
        except Exception as e:
            raise MicroPyError(f"Soft reset failed: {e}")

    def _auto_navigate(self, directory: str, log_func=None):
        """Automatically change to specified directory after reset."""
        code = (
            "import os\r\n"
            f"os.chdir('{directory}')\r\n"
            "print('CWD:' + os.getcwd())\r\n"
        )
        
        try:
            result = self._exec_raw_and_read(code, timeout=2.0)
            if log_func and "CWD:" in result:
                cwd = result.split("CWD:")[-1].strip().split()[0]
                log_func(f"📁 Auto-navigated to: {cwd}", "success")
        except Exception as e:
            if log_func:
                log_func(f"⚠️  Auto-navigation failed: {e}", "warning")

    def reset_soft_interactive(self, auto_cd=None, log_func=None):
        """Soft reset and enter REPL for interactive use.
        
        Args:
            auto_cd: Optional directory to navigate to (e.g., "/apps/installed_apps")
            log_func: Optional logging function
        
        Use when: User will interact with REPL after reset
        """
        return self.reset_soft_with_output(
            timeout=5.0,
            log_func=log_func,
            auto_cd=auto_cd,
            enter_repl=True  # REPL ready for user
        )

    def reset_soft_automated(self, auto_cd=None, log_func=None):
        """Soft reset without REPL for automated workflows.

        Args:
            auto_cd: Optional directory to navigate to (e.g., "/apps/installed_apps")
            log_func: Optional logging function

        Use when: Script will continue running commands after reset
        """
        return self.reset_soft_with_output(
            timeout=5.0,
            log_func=log_func,
            auto_cd=auto_cd,
            enter_repl=False  # No REPL - stay ready for automation
        )

    def run_file(self, file_path: str, timeout: float = 10.0, log_func=None):
        """Execute a Python file on the device and capture output.

        Args:
            file_path: Path to the file on CalSci (e.g., "/apps/my_app.py")
            timeout: How long to capture output (device continues running after)
            log_func: Optional logging function for real-time output

        Returns:
            Captured output string

        Note: Device continues running the file after timeout (no REPL blocking).
        """
        if log_func:
            log_func(f"▶ Running {file_path}...", "info")

        # Enter raw REPL mode
        self.ser.write(b"\x03\x03")  # Ctrl+C to interrupt any running code
        time.sleep(0.1)
        self.ser.reset_input_buffer()
        self.ser.write(b"\x01")  # Ctrl+A for raw REPL
        time.sleep(0.1)
        self.ser.reset_input_buffer()

        # Execute the file using exec()
        code = f"import sys\nif '/' not in sys.path: sys.path.append('/')\nexec(open('{file_path}').read())\r\n"
        self.ser.write(code.encode())
        time.sleep(0.05)

        # Send Ctrl+D to execute
        self.ser.write(b"\x04")

        # Capture output for specified timeout
        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            if self.ser.in_waiting:
                chunk = self.ser.read(self.ser.in_waiting)
                output += chunk

                # Log output in real-time
                if log_func:
                    try:
                        text = chunk.decode(errors="ignore")
                        for line in text.split('\n'):
                            line = line.strip()
                            if line and not line.startswith('>'):
                                if "Traceback" in line or "Error" in line:
                                    log_func(f"  ✗ {line}", "error")
                                else:
                                    log_func(f"  {line}", "output")
                    except:
                        pass

            time.sleep(0.01)

        result = output.decode(errors="ignore")

        # Check for errors
        if "Traceback" in result or "Error" in result:
            if log_func:
                log_func("⚠ Script encountered an error", "error")
        else:
            if log_func:
                log_func("✓ Script started successfully", "success")

        # Exit raw REPL but don't interrupt running code
        # Just send Ctrl+B to exit raw mode, the script continues running
        self.ser.write(b"\x02")
        time.sleep(0.05)

        return result

    def save_upload_and_run(self, remote_path: str, content: str, timeout: float = 10.0, log_func=None):
        """Complete workflow: upload file, inject into main.py, soft reset to run.

        This injects script execution into main.py temporarily, so after soft reset
        the device runs: boot.py → main.py → your script WITHOUT REPL mode.
        Device stays responsive for button clicks and inputs.

        Args:
            remote_path: Path on CalSci (e.g., "/apps/my_app.py")
            content: File content to upload
            timeout: How long to capture run output
            log_func: Optional logging function

        Returns:
            dict with 'upload_success', 'reset_output', 'run_output', 'errors'
        """
        result = {
            'upload_success': False,
            'reset_output': '',
            'run_output': '',
            'errors': []
        }

        # Marker to identify injected code
        RUN_MARKER = "# === CALSCI_AUTO_RUN ==="

        try:
            # Step 1: Upload the target file
            if log_func:
                log_func("📤 Step 1: Uploading file...", "info")

            self.ensure_dirs(remote_path.lstrip("/"))
            self.put_content(remote_path.lstrip("/"), content)
            result['upload_success'] = True

            if log_func:
                log_func(f"  ✓ Uploaded to {remote_path}", "success")

            # Step 2: Read current main.py and inject execution code
            if log_func:
                log_func("🔧 Step 2: Injecting auto-run into main.py...", "info")

            # First try to get original from backup (in case of interrupted previous run)
            original_main = ""
            try:
                original_main = self.get("main.py.bak")
                if log_func:
                    log_func("  📦 Using existing backup", "info")
            except:
                # No backup, read current main.py
                try:
                    original_main = self.get("main.py")
                    # If current main.py has injection, extract original content
                    if RUN_MARKER in original_main:
                        # Find where injection ends (look for def or import after marker)
                        lines = original_main.split('\n')
                        clean_lines = []
                        past_injection = False
                        blank_count = 0
                        for line in lines:
                            if RUN_MARKER in line:
                                past_injection = False
                                blank_count = 0
                            elif not past_injection:
                                if line.strip() == '':
                                    blank_count += 1
                                    if blank_count >= 1 and not line.startswith(' '):
                                        past_injection = True
                                elif not line.startswith(' ') and not line.startswith('\t'):
                                    if not any(line.startswith(x) for x in ['def ', 'try:', 'except', 'import ', 'from ', '_calsci']):
                                        past_injection = True
                                        clean_lines.append(line)
                            else:
                                clean_lines.append(line)
                        original_main = '\n'.join(clean_lines)
                except:
                    original_main = ""
                    if log_func:
                        log_func("  ⚠ No main.py found, creating one", "warning")

            # Create injection code with error handling
            # PREPEND to main.py so it runs BEFORE any while loops
            # Parse remote_path to get app_name and group_name
            path_parts = remote_path.strip("/").split("/")
            app_name = path_parts[-1].replace(".py", "")
            group_name = path_parts[-2] if len(path_parts) > 1 else "root"

            # Step 2a: Backup original main.py first (safer than marker parsing)
            if log_func:
                log_func("  📦 Backing up original main.py...", "info")
            self.put_content("main.py.bak", original_main)

            # Self-cleaning injection: restores from backup after running once
            # This ensures hard reset returns to normal behavior
            injection_code = f'''# === CALSCI_AUTO_RUN ===
def _calsci_restore():
    import os
    try:
        f = open("main.py.bak", "r")
        original = f.read()
        f.close()
        f = open("main.py", "w")
        f.write(original)
        f.close()
        os.remove("main.py.bak")
        print("[CalSci] main.py restored")
    except Exception as e:
        print("[CalSci] restore error:", e)

try:
    from data_modules.object_handler import app
    app.set_app_name("{app_name}")
    app.set_group_name("{group_name}")
    from process_modules.app_runner import app_runner
    _calsci_restore()
    app_runner()
except Exception as e:
    print("[CalSci] Error:", e)
    _calsci_restore()
'''

            # PREPEND injection to main.py (runs first, before any loops)
            modified_main = injection_code + original_main
            self.put_content("main.py", modified_main)

            if log_func:
                log_func(f"  ✓ Injected auto-run for {remote_path}", "success")

            # Step 3: Soft reset and DISCONNECT so device runs freely
            if log_func:
                log_func("🔄 Step 3: Soft reset & disconnect...", "info")

            # Send soft reset
            self.ser.write(b"\x03\x03")  # Ctrl+C to stop any running code
            time.sleep(0.1)
            self.ser.reset_input_buffer()
            self.ser.write(b"\x04")  # Ctrl+D for soft reset
            time.sleep(0.3)  # Brief wait for reset to start

            # Capture brief output to confirm reset started
            output = b""
            start = time.perf_counter()
            while time.perf_counter() - start < 2.0:  # Only 2 seconds
                if self.ser.in_waiting:
                    chunk = self.ser.read(self.ser.in_waiting)
                    output += chunk
                time.sleep(0.01)

            result['run_output'] = output.decode(errors="ignore")

            # Log what we captured
            if log_func:
                for line in result['run_output'].split('\n'):
                    line = line.strip()
                    if line and not line.startswith('>') and 'MicroPython' not in line:
                        if "Traceback" in line or "Error" in line:
                            log_func(f"  {line}", "error")
                        elif "▶" in line:
                            log_func(f"  {line}", "info")
                        else:
                            log_func(f"  {line}", "output")

            # CLOSE SERIAL so device runs independently!
            if log_func:
                log_func("🔌 Disconnecting serial (CalSci runs free)...", "info")

            self.ser.close()
            self.ser = None  # Mark as closed

            if log_func:
                log_func("✓ Disconnected! CalSci running independently", "success")
                log_func("✅ Save & Run complete!", "success")
                log_func("ℹ️ main.py auto-cleans after first run (safe to hard reset)", "info")

        except Exception as e:
            error_msg = str(e)
            result['errors'].append(error_msg)
            if log_func:
                log_func(f"✗ Error: {error_msg}", "error")

        return result

    def restore_main_py(self, log_func=None):
        """Remove auto-run injection from main.py by restoring from backup."""
        RUN_MARKER = "# === CALSCI_AUTO_RUN ==="

        try:
            if log_func:
                log_func("🔧 Restoring original main.py...", "info")

            # First, try to restore from backup file (preferred method)
            try:
                backup_content = self.get("main.py.bak")
                self.put_content("main.py", backup_content)
                self.delete_file("main.py.bak")
                if log_func:
                    log_func("✓ Restored from backup", "success")
                return True
            except:
                pass  # No backup, try marker-based restore

            # Fallback: check for injection marker and remove it
            main_content = self.get("main.py")

            if RUN_MARKER in main_content:
                # Find where the injection ends (empty line after injection)
                lines = main_content.split('\n')
                clean_lines = []
                in_injection = False
                for line in lines:
                    if RUN_MARKER in line:
                        in_injection = True
                    elif in_injection and line.strip() == '' and not line.startswith(' '):
                        in_injection = False
                    elif not in_injection:
                        clean_lines.append(line)

                clean_main = '\n'.join(clean_lines).lstrip('\n')
                self.put_content("main.py", clean_main)
                if log_func:
                    log_func("✓ Restored original main.py", "success")
                return True

            if log_func:
                log_func("ℹ️ No auto-run injection found", "info")
            return True

        except Exception as e:
            if log_func:
                log_func(f"✗ Error: {e}", "error")
            return False

    def stream_output(self, duration: float = 5.0, log_func=None):
        """Stream serial output for specified duration (for monitoring running scripts).

        Args:
            duration: How long to stream output
            log_func: Optional logging function

        Returns:
            Captured output string
        """
        output = b""
        start = time.perf_counter()

        while time.perf_counter() - start < duration:
            if self.ser.in_waiting:
                chunk = self.ser.read(self.ser.in_waiting)
                output += chunk

                if log_func:
                    try:
                        text = chunk.decode(errors="ignore")
                        for line in text.split('\n'):
                            line = line.strip()
                            if line:
                                log_func(f"  {line}", "output")
                    except:
                        pass
            time.sleep(0.01)

        return output.decode(errors="ignore")
