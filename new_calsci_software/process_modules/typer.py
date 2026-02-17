import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

# from data_modules.object_handler import test_deep_sleep_awake
from sleeping_features import test_deep_sleep_awake, swdt
import time
import machine
from machine import Pin

try:
    import esp32
except Exception:
    esp32 = None


class Typer:
    def __init__(self, keypad, keypad_map):
        self.keypad = keypad
        self.keypad_map = keypad_map
        self.debounce_delay_time = 0.2
        self.min_debounce_delay_time = 0.12
        self._switch_latched_key = None
        self._alpha_row = 0
        self._alpha_col = 1
        self._plus_key = self._find_key_coord("+")
        self._minus_key = self._find_key_coord("-")

    def _decode_partition_field(self, value):
        if isinstance(value, bytes):
            try:
                return value.decode()
            except Exception:
                return None
        if isinstance(value, str):
            return value
        return None

    def _partition_by_label(self, label):
        # Fast path for firmwares where Partition(label) is supported.
        try:
            return esp32.Partition(label)
        except Exception:
            pass

        # Fallback: scan app partitions and match label from info().
        try:
            parts = esp32.Partition.find(esp32.Partition.TYPE_APP)
        except Exception:
            return None

        for part in parts:
            try:
                info = part.info()
            except Exception:
                continue
            fields = info if isinstance(info, (tuple, list)) else (info,)
            for field in fields:
                if self._decode_partition_field(field) == label:
                    return part
        return None

    def _switch_to_partition(self, label, name):
        if esp32 is None:
            print("esp32 partition API not available")
            return
        try:
            part = self._partition_by_label(label)
            if part is None:
                print("firmware switch failed: partition not found:", label)
                return
            part.set_boot()
            print("Next boot:", name, "(", label, ")", sep="")
            print("Restarting...")
            time.sleep(0.2)
            machine.reset()
        except Exception as e:
            print("firmware switch failed:", e)

    def _slot_from_label(self, value):
        if isinstance(value, bytes):
            try:
                value = value.decode()
            except Exception:
                return None

        if isinstance(value, str) and value.startswith("ota_"):
            try:
                slot = int(value[4:])
            except Exception:
                return None
            if slot in (0, 1, 2):
                return slot

        return None

    def _current_slot(self):
        if esp32 is None:
            return None

        try:
            cur = esp32.Partition(esp32.Partition.RUNNING)
            info = cur.info()
        except Exception:
            return None

        if isinstance(info, (tuple, list)):
            for field in info:
                slot = self._slot_from_label(field)
                if slot is not None:
                    return slot
        return self._slot_from_label(info)

    def _is_key_pressed(self, target_row, target_col):
        try:
            rows = self.keypad.rows
            cols = self.keypad.cols
        except Exception:
            return False

        for row_idx, row_pin in enumerate(rows):
            try:
                Pin(row_pin, Pin.OUT).value(0)
                for col_idx, col_pin in enumerate(cols):
                    if Pin(col_pin, Pin.IN, Pin.PULL_UP).value() == 0:
                        if row_idx == target_row and col_idx == target_col:
                            return True
            except Exception:
                pass
            finally:
                try:
                    Pin(row_pin, Pin.OUT).value(1)
                except Exception:
                    pass

        return False

    def _find_key_coord(self, key_name):
        try:
            layout = self.keypad_map.states["d"]
        except Exception:
            return None

        for row_idx, row in enumerate(layout):
            for col_idx, value in enumerate(row):
                if value == key_name:
                    return (row_idx, col_idx)
        return None

    def _active_switch_key(self, default_key):
        if default_key in ("+", "-"):
            return default_key

        plus_pressed = (
            self._plus_key is not None
            and self._is_key_pressed(self._plus_key[0], self._plus_key[1])
        )
        minus_pressed = (
            self._minus_key is not None
            and self._is_key_pressed(self._minus_key[0], self._minus_key[1])
        )

        if plus_pressed and not minus_pressed:
            return "+"
        if minus_pressed and not plus_pressed:
            return "-"
        return None

    def _handle_live_switch_shortcut(self, row, col):
        try:
            default_key = self.keypad_map.states["d"][row][col]
        except Exception:
            return

        if not self._is_key_pressed(self._alpha_row, self._alpha_col):
            self._switch_latched_key = None
            return

        switch_key = self._active_switch_key(default_key)
        if switch_key is None:
            self._switch_latched_key = None
            return

        if self._switch_latched_key == switch_key:
            return
        self._switch_latched_key = switch_key

        slot = self._current_slot()
        if slot is None:
            print("cannot determine current OTA slot")
            return

        if switch_key == "+":
            target_slot = (slot + 1) % 3
        else:
            target_slot = (slot + 2) % 3

        names = {0: "MicroPython", 1: "C++", 2: "Rust"}
        self._switch_to_partition("ota_{}".format(target_slot), names[target_slot])

    def start_typing(self):
        time.sleep(self.debounce_delay_time)
        try:
            key_inp = self.keypad.keypad_loop()
            col = int(key_inp[0])
            row = int(key_inp[1])
            self._handle_live_switch_shortcut(row=row, col=col)
            text = self.keypad_map.key_out(col=col, row=row)
            swdt.feed()
            if text == "off" or text == "on":
                test_deep_sleep_awake()
            return text
        except KeyboardInterrupt:
            swdt.stop()
            print("soft watchdog timer stopped")
            raise  # Let REPL get it!

    def debounce_delay(self, t=None):
        if t == None:
            return self.debounce_delay_time
        if isinstance(t, (int, float)):
            if t >= self.min_debounce_delay_time:
                self.debounce_delay_time = t
                return self.debounce_delay_time
