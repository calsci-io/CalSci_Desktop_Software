# Installed Apps

This folder contains **user‑installed or add‑on apps** (sensors, demos, utilities). These can be added via the app installer/manager logic and then launched through the Installed Apps menu in `apps/root/installed_apps.py`.

## Apps

- **`add_2_nums.py`** – Simple addition demo.
- **`buzzer.py`** – Buzzer control/demo.
- **`data_reciever.py`** – Data receiver utility.
- **`dht11.py`** – DHT11 temperature/humidity sensor.
- **`dsgroup.py`** – Grouped sensor/app demo.
- **`dynamic_form.py`** – Dynamic form demo.
- **`flame_sensor.py`** – Flame sensor demo.
- **`master_slave.py`** – Master/slave example (communication demo).
- **`rgb.py`** – RGB LED controller.
- **`set.py`** – Settings helper app.
- **`slave_connector.py`** – Slave connector for comms.
- **`temp_sensor.py`** – Temperature sensor demo.
- **`ultra_sonic_sensor.py`** – Ultrasonic distance sensor.
- **`utc_time.py`** – UTC time display.

## How to use

Open **Installed Apps** from the root menu. Apps commonly use `menu`, `form`, or `text` buffers and render with their respective `*_refresh` uploaders.
