import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyradox
import pyradox.datatype as _pydt
from pyradox.filetype.txt import parse as parse_txt

from .data import government_map
from .paths import *
from .write_data import print_written

pyradox.Tree = _pydt.Tree
pyradox.Color = _pydt.Color

# ---------- Helper ----------


def parse_tree(file_path: Path):
    """Parse a file into a pyradox.Tree."""
    text = file_path.read_text(encoding="utf-8-sig")
    tree = parse_txt(text, filename=str(file_path))
    return tree


def _make_serializable(o: Any):
    if o is None or isinstance(o, (str, int, float, bool)):
        return o
    elif isinstance(o, dict):
        return {k: _make_serializable(v) for k, v in o.items()}
    elif isinstance(o, list):
        return [_make_serializable(v) for v in o]
    elif isinstance(o, _pydt.Color):
        return {"colorspace": o.colorspace, "values": o.channels}
    else:
        return str(o)


def write_json(data: Any, out_path: Path) -> Path:
    """Write `data` to `out_path` as JSON, converting non-serializable items.

    Returns the path written to.
    """
    serializable = _make_serializable(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print_written("JSON", out_path)
    return out_path


# ---------- Localisation ----------


def read_localisation_file(path: Path) -> dict[str, str]:
    """Read localisation from a directory or single file."""
    result: dict[str, str] = {}
    pattern = re.compile(r'^([A-Za-z0-9_@:\-\.]+):\s*\d+\s+"(.*)"')

    files = []
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix == ".yml")
    else:
        return result

    for file in files:
        for line in file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.endswith(":"):
                continue
            match = pattern.match(line)
            if match:
                key, value = match.groups()
                result[key] = value

    return result


# ---------- Data Extraction ----------


def extract_culture_data():
    culture_loc = read_localisation_file(ir_localisation)
    culture_blocks = []

    for path in ir_cultures.iterdir():
        if path.suffix != ".txt" or not path.is_file():
            continue

        tree = parse_tree(path)

        for group_tag, group_data in tree.items():
            [(_, ethnicity)] = group_data["ethnicities"].items()
            cultures = group_data["culture"]
            culture_blocks.append(
                {
                    "tag": f"ir_{group_tag}_g",
                    "name": f"{culture_loc[group_tag]}",
                    "name_desc": culture_loc.get(f"{group_tag}_desc", "REPLACE ME"),
                    "cultures": [
                        {
                            "tag": f"ir_{culture_tag}",
                            "name": culture_loc[culture_tag],
                        }
                        for culture_tag in cultures
                    ],
                    "color": group_data["color"],
                    "graphical_culture": f"ir_{group_data['graphical_culture']}",
                    "ethnicities": f"ir_{ethnicity}",
                }
            )

    return culture_blocks


def extract_religion_data():
    religion_tree = parse_tree(ir_religions)
    religion_loc = read_localisation_file(ir_localisation)
    religion_blocks = []

    for religion_tag, religion_data in religion_tree.items():
        religion_blocks.append(
            {
                "tag": f"ir_{religion_tag}",
                "name": religion_loc[religion_tag],
                "name_adj": religion_loc.get(f"{religion_tag}_ADJ", "REPLACE ME"),
                "name_desc": religion_loc.get(f"{religion_tag}_desc", "REPLACE ME"),
                "color": religion_data["color"],
            }
        )

    return religion_blocks


def extract_country_data():
    default_tree = parse_tree(ir_default)
    country_tree = default_tree["country"]["countries"]
    country_loc = read_localisation_file(ir_localisation)
    setup_tree = parse_tree(ir_countries_file)

    setup_dirs = dict(setup_tree.items())
    country_blocks = []

    for country_tag, country_data in country_tree.items():
        country_setup_file: Path = ir_game / setup_dirs.get(country_tag)
        country_setup_tree = parse_tree(country_setup_file)

        tag_loc_overrides = {
            "DEL": "Nesio",  # Nesiotic League
            "SEL": "Seleucids",  # Seleucid Empire
            "BPK": "Bospora",  # Bosporan Kingdom
            "PRY": "Antigonids",  # Antigonid Kingdom
        }

        country_name = (
            country_loc[country_tag]
            if country_tag not in tag_loc_overrides
            else tag_loc_overrides[country_tag]
        )
        country_name_adj = country_loc[f"{country_tag}_ADJ"]

        country_blocks.append(
            {
                "tag": country_tag,
                "name": country_name,
                "name_adj": country_name_adj,
                "culture": f"ir_{country_data['primary_culture']}",
                "religion": f"ir_{country_data['religion']}",
                "government": country_data["government"],
                "government_type": government_map.get(country_data["government"]),
                "color": country_setup_tree["color"],
                "setup_dir": country_setup_file.parent.name,
                "setup_file": country_setup_file.name,
            }
        )

    # Read EU5 countries for writing overrides
    override_blocks = defaultdict(list)

    for eu5_country_file in eu5_countries.iterdir():
        eu5_countries_tree = parse_tree(eu5_country_file)
        for country_tag, country_data in eu5_countries_tree.items():
            override_blocks[eu5_country_file.relative_to(eu5_game)].append(
                {
                    "tag": country_tag,
                    "culture": country_data["culture_definition"],
                    "religion": country_data["religion_definition"],
                    "color": country_data["color"],
                }
            )

    return country_blocks, override_blocks


