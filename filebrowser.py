"""
CalSci File Browser Module
VSCode-style file browser for CalSci with integrated editor.
"""

import sys
import threading
import hashlib
import re
import time
from pathlib import Path
from queue import Queue, Empty

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QProgressBar, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QSplitter,
    QFrame, QStatusBar, QMessageBox, QPlainTextEdit, QTabWidget, QMenu,
    QLineEdit, QToolButton, QInputDialog, QDialog, QDialogButtonBox,
    QScrollBar, QToolBar, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QSize, Signal, QRect
from PySide6.QtGui import (
    QColor, QFont, QAction, QTextCursor, QKeySequence, QShortcut,
    QPainter, QTextFormat, QPen, QBrush, QFontMetrics, QTextDocument,
    QSyntaxHighlighter, QTextCharFormat
)
from PySide6.QtWidgets import QCompleter
from PySide6.QtCore import QStringListModel

# Import from modular files
from config import ROOT, SELECTIONS_FILE
from utils import (
    SelectionMemory, find_esp32_ports, ensure_repo, delete_repo,
    repo_status, pull_repo, get_all_files
)
from flasher import MicroPyFlasher, MicroPyError
from signal_bridge import SignalBridge
from dialogs import FileSelectionDialog, ESP32FileSelectionDialog


# File type icons mapping
FILE_ICONS = {
    '.py': '🐍',
    '.json': '📋',
    '.txt': '📄',
    '.md': '📝',
    '.html': '🌐',
    '.css': '🎨',
    '.js': '⚡',
    '.mpy': '📦',
    '.bin': '💾',
    '.cfg': '⚙️',
    '.ini': '⚙️',
    '.log': '📜',
    'default': '📄'
}


def get_file_icon(filename):
    """Get appropriate icon for file type."""
    ext = Path(filename).suffix.lower()
    return FILE_ICONS.get(ext, FILE_ICONS['default'])


# Python keywords, builtins, and MicroPython modules for autocomplete
PYTHON_KEYWORDS = [
    'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
    'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
    'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
    'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try',
    'while', 'with', 'yield'
]

PYTHON_BUILTINS = [
    'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray', 'bytes',
    'callable', 'chr', 'classmethod', 'compile', 'complex', 'delattr',
    'dict', 'dir', 'divmod', 'enumerate', 'eval', 'exec', 'filter',
    'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr',
    'hash', 'help', 'hex', 'id', 'input', 'int', 'isinstance', 'issubclass',
    'iter', 'len', 'list', 'locals', 'map', 'max', 'memoryview', 'min',
    'next', 'object', 'oct', 'open', 'ord', 'pow', 'print', 'property',
    'range', 'repr', 'reversed', 'round', 'set', 'setattr', 'slice',
    'sorted', 'staticmethod', 'str', 'sum', 'super', 'tuple', 'type',
    'vars', 'zip', '__import__', 'Exception', 'BaseException', 'TypeError',
    'ValueError', 'KeyError', 'IndexError', 'AttributeError', 'ImportError',
    'RuntimeError', 'StopIteration', 'OSError', 'IOError', 'FileNotFoundError'
]

MICROPYTHON_MODULES = [
    'machine', 'utime', 'time', 'uos', 'os', 'usys', 'sys', 'gc', 'ubinascii',
    'binascii', 'ucollections', 'collections', 'uerrno', 'errno', 'uhashlib',
    'hashlib', 'uheapq', 'heapq', 'uio', 'io', 'ujson', 'json', 'uselect',
    'select', 'usocket', 'socket', 'ustruct', 'struct', 'network', 'esp',
    'esp32', 'neopixel', 'onewire', 'ds18x20', 'dht', 'framebuf', 'btree',
    'micropython', 'uasyncio', 'asyncio', 'uctypes', 'bluetooth', 'cryptolib',
    # machine submodules
    'Pin', 'PWM', 'ADC', 'DAC', 'I2C', 'SPI', 'UART', 'Timer', 'RTC',
    'TouchPad', 'WDT', 'SDCard', 'Signal', 'SoftI2C', 'SoftSPI',
    # Common constants/methods
    'sleep', 'sleep_ms', 'sleep_us', 'ticks_ms', 'ticks_us', 'ticks_diff',
    'freq', 'reset', 'soft_reset', 'unique_id', 'idle', 'lightsleep', 'deepsleep'
]

