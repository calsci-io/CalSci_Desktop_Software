"""
CalSci Hybrid Simulator
Raw virtual keypad input + real-chip display framebuffer mirror.
"""

import base64
import importlib.util
import json
import sys
import threading
import time
from collections import deque
from pathlib import Path

import serial
from PySide6.QtCore import QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

HYBRID_BAUDRATE = 115200
HYBRID_DEBOUNCE_MS = 35
SERIAL_WRITE_CHUNK = 256
SERIAL_WRITE_RETRIES = 2
STARTUP_SYNC_TIMEOUT_SEC = 2.5
PING_ECHO_TIMEOUT_SEC = 2.0
SYNC_FULL_RETRY_SEC = 0.35
KEY_ACK_TIMEOUT_FLOOR_SEC = 0.08
MAX_PENDING_KEYS = 1
HOLD_START_DELAY_FLOOR_MS = 220
HOLD_START_DELAY_FACTOR = 6

BIN_MAGIC = b"\xCA\x1C"
BIN_HEADER_LEN = 6
BIN_CRC_LEN = 2
BIN_PKT_FULL = 1
BIN_PKT_PATCH = 2
BIN_PKT_NAV = 3
BIN_PKT_LINES = 4
BIN_PKT_HEARTBEAT = 5


def _crc16_ccitt(data):
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

# Logical key labels by chip keymap modes (for button text only).
KEY_LAYOUT_DEFAULT = [
    ["on", "alpha", "beta", "home", "wifi"],
    ["backlight", "back", "toolbox", "diff()", "ln()"],
    ["nav_l", "nav_d", "nav_r", "ok", "nav_u"],
    ["module", "bluetooth", "sin()", "cos()", "tan()"],
    ["igtn()", "pi", "e", "summation", "fraction"],
    ["log", "pow(,)", "pow( ,0.5)", "pow( ,2)", "S_D"],
    ["7", "8", "9", "nav_b", "AC"],
    ["4", "5", "6", "*", "/"],
    ["1", "2", "3", "+", "-"],
    [".", "0", ",", "ans", "exe"],
]

KEY_LAYOUT_ALPHA = [
    ["on", "alpha", "beta", "home", "wifi"],
    ["backlight", "back", "caps", "f", "l"],
    ["nav_l", "nav_d", "nav_r", "ok", "nav_u"],
    ["a", "b", "c", "d", "e"],
    ["g", "h", "i", "j", "k"],
    ["m", "n", "o", "p", "q"],
    ["r", "s", "t", "nav_b", "AC"],
    ["u", "v", "w", "*", "/"],
    ["x", "y", "z", "+", "-"],
    [" ", "off", "tab", "ans", "exe"],
]

KEY_LAYOUT_BETA = [
    ["on", "alpha", "beta", "home", "wifi"],
    ["backlight", "back", "undo", "=", "$"],
    ["nav_l", "nav_d", "nav_r", "ok", "nav_u"],
    ["copy", "paste", "asin(", "acos(", "atan("],
    ["&", "`", '"', "'", "shot"],
    ["^", "~", "!", "<", ">"],
    ["[", "]", "%", "nav_b", "AC"],
    ["{", "}", ":", "*", "/"],
    ["(", ")", ";", "+", "-"],
    ["@", "?", '"', "ans", "exe"],
]

MODE_NAMES = {
    "d": "Default",
    "a": "Alpha",
    "b": "Beta",
    "A": "ALPHA",
}

# Row/col mapping to mirror calsci_simulator UI groups.
SYSTEM_GROUP_MAP = [
    [(0, 0), None, None],  # ON, RST, BT
    [(0, 1), (0, 2), (0, 3)],  # alpha, beta, home
    [(1, 1), (1, 0), (0, 4)],  # back, BL, wifi
]

NAV_GROUP_MAP = {
    (1, 1): (2, 3),  # OK
    (1, 0): (2, 4),  # up
    (1, 2): (2, 1),  # down
    (0, 1): (2, 0),  # left
    (2, 1): (2, 2),  # right
}

SECTION1_GROUP_MAP = [
    [(1, 2), (3, 0), (3, 1), (3, 2), (3, 3), (3, 4)],
    [(1, 3), (4, 0), (4, 1), (4, 2), (4, 3), (4, 4)],
    [(1, 4), (5, 0), (5, 1), (5, 2), (5, 3), (5, 4)],
]

SECTION2_GROUP_MAP = [
    [(6, 0), (6, 1), (6, 2), (6, 3), (6, 4)],
    [(7, 0), (7, 1), (7, 2), (7, 3), (7, 4)],
    [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4)],
    [(9, 0), (9, 1), (9, 2), (9, 3), (9, 4)],
]

DISPLAY_LABELS = {
    "on": "ON",
    "alpha": "a",
    "beta": "b",
    "home": "HOME",
    "wifi": "WIFI",
    "backlight": "BL",
    "back": "BACK",
    "toolbox": "TB",
    "diff()": "d/dx",
    "ln()": "ln",
    "nav_l": "<",
    "nav_d": "v",
    "nav_r": ">",
    "nav_u": "^",
    "ok": "OK",
    "module": "|x|",
    "bluetooth": "BT",
    "sin()": "sin",
    "cos()": "cos",
    "tan()": "tan",
    "igtn()": "int",
    "pi": "pi",
    "summation": "sum",
    "fraction": "a/b",
    "pow(,)": "x^y",
    "pow( ,0.5)": "sqrt",
    "pow( ,2)": "x^2",
    "S_D": "S<->D",
    "nav_b": "DEL",
    "ans": "ANS",
    "exe": "EXE",
    "caps": "caps",
    "undo": "undo",
    "copy": "copy",
    "paste": "paste",
    "asin(": "asin",
    "acos(": "acos",
    "atan(": "atan",
    "off": "off",
    "tab": "tab",
    "shot": "shot",
    " ": "SP",
}

# Protocol handlers are expected to be installed by device-side boot.py.


def _load_simulator_button_profile():
    """Load key layouts/symbols from calsci_simulator as source of truth."""
    sim_dir = Path(__file__).resolve().parent / "calsci_simulator"
    constants_path = sim_dir / "constants.py"
    keymap_path = sim_dir / "keymap.py"
    if not constants_path.exists() or not keymap_path.exists():
        return None

    const_mod = None
    keymap_mod = None
    old_constants = sys.modules.get("constants")

    try:
        spec_const = importlib.util.spec_from_file_location(
            "hybrid_sim_constants",
            str(constants_path),
        )
        if not spec_const or not spec_const.loader:
            return None
        const_mod = importlib.util.module_from_spec(spec_const)
        spec_const.loader.exec_module(const_mod)

        # keymap.py imports `constants`, so provide the loaded module under that name.
        sys.modules["constants"] = const_mod

        spec_keymap = importlib.util.spec_from_file_location(
            "hybrid_sim_keymap",
            str(keymap_path),
        )
        if not spec_keymap or not spec_keymap.loader:
            return None
        keymap_mod = importlib.util.module_from_spec(spec_keymap)
        spec_keymap.loader.exec_module(keymap_mod)

        Keypad = getattr(keymap_mod, "Keypad", None)
        KeypadMode = getattr(const_mod, "KeypadMode", None)
        KeyButtons = getattr(const_mod, "KeyButtons", None)
        if Keypad is None or KeypadMode is None or KeyButtons is None:
            return None

        keypad = Keypad()
        default_layout = keypad.states.get(KeypadMode.DEFAULT)
        alpha_layout = keypad.states.get(KeypadMode.ALPHA)
        beta_layout = keypad.states.get(KeypadMode.BETA)
        if not default_layout or not alpha_layout or not beta_layout:
            return None
        if len(default_layout) != 10 or any(len(row) != 5 for row in default_layout):
            return None

        all_keys = set()
        for layout in (default_layout, alpha_layout, beta_layout):
            for row in layout:
                for key in row:
                    all_keys.add(key)

        labels = {}
        for key in all_keys:
            try:
                label = str(KeyButtons.get_symbol(key))
            except Exception:
                label = str(key)
            labels[str(key)] = "SP" if str(key) == " " else label

        return {
            "default": [[str(v) for v in row] for row in default_layout],
            "alpha": [[str(v) for v in row] for row in alpha_layout],
            "beta": [[str(v) for v in row] for row in beta_layout],
            "labels": labels,
        }
    except Exception:
        return None
    finally:
        if old_constants is not None:
            sys.modules["constants"] = old_constants
        else:
            sys.modules.pop("constants", None)


