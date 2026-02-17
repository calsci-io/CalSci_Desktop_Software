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

def functions(db={}):
    display.clear_display()
    # json_file = "db/application_modules_app_list.json" 
    # with open(json_file, "r") as file:
    #     data = json.load(file)

    # menu_list = []
    # for apps in data:
    #     if apps["visibility"]:
    #         menu_list.append(apps["name"])
    

    menu.menu_list=["recently_used", "create_new", "delete_function"]
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
            elif inp =="ok":
                app.set_app_name(menu.menu_list[menu.menu_cursor])
                app.set_group_name("root.functions_apps")
                break
            menu.update_buffer(inp)
            menu_refresh.refresh(state=nav.current_state())
            # time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
