# from serial.tools import list_ports

# def list_serial_ports():
#     return list(list_ports.comports())

# for p in list_serial_ports():
#     print(p.device, p.description)

from serial.tools import list_ports

ESP32_KEYWORDS = (
    # "CP210",
    # "CH340",
    # "CH910",
    # "USB JTAG",
    # "Silicon Labs",
    "Espressif",
)

def find_esp32_ports():
    ports = []
    for p in list_ports.comports():
        text = f"{p.manufacturer} {p.description}".lower()
        if any(k.lower() in text for k in ESP32_KEYWORDS):
            ports.append(p.device)
    return ports


ports = find_esp32_ports()

if not ports:
    raise RuntimeError("No ESP32 detected")

print("Detected ESP32 ports:", ports)
PORT = ports[0]