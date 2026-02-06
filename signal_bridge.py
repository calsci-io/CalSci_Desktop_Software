"""
CalSci Flasher - Signal Bridge Module
Provides thread-safe communication between worker threads and Qt UI.
"""

from PySide6.QtCore import QObject, Signal


class SignalBridge(QObject):
    """Signal bridge for thread-safe UI updates."""

    # Main operation signals
    log_signal = Signal(str, str)                    # message, type
    progress_signal = Signal(float)                  # 0.0 → 1.0
    operation_done_signal = Signal()                 # unlock buttons
    device_status_signal = Signal(bool)              # device connected status

    # File browser signals
    file_tree_loaded_signal = Signal(object, object, object)  # files, dirs, modules
    file_content_loaded_signal = Signal(str, str, str)  # path, content, hash
    file_upload_complete_signal = Signal(str, bool)  # path, success
    scan_triggered_signal = Signal()  # trigger device scan from main thread
    status_message_signal = Signal(str)  # status bar message from background thread

    # Run signals
    run_log_signal = Signal(str, str)  # message, type (info/error/success/output)
    run_complete_signal = Signal(str, bool, str)  # path, success, output
