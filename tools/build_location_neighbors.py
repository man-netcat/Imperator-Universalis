#!/usr/bin/env python3
import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    script_path = Path(__file__).resolve()
    script_dir = script_path.parent
    tools_pyradox_src = script_dir / "pyradox" / "src"

    if not tools_pyradox_src.is_dir():
        print(
            f"Required tools pyradox not found at {tools_pyradox_src}.\n"
            "Run 'git submodule update --init --recursive' from the repository root."
        )
        sys.exit(1)

    sys.path.insert(0, str(tools_pyradox_src))
    sys.path.insert(0, str(script_dir))


def main() -> int:
    _bootstrap_paths()

    from ir_to_eu5.location_neighbors import (
        DEFAULT_LOCATION_NEIGHBORS_PATH,
        build_location_neighbors,
        save_location_neighbors,
    )
    from ir_to_eu5.map_data import parse_definitions
    from ir_to_eu5.paths import ir_path

    named_locations = parse_definitions()
    location_keys = {key for _, key, *_ in named_locations}
    provinces_png = ir_path("map_data/provinces.png")

    payload = build_location_neighbors(named_locations, location_keys, provinces_png)
    out_path = save_location_neighbors(payload, DEFAULT_LOCATION_NEIGHBORS_PATH)

    edge_count = 0
    neighbors = payload.get("neighbors", {})
    if isinstance(neighbors, dict):
        edge_count = sum(
            len(v) for v in neighbors.values() if isinstance(v, dict)
        ) // 2

    print(f"Wrote {out_path}")
    print(
        "Cached neighbor graph for "
        f"{len(location_keys)} locations with {edge_count} undirected edges."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
