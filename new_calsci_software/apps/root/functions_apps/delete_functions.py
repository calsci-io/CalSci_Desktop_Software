import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci

# Licensed under the MIT License.



from data_modules.object_handler import nav, keypad_state_manager, typer, display, app, menu, menu_refresh

from data_modules.db_instance import fun_db

from tinydb import Query



Function = Query()



def delete_functions():

    """Delete function app - shows list of functions to delete"""

    display.clear_display()

    

    # Load all functions from database

    all_functions = fun_db.all()

    

    if len(all_functions) == 0:

        

        menu.menu_list = [

            "Delete Function",

            "No functions found",

            "",

            "Press BACK to exit"

        ]

        menu.update()

        menu_refresh.refresh()

        

        while True:

            inp = typer.start_typing()

            if inp == "back":

                app.set_app_name("function_locker")

                app.set_group_name("root")

                return

            

            if inp == "alpha" or inp == "beta":

                keypad_state_manager(x=inp)

                menu.update_buffer("")

            

            menu.update_buffer(inp)

            menu_refresh.refresh(state=nav.current_state())

        

        return

    

    # Build menu list with all function names

    function_names = [row["name"] for row in all_functions]

    menu.menu_list = ["Delete Function"] + function_names

    menu.menu_cursor = 0

    menu.update()

    menu_refresh.refresh()

    

    selected_function = None

    

    try:

        while True:

            inp = typer.start_typing()

            

            if inp == "back":

                if selected_function is None:

                    # Not in confirmation mode, exit to functions menu

                    app.set_app_name("function_locker")

                    app.set_group_name("root")

                    return

                else:

                    # In confirmation mode, cancel deletion

                    selected_function = None

                    menu.menu_list = ["Delete Function"] + function_names

                    menu.menu_cursor = 0

                    menu.update()

                    display.clear_display()

                    menu_refresh.refresh()

            

            elif inp == "ok":

                if selected_function is None:

                    # First OK - select function to delete

                    if menu.menu_cursor > 0:  # Not on header

                        selected_idx = menu.menu_cursor - 1

                        selected_function = function_names[selected_idx]

                        

                        # Show confirmation screen

                        menu.menu_list = [

                            "Delete Function",

                            f"Delete: {selected_function}?",

                            "",

                            "OK to confirm",

                            "BACK to cancel"

                        ]

                        menu.update()

                        display.clear_display()

                        menu_refresh.refresh()

                else:

                    # Second OK - confirm deletion

                    try:

                        # Delete from database

                        fun_db.remove(Function.name == selected_function)

                        

                        # Show success message

                        menu.menu_list = [

                            "Delete Function",

                            f"Deleted: {selected_function}",

                            "Successfully removed",

                            "",

                            "Press BACK to exit"

                        ]

                        menu.update()

                        display.clear_display()

                        menu_refresh.refresh()

                        

                        # Wait for user to press back

                        while True:

                            inp = typer.start_typing()

                            if inp == "back":

                                app.set_app_name("function_locker")

                                app.set_group_name("root")

                                return

                            

                            if inp == "alpha" or inp == "beta":

                                keypad_state_manager(x=inp)

                                menu.update_buffer("")

                            

                            menu.update_buffer(inp)

                            menu_refresh.refresh(state=nav.current_state())

                    

                    except Exception as e:

                        # Show error message

                        print(f"Delete error: {e}")

                        menu.menu_list = [

                            "Delete Function",

                            "Error deleting",

                            str(e)[:20],

                            "",

                            "Press BACK to exit"

                        ]

                        menu.update()

                        display.clear_display()

                        menu_refresh.refresh()

                        

                        while True:

                            inp = typer.start_typing()

                            if inp == "back":

                                app.set_app_name("function_locker")

                                app.set_group_name("root")

                                return

                            

                            if inp == "alpha" or inp == "beta":

                                keypad_state_manager(x=inp)

                                menu.update_buffer("")

                            

                            menu.update_buffer(inp)

                            menu_refresh.refresh(state=nav.current_state())

            

            elif inp == "alpha" or inp == "beta":

                keypad_state_manager(x=inp)

                menu.update_buffer("")

            

            menu.update_buffer(inp)

            menu_refresh.refresh(state=nav.current_state())

            

    except Exception as e:

        print(f"Error: {e}")

        app.set_app_name("function_locker")

        app.set_group_name("root")
