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
import json
from data_modules.object_handler import nav, keypad_state_manager, typer, display
from data_modules.object_handler import current_app
# from process_modules import boot_up_data_update
from data_modules.object_handler import app
from data_modules.db_instance import fun_db
# import pygame
from tinydb import TinyDB, Query
Function = Query()
# Initialize the database, which will use 'db.json' to store data
# db = TinyDB('db/functions_data.json')


def recently_used():
    display.clear_display()
    # json_file = "db/application_modules_app_list.json" 
    # with open(json_file, "r") as file:
    #     data = json.load(file)
    function_names = [row["name"] for row in fun_db.all()]
    # menu_list = []
    # for apps in data:
    #     if apps["visibility"]:
    #         menu_list.append(apps["name"])
    

    menu.menu_list=function_names
    menu.update()
    menu_refresh.refresh()
    try:
        while True:
            inp = typer.start_typing()
            if inp == "back":
                app.set_app_name("functions")
                app.set_group_name("root")
                break
            elif inp == "alpha" or inp == "beta":                        
                keypad_state_manager(x=inp)
                menu.update_buffer("")
            elif inp =="ok":
                from data_modules.object_handler import data_bucket

                data_bucket["function"] = menu.menu_list[menu.menu_cursor]
                app.set_app_name("create_new")
                app.set_group_name("root.functions_apps")

                break
            menu.update_buffer(inp)
            menu_refresh.refresh(state=nav.current_state())
            # time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
