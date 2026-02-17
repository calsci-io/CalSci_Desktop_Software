import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

class Keypad_5X8:
    def __init__(self, state="d"):
        keypad_5X8_layout_default=[
            ["on", "alpha", "beta", "home", "wifi"],
            ["backlight", "back", "toolbox", "diff()", "ln()"],
            ["nav_l", "nav_d", "nav_r", "ok", "nav_u"],
            ["module", "bluetooth", "sin()", "cos()", "tan()"],
            ["igtn()", "pi", "e", "summation", "fraction"],
            ["log", "pow(,)", "pow( ,0.5)", "pow( ,2)", "S_D"],
            ["7", "8", "9", "nav_b", "AC"],
            ["4", "5", "6", "*", "/"],
            ["1", "2", "3", "+", "-"],
            [".", "0", ",", "ans", "exe"]
        ]
        keypad_5X8_layout_alpha=[
            ["on", "alpha", "beta", "home", "wifi"],
            ["backlight", "back", "caps", "f", "l"],
            ["nav_l", "nav_d", "nav_r", "ok", "nav_u"],
            ["a", "b", "c", "d", "e"],
            ["g", "h", "i", "j", "k"],
            ["m", "n", "o", "p", "q"],
            ["r", "s", "t", "nav_b", "AC"],
            ["u", "v", "w", "*", "/"],
            ["x", "y", "z", "+", "-"],
            [" ", "off", "tab", "ans", "exe"]
        ]
        keypad_5X8_layout_beta=[
            ["on", "alpha", "beta", "home", "wifi"],
            ["backlight", "back", "undo", "=", "$"],
            ["nav_l", "nav_d", "nav_r", "ok", "nav_u"],
            ["copy", "paste", "asin(", "acos(", "atan("],
            ["&", "`", '"', "'", "shot"],
            ["^", "~", "!", "<", ">"],
            ["[", "]", "%", "nav_b", "AC"],
            ["{", "}", ":", "*", "/"],
            ["(", ")", ";", "+", "-"],
            ["@", "?", "\"", "ans", "exe"]
        ]
        keypad_5X8_layout_ALPHA=[
            ["on", "alpha", "beta", "home", "wifi"],
            ["backlight", "back", "caps", "F", "L"],
            ["nav_l", "nav_d", "nav_r", "ok", "nav_u"],
            ["A", "B", "C", "D", "E"],
            ["G", "H", "I", "J", "K"],
            ["M", "N", "O", "P", "Q"],
            ["R", "S", "T", "nav_b", "AC"],
            ["U", "V", "W", "*", "/"],
            ["X", "Y", "Z", "+", "-"],
            [" ", "off", "tab", "ans", "exe"]
        ]

        self.state=state
        self.states={"d":keypad_5X8_layout_default, "a":keypad_5X8_layout_alpha, "b": keypad_5X8_layout_beta, "A": keypad_5X8_layout_ALPHA}
    def key_out(self, col, row):
        return self.states[self.state][row][col]
    def key_change(self, state):
        self.state=state
