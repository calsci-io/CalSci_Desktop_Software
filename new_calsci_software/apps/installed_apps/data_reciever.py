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
from data_modules.object_handler import nav, keypad_state_manager, typer, keymap
from data_modules.object_handler import current_app
from process_modules import boot_up_data_update
from data_modules.object_handler import app
from machine import Pin, ADC, deepsleep, reset

from dynamic_stuff.dynamic_switches import *
from dynamic_stuff.dynamic_menu_buffer_uploader import uploader
# from dynamic_stuff.dynamic_menu_buffer_data_generator import data_generator
from bootup_configs import bootup
import time
import json
from data_modules.object_handler import nav, keypad_state_manager, typer, sta_if
import espnow
# e.active(True)
from data_modules.object_handler import current_app
# from process_modules import boot_up_data_update
from data_modules.object_handler import app
import _thread
from dynamic_stuff.dynamic_data import menu_items_data
import gc
gc.enable()
def data_generator():
    e = espnow.ESPNow()
    e.active(True)
    while data_generator_status[0]==True:
        gc.collect()
        host, msg = e.recv()
        if msg:             # msg == None if timeout in recv()
            mac_str = ''.join('{:02X}'.format(b) for b in host)
            print(mac_str, msg)
            temp = round(float(msg), 2)
        # raw_value = adc.read()
        # voltage = (raw_value / 4095) * 3.3
        # print(voltage)
            menu_list = ["slave:", mac_str,"temp:",str(temp)]
        # if round(2*voltage +0.220, 3) <= 3.7 :
        #     deepsleep()
            data = {0:menu_list[0],1:menu_list[1],2:menu_list[2],3:menu_list[3]}
            print(data)
        # menu_items_data.clear()
        # menu_items_data=data
            menu_items_data.clear()
            menu_items_data.update(data)

            for i in menu_items_data:
                menu.menu_list[i]=menu_items_data[i]
            # time.sleep(5)
    e.active(False)
def data_reciever():
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
    menu_list=["slave:", "None","temp:","None"]
    menu.menu_list=menu_list
    menu.update()
    menu_refresh.refresh()
    try:
        while True:
            # raw_value = adc.read()
            # voltage = (raw_value / 4095) * 3.3
            # menu_list = ["battery voltage:", str(round(2*voltage +0.220, 3))]
            inp = typer.start_typing()
            if inp == "back":
                app.set_app_name("installed_apps")
                app.set_group_name("root")
                new_upload[0] = False
                data_generator_status[0]=False
                reset()
                # sta_if.active(False)
                # _thread.start_new_thread(bootup, ())
                # menu_list=["slave:", "None","temp:","None"]
                # menu.menu_list=menu_list
                # time.sleep(0.1)
                # e.active(False)
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
            menu.update_buffer(inp)
            menu_refresh.refresh()
            # time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
