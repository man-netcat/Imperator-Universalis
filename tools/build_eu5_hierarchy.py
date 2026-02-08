#!/usr/bin/env python3
import sys
from pathlib import Path
from pprint import pformat


def _bootstrap_paths() -> Path:
    script_path = Path(__file__).resolve()
    script_dir = script_path.parent
    tools_pyradox_src = script_dir / "pyradox" / "src"
    if not tools_pyradox_src.is_dir():
        print(
            f"Required tools pyradox not found at {tools_pyradox_src}.\n"
            "Run 'git submodule update --init --recursive' from the repository root."
        )
        raise SystemExit(1)
    sys.path.insert(0, str(tools_pyradox_src))
    sys.path.insert(0, str(script_dir))
    return script_dir


def main() -> int:
    script_dir = _bootstrap_paths()

    from ir_to_eu5.extract_data import parse_tree
    from ir_to_eu5.paths import eu5_game

    definitions_path = eu5_game / "in_game" / "map_data" / "definitions.txt"
    tree = parse_tree(definitions_path).to_python()

    continent_map: dict[str, list[str]] = {}
    superregion_map: dict[str, dict[str, list[str]]] = {}

    for continent_tag, continent_data in tree.items():
        if not isinstance(continent_data, dict):
            continue
        subcontinents: list[str] = []
        for subcontinent_tag, subcontinent_data in continent_data.items():
            if not isinstance(subcontinent_data, dict):
                continue
            subcontinents.append(str(subcontinent_tag))
            super_map: dict[str, list[str]] = {}
            for superregion_tag, superregion_data in subcontinent_data.items():
                if not isinstance(superregion_data, dict):
                    continue
                regions = [str(region_tag) for region_tag in superregion_data.keys()]
                super_map[str(superregion_tag)] = regions
            superregion_map[str(subcontinent_tag)] = super_map
        continent_map[str(continent_tag)] = subcontinents

    out_path = script_dir / "ir_to_eu5" / "eu5_hierarchy.py"
    lines = [
        "# Auto-generated from EU5 base game in_game/map_data/definitions.txt",
        "# Regenerate with: python3 tools/build_eu5_hierarchy.py",
        "",
        f"continent_map = {pformat(continent_map, width=120, sort_dicts=False)}",
        "",
        f"superregion_map = {pformat(superregion_map, width=120, sort_dicts=False)}",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(
        f"Continents: {len(continent_map)}, "
        f"subcontinents: {len(superregion_map)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
