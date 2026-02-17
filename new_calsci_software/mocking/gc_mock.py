import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

"""
Mock gc module extensions for simulator.
Adds MicroPython-specific gc functions to Python's gc module.
"""

import gc as _gc
import psutil
import os

# Get the current process
_process = psutil.Process(os.getpid())


def mem_free():
    """Return amount of free memory in bytes (MicroPython compatible)."""
    try:
        # Get available memory on the system
        mem_info = psutil.virtual_memory()
        return mem_info.available
    except:
        # Fallback: return a dummy value
        return 1024 * 1024  # 1MB dummy


def mem_alloc():
    """Return amount of allocated memory in bytes."""
    try:
        mem_info = psutil.virtual_memory()
        return mem_info.used
    except:
        return 1024 * 512  # 512KB dummy


def mem_total():
    """Return total memory in bytes."""
    try:
        mem_info = psutil.virtual_memory()
        return mem_info.total
    except:
        return 1024 * 1024 * 2  # 2MB dummy


# Expose the functions through gc module
_gc.mem_free = mem_free
_gc.mem_alloc = mem_alloc
_gc.mem_total = mem_total
