import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import urequests as req
import network
import ubinascii
from process_modules import update_feature as updater

def update(db={}):
    print("Entered update file")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)  # Ensure the Wi-Fi interface is active

    mac_address = wlan.config('mac')
    mac_address_in_hex = ubinascii.hexlify(mac_address).decode().upper() # Convert to hexadecimal string
    print(mac_address_in_hex)  

    app_check = req.get(f"https://czxnvqwbwszzfgecpkbi.supabase.co/functions/v1/check-pending-apps?macAddress={mac_address_in_hex}").json()
    print("Got 1st response check")
    print(f"1st response is{app_check}")
    if app_check["response"] in ["download", "update", "delete"]:
    # if app_check["response"]:

        app_details = req.get(f"https://czxnvqwbwszzfgecpkbi.supabase.co/functions/v1/get-pending-apps?macAddress={mac_address_in_hex}").json()
        print("Got 2nd response download")
        print(app_details)

        app_action = app_check["response"]
        app_name = app_details["response"]["app_name"]
        app_folder = app_details["response"]["app_folder"]
        if app_action != "delete":
            app_code = app_details["response"]["code"]
            print(type(app_code))
            # print(app_code)
            updater.app_updater(app_name=app_name, app_folder=app_folder, app_code=app_code, mac_address_in_hex=mac_address_in_hex)

        else:
            updater.app_deleter(app_name=app_name, app_folder=app_folder, mac_address_in_hex=mac_address_in_hex)

    else:
        print("Nothing to update or delete")
