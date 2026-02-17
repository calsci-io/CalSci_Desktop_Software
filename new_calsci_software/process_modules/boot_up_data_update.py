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
import json

from data_modules.object_handler import data_bucket, current_app

def main():
    boot_up_file = "db/boot_up.json"

    with open(boot_up_file, "r") as file:
        boot_up_data = json.load(file)

    if data_bucket["connection_status_g"]:
        boot_up_data["states"]["wifi_connected"] = True

    boot_up_data["data_points"]["last_used_app"] = (
        current_app[0] if current_app[0] != "update" else "home"
    )
    boot_up_data["data_points"]["last_used_app_folder"] = (
        current_app[1] if current_app[1] != "update" else "application_modules"
    )

    with open(boot_up_file, "w") as file:
        json.dump(boot_up_data, file)
