import csv
import re
from collections import defaultdict
from pathlib import Path

import pyradox.datatype as _pydt

from .extract_data import parse_tree
from .maps import *
from .paths import ir_map_data, iu_map_data
from .write_data import write_blocks

# ---------------- Utility Functions ---------------- #


def clean_name(name: str) -> str:
    """Convert names to safe lowercase keys."""
    name = re.sub(r"[ \-]+", "_", name)
    if not name.isupper() and name:
        new_name = name[0]
        for c, prev in zip(name[1:], name[:-1]):
            if c.isupper() and prev != "_":
                new_name += "_"
            new_name += c
        name = new_name
    return re.sub(r"[^a-z0-9_]", "", name.lower())


def read_csv(file_path: Path, skip_header=True):
    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";")
        if skip_header:
            next(reader, None)
        return list(reader)


def write_csv(file_path: Path, data: list[dict], fieldnames: list[str]):
    """Write a list of dictionaries to a CSV file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in data:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


# ---------------- Parsing Functions ---------------- #


def parse_definitions() -> list[tuple[int, str, int, int, int]]:
    """Parse definition.csv into (province_id, key, r, g, b)."""
    definition_file = ir_map_data / "definition.csv"
    rows = []
    counts = defaultdict(int)

    with open(definition_file, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)  # skip header / 0 row
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            prov_id, r, g, b, name = (
                int(row[0]),
                int(row[1]),
                int(row[2]),
                int(row[3]),
                row[4].strip(),
            )
            key = clean_name(name)
            counts[key] += 1
            rows.append((prov_id, key, r, g, b))

    # Handle duplicate keys
    used = defaultdict(int)
    final_rows = []
    for prov_id, key, r, g, b in rows:
        final_key = f"{key}_{used[key]}" if counts[key] > 1 else key
        if counts[key] > 1:
            used[key] += 1
        final_rows.append((prov_id, final_key, r, g, b))

    return final_rows


def parse_adjacencies(id_to_key: dict[int, str]) -> list[dict]:
    """Parse adjacencies.csv into dictionaries."""
    file = ir_map_data / "adjacencies.csv"
    adjacencies = []
    for row in read_csv(file, skip_header=True):
        if len(row) < 4:
            continue
        try:
            from_id, to_id, through_id = int(row[0]), int(row[1]), int(row[3])
        except ValueError:
            continue
        adjacencies.append(
            {
                "From": id_to_key.get(from_id, f"UNKNOWN_{from_id}"),
                "To": id_to_key.get(to_id, f"UNKNOWN_{to_id}"),
                "Through": id_to_key.get(through_id, f"UNKNOWN_{through_id}"),
                "Type": row[2],
                "x1": int(row[4]) if len(row) > 4 and row[4] else "",
                "y1": int(row[5]) if len(row) > 5 and row[5] else "",
                "x2": int(row[6]) if len(row) > 6 and row[6] else "",
                "y2": int(row[7]) if len(row) > 7 and row[7] else "",
                "Comment": row[-1] if len(row) > 8 else "",
            }
        )
    return adjacencies


def parse_ports(id_to_key: dict[int, str]) -> list[dict]:
    """Parse ports.csv into dictionaries."""
    file = ir_map_data / "ports.csv"
    ports = []
    for row in read_csv(file, skip_header=True):
        if len(row) < 4:
            continue
        try:
            land_id, sea_id = int(row[0]), int(row[1])
            x, y = float(row[2]), float(row[3])
        except ValueError:
            continue
        ports.append(
            {
                "LandProvince": id_to_key.get(land_id, f"UNKNOWN_{land_id}"),
                "SeaZone": id_to_key.get(sea_id, f"UNKNOWN_{sea_id}"),
                "x": x,
                "y": y,
            }
        )
    return ports


# ---------------- Area Validation ---------------- #


def build_regions(id_to_key: dict[int, str]):
    def as_list(x):
        if isinstance(x, list):
            return x
        if isinstance(x, dict):
            return list(x.values())
        return [x]

    areas = parse_tree(ir_map_data / "areas.txt").to_python()
    regions = parse_tree(ir_map_data / "regions.txt").to_python()

    region_map = {
        region: {
            area: [id_to_key[pid] for pid in as_list(areas[area]["provinces"])]
            for area in region_data["areas"]
            if area in areas
        }
        for region, region_data in regions.items()
    }

    return region_map


# ---------------- Main Port Map Function ---------------- #


def build_full_hierarchy(region_map, superregion_map, continent_map):
    """
    region_map: { region_tag: { area_tag: [province_keys] } }
    superregion_map: { subcontinent: { superregion: [region_tags] } }
    continent_map: { continent: [subcontinents] }
    """
    nested = {}

    for continent, subcontinents in continent_map.items():
        nested[continent] = {}
        for subcontinent in subcontinents:
            nested[continent][subcontinent] = {}
            if subcontinent not in superregion_map:
                continue
            for superregion, regions in superregion_map[subcontinent].items():
                nested[continent][subcontinent][superregion] = {}
                for region in regions:
                    if region not in region_map:
                        continue
                    nested[continent][subcontinent][superregion][region] = {}
                    for area, provinces in region_map[region].items():
                        nested[continent][subcontinent][superregion][region][
                            area
                        ] = provinces
    return nested


def hierarchy_to_blocks(data: dict) -> list[tuple[str, list]]:
    """
    Converts nested dicts into (tag, lines) blocks compatible with write_blocks.
    Leaf values must be lists of province keys.
    """
    blocks = []

    for tag, value in data.items():
        # Leaf: area -> [province_keys]
        if isinstance(value, list):
            province_list = " ".join(value)
            blocks.append(f"{tag} = {{ {province_list} }}")

        # Node: higher-level grouping
        elif isinstance(value, dict):
            sublines = hierarchy_to_blocks(value)
            blocks.append((tag, sublines))

        else:
            raise TypeError(f"Unsupported hierarchy value type: {type(value)}")

    return blocks


def port_map_data():
    """Parse definitions, write named locations, adjacencies, ports, and check areas."""
    named_locations = parse_definitions()
    id_to_key = {prov_id: key for prov_id, key, *_ in named_locations}

    # Named locations file
    named_path = iu_map_data / "named_locations"
    named_path.mkdir(parents=True, exist_ok=True)
    with open(named_path / "00_default.txt", "w", encoding="utf-8") as f:
        for _, key, r, g, b in named_locations:
            f.write(f"{key} = {r:02x}{g:02x}{b:02x}\n")

    # Adjacencies CSV
    write_csv(
        iu_map_data / "adjacencies.csv",
        parse_adjacencies(id_to_key),
        ["From", "To", "Type", "Through", "x1", "y1", "x2", "y2", "Comment"],
    )

    # Ports CSV
    write_csv(
        iu_map_data / "ports.csv",
        parse_ports(id_to_key),
        ["LandProvince", "SeaZone", "x", "y"],
    )

    # Area validation
    regions = build_regions(id_to_key)
    nested = build_full_hierarchy(regions, superregion_map, continent_map)

    blocks = hierarchy_to_blocks(nested)

    write_blocks(
        iu_map_data / "definitions.txt",
        blocks,
    )
