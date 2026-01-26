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


def _normalize_tag(tok: str):
    """Return the bare tag name with any existing FILE_PREFIX removed."""
    if not tok:
        return None
    s = str(tok)
    if s.startswith(FILE_PREFIX):
        s = s[len(FILE_PREFIX) :]
    return s


def _prefixed_tag(tok: str, suffix: str = ""):
    """Return a consistently prefixed tag: FILE_PREFIX + base + suffix.

    The input `tok` may already contain the prefix and/or suffix; these
    will be removed before constructing the normalized output.
    """
    if not tok:
        return None
    base = _normalize_tag(tok)
    if suffix and base.endswith(suffix):
        base = base[: -len(suffix)]
    return f"{FILE_PREFIX}{base}{suffix}"


def write_text_file(path: Path, content: str, encoding: str = "utf-8-sig", msg: str = None):
    """Write `content` to `path` and print a short report message.

    Returns the `path` for convenience.
    """
    path.write_text(content, encoding=encoding)
    if msg:
        print(msg, path)
    else:
        print("Wrote", path)
    return path


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
    culture_groups = {}
    religion_groups = {}
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
        # culture groups
        elif k.endswith("_group"):
            culture_groups[k] = v
        # religion groups (keys like religion_<cat>)
        elif k.startswith("religion_") and not k.endswith("_religion"):
            religion_groups[k] = v
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
        return write_text_file(path, "\n".join(lines) + "\n")

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
    # write culture groups localisation
    def _write_group_file(name: str, entries: dict):
        if not entries:
            return None
        path = out_dir / name
        lines = ["l_english:", ""]
        for kk, vv in sorted(entries.items()):
            safe = vv.replace('"', '\\"')
            lines.append(f" {kk}: \"{safe}\"")
        return write_text_file(path, "\n".join(lines) + "\n")

    f_cult_groups = _write_group_file(f"{FILE_PREFIX}culture_groups_l_english.yml", culture_groups)
    f_rel_groups = _write_group_file(f"{FILE_PREFIX}religion_groups_l_english.yml", religion_groups)

    # helper already printed file names; nothing more to do here


