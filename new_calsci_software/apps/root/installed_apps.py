import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

# import time
# import json
import machine
from data_modules.object_handler import nav, keypad_state_manager, menu, menu_refresh, typer, keymap, display, app
from data_modules.object_handler import current_app
from process_modules import boot_up_data_update
from process_modules.app_downloader import Apps
from data_modules.object_handler import apps_installer

def installed_apps():
    # time.sleep(0.1)
    display.clear_display()
    menu_list = apps_installer.get_group_apps()
    menu.menu_list=menu_list
    menu.update()
    menu_refresh.refresh()
    try:
        while True:
            inp = typer.start_typing()
            if inp == "back":
                app.set_app_name("home")
                app.set_group_name("root")
                break
            elif inp == "alpha" or inp == "beta":
                keypad_state_manager(x=inp)
                menu.update_buffer("")
            elif inp == "off":
                boot_up_data_update.main()
                machine.deepsleep()
            elif inp =="ok":
                app.set_app_name(menu.menu_list[menu.menu_cursor])
                app.set_group_name("installed_apps")
                break
            menu.update_buffer(inp)
            menu_refresh.refresh(state=nav.current_state())
            # time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
