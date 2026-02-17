import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
import network  # type: ignore
import time
import machine
from data_modules.object_handler import nav, keypad_state_manager, menu, menu_refresh, typer, keymap, display
from data_modules.object_handler import current_app, data_bucket
from process_modules import boot_up_data_update

sta_if = network.WLAN(network.STA_IF)

def disconnect_network():
    sta_if.disconnect()
    data_bucket["connection_status_g"] = False
    data_bucket["ssid_g"] = ""

def network_status(db={}):
    # time.sleep(0.2)
    display.clear_display()

    if data_bucket["connection_status_g"]:
        sometext = f"Connected to {data_bucket['ssid_g']}"
    else:
        sometext = "Not connected to internet."

    menu_list = [sometext]

    if data_bucket["connection_status_g"]:
        menu_list.append("Disconnect?")
    menu.menu_list=menu_list
    menu.update()
    menu_refresh.refresh()

    while True:
        inp = typer.start_typing()
        if inp in ["back"]:
            current_app[0]="settings"
            current_app[1]="application_modules"
            break
        elif inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            menu.update_buffer("")
        elif inp == "off":
            boot_up_data_update.main()
            machine.deepsleep()
        elif inp=="ok" and menu.menu_list[menu.menu_cursor]=="Disconnect?":
            disconnect_network()
            current_app[0]="settings"
            current_app[1]="application_modules"
            break
        elif inp=="ok" and menu.menu_list[menu.menu_cursor]!="Disconnect?":
            current_app[0]="settings"
            current_app[1]="application_modules"
            break
        menu.update_buffer(inp)
        menu_refresh.refresh(state=nav.current_state())
        # time.sleep(0.2)
