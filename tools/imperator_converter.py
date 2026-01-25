#!/usr/bin/env python3
"""Consolidated Imperator -> EU5 converter.

This single script replaces the previous multi-script pipeline. It parses
Imperator Rome `common/cultures` and `setup/countries` plus `common/religions`
and writes EU5-structured files under the mod `in_game` tree. It also applies
an optional hue shift to inner cultures so they are visually distinct.

Usage:
  python3 imperator_converter.py <eu5_root> <ir_root> <mod_root> [--hue-factor 0.04]
"""
from pathlib import Path
import argparse
import re
import sys
import colorsys


# runtime EU5 localisation map (populated in main)
EU5_LOC = {}

# runtime I:R localisation map (populated in main)
IR_LOC = {}

# prefix for all generated files
FILE_PREFIX = "ir_"


# localisation helpers
def parse_eu5_localisation(eu5_root: Path):
    loc_dir = eu5_root / "main_menu" / "localization" / "english"
    mapping = {}
    if not loc_dir.exists():
        return mapping
    rx = re.compile(r"^\s*([^:\s]+)\s*:\s*\d+\s*\"(.*)\"\s*$")
    for f in sorted(loc_dir.glob("*")):
        try:
            txt = f.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        for ln in txt.splitlines():
            m = rx.match(ln)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                mapping[key] = val
    return mapping


def parse_ir_localisation(ir_root: Path):
    """Parse Imperator localisation files (english) and return mapping key->string.

    Scans common locations where Imperator stores localisation; tolerates a
    couple of layout variants (top-level `localization/english` or
    `in_game/localization/english`).
    """
    candidates = [
        ir_root / "localization" / "english",
        ir_root / "in_game" / "localization" / "english",
    ]
    mapping = {}
    # flexible regex: key : [optional number] "value"
    rx = re.compile(r"^\s*([^:\s]+)\s*:\s*(?:\d+\s*)?\"(.*)\"\s*$")
    for loc in candidates:
        if not loc.exists():
            continue
        for f in sorted(loc.glob("*")):
            try:
                txt = f.read_text(encoding="utf-8-sig")
            except Exception:
                continue
            for ln in txt.splitlines():
                m = rx.match(ln)
                if m:
                    key = m.group(1).strip()
                    val = m.group(2).strip()
                    if key and val:
                        mapping[key] = val
    return mapping


def _humanize_name(name: str):
    return name.replace("_", " ").replace("-", " ").strip().title()


def _choose_local_text(eu5_loc: dict, candidates: list, comment: str, fallback: str):
    # Strict localisation policy: only use Imperator localisation strings.
    # If none of the candidate keys exist in the I:R localisation, return the
    # literal marker "MISSING" (no fallbacks allowed).
    for k in candidates:
        if not k:
            continue
        if k in IR_LOC:
            return IR_LOC[k]
    return "MISSING"


