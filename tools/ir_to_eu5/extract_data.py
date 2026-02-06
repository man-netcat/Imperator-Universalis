import json
import re
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyradox
import pyradox.datatype as _pydt
from pyradox.filetype.txt import ParseWarning
from pyradox.filetype.txt import parse as parse_txt

from .data import government_map
from .paths import *
from .write_data import print_written

warnings.filterwarnings("error", category=ParseWarning)

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


def read_localisation_file(path: Path | list[Path] | tuple[Path, ...]) -> dict[str, str]:
    """Read localisation from one or more directories/files, later paths override."""
    if isinstance(path, (list, tuple)):
        merged: dict[str, str] = {}
        for entry in path:
            merged.update(read_localisation_file(entry))
        return merged

    result: dict[str, str] = {}
    pattern = re.compile(r'^([A-Za-z0-9_@:\-\.]+):\s*(?:\d+\s*)?"(.*)"')

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
    culture_loc = read_localisation_file(ir_localisation_paths)
    culture_blocks = []

    for path in iter_ir_files("common/cultures"):
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
    religion_loc = read_localisation_file(ir_localisation_paths)
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


def extract_deity_data():
    deity_blocks = []
    if not ir_deities.exists():
        return deity_blocks

    deity_loc = read_localisation_file(
        [path / "deities" for path in ir_localisation_paths]
    )
    deity_loc.update(
        read_localisation_file(
            [path / "god_names_l_english.yml" for path in ir_localisation_paths]
        )
    )

    def resolve_deity_name(loc_key: str) -> str | None:
        if not loc_key:
            return None
        value = deity_loc.get(loc_key)
        if value and value.startswith("$") and value.endswith("$"):
            inner = value.strip("$")
            return deity_loc.get(inner, value)
        return value

    for path in iter_ir_files("common/deities"):
        if path.suffix != ".txt" or not path.is_file():
            continue

        tree = parse_tree(path)
        for deity_tag, deity_data in tree.items():
            if not isinstance(deity_tag, str) or not deity_tag.startswith("deity_"):
                continue
            religion = deity_data["religion"]
            category = deity_data["deity_category"]

            deity_blocks.append(
                {
                    "tag": deity_tag,
                    "religion": str(religion) if religion is not None else None,
                    "category": str(category) if category is not None else None,
                    "name": resolve_deity_name(deity_tag),
                }
            )

    return deity_blocks


def extract_country_data():
    default_tree = parse_tree(ir_default)
    country_tree = default_tree["country"]["countries"]
    country_loc = read_localisation_file(ir_localisation_paths)
    setup_tree = parse_tree(ir_countries_file)

    setup_dirs = dict(setup_tree.items())
    country_blocks = []

    def _fallback_country_name(setup_file: Path, tag: str) -> str:
        stem = setup_file.stem if setup_file and setup_file.stem else ""
        if stem:
            return stem.replace("_", " ").title()
        return tag

    for country_tag, country_data in country_tree.items():
        setup_rel = setup_dirs.get(country_tag)
        if not setup_rel:
            continue
        country_setup_file = ir_path(setup_rel)
        country_setup_tree = parse_tree(country_setup_file)

        tag_loc_overrides = {
            "DEL": "Nesio",  # Nesiotic League
            "SEL": "Seleucids",  # Seleucid Empire
            "BPK": "Bospora",  # Bosporan Kingdom
            "PRY": "Antigonids",  # Antigonid Kingdom
        }

        fallback_name = _fallback_country_name(country_setup_file, country_tag)
        country_name = tag_loc_overrides.get(
            country_tag,
            country_loc.get(country_tag, fallback_name),
        )
        country_name_adj = country_loc.get(f"{country_tag}_ADJ", country_name)

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
    defs_path = iu_map_data / "definitions.txt"
    if not defs_path.exists():
        defs_path = eu5_map_data
    tree = parse_tree(defs_path).to_python()
    return tree


def extract_start_data(file_name, root_key, sub_key=None):
    base_start = eu5_game / "main_menu" / "setup" / "start"
    if file_name == "10_countries.txt" and (base_start / file_name).exists():
        tree = parse_tree(base_start / file_name)
    else:
        tree = parse_tree(iu_setup_start / file_name)
    data = tree[root_key]
    if sub_key:
        data = data[sub_key]
    return data.to_python()


