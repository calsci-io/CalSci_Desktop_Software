import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

from data_modules.object_handler import display, form, nav, form_refresh, typer, keypad_state_manager, keypad_state_manager_reset
from data_modules.object_handler import app
# import urequests # type: ignore
import gc
import time
from sleeping_features import get_sleep_time, update_sleep_time
# def search(term):

# url = "http://67e91d51e7f4f94a1ce3.appwrite.global/search_molecule"
# headers = {"molecule": "glucose"}

def sleep_after(db={}):
    print("start of sleep_after", gc.mem_free())
    keypad_state_manager_reset()
    global display, form, form_refresh, typer, nav, current_app
    display.clear_display()
    form.input_list={"inp_0": str(int(get_sleep_time()/60000))}
    form.form_list=["sleep after minutes:", "inp_0"]
    form.update()
    form_refresh.refresh()
    while True:
        inp = typer.start_typing()
        if inp == "back":
            # del buffer1, fb1
            app.set_app_name("settings")
            app.set_group_name("root")
            break

        elif inp == "ok":
            tm=form.inp_list()["inp_0"]
            try:
                if int(tm)<=14400:
                    update_sleep_time(int(tm)*60000)
                    print("db time = ",get_sleep_time(), "form input time = ", tm)
                    form.form_list=["sleep after minutes:", "inp_0", "updated successfully"]
                    form.update()
                    form_refresh.refresh()
                elif int(tm)>14400:
                    form.form_list=["sleep after minutes:", "inp_0", "maximum is 14400"]
                    form.update()
                    form_refresh.refresh()
            except:
                form.form_list=["sleep after minutes:", "inp_0", "wrong input"]
                form.update()
                form_refresh.refresh()
            # form.form_list=["enter compound: ", "inp_0", "loading..."]
            # form.update()
            # form_refresh.refresh()
            # molecule=form.inp_list()["inp_0"]
            # url = "http://67e91d51e7f4f94a1ce3.appwrite.global/search_molecule"
            # headers = {"molecule": molecule}
            # try:
            #     response = urequests.get(url, headers=headers).text
            # except:
            #     response = "connect to internet"
            # print(response)
            # display.clear_display()
            # form.form_list=["enter compound: ", "inp_0", response]
            # form.update()
            # form_refresh.refresh()
        elif inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            form.update_buffer("")
        elif inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
            if "updated successfully" in form.form_list:
                form.form_list.pop()
                form.update()
                form_refresh.refresh()
        form_refresh.refresh(state=nav.current_state())
    
        time.sleep(0.1)