RE_BLOCK = re.compile(r"^\s*([a-z0-9_]+)\s*=\s*{", re.I | re.M)
RE_INNER = re.compile(r"^\s*([a-z0-9_]+)\s*=\s*{", re.I)
RE_RGB = re.compile(r"color\s*=\s*rgb\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}", re.I)
RE_HSV = re.compile(
    r"color\s*=\s*hsv\s*\{\s*([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*\}", re.I
)
RE_GRAPH = re.compile(r"graphical_culture\s*=\s*([a-z0-9_]+)", re.I)
RE_RELIGION = re.compile(r"religion\s*=\s*([a-z0-9_]+)", re.I)
RE_RELIGION_CATEGORY = re.compile(r"religion_category\s*=\s*([a-z0-9_]+)", re.I)
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
        # determine top-level graphical culture for fallback
        top_g = None
        gm = RE_GRAPH.search(text)
        if gm:
            top_g = gm.group(1)

        # find the top-level group block for this file (matching the filename-derived group)
        group_pat = re.compile(r"\b" + re.escape(group_base) + r"\s*=\s*{", re.I)
        m = group_pat.search(text)
        group_block_text = text
        if m:
            # locate the full brace-delimited group block
            i = text.find("{", m.end() - 1)
            if i != -1:
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
                if i <= end:
                    group_block_text = text[i + 1 : end]

        # find the inner `culture = { ... }` block if present and parse only its entries
        cult_m = re.search(r"culture\s*=\s*{", group_block_text, re.I)
        inner_search_space = group_block_text
        if cult_m:
            si = group_block_text.find("{", cult_m.end() - 1)
            if si != -1:
                depth = 0
                j = si
                while j < len(group_block_text):
                    if group_block_text[j] == "{":
                        depth += 1
                    elif group_block_text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            ei = j
                            break
                    j += 1
                if si <= ei:
                    inner_search_space = group_block_text[si + 1 : ei]

        # now find culture entries within the selected search space (handles indented names)
        for bm in RE_BLOCK.finditer(inner_search_space):
            # ensure the match is a direct child of the `culture = {}` block
            pos = bm.start()
            prefix = inner_search_space[:pos]
            # depth 0 => direct child entries; nested blocks (e.g. family)
            # will have depth > 0 and should be ignored here.
            if prefix.count("{") - prefix.count("}") != 0:
                continue
            name = bm.group(1)
            i = inner_search_space.find("{", bm.end() - 1)
            if i == -1:
                continue
            depth = 0
            j = i
            while j < len(inner_search_space):
                if inner_search_space[j] == "{":
                    depth += 1
                elif inner_search_space[j] == "}":
                    depth -= 1
                    if depth == 0:
                        end = j
                        break
                j += 1
            else:
                continue
            block = inner_search_space[i : end + 1]
            # collect preceding comment(s) as a human-readable name if available
            comment = None
            prev = inner_search_space[: bm.start()]
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
            # fallback: attempt to find a colour for this culture elsewhere
            # in the Imperator culture files (some colours live in different
            # files or are defined on the inner culture block).
            if not color or color == (0, 0, 0):
                try:
                    fc = find_color_for_culture(ir_root, name)
                    if fc:
                        color = fc
                except Exception:
                    pass
            # also fall back to a top-level file colour if present
            if not color or color == (0, 0, 0):
                try:
                    rgb_m2 = RE_RGB.search(text)
                    if rgb_m2:
                        color = (int(rgb_m2.group(1)), int(rgb_m2.group(2)), int(rgb_m2.group(3)))
                    else:
                        hsv_m2 = RE_HSV.search(text)
                        if hsv_m2:
                            color = hsv_to_rgb_int(
                                float(hsv_m2.group(1)),
                                float(hsv_m2.group(2)),
                                float(hsv_m2.group(3)),
                            )
                except Exception:
                    pass
            gm2 = RE_GRAPH.search(block)
            gfx = gm2.group(1) if gm2 else top_g

            # final fallback: generate a deterministic colour from the name
            def _name_to_color(n: str):
                # stable pseudo-random hue based on the name
                h = (sum(ord(c) for c in n) % 360) / 360.0
                s = 0.55
                v = 0.72
                return hsv_to_rgb_int(h, s, v)

            if not color or color == (0, 0, 0):
                color = _name_to_color(name)

            groups[group_base].append(
                {
                    "name": name,
                    "color": color,
                    "gfx": gfx,
                    "source": f.name,
                    "comment": comment,
                }
            )

        # fallback: if no inner cultures were found, treat the whole file/group as a single culture
        if not groups[group_base]:
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
    # write to a mod-specific filename to avoid unintentionally replacing
    # the base game's `00_culture_groups.txt` when the mod is loaded
    out_file = out_root / "ir_culture_groups.txt"
    # Header mirrors EU5 style but contains NO copied content from base game.
    lines = [
        "# avoid naming the same as Cultures and Languages",
        "",
    ]
    for group in sorted(groups.keys()):
        # append the EU5-style group name (ensure suffix) and prefix it
        base_g = f"{group}_group" if not group.endswith("_group") else group
        gname = _prefixed_tag(base_g, "_group")
        lines.append(f"{gname} = {{")
        lines.append("}")
        lines.append("")
    write_text_file(out_file, "\n".join(lines).rstrip() + "\n")
    # ensure localisation entries exist for each prefixed culture group
    for group in sorted(groups.keys()):
        base_g = f"{group}_group" if not group.endswith("_group") else group
        gname = f"{FILE_PREFIX}{base_g}"
        # prefer Imperator localisation if available, else humanize the group name
        LOCAL_ENTRIES.setdefault(gname, _choose_local_text(EU5_LOC, [group, base_g], None, _humanize_name(group)))


def write_mod_cultures(mod_root: Path, groups: dict):
    out_root = mod_root / "in_game" / "common" / "cultures"
    out_root.mkdir(parents=True, exist_ok=True)
    for group, cultures in groups.items():
        lines = [f"# Converted from Imperator group {group}", ""]
        seen = set()
        for c in cultures:
            cname = _prefixed_tag(c['name'], "_culture")
            if cname in seen:
                # skip duplicate culture definitions
                continue
            seen.add(cname)
            # prepare localisation entry
            comment = c.get('comment') if isinstance(c, dict) else None
            # Candidates include unprefixed Imperator keys so localisation
            # lookup still succeeds against the original I:R localisation map.
            disp = _choose_local_text(
                EU5_LOC,
                [c.get('name'), f"{c.get('name')}_culture", cname],
                comment,
                c.get('name'),
            )
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
            # reference the prefixed culture group key
            grp_pref = _prefixed_tag(group, "_group")
            lines.append(f"\tculture_groups = {{ {grp_pref} }}")
            lines.append(f"\t# source_file = {c['source']}")
            lines.append("}")
            lines.append("")
        out_file = out_root / f"{_prefixed_tag(group)}.txt"
        write_text_file(out_file, "\n".join(lines) + "\n")


