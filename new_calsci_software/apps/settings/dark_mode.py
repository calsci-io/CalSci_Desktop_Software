import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

# dark_mode_state=False
# from data_modules.object_handler import display
# from tinydb import TinyDB, Query
# db = TinyDB('db/settings.json')
# q=Query()
# dark_mode_state=db.search(q.feature=="dark_mode")[0]["value"]

# q=Query()
def dark_mode():
    from tinydb import TinyDB, Query
    db = TinyDB('db/settings.json')
    q=Query()
    # dark_mode_state=db.search(q.feature=="dark_mode")[0]["value"]
    # dm = dark_mode_state
    if db.search(q.feature=="dark_mode")[0]["value"] == False:
        # dark_mode_state=True
        display.invert(True)
        print("display inverted")
        db.update({'value':True}, q.feature == 'dark_mode')
    else:
        # dark_mode_state=False
        display.invert(False)
        print("display non inverted")
        db.update({'value':False}, q.feature == 'dark_mode')
