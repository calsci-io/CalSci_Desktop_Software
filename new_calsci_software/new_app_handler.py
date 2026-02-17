import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import sys, gc

def app_runner():
    if (app.get_app_name() is None) or (app.get_group_name() is None):
        app.set_app_name("home")
        app.set_group_name("root")

    module_name = f"apps.{app.get_group_name()}.{app.get_app_name()}"

    try:
        # Unload if already in memory
        if module_name in sys.modules:
            del sys.modules[module_name]
            gc.collect()

        # Import module dynamically
        mod = __import__(module_name)

        # Walk into submodules (apps.root.calc → calc)
        for part in module_name.split(".")[1:]:
            mod = getattr(mod, part)

        # Run entry function
        if hasattr(mod, app.get_app_name()):
            getattr(mod, app.get_app_name())()
        else:
            print("No entry function in app:", app.get_app_name())

    except Exception as e:
        print("Error loading app:", e)

    app.set_none()
