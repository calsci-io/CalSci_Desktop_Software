import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

from tinydb import TinyDB, Query
db = TinyDB('db/settings.json')
q=Query()

import time
from data_modules.object_handler import typer
# from data_modules.object_handler import current_app
# from process_modules import boot_up_data_update
from data_modules.object_handler import app
# from hcsr04 import HCSR04

def toggle_autowifi_connect():
    db.update({'value':not db.search(q.feature=="auto_wifi_connect")[0]["value"]}, q.feature == 'auto_wifi_connect')

def wifi_autoconnect():
    time.sleep(0.1)
    # sensor = HCSR04(trigger_pin=16, echo_pin=2)
    display.clear_display()
    menu_list=["auto wifi connect:", str(db.search(q.feature=="auto_wifi_connect")[0]["value"])]
    menu.menu_list=menu_list
    menu.update()
    menu_refresh.refresh()
    try:
        while True:
            inp = typer.start_typing()
            
            if inp == "back":
                # current_app[0]="home"
                # current_app[1]="application_modules"
                app.set_app_name("settings")
                app.set_group_name("root")
                break
            
            # elif inp == "alpha" or inp == "beta":                        
            #     keypad_state_manager(x=inp)
            #     menu.update_buffer("")
            elif inp =="ok":
                # distance = sensor.distance_cm()
                toggle_autowifi_connect()
                menu.menu_list=["auto wifi connect:", str(db.search(q.feature=="auto_wifi_connect")[0]["value"])]
                menu.update()
                menu_refresh.refresh()
            menu.update_buffer(inp)
            menu_refresh.refresh()
            time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
