from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from .chart_image import chart_song_id, parse_chart_args
from .identity import group_key
from .rbdx import catalog_kind_label, parse_catalog_kind, song_matches_query

USAGE = "用法：/rb chart [custom|arcade|test|test_all|英国人] <曲名或SongID> [B/M/H/SP]（默认 H）"


async def handle_chart(event: AstrMessageEvent, runtime, parts: list[str]):
    gid = group_key(event)
    explicit = parse_catalog_kind(parts[0]) if parts else None
    if explicit:
        if not runtime.settings.allow_catalog(gid, explicit):
            yield event.plain_result("本群未开这类谱")
            return
        parts = parts[1:]
        kinds = [explicit]
    else:
        kinds = [k for k in ("custom", "arcade", "test", "brit") if runtime.settings.allow_catalog(gid, k)]
    query, difficulty = parse_chart_args(parts)
    if not query:
        yield event.plain_result(USAGE)
        return

    # Exact aliases resolve to an ID, but must still pass catalog/group permissions.
    alias_ids = {
        entry.song_id for entry in runtime.aliases.entries
        if entry.alias.casefold() == query.casefold() and entry.song_id
    }
    try:
        matches: dict[int, tuple[str, dict]] = {}
        exact: dict[int, tuple[str, dict]] = {}
        for kind in kinds:
            songs = await runtime.rbdx.fetch_catalog(kind)
            for song in songs:
                sid = int(song["id"])
                ext = int((song.get("special") or {}).get("ExtID") or 0)
                if query.isdigit():
                    # IDs must match completely, not a substring of another ID.
                    hit = int(query) in {sid, ext}
                else:
                    hit = sid in alias_ids or (ext > 0 and ext in alias_ids) or song_matches_query(song, query)
                if not hit:
                    continue
                matches.setdefault(sid, (kind, song))
                if sid in alias_ids or (ext > 0 and ext in alias_ids) or str(song.get("name") or "").casefold() == query.casefold():
                    exact.setdefault(sid, (kind, song))
        selected = exact or matches
        if not selected:
            yield event.plain_result(f"没找到可查看的谱面「{query}」")
            return
        if len(selected) > 1:
            lines = [
                f'{song["id"]}  {song.get("name", "")}（{catalog_kind_label(kind)}）'
                for kind, song in list(selected.values())[:10]
            ]
            yield event.plain_result("匹配到多首，请用 SongID 指定：\n" + "\n".join(lines))
            return
        kind, song = next(iter(selected.values()))
        # An extended SongID requests SPECIAL automatically unless B/M was specified.
        ext_id = int((song.get("special") or {}).get("ExtID") or 0)
        if ext_id > 0 and difficulty == "H" and ((query.isdigit() and int(query) == ext_id) or ext_id in alias_ids):
            difficulty = "SP"
        song_id = chart_song_id(song, difficulty)
        pages = await runtime.rbdx.fetch_chart_images(song_id, difficulty, restricted=kind != "custom")
    except Exception as exc:
        logger.warning("chart image failed: %s", exc)
        yield event.plain_result(f"谱面图片获取失败：{exc}")
        return

    for i, path in enumerate(pages, 1):
        result = event.make_result()
        result.chain = [
            Plain(f'{song.get("name") or song_id} · {difficulty}  [{i}/{len(pages)}]\n'),
            Image(file=path),
        ]
        result.use_t2i(False)
        yield result