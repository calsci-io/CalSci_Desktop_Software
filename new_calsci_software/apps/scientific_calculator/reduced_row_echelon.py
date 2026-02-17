# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
from math import *
import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh, keymap
from process_modules import boot_up_data_update
from data_modules.object_handler import current_app

def is_valid_matrix(matrix, rows, cols):
    if not matrix or len(matrix) != rows or not matrix[0]:
        return False
    
    for row in matrix:
        if len(row) != cols:
            return False
        
    
    return True, (rows, cols)

def reduced_row_echelon_form_finder(matrix, rows, cols):
    is_valid = is_valid_matrix(matrix, rows, cols)
    if not is_valid:
        form.form_list = ["Reduced Row Echelon", "Form not possible"]
        form.update()
        display.clear_display()
        form_refresh.refresh()
        return None  
    
    matrix = [[float(x) for x in row] for row in matrix]  
    pivot_row = 0
    pivot_col = 0
    pivot_positions = []  
    
    while pivot_row < rows and pivot_col < cols:
        pivot_found = False
        for i in range(pivot_row, rows):
            if abs(matrix[i][pivot_col]) > 1e-10:
                pivot_found = True
                if i != pivot_row:
                    matrix[pivot_row], matrix[i] = matrix[i], matrix[pivot_row]
                break
        
        if not pivot_found:
            pivot_col += 1
            continue
        
        pivot = matrix[pivot_row][pivot_col]
        if abs(pivot) > 1e-10:
            for j in range(cols):
                matrix[pivot_row][j] /= pivot
            pivot_positions.append((pivot_row, pivot_col))
        
        for i in range(pivot_row + 1, rows):
            if abs(matrix[i][pivot_col]) > 1e-10:
                factor = matrix[i][pivot_col]
                for j in range(cols):
                    matrix[i][j] -= factor * matrix[pivot_row][j]
        
        pivot_row += 1
        pivot_col += 1
    
    for pivot_row, pivot_col in reversed(pivot_positions):
        for i in range(pivot_row):
            if abs(matrix[i][pivot_col]) > 1e-10:
                factor = matrix[i][pivot_col]
                for j in range(cols):
                    matrix[i][j] -= factor * matrix[pivot_row][j]

    for i in range(rows):
        for j in range(cols):
            if abs(matrix[i][j]) < 1e-10:
                matrix[i][j] = 0.0
    
    return matrix

def calculator(r, c):
    while True:
        inp = typer.start_typing()
        if inp == "back":
            form.input_list={"inp_0": " "}
            form.form_list = ["Enter matrix dimension", "r + c", "inp_0"]
            form.update()
            display.clear_display()
            form_refresh.refresh()
            break

        
        if inp == "ok":
            matrix = []
            for i in range(1, r + 1):
                    a = list(map(int, form.input_list[f"inp_{i}"].split("+")))
                    matrix.append(a)
            
            row_reduced_form = reduced_row_echelon_form_finder(matrix, r, c)
                
            form.form_list = ["Reduced Row Echelon", "Form"]
            for row in row_reduced_form:
                t = [round(x, 4) for x in row]
                form.form_list.append(" ".join(str(x) for x in t))

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



def reduced_row_echelon(db={}):
    form.input_list={"inp_0": " "}
    form.form_list = ["Enter matrix dimension", "r + c", "inp_0"]
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
            r, c = list(map(int, form.input_list[f"inp_0"].split("+")))
            form.form_list = []
            for i in range(1, r + 1):
                form.input_list[f"inp_{i}"] = " "
                form.form_list.append(f"Enter row no. {i}")
                form.form_list.append(f"inp_{i}")
            form.update()
            display.clear_display()
            form_refresh.refresh()
            
            calculator(r, c)
                
            
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



