import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

"""
things to be made:
1. dynamic menu buffer uploader in thread
2. dynamic menu buffer data generator
3. dynamic global switch which is turned on by data generator and turned off by uploader
4. a switch for turning on the data generator on or off
5. if a function is given to the data generator then it will stay on or it will turn off
"""
from dynamic_stuff.dynamic_switches import *
# from dynamic_stuff.dynamic_form_buffer_uploader import uploader
# from dynamic_stuff.dynamic_form_buffer_data_generator import data_generator
import time
import json
from data_modules.object_handler import nav, keypad_state_manager, typer
from data_modules.object_handler import current_app
# from process_modules import boot_up_data_update
from data_modules.object_handler import app
import _thread
import random
# def single_fun():
#     data_generator()
#     uploader()
#     time.sleep(0.1)

def data_generator():
    while data_generator_status[0] == True:
        form.form_list[1]=str(random.randint(50,100))
        form.form_list[2]=str(random.randint(50,100))
        form.form_list[3]=str(random.randint(50,100))
        form.form_list[4]=str(random.randint(50,100))
        form.form_list[5]=str(random.randint(50,100))
        form.form_list[6]=str(random.randint(50,100))
        form.display_buffer=form.form_list[form.menu_display_position:form.menu_display_position+form.menu_display_size]
        print("generator thread ran")
        time.sleep(0.5)
    print("generator thread stopped")
def uploader():
    while new_upload[0] == True:
        print(form.buffer())
        form.refresh_rows=(0,form.actual_rows)
        print("ref ar = ", form.ref_ar())
        form_refresh.refresh(state=nav.current_state())
        print("uploader thread ran")
        time.sleep(0.5)
    print("uploader thread stopped")


def dynamic_form(db={}):
    # _thread.start_new_thread(single_fun, ())
    global data_generator_status, new_upload
    new_upload[0] = False
    data_generator_status[0] = False
    display.clear_display()
    # json_file = "/db/application_modules_app_list.json" 
    # with open(json_file, "r") as file:
    #     data = json.load(file)

    # menu_list = []
    # for apps in data:
    #     if apps["visibility"]:
    #         menu_list.append(apps["name"])
    form.input_list={"inp_0": ""}
    menu_list=["press ok", "random a", "random b", "random c", "random d", "random e", "random f", "inp_0", "random h", "random i", "random j"]
    form.form_list=menu_list
    form.update()
    form_refresh.refresh()
    try:
        while True:
            inp = typer.start_typing()
            if inp == "back":
                app.set_app_name("installed_apps")
                app.set_group_name("root")
                new_upload[0] = False
                data_generator_status[0]=False
                break
            elif inp =="ok":
                
                # app.set_app_name(menu.menu_list[menu.menu_cursor])
                # app.set_group_name("root")
                # break
                # if new_upload == False or data_generator_status == False:
                
                # new_upload[0] = True
                # data_generator_status[0] = True
                new_upload[0] = not new_upload[0]
                data_generator_status[0] = not data_generator_status[0]
                # print("switch status changed")
                if new_upload[0] == True or data_generator_status[0] == True:

                #     _thread.start_new_thread(single_fun, ())
                #     print("starting the thread")
                    _thread.start_new_thread(uploader, ())
                    _thread.start_new_thread(data_generator, ())
            elif inp == "alpha" or inp == "beta":
                keypad_state_manager(x=inp)
                form.update_buffer("")
            elif inp not in ["alpha", "beta", "ok"]:
                form.update_buffer(inp)
            # form.update_buffer(inp)
            # print("ref_ar", form.ref_ar())
            # form.form_list[2]=str(random.randint(50,100))
            # form.refresh_rows=(0,form.actual_rows)
            # print("ref_ar", form.ref_ar())
            form_refresh.refresh(state=nav.current_state())
            # time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