def derive_adjective(name: str) -> str:
    """Derive a plausible English adjective from a country/display name.

    This uses a small exceptions table and a set of simple suffix heuristics.
    It's intentionally conservative — if nothing sensible is produced the
    function returns a title-cased form of the input.
    """
    if not name:
        return ""
    exceptions = {
        "France": "French",
        "Greece": "Greek",
        "England": "English",
        "Scotland": "Scottish",
        "Ireland": "Irish",
        "Rome": "Roman",
        "Persia": "Persian",
        "Spain": "Spanish",
        "Germany": "German",
        "Egypt": "Egyptian",
        "Herakleia Minoa": "Minoan",
        "Minoa": "Minoan",
        "Athens": "Athenian",
        "Byzantion": "Byzantine",
        "Byzantium": "Byzantine",
    }
    n = name.strip().strip('"')
    if not n:
        return ""
    # case-insensitive exceptions match
    for k, v in exceptions.items():
        if n.lower() == k.lower():
            return v
    # prefer the last word for multi-word names (e.g. "New Granada" -> Granada)
    parts = n.split()
    stem = parts[-1]
    # remove punctuation
    stem = re.sub(r"[^\w]", "", stem)
    # normalize trailing single 'i' which often denotes a plural/latin ending
    # e.g. 'Ambiani' -> 'Ambian' before applying adjectival suffixes
    if stem.lower().endswith('i') and len(stem) > 2:
        stem = stem[:-1]
    if not stem:
        return n.title()
    # if the stem already looks adjectival, return it title-cased
    adjectival_suffixes = ("ian", "an", "ese", "ish", "ic", "ean", "ine")
    low = stem.lower()
    for sfx in adjectival_suffixes:
        if low.endswith(sfx):
            return stem.title()
    # common pattern: ...ia -> ...ian (India -> Indian)
    if low.endswith("ia") and len(stem) > 2:
        return (stem[:-2] + "ian").title()
    # common classical pattern: ...ion -> ...ine (Byzantion -> Byzantine)
    # prefer handling Greek '-eion' endings as '-eian' (Hemeroskopeion -> Hemeroskopeian)
    if low.endswith("eion") and len(stem) > 4:
        return (stem[:-4] + "eian").title()

    # common classical pattern: ...ion -> ...ine (Byzantion -> Byzantine)
    if low.endswith("ion") and len(stem) > 3:
        return (stem[:-3] + "ine").title()

    # special-case: names ending in 'nses' -> produce '-nsian'
    # Example: 'Eburones' -> 'Eburonsian'
    if low.endswith("nses") and len(stem) > 4:
        return (stem[:-2] + "ian").title()

    # helper to safely join stem + suffix avoiding duplicated vowels/letters
    def join_safe(stem: str, suf: str) -> str:
        if not stem:
            return suf.title()
        base = stem
        v = "aeiou"
        # trim trailing characters while they conflict with suffix start
        while base and (base[-1].lower() == suf[0].lower() or (base[-1].lower() in v and suf[0].lower() in v)):
            base = base[:-1]
        if not base:
            # nothing left, fall back to title-cased concatenation
            return (stem + suf).title()
        return (base + suf).title()

    # try a sequence of common adjective suffixes with safe join
    for suf in ("ian", "ese", "ish", "ic", "an"):
        cand = join_safe(stem, suf)
        if cand.lower() != stem.lower():
            return cand

    # fallback: title-case the stem
    return stem.title()


# collect localisation entries for the mod
LOCAL_ENTRIES = {}



def write_mod_localisation(mod_root: Path):
    if not LOCAL_ENTRIES:
        return
    out_dir = mod_root / "in_game" / "localization" / "english"
    out_dir.mkdir(parents=True, exist_ok=True)

    countries = {}
    cultures = {}
    religions = {}
    for k, v in LOCAL_ENTRIES.items():
        # country tags are typically uppercase 2-3 letter codes
        if k.isupper() and len(k) <= 3:
            countries[k] = v
        # explicit culture keys
        elif k.endswith("_culture"):
            cultures[k] = v
        # adjectives for countries (TAG_ADJ) should be grouped with countries
        elif k.endswith("_ADJ"):
            countries[k] = v
        else:
            # treat remaining as religions or generic keys
            religions[k] = v

    def _write_file(name: str, entries: dict):
        if not entries:
            return None
        path = out_dir / name
        lines = ["l_english:", ""]
        for kk, vv in sorted(entries.items()):
            safe = vv.replace('"', '\\"')
            lines.append(f" {kk}: \"{safe}\"")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
        return path

    # add adjective entries for countries: use I:R localisation `_ADJ` keys only.
    # No fallbacks or derivation — if an adjective key is not present in the
    # Imperator localisation, write the literal marker "MISSING".
    for tag in list(countries.keys()):
        # avoid creating duplicate adjective keys for entries that are
        # already adjective keys (e.g. TAG_ADJ). Only add TAG_ADJ for
        # base country tags.
        if tag.endswith("_ADJ"):
            continue
        adj_key = f"{tag}_ADJ"
        if adj_key in IR_LOC:
            countries[adj_key] = IR_LOC[adj_key]
        else:
            countries[adj_key] = "MISSING"

    f_countries = _write_file(f"{FILE_PREFIX}countries_l_english.yml", countries)
    
    # tidy religion values: remove trailing descriptive words that read awkward
    # in-game (e.g. "Anatolian Religion" -> "Anatolian", "Egyptian Pantheon" -> "Egyptian")
    for rk, rv in list(religions.items()):
        if not rv:
            continue
        val = rv
        if val.lower().endswith(" religion"):
            val = val[: -len(" Religion")].strip()
        if val.lower().endswith(" pantheon"):
            val = val[: -len(" Pantheon")].strip()
        religions[rk] = val

    f_cultures = _write_file(f"{FILE_PREFIX}cultures_l_english.yml", cultures)
    f_religion = _write_file(f"{FILE_PREFIX}religion_l_english.yml", religions)

    if f_countries:
        print("Wrote localisation to", f_countries)
    if f_cultures:
        print("Wrote localisation to", f_cultures)
    if f_religion:
        print("Wrote localisation to", f_religion)


