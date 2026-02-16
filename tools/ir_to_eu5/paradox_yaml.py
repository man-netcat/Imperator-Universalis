from __future__ import annotations

import re

from pathlib import Path
from typing import Iterable, Mapping


def _iter_files(path: Path | Iterable[Path]) -> list[Path]:
    if isinstance(path, Path):
        if path.is_file():
            return [path]
        if path.is_dir():
            return sorted(p for p in path.rglob("*.yml") if p.is_file())
        return []

    files: list[Path] = []
    for entry in path:
        files.extend(_iter_files(entry))
    return files


def _parse_localisation_value(raw: str) -> str | None:
    tail = raw.lstrip()
    idx = 0
    while idx < len(tail) and tail[idx].isdigit():
        idx += 1
    while idx < len(tail) and tail[idx].isspace():
        idx += 1
    tail = tail[idx:]
    if not tail:
        return None

    if tail[0] == '"':
        out_chars: list[str] = []
        escaped = False
        for ch in tail[1:]:
            if escaped:
                if ch == "n":
                    out_chars.append("\n")
                else:
                    out_chars.append(ch)
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                break
            out_chars.append(ch)
        return "".join(out_chars)

    return tail.split("#", 1)[0].strip() or None


def parse_localisation_text(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(":"):
            # language root key, e.g. l_english:
            continue
        if ":" not in line:
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue

        value = _parse_localisation_value(raw_value)
        if value is None:
            continue

        entries[key] = value

    return entries


_LOCALISATION_TOKEN_RE = re.compile(r"\$([^$]+)\$")


def _resolve_localisation_tokens(entries: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    resolving: set[str] = set()

    def resolve_key(key: str) -> str:
        if key in resolved:
            return resolved[key]
        if key in resolving:
            return entries.get(key, "")

        resolving.add(key)
        value = entries.get(key, "")

        # Resolve nested $KEY$ references in this value.
        for _ in range(16):
            changed = False

            def repl(match: re.Match[str]) -> str:
                nonlocal changed
                token = match.group(1)
                if token not in entries:
                    return match.group(0)
                changed = True
                return resolve_key(token)

            new_value = _LOCALISATION_TOKEN_RE.sub(repl, value)
            if not changed:
                break
            value = new_value

        resolving.remove(key)
        resolved[key] = value
        return value

    for loc_key in list(entries.keys()):
        resolve_key(loc_key)

    return resolved


def read_paradox_localisation(path: Path | Iterable[Path]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for file_path in _iter_files(path):
        payload = file_path.read_text(encoding="utf-8-sig")
        merged.update(parse_localisation_text(payload))
    return _resolve_localisation_tokens(merged)


def _escape_localisation_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def write_paradox_localisation(
    out_path: Path,
    entries: Mapping[str, object],
    *,
    language_key: str = "l_english",
    header: str = "",
    sort_keys: bool = True,
    include_value_index: bool = False,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    items = entries.items()
    if sort_keys:
        items = sorted(items, key=lambda item: item[0])

    with out_path.open("w", encoding="utf-8-sig") as handle:
        if header:
            handle.write(header)
        handle.write(f"{language_key}:\n")
        for key, value in items:
            escaped = _escape_localisation_value(str(value))
            if include_value_index:
                handle.write(f"  {key}:0 \"{escaped}\"\n")
            else:
                handle.write(f"  {key}: \"{escaped}\"\n")

    return out_path
