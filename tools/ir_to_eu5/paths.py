#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

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
            "Remove hardcoded paths and provide all required paths in tools/settings.json."
        )
    return Path(val)


def _p_optional(key: str) -> Path | None:
    val = _settings.get(key)
    if not val:
        return None
    return Path(val)


def _existing_paths(paths: Iterable[Path]) -> List[Path]:
    return [path for path in paths if path and path.exists()]


ir_game = _p("ir_game")
ir_mod = _p_optional("ir_mod")


def ir_path(relative: str) -> Path:
    """Return a file/dir path, preferring the mod when it exists."""
    if ir_mod:
        mod_path = ir_mod / relative
        if mod_path.exists():
            return mod_path
    return ir_game / relative


def ir_paths(relative: str) -> list[Path]:
    """Return base then mod paths for merging, if they exist."""
    base_path = ir_game / relative
    mod_path = ir_mod / relative if ir_mod else None
    return _existing_paths([base_path, mod_path])


def iter_ir_files(relative_dir: str, pattern: str = "*.txt", recursive: bool = False) -> list[Path]:
    """Iterate mod then base files, skipping base files overridden by the mod."""
    roots = []
    if ir_mod:
        roots.append(ir_mod / relative_dir)
    roots.append(ir_game / relative_dir)

    results: list[Path] = []
    seen: set[Path] = set()

    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        iterator = root.rglob(pattern) if recursive else root.glob(pattern)
        for path in sorted(iterator):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if rel in seen:
                continue
            seen.add(rel)
            results.append(path)

    return results


def ir_relative_display(path: Path) -> str:
    """Return a readable path relative to the mod or base game when possible."""
    if ir_mod:
        try:
            return str(path.relative_to(ir_mod))
        except ValueError:
            pass
    try:
        return str(path.relative_to(ir_game))
    except ValueError:
        return str(path)


ir_countries_dir = ir_path("setup/countries")
ir_countries_file = ir_path("setup/countries/countries.txt")
ir_default = ir_path("setup/main/00_default.txt")
ir_cultures = ir_path("common/cultures")
ir_religions = ir_path("common/religions/00_default.txt")
ir_deities = ir_path("common/deities")
ir_localisation = ir_path("localization/english")
ir_localisation_paths = ir_paths("localization/english")
ir_prescripted_coa = ir_path(
    "common/coat_of_arms/coat_of_arms/00_pre_scripted_countries.txt"
)
ir_coa_gfx = ir_path("gfx/coat_of_arms")
ir_map_data = ir_path("map_data")
ir_character_data = ir_path("setup/characters")

# EU5 game paths
eu5_game = _p("eu5_game")
eu5_countries = eu5_game / "in_game" / "setup" / "countries"
eu5_map_data = eu5_game / "in_game" / "map_data" / "definitions.txt"

# Imperator Universalis mod paths
# `mod_root` is derived from the location of this `tools` directory (two parents up).
mod_root = BASE.parent.parent

iu_countries = mod_root / "in_game" / "setup" / "countries"
iu_culture_groups = mod_root / "in_game" / "common" / "culture_groups"
iu_cultures = mod_root / "in_game" / "common" / "cultures"
iu_religion_groups = mod_root / "in_game" / "common" / "religion_groups"
iu_religions = mod_root / "in_game" / "common" / "religions"
iu_gods = mod_root / "in_game" / "common" / "gods"
iu_religious_aspects = mod_root / "in_game" / "common" / "religious_aspects"
iu_language_families = mod_root / "in_game" / "common" / "language_families"
iu_languages = mod_root / "in_game" / "common" / "languages"
iu_localisation = mod_root / "main_menu" / "localization" / "english"
iu_named_colors = mod_root / "main_menu" / "common" / "named_colors"
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
iu_setup_start = mod_root / "main_menu" / "setup" / "start"
