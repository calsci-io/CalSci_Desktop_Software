
PORT="/dev/ttyACM0"

echo ""
echo "Items present locally (excluding .git, hidden files, and *.pyc):"
echo ""

find . -type f \
    -not -path "./.git/*" \
    -not -name ".gitignore" \
    -not -name ".gitattributes" \
    -not -name "*.pyc" \
    -not -path "*/.*/*" \
    -not -name ".*" | while read -r file; do
    echo "$file"
done

echo ""
echo "Uploading files to ESP32..."
echo ""

# Function to create directories recursively on ESP32
create_dirs() {
    local path="$1"
    local current=""

    IFS='/' read -ra parts <<< "$path"
    for part in "${parts[@]}"; do
        if [ -n "$current" ]; then
            current="$current/$part"
        else
            current="$part"
        fi
        ampy -p "$PORT" mkdir "$current" 2>/dev/null
    done
}

find . -type f \
    -not -path "./.git/*" \
    -not -name ".gitignore" \
    -not -name ".gitattributes" \
    -not -name "*.pyc" \
    -not -path "*/.*/*" \
    -not -name ".*" | while read -r file; do
    # Strip the leading './'
    relative_path="${file#./}"

    echo "Uploading $relative_path"

    dir_path=$(dirname "$relative_path")
    if [ "$dir_path" != "." ]; then
        create_dirs "$dir_path"
    fi

    # Upload the file
    ampy -p "$PORT" put "$file" "$relative_path"

    echo "$relative_path uploaded"
    echo ""
done
