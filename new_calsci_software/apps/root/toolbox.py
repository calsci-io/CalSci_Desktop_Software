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
from data_modules.object_handler import nav, keypad_state_manager, typer, display
from data_modules.object_handler import text
# from process_modules import boot_up_data_update
from data_modules.object_handler import app
from data_modules.db_instance import fun_db

from tinydb import TinyDB, Query
Function = Query()
# Initialize the database, which will use 'db.json' to store data
# db = TinyDB('db/functions_data.json')

# def toolbox():
#     display.clear_display()
#     menu.menu_list=[row["name"] for row in fun_db.all()]
#     menu.update()
#     menu_refresh.refresh()
#     text.retain_data=True
#     try:
#         while True:
#             inp = typer.start_typing()
#             if inp == "back":
#                 app.set_app_name("calculate")
#                 app.set_group_name("root")
#                 text.update_buffer("")
#                 break
#             elif inp == "alpha" or inp == "beta":                        
#                 keypad_state_manager(x=inp)
#                 menu.update_buffer("")
#             elif inp =="ok":
#                 # app.set_app_name(menu.menu_list[menu.menu_cursor])
#                 text.update_buffer(menu.menu_list[menu.menu_cursor])
#                 app.set_app_name("calculate")
#                 app.set_group_name("root")
#                 break
#             menu.update_buffer(inp)
#             menu_refresh.refresh(state=nav.current_state())
#             # time.sleep(0.2)
#     except Exception as e:
#         print(f"Error: {e}")
def toolbox():
    """Toolbox app - shows user-defined functions"""
    from data_modules.db_instance import fun_db
    from tinydb import Query
    
    # Set retain flag to preserve calculate buffer
    text.retain_data = True
    
    # Load functions from database
    all_functions = fun_db.all()
    
    # Build menu list
    menu.menu_list = ["Functions"]
    for func in all_functions:
        menu.menu_list.append(func['name'])
    
    menu.menu_cursor = 0
    menu.update()
    display.clear_display()
    menu_refresh.refresh()
    
    try:
        while True:
            inp = typer.start_typing()
            
            if inp == "back":
                app.set_app_name("calculate")
                app.set_group_name("root")
                return
            
            elif inp == "ok":
                # Get selected function name
                if menu.menu_cursor > 0:  # Not on header
                    selected_idx = menu.menu_cursor - 1  # Adjust for header
                    selected_function = all_functions[selected_idx]
                    
                    # Get function name and variables
                    func_name = selected_function['name']
                    variables = selected_function.get('variables', [])
                    num_vars = len(variables)
                    
                    # Generate formatted insertion text
                    if num_vars > 0:
                        commas = "," * (num_vars - 1)
                        formatted_text = f"{func_name}({commas})"
                    else:
                        formatted_text = f"{func_name}()"
                    
                    # Insert into text buffer
                    text.update_buffer(formatted_text)
                    
                    # Return to calculate app
                    app.set_app_name("calculate")
                    app.set_group_name("root")
                    return
            
            elif inp == "alpha" or inp == "beta":
                keypad_state_manager(x=inp)
                menu.update_buffer("")
            
            menu.update_buffer(inp)
            menu_refresh.refresh(state=nav.current_state())
            
    except Exception as e:
        print(f"Toolbox error: {e}")
        app.set_app_name("calculate")
        app.set_group_name("root")
