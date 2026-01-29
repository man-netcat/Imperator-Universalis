import csv
import re
from collections import defaultdict
from pathlib import Path

import pyradox.datatype as _pydt

from .extract_data import parse_tree, read_localisation_file
from .paths import ir_localisation, ir_map_data, iu_localisation, iu_map_data
from .write_data import write_blocks

# ---------------- Static Mappings ---------------- #

continent_map = {"continent": ["europe", "asia", "africa"]}

superregion_map = {
    "europe": {
        "italy": [
            "central_italy_region",
            "magna_graecia_region",
            "cisalpine_gaul_region",
            "mediterranean_region",  # Italy "owns" it
        ],
        "germany": [
            "belgica_region",
            "germania_region",
            "germania_superior_region",
            "rhaetia_region",
            "bohemia_area",
        ],
        "france": [
            "transalpine_gaul_region",
            "central_gaul_region",
            "armorica_region",
            "aquitaine_region",
        ],
        "iberia": [
            "lusitania_region",
            "tarraconensis_region",
            "baetica_region",
            "contestania_region",
        ],
        "britain": [
            "britain_region",
            "caledonia_region",
        ],
        "north_sea": [
            "scandinavia_region",
            "baltic_sea_region",
            "atlantic_region",
        ],
        "balkans": [
            "greece_region",
            "macedonia_region",
            "illyria_region",
            "albania_region",
            "thrace_region",
            "moesia_region",
        ],
        "eastern_europe": [
            "dacia_region",
            "sarmatia_europea_region",
            "vistulia_region",
            "venedia_region",
            "pannonia_region",
        ],
    },
    "asia": {
        "anatolia": [
            "asia_region",
            "bithynia_region",
            "galatia_region",
            "cappadocia_region",
            "cappadocia_pontica_region",
            "cilicia_region",
            "pontus_region",
        ],
        "middle_east": [
            "taurica_region",
            "sarmatia_asiatica_region",
            "assyria_region",
            "mesopotamia_region",
            "gedrosia_region",
            "persis_region",
            "media_region",
            "bactriana_region",
            "ariana_region",
            "parthia_region",
            "syria_region",
            "palestine_region",
            "arabia_region",
            "arabia_felix_region",
            "persian_gulf_region",
            "red_sea_region",
            "cilician_river_region",
            "mesopotamia_river_region",
        ],
        "india": [
            "gandhara_region",
            "maru_region",
            "avanti_region",
            "madhyadesa_region",
            "pracya_region",
            "vindhyaprstha_region",
            "dravida_region",
            "aparanta_region",
            "karnata_region",
            "indo_gangetic_region",
            "indian_ocean_region",
        ],
        "central_asia": [
            "tibet_region",
            "himalayan_region",
            "sogdiana_region",
            "scythia_region",
            "don_river_region",
        ],
    },
    "africa": {
        "north_africa": [
            "cyrenaica_region",
            "numidia_region",
            "mauretainia_region",
            "africa_region",
        ],
        "egypt": [
            "upper_egypt_region",
            "lower_egypt_region",
            "nubia_region",
            "nile_region",
        ],
        "red_sea_region_group": [
            "punt_region",
            "red_sea_region",
            "indian_ocean_region",
        ],
    },
}


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


