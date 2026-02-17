import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

from data_modules.object_handler import display
import utime as time  # type:ignore
from math import *
from data_modules.object_handler import display, text, nav, text_refresh, typer, keypad_state_manager, keypad_state_manager_reset, menu, menu_refresh
from data_modules.object_handler import current_app

def contrast(db = {}):
    keypad_state_manager_reset()
    display.clear_display()
    text.all_clear()
    text_refresh.refresh()
    input_buffer = ""
    try:
        while True:

            x = typer.start_typing()

            if x == "back":
                current_app[0]="settings"
                break
            
            if x == "ok":
                try:
                    display.set_contrast(int(input_buffer))
                    res = f"success, contrast set to {input_buffer}"
                    input_buffer = ""
                except Exception as e:
                    res = "Invalid Input"
                text.all_clear()
                display.clear_display()
                text.update_buffer(res)

            elif x == "alpha" or x == "beta":
                if x == "alpha":
                    keypad_state_manager(x=x)
                    menu.update_buffer(x)
                    menu_refresh.refresh(state=nav.current_state())
                    time.sleep(0.2)
                    temp_inp = typer.start_typing()
                    if temp_inp == "on":
                        import machine
                        machine.deepsleep()
                keypad_state_manager(x=x)
                text.update_buffer("")

            else:
                input_buffer += x  # Append input to buffer
                text.all_clear()
                text.update_buffer(input_buffer)

            


            text_refresh.refresh(state=nav.current_state())
            time.sleep(0.1)

    except Exception as e:
        print(f"Error: {e}")
