from pathlib import Path

from PIL import Image

from .paths import iter_ir_files, iu_coa_gfx, mod_root
from .write_data import print_written


def remap_ir_colored_emblem_palette(
    img: Image.Image,
    tolerance: int = 96,
    min_r: int = 128,
    max_g_for_pink: int = 160,
    min_g_for_yellow: int = 128,
    max_rg_delta_for_yellow: int = 80,
    min_rg_delta_for_pink: int = 20,
) -> Image.Image:
    """
    Convert I:R colored-emblem palette to EU5 colored-emblem palette.

    I:R colored emblems use:
      - pink (255, 0, 128) for color1
      - light yellow (255, 255, 128) for color2
      - blue channel as brightness (0..255)

    EU5 colored emblems use:
      - color1 marker: (0, 0, 128)
      - color2 marker: (0, 255, 128)
      - blue channel as brightness (0..255)

    We remap R/G to EU5 markers while preserving B and alpha.
    """
    pixels = img.load()
    width, height = img.size

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]

            # Compare only R/G to allow variable brightness in B.
            # Use a mix of distance and threshold checks to catch antialiasing.
            if (r >= min_r and g <= max_g_for_pink and (r - g) >= min_rg_delta_for_pink) or (
                abs(r - 255) + abs(g - 0) <= tolerance
            ):
                pixels[x, y] = (0, 0, b, a)
            elif (r >= min_r and g >= min_g_for_yellow and abs(r - g) <= max_rg_delta_for_yellow) or (
                abs(r - 255) + abs(g - 255) <= tolerance
            ):
                pixels[x, y] = (0, 255, b, a)

    return img


def convert_images(
    input_paths: list[Path],
    output_dir: Path,
    size=(384, 256),
    stretch: bool = False,
    stretch_predicate=None,
    colour_shift: bool = False,
    tolerance: int = 96,
):
    output_dir.mkdir(parents=True, exist_ok=True)

    for path in input_paths:
        if path.suffix.lower() not in {".dds", ".tga"}:
            continue

        with Image.open(path) as img:
            img = img.convert("RGBA")

            if colour_shift:
                img = remap_ir_colored_emblem_palette(img, tolerance)

            should_stretch = stretch
            if stretch_predicate is not None:
                should_stretch = bool(stretch_predicate(path))

            if should_stretch:
                resized = img.resize(size, Image.LANCZOS)
            else:
                resized = Image.new("RGBA", size, (0, 0, 0, 0))
                img.thumbnail(size, Image.LANCZOS)

                x = (size[0] - img.width) // 2
                y = (size[1] - img.height) // 2
                resized.paste(img, (x, y))

            out_path = output_dir / (path.stem + ".dds")
            resized.save(out_path, format="DDS")
            print_written("image", out_path)


def port_coa_gfx():
    def _iter_gfx_files(relative_dir: str) -> list[Path]:
        return [
            path
            for path in iter_ir_files(relative_dir, pattern="*.*")
            if path.suffix.lower() in {".dds", ".tga"}
        ]

    colored_emblems = _iter_gfx_files("gfx/coat_of_arms/colored_emblems")
    patterns = _iter_gfx_files("gfx/coat_of_arms/patterns")
    textured_emblems = _iter_gfx_files("gfx/coat_of_arms/textured_emblems")

    out_colored_emblems = iu_coa_gfx / "colored_emblems"
    out_patterns = iu_coa_gfx / "patterns"
    out_textured_emblems = iu_coa_gfx / "textured_emblems"

    def is_border_emblem(path: Path) -> bool:
        # Border emblems are designed to reach the edges; stretch to fit EU5's 3:2 aspect.
        return path.stem.startswith("ce_border_")

    convert_images(
        colored_emblems,
        out_colored_emblems,
        stretch=False,
        stretch_predicate=is_border_emblem,
        colour_shift=True,
    )
    convert_images(patterns, out_patterns, stretch=True)
    convert_images(textured_emblems, out_textured_emblems, stretch=False)
