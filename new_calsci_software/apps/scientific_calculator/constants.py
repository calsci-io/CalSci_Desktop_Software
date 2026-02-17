# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import utime as time  # type:ignore
from math import *
import machine
from data_modules.object_handler import display, nav, typer, keypad_state_manager, form, form_refresh
from process_modules import boot_up_data_update
from data_modules.object_handler import current_app, data_bucket


def constants(db={}):
    constant_symbols_and_values = [
        "pi", "Pi", "3.141592653589793",
        "e", "Euler’s Number", "2.718281828459045",
        "g", "Gravitational Acceleration", "9.80665",
        "G", "Gravitational Constant", "6.67430e-11",
        "c", "Speed of Light", "2.99792458e8",
        "h", "Planck’s Constant", "6.62607015e-34",
        "k", "Boltzmann Constant", "1.380649e-23",
        "R", "Gas Constant", "8.314462618",
        "N_A", "Avogadro’s Number", "6.02214076e23",
        "eps_0", "Permittivity of Free Space", "8.8541878128e-12",
        "mu_0", "Permeability of Free Space", "1.25663706212e-6",
        "phi", "Golden Ratio", "1.618033988749895"
        ]
    form.form_list = constant_symbols_and_values
    form.update()
    display.clear_display()
    form_refresh.refresh()

    while True:
        inp = typer.start_typing()
        if inp == "back":
            current_app[0]="scientific_calculator"
            current_app[1]="application_modules"
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



