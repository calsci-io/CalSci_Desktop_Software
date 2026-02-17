import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

class Nav:
    def __init__(self, disp_out, chrs):
        self.state = "d"
        self.states = {"d": "default", "a": "alpha  ", "b": "beta   ", "A": "ALPHA  "}
        self.disp_out = disp_out
        self.chrs = chrs

    def state_change(self, state):
        self.state = state

    def current_state(self):
        return self.states[self.state]
