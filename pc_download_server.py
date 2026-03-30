import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def sanitize_export_name(name):
    raw = str(name or "").strip()
    cleaned = []
    for char in raw:
        if char.isalnum() or char in "._-":
            cleaned.append(char)
        elif char in (" ", "/"):
            cleaned.append("_")
    value = "".join(cleaned).strip("._-")
    return value[:48]


def default_export_name(path_value):
    try:
        candidate = Path(path_value).expanduser().resolve().name
    except Exception:
        candidate = str(path_value or "").strip()
    return sanitize_export_name(candidate) or "calsci_bundle"


def list_ipv4_addresses():
    addresses = []

    def remember(addr):
        if not addr or addr.startswith("127.") or addr in addresses:
            return
        addresses.append(addr)

    probe_socket = None
    try:
        probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe_socket.connect(("192.0.2.1", 80))
        remember(probe_socket.getsockname()[0])
    except Exception:
        pass
    finally:
        if probe_socket is not None:
            try:
                probe_socket.close()
            except Exception:
                pass

    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM)
        for info in infos:
            try:
                remember(info[4][0])
            except Exception:
                continue
    except Exception:
        pass

    if not addresses:
        addresses.append("127.0.0.1")
    return addresses


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def _is_blocked_relative_parts(parts):
    return any(str(part or "").strip() == ".git" for part in parts)


def _iter_export_files(root_path):
    root_path = Path(root_path)
    for current_root, dir_names, file_names in os.walk(root_path):
        dir_names[:] = [name for name in dir_names if name != ".git"]
        current_root_path = Path(current_root)
        for file_name in sorted(file_names):
            file_path = current_root_path / file_name
            try:
                relative_parts = file_path.relative_to(root_path).parts
            except Exception:
                continue
            if _is_blocked_relative_parts(relative_parts):
                continue
            yield file_path


