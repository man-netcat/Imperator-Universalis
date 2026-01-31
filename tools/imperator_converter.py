#!/usr/bin/env python3
import sys
from pathlib import Path

# Ensure the module's bundled `pyradox` package is used by inserting
# the tools' pyradox `src` into `sys.path` and failing if absent.
mod_root = Path(__file__).resolve().parent.parent
script_dir = Path(__file__).resolve().parent
tools_pyradox_src = script_dir / "pyradox" / "src"

if not tools_pyradox_src.is_dir():
    print(
        f"Required tools pyradox not found at {tools_pyradox_src}.\n"
        "Run 'git submodule update --init --recursive' from the repository root."
    )
    sys.exit(1)

sys.path.insert(0, str(tools_pyradox_src))

from ir_to_eu5.extract_data import (
    extract_10_countries,
    extract_coa_data,
    extract_country_data,
    extract_culture_data,
    extract_eu5_map_data,
    extract_formable_data,
    extract_religion_data,
    write_json,
)
from ir_to_eu5.map_data import parse_definitions, port_map_data
from ir_to_eu5.paths import mod_root
from ir_to_eu5.port_gfx import port_coa_gfx
from ir_to_eu5.write_data import (
    write_10_countries,
    write_coa_file,
    write_country_setup,
    write_culture_data,
    write_culture_group_data,
    write_localisation_files,
    write_religion_data,
    write_religion_group_data,
)

if __name__ == "__main__":
    culture_data = extract_culture_data()
    religion_data = extract_religion_data()
    country_data, country_overrides = extract_country_data()
    coa_data = extract_coa_data()
    named_locations = {t[0]: t[1] for t in parse_definitions()}
    ten_countries_data = extract_10_countries()
    eu5_map_data = extract_eu5_map_data()
    formable_data = extract_formable_data()

    write_json(culture_data, mod_root / "cultures.json")
    write_json(religion_data, mod_root / "religions.json")
    write_json(country_data, mod_root / "countries.json")
    write_json(coa_data, mod_root / "coats_of_arms.json")

    write_culture_group_data(culture_data)
    write_culture_data(culture_data)
    write_religion_group_data(religion_data)
    write_religion_data(religion_data)
    write_country_setup(country_data, country_overrides)
    write_10_countries(ten_countries_data, country_data, eu5_map_data)
    write_coa_file(coa_data)

    write_localisation_files(culture_data, religion_data, country_data)

    port_coa_gfx()

    # port_map_data()
