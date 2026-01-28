from collections import defaultdict
from pathlib import Path
from typing import List, Tuple, Union

import pyradox
import pyradox.datatype as _pydt

from .paths import *

pyradox.Color = _pydt.Color


def convert_color(color: _pydt.Color) -> str:
    if color.colorspace == "rgb":
        r, g, b = color.channels
        return f"rgb {{ {r} {g} {b} }}"
    elif color.colorspace == "hsv":
        h, s, v = color.channels
        return f"hsv {{ {h:.2f} {s:.2f} {v:.2f} }}"
    else:
        raise ValueError(f"Unsupported color space: {color.colorspace}")


def make_block(
    tag: str,
    lines: List[Union[str, Tuple[str, List[object]]]] | None = None,
    indent_level: int = 0,
    indent_str: str = "    ",
) -> str:
    if lines is None:
        lines = []

    prefix = indent_str * indent_level
    inner_prefix = prefix + indent_str

    parts: List[str] = [f"{prefix}{tag} = {{\n"]

    for line in lines:
        if isinstance(line, tuple) and len(line) == 2:
            subtag, sublines = line
            parts.append(make_block(subtag, sublines, indent_level + 1, indent_str))
        else:
            parts.append(f"{inner_prefix}{line}\n")

    parts.append(f"{prefix}}}\n")
    return "".join(parts)


def write_blocks(
    out_path: Path,
    blocks: Union[
        str,
        Tuple[str, List[object]],
        List[Union[str, Tuple[str, List[object]]]],
    ],
    mode: str = "w",
    encoding: str = "utf-8",
    indent_str: str = "    ",
) -> Path:
    # normalize to a list of blocks
    if isinstance(blocks, (tuple, str)):
        blocks_list = [blocks]
    elif isinstance(blocks, list):
        blocks_list = blocks
    else:
        raise TypeError("blocks must be a str, a (tag, lines) tuple, or a list")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open(mode, encoding=encoding) as f:
        for block in blocks_list:
            if isinstance(block, tuple) and len(block) == 2:
                tag, lines = block
                f.write(make_block(tag, lines, indent_level=0, indent_str=indent_str))
                # Keep a blank line after a generated block for readability
                f.write("\n")
            else:
                s = str(block)
                f.write(s)
                if not s.endswith("\n"):
                    f.write("\n")
                # For localisation files (YAML) we don't want blank lines between lines
                if out_path.suffix not in (".yml", ".yaml"):
                    f.write("\n")

    return out_path


def write_culture_group_data(culture_data: list):
    blocks = [(culture_group["tag"], []) for culture_group in culture_data]
    out_path = iu_culture_groups / f"ir_culture_groups.txt"
    write_blocks(out_path, blocks)


def write_culture_data(culture_data: list):
    for culture_group in culture_data:
        blocks = []

        for culture in culture_group["cultures"]:
            lines = [
                f"color = {culture_group['color']}",
                f"tags = {{ {culture_group['graphical_culture']} }}",
                f"culture_groups = {{ {culture_group['tag']} }}",
            ]

            blocks.append((culture["tag"], lines))

        out_path = iu_cultures / f"{culture_group['tag']}.txt"

        write_blocks(out_path, blocks)


def write_religion_group_data(religion_data: list):
    blocks = [
        (
            "ir_religion_group",
            [
                "# Will probably need to change this manually later",
                f"color = rgb {{ 255 255 255 }}",
            ],
        )
    ]

    out_path = iu_religion_groups / f"ir_default.txt"

    write_blocks(out_path, blocks)


def write_religion_data(religion_data: list):
    blocks = [
        (
            religion["tag"],
            [
                f"color = {convert_color(religion['color'])}",
                f"group = {{ ir_religion_group }}",
            ],
        )
        for religion in religion_data
    ]

    out_path = iu_religions / f"ir_religions.txt"

    write_blocks(out_path, blocks)


def write_country_setup(country_data: list):
    setup_dir_dict = defaultdict(list)

    for country in country_data:
        lines = [
            f"# {country['tag']} -> {ir_countries_dir.relative_to(ir_game)}/{country['setup_dir']}/{country['setup_file']}",
            f"color = {convert_color(country['color'])}",
            f"culture_definition = {country['culture']}",
            f"religion_definition = {country['religion']}",
        ]
        setup_dir_dict[country["setup_dir"]].append((country["tag"], lines))

    for setup_dir, country_blocks in setup_dir_dict.items():
        out_path = iu_countries / f"00_ir_{setup_dir}.txt"
        write_blocks(out_path, country_blocks)


def write_localisation_files(
    culture_data: list, religion_data: list, country_data: list
):
    culture_lines = [
        f" l_english:",
    ]
    for culture_group in culture_data:
        culture_lines.append(f"  {culture_group['tag']}: \"{culture_group['name']}\"")
        for culture in culture_group["cultures"]:
            culture_lines.append(f"  {culture['tag']}: \"{culture['name']}\"")

    religion_lines = [
        f" l_english:",
    ]
    for religion in religion_data:
        religion_lines.append(f"  {religion['tag']}: \"{religion['name']}\"")

    country_lines = [
        f" l_english:",
    ]
    for country in country_data:
        country_lines.append(f"  {country['tag']}: \"{country['name']}\"")
        country_lines.append(f"  {country['tag']}_ADJ: \"{country['name_adj']}\"")

    write_blocks(iu_localisation / "cultures_l_english.yml", culture_lines)
    write_blocks(iu_localisation / "religions_l_english.yml", religion_lines)
    write_blocks(iu_localisation / "countries_l_english.yml", country_lines)
