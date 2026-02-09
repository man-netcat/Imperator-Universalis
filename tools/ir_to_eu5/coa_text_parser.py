from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import pyradox.datatype as _pydt
from pyradox.filetype.txt import ParseWarning
from pyradox.filetype.txt import parse as parse_txt

from .script_utils import (
    brace_delta,
    extract_assignment_blocks,
    extract_block_body,
    rename_assignment_key,
    replace_file_extensions,
    replace_strings_recursive,
    strip_inline_comment,
)


def _replace_tga_with_dds_text(text: str) -> str:
    return replace_file_extensions(text, (".tga", ".png"), ".dds")


def _build_ir_key_maps(
    culture_data: list[dict[str, Any]], religion_data: list[dict[str, Any]]
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    culture_map: dict[str, str] = {}
    culture_group_map: dict[str, str] = {}
    religion_map: dict[str, str] = {}

    for group in culture_data:
        group_tag = group.get("tag")
        if isinstance(group_tag, str) and group_tag.startswith("ir_") and group_tag.endswith("_g"):
            culture_group_map[group_tag[3:-2]] = group_tag
        for culture in group.get("cultures", []):
            culture_tag = culture.get("tag")
            if isinstance(culture_tag, str) and culture_tag.startswith("ir_"):
                culture_map[culture_tag[3:]] = culture_tag

    for religion in religion_data:
        religion_tag = religion.get("tag")
        if isinstance(religion_tag, str) and religion_tag.startswith("ir_"):
            religion_map[religion_tag[3:]] = religion_tag

    return culture_map, culture_group_map, religion_map


def _build_group_to_cultures(culture_data: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for group in culture_data:
        group_tag = group.get("tag")
        if not isinstance(group_tag, str):
            continue
        cultures: list[str] = []
        for culture in group.get("cultures", []):
            tag = culture.get("tag")
            if isinstance(tag, str):
                cultures.append(tag)
        if cultures:
            out[group_tag] = cultures
    return out


def _remap_assignment_values(text: str, key: str, value_map: dict[str, str]) -> str:
    if not value_map:
        return text

    pattern = re.compile(
        rf'(\b{re.escape(key)}\s*=\s*)(?:"([A-Za-z0-9_@:\-\.]+)"|([A-Za-z0-9_@:\-\.]+))'
    )

    def _repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        quoted_val = match.group(2)
        bare_val = match.group(3)
        old = quoted_val if quoted_val is not None else bare_val
        new = value_map.get(old, old)
        if quoted_val is not None:
            return f'{prefix}"{new}"'
        return f"{prefix}{new}"

    return pattern.sub(_repl, text)


def _remap_coa_script_keys(
    text: str,
    culture_map: dict[str, str],
    culture_group_map: dict[str, str],
    religion_map: dict[str, str],
) -> str:
    out = text
    out = _remap_assignment_values(out, "primary_culture", culture_map)
    out = _remap_assignment_values(out, "country_culture_group", culture_group_map)
    out = _remap_assignment_values(out, "religion", religion_map)
    return out


def _normalize_template_trigger_syntax(
    text: str, group_to_cultures: dict[str, list[str]]
) -> str:
    def _collapse_unsupported_trigger_blocks(src: str) -> str:
        key_re = re.compile(
            r"^\s*(?:"
            r"is_color|"
            r"in_color_list|"
            r"has_white_flag_trigger|"
            r"has_yellow_flag_trigger|"
            r"ROOT\.(?:color|color1|color2|color3|color4|color5)(?:\.[A-Za-z_]+)?"
            r")\s*=\s*\{"
        )

        lines = src.splitlines()
        out_lines: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if key_re.match(strip_inline_comment(line)):
                indent = line[: len(line) - len(line.lstrip())]
                out_lines.append(f"{indent}always = yes")
                depth = brace_delta(line)
                i += 1
                while i < len(lines) and depth > 0:
                    depth += brace_delta(lines[i])
                    i += 1
                continue
            out_lines.append(line)
            i += 1
        return "\n".join(out_lines)

    def _primary_repl(match: re.Match[str]) -> str:
        indent, val = match.group(1), match.group(2)
        return f"{indent}scope:actor ?= {{ culture = culture:{val} }}"

    def _religion_repl(match: re.Match[str]) -> str:
        indent, val = match.group(1), match.group(2)
        return f"{indent}scope:actor ?= {{ religion = religion:{val} }}"

    def _group_repl(match: re.Match[str]) -> str:
        indent, val = match.group(1), match.group(2)
        cultures = group_to_cultures.get(val, [])
        if not cultures:
            return f"{indent}scope:actor ?= {{ always = no }}"
        inner = " ".join(f"culture = culture:{c}" for c in cultures)
        return f"{indent}scope:actor ?= {{ OR = {{ {inner} }} }}"

    out = text
    out = _collapse_unsupported_trigger_blocks(out)
    out = re.sub(
        r'(^\s*)primary_culture\s*=\s*"?(ir_[A-Za-z0-9_]+)"?\s*$',
        _primary_repl,
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r'(^\s*)religion\s*=\s*"?(ir_[A-Za-z0-9_]+)"?\s*$',
        _religion_repl,
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r'(^\s*)country_culture_group\s*=\s*"?(ir_[A-Za-z0-9_]+)"?\s*$',
        _group_repl,
        out,
        flags=re.MULTILINE,
    )

    def _primary_inline(match: re.Match[str]) -> str:
        return f"scope:actor ?= {{ culture = culture:{match.group(1)} }}"

    def _religion_inline(match: re.Match[str]) -> str:
        return f"scope:actor ?= {{ religion = religion:{match.group(1)} }}"

    def _group_inline(match: re.Match[str]) -> str:
        group = match.group(1)
        cultures = group_to_cultures.get(group, [])
        if not cultures:
            return "scope:actor ?= { always = no }"
        inner = " ".join(f"culture = culture:{c}" for c in cultures)
        return f"scope:actor ?= {{ OR = {{ {inner} }} }}"

    out = re.sub(r'\bprimary_culture\s*=\s*"?(ir_[A-Za-z0-9_]+)"?', _primary_inline, out)
    out = re.sub(r'\breligion\s*=\s*"?(ir_[A-Za-z0-9_]+)"?', _religion_inline, out)
    out = re.sub(
        r'\bcountry_culture_group\s*=\s*"?(ir_[A-Za-z0-9_]+)"?', _group_inline, out
    )

    out = re.sub(r"\bROOT\.(?:color|color1|color2|color3|color4|color5)(?:\.[A-Za-z_]+)?\b", "always", out)
    out = re.sub(r"\bhas_white_flag_trigger\b", "always = yes", out)
    out = re.sub(r"\bhas_yellow_flag_trigger\b", "always = yes", out)
    out = re.sub(r"\bis_color\b", "always = yes", out)
    out = re.sub(r"\bin_color_list\b", "always = yes", out)

    out = re.sub(r"(^\s*)always\s*(?:<=|>=|<|>)\s*.+$", r"\1always = yes", out, flags=re.MULTILINE)
    out = re.sub(r"(^\s*)always\s*=\s*\{\s*$", r"\1always = yes", out, flags=re.MULTILINE)
    out = re.sub(r"(^\s*)always\s*=\s*(?!yes\b|no\b).+$", r"\1always = yes", out, flags=re.MULTILINE)

    return out


def _normalize_color_list_aliases(text: str) -> str:
    return re.sub(r'(\blist\s+")metals(")', r'\1metal_colors_list\2', text)


def _normalize_coa_text(
    text: str,
    culture_map: dict[str, str],
    culture_group_map: dict[str, str],
    religion_map: dict[str, str],
    group_to_cultures: dict[str, list[str]],
) -> str:
    out = _replace_tga_with_dds_text(text)
    out = _remap_coa_script_keys(out, culture_map, culture_group_map, religion_map)
    out = _normalize_template_trigger_syntax(out, group_to_cultures)
    out = _normalize_color_list_aliases(out)
    return out


def _merge_container_block_text(top_key: str, existing: str, incoming: str) -> str:
    existing_inner = extract_assignment_blocks(extract_block_body(existing))
    incoming_inner = extract_assignment_blocks(extract_block_body(incoming))
    if not existing_inner or not incoming_inner:
        return existing
    if any(re.fullmatch(r"\d+", key) for key, _ in existing_inner + incoming_inner):
        return existing

    ordered_keys: list[str] = []
    merged: dict[str, str] = {}
    for key, block in existing_inner:
        if key in merged:
            continue
        ordered_keys.append(key)
        merged[key] = block
    for key, block in incoming_inner:
        if key in merged:
            continue
        ordered_keys.append(key)
        merged[key] = block

    lines = [f"{top_key} = {{"]
    for key in ordered_keys:
        for line in merged[key].splitlines():
            lines.append(f"    {line}" if line.strip() else "")
        lines.append("")
    lines.append("}")
    return "\n".join(lines)


def _rewrite_ir_coa_templates_to_eu5_style(text: str) -> str:
    top_blocks = extract_assignment_blocks(text)
    if not top_blocks:
        return text

    rebuilt_top_blocks: list[str] = []
    changed = False

    for top_key, top_block in top_blocks:
        if top_key != "coat_of_arms_template_lists":
            rebuilt_top_blocks.append(top_block)
            continue

        inner_blocks = extract_assignment_blocks(extract_block_body(top_block))
        if not inner_blocks:
            rebuilt_top_blocks.append(top_block)
            continue

        inner_map: dict[str, str] = {}
        ordered_keys: list[str] = []
        for key, block in inner_blocks:
            if key in inner_map:
                continue
            inner_map[key] = block
            ordered_keys.append(key)

        if "all" not in inner_map:
            rebuilt_top_blocks.append(top_block)
            continue

        all_block = inner_map["all"]
        if "country" not in inner_map:
            inner_map["country"] = rename_assignment_key(all_block, "country")
        if "dynasty" not in inner_map:
            inner_map["dynasty"] = rename_assignment_key(all_block, "dynasty")

        ordered_keys = [k for k in ordered_keys if k != "all"]
        for required in ("dynasty", "country"):
            if required in ordered_keys:
                ordered_keys.remove(required)
            ordered_keys.insert(0, required)

        lines = ["coat_of_arms_template_lists = {"]
        for key in ordered_keys:
            block = inner_map.get(key)
            if not block:
                continue
            for line in block.splitlines():
                lines.append(f"    {line}" if line.strip() else "")
            lines.append("")
        lines.append("}")
        rebuilt_top_blocks.append("\n".join(lines))
        changed = True

    if not changed:
        return text
    return "\n\n".join(block for block in rebuilt_top_blocks if block)


def extract_coa_data_from_files(
    coa_files: list[Path],
    fallback_coa_file: Path,
    parse_tree_fn: Callable[[Path], _pydt.Tree],
    relative_display_fn: Callable[[Path], str],
) -> _pydt.Tree:
    coa_tree = _pydt.Tree()
    seen_tags: set[str] = set()
    skipped_blocks: list[str] = []

    if coa_files:
        for coa_file in coa_files:
            text = coa_file.read_text(encoding="utf-8-sig")
            for key, block_text in extract_assignment_blocks(text):
                if key in {"template", "coat_of_arms_template_lists"}:
                    continue
                if key in seen_tags:
                    continue
                try:
                    parsed = parse_txt(_replace_tga_with_dds_text(block_text), filename=f"{coa_file}:{key}")
                except ParseWarning:
                    skipped_blocks.append(f"{relative_display_fn(coa_file)}::{key}")
                    continue
                if key in parsed:
                    seen_tags.add(key)
                    coa_tree[key] = parsed[key]

    if not seen_tags:
        coa_tree = parse_tree_fn(fallback_coa_file)

    if skipped_blocks:
        print("Skipped unparsable COA blocks: " + ", ".join(skipped_blocks))

    replace_strings_recursive(coa_tree, lambda s: replace_file_extensions(s, (".tga",), ".dds"))
    return coa_tree


def extract_coa_template_behaviour_from_files(
    coa_files: list[Path],
    template_list_sources: list[Path],
    existing_template_files: list[Path],
    culture_data: list[dict[str, Any]],
    religion_data: list[dict[str, Any]],
) -> tuple[list[str], dict[str, str]]:
    template_entries: dict[str, str] = {}
    template_list_blocks: dict[str, str] = {}
    culture_map, culture_group_map, religion_map = _build_ir_key_maps(culture_data, religion_data)
    group_to_cultures = _build_group_to_cultures(culture_data)

    existing_template_names: set[str] = set()
    for existing_path in existing_template_files:
        if not existing_path.exists():
            continue
        existing_text = existing_path.read_text(encoding="utf-8-sig")
        for existing_key, existing_block in extract_assignment_blocks(existing_text):
            if existing_key != "template":
                continue
            for inner_key, _ in extract_assignment_blocks(extract_block_body(existing_block)):
                existing_template_names.add(inner_key)

    for coa_file in coa_files:
        text = coa_file.read_text(encoding="utf-8-sig")
        for key, block_text in extract_assignment_blocks(text):
            normalized = _normalize_coa_text(
                block_text,
                culture_map,
                culture_group_map,
                religion_map,
                group_to_cultures,
            )

            if key == "template":
                for inner_key, inner_block in extract_assignment_blocks(extract_block_body(block_text)):
                    if inner_key in template_entries or inner_key in existing_template_names:
                        continue
                    transformed_inner = _normalize_coa_text(
                        inner_block,
                        culture_map,
                        culture_group_map,
                        religion_map,
                        group_to_cultures,
                    )
                    template_entries[inner_key] = transformed_inner
            elif key.endswith("_template_lists") and key not in template_list_blocks:
                template_list_blocks[key] = normalized

    blocks: list[str] = []
    if template_entries:
        lines = ["template = {"]
        for entry in template_entries.values():
            for line in entry.splitlines():
                lines.append(f"    {line}" if line.strip() else "")
            lines.append("")
        lines.append("}")
        blocks.append("\n".join(lines))

    blocks.extend(template_list_blocks.values())

    output_template_files: dict[str, str] = {}
    output_file_order: list[str] = []

    for file_path in template_list_sources:
        if file_path.name in {"color_lists.txt", "country_color_lists.txt"}:
            continue

        text = file_path.read_text(encoding="utf-8-sig")
        top_blocks = extract_assignment_blocks(text)
        if not top_blocks:
            continue

        if file_path.name not in output_template_files:
            output_file_order.append(file_path.name)
            output_template_files[file_path.name] = ""

        existing_blocks = extract_assignment_blocks(output_template_files[file_path.name])
        existing_map = {k: v for k, v in existing_blocks}
        ordered_keys = [k for k, _ in existing_blocks]

        for top_key, top_block in top_blocks:
            if top_key not in existing_map:
                existing_map[top_key] = top_block
                ordered_keys.append(top_key)
            else:
                existing_map[top_key] = _merge_container_block_text(top_key, existing_map[top_key], top_block)

        merged_text = "\n\n".join(existing_map[key] for key in ordered_keys if key in existing_map)
        merged_text = _normalize_coa_text(
            merged_text,
            culture_map,
            culture_group_map,
            religion_map,
            group_to_cultures,
        )

        if file_path.name == "coa_templates.txt":
            merged_text = _rewrite_ir_coa_templates_to_eu5_style(merged_text)

        if merged_text.strip():
            output_template_files[file_path.name] = merged_text

    if output_file_order:
        output_template_files = {name: output_template_files[name] for name in output_file_order}

    return blocks, output_template_files
