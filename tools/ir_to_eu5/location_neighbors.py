import json
from collections import defaultdict
from pathlib import Path

from PIL import Image


DEFAULT_LOCATION_NEIGHBORS_PATH = Path(__file__).parent / "location_neighbors.json"


def build_location_neighbors(
    named_locations: list[tuple[int, str, int, int, int, str]],
    location_keys: set[str],
    provinces_png: Path,
) -> dict:
    """Build neighbor edge weights and centroid cache from a province-color map."""
    if not provinces_png.exists():
        raise FileNotFoundError(f"Missing map image: {provinces_png}")

    valid_keys = set(location_keys)
    color_to_key: dict[int, str] = {}
    for _, key, r, g, b, _ in named_locations:
        if key in valid_keys:
            color_to_key[(r << 16) | (g << 8) | b] = key

    with Image.open(provinces_png) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        raw = rgb.tobytes()

    total = width * height
    key_grid = [""] * total
    area_count: dict[str, int] = defaultdict(int)
    sum_x: dict[str, float] = defaultdict(float)
    sum_y: dict[str, float] = defaultdict(float)
    neighbors: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for i in range(total):
        j = i * 3
        color = (raw[j] << 16) | (raw[j + 1] << 8) | raw[j + 2]
        key = color_to_key.get(color, "")
        key_grid[i] = key
        if key:
            y, x = divmod(i, width)
            area_count[key] += 1
            sum_x[key] += x
            sum_y[key] += y

    for y in range(height):
        row_off = y * width
        for x in range(width):
            i = row_off + x
            left_key = key_grid[i]
            if not left_key:
                continue
            if x + 1 < width:
                right_key = key_grid[i + 1]
                if right_key and right_key != left_key:
                    neighbors[left_key][right_key] += 1
                    neighbors[right_key][left_key] += 1
            if y + 1 < height:
                down_key = key_grid[i + width]
                if down_key and down_key != left_key:
                    neighbors[left_key][down_key] += 1
                    neighbors[down_key][left_key] += 1

    centroids: dict[str, list[float]] = {}
    for key, count in area_count.items():
        if count <= 0:
            continue
        centroids[key] = [
            round(sum_x[key] / float(count), 4),
            round(sum_y[key] / float(count), 4),
        ]

    serialized_neighbors = {
        key: {nbr: int(weight) for nbr, weight in sorted(edge_map.items())}
        for key, edge_map in sorted(neighbors.items())
    }
    serialized_areas = {key: int(value) for key, value in sorted(area_count.items())}

    return {
        "version": 1,
        "width": width,
        "height": height,
        "neighbors": serialized_neighbors,
        "centroids": centroids,
        "areas": serialized_areas,
    }


def save_location_neighbors(data: dict, path: Path = DEFAULT_LOCATION_NEIGHBORS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    return path


def load_location_neighbors(path: Path = DEFAULT_LOCATION_NEIGHBORS_PATH) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if not isinstance(payload.get("neighbors"), dict):
        return None
    return payload
