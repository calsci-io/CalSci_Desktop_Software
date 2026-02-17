import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import time  # type:ignore
# from math import *
# import 
from data_modules.object_handler import display, text, nav, text_refresh, typer, keypad_state_manager, keypad_state_manager_reset, current_app, app
# from process_modules import boot_up_data_update
from data_modules.object_handler import data_bucket
from process_modules.text_buffer import Textbuffer
from process_modules.text_buffer_uploader import Tbf
# t_error=Textbuffer()
# t_error.all_clear()
# try:
#     print("error_screen", data_bucket["error_msg"])
#     t_error.update_buffer(data_bucket["error_msg"])
#     # data_bucket.pop("error_msg")
# except:
#     t_error.update_buffer("No error message")
# t_error_refresh=Tbf(disp_out=display, chrs=chrs, t_b=t_error)

def error_screen():
    t_error=Textbuffer()
    t_error.all_clear()
    try:
        print("error_screen", data_bucket["error_msg"])
        t_error.update_buffer(data_bucket["error_msg"])
        # data_bucket.pop("error_msg")
    except:
        t_error.update_buffer("No error message")
    t_error_refresh=Tbf(disp_out=display, chrs=chrs, t_b=t_error)
    global task
    keypad_state_manager_reset()
    display.clear_display()
    text.retain_data=True
    # t_error.update_buffer("")
    t_error_refresh.refresh()
    # try:
    while True:
        time.sleep(0.5)
        x = typer.start_typing()
        try:
            app.set_app_name(data_bucket["error_parent_app_name"])
            app.set_group_name(data_bucket["error_parent_group_name"])
            break
        except:
            app.set_app_name("home")
            app.set_group_name("root")
            break
    # del t_error, t_error_refresh
    text.update_buffer("")
    return 0

