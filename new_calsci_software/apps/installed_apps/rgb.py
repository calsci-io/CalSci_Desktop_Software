import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

# import time
from machine import Pin, PWM
from data_modules.object_handler import nav, keypad_state_manager, app

def rgb():
    display.clear_display()

    # Initialize RGB PWM channels
    r = PWM(Pin(43), duty=0, freq=1000)
    g = PWM(Pin(2), duty=0, freq=1000)
    b = PWM(Pin(44), duty=0, freq=1000)

    menu.menu_list = [
        "RGB - (43,2,44)",
        "RED   OFF -------",
        "GREEN OFF -------",
        "BLUE  OFF -------",
        "press ok to on/off"
    ]
    menu.update()
    menu_refresh.refresh()

    MAX_LEVEL = 7  # brightness range: 0–7 (8 levels total)

    def update_menu_display():
        """Refresh menu display without losing cursor position."""
        cursor = menu.menu_cursor
        menu.update()
        menu.menu_cursor = cursor
        menu.refresh_rows=(cursor, cursor+1)
        menu_refresh.refresh()

    def get_item_name():
        return menu.menu_list[menu.menu_cursor][0:9]

    def get_bar_level(bar: str) -> int:
        """Return number of '+' characters as level."""
        return bar.count("+")

    def set_pwm_level(channel: PWM, level: int):
        """Set PWM duty proportionally to brightness level."""
        duty_val = int((1023 / MAX_LEVEL) * level)
        channel.duty(duty_val)

    def toggle_color(channel: PWM, index: int, color_name: str):
        """Toggle a color ON/OFF with full or zero brightness."""
        current = menu.menu_list[index]
        if "OFF" in current:
            menu.menu_list[index] = f"{color_name} ON  {'+' * MAX_LEVEL}"
            channel.duty(1023)
        else:
            menu.menu_list[index] = f"{color_name} OFF {'-' * MAX_LEVEL}"
            channel.duty(0)

    def adjust_brightness(channel: PWM, index: int, color_name: str, direction: int):
        """
        Adjust brightness by direction (-1 or +1).
        When OFF and direction=+1 (nav_r), turn ON at level 1.
        """
        item = menu.menu_list[index]
        bar = item[-MAX_LEVEL:]
        level = get_bar_level(bar)

        if "OFF" in item and direction > 0:
            # If OFF and user presses right, turn ON at level 1
            new_level = 1
        else:
            new_level = level + direction

        # Clamp level within 0..MAX_LEVEL
        new_level = max(0, min(MAX_LEVEL, new_level))

        if new_level == 0:
            menu.menu_list[index] = f"{color_name} OFF {'-' * MAX_LEVEL}"
        else:
            new_bar = "+" * new_level + "-" * (MAX_LEVEL - new_level)
            menu.menu_list[index] = f"{color_name} ON  {new_bar}"

        set_pwm_level(channel, new_level)

    try:
        while True:
            inp = typer.start_typing()

            if inp == "back":
                break

            elif inp == "ok":
                item = get_item_name()
                if "RED" in item:
                    toggle_color(r, 1, "RED  ")
                elif "GREEN" in item:
                    toggle_color(g, 2, "GREEN")
                elif "BLUE" in item:
                    toggle_color(b, 3, "BLUE ")
                update_menu_display()

            elif inp in ("nav_l", "nav_r"):
                item = get_item_name()
                direction = -1 if inp == "nav_l" else 1

                if "RED" in item:
                    adjust_brightness(r, 1, "RED  ", direction)
                elif "GREEN" in item:
                    adjust_brightness(g, 2, "GREEN", direction)
                elif "BLUE" in item:
                    adjust_brightness(b, 3, "BLUE ", direction)

                update_menu_display()

            menu.update_buffer(inp)
            menu_refresh.refresh(state=nav.current_state())
            # time.sleep(0.2)

    except Exception as e:
        print(f"Error: {e}")
        return 0
