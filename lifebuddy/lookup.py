from __future__ import annotations

from typing import Any, Literal

from .netease import NeteaseCloudMusicAPI
from .rbdx import RbdxAPI

Source = Literal["rbdx", "netease"]


async def search_lai_shou(
    query: str,
    rbdx: RbdxAPI,
    netease: NeteaseCloudMusicAPI,
    fallback: bool = True,
) -> tuple[Source | None, list[dict[str, Any]]]:
    """RBDX first, Netease second. Empty RBDX list keeps current 来首 behavior."""
    try:
        rbdx_hits = await rbdx.search_published(query, limit=5)
    except Exception:
        rbdx_hits = []
    if rbdx_hits:
        return "rbdx", rbdx_hits
    if fallback:
        songs = await netease.fetch_song_data(query, limit=1, pic=True)
        return "netease", songs or []
    return None, []
