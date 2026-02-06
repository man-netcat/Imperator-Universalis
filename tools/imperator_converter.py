#!/usr/bin/env python3
import argparse
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
sys.path.insert(0, str(script_dir))

from ir_to_eu5.extract_data import (
    extract_character_data,
    extract_coa_data,
    extract_country_data,
    extract_culture_data,
    extract_deity_data,
    extract_diplomacy_data,
    extract_dynasty_data,
    extract_eu5_map_data,
    extract_ir_country_capitals,
    extract_ir_country_locations,
    extract_religion_data,
    extract_start_data,
    write_json,
)
from ir_to_eu5.map_data import parse_definitions, port_map_data
from ir_to_eu5.paths import mod_root
from ir_to_eu5.port_gfx import port_coa_gfx
from ir_to_eu5.write_data import (
    write_04_dynasties,
    write_05_characters,
    write_10_countries,
    write_12_diplomacy,
    write_15_international_organizations,
    write_coa_file,
    write_country_setup,
    write_culture_data,
    write_culture_group_data,
    write_god_data,
    write_ir_religious_aspects,
    write_localisation_files,
    write_religion_data,
    write_religion_group_data,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IR → EU5 data converter")
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip writing image-related data (COA files and gfx)",
    )
    parser.add_argument(
        "--no-localisation",
        action="store_true",
        help="Skip writing localisation files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write raw extracted JSON data files",
    )
    parser.add_argument(
        "--port-map",
        action="store_true",
        help="Port EU5 map data from Imperator",
    )
    args = parser.parse_args()
    culture_data = extract_culture_data()
    religion_data = extract_religion_data()
    deity_data = extract_deity_data()
    character_data = extract_character_data()
    dynasty_data = extract_dynasty_data()
    country_rulers = {c["country"]: c["tag"] for c in character_data if c["is_ruler"]}
    country_data, country_overrides = extract_country_data()
    diplomatic_relationships, international_organisations = extract_diplomacy_data()
    named_locations = {t[0]: t[1] for t in parse_definitions()}
    ir_country_locations = extract_ir_country_locations()
    ir_country_capitals = extract_ir_country_capitals()
    # Do not seed from EU5 base 10_countries; generate from IR data only.
    ten_countries_data = {}
    five_characters_data = extract_start_data("05_characters.txt", "character_db")
    four_dynasties_data = extract_start_data("04_dynasties.txt", "dynasty_manager")
    twelve_diplomacy_data = extract_start_data("12_diplomacy.txt", "diplomacy_manager")
    fifteen_international_organizations_data = extract_start_data(
        "15_international_organizations.txt", "international_organization_manager"
    )

    eu5_map_data = extract_eu5_map_data()

    # Write a human-readable TSV of country -> location count for debugging/analysis
    try:
        counts_out = script_dir / "ir_to_eu5" / "country_location_counts.tsv"
        name_map = {c["tag"]: c["name"] for c in country_data}
        rows = []
        for tag, provs in ir_country_locations.items():
            rows.append((len(provs), tag, name_map.get(tag, tag)))
        # include tags with zero provinces
        for c in country_data:
            if c["tag"] not in ir_country_locations:
                rows.append((0, c["tag"], c["name"]))
        rows.sort(key=lambda r: (-r[0], r[1]))
        counts_out.parent.mkdir(parents=True, exist_ok=True)
        with counts_out.open("w", encoding="utf-8") as f:
            for count, tag, name in rows:
                f.write(f"{count}\t{tag}\t{name}\n")
        print(f"Wrote {counts_out}")
    except Exception:
        # Non-fatal: don't stop the converter if writing the TSV fails
        pass
    if not args.no_images:
        coa_data = extract_coa_data()

    if args.json:
        write_json(culture_data, mod_root / "cultures.json")
        write_json(religion_data, mod_root / "religions.json")
        write_json(country_data, mod_root / "countries.json")
        write_json(coa_data, mod_root / "coats_of_arms.json")
        write_json(character_data, mod_root / "characters.json")
    write_culture_group_data(culture_data)
    write_culture_data(culture_data)
    write_religion_group_data(religion_data)
    write_religion_data(religion_data)
    write_god_data(deity_data, religion_data)
    write_ir_religious_aspects(deity_data, religion_data)
    write_country_setup(country_data, country_overrides)
    write_04_dynasties(four_dynasties_data, dynasty_data)
    write_05_characters(five_characters_data, character_data)
    # Defaults for location templates and capital fallbacks
    default_culture = next(
        (
            culture.get("tag")
            for group in culture_data
            for culture in group.get("cultures", [])
            if culture.get("tag")
        ),
        None,
    )
    default_religion = religion_data[0].get("tag") if religion_data else None

    write_10_countries(
        ten_countries_data,
        country_data,
        eu5_map_data,
        country_rulers,
        culture_data,
        ir_country_locations=ir_country_locations,
        ir_country_capitals=ir_country_capitals,
        id_to_key=named_locations,
        location_keys=set(named_locations.values()),
    )
    write_12_diplomacy(twelve_diplomacy_data, diplomatic_relationships)
    write_15_international_organizations(
        fifteen_international_organizations_data, international_organisations
    )

    if not args.no_images:
        write_coa_file(coa_data)

    if not args.no_localisation:
        write_localisation_files(
            culture_data,
            religion_data,
            country_data,
            character_data,
            dynasty_data,
            deity_data,
        )

    if not args.no_images:
        port_coa_gfx()

    if args.port_map:
        port_map_data(default_culture=default_culture, default_religion=default_religion)
