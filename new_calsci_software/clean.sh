#!/bin/bash

PORT="/dev/ttyACM0"

echo "⚠️  Deleting all files and folders from ESP32 root..."

# Create a temporary Python cleanup script
TMPFILE=$(mktemp /tmp/clean_esp32.XXXX.py)

cat > "$TMPFILE" <<'EOF'
import os

def rmtree(path):
    for entry in os.ilistdir(path):
        name = entry[0]
        full_path = path + "/" + name if path else name
        if entry[1] == 0x4000:  # directory
            rmtree(full_path)
            try:
                os.rmdir(full_path)
            except:
                pass
        else:  # file
            try:
                os.remove(full_path)
            except:
                pass

# Clean everything in root
rmtree("")
EOF

# Run the cleanup script on ESP32
ampy -p "$PORT" run "$TMPFILE"

# Remove temporary file
rm "$TMPFILE"

echo "✅ ESP32 root is now clean."
