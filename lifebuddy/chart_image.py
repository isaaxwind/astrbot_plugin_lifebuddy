from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image as PILImage

from .image_cache import ImageCache

DIFFICULTIES = {
    "b": "B", "basic": "B", "m": "M", "medium": "M",
    "h": "H", "hard": "H", "sp": "SP", "special": "SP", "white": "SP",
}


def parse_chart_args(parts: list[str]) -> tuple[str, str]:
    """Only consume a trailing difficulty when a query precedes it."""
    query = list(parts)
    difficulty = "H"
    if len(query) > 1 and query[-1].lower() in DIFFICULTIES:
        difficulty = DIFFICULTIES[query.pop().lower()]
    return " ".join(query).strip(), difficulty


def chart_song_id(song: dict, difficulty: str) -> int:
    special = song.get("special") or {}
    return int(special.get("ExtID") or song["id"]) if difficulty == "SP" else int(song["id"])


def split_chart_image(data: bytes, columns: int, column_width: int, gap: int, cache: ImageCache) -> list[str]:
    """Keep two complete time columns per image, so QQ does not shrink the full chart."""
    if not 1 <= columns <= 64 or not 560 <= column_width <= 1200 or not 0 <= gap <= 32:
        raise ValueError("谱面图片布局无效")
    digest = hashlib.sha256(data).hexdigest()[:24]
    paths = []
    with PILImage.open(io.BytesIO(data)) as image:
        if image.format != "PNG" or image.width != columns * (column_width + gap) - gap:
            raise ValueError("谱面图片尺寸与接口布局不符")
        if not 120 <= image.height <= 8192 or image.width * image.height > 64_000_000:
            raise ValueError("谱面图片过大")
        image.load()
        for first in range(0, columns, 2):
            count = min(2, columns - first)
            left = first * (column_width + gap)
            page = image.crop((left, 0, left + count * (column_width + gap) - gap, image.height))
            path = cache.path_for(f"chart-{digest}-{first // 2 + 1}.png")
            page.save(path, format="PNG", optimize=True)
            paths.append(str(path))
    cache.prune()
    return paths