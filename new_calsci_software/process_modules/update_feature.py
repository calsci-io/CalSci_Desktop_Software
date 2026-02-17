import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import os

import machine
import urequests as req



def create_app_file(app_name, app_folder, app_code, mac_address_in_hex):
    installed_apps_location = app_folder
    app_file_path = f"{installed_apps_location}/{app_name}.py"
    os.mkdir(installed_apps_location)
    
    with open(app_file_path, "w") as app_to_install:
        app_to_install.write(app_code)
        
    app_check = req.get(
        "https://czxnvqwbwszzfgecpkbi.supabase.co/functions/v1/"
        f"confirm-download?macAddress={mac_address_in_hex}"
    ).json()
    if app_check["response"] in ["update_downloaded", "update_updated"]:
        boot_up_data_update.main()
        machine.reset()
        
    print("Installation error")
    
def add_to_json(new_app, file_name):
    if not os.path.exists(file_name):
        with open(file_name, "w") as file:
            json.dump([], file)

    with open(file_name, "r") as file:
        data = json.load(file)
    
    data.append(new_app)
    
    with open(file_name, "w") as file:
        json.dump(data, file)

def delete_app(app_name, app_folder, mac_address_in_hex):
    try:
        file_path = f"/{app_folder}/{app_name}"
        
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"File '{file_path}' deleted successfully.")
            app_check = req.get(
                "https://680fd07513e86af48dee.fra.appwrite.run/"
                f"success?mac={mac_address_in_hex}"
            ).json()
            if app_check["response"] == "deleted_successfully":
                boot_up_data_update.main()
                machine.reset()
        else:
            print(f"File '{file_path}' does not exist.")
    except OSError as e:
        print(f"Error deleting file '{file_path}': {e}")

def delete_app_from_json(app_name, json_file):
    with open(json_file, "r") as f:
        app_list = json.load(f)
    
    app_list = [app for app in app_list if app["name"] != app_name]
    
    with open(json_file, "w") as f:
        json.dump(app_list, f)


def app_updater(app_name, app_folder, app_code, mac_address_in_hex):
    print("entered main function of app_installer")
    app_name = app_name[:-3]
    installed_apps_location = app_folder
    new_app = {
        "name": app_name,
        "folder": installed_apps_location,
        "visibility": True,
    }
	json_file = f"/database/{INSTALLED_APPS_LOCATION}_app_list.json"
	add_to_json(new_app=new_app, file_name=json_file)
	print("name added to json")
	create_app_file(app_name=app_name, app_folder=app_folder, app_code=app_code, mac_address_in_hex=mac_address_in_hex)


def app_deleter(app_name, app_folder, mac_address_in_hex):
    installed_apps_location = app_folder
    json_file = f"/database/{installed_apps_location}_app_list.json"
    delete_app_from_json(app_name=app_name, json_file=json_file)
    delete_app(app_name=app_name, app_folder=app_folder, mac_address_in_hex=mac_address_in_hex)
            