RE_BLOCK = re.compile(r"^([a-z0-9_]+)\s*=\s*{", re.I)
RE_INNER = re.compile(r"^\s*([a-z0-9_]+)\s*=\s*{", re.I)
RE_RGB = re.compile(r"color\s*=\s*rgb\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}", re.I)
RE_HSV = re.compile(
    r"color\s*=\s*hsv\s*\{\s*([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*\}", re.I
)
RE_GRAPH = re.compile(r"graphical_culture\s*=\s*([a-z0-9_]+)", re.I)
RE_RELIGION = re.compile(r"religion\s*=\s*([a-z0-9_]+)", re.I)
RE_COUNTRY_LINE = re.compile(r"^([A-Z0-9]{2,3})\s*=\s*\"([^\"]+)\"$")
RE_RGB_FLOAT = re.compile(
    r"color\s*=\s*\{\s*([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*\}", re.I
)


def hsv_to_rgb_int(h, s, v):
    if h > 1:
        h = h / 360.0
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def parse_ir_cultures(ir_root: Path):
    src = ir_root / "common" / "cultures"
    groups = {}
    if not src.exists():
        return groups
    for f in sorted(src.glob("*.txt")):
        text = f.read_text(encoding="utf-8-sig")
        group_base = re.sub(r"^[0-9]+_", "", f.stem)
        group_base = re.sub(r"_group$", "", group_base)
        groups[group_base] = []
        top_g = None
        gm = RE_GRAPH.search(text)
        if gm:
            top_g = gm.group(1)
        for bm in RE_BLOCK.finditer(text):
            name = bm.group(1)
            i = text.find("{", bm.end() - 1)
            if i == -1:
                continue
            depth = 0
            j = i
            while j < len(text):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        end = j
                        break
                j += 1
            else:
                continue
            block = text[i : end + 1]
            if name == "culture" or name.endswith("_group"):
                continue
            # collect preceding comment(s) as a human-readable name if available
            comment = None
            prev = text[: bm.start()]
            pls = prev.rstrip().splitlines()
            comments = []
            for ln in reversed(pls[-8:]):
                ln = ln.strip()
                if ln.startswith("#"):
                    comments.append(ln.lstrip("#").strip())
                elif ln == "":
                    continue
                else:
                    break
            if comments:
                comments.reverse()
                comment = " ".join([c for c in comments if c])
            rgb_m = RE_RGB.search(block)
            color = None
            if rgb_m:
                color = (int(rgb_m.group(1)), int(rgb_m.group(2)), int(rgb_m.group(3)))
            else:
                hsv_m = RE_HSV.search(block)
                if hsv_m:
                    color = hsv_to_rgb_int(
                        float(hsv_m.group(1)),
                        float(hsv_m.group(2)),
                        float(hsv_m.group(3)),
                    )
            gm2 = RE_GRAPH.search(block)
            gfx = gm2.group(1) if gm2 else top_g
            groups[group_base].append(
                {
                    "name": name,
                    "color": color,
                    "gfx": gfx,
                    "source": f.name,
                    "comment": comment,
                }
            )
        if not groups[group_base]:
            # fallback: use group name as single culture
            name = group_base
            rgb_m = RE_RGB.search(text)
            color = None
            if rgb_m:
                color = (int(rgb_m.group(1)), int(rgb_m.group(2)), int(rgb_m.group(3)))
            else:
                hsv_m = RE_HSV.search(text)
                if hsv_m:
                    color = hsv_to_rgb_int(
                        float(hsv_m.group(1)),
                        float(hsv_m.group(2)),
                        float(hsv_m.group(3)),
                    )
            groups[group_base].append(
                {"name": name, "color": color, "gfx": top_g, "source": f.name, "comment": None}
            )
    return groups


