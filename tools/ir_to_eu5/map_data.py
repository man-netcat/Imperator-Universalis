import csv
import hashlib
import math
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import pyradox.datatype as _pydt
from PIL import Image

from .extract_data import extract_ir_country_locations, parse_tree, read_localisation_file
from .location_neighbors import (
    DEFAULT_LOCATION_NEIGHBORS_PATH,
    load_location_neighbors,
)
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
from .data import (
    IR_BUILDING_MAP_OVERRIDES,
    IR_CLIMATE_TO_EU5_CLIMATE,
    IR_GOODS_TO_EU5_GOODS,
    IR_GOODS_WEIGHT_OVERRIDES,
    IR_GROUP_TOWN_SETUPS,
    IR_TERRAIN_TO_TOPOGRAPHY,
    IR_TERRAIN_TO_VEGETATION,
    MEDITERRANEAN_COASTAL_AREAS,
    PORT_SEAZONE_OVERRIDES,
    continent_map,
    superregion_map,
)
from .output_text import print_written, write_blocks



def to_province_key(key: str) -> str:
    if not isinstance(key, str):
        return key
    text = key.strip()
    if text.endswith("_province"):
        return text
    if text.endswith("_area"):
        return f"{text[:-5]}_province"
    return f"{text}_province"


def to_area_key(key: str) -> str:
    if not isinstance(key, str):
        return key
    text = key.strip()
    if text.endswith("_area"):
        return text
    if text.endswith("_region"):
        return f"{text[:-7]}_area"
    return f"{text}_area"


def to_region_key(key: str) -> str:
    if not isinstance(key, str):
        return key
    text = key.strip()
    if text.endswith("_region"):
        return text
    if text.endswith("_area"):
        return f"{text[:-5]}_region"
    return f"{text}_region"


def normalize_superregion_map(raw: dict) -> dict:
    normalized: dict = {}
    for subcontinent, superregions in raw.items():
        norm_superregions: dict = {}
        for superregion, regions in superregions.items():
            norm_superregion = to_region_key(superregion)
            norm_regions = [to_area_key(region) for region in regions]
            norm_superregions[norm_superregion] = norm_regions
        normalized[subcontinent] = norm_superregions
    return normalized


# Default value for coastal locations if no I:R factors are found.
DEFAULT_COASTAL_NATURAL_HARBOR_SUITABILITY = "0.00"

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


def _write_text_file(path: Path, text: str, encoding: str = "utf-8-sig") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    print_written("file", path)


def _write_assignment_block(
    path: Path, block_name: str, lines: list[str], encoding: str = "utf-8"
) -> None:
    _write_text_file(path, f"{block_name} = {{\n" + "\n".join(lines) + "\n}\n", encoding=encoding)


def _copy_file_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print_written("file", dst)


def _render_map_object_locator(name: str, layer: str) -> str:
    return (
        "game_object_locator={\n"
        f"\tname=\"{name}\"\n"
        "\tclamp_to_water_level=no\n"
        "\trender_under_water=no\n"
        "\tgenerated_content=no\n"
        f"\tlayer=\"{layer}\"\n"
        "\tinstances={}\n"
        "}\n"
    )


def _write_locations_block(
    out_path: Path,
    location_blocks: list[tuple[str, list[str]]],
    *,
    encoding: str = "utf-8",
) -> None:
    write_blocks(out_path, [("locations", location_blocks)], encoding=encoding)


def _filter_tree_entries_by_tags(
    tree: _pydt.Tree,
    allowed_tags: set[str],
    *,
    root_key: str | None = None,
) -> _pydt.Tree:
    if root_key is None:
        source = tree
        container_key = None
    else:
        source = tree[root_key] if root_key in tree else _pydt.Tree()
        container_key = root_key

    filtered_source = _pydt.Tree()
    for tag, data in source.items():
        if tag in allowed_tags:
            filtered_source[tag] = data

    if container_key is None:
        return filtered_source

    out = _pydt.Tree()
    out[container_key] = filtered_source
    return out


def _write_town_setups_file(out_path: Path, setup_definitions: dict[str, dict[str, int]]) -> None:
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
    _write_text_file(out_path, "\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_map_object_override_files() -> None:
    locators_dir = mod_root / "in_game" / "gfx" / "map" / "map_objects"
    locators_dir.mkdir(parents=True, exist_ok=True)
    locator_defs = {
        "generated_map_object_locators_city.txt": ("city", "cities_layer"),
        "generated_map_object_locators_combat.txt": ("combat", "unit_layer"),
        "generated_map_object_locators_unit_stack.txt": ("unit_stack", "unit_layer"),
        "generated_map_object_locators_vfx.txt": ("vfx", "vfx_layer"),
    }
    for filename, (name, layer) in locator_defs.items():
        _write_text_file(
            locators_dir / filename,
            _render_map_object_locator(name, layer),
            encoding="utf-8",
        )

    locators_override_path = (
        mod_root / "in_game" / "gfx" / "map" / "locators_override" / "locators_override.txt"
    )
    _write_text_file(
        locators_override_path,
        "# Auto-generated empty override to avoid invalid province references.\n",
        encoding="utf-8",
    )

    map_objects_dir = mod_root / "in_game" / "gfx" / "map" / "map_objects"
    map_objects_dir.mkdir(parents=True, exist_ok=True)
    dynamic_objects_path = map_objects_dir / "dynamic_game_objects.txt"
    _write_text_file(
        dynamic_objects_path,
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

    volcano_locator = map_objects_dir / "generated_map_object_locators_volcano_eruption.txt"
    _write_text_file(
        volcano_locator,
        _render_map_object_locator("volcano_eruption", "vfx_layer"),
        encoding="utf-8",
    )


def _filter_exploration_preferences_text(
    lines: list[str],
    *,
    area_keys: set[str],
    region_keys: set[str],
    continent_keys: set[str],
    subcontinent_keys: set[str],
) -> list[str]:
    allowed_by_field = {
        "area": area_keys,
        "region": region_keys,
        "continent": continent_keys,
        "sub_continent": subcontinent_keys,
    }
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        keep = True
        for field, allowed in allowed_by_field.items():
            if stripped.startswith(field) and "=" in stripped:
                _, value = stripped.split("=", 1)
                key = value.strip().split()[0]
                if key not in allowed:
                    keep = False
                break
        if keep:
            out.append(line)
    return out


def _patch_script_file_references(
    src_path: Path,
    dst_path: Path,
    *,
    location_keys: set[str],
    region_keys: set[str],
    continent_keys: set[str],
    subcontinent_keys: set[str],
    fallback_location: str | None,
    fallback_region: str | None,
    fallback_continent: str | None,
    fallback_subcontinent: str | None,
) -> None:
    location_re = re.compile(r"(\blocation_key\s*=\s*)([A-Za-z0-9_:]+)")
    region_re = re.compile(r"(\bregion\s*=\s*)([A-Za-z0-9_:]+)")
    region_key_re = re.compile(r"(\bregion_key\s*=\s*)([A-Za-z0-9_:]+)")
    subcontinent_re = re.compile(r"(\bsub_continent\s*=\s*)([A-Za-z0-9_:]+)")
    continent_re = re.compile(r"(\bcontinent\s*=\s*)([A-Za-z0-9_:]+)")

    def _resolve_known_or_fallback(
        key: str, known: set[str], fallback: str | None
    ) -> str:
        if key in known:
            return key
        if ":" in key:
            tail = key.split(":")[-1]
            if tail in known:
                return tail
        return fallback or key

    changed = False
    lines: list[str] = []
    for line in src_path.read_text(encoding="utf-8-sig").splitlines():
        original = line
        if fallback_location:

            def repl_loc(m):
                key = m.group(2)
                return m.group(1) + (key if key in location_keys else fallback_location)

            line = location_re.sub(repl_loc, line)
        if fallback_region:

            def repl_region(m):
                return m.group(1) + _resolve_known_or_fallback(
                    m.group(2), region_keys, fallback_region
                )

            line = region_re.sub(repl_region, line)
            line = region_key_re.sub(repl_region, line)
        if fallback_subcontinent:

            def repl_subcontinent(m):
                return m.group(1) + _resolve_known_or_fallback(
                    m.group(2), subcontinent_keys, fallback_subcontinent
                )

            line = subcontinent_re.sub(repl_subcontinent, line)
        if fallback_continent:

            def repl_continent(m):
                return m.group(1) + _resolve_known_or_fallback(
                    m.group(2), continent_keys, fallback_continent
                )

            line = continent_re.sub(repl_continent, line)
        if line != original:
            changed = True
        lines.append(line)

    if changed:
        _write_text_file(dst_path, "\n".join(lines) + "\n", encoding="utf-8-sig")


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


def parse_ports(
    id_to_key: dict[int, str],
    sea_zones: set[str] | None = None,
) -> list[dict]:
    """Parse ports.csv and infer missing coastal ports from coastline adjacency.

    When sea_zones is provided, only sea-zone ports are kept and additional
    coastal ports are inferred from location neighbor geometry.
    """
    file = ir_path("map_data/ports.csv")
    ports: list[dict] = []
    seen_lands: set[str] = set()

    sea_zone_set = set(sea_zones or set())
    neighbor_payload = load_location_neighbors() if sea_zone_set else {}
    neighbors = neighbor_payload.get("neighbors", {}) if isinstance(neighbor_payload, dict) else {}
    centroids = neighbor_payload.get("centroids", {}) if isinstance(neighbor_payload, dict) else {}

    def _best_adjacent_sea(land_key: str) -> str | None:
        edge_map = neighbors.get(land_key, {}) if isinstance(neighbors, dict) else {}
        if not isinstance(edge_map, dict):
            return None
        candidates: list[tuple[int, str]] = []
        for neighbor_key, edge_weight in edge_map.items():
            if not isinstance(neighbor_key, str) or neighbor_key not in sea_zone_set:
                continue
            try:
                weight = int(edge_weight)
            except Exception:
                weight = 1
            candidates.append((max(1, weight), neighbor_key))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return candidates[0][1]

    if file.exists():
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

                if sea_zone_set:
                    if not isinstance(land_key, str) or land_key.startswith("UNKNOWN_"):
                        continue
                    best_sea = _best_adjacent_sea(land_key)
                    if not best_sea:
                        continue
                    if sea_key not in sea_zone_set:
                        sea_key = best_sea

                ports.append(
                    {
                        "LandProvince": land_key,
                        "SeaZone": sea_key,
                        "x": x,
                        "y": y,
                    }
                )
                if isinstance(land_key, str):
                    seen_lands.add(land_key)

    if sea_zone_set:
        location_keys = {
            key
            for key in id_to_key.values()
            if isinstance(key, str)
            and not key.startswith("UNKNOWN_")
            and key not in sea_zone_set
        }
        for land_key in sorted(location_keys):
            if land_key in seen_lands:
                continue
            sea_key = _best_adjacent_sea(land_key)
            if not sea_key:
                continue
            point = centroids.get(land_key)
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not isinstance(point[0], (int, float))
                or not isinstance(point[1], (int, float))
            ):
                continue
            ports.append(
                {
                    "LandProvince": land_key,
                    "SeaZone": sea_key,
                    "x": float(point[0]),
                    "y": float(point[1]),
                }
            )
            seen_lands.add(land_key)

        # Guarantee at least one attached port for each coastal sea zone.
        sea_port_counts: dict[str, int] = defaultdict(int)
        for row in ports:
            sea_key = row.get("SeaZone")
            if isinstance(sea_key, str) and sea_key in sea_zone_set:
                sea_port_counts[sea_key] += 1

        for sea_key in sorted(sea_zone_set):
            if sea_port_counts.get(sea_key, 0) > 0:
                continue
            edge_map = neighbors.get(sea_key, {}) if isinstance(neighbors, dict) else {}
            if not isinstance(edge_map, dict) or not edge_map:
                continue

            candidates: list[tuple[int, bool, str]] = []
            for land_key, edge_weight in edge_map.items():
                if not isinstance(land_key, str):
                    continue
                if land_key in sea_zone_set or land_key.startswith("UNKNOWN_"):
                    continue
                point = centroids.get(land_key)
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or not isinstance(point[0], (int, float))
                    or not isinstance(point[1], (int, float))
                ):
                    continue
                try:
                    weight = int(edge_weight)
                except Exception:
                    weight = 1
                # Prefer a land location that does not already have a port row.
                candidates.append((max(1, weight), land_key in seen_lands, land_key))

            if not candidates:
                continue

            candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
            chosen_land = candidates[0][2]
            point = centroids[chosen_land]
            ports.append(
                {
                    "LandProvince": chosen_land,
                    "SeaZone": sea_key,
                    "x": float(point[0]),
                    "y": float(point[1]),
                }
            )
            sea_port_counts[sea_key] += 1
            seen_lands.add(chosen_land)

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
        region_key = to_area_key(region)
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
            province_key = to_province_key(area)
            bucket = area_map.setdefault(province_key, [])
            for province in provinces:
                if province not in bucket:
                    bucket.append(province)
        if area_map:
            target = region_map.setdefault(region_key, {})
            for province_key, provinces in area_map.items():
                existing = target.setdefault(province_key, [])
                for province in provinces:
                    if province not in existing:
                        existing.append(province)

    return region_map


def dissolve_river_regions(
    regions: dict[str, dict[str, list[str]]],
) -> set[str]:
    """Remove standalone river regions and return their province keys."""
    moved_keys: set[str] = set()
    river_region_tags = [tag for tag in regions.keys() if "river_region" in tag]
    for region_tag in river_region_tags:
        area_map = regions.pop(region_tag, {})
        for provinces in area_map.values():
            if isinstance(provinces, list):
                moved_keys.update(provinces)
    return moved_keys


def assign_unmapped_water_to_regions(
    regions: dict[str, dict[str, list[str]]],
    location_to_region: dict[str, str],
    assigned_provinces: set[str],
    default_map: dict,
    named_locations: list[tuple[int, str, int, int, int, str]],
    location_keys: set[str],
    id_to_key: dict[int, str],
) -> dict[str, str]:
    """Assign sea/lake locations by proximity to existing land provinces."""
    if not isinstance(default_map, dict):
        return {}

    sea_zones = set(default_map.get("sea_zones", set()))
    lakes = set(default_map.get("lakes", set()))
    water_keys = (sea_zones | lakes) & set(location_keys)
    candidate_water = sorted(water_keys)
    if not candidate_water:
        return {}

    neighbor_payload = load_location_neighbors()
    if not neighbor_payload:
        print(
            "Warning: location neighbor cache missing; "
            f"run tools/build_location_neighbors.py to create {DEFAULT_LOCATION_NEIGHBORS_PATH.name}."
        )
        return {}

    neighbors = neighbor_payload.get("neighbors", {}) if isinstance(neighbor_payload, dict) else {}
    centroids = neighbor_payload.get("centroids", {}) if isinstance(neighbor_payload, dict) else {}
    non_land = _non_land_keys(default_map)

    land_to_area: dict[str, str] = {}
    land_to_region: dict[str, str] = {}
    existing_loc_to_area: dict[str, str] = {}
    area_to_region: dict[str, str] = {}
    for region_tag, area_map in regions.items():
        if not isinstance(area_map, dict):
            continue
        for area_tag, provinces in area_map.items():
            if not isinstance(provinces, list):
                continue
            area_to_region[area_tag] = region_tag
            for key in provinces:
                if not isinstance(key, str):
                    continue
                existing_loc_to_area.setdefault(key, area_tag)
                if key not in non_land:
                    land_to_area.setdefault(key, area_tag)
                    land_to_region.setdefault(key, region_tag)

    def _to_int_weight(value) -> int:
        try:
            return int(value)
        except Exception:
            return 1

    province_scores: dict[str, Counter[str]] = {key: Counter() for key in candidate_water}

    # Ports give strong location-specific hints.
    for row in parse_ports(id_to_key, sea_zones=sea_zones):
        water_key = row.get("SeaZone")
        land_key = row.get("LandProvince")
        if not isinstance(water_key, str) or water_key not in water_keys:
            continue
        if not isinstance(land_key, str) or land_key not in land_to_area:
            continue
        province_scores[water_key][land_key] += 8

    # Border-length neighbors from provinces map.
    for water_key in candidate_water:
        edge_map = neighbors.get(water_key, {}) if isinstance(neighbors, dict) else {}
        if not isinstance(edge_map, dict):
            continue
        scores = province_scores[water_key]
        for neighbor_key, edge_weight in edge_map.items():
            if not isinstance(neighbor_key, str) or neighbor_key not in land_to_area:
                continue
            scores[neighbor_key] += max(1, _to_int_weight(edge_weight))

    # Explicit adjacency supplements province-level evidence.
    for row in parse_adjacencies(id_to_key, location_keys):
        a_key = row.get("From")
        b_key = row.get("To")
        if isinstance(a_key, str) and a_key in water_keys and isinstance(b_key, str) and b_key in land_to_area:
            province_scores[a_key][b_key] += 3
        if isinstance(b_key, str) and b_key in water_keys and isinstance(a_key, str) and a_key in land_to_area:
            province_scores[b_key][a_key] += 3

    assignments_land: dict[str, str] = {}
    for water_key in candidate_water:
        scores = province_scores.get(water_key)
        if scores:
            assignments_land[water_key] = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]

    # Centroid fallback to nearest land province centroid.
    missing = [key for key in candidate_water if key not in assignments_land]
    if missing and isinstance(centroids, dict):
        land_points: list[tuple[str, float, float]] = []
        for land_key in land_to_area.keys():
            point = centroids.get(land_key)
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not isinstance(point[0], (int, float))
                or not isinstance(point[1], (int, float))
            ):
                continue
            land_points.append((land_key, float(point[0]), float(point[1])))

        for water_key in missing:
            point = centroids.get(water_key)
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not isinstance(point[0], (int, float))
                or not isinstance(point[1], (int, float))
                or not land_points
            ):
                continue
            wx = float(point[0])
            wy = float(point[1])
            best_land = None
            best_dist = None
            for land_key, lx, ly in land_points:
                dist = (wx - lx) * (wx - lx) + (wy - ly) * (wy - ly)
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_land = land_key
            if best_land:
                assignments_land[water_key] = best_land

    # Last-resort by nearest land province ID, or preserve prior area/region.
    missing = [key for key in candidate_water if key not in assignments_land]
    if missing:
        key_to_prov_id = {key: prov_id for prov_id, key, *_ in named_locations}
        land_candidates: list[tuple[int, str]] = []
        for land_key in land_to_area.keys():
            prov_id = key_to_prov_id.get(land_key)
            if prov_id is None:
                continue
            land_candidates.append((prov_id, land_key))

        for water_key in missing:
            prev_area = existing_loc_to_area.get(water_key)
            if prev_area and prev_area in area_to_region:
                # Keep deterministic ownership from existing area when present.
                prev_region = area_to_region[prev_area]
                for land_key, area_tag in land_to_area.items():
                    if area_tag == prev_area and land_to_region.get(land_key) == prev_region:
                        assignments_land[water_key] = land_key
                        break
                if water_key in assignments_land:
                    continue

            prov_id = key_to_prov_id.get(water_key)
            if prov_id is None or not land_candidates:
                continue
            nearest_land = sorted(
                land_candidates,
                key=lambda item: (abs(item[0] - prov_id), item[1]),
            )[0][1]
            assignments_land[water_key] = nearest_land

    # Remove all water tiles from existing (land) areas.
    # They are re-added as dedicated water-only areas inside proximate regions.
    for area_map in regions.values():
        for area_tag, provinces in area_map.items():
            if isinstance(provinces, list):
                area_map[area_tag] = [p for p in provinces if p not in water_keys]

    region_to_sea: dict[str, list[str]] = defaultdict(list)
    region_to_lakes: dict[str, list[str]] = defaultdict(list)

    for water_key in candidate_water:
        land_key = assignments_land.get(water_key)
        if not land_key:
            continue
        region_tag = land_to_region.get(land_key)
        if not region_tag:
            continue

        location_to_region[water_key] = region_tag
        if water_key in lakes:
            region_to_lakes[region_tag].append(water_key)
        else:
            region_to_sea[region_tag].append(water_key)

    def _unique_area_tag(area_map: dict[str, list[str]], preferred: str) -> str:
        if preferred not in area_map:
            return preferred
        i = 1
        while f"{preferred}_{i:02d}" in area_map:
            i += 1
        return f"{preferred}_{i:02d}"

    for region_tag, keys in sorted(region_to_sea.items()):
        if not keys:
            continue
        area_map = regions.setdefault(region_tag, {})
        base = region_tag[: -len('_area')] if region_tag.endswith('_area') else region_tag
        preferred = f"{base}_coastal_sea_province"
        area_tag = _unique_area_tag(area_map, preferred)
        area_map[area_tag] = sorted(set(keys))

    for region_tag, keys in sorted(region_to_lakes.items()):
        if not keys:
            continue
        area_map = regions.setdefault(region_tag, {})
        base = region_tag[: -len('_area')] if region_tag.endswith('_area') else region_tag
        preferred = f"{base}_coastal_lakes_province"
        area_tag = _unique_area_tag(area_map, preferred)
        area_map[area_tag] = sorted(set(keys))

    return {
        key: location_to_region[key]
        for key in candidate_water
        if key in location_to_region
    }