def write_mod_religions(mod_root: Path, ir_root: Path):
    src = ir_root / "common" / "religions"
    if not src.exists():
        return
    out_root = mod_root / "in_game" / "common" / "religions"
    out_root.mkdir(parents=True, exist_ok=True)
    lines = ["# Converted Imperator religions", ""]
    # collect categories to write religion_groups file
    religion_categories = set()
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
            # try to extract an Imperator religion_category and record it
            cat_m = RE_RELIGION_CATEGORY.search(block_text)
            category = None
            if cat_m:
                category = cat_m.group(1)
                religion_categories.add(category)
            # prefix religion tag names for the mod to avoid collisions
            pref_name = _prefixed_tag(name, "_religion")
            lines.append(f"{pref_name} = {{")
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
            # write group mapping (map Imperator religion_category -> EU5 religion group)
            if category:
                # point religions at the prefixed religion group key
                lines.append(f"\tgroup = {_prefixed_tag(category, '_group')}")
            # localisation entry for religion
            disp = _choose_local_text(EU5_LOC, [name, name.replace('_religion', '')], comment, name)
            if disp:
                LOCAL_ENTRIES[pref_name] = disp
            lines.append("}")
            lines.append("")
    out_file = out_root / f"{FILE_PREFIX}religions.txt"
    write_text_file(out_file, "\n".join(lines) + "\n")

    # write religion_groups file derived from collected Imperator religion_category values
    if religion_categories:
        rg_root = mod_root / "in_game" / "common" / "religion_groups"
        rg_root.mkdir(parents=True, exist_ok=True)
        rg_lines = ["# Religion groups auto-generated from Imperator religion_category", ""]
        for cat in sorted(religion_categories):
            # prefix group name to avoid collisions and match prefixed religion tags
            gname = _prefixed_tag(cat, "_group")
            rg_lines.append(f"{gname} = {{")
            # keep colour referencing the localisation key 'religion_<cat>'
            rg_lines.append(f"\tcolor = religion_{cat}")
            rg_lines.append("}")
            rg_lines.append("")
            # ensure localisation exists for the generated group key
            LOCAL_ENTRIES.setdefault(gname, _choose_local_text(EU5_LOC, [f"religion_{cat}", cat], None, _humanize_name(cat)))
        rg_file = rg_root / f"{FILE_PREFIX}religion_groups.txt"
        write_text_file(rg_file, "\n".join(rg_lines) + "\n")
        # also ensure the plain religion_<cat> localisation key exists (used as colour/local label)
        for cat in sorted(religion_categories):
            key = f"religion_{cat}"
            LOCAL_ENTRIES.setdefault(key, _choose_local_text(EU5_LOC, [key, cat], None, _humanize_name(cat)))


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


