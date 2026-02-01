import pathlib

# Get current directory
current_dir = pathlib.Path(".")  # "." = current folder

# Scan for text files
for file_path in current_dir.glob("*.yml"):
    print(f"Checking file: {file_path.name}")

    # Read lines
    with file_path.open(encoding="utf-8") as f:
        lines = f.readlines()

    # Track keys
    keys_seen = set()
    duplicates = []

    for line in lines:
        line = line.strip()
        if not line or ":" not in line:
            continue  # skip empty lines or lines without a colon
        key = line.split(":", 1)[0]  # everything before first colon
        if key in keys_seen:
            duplicates.append(key)
        else:
            keys_seen.add(key)

    # Report
    if duplicates:
        print("  Duplicate keys found:")
        for key in duplicates:
            print(f"    {key}")
    else:
        print("  No duplicate keys found.")