def assign_unmapped_non_ownable_to_regions(
    regions: dict[str, dict[str, list[str]]],
    location_to_region: dict[str, str],
    assigned_provinces: set[str],
    default_map: dict,
    named_locations: list[tuple[int, str, int, int, int, str]],
    location_keys: set[str],
) -> dict[str, str]:
    """Assign non-ownable land provinces into nearby existing regions."""
    if not isinstance(default_map, dict):
        return {}

    sea_zones = set(default_map.get("sea_zones", set()))
    lakes = set(default_map.get("lakes", set()))
    rivers = set(default_map.get("river_provinces", set()))

    target_keys = set()
    for key in (
        "uninhabitable",
        "non_ownable",
        "impassable_terrain",
        "wasteland",
        "impassable_mountains",
    ):
        target_keys.update(default_map.get(key, set()))
    target_keys = (target_keys & set(location_keys)) - sea_zones - lakes - rivers

    unassigned = sorted(target_keys - assigned_provinces)
    if not unassigned:
        return {}

    neighbor_payload = load_location_neighbors()
    if not neighbor_payload:
        print(
            "Warning: location neighbor cache missing; "
            f"run tools/build_location_neighbors.py to create {DEFAULT_LOCATION_NEIGHBORS_PATH.name}."
        )
        return {}

    neighbors = neighbor_payload.get("neighbors", {}) if isinstance(neighbor_payload, dict) else {}
    assignments: dict[str, str] = {}

    for key in unassigned:
        edge_map = neighbors.get(key, {}) if isinstance(neighbors, dict) else {}
        if not isinstance(edge_map, dict):
            continue
        scores: Counter[str] = Counter()
        for neighbor_key, edge_weight in edge_map.items():
            if not isinstance(neighbor_key, str):
                continue
            region_tag = location_to_region.get(neighbor_key)
            if not region_tag:
                continue
            try:
                weight = int(edge_weight)
            except Exception:
                weight = 1
            scores[region_tag] += max(1, weight)
        if scores:
            assignments[key] = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]

    # Centroid fallback for isolated/sparse-border non-ownable provinces.
    missing = [key for key in unassigned if key not in assignments]
    if missing:
        centroids = neighbor_payload.get("centroids", {}) if isinstance(neighbor_payload, dict) else {}
        if isinstance(centroids, dict):
            non_land = _non_land_keys(default_map)
            region_centroids: dict[str, tuple[float, float]] = {}
            region_accum: dict[str, list[float]] = {}
            for loc_key, region_tag in location_to_region.items():
                if loc_key in non_land:
                    continue
                point = centroids.get(loc_key)
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or not isinstance(point[0], (int, float))
                    or not isinstance(point[1], (int, float))
                ):
                    continue
                if region_tag not in region_accum:
                    region_accum[region_tag] = [0.0, 0.0, 0.0]
                region_accum[region_tag][0] += float(point[0])
                region_accum[region_tag][1] += float(point[1])
                region_accum[region_tag][2] += 1.0
            for region_tag, (sx, sy, n) in region_accum.items():
                if n > 0:
                    region_centroids[region_tag] = (sx / n, sy / n)

            for key in missing:
                point = centroids.get(key)
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or not isinstance(point[0], (int, float))
                    or not isinstance(point[1], (int, float))
                ):
                    continue
                x = float(point[0])
                y = float(point[1])
                best_region = None
                best_dist = None
                for region_tag, (rx, ry) in region_centroids.items():
                    dist = (x - rx) * (x - rx) + (y - ry) * (y - ry)
                    if best_dist is None or dist < best_dist:
                        best_dist = dist
                        best_region = region_tag
                if best_region:
                    assignments[key] = best_region

    # Last-resort assignment by nearest province ID with known region.
    missing = [key for key in unassigned if key not in assignments]
    if missing:
        key_to_prov_id = {key: prov_id for prov_id, key, *_ in named_locations}
        candidates: list[tuple[int, str]] = []
        for loc_key, region_tag in location_to_region.items():
            prov_id = key_to_prov_id.get(loc_key)
            if prov_id is None:
                continue
            candidates.append((prov_id, region_tag))
        for key in missing:
            prov_id = key_to_prov_id.get(key)
            if prov_id is None or not candidates:
                continue
            nearest_region = sorted(
                candidates,
                key=lambda item: (abs(item[0] - prov_id), item[1]),
            )[0][1]
            assignments[key] = nearest_region

    def to_int_weight(value) -> int:
        try:
            return int(value)
        except Exception:
            return 1

    # Insert non-ownables directly into existing areas by strongest border sharing.
    for loc_key, region_tag in sorted(assignments.items()):
        area_map = regions.setdefault(region_tag, {})
        if not area_map:
            base_area = f"{region_tag}_province_generated"
            area_map[base_area] = [loc_key]
            location_to_region.setdefault(loc_key, region_tag)
            continue

        edge_map = neighbors.get(loc_key, {}) if isinstance(neighbors, dict) else {}
        best_area = None
        best_score = -1
        best_len = -1

        for area_tag, provinces in area_map.items():
            if not isinstance(provinces, list):
                continue
            score = 0
            if isinstance(edge_map, dict):
                province_set = set(provinces)
                for neighbor_key, edge_weight in edge_map.items():
                    if neighbor_key in province_set:
                        score += max(1, to_int_weight(edge_weight))
            plen = len(provinces)
            if score > best_score or (score == best_score and plen > best_len):
                best_area = area_tag
                best_score = score
                best_len = plen

        if not best_area:
            best_area = sorted(area_map.keys())[0]
        target = area_map.get(best_area)
        if isinstance(target, list) and loc_key not in target:
            target.append(loc_key)
        location_to_region.setdefault(loc_key, region_tag)

    return assignments


def assign_unmapped_rivers_to_regions(
    regions: dict[str, dict[str, list[str]]],
    location_to_region: dict[str, str],
    assigned_provinces: set[str],
    default_map: dict,
    named_locations: list[tuple[int, str, int, int, int, str]],
    location_keys: set[str],
    extra_river_keys: set[str] | None = None,
) -> dict[str, str]:
    """Assign river provinces by proximity to existing land provinces."""
    if not isinstance(default_map, dict):
        return {}

    sea_zones = set(default_map.get("sea_zones", set()))
    lakes = set(default_map.get("lakes", set()))
    river_keys = set(default_map.get("river_provinces", set())) & set(location_keys)
    if extra_river_keys:
        river_keys.update(set(extra_river_keys) & set(location_keys))
    river_keys = river_keys - sea_zones - lakes
    candidate_rivers = sorted(river_keys)
    if not candidate_rivers:
        return {}

    neighbor_payload = load_location_neighbors()
    if not neighbor_payload:
        print(
            "Warning: location neighbor cache missing; "
            f"run tools/build_location_neighbors.py to create {DEFAULT_LOCATION_NEIGHBORS_PATH.name}."
        )
        return {}

    neighbors = neighbor_payload.get("neighbors", {}) if isinstance(neighbor_payload, dict) else {}
    centroids = neighbor_payload.get("centroids", {}) if isinstance(neighbor_payload, dict) else {}
    non_land = _non_land_keys(default_map)

    land_to_area: dict[str, str] = {}
    land_to_region: dict[str, str] = {}
    existing_loc_to_area: dict[str, str] = {}
    area_to_region: dict[str, str] = {}
    for region_tag, area_map in regions.items():
        if not isinstance(area_map, dict):
            continue
        for area_tag, provinces in area_map.items():
            if not isinstance(provinces, list):
                continue
            area_to_region[area_tag] = region_tag
            for key in provinces:
                if not isinstance(key, str):
                    continue
                existing_loc_to_area.setdefault(key, area_tag)
                if key not in non_land:
                    land_to_area.setdefault(key, area_tag)
                    land_to_region.setdefault(key, region_tag)

    def _to_int_weight(value) -> int:
        try:
            return int(value)
        except Exception:
            return 1

    province_scores: dict[str, Counter[str]] = {key: Counter() for key in candidate_rivers}

    # Border-strength to neighboring land provinces.
    for river_key in candidate_rivers:
        edge_map = neighbors.get(river_key, {}) if isinstance(neighbors, dict) else {}
        if not isinstance(edge_map, dict):
            continue
        scores = province_scores[river_key]
        for neighbor_key, edge_weight in edge_map.items():
            if not isinstance(neighbor_key, str) or neighbor_key not in land_to_area:
                continue
            scores[neighbor_key] += max(1, _to_int_weight(edge_weight))

    assignments_land: dict[str, str] = {}
    for river_key in candidate_rivers:
        scores = province_scores.get(river_key)
        if scores:
            assignments_land[river_key] = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]

    # Centroid fallback to nearest land province centroid.
    missing = [key for key in candidate_rivers if key not in assignments_land]
    if missing and isinstance(centroids, dict):
        land_points: list[tuple[str, float, float]] = []
        for land_key in land_to_area.keys():
            point = centroids.get(land_key)
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not isinstance(point[0], (int, float))
                or not isinstance(point[1], (int, float))
            ):
                continue
            land_points.append((land_key, float(point[0]), float(point[1])))

        for river_key in missing:
            point = centroids.get(river_key)
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not isinstance(point[0], (int, float))
                or not isinstance(point[1], (int, float))
                or not land_points
            ):
                continue
            rx = float(point[0])
            ry = float(point[1])
            best_land = None
            best_dist = None
            for land_key, lx, ly in land_points:
                dist = (rx - lx) * (rx - lx) + (ry - ly) * (ry - ly)
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_land = land_key
            if best_land:
                assignments_land[river_key] = best_land

    # Last-resort by nearest land province ID, or preserve prior area/region.
    missing = [key for key in candidate_rivers if key not in assignments_land]
    if missing:
        key_to_prov_id = {key: prov_id for prov_id, key, *_ in named_locations}
        land_candidates: list[tuple[int, str]] = []
        for land_key in land_to_area.keys():
            prov_id = key_to_prov_id.get(land_key)
            if prov_id is None:
                continue
            land_candidates.append((prov_id, land_key))

        for river_key in missing:
            prev_area = existing_loc_to_area.get(river_key)
            if prev_area and prev_area in area_to_region:
                prev_region = area_to_region[prev_area]
                for land_key, area_tag in land_to_area.items():
                    if area_tag == prev_area and land_to_region.get(land_key) == prev_region:
                        assignments_land[river_key] = land_key
                        break
                if river_key in assignments_land:
                    continue

            prov_id = key_to_prov_id.get(river_key)
            if prov_id is None or not land_candidates:
                continue
            nearest_land = sorted(
                land_candidates,
                key=lambda item: (abs(item[0] - prov_id), item[1]),
            )[0][1]
            assignments_land[river_key] = nearest_land

    # Remove all rivers from areas, then reinsert via chosen land province owner.
    for area_map in regions.values():
        for area_tag, provinces in area_map.items():
            if isinstance(provinces, list):
                area_map[area_tag] = [p for p in provinces if p not in river_keys]

    for river_key in candidate_rivers:
        land_key = assignments_land.get(river_key)
        if not land_key:
            continue
        area_tag = land_to_area.get(land_key)
        region_tag = land_to_region.get(land_key)
        if not area_tag or not region_tag:
            continue
        area_map = regions.setdefault(region_tag, {})
        target = area_map.setdefault(area_tag, [])
        if river_key not in target:
            target.append(river_key)
        location_to_region[river_key] = region_tag

    return {
        key: location_to_region[key]
        for key in candidate_rivers
        if key in location_to_region
    }



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
    # Warn if a region is not represented in the superregion map.
    # Missing regions should be fixed in data.py rather than routed into synthetic hierarchy nodes.
    missing_regions = {
        region
        for region, area_map in region_map.items()
        if region not in seen_regions and region_has_locations(area_map)
    }
    if missing_regions:
        print(
            "Warning: unmapped regions in superregion hierarchy: "
            + ", ".join(sorted(missing_regions))
        )

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


def _ir_countries_tree() -> _pydt.Tree:
    return parse_tree(ir_default)["country"]["countries"]


def _ir_capital_ids() -> list[int]:
    countries = _ir_countries_tree()
    return [int(data["capital"]) for data in countries.values() if data["capital"] is not None]


def _ir_country_capitals() -> dict[str, int]:
    countries = _ir_countries_tree()
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
        "impassable_mountains",
        "impassable_terrain",
        "uninhabitable",
        "wasteland",
        "non_ownable",
    ):
        excluded.update(default_map.get(key, set()))
    return excluded


def _infer_non_ownable_topography_vegetation(key: str, climate: str) -> tuple[str, str]:
    """Fallback terrain mapping for non_ownable corridors lacking I:R terrain data."""
    key_l = key.lower()
    is_pass = ("pass" in key_l) or ("gates" in key_l) or key_l in {"portae"}
    is_desert = (
        ("desert" in key_l)
        or ("kavir" in key_l)
        or ("taklamakan" in key_l)
        or key_l.startswith("lut_")
        or key_l.startswith("maru_")
    )

    if "jungle" in key_l:
        return "flatland", "jungle"
    if is_pass:
        if climate in {"arid", "arctic", "cold_arid"}:
            return "mountains", "sparse"
        return "mountains", "forest"
    if is_desert or climate == "arid":
        return "flatland", "desert"
    if climate in {"arctic", "cold_arid"}:
        return "flatland", "sparse"
    return "flatland", "forest"


def _default_vegetation_for_topography(topography: str, climate: str) -> str:
    t = (topography or "").strip().lower()
    c = (climate or "").strip().lower()
    if t in {"ocean", "inland_sea", "lakes", "mountain_wasteland", "mountains"}:
        return "sparse"
    if t in {"wetlands", "hills"}:
        return "woods"
    if t == "jungle":
        return "jungle"
    if t == "desert" or c == "arid":
        return "desert"
    if c in {"arctic", "cold_arid"}:
        return "sparse"
    return "grasslands"


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


def _eu5_allowed_buildings_from_ir() -> set[str]:
    allowed: set[str] = set()
    for mapped_key in build_ir_building_mapping().values():
        key_str = str(mapped_key).strip()
        if key_str:
            allowed.add(key_str)
    return allowed


FORT_LIKE_BUILDINGS = {
    "castle",
    "stockade",
    "provincial_garrison",
    "fortress_granary",
}

# 304 BC building tuning profile: temper high EU5 template levels for the much earlier start.
BUILDING_LEVEL_SCALE_304BC = {
    "castle": 0.22,
    "stockade": 0.25,
    "dock": 0.55,
    "granary": 0.70,
    "marketplace": 0.68,
    "mason": 0.64,
    "temple": 0.70,
    "slave_market": 0.62,
}

BUILDING_MAX_LEVEL_304BC = {
    "castle": 1,
    "stockade": 1,
    "dock": 1,
    "temple": 1,
    "granary": 2,
    "marketplace": 2,
    "mason": 2,
    "slave_market": 2,
}

# Extra cap scaling by building type after global map-scope scaling.
BUILDING_CAP_SCALE_304BC = {
    "castle": 0.62,
    "stockade": 0.60,
    "dock": 0.75,
    "granary": 0.62,
    "marketplace": 0.90,
    "mason": 0.55,
    "temple": 0.94,
    "slave_market": 0.63,
}

# Additional 304 BC downscaling for direct fort assignments written to 07_cities_and_buildings.txt.
DIRECT_FORT_SCALE_304BC = {
    "castle": 0.18,
    "stockade": 0.10,
}

# Prominent 304 BC fortified centers (manual-only assignment).
PROMINENT_CASTLE_LOCATIONS_304BC = (
    "alexandria",
    "carthago",
    "roma",
    "pella_0",
    "lysimacheia",
    "antigoneia",
    "athens",
    "thebes",
    "korinthos",
    "amphipolis",
    "chalcis",
    "byzantion",
    "jerusalem",
    "gaza",
    "pelusium",
    "damascus",
    "tarsus",
    "tyrus",
    "pergamon",
    "ephesos",
    "miletos",
    "halikarnassos",
    "persepolis",
    "ecbatana",
    "bactra",
    "babylon_1",
    "seleucia_magna",
    "shushan",
    "uruk",
    "pataliputra",
    "taxila",
    "sidon",
    "sparta",
    "rhodos",
    "syracusae",
    "sardis",
    "massalia",
)

PROMINENT_STOCKADE_LOCATIONS_304BC = (
    "memphis",
    "capua",
    "zeugma",
    "nisibis_0",
    "petra",
    "arbela",
    "charax",
    "sinope",
    "amisos",
    "ostia",
    "messana",
    "neapolis",
    "argos",
    "kyrene",
    "madurai",
    "kajangala",
)

CASTLE_RATIONALE_304BC = {
    "alexandria": "Ptolemaic capital and premier naval base of Egypt.",
    "carthago": "Carthaginian imperial capital and western Mediterranean war hub.",
    "roma": "Roman political and military center in central Italy.",
    "pella_0": "Macedonian royal center and staging ground in Greece.",
    "lysimacheia": "Thracian choke-point controlling Hellespont approaches.",
    "antigoneia": "Early Seleucid Syrian stronghold in the successor wars context.",
    "athens": "Strategic Aegean political and naval stronghold.",
    "thebes": "Boeotian strategic center restored in the late 4th century BC.",
    "korinthos": "Isthmus fortress-city controlling Peloponnesian land access.",
    "amphipolis": "Macedonian treasury and military base on the Strymon corridor.",
    "chalcis": "Euboean strait choke-point controlling central Greek sea lanes.",
    "byzantion": "Bosporus gate between Aegean and Black Sea.",
    "jerusalem": "Levantine hill stronghold and regional command node.",
    "gaza": "Egypt-Levant gateway fortress controlling the southern coastal corridor.",
    "pelusium": "Eastern gate of Egypt and primary Sinai invasion choke point.",
    "damascus": "Major inland Syrian capital and operational hub of southern Syria.",
    "tarsus": "Strategic Cilician center controlling passes between Anatolia and Syria.",
    "tyrus": "Primary Levantine fortress-port with island-city defenses.",
    "pergamon": "Naturally defensible acropolis fortress in western Anatolia.",
    "ephesos": "Major fortified Ionian harbor with regional military value.",
    "miletos": "Walled Ionian city anchoring Maeander approaches.",
    "halikarnassos": "Strongly fortified Carian center and major coastal bastion.",
    "persepolis": "Major Persian heartland fortress-administration center.",
    "ecbatana": "Median highland capital and Iranian interior military center.",
    "bactra": "Bactrian regional capital anchoring eastern frontier power.",
    "babylon_1": "Mesopotamian imperial center controlling central river corridor.",
    "seleucia_magna": "Seleucid royal capital on the Tigris from the early 3rd century BC.",
    "shushan": "Seleucid administrative capital in Susiana linking Mesopotamia and Iran.",
    "uruk": "Major enduring walled city of southern Mesopotamia.",
    "pataliputra": "Mauryan imperial capital and principal recruitment base.",
    "taxila": "Northwestern Indian hinge on transregional military routes.",
    "sidon": "Phoenician coastal stronghold with strategic depth.",
    "sparta": "Peloponnesian military center with persistent strategic value.",
    "rhodos": "Fortified island naval bastion in the southeastern Aegean.",
    "syracusae": "Dominant Sicilian fortress-city and fleet base.",
    "sardis": "Western Anatolian inland stronghold guarding Lydia-Phrygia corridor.",
    "massalia": "Western Greek fortified entrepot on Gallic frontier seas.",
}

STOCKADE_RATIONALE_304BC = {
    "memphis": "Major Nile military-administrative center secondary to Alexandria.",
    "capua": "Regional Campanian military center beneath the primary Roman core.",
    "zeugma": "Major Euphrates crossing point for army movement.",
    "nisibis_0": "Upper Mesopotamian frontier fortress on east-west route.",
    "petra": "Arabian caravan stronghold controlling desert communications.",
    "arbela": "Upper Mesopotamian operational base east of Tigris.",
    "charax": "Head-of-Gulf junction and river-mouth defense.",
    "sinope": "Black Sea promontory fort-port with regional projection.",
    "amisos": "Northern Anatolian military harbor and Pontic support base.",
    "ostia": "Rome's principal maritime gate requiring military garrisoning.",
    "messana": "Strait of Messina chokepoint for Italy-Sicily movement.",
    "neapolis": "Tyrrhenian military harbor supporting central Italian operations.",
    "argos": "Argolid fort node supporting Peloponnesian defense in depth.",
    "kyrene": "Cyrenaican regional military center between Egypt and Maghreb routes.",
    "madurai": "Deep south Indian military center in Tamil region.",
    "kajangala": "Mauryan eastern military corridor control point.",
}


