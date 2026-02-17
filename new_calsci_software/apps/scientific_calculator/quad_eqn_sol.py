# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
from math import *
import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh
from process_modules import boot_up_data_update
from data_modules.object_handler import current_app, data_bucket


def quad_eqn_sol(db={}):
    form.input_list={"inp_0": " "}
    form.form_list = ["eqn1:", "a+b+c", "inp_0"]
    form.update()
    display.clear_display()
    form_refresh.refresh()

    while True:
        inp = typer.start_typing()
        if inp == "back":
            current_app[0]="scientific_calculator"
            current_app[1]="application_modules"
            break
        

        if inp == "ok":
            a, b, c = list(map(int, form.input_list["inp_0"].split("+")))
            if a == 0:
                form.form_list = ["Not a quadratic eqn"]

            discriminant = b**2 - 4*a*c

            if discriminant > 0:
                root1 = (-b + (discriminant)**0.5) / (2*a)
                root2 = (-b - (discriminant)**0.5) / (2*a)
                form.form_list = ["Real Roots:", f"Root1={root1:.5f}", f"Root2={root2:.5f}"]

            elif discriminant == 0:
                root = -b / (2*a)
                form.form_list = ["Only 1 root", f"Root1={root:.5f}"]

            else:
                real_part = -b / (2*a)
                imag_part = ((-discriminant)**0.5) / (2*a)
                form.form_list = ["Imaginary Roots:", f"Root1={real_part:.2f}+{imag_part:.2f}i", f"Root2={real_part:.2f}-{imag_part:.2f}i"]


            form.update()
            display.clear_display()
            form_refresh.refresh()
            while True:
                inp_breaker = typer.start_typing()
                break
            
            

        if inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            form.update_buffer("")

        if inp == "off":
            machine.deepsleep()
        if inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
        form_refresh.refresh(state=nav.current_state())
        time.sleep(0.15)