def extract_coa_data():
    coa_tree = parse_tree(ir_prescripted_coa)

    def _replace_tga_with_dds(obj: Any) -> None:
        def _update_str(s: str) -> str:
            return re.sub(r"(?i)\.tga\b", ".dds", s)

        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if isinstance(v, str):
                    new_v = _update_str(v)
                    if new_v != v:
                        obj[k] = new_v
                else:
                    _replace_tga_with_dds(v)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, str):
                    new_v = _update_str(v)
                    if new_v != v:
                        obj[i] = new_v
                else:
                    _replace_tga_with_dds(v)
        elif isinstance(obj, _pydt.Tree):
            # pyradox.Tree behaves like a dict
            for k, v in list(obj.items()):
                if isinstance(v, str):
                    new_v = _update_str(v)
                    if new_v != v:
                        obj[k] = new_v
                else:
                    _replace_tga_with_dds(v)

    # Only convert .tga -> .dds for coat of arms data
    _replace_tga_with_dds(coa_tree)

    return coa_tree


def extract_eu5_map_data():
    tree = parse_tree(eu5_map_data).to_python()
    return tree


def extract_10_countries():
    # Extracts the data for the countries that are currently already written to 10_countries.txt
    tree = parse_tree(iu_setup_start / "10_countries.txt")
    countries = tree["countries"]["countries"].to_python()
    return countries


def extract_05_characters():
    # Extract the data from the characters that are currently already written to 05_characters.txt
    tree = parse_tree(iu_setup_start / "05_characters.txt")
    characters = tree["character_db"].to_python()
    return characters


def extract_04_dynasties():
    # Extract the data from the dynasties that are currently already written to 04_dynasties.txt
    tree = parse_tree(iu_setup_start / "04_dynasties.txt")
    dynasties = tree["dynasty_manager"].to_python()
    return dynasties


def extract_character_data():
    character_loc = read_localisation_file(ir_localisation)

    def is_ruler(char_data):
        for key, value in char_data.items():
            if key.startswith("c:") and value["set_as_ruler"]:
                return True
        return False

    characters = []
    dynasties = []
    tag_counts = {}
    dynasty_tags_seen = set()  # track which dynasties we've already added

    for path in ir_character_data.iterdir():
        if path.suffix != ".txt" or not path.is_file():
            continue

        character_tree = parse_tree(path)
        for _, country_characters in character_tree.items():
            for char_id, char_data in country_characters.items():
                if char_id == "country":
                    # Set country tag for this loop
                    country_tag = char_data
                    continue

                ruler_flag = is_ruler(char_data)
                if "first_name" in char_data:
                    ir_name_tag = char_data["first_name"]
                    name_tag = char_data["first_name"]
                    name = (
                        character_loc[ir_name_tag]
                        if ir_name_tag in character_loc
                        else ir_name_tag
                    )
                else:
                    name_tag = None

                if "nickname" in char_data:
                    nickname_tag = char_data["nickname"]
                    nickname = (
                        (
                            character_loc[char_data["nickname"]]
                            if nickname_tag in character_loc
                            else nickname_tag
                        )
                        .strip("'")
                        .replace(" ", "_")
                    )
                else:
                    nickname_tag = None
                    nickname = None

                if "family" in char_data:
                    if char_data["family"].startswith("c:"):
                        dynasty = f"{char_data['family'].split(':')[2].lower()}"
                    else:
                        dynasty = char_data["family"]
                    dynasty_tag = f"{dynasty.lower()}_dynasty"
                    dynasty_name = dynasty.capitalize()
                    dynasty = dynasty.lower().replace(" ", "_")
                    if dynasty_tag not in dynasty_tags_seen:
                        dynasties.append({"tag": dynasty_tag, "name": dynasty_name})
                        dynasty_tags_seen.add(dynasty_tag)
                else:
                    dynasty_tag = None
                    dynasty_name = None

                father = (
                    (
                        int(char_data["father"].split(":")[1])
                        if char_data["father"].startswith("char:")
                        else None
                    )
                    if "father" in char_data
                    else None
                )
                mother = (
                    (
                        int(char_data["mother"].split(":")[1])
                        if char_data["mother"].startswith("char:")
                        else None
                    )
                    if "mother" in char_data
                    else None
                )
                spouse = (
                    (
                        int(char_data["marry_character"].split(":")[1])
                        if char_data["marry_character"].startswith("char:")
                        else None
                    )
                    if "marry_character" in char_data
                    else None
                )

                # Construct base unique tag
                parts = [country_tag]
                if name:
                    parts.append(name.lower().replace(" ", "_"))
                else:
                    parts.append("char")
                if dynasty:
                    parts.append(dynasty.lower().replace(" ", "_"))
                base_tag = "_".join(parts).lower()

                # Make tag truly unique
                if base_tag in tag_counts:
                    tag_counts[base_tag] += 1
                    unique_tag = f"{base_tag}_{tag_counts[base_tag]}"
                else:
                    tag_counts[base_tag] = 1
                    unique_tag = base_tag

                data = {
                    "id": int(char_id),
                    "name_tag": name_tag,
                    "name": name,
                    "dynasty_tag": dynasty_tag,
                    "dynasty_name": (dynasty.capitalize() if dynasty else None),
                    "nickname_tag": nickname_tag,
                    "nickname": nickname,
                    "birth_date": char_data["birth_date"],
                    "death_date": char_data["death_date"] if "death_date" in char_data else None,
                    "father": father,
                    "mother": mother,
                    "female": char_data["female"] if "female" in char_data else False,
                    "spouse": spouse,
                    "culture": f"ir_{char_data['culture']}",
                    "religion": f"ir_{char_data['religion']}",
                    "country": country_tag,
                    "scope": char_data["save_scope_as"],
                    "is_ruler": ruler_flag,
                    "tag": unique_tag,  # final unique tag
                }
                characters.append(data)
    return characters, dynasties
