#!/bin/bash
# Recursive downloader using ampy (duplicate path bug fixed)

PORT="/dev/ttyACM0"
BACKUP_DIR="./"

normalize_remote() {
    # Ensure leading / and collapse multiple slashes
    echo "/$1" | sed 's#//*#/#g'
}

download_recursive() {
    local remote_path=$(normalize_remote "$1")
    local local_path="$2"

    mkdir -p "$local_path"

    # List contents of the current remote path
    for entry in $(ampy --port $PORT ls "$remote_path" 2>/dev/null); do
        entry=$(echo "$entry" | tr -d '\r')

        # `ampy ls` already returns full path → don’t join twice
        local remote_item=$(normalize_remote "$entry")

        # Strip leading / for local mirror
        local rel_item="${remote_item#/}"
        local local_item="$BACKUP_DIR/$rel_item"

        echo "🔍 Checking $remote_item ..."

        if ampy --port $PORT ls "$remote_item" >/dev/null 2>&1; then
            echo "📂 Entering directory: $remote_item"
            download_recursive "$remote_item" "$(dirname "$local_item")/$(basename "$remote_item")"
        else
            echo "⬇️  Downloading $remote_item → $local_item"
            mkdir -p "$(dirname "$local_item")"
            if ! ampy --port $PORT get "$remote_item" "$local_item"; then
                echo "⚠️ Failed to download $remote_item"
            fi
        fi
    done
}

echo ""
echo "📥 Downloading all files and folders from ESP32 to $BACKUP_DIR ..."
echo ""

download_recursive "/" "$BACKUP_DIR"

echo ""
echo "✅ Download complete."
