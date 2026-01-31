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
    tree = parse_tree(iu_10_countries)
    countries = tree["countries"]["countries"].to_python()
    return countries


def extract_formable_data():
    def find_tags(obj, target_tag=None, inside_not=False):
        """Recursively find positive and negative tags."""
        pos_tags = []
        neg_tags = []

        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.upper() == "NOT":
                    # Anything under NOT is negative
                    pt, nt = find_tags(value, target_tag, inside_not=True)
                    neg_tags.extend(pt + nt)
                elif key == "tag":
                    if isinstance(value, list):
                        for v in value:
                            if not inside_not:
                                pos_tags.append(v)
                            else:
                                neg_tags.append(v)
                    else:
                        if not inside_not:
                            pos_tags.append(value)
                        else:
                            neg_tags.append(value)
                else:
                    pt, nt = find_tags(value, target_tag, inside_not)
                    pos_tags.extend(pt)
                    neg_tags.extend(nt)

        elif isinstance(obj, list):
            for item in obj:
                pt, nt = find_tags(item, target_tag, inside_not)
                pos_tags.extend(pt)
                neg_tags.extend(nt)

        return pos_tags, neg_tags

    formables = []

    for tier in [ir_tier_1_formables, ir_tier_2_formables, ir_tier_3_formables]:
        for path in tier.iterdir():
            print(path)
            if path.suffix != ".txt" or not path.is_file():
                continue

            tree = parse_tree(path)
            country_decisions = tree["country_decisions"]

            for decision, decision_data in country_decisions.items():
                print(decision)
                decision_dict = decision_data["potential"].to_python()
                pos, neg = find_tags(decision_dict)
                print("Positive tags:", pos, "Negative tags:", neg)
                formables.append(
                    {"decision": decision, "positive_tags": pos, "negative_tags": neg}
                )

    return formables