def _tune_building_level_304bc(building_key: str, level) -> int:
    try:
        parsed = int(level)
    except Exception:
        try:
            parsed = int(str(level).strip())
        except Exception:
            parsed = 0
    if parsed <= 0:
        return 0

    key = str(building_key)
    scaled = int(round(parsed * float(BUILDING_LEVEL_SCALE_304BC.get(key, 0.65))))
    if scaled <= 0:
        scaled = 1

    max_level = int(BUILDING_MAX_LEVEL_304BC.get(key, 2))
    return max(0, min(max_level, scaled))


def _tune_template_vector_304bc(buildings: dict[str, int]) -> dict[str, int]:
    tuned: dict[str, int] = {}
    for building_key, level in (buildings or {}).items():
        tuned_level = _tune_building_level_304bc(str(building_key), level)
        if tuned_level > 0:
            tuned[str(building_key)] = tuned_level
    return tuned


FOOD_GOODS = {
    "wheat",
    "maize",
    "rice",
    "millet",
    "legumes",
    "potato",
    "livestock",
    "olives",
    "fruit",
    "wool",
}
FOREST_GOODS = {"wild_game", "fur", "beeswax", "lumber"}
FOREST_VEGETATION = {"forest", "woods", "jungle"}
WATER_TOPOGRAPHIES = {"ocean", "inland_sea", "lakes", "mountain_wasteland"}


def _classify_rural_building(
    raw_material: str | None,
    vegetation: str | None,
    is_coastal: bool,
) -> str:
    if raw_material == "fish" and is_coastal:
        return "fishing_village"
    if raw_material in FOOD_GOODS:
        return "farming_village"
    if raw_material in FOREST_GOODS or (vegetation in FOREST_VEGETATION):
        return "forest_village"
    return "market_village"


def _build_country_prosperity(
    country_locations: dict[str, list[int]],
    id_to_key: dict[int, str],
    civilization_values: dict[str, float],
) -> dict[str, float]:
    prosperity: dict[str, float] = {}
    for tag, prov_ids in country_locations.items():
        values: list[float] = []
        for prov_id in prov_ids:
            loc_key = id_to_key.get(prov_id)
            if not loc_key:
                continue
            civ = civilization_values.get(loc_key)
            if civ is None:
                continue
            values.append(float(civ))
        avg = sum(values) / len(values) if values else 0.0
        prosperity[tag] = max(0.0, min(avg / 100.0, 1.0))
    return prosperity


_EU5_RURAL_DISTRIBUTION_CACHE: dict[str, float] | None = None


def _eu5_rural_distribution() -> dict[str, float]:
    global _EU5_RURAL_DISTRIBUTION_CACHE
    if _EU5_RURAL_DISTRIBUTION_CACHE is not None:
        return _EU5_RURAL_DISTRIBUTION_CACHE

    templates_path = eu5_game / "in_game" / "map_data" / "location_templates.txt"
    if not templates_path.exists():
        _EU5_RURAL_DISTRIBUTION_CACHE = {
            "fishing_village": 0.1,
            "farming_village": 0.5,
            "forest_village": 0.2,
            "market_village": 0.2,
        }
        return _EU5_RURAL_DISTRIBUTION_CACHE

    tree = parse_tree(templates_path)
    counts: dict[str, int] = defaultdict(int)
    for _, value in tree.items():
        block = value[0] if isinstance(value, list) and value else value
        if not isinstance(block, (_pydt.Tree, dict)):
            continue
        topography = block["topography"] if "topography" in block else None
        if isinstance(topography, list):
            topography = topography[0] if topography else None
        if isinstance(topography, str) and topography.strip().lower() in WATER_TOPOGRAPHIES:
            continue

        raw_material = block["raw_material"] if "raw_material" in block else None
        if isinstance(raw_material, list):
            raw_material = raw_material[0] if raw_material else None
        if isinstance(raw_material, str):
            raw_material = raw_material.strip()

        vegetation = block["vegetation"] if "vegetation" in block else None
        if isinstance(vegetation, list):
            vegetation = vegetation[0] if vegetation else None
        if isinstance(vegetation, str):
            vegetation = vegetation.strip()

        is_coastal = "natural_harbor_suitability" in block
        kind = _classify_rural_building(raw_material, vegetation, is_coastal)
        counts[kind] += 1

    total = sum(counts.values())
    if total <= 0:
        _EU5_RURAL_DISTRIBUTION_CACHE = {
            "fishing_village": 0.1,
            "farming_village": 0.5,
            "forest_village": 0.2,
            "market_village": 0.2,
        }
        return _EU5_RURAL_DISTRIBUTION_CACHE

    _EU5_RURAL_DISTRIBUTION_CACHE = {
        "fishing_village": counts.get("fishing_village", 0) / total,
        "farming_village": counts.get("farming_village", 0) / total,
        "forest_village": counts.get("forest_village", 0) / total,
        "market_village": counts.get("market_village", 0) / total,
    }
    return _EU5_RURAL_DISTRIBUTION_CACHE


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


def build_ir_civilization_values(id_to_key: dict[int, str]) -> dict[str, float]:
    province_files = _iter_ir_province_files()
    if not province_files:
        return {}

    result: dict[str, float] = {}
    for path in province_files:
        tree = parse_tree(path)
        for raw_id, data in tree.items():
            try:
                prov_id = int(raw_id)
            except Exception:
                continue
            loc_key = id_to_key.get(prov_id)
            if not loc_key or not isinstance(data, (_pydt.Tree, dict)):
                continue
            civ = data.get("civilization_value") if isinstance(data, dict) else data["civilization_value"]
            if civ is None:
                continue
            try:
                result[loc_key] = float(civ)
            except Exception:
                continue
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


def build_ir_climate_map(id_to_key: dict[int, str]) -> dict[str, str]:
    """Return {location_key: eu5_climate} from I:R map_data/climate.txt."""
    climate_file = ir_path("map_data/climate.txt")
    if not climate_file.exists():
        return {}

    result: dict[str, str] = {}
    mode = None
    current_category = None
    buffer: list[str] = []

    def map_category(raw_category: str | None) -> str | None:
        if not raw_category:
            return None
        return IR_CLIMATE_TO_EU5_CLIMATE.get(str(raw_category).lower().strip())

    def add_list(raw_category: str, values: list[str]) -> None:
        climate = map_category(raw_category)
        if not climate:
            return
        for token in values:
            if not token.isdigit():
                continue
            prov_id = int(token)
            key = id_to_key.get(prov_id)
            if key:
                result[key] = climate

    def add_range(raw_category: str, values: list[str]) -> None:
        climate = map_category(raw_category)
        if not climate or len(values) < 2:
            return
        try:
            start = int(values[0])
            end = int(values[1])
        except Exception:
            return
        if start > end:
            start, end = end, start
        for prov_id in range(start, end + 1):
            key = id_to_key.get(prov_id)
            if key:
                result[key] = climate

    for raw_line in climate_file.read_text(encoding="utf-8-sig").splitlines():
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
                        add_list(category, values)
                    else:
                        add_range(category, values)
                    continue
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
                        add_list(current_category, buffer)
                    else:
                        add_range(current_category, buffer)
                buffer = []
                mode = None
                current_category = None
            else:
                buffer.extend([t for t in tokens if t not in ("{", "}")])

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

    port_rows = parse_ports(
        {prov_id: key for prov_id, key, *_ in named_locations},
        sea_zones=sea_zones,
    )

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


def _setup_signature(buildings: dict[str, int]) -> tuple[tuple[str, int], ...]:
    items: list[tuple[str, int]] = []
    for key, value in sorted((buildings or {}).items()):
        try:
            level = int(value)
        except Exception:
            continue
        if level > 0:
            items.append((str(key), level))
    return tuple(items)


def _template_name_from_signature(signature: tuple[tuple[str, int], ...]) -> str:
    if not signature:
        return "ir_tpl_empty"

    alias = {
        "dock": "port",
        "marketplace": "market",
        "slave_market": "slave_market",
        "castle": "castle",
        "fortress": "fortress",
        "temple": "temple",
    }

    tokens: list[str] = []
    for building_key, level in signature:
        token = alias.get(building_key, building_key)
        tokens.append(f"{token}{level}")

    name = "ir_tpl_" + "_".join(tokens)
    if len(name) <= 96:
        return name

    # Keep names readable but bounded for parser/UI stability.
    compact = "_".join(tokens[:5])
    sig_text = "|".join(f"{key}:{level}" for key, level in signature)
    sig_hash = hashlib.md5(sig_text.encode("utf-8")).hexdigest()[:8]
    return f"ir_tpl_{compact}_{sig_hash}"


def _dedupe_location_setup_templates(
    location_to_setup: dict[str, str],
    setup_definitions: dict[str, dict[str, int]],
) -> tuple[dict[str, str], dict[str, dict[str, int]]]:
    """Collapse per-location setup names into shared templates by building signature."""
    signature_to_name: dict[tuple[tuple[str, int], ...], str] = {}
    deduped_definitions: dict[str, dict[str, int]] = {}
    deduped_location_to_setup: dict[str, str] = {}
    used_names: set[str] = set()

    for loc_key in sorted(location_to_setup.keys()):
        source_setup = location_to_setup[loc_key]
        signature = _setup_signature(setup_definitions.get(source_setup, {}))

        setup_name = signature_to_name.get(signature)
        if not setup_name:
            base_name = _template_name_from_signature(signature)
            setup_name = base_name
            suffix = 2
            while setup_name in used_names:
                setup_name = f"{base_name}_{suffix}"
                suffix += 1
            signature_to_name[signature] = setup_name
            used_names.add(setup_name)
            deduped_definitions[setup_name] = {k: v for k, v in signature}

        deduped_location_to_setup[loc_key] = setup_name

    return deduped_location_to_setup, deduped_definitions


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


# Curated market hubs for the 304 BC conversion.
# Each tuple is (display_label, candidate_location_keys in priority order).
HARDCODED_MARKET_HUBS_304BC: list[tuple[str, list[str]]] = [
    ("Alexandria", ["alexandria"]),
    ("Rhodes", ["rhodos"]),
    ("Athens", ["athens"]),
    ("Piraeus", ["pira"]),
    ("Corinth", ["korinthos"]),
    ("Carthage", ["carthago"]),
    ("Syracuse", ["syracusae"]),
    ("Tyre", ["tyrus"]),
    ("Gaza", ["gaza"]),
    ("Damascus", ["damascus"]),
    ("Pelusium", ["pelusium"]),
    ("Babylon", ["babylon_1", "babylon_0"]),
    ("Seleucia-on-the-Tigris", ["seleucia_magna"]),
    ("Susa", ["alexandria_susiana"]),
    ("Ecbatana", ["ecbatana"]),
    ("Gerrha", ["gerrha"]),
    ("Petra", ["petra"]),
    ("Omana", ["omana"]),
    ("Pataliputra", ["pataliputra"]),
    ("Taxila", ["taxila"]),
    ("Ujjain", ["ujjayini"]),
    ("Madurai", ["madurai"]),
    ("Massalia", ["massalia"]),
    ("Emporion", ["emporiae"]),
    ("Gades", ["gadir_0", "gadir_1"]),
    ("Tartessos", ["tartessos", "tartessia", "gadir_1"]),
    ("Saguntum", ["saguntum"]),
    ("Narbo", ["narbo"]),
    ("Tolosa", ["tolosa"]),
    ("Avaricum", ["avaricum"]),
    # Underrepresented Western fringe: British Isles & Ireland.
    ("Londinium", ["londinium"]),
    ("Camulodunum", ["camulodunum"]),
    ("Eboracum", ["eboracum"]),
    ("Deva", ["deva"]),
    ("Isca Dumnoniorum", ["isca_dumnoniorum"]),
    ("Eblana", ["eblana"]),
    ("Lindum", ["lindum"]),
    ("Byzantion", ["byzantion"]),
    ("Callatis", ["callatis"]),
    ("Olbia", ["olbia"]),
    ("Chersonesos Taurica", ["chersonesos"]),
    ("Panticapaeum", ["pantikapaion"]),
    ("Phasis", ["phasis"]),
    ("Tanais", ["tanais_0"]),
    ("Sinope", ["sinope"]),
    ("Amisos", ["amisos"]),
    ("Trapezus", ["trapezous", "trapezon"]),
    ("Artaxata", ["artaxata"]),
    ("Tigranocerta", ["tigranocerta"]),
    ("Nisibis", ["nisibis_0", "nisibis_1"]),
    ("Hatra", ["hatra"]),
    ("Dura-Europos", ["dura"]),
    ("Charax Spasinu", ["charax"]),
    ("Opis", ["opis"]),
    ("Uruk", ["uruk"]),
    ("Borsippa", ["borsippa"]),
    ("Dedan", ["dedan"]),
    ("Hegra", ["hegra"]),
    ("Qaryat al-Faw", ["karna", "mariaba", "dedan"]),
    ("Najran", ["mariaba", "sabata", "karna"]),
    ("Adulis", ["adouli"]),
    ("Avalites", ["aualites"]),
    ("Opone", ["opone"]),
    ("Rhapta", ["mosylon", "opone"]),
    ("Bactra", ["bactra"]),
    ("Alexandria Eschate", ["alexandreia_eschate"]),
    ("Marakanda", ["marakanda"]),
    ("Cyropolis", ["cyropolis_persica"]),
    ("Kashgar", ["kashgar"]),
    ("Korkai", ["koti"]),
    ("Arikamedu Region Port", ["mayurasattapattinam", "kanci", "kancipuram"]),
    ("Tamralipti", ["tamralipti"]),
]

MARKET_REGION_MINIMUMS_304BC: dict[str, int] = {
    # Regional floor guarantees for underrepresented 304 BC trade zones.
    "north_german_region": 2,
    "scandinavian_region": 2,
    "carpathia_region": 2,
    "baltic_region": 2,
}


def _is_within_hops(
    start: str,
    targets: set[str],
    neighbors: dict,
    max_hops: int,
) -> bool:
    if not targets or max_hops < 0:
        return False

    queue: list[tuple[str, int]] = [(start, 0)]
    visited: set[str] = {start}
    index = 0
    while index < len(queue):
        node, depth = queue[index]
        index += 1

        if depth > 0 and node in targets:
            return True
        if depth >= max_hops:
            continue

        edge_map = neighbors.get(node, {}) if isinstance(neighbors, dict) else {}
        if not isinstance(edge_map, dict):
            continue

        for neighbor_key in edge_map.keys():
            if not isinstance(neighbor_key, str) or neighbor_key in visited:
                continue
            visited.add(neighbor_key)
            queue.append((neighbor_key, depth + 1))

    return False



def _resolve_hardcoded_market_hubs(
    location_keys: set[str],
    excluded: set[str],
) -> list[str]:
    markets: list[str] = []
    seen: set[str] = set()
    unresolved_labels: list[str] = []

    for label, candidates in HARDCODED_MARKET_HUBS_304BC:
        chosen = None
        for key in candidates:
            if key in location_keys and key not in excluded:
                chosen = key
                break
        if chosen is None:
            unresolved_labels.append(label)
            continue
        if chosen in seen:
            continue
        seen.add(chosen)
        markets.append(chosen)

    if unresolved_labels:
        print(
            "Markets hardcode: unresolved hubs="
            + str(len(unresolved_labels))
            + " ("
            + ", ".join(unresolved_labels)
            + ")"
        )

    return markets



def _build_market_keys(
    id_to_key: dict[int, str],
    location_keys: set[str],
    default_map: dict,
    location_to_region: dict[str, str],
    country_locations: dict[str, list[int]],
    country_capitals: dict[str, int],
    top_capitals: int = 35,
    max_markets: int = 35,
    min_markets: int = 90,
    min_market_hops: int = 5,
) -> list[str]:
    excluded = _non_land_keys(default_map)
    target_markets = max(0, min_markets)
    region_minimums = {
        key: int(count)
        for key, count in MARKET_REGION_MINIMUMS_304BC.items()
        if isinstance(count, int) and count > 0
    }

    def valid_id(pid: int) -> bool:
        key = id_to_key.get(pid)
        return key is not None and key in location_keys and key not in excluded

    top_country_tags = sorted(
        country_locations.keys(),
        key=lambda tag: len(country_locations.get(tag, [])),
        reverse=True,
    )

    def _capital_keys(tags: list[str]) -> list[str]:
        cap_keys: list[str] = []
        for tag in tags:
            cap_id = country_capitals.get(tag)
            if cap_id is None or not valid_id(cap_id):
                continue
            cap_key = id_to_key[cap_id]
            if cap_key not in cap_keys:
                cap_keys.append(cap_key)
        return cap_keys

    spacing_immune_capital_keys = _capital_keys(top_country_tags[:30])
    all_capital_keys = _capital_keys(top_country_tags)

    road_degree: dict[str, int] = {}
    for a_id, b_id in _parse_ir_road_pairs():
        a_key = id_to_key.get(a_id)
        b_key = id_to_key.get(b_id)
        if a_key in location_keys and a_key not in excluded:
            road_degree[a_key] = road_degree.get(a_key, 0) + 1
        if b_key in location_keys and b_key not in excluded:
            road_degree[b_key] = road_degree.get(b_key, 0) + 1
    road_ranked_keys = sorted(road_degree.keys(), key=lambda key: (-road_degree[key], key))
    all_land_keys = sorted(key for key in location_keys if key not in excluded)

    region_candidate_keys: dict[str, list[str]] = {region_key: [] for region_key in region_minimums.keys()}
    for source in (road_ranked_keys, all_capital_keys, all_land_keys):
        for key in source:
            region_key = location_to_region.get(key)
            if region_key not in region_candidate_keys:
                continue
            if key not in region_candidate_keys[region_key]:
                region_candidate_keys[region_key].append(key)

    neighbor_payload = load_location_neighbors()
    neighbors = neighbor_payload.get("neighbors", {}) if isinstance(neighbor_payload, dict) else {}
    enforce_spacing = isinstance(neighbors, dict) and bool(neighbors) and min_market_hops > 1
    if min_market_hops > 1 and not enforce_spacing:
        print("Markets: neighbor graph unavailable; skipping hop-spacing enforcement.")

    def _append_if_valid(markets: list[str], key: str, *, ignore_spacing: bool = False) -> bool:
        if key in markets:
            return False
        if key not in location_keys or key in excluded:
            return False
        if (
            enforce_spacing
            and not ignore_spacing
            and _is_within_hops(key, set(markets), neighbors, min_market_hops - 1)
        ):
            return False
        markets.append(key)
        return True

    def _append_from(markets: list[str], source: list[str], *, ignore_spacing: bool = False) -> int:
        added = 0
        for key in source:
            if _append_if_valid(markets, key, ignore_spacing=ignore_spacing):
                added += 1
        return added

    def _enforce_region_minimums(markets: list[str]) -> tuple[int, list[str]]:
        if not region_minimums:
            return 0, []
        added = 0
        missing: list[str] = []
        for region_key, min_count in region_minimums.items():
            current = sum(1 for key in markets if location_to_region.get(key) == region_key)
            needed = min_count - current
            if needed <= 0:
                continue
            for candidate in region_candidate_keys.get(region_key, []):
                if _append_if_valid(markets, candidate):
                    added += 1
                    needed -= 1
                    if needed <= 0:
                        break
            if needed > 0:
                missing.append(f"{region_key}(-{needed})")
        return added, missing

    def _extend_to_target(markets: list[str]) -> int:
        if not target_markets or len(markets) >= target_markets:
            return 0
        added = 0
        for source in (all_capital_keys, road_ranked_keys, all_land_keys):
            for key in source:
                if _append_if_valid(markets, key):
                    added += 1
                if len(markets) >= target_markets:
                    return added
        return added

    hardcoded_markets = _resolve_hardcoded_market_hubs(location_keys, excluded)
    if hardcoded_markets:
        merged: list[str] = []
        added_immune_capitals = _append_from(
            merged,
            spacing_immune_capital_keys,
            ignore_spacing=True,
        )
        curated_added = _append_from(merged, hardcoded_markets)
        added_regions, missing_regions = _enforce_region_minimums(merged)
        added_fill = _extend_to_target(merged)
        print(
            "Markets hardcode: using "
            + str(curated_added)
            + " curated hubs"
            + (
                " + "
                + str(added_immune_capitals)
                + " spacing-immune top-30 capitals"
                if added_immune_capitals
                else ""
            )
            + (
                " + "
                + str(added_regions)
                + " regional guarantees"
                if added_regions
                else ""
            )
            + (
                " + "
                + str(added_fill)
                + " deterministic fillers to reach "
                + str(target_markets)
                if added_fill
                else ""
            )
            + "."
        )
        if missing_regions:
            print("Markets warning: unmet regional minimums: " + ", ".join(missing_regions))
        if target_markets and len(merged) < target_markets:
            print(
                "Markets warning: only "
                + str(len(merged))
                + " markets could be assigned while keeping minimum hop spacing of "
                + str(min_market_hops)
                + " (excluding spacing-immune capitals)."
            )
        return merged

    preferred_capitals: list[int] = []
    for tag in top_country_tags[:top_capitals]:
        cap_id = country_capitals.get(tag)
        if cap_id is None:
            continue
        if valid_id(cap_id):
            preferred_capitals.append(cap_id)
    preferred_capitals = _dedupe(preferred_capitals)

    markets: list[str] = []
    _append_from(markets, spacing_immune_capital_keys, ignore_spacing=True)
    for pid in preferred_capitals:
        key = id_to_key[pid]
        if _append_if_valid(markets, key) and len(markets) >= max_markets:
            break

    _enforce_region_minimums(markets)
    _extend_to_target(markets)

    if target_markets and len(markets) < target_markets:
        print(
            "Markets warning: only "
            + str(len(markets))
            + " markets could be assigned while keeping minimum hop spacing of "
            + str(min_market_hops)
            + " (excluding spacing-immune capitals)."
        )

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
    coastal_land_locations: set[str] | None = None,
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
        if rank == "city" or "metropolis" in rank:
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
            is_port = ("port_building" in data and data["port_building"]) or (
                coastal_land_locations is not None and loc_key in coastal_land_locations
            )
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
        return rank == "city" or "metropolis" in rank

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
        "volcanoes": "volcanoes",
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

        # Keep Caspian (`mare_hyrcanum_*`) selectable by classifying it as sea_zones.
        hyrcanum = {k for k in mapped_data.get("lakes", set()) if str(k).startswith("mare_hyrcanum_")}
        if hyrcanum:
            mapped_data.setdefault("sea_zones", set()).update(hyrcanum)
            mapped_data["lakes"] = set(mapped_data.get("lakes", set())) - hyrcanum

        # Write each mapped category once.
        for mapped_category in sorted(mapped_data.keys()):
            write_category(mapped_category, mapped_data[mapped_category])
    print_written("file", default_map)


