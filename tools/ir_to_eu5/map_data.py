import csv
import math
import re
import shutil
from collections import defaultdict
from pathlib import Path

import pyradox.datatype as _pydt
from PIL import Image

from .extract_data import extract_ir_country_locations, parse_tree, read_localisation_file
from .paths import (
    eu5_game,
    ir_default,
    ir_game,
    ir_localisation_paths,
    ir_map_data,
    ir_path,
    iter_ir_files,
    iu_localisation,
    iu_map_data,
    iu_setup_start,
    mod_root,
)
from .write_data import write_blocks, print_written

# ---------------- Static Mappings ---------------- #

continent_map = {
    "europe": [
        "western_europe",
        "eastern_europe",
    ],
    "asia": [
        "western_asia",
        "india",
        "inner_asia",
    ],
    "africa": [
        "north_africa",
        "nile_and_horn",
    ],
}

superregion_map = {
    "western_europe": {
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
            "gallaecia_region",
            "western_mediterranean_river_region",
        ],
        "britain": [
            "britain_region",
            "caledonia_region",
        ],
        "north_sea": [
            "scandinavia_region",
            "baltic_sea_region",
            "atlantic_region",
            "baltic_river_region",
            "north_sea_river_region",
            "northern_atlantic_river_region",
            "southern_atlantic_river_region",
        ],
    },
    "eastern_europe": {
        "balkans": [
            "greece_region",
            "macedonia_region",
            "illyria_region",
            "thrace_region",
            "moesia_region",
            "moesia_s_region",
        ],
        "carpathia": [
            "dacia_region",
            "pannonia_region",
        ],
        "northern_forests": [
            "vistulia_region",
            "venedia_region",
            "hyperborea_region",
        ],
        "pontic_steppe": [
            "sarmatia_europea_region",
            "borysthenia_region",
            "black_sea_river_region",
            "taurica_region",
            "scythia_region",
            "don_river_region",
        ],
    },
    "western_asia": {
        "anatolia": [
            "asia_region",
            "bithynia_region",
            "galatia_region",
            "cappadocia_region",
            "cappadocia_pontica_region",
            "cilicia_region",
            "pontus_region",
            "cilician_river_region",
        ],
        "caucasus": [
            "armenia_region",
            "colchis_region",
            "albania_region",
        ],
        "persia": [
            "gedrosia_region",
            "persis_region",
            "media_region",
            "bactriana_region",
            "ariana_region",
        ],
        "arabia": [
            "arabia_region",
            "arabia_felix_region",
            "persian_gulf_region",
            "red_sea_region",
        ],
        "levant": [
            "assyria_region",
            "mesopotamia_region",
            "mesopotamia_river_region",
            "syria_region",
            "palestine_region",
            "eastern_mediterranean_river_region",
        ],
    },
    "india": {
        "indo_gangetic": [
            "gandhara_region",
            "maru_region",
            "avanti_region",
            "madhyadesa_region",
            "indo_gangetic_region",
        ],
        "deccan": [
            "vindhyaprstha_region",
            "dravida_region",
            "aparanta_region",
            "karnata_region",
            "southern_india_river_region",
            "western_india_river_region",
        ],
        "eastern_india": [
            "pracya_region",
            "indian_ocean_region",
            "burma_region",
        ],
    },
    "inner_asia": {
        "tibet": [
            "tibet_region",
        ],
        "central_asia": [
            "himalayan_region",
            "sogdiana_region",
            "central_asian_steppes_region",
            "sarmatia_asiatica_region",
            "sakia_region",
            "parthia_region",
        ],
    },
    "north_africa": {
        "maghreb": [
            "numidia_region",
            "mauretainia_region",
            "africa_region",
            "atlas_region",
        ],
        "libya": [
            "cyrenaica_region",
            "fezzan_region",
        ],
    },
    "nile_and_horn": {
        "egypt": [
            "upper_egypt_region",
            "lower_egypt_region",
            "nile_region",
        ],
        "nubia": [
            "nubia_region",
            "lower_nubia_region",
        ],
        "red_sea_region_group": [
            "punt_region",
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

# Map I:R building keys to EU5 building types.
# Defaults to identity, with optional overrides for renamed EU5 types.
IR_BUILDING_MAP_OVERRIDES = {
    # Map I:R buildings to EU5 base buildings to preserve base functionality.
    "fortress_building": "castle",
    "fortress_ramparts_building": "bastion",
    "hill_fort": "stockade",
    "port_building": "dock",
    "barracks_building": "barracks",
    "military_building": "armory",
    "foundry_building": "mason",
    "workshop_building": "tools_workshop",
    "commerce_building": "marketplace",
    "forum_building": "merchants_quarters",
    "court_building": "counting_house",
    "town_hall_building": "minting_office",
    "temple_building": "temple",
    "library_building": "library",
    "academy_building": "university",
    "theathre_building": "theater",
    "aqueduct_building": "construction_center",
    "population_building": "granary",
    "latifundia_building": "farming_village",
    "basic_settlement_infratructure_building": "market_village",
    "slave_mine_building": "slave_market",
    "local_forum_building": "bailiff",
}

# Map I:R trade_goods to EU5 goods keys used in location_templates raw_material.
IR_GOODS_TO_EU5_GOODS = {
    "grain": ("wheat", "rice", "maize"),
    "vegetables": ("wheat", "rice", "maize"),
    "wood": ("lumber",),
    "base_metals": ("iron", "copper", "lead", "tin"),
    "precious_metals": ("goods_gold", "silver"),
    "marble": ("stone",),
    "olive": ("wine", "wheat"),
    "papyrus": ("paper", "fiber_crops", "cloth"),
    "elephants": ("ivory",),
    "gemstones": ("gems",),
    "spices": ("incense", "tea"),
    "silk": ("silk",),
    "incense": ("incense",),
    "fish": ("fish",),
    "salt": ("salt",),
    "horses": ("horses",),
    "steppe_horses": ("horses",),
    "wine": ("wine",),
    "amber": ("amber",),
    "stone": ("stone",),
    "glass": ("glass",),
    "cloth": ("cloth", "fiber_crops"),
    "dye": ("dyes",),
    "fur": ("fur",),
    "wild_game": ("wild_game",),
    "cattle": ("wool",),
    "leather": ("fur", "wool"),
    "hemp": ("fiber_crops",),
    "woad": ("dyes",),
    "honey": ("wheat",),
    "dates": ("wheat",),
    "earthware": ("clay",),
    "camel": ("horses",),
}

# Per-I:R-good candidate weight overrides (higher = more likely).
IR_GOODS_WEIGHT_OVERRIDES = {
    "grain": {
        "wheat": 1.0,
        "rice": 0.6,
        "maize": 0.15,
    },
    "vegetables": {
        "wheat": 1.0,
        "rice": 0.6,
        "maize": 0.15,
    },
    "base_metals": {
        "iron": 1.0,
        "copper": 0.7,
        "lead": 0.4,
        "tin": 0.2,
    },
    "precious_metals": {
        "goods_gold": 0.25,
        "silver": 1.0,
    },
    "olive": {
        "wine": 0.8,
        "wheat": 0.3,
    },
    "papyrus": {
        "paper": 0.3,
        "fiber_crops": 1.0,
        "cloth": 0.6,
    },
    "spices": {
        "incense": 1.0,
        "tea": 0.2,
    },
    "cloth": {
        "cloth": 1.0,
        "fiber_crops": 0.5,
    },
    "leather": {
        "fur": 0.4,
        "wool": 1.0,
    },
}

# Targeted overrides from known EU5/I:R data mismatches.
# - `calacte` port works in-game against `mare_tyrrenum` with current I:U map geometry.
PORT_SEAZONE_OVERRIDES = {
    "calacte": "mare_tyrrenum",
}

# Default value for coastal locations if no I:R factors are found.
DEFAULT_COASTAL_NATURAL_HARBOR_SUITABILITY = "0.00"

# Map I:R terrain keys to EU5 topography and vegetation.
IR_TERRAIN_TO_TOPOGRAPHY = {
    "plains": "flatland",
    "farmland": "flatland",
    "forest": "flatland",
    "jungle": "flatland",
    "desert": "flatland",
    "hills": "hills",
    "mountain": "mountains",
    "marsh": "wetlands",
    "coastal_terrain": "flatland",
    "riverine_terrain": "flatland",
    "impassable_terrain": "mountains",
}

IR_TERRAIN_TO_VEGETATION = {
    "plains": "grasslands",
    "farmland": "farmland",
    "forest": "forest",
    "jungle": "jungle",
    "desert": "desert",
    "hills": "woods",
    "mountain": "sparse",
    "marsh": "woods",
    "coastal_terrain": "grasslands",
    "riverine_terrain": "grasslands",
    "impassable_terrain": "sparse",
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


def _sync_world_extents(defines_path: Path, size: tuple[int, int]) -> None:
    world_x, world_z = size
    x_line = f"\tWORLD_EXTENTS_X = {world_x}"
    z_line = f"\tWORLD_EXTENTS_Z = {world_z}"

    text = ""
    if defines_path.exists():
        text = defines_path.read_text(encoding="utf-8-sig")

    if "NJominiMap" not in text:
        if text and not text.endswith("\n"):
            text += "\n"
        text += (
            "\nNJominiMap = {\n"
            f"{x_line}\n"
            f"{z_line}\n"
            "}\n"
        )
    else:
        x_re = r"(?m)^([ \t]*)WORLD_EXTENTS_X\s*=\s*.+$"
        z_re = r"(?m)^([ \t]*)WORLD_EXTENTS_Z\s*=\s*.+$"

        if re.search(x_re, text):
            text = re.sub(x_re, x_line, text, count=1)
        else:
            text = re.sub(
                r"(NJominiMap\s*=\s*\{\n)",
                r"\1" + x_line + "\n",
                text,
                count=1,
            )

        if re.search(z_re, text):
            text = re.sub(z_re, z_line, text, count=1)
        else:
            text = re.sub(
                r"(NJominiMap\s*=\s*\{\n(?:.*\n)*?)",
                r"\1" + z_line + "\n",
                text,
                count=1,
            )

    defines_path.parent.mkdir(parents=True, exist_ok=True)
    defines_path.write_text(text, encoding="utf-8-sig")
    print_written("file", defines_path)


def _iter_ir_province_files() -> list[Path]:
    return [path for path in iter_ir_files("setup/provinces") if path.suffix == ".txt"]


# ---------------- Parsing Functions ---------------- #


def parse_definitions() -> list[tuple[int, str, int, int, int, str]]:
    """
    Parse definition.csv but generate keys from the localisation file.
    Returns: (prov_id, key, r, g, b, name)
    """
    definition_file = ir_path("map_data/definition.csv")
    ir_loc = read_localisation_file(ir_localisation_paths)  # read all localisation

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
    file = ir_path("map_data/adjacencies.csv")
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
    file = ir_path("map_data/ports.csv")
    ports = []
    with file.open(encoding="utf-8-sig", newline="") as f:
        sample = f.read(1024)
        f.seek(0)
        delimiter = "," if "," in sample and ";" not in sample else ";"
        reader = csv.reader(f, delimiter=delimiter)
        next(reader, None)  # header
        for row in reader:
            if len(row) < 4:
                continue
            try:
                land_id, sea_id = int(row[0]), int(row[1])
                x, y = float(row[2]), float(row[3])
            except ValueError:
                continue
            land_key = id_to_key.get(land_id, f"UNKNOWN_{land_id}")
            sea_key = id_to_key.get(sea_id, f"UNKNOWN_{sea_id}")
            sea_key = PORT_SEAZONE_OVERRIDES.get(land_key, sea_key)
            ports.append(
                {
                    "LandProvince": land_key,
                    "SeaZone": sea_key,
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

    areas = parse_tree(ir_path("map_data/areas.txt")).to_python()
    regions = parse_tree(ir_path("map_data/regions.txt")).to_python()

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
    default_map = ir_path("map_data/default.map")
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


def build_default_map_range_groups(
    id_to_key: dict[int, str],
    categories: set[str] | None = None,
) -> dict[str, list[list[str]]]:
    """
    Parse default.map and preserve individual RANGE groups per category.
    Returns:
      { category_name_lowercase: [ [province_key, ...], ... ] }
    """
    target_categories = {c.lower() for c in categories} if categories else None
    default_map = ir_path("map_data/default.map")
    groups: dict[str, list[list[str]]] = {}
    mode = None
    current_category = None
    buffer: list[str] = []

    def _add_range_group(category: str, values: list[str]) -> None:
        if len(values) < 2:
            return
        try:
            start = int(values[0])
            end = int(values[1])
        except Exception:
            return
        keys = [id_to_key[n] for n in range(start, end + 1) if n in id_to_key]
        if keys:
            groups.setdefault(category, []).append(keys)

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
                if type_token != "RANGE":
                    continue
                if target_categories is not None and category not in target_categories:
                    continue
                if "{" in tokens:
                    brace_idx = tokens.index("{")
                    tail = tokens[brace_idx + 1 :]
                    if "}" in tail:
                        end_idx = tail.index("}")
                        values = tail[:end_idx]
                        _add_range_group(category, values)
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
                        _add_range_group(current_category, buffer)
                    buffer = []
                    mode = None
                    current_category = None
                else:
                    buffer.extend([t for t in tokens if t not in ("{", "}")])

    return groups


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


def _ir_country_capitals() -> dict[str, int]:
    countries = parse_tree(ir_default)["country"]["countries"]
    capitals: dict[str, int] = {}
    for tag, data in countries.items():
        try:
            cap = data["capital"]
        except Exception:
            cap = None
        if cap is None:
            continue
        try:
            capitals[str(tag)] = int(cap)
        except Exception:
            continue
    return capitals


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
    for path in iter_ir_files("common/cultures"):
        if path.suffix != ".txt" or not path.is_file():
            continue
        tree = parse_tree(path)
        for group_tag, group_data in tree.items():
            group_key = f"ir_{group_tag}_g"
            for culture_tag in group_data["culture"]:
                mapping[str(culture_tag)] = group_key
    return mapping


def _load_ir_building_keys() -> set[str]:
    ir_buildings = ir_path("common/buildings/00_default.txt")
    if not ir_buildings.exists():
        return set()
    tree = parse_tree(ir_buildings)
    return {str(key) for key in tree.keys()}


def _load_eu5_goods_keys() -> set[str]:
    goods_dir = eu5_game / "in_game" / "common" / "goods"
    if not goods_dir.exists():
        return set()
    keys: set[str] = set()
    for path in goods_dir.glob("*.txt"):
        tree = parse_tree(path)
        for key in tree.keys():
            keys.add(str(key))
    return keys


def build_ir_building_mapping() -> dict[str, str]:
    keys = _load_ir_building_keys()
    mapping = {key: key for key in keys}
    mapping.update(IR_BUILDING_MAP_OVERRIDES)
    return mapping


def build_ir_raw_materials(id_to_key: dict[int, str]) -> dict[str, str]:
    """Map I:R trade_goods to EU5 raw_material keys per location."""
    province_files = _iter_ir_province_files()
    if not province_files:
        return {}

    eu5_goods = _load_eu5_goods_keys()

    def map_good(
        ir_good: str | None,
        usage_counts: dict[str, int],
        seed_key: str,
    ) -> str | None:
        if not ir_good:
            return None
        key = str(ir_good).strip()
        candidates: list[str] = []
        if key in eu5_goods:
            candidates = [key]
        else:
            mapped = IR_GOODS_TO_EU5_GOODS.get(key)
            if mapped:
                candidates = [c for c in mapped if c in eu5_goods]
        if candidates:
            # Deterministic weighted pick: rarer candidates (lower usage) get higher weight.
            bias = IR_GOODS_WEIGHT_OVERRIDES.get(key, {})
            weights = [
                (1.0 / (1 + usage_counts.get(candidate, 0))) * bias.get(candidate, 1.0)
                for candidate in candidates
            ]
            total = sum(weights)
            if total <= 0:
                return candidates[0]
            import hashlib

            digest = hashlib.sha256(seed_key.encode("utf-8")).digest()
            r = int.from_bytes(digest, "big") / (1 << (8 * len(digest)))
            threshold = r * total
            cumulative = 0.0
            for candidate, weight in zip(candidates, weights):
                cumulative += weight
                if cumulative >= threshold:
                    return candidate
            return candidates[-1]
        return None

    result: dict[str, str] = {}
    eu5_usage_counts: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    mapped_counts: dict[str, int] = defaultdict(int)
    missing: dict[str, int] = defaultdict(int)
    for path in province_files:
        tree = parse_tree(path)
        for raw_id, data in sorted(tree.items(), key=lambda item: int(item[0])):
            try:
                prov_id = int(raw_id)
            except Exception:
                continue
            if prov_id not in id_to_key:
                continue
            if not isinstance(data, (_pydt.Tree, dict)):
                continue
            ir_good = data.get("trade_goods") if isinstance(data, dict) else data["trade_goods"]
            if ir_good:
                counts[str(ir_good)] += 1
            loc_key = id_to_key[prov_id]
            mapped = map_good(ir_good, eu5_usage_counts, f"{loc_key}|{ir_good}")
            if not mapped:
                if ir_good:
                    missing[str(ir_good)] += 1
                continue
            result[loc_key] = mapped
            eu5_usage_counts[mapped] += 1
            if ir_good:
                mapped_counts[str(ir_good)] += 1

    report_path = Path(__file__).parent / "ir_goods_mapping_report.tsv"
    lines = ["ir_good\tcount\tmapped\tmissing\tmapped_to"]
    for ir_good in sorted(counts.keys()):
        mapped_to = IR_GOODS_TO_EU5_GOODS.get(ir_good, "")
        if isinstance(mapped_to, (list, tuple)):
            mapped_to = ",".join(mapped_to)
        lines.append(
            f"{ir_good}\t{counts[ir_good]}\t{mapped_counts[ir_good]}\t{missing[ir_good]}\t{mapped_to}"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print_written("file", report_path)

    return result


def build_ir_terrain_maps(id_to_key: dict[int, str]) -> dict[str, tuple[str, str]]:
    """Return {location_key: (topography, vegetation)} from I:R province terrain."""
    province_files = _iter_ir_province_files()
    if not province_files:
        return {}

    result: dict[str, tuple[str, str]] = {}
    for path in province_files:
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
            terrain = data.get("terrain") if isinstance(data, dict) else data["terrain"]
            if not terrain:
                continue
            terrain_key = str(terrain).strip()
            topography = IR_TERRAIN_TO_TOPOGRAPHY.get(terrain_key)
            vegetation = IR_TERRAIN_TO_VEGETATION.get(terrain_key)
            if not topography or not vegetation:
                continue
            result[id_to_key[prov_id]] = (topography, vegetation)

    return result


def build_ir_harbor_suitability(
    named_locations: list[tuple[int, str, int, int, int, str]],
    location_keys: set[str],
    default_map: dict,
    coastal_locations: set[str],
) -> dict[str, str]:
    """Build natural_harbor_suitability from Imperator map geometry only.

    Factors:
    - Local shoreline enclosure around each port coordinate
    - Sea-zone coastline density (coastline length relative to area)
    - Sea-zone size (smaller zones are generally more sheltered)
    """
    if not coastal_locations:
        return {}

    sea_zones = set(default_map.get("sea_zones", set())) if isinstance(default_map, dict) else set()
    if not sea_zones:
        return {loc: DEFAULT_COASTAL_NATURAL_HARBOR_SUITABILITY for loc in coastal_locations}

    locations_png = ir_path("map_data/provinces.png")
    if not locations_png.exists():
        return {loc: DEFAULT_COASTAL_NATURAL_HARBOR_SUITABILITY for loc in coastal_locations}

    key_to_idx: dict[str, int] = {}
    idx_to_key: list[str] = []

    def idx_for_key(key: str) -> int:
        if key in key_to_idx:
            return key_to_idx[key]
        idx = len(idx_to_key)
        key_to_idx[key] = idx
        idx_to_key.append(key)
        return idx

    for key in sorted(location_keys):
        idx_for_key(key)

    unknown_idx = idx_for_key("__unknown__")

    color_to_idx: dict[int, int] = {}
    for _, key, r, g, b, _ in named_locations:
        color_to_idx[(r << 16) | (g << 8) | b] = key_to_idx.get(key, unknown_idx)

    sea_idx_set = {key_to_idx[key] for key in sea_zones if key in key_to_idx}

    with Image.open(locations_png) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        raw = rgb.tobytes()

    total = width * height
    idx_grid = [unknown_idx] * total
    for i in range(total):
        j = i * 3
        color = (raw[j] << 16) | (raw[j + 1] << 8) | raw[j + 2]
        idx_grid[i] = color_to_idx.get(color, unknown_idx)

    sea_area: dict[int, int] = defaultdict(int)
    sea_coast_edges: dict[int, int] = defaultdict(int)

    for y in range(height):
        row_off = y * width
        for x in range(width):
            i = row_off + x
            idx = idx_grid[i]
            if idx not in sea_idx_set:
                continue
            sea_area[idx] += 1
            if x + 1 < width:
                right = idx_grid[i + 1]
                if right not in sea_idx_set:
                    sea_coast_edges[idx] += 1
            if y + 1 < height:
                down = idx_grid[i + width]
                if down not in sea_idx_set:
                    sea_coast_edges[idx] += 1

    size_factor: dict[int, float] = {}
    density_factor: dict[int, float] = {}

    if sea_area:
        logs = {idx: math.log(max(area, 1)) for idx, area in sea_area.items()}
        min_log = min(logs.values())
        max_log = max(logs.values())
        log_span = max(1e-9, max_log - min_log)
        for idx, lval in logs.items():
            size_factor[idx] = 1.0 - ((lval - min_log) / log_span)

        raw_density = {
            idx: sea_coast_edges.get(idx, 0) / max(1.0, math.sqrt(float(area)))
            for idx, area in sea_area.items()
        }
        min_den = min(raw_density.values())
        max_den = max(raw_density.values())
        den_span = max(1e-9, max_den - min_den)
        for idx, dval in raw_density.items():
            density_factor[idx] = (dval - min_den) / den_span

    port_rows = parse_ports({prov_id: key for prov_id, key, *_ in named_locations})

    result: dict[str, str] = {}
    for row in port_rows:
        land_key = row.get("LandProvince")
        sea_key = row.get("SeaZone")
        if not isinstance(land_key, str) or land_key not in coastal_locations:
            continue
        if not isinstance(sea_key, str):
            continue
        sea_idx = key_to_idx.get(sea_key)
        if sea_idx is None or sea_idx not in sea_idx_set:
            result[land_key] = DEFAULT_COASTAL_NATURAL_HARBOR_SUITABILITY
            continue

        x = int(round(float(row.get("x", 0.0))))
        y = int(round(float(row.get("y", 0.0))))

        sample_dirs = []
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            sample_dirs.append((math.cos(rad), math.sin(rad)))

        ring_radii = (6, 12, 18)
        valid = 0
        water_count = 0
        same_sea_count = 0
        for radius in ring_radii:
            for dx, dy in sample_dirs:
                sx = int(round(x + dx * radius))
                sy = int(round(y + dy * radius))
                if sx < 0 or sy < 0 or sx >= width or sy >= height:
                    continue
                valid += 1
                sidx = idx_grid[sy * width + sx]
                if sidx in sea_idx_set:
                    water_count += 1
                    if sidx == sea_idx:
                        same_sea_count += 1

        if valid <= 0:
            local_enclosure = 0.0
        else:
            land_fraction = (valid - water_count) / float(valid)
            same_sea_fraction = same_sea_count / float(valid)
            local_enclosure = 0.6 * land_fraction + 0.4 * (1.0 - same_sea_fraction)

        score = (
            0.50 * local_enclosure
            + 0.30 * density_factor.get(sea_idx, 0.0)
            + 0.20 * size_factor.get(sea_idx, 0.0)
        )
        score = max(0.0, min(1.0, score))
        score = round(score * 20) / 20
        result[land_key] = f"{score:.2f}"

    for loc_key in coastal_locations:
        result.setdefault(loc_key, DEFAULT_COASTAL_NATURAL_HARBOR_SUITABILITY)

    return result


def build_ir_location_building_setups(
    id_to_key: dict[int, str],
    locations_with_pops: set[str],
    building_map: dict[str, str],
    include_locations: set[str] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, int]]]:
    """Build per-location town_setups based on I:R buildings.

    Returns:
        - location_to_setup: { location_key: setup_name }
        - setup_definitions: { setup_name: { building_key: level } }
    """
    province_files = _iter_ir_province_files()
    if not province_files:
        return {}, {}

    def normalize_level(value) -> int:
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        try:
            return int(str(value).strip())
        except Exception:
            return 0

    location_to_setup: dict[str, str] = {}
    setup_definitions: dict[str, dict[str, int]] = {}

    for path in province_files:
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

            buildings: dict[str, int] = {}

            for key, value in data.items():
                key_str = str(key)
                if key_str == "buildings" and isinstance(value, (_pydt.Tree, dict)):
                    for b_key, b_value in value.items():
                        b_key_str = str(b_key)
                        if b_key_str not in building_map:
                            continue
                        level = normalize_level(b_value)
                        if level > 0:
                            mapped = building_map[b_key_str]
                            buildings[mapped] = max(buildings.get(mapped, 0), level)
                    continue

                if key_str not in building_map:
                    continue
                level = normalize_level(value)
                if level <= 0:
                    continue
                mapped = building_map[key_str]
                buildings[mapped] = max(buildings.get(mapped, 0), level)

            setup_name = f"ir_loc_{loc_key}"
            location_to_setup[loc_key] = setup_name
            setup_definitions[setup_name] = buildings

    if include_locations:
        for loc_key in sorted(include_locations):
            setup_name = f"ir_loc_{loc_key}"
            location_to_setup.setdefault(loc_key, setup_name)
            setup_definitions.setdefault(setup_name, {})

    return location_to_setup, setup_definitions


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
    location_to_region: dict[str, str],
    country_locations: dict[str, list[int]],
    country_capitals: dict[str, int],
    top_capitals: int = 35,
    max_markets: int = 35,
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

    top_country_tags = sorted(
        country_locations.keys(),
        key=lambda tag: len(country_locations.get(tag, [])),
        reverse=True,
    )
    preferred_capitals: list[int] = []
    for tag in top_country_tags[:top_capitals]:
        cap_id = country_capitals.get(tag)
        if cap_id is None:
            continue
        if valid_id(cap_id):
            preferred_capitals.append(cap_id)
    preferred_capitals = _dedupe(preferred_capitals)

    markets: list[str] = []
    for pid in preferred_capitals:
        key = id_to_key[pid]
        if key not in markets:
            markets.append(key)
        if len(markets) >= max_markets:
            break

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
    province_files = _iter_ir_province_files()
    if not province_files:
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

    for path in province_files:
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
    location_town_setups: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build EU5 location rank data from Imperator province setup data."""
    province_files = _iter_ir_province_files()
    if not province_files:
        return {}

    culture_to_group = _build_ir_culture_to_group_map()

    ranks: dict[str, str] = {}

    def map_rank_to_eu5(raw_rank: str | None) -> str | None:
        if not raw_rank:
            return None
        rank = str(raw_rank).strip().lower()
        if rank == "city":
            return "town"
        if rank == "metropolis":
            return "town"
        if rank == "settlement":
            return None
        return None

    for path in province_files:
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
            eu5_rank = map_rank_to_eu5(rank)
            if not eu5_rank:
                continue
            culture = data["culture"]
            group_tag = culture_to_group[str(culture)]
            is_port = "port_building" in data and data["port_building"]
            if location_town_setups is not None:
                setup = location_town_setups.get(loc_key, f"ir_loc_{loc_key}")
            else:
                setup = _select_town_setup(group_tag, rank, bool(is_port), town_setup)
            ranks[loc_key] = f"rank = {eu5_rank} town_setup = {setup}"

    return ranks


def build_ir_rankable_locations(
    id_to_key: dict[int, str],
    locations_with_pops: set[str],
) -> set[str]:
    """Return locations that should receive a rank entry in EU5."""
    province_files = _iter_ir_province_files()
    if not province_files:
        return set()

    def map_rank_to_eu5(raw_rank: str | None) -> bool:
        if not raw_rank:
            return False
        rank = str(raw_rank).strip().lower()
        return rank in ("city", "metropolis")

    rankable: set[str] = set()
    for path in province_files:
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
            if map_rank_to_eu5(data["province_rank"]):
                rankable.add(loc_key)
    return rankable


def write_default_map(ir_default_map_data: dict):
    """
    Writes the default.map file for Imperator / EU modding, mapping and aggregating categories.
    ir_default_map_data: { category_name: set of province keys }
    """
    default_map = iu_map_data / "default.map"

    # Category mapping:
    # - I:R impassable_terrain and wasteland should both become EU5 impassable_mountains.
    # - I:R uninhabitable is used for corridor-like non-ownable connectors.
    category_mapping = {
        "sea_zones": "sea_zones",
        "lakes": "lakes",
        "impassable_terrain": "impassable_mountains",
        "wasteland": "impassable_mountains",
        "uninhabitable": "non_ownable",
        "non_ownable": "non_ownable",
        "river_provinces": "river_provinces",
    }

    # Ensure river provinces are not treated as sea zones
    if "sea_zones" in ir_default_map_data and "river_provinces" in ir_default_map_data:
        ir_default_map_data["sea_zones"] = ir_default_map_data["sea_zones"] - ir_default_map_data[
            "river_provinces"
        ]

    init_lines = [
        'provinces = "locations.png"',
        'rivers = "rivers.png"',
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

        # Merge categories that map to the same EU5 category (e.g. wasteland + impassable_terrain).
        mapped_data: dict[str, set] = {}
        for category, keys in ir_default_map_data.items():
            mapped_category = category_mapping.get(category, category)
            mapped_data.setdefault(mapped_category, set()).update(keys)

        # Write each mapped category once.
        for mapped_category in sorted(mapped_data.keys()):
            write_category(mapped_category, mapped_data[mapped_category])
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
    ports = parse_ports(id_to_key)
    write_csv(
        iu_map_data / "ports.csv",
        ports,
        ["LandProvince", "SeaZone", "x", "y"],
    )
    coastal_land_locations = {
        row["LandProvince"]
        for row in ports
        if isinstance(row.get("LandProvince"), str)
        and row["LandProvince"]
        and not row["LandProvince"].startswith("UNKNOWN_")
    }
    # Default map categories (for sea zones, rivers, etc.)
    default_map = build_default_map(id_to_key)
    harbor_suitability_map = build_ir_harbor_suitability(
        named_locations,
        location_keys,
        default_map,
        coastal_land_locations,
    )

    # Area validation
    regions = build_regions(id_to_key)
    location_to_region: dict[str, str] = {}
    for region_tag, area_map in regions.items():
        for provinces in area_map.values():
            if not isinstance(provinces, list):
                continue
            for key in provinces:
                location_to_region.setdefault(key, region_tag)
    assigned_provinces = {
        province
        for area_map in regions.values()
        for provinces in area_map.values()
        if isinstance(provinces, list)
        for province in provinces
    }

    def add_generated_region(region_tag: str, area_tag: str, keys) -> None:
        nonlocal assigned_provinces
        unassigned = set(keys) - assigned_provinces
        if unassigned:
            regions.setdefault(region_tag, {})[area_tag] = sorted(unassigned)
            assigned_provinces = assigned_provinces | set(unassigned)

    range_groups = build_default_map_range_groups(
        id_to_key,
        {
            "impassable_terrain",
            "wasteland",
            "sea_zones",
            "lakes",
            "river_provinces",
            "uninhabitable",
            "non_ownable",
        },
    )

    def add_generated_region_from_ranges(
        region_tag: str,
        area_prefix: str,
        keys,
        source_categories: tuple[str, ...],
    ) -> None:
        nonlocal assigned_provinces
        area_index = 1
        target_keys = set(keys)
        for source in source_categories:
            for group in range_groups.get(source, []):
                group_keys = [
                    key
                    for key in group
                    if key in target_keys and key not in assigned_provinces
                ]
                if not group_keys:
                    continue
                area_tag = f"{area_prefix}_{area_index:03d}"
                regions.setdefault(region_tag, {})[area_tag] = group_keys
                assigned_provinces = assigned_provinces | set(group_keys)
                area_index += 1
        leftovers = set(target_keys) - assigned_provinces
        if leftovers:
            add_generated_region(region_tag, f"{area_prefix}_misc", leftovers)

    river_provinces = default_map.get("river_provinces", set()) if isinstance(default_map, dict) else set()
    if river_provinces:
        add_generated_region_from_ranges(
            "river_provinces_region",
            "river_provinces_area",
            river_provinces,
            ("river_provinces",),
        )

    sea_zones = default_map.get("sea_zones", set()) if isinstance(default_map, dict) else set()
    if sea_zones:
        add_generated_region_from_ranges(
            "sea_zones_region",
            "sea_zones_area",
            sea_zones,
            ("sea_zones",),
        )

    lakes = default_map.get("lakes", set()) if isinstance(default_map, dict) else set()
    if lakes:
        add_generated_region_from_ranges(
            "lakes_region",
            "lakes_area",
            lakes,
            ("lakes",),
        )

    impassable = set()
    for key in ("impassable_terrain", "wasteland", "impassable_mountains"):
        impassable.update(default_map.get(key, set()) if isinstance(default_map, dict) else set())
    # Keep non-land special buckets separate from impassable terrain.
    impassable = set(impassable) - set(sea_zones) - set(lakes) - set(river_provinces)
    if impassable:
        add_generated_region_from_ranges(
            "impassable_terrain_region",
            "impassable_terrain_area",
            impassable,
            ("impassable_terrain", "wasteland"),
        )

    non_ownable = set()
    for key in ("uninhabitable", "non_ownable"):
        non_ownable.update(default_map.get(key, set()) if isinstance(default_map, dict) else set())
    # Avoid overlaps between non-ownable and other special buckets.
    non_ownable = set(non_ownable) - set(sea_zones) - set(lakes) - set(river_provinces) - set(impassable)
    if non_ownable:
        add_generated_region_from_ranges(
            "non_ownable_region",
            "non_ownable_area",
            non_ownable,
            ("uninhabitable", "non_ownable"),
        )

    all_unassigned = set(location_keys) - assigned_provinces
    if all_unassigned:
        add_generated_region("unassigned_locations_region", "unassigned_locations_area", all_unassigned)
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
        continent_keys.update(continent_map.keys())
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
    ir_loc = read_localisation_file(ir_localisation_paths)
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

    superregion_name_overrides = {
        "persia": "Persia",
        "arabia": "Arabia",
        "caucasus": "Caucasus",
        "levant": "Levant",
        "carpathia": "Carpathia",
        "northern_forests": "Northern Forests",
        "pontic_steppe": "Pontic Steppe",
        "maghreb": "Maghreb",
        "ifriqiya": "Ifriqiya",
        "libya": "Libya",
        "sahara": "Sahara",
    }

    superregion_keys = sorted(
        {superregion for sub in superregion_map.values() for superregion in sub.keys()}
    )
    for key in superregion_keys:
        if key not in existing_loc:
            label = superregion_name_overrides.get(key, ir_loc.get(key, _title_key(key)))
            loc_lines.append(f'  {key}: "{label}"')

    for key in sorted(subcontinent_keys):
        if key not in existing_loc:
            loc_lines.append(f'  {key}: "{ir_loc.get(key, _title_key(key))}"')

    for key in sorted(continent_keys):
        if key not in existing_loc:
            loc_lines.append(f'  {key}: "{ir_loc.get(key, _title_key(key))}"')

    # --- Generated map helper regions/areas ---
    for key in (
        "impassable_terrain_region",
        "impassable_terrain_area",
        "lakes_region",
        "lakes_area",
        "non_ownable_region",
        "non_ownable_area",
        "river_provinces_region",
        "river_provinces_area",
        "sea_zones_region",
        "sea_zones_area",
        "unassigned_locations_region",
        "unassigned_locations_area",
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
    excluded_locations = _non_land_keys(default_map) if isinstance(default_map, dict) else set()
    raw_materials = build_ir_raw_materials(id_to_key)
    terrain_map = build_ir_terrain_maps(id_to_key)
    with location_templates.open("w", encoding="utf-8") as f:
        for key in sorted(location_keys):
            if key in sea_zones:
                continue
            is_ownable = key not in excluded_locations
            parts = ["climate = continental"]
            if is_ownable:
                terrain = terrain_map.get(key)
                topography = terrain[0] if terrain else "flatland"
                vegetation = terrain[1] if terrain else "grasslands"
                parts.insert(0, f"vegetation = {vegetation}")
                parts.insert(0, f"topography = {topography}")
            if default_religion:
                parts.append(f"religion = {default_religion}")
            if default_culture:
                parts.append(f"culture = {default_culture}")
            if is_ownable:
                parts.append(f"raw_material = {raw_materials.get(key, 'wool')}")
            if is_ownable and key in coastal_land_locations:
                harbor_suitability = harbor_suitability_map.get(
                    key, DEFAULT_COASTAL_NATURAL_HARBOR_SUITABILITY
                )
                parts.append(f"natural_harbor_suitability = {harbor_suitability}")
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

    # Situations in I:U should remain blank (basegame logic/data dependencies).
    src_situations = eu5_game / "in_game" / "common" / "situations"
    dst_situations = mod_root / "in_game" / "common" / "situations"
    if src_situations.exists():
        dst_situations.mkdir(parents=True, exist_ok=True)
        for src in src_situations.rglob("*.txt"):
            rel = src.relative_to(src_situations)
            dst = dst_situations / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("", encoding="utf-8-sig")
            print_written("file", dst)

    # Scripted triggers still need location-aware patching.
    scripted_triggers_root = eu5_game / "in_game" / "common" / "scripted_triggers"
    if scripted_triggers_root.exists():
        for src in scripted_triggers_root.rglob("*.txt"):
            rel = src.relative_to(eu5_game / "in_game")
            dst = mod_root / "in_game" / rel
            fix_script_file(src, dst)

    # --- Filter start setup files keyed by location ---
    setup_start_dir = eu5_game / "main_menu" / "setup" / "start"
    dst_setup_start_dir = mod_root / "main_menu" / "setup" / "start"
    location_keyed_files = {
        "07_cities_and_buildings.txt",
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

    # --- Ownable locations (exclude seas/lakes/rivers/non-ownable) ---
    excluded_locations = _non_land_keys(default_map) if isinstance(default_map, dict) else set()
    ownable_locations = sorted(set(pops_by_location.keys()) - excluded_locations)

    # --- Generate institutions spread (08_institutions) for ownable locations only ---
    institutions_dst = mod_root / "main_menu" / "setup" / "start" / "08_institutions.txt"
    institution_blocks = []
    for loc_key in ownable_locations:
        institution_blocks.append(
            (
                loc_key,
                [
                    "feudalism = yes",
                    "legalism = yes",
                    "meritocracy = yes",
                ],
            )
        )
    write_blocks(
        institutions_dst,
        [("locations", institution_blocks)],
        encoding="utf-8",
    )

    # --- Port Imperator building setups (per location) ---
    building_map = build_ir_building_mapping()
    rankable_locations = build_ir_rankable_locations(id_to_key, set(pops_by_location.keys()))
    location_building_setups, setup_definitions = build_ir_location_building_setups(
        id_to_key,
        set(pops_by_location.keys()),
        building_map,
        include_locations=rankable_locations,
    )
    # --- Also include any building assignments present in Imperator's main/default setup ---
    main_setup = ir_path("setup/main/00_default.txt")
    if main_setup.exists():
        main_tree = parse_tree(main_setup)
        provinces = main_tree["provinces"] if "provinces" in main_tree else None
        merged_count = 0
        if isinstance(provinces, (_pydt.Tree, dict)):
            for raw_id, data in provinces.items():
                try:
                    prov_id = int(raw_id)
                except Exception:
                    continue
                loc_key = id_to_key.get(prov_id)
                if not loc_key:
                    continue
                if not isinstance(data, (_pydt.Tree, dict)):
                    continue
                setup_name = f"ir_loc_{loc_key}"
                dst_buildings = setup_definitions.setdefault(setup_name, {})
                # If there's an inner 'buildings' block, handle it first
                inner = (
                    data.get("buildings")
                    if isinstance(data, dict)
                    else data["buildings"] if "buildings" in data else None
                )
                if isinstance(inner, (_pydt.Tree, dict)):
                    for b_key, b_val in inner.items():
                        b_key_str = str(b_key)
                        if b_key_str not in building_map:
                            continue
                        try:
                            level = int(str(b_val).strip())
                        except Exception:
                            level = 0
                        if level > 0:
                            mapped = building_map[b_key_str]
                            dst_buildings[mapped] = max(dst_buildings.get(mapped, 0), level)
                            merged_count += 1
                # Also check top-level keys for direct building assignments
                for key, val in data.items():
                    key_str = str(key)
                    if key_str not in building_map:
                        continue
                    try:
                        level = int(str(val).strip())
                    except Exception:
                        level = 0
                    if level <= 0:
                        continue
                    mapped = building_map[key_str]
                    dst_buildings[mapped] = max(dst_buildings.get(mapped, 0), level)
                    merged_count += 1
        if merged_count > 0:
            print(
                "Merged "
                + str(merged_count)
                + " building assignments from Imperator main setup into town_setups"
            )
    town_setups_dir = mod_root / "in_game" / "common" / "town_setups"
    town_setups_dir.mkdir(parents=True, exist_ok=True)
    town_setups_path = town_setups_dir / "ir_location_setups.txt"
    lines = [
        "# Auto-generated from Imperator buildings. Do not edit manually.",
        "",
    ]
    for setup_name in sorted(setup_definitions.keys()):
        lines.append(f"{setup_name} = {{")
        for building_key, level in sorted(setup_definitions[setup_name].items()):
            lines.append(f"    {building_key} = {level}")
        lines.append("}")
        lines.append("")
    town_setups_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print_written("file", town_setups_path)

    # --- Port Imperator location ranks (towns/cities) ---
    rank_lines = build_ir_location_ranks(
        id_to_key,
        set(pops_by_location.keys()),
        town_setup="italian_city",
        location_town_setups=location_building_setups,
    )
    rank_blocks = [(loc_key, [rank_lines[loc_key]]) for loc_key in sorted(rank_lines.keys())]
    write_blocks(
        iu_setup_start / "07_cities_and_buildings.txt",
        [("locations", rank_blocks)],
        encoding="utf-8",
    )

    # --- Build markets from IR roads + capitals ---
    markets_dst = mod_root / "main_menu" / "setup" / "start" / "03_markets.txt"
    country_locations = extract_ir_country_locations()
    country_capitals = _ir_country_capitals()
    markets = _build_market_keys(
        id_to_key,
        location_keys,
        default_map,
        location_to_region,
        country_locations,
        country_capitals,
        top_capitals=35,
        max_markets=35,
    )
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
        ir_path("map_data/provinces.png"): iu_map_data / "locations.png",
        ir_path("map_data/rivers.png"): iu_map_data / "rivers.png",
    }
    for src, dst in map_files.items():
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print_written("file", dst)

    # --- Keep Imperator dimensions and sync world extents defines ---
    locations_img = iu_map_data / "locations.png"
    locations_size = _png_size(locations_img)
    if locations_size:
        defines_override = (
            mod_root / "loading_screen" / "common" / "defines" / "ir_defines.txt"
        )
        _sync_world_extents(defines_override, locations_size)

    # Compare against EU5 base dimensions for visibility only.
    eu5_locations_png = eu5_game / "in_game" / "map_data" / "locations.png"
    target_size = _png_size(eu5_locations_png) if eu5_locations_png.exists() else None
    if target_size and locations_size and locations_size != target_size:
        # Keep Imperator rivers.png even when dimensions differ.
        # Do not replace with EU5 base rivers; mod must use I:R river layout.
        rivers_img = iu_map_data / "rivers.png"
        rivers_size = _png_size(rivers_img)
        if rivers_size and rivers_size != locations_size:
            print(
                f"Warning: rivers.png size {rivers_size} differs from locations.png "
                f"{locations_size}; keeping Imperator rivers.png"
            )