def extract_ir_country_locations():
    """Return mapping of country tag -> list of province IDs from IR own_control_core."""
    def _collect_ids(value: Any, out: list[int]) -> None:
        if isinstance(value, int):
            out.append(value)
        elif isinstance(value, str):
            out.append(int(value))
        elif isinstance(value, _pydt.Color):
            out.extend(int(channel) for channel in value.channels)
        elif isinstance(value, (list, tuple)):
            for v in value:
                _collect_ids(v, out)
        elif isinstance(value, (_pydt.Tree, dict)):
            for k, v in value.items():
                _collect_ids(k, out)
                _collect_ids(v, out)

    tree = parse_tree(ir_default)
    countries = tree["country"]["countries"]
    result: dict[str, list[int]] = {}

    for tag, data in countries.items():
        prov_ids: list[int] = []
        for value in data.find_all("own_control_core"):
            _collect_ids(value, prov_ids)

        if prov_ids:
            seen = set()
            deduped = []
            for pid in prov_ids:
                if pid not in seen:
                    seen.add(pid)
                    deduped.append(pid)
            result[tag] = deduped

    return result


def extract_ir_country_capitals() -> dict[str, int]:
    """Return mapping of country tag -> capital province ID from IR 00_default."""
    tree = parse_tree(ir_default)
    countries = tree["country"]["countries"]
    result: dict[str, int] = {}

    for tag, data in countries.items():
        capital = data["capital"]
        if capital is None:
            continue
        result[tag] = int(capital)

    return result


def extract_character_data():
    character_loc = read_localisation_file(ir_localisation_paths)

    def is_ruler(char_data):
        for key, value in char_data.items():
            if key.startswith("c:") and value["set_as_ruler"]:
                return True
        return False

    characters = []
    tag_counts = {}

    for path in iter_ir_files("setup/characters"):
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

                dynasty = None
                if "family" in char_data:
                    if char_data["family"].startswith("c:"):
                        dynasty = f"{char_data['family'].split(':')[2].lower()}"
                    else:
                        dynasty = char_data["family"]
                    dynasty_tag = f"{dynasty.lower().replace(' ', '_')}_dynasty"
                    dynasty_name = dynasty
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
                    "death_date": (
                        char_data["death_date"] if "death_date" in char_data else None
                    ),
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
    return characters


def extract_dynasty_data():
    """Extract dynasties from IR default family database."""
    families_tree = parse_tree(ir_default)["family"]["families"]

    dynasties = []
    seen = set()

    for _, family in families_tree.items():
        if isinstance(family, (_pydt.Tree, dict)) and "key" in family:
            name = str(family["key"])
        else:
            continue
        tag = f"{name.lower().replace(' ', '_')}_dynasty"
        if tag in seen:
            continue
        seen.add(tag)
        dynasties.append({"tag": tag, "name": name})

    return dynasties


def extract_diplomacy_data():
    diplomacy_data = parse_tree(ir_default)["diplomacy"]
    diplomatic_relationships = []
    international_organizations = []
    for diplomacy_type, data in diplomacy_data.items():
        if diplomacy_type == "defensive_league":
            # Should be done through International Organisation
            international_organizations.append(
                {
                    "type": "defensive_league",
                    "members": [member for member in data.values()],
                }
            )
        elif diplomacy_type == "dependency":
            # Actual vassal relationships
            diplomatic_relationships.append(
                {
                    "tag": "dependency",
                    "first": data["first"],
                    "second": data["second"],
                    "subject_type": data["subject_type"],
                }
            )
        elif diplomacy_type == "alliance":
            # scripted_mutual with type = alliance
            diplomatic_relationships.append(
                {
                    "tag": "scripted_mutual",
                    "first": data["first"],
                    "second": data["second"],
                    "type": "alliance",
                }
            )
        elif diplomacy_type == "guarantee":
            # scripted_oneway with type = guarantee
            diplomatic_relationships.append(
                {
                    "tag": "scripted_oneway",
                    "first": data["first"],
                    "second": data["second"],
                    "type": "guarantee",
                }
            )
        else:
            # TODO: Handle trade_access
            pass
    return diplomatic_relationships, international_organizations