# Module definitions for intelligent dot-completion
# Structure: module_name -> { 'classes': {class_name: [methods]}, 'functions': [func_names], 'constants': [const_names] }
# These definitions are extracted from calsci_simulator folder
MODULE_DEFINITIONS = {
    # ============== PROCESS_MODULES ==============
    'process_modules': {
        'classes': {
            # process_modules/app.py
            'App': ['get_app_name', 'get_group_name', 'set_app_name', 'set_group_name', 'set_none'],
            # process_modules/navbar.py & nav_buffer.py
            'Nav': ['state_change', 'current_state', 'update_buffer', 'buffer', 'refresh_element', 'update'],
            # process_modules/text_buffer.py
            'Textbuffer': ['buffer', 'update_buffer', 'all_clear', 'ref_ar', 'cursor'],
            # process_modules/menu_buffer.py
            'Menu': ['update_buffer', 'buffer', 'cursor', 'ref_ar', 'update'],
            # process_modules/form_buffer.py
            'Form': ['update_buffer', 'ref_ar', 'buffer', 'cursor', 'act_rows', 'inp_cursor',
                     'inp_list', 'inp_display_position', 'inp_cols', 'update', 'update_label'],
            # process_modules/uploader.py
            'BaseUploader': ['update', 'refresh', '_print_character', '_display_bar', '_clear_row_display'],
            # process_modules/text_buffer_uploader.py
            'TextUploader': ['update', 'refresh'],
            # process_modules/menu_buffer_uploader.py
            'MenuUploader': ['refresh'],
            # process_modules/form_buffer_uploader.py
            'FormUploader': ['refresh'],
            # process_modules/app_downloader.py
            'Apps': ['insert', 'search_app_name', 'sea_by_g', 'get_group_apps', 'insert_new_app', 'delete_app'],
            'App_downloader': ['check_status', 'download_app', 'update_app_list', 'send_confirmation', 'reset'],
        },
        'functions': ['app_runner', 'keypad_state_manager', 'keypad_state_manager_reset'],
        'constants': [],
    },

    # ============== DATA_MODULES ==============
    'data_modules': {
        'classes': {
            # data_modules/constants.py
            'GPIOPins': ['GPIO0', 'GPIO1', 'GPIO2', 'GPIO3', 'GPIO4', 'GPIO5', 'GPIO12', 'GPIO13',
                         'GPIO14', 'GPIO15', 'GPIO16', 'GPIO17', 'GPIO18', 'GPIO19', 'GPIO21',
                         'GPIO22', 'GPIO23', 'GPIO25', 'GPIO26', 'GPIO27', 'GPIO32', 'GPIO33',
                         'GPIO34', 'GPIO35', 'GPIO36', 'GPIO39'],
            'KeyButtons': ['get_symbol', 'get_char', 'create_reverse_key_map', 'KEY_MAP', 'REVERSE_KEY_MAP',
                          'RST', 'BT', 'OK', 'ON', 'NAV_D', 'NAV_U', 'NAV_L', 'NAV_R', 'BETA', 'ALPHA',
                          'HOME', 'WIFI', 'TAB', 'BACKLIGHT', 'BACK', 'TOOLBOX', 'DIFF', 'LN', 'MODULE',
                          'BLUETOOTH', 'SIN', 'COS', 'TAN', 'ASIN', 'ACOS', 'ATAN', 'PI', 'LOG', 'POW',
                          'SQRT', 'EXE', 'CAPS', 'SPACE', 'PLUS', 'MINUS', 'SLASH', 'ASTERISK'],
            'KeypadMode': ['DEFAULT', 'ALPHA', 'BETA'],
            # data_modules/characters.py
            'Characters': ['Chr2bytes', 'invert_letter', 'Chr5X8_data'],
            # data_modules/keypad_map.py
            'Keypad_5X8': ['key_out', 'key_change'],
        },
        'functions': ['keypad_state_manager', 'keypad_state_manager_reset'],
        'constants': ['keypad_rows', 'keypad_cols', 'st7565_display_pins', 'keyin', 'network_info'],
    },

    # ============== DISPLAY ==============
    'display': {
        'classes': {
            # display/display.py
            'Display': ['draw_pixel', 'clear_display', 'turn_off_all_pixels', 'turn_on_all_pixels',
                       'turn_on_pixel', 'turn_off_pixel', 'get_pos', 'write_data', 'reset_cursor',
                       'set_page_address', 'set_column_address'],
            # display/characters.py
            'Characters': ['Chr2bytes', 'invert_letter', 'data'],
            # display/base_buffer.py
            'BaseBuffer': ['update_buffer', 'all_clear'],
            # display/text_buffer.py
            'TextBuffer': ['buffer', 'update_buffer', 'all_clear', 'ref_ar', 'cursor'],
            # display/text_uploader.py
            'TextUploader': ['update', 'refresh'],
        },
        'functions': [],
        'constants': ['FPS', 'BOXSIZE', 'GAPSIZE', 'BOARDWIDTH', 'BOARDHEIGHT', 'MARGIN',
                     'WINDOWWIDTH', 'WINDOWHEIGHT', 'XMARGIN', 'YMARGIN', 'PIXELON', 'PIXELOFF'],
    },

    # ============== APPS ==============
    'apps': {
        'classes': {},
        'functions': ['home', 'installed_apps', 'calculate', 'chatbot_ai', 'scientific_calculator', 'settings'],
        'constants': [],
    },

    # ============== COMPONENTS (root) ==============
    'components': {
        'classes': {
            'Button': ['draw', 'is_clicked', 'get_text', 'get_text_font'],
            'OtherButton': ['draw', 'get_text', 'is_clicked'],
        },
        'functions': [],
        'constants': ['main_font', 'fallback_font', 'emoji_font'],
    },

    # ============== CONSTANTS (root) ==============
    'constants': {
        'classes': {
            'KeyButtons': ['get_symbol', 'get_char', 'create_reverse_key_map', 'KEY_MAP', 'REVERSE_KEY_MAP'],
            'KeypadMode': ['DEFAULT', 'ALPHA', 'BETA'],
        },
        'functions': [],
        'constants': [],
    },

    # ============== KEYMAP (root) ==============
    'keymap': {
        'classes': {
            'Keypad': ['key_out', 'key_change'],
        },
        'functions': [],
        'constants': [],
    },

    # ============== TYPER (root) ==============
    'typer': {
        'classes': {
            'Typer': ['start_typing', 'change_keymaps'],
        },
        'functions': ['get_buttons', 'get_other_buttons', 'keypad_state_manager', 'keypad_state_manager_reset'],
        'constants': ['screen', 'clock', 'keypad', 'display', 'typer', 'nav', 'text', 'menu', 'form',
                     'text_refresh', 'menu_refresh', 'form_refresh', 'app', 'apps_installer',
                     'current_app', 'data_bucket'],
    },

    # ============== WATCHER (root) ==============
    'watcher': {
        'classes': {
            'ChangeHandler': ['on_modified'],
        },
        'functions': ['start_app', 'stop_app', 'main'],
        'constants': ['COMMAND', 'WATCH_EXT', 'running_process', 'DEBOUNCE_DELAY', 'last_trigger'],
    },

    # ============== MACHINE (simulator) ==============
    'machine': {
        'classes': {
            'Pin': ['init', 'value', 'on', 'off', 'irq', 'low', 'high', 'mode', 'pull', 'drive', 'toggle',
                   'IN', 'OUT', 'OPEN_DRAIN', 'ALT', 'ALT_OPEN_DRAIN', 'ANALOG',
                   'PULL_UP', 'PULL_DOWN', 'PULL_HOLD', 'DRIVE_0', 'DRIVE_1', 'DRIVE_2',
                   'IRQ_FALLING', 'IRQ_RISING', 'IRQ_LOW_LEVEL', 'IRQ_HIGH_LEVEL'],
            'PWM': ['freq', 'duty', 'duty_u16', 'duty_ns', 'deinit', 'init'],
            'ADC': ['read', 'read_u16', 'read_uv', 'atten', 'width', 'init'],
            'DAC': ['write', 'deinit'],
            'I2C': ['scan', 'start', 'stop', 'readinto', 'write', 'readfrom', 'readfrom_into',
                    'writeto', 'readfrom_mem', 'readfrom_mem_into', 'writeto_mem', 'init', 'deinit'],
            'SPI': ['read', 'readinto', 'write', 'write_readinto', 'init', 'deinit'],
            'UART': ['read', 'readline', 'readinto', 'write', 'any', 'init', 'deinit',
                     'sendbreak', 'flush', 'txdone'],
            'Timer': ['init', 'deinit', 'value'],
            'RTC': ['datetime', 'init', 'memory'],
            'WDT': ['feed'],
            'TouchPad': ['read', 'config'],
            'SDCard': ['info', 'readblocks', 'writeblocks', 'ioctl'],
        },
        'functions': ['reset', 'soft_reset', 'reset_cause', 'bootloader', 'disable_irq', 'enable_irq',
                      'freq', 'idle', 'sleep', 'lightsleep', 'deepsleep', 'wake_reason',
                      'unique_ids', 'time_pulse_us', 'bitstream', 'rng'],
        'constants': ['IDLE', 'SLEEP', 'DEEPSLEEP', 'PWRON_RESET', 'HARD_RESET', 'WDT_RESET',
                      'DEEPSLEEP_RESET', 'SOFT_RESET', 'WLAN_WAKE', 'PIN_WAKE', 'RTC_WAKE',
                      'mem8', 'mem16', 'mem32', 'irq', 'frequency'],
    },

    # ============== DYNAMIC_STUFF ==============
    'dynamic_stuff': {
        'classes': {},
        'functions': ['get_data'],
        'constants': ['new_upload', 'data_generator_status'],
    },

    # ============== LIB/TINYDB ==============
    'tinydb': {
        'classes': {
            'TinyDB': ['insert', 'insert_multiple', 'search', 'get', 'contains', 'update', 'upsert',
                       'remove', 'truncate', 'all', 'count', 'close', 'table', 'tables',
                       'drop_table', 'drop_tables'],
            'Query': ['exists', 'matches', 'search', 'test', 'any', 'all', 'one_of', 'noop',
                      'fragment', 'map'],
            'Table': ['insert', 'insert_multiple', 'search', 'get', 'contains', 'update', 'upsert',
                      'remove', 'truncate', 'all', 'count', 'clear_cache'],
            'Storage': ['read', 'write', 'close'],
            'JSONStorage': ['read', 'write', 'close'],
            'MemoryStorage': ['read', 'write', 'close'],
        },
        'functions': ['where'],
        'constants': [],
    },

    # ============== STANDARD MICROPYTHON MODULES ==============
    'time': {
        'classes': {},
        'functions': ['sleep', 'sleep_ms', 'sleep_us', 'ticks_ms', 'ticks_us', 'ticks_cpu',
                      'ticks_add', 'ticks_diff', 'time', 'time_ns', 'gmtime', 'localtime', 'mktime'],
        'constants': [],
    },
    'utime': {
        'classes': {},
        'functions': ['sleep', 'sleep_ms', 'sleep_us', 'ticks_ms', 'ticks_us', 'ticks_cpu',
                      'ticks_add', 'ticks_diff', 'time', 'time_ns', 'gmtime', 'localtime', 'mktime'],
        'constants': [],
    },
    'network': {
        'classes': {
            'WLAN': ['active', 'connect', 'disconnect', 'scan', 'isconnected', 'config',
                     'ifconfig', 'status', 'hostname'],
            'LAN': ['active', 'isconnected', 'config', 'ifconfig', 'status'],
        },
        'functions': ['hostname', 'country', 'phy_mode'],
        'constants': ['STA_IF', 'AP_IF', 'MODE_11B', 'MODE_11G', 'MODE_11N'],
    },
    'json': {
        'classes': {},
        'functions': ['dumps', 'dump', 'loads', 'load'],
        'constants': [],
    },
    'ujson': {
        'classes': {},
        'functions': ['dumps', 'dump', 'loads', 'load'],
        'constants': [],
    },
    'os': {
        'classes': {
            'VfsFat': ['mkfs', 'open', 'ilistdir', 'mkdir', 'rmdir', 'chdir', 'getcwd',
                       'remove', 'rename', 'stat', 'statvfs', 'mount', 'umount'],
        },
        'functions': ['uname', 'urandom', 'chdir', 'getcwd', 'ilistdir', 'listdir',
                      'mkdir', 'remove', 'rmdir', 'rename', 'stat', 'statvfs', 'sync',
                      'mount', 'umount', 'dupterm'],
        'constants': [],
    },
    'uos': {
        'classes': {
            'VfsFat': ['mkfs', 'open', 'ilistdir', 'mkdir', 'rmdir', 'chdir', 'getcwd',
                       'remove', 'rename', 'stat', 'statvfs', 'mount', 'umount'],
        },
        'functions': ['uname', 'urandom', 'chdir', 'getcwd', 'ilistdir', 'listdir',
                      'mkdir', 'remove', 'rmdir', 'rename', 'stat', 'statvfs', 'sync',
                      'mount', 'umount', 'dupterm'],
        'constants': [],
    },
    'gc': {
        'classes': {},
        'functions': ['enable', 'disable', 'collect', 'isenabled', 'mem_free', 'mem_alloc', 'threshold'],
        'constants': [],
    },
    'esp': {
        'classes': {},
        'functions': ['osdebug', 'flash_size', 'flash_user_start', 'flash_read', 'flash_write', 'flash_erase'],
        'constants': [],
    },
    'esp32': {
        'classes': {
            'Partition': ['find', 'info', 'readblocks', 'writeblocks', 'ioctl', 'set_boot', 'get_next_update'],
            'RMT': ['write_pulses', 'wait_done', 'loop', 'deinit'],
            'ULP': ['set_wakeup_period', 'load_binary', 'run'],
            'NVS': ['get_i32', 'set_i32', 'get_blob', 'set_blob', 'erase_key', 'commit'],
        },
        'functions': ['wake_on_touch', 'wake_on_ext0', 'wake_on_ext1', 'raw_temperature',
                      'hall_sensor', 'idf_heap_info'],
        'constants': ['WAKEUP_ALL_LOW', 'WAKEUP_ANY_HIGH', 'HEAP_DATA', 'HEAP_EXEC'],
    },
}

# All words for basic autocomplete (when not in dot-completion context)
AUTOCOMPLETE_WORDS = sorted(set(
    PYTHON_KEYWORDS + PYTHON_BUILTINS + MICROPYTHON_MODULES +
    list(MODULE_DEFINITIONS.keys())
))


class PythonHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Python/MicroPython code."""

    def __init__(self, document):
        super().__init__(document)
        self._init_formats()
        self._init_rules()

    def _init_formats(self):
        """Initialize text formats for different token types."""
        # Keywords (purple/magenta)
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor('#c586c0'))
        self.keyword_format.setFontWeight(QFont.Weight.Bold)

        # Builtins (cyan)
        self.builtin_format = QTextCharFormat()
        self.builtin_format.setForeground(QColor('#4ec9b0'))

        # Strings (orange/brown)
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor('#ce9178'))

        # Comments (green)
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor('#6a9955'))
        self.comment_format.setFontItalic(True)

        # Numbers (light green)
        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor('#b5cea8'))

        # Decorators (yellow)
        self.decorator_format = QTextCharFormat()
        self.decorator_format.setForeground(QColor('#dcdcaa'))

        # Function/method definitions (light blue)
        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor('#dcdcaa'))

        # Class names (green)
        self.class_format = QTextCharFormat()
        self.class_format.setForeground(QColor('#4ec9b0'))

        # self/cls (blue)
        self.self_format = QTextCharFormat()
        self.self_format.setForeground(QColor('#9cdcfe'))
        self.self_format.setFontItalic(True)

        # Imports (blue)
        self.import_format = QTextCharFormat()
        self.import_format.setForeground(QColor('#569cd6'))

        # Operators
        self.operator_format = QTextCharFormat()
        self.operator_format.setForeground(QColor('#d4d4d4'))

    def _init_rules(self):
        """Initialize highlighting rules."""
        self.rules = []

        # Keywords
        keyword_pattern = r'\b(' + '|'.join(PYTHON_KEYWORDS) + r')\b'
        self.rules.append((re.compile(keyword_pattern), self.keyword_format))

        # Builtins
        builtin_pattern = r'\b(' + '|'.join(PYTHON_BUILTINS) + r')\b'
        self.rules.append((re.compile(builtin_pattern), self.builtin_format))

        # self and cls
        self.rules.append((re.compile(r'\b(self|cls)\b'), self.self_format))

        # Decorators
        self.rules.append((re.compile(r'@\w+'), self.decorator_format))

        # Function definitions
        self.rules.append((re.compile(r'\bdef\s+(\w+)'), self.function_format, 1))

        # Class definitions
        self.rules.append((re.compile(r'\bclass\s+(\w+)'), self.class_format, 1))

        # Numbers (int, float, hex, binary, octal)
        self.rules.append((re.compile(r'\b0[xX][0-9a-fA-F]+\b'), self.number_format))
        self.rules.append((re.compile(r'\b0[bB][01]+\b'), self.number_format))
        self.rules.append((re.compile(r'\b0[oO][0-7]+\b'), self.number_format))
        self.rules.append((re.compile(r'\b[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?\b'), self.number_format))

        # Import statements - highlight module names
        self.rules.append((re.compile(r'\bimport\s+(\w+)'), self.import_format, 1))
        self.rules.append((re.compile(r'\bfrom\s+(\w+)'), self.import_format, 1))

    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text."""
        # Apply regular rules
        for rule in self.rules:
            if len(rule) == 2:
                pattern, fmt = rule
                for match in pattern.finditer(text):
                    self.setFormat(match.start(), match.end() - match.start(), fmt)
            else:
                pattern, fmt, group = rule
                for match in pattern.finditer(text):
                    start = match.start(group)
                    length = match.end(group) - start
                    self.setFormat(start, length, fmt)

        # Handle strings (single and double quotes) - must be after other rules
        self._highlight_strings(text)

        # Handle comments last (they override everything)
        self._highlight_comments(text)

    def _highlight_strings(self, text):
        """Highlight string literals."""
        # Triple-quoted strings
        for pattern in [r'""".*?"""', r"'''.*?'''", r'""".*$', r"'''.*$"]:
            for match in re.finditer(pattern, text, re.DOTALL):
                self.setFormat(match.start(), match.end() - match.start(), self.string_format)

        # Single-line strings (careful not to match inside triple quotes)
        in_triple = set()
        for match in re.finditer(r'("""|\'\'\').*?("""|\'\'\'|$)', text):
            for i in range(match.start(), match.end()):
                in_triple.add(i)

        # Double and single quoted strings
        for pattern in [r'"(?:[^"\\]|\\.)*"', r"'(?:[^'\\]|\\.)*'"]:
            for match in re.finditer(pattern, text):
                if match.start() not in in_triple:
                    self.setFormat(match.start(), match.end() - match.start(), self.string_format)

    def _highlight_comments(self, text):
        """Highlight comments (# to end of line)."""
        # Find # that's not inside a string
        i = 0
        in_string = None
        while i < len(text):
            char = text[i]

            # Track string state
            if in_string is None:
                if char == '#':
                    # This is a comment
                    self.setFormat(i, len(text) - i, self.comment_format)
                    break
                elif char in '"\'':
                    # Check for triple quotes
                    if text[i:i+3] in ['"""', "'''"]:
                        in_string = text[i:i+3]
                        i += 3
                        continue
                    else:
                        in_string = char
            else:
                # In a string, look for end
                if in_string in ['"""', "'''"]:
                    if text[i:i+3] == in_string:
                        in_string = None
                        i += 3
                        continue
                elif char == in_string and (i == 0 or text[i-1] != '\\'):
                    in_string = None
            i += 1


