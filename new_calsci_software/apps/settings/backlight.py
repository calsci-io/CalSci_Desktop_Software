import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

from machine import Pin # type: ignore
from tinydb import TinyDB, Query
# Assuming the backlight is connected to a specific pin (e.g., Pin 15)
# backlight_pin = Pin(19, Pin.OUT) #3.0
db = TinyDB('db/settings.json')
q=Query()

backlight_pin = Pin(5, Pin.OUT) #2.9
backlight_label=""
if backlight_pin.value() ==1:

    backlight_label="backlight off"
    # db.update({'value':False}, q.feature == 'backlight')

else:
    backlight_label="backlight on"
    # db.update({'value':False}, q.feature == 'backlight')
# Function to toggle the backlight
def backlight():
    global db, q
    current_state = backlight_pin.value()  # Read the current state
    if current_state == 1:  # If the backlight is OFF
        backlight_pin.off()  # Turn it ON
        db.update({'value':True}, q.feature == 'backlight')

    else:  # If the backlight is ON
        backlight_pin.on()  # Turn it OFF
        db.update({'value':False}, q.feature == 'backlight')
