from __future__ import annotations

import hashlib
import io
import warnings

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


def store_chart_image(data: bytes, columns: int, column_width: int, gap: int, cache: ImageCache) -> str:
    """Validate and retain the exact full PNG from the editor; never crop or resize."""
    if not 1 <= columns <= 64 or not 560 <= column_width <= 2000 or not 0 <= gap <= 32:
        raise ValueError("谱面图片布局无效")
    with warnings.catch_warnings():
        # The editor intentionally supports up to 160 MP, beyond Pillow's warning threshold.
        warnings.simplefilter("ignore", PILImage.DecompressionBombWarning)
        with PILImage.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or image.width != columns * (column_width + gap) - gap:
                raise ValueError("谱面图片尺寸与接口布局不符")
            if image.width > 32767 or not 120 <= image.height <= 16384 or image.width * image.height > 160_000_000:
                raise ValueError("谱面图片超过 editor 上限")
            image.verify()
    digest = hashlib.sha256(data).hexdigest()[:24]
    path = cache.put(f"chart-{digest}.png", data)
    if path is None:
        raise RuntimeError("谱面图片保存失败")
    return str(path)
