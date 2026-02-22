import json
import re
import warnings

from collections import defaultdict
from pathlib import Path
from typing import Any

import pyradox
import pyradox.datatype as _pydt
from pyradox.filetype.txt import ParseWarning
from pyradox.filetype.txt import parse as parse_txt

from .data import government_map, custom_formable_data
from .paths import *
from .coa_text_parser import (
    extract_coa_data_from_files,
    extract_coa_template_behaviour_from_files,
)
from .output_text import print_written
from .paradox_yaml import read_paradox_localisation
from .source_files import iter_overlay_files

warnings.filterwarnings("error", category=ParseWarning)

pyradox.Tree = _pydt.Tree
pyradox.Color = _pydt.Color

# ---------- Helper ----------


def parse_tree(file_path: Path):
    """Parse a file into a pyradox.Tree."""
    text = file_path.read_text(encoding="utf-8-sig")
    tree = parse_txt(text, filename=str(file_path))
    return tree


def _make_serializable(o: Any):
    if o is None or isinstance(o, (str, int, float, bool)):
        return o
    elif isinstance(o, dict):
        return {k: _make_serializable(v) for k, v in o.items()}
    elif isinstance(o, list):
        return [_make_serializable(v) for v in o]
    elif isinstance(o, _pydt.Color):
        return {"colorspace": o.colorspace, "values": o.channels}
    else:
        return str(o)