def write_mod_culture_groups(mod_root: Path, groups: dict):
    """Write a culture_groups file for the mod derived from Imperator groups.

    Each Imperator group becomes a `group_name_group = { }` entry to match
    EU5 layout. The file is intentionally lightweight (empty bodies) so it
    can be extended later with modifiers.
    """
    out_root = mod_root / "in_game" / "common" / "culture_groups"
    out_root.mkdir(parents=True, exist_ok=True)
    out_file = out_root / "00_culture_groups.txt"
    # Header mirrors EU5 style but contains NO copied content from base game.
    lines = [
        "# avoid naming the same as Cultures and Languages",
        "",
    ]
    for group in sorted(groups.keys()):
        # append the EU5-style group name (ensure suffix)
        gname = f"{group}_group" if not group.endswith("_group") else group
        lines.append(f"{gname} = {{")
        lines.append("}")
        lines.append("")
    out_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8-sig")
    print("Wrote", out_file)


def write_mod_cultures(mod_root: Path, groups: dict):
    out_root = mod_root / "in_game" / "common" / "cultures"
    out_root.mkdir(parents=True, exist_ok=True)
    for group, cultures in groups.items():
        lines = [f"# Converted from Imperator group {group}", ""]
        for c in cultures:
            cname = f"{c['name']}_culture"
            # prepare localisation entry
            comment = c.get('comment') if isinstance(c, dict) else None
            disp = _choose_local_text(EU5_LOC, [cname, c.get('name'), f"{c.get('name')}_culture"], comment, c.get('name'))
            if disp:
                LOCAL_ENTRIES[cname] = disp
            lines.append(f"{cname} = {{")
            if c["color"]:
                r, g, b = c["color"]
                lines.append(f"\tcolor = rgb {{ {r} {g} {b} }}")
            else:
                lines.append("\t# no color")
            if c["gfx"]:
                lines.append(f"\ttags = {{ {c['gfx']} }}")
            else:
                lines.append("\ttags = { imperator_gfx }")
            lines.append(f"\tculture_groups = {{ {group}_group }}")
            lines.append(f"\t# source_file = {c['source']}")
            lines.append("}")
            lines.append("")
        out_file = out_root / f"{FILE_PREFIX}{group}.txt"
        out_file.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
        print("Wrote", out_file)


def write_mod_religions(mod_root: Path, ir_root: Path):
    src = ir_root / "common" / "religions"
    if not src.exists():
        return
    out_root = mod_root / "in_game" / "common" / "religions"
    out_root.mkdir(parents=True, exist_ok=True)
    lines = ["# Converted Imperator religions", ""]
    for f in sorted(src.glob("*.txt")):
        txt = f.read_text(encoding="utf-8-sig")
        lns = txt.splitlines()
        i = 0
        while i < len(lns):
            line = lns[i].lstrip("\ufeff")
            m = re.match(r"^([a-zA-Z0-9_]+)\s*=\s*{", line)
            if not m:
                i += 1
                continue
            name = m.group(1)
            # collect block lines
            block_lines = [lns[i]]
            depth = lns[i].count("{") - lns[i].count("}")
            i += 1
            while i < len(lns) and depth > 0:
                block_lines.append(lns[i])
                depth += lns[i].count("{") - lns[i].count("}")
                i += 1
            block_text = "\n".join(block_lines)
            # try to capture a comment from the block for localisation
            comment = None
            for bl in block_lines:
                if bl.strip().startswith("#"):
                    comment = bl.strip().lstrip("#").strip()
                    break
            # try to extract a color
            rgb_m = RE_RGB.search(block_text)
            hsv_m = RE_HSV.search(block_text)
            float_m = RE_RGB_FLOAT.search(block_text)
            lines.append(f"{name} = {{")
            if rgb_m:
                r, g, b = int(rgb_m.group(1)), int(rgb_m.group(2)), int(rgb_m.group(3))
                lines.append(f"\tcolor = rgb {{ {r} {g} {b} }}")
            elif hsv_m:
                r, g, b = hsv_to_rgb_int(
                    float(hsv_m.group(1)), float(hsv_m.group(2)), float(hsv_m.group(3))
                )
                lines.append(f"\tcolor = rgb {{ {r} {g} {b} }}")
            elif float_m:
                a, b1, c = (
                    float(float_m.group(1)),
                    float(float_m.group(2)),
                    float(float_m.group(3)),
                )
                # detect whether values are normalized (0..1) or already 0..255
                if max(a, b1, c) <= 1.0:
                    r, g, b = (
                        int(round(a * 255)),
                        int(round(b1 * 255)),
                        int(round(c * 255)),
                    )
                else:
                    r, g, b = int(round(a)), int(round(b1)), int(round(c))
                lines.append(f"\tcolor = rgb {{ {r} {g} {b} }}")
            else:
                lines.append("\t# no color")
            # localisation entry for religion
            disp = _choose_local_text(EU5_LOC, [name, name.replace('_religion', '')], comment, name)
            if disp:
                LOCAL_ENTRIES[name] = disp
            lines.append("}")
            lines.append("")
    out_file = out_root / f"{FILE_PREFIX}religions.txt"
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("Wrote", out_file)


