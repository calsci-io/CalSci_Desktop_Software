# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
from math import *
import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh, keymap
from process_modules import boot_up_data_update
from data_modules.object_handler import current_app


def simultanious_eqn_sol(db={}):
    form.input_list={"inp_0": " ", "inp_1": " "}
    form.form_list = ["eqn1:", "a1+b1+c1", "inp_0","eqn2:", "a2+b2+c2", "inp_1"]
    form.update()
    display.clear_display()
    form_refresh.refresh()

    while True:
        inp = typer.start_typing()
        if inp == "back":
            current_app[0]="scientific_calculator"
            current_app[1]="application_modules"
            break
        
        result = ""

        if inp == "ok":
            a1, b1, c1 = list(map(int, form.input_list["inp_0"].split("+")))
            a2, b2, c2 = list(map(int, form.input_list["inp_1"].split("+")))

            determinant = a1 * b2 - a2 * b1
            if determinant == 0:
                form.form_list("No unique solution")

            x = (c1 * b2 - c2 * b1) / determinant
            y = (c2 * a1 - c1 * a2) / determinant


            form.form_list = ["Solution:", f"x = {x:.5f}", f"y = {y:.5f}"]
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
            boot_up_data_update.main()
            machine.deepsleep()
        if inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
        form_refresh.refresh(state=nav.current_state())
        time.sleep(0.15)



