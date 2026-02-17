import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

from data_modules.object_handler import data_bucket, current_app, text, menu, form, keypad_state_manager_reset
import gc
import json
from process_modules.app_runner import app_runner

def app_handler():
    while True:
        keypad_state_manager_reset()
        
       
        app_runner()
        gc.collect()
        print(gc.mem_free(), gc.mem_alloc())
