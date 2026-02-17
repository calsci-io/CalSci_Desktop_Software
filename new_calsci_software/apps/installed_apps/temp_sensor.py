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
# from machine import Pin, ADC, deepsleep
# adc_pin = Pin(6)
# adc = ADC(adc_pin)
# adc.atten(ADC.ATTN_11DB)
# adc.width(ADC.WIDTH_12BIT)

# charge_pin=Pin(4, Pin.IN, Pin.PULL_DOWN)
# # from sleeping_features import test_deep_sleep_awake
# def battery_status_none():
#     display.clear_display()
#     # json_file = "/db/application_modules_app_list.json" 
#     # with open(json_file, "r") as file:
#     #     data = json.load(file)

#     # menu_list = []
#     # # for apps in data:
#     # #     if apps["visibility"]:
    
#     # #         menu_list.append(apps["name"])

#     # menu.menu_list=menu_list
#     # menu.update()
#     # menu_refresh.refresh()
#     try:
#         while True:
#             raw_value = adc.read()
#             voltage = (raw_value / 4095) * 3.3
#             menu_list = ["battery voltage:", str(round(2*voltage +0.220, 3))]
#             menu.menu_list=menu_list
#             menu.update()
#             menu_refresh.refresh()
#             # inp = typer.start_typing()

#             # if inp == "back":
#             #     pass
#             # elif inp == "alpha" or inp == "beta":                        
#             #     keypad_state_manager(x=inp)
#             #     menu.update_buffer("")
#             # elif inp =="ok":
#             #     app.set_app_name(menu.menu_list[menu.menu_cursor])
#             #     app.set_group_name("root")
#             #     break

#             # menu.update_buffer(inp)
#             # menu_refresh.refresh(state=nav.current_state())
#             time.sleep(1)
#     except Exception as e:
#         print(f"Error: {e}")


"""
things to be made:
1. dynamic menu buffer uploader in thread
2. dynamic menu buffer data generator
3. dynamic global switch which is turned on by data generator and turned off by uploader
4. a switch for turning on the data generator on or off
5. if a function is given to the data generator then it will stay on or it will turn off
"""
from dynamic_stuff.dynamic_switches import *
from dynamic_stuff.dynamic_menu_buffer_uploader import uploader
# from dynamic_stuff.dynamic_menu_buffer_data_generator import data_generator
import time
import json
from data_modules.object_handler import nav, keypad_state_manager, typer
from data_modules.object_handler import current_app
# from process_modules import boot_up_data_update
from data_modules.object_handler import app
import _thread
from dynamic_stuff.dynamic_data import menu_items_data
# def single_fun():
#     data_generator()
#     uploader()
#     time.sleep(0.1)

# def data_generator():

#     while data_generator_status[0]==True:
#         raw_value = adc.read()
#         voltage = (raw_value / 4095) * 3.3
#         print(voltage)
#         menu_list = ["battery voltage:", str(round(2*voltage +0.220, 3))+" "+str(charge_pin.value())]
#         if round(2*voltage +0.220, 3) <= 3.7 :
#             # deepsleep()
#             pass
#         data = {0:menu_list[0],1:menu_list[1]}
#         # menu_items_data.clear()
#         # menu_items_data=data
#         menu_items_data.clear()
#         menu_items_data.update(data)

#         for i in menu_items_data:
#             menu.menu_list[i]=menu_items_data[i]
#         time.sleep(5)

import network
import time
import ujson
import random
from umqtt.robust import MQTTClient
import config
import machine
import ntptime

import espnow
macs = [
    "349F14333413",
    "1039FD70D7DE",
    "065C087E1271",
    "0EA6185C9043",
    "EFEA81F6C36C",
    "E829A0CBE235",
    "3C3B7A6B1F43",
    "AB8DAA24A9B8",
    "D63F7598FF52",
    "97C59EC4D69B"
]

# import urandom

def random_mac():
    # 6 bytes → 12 hex chars
    mac_bytes = [random.getrandbits(8) for _ in range(6)]
    return ''.join('{:02X}'.format(b) for b in mac_bytes)

def rtc_isoformat():
    rtc = machine.RTC()
    y, m, d, wd, hh, mm, ss, sub = rtc.datetime()
    # Format: YYYY-MM-DD HH:MM:SS[.ffffff] UTC
    return "{}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}.{:06d} UTC".format(
        y, m, d, hh, mm, ss, sub
    )

def byte_to_mac(mac_bytes):
    # mac_bytes is a bytes object like b'\x30\xae...' -> "30AE1C..."
    return ''.join('{:02X}'.format(b) for b in mac_bytes)