def write_json(data: Any, out_path: Path) -> Path:
    """Write `data` to `out_path` as JSON, converting non-serializable items.

    Returns the path written to.
    """
    serializable = _make_serializable(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print_written("JSON", out_path)
    return out_path


# ---------- Localisation ----------


def read_localisation_file(path: Path | list[Path] | tuple[Path, ...]) -> dict[str, str]:
    """Read localisation from one or more directories/files, later paths override."""
    return read_paradox_localisation(path)


# ---------- Data Extraction ----------


def extract_culture_data():
    culture_loc = read_localisation_file(ir_localisation_paths)
    culture_blocks = []

    for path in iter_ir_files("common/cultures"):
        if path.suffix != ".txt" or not path.is_file():
            continue

        tree = parse_tree(path)

        for group_tag, group_data in tree.items():
            [(_, ethnicity)] = group_data["ethnicities"].items()
            cultures = group_data["culture"]
            culture_blocks.append(
                {
                    "tag": f"ir_{group_tag}_g",
                    "name": f"{culture_loc[group_tag]}",
                    "name_desc": culture_loc.get(f"{group_tag}_desc", "REPLACE ME"),
                    "cultures": [
                        {
                            "tag": f"ir_{culture_tag}",
                            "name": culture_loc[culture_tag],
                        }
                        for culture_tag in cultures
                    ],
                    "color": group_data["color"],
                    "graphical_culture": f"ir_{group_data['graphical_culture']}",
                    "ethnicities": f"ir_{ethnicity}",
                }
            )

    return culture_blocks


def extract_religion_data():
    religion_tree = parse_tree(ir_religions)
    religion_loc = read_localisation_file(ir_localisation_paths)
    religion_blocks = []

    for religion_tag, religion_data in religion_tree.items():
        religion_blocks.append(
            {
                "tag": f"ir_{religion_tag}",
                "name": religion_loc[religion_tag],
                "name_adj": religion_loc.get(f"{religion_tag}_ADJ", "REPLACE ME"),
                "name_desc": religion_loc.get(f"{religion_tag}_desc", "REPLACE ME"),
                "color": religion_data["color"],
            }
        )

    return religion_blocks


def extract_deity_data():
    deity_blocks = []
    if not ir_deities.exists():
        return deity_blocks

    deity_loc = read_localisation_file(
        [path / "deities" for path in ir_localisation_paths]
    )
    deity_loc.update(
        read_localisation_file(
            [path / "god_names_l_english.yml" for path in ir_localisation_paths]
        )
    )

    def resolve_deity_name(loc_key: str) -> str | None:
        if not loc_key:
            return None
        value = deity_loc.get(loc_key)
        if value and value.startswith("$") and value.endswith("$"):
            inner = value.strip("$")
            return deity_loc.get(inner, value)
        return value

    for path in iter_ir_files("common/deities"):
        if path.suffix != ".txt" or not path.is_file():
            continue

        tree = parse_tree(path)
        for deity_tag, deity_data in tree.items():
            if not isinstance(deity_tag, str) or not deity_tag.startswith("deity_"):
                continue
            religion = deity_data["religion"]
            category = deity_data["deity_category"]

            deity_blocks.append(
                {
                    "tag": deity_tag,
                    "religion": str(religion) if religion is not None else None,
                    "category": str(category) if category is not None else None,
                    "name": resolve_deity_name(deity_tag),
                }
            )

    return deity_blocks


def extract_country_data():
    default_tree = parse_tree(ir_default)
    country_tree = default_tree["country"]["countries"]
    country_loc = read_localisation_file(ir_localisation_paths)
    setup_tree = parse_tree(ir_countries_file)

    setup_dirs = dict(setup_tree.items())
    country_blocks = []

    def _fallback_country_name(setup_file: Path, tag: str) -> str:
        stem = setup_file.stem if setup_file and setup_file.stem else ""
        if stem:
            return stem.replace("_", " ").title()
        return tag

    for country_tag, country_data in country_tree.items():
        setup_rel = setup_dirs.get(country_tag)
        if not setup_rel:
            continue
        country_setup_file = ir_path(setup_rel)
        country_setup_tree = parse_tree(country_setup_file)

        tag_loc_overrides = {
            "DEL": "Nesio",  # Nesiotic League
            "SEL": "Seleucids",  # Seleucid Empire
            "BPK": "Bospora",  # Bosporan Kingdom
            "PRY": "Antigonids",  # Antigonid Kingdom
            "EGY": "Ptolemies",  # Ptolemaic Kingdom
        }

        fallback_name = _fallback_country_name(country_setup_file, country_tag)
        country_name = tag_loc_overrides.get(
            country_tag,
            country_loc.get(country_tag, fallback_name),
        )
        country_name_adj = country_loc.get(f"{country_tag}_ADJ", country_name)

        country_blocks.append(
            {
                "tag": country_tag,
                "name": country_name,
                "name_adj": country_name_adj,
                "culture": f"ir_{country_data['primary_culture']}",
                "religion": f"ir_{country_data['religion']}",
                "government": country_data["government"],
                "government_type": government_map.get(country_data["government"]),
                "color": country_setup_tree["color"],
                "setup_dir": country_setup_file.parent.name,
                "setup_file": country_setup_file.name,
            }
        )

    # Read EU5 countries for writing overrides
    override_blocks = defaultdict(list)

    for eu5_country_file in eu5_countries.iterdir():
        eu5_countries_tree = parse_tree(eu5_country_file)
        for country_tag, country_data in eu5_countries_tree.items():
            override_blocks[eu5_country_file.relative_to(eu5_game)].append(
                {
                    "tag": country_tag,
                    "culture": country_data["culture_definition"],
                    "religion": country_data["religion_definition"],
                    "color": country_data["color"],
                }
            )

    return country_blocks, override_blocks


def _iter_ir_overlay_files(relative_dir: str, pattern: str = "*.txt") -> list[Path]:
    return iter_overlay_files(ir_mod, ir_game, relative_dir, pattern)


def _order_base_then_mod(paths: list[Path]) -> list[Path]:
    """Return paths in effective load order: base ascending, then mod ascending."""
    if not ir_mod:
        return sorted(paths)

    base_paths: list[Path] = []
    mod_paths: list[Path] = []

    for path in paths:
        try:
            path.relative_to(ir_mod)
            mod_paths.append(path)
        except ValueError:
            base_paths.append(path)

    return sorted(base_paths) + sorted(mod_paths)


def extract_coa_data():
    coa_files = _order_base_then_mod(
        _iter_ir_overlay_files("common/coat_of_arms/coat_of_arms", pattern="*.txt")
    )
    return extract_coa_data_from_files(
        coa_files=coa_files,
        fallback_coa_file=ir_prescripted_coa,
        parse_tree_fn=parse_tree,
        relative_display_fn=ir_relative_display,
    )


def extract_coa_template_behaviour(
    culture_data: list[dict[str, Any]],
    religion_data: list[dict[str, Any]],
) -> tuple[list[str], dict[str, str]]:
    coa_files = _order_base_then_mod(
        _iter_ir_overlay_files("common/coat_of_arms/coat_of_arms", pattern="*.txt")
    )
    template_list_sources = _order_base_then_mod(
        _iter_ir_overlay_files("common/coat_of_arms/template_lists", pattern="*.txt")
    )
    existing_template_dir = iu_prescripted_coa.parent
    existing_template_files = [
        existing_template_dir / "00_random_countries.txt",
        existing_template_dir / "00_random_countries_checker.txt",
        existing_template_dir / "00_random_dynasties.txt",
    ]
    return extract_coa_template_behaviour_from_files(
        coa_files=coa_files,
        template_list_sources=template_list_sources,
        existing_template_files=existing_template_files,
        culture_data=culture_data,
        religion_data=religion_data,
    )


def extract_named_color_data() -> _pydt.Tree:
    colors = _pydt.Tree()
    seen: set[str] = set()
    for color_file in _iter_ir_overlay_files("common/named_colors", pattern="*.txt"):
        try:
            tree = parse_tree(color_file)
        except ParseWarning:
            continue
        if "colors" not in tree:
            continue
        for color_name, color_value in tree["colors"].items():
            if color_name in seen:
                continue
            seen.add(color_name)
            colors[color_name] = color_value

    # Invictus references GELAEAN_FLAG with `gelaean_color`, but that color is
    # not defined in upstream named_colors files. Provide a stable fallback to
    # avoid pink fallback colors on that flag.
    if "gelaean_color" not in colors:
        colors["gelaean_color"] = _pydt.Color([224, 186, 123], "rgb")

    out = _pydt.Tree()
    out["colors"] = colors
    return out


def extract_eu5_map_data():
    defs_path = iu_map_data / "definitions.txt"
    if not defs_path.exists():
        defs_path = eu5_map_data
    tree = parse_tree(defs_path).to_python()
    return tree


def extract_start_data(file_name, root_key, sub_key=None):
    base_start = eu5_game / "main_menu" / "setup" / "start"
    if file_name == "10_countries.txt" and (base_start / file_name).exists():
        tree = parse_tree(base_start / file_name)
    else:
        tree = parse_tree(iu_setup_start / file_name)
    data = tree[root_key]
    if sub_key:
        data = data[sub_key]
    return data.to_python()


def _ir_countries_tree() -> _pydt.Tree:
    return parse_tree(ir_default)["country"]["countries"]


def extract_ir_country_locations():
    """Return mapping of country tag -> list of province IDs from IR own_control_core."""
    def _collect_ids(value: Any, out: list[int]) -> None:
        if isinstance(value, int):
            out.append(value)
        elif isinstance(value, str):
            out.append(int(value))
        elif isinstance(value, _pydt.Color):
            out.extend(int(channel) for channel in value.channels)
        elif isinstance(value, (list, tuple)):
            for v in value:
                _collect_ids(v, out)
        elif isinstance(value, (_pydt.Tree, dict)):
            for k, v in value.items():
                _collect_ids(k, out)
                _collect_ids(v, out)

    countries = _ir_countries_tree()
    result: dict[str, list[int]] = {}

    for tag, data in countries.items():
        prov_ids: list[int] = []
        for value in data.find_all("own_control_core"):
            _collect_ids(value, prov_ids)

        if prov_ids:
            seen = set()
            deduped = []
            for pid in prov_ids:
                if pid not in seen:
                    seen.add(pid)
                    deduped.append(pid)
            result[tag] = deduped

    return result


def extract_ir_country_capitals() -> dict[str, int]:
    """Return mapping of country tag -> capital province ID from IR 00_default."""
    countries = _ir_countries_tree()
    result: dict[str, int] = {}

    for tag, data in countries.items():
        capital = data["capital"]
        if capital is None:
            continue
        result[tag] = int(capital)

    return result


def extract_formable_data() -> dict[str, dict[str, object]]:
    """Return formable metadata from I:R + Invictus trigger lists via pyradox trees."""
    block_to_level = {
        "is_tier_1_formable_trigger": 1,
        "is_tier_2_formable_trigger": 2,
        "is_endgame_tag_trigger": 3,
    }
    data: dict[str, dict[str, object]] = {}
    country_loc = read_localisation_file(ir_localisation_paths)

    def _resolve_loc_value(key: str) -> str:
        value = country_loc.get(key, key)
        # Resolve simple indirection like "$ARABIA_NAME$".
        if isinstance(value, str) and value.startswith("$") and value.endswith("$"):
            inner = value.strip("$")
            return country_loc.get(inner, inner)
        return value

    def _resolve_loc_optional(key: str) -> str | None:
        if key not in country_loc:
            return None
        resolved = _resolve_loc_value(key)
        if not isinstance(resolved, str):
            return None
        text = resolved.strip()
        return text or None

    def _pretty_name_from_decision_key(decision_key: str) -> str | None:
        if not isinstance(decision_key, str):
            return None
        raw_name = _resolve_loc_value(decision_key)
        if not isinstance(raw_name, str) or not raw_name.strip():
            return None
        name = raw_name.strip()
        lower = name.lower()
        if lower.startswith("form "):
            name = name[5:].strip()
        return name or None

    def _collect_tags(node) -> list[str]:
        tags: list[str] = []
        if isinstance(node, _pydt.Tree):
            for key, value in node.items():
                if str(key) == "tag" and isinstance(value, str):
                    tags.append(value)
                else:
                    tags.extend(_collect_tags(value))
        elif isinstance(node, list):
            for item in node:
                tags.extend(_collect_tags(item))
        return tags

    for path in iter_ir_files("common/scripted_triggers"):
        if path.suffix != ".txt" or "decision" not in path.name.lower():
            continue
        tree = parse_tree(path)
        for block_name, level in block_to_level.items():
            if block_name not in tree:
                continue
            block = tree[block_name]
            if isinstance(block, list) and block:
                block = block[0]
            if not isinstance(block, _pydt.Tree):
                continue
            for tag in _collect_tags(block):
                # First source wins: keep earliest tag metadata encountered
                # (Invictus first, then base files that are not overridden).
                if tag in data:
                    continue
                current = {"level": level, "name": _resolve_loc_value(tag)}
                tag_adj = _resolve_loc_optional(f"{tag}_ADJ")
                if tag_adj:
                    current["adj"] = tag_adj
                data[tag] = current

    def _to_province_id(value) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("p:"):
                text = text[2:]
            if text.isdigit():
                return int(text)
        return None

    def _tree_get(node, key):
        if not isinstance(node, _pydt.Tree):
            return None
        if key not in node:
            return None
        return node[key]

    def _collect_change_country_tag(node) -> str | None:
        if isinstance(node, _pydt.Tree):
            for key, value in node.items():
                if str(key) == "change_country_tag" and isinstance(value, str):
                    return value
                nested = _collect_change_country_tag(value)
                if nested:
                    return nested
        elif isinstance(node, list):
            for item in node:
                nested = _collect_change_country_tag(item)
                if nested:
                    return nested
        return None

    def _infer_level_from_decision_path(path: Path) -> int:
        lower_parts = [part.lower() for part in path.parts]
        if "endgame_tags" in lower_parts:
            return 3
        if "tier_2_formables" in lower_parts:
            return 2
        if "tier_1_formables" in lower_parts:
            return 1
        return 0

    def _normalize_area(value) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if text.startswith("area:"):
            text = text[5:]
        # Ignore dynamic/script scopes and variables (not literal keys).
        if (
            not text
            or text.startswith("scope:")
            or text.startswith("root.")
            or text.startswith("prev.")
            or text.startswith("from.")
            or text.startswith("p:")
            or "$" in text
        ):
            return None
        # Some IR content uses cross-tier names (e.g. *_region passed to area checks).
        if text.endswith("_area") or text.endswith("_region"):
            return text
        return f"{text}_area"

    def _normalize_region(value) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if text.startswith("region:"):
            text = text[7:]
        # Ignore dynamic/script scopes and variables (not literal keys).
        if (
            not text
            or text.startswith("scope:")
            or text.startswith("root.")
            or text.startswith("prev.")
            or text.startswith("from.")
            or text.startswith("p:")
            or "$" in text
        ):
            return None
        # Some IR content uses cross-tier names (e.g. bohemia_area in region checks).
        if text.endswith("_region") or text.endswith("_area"):
            return text
        return f"{text}_region"

    def _extract_scope_requirements(
        node,
        locations: set[int],
        regions: set[str],
        areas: set[str],
        region_percent: list[tuple[int, float]],
        parse_or: bool = False,
    ) -> None:
        if not isinstance(node, _pydt.Tree):
            return
        for key, value in node.items():
            k = str(key)
            if k in {"OR", "NOR"}:
                if parse_or:
                    branches = value if isinstance(value, list) else [value]
                    for branch in branches:
                        if isinstance(branch, _pydt.Tree):
                            _extract_scope_requirements(
                                branch, locations, regions, areas, region_percent, parse_or=False
                            )
                continue
            if k in {"NOT"}:
                continue

            if k in {"owns_or_subject_owns", "owns"}:
                if isinstance(value, list):
                    for item in value:
                        pid = _to_province_id(item)
                        if pid is not None:
                            locations.add(pid)
                else:
                    pid = _to_province_id(value)
                    if pid is not None:
                        locations.add(pid)
                continue

            if k in {"owns_or_subject_owns_region", "owns_region"}:
                if isinstance(value, list):
                    for item in value:
                        region = _normalize_region(item)
                        if region:
                            regions.add(region)
                else:
                    region = _normalize_region(value)
                    if region:
                        regions.add(region)
                continue

            if k in {"owns_or_subject_owns_area", "owns_area"}:
                if isinstance(value, list):
                    for item in value:
                        area = _normalize_area(item)
                        if area:
                            areas.add(area)
                else:
                    area = _normalize_area(value)
                    if area:
                        areas.add(area)
                continue

            if k == "owns_percent_of_region":
                blocks = value if isinstance(value, list) else [value]
                for block in blocks:
                    if not isinstance(block, _pydt.Tree):
                        continue
                    pid = _to_province_id(_tree_get(block, "PROVINCE"))
                    pct = _tree_get(block, "PERCENT")
                    try:
                        pct_val = float(str(pct).strip('"')) if pct is not None else 1.0
                    except ValueError:
                        pct_val = 1.0
                    if pid is not None:
                        region_percent.append((pid, pct_val))
                continue

            if k == "is_in_region":
                region = _normalize_region(value)
                if region:
                    regions.add(region)
                continue
            if k == "is_in_area":
                area = _normalize_area(value)
                if area:
                    areas.add(area)
                continue
            if k == "province_id":
                if isinstance(value, list):
                    for item in value:
                        pid = _to_province_id(item)
                        if pid is not None:
                            locations.add(pid)
                else:
                    pid = _to_province_id(value)
                    if pid is not None:
                        locations.add(pid)
                continue

            # Recurse into compound/nested blocks (AND, scope blocks, custom_tooltip wrappers, etc.).
            if isinstance(value, _pydt.Tree):
                _extract_scope_requirements(
                    value, locations, regions, areas, region_percent, parse_or=parse_or
                )
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, _pydt.Tree):
                        _extract_scope_requirements(
                            item, locations, regions, areas, region_percent, parse_or=parse_or
                        )

    def _extract_identity_requirements(
        node,
        primary_cultures: set[str],
        culture_groups: set[str],
        religions: set[str],
    ) -> None:
        if not isinstance(node, _pydt.Tree):
            return
        for key, value in node.items():
            k = str(key)

            if k in {"NOT", "NOR"}:
                continue

            if k == "primary_culture":
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            primary_cultures.add(item)
                elif isinstance(value, str):
                    primary_cultures.add(value)
                continue

            if k == "country_culture_group":
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            culture_groups.add(item)
                elif isinstance(value, str):
                    culture_groups.add(value)
                continue

            if k == "religion":
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            religions.add(item)
                elif isinstance(value, str):
                    religions.add(value)
                continue

            if isinstance(value, _pydt.Tree):
                _extract_identity_requirements(value, primary_cultures, culture_groups, religions)
                continue

            if isinstance(value, list):
                for item in value:
                    if isinstance(item, _pydt.Tree):
                        _extract_identity_requirements(
                            item, primary_cultures, culture_groups, religions
                        )

    for path in iter_ir_files("decisions", pattern="*.txt", recursive=True):
        tree = parse_tree(path)
        inferred_level = _infer_level_from_decision_path(path)
        if "country_decisions" not in tree:
            continue
        decisions = tree["country_decisions"]
        if isinstance(decisions, list) and decisions:
            decisions = decisions[0]
        if not isinstance(decisions, _pydt.Tree):
            continue

        for _decision_name, decision_value in decisions.items():
            block = decision_value[0] if isinstance(decision_value, list) and decision_value else decision_value
            if not isinstance(block, _pydt.Tree):
                continue
            effect = _tree_get(block, "effect")
            effect = effect[0] if isinstance(effect, list) and effect else effect
            form_tag = _collect_change_country_tag(effect)
            if not form_tag:
                continue

            # First source wins for decision requirements per formable tag.
            existing = data.get(form_tag)
            if isinstance(existing, dict) and existing.get("has_decision_requirements"):
                continue
            current = existing if isinstance(existing, dict) else {
                "level": 0,
                "name": _resolve_loc_value(form_tag),
            }
            if inferred_level > 0:
                current["level"] = max(inferred_level, int(current.get("level", 0)))
            if current.get("name") in {form_tag, None, ""}:
                decision_name = _pretty_name_from_decision_key(str(_decision_name))
                if decision_name:
                    current["name"] = decision_name
            if not current.get("adj"):
                tag_adj = _resolve_loc_optional(f"{form_tag}_ADJ")
                if tag_adj:
                    current["adj"] = tag_adj
            if not current.get("desc"):
                decision_desc = _resolve_loc_optional(f"{_decision_name}_desc")
                if decision_desc:
                    current["desc"] = decision_desc
            current["has_decision_requirements"] = True
            locations: set[int] = set()
            regions: set[str] = set()
            areas: set[str] = set()
            region_percent: list[tuple[int, float]] = []

            allow = _tree_get(block, "allow")
            allow = allow[0] if isinstance(allow, list) and allow else allow
            if isinstance(allow, _pydt.Tree):
                _extract_scope_requirements(
                    allow, locations, regions, areas, region_percent, parse_or=False
                )

            # Secondary source for explicit target scope when allow has no direct location list.
            if not locations and not regions and not areas:
                highlight = _tree_get(block, "highlight")
                highlight = highlight[0] if isinstance(highlight, list) and highlight else highlight
                if isinstance(highlight, _pydt.Tree):
                    _extract_scope_requirements(
                        highlight, locations, regions, areas, region_percent, parse_or=True
                    )

            primary_cultures: set[str] = set()
            culture_groups: set[str] = set()
            religions: set[str] = set()

            potential = _tree_get(block, "potential")
            potential = potential[0] if isinstance(potential, list) and potential else potential
            if isinstance(potential, _pydt.Tree):
                _extract_identity_requirements(
                    potential, primary_cultures, culture_groups, religions
                )
            if isinstance(allow, _pydt.Tree):
                _extract_identity_requirements(
                    allow, primary_cultures, culture_groups, religions
                )

            if locations:
                existing = set(current.get("required_location_ids", []))
                current["required_location_ids"] = sorted(existing | locations)
            if regions:
                existing = set(current.get("required_regions", []))
                current["required_regions"] = sorted(existing | regions)
            if areas:
                existing = set(current.get("required_areas", []))
                current["required_areas"] = sorted(existing | areas)
            if region_percent:
                existing = list(current.get("required_region_percent", []))
                current["required_region_percent"] = existing + region_percent
            if primary_cultures:
                existing = set(current.get("required_primary_cultures", []))
                current["required_primary_cultures"] = sorted(existing | primary_cultures)
            if culture_groups:
                existing = set(current.get("required_culture_groups", []))
                current["required_culture_groups"] = sorted(existing | culture_groups)
            if religions:
                existing = set(current.get("required_religions", []))
                current["required_religions"] = sorted(existing | religions)

            data[form_tag] = current

    # Backstop: any decision-derived formable without explicit tier still behaves as tier 1.
    for tag, meta in data.items():
        if meta.get("has_decision_requirements") and int(meta.get("level", 0)) <= 0:
            meta["level"] = 1

    # Inject curated custom formables that are outside vanilla I:R/Invictus pools.
    for tag, meta in custom_formable_data.items():
        if tag in data:
            continue
        data[tag] = dict(meta)

    return data


