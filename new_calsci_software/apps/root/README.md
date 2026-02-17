# Root Apps (Core UI)

These apps define the **top‑level UI flow**: Home, Settings, Scientific Calculator launcher, and general utilities. Most of these use the `menu` buffer and `menu_refresh` to render list screens.

## Apps

- **`home.py`** – Main home screen. Builds the menu from `db/application_modules_app_list.json` and launches the selected app group.
- **`scientific_calculator.py`** – Menu that opens tools under `apps/scientific_calculator/`.
- **`settings.py`** – Menu that opens apps under `apps/settings/`.
- **`installed_apps.py`** – Menu to open apps under `apps/installed_apps/`.
- **`calculate.py`** – Main calculator UI (text buffer input/response).
- **`functions.py`** – Entry point for custom functions management.
- **`toolbox.py`** – Utility tools menu (device helpers).
- **`chatbot_ai.py`** – Text/form‑driven chat UI (local or connected logic).
- **`error_screen.py`** – Error display screen for exceptions or alerts.

## How to use

- Start from **Home** (`home.py`).
- Use **OK** to select items, **Back** to return.
- Most menus are rendered with the `menu` buffer and refreshed with `menu_refresh.refresh(state=nav.current_state())`.