def _write_map_localisation(
    named_locations: list[tuple[int, str, int, int, int, str]],
    regions: dict[str, dict[str, list[str]]],
    normalized_superregion_map: dict,
    subcontinent_keys: set[str],
    continent_keys: set[str],
) -> None:
    # Localisation: provinces, areas, regions
    loc_lines = ["l_english:"]

    # Prefer existing Imperator localisation if present
    ir_loc = read_localisation_file(ir_localisation_paths)
    location_names_dir = iu_localisation / "location_names"
    existing_loc = (
        read_localisation_file(location_names_dir) if location_names_dir.exists() else {}
    )

    def _title_key(key: str) -> str:
        return key.replace("_", " ").strip().title() if key else key

    def _prettify_tier_key(key: str) -> str:
        base = key
        for suffix in ("_province", "_area", "_region"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return _title_key(base)

    def _lookup_map_loc_name(key: str) -> str:
        candidates: list[str] = [key]
        if key.endswith("_province"):
            stem = key[: -len("_province")]
            candidates.extend([stem, f"{stem}_area", f"{stem}_region"])
        elif key.endswith("_area"):
            stem = key[: -len("_area")]
            candidates.extend([stem, f"{stem}_region", f"{stem}_province"])
        elif key.endswith("_region"):
            stem = key[: -len("_region")]
            candidates.extend([stem, f"{stem}_area", f"{stem}_province"])

        for candidate in candidates:
            value = ir_loc.get(candidate)
            if isinstance(value, str) and value.strip() and value.strip() != candidate:
                return value.strip()
        return _prettify_tier_key(key)

    # --- Provinces ---
    for prov_id, key, *_ in named_locations:
        if key in existing_loc:
            continue
        name = ir_loc.get(f"PROV{prov_id}")
        if not isinstance(name, str) or not name.strip():
            name = _lookup_map_loc_name(key)
        loc_lines.append(f'  {key}: "{name}"')

    # --- Regions ---
    for region_tag in regions:
        name = _lookup_map_loc_name(region_tag)
        loc_lines.append(f'  {region_tag}: "{name}"')

    # --- Areas ---
    for area_list in regions.values():
        for area_tag in area_list:
            name = _lookup_map_loc_name(area_tag)
            loc_lines.append(f'  {area_tag}: "{name}"')

    # --- Superregions, subcontinents, and continents ---
    def _superregion_label(key: str) -> str:
        if not key:
            return key
        base = key[:-7] if key.endswith("_region") else key
        return _title_key(base)

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
        {superregion for sub in normalized_superregion_map.values() for superregion in sub.keys()}
    )
    for key in superregion_keys:
        if key not in existing_loc:
            label = superregion_name_overrides.get(key, ir_loc.get(key, _superregion_label(key)))
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
        "lakes_area",
        "lakes_province",
        "non_ownable_area",
        "non_ownable_province",
        "river_provinces_area",
        "river_provinces_province",
        "sea_zones_area",
        "sea_zones_province",
        "unassigned_locations_area",
        "unassigned_locations_province",
    ):
        if key not in existing_loc:
            loc_lines.append(f'  {key}: "{_title_key(key)}"')

    # Write localisation file
    write_blocks(iu_localisation / "ir_map_l_english.yml", loc_lines)


def _write_location_templates(
    location_keys: set[str],
    default_map: dict,
    coastal_land_locations: set[str],
    location_to_region: dict[str, str],
    id_to_key: dict[int, str],
    default_culture: str | None,
    default_religion: str | None,
    harbor_suitability_map: dict[str, str],
) -> None:
    # --- Location templates (only for existing land locations) ---
    location_templates = iu_map_data / "location_templates.txt"
    location_templates.parent.mkdir(parents=True, exist_ok=True)
    sea_zones = default_map.get("sea_zones", set()) if isinstance(default_map, dict) else set()
    lakes = default_map.get("lakes", set()) if isinstance(default_map, dict) else set()
    river_provinces = (
        default_map.get("river_provinces", set()) if isinstance(default_map, dict) else set()
    )
    impassable_mountains = (
        default_map.get("impassable_mountains", set()) if isinstance(default_map, dict) else set()
    )
    non_ownable = default_map.get("non_ownable", set()) if isinstance(default_map, dict) else set()
    excluded_locations = _non_land_keys(default_map) if isinstance(default_map, dict) else set()
    raw_materials = build_ir_raw_materials(id_to_key)
    terrain_map = build_ir_terrain_maps(id_to_key)
    climate_map = build_ir_climate_map(id_to_key)
    with location_templates.open("w", encoding="utf-8") as f:
        for key in sorted(location_keys):
            is_ownable = key not in excluded_locations
            is_water_location = (
                key in sea_zones
                or key in lakes
                or key in river_provinces
                or key.startswith("mare_hyrcanum_")
            )
            if is_water_location:
                is_ownable = False
            climate = climate_map.get(key, "continental")
            if (
                climate in ("oceanic", "continental")
                and key in coastal_land_locations
                and location_to_region.get(key) in MEDITERRANEAN_COASTAL_AREAS
            ):
                climate = "mediterranean"
            parts = [f"climate = {climate}"]
            terrain = terrain_map.get(key)
            if is_ownable:
                topography = terrain[0] if terrain else "flatland"
                vegetation = terrain[1] if terrain else "grasslands"
                parts.insert(0, f"vegetation = {vegetation}")
                parts.insert(0, f"topography = {topography}")
            else:
                write_vegetation = True
                if key in sea_zones or key.startswith("mare_hyrcanum_"):
                    if key.startswith("mare_hyrcanum_"):
                        topography = "inland_sea"
                    else:
                        topography = "ocean"
                    vegetation = "sparse"
                    # EU5 logs an error if sea locations have any vegetation field.
                    write_vegetation = False
                elif key in lakes:
                    topography = "lakes"
                    vegetation = "sparse"
                    write_vegetation = False
                elif key in river_provinces:
                    topography = "flatland"
                    vegetation = "grasslands"
                    write_vegetation = False
                elif key in non_ownable:
                    if terrain:
                        topography, vegetation = terrain
                    else:
                        topography, vegetation = _infer_non_ownable_topography_vegetation(key, climate)
                elif terrain:
                    topography = terrain[0]
                    vegetation = terrain[1]
                elif key in impassable_mountains:
                    topography = "mountain_wasteland"
                    vegetation = "sparse"
                else:
                    topography = "flatland"
                    vegetation = _default_vegetation_for_topography(topography, climate)

                if write_vegetation:
                    parts.insert(0, f"vegetation = {vegetation}")
                parts.insert(0, f"topography = {topography}")
            if is_ownable and default_religion:
                parts.append(f"religion = {default_religion}")
            if is_ownable and default_culture:
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


def _apply_map_content_overrides(
    location_keys: set[str],
    region_keys: set[str],
    continent_keys: set[str],
    subcontinent_keys: set[str],
) -> None:
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

    # --- Empty map object locators/overrides to avoid unknown location references ---
    _write_map_object_override_files()

    # --- Patch scripts referencing missing locations/regions ---
    if location_keys:
        fallback_location = next(iter(sorted(location_keys)))
    else:
        fallback_location = None
    fallback_region = next(iter(sorted(region_keys))) if region_keys else None
    fallback_continent = next(iter(sorted(continent_keys))) if continent_keys else None
    fallback_subcontinent = next(iter(sorted(subcontinent_keys))) if subcontinent_keys else None

    # Script-driven data files still need location-aware patching.
    script_roots = [
        eu5_game / "in_game" / "common" / "scripted_triggers",
        eu5_game / "in_game" / "common" / "advances",
    ]
    for script_root in script_roots:
        if not script_root.exists():
            continue
        for src in script_root.rglob("*.txt"):
            rel = src.relative_to(eu5_game / "in_game")
            dst = mod_root / "in_game" / rel
            _patch_script_file_references(
                src,
                dst,
                location_keys=location_keys,
                region_keys=region_keys,
                continent_keys=continent_keys,
                subcontinent_keys=subcontinent_keys,
                fallback_location=fallback_location,
                fallback_region=fallback_region,
                fallback_continent=fallback_continent,
                fallback_subcontinent=fallback_subcontinent,
            )


def _copy_filtered_location_start_files(location_keys: set[str]) -> None:
    setup_start_dir = eu5_game / "main_menu" / "setup" / "start"
    dst_setup_start_dir = mod_root / "main_menu" / "setup" / "start"
    location_keyed_files = {"07_cities_and_buildings.txt"}
    if not setup_start_dir.exists():
        return

    dst_setup_start_dir.mkdir(parents=True, exist_ok=True)
    for filename in location_keyed_files:
        src_file = setup_start_dir / filename
        if not src_file.exists():
            continue
        tree = parse_tree(src_file)
        filtered = _filter_tree_entries_by_tags(tree, location_keys)
        write_blocks(dst_setup_start_dir / filename, filtered, encoding="utf-8")


def _write_pops_file(id_to_key: dict[int, str]) -> dict[str, list[str]]:
    pops_by_location = build_ir_pops(id_to_key)
    pops_blocks = [
        (loc_key, pops_by_location[loc_key]) for loc_key in sorted(pops_by_location.keys())
    ]
    _write_locations_block(iu_setup_start / "06_pops.txt", pops_blocks, encoding="utf-8")
    return pops_by_location


def _write_institutions_file(pops_by_location: dict[str, list[str]], default_map: dict) -> None:
    excluded_locations = _non_land_keys(default_map) if isinstance(default_map, dict) else set()
    ownable_locations = sorted(set(pops_by_location.keys()) - excluded_locations)
    institutions_dst = mod_root / "main_menu" / "setup" / "start" / "08_institutions.txt"
    institution_blocks = [
        (loc_key, ["feudalism = yes", "legalism = yes", "meritocracy = yes"])
        for loc_key in ownable_locations
    ]
    _write_locations_block(institutions_dst, institution_blocks, encoding="utf-8")


def _merge_main_setup_buildings(
    setup_definitions: dict[str, dict[str, int]],
    building_map: dict[str, str],
    id_to_key: dict[int, str],
) -> None:
    main_setup = ir_path("setup/main/00_default.txt")
    if not main_setup.exists():
        return

    main_tree = parse_tree(main_setup)
    provinces = main_tree["provinces"] if "provinces" in main_tree else None
    if not isinstance(provinces, (_pydt.Tree, dict)):
        return

    merged_count = 0
    for raw_id, data in provinces.items():
        try:
            prov_id = int(raw_id)
        except Exception:
            continue
        loc_key = id_to_key.get(prov_id)
        if not loc_key or not isinstance(data, (_pydt.Tree, dict)):
            continue

        setup_name = f"ir_loc_{loc_key}"
        dst_buildings = setup_definitions.setdefault(setup_name, {})
        inner = data.get("buildings") if isinstance(data, dict) else data["buildings"] if "buildings" in data else None

        for block in (inner, data):
            if not isinstance(block, (_pydt.Tree, dict)):
                continue
            for b_key, b_val in block.items():
                b_key_str = str(b_key)
                if b_key_str not in building_map:
                    continue
                try:
                    level = int(str(b_val).strip())
                except Exception:
                    level = 0
                if level <= 0:
                    continue
                mapped = building_map[b_key_str]
                dst_buildings[mapped] = max(dst_buildings.get(mapped, 0), level)
                merged_count += 1

    if merged_count > 0:
        print(
            "Merged "
            + str(merged_count)
            + " building assignments from Imperator main setup into town_setups"
        )




def _tree_block(value):
    if isinstance(value, (_pydt.Tree, dict)):
        return value
    if isinstance(value, list) and value and isinstance(value[0], (_pydt.Tree, dict)):
        return value[0]
    return None


def _to_int(value) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        value = value[0] if value else 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).strip())
    except Exception:
        return 0


def _allocate_levels(locations: list[str], extra_levels: int) -> dict[str, int]:
    allocation: dict[str, int] = {}
    if not locations or extra_levels <= 0:
        return allocation
    idx = 0
    while extra_levels > 0:
        loc_key = locations[idx % len(locations)]
        allocation[loc_key] = allocation.get(loc_key, 0) + 1
        extra_levels -= 1
        idx += 1
    return allocation


def _to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, list):
        value = value[0] if value else default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return default