def parse_countries_list(ir_root: Path):
    p = ir_root / "setup" / "countries" / "countries.txt"
    tags = {}
    if not p.exists():
        return tags
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = RE_COUNTRY_LINE.match(line)
        if m:
            tags[m.group(1)] = m.group(2)
    return tags


def find_country_file_for_tag(ir_root: Path, tag: str):
    """Fallback: scan setup/countries files for a tag definition and return
    a path relative to the ir_root if found, otherwise None.
    """
    base = ir_root / "setup" / "countries"
    if not base.exists():
        return None
    patt = re.compile(r'^\s*' + re.escape(tag) + r"\s*=\s*\{", re.M)
    for f in sorted(base.rglob("*.txt")):
        try:
            txt = f.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception:
            continue
        if patt.search(txt):
            # return a path relative to the game root to match existing tags_map values
            try:
                return str(f.relative_to(ir_root))
            except Exception:
                return str(f)
    return None


def parse_default_order(ir_root: Path):
    """Return a list of country tags in the order they appear in 00_default.txt.

    This preserves the game's logical ordering and is used to drive the
    generation order for the mod country output when available.
    """
    p = ir_root / "setup" / "main" / "00_default.txt"
    if not p.exists():
        return []
    try:
        txt = p.read_text(encoding="utf-8-sig")
    except Exception:
        return []
    # find occurrences like: SCE = {
    tags = []
    for m in re.finditer(r"^\s*([A-Z0-9]{2,3})\s*=\s*\{", txt, re.M):
        tag = m.group(1)
        # ignore purely-numeric entries (these are often non-country entries)
        if not any(c.isalpha() for c in tag):
            continue
        if tag not in tags:
            tags.append(tag)
    return tags


