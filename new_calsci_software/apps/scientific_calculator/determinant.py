# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
from math import *
import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh, keymap
from process_modules import boot_up_data_update
from data_modules.object_handler import current_app


def calculator(n, matrix=[]):
    while True:
        inp = typer.start_typing()
        if inp == "back":
            form.input_list={"inp_0": " "}
            form.form_list = ["Enter matrix dimension", "inp_0"]
            form.update()
            display.clear_display()
            form_refresh.refresh()
            break

        
        if inp == "ok":
            if n == 1:
                form.form_list = ["determinant is:", form.input_list["inp_1"]]

            if n == 2:
                # print(form.input_list["inp_1"])
                # print(form.input_list["inp_2"])

                a1, b1 = list(map(int, form.input_list["inp_1"].split("+")))
                a2, b2 = list(map(int, form.input_list["inp_2"].split("+")))
                # print(a1, b1)
                # print(a2, b2)

                det = a1 * b2 - a2 * b1
                # print(det)
                form.form_list = ["determinant is:", f"{det}"]

            if n > 2:

                def det_cal(matrix, n):
                    if n == 1:
                        return matrix[0][0]
                    if n == 2:
                        return matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
                    
                    det = 0
                    for j in range(n):
                        submatrix = [[matrix[i][k] for k in range(n) if k != j] for i in range(1, n)]
                        det += ((-1) ** j) * matrix[0][j] * det_cal(submatrix, n-1)
                    return det

                matrix = []
                for i in range(1, n + 1):
                    a = list(map(int, form.input_list[f"inp_{i}"].split("+")))
                    matrix.append(a)

                det = det_cal(matrix, n)
                form.form_list = ["determinant is:", f"{det}"]

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



def determinant(db={}):
    form.input_list={"inp_0": " "}
    form.form_list = ["Enter matrix dimension", "inp_0"]
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
            n = int(form.input_list["inp_0"])
            form.form_list = []
            for i in range(1, n + 1):
                form.input_list[f"inp_{i}"] = " "
                form.form_list.append(f"Enter row no. {i}")
                form.form_list.append(f"inp_{i}")
            form.update()
            display.clear_display()
            form_refresh.refresh()
            
            calculator(n=n)
            



                 

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



