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
# from sleeping_features import get_sleep_time, update_sleep_time
from tinydb import TinyDB, Query
# Assuming the backlight is connected to a specific pin (e.g., Pin 15)
# backlight_pin = Pin(19, Pin.OUT) #3.0
db = TinyDB('db/settings.json')
q=Query()
# def search(term):
from sleeping_features import swdt
# url = "http://67e91d51e7f4f94a1ce3.appwrite.global/search_molecule"
# headers = {"molecule": "glucose"}

def autosleep_on():
    display.clear_display()
    form.input_list={"inp_0": str(int(db.search(q.feature=="sleep_timer")[0]["value"]/60000))}
    # form.form_list=["autosleep: ON","sleep after minutes:", "inp_0"]
    form.form_list.clear()
    form.form_list.extend(["autosleep: ON","sleep after minutes:", "inp_0"])
    form.update()
    form_refresh.refresh()
    db.update({'value':True}, q.feature == 'auto_sleep')

def autosleep_off():
    display.clear_display()
    form.input_list={"inp_0": str(int(db.search(q.feature=="sleep_timer")[0]["value"]/60000))}
    # form.form_list=["autosleep: OFF","press OK", "to turn ON"]
    form.form_list.clear()
    form.form_list.extend(["autosleep: OFF","press OK", "to turn ON"])

    form.update()
    form_refresh.refresh()
    db.update({'value':False}, q.feature == 'auto_sleep')



def auto_sleep():
    # print("start of sleep_after", gc.mem_free())
    # keypad_state_manager_reset()
    # global display, form, form_refresh, typer, nav
    display.clear_display()
    # form.input_list={"inp_0": str(int(get_sleep_time()/60000))}
    # form.form_list=["sleep after minutes:", "inp_0"]
    # form.update()
    # form_refresh.refresh()

    if db.search(q.feature=="auto_sleep")[0]["value"] == True:
        autosleep_on()
    else:
        autosleep_off()

    while True:
        inp = typer.start_typing()
        if inp == "back":
            # del buffer1, fb1
            app.set_app_name("settings")
            app.set_group_name("root")
            break

        elif inp == "ok" and db.search(q.feature=="auto_sleep")[0]["value"] == True and form.menu_cursor == 0:
            autosleep_off()
            # tm=form.inp_list()["inp_0"]
            # try:
            #     if int(tm)<=14400:
            #         update_sleep_time(int(tm)*60000)
            #         print("db time = ",get_sleep_time(), "form input time = ", tm)
            #         form.form_list=["sleep after minutes:", "inp_0", "updated successfully"]
            #         form.update()
            #         form_refresh.refresh()
            #     elif int(tm)>14400:
            #         form.form_list=["sleep after minutes:", "inp_0", "maximum is 14400"]
            #         form.update()
            #         form_refresh.refresh()
            # except:
            #     form.form_list=["sleep after minutes:", "inp_0", "wrong input"]
            #     form.update()
            #     form_refresh.refresh()
        elif inp == "ok" and db.search(q.feature=="auto_sleep")[0]["value"] == False and form.menu_cursor == 0:
            autosleep_on()
        elif inp == "ok" and db.search(q.feature=="auto_sleep")[0]["value"] == True and form.menu_cursor != 0:
            tm=form.inp_list()["inp_0"]
            try:
                if int(tm)<=14400 and int(tm)>=1:
                    # update_sleep_time(int(tm)*60000)
                    db.update({'value':int(tm)*60000}, q.feature == 'sleep_timer')
                    swdt.update_time(timeout_ms=int(tm)*60000)
                    print("db time = ",db.search(q.feature=="sleep_timer")[0]["value"], "form input time = ", tm)
                    display.clear_display()
                    form.input_list={"inp_0": str(int(db.search(q.feature=="sleep_timer")[0]["value"]/60000))}
                    # form.form_list=["autosleep: ON","sleep after minutes:", "inp_0", "updated successfully"]
                    form.form_list.append("updated successfully")
                    form.update()
                    form_refresh.refresh()
                    print("update form refresh", form.form_list, form.actual_rows)
                elif int(tm)>14400:
                    display.clear_display()
                    form.input_list={"inp_0": str(int(db.search(q.feature=="sleep_timer")[0]["value"]/60000))}
                    # form.form_list=["autosleep: ON","sleep after minutes:", "inp_0", "maximum is 14400"]
                    form.form_list.append("maximum is 14400")
                    form.update()
                    form_refresh.refresh()
                elif int(tm)<1:
                    display.clear_display()
                    form.input_list={"inp_0": str(int(db.search(q.feature=="sleep_timer")[0]["value"]/60000))}
                    # form.form_list=["autosleep: ON","sleep after minutes:", "inp_0", "maximum is 14400"]
                    form.form_list.append("minimum is 1")
                    form.update()
                    form_refresh.refresh()
            except:
                display.clear_display()
                form.input_list={"inp_0": str(int(db.search(q.feature=="sleep_timer")[0]["value"]/60000))}
                # form.form_list=["autosleep: ON","sleep after minutes:", "inp_0", "wrong input"]
                form.form_list.append("wrong input")
                form.update()
                form_refresh.refresh()
                print(form.form_list, form.actual_rows)
        
        elif inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            form.update_buffer("")
        elif inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
            # if "updated successfully" in form.form_list:
            #     form.form_list.pop()
            #     form.update()
            #     form_refresh.refresh()
        form_refresh.refresh(state=nav.current_state())
        print("last form refresh", form.form_list, form.actual_rows)
    
        # time.sleep(0.2)
