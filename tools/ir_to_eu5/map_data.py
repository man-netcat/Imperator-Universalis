import csv
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pyradox.datatype as _pydt

from .extract_data import parse_tree, read_localisation_file
from .paths import (
    ir_game,
    ir_localisation,
    ir_map_data,
    ir_cultures,
    ir_default,
    iu_localisation,
    iu_map_data,
    iu_setup_start,
    mod_root,
    eu5_game,
)
from .write_data import write_blocks, print_written

### THIS FILE IS EXPERIMENTAL AND CURRENTLY NOT USED ###
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


IR_GROUP_TOWN_SETUPS = {
    "ir_hellenic_g": {
        "city": "greek_city_port",
        "city_port": "greek_city_port",
        "town": "greek_town",
        "town_port": "greek_town_port",
    },
    "ir_latin_g": {
        "city": "italian_city",
        "city_port": "italian_coastal_city",
        "town": "italian_town",
        "town_port": "italian_coastal_town",
    },
    "ir_iberia_g": {
        "city": "iberian_city",
        "city_port": "iberian_city_port",
        "town": "iberian_town",
        "town_port": "iberian_town_port",
    },
    "ir_celt_iberia_g": {
        "city": "iberian_city",
        "city_port": "iberian_city_port",
        "town": "iberian_town",
        "town_port": "iberian_town_port",
    },
    "ir_germanic_g": {
        "city": "german_city",
        "city_port": "german_coastal_city",
        "town": "german_town",
        "town_port": "german_coastal_town",
    },
    "ir_britannic_g": {
        "city": "british_town",
        "city_port": "british_town_port",
        "town": "british_town",
        "town_port": "british_town_port",
    },
    "ir_gaelic_g": {
        "city": "british_town",
        "city_port": "british_town_port",
        "town": "british_town",
        "town_port": "british_town_port",
    },
    "ir_gallic_g": {"city": "french_city", "town": "french_town"},
    "ir_belgae_group_g": {
        "city": "lowlands_city",
        "city_port": "lowlands_coastal_city",
        "town": "lowlands_town",
        "town_port": "lowlands_costal_town",
    },
    "ir_celto_pannonian_group_g": {
        "city": "carpathian_town",
        "town": "carpathian_town",
    },
    "ir_dacia_group_g": {"city": "carpathian_town", "town": "carpathian_town"},
    "ir_illyrian_group_g": {"city": "balkan_town", "town": "balkan_town"},
    "ir_baltic_g": {"city": "baltic_town", "town": "baltic_town"},
    "ir_scythia_g": {
        "city": "central_asian_city",
        "town": "central_asian_town",
    },
    "ir_persia_g": {
        "city": "central_asian_city",
        "town": "central_asian_town",
    },
    "ir_bactrian_g": {
        "city": "central_asian_city",
        "town": "central_asian_town",
    },
    "ir_aryan_g": {
        "city": "indian_city",
        "city_port": "indian_coastal_city",
        "town": "indian_town",
    },
    "ir_pracyan_g": {
        "city": "indian_city",
        "city_port": "indian_coastal_city",
        "town": "indian_town",
    },
    "ir_indian_g": {
        "city": "indian_city",
        "city_port": "indian_coastal_city",
        "town": "indian_town",
    },
    "ir_tibetan_g": {
        "city": "central_asian_city",
        "town": "central_asian_town",
    },
    "ir_anatolian_g": {
        "city": "anatolian_city",
        "town": "anatolian_town",
    },
    "ir_caucasian_g": {
        "city": "central_asian_city",
        "town": "central_asian_town",
    },
    "ir_east_levantine_g": {
        "city": "levant_city",
        "town": "levant_town",
    },
    "ir_west_levantine_g": {
        "city": "levant_city",
        "town": "levant_town",
    },
    "ir_south_levantine_g": {
        "city": "levant_city",
        "town": "levant_town",
    },
    "ir_north_african_g": {
        "city": "egyptian_city",
        "city_port": "maghreb_coastal_city",
        "town": "maghreb_town",
        "town_port": "maghreb_coastal_town",
    },
    "ir_numidian_g": {
        "city": "maghreb_city",
        "city_port": "maghreb_coastal_city",
        "town": "maghreb_town",
        "town_port": "maghreb_coastal_town",
    },
    "ir_meroitic_group_g": {
        "city": "east_african_town",
        "city_port": "east_african_coastal_town",
        "town": "east_african_town",
        "town_port": "east_african_coastal_town",
    },
    "ir_aksumite_group_g": {
        "city": "east_african_town",
        "city_port": "east_african_coastal_town",
        "town": "east_african_town",
        "town_port": "east_african_coastal_town",
    },
    "ir_proto_european_g": {"city": "french_city", "town": "french_town"},
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
    name = re.sub(r"[^a-z0-9_]", "", name.lower())
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "unnamed"


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
    print_written("CSV", file_path)


def _png_size(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            f.read(4)
            if f.read(4) != b"IHDR":
                return None
            w = int.from_bytes(f.read(4), "big")
            h = int.from_bytes(f.read(4), "big")
            return w, h
    except Exception:
        return None


def _resize_png_in_place(path: Path, target: tuple[int, int]) -> bool:
    width, height = target
    try:
        result = subprocess.run(
            [
                "convert",
                "-limit",
                "memory",
                "1GiB",
                "-limit",
                "map",
                "2GiB",
                str(path),
                "-filter",
                "point",
                "-resize",
                f"{width}x{height}!",
                "-define",
                "png:color-type=2",
                "-depth",
                "8",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


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
            if key == "unnamed":
                key = f"unnamed_{prov_id}"

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


def parse_adjacencies(id_to_key: dict[int, str], location_keys: set[str] | None = None) -> list[dict]:
    """Parse adjacencies.csv into dictionaries."""
    file = ir_map_data / "adjacencies.csv"
    type_map = {
        "river_large": "sea",
    }
    if location_keys is None:
        location_keys = set(id_to_key.values())
    adjacencies = []
    for row in read_csv(file, skip_header=True):
        if len(row) < 4:
            continue
        try:
            from_id, to_id, through_id = int(row[0]), int(row[1]), int(row[3])
        except ValueError:
            continue
        raw_type = row[2].strip()
        adj_type = type_map.get(raw_type, raw_type)
        from_key = id_to_key.get(from_id, "")
        to_key = id_to_key.get(to_id, "")
        through_key = id_to_key.get(through_id, "")
        if not from_key or not to_key:
            continue
        if from_key not in location_keys or to_key not in location_keys:
            continue
        if not through_key or through_key not in location_keys:
            through_key = from_key
        adjacencies.append(
            {
                "From": from_key,
                "To": to_key,
                "Through": through_key,
                "Type": adj_type,
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

    region_map = {}
    for region, region_data in regions.items():
        area_map = {}
        for area in region_data["areas"]:
            if area not in areas:
                continue
            province_ids = as_list(areas[area]["provinces"])
            if not province_ids:
                continue
            provinces = [id_to_key[pid] for pid in province_ids if pid in id_to_key]
            if not provinces:
                continue
            area_map[area] = provinces
        if area_map:
            region_map[region] = area_map

    return region_map


# ---------------- Main Port Map Function ---------------- #


def build_full_hierarchy(region_map, superregion_map, continent_map):
    """
    region_map: { region_tag: { area_tag: [province_keys] } }
    superregion_map: { subcontinent: { superregion: [region_tags] } }
    continent_map: { continent: [subcontinents] }
    """
    nested = {}
    seen_regions: dict[str, dict] = {}

    def region_has_locations(area_map: dict) -> bool:
        return any(isinstance(provinces, list) and len(provinces) > 0 for provinces in area_map.values())

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
                    area_map = region_map[region]
                    if region in seen_regions:
                        if not region_has_locations(area_map):
                            continue
                        target = seen_regions[region]
                        for area, provinces in area_map.items():
                            if area not in target:
                                target[area] = provinces
                            else:
                                merged = list(dict.fromkeys(target[area] + provinces))
                                target[area] = merged
                        continue
                    if not region_has_locations(area_map):
                        continue
                    target = {}
                    seen_regions[region] = target
                    nested[continent][subcontinent][superregion][region] = target
                    for area, provinces in area_map.items():
                        target[area] = provinces
    # Add any regions not covered by the superregion map
    missing_regions = set(region_map.keys()) - set(seen_regions.keys())
    if missing_regions:
        nested.setdefault("unmapped_continent", {})
        nested["unmapped_continent"].setdefault("unmapped_subcontinent", {})
        nested["unmapped_continent"]["unmapped_subcontinent"].setdefault(
            "unmapped_superregion", {}
        )
        bucket = nested["unmapped_continent"]["unmapped_subcontinent"][
            "unmapped_superregion"
        ]
        for region in sorted(missing_regions):
            bucket[region] = region_map[region]

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
            cleaned_values = [v for v in value if isinstance(v, str) and v.strip()]
            unique_values = list(dict.fromkeys(cleaned_values))
            province_list = " ".join(unique_values)
            blocks.append(f"{tag} = {{ {province_list} }}")

        # Node: higher-level grouping
        elif isinstance(value, dict):
            sublines = hierarchy_to_blocks(value)
            if sublines:
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
    mode = None
    current_category = None
    buffer: list[str] = []

    def _add_list(category: str, values: list[str]) -> None:
        keys = {
            id_to_key[int(n)]
            for n in values
            if n.isdigit() and int(n) in id_to_key
        }
        if keys:
            data.setdefault(category, set()).update(keys)

    def _add_range(category: str, values: list[str]) -> None:
        if len(values) < 2:
            return
        try:
            start = int(values[0])
            end = int(values[1])
        except Exception:
            return
        keys = {
            id_to_key[n]
            for n in range(start, end + 1)
            if n in id_to_key
        }
        if keys:
            data.setdefault(category, set()).update(keys)

    with open(default_map, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue

            tokens = line.replace("{", " { ").replace("}", " } ").split()
            if not tokens:
                continue

            if mode is None:
                if "=" not in tokens:
                    continue
                eq_idx = tokens.index("=")
                if eq_idx == 0 or eq_idx + 1 >= len(tokens):
                    continue
                category = tokens[0].lower()
                type_token = tokens[eq_idx + 1].upper()
                if type_token not in ("LIST", "RANGE"):
                    continue
                if "{" in tokens:
                    brace_idx = tokens.index("{")
                    tail = tokens[brace_idx + 1 :]
                    if "}" in tail:
                        end_idx = tail.index("}")
                        values = tail[:end_idx]
                        if type_token == "LIST":
                            _add_list(category, values)
                        else:
                            _add_range(category, values)
                        continue
                    else:
                        buffer = tail
                        mode = type_token
                        current_category = category
                else:
                    buffer = []
                    mode = type_token
                    current_category = category
            else:
                if "}" in tokens:
                    end_idx = tokens.index("}")
                    buffer.extend([t for t in tokens[:end_idx] if t not in ("{", "}")])
                    if current_category:
                        if mode == "LIST":
                            _add_list(current_category, buffer)
                        else:
                            _add_range(current_category, buffer)
                    buffer = []
                    mode = None
                    current_category = None
                else:
                    buffer.extend([t for t in tokens if t not in ("{", "}")])

    return data


def _parse_ir_road_pairs() -> list[tuple[int, int]]:
    in_block = False
    pairs: list[tuple[int, int]] = []
    for line in ir_default.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not in_block:
            if stripped.startswith("road_network") and "{" in stripped:
                in_block = True
            continue
        if stripped.startswith("}"):
            break
        line_no_comment = stripped.split("#", 1)[0].strip()
        if not line_no_comment or "=" not in line_no_comment:
            continue
        left, right = [s.strip() for s in line_no_comment.split("=", 1)]
        pairs.append((int(left), int(right.split()[0])))
    return pairs


def _ir_capital_ids() -> list[int]:
    countries = parse_tree(ir_default)["country"]["countries"]
    return [int(data["capital"]) for data in countries.values() if data["capital"] is not None]


def _non_land_keys(default_map: dict) -> set[str]:
    excluded = set()
    for key in (
        "sea_zones",
        "lakes",
        "river_provinces",
        "impassable_terrain",
        "uninhabitable",
        "wasteland",
        "non_ownable",
    ):
        excluded.update(default_map.get(key, set()))
    return excluded


def _dedupe(items: list) -> list:
    return list(dict.fromkeys(items))


def _build_ir_culture_to_group_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in ir_cultures.iterdir():
        if path.suffix != ".txt" or not path.is_file():
            continue
        tree = parse_tree(path)
        for group_tag, group_data in tree.items():
            group_key = f"ir_{group_tag}_g"
            for culture_tag in group_data["culture"]:
                mapping[str(culture_tag)] = group_key
    return mapping


def _select_town_setup(
    group_tag: str,
    rank: str,
    is_port: bool,
    default_city_setup: str,
) -> str:
    default_town_setup = (
        default_city_setup.replace("_city", "_town")
        if default_city_setup.endswith("_city")
        else default_city_setup
    )
    setup = IR_GROUP_TOWN_SETUPS.get(group_tag, {})
    if rank in ("city", "metropolis"):
        if is_port and "city_port" in setup:
            return setup["city_port"]
        return setup.get("city", default_city_setup)
    if is_port and "town_port" in setup:
        return setup["town_port"]
    return setup.get("town", default_town_setup)


def _build_market_keys(
    id_to_key: dict[int, str],
    location_keys: set[str],
    default_map: dict,
    max_markets: int = 20,
) -> list[str]:
    excluded = _non_land_keys(default_map)
    road_pairs = _parse_ir_road_pairs()
    degree: dict[int, int] = defaultdict(int)
    for a_id, b_id in road_pairs:
        degree[a_id] += 1
        degree[b_id] += 1

    def valid_id(pid: int) -> bool:
        key = id_to_key[pid]
        return key in location_keys and key not in excluded

    capitals = [pid for pid in _ir_capital_ids() if valid_id(pid)]
    capitals = sorted(_dedupe(capitals), key=lambda pid: degree.get(pid, 0), reverse=True)

    candidates = sorted(degree.keys(), key=lambda pid: degree.get(pid, 0), reverse=True)

    markets: list[str] = []
    for pid in capitals + candidates:
        if len(markets) >= max_markets:
            break
        if not valid_id(pid):
            continue
        key = id_to_key[pid]
        if key in markets:
            continue
        markets.append(key)
    return markets


def _get_tree_value(data, key: str):
    if isinstance(data, _pydt.Tree):
        return data[key] if key in data else None
    if isinstance(data, dict):
        return data.get(key)
    return None


def _prefix_ir(tag: str | None) -> str | None:
    if not tag:
        return None
    return tag if tag.startswith("ir_") else f"ir_{tag}"


def build_ir_pops(id_to_key: dict[int, str]) -> dict[str, list[str]]:
    """Build EU5 pop blocks from Imperator province setup data.

    Returns: { location_key: [define_pop_line, ...] }
    """
    province_dir = ir_game / "setup" / "provinces"
    if not province_dir.exists():
        return {}

    pop_type_map = {
        "nobles": "nobles",
        "citizen": "burghers",
        "freemen": "peasants",
        "slaves": "slaves",
        "tribesmen": "tribesmen",
    }

    def format_size(value) -> str:
        try:
            num = float(value)
        except Exception:
            return "0"
        return f"{num:.3f}"

    locations: dict[str, list[str]] = {}

    for path in sorted(province_dir.glob("*.txt")):
        tree = parse_tree(path)
        for raw_id, data in tree.items():
            try:
                prov_id = int(raw_id)
            except Exception:
                continue
            if prov_id not in id_to_key:
                continue
            if not isinstance(data, (_pydt.Tree, dict)):
                continue

            province_culture = _get_tree_value(data, "culture")
            province_religion = _get_tree_value(data, "religion")

            for pop_key, pop_value in data.items():
                if pop_key not in pop_type_map:
                    continue
                entries = pop_value if isinstance(pop_value, list) else [pop_value]
                for entry in entries:
                    if not isinstance(entry, (_pydt.Tree, dict)):
                        continue
                    amount = _get_tree_value(entry, "amount")
                    if amount is None:
                        continue
                    culture = _get_tree_value(entry, "culture") or province_culture
                    religion = _get_tree_value(entry, "religion") or province_religion
                    culture = _prefix_ir(str(culture)) if culture else None
                    religion = _prefix_ir(str(religion)) if religion else None
                    if not culture or not religion:
                        continue

                    loc_key = id_to_key[prov_id]
                    pop_type = pop_type_map[pop_key]
                    size = format_size(amount)
                    line = (
                        "define_pop = { "
                        f"type = {pop_type} "
                        f"size = {size} "
                        f"culture = {culture} "
                        f"religion = {religion} "
                        "}"
                    )
                    locations.setdefault(loc_key, []).append(line)

    return locations


def build_ir_location_ranks(
    id_to_key: dict[int, str],
    locations_with_pops: set[str],
    town_setup: str,
) -> dict[str, str]:
    """Build EU5 location rank data from Imperator province setup data."""
    province_dir = ir_game / "setup" / "provinces"
    if not province_dir.exists():
        return {}

    culture_to_group = _build_ir_culture_to_group_map()

    ranks: dict[str, str] = {}

    for path in sorted(province_dir.glob("*.txt")):
        tree = parse_tree(path)
        for raw_id, data in tree.items():
            try:
                prov_id = int(raw_id)
            except Exception:
                continue
            loc_key = id_to_key.get(prov_id)
            if not loc_key or loc_key not in locations_with_pops:
                continue
            if not isinstance(data, (_pydt.Tree, dict)):
                continue

            rank = data["province_rank"]
            if not rank:
                continue
            culture = data["culture"]
            group_tag = culture_to_group[str(culture)]
            is_port = "port_building" in data and data["port_building"]
            setup = _select_town_setup(group_tag, rank, bool(is_port), town_setup)
            ranks[loc_key] = f"rank = town town_setup = {setup}"

    return ranks


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

    # Ensure river provinces are not treated as sea zones
    if "sea_zones" in ir_default_map_data and "river_provinces" in ir_default_map_data:
        ir_default_map_data["sea_zones"] = ir_default_map_data["sea_zones"] - ir_default_map_data[
            "river_provinces"
        ]

    init_lines = [
        'provinces = "locations.png"',
        'rivers = "rivers.png"',
        'topology = "heightmap.heightmap"',
        'adjacencies = "adjacencies.csv"',
        'setup = "definitions.txt"',
        'ports = "ports.csv"',
        'location_templates = "location_templates.txt"',
        "equator_y = 3340",
        "wrap_x = yes",
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
    print_written("file", default_map)


def port_map_data(default_culture: str | None = None, default_religion: str | None = None):
    """Parse definitions, write named locations, adjacencies, ports, and check areas."""
    named_locations = parse_definitions()
    id_to_key = {prov_id: key for prov_id, key, *_ in named_locations}
    location_keys = {key for _, key, *_ in named_locations}

    # Named locations file
    named_path = iu_map_data / "named_locations"
    named_path.mkdir(parents=True, exist_ok=True)
    with open(named_path / "00_default.txt", "w", encoding="utf-8-sig") as f:
        for _, key, r, g, b, _ in named_locations:
            f.write(f"{key} = {r:02x}{g:02x}{b:02x}\n")
    print_written("file", named_path / "00_default.txt")

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
        parse_adjacencies(id_to_key, location_keys)[:-1],
        ["From", "To", "Type", "Through", "x1", "y1", "x2", "y2", "Comment"],
    )

    # Ports CSV
    write_csv(
        iu_map_data / "ports.csv",
        parse_ports(id_to_key),
        ["LandProvince", "SeaZone", "x", "y"],
    )

    # Default map categories (for sea zones, rivers, etc.)
    default_map = build_default_map(id_to_key)

    # Area validation
    regions = build_regions(id_to_key)
    assigned_provinces = {
        province
        for area_map in regions.values()
        for provinces in area_map.values()
        if isinstance(provinces, list)
        for province in provinces
    }

    river_provinces = default_map.get("river_provinces", set()) if isinstance(default_map, dict) else set()
    river_unassigned = set(river_provinces) - assigned_provinces
    if river_unassigned:
        regions.setdefault("river_provinces_region", {})["river_provinces_area"] = sorted(
            river_unassigned
        )

    sea_zones = default_map.get("sea_zones", set()) if isinstance(default_map, dict) else set()
    sea_unassigned = set(sea_zones) - assigned_provinces
    if sea_unassigned:
        regions.setdefault("sea_zones_region", {})["sea_zones_area"] = sorted(sea_unassigned)

    lakes = default_map.get("lakes", set()) if isinstance(default_map, dict) else set()
    lakes_unassigned = set(lakes) - assigned_provinces
    if lakes_unassigned:
        regions.setdefault("lakes_region", {})["lakes_area"] = sorted(lakes_unassigned)

    non_ownable = set()
    for key in ("impassable_terrain", "uninhabitable", "wasteland"):
        non_ownable.update(default_map.get(key, set()) if isinstance(default_map, dict) else set())
    # Avoid overlaps between non-ownable and other special buckets.
    non_ownable = set(non_ownable) - set(sea_zones) - set(lakes) - set(river_provinces)
    non_ownable_unassigned = set(non_ownable) - assigned_provinces
    if non_ownable_unassigned:
        regions.setdefault("non_ownable_region", {})["non_ownable_area"] = sorted(
            non_ownable_unassigned
        )
    region_keys = set(regions.keys())
    area_keys = {area for region in regions.values() for area in region.keys()}
    known_provinces = {
        province
        for region in regions.values()
        for provinces in region.values()
        if isinstance(provinces, list)
        for province in provinces
    }
    continent_keys = set()
    if isinstance(continent_map, dict):
        for key, value in continent_map.items():
            if isinstance(value, list):
                continent_keys.update(value)
            else:
                continent_keys.add(key)
    subcontinent_keys = set(superregion_map.keys()) if isinstance(superregion_map, dict) else set()
    nested = build_full_hierarchy(regions, superregion_map, continent_map)

    blocks = hierarchy_to_blocks(nested)

    write_blocks(
        iu_map_data / "definitions.txt",
        blocks,
    )

    # --- Exploration template (IR regions/areas/provinces mapping) ---
    template_path = mod_root / "main_menu" / "setup" / "templates" / "expl_imperator_rome.txt"
    template_path.parent.mkdir(parents=True, exist_ok=True)

    superregion_keys = sorted(
        {superregion for sub in superregion_map.values() for superregion in sub.keys()}
    )
    discovered_regions = sorted(superregion_keys)
    discovered_areas = sorted(region_keys)
    discovered_provinces = sorted(area_keys)

    with template_path.open("w", encoding="utf-8") as f:
        f.write("discovered_regions = {\n")
        for key in discovered_regions:
            f.write(f"\t{key}\n")
        f.write("}\n\n")

        f.write("discovered_areas = {\n")
        for key in discovered_areas:
            f.write(f"\t{key}\n")
        f.write("}\n\n")

        f.write("discovered_provinces = {\n")
        for key in discovered_provinces:
            f.write(f"\t{key}\n")
        f.write("}\n")

    print_written("file", template_path)

    # Localisation: provinces, areas, regions
    loc_lines = ["l_english:"]

    # Prefer existing Imperator localisation if present
    ir_loc = read_localisation_file(ir_localisation)
    location_names_dir = iu_localisation / "location_names"
    existing_loc = (
        read_localisation_file(location_names_dir) if location_names_dir.exists() else {}
    )

    # --- Provinces ---
    for prov_id, key, *_ in named_locations:
        if key in existing_loc:
            continue
        name = ir_loc.get(f"PROV{prov_id}", key)
        loc_lines.append(f'  {key}: "{name}"')

    # --- Regions ---
    for region_tag in regions:
        name = ir_loc.get(region_tag, region_tag)
        loc_lines.append(f'  {region_tag}: "{name}"')

    # --- Areas ---
    for area_list in regions.values():
        for area_tag in area_list:
            name = ir_loc.get(area_tag, area_tag)
            loc_lines.append(f'  {area_tag}: "{name}"')

    # --- Superregions, subcontinents, and continents ---
    def _title_key(key: str) -> str:
        return key.replace("_", " ").strip().title() if key else key

    superregion_keys = sorted(
        {superregion for sub in superregion_map.values() for superregion in sub.keys()}
    )
    for key in superregion_keys:
        if key not in existing_loc:
            loc_lines.append(f'  {key}: "{ir_loc.get(key, _title_key(key))}"')

    for key in sorted(subcontinent_keys):
        if key not in existing_loc:
            loc_lines.append(f'  {key}: "{ir_loc.get(key, _title_key(key))}"')

    for key in sorted(continent_keys):
        if key not in existing_loc:
            loc_lines.append(f'  {key}: "{ir_loc.get(key, _title_key(key))}"')

    # --- Generated map helper regions/areas ---
    for key in (
        "lakes_region",
        "lakes_area",
        "non_ownable_region",
        "non_ownable_area",
        "river_provinces_region",
        "river_provinces_area",
        "sea_zones_region",
        "sea_zones_area",
    ):
        if key not in existing_loc:
            loc_lines.append(f'  {key}: "{_title_key(key)}"')

    # Write localisation file
    write_blocks(iu_localisation / "ir_map_l_english.yml", loc_lines)

    write_default_map(default_map)

    # --- Location templates (only for existing land locations) ---
    location_templates = iu_map_data / "location_templates.txt"
    location_templates.parent.mkdir(parents=True, exist_ok=True)
    sea_zones = default_map.get("sea_zones", set()) if isinstance(default_map, dict) else set()
    with location_templates.open("w", encoding="utf-8") as f:
        for key in sorted(location_keys):
            if key in sea_zones:
                continue
            parts = [
                "topography = flatland",
                "vegetation = grasslands",
                "climate = continental",
            ]
            if default_religion:
                parts.append(f"religion = {default_religion}")
            if default_culture:
                parts.append(f"culture = {default_culture}")
            parts.append("raw_material = wool")
            f.write(f"{key} = {{ {' '.join(parts)} }}\n")
    print_written("file", location_templates)

    # --- Filter building triggers that reference missing locations ---
    src_building_triggers = (
        eu5_game / "in_game" / "common" / "scripted_triggers" / "building_triggers.txt"
    )
    dst_building_triggers = (
        mod_root / "in_game" / "common" / "scripted_triggers" / "building_triggers.txt"
    )
    if src_building_triggers.exists():
        dst_building_triggers.parent.mkdir(parents=True, exist_ok=True)
        with src_building_triggers.open(encoding="utf-8-sig") as src, dst_building_triggers.open(
            "w", encoding="utf-8-sig"
        ) as dst:
            for line in src:
                stripped = line.strip()
                if stripped.startswith("location_key") and "=" in stripped:
                    _, value = stripped.split("=", 1)
                    key = value.strip().split()[0]
                    if key not in location_keys:
                        continue
                dst.write(line)
        print_written("file", dst_building_triggers)

    # --- Filter/override holy sites that reference missing locations ---
    src_holy_sites = eu5_game / "in_game" / "common" / "holy_sites"
    dst_holy_sites = mod_root / "in_game" / "common" / "holy_sites"
    fallback_location = next(iter(sorted(location_keys))) if location_keys else None
    if src_holy_sites.exists():
        dst_holy_sites.mkdir(parents=True, exist_ok=True)
        for hs_file in src_holy_sites.glob("*.txt"):
            tree = parse_tree(hs_file)
            filtered = _pydt.Tree()
            for tag, data in tree.items():
                loc = None
                if isinstance(data, _pydt.Tree):
                    loc = data["location"] if "location" in data else None
                elif isinstance(data, dict):
                    loc = data.get("location")
                if isinstance(loc, str) and loc not in location_keys and fallback_location:
                    data["location"] = fallback_location
                filtered[tag] = data
            write_blocks(dst_holy_sites / hs_file.name, filtered)

    # --- Empty map object locators to avoid unknown location references ---
    locators_dir = mod_root / "in_game" / "gfx" / "map" / "map_objects"
    locators_dir.mkdir(parents=True, exist_ok=True)
    locator_defs = {
        "generated_map_object_locators_city.txt": ("city", "cities_layer"),
        "generated_map_object_locators_combat.txt": ("combat", "unit_layer"),
        "generated_map_object_locators_unit_stack.txt": ("unit_stack", "unit_layer"),
        "generated_map_object_locators_vfx.txt": ("vfx", "vfx_layer"),
    }
    for filename, (name, layer) in locator_defs.items():
        out_path = locators_dir / filename
        with out_path.open("w", encoding="utf-8") as f:
            f.write(
                "game_object_locator={\n"
                f"\tname=\"{name}\"\n"
                "\tclamp_to_water_level=no\n"
                "\trender_under_water=no\n"
                "\tgenerated_content=no\n"
                f"\tlayer=\"{layer}\"\n"
                "\tinstances={}\n"
                "}\n"
            )
        print_written("file", out_path)

    # --- Override locators_override to avoid invalid province names ---
    locators_override_dir = mod_root / "in_game" / "gfx" / "map" / "locators_override"
    locators_override_dir.mkdir(parents=True, exist_ok=True)
    locators_override_path = locators_override_dir / "locators_override.txt"
    locators_override_path.write_text(
        "# Auto-generated empty override to avoid invalid province references.\n",
        encoding="utf-8",
    )
    print_written("file", locators_override_path)

    # --- Override dynamic_game_objects to remove unknown location references ---
    map_objects_dir = mod_root / "in_game" / "gfx" / "map" / "map_objects"
    map_objects_dir.mkdir(parents=True, exist_ok=True)
    dynamic_objects_path = map_objects_dir / "dynamic_game_objects.txt"
    dynamic_objects_path.write_text(
        "dynamic_game_object = {\n"
        "\tname = \"desert_sandstorm\"\n"
        "\tschematic_name = { \"sand_storm_01_small_schematic\" \"sand_storm_01_medium_schematic\" \"sand_storm_01_large_schematic\" }\n"
        "\tentity_province_size_thresholds = { 1100.0 2100.0 }\n"
        "\ttemporary = yes\n"
        "}\n\n"
        "dynamic_game_object = {\n"
        "\tname = \"snowstorm\"\n"
        "\tschematic_name = { \"snow_storm_01_small_schematic\" \"snow_storm_01_medium_schematic\" \"snow_storm_01_large_schematic\" }\n"
        "\tentity_province_size_thresholds = { 2000.0 4000.0 }\n"
        "\ttemporary = yes\n"
        "}\n\n"
        "dynamic_game_object = {\n"
        "\tname = \"seastorm\"\n"
        "\tschematic_name = { \"sea_storm_01_small_schematic\" \"sea_storm_01_medium_schematic\" \"sea_storm_01_large_schematic\" }\n"
        "\tentity_province_size_thresholds = { 7000.0 13500.0 }\n"
        "\ttemporary = yes\n"
        "}\n\n"
        "dynamic_game_object = {\n"
        "\tname = \"volcano_eruption\"\n"
        "\tschematic_name = \"volcano_eruption_schematic\"\n"
        "\ttemporary = yes\n"
        "}\n\n"
        "dynamic_game_object = {\n"
        "\tname = \"volcano_eruption_test\"\n"
        "\tschematic_name = \"volcano_eruption_schematic\"\n"
        "\ttemporary = yes\n"
        "}\n",
        encoding="utf-8",
    )
    print_written("file", dynamic_objects_path)

    # --- Empty volcano locator file to prevent unknown location refs ---
    volcano_locator = map_objects_dir / "generated_map_object_locators_volcano_eruption.txt"
    volcano_locator.write_text(
        "game_object_locator={\n"
        "\tname=\"volcano_eruption\"\n"
        "\tclamp_to_water_level=no\n"
        "\trender_under_water=no\n"
        "\tgenerated_content=no\n"
        "\tlayer=\"vfx_layer\"\n"
        "\tinstances={}\n"
        "}\n",
        encoding="utf-8",
    )
    print_written("file", volcano_locator)

    # --- Patch scripts referencing missing locations/regions ---
    if location_keys:
        fallback_location = next(iter(sorted(location_keys)))
    else:
        fallback_location = None
    fallback_region = next(iter(sorted(region_keys))) if region_keys else None
    fallback_continent = next(iter(sorted(continent_keys))) if continent_keys else None
    fallback_subcontinent = next(iter(sorted(subcontinent_keys))) if subcontinent_keys else None

    def fix_script_file(src_path: Path, dst_path: Path):
        location_re = re.compile(r"(\blocation_key\s*=\s*)([A-Za-z0-9_:]+)")
        region_re = re.compile(r"(\bregion\s*=\s*)([A-Za-z0-9_:]+)")
        region_key_re = re.compile(r"(\bregion_key\s*=\s*)([A-Za-z0-9_:]+)")
        subcontinent_re = re.compile(r"(\bsub_continent\s*=\s*)([A-Za-z0-9_:]+)")
        continent_re = re.compile(r"(\bcontinent\s*=\s*)([A-Za-z0-9_:]+)")

        changed = False
        lines = []
        for line in src_path.read_text(encoding="utf-8-sig").splitlines():
            original = line
            if fallback_location:
                def repl_loc(m):
                    key = m.group(2)
                    return m.group(1) + (key if key in location_keys else fallback_location)
                line = location_re.sub(repl_loc, line)
            if fallback_region:
                def repl_region(m):
                    key = m.group(2)
                    if key in region_keys:
                        return m.group(1) + key
                    if ":" in key:
                        tail = key.split(":")[-1]
                        if tail in region_keys:
                            return m.group(1) + tail
                    return m.group(1) + fallback_region
                line = region_re.sub(repl_region, line)
                line = region_key_re.sub(repl_region, line)
            if fallback_subcontinent:
                def repl_subcontinent(m):
                    key = m.group(2)
                    if key in subcontinent_keys:
                        return m.group(1) + key
                    if ":" in key:
                        tail = key.split(":")[-1]
                        if tail in subcontinent_keys:
                            return m.group(1) + tail
                    return m.group(1) + fallback_subcontinent
                line = subcontinent_re.sub(repl_subcontinent, line)
            if fallback_continent:
                def repl_continent(m):
                    key = m.group(2)
                    if key in continent_keys:
                        return m.group(1) + key
                    if ":" in key:
                        tail = key.split(":")[-1]
                        if tail in continent_keys:
                            return m.group(1) + tail
                    return m.group(1) + fallback_continent
                line = continent_re.sub(repl_continent, line)
            if line != original:
                changed = True
            lines.append(line)

        if changed:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            dst_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
            print_written("file", dst_path)

    script_roots = [
        eu5_game / "in_game" / "events",
        eu5_game / "in_game" / "common" / "situations",
        eu5_game / "in_game" / "common" / "scripted_triggers",
    ]
    for root in script_roots:
        if not root.exists():
            continue
        for src in root.rglob("*.txt"):
            rel = src.relative_to(eu5_game / "in_game")
            dst = mod_root / "in_game" / rel
            fix_script_file(src, dst)

    # --- Filter start setup files keyed by location ---
    setup_start_dir = eu5_game / "main_menu" / "setup" / "start"
    dst_setup_start_dir = mod_root / "main_menu" / "setup" / "start"
    location_keyed_files = {
        "07_cities_and_buildings.txt",
        "08_institutions.txt",
        "14_development.txt",
    }
    if setup_start_dir.exists():
        dst_setup_start_dir.mkdir(parents=True, exist_ok=True)
        for filename in location_keyed_files:
            src_file = setup_start_dir / filename
            if not src_file.exists():
                continue
            tree = parse_tree(src_file)
            filtered = _pydt.Tree()
            for tag, data in tree.items():
                if tag in location_keys:
                    filtered[tag] = data
            write_blocks(dst_setup_start_dir / filename, filtered, encoding="utf-8")

    # --- Port Imperator population data (locations) ---
    pops_by_location = build_ir_pops(id_to_key)
    pops_blocks = []
    for loc_key in sorted(pops_by_location.keys()):
        pops_blocks.append((loc_key, pops_by_location[loc_key]))
    write_blocks(iu_setup_start / "06_pops.txt", [("locations", pops_blocks)], encoding="utf-8")

    # --- Port Imperator location ranks (towns/cities) ---
    rank_lines = build_ir_location_ranks(
        id_to_key,
        set(pops_by_location.keys()),
        town_setup="italian_city",
    )
    rank_blocks = [(loc_key, [rank_lines[loc_key]]) for loc_key in sorted(rank_lines.keys())]
    write_blocks(
        iu_setup_start / "07_cities_and_buildings.txt",
        [("locations", rank_blocks)],
        encoding="utf-8",
    )

    # --- Build markets from IR roads + capitals ---
    markets_dst = mod_root / "main_menu" / "setup" / "start" / "03_markets.txt"
    markets = _build_market_keys(id_to_key, location_keys, default_map, max_markets=20)
    markets_dst.parent.mkdir(parents=True, exist_ok=True)
    markets_dst.write_text(
        "market_manager = {\n"
        + "\n".join(f"\tadd_market = {key}" for key in markets)
        + "\n}\n",
        encoding="utf-8",
    )
    print_written("file", markets_dst)

    # --- Build roads from IR road network ---
    roads_dst = mod_root / "main_menu" / "setup" / "start" / "09_roads.txt"
    excluded = _non_land_keys(default_map)
    road_lines = []
    for a_id, b_id in _parse_ir_road_pairs():
        a_key = id_to_key[a_id]
        b_key = id_to_key[b_id]
        if a_key not in location_keys or b_key not in location_keys:
            continue
        if a_key in excluded or b_key in excluded:
            continue
        road_lines.append(f"\t{a_key} = {b_key}")

    roads_dst.parent.mkdir(parents=True, exist_ok=True)
    roads_dst.write_text(
        "road_network = {\n" + "\n".join(road_lines) + "\n}\n",
        encoding="utf-8",
    )
    print_written("file", roads_dst)

    # --- Filter exploration preferences (areas/regions) ---
    explor_src = eu5_game / "main_menu" / "setup" / "start" / "17_exploration_preferences.txt"
    explor_dst = mod_root / "main_menu" / "setup" / "start" / "17_exploration_preferences.txt"
    if explor_src.exists():
        lines = []
        for line in explor_src.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if stripped.startswith("area") and "=" in stripped:
                _, value = stripped.split("=", 1)
                key = value.strip().split()[0]
                if key not in area_keys:
                    continue
            if stripped.startswith("region") and "=" in stripped:
                _, value = stripped.split("=", 1)
                key = value.strip().split()[0]
                if key not in region_keys:
                    continue
            if stripped.startswith("continent") and "=" in stripped:
                _, value = stripped.split("=", 1)
                key = value.strip().split()[0]
                if key not in continent_keys:
                    continue
            if stripped.startswith("sub_continent") and "=" in stripped:
                _, value = stripped.split("=", 1)
                key = value.strip().split()[0]
                if key not in subcontinent_keys:
                    continue
            lines.append(line)
        explor_dst.parent.mkdir(parents=True, exist_ok=True)
        explor_dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print_written("file", explor_dst)

    # --- Filter location modifiers (21_locations) ---
    loc_src = eu5_game / "main_menu" / "setup" / "start" / "21_locations.txt"
    loc_dst = mod_root / "main_menu" / "setup" / "start" / "21_locations.txt"
    if loc_src.exists():
        tree = parse_tree(loc_src)
        filtered = _pydt.Tree()
        locations_block = tree["locations"] if "locations" in tree else _pydt.Tree()
        new_locations = _pydt.Tree()
        for tag, data in locations_block.items():
            if tag in location_keys:
                new_locations[tag] = data
        filtered["locations"] = new_locations
        write_blocks(loc_dst, filtered)

    # --- Filter colonies (province definitions not present) ---
    colonies_dst = mod_root / "main_menu" / "setup" / "start" / "23_colonies.txt"
    colonies_tree = _pydt.Tree()
    colonies_tree["colony_manager"] = _pydt.Tree()
    write_blocks(colonies_dst, colonies_tree)

    # Copy core map files so location IDs match definitions
    map_files = {
        ir_map_data / "provinces.png": iu_map_data / "locations.png",
        ir_map_data / "rivers.png": iu_map_data / "rivers.png",
        ir_map_data / "heightmap.heightmap": iu_map_data / "heightmap.heightmap",
    }
    for src, dst in map_files.items():
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print_written("file", dst)

    # --- Match EU5 map image dimensions to avoid scaled overlays ---
    eu5_locations_png = eu5_game / "in_game" / "map_data" / "locations.png"
    target_size = _png_size(eu5_locations_png) if eu5_locations_png.exists() else None
    if target_size:
        # locations.png must match EU5 size; resize with nearest-neighbor to avoid new colors
        locations_img = iu_map_data / "locations.png"
        size = _png_size(locations_img)
        if size and size != target_size:
            if _resize_png_in_place(locations_img, target_size):
                print_written("image", locations_img)

        # rivers.png: prefer EU5 base if sizes mismatch (avoid expensive resize failures)
        rivers_img = iu_map_data / "rivers.png"
        rivers_size = _png_size(rivers_img)
        if rivers_size and rivers_size != target_size:
            eu5_rivers = eu5_game / "in_game" / "map_data" / "rivers.png"
            if eu5_rivers.exists():
                shutil.copy2(eu5_rivers, rivers_img)
                print_written("file", rivers_img)
