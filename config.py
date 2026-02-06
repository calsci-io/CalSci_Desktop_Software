"""
CalSci Flasher - Configuration Module
Contains all configuration constants and settings.
"""

from pathlib import Path

# ================= GIT REPOSITORY CONFIG =================
REPO_URL = "https://github.com/calsci-io/calsci_latest_itr"
BRANCH = "main"
ROOT = Path("./calsci_latest_itr")
SELECTIONS_FILE = Path("./upload_selections.json")
FIRMWARE_BIN = Path(__file__).resolve().parent / "firmware.bin"

# ================= ESP32 SERIAL CONFIG =================
ESP32_KEYWORDS = ("Espressif",)
ESP_CHIP = "esp32s3"
ESP_BEFORE = "usb-reset"
ESP_AFTER = "hard-reset"
ESP_BOOTLOADER_AFTER = "no-reset"
ESP_CONNECT_ATTEMPTS = 10
ESP_AFTER_ERASE = "no-reset"
ESP_AFTER_FLASH = "no-reset"
ESP_AFTER_RUN = "hard-reset"
ESP_PORT_RESCAN_TIMEOUT = 12
ESP_PORT_RESCAN_INTERVAL = 0.5
BAUDRATE =  115200
REPL_DELAY = 0.001

# ================= FILE TRANSFER CONFIG =================
CHUNK_SIZE = 512
