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
    
    if rows != cols:
        return False
    
    for row in matrix:
        if len(row) != cols:
            return False
    
    return True

def qr_decomposition(matrix, n):
    """Perform QR decomposition using Gram-Schmidt process."""
    Q = [[0.0 for _ in range(n)] for _ in range(n)]
    R = [[0.0 for _ in range(n)] for _ in range(n)]
    A = [[float(x) for x in row] for row in matrix]
    
    for j in range(n):
        norm = 0.0
        for i in range(n):
            norm += A[i][j] ** 2
        norm = sqrt(norm)
        
        if abs(norm) < 1e-10:
            continue
            
        R[j][j] = norm
        for i in range(n):
            Q[i][j] = A[i][j] / norm
        
        for k in range(j + 1, n):
            dot = 0.0
            for i in range(n):
                dot += A[i][k] * Q[i][j]
            R[j][k] = dot
            for i in range(n):
                A[i][k] -= dot * Q[i][j]
    
    return Q, R

def matrix_multiply(A, B, n):
    result = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            for k in range(n):
                result[i][j] += A[i][k] * B[k][j]
    return result

def eigenvalues_finder(matrix, rows, cols):
    is_valid = is_valid_matrix(matrix, rows, cols)
    if not is_valid:
        form.form_list = ["Eigenvalues", "not possible"]
        form.update()
        display.clear_display()
        form_refresh.refresh()
        return None
    
    n = rows
    A = [[float(x) for x in row] for row in matrix]
    
    max_iterations = 200
    for _ in range(max_iterations):
        Q, R = qr_decomposition(A, n)
        A = matrix_multiply(R, Q, n)
    
    eigenvalues = []
    for i in range(n):
        val = A[i][i]
        eigenvalues.append(0.0 if abs(val) < 1e-10 else val)
    
    return eigenvalues

def calculator(n):
    while True:
        inp = typer.start_typing()
        if inp == "back":
            form.input_list = {"inp_0": " "}
            form.form_list = ["Enter square matrix", "dimension", "inp_0"]
            form.update()
            display.clear_display()
            form_refresh.refresh()
            break
        
        if inp == "ok":
            matrix = []
            for i in range(1, n + 1):
                a = list(map(int, form.input_list[f"inp_{i}"].split("+")))
                matrix.append(a)
            
            eigenvalues = eigenvalues_finder(matrix, n, n)
            if eigenvalues is None:
                return
                
            form.form_list = ["Eigen Values:"]
            for val in eigenvalues:
                form.form_list.append(str(round(val, 4)))
            
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

def eigen_values(db={}):
    form.input_list = {"inp_0": " "}
    form.form_list = ["Enter square matrix", "dimension", "inp_0"]
    form.update()
    display.clear_display()
    form_refresh.refresh()

    while True:
        inp = typer.start_typing()
        if inp == "back":
            current_app[0] = "matrix_operations"
            current_app[1] = "scientific_calculator"
            break
        
        if inp == "ok":
            
            n = int(form.input_list[f"inp_0"])
            
            form.form_list = []
            for i in range(1, n + 1):
                form.input_list[f"inp_{i}"] = " "
                form.form_list.append(f"Enter row no. {i}")
                form.form_list.append(f"inp_{i}")
            form.update()
            display.clear_display()
            form_refresh.refresh()
            
            calculator(n)
            
        
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