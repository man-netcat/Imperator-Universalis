#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any, Dict

# Load user settings from `settings.json` placed next to the base script.
BASE = Path(__file__).resolve().parent


def _load_settings() -> Dict[str, Any]:
    settings_path = BASE.parent / "settings.json"
    try:
        with settings_path.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(
            f"Missing settings file: {settings_path}\n"
            "Create tools/settings.json with keys: 'ir_game' and 'eu5_game'."
        )
    except json.JSONDecodeError:
        print(f"Invalid JSON in settings file: {settings_path}")
    except Exception as e:
        print(f"Failed to load settings from {settings_path}: {e}")

    sys.exit(1)


_settings = _load_settings()


def _p(key: str) -> Path:
    val = _settings.get(key)
    if not val:
        raise RuntimeError(
            f"Missing required setting '{key}' in settings.json.\n"
            "Remove hardcoded paths and provide all required paths in tools/ir_to_eu5/settings.json."
        )
    return Path(val)


# Imperator Rome game paths
ir_game = _p("ir_game")

ir_countries_dir = ir_game / "setup" / "countries"
ir_countries_file = ir_countries_dir / "countries.txt"
ir_default = ir_game / "setup" / "main" / "00_default.txt"
ir_cultures = (
    ir_game / "common" / "cultures"
)  # Dir containing files each representing a culture group
ir_religions = ir_game / "common" / "religions" / "00_default.txt"
ir_localisation = ir_game / "localization" / "english"
ir_prescripted_coa = (
    ir_game
    / "common"
    / "coat_of_arms"
    / "coat_of_arms"
    / "00_pre_scripted_countries.txt"
)
ir_coa_gfx = ir_game / "gfx" / "coat_of_arms"
ir_map_data = ir_game / "map_data"

# EU5 game paths
eu5_game = _p("eu5_game")
eu5_countries = eu5_game / "in_game" / "setup" / "countries"

# Imperator Universalis mod paths
# `mod_root` is derived from the location of this `tools` directory (two parents up).
mod_root = BASE.parent.parent

iu_countries = mod_root / "in_game" / "setup" / "countries"
iu_culture_groups = mod_root / "in_game" / "common" / "culture_groups"
iu_cultures = mod_root / "in_game" / "common" / "cultures"
iu_religion_groups = mod_root / "in_game" / "common" / "religion_groups"
iu_religions = mod_root / "in_game" / "common" / "religions"
iu_localisation = mod_root / "main_menu" / "localization" / "english"
iu_coa_gfx = mod_root / "main_menu" / "gfx" / "coat_of_arms"
iu_prescripted_coa = (
    mod_root
    / "main_menu"
    / "common"
    / "coat_of_arms"
    / "coat_of_arms"
    / "zz_ir_pre_scripted_countries.txt"
)
iu_map_data = mod_root / "in_game" / "map_data"