class LineNumberArea(QWidget):
    """Line number area widget for the code editor."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setFont(editor.font())

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    """Enhanced code editor with line numbers, syntax highlighting, and autocomplete."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.update_line_number_area_width(0)
        self.highlight_current_line()

        # Set monospace font
        font = QFont('Consolas', 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.line_number_area.setFont(font)

        # Tab settings
        self.setTabStopDistance(QFontMetrics(font).horizontalAdvance(' ') * 4)

        # Syntax highlighter for Python
        self.highlighter = PythonHighlighter(self.document())

        # Autocomplete setup
        self._setup_completer()

        # Custom undo/redo (character-wise)
        self.setUndoRedoEnabled(False)
        self._undo_stack = []
        self._redo_stack = []
        self._suppress_undo_record = False
        self._last_text = self.toPlainText()
        self.document().contentsChange.connect(self._on_contents_change)

        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.undo_shortcut.activated.connect(self._custom_undo)
        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.redo_shortcut.activated.connect(self._custom_redo)
        self.redo_shortcut2 = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.redo_shortcut2.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.redo_shortcut2.activated.connect(self._custom_redo)

    def setPlainText(self, text):
        self._suppress_undo_record = True
        super().setPlainText(text)
        self._suppress_undo_record = False
        self._last_text = self.toPlainText()
        self._undo_stack.clear()
        self._redo_stack.clear()

    def _on_contents_change(self, position, chars_removed, chars_added):
        new_text = self.toPlainText()
        if self._suppress_undo_record:
            self._last_text = new_text
            return

        old_text = self._last_text
        removed_text = old_text[position:position + chars_removed] if chars_removed else ""
        added_text = new_text[position:position + chars_added] if chars_added else ""

        if removed_text or added_text:
            # Record removals first (per-character, same position),
            # then additions (per-character, advancing position).
            if removed_text:
                for ch in removed_text:
                    self._undo_stack.append((position, ch, ""))
            if added_text:
                for i, ch in enumerate(added_text):
                    self._undo_stack.append((position + i, "", ch))
            self._redo_stack.clear()

        self._last_text = new_text

    def _custom_undo(self):
        if not self._undo_stack:
            return

        position, removed_text, added_text = self._undo_stack.pop()
        self._suppress_undo_record = True

        cursor = self.textCursor()
        cursor.setPosition(position)
        if added_text:
            cursor.setPosition(position + len(added_text), QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        if removed_text:
            cursor.insertText(removed_text)
        self.setTextCursor(cursor)

        self._suppress_undo_record = False
        self._last_text = self.toPlainText()
        self._redo_stack.append((position, removed_text, added_text))

    def _custom_redo(self):
        if not self._redo_stack:
            return

        position, removed_text, added_text = self._redo_stack.pop()
        self._suppress_undo_record = True

        cursor = self.textCursor()
        cursor.setPosition(position)
        if removed_text:
            cursor.setPosition(position + len(removed_text), QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        if added_text:
            cursor.insertText(added_text)
        self.setTextCursor(cursor)

        self._suppress_undo_record = False
        self._last_text = self.toPlainText()
        self._undo_stack.append((position, removed_text, added_text))

    def line_number_area_width(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor('#1a1a1a'))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        current_line = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                if block_number == current_line:
                    painter.setPen(QColor('#e95420'))
                else:
                    painter.setPen(QColor('#606060'))
                painter.drawText(0, top, self.line_number_area.width() - 5,
                               self.fontMetrics().height(),
                               Qt.AlignmentFlag.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self):
        extra_selections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor('#2a2a2a')
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)

    def _setup_completer(self):
        """Setup autocomplete with intelligent dot-completion."""
        self.completer_model = QStringListModel(AUTOCOMPLETE_WORDS, self)
        self.completer = QCompleter(self)
        self.completer.setModel(self.completer_model)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.activated.connect(self._insert_completion)

        # Track current completion context
        self._completion_context = []  # e.g., ['machine', 'Pin'] for machine.Pin.
        self._is_dot_completion = False

        # Style the popup
        popup = self.completer.popup()
        popup.setStyleSheet("""
            QListView {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3a3a3a;
                selection-background-color: #094771;
                selection-color: #ffffff;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 11pt;
            }
            QListView::item {
                padding: 4px 8px;
            }
            QListView::item:hover {
                background-color: #2a2d2e;
            }
        """)

    def _get_word_under_cursor(self):
        """Get the word being typed at cursor position."""
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        return cursor.selectedText()

    def _get_text_before_cursor(self):
        """Get text from start of line to cursor position."""
        cursor = self.textCursor()
        block = cursor.block()
        line_text = block.text()
        col = cursor.positionInBlock()
        return line_text[:col]

    def _parse_dot_chain(self, text_before):
        """Parse the chain of identifiers before cursor (e.g., 'machine.Pin.' -> ['machine', 'Pin'])."""
        # Match pattern like: identifier.identifier.identifier (with optional partial word at end)
        # Look backwards from end of text
        pattern = r'([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\.([a-zA-Z_][a-zA-Z0-9_]*)?$'
        match = re.search(pattern, text_before)
        if match:
            chain = match.group(1).split('.')
            partial = match.group(2) or ''
            return chain, partial
        return [], ''

    def _get_completions_for_context(self, chain):
        """Get available completions based on the dot-chain context."""
        if not chain:
            return AUTOCOMPLETE_WORDS

        module_name = chain[0]

        # Check if module exists in definitions
        if module_name not in MODULE_DEFINITIONS:
            return []

        module_def = MODULE_DEFINITIONS[module_name]

        if len(chain) == 1:
            # module. -> show classes, functions, constants
            completions = []
            completions.extend(module_def.get('classes', {}).keys())
            completions.extend(module_def.get('functions', []))
            completions.extend(module_def.get('constants', []))
            return sorted(completions)

        elif len(chain) == 2:
            # module.Class. -> show methods of that class
            class_name = chain[1]
            classes = module_def.get('classes', {})
            if class_name in classes:
                return sorted(classes[class_name])
            # Maybe it's a function/constant, no further completions
            return []

        # Deeper chains not supported yet
        return []

    def _insert_completion(self, completion):
        """Insert the selected completion."""
        cursor = self.textCursor()

        if self._is_dot_completion:
            # For dot completion, only replace the partial word after the dot
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            cursor.insertText(completion)
        else:
            # For regular completion, replace the word under cursor
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            cursor.insertText(completion)

        self.setTextCursor(cursor)
        self._is_dot_completion = False

    def _show_completer(self, words, prefix=''):
        """Show completer with given words and prefix filter."""
        if not words:
            self.completer.popup().hide()
            return

        self.completer_model.setStringList(words)
        self.completer.setCompletionPrefix(prefix)

        if self.completer.completionCount() > 0:
            cursor_rect = self.cursorRect()
            cursor_rect.setWidth(
                max(200, self.completer.popup().sizeHintForColumn(0) +
                    self.completer.popup().verticalScrollBar().sizeHint().width())
            )
            self.completer.complete(cursor_rect)
        else:
            self.completer.popup().hide()

    def keyPressEvent(self, event):
        """Handle key press for autocomplete with dot-completion support."""
        if event.matches(QKeySequence.StandardKey.Undo):
            self._custom_undo()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self._custom_redo()
            return
        # If completer popup is visible, let it handle certain keys
        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return,
                               Qt.Key.Key_Escape, Qt.Key.Key_Tab,
                               Qt.Key.Key_Backtab):
                event.ignore()
                return

        # Handle Tab for indentation
        if event.key() == Qt.Key.Key_Tab and not self.completer.popup().isVisible():
            cursor = self.textCursor()
            cursor.insertText('    ')  # 4 spaces
            return

        # Handle auto-indent on Enter
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()

            # Get current indentation
            indent = ''
            for char in text:
                if char in ' \t':
                    indent += char
                else:
                    break

            # Add extra indent after colon
            stripped = text.rstrip()
            if stripped.endswith(':'):
                indent += '    '

            super().keyPressEvent(event)
            self.textCursor().insertText(indent)
            return

        # Check if this is a dot key press
        is_dot = event.text() == '.'

        super().keyPressEvent(event)

        # Handle dot-completion trigger
        if is_dot:
            text_before = self._get_text_before_cursor()
            chain, partial = self._parse_dot_chain(text_before)

            if chain:
                completions = self._get_completions_for_context(chain)
                if completions:
                    self._is_dot_completion = True
                    self._completion_context = chain
                    self._show_completer(completions, partial)
                    return

        # Hide completer for navigation/deletion keys
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Backspace,
                           Qt.Key.Key_Delete, Qt.Key.Key_Left, Qt.Key.Key_Right,
                           Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home,
                           Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self.completer.popup().hide()
            self._is_dot_completion = False
            return

        # Check if we're continuing a dot-completion (typing after the dot)
        text_before = self._get_text_before_cursor()
        chain, partial = self._parse_dot_chain(text_before)

        if chain:
            completions = self._get_completions_for_context(chain)
            if completions:
                self._is_dot_completion = True
                self._completion_context = chain
                self._show_completer(completions, partial)
                return

        # Fall back to regular word completion
        self._is_dot_completion = False
        word = self._get_word_under_cursor()

        if len(word) >= 2 and word.isalnum():
            self.completer_model.setStringList(AUTOCOMPLETE_WORDS)
            self.completer.setCompletionPrefix(word)
            if self.completer.completionCount() > 0:
                cursor_rect = self.cursorRect()
                cursor_rect.setWidth(
                    max(200, self.completer.popup().sizeHintForColumn(0) +
                        self.completer.popup().verticalScrollBar().sizeHint().width())
                )
                self.completer.complete(cursor_rect)
            else:
                self.completer.popup().hide()
        else:
            self.completer.popup().hide()


class FindReplaceDialog(QDialog):
    """Find and Replace dialog."""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Find and Replace")
        self.setModal(False)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Find row
        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("Find:"))
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Search text...")
        self.find_input.returnPressed.connect(self.find_next)
        find_layout.addWidget(self.find_input)
        layout.addLayout(find_layout)

        # Replace row
        replace_layout = QHBoxLayout()
        replace_layout.addWidget(QLabel("Replace:"))
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replace with...")
        replace_layout.addWidget(self.replace_input)
        layout.addLayout(replace_layout)

        # Options
        options_layout = QHBoxLayout()
        self.case_sensitive = QCheckBox("Case sensitive")
        self.whole_word = QCheckBox("Whole word")
        options_layout.addWidget(self.case_sensitive)
        options_layout.addWidget(self.whole_word)
        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        self.find_btn = QPushButton("Find Next")
        self.find_btn.clicked.connect(self.find_next)
        btn_layout.addWidget(self.find_btn)

        self.find_prev_btn = QPushButton("Find Previous")
        self.find_prev_btn.clicked.connect(self.find_previous)
        btn_layout.addWidget(self.find_prev_btn)

        self.replace_btn = QPushButton("Replace")
        self.replace_btn.clicked.connect(self.replace)
        btn_layout.addWidget(self.replace_btn)

        self.replace_all_btn = QPushButton("Replace All")
        self.replace_all_btn.clicked.connect(self.replace_all)
        btn_layout.addWidget(self.replace_all_btn)

        layout.addLayout(btn_layout)

        # Result label
        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: #888;")
        layout.addWidget(self.result_label)

        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #252525;
                color: #cccccc;
            }
            QLabel {
                color: #cccccc;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px;
            }
            QLineEdit:focus {
                border-color: #e95420;
            }
            QCheckBox {
                color: #cccccc;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #555;
                border-radius: 3px;
                background: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background-color: #e95420;
                border-color: #e95420;
            }
            QPushButton {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: rgba(233, 84, 32, 0.7);
            }
        """)

    def find_next(self):
        self._find(forward=True)

    def find_previous(self):
        self._find(forward=False)

    def _find(self, forward=True):
        text = self.find_input.text()
        if not text:
            return

        flags = QTextDocument.FindFlags()
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
        if self.case_sensitive.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.whole_word.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords

        found = self.editor.find(text, flags)

        if not found:
            # Wrap around
            cursor = self.editor.textCursor()
            if forward:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.End)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(text, flags)

        if found:
            self.result_label.setText("Found")
            self.result_label.setStyleSheet("color: #77b255;")
        else:
            self.result_label.setText("Not found")
            self.result_label.setStyleSheet("color: #e74c3c;")

    def replace(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_input.text())
        self.find_next()

    def replace_all(self):
        text = self.find_input.text()
        replacement = self.replace_input.text()
        if not text:
            return

        content = self.editor.toPlainText()

        if self.case_sensitive.isChecked():
            if self.whole_word.isChecked():
                pattern = r'\b' + re.escape(text) + r'\b'
                new_content, count = re.subn(pattern, replacement, content)
            else:
                new_content = content.replace(text, replacement)
                count = content.count(text)
        else:
            if self.whole_word.isChecked():
                pattern = r'\b' + re.escape(text) + r'\b'
                new_content, count = re.subn(pattern, replacement, content, flags=re.IGNORECASE)
            else:
                pattern = re.escape(text)
                new_content, count = re.subn(pattern, replacement, content, flags=re.IGNORECASE)

        if count > 0:
            self.editor.setPlainText(new_content)
            self.result_label.setText(f"Replaced {count} occurrence(s)")
            self.result_label.setStyleSheet("color: #77b255;")
        else:
            self.result_label.setText("No matches found")
            self.result_label.setStyleSheet("color: #e74c3c;")


class ESP32FileBrowser(QMainWindow):
    """VSCode-style file browser for CalSci with integrated editor."""

    def __init__(self, port, bridge, parent=None):
        super().__init__(parent)
        self.port = port
        self.bridge = bridge
        self.flasher = None
        self._device_connected = False
        self._all_files = []  # Store all files for filtering
        self._all_dirs = []   # Store all dirs for filtering
        self._all_modules = []
        self._scan_cache = None
        self._scan_cache_time = 0.0
        self._pending_expand_paths = None
        self._pending_selected_path = None

        self.open_files = {}
        self.find_dialog = None
        self._log_panel_sizes = None
        self._log_collapsed = False
        self._normal_size = QSize(1200, 800)
        self._lock_resize = False

        # Track the file that was last run with Save & Run
        # Used to detect when user switches to a different file
        self._last_run_file = None
        self._needs_main_restore = False  # Flag to restore main.py on reconnect

        self.setWindowTitle("CalSci File Browser")
        self.setMinimumSize(self._normal_size)
        self.resize(self._normal_size)

        self._build_ui()
        self._apply_stylesheet()
        self._setup_shortcuts()

        self.bridge.file_tree_loaded_signal.connect(self._on_tree_loaded)
        self.bridge.file_content_loaded_signal.connect(self._on_file_content_loaded)
        self.bridge.file_upload_complete_signal.connect(self._on_upload_complete)
        self.bridge.scan_triggered_signal.connect(lambda: self._scan_device_preserve(force=True))
        self.bridge.status_message_signal.connect(self._on_status_message)
        self.bridge.run_log_signal.connect(self._on_run_log)
        self.bridge.run_complete_signal.connect(self._on_run_complete)

        # Start device status monitoring
        self.device_timer = QTimer()
        self.device_timer.timeout.connect(self._check_device_status)
        self.device_timer.start(2000)  # Check every 2 seconds
        self._check_device_status()  # Initial check

        self.file_tree.itemExpanded.connect(self._on_tree_item_expanded)
        self._scan_device()

    def resizeEvent(self, event):
        if not self.isMaximized() and not self.isFullScreen():
            if not self._lock_resize and self.size() != self._normal_size:
                self._lock_resize = True
                self.resize(self._normal_size)
                self._lock_resize = False
                return
        super().resizeEvent(event)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Save shortcut
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._save_and_upload)

        # Find shortcut
        find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        find_shortcut.activated.connect(self._show_find_dialog)

        # Find/Replace shortcut
        replace_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        replace_shortcut.activated.connect(self._show_find_dialog)

        # Close tab shortcut
        close_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        close_shortcut.activated.connect(self._close_current_tab)

        # Refresh shortcut
        refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        refresh_shortcut.activated.connect(self._scan_device)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Header with device status
        header = QFrame()
        header.setFixedHeight(36)
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 12, 4)

        self.device_label = QLabel("Checking device...")
        self.device_label.setObjectName("deviceLabel")
        header_layout.addWidget(self.device_label)

        header_layout.addStretch()

        # Breadcrumb / path display
        self.path_label = QLabel("CalSci:/")
        self.path_label.setObjectName("pathLabel")
        header_layout.addWidget(self.path_label)

        header_layout.addStretch()

        main_layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")

        # Left panel - Explorer
        left_panel = QWidget()
        left_panel.setObjectName("explorerPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Explorer header with title and toolbar
        explorer_header = QFrame()
        explorer_header.setObjectName("explorerHeader")
        explorer_header_layout = QHBoxLayout(explorer_header)
        explorer_header_layout.setContentsMargins(12, 6, 8, 6)
        explorer_header_layout.setSpacing(4)

        tree_label = QLabel("EXPLORER")
        tree_label.setObjectName("sectionLabel")
        explorer_header_layout.addWidget(tree_label)

        explorer_header_layout.addStretch()

        # Toolbar buttons
        self.new_file_btn = QToolButton()
        self.new_file_btn.setText("📄")
        self.new_file_btn.setToolTip("New File (on CalSci)")
        self.new_file_btn.setObjectName("toolBtn")
        self.new_file_btn.clicked.connect(self._new_file)
        explorer_header_layout.addWidget(self.new_file_btn)

        self.new_folder_btn = QToolButton()
        self.new_folder_btn.setText("📁")
        self.new_folder_btn.setToolTip("New Folder (on CalSci)")
        self.new_folder_btn.setObjectName("toolBtn")
        self.new_folder_btn.clicked.connect(self._new_folder)
        explorer_header_layout.addWidget(self.new_folder_btn)

        self.collapse_btn = QToolButton()
        self.collapse_btn.setText("⊟")
        self.collapse_btn.setToolTip("Collapse All")
        self.collapse_btn.setObjectName("toolBtn")
        self.collapse_btn.clicked.connect(self._collapse_all)
        explorer_header_layout.addWidget(self.collapse_btn)

        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("↻")
        self.refresh_btn.setToolTip("Refresh (F5)")
        self.refresh_btn.setObjectName("toolBtn")
        self.refresh_btn.clicked.connect(lambda: self._scan_device(force=True))
        explorer_header_layout.addWidget(self.refresh_btn)

        left_layout.addWidget(explorer_header)

        # Search/filter box
        search_frame = QFrame()
        search_frame.setObjectName("searchFrame")
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(8, 4, 8, 4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter files...")
        self.search_input.setObjectName("searchInput")
        self.search_input.textChanged.connect(self._filter_tree)
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)

        left_layout.addWidget(search_frame)

        # File tree
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setObjectName("fileTree")
        self.file_tree.setAnimated(True)
        self.file_tree.setIndentation(16)
        self.file_tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self.file_tree.itemClicked.connect(self._on_tree_single_click)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        self.file_tree.setExpandsOnDoubleClick(False)
        left_layout.addWidget(self.file_tree)

        splitter.addWidget(left_panel)

        # Right panel - Editor area
        right_panel = QWidget()
        right_panel.setObjectName("editorPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Splitter for editor and log panel
        self.editor_splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor_splitter.setObjectName("editorSplitter")

        # Tab widget for open files
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("editorTabs")
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        # Note: currentChanged signal connected after all widgets are created (see below)
        self.editor_splitter.addWidget(self.tab_widget)

        # Log panel (collapsible)
        self.log_panel = QFrame()
        self.log_panel.setObjectName("logPanel")
        log_layout = QVBoxLayout(self.log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(0)

        # Log header with title and buttons
        self.log_header = QFrame()
        self.log_header.setObjectName("logHeader")
        log_header_layout = QHBoxLayout(self.log_header)
        log_header_layout.setContentsMargins(12, 4, 8, 4)

        log_title = QLabel("OUTPUT")
        log_title.setObjectName("sectionLabel")
        log_header_layout.addWidget(log_title)

        log_header_layout.addStretch()

        self.clear_log_btn = QToolButton()
        self.clear_log_btn.setText("🗑")
        self.clear_log_btn.setToolTip("Clear Log")
        self.clear_log_btn.setObjectName("toolBtn")
        self.clear_log_btn.clicked.connect(self._clear_log)
        log_header_layout.addWidget(self.clear_log_btn)

        self.toggle_log_btn = QToolButton()
        self.toggle_log_btn.setText("▼")
        self.toggle_log_btn.setToolTip("Toggle Log Panel")
        self.toggle_log_btn.setObjectName("toolBtn")
        self.toggle_log_btn.clicked.connect(self._toggle_log_panel)
        log_header_layout.addWidget(self.toggle_log_btn)

        log_layout.addWidget(self.log_header)

        # Log text area
        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(1000)  # Limit log lines
        log_layout.addWidget(self.log_output)

        self.editor_splitter.addWidget(self.log_panel)
        self.editor_splitter.setSizes([600, 200])  # Editor gets more space initially

        right_layout.addWidget(self.editor_splitter)

        # Welcome tab when no file is open
        self.welcome_widget = QWidget()
        welcome_layout = QVBoxLayout(self.welcome_widget)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        welcome_label = QLabel("CalSci File Browser")
        welcome_label.setObjectName("welcomeTitle")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(welcome_label)

        welcome_subtitle = QLabel("Double-click a file in the explorer to open it")
        welcome_subtitle.setObjectName("welcomeSubtitle")
        welcome_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(welcome_subtitle)

        shortcuts_label = QLabel(
            "Keyboard Shortcuts:\n"
            "Ctrl+S - Save & Upload\n"
            "Ctrl+F - Find\n"
            "Ctrl+H - Find & Replace\n"
            "Ctrl+W - Close Tab\n"
            "F5 - Refresh"
        )
        shortcuts_label.setObjectName("welcomeShortcuts")
        shortcuts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(shortcuts_label)

        self.tab_widget.addTab(self.welcome_widget, "Welcome")

        # Action bar at bottom
        action_bar = QFrame()
        action_bar.setObjectName("actionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(12, 8, 12, 8)
        action_layout.setSpacing(8)

        self.status_label = QLabel("No file open")
        self.status_label.setObjectName("statusLabel")
        action_layout.addWidget(self.status_label)

        action_layout.addStretch()

        # Word wrap toggle
        self.word_wrap_btn = QPushButton("Word Wrap: Off")
        self.word_wrap_btn.setObjectName("toggleBtn")
        self.word_wrap_btn.setCheckable(True)
        self.word_wrap_btn.clicked.connect(self._toggle_word_wrap)
        action_layout.addWidget(self.word_wrap_btn)

        # Find button
        self.find_btn = QPushButton("🔍 Find")
        self.find_btn.setObjectName("actionBtn")
        self.find_btn.clicked.connect(self._show_find_dialog)
        action_layout.addWidget(self.find_btn)

        self.save_upload_btn = QPushButton("💾 Save & Upload")
        self.save_upload_btn.setObjectName("saveBtn")
        self.save_upload_btn.setEnabled(False)
        self.save_upload_btn.clicked.connect(self._save_and_upload)
        action_layout.addWidget(self.save_upload_btn)

        self.save_run_btn = QPushButton("▶ Save & Run")
        self.save_run_btn.setObjectName("runBtn")
        self.save_run_btn.setEnabled(False)
        self.save_run_btn.clicked.connect(self._save_and_run)
        action_layout.addWidget(self.save_run_btn)

        self.revert_btn = QPushButton("↶ Revert")
        self.revert_btn.setObjectName("revertBtn")
        self.revert_btn.setEnabled(False)
        self.revert_btn.clicked.connect(self._revert_current)
        action_layout.addWidget(self.revert_btn)

        right_layout.addWidget(action_bar)

        splitter.addWidget(right_panel)
        splitter.setSizes([280, 920])

        main_layout.addWidget(splitter)

        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")

        # Connect tab changed signal after all widgets are created
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                color: #d0d0d0;
                font-family: 'Fira Sans', 'Noto Sans', 'DejaVu Sans', sans-serif;
                font-size: 12px;
            }
            QWidget {
                color: #d0d0d0;
                font-family: 'Fira Sans', 'Noto Sans', 'DejaVu Sans', sans-serif;
            }

            QFrame#header {
                background-color: #151515;
                border-bottom: 1px solid #2b2b2b;
            }

            QLabel#deviceLabel {
                color: #77b255;
                font-size: 12px;
                font-weight: 600;
            }

            QLabel#pathLabel {
                color: #a0a0a0;
                font-size: 11px;
            }

            QWidget#explorerPanel {
                background-color: #1e1e1e;
            }

            QFrame#explorerHeader {
                background-color: #161616;
                border-bottom: 1px solid #262626;
            }

            QLabel#sectionLabel {
                color: #888;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }

            QToolButton#toolBtn {
                background-color: transparent;
                color: #9a9a9a;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 12px;
            }
            QToolButton#toolBtn:hover {
                background-color: #262626;
                border-color: #303030;
                color: #e95420;
            }
            QToolButton#toolBtn:pressed {
                background-color: rgba(233, 84, 32, 0.35);
            }

            QFrame#searchFrame {
                background-color: #1e1e1e;
                border-bottom: 1px solid #2a2a2a;
            }

            QLineEdit#searchInput {
                background-color: #252525;
                color: #d0d0d0;
                border: 1px solid #303030;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                selection-background-color: rgba(233, 84, 32, 0.35);
            }
            QLineEdit#searchInput:focus {
                border-color: #e95420;
            }
            QLineEdit#searchInput::placeholder {
                color: #666;
            }

            QTreeWidget#fileTree {
                background-color: #1e1e1e;
                color: #cfcfcf;
                border: none;
                font-size: 13px;
                outline: none;
            }
            QTreeWidget#fileTree::item {
                padding: 4px 6px;
                border-radius: 3px;
            }
            QTreeWidget#fileTree::item:hover {
                background-color: #242424;
            }
            QTreeWidget#fileTree::item:selected {
                background-color: #2b2b2b;
                color: #ffffff;
                border-left: 2px solid #e95420;
            }
            QTreeWidget#fileTree::branch:has-children:!has-siblings:closed,
            QTreeWidget#fileTree::branch:closed:has-children:has-siblings {
                border-image: none;
                image: url(none);
            }
            QTreeWidget#fileTree::branch:open:has-children:!has-siblings,
            QTreeWidget#fileTree::branch:open:has-children:has-siblings {
                border-image: none;
                image: url(none);
            }

            QWidget#editorPanel {
                background-color: #1e1e1e;
            }

            QTabWidget#editorTabs::pane {
                border: none;
                background-color: #1e1e1e;
            }
            QTabWidget#editorTabs QTabBar {
                background-color: #141414;
            }
            QTabWidget#editorTabs QTabBar::tab {
                background-color: #1b1b1b;
                color: #9a9a9a;
                padding: 7px 16px;
                border: none;
                border-right: 1px solid #131313;
                border-top: 2px solid transparent;
                font-size: 12px;
                min-width: 80px;
            }
            QTabWidget#editorTabs QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #f0f0f0;
                border-top: 2px solid #e95420;
            }
            QTabWidget#editorTabs QTabBar::tab:hover:!selected {
                background-color: #242424;
                color: #d0d0d0;
            }
            QTabWidget#editorTabs QTabBar::close-button {
                image: none;
                subcontrol-position: right;
            }
            QTabWidget#editorTabs QTabBar::close-button:hover {
                background-color: rgba(233, 84, 32, 0.5);
            }

            QPlainTextEdit, CodeEditor {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                selection-background-color: rgba(233, 84, 32, 0.35);
            }

            QLabel#welcomeTitle {
                color: #e95420;
                font-size: 28px;
                font-weight: 700;
                margin-bottom: 10px;
            }
            QLabel#welcomeSubtitle {
                color: #888;
                font-size: 14px;
                margin-bottom: 20px;
            }
            QLabel#welcomeShortcuts {
                color: #666;
                font-size: 12px;
                font-family: 'Consolas', monospace;
            }

            QFrame#actionBar {
                background-color: #151515;
                border-top: 1px solid #262626;
            }

            QLabel#statusLabel {
                color: #9a9a9a;
                font-size: 11px;
            }

            QPushButton#saveBtn, QPushButton#actionBtn {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#saveBtn:hover, QPushButton#actionBtn:hover {
                background-color: rgba(233, 84, 32, 0.7);
            }
            QPushButton#saveBtn:disabled, QPushButton#actionBtn:disabled {
                background-color: rgba(85, 85, 85, 0.3);
                color: #555;
                border-color: rgba(85, 85, 85, 0.5);
            }

            QPushButton#runBtn {
                background-color: rgba(46, 204, 113, 0.5);
                color: #ffffff;
                border: 1px solid rgba(46, 204, 113, 0.8);
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#runBtn:hover {
                background-color: rgba(46, 204, 113, 0.7);
            }
            QPushButton#runBtn:disabled {
                background-color: rgba(85, 85, 85, 0.3);
                color: #555;
                border-color: rgba(85, 85, 85, 0.5);
            }

            QPushButton#revertBtn, QPushButton#toggleBtn {
                background-color: rgba(60, 60, 60, 0.5);
                color: #aaa;
                border: 1px solid rgba(100, 100, 100, 0.5);
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton#revertBtn:hover, QPushButton#toggleBtn:hover {
                background-color: rgba(233, 84, 32, 0.4);
                color: #fff;
                border-color: rgba(233, 84, 32, 0.6);
            }
            QPushButton#revertBtn:disabled, QPushButton#toggleBtn:disabled {
                background-color: rgba(40, 40, 40, 0.3);
                color: #444;
                border-color: rgba(60, 60, 60, 0.3);
            }
            QPushButton#toggleBtn:checked {
                background-color: rgba(233, 84, 32, 0.5);
                color: #fff;
                border-color: rgba(233, 84, 32, 0.8);
            }

            QStatusBar {
                background-color: #e95420;
                color: #ffffff;
                font-size: 11px;
                padding: 2px 8px;
            }

            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background-color: #3a3a3a;
                min-height: 30px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #555;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                background-color: #1e1e1e;
                height: 10px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background-color: #3a3a3a;
                min-width: 30px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #555;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }

            QMenu {
                background-color: #252525;
                color: #cccccc;
                border: 1px solid #3a3a3a;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: rgba(233, 84, 32, 0.5);
            }
            QMenu::separator {
                height: 1px;
                background-color: #3a3a3a;
                margin: 4px 8px;
            }

            QSplitter::handle {
                background-color: #333;
            }
            QSplitter::handle:horizontal {
                width: 2px;
            }
            QSplitter::handle:vertical {
                height: 2px;
            }
            QSplitter::handle:hover {
                background-color: #e95420;
            }

            QFrame#logPanel {
                background-color: #171717;
                border-top: 1px solid #262626;
            }

            QFrame#logHeader {
                background-color: #151515;
                border-bottom: 1px solid #262626;
            }

            QPlainTextEdit#logOutput {
                background-color: #101010;
                color: #d4d4d4;
                border: none;
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 8px;
            }

            QMessageBox {
                background-color: #252525;
            }
            QMessageBox QLabel {
                color: #cccccc;
            }
            QMessageBox QPushButton {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 4px;
                padding: 6px 20px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: rgba(233, 84, 32, 0.7);
            }

            QInputDialog {
                background-color: #252525;
            }
            QInputDialog QLabel {
                color: #cccccc;
            }
            QInputDialog QLineEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px;
            }
            QInputDialog QPushButton {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 4px;
                padding: 6px 20px;
            }
        """)

    def _check_device_status(self):
        """Periodically check if device is still connected."""
        ports = find_esp32_ports()
        is_connected = self.port in ports

        if is_connected != self._device_connected:
            self._device_connected = is_connected

            if is_connected:
                self.device_label.setText(f"● Connected: {self.port}")
                self.device_label.setStyleSheet("color: #77b255; font-size: 12px; font-weight: 600;")
            else:
                self.device_label.setText(f"⚠ Disconnected: {self.port}")
                self.device_label.setStyleSheet("color: #e74c3c; font-size: 12px; font-weight: 600;")
                self.status_bar.showMessage("Device disconnected")
                # Close flasher on disconnect
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                    self.flasher = None

    def _get_flasher(self):
        """Get or create a persistent MicroPyFlasher instance for speed optimization."""
        if self.flasher is None:
            try:
                self.flasher = MicroPyFlasher(self.port)
            except Exception as e:
                raise Exception(f"Failed to connect to CalSci: {e}")
        return self.flasher

    def _ensure_raw_repl(self, flasher):
        """Keep raw REPL open for faster repeated reads."""
        try:
            if flasher and not flasher.is_raw_repl():
                flasher.enter_raw_repl()
        except Exception:
            pass

    def _scan_device(self, force=False):
        self.status_bar.showMessage("Scanning device...")
        self.refresh_btn.setEnabled(False)

        if not force and self._scan_cache and (time.time() - self._scan_cache_time) < 5.0:
            files, dirs, modules = self._scan_cache
            self.bridge.file_tree_loaded_signal.emit(files, dirs, modules)
            self.refresh_btn.setEnabled(True)
            return

        def run():
            try:
                start_time = time.time()
                flasher = self._get_flasher()

                # If we need to restore main.py (after a Save & Run), do it now
                if self._needs_main_restore:
                    self.bridge.run_log_signal.emit("🔧 Restoring original main.py...", "info")
                    try:
                        flasher.restore_main_py(log_func=lambda msg, typ: self.bridge.run_log_signal.emit(msg, typ))
                        self._needs_main_restore = False
                        self._last_run_file = None
                    except Exception as e:
                        self.bridge.run_log_signal.emit(f"⚠ Could not restore main.py: {e}", "warning")

                # Full scan in one operation (raw REPL kept open for speed)
                self._ensure_raw_repl(flasher)
                files, dirs, modules = flasher.scan_device_fast_raw(timeout=30.0, stall_timeout=5.0)
                self._scan_cache = (files, dirs, modules)
                self._scan_cache_time = time.time()
                duration = time.time() - start_time
                self.bridge.status_message_signal.emit(
                    f"Scan complete: {len(files)} files, {len(dirs)} dirs in {duration:.1f}s"
                )
                # Don't close - reuse for next operation

                self.bridge.file_tree_loaded_signal.emit(files, dirs, modules)
            except Exception as e:
                # On error, reset flasher for next attempt
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                    self.flasher = None
                self.bridge.status_message_signal.emit(f"Error scanning: {str(e)[:50]}")
                self.bridge.file_tree_loaded_signal.emit([], [], [])

        threading.Thread(target=run, daemon=True).start()

    def _scan_device_preserve(self, force=False):
        """Scan device while preserving expanded tree state and selection."""
        self._capture_tree_state()
        self._scan_device(force=force)

    def _on_tree_loaded(self, files, dirs, modules):
        # Store for filtering
        self._all_files = files
        self._all_dirs = dirs
        self._all_modules = modules

        self.file_tree.setUpdatesEnabled(False)
        try:
            self._populate_tree(files, dirs, modules)
            self._restore_tree_state()
        finally:
            self.file_tree.setUpdatesEnabled(True)

        self.status_bar.showMessage(f"Found {len(files)} files")
        self.refresh_btn.setEnabled(True)

    def _populate_tree(self, files, dirs, modules, filter_text=""):
        """Populate the file tree with files, optionally filtered."""
        self.file_tree.clear()

        # Filter files if search text provided
        if filter_text:
            filter_lower = filter_text.lower()
            files = [f for f in files if filter_lower in f.lower()]

        user_files_root = QTreeWidgetItem(self.file_tree)
        user_files_root.setText(0, "📁 CalSci")
        user_files_root.setForeground(0, QColor("#e95420"))
        user_files_root.setData(0, Qt.ItemDataRole.UserRole, None)
        user_files_root.setExpanded(True)

        # Build full tree
        dirs_set = set(dirs)
        files_set = set(files)

        # Filter support: only include matching files and their parents
        if filter_text:
            filter_lower = filter_text.lower()
            files_set = {f for f in files_set if filter_lower in f.lower()}

        def add_parent_dirs(path, target_set):
            if not path or path == "/":
                return
            parts = path.strip("/").split("/")
            cur = ""
            for part in parts[:-1]:
                cur = f"{cur}/{part}" if cur else f"/{part}"
                target_set.add(cur)

        # Ensure all parent dirs exist
        for f in files_set:
            add_parent_dirs(f, dirs_set)
        for d in list(dirs_set):
            add_parent_dirs(d, dirs_set)

        dir_items = {"/": user_files_root}

        def parent_dir(path):
            if path == "/":
                return None
            parts = path.rstrip("/").split("/")
            if len(parts) <= 2:
                return "/"
            return "/".join(parts[:-1])

        for d in sorted(dirs_set, key=lambda p: (p.count("/"), p)):
            if d == "/":
                continue
            parent = parent_dir(d) or "/"
            parent_item = dir_items.get(parent, user_files_root)
            name = d.rsplit("/", 1)[-1]
            folder_item = QTreeWidgetItem()
            folder_item.setText(0, f"📂 {name}")
            folder_item.setForeground(0, QColor("#e95420"))
            folder_item.setData(0, Qt.ItemDataRole.UserRole, f"folder:{d}")
            folder_item.setData(0, Qt.ItemDataRole.UserRole + 1, True)  # already loaded
            parent_item.addChild(folder_item)
            dir_items[d] = folder_item

        for f in sorted(files_set):
            parent = parent_dir(f) or "/"
            parent_item = dir_items.get(parent, user_files_root)
            name = f.rsplit("/", 1)[-1]
            icon = get_file_icon(name)
            file_item = QTreeWidgetItem()
            file_item.setText(0, f"{icon} {name}")
            file_item.setForeground(0, QColor("#d0d0d0"))
            file_item.setData(0, Qt.ItemDataRole.UserRole, f)
            file_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            parent_item.addChild(file_item)

        # Expand folders when filtering
        if filter_text:
            self._expand_all_items(user_files_root)

    def _expand_all_items(self, item):
        """Recursively expand all items."""
        item.setExpanded(True)
        for i in range(item.childCount()):
            self._expand_all_items(item.child(i))

    def _capture_tree_state(self):
        """Capture expanded folders and selected item before refresh."""
        expanded = set()
        selected_path = None

        current_item = self.file_tree.currentItem()
        if current_item:
            path = current_item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(path, str):
                selected_path = path

        def walk(item):
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(path, str) and path.startswith("folder:") and item.isExpanded():
                expanded.add(path)
            for i in range(item.childCount()):
                walk(item.child(i))

        root = self.file_tree.topLevelItem(0)
        if root:
            walk(root)

        self._pending_expand_paths = expanded
        self._pending_selected_path = selected_path

    def _restore_tree_state(self):
        """Restore expanded folders and selected item after refresh."""
        if not self._pending_expand_paths and not self._pending_selected_path:
            return
        expand_set = self._pending_expand_paths or set()
        selected_path = self._pending_selected_path

        def walk(item):
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(path, str):
                if path in expand_set:
                    item.setExpanded(True)
                if selected_path and path == selected_path:
                    self.file_tree.setCurrentItem(item)
            for i in range(item.childCount()):
                walk(item.child(i))

        root = self.file_tree.topLevelItem(0)
        if root:
            walk(root)

        self._pending_expand_paths = None
        self._pending_selected_path = None

    def _filter_tree(self, text):
        """Filter the file tree based on search text."""
        if self._scan_cache is None:
            return
        self._populate_tree(self._all_files, self._all_dirs, self._all_modules, text)

    def _collapse_all(self):
        """Collapse all tree items."""
        self.file_tree.collapseAll()
        # Keep root expanded
        root = self.file_tree.topLevelItem(0)
        if root:
            root.setExpanded(True)

    def _on_tree_item_expanded(self, item):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path or not isinstance(path, str):
            return
        if not path.startswith("folder:"):
            return
        if item.data(0, Qt.ItemDataRole.UserRole + 1):
            return
        folder_path = path.replace("folder:", "")
        self.bridge.status_message_signal.emit(f"Loading folder:{folder_path}...")

        load_token = time.time()
        item.setData(0, Qt.ItemDataRole.UserRole + 2, load_token)

        if not folder_path:
            return

        def run():
            try:
                flasher = self._get_flasher()
                # Prefer raw REPL listing for speed; fallback to exec if needed
                try:
                    self._ensure_raw_repl(flasher)
                    files, dirs = flasher.list_dir_raw(folder_path)
                except Exception:
                    try:
                        flasher.exit_raw_repl()
                    except Exception:
                        pass
                    files, dirs = flasher.list_dir_exec(folder_path)
                children = []

                for d in sorted(dirs):
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, f"📂 {d}")
                    folder_item.setForeground(0, QColor("#e95420"))
                    full = folder_path.rstrip("/") + "/" + d
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, f"folder:{full}")
                    folder_item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
                    folder_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                    children.append(folder_item)

                for f in sorted(files):
                    icon = get_file_icon(f)
                    file_item = QTreeWidgetItem()
                    file_item.setText(0, f"{icon} {f}")
                    file_item.setForeground(0, QColor("#d0d0d0"))
                    full = folder_path.rstrip("/") + "/" + f
                    file_item.setData(0, Qt.ItemDataRole.UserRole, full)
                    file_item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                    )
                    children.append(file_item)

                def apply_children():
                    try:
                        if item.data(0, Qt.ItemDataRole.UserRole + 2) != load_token:
                            return
                        item.takeChildren()
                        if not children:
                            empty_item = QTreeWidgetItem()
                            empty_item.setText(0, "  (empty)")
                            empty_item.setForeground(0, QColor("#666"))
                            item.addChild(empty_item)
                        else:
                            for child in children:
                                item.addChild(child)
                        item.setData(0, Qt.ItemDataRole.UserRole + 1, True)
                        item.setExpanded(True)
                        self.bridge.status_message_signal.emit(
                            f"Loaded {len(files)} files, {len(dirs)} folders in {folder_path}"
                        )
                    except RuntimeError:
                        # Item was deleted while loading; ignore.
                        return

                QTimer.singleShot(0, apply_children)
            except Exception as e:
                self.bridge.status_message_signal.emit(f"Error loading {folder_path}: {str(e)[:50]}")

        threading.Thread(target=run, daemon=True).start()

        def on_timeout():
            try:
                if item.data(0, Qt.ItemDataRole.UserRole + 2) != load_token:
                    return
                if item.data(0, Qt.ItemDataRole.UserRole + 1):
                    return
                item.takeChildren()
                timeout_item = QTreeWidgetItem()
                timeout_item.setText(0, "  (timeout)")
                timeout_item.setForeground(0, QColor("#666"))
                item.addChild(timeout_item)
                self.bridge.status_message_signal.emit(f"Timeout loading {folder_path}")
            except RuntimeError:
                # Item was deleted while waiting.
                return

        QTimer.singleShot(20000, on_timeout)

    def _on_tree_single_click(self, item, column):
        """Handle single click - update path label."""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and not path.startswith("builtin:") and not path.startswith("folder:"):
            self.path_label.setText(f"CalSci:{path}")
        elif path and path.startswith("folder:"):
            folder_path = path.replace("folder:", "")
            self.path_label.setText(f"CalSci:{folder_path}/")
        else:
            self.path_label.setText("CalSci:/")

    def _on_tree_double_click(self, item, column):
        path = item.data(0, Qt.ItemDataRole.UserRole)

        if not path or path.startswith("folder:"):
            item.setExpanded(not item.isExpanded())
            return

        if path.startswith("builtin:"):
            module_name = path.replace("builtin:", "")
            QMessageBox.information(
                self,
                "Built-in Module",
                f"'{module_name}' is a built-in firmware module.\n\n"
                f"These modules are compiled into the firmware and cannot be edited."
            )
            return

        self._open_file(path)

    def _open_file(self, path):
        # Remove welcome tab if present
        for i in range(self.tab_widget.count()):
            if self.tab_widget.widget(i) == self.welcome_widget:
                self.tab_widget.removeTab(i)
                break

        # If opening a different file than the last run file, note that system will reset
        if self._last_run_file and self._last_run_file != path:
            self.bridge.run_log_signal.emit(
                f"ℹ️ Opening new file. Previous run ({self._last_run_file.split('/')[-1]}) will be reset on next Save & Run.",
                "info"
            )

        if path in self.open_files:
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) == self.open_files[path]["widget"]:
                    self.tab_widget.setCurrentIndex(i)
                    return

        self.status_bar.showMessage(f"Loading {path}...")

        def run():
            try:
                flasher = self._get_flasher()
                self._ensure_raw_repl(flasher)
                content = flasher.get(path)
                content_hash = hashlib.md5(content.encode()).hexdigest()
                # Don't close - reuse for next operation

                self.bridge.file_content_loaded_signal.emit(path, content, content_hash)
            except Exception as e:
                # On error, reset flasher for next attempt
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                    self.flasher = None
                self.status_bar.showMessage(f"Error loading {path}: {str(e)[:50]}")

        threading.Thread(target=run, daemon=True).start()

    def _on_file_content_loaded(self, path, content, content_hash):
        editor = CodeEditor()
        editor.setPlainText(content)
        editor.textChanged.connect(lambda: self._on_editor_changed(path))
        editor.cursorPositionChanged.connect(self._update_cursor_position)

        filename = path.split("/")[-1]
        icon = get_file_icon(filename)
        tab_index = self.tab_widget.addTab(editor, f"{icon} {filename}")
        self.tab_widget.setCurrentIndex(tab_index)

        self.open_files[path] = {
            "content": content,
            "hash": content_hash,
            "modified": False,
            "widget": editor
        }

        self._update_status(path)
        self._update_buttons()
        self.status_bar.showMessage(f"Loaded {path}")

    def _on_editor_changed(self, path):
        if path not in self.open_files:
            return

        editor = self.open_files[path]["widget"]
        current_content = editor.toPlainText()
        current_hash = hashlib.md5(current_content.encode()).hexdigest()
        original_hash = self.open_files[path]["hash"]

        is_modified = current_hash != original_hash

        if is_modified != self.open_files[path]["modified"]:
            self.open_files[path]["modified"] = is_modified
            self._update_tab_title(path)
            self._update_buttons()

    def _update_tab_title(self, path):
        filename = path.split("/")[-1]
        icon = get_file_icon(filename)
        editor = self.open_files[path]["widget"]

        for i in range(self.tab_widget.count()):
            if self.tab_widget.widget(i) == editor:
                if self.open_files[path]["modified"]:
                    self.tab_widget.setTabText(i, f"● {icon} {filename}")
                else:
                    self.tab_widget.setTabText(i, f"{icon} {filename}")
                break

    def _update_buttons(self):
        current_path = self._get_current_path()

        if current_path and current_path in self.open_files:
            is_modified = self.open_files[current_path]["modified"]
            self.save_upload_btn.setText("💾 Save & Upload")
            self.save_upload_btn.setToolTip("Save and upload to CalSci")
            self.save_upload_btn.setEnabled(is_modified)
            # Save & Run enabled whenever a file is open
            self.save_run_btn.setEnabled(True)
            self.save_run_btn.setToolTip("Save and run on CalSci")
            self.revert_btn.setEnabled(is_modified)
        else:
            self.save_upload_btn.setEnabled(False)
            self.revert_btn.setEnabled(False)
            self.save_run_btn.setEnabled(False)
            self.save_upload_btn.setText("💾 Save & Upload")
            self.save_upload_btn.setToolTip("")
            self.save_run_btn.setToolTip("")

    def _update_status(self, path=None):
        if not path:
            path = self._get_current_path()

        if path and path in self.open_files:
            editor = self.open_files[path]["widget"]
            cursor = editor.textCursor()
            line = cursor.blockNumber() + 1
            col = cursor.columnNumber() + 1

            content = editor.toPlainText()
            size = len(content.encode('utf-8'))
            size_str = f"{size} bytes" if size < 1024 else f"{size/1024:.1f} KB"
            lines = content.count('\n') + 1

            self.status_label.setText(f"{path}  •  {lines} lines  •  {size_str}  •  Ln {line}, Col {col}  •  UTF-8")
            self.path_label.setText(f"CalSci:{path}")
        else:
            self.status_label.setText("No file open")
            self.path_label.setText("CalSci:/")

    def _update_cursor_position(self):
        self._update_status()

    def _get_current_path(self):
        current_widget = self.tab_widget.currentWidget()
        if not current_widget or current_widget == self.welcome_widget:
            return None

        for path, data in self.open_files.items():
            if data["widget"] == current_widget:
                return path

        return None

    def _on_tab_changed(self, index):
        self._update_status()
        self._update_buttons()

    def _close_current_tab(self):
        """Close the current tab (for keyboard shortcut)."""
        index = self.tab_widget.currentIndex()
        if index >= 0:
            self._close_tab(index)

    def _close_tab(self, index):
        widget = self.tab_widget.widget(index)

        if widget == self.welcome_widget:
            return

        path = None
        for p, data in self.open_files.items():
            if data["widget"] == widget:
                path = p
                break

        if not path:
            self.tab_widget.removeTab(index)
            return

        if self.open_files[path]["modified"]:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"'{path.split('/')[-1]}' has unsaved changes.\n\nClose anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        self.tab_widget.removeTab(index)
        del self.open_files[path]

        # Show welcome tab if no files open
        if self.tab_widget.count() == 0:
            self.tab_widget.addTab(self.welcome_widget, "Welcome")
            self._update_status()
            self._update_buttons()

    def _toggle_word_wrap(self, checked):
        """Toggle word wrap in the current editor."""
        current_path = self._get_current_path()
        if current_path and current_path in self.open_files:
            editor = self.open_files[current_path]["widget"]
            if checked:
                editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
                self.word_wrap_btn.setText("Word Wrap: On")
            else:
                editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
                self.word_wrap_btn.setText("Word Wrap: Off")

    def _show_find_dialog(self):
        """Show the find/replace dialog."""
        current_path = self._get_current_path()
        if not current_path or current_path not in self.open_files:
            return

        editor = self.open_files[current_path]["widget"]

        if self.find_dialog is None:
            self.find_dialog = FindReplaceDialog(editor, self)
        else:
            self.find_dialog.editor = editor

        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.find_input.setFocus()
        self.find_dialog.find_input.selectAll()

    def _save_and_upload(self):
        path = self._get_current_path()
        if not path or path not in self.open_files:
            return

        editor = self.open_files[path]["widget"]
        content = editor.toPlainText()

        self.status_bar.showMessage(f"Uploading {path}...")
        self.save_upload_btn.setEnabled(False)

        def run():
            try:
                flasher = self._get_flasher()
                flasher.ensure_dirs(path.lstrip("/"))
                flasher.put_content(path.lstrip("/"), content)
                # Don't close - reuse for next operation

                self.bridge.file_upload_complete_signal.emit(path, True)
            except Exception as e:
                # On error, reset flasher for next attempt
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                    self.flasher = None
                self.status_bar.showMessage(f"Upload failed: {str(e)[:50]}")
                self.save_upload_btn.setEnabled(True)

        threading.Thread(target=run, daemon=True).start()

    def _on_upload_complete(self, path, success):
        if success:
            editor = self.open_files[path]["widget"]
            content = editor.toPlainText()
            new_hash = hashlib.md5(content.encode()).hexdigest()

            self.open_files[path]["content"] = content
            self.open_files[path]["hash"] = new_hash
            self.open_files[path]["modified"] = False

            self._update_tab_title(path)
            self._update_buttons()

            self.status_bar.showMessage(f"✓ Uploaded {path}")
        else:
            self.status_bar.showMessage(f"✗ Upload failed")
            self.save_upload_btn.setEnabled(True)

    def _save_and_run(self):
        """Save the current file (if modified) and run it on the device."""
        path = self._get_current_path()
        if not path or path not in self.open_files:
            return

        if not path.endswith('.py'):
            QMessageBox.warning(self, "Cannot Run", "Only Python files (.py) can be run.")
            return

        # If we're running a different file than before, restore main.py first
        if self._last_run_file and self._last_run_file != path and self.flasher:
            try:
                self.bridge.run_log_signal.emit("🔧 Resetting previous run...", "info")
                self.flasher.restore_main_py()
            except Exception as e:
                self.bridge.run_log_signal.emit(f"⚠ Could not reset: {e}", "warning")

        editor = self.open_files[path]["widget"]
        content = editor.toPlainText()

        self.status_bar.showMessage(f"▶ Save & Run: {path}...")
        self.save_run_btn.setEnabled(False)
        self.save_upload_btn.setEnabled(False)

        # Create log function that emits to signal
        def log_func(message, msg_type="info"):
            self.bridge.run_log_signal.emit(message, msg_type)

        def run():
            try:
                flasher = self._get_flasher()

                # Use the combined save_upload_and_run method
                # This will CLOSE the serial connection so CalSci runs free
                result = flasher.save_upload_and_run(
                    remote_path=path,
                    content=content,
                    timeout=10.0,
                    log_func=log_func
                )

                # Flasher closed the serial, mark it as None
                self.flasher = None

                success = result['upload_success'] and len(result['errors']) == 0
                output = result.get('run_output', '')

                # Track this file as the last run file, and flag for restore on reconnect
                if success:
                    self._last_run_file = path
                    self._needs_main_restore = True

                self.bridge.run_complete_signal.emit(path, success, output)

            except Exception as e:
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                self.flasher = None
                self.bridge.run_log_signal.emit(f"✗ Error: {str(e)}", "error")
                self.bridge.run_complete_signal.emit(path, False, str(e))

        threading.Thread(target=run, daemon=True).start()

    def _on_run_log(self, message, msg_type):
        """Handle log messages from the run process."""
        # Update status bar with latest log
        self.status_bar.showMessage(message)

        # Color-coded output to log panel
        color_map = {
            "info": "#888888",
            "success": "#77b255",
            "error": "#e74c3c",
            "warning": "#f39c12",
            "output": "#d4d4d4"
        }
        color = color_map.get(msg_type, "#d4d4d4")

        # Append to log with color
        self.log_output.appendHtml(f'<span style="color: {color};">{message}</span>')

        # Auto-scroll to bottom
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_log(self):
        """Clear the log output panel."""
        self.log_output.clear()

    def _toggle_log_panel(self):
        """Toggle log panel visibility."""
        if self.log_output.isVisible():
            # Collapse to header-only (VS Code style)
            self._log_panel_sizes = self.editor_splitter.sizes()
            self.log_output.hide()
            self.toggle_log_btn.setText("▲")
            self.toggle_log_btn.setToolTip("Show Log Panel")

            header_h = self.log_header.sizeHint().height()
            collapsed_h = max(header_h + 6, 24)
            self.log_panel.setMinimumHeight(collapsed_h)
            self.log_panel.setMaximumHeight(collapsed_h)

            if self._log_panel_sizes and len(self._log_panel_sizes) == 2:
                total = sum(self._log_panel_sizes)
                self.editor_splitter.setSizes([max(total - collapsed_h, 1), collapsed_h])
            self._log_collapsed = True
        else:
            # Expand to previous size
            self.log_panel.setMinimumHeight(0)
            self.log_panel.setMaximumHeight(16777215)
            self.log_output.show()
            self.toggle_log_btn.setText("▼")
            self.toggle_log_btn.setToolTip("Hide Log Panel")

            if self._log_panel_sizes and len(self._log_panel_sizes) == 2:
                self.editor_splitter.setSizes(self._log_panel_sizes)
            else:
                self.editor_splitter.setSizes([600, 200])
            self._log_collapsed = False

    def _on_run_complete(self, path, success, output):
        """Handle run completion."""
        if success:
            # Update file hash since it was uploaded
            if path in self.open_files:
                editor = self.open_files[path]["widget"]
                content = editor.toPlainText()
                new_hash = hashlib.md5(content.encode()).hexdigest()

                self.open_files[path]["content"] = content
                self.open_files[path]["hash"] = new_hash
                self.open_files[path]["modified"] = False

                self._update_tab_title(path)

            self.status_bar.showMessage(f"✓ CalSci running independently (disconnected)")
        else:
            self.status_bar.showMessage(f"✗ Run failed: {output[:50] if output else 'Unknown error'}")

        self._update_buttons()

    def _revert_current(self):
        path = self._get_current_path()
        if not path or path not in self.open_files:
            return

        reply = QMessageBox.question(
            self,
            "Revert Changes",
            f"Revert '{path.split('/')[-1]}' to last saved version?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        original_content = self.open_files[path]["content"]
        editor = self.open_files[path]["widget"]

        editor.blockSignals(True)
        editor.setPlainText(original_content)
        editor.blockSignals(False)

        self.open_files[path]["modified"] = False
        self._update_tab_title(path)
        self._update_buttons()

        self.status_bar.showMessage(f"Reverted {path}")

    def _on_status_message(self, message):
        """Handle status bar messages from background threads."""
        self.status_bar.showMessage(message)

    def _new_file(self):
        """Create a new file on CalSci."""
        # Get current folder from selection
        item = self.file_tree.currentItem()
        base_path = "/"

        if item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                if path.startswith("folder:"):
                    base_path = path.replace("folder:", "") + "/"
                elif not path.startswith("builtin:"):
                    # It's a file, get its directory
                    base_path = "/" + "/".join(path.strip("/").split("/")[:-1])
                    if base_path != "/":
                        base_path += "/"

        filename, ok = QInputDialog.getText(
            self,
            "New File",
            f"Enter filename (will be created in {base_path}):",
            text="new_file.py"
        )

        if not ok or not filename:
            return

        full_path = base_path + filename

        self.status_bar.showMessage(f"Creating {full_path}...")

        def run():
            try:
                flasher = self._get_flasher()
                flasher.ensure_dirs(full_path.lstrip("/"))
                flasher.put_content(full_path.lstrip("/"), "")
                # Use signals for thread-safe Qt operations
                self.bridge.status_message_signal.emit(f"✓ Created {full_path}")
                self.bridge.scan_triggered_signal.emit()
            except Exception as e:
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                    self.flasher = None
                self.bridge.status_message_signal.emit(f"Error: {str(e)[:50]}")

        threading.Thread(target=run, daemon=True).start()

    def _new_folder(self):
        """Create a new folder on CalSci."""
        # Get current folder from selection
        item = self.file_tree.currentItem()
        base_path = "/"

        if item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                if path.startswith("folder:"):
                    base_path = path.replace("folder:", "") + "/"
                elif not path.startswith("builtin:"):
                    # It's a file, get its directory
                    base_path = "/" + "/".join(path.strip("/").split("/")[:-1])
                    if base_path != "/":
                        base_path += "/"

        foldername, ok = QInputDialog.getText(
            self,
            "New Folder",
            f"Enter folder name (will be created in {base_path}):",
            text="new_folder"
        )

        if not ok or not foldername:
            return

        full_path = base_path + foldername

        self.status_bar.showMessage(f"Creating folder {full_path}...")

        def run():
            try:
                flasher = self._get_flasher()
                # Create folder by creating a .keep file inside it
                flasher.ensure_dirs((full_path + "/.keep").lstrip("/"))
                flasher.put_content((full_path + "/.keep").lstrip("/"), "")
                # Use signals for thread-safe Qt operations
                self.bridge.status_message_signal.emit(f"✓ Created folder {full_path}")
                self.bridge.scan_triggered_signal.emit()
            except Exception as e:
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                    self.flasher = None
                self.bridge.status_message_signal.emit(f"Error: {str(e)[:50]}")

        threading.Thread(target=run, daemon=True).start()

    def _show_tree_context_menu(self, position):
        item = self.file_tree.itemAt(position)
        if not item:
            # Context menu for empty area - show new file/folder
            menu = QMenu(self)
            new_file_action = menu.addAction("📄 New File")
            new_folder_action = menu.addAction("📁 New Folder")
            menu.addSeparator()
            refresh_action = menu.addAction("↻ Refresh")

            action = menu.exec(self.file_tree.mapToGlobal(position))

            if action == new_file_action:
                self._new_file()
            elif action == new_folder_action:
                self._new_folder()
            elif action == refresh_action:
                self._scan_device(force=True)
            return

        path = item.data(0, Qt.ItemDataRole.UserRole)

        if not path or path.startswith("builtin:"):
            return

        menu = QMenu(self)

        if path.startswith("folder:"):
            # Folder context menu
            folder_path = path.replace("folder:", "")

            new_file_action = menu.addAction("📄 New File Here")
            new_folder_action = menu.addAction("📁 New Folder Here")
            menu.addSeparator()
            copy_path_action = menu.addAction("📋 Copy Path")
            menu.addSeparator()
            delete_action = menu.addAction("🗑️ Delete Folder")

            action = menu.exec(self.file_tree.mapToGlobal(position))

            if action == new_file_action:
                self._new_file()
            elif action == new_folder_action:
                self._new_folder()
            elif action == copy_path_action:
                QApplication.clipboard().setText(folder_path)
                self.status_bar.showMessage(f"Copied: {folder_path}")
            elif action == delete_action:
                self._delete_folder_from_tree(folder_path)
        else:
            # File context menu
            open_action = menu.addAction("📂 Open")
            menu.addSeparator()
            rename_action = menu.addAction("✏️ Rename")
            copy_path_action = menu.addAction("📋 Copy Path")
            menu.addSeparator()
            delete_action = menu.addAction("🗑️ Delete")

            action = menu.exec(self.file_tree.mapToGlobal(position))

            if action == open_action:
                self._open_file(path)
            elif action == rename_action:
                self._rename_file(path)
            elif action == copy_path_action:
                QApplication.clipboard().setText(path)
                self.status_bar.showMessage(f"Copied: {path}")
            elif action == delete_action:
                self._delete_file_from_tree(path)

    def _rename_file(self, path):
        """Rename a file on CalSci."""
        old_name = path.split("/")[-1]
        dir_path = "/".join(path.split("/")[:-1])
        if not dir_path:
            dir_path = "/"

        new_name, ok = QInputDialog.getText(
            self,
            "Rename File",
            "Enter new filename:",
            text=old_name
        )

        if not ok or not new_name or new_name == old_name:
            return

        new_path = dir_path + "/" + new_name if dir_path != "/" else "/" + new_name

        self.status_bar.showMessage(f"Renaming {path} to {new_path}...")

        def run():
            try:
                flasher = self._get_flasher()
                self._ensure_raw_repl(flasher)
                # Read old content
                content = flasher.get(path)
                # Create new file
                flasher.put_content(new_path.lstrip("/"), content)
                # Delete old file
                flasher.delete_file(path)

                # Update open files if this file was open
                if path in self.open_files:
                    data = self.open_files[path]
                    del self.open_files[path]
                    self.open_files[new_path] = data
                    self._update_tab_title(new_path)

                self.status_bar.showMessage(f"✓ Renamed to {new_path}")
                self._scan_device_preserve(force=True)
            except Exception as e:
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                    self.flasher = None
                self.status_bar.showMessage(f"Error: {str(e)[:50]}")

        threading.Thread(target=run, daemon=True).start()

    def _delete_file_from_tree(self, path):
        reply = QMessageBox.question(
            self,
            "Delete File",
            f"Permanently delete '{path}' from CalSci?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage(f"Deleting {path}...")

        def run():
            try:
                flasher = self._get_flasher()
                success = flasher.delete_file(path)
                # Don't close - reuse for next operation

                if success:
                    if path in self.open_files:
                        editor = self.open_files[path]["widget"]
                        for i in range(self.tab_widget.count()):
                            if self.tab_widget.widget(i) == editor:
                                self.tab_widget.removeTab(i)
                                break
                        del self.open_files[path]

                    self.status_bar.showMessage(f"✓ Deleted {path}")
                    self._scan_device_preserve(force=True)
                else:
                    self.status_bar.showMessage(f"✗ Delete failed")
            except Exception as e:
                # On error, reset flasher for next attempt
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                    self.flasher = None
                self.status_bar.showMessage(f"Error: {str(e)[:50]}")

        threading.Thread(target=run, daemon=True).start()

    def _delete_folder_from_tree(self, folder_path):
        """Delete a folder and its contents from CalSci."""
        reply = QMessageBox.question(
            self,
            "Delete Folder",
            f"Permanently delete '{folder_path}' and all its contents from CalSci?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage(f"Deleting folder {folder_path}...")

        def run():
            try:
                flasher = self._get_flasher()

                # Close any open files under this folder
                for file_path in list(self.open_files.keys()):
                    if file_path.startswith(folder_path + "/"):
                        editor = self.open_files[file_path]["widget"]
                        for i in range(self.tab_widget.count()):
                            if self.tab_widget.widget(i) == editor:
                                self.tab_widget.removeTab(i)
                                break
                        del self.open_files[file_path]

                # Remove folder recursively on device
                flasher.remove_dir(folder_path)

                self.status_bar.showMessage(f"✓ Deleted folder {folder_path}")
                self._scan_device_preserve(force=True)
            except Exception as e:
                if self.flasher:
                    try:
                        self.flasher.close()
                    except:
                        pass
                    self.flasher = None
                self.status_bar.showMessage(f"Error: {str(e)[:50]}")

        threading.Thread(target=run, daemon=True).start()

    def closeEvent(self, event):
        unsaved = [path for path, data in self.open_files.items() if data["modified"]]

        if unsaved:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"{len(unsaved)} file(s) have unsaved changes.\n\nClose anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # Stop device monitoring timer
        if hasattr(self, 'device_timer'):
            self.device_timer.stop()

        # Close find dialog if open
        if self.find_dialog:
            self.find_dialog.close()

        # Close persistent flasher connection
        if self.flasher:
            try:
                self.flasher.close()
            except:
                pass
            self.flasher = None

        event.accept()
