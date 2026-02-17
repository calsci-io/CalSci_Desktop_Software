import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

# import _thread
# from dynamic_stuff.dynamic_functions import get_data
from dynamic_stuff.dynamic_switches import new_upload
from dynamic_stuff.dynamic_data import menu_items_data
# from data_modules.object_handler import menu
# from data_modules.object_handler import chrs
import time

def refresh():
    buf=menu.buffer()
    ref_rows=menu_items_data.keys()
    for i in ref_rows:
        if i in range(menu.menu_display_position,menu.menu_display_position+menu.rows):
            display.set_page_address(i-menu.menu_display_position)
            display.set_column_address(0)
            # print("---key pressed---")
            # print("display page address = ", i-menu.menu_display_position)
            # print("menu item index = ", i)
            # print("menu_display_pos = ", menu.menu_display_position)
            # print("menu cursor = ", menu.cursor())
            menu_items_data[i]+=" "*(menu.cols-len(menu_items_data[i]))
            for j in menu_items_data[i]:
                if i-menu.menu_display_position == menu.cursor():
                    chtr_byte_data=chrs.invert_letter(j)
                    cursor_line=0b11111111
                    for k in chtr_byte_data:
                        display.write_data(k)
                    display.write_data(cursor_line)
                else:
                    chtr_byte_data=chrs.Chr2bytes(j)
                    cursor_line=0b00000000
                    for k in chtr_byte_data:
                        display.write_data(k)
                    display.write_data(cursor_line)
    menu_items_data.clear()

def uploader():
    while new_upload[0]==True:
        # data = get_data()
        # for i in data.keys():
        #     if i in range(menu.menu_display_position,menu.menu_display_position+menu.rows):
        #         pass
        refresh()
        time.sleep(0.1)
