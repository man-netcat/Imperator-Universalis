#!/usr/bin/env python3
from pathlib import Path
import json
from typing import Dict, Any

# Load user settings from a settings.json placed next to this file (or its parent).
def _load_settings() -> Dict[str, Any]:
    base = Path(__file__).resolve().parent
    candidates = [base / "settings.json", base.parent / "settings.json"]
    for p in candidates:
        if p.exists():
            try:
                with p.open() as f:
                    return json.load(f)
            except Exception:
                break
    return {}

_settings = _load_settings()

def _p(key: str, default: str) -> Path:
    val = _settings.get(key)
    return Path(val) if val else Path(default)

# Imperator Rome game paths
ir_game = _p("ir_game", "/home/rick/Paradox/Games/Imperator Rome/game")

ir_countries_dir = ir_game / "setup" / "countries"
ir_countries_file = ir_countries_dir / "countries.txt"
ir_default = ir_game / "setup" / "main" / "00_default.txt"
ir_cultures = ir_game / "common" / "cultures"  # Dir containing files each representing a culture group
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
eu5_game = _p("eu5_game", "/home/rick/Paradox/Games/Europa Universalis V/game")
eu5_countries = eu5_game / "in_game" / "setup" / "countries"

# Imperator Universalis mod paths
mod_root = _p("mod_root", "/home/rick/Paradox/Documents/Europa Universalis V/mod/Imperator Universalis")

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
