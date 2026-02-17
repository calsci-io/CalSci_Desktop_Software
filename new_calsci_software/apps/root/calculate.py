import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

from math import *
from data_modules.object_handler import display, text, nav, text_refresh, typer, keypad_state_manager, keypad_state_manager_reset, current_app, app
from data_modules.db_instance import fun_db
from data_modules.object_handler import data_bucket

def build_function(func_def, safe_globals):
    vars_ = func_def["variables"]
    expr = func_def["expression"]

    def generated_function(*args):
        if len(args) != len(vars_):
            raise ValueError("Wrong number of arguments")

        local_scope = {}
        for i in range(len(vars_)):
            local_scope[vars_[i]] = args[i]

        return eval(expr, safe_globals, local_scope)

    return generated_function

# from math import sin, cos, tan, sqrt, radians

FUNCTIONS = {}

# SAFE_GLOBALS = {
#     "__builtins__": {},
#     "sin": sin,
#     "cos": cos,
#     "tan": tan,
#     "sqrt": sqrt,
#     "radians": radians,


# }

ans=[0,0]

SAFE_GLOBALS = {
    "__builtins__": {},

    # trig + inverse trig
    "sin": sin,
    "cos": cos,
    "tan": tan,
    "asin": asin,
    "acos": acos,
    "atan": atan,
    "atan2": atan2,

    # hyperbolic
    "sinh": sinh,
    "cosh": cosh,
    "tanh": tanh,
    "asinh": asinh,
    "acosh": acosh,
    "atanh": atanh,

    # exponentials/logs
    "exp": exp,
    "expm1": expm1,
    "log": log,
    "log10": log10,
    "log2": log2,
    "pow": pow,
    "sqrt": sqrt,

    # rounding/parts
    "ceil": ceil,
    "floor": floor,
    "trunc": trunc,
    "modf": modf,
    "frexp": frexp,
    "ldexp": ldexp,
    "fmod": fmod,

    # misc math
    "fabs": fabs,
    "copysign": copysign,
    "degrees": degrees,
    "radians": radians,

    # special functions
    "erf": erf,
    "erfc": erfc,
    "gamma": gamma,
    "lgamma": lgamma,

    # checks
    "isfinite": isfinite,
    "isinf": isinf,
    "isnan": isnan,

    # constants
    "e": e,
    "pi": pi,
    "ans":ans[0]
}


def load_all_functions():
    FUNCTIONS.clear()

    for row in fun_db.all():
        name = row.get("name")
        variables = row.get("variables")
        expression = row.get("expression")

        if not name or not variables or not expression:
            continue  # skip broken entries

        func_def = {
            "variables": variables,
            "expression": expression
        }

        FUNCTIONS[name] = build_function(func_def, SAFE_GLOBALS)
        SAFE_GLOBALS[name] = FUNCTIONS[name]  # 👈 critical


# from process_modules import boot_up_data_update
# import uasyncio as asyncio
# from test_async import main, cancel_task
# asyncio.run(main())
# from 
# from test_thread import run_espnow_message, end_espnow_task
task=None
def calculate():
    global ans
    load_all_functions()
    global task
    keypad_state_manager_reset()
    display.clear_display()
    if text.retain_data == False:
        text.all_clear()
    else:
        text.refresh_area=(0, text.rows * text.cols)
        text.retain_data = False
    text_refresh.new=True
    text_refresh.refresh()
    task=None
    try:
        while True:

            x = typer.start_typing()
            if x == "back":
                current_app[0]="home"
                current_app[1] = "application_modules"
                break

            if (x== "exe" or x == "ok") and text.text_buffer[0] != "𖤓":
                try:
                    # 1. Get the raw result from eval
                    raw_res = eval(text.text_buffer[:text.text_buffer_nospace], SAFE_GLOBALS)
                    
                    # 2. Format it using an f-string
                    res = f"= {raw_res:.12g}"
                    ans[0]=raw_res
                    SAFE_GLOBALS["ans"]=ans[0]
                except Exception as e:
                    res = str(e)
                    if "error_msg" in data_bucket.keys():
                        data_bucket.pop("error_msg")
                    data_bucket["error_msg"]=res
                    print("calculate", data_bucket["error_msg"])
                    data_bucket["error_parent_app_name"]="calculate"
                    data_bucket["error_parent_group_name"]="root"
                    app.set_app_name("error_screen")
                    app.set_group_name("root")
                    break
                print(res)

                # text.all_clear()
                # display.clear_display()
                # text.update_buffer(res)
                text.update_buffer("")
                text_refresh.refresh(state=res)
                text_refresh.new=True
                continue

            elif x == "alpha" or x == "beta":                        
                keypad_state_manager(x=x)
                text.update_buffer("")
                text_refresh.refresh(state=nav.current_state())
                continue
            elif x == "caps":
                keypad_state_manager(x="A")
                text.update_buffer("")
                text_refresh.refresh(state=nav.current_state())
                continue
            
            elif x == "toolbox":
                app.set_app_name("toolbox")
                app.set_group_name("root")
                break

            elif not (x== "exe" or x == "ok"):
                text.update_buffer(x)

            if nav.current_state().strip() in ["alpha", "beta", "ALPHA"]:
                keypad_state_manager_reset()
                text.update_buffer("")
                text_refresh.refresh(state=nav.current_state())
                continue
            
            if text.text_buffer[0] == "𖤓":
                # display.clear_display()
                text.all_clear()
            

            text_refresh.refresh(state=nav.current_state())
            # time.sleep(0.2)

    except Exception as e:
        print(f"Error: {e}")
