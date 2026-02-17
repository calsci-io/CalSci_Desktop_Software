import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

class Tbf:
    def __init__(self, disp_out, chrs, t_b):
        self.disp_out = disp_out
        self.chrs = chrs
        self.t_b = t_b
        self.disp_out.clear_display()
        self.nav = ""
        self.new = False
    def update(self, t_b_new):
        self.t_b = t_b_new
    def refresh(self, state="default"):
        buf = self.t_b.buffer()
        ref_ar = self.t_b.ref_ar()
        for i in range(ref_ar[0] // self.t_b.cols, ref_ar[1] // self.t_b.cols):
            self.disp_out.set_page_address(i)
            self.disp_out.set_column_address(0)      
            should_draw = (
                buf[i].strip() != "" or self.t_b.cursor() // self.t_b.cols == i
            ) or self.t_b.ac
            if should_draw:
                j_counter = 0
                for j in buf[i]:
                    cursor_line = 0b00000000
                    chtr_byte_data = self.chrs.Chr2bytes(j)
                    if j_counter + i * self.t_b.cols == self.t_b.cursor():
                        chtr_byte_data = self.chrs.invert_letter(j)
                        cursor_line = 0b11111111
                    for k in chtr_byte_data:
                        self.disp_out.write_data(k)
                    self.disp_out.write_data(cursor_line)
                    j_counter += 1
            else:
                
                for k in range(6):
                    self.disp_out.write_data(0b00000000)
        if self.nav != state or self.new == True:
            self.nav = state
            self.disp_out.set_page_address(7)
            self.disp_out.set_column_address(0)
            for col in range(128):
                self.disp_out.write_data(0b00000000)
            self.disp_out.set_column_address(0)
            j_counter = 0
            if "default" in state or "alpha" in state or "beta" in state or "ALPHA" in state:
                for j in state:
                    chtr_byte_data = self.chrs.invert_letter(j)
                    cursor_line = 0b11111111
                    for k in chtr_byte_data:
                        self.disp_out.write_data(k)
                    self.disp_out.write_data(cursor_line)
                    j_counter += 1
            else:
                for j in state:
                    chtr_byte_data = self.chrs.Chr2bytes(j)
                    cursor_line = 0b00000000
                    for k in chtr_byte_data:
                        self.disp_out.write_data(k)
                    self.disp_out.write_data(cursor_line)
                    j_counter += 1

        self.new = False
