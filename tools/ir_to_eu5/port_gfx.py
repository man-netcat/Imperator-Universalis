from pathlib import Path
from PIL import Image
from .paths import ir_coa_gfx, iu_coa_gfx


def convert_images(
    input_dir: Path, output_dir: Path, size=(384, 256), stretch: bool = False
):
    output_dir.mkdir(parents=True, exist_ok=True)

    for path in input_dir.iterdir():
        if path.suffix.lower() not in {".dds", ".tga"}:
            continue

        with Image.open(path) as img:
            img = img.convert("RGBA")

            if stretch:
                resized = img.resize(size, Image.LANCZOS)
            else:
                # Preserve aspect ratio, center on canvas
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

    convert_images(colored_emblems, out_colored_emblems, stretch=False)
    convert_images(patterns, out_patterns, stretch=True)
    convert_images(textured_emblems, out_textured_emblems, stretch=False)
