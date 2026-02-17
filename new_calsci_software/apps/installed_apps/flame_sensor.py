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
from data_modules.object_handler import keypad_state_manager, display
# from data_modules.object_handler import current_app
# from process_modules import boot_up_data_update
from data_modules.object_handler import app
# from hcsr04 import HCSR04

# def dist_measure(sensor):
#     try:
#         distance = sensor.distance_cm()
#         print('Distance:', distance, 'cm')
#     except OSError as e:
#         print('Sensor error:', e)
#     time.sleep(1)

def flame_sensor_module():
    try:
        from machine import ADC, Pin
        adc_pin = Pin(2)  # Example: Using GPIO 26 on Raspberry Pi Pico
        adc = ADC(adc_pin)
        raw_value = adc.read()
        return str(raw_value)
    except:
        print("machine library not detected")
        import random
        v=random.randint(10, 50)
        return str(v)

def flame_sensor():
    # sensor = HCSR04(trigger_pin=16, echo_pin=2)
    display.clear_display()
    menu_list=["Flame sensor:", "GPIO - 2","Value = 0", "hit ok to start"]
    menu.menu_list=menu_list
    menu.update()
    menu_refresh.refresh()
    try:
        while True:
            inp = typer.start_typing()
            
            if inp == "back":
                break
            
            elif inp == "alpha" or inp == "beta":                        
                keypad_state_manager(x=inp)
                menu.update_buffer("")
            elif inp =="ok":
                v=flame_sensor_module()
                display.clear_display()
                menu_list=["Flame sensor:", "GPIO - 2","Value = "+v]
                menu.menu_list=menu_list
                menu.update()
                menu_refresh.refresh()
                print(menu.ref_ar())
            menu.update_buffer(inp)
            menu_refresh.refresh(state=nav.current_state())
            time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
