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
SYNC_SOURCES_FILE = Path("./sync_sources.json")
TRIPLE_FIRMWARE_PATHS_FILE = Path("./triple_firmware_paths.json")
APP_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = APP_DIR.parent
FIRMWARE_BIN = APP_DIR / "firmware.bin"

# ================= TRIPLE BOOT FLASH CONFIG =================
TRIPLE_BOOTLOADER_OFFSET = "0x0"
TRIPLE_PARTITION_TABLE_OFFSET = "0x8000"
TRIPLE_OTADATA_OFFSET = "0xF000"
TRIPLE_MPY_OFFSET = "0x20000"
TRIPLE_CPP_OFFSET = "0x420000"
TRIPLE_RUST_OFFSET = "0x820000"
TRIPLE_ARTIFACTS_DIR = APP_DIR / "triple_boot_images"
TRIPLE_LOCAL_BOOTLOADER = TRIPLE_ARTIFACTS_DIR / "bootloader.bin"
TRIPLE_LOCAL_PARTITION_TABLE = TRIPLE_ARTIFACTS_DIR / "partition-table.bin"
TRIPLE_LOCAL_OTADATA = TRIPLE_ARTIFACTS_DIR / "ota_data_initial.bin"
TRIPLE_LOCAL_MPY = TRIPLE_ARTIFACTS_DIR / "micropython.bin"
TRIPLE_LOCAL_CPP = TRIPLE_ARTIFACTS_DIR / "cpp_app.bin"
TRIPLE_LOCAL_RUST_BIN = TRIPLE_ARTIFACTS_DIR / "rust_app.bin"
TRIPLE_LOCAL_RUST_ELF = TRIPLE_ARTIFACTS_DIR / "rust_app.elf"

TRIPLE_BOOTLOADER_SOURCE_CANDIDATES = (
    WORKSPACE_ROOT / "cpp_driver_intergration_firmware/build/bootloader/bootloader.bin",
    WORKSPACE_ROOT / "triple_boot/cpp_app/build/bootloader/bootloader.bin",
)
TRIPLE_PARTITION_TABLE_SOURCE_CANDIDATES = (
    WORKSPACE_ROOT / "cpp_driver_intergration_firmware/build/partition_table/partition-table.bin",
    WORKSPACE_ROOT / "triple_boot/cpp_app/build/partition_table/partition-table.bin",
)
TRIPLE_OTADATA_SOURCE_CANDIDATES = (
    WORKSPACE_ROOT / "cpp_driver_intergration_firmware/build/ota_data_initial.bin",
    WORKSPACE_ROOT / "triple_boot/cpp_app/build/ota_data_initial.bin",
)
TRIPLE_MPY_SOURCE_CANDIDATES = (
    WORKSPACE_ROOT
    / "mpy_driver_intergration_firmware/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT-st7565-integration/micropython.bin",
    WORKSPACE_ROOT / "triple_boot/micropython/micropython_s3.bin",
)
TRIPLE_CPP_SOURCE_CANDIDATES = (
    WORKSPACE_ROOT / "cpp_driver_intergration_firmware/build/cpp_app.bin",
    WORKSPACE_ROOT / "triple_boot/cpp_app/build/cpp_app.bin",
)
TRIPLE_RUST_BIN_SOURCE_CANDIDATES = (
    WORKSPACE_ROOT / "rust_driver_intergration_firmware/rust_app.bin",
    WORKSPACE_ROOT / "triple_boot/rust_app/rust_app.bin",
)
TRIPLE_RUST_ELF_SOURCE_CANDIDATES = (
    WORKSPACE_ROOT / "rust_driver_intergration_firmware/target/xtensa-esp32s3-espidf/release/rust_app",
    WORKSPACE_ROOT / "triple_boot/rust_app/target/release/rust_app",
)

TRIPLE_BOOTLOADER_CANDIDATES = (TRIPLE_LOCAL_BOOTLOADER, *TRIPLE_BOOTLOADER_SOURCE_CANDIDATES)
TRIPLE_PARTITION_TABLE_CANDIDATES = (
    TRIPLE_LOCAL_PARTITION_TABLE,
    *TRIPLE_PARTITION_TABLE_SOURCE_CANDIDATES,
)
TRIPLE_OTADATA_CANDIDATES = (TRIPLE_LOCAL_OTADATA, *TRIPLE_OTADATA_SOURCE_CANDIDATES)
TRIPLE_MPY_CANDIDATES = (TRIPLE_LOCAL_MPY, *TRIPLE_MPY_SOURCE_CANDIDATES)
TRIPLE_CPP_CANDIDATES = (TRIPLE_LOCAL_CPP, *TRIPLE_CPP_SOURCE_CANDIDATES)
TRIPLE_RUST_BIN_CANDIDATES = (TRIPLE_LOCAL_RUST_BIN, *TRIPLE_RUST_BIN_SOURCE_CANDIDATES)
TRIPLE_RUST_ELF_CANDIDATES = (TRIPLE_LOCAL_RUST_ELF, *TRIPLE_RUST_ELF_SOURCE_CANDIDATES)

# ================= ESP32 SERIAL CONFIG =================
ESP32_KEYWORDS = ("Espressif",)
ESP_CHIP = "esp32s3"
ESP_BEFORE = "usb-reset"
ESP_AFTER = "hard-reset"
ESP_BOOTLOADER_AFTER = "no-reset"
ESP_CONNECT_ATTEMPTS = 10
ESP_AFTER_ERASE = "hard-reset"
ESP_AFTER_FLASH = "hard-reset"
ESP_AFTER_RUN = "hard-reset"
ESP_PORT_RESCAN_TIMEOUT = 12
ESP_PORT_RESCAN_INTERVAL = 0.5
BAUDRATE =  115200
REPL_DELAY = 0.001

# ================= FILE TRANSFER CONFIG =================
CHUNK_SIZE = 512
