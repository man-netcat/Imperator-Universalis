from __future__ import annotations

from typing import Any


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def replace_file_extensions(text: str, old_suffixes: tuple[str, ...], new_suffix: str) -> str:
    """Case-insensitive suffix replacement with a word-boundary check."""
    if not text:
        return text

    out: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        replaced = False
        for suffix in old_suffixes:
            size = len(suffix)
            if i + size > n:
                continue
            chunk = text[i : i + size]
            if chunk.lower() != suffix.lower():
                continue
            next_char = text[i + size] if i + size < n else ""
            if next_char and _is_word_char(next_char):
                continue
            out.append(new_suffix)
            i += size
            replaced = True
            break
        if replaced:
            continue
        out.append(text[i])
        i += 1

    return "".join(out)


def replace_strings_recursive(obj: Any, transform) -> None:
    """Mutate nested mapping/list structures by applying `transform` to each string."""
    if isinstance(obj, list):
        for idx, value in enumerate(obj):
            if isinstance(value, str):
                obj[idx] = transform(value)
            else:
                replace_strings_recursive(value, transform)
        return

    if isinstance(obj, dict) or hasattr(obj, "items"):
        for key, value in list(obj.items()):
            if isinstance(value, str):
                obj[key] = transform(value)
            else:
                replace_strings_recursive(value, transform)


def strip_inline_comment(line: str) -> str:
    in_quote = False
    escaped = False
    out_chars: list[str] = []

    for ch in line:
        if escaped:
            out_chars.append(ch)
            escaped = False
            continue
        if ch == "\\" and in_quote:
            out_chars.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_quote = not in_quote
            out_chars.append(ch)
            continue
        if ch == "#" and not in_quote:
            break
        out_chars.append(ch)

    return "".join(out_chars)


def brace_delta(line: str) -> int:
    in_quote = False
    escaped = False
    delta = 0

    for ch in strip_inline_comment(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_quote:
            escaped = True
            continue
        if ch == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if ch == "{":
            delta += 1
        elif ch == "}":
            delta -= 1

    return delta


def _find_unquoted_equals(text: str) -> int:
    in_quote = False
    escaped = False

    for idx, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_quote:
            escaped = True
            continue
        if ch == '"':
            in_quote = not in_quote
            continue
        if not in_quote and ch == "=":
            return idx

    return -1


def _extract_assignment_key(line: str) -> str | None:
    clean = strip_inline_comment(line).strip()
    if not clean:
        return None

    eq_idx = _find_unquoted_equals(clean)
    if eq_idx <= 0:
        return None

    lhs = clean[:eq_idx].strip()
    if not lhs:
        return None

    if lhs.startswith('"') and lhs.endswith('"') and len(lhs) >= 2:
        lhs = lhs[1:-1]

    if not lhs:
        return None

    return lhs


def extract_assignment_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        key = _extract_assignment_key(line)
        if key is None:
            i += 1
            continue

        block_lines = [line]
        depth = brace_delta(line)
        i += 1

        while depth > 0 and i < len(lines):
            nxt = lines[i]
            block_lines.append(nxt)
            depth += brace_delta(nxt)
            i += 1

        block_text = "\n".join(block_lines).strip()
        if block_text:
            blocks.append((key, block_text))

    return blocks


def extract_block_body(block_text: str) -> str:
    start = block_text.find("{")
    if start == -1:
        return ""

    depth = 0
    end = -1
    in_quote = False
    escaped = False
    in_comment = False

    for idx, ch in enumerate(block_text[start:], start=start):
        if in_comment:
            if ch == "\n":
                in_comment = False
            continue

        if escaped:
            escaped = False
            continue

        if ch == "\\" and in_quote:
            escaped = True
            continue

        if ch == '"':
            in_quote = not in_quote
            continue

        if not in_quote and ch == "#":
            in_comment = True
            continue

        if in_quote:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx
                break

    if end == -1:
        return ""

    return block_text[start + 1 : end]


def rename_assignment_key(block_text: str, new_key: str) -> str:
    lines = block_text.splitlines()
    if not lines:
        return f"{new_key} = {{}}"

    line = lines[0]
    eq_idx = _find_unquoted_equals(line)
    if eq_idx == -1:
        lines[0] = f"{new_key} = {line.strip()}"
    else:
        lhs = line[:eq_idx]
        indent = lhs[: len(lhs) - len(lhs.lstrip())]
        lines[0] = f"{indent}{new_key} {line[eq_idx:]}"

    return "\n".join(lines)