class FolderExportServer:
    def __init__(self, log_func=None):
        self._log_func = log_func
        self._lock = threading.RLock()
        self._httpd = None
        self._thread = None
        self._root_path = None
        self._export_name = ""
        self._requested_port = 0

    @property
    def export_name(self):
        return self._export_name

    @property
    def root_path(self):
        return self._root_path

    @property
    def port(self):
        if self._httpd is None:
            return int(self._requested_port or 0)
        return int(self._httpd.server_address[1])

    def is_running(self):
        return self._httpd is not None

    def start(self, root_path, export_name, port):
        path_obj = Path(root_path).expanduser().resolve()
        if not path_obj.exists():
            raise ValueError("Selected PC folder does not exist")
        if not path_obj.is_dir():
            raise ValueError("Selected PC path is not a folder")

        alias = sanitize_export_name(export_name) or default_export_name(path_obj)
        try:
            port_number = int(port)
        except Exception as exc:
            raise ValueError("Port must be a number") from exc
        if port_number < 1 or port_number > 65535:
            raise ValueError("Port must be between 1 and 65535")

        with self._lock:
            self.stop(silent=True)
            self._root_path = path_obj
            self._export_name = alias
            self._requested_port = port_number
            self._httpd = _ReusableThreadingHTTPServer(("0.0.0.0", port_number), self._build_handler())
            self._httpd.daemon_threads = True
            self._thread = threading.Thread(
                target=self._httpd.serve_forever,
                name="CalSciFolderExportServer",
                daemon=True,
            )
            self._thread.start()

        self._log("PC folder server started: {} -> {}:{}".format(path_obj, alias, self.port))
        return {
            "export_name": alias,
            "port": self.port,
            "addresses": list_ipv4_addresses(),
            "root_path": str(path_obj),
        }

    def stop(self, silent=False):
        with self._lock:
            httpd = self._httpd
            thread = self._thread
            self._httpd = None
            self._thread = None

        if httpd is None:
            return

        try:
            httpd.shutdown()
        except Exception:
            pass
        try:
            httpd.server_close()
        except Exception:
            pass
        if thread is not None:
            thread.join(timeout=1.5)

        if not silent:
            self._log("PC folder server stopped")

    def status(self):
        addresses = list_ipv4_addresses()
        return {
            "running": self.is_running(),
            "root_path": str(self._root_path) if self._root_path else "",
            "export_name": self._export_name,
            "port": self.port,
            "addresses": addresses,
            "primary_address": addresses[0] if addresses else "",
        }

    def _log(self, message):
        if self._log_func is None:
            return
        try:
            self._log_func(message, "info")
        except Exception:
            pass

    def _current_root(self):
        if self._root_path is None:
            raise RuntimeError("Server folder is not configured")
        return self._root_path

    def _resolve_export(self, requested_name):
        current_name = self._export_name
        requested_name = str(requested_name or "").strip()
        if not current_name:
            raise FileNotFoundError("No folder export is active")
        if requested_name and requested_name != current_name:
            raise FileNotFoundError("Unknown folder name")
        return current_name

    def _manifest_payload(self, requested_name):
        export_name = self._resolve_export(requested_name)
        root_path = self._current_root()
        files = []
        total_bytes = 0

        for file_path in _iter_export_files(root_path):
            rel_path = file_path.relative_to(root_path).as_posix()
            size = int(file_path.stat().st_size)
            total_bytes += size
            files.append({"path": rel_path, "size": size})

        return {
            "folder_name": export_name,
            "file_count": len(files),
            "total_bytes": total_bytes,
            "files": files,
        }

    def _resolve_file_path(self, requested_name, relative_path):
        self._resolve_export(requested_name)
        root_path = self._current_root()
        rel_path = str(relative_path or "").replace("\\", "/").strip("/")
        if not rel_path:
            raise FileNotFoundError("Missing file path")
        parts = [part for part in rel_path.split("/") if part]
        if any(part in (".", "..") for part in parts):
            raise FileNotFoundError("Invalid file path")
        if _is_blocked_relative_parts(parts):
            raise FileNotFoundError("File not found")

        candidate = (root_path / Path(*parts)).resolve()
        candidate.relative_to(root_path)
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError("File not found")
        return candidate

    def _write_json(self, handler, payload, status=200):
        body = json.dumps(payload, indent=2).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)

    def _write_error(self, handler, status, message):
        self._write_json(handler, {"ok": False, "error": message}, status=status)

    def _build_handler(self):
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format_str, *args):
                return

            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                requested_name = query.get("folder", [""])[0]

                try:
                    if parsed.path == "/health":
                        status = parent.status()
                        payload = {
                            "ok": True,
                            "running": status["running"],
                            "folder_name": status["export_name"],
                            "port": status["port"],
                            "addresses": status["addresses"],
                        }
                        parent._write_json(self, payload)
                        return

                    if parsed.path == "/folders":
                        payload = parent._manifest_payload(requested_name="")
                        parent._write_json(
                            self,
                            {
                                "ok": True,
                                "folders": [
                                    {
                                        "name": payload["folder_name"],
                                        "file_count": payload["file_count"],
                                        "total_bytes": payload["total_bytes"],
                                    }
                                ],
                            },
                        )
                        return

                    if parsed.path == "/manifest":
                        payload = parent._manifest_payload(requested_name)
                        payload["ok"] = True
                        parent._write_json(self, payload)
                        return

                    if parsed.path == "/file":
                        rel_path = query.get("path", [""])[0]
                        file_path = parent._resolve_file_path(requested_name, rel_path)
                        size = int(file_path.stat().st_size)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/octet-stream")
                        self.send_header("Content-Length", str(size))
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        with file_path.open("rb") as handle:
                            while True:
                                chunk = handle.read(4096)
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                        return

                    parent._write_error(self, 404, "Unknown endpoint")
                except FileNotFoundError as exc:
                    parent._write_error(self, 404, str(exc))
                except ValueError as exc:
                    parent._write_error(self, 400, str(exc))
                except Exception as exc:
                    parent._write_error(self, 500, str(exc))

        return Handler