def extract_color(file_path: Path):
    try:
        txt = file_path.read_text(encoding="utf-8-sig")
    except Exception:
        return None
    m = RE_RGB.search(txt)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = RE_HSV.search(txt)
    if m:
        return hsv_to_rgb_int(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return None


def apply_hue_shifts(mod_root: Path, factor: float = 0.04):
    cult_dir = mod_root / "in_game" / "common" / "cultures"
    if not cult_dir.exists():
        return []
    patched = []
    for f in sorted(cult_dir.glob("*.txt")):
        text = f.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        blocks = []
        i = 0
        while i < len(lines):
            m = RE_BLOCK.match(lines[i].lstrip("\ufeff"))
            if not m:
                i += 1
                continue
            start = i
            depth = 0
            while i < len(lines):
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
                if depth <= 0:
                    end = i
                    blocks.append((start, end))
                    break
        if not blocks:
            continue
        bstart, bend = blocks[0]
        base_rgb = None
        for j in range(bstart, bend):
            m = RE_RGB.search(lines[j])
            if m:
                base_rgb = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
                break
        if not base_rgb:
            continue
        bh, bs, bv = colorsys.rgb_to_hsv(
            base_rgb[0] / 255.0, base_rgb[1] / 255.0, base_rgb[2] / 255.0
        )
        out = list(lines)
        changed = False
        for idx, (s, e) in enumerate(blocks):
            new_h = (bh + idx * factor) % 1.0
            nr, ng, nb = hsv_to_rgb_int(new_h, bs, bv)
            replaced = False
            for j in range(s, e):
                if RE_RGB.search(lines[j]):
                    indent = re.match(r"^(\s*)", lines[j]).group(1)
                    out[j] = f"{indent}color = rgb {{ {nr} {ng} {nb} }}"
                    replaced = True
                    changed = True
                    break
            if not replaced:
                for j in range(s, e):
                    if "{" in lines[j]:
                        out.insert(j + 1, f"\tcolor = rgb {{ {nr} {ng} {nb} }}")
                        changed = True
                        break
        if changed:
            f.write_text("\n".join(out) + "\n", encoding="utf-8-sig")
            patched.append(f.name)
    return patched


def parse_ir_gfx_map(ir_root: Path):
    mapping = {}
    src = ir_root / "common" / "cultures"
    if not src.exists():
        return mapping
    for f in sorted(src.glob("*.txt")):
        txt = f.read_text(encoding="utf-8-sig")
        for m in re.finditer(r"([a-z0-9_]+)\s*=\s*\{", txt, re.I):
            name = m.group(1)
            start = txt.find("{", m.end() - 1)
            if start == -1:
                continue
            i = start
            depth = 0
            while i < len(txt):
                if txt[i] == "{":
                    depth += 1
                elif txt[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
                i += 1
            block = txt[start : end + 1]
            gm = RE_GRAPH.search(block)
            if gm:
                mapping[name] = gm.group(1)
            else:
                idx = block.find("culture")
                if idx != -1:
                    sub = block[idx:]
                    for mm in re.finditer(r"([a-z0-9_]+)\s*=\s*\{", sub, re.I):
                        iname = mm.group(1)
                        istart = sub.find("{", mm.end() - 1)
                        if istart == -1:
                            continue
                        j = istart
                        d = 0
                        while j < len(sub):
                            if sub[j] == "{":
                                d += 1
                            elif sub[j] == "}":
                                d -= 1
                                if d == 0:
                                    iend = j
                                    break
                            j += 1
                        iblock = sub[istart : iend + 1]
                        gm2 = RE_GRAPH.search(iblock)
                        if gm2:
                            mapping[iname] = gm2.group(1)
                        else:
                            if gm:
                                mapping[iname] = gm.group(1)
    return mapping


def patch_tags_from_ir(mod_root: Path, ir_map: dict):
    mod_dir = mod_root / "in_game" / "common" / "cultures"
    if not mod_dir.exists():
        return
    for f in sorted(mod_dir.glob("*.txt")):
        text = f.read_text(encoding="utf-8-sig")
        out_lines = []
        lines = text.splitlines()
        i = 0
        changed = False
        while i < len(lines):
            m = re.match(r"^([a-z0-9_]+)\s*=\s*{", lines[i].lstrip("\ufeff"), re.I)
            if not m:
                out_lines.append(lines[i])
                i += 1
                continue
            name = m.group(1)
            bl = []
            depth = 0
            while i < len(lines):
                l = lines[i]
                bl.append(l)
                depth += l.count("{") - l.count("}")
                i += 1
                if depth <= 0:
                    break
            btext = "\n".join(bl)
            base = name.replace("_culture", "")
            gfx = ir_map.get(base)
            if gfx:
                if re.search(r"tags\s*=\s*\{[^}]*\}", btext, re.I):
                    new_block = re.sub(
                        r"tags\s*=\s*\{[^}]*\}",
                        f"tags = {{ {gfx} }}",
                        btext,
                        flags=re.I,
                    )
                else:
                    new_block = btext.replace("{", "{\n\ttags = { " + gfx + " }", 1)
                out_lines.extend(new_block.splitlines())
                changed = True
            else:
                out_lines.extend(bl)
        if changed:
            f.write_text("\n".join(out_lines) + "\n", encoding="utf-8-sig")
            print("Updated tags from I:R gfx for", f)


def write_mod_countries(mod_root: Path, ir_root: Path, tags_map: dict, groups: dict, default_order: list = None):
    out_base = mod_root / "in_game" / "setup" / "countries"
    out_base.mkdir(parents=True, exist_ok=True)
    groups_out = {}
    # start from explicit mappings
    for tag, rel in tags_map.items():
        p = Path(rel)
        group = p.parent.name if p.parent.name else "root"
        if group not in groups_out:
            groups_out[group] = []
        groups_out[group].append((tag, rel))
    # ensure tags that appear in 00_default.txt but are not listed in
    # countries.txt are included using the fallback scanner
    if default_order:
        for tag in default_order:
            # already present from countries.txt
            present = any(tag == t for grp in groups_out.values() for (t, _) in grp)
            if present:
                continue
            rel = find_country_file_for_tag(ir_root, tag)
            if not rel:
                continue
            p = Path(rel)
            group = p.parent.name if p.parent.name else "root"
            if group not in groups_out:
                groups_out[group] = []
            groups_out[group].append((tag, rel))

    # If a default order is provided (from 00_default.txt), reorder the
    # grouped entries to follow that sequence. Tags not present in the
    # default order will be appended afterwards.
    if default_order:
        ordered_groups = {}
        tag_to_rel = {t: r for t, r in tags_map.items()}
        for tag in default_order:
            if tag not in tag_to_rel:
                continue
            rel = tag_to_rel[tag]
            p = Path(rel)
            group = p.parent.name if p.parent.name else "root"
            if group not in ordered_groups:
                ordered_groups[group] = []
            ordered_groups[group].append((tag, rel))
        # append remaining tags that weren't in default_order
        for group, entries in groups_out.items():
            if group not in ordered_groups:
                ordered_groups[group] = list(entries)
            else:
                existing = {t for t, _ in ordered_groups[group]}
                for t, r in entries:
                    if t not in existing:
                        ordered_groups[group].append((t, r))
        groups_out = ordered_groups

    # try to read default setup file for additional country info
    default_setup = ir_root / "setup" / "main" / "00_default.txt"
    default_txt = None
    if default_setup.exists():
        try:
            default_txt = default_setup.read_text(encoding='utf-8-sig')
        except Exception:
            default_txt = None

    def _extract_from_default(tag: str):
        if not default_txt:
            return None, None
        # find all occurrences of the country block for this tag and inspect
        # each full brace-delimited block. Prefer blocks that contain
        # `primary_culture` and `religion` (in that order).
        pattern = re.compile(r"\b" + re.escape(tag) + r"\s*=\s*\{", re.I)
        best_r = None
        best_c = None
        for m in pattern.finditer(default_txt):
            # find the full brace-delimited block starting at m.end()-1
            i = m.end() - 1
            depth = 0
            block_start = i
            block_end = None
            while i < len(default_txt):
                ch = default_txt[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        block_end = i + 1
                        break
                i += 1
            if not block_end:
                # fallback to a limited window if braces couldn't be matched
                start = max(0, m.start() - 500)
                end = min(len(default_txt), m.start() + 500)
                block = default_txt[start:end]
            else:
                block = default_txt[m.start():block_end]

            # extract religion and culture from the block
            r = None
            c = None
            rm = RE_RELIGION.search(block)
            if rm:
                r = rm.group(1)
            # Prefer explicit primary_culture, then culture_definition, then culture
            cm = re.search(r"primary_culture\s*=\s*([a-z0-9_]+)", block, re.I)
            if not cm:
                cm = re.search(r"culture_definition\s*=\s*([a-z0-9_]+)", block, re.I)
            if not cm:
                cm = re.search(r"culture\s*=\s*([a-z0-9_]+)", block, re.I)
            if cm:
                c = cm.group(1)

            # choose the best candidate: prefer having both, then culture, then religion
            if best_c and best_r:
                # already have ideal candidate
                break
            if c and r:
                best_c = c
                best_r = r
                break
            if c and not best_c:
                best_c = c
            if r and not best_r:
                best_r = r

        return best_r, best_c

    for group, entries in groups_out.items():
        lines = [f"# ===== {group} =====", ""]
        for tag, rel in entries:
            # only generate countries for tags that exist in the Imperator localisation
            if tag not in IR_LOC:
                continue
            ir_file = None
            color = None
            # rel may be a path relative to the game root; try several candidates
            if rel:
                candidates = [
                    ir_root / rel,
                    ir_root / "setup" / rel,
                    ir_root / "setup" / "countries" / rel,
                    ir_root / "setup" / "countries" / Path(rel).name,
                ]
                for c in candidates:
                    if c.exists():
                        ir_file = c
                        break
            # if we still don't have a file, attempt scanning fallback
            if not ir_file:
                found = find_country_file_for_tag(ir_root, tag)
                if found:
                    fq = ir_root / found
                    if fq.exists():
                        ir_file = fq
            if ir_file:
                color = extract_color(ir_file)
            # omit `culture_definition` for now — leave culture mapping out
            # of generated country files until reviewed
            religion = None
            txt = ""
            if ir_file:
                try:
                    txt = ir_file.read_text(encoding='utf-8-sig')
                except Exception:
                    txt = ""
            # prefer values from default setup if available
            r_def, c_def = _extract_from_default(tag)
            religion = r_def
            culture_def = c_def
            # fall back to parsing the individual country file
            if not religion:
                rm = RE_RELIGION.search(txt)
                if rm:
                    religion = rm.group(1)
            if not culture_def:
                cm = re.search(r"culture_definition\s*=\s*([a-z0-9_]+)", txt, re.I)
                if not cm:
                    cm = re.search(r"culture\s*=\s*([a-z0-9_]+)", txt, re.I)
                if cm:
                    culture_def = cm.group(1)

            lines.append(f"# {tag} -> {rel}")
            if color:
                r, g, b = color
                lines.append(f"{tag} = {{")
                lines.append(f"\tcolor = rgb {{ {r} {g} {b} }}")
                if culture_def:
                    lines.append(f"\tculture_definition = {culture_def}")
                if religion:
                    lines.append(f"\treligion_definition = {religion}")
                lines.append("}")
                lines.append("")
            else:
                # No colour found — still emit a proper country block including
                # culture and religion if available (use I:R basegame tags).
                lines.append(f"{tag} = {{")
                if culture_def:
                    lines.append(f"\tculture_definition = {culture_def}")
                if religion:
                    lines.append(f"\treligion_definition = {religion}")
                lines.append("}")
                lines.append("")
            # localisation for country tag — prefer I:R localisation string, then filename fallback
            # localisation for country tag — use I:R localisation only; no fallback
            LOCAL_ENTRIES[tag] = IR_LOC.get(tag, "MISSING")
            # also include adjective key from I:R if present, otherwise mark MISSING
            adjk = f"{tag}_ADJ"
            if adjk in IR_LOC:
                LOCAL_ENTRIES[adjk] = IR_LOC[adjk]
            else:
                LOCAL_ENTRIES[adjk] = "MISSING"
        out_file = out_base / f"{FILE_PREFIX}{group}.txt"
        out_file.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eu5_root")
    ap.add_argument("ir_root")
    ap.add_argument("mod_root")
    ap.add_argument("--hue-factor", type=float, default=0.04)
    args = ap.parse_args()

    eu5_root = Path(args.eu5_root)
    ir_root = Path(args.ir_root)
    mod_root = Path(args.mod_root)
    # load EU5 basegame localisation to prefer existing keys; also load I:R localisation
    global EU5_LOC, IR_LOC
    EU5_LOC = parse_eu5_localisation(eu5_root)
    IR_LOC = parse_ir_localisation(ir_root)

    groups = parse_ir_cultures(ir_root)
    write_mod_cultures(mod_root, groups)
    # write culture_groups derived from the converted culture files (EU5-style, empty bodies)
    write_mod_culture_groups(mod_root, groups)
    write_mod_religions(mod_root, ir_root)
    tags_map = parse_countries_list(ir_root)
    default_order = parse_default_order(ir_root)
    write_mod_countries(mod_root, ir_root, tags_map, groups, default_order=default_order)
    ir_map = parse_ir_gfx_map(ir_root)
    patch_tags_from_ir(mod_root, ir_map)
    patched = apply_hue_shifts(mod_root, factor=args.hue_factor)
    if patched:
        print("Hue-shifted files:", len(patched))
    # write collected localisation entries
    write_mod_localisation(mod_root)


if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()
