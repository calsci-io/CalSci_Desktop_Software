import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

from data_modules.object_handler import keypad_state_manager , typer , display
import time


pinval=False
def check_buzzer():
    global pinval
    import machine
    from machine import Pin
    pin=Pin(2,Pin.OUT)
    if pinval is False :
        pin.value(0)
        pinval=True
        return False
    else:
        pin.value(1)
        pinval=False    
        return True
   
        
        

def buzzer():
    # sensor = HCSR04(trigger_pin=16, echo_pin=2)
    display.clear_display()
    menu_list=["buzzer testing : ", "GPIO - 2", "hit ok to start"]
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
                result=check_buzzer()
                display.clear_display()
                if result:
                   menu_list=["Buzzer activated"]
                else:
                   menu_list=["Buzzer deactivated"]
                menu.menu_list=menu_list
                menu.update()
                menu_refresh.refresh()
                print(menu.ref_ar())
            menu.update_buffer(inp)
            menu_refresh.refresh(state=nav.current_state())
            time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
