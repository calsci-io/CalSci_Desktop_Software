import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

class Nav:
    def __init__(self, elements=None):
        self.elements = elements or {
            "keypad": "D",
            "wifi": "WN",
            "bluetooth": "B",
            "capslock": "C",
            "app_name": "app",
            "charging": "NCH",
        }
        self.keypad = self.elements["keypad"]
        self.wifi = self.elements["wifi"]
        self.bluetooth = self.elements["bluetooth"]
        self.capslock = self.elements["capslock"]
        self.app_name = self.elements["app_name"]
        self.charging = self.elements["charging"]
        self.changed_element = ""
        
    def update_buffer(self, element):
        self.elements[element[0]] = element[1]
        self.changed_element = element[0]
        self.keypad = self.elements["keypad"]
        self.wifi = self.elements["wifi"]
        self.bluetooth = self.elements["bluetooth"]
        self.capslock = self.elements["capslock"]
        self.app_name = self.elements["app_name"]
        self.charging = self.elements["charging"]

    def buffer(self):
        buf=[self.keypad, self.wifi, self.bluetooth, self.capslock, self.app_name, self.charging]
        nav_str=""
        for i in range(len(buf)):
            nav_str += (buf[i] + "-" if i != len(buf)-1 else buf[i])
        return nav_str
    
    def refresh_element(self):
        return self.changed_element
    
    def update(self):
        pass
