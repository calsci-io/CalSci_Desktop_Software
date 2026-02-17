# CalSci App-Building Modules (from `object_handler`)

This README documents the **modules and objects made available by `data_modules/object_handler.py`** so you can build apps consistently across the codebase. These are the same objects that apps import directly (e.g., `menu`, `form`, `text`, `typer`, `nav`, and the `*_refresh` uploaders).【F:data_modules/object_handler.py†L4-L107】

---

## 1) `object_handler` — central wiring for apps

`object_handler` creates and exports the core runtime objects used by apps:

- **Input/Navigation**
  - `keymap` (`Keypad_5X8`) and `typer` (`Typer`) are created for keypad input handling.【F:data_modules/object_handler.py†L56-L58】
  - `keypad_state_manager(...)` and `keypad_state_manager_reset()` update the keymap + navbar state when alpha/beta modes change.【F:data_modules/object_handler.py†L91-L107】
- **Buffers**
  - `text`, `menu`, `form` are instantiated from `Textbuffer`, `Menu`, and `Form` respectively.【F:data_modules/object_handler.py†L63-L68】
- **Navbar**
  - `nav = Nav(...)` is created and used to show alpha/beta status text in the UI.【F:data_modules/object_handler.py†L72-L73】
- **Uploaders**
  - `text_refresh`, `menu_refresh`, `form_refresh` connect buffers to the display driver and are used by apps to render frames.【F:data_modules/object_handler.py†L75-L80】
- **App routing & installer**
  - `app = App()` is used to set next app/group names for the launcher loop.【F:data_modules/object_handler.py†L82-L83】
  - `apps_installer = Apps()` is available for installed app metadata.【F:data_modules/object_handler.py†L88-L89】

Apps typically import these globals directly, for example `menu`, `menu_refresh`, `nav`, and `typer` in `apps/root/home.py`, and render via `menu_refresh.refresh(state=nav.current_state())`.【F:apps/root/home.py†L6-L38】

---

## 2) Text Input Buffer — `Textbuffer`

**Module:** `process_modules/text_buffer.py`  
**Object instance:** `text`

### Key attributes
- `text_buffer`, `menu_buffer`, `menu_buffer_cursor`, `rows`, `cols` track the current text and cursor state.【F:process_modules/text_buffer.py†L4-L28】
- `refresh_area` indicates which region should be redrawn by the uploader.【F:process_modules/text_buffer.py†L24-L28】
- `ac` tracks whether an “all clear” action occurred.【F:process_modules/text_buffer.py†L27-L28】

### Key methods
- `buffer()` returns displayable rows for the screen and updates internal spacing/padding.【F:process_modules/text_buffer.py†L30-L66】
- `update_buffer(text)` handles navigation (`nav_*`), delete, and regular input writes.【F:process_modules/text_buffer.py†L68-L179】
- `all_clear()` resets the buffer and cursor state.【F:process_modules/text_buffer.py†L180-L189】
- `ref_ar()` returns the refresh area; `cursor()` returns the cursor position offset.【F:process_modules/text_buffer.py†L192-L196】

### Typical app usage
- Read input with `typer.start_typing()` and pass it into `text.update_buffer(...)`.
- Refresh display with `text_refresh.refresh(state=nav.current_state())`.【F:apps/root/calculate.py†L77-L210】

---

## 3) Menu Buffer — `Menu`

**Module:** `process_modules/menu_buffer.py`  
**Object instance:** `menu`

### Key attributes
- `menu_list` stores visible menu items.
- `menu_cursor`, `menu_display_position`, `display_cursor` track the current selection and visible window.【F:process_modules/menu_buffer.py†L13-L24】

### Key methods
- `update_buffer(text)` handles `nav_d`/`nav_u` input and updates refresh bounds.【F:process_modules/menu_buffer.py†L26-L60】
- `buffer()` returns the visible menu slice; `cursor()` returns current cursor row.【F:process_modules/menu_buffer.py†L62-L66】
- `ref_ar()` returns rows needing refresh; `update()` resets cursor/viewport for new menus.【F:process_modules/menu_buffer.py†L68-L80】

### Typical app usage
- Populate `menu.menu_list`, call `menu.update()`, then render with `menu_refresh.refresh(state=nav.current_state())`.【F:apps/root/home.py†L14-L38】

---

## 4) Form Buffer — `Form`

**Module:** `process_modules/form_buffer.py`  
**Object instance:** `form`

### Key attributes
- `form_list` defines the form row order (labels + input placeholders).
- `input_list` stores the input values for each `inp_*` field.
- `menu_cursor`, `input_cursor`, and display positions track where the user is editing.【F:process_modules/form_buffer.py†L16-L41】