_sim_profile = _load_simulator_button_profile()
if _sim_profile:
    KEY_LAYOUT_DEFAULT = _sim_profile["default"]
    KEY_LAYOUT_ALPHA = _sim_profile["alpha"]
    KEY_LAYOUT_BETA = _sim_profile["beta"]
    DISPLAY_LABELS.update(_sim_profile["labels"])


def display_label(key_value):
    return DISPLAY_LABELS.get(key_value, key_value)


class DisplayWidget(QWidget):
    """Render mirrored 128x64 framebuffer from real device."""

    def __init__(self, parent=None, size=QSize(460, 250), simulator_layout=False):
        super().__init__(parent)
        self.framebuffer = bytearray(1024)
        self.has_framebuffer = False
        self.nav_text = ""
        self.text_lines = []
        self.simulator_layout = simulator_layout
        self.setFixedSize(size)

    def paintEvent(self, event):
        painter = QPainter(self)
        bg = QColor(255, 255, 255) if self.simulator_layout else QColor(190, 214, 224)
        painter.fillRect(self.rect(), bg)
        if not self.simulator_layout:
            painter.setPen(QPen(QColor(26, 30, 36), 2))
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        has_pixels = any(self.framebuffer)
        if self.has_framebuffer:
            pad = 0 if self.simulator_layout else 10
            avail_w = max(1, self.width() - (pad * 2))
            avail_h = max(1, self.height() - (pad * 2))
            pixel_size = max(1, min(avail_w // 128, avail_h // 64))
            draw_w = 128 * pixel_size
            draw_h = 64 * pixel_size
            off_x = (self.width() - draw_w) // 2
            off_y = (self.height() - draw_h) // 2
            black = QColor(16, 24, 30)

            if has_pixels:
                for page in range(8):
                    base = page * 128
                    for col in range(128):
                        data = self.framebuffer[base + col]
                        if data == 0:
                            continue
                        for bit in range(8):
                            if data & (1 << bit):
                                y = (page * 8) + bit
                                painter.fillRect(
                                    off_x + (col * pixel_size),
                                    off_y + (y * pixel_size),
                                    pixel_size,
                                    pixel_size,
                                    black,
                                )
            return

        if self.text_lines:
            painter.setPen(QColor(16, 24, 30))
            painter.setFont(QFont("DejaVu Sans Mono", 12 if self.simulator_layout else 14))
            line_h = 24 if self.simulator_layout else 28
            y = 8 if self.simulator_layout else 14
            for line in self.text_lines[:7]:
                painter.drawText(
                    8 if self.simulator_layout else 14,
                    y,
                    self.width() - (16 if self.simulator_layout else 28),
                    line_h,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    str(line)[:28],
                )
                y += line_h
            return

        # Fallback if no framebuffer received yet.
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(14, self.height() - 24, self.width() - 14, self.height() - 24)
        if self.nav_text:
            painter.setPen(QColor(0, 0, 0))
            painter.setFont(QFont("DejaVu Sans Mono", 10))
            painter.drawText(
                14,
                self.height() - 23,
                self.width() - 28,
                20,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.nav_text,
            )


class MatrixKeyButton(QPushButton):
    """Main-key renderer with top-left alpha, top-right beta, and main bottom label."""

    def __init__(self, main_text, alpha_text="", beta_text="", parent=None):
        super().__init__("", parent)
        self.main_text = str(main_text)
        self.alpha_text = str(alpha_text) if alpha_text else ""
        self.beta_text = str(beta_text) if beta_text else ""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)

        mode_active = bool(self.property("modeActive"))
        mapped = bool(self.property("mapped"))
        pressed = self.isDown()
        hold_active = bool(self.property("holdActive"))
        depressed = pressed or hold_active
        enabled = self.isEnabled() and mapped

        base = QColor(255, 255, 255)
        top_hi = QColor(255, 255, 255)
        low_fill = QColor(236, 236, 236)
        border = QColor(92, 92, 92)
        shadow = QColor(150, 150, 150)
        text = QColor(17, 17, 17)

        if not enabled:
            base = QColor(241, 241, 241)
            top_hi = QColor(247, 247, 247)
            low_fill = QColor(236, 236, 236)
            border = QColor(140, 140, 140)
            shadow = QColor(180, 180, 180)
            text = QColor(94, 94, 94)
        elif mode_active:
            base = QColor(244, 244, 244)
            top_hi = QColor(252, 252, 252)
            low_fill = QColor(226, 226, 226)
            border = QColor(111, 111, 111)
            shadow = QColor(130, 130, 130)
        if depressed:
            base = QColor(224, 224, 224)
            top_hi = QColor(232, 232, 232)
            low_fill = QColor(214, 214, 214)
            shadow = QColor(160, 160, 160)

        shadow_offset = 0 if depressed else 2
        face_rect = rect.adjusted(0, 0, 0, -shadow_offset)
        if shadow_offset > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow)
            painter.drawRoundedRect(face_rect.translated(0, shadow_offset), 8, 8)

        painter.setPen(QPen(border, 2 if mode_active or hold_active else 1))
        painter.setBrush(QColor(low_fill))
        painter.drawRoundedRect(face_rect, 8, 8)
        top_band = face_rect.adjusted(1, 1, -1, -face_rect.height() // 2)
        painter.fillRect(top_band, top_hi)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawLine(face_rect.left() + 3, face_rect.top() + 2, face_rect.right() - 3, face_rect.top() + 2)

        painter.setPen(text)
        pad = 4
        y_shift = 1 if depressed else 0

        small_font = QFont("DejaVu Sans", 7)
        if self.alpha_text:
            painter.setFont(small_font)
            painter.drawText(
                QRect(pad, 2 + y_shift, (self.width() // 2) - pad, (self.height() // 2)),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                self.alpha_text,
            )
        if self.beta_text:
            painter.setFont(small_font)
            painter.drawText(
                QRect(self.width() // 2, 2 + y_shift, (self.width() // 2) - pad, (self.height() // 2)),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                self.beta_text,
            )

        main_size = 11
        main_font = QFont("DejaVu Sans Mono", main_size)
        main_font.setBold(True)
        fm = QFontMetrics(main_font)
        while main_size > 7 and fm.horizontalAdvance(self.main_text) > (self.width() - 8):
            main_size -= 1
            main_font = QFont("DejaVu Sans Mono", main_size)
            main_font.setBold(True)
            fm = QFontMetrics(main_font)

        painter.setFont(main_font)
        painter.drawText(
            QRect(2, y_shift, self.width() - 4, self.height() - 4),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            self.main_text,
        )


class SerialReaderThread(QThread):
    """Read device serial output and emit parsed state updates."""

    state_received = Signal(dict)
    error_occurred = Signal(str)
    raw_line = Signal(str)

    def __init__(self, ser):
        super().__init__()
        self.ser = ser
        self.running = True
        self._rx_buffer = bytearray()
        self._max_buffer = 65536
        self._last_state_emit_ts = 0.0
        self._min_state_emit_sec = 0.001

    def _emit_state(self, state, high_priority=False):
        now = time.perf_counter()
        if not high_priority and (now - self._last_state_emit_ts) < self._min_state_emit_sec:
            return
        self._last_state_emit_ts = now
        self.state_received.emit(state)

    def _process_text_line(self, line):
        text = line.strip()
        if not text:
            return

        found_state = False
        scan = 0
        while True:
            state_pos = text.find("STATE:", scan)
            if state_pos < 0:
                break
            left = text.find("{", state_pos)
            if left < 0:
                break
            depth = 0
            right = -1
            for idx in range(left, len(text)):
                ch = text[idx]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        right = idx
                        break
            if right < 0:
                break
            payload = text[left : right + 1]
            try:
                state = json.loads(payload)
                now = time.perf_counter()
                emit_allowed = (now - self._last_state_emit_ts) >= self._min_state_emit_sec
                if not emit_allowed:
                    # Keep high-importance display deltas flowing.
                    if state.get("fb_full") or state.get("fb") or state.get("patches"):
                        emit_allowed = True
                    elif "lines" in state or "nav" in state:
                        emit_allowed = True
                if emit_allowed:
                    self._last_state_emit_ts = now
                    self._emit_state(state, high_priority=True)
                    found_state = True
            except Exception:
                self.raw_line.emit("Malformed STATE payload")
            scan = right + 1

        if not found_state:
            self.raw_line.emit(text)

    def _process_binary_packet(self, pkt_type, flags, payload):
        fb_seen = bool(flags & 0x01)
        fb_seq = (int(flags) >> 1) & 0x7F

        if pkt_type == BIN_PKT_FULL:
            if len(payload) >= 1024:
                self._emit_state(
                    {
                        "fb_raw": payload[:1024],
                        "fb_full": True,
                        "fb_seen": fb_seen,
                        "fb_seq": fb_seq,
                    },
                    high_priority=True,
                )
            return

        if pkt_type == BIN_PKT_PATCH:
            if len(payload) < 4:
                return
            page = int(payload[0])
            col = int(payload[1])
            width = int(payload[2])
            pages = int(payload[3])
            if width <= 0 or pages <= 0:
                return
            if page > 7 or col > 127:
                return
            if (page + pages) > 8 or (col + width) > 128:
                return
            needed = width * pages
            data = payload[4:]
            if len(data) < needed:
                return
            self._emit_state(
                {
                    "patches_raw": [(page, col, width, pages, data[:needed])],
                    "fb_seen": fb_seen,
                    "fb_seq": fb_seq,
                },
                high_priority=True,
            )
            return

        if pkt_type == BIN_PKT_NAV:
            try:
                nav = payload.decode("utf-8", errors="ignore")
            except Exception:
                nav = ""
            self._emit_state({"nav": nav}, high_priority=False)
            return

        if pkt_type == BIN_PKT_LINES:
            lines = []
            if payload:
                count = int(payload[0])
                pos = 1
                for _ in range(count):
                    if pos >= len(payload):
                        break
                    ln = int(payload[pos])
                    pos += 1
                    if ln < 0 or (pos + ln) > len(payload):
                        break
                    raw = payload[pos : pos + ln]
                    pos += ln
                    try:
                        lines.append(raw.decode("utf-8", errors="ignore"))
                    except Exception:
                        lines.append("")
            self._emit_state({"lines": lines}, high_priority=False)
            return

        if pkt_type == BIN_PKT_HEARTBEAT:
            self._emit_state({"fb_seen": fb_seen}, high_priority=False)
            return

    def _process_rx_buffer(self):
        while self.running:
            if not self._rx_buffer:
                return

            nl = self._rx_buffer.find(b"\n")
            magic = self._rx_buffer.find(BIN_MAGIC)

            if magic < 0:
                if nl < 0:
                    if len(self._rx_buffer) > self._max_buffer:
                        del self._rx_buffer[:-self._max_buffer]
                    return
                line = bytes(self._rx_buffer[:nl])
                del self._rx_buffer[: nl + 1]
                self._process_text_line(line.decode("utf-8", errors="ignore"))
                continue

            if nl >= 0 and nl < magic:
                line = bytes(self._rx_buffer[:nl])
                del self._rx_buffer[: nl + 1]
                self._process_text_line(line.decode("utf-8", errors="ignore"))
                continue

            if magic > 0:
                prefix = bytes(self._rx_buffer[:magic])
                del self._rx_buffer[:magic]
                if prefix:
                    for frag in prefix.split(b"\n"):
                        text = frag.decode("utf-8", errors="ignore").strip()
                        if text:
                            self.raw_line.emit(text)
                continue

            if len(self._rx_buffer) < (BIN_HEADER_LEN + BIN_CRC_LEN):
                return

            plen = int(self._rx_buffer[4]) | (int(self._rx_buffer[5]) << 8)
            if plen > 4096:
                del self._rx_buffer[0]
                continue

            frame_len = BIN_HEADER_LEN + plen + BIN_CRC_LEN
            if len(self._rx_buffer) < frame_len:
                return

            crc_calc = _crc16_ccitt(bytes(self._rx_buffer[2 : 6 + plen]))
            crc_recv = int(self._rx_buffer[6 + plen]) | (int(self._rx_buffer[7 + plen]) << 8)
            if crc_calc != crc_recv:
                del self._rx_buffer[0]
                continue

            pkt_type = int(self._rx_buffer[2])
            flags = int(self._rx_buffer[3])
            payload = bytes(self._rx_buffer[6 : 6 + plen])
            del self._rx_buffer[:frame_len]
            self._process_binary_packet(pkt_type, flags, payload)

    def run(self):
        try:
            while self.running:
                if not self.ser or not self.ser.is_open:
                    time.sleep(0.05)
                    continue
                try:
                    waiting = 0
                    try:
                        waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
                    except Exception:
                        waiting = 0

                    chunk = self.ser.read(waiting if waiting > 0 else 1)
                    if not chunk:
                        continue

                    self._rx_buffer.extend(chunk)
                    if len(self._rx_buffer) > self._max_buffer:
                        del self._rx_buffer[:-self._max_buffer]
                    self._process_rx_buffer()
                except Exception:
                    if self.running:
                        time.sleep(0.03)
        except Exception as exc:
            self.error_occurred.emit(f"Serial reader error: {exc}")

    def stop(self):
        self.running = False


class HybridSimulatorWindow(QMainWindow):
    """Raw keypad passthrough + real display mirror."""

    def __init__(self, port):
        super().__init__()
        self.port = port
        self.ser = None
        self.reader_thread = None
        self._write_lock = threading.Lock()
        self.connected = False
        # Hybrid simulator uses direct line protocol only (no REPL fallback).
        self.transport_mode = "line"
        self._last_state_apply_ts = 0.0
        self._min_state_apply_sec = 0.001
        self._have_full_frame = False
        self._last_fb_seq = None
        self._last_sync_full_request_ts = 0.0
        self._effective_debounce_ms = int(HYBRID_DEBOUNCE_MS)
        self._device_graph_fast_ms = None
        self._key_ack_timeout_sec = KEY_ACK_TIMEOUT_FLOOR_SEC
        self._pending_keys = deque()
        self._key_in_flight = None
        self._hold_repeat_active = False
        self._hold_timer = QTimer(self)
        self._hold_timer.setInterval(max(1, int(self._effective_debounce_ms)))
        self._hold_timer.timeout.connect(self._emit_held_key)
        self._key_ack_timer = QTimer(self)
        self._key_ack_timer.setSingleShot(True)
        self._key_ack_timer.timeout.connect(self._on_key_ack_timeout)
        self._configure_input_timing(self._effective_debounce_ms)
        self._held_key = None
        self._held_button = None
        self.current_mode = "d"
        self.buttons = {}

        self.setWindowTitle("CalSci Hybrid Simulator")
        self.setMinimumSize(QSize(470, 990))
        self._build_ui()
        self._setup_device()

    def _build_ui(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f7f7f7;
            }
            QLabel#modeLabel {
                color: #333333;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#statusLabel {
                color: #555555;
                font-size: 11px;
            }
            QWidget#shellWidget {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:0.55 #f2f2f2, stop:1 #e4e4e4);
                border: 2px solid #a1a1a1;
                border-radius: 32px;
            }
            QWidget#displayBezel {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #e9e9e9);
                border: 2px solid #939393;
                border-radius: 14px;
            }
            QLabel#brandLabel {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #ececec);
                color: #1a1a1a;
                border: 1px solid #8e8e8e;
                border-radius: 6px;
                font-family: "DejaVu Sans";
                font-size: 16px;
                font-weight: 500;
            }
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:0.6 #f2f2f2, stop:1 #e2e2e2);
                color: #111111;
                border: 1px solid #5c5c5c;
                border-bottom: 2px solid #474747;
                border-radius: 8px;
                padding: 0px 0px 1px 0px;
                font-family: "DejaVu Sans";
                font-size: 15px;
                font-weight: 600;
                text-align: center;
            }
            QPushButton[mainKey="true"] {
                font-family: "DejaVu Sans Mono";
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton[shape="circle"] {
                border-radius: 20px;
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e4e4e4, stop:1 #d2d2d2);
                border-bottom: 1px solid #4a4a4a;
                padding: 1px 0px 0px 1px;
            }
            QPushButton[holdActive="true"] {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e4e4e4, stop:1 #d2d2d2);
                border-bottom: 1px solid #4a4a4a;
                padding: 1px 0px 0px 1px;
            }
            QPushButton[modeActive="true"] {
                background-color: #ececec;
                border: 2px solid #6f6f6f;
            }
            QPushButton[mapped="false"] {
                background-color: #f1f1f1;
                color: #5e5e5e;
            }
            """
        )

        self.setMinimumSize(QSize(470, 990))
        self.setMaximumSize(QSize(470, 990))
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 6)
        root_layout.setSpacing(6)

        shell = QWidget()
        shell.setObjectName("shellWidget")
        shell.setFixedSize(QSize(450, 950))
        self._build_simulator_shell(shell)
        root_layout.addWidget(shell, alignment=Qt.AlignmentFlag.AlignHCenter)

        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.mode_label = QLabel("Mode: Default")
        self.mode_label.setObjectName("modeLabel")
        footer.addWidget(self.mode_label)

        self.status_label = QLabel("Initializing...")
        self.status_label.setObjectName("statusLabel")
        footer.addWidget(self.status_label, stretch=1)

        root_layout.addLayout(footer)
        self.setCentralWidget(root)
        self._refresh_mode_indicator()

    def _build_simulator_shell(self, shell):
        self.buttons = {}

        # Geometry mirrors calsci_simulator constants.
        shell_w = 450
        display_x = 33
        display_y = 85
        display_w = 384
        display_h = 192
        bezel_pad = 16
        top_start = display_y + display_h + (bezel_pad * 2) + 14
        left_margin = display_x

        brand = QLabel("CalSci", shell)
        brand.setObjectName("brandLabel")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setGeometry((shell_w - 90) // 2, 18, 90, 26)

        bezel = QWidget(shell)
        bezel.setObjectName("displayBezel")
        bezel.setGeometry(display_x - bezel_pad, display_y - bezel_pad, display_w + (2 * bezel_pad), display_h + (2 * bezel_pad))

        self.display_widget = DisplayWidget(shell, size=QSize(display_w, display_h), simulator_layout=True)
        self.display_widget.move(display_x, display_y)
        self.display_widget.raise_()

        system_key = 40
        system_gap_x = 12
        system_gap_y = 8
        system_rows = [
            [("on", True, None, None, "rect"), ("RST", False, None, None, "circle"), ("Boot", False, None, None, "circle")],
            [("alpha", True, 0, 1, "rect"), ("beta", True, 0, 2, "rect"), ("home", True, 0, 3, "rect")],
            [("back", True, 1, 1, "rect"), ("backlight", True, 1, 0, "rect"), ("wifi", True, 0, 4, "rect")],
        ]
        for r, row_vals in enumerate(system_rows):
            y = top_start + r * (system_key + system_gap_y)
            for c, (label_key, mapped, row, col, shape) in enumerate(row_vals):
                x = left_margin + c * (system_key + system_gap_x)
                txt = str(display_label(label_key)) if mapped else str(label_key)
                self._add_shell_button(shell, txt, x, y, system_key, system_key, mapped, row, col, shape=shape, main_key=False)

        nav_ok = 50
        nav_lr_w = 50
        nav_lr_h = 50
        nav_gap = 4
        nav_ud_w = 50
        nav_ud_h = 50
        nav_offset_x = -6
        nav_offset_y = -2

        system_width = (3 * system_key) + (2 * system_gap_x)
        nav_width = nav_lr_w + nav_gap + nav_ok + nav_gap + nav_lr_w
        nav_height = nav_ud_h + nav_gap + nav_ok + nav_gap + nav_ud_h
        top_gap = max(384 - system_width - nav_width, system_gap_x)
        nav_left = left_margin + system_width + top_gap + nav_offset_x
        system_block_h = (3 * system_key) + (2 * system_gap_y)
        nav_top = top_start + ((system_block_h - nav_height) // 2) + nav_offset_y
        nav_ok_x = nav_left + nav_lr_w + nav_gap
        nav_ok_y = nav_top + nav_ud_h + nav_gap
        nav_ud_x = nav_left + ((nav_width - nav_ud_w) // 2)
        nav_lr_y = nav_ok_y + ((nav_ok - nav_lr_h) // 2)

        self._add_shell_button(shell, str(display_label("ok")), nav_ok_x, nav_ok_y, nav_ok, nav_ok, True, 2, 3, shape="rect", main_key=False)
        self._add_shell_button(shell, str(display_label("nav_u")), nav_ud_x, nav_top, nav_ud_w, nav_ud_h, True, 2, 4, shape="rect", main_key=False)
        self._add_shell_button(shell, str(display_label("nav_d")), nav_ud_x, nav_ok_y + nav_ok + nav_gap, nav_ud_w, nav_ud_h, True, 2, 1, shape="rect", main_key=False)
        self._add_shell_button(shell, str(display_label("nav_l")), nav_left, nav_lr_y, nav_lr_w, nav_lr_h, True, 2, 0, shape="rect", main_key=False)
        self._add_shell_button(shell, str(display_label("nav_r")), nav_left + nav_lr_w + nav_gap + nav_ok + nav_gap, nav_lr_y, nav_lr_w, nav_lr_h, True, 2, 2, shape="rect", main_key=False)

        main_key = 50
        main_gap_y = 16
        section_1_gap_x = max(int((384 - (6 * main_key)) / 5), 5)
        section_1_y_start = top_start + system_block_h + 12
        for r, row_coords in enumerate(SECTION1_GROUP_MAP):
            y = section_1_y_start + (r * (main_key + main_gap_y))
            for c, (row, col) in enumerate(row_coords):
                x = left_margin + (c * (main_key + section_1_gap_x))
                btn = self._make_matrix_button(row, col, QSize(main_key, main_key), parent=shell, main_key=True)
                btn.move(x, y)

        section_2_y_start = section_1_y_start + int(3.0 * (main_key + main_gap_y))
        section_2_gap_x = max(int((384 - (5 * main_key)) / 4), 25)
        for r, row_coords in enumerate(SECTION2_GROUP_MAP):
            y = section_2_y_start + (r * (main_key + main_gap_y))
            for c, (row, col) in enumerate(row_coords):
                x = left_margin + (c * (main_key + section_2_gap_x))
                btn = self._make_matrix_button(row, col, QSize(main_key, main_key), parent=shell, main_key=True)
                btn.move(x, y)

    def _add_shell_button(self, parent, label, x, y, w, h, mapped, row, col, shape="rect", main_key=False):
        btn = QPushButton(str(label), parent)
        btn.setFixedSize(QSize(w, h))
        btn.move(x, y)
        btn.setProperty("modeActive", False)
        btn.setProperty("mapped", bool(mapped))
        btn.setProperty("shape", "circle" if shape == "circle" else "rect")
        btn.setProperty("mainKey", bool(main_key))
        if mapped and row is not None and col is not None:
            self._attach_key_button(btn, row, col)
        else:
            btn.setEnabled(False)
        return btn

    def _attach_key_button(self, button, row, col):
        button.setProperty("keyRow", int(row))
        button.setProperty("keyCol", int(col))
        button.setProperty("holdActive", False)
        button.pressed.connect(lambda rr=row, cc=col, btn=button: self._on_button_pressed(rr, cc, btn))
        button.released.connect(lambda btn=button: self._on_button_released(btn))
        self.buttons[(row, col)] = button

    def _build_top_group(self):
        top = QHBoxLayout()
        top.setSpacing(14)

        system_grid = QGridLayout()
        system_grid.setHorizontalSpacing(8)
        system_grid.setVerticalSpacing(8)

        system_labels = [
            [("ON", True), ("RST", False), ("BT", False)],
            [("a", True), ("b", True), ("HOME", True)],
            [("BACK", True), ("BL", True), ("WIFI", True)],
        ]

        for r in range(3):
            for c in range(3):
                label, mapped = system_labels[r][c]
                matrix_rc = SYSTEM_GROUP_MAP[r][c]
                button = QPushButton(label)
                button.setMinimumSize(QSize(88, 58))
                button.setProperty("modeActive", False)
                button.setProperty("mapped", mapped)
                if mapped and matrix_rc is not None:
                    row, col = matrix_rc
                    button.clicked.connect(
                        lambda checked=False, rr=row, cc=col: self._on_key_pressed(rr, cc)
                    )
                    self.buttons[(row, col)] = button
                else:
                    button.setEnabled(False)
                system_grid.addWidget(button, r, c)

        top.addLayout(system_grid)

        nav_grid = QGridLayout()
        nav_grid.setHorizontalSpacing(6)
        nav_grid.setVerticalSpacing(6)
        nav_map = {
            (1, 1): "OK",
            (1, 0): "^",
            (1, 2): "v",
            (0, 1): "<",
            (2, 1): ">",
        }
        for r in range(3):
            for c in range(3):
                text = nav_map.get((c, r), "")
                btn = QPushButton(text)
                btn.setMinimumSize(QSize(72, 58))
                btn.setProperty("modeActive", False)
                if (c, r) in NAV_GROUP_MAP:
                    row, col = NAV_GROUP_MAP[(c, r)]
                    btn.setProperty("mapped", True)
                    btn.clicked.connect(
                        lambda checked=False, rr=row, cc=col: self._on_key_pressed(rr, cc)
                    )
                    self.buttons[(row, col)] = btn
                else:
                    btn.setProperty("mapped", False)
                    btn.setEnabled(False)
                nav_grid.addWidget(btn, r, c)

        top.addLayout(nav_grid)
        top.addStretch(1)
        return top

    def _build_main_group(self):
        main = QVBoxLayout()
        main.setSpacing(8)

        section1 = QGridLayout()
        section1.setHorizontalSpacing(8)
        section1.setVerticalSpacing(8)
        for r, row_coords in enumerate(SECTION1_GROUP_MAP):
            for c, (row, col) in enumerate(row_coords):
                section1.addWidget(self._make_matrix_button(row, col, QSize(94, 62)), r, c)
        main.addLayout(section1)

        section2 = QGridLayout()
        section2.setHorizontalSpacing(10)
        section2.setVerticalSpacing(8)
        for r, row_coords in enumerate(SECTION2_GROUP_MAP):
            for c, (row, col) in enumerate(row_coords):
                section2.addWidget(self._make_matrix_button(row, col, QSize(110, 62)), r, c)
        main.addLayout(section2)
        return main

    def _make_matrix_button(self, row, col, size, parent=None, main_key=False):
        default_key = KEY_LAYOUT_DEFAULT[row][col]
        alpha_key = KEY_LAYOUT_ALPHA[row][col]
        beta_key = KEY_LAYOUT_BETA[row][col]
        main_label = str(display_label(default_key))
        alpha_label = self._corner_label(alpha_key, default_key)
        beta_label = self._corner_label(beta_key, default_key)

        button = MatrixKeyButton(main_label, alpha_label, beta_label, parent)
        button.setFixedSize(size)
        button.setProperty("modeActive", False)
        button.setProperty("mapped", True)
        button.setProperty("shape", "rect")
        button.setProperty("mainKey", bool(main_key))
        self._attach_key_button(button, row, col)
        return button

    def _format_key_caption(self, default_key, alpha_key, beta_key):
        main = display_label(default_key)
        alpha = self._corner_label(alpha_key, default_key)
        beta = self._corner_label(beta_key, default_key)
        if alpha or beta:
            return f"{alpha:<5}{beta:>5}\n{main}"
        return str(main)

    def _corner_label(self, alt_key, default_key):
        if alt_key == default_key:
            return ""
        if alt_key in {
            "on",
            "alpha",
            "beta",
            "home",
            "wifi",
            "backlight",
            "back",
            "nav_l",
            "nav_d",
            "nav_r",
            "nav_u",
            "ok",
            "nav_b",
            "AC",
            "ans",
            "exe",
        }:
            return ""
        lbl = str(display_label(alt_key))
        if len(lbl) > 5:
            return lbl[:5]
        return lbl

    def _layout_for_mode(self, mode):
        if mode in ("a", "A"):
            return KEY_LAYOUT_ALPHA
        if mode == "b":
            return KEY_LAYOUT_BETA
        return KEY_LAYOUT_DEFAULT

    def _key_value_for(self, row, col, mode=None):
        active_mode = self.current_mode if mode is None else mode
        layout = self._layout_for_mode(active_mode)
        return layout[row][col]

    def _apply_mode_hint_after_press(self, key_value):
        key = str(key_value)
        if key == "alpha":
            self.current_mode = "d" if self.current_mode in ("a", "A") else "a"
            self._refresh_mode_indicator()
            return
        if key == "beta":
            self.current_mode = "d" if self.current_mode == "b" else "b"
            self._refresh_mode_indicator()
            return
        if key == "caps" and self.current_mode in ("a", "A"):
            self.current_mode = "a" if self.current_mode == "A" else "A"
            self._refresh_mode_indicator()

    def _set_button_hold_state(self, button, active):
        if button is None:
            return
        button.setProperty("holdActive", bool(active))
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _stop_held_key(self):
        if self._hold_timer.isActive():
            self._hold_timer.stop()
        self._hold_repeat_active = False
        if self._held_button is not None:
            self._set_button_hold_state(self._held_button, False)
        self._held_key = None
        self._held_button = None
        if self._pending_keys:
            self._pending_keys = deque(item for item in self._pending_keys if not item[2])

    def _configure_input_timing(self, debounce_ms=None):
        value = self._effective_debounce_ms
        if debounce_ms is not None:
            try:
                value = int(round(float(debounce_ms)))
            except Exception:
                value = self._effective_debounce_ms
        if value < 1:
            value = 1
        self._effective_debounce_ms = value
        if self._hold_repeat_active:
            self._hold_timer.setInterval(value)
        scaled_timeout = (value * 3.0) / 1000.0
        self._key_ack_timeout_sec = max(KEY_ACK_TIMEOUT_FLOOR_SEC, min(0.35, scaled_timeout))

    def _on_button_pressed(self, row, col, button):
        if self._held_button is not None and self._held_button is not button:
            self._stop_held_key()
        self._held_key = (row, col)
        self._held_button = button
        self._hold_repeat_active = False
        self._set_button_hold_state(button, True)
        self._on_key_pressed(row, col, from_hold=False)
        if self.connected and self.ser and self.ser.is_open:
            first_repeat_ms = max(
                HOLD_START_DELAY_FLOOR_MS,
                int(self._effective_debounce_ms * HOLD_START_DELAY_FACTOR),
            )
            self._hold_timer.setInterval(first_repeat_ms)
            self._hold_timer.start()

    def _on_button_released(self, button):
        if self._held_button is button:
            self._stop_held_key()

    def _emit_held_key(self):
        if self._held_key is None:
            self._stop_held_key()
            return
        row, col = self._held_key
        self._on_key_pressed(row, col, from_hold=True)
        if not self._hold_repeat_active:
            self._hold_repeat_active = True
            self._hold_timer.setInterval(max(1, int(self._effective_debounce_ms)))

    def _setup_device(self):
        try:
            self.status_label.setText(f"Connecting to {self.port}...")
            self.ser = self._open_serial_port(self.port)

            self.status_label.setText("Syncing with device bridge...")
            sync = self._sync_startup_markers(timeout=STARTUP_SYNC_TIMEOUT_SEC)
            if sync.get("bridge_err"):
                raise RuntimeError(sync["bridge_err"])

            # Test message (step validation): PING -> ECHO (or at least echoed input)
            token = f"PC_HELLO_{int(time.time() * 1000)}"
            self.status_label.setText("Testing serial link (PING/ECHO)...")
            self._send_line(f"PING:{token}")
            marker = self._wait_for_any_markers(
                [f"ECHO:{token}", f"PING:{token}"], timeout=PING_ECHO_TIMEOUT_SEC
            )
            echo_ok = marker == f"ECHO:{token}"
            link_ok = marker is not None
            self.transport_mode = "line"

            device_debounce_ms = sync.get("key_debounce_ms", None)
            self._device_graph_fast_ms = sync.get("graph_fast_ms", None)
            self._configure_input_timing(device_debounce_ms)

            self.status_label.setText("Starting live serial stream...")
            self.reader_thread = SerialReaderThread(self.ser)
            self.reader_thread.state_received.connect(self._on_state_received)
            self.reader_thread.error_occurred.connect(self._on_serial_error)
            self.reader_thread.raw_line.connect(self._on_raw_line)
            self.reader_thread.start()

            # Ensure desktop gets a deterministic baseline frame for binary patch mode.
            self._request_full_frame(force=True)

            self.connected = True
            timing_note = f", sync {self._effective_debounce_ms}ms"
            if echo_ok and sync.get("ready_seen"):
                self.status_label.setText(f"Connected on {self.port} (echo OK{timing_note})")
            elif echo_ok:
                self.status_label.setText(
                    f"Connected on {self.port} (echo OK, waiting STATE{timing_note})"
                )
            elif link_ok:
                self.status_label.setText(
                    f"Connected on {self.port} (serial OK, bridge response pending{timing_note})"
                )
            else:
                self.status_label.setText(
                    f"Connected on {self.port} (waiting bridge response{timing_note})"
                )
        except Exception as exc:
            self.connected = False
            msg = self._friendly_setup_error(exc)
            self.status_label.setText(msg)
            QMessageBox.critical(self, "Hybrid Simulator Error", msg)

    def _open_serial_port(self, port):
        kwargs = {
            "port": port,
            "baudrate": HYBRID_BAUDRATE,
            "timeout": 0.001,
            "write_timeout": 0.25,
        }
        try:
            return serial.Serial(exclusive=False, **kwargs)
        except TypeError:
            return serial.Serial(**kwargs)

    def _friendly_setup_error(self, exc):
        raw = str(exc)
        lower = raw.lower()
        if "permission denied" in lower:
            return (
                f"Cannot access {self.port} (permission denied or busy). "
                "Close any app using the port and reconnect device."
            )
        if "could not open port" in lower:
            return f"Could not open {self.port}. Check cable/port and retry."
        if "hybrid_bridge_err" in lower:
            return f"Device bridge error: {raw}"
        if "write timeout" in lower:
            return "Serial write timeout during setup. Reconnect device and retry."
        return f"Hybrid setup failed: {raw}"

    def _serial_write_bytes(self, data, flush=False, retries=SERIAL_WRITE_RETRIES):
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial port is not open")

        if not data:
            return

        last_exc = None
        for attempt in range(retries + 1):
            try:
                with self._write_lock:
                    sent = 0
                    mv = memoryview(data)
                    total = len(data)
                    stall_count = 0
                    while sent < total:
                        end = min(sent + SERIAL_WRITE_CHUNK, total)
                        wrote = self.ser.write(mv[sent:end])
                        if wrote is None:
                            wrote = 0
                        if wrote <= 0:
                            stall_count += 1
                            if stall_count >= 5:
                                raise serial.SerialTimeoutException("Serial write stalled")
                            time.sleep(0.01)
                            continue
                        stall_count = 0
                        sent += wrote
                    if flush:
                        self.ser.flush()
                return
            except serial.SerialTimeoutException as exc:
                last_exc = exc
                time.sleep(0.03 * (attempt + 1))
            except serial.SerialException as exc:
                last_exc = exc
                time.sleep(0.05 * (attempt + 1))

        if last_exc is not None:
            raise last_exc

    def _send_line(self, line):
        self._serial_write_bytes((line + "\n").encode("utf-8"), flush=False)

    def _request_full_frame(self, force=False):
        now = time.perf_counter()
        if not force and (now - self._last_sync_full_request_ts) < SYNC_FULL_RETRY_SEC:
            return False
        self._last_sync_full_request_ts = now
        try:
            self._send_line("SYNC:FULL")
            return True
        except Exception:
            return False

    def _wait_for_marker(self, marker, timeout=5.0):
        return self._wait_for_any_markers([marker], timeout=timeout) is not None

    def _wait_for_any_markers(self, markers, timeout=5.0):
        deadline = time.time() + timeout
        buf = ""
        while time.time() < deadline:
            try:
                waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
                chunk = self.ser.read(waiting if waiting > 0 else 1)
                if chunk:
                    buf += chunk.decode("utf-8", errors="ignore")
                    for marker in markers:
                        if marker in buf:
                            return marker
                    if len(buf) > 4096:
                        buf = buf[-4096:]
                else:
                    time.sleep(0.01)
            except Exception:
                time.sleep(0.01)
        return None

    def _sync_startup_markers(self, timeout=STARTUP_SYNC_TIMEOUT_SEC):
        result = {
            "ready_seen": False,
            "state_seen": False,
            "baud_seen": False,
            "key_debounce_ms": None,
            "graph_fast_ms": None,
            "bridge_err": "",
        }
        deadline = time.time() + max(0.2, timeout)
        buf = ""
        while time.time() < deadline:
            try:
                waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
                chunk = self.ser.read(waiting if waiting > 0 else 1)
                if not chunk:
                    time.sleep(0.01)
                    continue
                buf += chunk.decode("utf-8", errors="ignore")
                while True:
                    nl = buf.find("\n")
                    if nl < 0:
                        break
                    line = buf[:nl].strip()
                    buf = buf[nl + 1 :]
                    if not line:
                        continue
                    if line.startswith("HYBRID_READY"):
                        result["ready_seen"] = True
                    elif line.startswith("HYBRID_BAUD:"):
                        result["baud_seen"] = line == f"HYBRID_BAUD:{HYBRID_BAUDRATE}"
                    elif line.startswith("HYB_KEY_DEB_MS:"):
                        try:
                            value = int(line.split(":", 1)[1].strip())
                            if value > 0:
                                result["key_debounce_ms"] = value
                        except Exception:
                            pass
                    elif line.startswith("HYB_GRAPH_FAST_MS:"):
                        try:
                            value = int(line.split(":", 1)[1].strip())
                            if value > 0:
                                result["graph_fast_ms"] = value
                        except Exception:
                            pass
                    elif line.startswith("HYBRID_BRIDGE_ERR"):
                        result["bridge_err"] = line
                        return result
                    elif "STATE:" in line:
                        result["state_seen"] = True
            except Exception:
                time.sleep(0.01)
        return result

    def _probe_repl_helper(self, token):
        safe = "".join(ch for ch in token if ch.isalnum() or ch in ("_", "-"))
        if not safe:
            safe = "PCHELLO"
        # First choice: call helper provided by boot.py.
        self._send_line(
            'print("ECHO:%s") if "_hyb_ping" not in globals() else _hyb_ping("%s")'
            % (safe, safe)
        )
        return self._wait_for_marker(f"ECHO:{safe}", timeout=1.2)

    def _clear_key_pipeline(self):
        if self._key_ack_timer.isActive():
            self._key_ack_timer.stop()
        self._pending_keys.clear()
        self._key_in_flight = None

    def _ack_inflight_key(self):
        if self._key_in_flight is None:
            return
        if self._key_ack_timer.isActive():
            self._key_ack_timer.stop()
        self._key_in_flight = None
        self._send_next_queued_key()

    def _on_key_ack_timeout(self):
        if self._key_in_flight is None:
            return
        row, col, from_hold, key_label = self._key_in_flight
        self._key_in_flight = None
        if not from_hold:
            self.status_label.setText(f"Sync timeout on {key_label} (c{col},r{row}); continuing")
        self._send_next_queued_key()

    def _send_next_queued_key(self):
        if self._key_in_flight is not None:
            return
        if not self._pending_keys:
            return
        if not self.connected or not self.ser or not self.ser.is_open:
            self._clear_key_pipeline()
            return

        row, col, from_hold = self._pending_keys.popleft()
        key_value = self._key_value_for(row, col)
        key_label = str(display_label(key_value)).strip() or str(key_value)

        try:
            self._serial_write_bytes(
                f"KEY:{col},{row}\n".encode("ascii"),
                flush=False,
                retries=1,
            )
            self._key_in_flight = (row, col, from_hold, key_label)
            self._key_ack_timer.start(max(1, int(self._key_ack_timeout_sec * 1000)))
            if from_hold:
                self.status_label.setText(f"Holding {key_label} (c{col},r{row})")
            else:
                self.status_label.setText(f"Sent {key_label} (c{col},r{row})")
            self._apply_mode_hint_after_press(key_value)
        except serial.SerialTimeoutException:
            if from_hold:
                self.status_label.setText(f"Holding {key_label}: timeout")
            else:
                self.status_label.setText("Serial write timeout (key dropped)")
            self._send_next_queued_key()
        except Exception as exc:
            if from_hold:
                self._stop_held_key()
            self._on_serial_error(f"Write failed: {exc}")

    def _on_key_pressed(self, row, col, from_hold=False):
        if not from_hold and self._held_key is not None and self._held_key != (row, col):
            self._stop_held_key()
        if not self.connected or not self.ser or not self.ser.is_open:
            if from_hold:
                self._stop_held_key()
            self.status_label.setText("Not connected to device")
            return
        row = int(row)
        col = int(col)

        if from_hold:
            if self._key_in_flight is not None:
                in_row, in_col, _, _ = self._key_in_flight
                if in_row == row and in_col == col:
                    return
            if self._pending_keys:
                last_row, last_col, _ = self._pending_keys[-1]
                if last_row == row and last_col == col:
                    return

        if len(self._pending_keys) >= MAX_PENDING_KEYS:
            if from_hold:
                return
            self._pending_keys.popleft()

        self._pending_keys.append((row, col, bool(from_hold)))
        self._send_next_queued_key()

    def _refresh_mode_indicator(self):
        mode_name = MODE_NAMES.get(self.current_mode, "Default")
        self.mode_label.setText(f"Mode: {mode_name}")

        alpha_active = self.current_mode in ("a", "A")
        beta_active = self.current_mode == "b"
        caps_active = self.current_mode == "A"

        active_by_coord = {
            (0, 1): alpha_active,  # alpha key
            (0, 2): beta_active,   # beta key
            (1, 2): caps_active,   # caps key (shared button position)
        }

        for coord, button in self.buttons.items():
            active = active_by_coord.get(coord, False)
            button.setProperty("modeActive", active)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _on_state_received(self, state):
        now = time.perf_counter()
        repaint_due = (now - self._last_state_apply_ts) >= self._min_state_apply_sec
        repaint_needed = False
        key_sync_event = any(
            key in state for key in ("fb_raw", "fb", "patches_raw", "patches", "fb_full", "lines", "nav")
        )

        nav = self.display_widget.nav_text
        if "nav" in state:
            nav = str(state.get("nav", "")).strip()
            self.display_widget.nav_text = nav
            repaint_needed = True
        lines = state.get("lines") if "lines" in state else None
        if isinstance(lines, list):
            self.display_widget.text_lines = [str(x) for x in lines[:8]]
            repaint_needed = True

        fb_seen_present = "fb_seen" in state
        fb_seen = bool(state.get("fb_seen", False))
        fb_full = bool(state.get("fb_full", False))
        fb_b64 = state.get("fb", "")
        fb_raw = state.get("fb_raw", None)
        fb_seq = state.get("fb_seq", None)
        if fb_seq is not None:
            try:
                fb_seq = int(fb_seq) & 0x7F
            except Exception:
                fb_seq = None

        fb_raw_bytes = None
        if fb_raw is not None:
            try:
                fb_raw_bytes = bytes(fb_raw)
            except Exception:
                fb_raw_bytes = None

        full_applied = False
        if fb_raw_bytes is not None and len(fb_raw_bytes) >= 1024:
            self.display_widget.framebuffer[:] = fb_raw_bytes[:1024]
            self.display_widget.has_framebuffer = True
            self._have_full_frame = True
            self._last_fb_seq = fb_seq
            full_applied = True
        elif isinstance(fb_b64, str) and fb_b64:
            try:
                raw = base64.b64decode(fb_b64.encode("ascii"), validate=False)
                if len(raw) >= 1024:
                    self.display_widget.framebuffer[:] = raw[:1024]
                    self.display_widget.has_framebuffer = True
                    self._have_full_frame = True
                    self._last_fb_seq = fb_seq
                    full_applied = True
            except Exception:
                pass
        elif fb_full and fb_seen:
            # Explicit full-frame blank payload.
            self.display_widget.framebuffer[:] = b"\x00" * 1024
            self.display_widget.has_framebuffer = True
            self._have_full_frame = True
            self._last_fb_seq = fb_seq
            full_applied = True

        patch_applied = False
        patch_seen = False
        patch_requires_full = False

        def _accept_patch_seq(seq):
            if seq is None:
                return True
            if self._last_fb_seq is None:
                return False
            expected = (self._last_fb_seq + 1) & 0x7F
            if seq == self._last_fb_seq:
                return True
            if seq == expected:
                self._last_fb_seq = seq
                return True
            return False

        patches_raw = state.get("patches_raw")
        if isinstance(patches_raw, list) and patches_raw:
            patch_seen = True
            if not self._have_full_frame:
                patch_requires_full = True
            elif not _accept_patch_seq(fb_seq):
                patch_requires_full = True
            else:
                for patch in patches_raw:
                    if not isinstance(patch, (tuple, list)) or len(patch) != 5:
                        continue
                    try:
                        page = int(patch[0])
                        col = int(patch[1])
                        width = int(patch[2])
                        pages = int(patch[3])
                        raw = patch[4]
                    except Exception:
                        continue

                    if (
                        page < 0
                        or col < 0
                        or width <= 0
                        or pages <= 0
                        or page > 7
                        or col > 127
                        or (page + pages) > 8
                        or (col + width) > 128
                    ):
                        continue

                    needed = width * pages
                    try:
                        raw_bytes = bytes(raw)
                    except Exception:
                        continue
                    if len(raw_bytes) < needed:
                        continue

                    src = 0
                    for p in range(pages):
                        dst = (page + p) * 128 + col
                        self.display_widget.framebuffer[dst : dst + width] = raw_bytes[src : src + width]
                        src += width
                    patch_applied = True

        patches = state.get("patches")
        if isinstance(patches, list) and patches:
            patch_seen = True
            if not self._have_full_frame:
                patch_requires_full = True
            elif not _accept_patch_seq(fb_seq):
                patch_requires_full = True
            else:
                for patch in patches:
                    if not isinstance(patch, dict):
                        continue
                    try:
                        page = int(patch.get("p", 0))
                        col = int(patch.get("c", 0))
                        width = int(patch.get("w", 0))
                        pages = int(patch.get("g", 0))
                        data_b64 = patch.get("d", "")
                    except Exception:
                        continue

                    if (
                        page < 0
                        or col < 0
                        or width <= 0
                        or pages <= 0
                        or page > 7
                        or col > 127
                        or (page + pages) > 8
                        or (col + width) > 128
                        or not isinstance(data_b64, str)
                        or not data_b64
                    ):
                        continue

                    try:
                        raw = base64.b64decode(data_b64.encode("ascii"), validate=False)
                    except Exception:
                        continue

                    needed = width * pages
                    if len(raw) < needed:
                        continue

                    src = 0
                    for p in range(pages):
                        dst = (page + p) * 128 + col
                        self.display_widget.framebuffer[dst : dst + width] = raw[src : src + width]
                        src += width
                    patch_applied = True

        if patch_seen and patch_requires_full:
            self._have_full_frame = False
            self._last_fb_seq = None
            self._request_full_frame()

        if full_applied or patch_applied:
            repaint_needed = True

        if patch_applied:
            self.display_widget.has_framebuffer = True
        elif not full_applied:
            # Only change framebuffer mode when device explicitly reports fb_seen.
            if fb_seen_present and fb_seen:
                if not self.display_widget.has_framebuffer:
                    self.display_widget.framebuffer[:] = b"\x00" * 1024
                    self.display_widget.has_framebuffer = True
            elif fb_seen_present and self.display_widget.text_lines:
                self.display_widget.has_framebuffer = False
                self._have_full_frame = False
                self._last_fb_seq = None

        if repaint_needed and (repaint_due or full_applied):
            self._last_state_apply_ts = now
            self.display_widget.update()

        if key_sync_event:
            self._ack_inflight_key()

        mapped_mode = self._mode_from_nav(nav)
        if mapped_mode and mapped_mode != self.current_mode:
            self.current_mode = mapped_mode
            self._refresh_mode_indicator()

    def _mode_from_nav(self, nav_text):
        cleaned = nav_text.strip()
        lowered = cleaned.lower()
        if lowered == "default":
            return "d"
        if cleaned == "ALPHA":
            return "A"
        if lowered == "alpha":
            return "a"
        if lowered == "beta":
            return "b"
        return None

    def _on_raw_line(self, line):
        if line.startswith("ECHO:"):
            self.status_label.setText(f"Echo: {line[5:].strip()}")
            return
        if line.startswith("HYBRID_READY"):
            self.status_label.setText(f"Connected on {self.port} (bridge ready)")
            return
        if line.startswith("HYBRID_PROTO:"):
            return
        if line.startswith("HYBRID_BAUD:"):
            if line.strip() != f"HYBRID_BAUD:{HYBRID_BAUDRATE}":
                self.status_label.setText(f"Bridge baud mismatch: {line.strip()}")
            return
        if line.startswith("HYB_KEY_DEB_MS:"):
            try:
                value = int(line.split(":", 1)[1].strip())
                if value > 0:
                    self._configure_input_timing(value)
            except Exception:
                pass
            return
        if line.startswith("HYB_GRAPH_FAST_MS:"):
            try:
                value = int(line.split(":", 1)[1].strip())
                if value > 0:
                    self._device_graph_fast_ms = value
            except Exception:
                pass
            return
        if line.startswith("HYBRID_BRIDGE_ERR"):
            self.status_label.setText(line.strip())
            return
        if line.startswith("DEB:"):
            return
        if line.startswith("RX:"):
            return
        if line.startswith("Traceback"):
            self.status_label.setText("Device error: Traceback reported")

    def _on_serial_error(self, error):
        self._stop_held_key()
        self._clear_key_pipeline()
        self.status_label.setText(error)
        QMessageBox.warning(self, "Hybrid Simulator", error)
        self.close()

    def closeEvent(self, event):
        self._stop_held_key()
        self._clear_key_pipeline()
        if self.reader_thread:
            self.reader_thread.stop()
            self.reader_thread.wait(800)
        if self.ser and self.ser.is_open:
            self.ser.close()
        event.accept()
