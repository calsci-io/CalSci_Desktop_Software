import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

"""
Mocking module for CalSci simulator.
Contains mock implementations of MicroPython modules for desktop simulation.
"""

#from mocking import gc_mock
#from mocking import utime
from mocking import framebuf
#from mocking import machine
#from mocking import urequests
