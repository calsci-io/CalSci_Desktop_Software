import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

"""
Mock utime module for simulator.
Provides time functions compatible with MicroPython's utime module.
"""

import time as _time

# Alias time functions to match MicroPython's utime API
ticks_ms = lambda: int(_time.time() * 1000)
ticks_us = lambda: int(_time.time() * 1000000)
ticks_cpu = ticks_us

sleep = _time.sleep
sleep_ms = lambda ms: _time.sleep(ms / 1000)
sleep_us = lambda us: _time.sleep(us / 1000000)

def time():
    """Return seconds since epoch."""
    return int(_time.time())

def localtime(secs=None):
    """Convert seconds since epoch to time tuple."""
    if secs is None:
        secs = time()
    return _time.localtime(secs)

def mktime(time_tuple):
    """Convert time tuple to seconds since epoch."""
    return int(_time.mktime(time_tuple))
