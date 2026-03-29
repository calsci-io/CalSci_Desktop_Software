"""
WebREPL transport helpers for CalSci desktop software.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import socket
import struct
import time
import webbrowser

from config import (
    CHUNK_SIZE,
    WEBREPL_CLIENT_HTML,
    WIRELESS_DEFAULT_PORT,
    WIRELESS_RESET_DELAY_MS,
    WIRELESS_STATUS_PORT,
)


WEBREPL_REQ_S = "<2sBBQLH64s"
WEBREPL_PUT_FILE = 1
WEBREPL_FRAME_TXT = 0x81
WEBREPL_FRAME_BIN = 0x82


class WirelessTransferError(RuntimeError):
    pass


def _friendly_network_error(exc, host=None, port=None):
    err_no = getattr(exc, "errno", None)
    target = ""
    if host:
        target = str(host)
        if port:
            target += ":" + str(port)

    if err_no == 113:
        detail = "No route to host"
        if target:
            detail += " for " + target
        return WirelessTransferError(
            detail
            + ". Your laptop cannot reach the CalSci IP on the LAN. This is usually AP/client isolation, guest-network isolation, or blocked peer-to-peer traffic on the router."
        )

    if err_no == 111:
        detail = "Connection refused"
        if target:
            detail += " by " + target
        return WirelessTransferError(detail + ". WebREPL is not accepting connections on the device.")

    if isinstance(exc, socket.timeout):
        detail = "Timed out while connecting"
        if target:
            detail += " to " + target
        return WirelessTransferError(detail + ". The device did not answer on the network.")

    return WirelessTransferError(str(exc))


class _WebSocket:
    def __init__(self, sock):
        self.s = sock
        self.buf = b""

    def write(self, data, frame=WEBREPL_FRAME_BIN):
        size = len(data)
        if size < 126:
            header = struct.pack(">BB", frame, size)
        else:
            header = struct.pack(">BBH", frame, 126, size)
        self.s.sendall(header)
        if data:
            self.s.sendall(data)

    def recvexactly(self, size):
        result = b""
        while size:
            chunk = self.s.recv(size)
            if not chunk:
                break
            result += chunk
            size -= len(chunk)
        return result

    def read(self, size, text_ok=False):
        if not self.buf:
            while True:
                header = self.recvexactly(2)
                if len(header) != 2:
                    raise WirelessTransferError("Connection closed while reading WebREPL frame")
                frame_type, frame_size = struct.unpack(">BB", header)
                if frame_size == 126:
                    header = self.recvexactly(2)
                    if len(header) != 2:
                        raise WirelessTransferError("Connection closed while reading WebREPL frame size")
                    (frame_size,) = struct.unpack(">H", header)
                if frame_type == WEBREPL_FRAME_BIN or (text_ok and frame_type == WEBREPL_FRAME_TXT):
                    break
                while frame_size:
                    skipped = self.s.recv(frame_size)
                    if not skipped:
                        raise WirelessTransferError("Connection closed while skipping WebREPL frame")
                    frame_size -= len(skipped)
            data = self.recvexactly(frame_size)
            if len(data) != frame_size:
                raise WirelessTransferError("Connection closed while reading WebREPL payload")
            self.buf = data

        data = self.buf[:size]
        self.buf = self.buf[size:]
        return data

    def ioctl(self, req, val):
        if req != 9 or val != 2:
            raise WirelessTransferError("Unsupported WebREPL websocket ioctl request")


def _parse_remote(host: str, default_port: int = WIRELESS_DEFAULT_PORT):
    host = str(host or "").strip()
    if not host:
        raise WirelessTransferError("Wireless host/IP is empty")
    if ":" in host:
        base, port_text = host.rsplit(":", 1)
        return base.strip(), int(port_text)
    return host, int(default_port)


def _client_handshake(sock):
    handle = sock.makefile("rwb", 0)
    handle.write(
        b"GET / HTTP/1.1\r\n"
        b"Host: calsci\r\n"
        b"Connection: Upgrade\r\n"
        b"Upgrade: websocket\r\n"
        b"Sec-WebSocket-Key: calsci\r\n"
        b"\r\n"
    )
    handle.readline()
    while True:
        line = handle.readline()
        if line == b"\r\n":
            break


def _login(ws, password):
    while True:
        token = ws.read(1, text_ok=True)
        if token == b":":
            next_char = ws.read(1, text_ok=True)
            if next_char == b" ":
                break
    ws.write(str(password).encode("utf-8") + b"\r", WEBREPL_FRAME_TXT)


def _read_resp(ws):
    data = ws.read(4)
    if len(data) != 4:
        raise WirelessTransferError("Incomplete WebREPL response")
    sig, code = struct.unpack("<2sH", data)
    if sig != b"WB":
        raise WirelessTransferError("Unexpected WebREPL response signature")
    return code


def _send_req(ws, op, size=0, fname=b""):
    if len(fname) > 64:
        raise WirelessTransferError("Remote path is too long for WebREPL file transfer")
    record = struct.pack(WEBREPL_REQ_S, b"WA", op, 0, 0, size, len(fname), fname)
    ws.write(record[:10])
    ws.write(record[10:])


def _extract_python_literal(text: str, marker: str):
    start = text.find(marker)
    if start == -1:
        raise WirelessTransferError("Missing marker: %s" % marker)
    start += len(marker)

    open_char = None
    close_char = None
    for char in text[start:]:
        if char in "[{(":
            open_char = char
            close_char = {"[": "]", "{": "}", "(": ")"}[char]
            break
        if char == "'" or char == '"':
            open_char = char
            close_char = char
            break
    if open_char is None:
        raise WirelessTransferError("No literal found after marker: %s" % marker)

    literal_start = text.find(open_char, start)
    if literal_start == -1:
        raise WirelessTransferError("No literal start found after marker: %s" % marker)

    if open_char in ("'", '"'):
        literal_end = text.find(close_char, literal_start + 1)
        if literal_end == -1:
            raise WirelessTransferError("Unterminated literal for marker: %s" % marker)
        literal = text[literal_start:literal_end + 1]
        return ast.literal_eval(literal)

    depth = 0
    literal_end = literal_start
    for index in range(literal_start, len(text)):
        char = text[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                literal_end = index + 1
                break
    literal = text[literal_start:literal_end]
    return ast.literal_eval(literal)


class WirelessProgressReporter:
    def __init__(self, host: str, port: int = WIRELESS_STATUS_PORT, throttle_s: float = 0.12):
        self.host = str(host or "").strip()
        self.port = int(port)
        self.throttle_s = max(0.02, float(throttle_s))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.session_id = str(int(time.time() * 1000))
        self.last_sent_at = 0.0
        self.operation = "wireless"
        self.total_files = 0
        self.total_bytes = 0
        self.done_files = 0
        self.current_file = ""
        self.current_file_size = 0
        self.current_file_sent = 0
        self.overall_sent = 0

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

    def _send(self, payload, force=False):
        if not self.host:
            return
        now = time.monotonic()
        if not force and now - self.last_sent_at < self.throttle_s:
            return
        self.last_sent_at = now
        payload = dict(payload)
        payload["session_id"] = self.session_id
        payload["updated_at_ms"] = int(time.time() * 1000)
        data = json.dumps(payload).encode("utf-8")
        try:
            self.sock.sendto(data, (self.host, self.port))
        except Exception:
            pass

    def begin(self, operation: str, total_files: int, total_bytes: int):
        self.operation = str(operation or "wireless")
        self.total_files = max(0, int(total_files))
        self.total_bytes = max(0, int(total_bytes))
        self.done_files = 0
        self.current_file = ""
        self.current_file_size = 0
        self.current_file_sent = 0
        self.overall_sent = 0
        self._send(
            {
                "state": "ready",
                "operation": self.operation,
                "message": "Waiting to upload",
                "total_files": self.total_files,
                "files_done": self.done_files,
                "files_remaining": self.total_files,
                "bytes_total": self.total_bytes,
                "bytes_sent": self.overall_sent,
                "bytes_remaining": self.total_bytes,
                "percent": 0.0,
                "current_file": "",
                "current_file_size": 0,
                "current_file_sent": 0,
            },
            force=True,
        )

    def file_started(self, file_index: int, remote_path: str, file_size: int):
        self.current_file = str(remote_path)
        self.current_file_size = max(0, int(file_size))
        self.current_file_sent = 0
        self._send(
            {
                "state": "uploading",
                "operation": self.operation,
                "message": "Uploading {}".format(Path(remote_path).name),
                "current_index": int(file_index),
                "total_files": self.total_files,
                "files_done": self.done_files,
                "files_remaining": max(self.total_files - self.done_files, 0),
                "bytes_total": self.total_bytes,
                "bytes_sent": self.overall_sent,
                "bytes_remaining": max(self.total_bytes - self.overall_sent, 0),
                "percent": round((self.overall_sent / max(self.total_bytes, 1)) * 100, 2),
                "current_file": self.current_file,
                "current_file_size": self.current_file_size,
                "current_file_sent": self.current_file_sent,
            },
            force=True,
        )

    def file_progress(self, file_bytes_sent: int, overall_bytes_sent: int):
        self.current_file_sent = max(0, int(file_bytes_sent))
        self.overall_sent = max(0, int(overall_bytes_sent))
        self._send(
            {
                "state": "uploading",
                "operation": self.operation,
                "message": "Uploading {}".format(Path(self.current_file).name if self.current_file else "file"),
                "total_files": self.total_files,
                "files_done": self.done_files,
                "files_remaining": max(self.total_files - self.done_files, 0),
                "bytes_total": self.total_bytes,
                "bytes_sent": self.overall_sent,
                "bytes_remaining": max(self.total_bytes - self.overall_sent, 0),
                "percent": round((self.overall_sent / max(self.total_bytes, 1)) * 100, 2),
                "current_file": self.current_file,
                "current_file_size": self.current_file_size,
                "current_file_sent": self.current_file_sent,
            },
        )

    def file_finished(self, success=True):
        if success:
            self.done_files += 1
        self._send(
            {
                "state": "uploading" if success else "error",
                "operation": self.operation,
                "message": "Uploaded {}".format(Path(self.current_file).name) if success else "Upload failed",
                "total_files": self.total_files,
                "files_done": self.done_files,
                "files_remaining": max(self.total_files - self.done_files, 0),
                "bytes_total": self.total_bytes,
                "bytes_sent": self.overall_sent,
                "bytes_remaining": max(self.total_bytes - self.overall_sent, 0),
                "percent": round((self.overall_sent / max(self.total_bytes, 1)) * 100, 2),
                "current_file": self.current_file,
                "current_file_size": self.current_file_size,
                "current_file_sent": self.current_file_sent,
            },
            force=True,
        )

    def fail(self, message: str):
        self._send(
            {
                "state": "error",
                "operation": self.operation,
                "message": str(message or "Wireless transfer failed"),
                "total_files": self.total_files,
                "files_done": self.done_files,
                "files_remaining": max(self.total_files - self.done_files, 0),
                "bytes_total": self.total_bytes,
                "bytes_sent": self.overall_sent,
                "bytes_remaining": max(self.total_bytes - self.overall_sent, 0),
                "percent": round((self.overall_sent / max(self.total_bytes, 1)) * 100, 2),
                "current_file": self.current_file,
                "current_file_size": self.current_file_size,
                "current_file_sent": self.current_file_sent,
            },
            force=True,
        )

    def complete(self, auto_reset=True, reset_delay_ms=WIRELESS_RESET_DELAY_MS):
        self.overall_sent = max(self.overall_sent, self.total_bytes)
        self._send(
            {
                "state": "complete",
                "operation": self.operation,
                "message": "Upload complete",
                "total_files": self.total_files,
                "files_done": self.total_files,
                "files_remaining": 0,
                "bytes_total": self.total_bytes,
                "bytes_sent": self.overall_sent,
                "bytes_remaining": 0,
                "percent": 100.0,
                "current_file": self.current_file,
                "current_file_size": self.current_file_size,
                "current_file_sent": self.current_file_size,
                "auto_reset": bool(auto_reset),
                "reset_delay_ms": int(reset_delay_ms),
            },
            force=True,
        )


class WirelessWebReplTransport:
    def __init__(
        self,
        host: str,
        password: str,
        port: int = WIRELESS_DEFAULT_PORT,
        status_port: int = WIRELESS_STATUS_PORT,
        reset_delay_ms: int = WIRELESS_RESET_DELAY_MS,
    ):
        self.host = str(host or "").strip()
        self.password = str(password or "")
        self.port = int(port)
        self.status_port = int(status_port)
        self.reset_delay_ms = int(reset_delay_ms)
        self.progress_reporter = WirelessProgressReporter(self.host, self.status_port)

    def close(self):
        self.progress_reporter.close()

    def reconnect(self):
        return WirelessWebReplTransport(
            host=self.host,
            password=self.password,
            port=self.port,
            status_port=self.status_port,
            reset_delay_ms=self.reset_delay_ms,
        )

    def is_raw_repl(self):
        return False

    def enter_raw_repl(self):
        return None

    def exit_raw_repl(self):
        return None

    def _open_socket(self, timeout: float = 8.0):
        host, port = _parse_remote("{}:{}".format(self.host, self.port))
        sock = socket.socket()
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            _client_handshake(sock)
            ws = _WebSocket(sock)
            _login(ws, self.password)
            return sock, ws
        except Exception as exc:
            try:
                sock.close()
            except Exception:
                pass
            raise _friendly_network_error(exc, host=host, port=port) from exc

    def _open_binary_ws(self, timeout: float = 8.0):
        sock, ws = self._open_socket(timeout=timeout)
        _read_until_prompt(ws, timeout=min(timeout, 3.0))
        ws.ioctl(9, 2)
        return sock, ws

    def exec_script(self, script: str, timeout: float = 10.0):
        sock, ws = self._open_socket(timeout=timeout)
        try:
            _read_until_prompt(ws, timeout=min(timeout, 3.0))
            command = "exec(" + repr(str(script)) + ")\r"
            ws.write(command.encode("utf-8"), WEBREPL_FRAME_TXT)
            result = _read_until_prompt(ws, timeout=timeout)
            if "Traceback" in result:
                raise WirelessTransferError(result)
            return result
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def mkdir(self, path):
        path_expr = repr(str(path))
        result = self.exec_script(
            "import os\n"
            "try:\n"
            "    os.mkdir({})\n"
            "except Exception:\n"
            "    pass\n"
            "try:\n"
            "    os.stat({})\n"
            "    print('EXISTS')\n"
            "except Exception:\n"
            "    print('MISSING')\n".format(path_expr, path_expr),
            timeout=4.0,
        )
        return "EXISTS" in result

    def ensure_dirs(self, remote_path: str):
        parts = str(remote_path).split("/")[:-1]
        current = ""
        for part in parts:
            if not part:
                continue
            current = "{}/{}".format(current, part) if current else part
            self.mkdir(current)

    def sync_folder_structure(self, files, log_func, root_path):
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
            for index in range(len(parts) - 1):
                required_folders.add("/".join(parts[: index + 1]))

        sorted_folders = sorted(required_folders, key=lambda value: len(value.split("/")))
        log_func("Creating folder structure…", "info")
        for folder in sorted_folders:
            if self.mkdir(folder):
                log_func(f"  + {folder}", "info")
            else:
                log_func(f"  ! {folder} (failed)", "warning")
        log_func("Folder structure synced ✓", "success")

    def get_file_sizes(self, timeout: float = 25.0):
        result = self.exec_script(
            "import os\n"
            "result = {}\n"
            "def scan(path):\n"
            "    try:\n"
            "        for entry in os.ilistdir(path):\n"
            "            name = entry[0]\n"
            "            full = path + '/' + name if path != '/' else '/' + name\n"
            "            try:\n"
            "                if entry[1] & 0x4000:\n"
            "                    scan(full)\n"
            "                else:\n"
            "                    if len(entry) > 3 and isinstance(entry[3], int):\n"
            "                        result[full] = entry[3]\n"
            "                    else:\n"
            "                        result[full] = os.stat(full)[6]\n"
            "            except Exception:\n"
            "                pass\n"
            "    except Exception:\n"
            "        pass\n"
            "scan('/')\n"
            "print('SIZES:' + repr(result))\n",
            timeout=timeout,
        )
        try:
            return _extract_python_literal(result, "SIZES:")
        except Exception as exc:
            raise WirelessTransferError(f"Failed to parse remote file sizes: {exc}") from exc

    def put(self, local: Path, remote: str, progress_cb=None):
        return self._put_file(local, remote, progress_cb=progress_cb)

    def put_raw(self, local: Path, remote: str, progress_cb=None):
        return self._put_file(local, remote, progress_cb=progress_cb)

    def _put_file(self, local: Path, remote: str, progress_cb=None):
        local = Path(local)
        total_size = local.stat().st_size
        remote_name = str(remote)
        if not remote_name.startswith("/"):
            remote_name = "/" + remote_name
        dest = remote_name.encode("utf-8")

        sock, ws = self._open_binary_ws(timeout=10.0)
        try:
            _send_req(ws, WEBREPL_PUT_FILE, total_size, dest)
            if _read_resp(ws) != 0:
                raise WirelessTransferError(f"WebREPL rejected upload for {remote_name}")

            sent = 0
            with open(local, "rb") as handle:
                while True:
                    chunk = handle.read(max(1024, CHUNK_SIZE))
                    if not chunk:
                        break
                    ws.write(chunk)
                    sent += len(chunk)
                    if callable(progress_cb):
                        progress_cb(sent, total_size)

            if callable(progress_cb):
                progress_cb(total_size, total_size)

            if _read_resp(ws) != 0:
                raise WirelessTransferError(f"WebREPL failed to finalize upload for {remote_name}")
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def delete_file(self, path):
        result = self.exec_script(
            "import os\n"
            "try:\n"
            "    os.remove({})\n"
            "    print('DELETED')\n"
            "except Exception as exc:\n"
            "    print('ERROR:' + str(exc))\n".format(repr(str(path))),
            timeout=4.0,
        )
        return "DELETED" in result

    def clean_all(self, log_func=None):
        result = self.exec_script(
            "import os\n"
            "def rmtree(path):\n"
            "    try:\n"
            "        for entry in os.ilistdir(path):\n"
            "            name = entry[0]\n"
            "            full = path + '/' + name if path else name\n"
            "            if entry[1] & 0x4000:\n"
            "                rmtree(full)\n"
            "                try:\n"
            "                    os.rmdir(full)\n"
            "                    print('DIR_DEL:' + full)\n"
            "                except Exception as exc:\n"
            "                    print('DIR_ERR:' + full + ' ' + str(exc))\n"
            "            else:\n"
            "                try:\n"
            "                    os.remove(full)\n"
            "                    print('FILE_DEL:' + full)\n"
            "                except Exception as exc:\n"
            "                    print('FILE_ERR:' + full + ' ' + str(exc))\n"
            "    except Exception as exc:\n"
            "        print('ERR:' + str(exc))\n"
            "print('CLEANUP_START')\n"
            "rmtree('')\n"
            "print('CLEANUP_DONE')\n",
            timeout=30.0,
        )
        if "CLEANUP_DONE" not in result:
            raise WirelessTransferError("Wireless cleanup did not complete")
        if callable(log_func):
            for line in result.splitlines():
                line = line.strip()
                if line.startswith("FILE_DEL:"):
                    log_func(f"  🗑️  {line.replace('FILE_DEL:', '').strip()}", "info")
                elif line.startswith("DIR_DEL:"):
                    log_func(f"  📁  {line.replace('DIR_DEL:', '').strip()}", "info")

    def reset_device(self, delay_ms=None):
        delay_ms = self.reset_delay_ms if delay_ms is None else int(delay_ms)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        try:
            self.exec_script("import machine\nmachine.reset()\n", timeout=2.0)
        except Exception:
            return True
        return True


class WirelessReplSession:
    def __init__(self, host: str, password: str, port: int = WIRELESS_DEFAULT_PORT):
        self.host = str(host or "").strip()
        self.password = str(password or "")
        self.port = int(port)
        self.sock = None
        self.ws = None

    def connect(self, timeout: float = 8.0):
        self.close()
        host, port = _parse_remote("{}:{}".format(self.host, self.port))
        sock = socket.socket()
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            _client_handshake(sock)
            ws = _WebSocket(sock)
            _login(ws, self.password)
            sock.settimeout(0.35)
            self.sock = sock
            self.ws = ws
            return _read_until_silence(ws, timeout=max(1.5, timeout), idle_s=0.22)
        except Exception as exc:
            try:
                sock.close()
            except Exception:
                pass
            raise _friendly_network_error(exc, host=host, port=port) from exc

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self.ws = None

    def is_connected(self):
        return self.sock is not None and self.ws is not None

    def send_text(self, text: str):
        if not self.is_connected():
            raise WirelessTransferError("Wireless REPL is not connected")
        try:
            self.ws.write(str(text).encode("utf-8"), WEBREPL_FRAME_TXT)
        except Exception as exc:
            self.close()
            raise WirelessTransferError("Wireless REPL disconnected while sending data") from exc

    def interrupt(self):
        self.send_text("\x03")

    def read_available(self, timeout: float = 0.25):
        if not self.is_connected():
            return ""
        previous_timeout = None
        try:
            previous_timeout = self.sock.gettimeout()
        except Exception:
            previous_timeout = None
        try:
            self.sock.settimeout(max(0.05, float(timeout)))
        except Exception:
            pass
        try:
            return _read_until_silence(self.ws, timeout=max(0.08, float(timeout)), idle_s=0.08)
        except WirelessTransferError:
            self.close()
            raise
        finally:
            if self.sock is not None and previous_timeout is not None:
                try:
                    self.sock.settimeout(previous_timeout)
                except Exception:
                    pass


def _read_until_prompt(ws, timeout: float = 6.0):
    end_time = time.monotonic() + max(0.5, float(timeout))
    chunks = []
    while time.monotonic() < end_time:
        try:
            token = ws.read(1, text_ok=True)
        except (socket.timeout, TimeoutError):
            continue
        except OSError:
            break
        if not token:
            break
        chunks.append(token)
        joined = b"".join(chunks)
        if joined.endswith(b">>> ") or joined.endswith(b"... "):
            break
    return b"".join(chunks).decode("utf-8", errors="ignore")


def _read_until_silence(ws, timeout: float = 1.0, idle_s: float = 0.12):
    end_time = time.monotonic() + max(0.2, float(timeout))
    last_data_at = None
    chunks = []

    while time.monotonic() < end_time:
        try:
            token = ws.read(1, text_ok=True)
        except (socket.timeout, TimeoutError):
            if chunks and last_data_at is not None and time.monotonic() - last_data_at >= idle_s:
                break
            continue
        except OSError as exc:
            if chunks:
                break
            raise WirelessTransferError("Wireless REPL disconnected") from exc

        if not token:
            if chunks:
                break
            raise WirelessTransferError("Wireless REPL disconnected")

        chunks.append(token)
        last_data_at = time.monotonic()
        joined = b"".join(chunks)
        if joined.endswith(b">>> ") or joined.endswith(b"... "):
            if idle_s <= 0:
                break

    return b"".join(chunks).decode("utf-8", errors="ignore")


def check_webrepl_available(host: str, port: int = WIRELESS_DEFAULT_PORT, timeout: float = 0.6):
    try:
        resolved_host, resolved_port = _parse_remote("{}:{}".format(host, port))
        with socket.create_connection((resolved_host, resolved_port), timeout=timeout):
            return True
    except Exception:
        return False


def launch_webrepl_client(host: str, port: int = WIRELESS_DEFAULT_PORT):
    html_path = Path(WEBREPL_CLIENT_HTML)
    if not html_path.exists():
        raise WirelessTransferError(f"WebREPL client HTML not found: {html_path}")
    resolved_host, resolved_port = _parse_remote("{}:{}".format(host, port))
    url = html_path.resolve().as_uri() + "#{}:{}".format(resolved_host, resolved_port)
    opened = webbrowser.open(url)
    if not opened:
        raise WirelessTransferError("Failed to open local WebREPL client in a browser")
    return url
