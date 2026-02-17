# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
from math import *
import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh
from process_modules import boot_up_data_update
from data_modules.object_handler import current_app, data_bucket



def calculator(r1, c1, r2, c2):
    while True:
        inp = typer.start_typing()
        if inp == "back":
            form.input_list={"inp_0": " ", "inp_1": " "}
            form.form_list = ["rows and cols of mat1", "r1+c1", "inp_0", "rows and cols of mat2", "r2+c2", "inp_1"]
            form.update()
            display.clear_display()
            form_refresh.refresh()
            break

        
        if inp == "ok":
            matrix1 = []
            matrix2 = []
            for i in range(1, r1 + 1):
                    a = list(map(int, form.input_list[f"inp_{i}"].split("+")))
                    matrix1.append(a)
            for i in range(1, r2 + 1):
                    a = list(map(int, form.input_list[f"inp_{r1 + i}"].split("+")))
                    matrix2.append(a)
            result = [[0 for _ in range(c1)] for _ in range(r1)]
            for i in range(r1):
                for j in range(c2):
                        result[i][j] += matrix1[i][j] + matrix2[i][j]
            form.form_list = ["Resulting matirx", "after addition:"]
            form.form_list.append(f"Rows = {r1}")
            form.form_list.append(f"Cols = {c1}")
            form.form_list.append("Matrix:")
            for i in result:
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



def add_matrices(db={}):
    form.input_list={"inp_0": " ", "inp_1": " "}
    form.form_list = ["rows and cols of mat1", "r1+c1", "inp_0", "rows and cols of mat2", "r2+c2", "inp_1"]
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
            r2, c2 = list(map(int, form.input_list["inp_1"].split("+")))

            if r1 != r2 or c1 != c2:
                form.form_list = ["Matrix addition", "not possible"]
                form.update()
                display.clear_display()
                form_refresh.refresh()

            else:
                form.form_list = ["Matrix 1"]
                for i in range(1, r1 + 1):
                    form.input_list[f"inp_{i}"] = " "
                    form.form_list.append(f"Enter row no. {i}")
                    form.form_list.append(f"inp_{i}")
                
                form.form_list.append("Matrix 2")
                for i in range(1, r2 + 1):
                    form.input_list[f"inp_{r1 + i}"] = " "
                    form.form_list.append(f"Enter row no. {i}")
                    form.form_list.append(f"inp_{r1 + i}")
                form.update()
                display.clear_display()
                form_refresh.refresh()
                calculator(r1, c1, r2, c2)
            
            
            
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