def parse_definitions() -> list[tuple[int, str, int, int, int, str]]:
    """
    Parse definition.csv but generate keys from the localisation file.
    Returns: (prov_id, key, r, g, b, name)
    """
    definition_file = ir_map_data / "definition.csv"
    ir_loc = read_localisation_file(ir_localisation)  # read all localisation

    rows = []
    counts = defaultdict(int)
    skipped_first = False

    with open(definition_file, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if not row or row[0].startswith("#"):
                continue

            prov_id, r, g, b = int(row[0]), int(row[1]), int(row[2]), int(row[3])

            # Skip the first valid entry (the 0 entry)
            if not skipped_first:
                skipped_first = True
                continue

            # Get the name from localisation if possible, fallback to "unnamed"
            loc_name = ir_loc.get(
                f"PROV{prov_id}", row[4].strip() if len(row) > 4 else f"PROV{prov_id}"
            )
            if not loc_name.strip():
                loc_name = "unnamed"

            key = clean_name(loc_name)

            counts[key] += 1
            rows.append((prov_id, key, r, g, b, loc_name))

    # Handle duplicate keys
    used = defaultdict(int)
    final_rows = []
    for prov_id, key, r, g, b, name in rows:
        final_key = f"{key}_{used[key]}" if counts[key] > 1 else key
        if counts[key] > 1:
            used[key] += 1
        final_rows.append((prov_id, final_key, r, g, b, name))

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

    # print(list(regions.keys()))

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


def build_default_map(id_to_key: dict[int, str]):
    """
    Parses default.map and returns a dictionary:
    { category_name_lowercase: set of province keys }
    """
    default_map = ir_map_data / "default.map"
    data = {}

    # Patterns
    list_pattern = re.compile(r"(\w+)\s*=\s*LIST\s*{\s*([\d\s]+)\s*}")
    range_pattern = re.compile(r"(\w+)\s*=\s*RANGE\s*{\s*(\d+)\s+(\d+)\s*}")

    with open(default_map, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # LIST entry
            list_match = list_pattern.match(line)
            if list_match:
                category, numbers = list_match.groups()
                category = category.lower()  # normalize to lowercase
                keys = {id_to_key[int(n)] for n in numbers.split()}
                data.setdefault(category, set()).update(keys)
                continue

            # RANGE entry
            range_match = range_pattern.match(line)
            if range_match:
                category, start, end = range_match.groups()
                category = category.lower()  # normalize to lowercase
                keys = {id_to_key[n] for n in range(int(start), int(end) + 1)}
                data.setdefault(category, set()).update(keys)
                continue

    return data


def write_default_map(ir_default_map_data: dict):
    """
    Writes the default.map file for Imperator / EU modding, mapping and aggregating categories.
    ir_default_map_data: { category_name: set of province keys }
    """
    default_map = iu_map_data / "default.map"

    # Category mapping
    category_mapping = {
        "sea_zones": "sea_zones",
        "lakes": "lakes",
        "impassable_terrain": "impassable_mountains",
        "uninhabitable": "non_ownable",
        "wasteland": "non_ownable",
        "river_provinces": "river_provinces",
    }

    # Aggregate wasteland into non_ownable if present
    if "wasteland" in ir_default_map_data:
        ir_default_map_data.setdefault("uninhabitable", set()).update(
            ir_default_map_data["wasteland"]
        )
        ir_default_map_data.pop("wasteland")

    init_lines = [
        'provinces = "locations.png"',
        'rivers = "rivers.png"',
        'topology = "heightmap.heightmap"',
        'adjacencies = "adjacencies.csv"',
        'setup = "definitions.txt"',
        'ports = "ports.csv"',
        'location_templates = "location_templates.txt"',
        "equator_y = 3340",
        "wrap_x = no",
    ]

    with default_map.open("w", encoding="utf-8") as f:
        # Write header/init lines
        for line in init_lines:
            f.write(f"{line}\n")
        f.write("\n")

        # Helper: write a category as a LIST block
        def write_category(cat_name: str, keys: set):
            f.write(f"{cat_name} = {{\n")
            for key in sorted(keys):
                f.write(f"    {key}\n")
            f.write("}\n\n")

        # Write each category in the aggregated data using mapping
        for category, keys in ir_default_map_data.items():
            mapped_category = category_mapping.get(category, category)
            write_category(mapped_category, keys)


def port_map_data():
    """Parse definitions, write named locations, adjacencies, ports, and check areas."""
    named_locations = parse_definitions()
    id_to_key = {prov_id: key for prov_id, key, *_ in named_locations}

    # Named locations file
    named_path = iu_map_data / "named_locations"
    named_path.mkdir(parents=True, exist_ok=True)
    with open(named_path / "00_default.txt", "w", encoding="utf-8-sig") as f:
        for _, key, r, g, b, _ in named_locations:
            f.write(f"{key} = {r:02x}{g:02x}{b:02x}\n")

    # ---------------- Reference ID-to-Key File ---------------- #
    ref_file = Path(__file__).parent / "province_id_to_key.csv"
    write_csv(
        ref_file,
        [{"ID": prov_id, "Key": key} for prov_id, key, *_ in named_locations],
        fieldnames=["ID", "Key"],
    )

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

    # Localisation: provinces, areas, regions
    loc_lines = ["l_english:"]

    # Prefer existing Imperator localisation if present
    ir_loc = read_localisation_file(ir_localisation)

    # --- Provinces ---
    for prov_id, key, *_ in named_locations:
        name = ir_loc[f"PROV{prov_id}"]
        loc_lines.append(f'  {key}: "{name}"')

    # --- Regions ---
    for region_tag in regions:
        name = ir_loc[region_tag]
        loc_lines.append(f'  {region_tag}: "{name}"')

    # --- Areas ---
    for area_list in regions.values():
        for area_tag in area_list:
            name = ir_loc[area_tag]
            loc_lines.append(f'  {area_tag}: "{name}"')

    # Write localisation file
    write_blocks(iu_localisation / "ir_map_l_english.yml", loc_lines)

    default_map = build_default_map(id_to_key)

    write_default_map(default_map)