### Key methods
- `update_buffer(inp)` handles navigation and editing for `inp_*` fields, including delete and clear.【F:process_modules/form_buffer.py†L41-L179】
- `buffer()`, `cursor()`, `ref_ar()` return display data and refresh bounds.【F:process_modules/form_buffer.py†L187-L195】
- `inp_list()`, `inp_cursor()`, `inp_display_position()`, `inp_cols()` expose input state for uploaders and apps.【F:process_modules/form_buffer.py†L199-L209】
- `update()` resets the form layout; `update_label(...)` edits label entries dynamically.【F:process_modules/form_buffer.py†L211-L226】

### Typical app usage
- Apps edit the form with `form.update_buffer(...)` and render with `form_refresh.refresh(state=nav.current_state())`.【F:apps/scientific_calculator/determinant.py†L7-L77】

---

## 5) Navbar / Alpha–Beta State — `Nav`

**Module:** `process_modules/navbar.py`  
**Object instance:** `nav`

### Key attributes & methods
- The navbar tracks `state` (`"d"`, `"a"`, `"b"`, `"A"`) and maps it to the display text (`default`, `alpha`, `beta`, `ALPHA`).【F:process_modules/navbar.py†L4-L15】
- `state_change(...)` updates the mode; `current_state()` returns the display string used by uploaders.【F:process_modules/navbar.py†L11-L15】

### Where it is shown
- The state string is drawn in the **text buffer uploader** on the bottom page (page 7).【F:process_modules/text_buffer_uploader.py†L39-L62】
- Apps pass `nav.current_state()` into refresh calls so the navbar shows the active mode.【F:apps/root/home.py†L38-L38】

---

## 6) Buffer Uploaders (renderers)

These classes translate buffer state into display writes:

### `text_buffer_uploader.Tbf`
- Consumes `Textbuffer` output and draws characters + cursor.
- Draws navbar state string on the last page (page 7).【F:process_modules/text_buffer_uploader.py†L4-L64】

### `menu_buffer_uploader.Tbf`
- Renders visible menu rows and highlights the selected row cursor.【F:process_modules/menu_buffer_uploader.py†L4-L31】

### `form_buffer_uploader.Tbf`
- Renders label/input rows and draws an input cursor when editing `inp_*` fields.【F:process_modules/form_buffer_uploader.py†L4-L69】

---

## 7) Input & Typing — `Typer`

**Module:** `process_modules/typer.py`  
**Object instance:** `typer`

### Key methods
- `start_typing()` reads the keypad, translates row/col to a symbol, and returns it to the app loop (typical usage in every app input loop).【F:process_modules/typer.py†L9-L28】
- `debounce_delay(t=None)` lets apps adjust key debounce timing.【F:process_modules/typer.py†L29-L35】

---

## 8) App Routing — `App`

**Module:** `process_modules/app.py`  
**Object instance:** `app`

### Key methods
- `set_app_name(...)`, `set_group_name(...)` are used by apps to request a different app to run next.【F:process_modules/app.py†L13-L20】
- `get_app_name()` / `get_group_name()` are used by the app runner to load the next app.【F:process_modules/app.py†L9-L12】
- `set_none()` clears the pending app state after launch.【F:process_modules/app.py†L21-L23】

### Typical app usage
- Menu apps set `app` fields before returning to the launcher loop (e.g., home screen).【F:apps/root/home.py†L25-L33】

---

## 9) Connectivity & Shared State

`object_handler` also defines shared state used across apps:
- `current_app` and `data_bucket` track the active app and Wi‑Fi status, respectively.【F:data_modules/object_handler.py†L42-L43】
- `sta_if` / `ap_if` are initialized network interfaces for Wi‑Fi workflows.【F:data_modules/object_handler.py†L31-L40】
- `mac_str` exposes device MAC address for settings pages.【F:data_modules/object_handler.py†L85-L86】

---

## 10) Practical Patterns (as seen in apps)

### Menu-driven screens
- Set `menu.menu_list`, call `menu.update()`, then render with `menu_refresh.refresh(state=nav.current_state())`.【F:apps/root/home.py†L14-L38】

### Form-based input flows
- Use `form.update_buffer(inp)` for nav/edit input and draw with `form_refresh.refresh(state=nav.current_state())`.【F:apps/scientific_calculator/determinant.py†L7-L77】

### Text input / calculator screens
- Use `text.update_buffer(...)` and `text_refresh.refresh(state=nav.current_state())`.【F:apps/root/calculate.py†L77-L210】

---

## 11) Extending for new apps

When creating a new app:
1. Import the relevant buffer + uploader from `data_modules.object_handler`.
2. Read input with `typer.start_typing()`.
3. Update the buffer (`text`, `menu`, or `form`).
4. Call the corresponding `*_refresh.refresh(state=nav.current_state())` to render.

This is the same flow used across the existing apps in `apps/root`, `apps/settings`, `apps/scientific_calculator`, and `apps/installed_apps`.【F:apps/root/home.py†L6-L38】【F:apps/scientific_calculator/determinant.py†L7-L77】【F:apps/root/calculate.py†L77-L210】