def _scalar_text(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _load_location_template_index(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        tree = parse_tree(path)
    except Exception:
        return {}

    index: dict[str, dict[str, str]] = {}
    for loc_key, raw_block in tree.items():
        block = _tree_block(raw_block)
        if not isinstance(block, (_pydt.Tree, dict)):
            continue

        info = {
            "climate": _scalar_text(block["climate"] if "climate" in block else None) or "unknown",
            "topography": _scalar_text(block["topography"] if "topography" in block else None)
            or "unknown",
            "vegetation": _scalar_text(block["vegetation"] if "vegetation" in block else None)
            or "unknown",
            "raw_material": _scalar_text(block["raw_material"] if "raw_material" in block else None)
            or "unknown",
            "coastal": "yes" if "natural_harbor_suitability" in block else "no",
        }
        index[str(loc_key)] = info
    return index


def _raw_material_bucket(raw_material: str | None) -> str:
    if not raw_material:
        return "other"
    key = str(raw_material).strip().lower()
    if key == "fish":
        return "fish"
    if key in FOOD_GOODS:
        return "food"
    if key in FOREST_GOODS:
        return "forest"
    if key in {
        "iron",
        "copper",
        "gold",
        "silver",
        "lead",
        "tin",
        "salt",
        "stone",
        "gems",
        "marble",
    }:
        return "minerals"
    if key in {
        "fiber_crops",
        "cotton",
        "silk",
        "flax",
        "wool",
        "dyes",
    }:
        return "textiles"
    return "other"


def _location_geo_bucket(info: dict[str, str] | None) -> str:
    if not info:
        return "inland|unknown|unknown|other"
    coast = "coastal" if info.get("coastal") == "yes" else "inland"
    climate = info.get("climate", "unknown")
    topography = info.get("topography", "unknown")
    raw_bucket = _raw_material_bucket(info.get("raw_material"))
    return f"{coast}|{climate}|{topography}|{raw_bucket}"


def _base_development_rules() -> dict[str, float]:
    return {
        "base": -2.0,
        "coastal": 5.0,
        "river": 0.5,
        "road": 2.0,
        "city": 5.0,
        "town": 2.0,
        "grasslands": 1.0,
        "farmland": 3.0,
        "sparse": -1.0,
        "forest": -2.0,
        "woods": -1.0,
        "desert": -3.0,
        "jungle": -4.0,
        "tropical": -3.0,
        "subtropical": 2.0,
        "oceanic": 1.0,
        "arid": -4.0,
        "cold_arid": -3.0,
        "mediterranean": 2.0,
        "continental": 1.0,
        "arctic": -5.0,
        "flatland": 1.0,
        "mountains": -3.0,
        "hills": -2.0,
        "plateau": -1.0,
        "wetlands": -4.0,
    }


def _location_development_components(
    info: dict[str, str] | None,
    rank: str | None,
    development_rules: dict[str, float],
) -> float:
    total = float(development_rules.get("base", 0.0))
    if rank in ("city", "town"):
        total += float(development_rules.get(rank, 0.0))
    if info:
        if info.get("coastal") == "yes":
            total += float(development_rules.get("coastal", 0.0))
        climate = info.get("climate")
        topography = info.get("topography")
        vegetation = info.get("vegetation")
        if climate:
            total += float(development_rules.get(climate, 0.0))
        if topography:
            total += float(development_rules.get(topography, 0.0))
        if vegetation:
            total += float(development_rules.get(vegetation, 0.0))
    return total


def _map_values_to_reference_distribution(
    source_values: dict[str, float],
    reference_values: list[float],
) -> dict[str, float]:
    if not source_values:
        return {}

    src_sorted = sorted(source_values.items(), key=lambda item: (item[1], item[0]))
    ref_sorted = sorted(reference_values)
    if not ref_sorted:
        ref_sorted = [value for _, value in src_sorted]

    n = len(src_sorted)
    m = len(ref_sorted)
    out: dict[str, float] = {}

    for idx, (loc_key, _) in enumerate(src_sorted):
        if n == 1:
            ref_idx = (m - 1) // 2 if m > 0 else 0
        else:
            position = idx / (n - 1)
            ref_idx = int(round(position * (m - 1))) if m > 1 else 0
        out[loc_key] = float(ref_sorted[ref_idx])

    return out


def build_ir_development_metrics(id_to_key: dict[int, str]) -> dict[str, dict[str, float | str]]:
    province_files = _iter_ir_province_files()
    if not province_files:
        return {}

    pop_weights = {
        "nobles": 3.2,
        "citizen": 2.4,
        "freemen": 1.8,
        "slaves": 1.0,
        "tribesmen": 0.8,
    }

    road_pairs = _parse_ir_road_pairs()
    degree: dict[int, int] = defaultdict(int)
    for a_id, b_id in road_pairs:
        degree[a_id] += 1
        degree[b_id] += 1

    ir_building_keys = _load_ir_building_keys()

    metrics: dict[str, dict[str, float | str]] = {}
    for path in province_files:
        tree = parse_tree(path)
        for raw_id, data in tree.items():
            try:
                prov_id = int(raw_id)
            except Exception:
                continue
            loc_key = id_to_key.get(prov_id)
            if not loc_key or not isinstance(data, (_pydt.Tree, dict)):
                continue

            weighted_pop = 0.0
            total_pop = 0.0
            for pop_key, pop_weight in pop_weights.items():
                pop_block = data.get(pop_key) if isinstance(data, dict) else data[pop_key]
                if pop_block is None:
                    continue
                entries = pop_block if isinstance(pop_block, list) else [pop_block]
                for entry in entries:
                    block = _tree_block(entry)
                    if not isinstance(block, (_pydt.Tree, dict)):
                        continue
                    amount = _to_float(
                        block.get("amount") if isinstance(block, dict) else block["amount"]
                    )
                    if amount <= 0:
                        continue
                    weighted_pop += amount * pop_weight
                    total_pop += amount

            civ = _to_float(
                data.get("civilization_value") if isinstance(data, dict) else data["civilization_value"]
            )
            province_rank = _scalar_text(
                data.get("province_rank") if isinstance(data, dict) else data["province_rank"]
            )
            rank_text = province_rank.lower() if province_rank else ""
            rank_bonus = 0.0
            if "metropolis" in rank_text:
                rank_bonus = 2.8
            elif rank_text == "city":
                rank_bonus = 1.5

            building_levels = 0.0
            for building_key in ir_building_keys:
                if isinstance(data, dict):
                    raw_level = data.get(building_key)
                else:
                    raw_level = data[building_key] if building_key in data else None
                if raw_level is None:
                    continue
                building_levels += max(0.0, _to_float(raw_level))

            if isinstance(data, dict):
                port_raw = data.get("port_building")
            else:
                port_raw = data["port_building"] if "port_building" in data else None
            is_port = _to_float(port_raw, default=0.0) > 0.0

            road_degree = degree.get(prov_id, 0)
            pop_component = math.log1p(max(0.0, weighted_pop)) * 5.2
            civ_component = (max(0.0, civ) / 100.0) * 7.0
            road_bonus = min(2.0, math.log1p(max(0, road_degree)) * 1.1)
            building_bonus = min(3.5, math.log1p(max(0.0, building_levels)) * 1.8)
            port_bonus = 0.5 if is_port else 0.0

            raw_score = (
                pop_component
                + civ_component
                + rank_bonus
                + road_bonus
                + building_bonus
                + port_bonus
            )
            if raw_score <= 0 and total_pop > 0:
                raw_score = math.log1p(total_pop) * 3.0
            if raw_score <= 0 and civ > 0:
                raw_score = (civ / 100.0) * 3.0

            metrics[loc_key] = {
                "raw_score": raw_score,
                "total_pop": total_pop,
                "weighted_pop": weighted_pop,
                "civilization_value": civ,
                "province_rank": province_rank or "",
                "road_degree": float(road_degree),
                "building_levels": building_levels,
                "is_port": 1.0 if is_port else 0.0,
                "pop_component": pop_component,
                "civ_component": civ_component,
                "rank_bonus": rank_bonus,
                "road_bonus": road_bonus,
                "building_bonus": building_bonus,
                "port_bonus": port_bonus,
            }

    return metrics


def build_ir_raw_development_values(id_to_key: dict[int, str]) -> dict[str, float]:
    metrics = build_ir_development_metrics(id_to_key)
    return {
        loc_key: float(values.get("raw_score", 0.0))
        for loc_key, values in metrics.items()
    }


def _eu5_economy_targets() -> dict:
    targets = {
        "city_share": 0.25,
        "avg_by_rank": {},
        "rank_counts": {"city": 0, "town": 0, "rural_settlement": 0},
        "all_buildings": [],
        "building_totals": {},
        "template_definitions": {},
        "template_distribution": {},
        "template_distribution_geo": {},
        "template_development": {},
        "development_by_rank": {},
        "direct_building_totals": {},
    }

    setup_path = eu5_game / "main_menu" / "setup" / "start" / "07_cities_and_buildings.txt"
    town_setups_path = eu5_game / "in_game" / "common" / "town_setups" / "00_default.txt"
    location_templates_path = eu5_game / "in_game" / "map_data" / "location_templates.txt"
    development_path = eu5_game / "main_menu" / "setup" / "start" / "14_development.txt"

    if not setup_path.exists() or not town_setups_path.exists():
        return targets

    try:
        setup_tree = parse_tree(setup_path)
        setup_locations = _tree_block(setup_tree["locations"]) if "locations" in setup_tree else None
        town_setups_tree = parse_tree(town_setups_path)
    except Exception:
        return targets

    if not isinstance(setup_locations, (_pydt.Tree, dict)):
        return targets

    location_template_index = _load_location_template_index(location_templates_path)

    development_rules = _base_development_rules()
    if development_path.exists():
        try:
            development_tree = parse_tree(development_path)
            development_block = (
                _tree_block(development_tree["development"]) if "development" in development_tree else None
            )
            if isinstance(development_block, (_pydt.Tree, dict)):
                for key, value in development_block.items():
                    key_str = str(key)
                    parsed = _to_float(value, default=float("nan"))
                    if math.isnan(parsed):
                        continue
                    development_rules[key_str] = parsed
        except Exception:
            pass


    allowed_buildings = _eu5_allowed_buildings_from_ir()
    direct_building_totals: Counter = Counter()
    try:
        setup_text = setup_path.read_text(encoding="utf-8-sig")
    except Exception:
        setup_text = ""

    if setup_text:
        direct_pattern = re.compile(
            r"^\s*([A-Za-z0-9_]+)\s*=\s*\{[^{}\n]*\blevel\s*=\s*([0-9]+)[^{}\n]*\blocation\s*=\s*([A-Za-z0-9_]+)[^{}\n]*\}",
            re.MULTILINE,
        )
        for match in direct_pattern.finditer(setup_text):
            building_key = str(match.group(1))
            level = max(0, _to_int(match.group(2)))
            if level <= 0:
                continue
            if allowed_buildings and building_key not in allowed_buildings:
                continue
            direct_building_totals[building_key] += level

    template_definitions: dict[str, dict[str, int]] = {}
    all_buildings: set[str] = set()
    filtered_template_entries = 0
    for template_name, raw_template in town_setups_tree.items():
        block = _tree_block(raw_template)
        if not isinstance(block, (_pydt.Tree, dict)):
            continue
        template_buildings: dict[str, int] = {}
        for key, value in block.items():
            key_str = str(key)
            if key_str in ("rank", "town_setup"):
                continue
            if allowed_buildings and key_str not in allowed_buildings:
                filtered_template_entries += 1
                continue
            level = _to_int(value)
            if level <= 0:
                continue
            template_buildings[key_str] = level
            all_buildings.add(key_str)
        template_definitions[str(template_name)] = template_buildings

    rank_counts: Counter = Counter()
    totals_by_rank: dict[str, Counter] = defaultdict(Counter)
    totals_all: Counter = Counter()
    template_distribution: dict[str, Counter] = defaultdict(Counter)
    template_distribution_geo: dict[str, Counter] = defaultdict(Counter)
    template_dev_totals: Counter = Counter()
    template_dev_counts: Counter = Counter()
    development_by_rank: dict[str, list[float]] = defaultdict(list)

    for loc_key, raw_loc_data in setup_locations.items():
        loc_data = _tree_block(raw_loc_data)
        if not isinstance(loc_data, (_pydt.Tree, dict)):
            continue

        rank_value = loc_data["rank"] if "rank" in loc_data else None
        setup_name = loc_data["town_setup"] if "town_setup" in loc_data else None
        if not rank_value or not setup_name:
            continue

        loc_key_str = str(loc_key)
        rank = str(rank_value).strip()
        setup_name = str(setup_name).strip()
        if rank not in ("city", "town", "rural_settlement"):
            continue
        if setup_name not in template_definitions:
            continue

        info = location_template_index.get(loc_key_str, {})
        is_coastal = info.get("coastal") == "yes"
        geo_bucket = _location_geo_bucket(info)

        rank_counts[rank] += 1
        template_distribution[f"{rank}|any"][setup_name] += 1
        template_distribution[f"{rank}|{'coastal' if is_coastal else 'inland'}"][setup_name] += 1
        template_distribution_geo[f"{rank}|{geo_bucket}"][setup_name] += 1

        dev_score = _location_development_components(info, rank, development_rules)
        dev_score += float(development_rules.get(loc_key_str, 0.0))
        development_by_rank[rank].append(dev_score)
        template_dev_totals[setup_name] += dev_score
        template_dev_counts[setup_name] += 1

        for building_key, level in template_definitions[setup_name].items():
            totals_by_rank[rank][building_key] += level
            totals_all[building_key] += level

    urban = rank_counts["city"] + rank_counts["town"]
    if urban > 0:
        targets["city_share"] = rank_counts["city"] / urban

    targets["rank_counts"] = {
        "city": rank_counts["city"],
        "town": rank_counts["town"],
        "rural_settlement": rank_counts["rural_settlement"],
    }

    avg_by_rank: dict[str, dict[str, float]] = {}
    for rank in ("city", "town", "rural_settlement"):
        count = rank_counts[rank]
        rank_avg: dict[str, float] = {}
        for building_key in sorted(all_buildings):
            if count > 0:
                rank_avg[building_key] = totals_by_rank[rank][building_key] / count
            else:
                rank_avg[building_key] = 0.0
        avg_by_rank[rank] = rank_avg

    for direct_building_key in direct_building_totals.keys():
        all_buildings.add(str(direct_building_key))

    targets["avg_by_rank"] = avg_by_rank
    targets["all_buildings"] = sorted(all_buildings)
    targets["building_totals"] = {
        building_key: totals_all[building_key] for building_key in sorted(all_buildings)
    }
    for fort_key in FORT_LIKE_BUILDINGS:
        if fort_key in direct_building_totals:
            targets["building_totals"][fort_key] = max(0, _to_int(direct_building_totals[fort_key]))
    targets["template_definitions"] = template_definitions
    targets["template_distribution"] = {
        key: dict(counter) for key, counter in template_distribution.items()
    }
    targets["template_distribution_geo"] = {
        key: dict(counter) for key, counter in template_distribution_geo.items()
    }
    targets["template_development"] = {
        template: (template_dev_totals[template] / template_dev_counts[template])
        for template in sorted(template_dev_totals.keys())
        if template_dev_counts[template] > 0
    }
    targets["development_by_rank"] = {
        rank: sorted(values) for rank, values in development_by_rank.items()
    }
    targets["direct_building_totals"] = {
        key: max(0, _to_int(value))
        for key, value in sorted(direct_building_totals.items())
    }

    print(
        "EU5 economy baseline: "
        f"city_share={targets['city_share']:.3f}, "
        f"cities={rank_counts['city']}, towns={rank_counts['town']}, "
        f"rural={rank_counts['rural_settlement']}, "
        f"templates={len(template_definitions)}, buildings={len(all_buildings)}, "
        f"filtered_template_entries={filtered_template_entries}, "
        f"direct_castles={targets['direct_building_totals'].get('castle', 0)}, "
        f"direct_stockades={targets['direct_building_totals'].get('stockade', 0)}"
    )
    return targets


def _write_economy_balance_report(
    baseline_targets: dict,
    rank_lines: dict[str, str],
    location_building_setups: dict[str, str],
    setup_definitions: dict[str, dict[str, int]],
    direct_building_levels: dict[str, int] | None = None,
) -> None:
    baseline_buildings = set(baseline_targets.get("all_buildings", []))
    generated_buildings = {
        key for setup in setup_definitions.values() for key, level in setup.items() if _to_int(level) > 0
    }
    direct_buildings = {
        key for key, level in (direct_building_levels or {}).items() if max(0, _to_int(level)) > 0
    }
    tracked = sorted(baseline_buildings | generated_buildings | direct_buildings)

    rank_counts: Counter = Counter()
    totals_by_rank: dict[str, Counter] = defaultdict(Counter)
    generated_totals: Counter = Counter()

    rank_pattern = re.compile(r"\brank\s*=\s*(city|town|rural_settlement)\b")

    for loc_key, line in rank_lines.items():
        match = rank_pattern.search(line)
        if not match:
            continue
        rank = match.group(1)
        rank_counts[rank] += 1

        setup_name = location_building_setups.get(loc_key)
        if not setup_name:
            continue
        setup = setup_definitions.get(setup_name, {})
        for key in tracked:
            level = max(0, _to_int(setup.get(key)))
            totals_by_rank[rank][key] += level
            generated_totals[key] += level

    for key, level in (direct_building_levels or {}).items():
        generated_totals[str(key)] += max(0, _to_int(level))

    report_rows = []
    report_rows.append(("metric", "baseline", "iu_generated"))

    baseline_city = baseline_targets.get("rank_counts", {}).get("city", 0)
    baseline_town = baseline_targets.get("rank_counts", {}).get("town", 0)
    baseline_urban = baseline_city + baseline_town
    baseline_city_share = (
        (baseline_city / baseline_urban) if baseline_urban > 0 else baseline_targets.get("city_share", 0.25)
    )

    iu_city = rank_counts["city"]
    iu_town = rank_counts["town"]
    iu_urban = iu_city + iu_town
    iu_city_share = (iu_city / iu_urban) if iu_urban > 0 else 0.0

    report_rows.append(("urban_city_share", f"{baseline_city_share:.4f}", f"{iu_city_share:.4f}"))
    report_rows.append(("rank_city_count", str(baseline_city), str(iu_city)))
    report_rows.append(("rank_town_count", str(baseline_town), str(iu_town)))
    report_rows.append(
        (
            "rank_rural_count",
            str(baseline_targets.get("rank_counts", {}).get("rural_settlement", 0)),
            str(rank_counts["rural_settlement"]),
        )
    )

    baseline_totals = baseline_targets.get("building_totals", {})
    scaled_caps = baseline_targets.get("scaled_building_caps", {})
    if scaled_caps:
        report_rows.append(("cap_scale_global", "1.0000", f"{float(baseline_targets.get('building_cap_scale', 1.0)):.4f}"))
        report_rows.append(("cap_scale_fort", "1.0000", f"{float(baseline_targets.get('fort_cap_scale', 1.0)):.4f}"))
    for key in tracked:
        if scaled_caps:
            report_rows.append(
                (
                    f"cap_{key}",
                    str(max(0, _to_int(baseline_totals.get(key, 0)))),
                    str(max(0, _to_int(scaled_caps.get(key, 0)))),
                )
            )
        report_rows.append(
            (
                f"total_{key}",
                str(max(0, _to_int(baseline_totals.get(key, 0)))),
                str(max(0, _to_int(generated_totals.get(key, 0)))),
            )
        )

    for rank in ("city", "town", "rural_settlement"):
        count = rank_counts[rank]
        baseline_avg = baseline_targets.get("avg_by_rank", {}).get(rank, {})
        for key in tracked:
            iu_avg = (totals_by_rank[rank][key] / count) if count > 0 else 0.0
            report_rows.append(
                (
                    f"avg_{rank}_{key}",
                    f"{float(baseline_avg.get(key, 0.0)):.4f}",
                    f"{iu_avg:.4f}",
                )
            )

    report_path = mod_root / "tools" / "ir_to_eu5" / "iu_economy_balance_report.tsv"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        for row in report_rows:
            f.write("\t".join(row) + "\n")
    print_written("file", report_path)


def _write_town_setups_and_ranks(
    id_to_key: dict[int, str],
    location_keys: set[str],
    default_map: dict,
    coastal_land_locations: set[str],
    location_to_region: dict[str, str],
) -> None:
    location_keys = set(location_keys)
    rankable_locations = build_ir_rankable_locations(id_to_key, location_keys) & location_keys
    rankless_locations = location_keys - rankable_locations
    civilization_values = build_ir_civilization_values(id_to_key)

    economy_targets = _eu5_economy_targets()
    city_share_target = max(0.05, min(0.95, float(economy_targets.get("city_share", 0.25))))
    source_template_definitions = economy_targets.get("template_definitions", {})
    template_distribution = {
        key: Counter(value)
        for key, value in economy_targets.get("template_distribution", {}).items()
    }
    template_distribution_geo = {
        key: Counter(value)
        for key, value in economy_targets.get("template_distribution_geo", {}).items()
    }
    source_template_development = {
        key: float(value)
        for key, value in economy_targets.get("template_development", {}).items()
    }

    if not source_template_definitions:
        raise RuntimeError("EU5 baseline templates could not be loaded; cannot distribute baseline buildings.")

    # Tune EU5 template vectors down to a 304 BC intensity profile.
    template_definitions: dict[str, dict[str, int]] = {}
    template_development: dict[str, float] = {}
    for template_name, raw_buildings in source_template_definitions.items():
        raw_vector = {
            str(building_key): max(0, _to_int(level))
            for building_key, level in (raw_buildings or {}).items()
            if max(0, _to_int(level)) > 0
        }
        tuned_vector = _tune_template_vector_304bc(raw_vector)
        for fort_key in FORT_LIKE_BUILDINGS:
            tuned_vector.pop(fort_key, None)
        if not tuned_vector:
            fallback_order = (
                "marketplace",
                "temple",
                "granary",
                "mason",
                "slave_market",
                "dock",
            )
            chosen_key = next((key for key in fallback_order if key in raw_vector), None)
            if not chosen_key:
                chosen_key = sorted(raw_vector.keys())[0] if raw_vector else "granary"
            tuned_vector = {str(chosen_key): 1}

        template_definitions[str(template_name)] = tuned_vector

        raw_complexity = sum(raw_vector.values())
        tuned_complexity = sum(tuned_vector.values())
        source_dev = float(source_template_development.get(template_name, 0.0))
        if raw_complexity > 0 and tuned_complexity > 0:
            complexity_ratio = tuned_complexity / raw_complexity
            template_development[str(template_name)] = source_dev * (0.60 + 0.40 * complexity_ratio)
        elif tuned_complexity > 0:
            template_development[str(template_name)] = source_dev
        else:
            template_development[str(template_name)] = 0.0

    # Rank-specific target complexity to avoid overtuned low-tier settlements.
    rank_complexity_limit = {
        "city": 12,
        "town": 7,
        "rural_settlement": 4,
    }

    # Soft target for how many locations may end up fully empty after cap enforcement.
    max_empty_share = 0.08

    tracked_buildings = sorted(set(economy_targets.get("all_buildings", [])))
    baseline_building_caps = {
        str(key): max(0, _to_int(value))
        for key, value in economy_targets.get("building_totals", {}).items()
    }
    for building_key in tracked_buildings:
        baseline_building_caps.setdefault(building_key, 0)

    baseline_rank_counts = economy_targets.get("rank_counts", {})
    baseline_urban_count = max(
        0,
        _to_int(baseline_rank_counts.get("city", 0)) + _to_int(baseline_rank_counts.get("town", 0)),
    )
    baseline_rural_count = max(0, _to_int(baseline_rank_counts.get("rural_settlement", 0)))
    rural_per_urban = (baseline_rural_count / baseline_urban_count) if baseline_urban_count > 0 else 0.0

    target_rural_count = int(round(len(rankable_locations) * rural_per_urban))
    if baseline_rural_count > 0 and rankless_locations:
        target_rural_count = max(1, target_rural_count)
    target_rural_count = min(len(rankless_locations), max(0, target_rural_count))

    rural_candidates = sorted(
        rankless_locations,
        key=lambda k: (
            0 if k in coastal_land_locations else 1,
            -civilization_values.get(k, 0.0),
            k,
        ),
    )
    selected_rural_locations = set(rural_candidates[:target_rural_count])

    active_locations = sorted(rankable_locations | selected_rural_locations)

    baseline_total_locations = max(1, baseline_urban_count + baseline_rural_count)
    iu_total_locations = len(active_locations)
    location_coverage_scale = min(1.0, iu_total_locations / baseline_total_locations)

    # EU5 start covers substantially more world space than I:R scope; downscale caps accordingly.
    map_scope_scale = 0.70
    global_building_cap_scale = max(0.25, min(1.0, location_coverage_scale * map_scope_scale))

    # Fortification buildings are assigned directly in 07_cities_and_buildings building_manager.
    fort_cap_scale = 0.0
    fort_like_keys = set(FORT_LIKE_BUILDINGS)

    building_caps: dict[str, int] = {}
    for building_key, baseline_cap in baseline_building_caps.items():
        per_building_scale = float(BUILDING_CAP_SCALE_304BC.get(building_key, 0.70))
        scaled_cap = int(round(baseline_cap * global_building_cap_scale * per_building_scale))
        if building_key in fort_like_keys:
            scaled_cap = 0
        elif baseline_cap > 0:
            scaled_cap = max(1, scaled_cap)
        building_caps[building_key] = max(0, scaled_cap)

    direct_baseline_totals = {
        str(key): max(0, _to_int(value))
        for key, value in economy_targets.get("direct_building_totals", {}).items()
    }
    direct_fort_caps: dict[str, int] = {}
    for fort_key in ("castle", "stockade"):
        baseline_direct = max(0, _to_int(direct_baseline_totals.get(fort_key, 0)))
        if baseline_direct <= 0:
            baseline_direct = max(0, _to_int(baseline_building_caps.get(fort_key, 0)))
        fort_scale = float(DIRECT_FORT_SCALE_304BC.get(fort_key, 0.10))
        per_building_scale = float(BUILDING_CAP_SCALE_304BC.get(fort_key, 0.60))
        scaled = int(round(baseline_direct * global_building_cap_scale * per_building_scale * fort_scale))
        if baseline_direct > 0:
            scaled = max(1, scaled)
        direct_fort_caps[fort_key] = max(0, scaled)

    if direct_fort_caps.get("castle", 0) > 0 and direct_fort_caps.get("stockade", 0) > 0:
        direct_fort_caps["stockade"] = min(
            direct_fort_caps["stockade"],
            max(1, int(round(direct_fort_caps["castle"] * 0.35))),
        )

    economy_targets["scaled_building_caps"] = dict(building_caps)
    economy_targets["scaled_direct_fort_caps"] = dict(direct_fort_caps)
    economy_targets["building_cap_scale"] = float(global_building_cap_scale)
    economy_targets["fort_cap_scale"] = float(fort_cap_scale)

    print(
        "Economy building caps scaled: "
        + f"location_coverage={location_coverage_scale:.3f}, "
        + f"global_scale={global_building_cap_scale:.3f}, "
        + f"template_fort_scale={fort_cap_scale:.3f}, "
        + f"direct_castles={direct_fort_caps.get('castle', 0)}, "
        + f"direct_stockades={direct_fort_caps.get('stockade', 0)}"
    )

    ranked_urban = sorted(
        rankable_locations,
        key=lambda k: (civilization_values.get(k, 0.0), k),
        reverse=True,
    )
    target_city_count = int(round(len(ranked_urban) * city_share_target))
    if ranked_urban:
        target_city_count = max(1, min(len(ranked_urban), target_city_count))

    city_locations = set(ranked_urban[:target_city_count])

    rank_by_location: dict[str, str] = {}
    for loc_key in active_locations:
        if loc_key in city_locations:
            rank_by_location[loc_key] = "city"
        elif loc_key in rankable_locations:
            rank_by_location[loc_key] = "town"
        else:
            rank_by_location[loc_key] = "rural_settlement"

    development_rank_by_location: dict[str, str] = {}
    for loc_key in location_keys:
        if loc_key in city_locations:
            development_rank_by_location[loc_key] = "city"
        elif loc_key in rankable_locations:
            development_rank_by_location[loc_key] = "town"
        else:
            development_rank_by_location[loc_key] = "rural_settlement"

    iu_template_index = _load_location_template_index(iu_map_data / "location_templates.txt")
    geo_by_location = {
        loc_key: _location_geo_bucket(iu_template_index.get(loc_key, {}))
        for loc_key in location_keys
    }

    development_metrics = build_ir_development_metrics(id_to_key)
    raw_development = {
        loc_key: float(values.get("raw_score", 0.0))
        for loc_key, values in development_metrics.items()
    }
    eu5_development_by_rank = {
        rank: [float(value) for value in values]
        for rank, values in economy_targets.get("development_by_rank", {}).items()
    }

    raw_values_by_rank: dict[str, dict[str, float]] = {
        "city": {},
        "town": {},
        "rural_settlement": {},
    }
    for loc_key in location_keys:
        rank = development_rank_by_location.get(loc_key, "rural_settlement")
        fallback_raw = (civilization_values.get(loc_key, 0.0) / 100.0) * 6.0
        raw_values_by_rank[rank][loc_key] = float(raw_development.get(loc_key, fallback_raw))

    mapped_development: dict[str, float] = {}
    for rank in ("city", "town", "rural_settlement"):
        mapped = _map_values_to_reference_distribution(
            raw_values_by_rank[rank],
            eu5_development_by_rank.get(rank, []),
        )
        mapped_development.update(mapped)

    all_reference_values = sorted(
        value
        for values in eu5_development_by_rank.values()
        for value in values
    )
    default_development = all_reference_values[len(all_reference_values) // 2] if all_reference_values else 8.0
    for loc_key in location_keys:
        mapped_development.setdefault(loc_key, float(default_development))

    development_metric_report_path = mod_root / "tools" / "ir_to_eu5" / "iu_ir_development_metric_report.tsv"
    development_metric_report_path.parent.mkdir(parents=True, exist_ok=True)
    with development_metric_report_path.open("w", encoding="utf-8") as report:
        report.write(
            "location	development_rank	ir_province_rank	total_pop	weighted_pop	civilization_value	road_degree	building_levels	is_port	raw_score	mapped_target\n"
        )
        for loc_key in sorted(location_keys):
            metric = development_metrics.get(loc_key, {})
            report.write(
                "	".join(
                    [
                        loc_key,
                        development_rank_by_location.get(loc_key, "rural_settlement"),
                        str(metric.get("province_rank", "")),
                        f"{float(metric.get('total_pop', 0.0)):.3f}",
                        f"{float(metric.get('weighted_pop', 0.0)):.3f}",
                        f"{float(metric.get('civilization_value', civilization_values.get(loc_key, 0.0))):.3f}",
                        str(int(round(float(metric.get("road_degree", 0.0))))),
                        f"{float(metric.get('building_levels', 0.0)):.3f}",
                        str(int(round(float(metric.get("is_port", 0.0))))),
                        f"{float(raw_development.get(loc_key, 0.0)):.3f}",
                        f"{float(mapped_development.get(loc_key, default_development)):.3f}",
                    ]
                )
                + "\n"
            )
    print_written("file", development_metric_report_path)

    def scaled_template_counts(counter: Counter, target_total: int) -> Counter:
        if target_total <= 0 or not counter:
            return Counter()
        source_total = sum(counter.values())
        if source_total <= 0:
            return Counter()

        scaled = Counter()
        for template_name, value in counter.items():
            scaled[template_name] = int(round((value / source_total) * target_total))

        diff = target_total - sum(scaled.values())
        order = [name for name, _ in counter.most_common()]
        idx = 0
        while diff != 0 and order:
            key = order[idx % len(order)]
            if diff > 0:
                scaled[key] += 1
                diff -= 1
            elif scaled[key] > 0:
                scaled[key] -= 1
                diff += 1
            idx += 1

        return Counter({k: v for k, v in scaled.items() if v > 0})

    def pick_distribution(rank: str, geo_bucket: str, is_coastal: bool) -> Counter:
        geo_key = f"{rank}|{geo_bucket}"
        if geo_key in template_distribution_geo and template_distribution_geo[geo_key]:
            return template_distribution_geo[geo_key]

        direct_key = f"{rank}|{'coastal' if is_coastal else 'inland'}"
        any_key = f"{rank}|any"
        if direct_key in template_distribution and template_distribution[direct_key]:
            return template_distribution[direct_key]
        if any_key in template_distribution and template_distribution[any_key]:
            return template_distribution[any_key]
        for fallback_rank in ("town", "city", "rural_settlement"):
            fallback_any = f"{fallback_rank}|any"
            if fallback_any in template_distribution and template_distribution[fallback_any]:
                return template_distribution[fallback_any]
        return Counter({next(iter(template_definitions.keys())): 1})

    # Add deterministic low-intensity variants so cap enforcement can downgrade without emptying locations.
    base_template_names = sorted(template_definitions.keys())
    signature_to_template: dict[tuple[tuple[str, int], ...], str] = {}
    for template_name in base_template_names:
        signature = _setup_signature(template_definitions.get(template_name, {}))
        if signature:
            signature_to_template.setdefault(signature, template_name)

    def register_template_variant(
        base_template: str,
        suffix: str,
        vector: dict[str, int],
        dev_scale: float,
    ) -> str | None:
        cleaned = {k: max(0, _to_int(v)) for k, v in vector.items() if max(0, _to_int(v)) > 0}
        signature = _setup_signature(cleaned)
        if not signature:
            return None

        existing = signature_to_template.get(signature)
        if existing:
            return existing

        candidate_name = f"{base_template}__{suffix}"
        variant_name = candidate_name
        serial = 2
        while variant_name in template_definitions:
            variant_name = f"{candidate_name}_{serial}"
            serial += 1

        template_definitions[variant_name] = cleaned
        template_development[variant_name] = float(template_development.get(base_template, 0.0)) * dev_scale
        signature_to_template[signature] = variant_name
        return variant_name

    relief_drop_order = (
        "marketplace",
        "granary",
        "mason",
        "slave_market",
        "temple",
        "castle",
        "stockade",
        "dock",
    )
    for template_name in base_template_names:
        base_vector = {
            key: max(0, _to_int(level))
            for key, level in template_definitions.get(template_name, {}).items()
            if max(0, _to_int(level)) > 0
        }
        if not base_vector:
            continue

        register_template_variant(
            template_name,
            "l1",
            {key: 1 for key in base_vector.keys()},
            0.72,
        )

        for drop_key in relief_drop_order:
            if drop_key not in base_vector:
                continue
            reduced = {k: v for k, v in base_vector.items() if k != drop_key}
            register_template_variant(template_name, f"drop_{drop_key}", reduced, 0.74)

        for soften_key in ("marketplace", "granary", "mason", "slave_market"):
            if soften_key not in base_vector or base_vector[soften_key] <= 1:
                continue
            softened = dict(base_vector)
            softened[soften_key] = max(1, softened[soften_key] - 1)
            register_template_variant(template_name, f"soft_{soften_key}", softened, 0.80)

    core_fallback_templates = [
        ("ir_core_marketplace_1", {"marketplace": 1}, 0.26),
        ("ir_core_temple_1", {"temple": 1}, 0.24),
        ("ir_core_market_temple_1", {"marketplace": 1, "temple": 1}, 0.34),
        ("ir_core_granary_1", {"granary": 1}, 0.19),
        ("ir_core_mason_1", {"mason": 1}, 0.18),
        ("ir_core_slave_market_1", {"slave_market": 1}, 0.16),
    ]
    core_template_names: list[str] = []
    for preferred_name, vector, development_value in core_fallback_templates:
        signature = _setup_signature(vector)
        if not signature:
            continue

        existing = signature_to_template.get(signature)
        if existing:
            core_template_names.append(existing)
            continue

        template_name = preferred_name
        serial = 2
        while template_name in template_definitions:
            template_name = f"{preferred_name}_{serial}"
            serial += 1

        template_definitions[template_name] = dict(vector)
        template_development[template_name] = float(development_value)
        signature_to_template[signature] = template_name
        core_template_names.append(template_name)

    template_complexity = {
        name: sum(max(0, _to_int(level)) for level in buildings.values())
        for name, buildings in template_definitions.items()
    }

    location_building_setups: dict[str, str] = {}

    grouped_locations: dict[tuple[str, str, bool], list[str]] = defaultdict(list)
    for loc_key in active_locations:
        rank = rank_by_location[loc_key]
        geo_bucket = geo_by_location.get(loc_key, "inland|unknown|unknown|other")
        is_coastal = loc_key in coastal_land_locations
        grouped_locations[(rank, geo_bucket, is_coastal)].append(loc_key)

    for (rank, geo_bucket, is_coastal), locs in sorted(
        grouped_locations.items(),
        key=lambda item: (item[0][0], item[0][1], item[0][2]),
    ):
        source_counter = pick_distribution(rank, geo_bucket, is_coastal)
        complexity_cap = rank_complexity_limit.get(rank)
        if complexity_cap is not None:
            complexity_filtered = Counter(
                {
                    template_name: count
                    for template_name, count in source_counter.items()
                    if template_complexity.get(template_name, 0) <= complexity_cap
                }
            )
            if complexity_filtered:
                source_counter = complexity_filtered

        scaled_counter = scaled_template_counts(source_counter, len(locs))

        expanded_templates: list[str] = []
        for template_name, amount in scaled_counter.items():
            expanded_templates.extend([template_name] * amount)

        if len(expanded_templates) < len(locs):
            fallback_template = source_counter.most_common(1)[0][0]
            expanded_templates.extend([fallback_template] * (len(locs) - len(expanded_templates)))
        elif len(expanded_templates) > len(locs):
            expanded_templates = expanded_templates[: len(locs)]

        rank_complexity_bias = {
            "city": 1.00,
            "town": 0.58,
            "rural_settlement": 0.30,
        }.get(rank, 0.60)

        expanded_templates.sort(
            key=lambda name: (
                template_development.get(name, 0.0),
                template_complexity.get(name, 0) * rank_complexity_bias,
                source_counter.get(name, 0),
                name,
            ),
            reverse=True,
        )

        ordered_locs = sorted(
            locs,
            key=lambda k: (mapped_development.get(k, 0.0), civilization_values.get(k, 0.0), k),
            reverse=True,
        )

        for loc_key, template_name in zip(ordered_locs, expanded_templates):
            location_building_setups[loc_key] = template_name

    fallback_by_rank: dict[str, str] = {}
    for rank in ("city", "town", "rural_settlement"):
        any_key = f"{rank}|any"
        if any_key in template_distribution and template_distribution[any_key]:
            fallback_by_rank[rank] = template_distribution[any_key].most_common(1)[0][0]
    global_fallback = next(iter(template_definitions.keys()))

    for loc_key in active_locations:
        if loc_key in location_building_setups:
            continue
        rank = rank_by_location[loc_key]
        location_building_setups[loc_key] = fallback_by_rank.get(rank, global_fallback)

    empty_setup_name = "ir_tpl_empty"
    if empty_setup_name not in template_definitions:
        template_definitions[empty_setup_name] = {}
    template_development[empty_setup_name] = 0.0
    template_complexity[empty_setup_name] = 0

    template_vectors: dict[str, dict[str, int]] = {}
    for setup_name, buildings in template_definitions.items():
        vector: dict[str, int] = {}
        for building_key, level in buildings.items():
            parsed = max(0, _to_int(level))
            if parsed > 0:
                vector[str(building_key)] = parsed
        template_vectors[setup_name] = vector

    def compute_building_totals(assignments: dict[str, str]) -> Counter:
        totals: Counter = Counter()
        for setup_name in assignments.values():
            vector = template_vectors.get(setup_name, {})
            for building_key, level in vector.items():
                if building_key in building_caps:
                    totals[building_key] += level
        return totals

    def overage_sum(totals: Counter) -> int:
        return sum(
            max(0, totals.get(building_key, 0) - building_caps.get(building_key, 0))
            for building_key in tracked_buildings
        )

    all_templates_desc = sorted(
        (name for name in template_definitions.keys() if name != empty_setup_name),
        key=lambda name: (
            template_development.get(name, 0.0),
            template_complexity.get(name, 0),
            name,
        ),
        reverse=True,
    )

    candidate_cache: dict[tuple[str, str, bool], list[str]] = {}

    def candidate_templates(rank: str, geo_bucket: str, is_coastal: bool) -> list[str]:
        cache_key = (rank, geo_bucket, is_coastal)
        if cache_key in candidate_cache:
            return candidate_cache[cache_key]

        ordered: list[str] = []
        for source in (
            pick_distribution(rank, geo_bucket, is_coastal),
            template_distribution.get(f"{rank}|{'coastal' if is_coastal else 'inland'}", Counter()),
            template_distribution.get(f"{rank}|any", Counter()),
        ):
            for template_name, _ in source.most_common():
                if template_name in template_definitions:
                    ordered.append(template_name)

        ordered.extend(all_templates_desc)
        ordered.append(empty_setup_name)

        seen: set[str] = set()
        deduped: list[str] = []
        for template_name in ordered:
            if template_name in seen:
                continue
            seen.add(template_name)
            deduped.append(template_name)

        candidate_cache[cache_key] = deduped
        return deduped

    cap_enforced = False
    if tracked_buildings and building_caps:
        cap_enforced = True
        generated_totals = compute_building_totals(location_building_setups)
        current_overage = overage_sum(generated_totals)

        if current_overage > 0:
            rank_priority = {"rural_settlement": 0, "town": 1, "city": 2}
            downgrade_order = sorted(
                active_locations,
                key=lambda loc_key: (
                    rank_priority.get(rank_by_location.get(loc_key, "rural_settlement"), 0),
                    mapped_development.get(loc_key, 0.0),
                    civilization_values.get(loc_key, 0.0),
                    0 if loc_key not in coastal_land_locations else 1,
                    loc_key,
                ),
            )

            for _ in range(8):
                if current_overage <= 0:
                    break
                changed = False

                for loc_key in downgrade_order:
                    if current_overage <= 0:
                        break

                    current_setup = location_building_setups.get(loc_key)
                    if not current_setup or template_complexity.get(current_setup, 0) <= 0:
                        continue

                    current_vector = template_vectors.get(current_setup, {})
                    if not any(
                        current_vector.get(building_key, 0) > 0
                        and generated_totals.get(building_key, 0) > building_caps.get(building_key, 0)
                        for building_key in tracked_buildings
                    ):
                        continue

                    rank = rank_by_location.get(loc_key, "rural_settlement")
                    geo_bucket = geo_by_location.get(loc_key, "inland|unknown|unknown|other")
                    is_coastal = loc_key in coastal_land_locations

                    best_setup = None
                    best_overage = current_overage
                    best_development = -1e9
                    best_complexity = 10**9

                    for candidate_setup in candidate_templates(rank, geo_bucket, is_coastal):
                        if candidate_setup == current_setup:
                            continue
                        candidate_vector = template_vectors.get(candidate_setup, {})

                        affected = set(current_vector.keys()) | set(candidate_vector.keys())
                        next_overage = current_overage
                        for building_key in affected:
                            if building_key not in building_caps:
                                continue
                            old_total = generated_totals.get(building_key, 0)
                            old_over = max(0, old_total - building_caps[building_key])
                            new_total = (
                                old_total
                                - current_vector.get(building_key, 0)
                                + candidate_vector.get(building_key, 0)
                            )
                            next_overage += max(0, new_total - building_caps[building_key]) - old_over

                        candidate_dev = template_development.get(candidate_setup, 0.0)
                        candidate_comp = template_complexity.get(candidate_setup, 0)
                        candidate_is_empty = 1 if candidate_setup == empty_setup_name else 0

                        should_take = False
                        if next_overage < best_overage:
                            should_take = True
                        elif next_overage == best_overage:
                            if best_setup is None:
                                should_take = True
                            else:
                                best_is_empty = 1 if best_setup == empty_setup_name else 0
                                if candidate_is_empty < best_is_empty:
                                    should_take = True
                                elif candidate_is_empty == best_is_empty:
                                    if rank == "city":
                                        if candidate_dev > best_development:
                                            should_take = True
                                        elif candidate_dev == best_development and candidate_comp < best_complexity:
                                            should_take = True
                                    else:
                                        if candidate_comp < best_complexity:
                                            should_take = True
                                        elif candidate_comp == best_complexity and candidate_dev > best_development:
                                            should_take = True

                        if should_take:
                            best_setup = candidate_setup
                            best_overage = next_overage
                            best_development = candidate_dev
                            best_complexity = candidate_comp

                    if best_setup is None or best_overage >= current_overage:
                        continue

                    best_vector = template_vectors.get(best_setup, {})
                    for building_key in set(current_vector.keys()) | set(best_vector.keys()):
                        if building_key not in building_caps:
                            continue
                        generated_totals[building_key] = (
                            generated_totals.get(building_key, 0)
                            - current_vector.get(building_key, 0)
                            + best_vector.get(building_key, 0)
                        )

                    location_building_setups[loc_key] = best_setup
                    current_overage = best_overage
                    changed = True

                if not changed:
                    break

            if current_overage > 0:
                for loc_key in downgrade_order:
                    if current_overage <= 0:
                        break

                    current_setup = location_building_setups.get(loc_key)
                    if not current_setup or template_complexity.get(current_setup, 0) <= 0:
                        continue

                    current_vector = template_vectors.get(current_setup, {})
                    if not any(
                        current_vector.get(building_key, 0) > 0
                        and generated_totals.get(building_key, 0) > building_caps.get(building_key, 0)
                        for building_key in tracked_buildings
                    ):
                        continue

                    for building_key, level in current_vector.items():
                        if building_key in building_caps:
                            generated_totals[building_key] = max(
                                0,
                                generated_totals.get(building_key, 0) - level,
                            )

                    location_building_setups[loc_key] = empty_setup_name
                    current_overage = overage_sum(generated_totals)

        target_empty_count = int(round(len(active_locations) * max_empty_share))
        current_empty_locations = [
            loc_key
            for loc_key in active_locations
            if template_complexity.get(location_building_setups.get(loc_key, ""), 0) <= 0
        ]
        if len(current_empty_locations) > target_empty_count:
            refill_candidates = sorted(
                current_empty_locations,
                key=lambda loc_key: (
                    mapped_development.get(loc_key, 0.0),
                    civilization_values.get(loc_key, 0.0),
                    loc_key,
                ),
                reverse=True,
            )

            for loc_key in refill_candidates:
                current_empty_count = sum(
                    1
                    for key in active_locations
                    if template_complexity.get(location_building_setups.get(key, ""), 0) <= 0
                )
                if current_empty_count <= target_empty_count:
                    break

                rank = rank_by_location.get(loc_key, "rural_settlement")
                geo_bucket = geo_by_location.get(loc_key, "inland|unknown|unknown|other")
                is_coastal = loc_key in coastal_land_locations

                options = [name for name in core_template_names if template_complexity.get(name, 0) > 0]
                options.extend(
                    [
                        name
                        for name in candidate_templates(rank, geo_bucket, is_coastal)
                        if name != empty_setup_name and template_complexity.get(name, 0) > 0
                    ]
                )

                deduped_options: list[str] = []
                seen_options: set[str] = set()
                for name in options:
                    if name in seen_options:
                        continue
                    seen_options.add(name)
                    deduped_options.append(name)
                options = deduped_options

                options.sort(
                    key=lambda name: (
                        0 if name in core_template_names else 1,
                        template_complexity.get(name, 0),
                        -template_development.get(name, 0.0),
                        name,
                    )
                )

                for candidate_setup in options:
                    candidate_vector = template_vectors.get(candidate_setup, {})
                    if not candidate_vector:
                        continue
                    if any(
                        building_key in building_caps
                        and generated_totals.get(building_key, 0) + level > building_caps.get(building_key, 0)
                        for building_key, level in candidate_vector.items()
                    ):
                        continue

                    location_building_setups[loc_key] = candidate_setup
                    for building_key, level in candidate_vector.items():
                        if building_key in building_caps:
                            generated_totals[building_key] = generated_totals.get(building_key, 0) + level
                    break

        over_cap_buildings = [
            key
            for key in tracked_buildings
            if generated_totals.get(key, 0) > building_caps.get(key, 0)
        ]
        if over_cap_buildings:
            print(
                "Economy cap enforcement warning: "
                + str(len(over_cap_buildings))
                + " building types still exceed EU5 baseline totals."
            )
        else:
            built_locations = sum(
                1
                for setup_name in location_building_setups.values()
                if template_complexity.get(setup_name, 0) > 0
            )
            print(
                "Economy cap enforcement: all building totals are within EU5 baseline caps; "
                + str(built_locations)
                + " / "
                + str(len(location_building_setups))
                + " locations retain non-empty setups."
            )

    if not cap_enforced:
        print("Economy cap enforcement skipped: EU5 baseline building totals unavailable.")
        generated_totals = compute_building_totals(location_building_setups)

    baseline_assignment_total = max(1, baseline_urban_count + baseline_rural_count)
    target_assigned_locations = int(round(baseline_assignment_total * 0.62))
    target_assigned_locations = max(500, min(700, target_assigned_locations))
    target_assigned_locations = min(target_assigned_locations, len(active_locations))

    def setup_is_non_empty(setup_name: str | None) -> bool:
        if not setup_name:
            return False
        return template_complexity.get(setup_name, 0) > 0

    def can_fit_setup(setup_name: str) -> bool:
        vector = template_vectors.get(setup_name, {})
        if not vector:
            return False
        return not any(
            building_key in building_caps
            and generated_totals.get(building_key, 0) + level > building_caps.get(building_key, 0)
            for building_key, level in vector.items()
        )

    assigned_locations = [
        loc_key
        for loc_key in active_locations
        if setup_is_non_empty(location_building_setups.get(loc_key))
    ]

    if len(assigned_locations) < target_assigned_locations:
        refill_order = sorted(
            [loc_key for loc_key in active_locations if loc_key not in set(assigned_locations)],
            key=lambda loc_key: (
                mapped_development.get(loc_key, 0.0),
                civilization_values.get(loc_key, 0.0),
                loc_key,
            ),
            reverse=True,
        )

        for loc_key in refill_order:
            if len(assigned_locations) >= target_assigned_locations:
                break

            rank = rank_by_location.get(loc_key, "rural_settlement")
            geo_bucket = geo_by_location.get(loc_key, "inland|unknown|unknown|other")
            is_coastal = loc_key in coastal_land_locations

            options = [name for name in core_template_names if setup_is_non_empty(name)]
            options.extend(
                [
                    name
                    for name in candidate_templates(rank, geo_bucket, is_coastal)
                    if setup_is_non_empty(name)
                ]
            )

            seen_options: set[str] = set()
            deduped_options: list[str] = []
            for name in options:
                if name in seen_options:
                    continue
                seen_options.add(name)
                deduped_options.append(name)

            deduped_options.sort(
                key=lambda name: (
                    0 if name in core_template_names else 1,
                    template_complexity.get(name, 0),
                    -template_development.get(name, 0.0),
                    name,
                )
            )

            for candidate_setup in deduped_options:
                if not can_fit_setup(candidate_setup):
                    continue
                location_building_setups[loc_key] = candidate_setup
                for building_key, level in template_vectors.get(candidate_setup, {}).items():
                    if building_key in building_caps:
                        generated_totals[building_key] = generated_totals.get(building_key, 0) + level
                assigned_locations.append(loc_key)
                break

    elif len(assigned_locations) > target_assigned_locations:
        prune_order = sorted(
            assigned_locations,
            key=lambda loc_key: (
                mapped_development.get(loc_key, 0.0),
                civilization_values.get(loc_key, 0.0),
                loc_key,
            ),
        )

        for loc_key in prune_order:
            if len(assigned_locations) <= target_assigned_locations:
                break
            setup_name = location_building_setups.get(loc_key)
            if not setup_is_non_empty(setup_name):
                continue
            for building_key, level in template_vectors.get(setup_name, {}).items():
                if building_key in building_caps:
                    generated_totals[building_key] = max(0, generated_totals.get(building_key, 0) - level)
            location_building_setups[loc_key] = empty_setup_name
            assigned_locations.pop(assigned_locations.index(loc_key))

    # Keep 07_cities_and_buildings sparse like EU5: only emit non-empty assigned locations.
    location_building_setups = {
        loc_key: setup_name
        for loc_key, setup_name in location_building_setups.items()
        if setup_is_non_empty(setup_name)
    }
    active_locations = sorted(location_building_setups.keys())

    print(
        "Economy assignment targeting: "
        + str(len(active_locations))
        + " / "
        + str(len(rankable_locations | selected_rural_locations))
        + " locations kept (target "
        + str(target_assigned_locations)
        + ")"
    )

    def region_profile_for_location(loc_key: str) -> str:
        raw_region = to_region_key(location_to_region.get(loc_key, "")) if location_to_region.get(loc_key) else ""
        stem = raw_region[:-7] if raw_region.endswith("_region") else raw_region
        stem = re.sub(r"[^a-z0-9_]+", "_", stem.lower()).strip("_")

        if not stem:
            return "frontier"

        alias_by_keyword = {
            "greece": "greek",
            "hellas": "greek",
            "aegean": "greek",
            "thrace": "greek",
            "macedon": "greek",
            "anatolia": "anatolian",
            "asia_minor": "anatolian",
            "italy": "italic",
            "iberia": "iberian",
            "france": "gaulish",
            "gaul": "gaulish",
            "britain": "britannic",
            "scandinav": "nordic",
            "german": "germanic",
            "balkan": "illyrian",
            "illyria": "illyrian",
            "egypt": "egyptian",
            "nubia": "nubian",
            "maghreb": "numidian",
            "africa": "numidian",
            "levant": "levantine",
            "mesopot": "mesopotamian",
            "assyria": "mesopotamian",
            "babyl": "mesopotamian",
            "persia": "persian",
            "iran": "persian",
            "arabia": "arabian",
            "caucas": "caucasian",
            "india": "indian",
            "sindh": "indian",
            "gandhara": "indian",
            "steppe": "scythian",
            "scyth": "scythian",
            "sarmatia": "scythian",
            "bactria": "bactrian",
        }
        for keyword, alias in alias_by_keyword.items():
            if keyword in stem:
                return alias

        stem = re.sub(r"(north|south|east|west|upper|lower)", "", stem)
        stem = re.sub(r"_+", "_", stem).strip("_")
        return stem or "frontier"

    regional_setup_definitions: dict[str, dict[str, int]] = {}
    regional_location_setups: dict[str, str] = {}
    regional_name_counts: Counter = Counter()
    regional_key_to_name: dict[tuple[str, tuple[tuple[str, int], ...]], str] = {}

    for loc_key in sorted(location_building_setups.keys()):
        source_setup = location_building_setups[loc_key]
        source_vector = {
            str(key): max(0, _to_int(level))
            for key, level in template_definitions.get(source_setup, {}).items()
            if max(0, _to_int(level)) > 0
        }

        rank = rank_by_location.get(loc_key, "town")
        profile = region_profile_for_location(loc_key)

        for fort_key in fort_like_keys:
            source_vector.pop(fort_key, None)
        if not source_vector:
            source_vector = {"granary": 1}

        signature = _setup_signature(source_vector)
        if not signature:
            continue

        coastal_suffix = "_coastal" if loc_key in coastal_land_locations else ""
        base_name = f"ir_{profile}_{rank}{coastal_suffix}"

        regional_key = (base_name, signature)
        setup_name = regional_key_to_name.get(regional_key)
        if not setup_name:
            regional_name_counts[base_name] += 1
            serial = regional_name_counts[base_name]
            setup_name = base_name if serial == 1 else f"{base_name}_{serial:02d}"
            regional_key_to_name[regional_key] = setup_name
            regional_setup_definitions[setup_name] = {key: level for key, level in signature}

        regional_location_setups[loc_key] = setup_name

    location_building_setups = regional_location_setups
    setup_definitions = regional_setup_definitions

    if not setup_definitions:
        setup_definitions = {"ir_frontier_town": {"granary": 1}}

    town_setups_dir = mod_root / "in_game" / "common" / "town_setups"
    town_setups_dir.mkdir(parents=True, exist_ok=True)
    town_setups_path = town_setups_dir / "ir_location_setups.txt"
    _write_town_setups_file(town_setups_path, setup_definitions)

    rank_lines: dict[str, str] = {}
    for loc_key in active_locations:
        rank = rank_by_location[loc_key]
        setup = location_building_setups[loc_key]
        rank_lines[loc_key] = f"rank = {rank} town_setup = {setup}"

    country_locations_for_forts = extract_ir_country_locations()
    location_owner_by_key: dict[str, str] = {}
    for tag, prov_ids in country_locations_for_forts.items():
        tag_key = str(tag).strip()
        for prov_id in (prov_ids or []):
            loc_key = id_to_key.get(_to_int(prov_id))
            if loc_key:
                location_owner_by_key[loc_key] = tag_key

    fort_candidates = set(location_keys)

    requested_castle_locations = [
        loc_key
        for loc_key in PROMINENT_CASTLE_LOCATIONS_304BC
        if loc_key in fort_candidates
    ]
    requested_castle_set = set(requested_castle_locations)

    requested_stockade_locations = [
        loc_key
        for loc_key in PROMINENT_STOCKADE_LOCATIONS_304BC
        if loc_key in fort_candidates and loc_key not in requested_castle_set
    ]

    requested_forts: list[tuple[str, str, str]] = []
    requested_forts.extend(
        ("castle", loc_key, CASTLE_RATIONALE_304BC.get(loc_key, ""))
        for loc_key in requested_castle_locations
    )
    requested_forts.extend(
        ("stockade", loc_key, STOCKADE_RATIONALE_304BC.get(loc_key, ""))
        for loc_key in requested_stockade_locations
    )

    verified_forts: list[tuple[str, str, str, str]] = []
    verification_rows: list[tuple[str, str, str, str, str, str]] = []
    seen_locations: set[str] = set()

    for building_key, loc_key, rationale in requested_forts:
        owner_tag = str(location_owner_by_key.get(loc_key, "")).strip()
        status = "ok"

        if loc_key in seen_locations:
            status = "duplicate_location_dropped"
            verification_rows.append((building_key, loc_key, "", owner_tag, status, rationale))
            continue

        if not owner_tag:
            status = "missing_owner_dropped"
            verification_rows.append((building_key, loc_key, "", owner_tag, status, rationale))
            continue

        if not re.fullmatch(r"[A-Z0-9_]{2,8}", owner_tag):
            status = "invalid_owner_tag_dropped"
            verification_rows.append((building_key, loc_key, "", owner_tag, status, rationale))
            continue

        seen_locations.add(loc_key)
        verified_forts.append((building_key, loc_key, owner_tag, rationale))
        verification_rows.append((building_key, loc_key, owner_tag, owner_tag, status, rationale))

    castle_locations = [loc_key for building_key, loc_key, _, _ in verified_forts if building_key == "castle"]
    stockade_locations = [loc_key for building_key, loc_key, _, _ in verified_forts if building_key == "stockade"]

    direct_building_levels = {
        "castle": len(castle_locations),
        "stockade": len(stockade_locations),
    }

    building_manager_lines: list[str] = []
    for building_key, loc_key, owner_tag, _ in verified_forts:
        building_manager_lines.append(
            f"{building_key} = {{ tag = {owner_tag} level = 1 location = {loc_key} }}"
        )

    fort_verify_report = mod_root / "tools" / "ir_to_eu5" / "iu_fort_assignment_verification.tsv"
    fort_verify_report.parent.mkdir(parents=True, exist_ok=True)
    with fort_verify_report.open("w", encoding="utf-8") as f:
        f.write("building\tlocation\tassigned_tag\texpected_owner\tstatus\trationale\n")
        for row in verification_rows:
            f.write("\t".join(row) + "\n")
    print_written("file", fort_verify_report)

    dropped_forts = sum(1 for _, _, _, _, status, _ in verification_rows if status != "ok")
    print(
        "Economy direct fort assignment (manual-only, verified): "
        + f"castles={len(castle_locations)}, "
        + f"stockades={len(stockade_locations)}, "
        + f"dropped={dropped_forts}"
    )

    development_rules = _base_development_rules()

    def _fmt_num(value: float) -> str:
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:.3f}".rstrip("0").rstrip(".")

    rule_order = [
        "base",
        "coastal",
        "river",
        "road",
        "city",
        "town",
        "grasslands",
        "farmland",
        "sparse",
        "forest",
        "woods",
        "desert",
        "jungle",
        "tropical",
        "subtropical",
        "oceanic",
        "arid",
        "cold_arid",
        "mediterranean",
        "continental",
        "arctic",
        "flatland",
        "mountains",
        "hills",
        "plateau",
        "wetlands",
    ]

    development_lines = [f"{key} = {_fmt_num(float(development_rules[key]))}" for key in rule_order]

    base_components: dict[str, float] = {}
    target_values: dict[str, float] = {}
    raw_delta_by_location: dict[str, float] = {}
    region_score_samples: dict[str, list[float]] = defaultdict(list)

    for loc_key in sorted(location_keys):
        rank = development_rank_by_location.get(loc_key)
        info = iu_template_index.get(loc_key, {})
        base_component = _location_development_components(info, rank, development_rules)
        target_value = float(mapped_development.get(loc_key, base_component))
        delta = target_value - base_component
        base_components[loc_key] = base_component
        target_values[loc_key] = target_value
        raw_delta_by_location[loc_key] = delta
        raw_region_tag = location_to_region.get(loc_key)
        region_tag = to_region_key(raw_region_tag) if raw_region_tag else None
        if region_tag:
            region_score_samples[region_tag].append(raw_development.get(loc_key, target_value))

    eu5_dev_path = eu5_game / "main_menu" / "setup" / "start" / "14_development.txt"
    eu5_region_reference: list[float] = []
    eu5_region_values_by_key: dict[str, float] = {}
    eu5_area_reference: list[float] = []
    eu5_special_reference: list[float] = []
    if eu5_dev_path.exists():
        try:
            eu5_dev_tree = parse_tree(eu5_dev_path)
            dev_block = _tree_block(eu5_dev_tree["development"]) if "development" in eu5_dev_tree else None
            if isinstance(dev_block, (_pydt.Tree, dict)):
                for raw_key, raw_value in dev_block.items():
                    key = str(raw_key)
                    if key in rule_order:
                        continue
                    val = _to_float(raw_value, default=float("nan"))
                    if math.isnan(val):
                        continue
                    if key.endswith("_region"):
                        eu5_region_reference.append(val)
                        eu5_region_values_by_key[key] = val
                    elif key.endswith("_area"):
                        eu5_area_reference.append(val)
                    elif not key.endswith("_province"):
                        eu5_special_reference.append(val)
        except Exception:
            eu5_region_reference = []
            eu5_region_values_by_key = {}
            eu5_area_reference = []
            eu5_special_reference = []

    if not eu5_region_reference:
        eu5_region_reference = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
    if not eu5_area_reference:
        eu5_area_reference = [-10.0, -5.0, -3.0, 0.0, 3.0, 5.0, 7.0]
    if not eu5_special_reference:
        eu5_special_reference = [-5.0, -3.0, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]

    region_source_scores: dict[str, float] = {
        region_tag: (sum(scores) / len(scores))
        for region_tag, scores in region_score_samples.items()
        if scores
    }
    mapped_region_values = _map_values_to_reference_distribution(
        region_source_scores,
        sorted(eu5_region_reference),
    )

    region_delta_by_tag: dict[str, int] = {}
    region_score_mean = (
        (sum(region_source_scores.values()) / len(region_source_scores))
        if region_source_scores
        else 0.0
    )
    region_global_boost = 10
    preferred_region_values: dict[str, int] = {
        # --- India (highest densities west of China in 304 BC) ---
        "madhyadesa_region": 30,
        "bengal_region": 29,
        "hindustan_region": 28,
        "avanti_region": 27,
        "dravida_region": 27,
        "gandhara_region": 27,
        "karnata_region": 26,

        # --- Nile (very high, but still below Gangetic plain) ---
        "lower_egypt_region": 28,
        "egypt_region": 27,
        "upper_egypt_region": 20,
        "nubia_region": 13,
        "ethiopia_region": 12,
        "punt_region": 11,

        # --- Mesopotamia / Iran plateau (high bureaucratic agrarian cores) ---
        "mesopotamia_region": 27,
        "assyria_region": 23,
        "media_region": 24,
        "persis_region": 24,
        "parthia_region": 21,
        "khorasan_region": 18,

        # --- Levant / Fertile Crescent / Syria (trade + administration + constant war) ---
        "syria_region": 27,
        "crescent_region": 22,
        "palestine_region": 21,
        "cilicia_region": 21,
        "arabia_felix_region": 18,
        "arabia_region": 14,

        # --- Hellenic world (dense urban coasts; should feel richer than Italy) ---
        "greece_region": 26,
        "macedonia_region": 20,
        "thrace_region": 19,
        "anatolia_region": 23,
        "bithynia_region": 20,
        "colchis_region": 16,

        # --- North Africa / Carthaginian sphere (strong coastal, weak interior) ---
        "cyrenaica_region": 17,
        "maghreb_region": 18,
        "numidia_region": 14,
        "mauretainia_region": 10,
        "africa_region": 15,

        # --- Italy (rising, organized, but not the dense core yet) ---
        "italy_region": 18,
        "central_italy_region": 20,
        "magna_graecia_region": 21,

        # --- Iberia (moderate; pockets of strength, not fully urbanized) ---
        "iberia_region": 15,
        "baetica_region": 16,
        "tarraconensis_region": 12,
        "lusitania_region": 10,

        # --- Gaul (lower density; proto-urban pockets only) ---
        "france_region": 13,
        "transalpine_gaul_region": 11,
        "central_gaul_region": 10,
        "aquitaine_region": 9,
        "armorica_region": 9,
        "belgica_region": 8,

        # --- Britain & North (very low in 304 BC) ---
        "great_britain_region": 7,
        "britain_region": 6,
        "scandinavian_region": 5,
        "baltic_region": 6,

        # --- Germania (sparse, decentralized) ---
        "south_german_region": 8,
        "north_german_region": 7,
        "germania_superior_region": 6,

        # --- Balkans / inland Europe (moderate-low) ---
        "illyria_region": 10,
        "carpathia_region": 8,
        "pannonia_region": 7,

        # --- Steppe / Crimea (strategic, mobile, low settlement density) ---
        "steppes_region": 6,
        "taurica_region": 7,

        # --- Mountains / high plateau (routes, not population cores) ---
        "tibet_region": 4,
        "himalayan_region": 3,
    }


    for region_tag, value in sorted(mapped_region_values.items()):
        forced_value = preferred_region_values.get(region_tag)
        if forced_value is not None:
            rounded = int(forced_value)
        else:
            eu5_base_value = eu5_region_values_by_key.get(region_tag)
            if eu5_base_value is not None:
                # Emulate EU5 regional baseline directly, then apply requested global uplift.
                rounded = int(round(eu5_base_value))
            else:
                rounded = int(round(value))
                if region_score_mean > 0.0:
                    relative_strength = region_source_scores.get(region_tag, region_score_mean) / region_score_mean
                    # I:R regions are denser than full-world EU5 coverage; scale stronger regions up modestly.
                    dynamic_uplift = max(0, min(5, int(round((relative_strength - 0.86) * 6.0))))
                    rounded = min(35, rounded + dynamic_uplift)
                rounded += region_global_boost
        if rounded == 0:
            continue
        region_delta_by_tag[region_tag] = rounded
        development_lines.append(f"{region_tag} = {rounded}")

    for region_tag, forced_value in sorted(preferred_region_values.items()):
        if region_tag in region_delta_by_tag:
            continue
        region_delta_by_tag[region_tag] = int(forced_value)
        development_lines.append(f"{region_tag} = {int(forced_value)}")
    # Assign per-location overrides purely from I:R-derived development signals.
    candidate_locations = sorted(active_locations)

    capital_id_by_tag = _ir_country_capitals()
    capital_location_to_tag: dict[str, str] = {}
    for tag, capital_id in capital_id_by_tag.items():
        loc_key = id_to_key.get(capital_id)
        if loc_key:
            capital_location_to_tag[loc_key] = str(tag)

    country_location_counts = {
        str(tag): len(locations)
        for tag, locations in extract_ir_country_locations().items()
        if isinstance(locations, list)
    }

    metric_source_scores: dict[str, float] = {}
    for loc_key in candidate_locations:
        rank = development_rank_by_location.get(loc_key, "rural_settlement")
        raw_region_tag = location_to_region.get(loc_key, "")
        region_tag = to_region_key(raw_region_tag) if raw_region_tag else ""

        raw_score = raw_development.get(loc_key, target_values.get(loc_key, 0.0))
        region_average = region_source_scores.get(region_tag, raw_score)
        local_exception = raw_score - region_average

        province_rank_text = str(
            development_metrics.get(loc_key, {}).get("province_rank", "")
        ).lower()
        metropolis_bonus = 0.0
        if "metropolis" in province_rank_text:
            metropolis_bonus = 2.0
        elif province_rank_text == "city":
            metropolis_bonus = 0.4

        capital_bonus = 0.0
        capital_tag = capital_location_to_tag.get(loc_key, "")
        if capital_tag:
            country_size = country_location_counts.get(capital_tag, 0)
            # Use only I:R country size data to bias notable state capitals upward.
            capital_bonus = min(3.6, 0.90 * math.log1p(max(1, country_size)))

        metric_source_scores[loc_key] = (
            (0.78 * raw_score)
            + (0.22 * local_exception)
            + (0.60 * rank_priority.get(rank, 0))
            + metropolis_bonus
            + capital_bonus
        )

    max_special_overrides = min(100, len(candidate_locations))
    positive_special_reference = sorted(value for value in eu5_special_reference if value > 0)
    positive_area_reference = sorted(value for value in eu5_area_reference if value > 0)
    if not positive_special_reference:
        positive_special_reference = [1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
    if not positive_area_reference:
        positive_area_reference = [1.0, 3.0, 5.0, 7.0]

    selected_keys = sorted(
        candidate_locations,
        key=lambda key: (metric_source_scores.get(key, 0.0), key),
        reverse=True,
    )[:max_special_overrides]

    selected_scores = {
        loc_key: metric_source_scores.get(loc_key, 0.0) for loc_key in selected_keys
    }
    score_min = min(selected_scores.values()) if selected_scores else 0.0
    score_max = max(selected_scores.values()) if selected_scores else 1.0
    score_span = max(1e-9, score_max - score_min)

    eu5_region_sorted = sorted(eu5_region_reference)
    region_q3 = eu5_region_sorted[int(0.75 * (len(eu5_region_sorted) - 1))] if eu5_region_sorted else 25.0
    special_cap = int(
        round(
            min(
                24.0,
                max(
                    12.0,
                    max(positive_special_reference)
                    + max(positive_area_reference)
                    + (0.25 * region_q3),
                ),
            )
        )
    )
    special_floor = 2

    override_rows: list[dict[str, str]] = []
    selected_special = 0
    for loc_key in selected_keys:
        score = selected_scores.get(loc_key, score_min)
        normalized = (score - score_min) / score_span
        # Convex scaling gives the very top I:R urban hubs a stronger boost.
        mapped_value = special_floor + ((special_cap - special_floor) * (normalized ** 0.72))
        final_delta = max(special_floor, int(round(mapped_value)))
        development_lines.append(f"{loc_key} = {final_delta}")
        selected_special += 1

        raw_region_tag = location_to_region.get(loc_key, "")
        region_tag = to_region_key(raw_region_tag) if raw_region_tag else ""
        override_rows.append(
            {
                "location": loc_key,
                "development_rank": development_rank_by_location.get(loc_key, "rural_settlement"),
                "region": region_tag,
                "region_modifier": str(region_delta_by_tag.get(region_tag, 0)),
                "target_value": f"{target_values.get(loc_key, 0.0):.3f}",
                "metric_score": f"{metric_source_scores.get(loc_key, 0.0):.3f}",
                "mapped_value": f"{mapped_value:.3f}",
                "final_override": str(final_delta),
            }
        )

    override_rows_sorted = sorted(
        override_rows,
        key=lambda row: (
            int(row["final_override"]),
            float(row["metric_score"]),
            row["location"],
        ),
        reverse=True,
    )

    overrides_report_path = mod_root / "tools" / "ir_to_eu5" / "iu_location_development_overrides.tsv"
    overrides_report_path.parent.mkdir(parents=True, exist_ok=True)
    with overrides_report_path.open("w", encoding="utf-8") as f:
        f.write(
            "location	development_rank	region	region_modifier	target_value	metric_score	mapped_value	final_override\n"
        )
        for row in override_rows_sorted:
            f.write(
                "	".join(
                    [
                        row["location"],
                        row["development_rank"],
                        row["region"],
                        row["region_modifier"],
                        row["target_value"],
                        row["metric_score"],
                        row["mapped_value"],
                        row["final_override"],
                    ]
                )
                + "\n"
            )
    print_written("file", overrides_report_path)

    print(
        "Development special overrides: assigned "
        + str(selected_special)
        + " data-driven location overrides."
    )

    development_path = mod_root / "main_menu" / "setup" / "start" / "14_development.txt"
    write_blocks(development_path, [("development", development_lines)], encoding="utf-8")

    print(
        "Economy calibration: active_locations="
        + str(len(active_locations))
        + ", promoted "
        + str(len(city_locations))
        + " urban locations to city rank (target city share "
        + f"{city_share_target:.3f}), selected "
        + str(len(selected_rural_locations))
        + " rural locations (target "
        + str(target_rural_count)
        + ")"
    )

    _write_economy_balance_report(
        economy_targets,
        rank_lines,
        location_building_setups,
        setup_definitions,
        direct_building_levels,
    )

    rank_blocks = [(loc_key, [rank_lines[loc_key]]) for loc_key in sorted(rank_lines.keys())]
    cities_blocks: list[tuple[str, list[object]]] = [("locations", rank_blocks)]
    if building_manager_lines:
        cities_blocks.append(("building_manager", building_manager_lines))
    write_blocks(
        iu_setup_start / "07_cities_and_buildings.txt",
        cities_blocks,
        encoding="utf-8",
    )


def _write_markets_file(
    id_to_key: dict[int, str],
    location_keys: set[str],
    default_map: dict,
    location_to_region: dict[str, str],
) -> None:
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
        min_markets=90,
    )
    _write_assignment_block(
        markets_dst,
        "market_manager",
        [f"	add_market = {key}" for key in markets],
        encoding="utf-8",
    )


def _write_roads_file(
    id_to_key: dict[int, str],
    location_keys: set[str],
    default_map: dict,
) -> None:
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
        road_lines.append(f"	{a_key} = {b_key}")

    _write_assignment_block(roads_dst, "road_network", road_lines, encoding="utf-8")


def _filter_start_setup_content(
    location_keys: set[str],
    area_keys: set[str],
    region_keys: set[str],
    continent_keys: set[str],
    subcontinent_keys: set[str],
) -> None:
    explor_src = eu5_game / "main_menu" / "setup" / "start" / "17_exploration_preferences.txt"
    explor_dst = mod_root / "main_menu" / "setup" / "start" / "17_exploration_preferences.txt"
    if explor_src.exists():
        lines = _filter_exploration_preferences_text(
            explor_src.read_text(encoding="utf-8-sig").splitlines(),
            area_keys=area_keys,
            region_keys=region_keys,
            continent_keys=continent_keys,
            subcontinent_keys=subcontinent_keys,
        )
        _write_text_file(explor_dst, "\n".join(lines) + "\n", encoding="utf-8")

    loc_src = eu5_game / "main_menu" / "setup" / "start" / "21_locations.txt"
    loc_dst = mod_root / "main_menu" / "setup" / "start" / "21_locations.txt"
    if loc_src.exists():
        tree = parse_tree(loc_src)
        filtered = _filter_tree_entries_by_tags(tree, location_keys, root_key="locations")
        write_blocks(loc_dst, filtered)

    colonies_dst = mod_root / "main_menu" / "setup" / "start" / "23_colonies.txt"
    colonies_tree = _pydt.Tree()
    colonies_tree["colony_manager"] = _pydt.Tree()
    write_blocks(colonies_dst, colonies_tree)


def _write_start_setup_content(
    id_to_key: dict[int, str],
    location_keys: set[str],
    default_map: dict,
    location_to_region: dict[str, str],
    area_keys: set[str],
    region_keys: set[str],
    continent_keys: set[str],
    subcontinent_keys: set[str],
    coastal_land_locations: set[str],
) -> None:
    _copy_filtered_location_start_files(location_keys)

    pops_by_location = _write_pops_file(id_to_key)
    _write_institutions_file(pops_by_location, default_map)
    _write_town_setups_and_ranks(
        id_to_key,
        set(pops_by_location.keys()),
        default_map,
        coastal_land_locations,
        location_to_region,
    )

    _write_markets_file(id_to_key, location_keys, default_map, location_to_region)
    _write_roads_file(id_to_key, location_keys, default_map)
    _filter_start_setup_content(
        location_keys,
        area_keys,
        region_keys,
        continent_keys,
        subcontinent_keys,
    )


def _write_named_locations_file(named_locations: list[tuple[int, str, int, int, int, str]]) -> None:
    named_path = iu_map_data / "named_locations"
    named_path.mkdir(parents=True, exist_ok=True)
    lines = [f"{key} = {r:02x}{g:02x}{b:02x}" for _, key, r, g, b, _ in named_locations]
    _write_text_file(named_path / "00_default.txt", "\n".join(lines) + "\n")


def _write_reference_outputs(
    named_locations: list[tuple[int, str, int, int, int, str]],
    id_to_key: dict[int, str],
    location_keys: set[str],
    sea_zones: set[str],
) -> set[str]:
    ref_file = Path(__file__).parent / "province_id_to_key.csv"
    write_csv(
        ref_file,
        [{"ID": prov_id, "Key": key} for prov_id, key, *_ in named_locations],
        fieldnames=["ID", "Key"],
    )

    write_csv(
        iu_map_data / "adjacencies.csv",
        parse_adjacencies(id_to_key, location_keys)[:-1],
        ["From", "To", "Type", "Through", "x1", "y1", "x2", "y2", "Comment"],
    )

    ports = parse_ports(id_to_key, sea_zones=sea_zones)
    write_csv(iu_map_data / "ports.csv", ports, ["LandProvince", "SeaZone", "x", "y"])
    return {
        row["LandProvince"]
        for row in ports
        if isinstance(row.get("LandProvince"), str)
        and row["LandProvince"]
        and not row["LandProvince"].startswith("UNKNOWN_")
    }


def _build_location_to_region_map(regions: dict[str, dict[str, list[str]]]) -> dict[str, str]:
    location_to_region: dict[str, str] = {}
    for region_tag, area_map in regions.items():
        for provinces in area_map.values():
            if not isinstance(provinces, list):
                continue
            for key in provinces:
                location_to_region.setdefault(key, region_tag)
    return location_to_region


def _build_location_to_region_map_from_hierarchy(
    hierarchy: _pydt.Tree | dict,
) -> dict[str, str]:
    """Build location -> final EU5 region mapping from generated definitions hierarchy."""
    location_to_region: dict[str, str] = {}

    def _walk(node, current_region: str | None = None) -> None:
        block = _tree_block(node)
        if not isinstance(block, (_pydt.Tree, dict)):
            return
        for raw_key, raw_value in block.items():
            key = str(raw_key)
            next_region = current_region
            if key.endswith("_region"):
                next_region = key

            child = _tree_block(raw_value)
            if isinstance(child, (_pydt.Tree, dict)):
                _walk(child, next_region)
                continue

            if not next_region:
                continue
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            for value in values:
                if isinstance(value, str) and value:
                    location_to_region.setdefault(value, next_region)

    _walk(hierarchy)
    return location_to_region


def _collect_assigned_provinces(regions: dict[str, dict[str, list[str]]]) -> set[str]:
    return {
        province
        for area_map in regions.values()
        for provinces in area_map.values()
        if isinstance(provinces, list)
        for province in provinces
    }


def _merge_inferred_membership(
    assigned_provinces: set[str],
    inferred_regions: dict[str, str],
    label: str,
) -> set[str]:
    if not inferred_regions:
        return assigned_provinces
    updated = assigned_provinces | set(inferred_regions.keys())
    print(f"Inferred region membership for {len(inferred_regions)} {label}.")
    return updated


def _add_generated_region(
    regions: dict[str, dict[str, list[str]]],
    assigned_provinces: set[str],
    region_tag: str,
    area_tag: str,
    keys: set[str],
) -> set[str]:
    unassigned = set(keys) - assigned_provinces
    if not unassigned:
        return assigned_provinces
    regions.setdefault(region_tag, {})[area_tag] = sorted(unassigned)
    return assigned_provinces | unassigned


def _add_generated_region_from_ranges(
    regions: dict[str, dict[str, list[str]]],
    assigned_provinces: set[str],
    range_groups: dict[str, list[list[str]]],
    region_tag: str,
    area_prefix: str,
    keys: set[str],
    source_categories: tuple[str, ...],
) -> set[str]:
    area_index = 1
    target_keys = set(keys)
    for source in source_categories:
        for group in range_groups.get(source, []):
            group_keys = [key for key in group if key in target_keys and key not in assigned_provinces]
            if not group_keys:
                continue
            area_tag = f"{area_prefix}_{area_index:03d}"
            regions.setdefault(region_tag, {})[area_tag] = group_keys
            assigned_provinces = assigned_provinces | set(group_keys)
            area_index += 1

    leftovers = target_keys - assigned_provinces
    if leftovers:
        assigned_provinces = _add_generated_region(
            regions,
            assigned_provinces,
            region_tag,
            f"{area_prefix}_misc",
            leftovers,
        )
    return assigned_provinces


def _augment_regions_with_generated_buckets(
    regions: dict[str, dict[str, list[str]]],
    assigned_provinces: set[str],
    id_to_key: dict[int, str],
    default_map: dict,
    location_keys: set[str],
) -> set[str]:
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

    region_specs = (
        ("sea_zones_area", "sea_zones_province", "sea_zones", ("sea_zones",)),
        ("lakes_area", "lakes_province", "lakes", ("lakes",)),
    )
    for region_tag, area_prefix, default_map_key, sources in region_specs:
        keys = default_map.get(default_map_key, set()) if isinstance(default_map, dict) else set()
        if not keys:
            continue
        assigned_provinces = _add_generated_region_from_ranges(
            regions,
            assigned_provinces,
            range_groups,
            region_tag,
            area_prefix,
            set(keys),
            sources,
        )

    all_unassigned = set(location_keys) - assigned_provinces
    if all_unassigned:
        assigned_provinces = _add_generated_region(
            regions,
            assigned_provinces,
            "unassigned_locations_area",
            "unassigned_locations_province",
            all_unassigned,
        )
    return assigned_provinces


def _build_region_hierarchy(
    named_locations: list[tuple[int, str, int, int, int, str]],
    location_keys: set[str],
    id_to_key: dict[int, str],
    default_map: dict,
) -> tuple[
    dict[str, dict[str, list[str]]],
    dict[str, str],
    set[str],
    set[str],
    set[str],
    dict,
    set[str],
]:
    regions = build_regions(id_to_key)
    dissolved_river_keys = dissolve_river_regions(regions)
    location_to_region = _build_location_to_region_map(regions)
    assigned_provinces = _collect_assigned_provinces(regions)

    inferred_water_regions = assign_unmapped_water_to_regions(
        regions,
        location_to_region,
        assigned_provinces,
        default_map,
        named_locations,
        location_keys,
        id_to_key,
    )
    assigned_provinces = _merge_inferred_membership(
        assigned_provinces,
        inferred_water_regions,
        "unassigned sea/lake locations",
    )

    inferred_non_ownable_regions = assign_unmapped_non_ownable_to_regions(
        regions,
        location_to_region,
        assigned_provinces,
        default_map,
        named_locations,
        location_keys,
    )
    assigned_provinces = _merge_inferred_membership(
        assigned_provinces,
        inferred_non_ownable_regions,
        "non-ownable locations",
    )

    inferred_river_regions = assign_unmapped_rivers_to_regions(
        regions,
        location_to_region,
        assigned_provinces,
        default_map,
        named_locations,
        location_keys,
        dissolved_river_keys,
    )
    assigned_provinces = _merge_inferred_membership(
        assigned_provinces,
        inferred_river_regions,
        "river locations",
    )

    _augment_regions_with_generated_buckets(
        regions,
        assigned_provinces,
        id_to_key,
        default_map,
        location_keys,
    )

    region_keys = set(regions.keys())
    area_keys = {area for region in regions.values() for area in region.keys()}
    continent_keys = set(continent_map.keys()) if isinstance(continent_map, dict) else set()
    normalized_superregion_map = normalize_superregion_map(superregion_map)
    subcontinent_keys = (
        set(normalized_superregion_map.keys()) if isinstance(normalized_superregion_map, dict) else set()
    )
    hierarchy = build_full_hierarchy(regions, normalized_superregion_map, continent_map)
    write_blocks(iu_map_data / "definitions.txt", hierarchy_to_blocks(hierarchy))

    final_location_to_region = _build_location_to_region_map_from_hierarchy(hierarchy)
    if not final_location_to_region:
        final_location_to_region = {
            key: to_region_key(raw_region)
            for key, raw_region in location_to_region.items()
            if isinstance(key, str) and isinstance(raw_region, str)
        }
    else:
        for key, raw_region in location_to_region.items():
            if not isinstance(key, str) or not isinstance(raw_region, str):
                continue
            final_location_to_region.setdefault(key, to_region_key(raw_region))

    return (
        regions,
        final_location_to_region,
        area_keys,
        region_keys,
        continent_keys,
        normalized_superregion_map,
        subcontinent_keys,
    )


def _write_exploration_template(
    normalized_superregion_map: dict,
    region_keys: set[str],
    area_keys: set[str],
) -> None:
    template_path = mod_root / "main_menu" / "setup" / "templates" / "expl_imperator_rome.txt"
    template_path.parent.mkdir(parents=True, exist_ok=True)

    superregion_keys = sorted(
        {superregion for sub in normalized_superregion_map.values() for superregion in sub.keys()}
    )
    sections = {
        "discovered_regions": superregion_keys,
        "discovered_areas": sorted(region_keys),
        "discovered_provinces": sorted(area_keys),
    }

    lines: list[str] = []
    for section, keys in sections.items():
        lines.append(f"{section} = {{")
        lines.extend(f"	{key}" for key in keys)
        lines.append("}")
        lines.append("")

    _write_text_file(template_path, "\n".join(lines[:-1]) + "\n", encoding="utf-8")


def _copy_and_validate_map_images() -> None:
    map_files = {
        ir_path("map_data/provinces.png"): iu_map_data / "locations.png",
        ir_path("map_data/rivers.png"): iu_map_data / "rivers.png",
    }
    for src, dst in map_files.items():
        _copy_file_if_exists(src, dst)

    locations_img = iu_map_data / "locations.png"
    locations_size = _png_size(locations_img)
    if locations_size:
        defines_override = mod_root / "loading_screen" / "common" / "defines" / "ir_defines.txt"
        _sync_world_extents(defines_override, locations_size)

    eu5_locations_png = eu5_game / "in_game" / "map_data" / "locations.png"
    target_size = _png_size(eu5_locations_png) if eu5_locations_png.exists() else None
    if target_size and locations_size and locations_size != target_size:
        rivers_img = iu_map_data / "rivers.png"
        rivers_size = _png_size(rivers_img)
        if rivers_size and rivers_size != locations_size:
            print(
                f"Warning: rivers.png size {rivers_size} differs from locations.png "
                f"{locations_size}; keeping Imperator rivers.png"
            )


def port_map_data(default_culture: str | None = None, default_religion: str | None = None):
    """Parse Imperator map data and write converted EU5 map/setup assets."""
    named_locations = parse_definitions()
    id_to_key = {prov_id: key for prov_id, key, *_ in named_locations}
    location_keys = {key for _, key, *_ in named_locations}

    _write_named_locations_file(named_locations)

    default_map = build_default_map(id_to_key)
    volcanoes = {key for key in location_keys if isinstance(key, str) and key.endswith("_volcano")}
    if volcanoes:
        default_map.setdefault("volcanoes", set()).update(volcanoes)

    sea_zones = set(default_map.get("sea_zones", set())) if isinstance(default_map, dict) else set()
    if isinstance(default_map, dict):
        sea_zones.update(
            {
                key
                for key in default_map.get("lakes", set())
                if isinstance(key, str) and key.startswith("mare_hyrcanum_")
            }
        )
    coastal_land_locations = _write_reference_outputs(
        named_locations,
        id_to_key,
        location_keys,
        sea_zones,
    )

    harbor_suitability_map = build_ir_harbor_suitability(
        named_locations,
        location_keys,
        default_map,
        coastal_land_locations,
    )

    (
        regions,
        location_to_region,
        area_keys,
        region_keys,
        continent_keys,
        normalized_superregion_map,
        subcontinent_keys,
    ) = _build_region_hierarchy(named_locations, location_keys, id_to_key, default_map)

    _write_exploration_template(normalized_superregion_map, region_keys, area_keys)

    _write_map_localisation(
        named_locations,
        regions,
        normalized_superregion_map,
        subcontinent_keys,
        continent_keys,
    )
    write_default_map(default_map)

    _write_location_templates(
        location_keys,
        default_map,
        coastal_land_locations,
        location_to_region,
        id_to_key,
        default_culture,
        default_religion,
        harbor_suitability_map,
    )

    script_region_keys = set(
        superregion
        for sub in normalized_superregion_map.values()
        if isinstance(sub, dict)
        for superregion in sub.keys()
        if isinstance(superregion, str)
    )
    if not script_region_keys:
        script_region_keys = region_keys

    _apply_map_content_overrides(location_keys, script_region_keys, continent_keys, subcontinent_keys)
    _write_start_setup_content(
        id_to_key,
        location_keys,
        default_map,
        location_to_region,
        area_keys,
        region_keys,
        continent_keys,
        subcontinent_keys,
        coastal_land_locations,
    )

    _copy_and_validate_map_images()
