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
from data_modules.object_handler import nav, keypad_state_manager, typer, keymap
from data_modules.object_handler import current_app
from process_modules import boot_up_data_update
from data_modules.object_handler import app
# from hcsr04 import HCSR04
import dht
import machine
from dynamic_stuff.dynamic_switches import *
# from dynamic_stuff.dynamic_switches import data_generator_status
from dynamic_stuff.dynamic_data import menu_items_data
from dynamic_stuff.dynamic_menu_buffer_uploader import uploader
import time
import _thread
sensor = dht.DHT11(machine.Pin(43))

# def dist_measure(sensor):
#     try:
#         distance = sensor.distance_cm()
#         print('Distance:', distance, 'cm')
#     except OSError as e:
#         print('Sensor error:', e)
#     time.sleep(1)

def get_data(sensor=sensor):
    # a=random.randint(1,99)
    # b=random.randint(1000,5000)
    # c=[a,b]
    sensor.measure()
    t=sensor.temperature()
    h=sensor.humidity()
    c={
        0:"temperature in celcius:",
        1:"=> "+str(t),
        2:"humidity in %:",
        3:"=> "+str(h)
    }
    return c

def data_generator():

    while data_generator_status[0]==True:
        data = get_data()
        # menu_items_data.clear()
        # menu_items_data=data
        menu_items_data.clear()
        menu_items_data.update(data)
        for i in menu_items_data:
            menu.menu_list[i]=menu_items_data[i]
        time.sleep(0.1)

def dht11(db={}):
    new_upload[0] = False
    data_generator_status[0] = False
    # sensor = HCSR04(trigger_pin=16, echo_pin=2)
    display.clear_display()
    menu_list=["temperature in celcius:", "=> ",  "humidity in %:", "=> "]
    menu.menu_list=menu_list
    menu.update()
    menu_refresh.refresh()
    try:
        while True:
            inp = typer.start_typing()
            
            if inp == "back":
                new_upload[0] = False
                data_generator_status[0]=False
                break
            
            elif inp == "alpha" or inp == "beta":                        
                keypad_state_manager(x=inp)
                menu.update_buffer("")
            elif inp =="ok":
                # distance = sensor.distance_cm()
                # menu.menu_list=["distance:", str(distance)]
                # menu.update()
                # menu_refresh.refresh()
                new_upload[0] = not new_upload[0]
                data_generator_status[0] = not data_generator_status[0]
                # print("switch status changed")
                if new_upload[0] == True or data_generator_status[0] == True:

                #     _thread.start_new_thread(single_fun, ())
                #     print("starting the thread")
                    _thread.start_new_thread(uploader, ())
                    _thread.start_new_thread(data_generator, ())
            menu.update_buffer(inp)
            menu_refresh.refresh(state=nav.current_state())
            # time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