def find_color_for_culture(ir_root: Path, culture_name: str):
    """Search all Imperator culture files for a colour defined for a specific culture name.

    Looks for a block starting with `culture_name = {` and returns the first
    RGB/HSV/float color found within that block.
    """
    candidates = [
        ir_root / "common" / "cultures",
        ir_root / "in_game" / "common" / "cultures",
    ]
    patt = re.compile(r"\b" + re.escape(culture_name) + r"\s*=\s*{", re.I)
    for src in candidates:
        if not src.exists():
            continue
        for f in sorted(src.glob("*.txt")):
            try:
                txt = f.read_text(encoding="utf-8-sig", errors="ignore")
            except Exception:
                continue
        for m in patt.finditer(txt):
            start = txt.find("{", m.end() - 1)
            if start == -1:
                continue
            depth = 0
            i = start
            end = None
            while i < len(txt):
                if txt[i] == "{":
                    depth += 1
                elif txt[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
                i += 1
            if end is None:
                continue
            block = txt[start:end+1]
            m_rgb = RE_RGB.search(block)
            if m_rgb:
                return (int(m_rgb.group(1)), int(m_rgb.group(2)), int(m_rgb.group(3)))
            m_hsv = RE_HSV.search(block)
            if m_hsv:
                return hsv_to_rgb_int(float(m_hsv.group(1)), float(m_hsv.group(2)), float(m_hsv.group(3)))
            m_float = RE_RGB_FLOAT.search(block)
            if m_float:
                a, b1, c = float(m_float.group(1)), float(m_float.group(2)), float(m_float.group(3))
                if max(a, b1, c) <= 1.0:
                    return (int(round(a*255)), int(round(b1*255)), int(round(c*255)))
                else:
                    return (int(round(a)), int(round(b1)), int(round(c)))
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
            # remove mod prefix and suffix before looking up in the I:R gfx map
            base = name
            if base.startswith(FILE_PREFIX):
                base = base[len(FILE_PREFIX):]
            if base.endswith("_culture"):
                base = base[: -len("_culture")]
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
            f.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
            print("Updated tags from I:R gfx for", f)


def write_mod_countries(mod_root: Path, ir_root: Path, tags_map: dict, groups: dict, default_order: list = None):
    out_base = mod_root / "in_game" / "setup" / "countries"
    out_base.mkdir(parents=True, exist_ok=True)
    groups_out = {}
    # Write a hardcoded `_default.txt` file per user request. This replaces the
    # dynamic `ir_countries.txt` output for the base countries listing.
    hardcoded = """# ===== countries =====

# BAR -> setup/countries/barbarians.txt
BAR = {
	color = rgb { 96 95 78 }
}

# REB -> setup/countries/rebels.txt
REB = {
	color = rgb { 40 40 40 }
}

# PIR -> setup/countries/pirates.txt
PIR = {
	color = rgb { 116 143 139 }
}

# MER -> setup/countries/mercenaries.txt
MER = {
	color = rgb { 72 85 83 }
}
"""
    out_file_default = out_base / "_default.txt"
    write_text_file(out_file_default, hardcoded.rstrip() + "\n")
    # start from explicit mappings
    for tag, rel in tags_map.items():
        p = Path(rel)
        group = p.parent.name if p.parent.name else "root"
        if group not in groups_out:
            groups_out[group] = []
        groups_out[group].append((tag, rel))
    # Prevent writing a generated `ir_countries.txt` by dropping any
    # group named 'countries' after building the mappings from `tags_map`.
    groups_out.pop("countries", None)
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

    # If a default order is provided, restrict output to only those tags
    # that appear in 00_default.txt. This prevents writing country files
    # for tags not present in the main default setup.
    if default_order:
        allowed = set(default_order)
        for grp in list(groups_out.keys()):
            entries = groups_out.get(grp, [])
            filtered = [(t, r) for (t, r) in entries if t in allowed]
            if filtered:
                groups_out[grp] = filtered
            else:
                # remove empty groups to avoid emitting empty files
                groups_out.pop(grp, None)

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
        # ensure we never write a generated `ir_countries.txt` file
        if group == "countries":
            continue
        lines = [f"# ===== {group} =====", ""]
        for tag, rel in entries:
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
                # ensure country references point at the prefixed mod tags
                if culture_def:
                    ctag = _prefixed_tag(culture_def, "_culture")
                    if ctag:
                        lines.append(f"\tculture_definition = {ctag}")
                if religion:
                    rtag = _prefixed_tag(religion, "_religion")
                    if rtag:
                        lines.append(f"\treligion_definition = {rtag}")
                lines.append("}")
                lines.append("")
            else:
                # No colour found — still emit a proper country block including
                # culture and religion if available (use I:R basegame tags).
                lines.append(f"{tag} = {{")
                if culture_def:
                    ctag = _prefixed_tag(culture_def, "_culture")
                    if ctag:
                        lines.append(f"\tculture_definition = {ctag}")
                if religion:
                    rtag = _prefixed_tag(religion, "_religion")
                    if rtag:
                        lines.append(f"\treligion_definition = {rtag}")
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
        out_file = out_base / f"{_prefixed_tag(group)}.txt"
        write_text_file(out_file, "\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eu5_root", nargs="?", default="/home/rick/Paradox/Games/Europa Universalis V/game")
    ap.add_argument("ir_root", nargs="?", default="/home/rick/Paradox/Games/Imperator Rome/game")
    ap.add_argument("mod_root", nargs="?", default="/home/rick/Paradox/Documents/Europa Universalis V/mod/Imperator Universalis")
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
    # attempt to map Imperator graphical culture names to EU5 gfx keys
    # and patch generated culture `tags = { ... }` entries where possible
    try:
        ir_gfx_map = parse_ir_gfx_map(ir_root)
        if ir_gfx_map:
            patch_tags_from_ir(mod_root, ir_gfx_map)
    except Exception:
        pass
    write_mod_religions(mod_root, ir_root)
    tags_map = parse_countries_list(ir_root)
    default_order = parse_default_order(ir_root)
    write_mod_countries(mod_root, ir_root, tags_map, groups, default_order=default_order)
    # Note: automatic patching of `tags = { ... }` from I:R gfx mappings
    # has been disabled to avoid unexpected replacements. If you want to
    # re-enable it, call `parse_ir_gfx_map()` and `patch_tags_from_ir()` here.
    patched = apply_hue_shifts(mod_root, factor=args.hue_factor)
    if patched:
        print("Hue-shifted files:", len(patched))
    # write collected localisation entries
    write_mod_localisation(mod_root)


if __name__ == "__main__":
    main()
