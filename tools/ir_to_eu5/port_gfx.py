from pathlib import Path
from PIL import Image
from .paths import ir_coa_gfx, iu_coa_gfx


def replace_magenta_red_channel(
    img: Image.Image,
    tolerance: int = 10,
) -> Image.Image:
    pixels = img.load()
    width, height = img.size

    # Source and target
    fr, fg, fb = 255, 0, 128
    tr, tg, tb = 0, 0, 128

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]

            if (
                abs(r - fr) <= tolerance
                and abs(g - fg) <= tolerance
                and abs(b - fb) <= tolerance
            ):
                pixels[x, y] = (tr, tg, tb, a)

    return img


def convert_images(
    input_dir: Path,
    output_dir: Path,
    size=(384, 256),
    stretch: bool = False,
    colour_shift: bool = False,
    tolerance: int = 10,
):
    output_dir.mkdir(parents=True, exist_ok=True)

    for path in input_dir.iterdir():
        if path.suffix.lower() not in {".dds", ".tga"}:
            continue

        with Image.open(path) as img:
            img = img.convert("RGBA")

            if colour_shift:
                img = replace_magenta_red_channel(img, tolerance)

            if stretch:
                resized = img.resize(size, Image.LANCZOS)
            else:
                resized = Image.new("RGBA", size, (0, 0, 0, 0))
                img.thumbnail(size, Image.LANCZOS)

                x = (size[0] - img.width) // 2
                y = (size[1] - img.height) // 2
                resized.paste(img, (x, y))

            out_path = output_dir / (path.stem + ".dds")
            resized.save(out_path, format="DDS")


def port_coa_gfx():
    colored_emblems = ir_coa_gfx / "colored_emblems"
    patterns = ir_coa_gfx / "patterns"
    textured_emblems = ir_coa_gfx / "textured_emblems"

    out_colored_emblems = iu_coa_gfx / "colored_emblems"
    out_patterns = iu_coa_gfx / "patterns"
    out_textured_emblems = iu_coa_gfx / "textured_emblems"

    convert_images(colored_emblems, out_colored_emblems, stretch=False, colour_shift=True)
    convert_images(patterns, out_patterns, stretch=True)
    convert_images(textured_emblems, out_textured_emblems, stretch=False)
