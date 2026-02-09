#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path


def _ensure_bundled_pyradox(script_dir: Path) -> None:
    """Use the converter's bundled pyradox package."""
    tools_pyradox_src = script_dir / "pyradox" / "src"
    if not tools_pyradox_src.is_dir():
        print(
            f"Required tools pyradox not found at {tools_pyradox_src}.\n"
            "Run 'git submodule update --init --recursive' from the repository root."
        )
        sys.exit(1)

    sys.path.insert(0, str(tools_pyradox_src))
    sys.path.insert(0, str(script_dir))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IR -> EU5 data converter")
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
        "--no-map",
        action="store_true",
        help="Skip writing map-specific data (images and map data only)",
    )
    return parser


def _write_country_location_counts(
    script_dir: Path,
    country_data: list[dict],
    ir_country_locations: dict[str, list[int]],
) -> None:
    """Write country -> province count report used for debugging/analysis."""
    try:
        counts_out = script_dir / "ir_to_eu5" / "country_location_counts.tsv"
        name_map = {country["tag"]: country["name"] for country in country_data}

        rows = [(len(provs), tag, name_map.get(tag, tag)) for tag, provs in ir_country_locations.items()]
        rows.extend(
            (0, country["tag"], country["name"])
            for country in country_data
            if country["tag"] not in ir_country_locations
        )
        rows.sort(key=lambda row: (-row[0], row[1]))

        counts_out.parent.mkdir(parents=True, exist_ok=True)
        with counts_out.open("w", encoding="utf-8") as handle:
            for count, tag, name in rows:
                handle.write(f"{count}\t{tag}\t{name}\n")
        print(f"Wrote {counts_out}")
    except Exception:
        # Non-fatal: converter output should still be produced.
        pass


def _extract_default_templates(
    culture_data: list[dict], religion_data: list[dict]
) -> tuple[str | None, str | None]:
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
    return default_culture, default_religion


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    _ensure_bundled_pyradox(script_dir)

    from ir_to_eu5.extract_data import (
        extract_character_data,
        extract_coa_data,
        extract_coa_template_behaviour,
        extract_country_data,
        extract_culture_data,
        extract_deity_data,
        extract_diplomacy_data,
        extract_dynasty_data,
        extract_eu5_map_data,
        extract_formable_data,
        extract_ir_country_capitals,
        extract_ir_country_locations,
        extract_named_color_data,
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
        write_coa_template_behaviour,
        write_country_setup,
        write_culture_data,
        write_culture_group_data,
        write_culture_language_report,
        write_formable_countries,
        write_god_data,
        write_ir_religious_aspects,
        write_localisation_files,
        write_named_colors_file,
        write_religion_data,
        write_religion_group_data,
    )

    args = _build_parser().parse_args()

    culture_data = extract_culture_data()
    religion_data = extract_religion_data()
    deity_data = extract_deity_data()
    character_data = extract_character_data()
    dynasty_data = extract_dynasty_data()
    country_data, country_overrides = extract_country_data()
    formable_data = extract_formable_data()
    diplomatic_relationships, international_organisations = extract_diplomacy_data()

    country_rulers = {entry["country"]: entry["tag"] for entry in character_data if entry["is_ruler"]}

    named_locations = {province_id: key for province_id, key, *_ in parse_definitions()}
    ir_country_locations = extract_ir_country_locations()
    ir_country_capitals = extract_ir_country_capitals()
    eu5_map_data = extract_eu5_map_data()

    _write_country_location_counts(script_dir, country_data, ir_country_locations)

    five_characters_data = extract_start_data("05_characters.txt", "character_db")
    four_dynasties_data = extract_start_data("04_dynasties.txt", "dynasty_manager")
    twelve_diplomacy_data = extract_start_data("12_diplomacy.txt", "diplomacy_manager")
    fifteen_international_organizations_data = extract_start_data(
        "15_international_organizations.txt", "international_organization_manager"
    )

    coa_data = None
    coa_template_blocks = None
    coa_template_list_files = None
    named_color_data = None
    if not args.no_images:
        coa_data = extract_coa_data()
        coa_template_blocks, coa_template_list_files = extract_coa_template_behaviour(
            culture_data, religion_data
        )
        named_color_data = extract_named_color_data()

    if args.json:
        write_json(culture_data, mod_root / "cultures.json")
        write_json(religion_data, mod_root / "religions.json")
        write_json(country_data, mod_root / "countries.json")
        write_json(character_data, mod_root / "characters.json")
        if coa_data is not None:
            write_json(coa_data, mod_root / "coats_of_arms.json")

    write_culture_group_data(culture_data)
    write_culture_data(culture_data)
    write_culture_language_report(culture_data)
    write_religion_group_data(religion_data)
    write_religion_data(religion_data)
    write_god_data(deity_data, religion_data)
    write_ir_religious_aspects(deity_data, religion_data)
    write_country_setup(country_data, country_overrides)

    write_formable_countries(
        formable_data=formable_data,
        country_data=country_data,
        ir_country_locations=ir_country_locations,
        ir_country_capitals=ir_country_capitals,
        id_to_key=named_locations,
        eu5_map_data=eu5_map_data,
    )

    write_04_dynasties(four_dynasties_data, dynasty_data)
    write_05_characters(five_characters_data, character_data)

    # Do not seed from EU5 base 10_countries; generate from IR data only.
    ten_countries_data: dict = {}
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
        fifteen_international_organizations_data,
        international_organisations,
    )

    if not args.no_images:
        write_coa_file(coa_data)
        write_coa_template_behaviour(coa_template_blocks, coa_template_list_files)
        write_named_colors_file(named_color_data)
        port_coa_gfx()

    if not args.no_localisation:
        write_localisation_files(
            culture_data,
            religion_data,
            country_data,
            character_data,
            dynasty_data,
            deity_data,
            formable_data=formable_data,
        )

    if not args.no_map:
        default_culture, default_religion = _extract_default_templates(
            culture_data, religion_data
        )
        port_map_data(default_culture=default_culture, default_religion=default_religion)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
