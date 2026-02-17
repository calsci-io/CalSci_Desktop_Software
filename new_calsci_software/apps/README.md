# CalSci Apps Overview

This folder contains the **application groups** used by CalSci. Each group is a subpackage loaded by the app runner (`apps.<group>.<app>`). The launcher (`apps/root/home.py`) builds menus from JSON in `db/` and sets the next app to run via the shared `app` object in `data_modules.object_handler`.

## App groups

- **`root/`** – Core launcher apps like Home, Settings, Scientific Calculator menu, Toolbox, and top‑level utilities.
- **`scientific_calculator/`** – Math tools (matrices, eigenvalues, graphing, etc.).
- **`settings/`** – Device settings (Wi‑Fi, backlight, contrast, sleep, about, updates).
- **`installed_apps/`** – User‑installed or add‑on apps (sensors, utilities, demos).

## How apps are used

1. The **Home** app (`root/home.py`) reads `db/application_modules_app_list.json` to populate the main menu.
2. Selecting a menu item sets `app.set_app_name(...)` and `app.set_group_name(...)`.
3. The main loop imports and runs `apps.<group>.<app>`.

Each app generally:
- reads keypad input via `typer.start_typing()`,
- updates a buffer (`text`, `menu`, or `form`),
- refreshes the display with `*_refresh.refresh(state=nav.current_state())`.