# ---- Load certs (DER format) ----
with open(config.CERT_KEY_PATHS["key_der"], 'rb') as f:
    DEV_KEY = f.read()
with open(config.CERT_KEY_PATHS["cert_der"], 'rb') as f:
    DEV_CRT = f.read()
with open(config.CERT_KEY_PATHS["ca_der"], 'rb') as f:
    CA_CRT = f.read()


# ---- WiFi Connection ----
def wifi():
    print("Connecting to WiFi...")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    wlan.disconnect()
    wlan.connect(config.WIFI_SSID, config.WIFI_PASS)

    while not wlan.isconnected():
        print(".", end="")
        time.sleep(1)

    print("\n✅ WiFi connected:", wlan.ifconfig())
    ntptime.settime()


# ---- MQTT ----
def on_msg(topic, msg):
    print("\n<< FROM AWS:", topic, msg)


def mqtt_connect():
    c = MQTTClient(
        client_id=config.CLIENT_ID,
        server=config.AWS_ENDPOINT,
        port=8883,
        keepalive=60,
        ssl=True,
        ssl_params={
            "key": DEV_KEY,
            "cert": DEV_CRT,
            "cadata": CA_CRT,
            "server_side": False
        }
    )
    c.set_callback(on_msg)
    c.connect()
    c.subscribe(config.TOPIC_DOWN)
    print("MQTT connected, subscribed to", config.TOPIC_DOWN)
    return c




# ---- Build payload with slaves ----
def build_payload():
    global macs
    slaves = []
    for i in range(0, 10):  # 3 slaves for example
        if random.random() > 0.2:  # 80% chance slave is OK
            temp = round(random.uniform(30.0, 35.0), 1)
            status = "ok"
        else:
            temp = None
            status = "missing"

        slaves.append({
            "slave_id": macs[i],
            "temperature": temp,
            "status": status
        })
    time_stamp=rtc_isoformat()
    payload = {
        "master_id": byte_to_mac(machine.unique_id()),
        "timestamp": time_stamp,
        "slaves": slaves
    }
    print(payload)
    return ujson.dumps(payload)



# ---- Main ----
def main():
    # wifi()
    client = mqtt_connect()
    while True:
        payload = build_payload()
        client.publish(config.TOPIC_UP, payload)
        print(">> TO AWS:", payload)
        client.check_msg()  # check if any DOWN messages arrived
        time.sleep(10)  # every 10 seconds


# if __name__ == "__main__":
#     main()

def data_generator():
    client = mqtt_connect()
    counter = 1
    e = espnow.ESPNow()
    e.active(True)
    e.config(timeout_ms=2000)
    while data_generator_status[0]==True:
        # payload = build_payload()
        # client.publish(config.TOPIC_UP, payload)
        mac_str="NO DEVICE"
        temp="0"
        host, msg = e.recv()
        if msg:             # msg == None if timeout in recv()
            mac_str = ''.join('{:02X}'.format(b) for b in host)
            print(mac_str, msg)
            temp = round(float(msg), 2)
            slaves = []
            slaves.append({
            "slave_id": mac_str,
            "temperature": temp,
            "status": "ok"
                })
            time_stamp=rtc_isoformat()
            payload = {
                "master_id": byte_to_mac(machine.unique_id()),
                "timestamp": time_stamp,
                "slaves": slaves
            }
            # print(payload)
            payload = ujson.dumps(payload)
            # client.publish(config.TOPIC_UP, payload)
        else:
            # payload = build_payload()
            continue
        client.publish(config.TOPIC_UP, payload)
        # print(">> TO AWS:", payload)
        # client.check_msg()  # check if any DOWN messages arrived

        # raw_value = adc.read()
        # voltage = (raw_value / 4095) * 3.3
        # print(voltage)
        menu_list = ["mac= "+mac_str, "temp: "+str(temp)+" "+str(counter)]
        # if round(2*voltage +0.220, 3) <= 3.7 :
        #     # deepsleep()
        #     pass
        data = {0:menu_list[0],1:menu_list[1]}
        # menu_items_data.clear()
        # menu_items_data=data
        menu_items_data.clear()
        menu_items_data.update(data)

        for i in menu_items_data:
            menu.menu_list[i]=menu_items_data[i]
        counter+=1
        time.sleep(1)

def temp_sensor():
    ntptime.settime()
    # client = mqtt_connect()
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
    menu_list=["press ok", "to start"]
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
