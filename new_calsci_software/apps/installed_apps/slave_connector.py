import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

# import time
from data_modules.object_handler import keypad_state_manager, sta_if
from data_modules.object_handler import app
import _thread

def ssid_is_mac_like(s):
    """Return True if s looks like 12 hex characters (MAC without separators)."""
    if len(s) != 12:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False

def scanner():
    sta_if.active(True)
    all_ssids=sta_if.scan()
    print(all_ssids)
    strong_ssids=[]
    for ssid in all_ssids:
        if ssid[3]>=-80 and ssid_is_mac_like(ssid[0].decode()):
            strong_ssids.append(ssid[0].decode())
    # print(strong_ssids)
    return strong_ssids

def show_slaves():
    display.clear_display()
    menu.menu_list.clear()
    menu.menu_list.append("Scanning...")
    menu.menu_list.append("wait for a sec...")
    menu.update()
    menu_refresh.refresh()
    
    l=scanner()
    menu.menu_list.clear()
    if len(l) != 0:

    # menu.menu_list.clear()
        menu.menu_list.append("available slaves:")
        menu.menu_list.extend(l)
    else:
        menu.menu_list.extend(["Sorry", "No Slaves Found"])
    # print(menu.menu_list)
    menu.update()
    menu_refresh.refresh()

def slave_connector():
    _thread.start_new_thread(show_slaves, ())
    try:
        while True:
            inp_menu = typer.start_typing()

            if inp_menu == "back":
                app.set_app_name("installed_apps")
                app.set_group_name("root")
                break  

            elif inp_menu =="ok":
                pass
            menu.update_buffer(inp_menu)
            menu_refresh.refresh(state=nav.current_state())
            # time.sleep(0.2)
    except Exception as e:
        print(f"Error: {e}")
