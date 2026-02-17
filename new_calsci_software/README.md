# 🧮 CalSci — A Programmable Scientific Calculator on ESP32‑S3

CalSci is a **fully programmable scientific calculator** powered by **MicroPython** and the **ESP32‑S3**. It blends the feel of a classic calculator with the flexibility of a tiny embedded computer—so you can run built‑in tools *and* build your own apps.

---

## ✨ Why CalSci?

- **Hackable by design** — Apps are written in MicroPython and loaded at runtime.
- **Embedded‑first** — Tailored for keypad + monochrome LCD workflows.
- **Modular** — Calculator, graphing, tools, and settings live as independent apps.
- **Educational** — Ideal for students, engineers, and makers learning embedded Python.

---

## ⚙️ Hardware Snapshot

| Component | Details |
| --- | --- |
| MCU | ESP32‑S3 N16R8 (dual‑core, 240 MHz) |
| Memory | 16 MB Flash, 8 MB PSRAM |
| Display | Monochrome graphical LCD (ST7565) |
| Input | 40+ key matrix keypad |
| Storage | Internal flash + microSD support |
| Connectivity | USB, Wi‑Fi, Bluetooth |
| Power | Li‑ion battery + power management |
| Expansion | GPIO headers for sensors and I/O |

---

## 🧠 What’s in this Repo?

### Core runtime
- **`main.py`** — Entry point that boots the app loop.
- **`process_modules/`** — Scheduler, navigation, buffer rendering, and app routing.
- **`data_modules/`** — Global device objects (keypad, display, buffers) and configuration.

### Apps & UI
- **`apps/root/`** — Home screen, menu navigation, settings, and launcher apps.
- **`apps/scientific_calculator/`** — Calculator‑specific apps (e.g., functions, operations).
- **`db/`** — JSON app lists, settings, and boot state.

### Libraries & Drivers
- **`lib/`** — Math tools, graphing, sensor drivers, utility modules.
- **`input_modules/`** — Keypad scanning and input handling.

---

## 🏗️ How the System Works

```text
+------------------------------+
|        CalSci Apps           |
|  - Calculator / Graphing     |
|  - GPIO / Tools / Settings   |
+------------------------------+
|   CalSci Runtime (Python)    |
|  - App router + scheduler    |
|  - UI buffers + rendering    |
|  - Keypad input handling     |
+------------------------------+
| MicroPython + ESP32‑S3 HAL   |
+------------------------------+
```

The runtime continuously:
1. Reads keypad input.
2. Updates UI buffers.
3. Dynamically loads the selected app.
4. Executes it and returns to the loop.

---

## 🚀 Get Started (Development)

> CalSci targets MicroPython on ESP32‑S3. Typical workflows include editing Python files and flashing firmware to the device.

Suggested starting points:
- Browse **`apps/root/`** to see how menus are built.
- Check **`process_modules/app_runner.py`** for dynamic app loading.
- Review **`data_modules/object_handler.py`** to see how the keypad, display, and buffers are wired.

---

## 📁 Repository Structure

```text
apps/               # App groups (root, scientific_calculator, settings)
process_modules/    # App scheduling, UI buffers, nav, loaders
data_modules/       # Global objects, configuration, keypad map
input_modules/      # Keypad input scanning
lib/                # Math, graphing, sensor, and utility libs
db/                 # JSON config + app lists
```

---

## 🌟 Vision

CalSci aims to be more than a calculator—it’s a tiny programmable computing platform you can keep in your backpack. Whether you’re solving equations, exploring electronics, or building new MicroPython tools, CalSci is designed to be open, extensible, and fun.

---

## 📄 License

CalSci is available under the MIT License. See the [LICENSE](LICENSE) file for details.
