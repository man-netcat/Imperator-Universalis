from pathlib import Path

# Imperator Rome game paths

ir_game = Path("/home/rick/Paradox/Games/Imperator Rome/game")
ir_setup = ir_game / "setup"
ir_common = ir_game / "common"
ir_localisation = ir_game / "localization" / "english"

ir_countries_dir = ir_setup / "countries"
ir_countries_file = ir_countries_dir / "countries.txt"
ir_main = ir_setup / "main"
ir_default = ir_main / "00_default.txt"
ir_cultures = (
    ir_common / "cultures"
)  # Dir containing files each representing a culture group
ir_religions = ir_common / "religions" / "00_default.txt"

# Localisation files
ir_cultures_loc = ir_localisation / "cultures_l_english.yml"
ir_religions_loc = ir_localisation / "text_l_english.yml"
ir_countries_loc = ir_localisation / "countries_l_english.yml"


# Imperator Universalis mod paths
mod_root = Path(
    "/home/rick/Paradox/Documents/Europa Universalis V/mod/Imperator Universalis"
)
iu_in_game = mod_root / "in_game"
iu_in_game_setup = iu_in_game / "setup"
iu_main_menu = mod_root / "main_menu"
iu_countries = iu_in_game_setup / "countries"
iu_main_menu_setup = iu_main_menu / "setup"
iu_10_countries = iu_main_menu_setup / "10_countries.txt"
iu_in_game_common = iu_in_game / "common"
iu_culture_groups = iu_in_game_common / "culture_groups" / "00_culture_groups.txt"
iu_cultures = iu_in_game_common / "cultures"
iu_religion_groups = iu_in_game_common / "religion_groups" / "00_default.txt"
iu_religions = iu_in_game_common / "religions"
iu_localisation = iu_main_menu / "localization" / "english"