def extract_formable_tags() -> dict[str, int]:
    """Return formable tag -> EU5 level, collected from I:R + Invictus triggers."""
    return {tag: int(meta["level"]) for tag, meta in extract_formable_data().items()}


def extract_character_data():
    character_loc = read_localisation_file(ir_localisation_paths)

    def is_ruler(char_data):
        for key, value in char_data.items():
            if key.startswith("c:") and value["set_as_ruler"]:
                return True
        return False

    characters = []
    tag_counts = {}

    for path in iter_ir_files("setup/characters"):
        if path.suffix != ".txt" or not path.is_file():
            continue

        character_tree = parse_tree(path)
        for _, country_characters in character_tree.items():
            for char_id, char_data in country_characters.items():
                if char_id == "country":
                    # Set country tag for this loop
                    country_tag = char_data
                    continue

                ruler_flag = is_ruler(char_data)
                if "first_name" in char_data:
                    ir_name_tag = char_data["first_name"]
                    name_tag = char_data["first_name"]
                    name = (
                        character_loc[ir_name_tag]
                        if ir_name_tag in character_loc
                        else ir_name_tag
                    )
                else:
                    name_tag = None

                if "nickname" in char_data:
                    nickname_tag = char_data["nickname"]
                    nickname = (
                        (
                            character_loc[char_data["nickname"]]
                            if nickname_tag in character_loc
                            else nickname_tag
                        )
                        .strip("'")
                        .replace(" ", "_")
                    )
                else:
                    nickname_tag = None
                    nickname = None

                dynasty = None
                if "family" in char_data:
                    if char_data["family"].startswith("c:"):
                        dynasty = f"{char_data['family'].split(':')[2].lower()}"
                    else:
                        dynasty = char_data["family"]
                    dynasty_tag = f"{dynasty.lower().replace(' ', '_')}_dynasty"
                    dynasty_name = dynasty
                else:
                    dynasty_tag = None
                    dynasty_name = None

                father = (
                    (
                        int(char_data["father"].split(":")[1])
                        if char_data["father"].startswith("char:")
                        else None
                    )
                    if "father" in char_data
                    else None
                )
                mother = (
                    (
                        int(char_data["mother"].split(":")[1])
                        if char_data["mother"].startswith("char:")
                        else None
                    )
                    if "mother" in char_data
                    else None
                )
                spouse = (
                    (
                        int(char_data["marry_character"].split(":")[1])
                        if char_data["marry_character"].startswith("char:")
                        else None
                    )
                    if "marry_character" in char_data
                    else None
                )

                # Construct base unique tag
                parts = [country_tag]
                if name:
                    parts.append(name.lower().replace(" ", "_"))
                else:
                    parts.append("char")
                if dynasty:
                    parts.append(dynasty.lower().replace(" ", "_"))
                base_tag = "_".join(parts).lower()

                # Make tag truly unique
                if base_tag in tag_counts:
                    tag_counts[base_tag] += 1
                    unique_tag = f"{base_tag}_{tag_counts[base_tag]}"
                else:
                    tag_counts[base_tag] = 1
                    unique_tag = base_tag

                data = {
                    "id": int(char_id),
                    "name_tag": name_tag,
                    "name": name,
                    "dynasty_tag": dynasty_tag,
                    "dynasty_name": (dynasty.capitalize() if dynasty else None),
                    "nickname_tag": nickname_tag,
                    "nickname": nickname,
                    "birth_date": char_data["birth_date"],
                    "death_date": (
                        char_data["death_date"] if "death_date" in char_data else None
                    ),
                    "father": father,
                    "mother": mother,
                    "female": char_data["female"] if "female" in char_data else False,
                    "spouse": spouse,
                    "culture": f"ir_{char_data['culture']}",
                    "religion": f"ir_{char_data['religion']}",
                    "country": country_tag,
                    "scope": char_data["save_scope_as"],
                    "is_ruler": ruler_flag,
                    "tag": unique_tag,  # final unique tag
                }
                characters.append(data)
    return characters


