# Settings Apps

These apps expose **device configuration** and system status screens. Most use menu or form buffers.

## Apps

- **`about_calsci.py`** – About/credits/info screen.
- **`auto_sleep.py`** – Auto‑sleep configuration.
- **`backlight.py`** – Backlight brightness control.
- **`battery_status.py`** – Battery status information.
- **`contrast.py`** – Display contrast adjustment.
- **`dark_mode.py`** – Dark mode toggle (if supported).
- **`download_updates.py`** – Download firmware/app updates.
- **`mac_address.py`** – Show device MAC address.
- **`network_status.py`** – Wi‑Fi network status view.
- **`sleep_after.py`** – Sleep timer configuration.
- **`update.py`** – Update manager.
- **`wifi_app.py`** – Wi‑Fi app entry menu.
- **`wifi_autoconnect.py`** – Auto‑connect settings.
- **`wifi_connector.py`** – SSID/password connect UI.

## How to use

Open **Settings** from the root menu. Use **OK** to select items and **Back** to return. Most screens render with `menu_refresh` or `form_refresh` and pass `nav.current_state()` into the refresh call.
