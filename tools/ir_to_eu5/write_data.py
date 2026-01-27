from .paths import *
from pathlib import Path
from typing import List, Union, Tuple


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
            else:
                s = str(block)
                f.write(s)
                if not s.endswith("\n"):
                    f.write("\n")
            f.write("\n")

    return out_path


def write_culture_group_data(culture_data: list):
    blocks = [(culture_group["tag"], []) for culture_group in culture_data]
    write_blocks(iu_culture_groups, blocks)


def write_culture_data(culture_data: list):
    for culture_group in culture_data:
        blocks: List[Tuple[str, List[object]]] = []

        for culture in culture_group["cultures"]:
            lines = [
                f"color = {culture_group['color']}",
                f"tags = {{ {culture_group['graphical_culture']} }}",
                f"culture_groups = {{ {culture_group['tag']} }}",
            ]

            blocks.append((culture["tag"], lines))

        out_path = iu_cultures / f"{culture_group['tag']}.txt"

        write_blocks(out_path, blocks)