def extract_dynasty_data():
    """Extract dynasties from IR default family database."""
    families_tree = parse_tree(ir_default)["family"]["families"]

    dynasties = []
    seen = set()

    for _, family in families_tree.items():
        if isinstance(family, (_pydt.Tree, dict)) and "key" in family:
            name = str(family["key"])
        else:
            continue
        tag = f"{name.lower().replace(' ', '_')}_dynasty"
        if tag in seen:
            continue
        seen.add(tag)
        dynasties.append({"tag": tag, "name": name})

    return dynasties


def extract_diplomacy_data():
    diplomacy_data = parse_tree(ir_default)["diplomacy"]
    diplomatic_relationships = []
    international_organizations = []
    for diplomacy_type, data in diplomacy_data.items():
        if diplomacy_type == "defensive_league":
            # Should be done through International Organisation
            international_organizations.append(
                {
                    "type": "defensive_league",
                    "members": [member for member in data.values()],
                }
            )
        elif diplomacy_type == "dependency":
            # Actual vassal relationships
            diplomatic_relationships.append(
                {
                    "tag": "dependency",
                    "first": data["first"],
                    "second": data["second"],
                    "subject_type": data["subject_type"],
                }
            )
        elif diplomacy_type == "alliance":
            # scripted_mutual with type = alliance
            diplomatic_relationships.append(
                {
                    "tag": "scripted_mutual",
                    "first": data["first"],
                    "second": data["second"],
                    "type": "alliance",
                }
            )
        elif diplomacy_type == "guarantee":
            # scripted_oneway with type = guarantee
            diplomatic_relationships.append(
                {
                    "tag": "scripted_oneway",
                    "first": data["first"],
                    "second": data["second"],
                    "type": "guarantee",
                }
            )
        else:
            # TODO: Handle trade_access
            pass
    return diplomatic_relationships, international_organizations
