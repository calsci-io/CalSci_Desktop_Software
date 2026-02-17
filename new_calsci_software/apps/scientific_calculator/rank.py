# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
from math import *
import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh, keymap
from process_modules import boot_up_data_update
from data_modules.object_handler import current_app

def matrix_rank(matrix):
    if not matrix or not matrix[0]:
        return 0
    
    rows = len(matrix)
    cols = len(matrix[0])
    matrix = [row[:] for row in matrix]
    rank = 0
    pivot_col = 0
    
    while pivot_col < cols and rank < rows:
        pivot_row = rank
        while pivot_row < rows and matrix[pivot_row][pivot_col] == 0:
            pivot_row += 1
        
        if pivot_row == rows:
            pivot_col += 1
            continue
            
        if pivot_row != rank:
            matrix[rank], matrix[pivot_row] = matrix[pivot_row], matrix[rank]
        
        pivot = matrix[rank][pivot_col]
        if pivot != 0:
            for j in range(cols):
                matrix[rank][j] /= pivot
        
        for i in range(rows):
            if i != rank and matrix[i][pivot_col] != 0:
                factor = matrix[i][pivot_col]
                for j in range(cols):
                    matrix[i][j] -= factor * matrix[rank][j]
        
        rank += 1
        pivot_col += 1
    
    return rank


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
            
            rank = matrix_rank(matrix)
            form.form_list = [f"Rank = {rank}"]
            
            
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



def rank(db={}):
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



