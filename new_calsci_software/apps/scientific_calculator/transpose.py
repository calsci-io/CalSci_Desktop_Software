# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
from math import *
import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh
from process_modules import boot_up_data_update
from data_modules.object_handler import current_app, data_bucket



def calculator(r1, c1):
    while True:
        inp = typer.start_typing()
        if inp == "back":
            form.input_list={"inp_0": " "}
            form.form_list = ["rows and cols of mat", "r1+c1", "inp_0"]
            form.update()
            display.clear_display()
            form_refresh.refresh()
            break

        
        if inp == "ok":
            matrix = []
            for i in range(1, r1 + 1):
                    a = list(map(int, form.input_list[f"inp_{i}"].split("+")))
                    matrix.append(a)
            
            transpose_matrix = [[0 for _ in range(r1)] for _ in range(c1)]
            
            form.form_list = ["Transpose matirx"]
            form.form_list.append(f"Rows = {c1}")
            form.form_list.append(f"Cols = {r1}")
            form.form_list.append("Matrix:")
            for i in range(r1):
                for j in range(c1):
                    transpose_matrix[j][i] = matrix[i][j]
            for i in transpose_matrix:
                form.form_list.append(" ".join(str(x) for x in i))
            
            form.update()
            display.clear_display()
            form_refresh.refresh()


        if inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            form.update_buffer("")

        if inp == "off":
            boot_up_data_update.main()
            machine.deepsleep()
        if inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
        form_refresh.refresh(state=nav.current_state())
        time.sleep(0.15)



def transpose(db={}):
    form.input_list={"inp_0": " "}
    form.form_list = ["rows and cols of mat", "r1+c1", "inp_0"]
    form.update()
    display.clear_display()
    form_refresh.refresh()

    while True:
        inp = typer.start_typing()
        if inp == "back":
            current_app[0]="matrix_operations"
            current_app[1]="scientific_calculator"
            break
        

        if inp == "ok":
            r1, c1 = list(map(int, form.input_list["inp_0"].split("+")))

            

            form.form_list = ["Matrix 1"]
            for i in range(1, r1 + 1):
                form.input_list[f"inp_{i}"] = " "
                form.form_list.append(f"Enter row no. {i}")
                form.form_list.append(f"inp_{i}")
            
            form.update()
            display.clear_display()
            form_refresh.refresh()

            calculator(r1, c1)
            
            
        if inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            form.update_buffer("")

        if inp == "off":
            boot_up_data_update.main()
            machine.deepsleep()
        if inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
        form_refresh.refresh(state=nav.current_state())
        time.sleep(0.15)



