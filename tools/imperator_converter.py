#!/usr/bin/env python3
from ir_to_eu5.extract_data import (
    extract_country_data,
    extract_culture_data,
    extract_religion_data,
    write_json,
)
from ir_to_eu5.paths import mod_root
from ir_to_eu5.write_data import write_culture_data

if __name__ == "__main__":
    culture_data = extract_culture_data()
    religion_data = extract_religion_data()
    country_data = extract_country_data()

    # write_json(culture_data, mod_root / "cultures.json")
    # write_json(religion_data, mod_root / "religions.json")
    # write_json(country_data, mod_root / "countries.json")

    write_culture_data(culture_data)
