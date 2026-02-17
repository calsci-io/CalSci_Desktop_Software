# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
from math import *
import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh, keymap
from process_modules import boot_up_data_update
from data_modules.object_handler import current_app

def determinant(matrix):
    n = len(matrix)
    
    
    if n == 1:
        return matrix[0][0]
    
    if n == 2:
        return matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    
    det = 0
    for j in range(n):
        det += matrix[0][j] * cofactor(matrix, 0, j)
    return det

def cofactor(matrix, i, j):
    minor = get_minor(matrix, i, j)
    return ((-1) ** (i + j)) * determinant(minor)

def get_minor(matrix, i, j):
    return [[matrix[r][c] for c in range(len(matrix)) if c != j]
            for r in range(len(matrix)) if r != i]

def transpose(matrix):
    return [[matrix[j][i] for j in range(len(matrix))] for i in range(len(matrix[0]))]

def inverse(matrix, det):
    n = len(matrix)
    
        
    cofactor_matrix = [[cofactor(matrix, i, j) for j in range(n)] for i in range(n)]
    adjugate = transpose(cofactor_matrix)
    inverse_matrix = [[adjugate[i][j] / det for j in range(n)] for i in range(n)]
    return inverse_matrix

def calculator(r1, c1):
    while True:
        inp = typer.start_typing()
        if inp == "back":
            form.input_list={"inp_0": " "}
            form.form_list = ["matrix_inverse", "rows and cols of mat1", "r1+c1", "inp_0"]
            form.update()
            display.clear_display()
            form_refresh.refresh()
            break

        
        if inp == "ok":
            matrix = []
            for i in range(1, r1 + 1):
                    a = list(map(int, form.input_list[f"inp_{i}"].split("+")))
                    matrix.append(a)

            det = determinant(matrix)
            if det == 0:
                form.form_list = ["Inverse Matrix", "not possible"]
            else:
            
                inv_matrix = inverse(matrix, det)

                form.form_list = ["Inverse matirx", f"Rows = {len(inv_matrix)}", f"Cols = {len(inv_matrix[0])}"]
                form.form_list.append("Matrix:")
                for i in inv_matrix:
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



def matrix_inverse(db={}):
    form.input_list={"inp_0": " "}
    form.form_list = ["matrix_inverse", "rows and cols of mat1", "r1+c1", "inp_0"]
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
            machine.deepsleep()
        if inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
        form_refresh.refresh(state=nav.current_state())
        time.sleep(0.15)