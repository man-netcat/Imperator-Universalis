from __future__ import annotations

from pathlib import Path


def iter_overlay_files(
    mod_root: Path | None,
    game_root: Path,
    relative_dir: str,
    pattern: str = "*.txt",
) -> list[Path]:
    """Return files from mod first, then base game for an overlayed directory."""
    files: list[Path] = []

    if mod_root:
        mod_dir = mod_root / relative_dir
        if mod_dir.is_dir():
            files.extend(sorted(path for path in mod_dir.glob(pattern) if path.is_file()))

    game_dir = game_root / relative_dir
    if game_dir.is_dir():
        files.extend(sorted(path for path in game_dir.glob(pattern) if path.is_file()))

    return files
