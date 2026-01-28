import csv
import re
from collections import defaultdict
from pathlib import Path

from .paths import ir_map_data, iu_map_data


def parse_definitions():
    definition = ir_map_data / "definition.csv"
    named_locations = []

    name_counts = defaultdict(int)
    rows = []

    skip_first = True  # Ignore 0 row

    with open(definition, newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile, delimiter=";")
        for row in reader:
            if not row or row[0].startswith("#"):
                continue

            if skip_first:
                skip_first = False
                continue  # ignore first valid row

            province_id = int(row[0])
            r = int(row[1])
            g = int(row[2])
            b = int(row[3])
            name = row[4].strip()

            if not name:  # skip completely empty names
                continue

            # Step 1: replace spaces and dashes with underscores
            cleaned = re.sub(r"[ \-]+", "_", name)

            # Step 2: insert underscores before uppercase letters (unless all uppercase)
            if not name.isupper() and cleaned:
                new_str = cleaned[0]
                for c, prev in zip(cleaned[1:], cleaned[:-1]):
                    if c.isupper() and prev != "_":
                        new_str += "_"
                    new_str += c
                cleaned = new_str

            # Step 3: lowercase and remove any non-alphanumeric/underscore
            base_key = re.sub(r"[^a-z0-9_]", "", cleaned.lower())

            if not base_key:  # skip if nothing left after cleaning
                continue

            name_counts[base_key] += 1
            rows.append((province_id, r, g, b, base_key))

    # Second pass: assign name_key with suffixes if duplicates
    used_counters = defaultdict(int)
    for province_id, r, g, b, base_key in rows:
        if name_counts[base_key] > 1:
            count = used_counters[base_key]
            name_key = f"{base_key}_{count}"
            used_counters[base_key] += 1
        else:
            name_key = base_key

        named_locations.append((province_id, name_key, r, g, b))

    return named_locations


def parse_adjacencies(id_to_key):
    source_file = iu_map_data / "adjacencies.csv"

    adjacencies = []

    with open(source_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";")
        headers = next(reader)
        headers = [h.strip() for h in headers if h.strip()]

        for row in reader:
            if not row or len(row) < 4:
                continue

            try:
                from_id = int(row[0])
                to_id = int(row[1])
                through_id = int(row[3])

                from_key = id_to_key.get(from_id, f"UNKNOWN_{from_id}")
                to_key = id_to_key.get(to_id, f"UNKNOWN_{to_id}")
                through_key = id_to_key.get(through_id, f"UNKNOWN_{through_id}")

                x1 = int(row[4]) if len(row) > 4 and row[4] else None
                y1 = int(row[5]) if len(row) > 5 and row[5] else None
                x2 = int(row[6]) if len(row) > 6 and row[6] else None
                y2 = int(row[7]) if len(row) > 7 and row[7] else None

                comment = row[-1] if len(row) > 8 else ""

                adjacencies.append(
                    {
                        "From": from_key,
                        "To": to_key,
                        "Through": through_key,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "Type": row[2],
                        "Comment": comment,
                    }
                )
            except ValueError:
                continue

    return adjacencies


def write_adjacencies(adj_list):
    output_file = iu_map_data / "adjacencies.csv"
    iu_map_data.mkdir(parents=True, exist_ok=True)

    # Define CSV columns in the order you want
    fieldnames = ["From", "To", "Type", "Through", "x1", "y1", "x2", "y2", "Comment"]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()

        for adj in adj_list:
            row = {
                "From": adj.get("From", ""),
                "To": adj.get("To", ""),
                "Type": adj.get("Type", ""),
                "Through": adj.get("Through", ""),
                "x1": adj.get("x1", ""),
                "y1": adj.get("y1", ""),
                "x2": adj.get("x2", ""),
                "y2": adj.get("y2", ""),
                "Comment": adj.get("Comment", ""),
            }
            writer.writerow(row)


def parse_ports(id_to_key):
    source_file = ir_map_data / "ports.csv"

    ports = []

    with open(source_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";")
        headers = next(reader)  # skip header

        for row in reader:
            if not row or len(row) < 4:
                continue

            try:
                land_id = int(row[0])
                sea_id = int(row[1])
                x = float(row[2])
                y = float(row[3])

                land_key = id_to_key.get(land_id, f"UNKNOWN_{land_id}")
                sea_key = id_to_key.get(sea_id, f"UNKNOWN_{sea_id}")

                ports.append(
                    {"LandProvince": land_key, "SeaZone": sea_key, "x": x, "y": y}
                )
            except ValueError:
                continue  # skip malformed rows

    return ports


def write_ports(ports_list):
    output_file = iu_map_data / "ports.csv"
    iu_map_data.mkdir(parents=True, exist_ok=True)

    # Define CSV columns
    fieldnames = ["LandProvince", "SeaZone", "x", "y"]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()

        for port in ports_list:
            row = {
                "LandProvince": port.get("LandProvince", ""),
                "SeaZone": port.get("SeaZone", ""),
                "x": port.get("x", ""),
                "y": port.get("y", ""),
            }
            writer.writerow(row)


def port_map_data():
    named_locations = parse_definitions()
    id_to_key = {prov_id: name_key for prov_id, name_key, *_ in named_locations}

    named_locations_path = iu_map_data / "named_locations"
    iu_map_data.mkdir(parents=True, exist_ok=True)
    named_locations_path.mkdir(parents=True, exist_ok=True)

    # Write named_locations
    named_locations_file = named_locations_path / "00_default.txt"
    with open(named_locations_file, "w", encoding="utf-8") as f:
        for _, name_key, r, g, b in named_locations:
            line = f"{name_key} = {r:02x}{g:02x}{b:02x}\n"
            f.write(line)

    adj_list = parse_adjacencies(id_to_key)

    write_adjacencies(adj_list)

    ports_list = parse_ports(id_to_key)

    write_ports(ports_list)
