import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

from input_modules.keypad import Keypad
keypad_rows=[33, 25, 26, 27, 14, 12, 13, 23]
keypad_cols=[36, 39, 34, 35, 32]

st7565_display_pins={"cs1":5, "rs":19, "rst":18, "sda":22, "sck":21}
keyin = Keypad(rows=keypad_rows, cols=keypad_cols)

network_info = {"ssid_g" : "", "connection_status_g" : False}

