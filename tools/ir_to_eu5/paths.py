from pathlib import Path

# Imperator Rome game paths

ir_game = Path("/home/rick/Paradox/Games/Imperator Rome/game")

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

# Imperator Universalis mod paths
mod_root = Path(
    "/home/rick/Paradox/Documents/Europa Universalis V/mod/Imperator Universalis"
)

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
