import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

class App():
    def __init__(self):
        self.app_data = {
            "app_name": None,
            "group_name": None,
        }
    
    def get_app_name(self):
        return self.app_data["app_name"]
    
    def get_group_name(self):
        return self.app_data["group_name"]

    def set_app_name(self, app_name):
        self.app_data["app_name"] = app_name
    
    def set_group_name(self, group_name):
        self.app_data["group_name"] = group_name
    
    def set_none(self):
        self.app_data["app_name"] = None
        self.app_data["group_name"] = None
    
