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
import json
import machine
from data_modules.object_handler import current_app, nav, keypad_state_manager, menu, menu_refresh, typer, keymap, display
from apps.settings.backlight import backlight, backlight_pin
from apps.settings.dark_mode import dark_mode
from process_modules import boot_up_data_update
from data_modules.object_handler import app
# from process_modules.app_downloader import App_downloader
from data_modules.object_handler import mac_str


def mac_address():
    # operation_no = 0
    # screens=[["check_updates"], ["download_app"], ["update_app_list"], ["send_confirmation"], ["reset"]]
    # app_downloader = App_downloader()
    # operations=[app_downloader.check_status, app_downloader.download_app, app_downloader.update_app_list, app_downloader.send_confirmation, app_downloader.reset]
    display.clear_display()
    # json_file = "/db/settings_app_list.json" 
    # with open(json_file, "r") as file:
    #     data = json.load(file)
    

    # for apps in data:
    #     if apps["visibility"]:
    #         settins_list.append(apps["name"])

    # menu.menu_list=screens[operation_no]
    menu.menu_list=["mac address:", mac_str, str(machine.unique_id())]
    menu.update()
    menu_refresh.refresh()
    try:
        while True:
            inp_menu = typer.start_typing()

            if inp_menu == "back":
                # current_app[0]="home"
                # current_app[1]="application_modules"
                app.set_app_name("settings")
                app.set_group_name("root")
                break  
        
            elif inp_menu == "alpha" or inp_menu == "beta":
                keypad_state_manager(x=inp_menu)
                menu.update_buffer("")
            elif inp_menu == "off":
                boot_up_data_update.main()
                machine.deepsleep()
            # elif inp_menu =="ok" and menu.menu_list[menu.menu_cursor] in ["backlight"]:
            #     backlight()
            # elif inp_menu =="ok" and menu.menu_list[menu.menu_cursor] in ["Dark_Mode"]:
            #     dark_mode()
            elif inp_menu =="ok":
                # if operation_no == 4:
                app.set_app_name("settings")
                app.set_group_name("root")
                break
                # current_app[0]=menu.menu_list[menu.menu_cursor]
                # current_app[1] = "settings"
                # app.set_app_name(menu.menu_list[menu.menu_cursor])
                # app.set_group_name("settings")
                # break
                # operations[operation_no]()
                # operation_no+=1
                # menu.menu_list=screens[operation_no]
                # menu.update()
                # menu_refresh.refresh()
            menu.update_buffer(inp_menu)
            menu_refresh.refresh(state=nav.current_state())
            # time.sleep(0.1)
    except Exception as e:
        print(f"Error: {e}")
