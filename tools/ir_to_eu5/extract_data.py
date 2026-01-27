import colorsys
import json
import re
import warnings
from pathlib import Path
from pprint import pprint
from typing import Any

import pyradox
import pyradox.datatype as _pydt
from paths import *
from pyradox.filetype.txt import parse as parse_txt

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
            cultures = group_data["culture"]
            culture_blocks.append(
                {
                    "tag": group_tag,
                    "name": culture_loc[group_tag],
                    "cultures": [
                        {
                            "tag": culture_tag,
                            "name": culture_loc[culture_tag],
                        }
                        for culture_tag in cultures
                    ],
                    "color": group_data["color"],
                    "tags": group_data["graphical_culture"],
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
                "tag": religion_tag,
                "name": religion_loc[religion_tag],
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
        country_setup_file = ir_game / setup_dirs.get(country_tag)
        country_setup_tree = parse_tree(country_setup_file)

        country_name = country_loc[country_tag]
        country_name_adj = country_loc[f"{country_tag}_ADJ"]

        country_blocks.append(
            {
                "tag": country_tag,
                "name": country_name,
                "name_adj": country_name_adj,
                "culture": country_data["primary_culture"],
                "religion": country_data["religion"],
                "color": country_setup_tree["color"],
            }
        )

    return country_blocks


# ---------- Run and write ----------

if __name__ == "__main__":
    culture_data = extract_culture_data()
    religion_data = extract_religion_data()
    country_data = extract_country_data()

    write_json(culture_data, mod_root / "cultures.json")
    write_json(religion_data, mod_root / "religions.json")
    write_json(country_data, mod_root / "countries.json")
