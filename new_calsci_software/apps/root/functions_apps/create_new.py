import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

# import time  # type:ignore
from math import *
# import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh
# from process_modules import boot_up_data_update
from data_modules.object_handler import app
from data_modules.db_instance import fun_db
from tinydb import TinyDB, Query
Function = Query()
# Initialize the database, which will use 'db.json' to store data
#fun_db = TinyDB('db/functions_data.json')
from data_modules.object_handler import data_bucket

def _is_identifier(name):
    if not name:
        return False

    c = name[0]
    if not (('a' <= c <= 'z') or ('A' <= c <= 'Z') or c == '_'):
        return False

    for c in name[1:]:
        if not (('a' <= c <= 'z') or ('A' <= c <= 'Z') or
                ('0' <= c <= '9') or c == '_'):
            return False

    return True

def parse_variables(var_string):
    variables = []

    for v in var_string.split(","):
        v = v.strip()

        if not v:
            continue

        if not _is_identifier(v):
            raise ValueError("Invalid variable name: " + v)

        if v in variables:   # list check instead of set
            raise ValueError("Duplicate variable: " + v)

        variables.append(v)

    return variables


def upsert_function(name, variables, expression):
    if fun_db.contains(Function.name == name):
        fun_db.update(
            {
                "variables": variables,
                "expression": expression
            },
            Function.name == name
        )
    else:
        fun_db.insert(
            {
                "name": name,
                "variables": variables,
                "expression": expression
            }
        )

def get_function_display_data():
    name=""
    if "function" in data_bucket.keys():
        name=data_bucket["function"]
    else:
        return None
    row =fun_db.get(Function.name == name)
    if not row:
        return None

    variables_str = ", ".join(row.get("variables", []))

    return {
        "name": row.get("name", ""),
        "variables": variables_str,
        "expression": row.get("expression", "")
    }

def create_new():
    data = get_function_display_data()   # CALL THE FUNCTION

    if data is None:
        form.input_list = {
            "inp_0": " ",
            "inp_1": " ",
            "inp_2": " "
        }
    else:
        name = data["name"]
        variables = data["variables"]
        expression = data["expression"]

        form.input_list = {
            "inp_0": name,
            "inp_1": variables,
            "inp_2": expression
        }

        data_bucket.clear()  # safe
    form.form_list = ["create new function", "name", "inp_0", "variables", "inp_1", "expression", "inp_2"]
    form.update()
    display.clear_display()
    form_refresh.refresh()
    
    while True:
        inp = typer.start_typing()
        # print(type(inp))
        if inp == "back":
            app.set_app_name("function_locker")
            app.set_group_name("root")
            break
        
        if inp == "ok":
            try:
                name=form.inp_list()["inp_0"].strip()       
                variables=parse_variables(form.inp_list()["inp_1"])
                expression=form.inp_list()["inp_2"].strip()
                #fun_db.insert({
                #     "name": name,
                #     "variables": variables,
                #     "expression": expression
                # })
                upsert_function(name=name, variables=variables, expression=expression)
                # if form.form_list[-1] == "error in input " or form.form_list[-1] ==  "successfully added ":
                if "error in input" in form.form_list[-1] or "successfully added" in form.form_list[-1]:
                    form.form_list.pop()
                    # form.form_list.update()
                form.form_list.append("successfully added")
                form.update()
                form.update_buffer("nav_u")
                form_refresh.refresh()


            except Exception as e:
                print(e)
                form.form_list.append("error in input")
                form.update()
                form.update_buffer("nav_u")
                form_refresh.refresh()
            
        if inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            form.update_buffer("")

        if inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
        form_refresh.refresh(state=nav.current_state())
        # time.sleep(0.15)
