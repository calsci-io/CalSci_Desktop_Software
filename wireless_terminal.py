"""
Native in-app Wireless REPL dialog for CalSci desktop software.
"""

from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from config import WIRELESS_DEFAULT_PORT
from wireless import WirelessReplSession, WirelessTransferError


class WirelessReplDialog(QDialog):
    def __init__(self, host: str, password: str, port: int = WIRELESS_DEFAULT_PORT, parent=None):
        super().__init__(parent)
        self.host = str(host or "").strip()
        self.password = str(password or "")
        self.port = int(port)

        self._session = None
        self._reader_thread = None
        self._stop_event = None
        self._events = queue.Queue()
        self._connected = False

        self.setWindowTitle("Wireless REPL")
        self.resize(780, 520)
        self._build_ui()

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._drain_events)
        self._ui_timer.start(70)

        self._connect_session()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        info = QLabel("Direct WebREPL session inside CalSci Desktop Software")
        layout.addWidget(info)

        host_row = QHBoxLayout()
        host_label = QLabel("Target:")
        self.host_value = QLabel("{}:{}".format(self.host, self.port))
        self.status_label = QLabel("Disconnected")
        host_row.addWidget(host_label)
        host_row.addWidget(self.host_value, 1)
        host_row.addWidget(self.status_label)
        layout.addLayout(host_row)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setUndoRedoEnabled(False)
        layout.addWidget(self.output, 1)

        input_row = QHBoxLayout()
        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Type a Python command and press Enter")
        self.input_line.returnPressed.connect(self._send_current_line)
        input_row.addWidget(self.input_line, 1)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._send_current_line)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

        button_row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._connect_session)
        button_row.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._disconnect_session)
        button_row.addWidget(self.disconnect_btn)

        self.interrupt_btn = QPushButton("Interrupt")
        self.interrupt_btn.clicked.connect(self._interrupt_session)
        button_row.addWidget(self.interrupt_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.output.clear)
        button_row.addWidget(self.clear_btn)

        layout.addLayout(button_row)
        self._set_connected(False)

    def _append_output(self, text: str):
        if not text:
            return
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()

    def _set_connected(self, connected: bool):
        self._connected = bool(connected)
        self.status_label.setText("Connected" if connected else "Disconnected")
        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)
        self.interrupt_btn.setEnabled(connected)
        self.input_line.setEnabled(connected)
        self.send_btn.setEnabled(connected)

    def _reader_worker(self, stop_event, session: WirelessReplSession):
        try:
            banner = session.connect()
            self._events.put(("connected", banner))
            while not stop_event.is_set():
                payload = session.read_available(timeout=0.25)
                if payload:
                    self._events.put(("data", payload))
        except Exception as exc:
            self._events.put(("error", str(exc)))
        finally:
            session.close()
            self._events.put(("closed", None))

    def _connect_session(self):
        if self._reader_thread and self._reader_thread.is_alive():
            return
        self._disconnect_session(silent=True)
        self._append_output("\n[connecting to {}:{}]\n".format(self.host, self.port))
        self._stop_event = threading.Event()
        self._session = WirelessReplSession(self.host, self.password, self.port)
        self._reader_thread = threading.Thread(
            target=self._reader_worker,
            args=(self._stop_event, self._session),
            daemon=True,
        )
        self._reader_thread.start()

    def _disconnect_session(self, silent=False):
        if self._stop_event is not None:
            self._stop_event.set()
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
        self._set_connected(False)
        if (not silent) and self.output.toPlainText().strip():
            self._append_output("\n[disconnected]\n")

    def _interrupt_session(self):
        if not self._session or not self._connected:
            return
        try:
            self._session.interrupt()
        except Exception as exc:
            QMessageBox.warning(self, "Wireless REPL", str(exc))

    def _send_current_line(self):
        if not self._session or not self._connected:
            return
        payload = self.input_line.text()
        if not payload and payload != "":
            return
        try:
            self._session.send_text(payload + "\r")
            self.input_line.clear()
        except WirelessTransferError as exc:
            QMessageBox.warning(self, "Wireless REPL", str(exc))
            self._disconnect_session()

    def _drain_events(self):
        while True:
            try:
                event, payload = self._events.get_nowait()
            except queue.Empty:
                break

            if event == "connected":
                self._set_connected(True)
                if payload:
                    self._append_output(payload)
            elif event == "data":
                self._append_output(payload)
            elif event == "error":
                self._append_output("\n[error] {}\n".format(payload))
            elif event == "closed":
                was_connected = self._connected
                self._set_connected(False)
                self._session = None
                self._reader_thread = None
                self._stop_event = None
                if was_connected:
                    self._append_output("\n[connection closed]\n")

    def closeEvent(self, event):
        self._disconnect_session(silent=True)
        super().closeEvent(event)
