import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import network # type: ignore
import time
import machine
from data_modules.object_handler import nav, menu, menu_refresh, typer, display, keypad_state_manager, app
from data_modules.object_handler import current_app, data_bucket
from process_modules import boot_up_data_update

def wifi_app(db={}):
    display.clear_display()
    menu_list = ["Scanning..."]
    menu.menu_list=menu_list
    menu.update()
    menu_refresh.refresh()

    network_names = scan_networks()

    menu_list=network_names[:15] if len(network_names) >= 15 else network_names
    menu.menu_list=menu_list
    menu.update()
    menu_refresh.refresh()

    while True:
        inp = typer.start_typing()
        if inp == "ok":
            data_bucket["ssid_g"] = network_names[menu.cursor()][3:]
            # current_app[0]="wifi_connector"
            app.set_app_name("wifi_connector")
            app.set_group_name("settings")
            break

        if inp == "back":
            # current_app[0]="settings"
            # current_app[1]="application_modules"
            app.set_app_name("settings")
            app.set_group_name("root")
            break
        if inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            menu.update_buffer("")
        if inp == "off":
            boot_up_data_update.main()
            machine.deepsleep()
        menu.update_buffer(inp)
        menu_refresh.refresh(state=nav.current_state())
        # time.sleep(0.1)

def scan_networks():
    network_names = []
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(True)
    networks = sta_if.scan()
    for i, network_info in enumerate(networks):
        ssid = network_info[0].decode()
        network_names.append(f'{i + 1}. {ssid}')

    return network_names
