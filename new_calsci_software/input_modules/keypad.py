import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

# from machine import Pin  # type: ignore     #############3.0
# import utime as time #type: ignore

# class Keypad:
#     def __init__(self, rows, cols):
#         self.rows=rows
#         self.cols=cols
#         for pin in rows:
#             Pin(pin, Pin.IN, Pin.PULL_UP)
#         for pin in cols:
#             p = Pin(pin, Pin.OUT)
#             p.value(1)
#         self.state=True
#     def keypad_loop(self):    
#         while self.state==True:
#             for col in range(len(self.cols)):
#                 Pin(self.cols[col], Pin.OUT).value(0)
#                 for row in range(len(self.rows)):
#                     buttonState = Pin(self.rows[row], Pin.IN, Pin.PULL_UP).value()
                    
#                     if buttonState == 0:
#                         Pin(self.cols[col], Pin.OUT).value(1)
#                         col_row=(col, row)
#                         print(col_row)
#                         return col_row
#                 Pin(self.cols[col], Pin.OUT).value(1)
#     def keypad_stop(self):
#         self.state=False

#     def keypad_start(self):
#         self.state=True


from machine import Pin  # type: ignore      ###########2.9
import utime as time #type: ignore

class Keypad:
    # Instance attribute
    def __init__(self, rows, cols):
        self.rows=rows
        self.cols=cols
        for pin in cols:
            Pin(pin, Pin.IN, Pin.PULL_UP)

        # Set column pins as OUTPUT and HIGH
        for pin in rows:
            p = Pin(pin, Pin.OUT)
            p.value(1)
        self.state=True
    def keypad_loop(self):    
        # global numRows, rowPins, numCols, colPins, graph_letters
        while self.state==True:
            for row in range(len(self.rows)):

                Pin(self.rows[row], Pin.OUT).value(0)
                for col in range(len(self.cols)):
                    buttonState = Pin(self.cols[col], Pin.IN, Pin.PULL_UP).value()
                    
                    if buttonState == 0:
                        # str=default_key(row, col)
                        # time.sleep(0.4)  # Debounce delay
                        Pin(self.rows[row], Pin.OUT).value(1)
                        # time.sleep(0.3)  # Debounce delay
                        col_row=(col, row)
                        print(col_row)
                        return col_row
                Pin(self.rows[row], Pin.OUT).value(1)
    def keypad_stop(self):
        self.state=False

    def keypad_start(self):
        self.state=True
