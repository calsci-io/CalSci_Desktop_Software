import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import time
import usb.device
from usb.device.keyboard import KeyboardInterface

def keyboard_example():
    kbd = KeyboardInterface()

    # Start USB device with builtin CDC REPL still active
    usb.device.get().init(kbd, builtin_driver=True)

    # Wait until host enumerates HID keyboard
    while not kbd.is_open():
        time.sleep_ms(100)

    time.sleep_ms(1000)  # small delay before typing

    # Send keystrokes
    for ch in "Hello":
        kbd.send_keys([ch])
        time.sleep_ms(200)

    kbd.send_keys(["ENTER"])
    print("Done typing!")

keyboard_example()


