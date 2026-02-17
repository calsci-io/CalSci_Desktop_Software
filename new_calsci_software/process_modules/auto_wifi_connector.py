import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import network # type: ignore
from data_modules.object_handler import display
import time
from data_modules.object_handler import data_bucket
import json
import time

import network  # type: ignore

from data_modules.object_handler import data_bucket, display

wifi_password_data = "/database/wifi.json"
sta_if = network.WLAN(network.STA_IF)

def auto_wifi_connector():
    display.clear_display()
    with open(wifi_password_data, "r") as file:
        data = json.load(file)

    network_names = scan_networks()
    network_names = network_names[:5] if len(network_names) >= 5 else network_names
    network_names[:] = [network[3:] for network in network_names]
        
    for network in data:
        for network_name in network_names:
            if network["ssid"] == network_name and not data_bucket["connection_status_g"]:
                do_connect(ssid=network_name, password=network["password"])
                data_bucket["connection_status_g"] = sta_if.isconnected()
                if data_bucket["connection_status_g"]:
                    data_bucket["ssid_g"] = network_name

                    break

                
def scan_networks():
    network_names = []
    station = network.WLAN(network.STA_IF)
    station.active(True)
    networks = station.scan()
    for i, network_info in enumerate(networks):
        ssid = network_info[0].decode()
        network_names.append(f"{i + 1}. {ssid}")

    return network_names

def do_connect(ssid, password):
    sta_if.active(True)
    if sta_if.isconnected():
        return None
    print(f"Trying to connect to {ssid}...")
    sta_if.connect(ssid, password)
    for _ in range(100):
        connected = sta_if.isconnected()
        if connected:
            break
        time.sleep(0.1)
    if connected:
        print("\nConnected. Network config: ", sta_if.ifconfig())
        
    else:
        print('\nFailed. Not Connected to: ' + ssid)

