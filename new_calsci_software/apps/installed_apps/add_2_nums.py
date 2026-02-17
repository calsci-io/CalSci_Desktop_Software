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
from data_modules.object_handler import keypad_state_manager

def add_2_nums(db={}):
    form.input_list={"inp_0": " ", "inp_1": " "}
    form.form_list = ["addition", "1st num", "inp_0", "2nd num", "inp_1"]
    form.update()
    display.clear_display()
    form_refresh.refresh()

    while True:
        inp = typer.start_typing()
        if inp == "back":
            app.set_app_name("installed_apps")
            app.set_group_name("root")
            break
        
        if inp == "ok":
            try:
                num1=form.inp_list()["inp_0"]       
                num2=form.inp_list()["inp_1"]
                nums_sum=" = "+str(float(num1)+float(num2))
                form.form_list.append(nums_sum)
                form.update()
                form.update_buffer("nav_u")
                form_refresh.refresh()
            except:
                form.form_list.append(" = error")
                form.update()
                form.update_buffer("nav_u")
                form_refresh.refresh()
            
        if inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            form.update_buffer("")

        if inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
        form_refresh.refresh(state=nav.current_state())
