# Functions Apps (Custom Functions)

This folder contains helper apps used by the **Functions** menu in `apps/root/functions.py`.

## Apps

- **`create_new.py`** – Create a new custom function entry.
- **`delete_function.py`** – Delete an existing function entry.
- **`recently_used.py`** – View or re‑open recently used functions.

## How to use

Open **Functions** from the root menu, then choose one of these actions. These apps generally use the `menu` or `form` buffers and refresh using `menu_refresh`/`form_refresh` with `nav.current_state()`.
