from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from .identity import group_key, is_admin, observe, sender_qq
from .rbdx import RbdxAPI
from .store import BuddyStore, DibRow

USAGE = (
    "用法：\n"
    "/dib <曲名或SongID>  占坑（口香歌曲，占了不能弃，别人不能抢）\n"
    "/dib  查看本群占坑\n"
    "/dib del <QQ或曲名>  管理员删坑"
)


async def handle_dib(event: AstrMessageEvent, store: BuddyStore, rbdx: RbdxAPI, context=None):
    observe(event, store)
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    gid = group_key(event)
    qq = sender_qq(event)

    if not args:
        yield event.plain_result(_list_text(store, gid))
        return

    head = args[0].lower()
    if head in ("list", "ls"):
        yield event.plain_result(_list_text(store, gid))
        return

    if head in ("cancel", "drop", "undib"):
        yield event.plain_result("占了就不能弃，叫管理员 /dib del")
        return

    if head in ("del", "rm", "remove"):
        if not is_admin(event, context):
            yield event.plain_result("只有管理员能删别人的口香曲")
            return
        target = " ".join(args[1:]).strip()
        if not target:
            yield event.plain_result("用法：/dib del <QQ或曲名>")
            return
        if target.isdigit():
            row = store.clear_dib(gid, target)
            if not row:
                found = store.find_dib_by_song(gid, int(target), target)
                row = store.clear_dib(gid, found.qq) if found else None
        else:
            row = store.clear_dib_by_song(gid, target)
        if not row:
            yield event.plain_result(f"没找到口香：{target}")
            return
        yield event.plain_result(f"已删除 {store.display_name(row.qq)} 的 {row.song_name}")
        return

    if head in ("help", "?"):
        yield event.plain_result(USAGE)
        return

    if not qq:
        yield event.plain_result("拿不到你的 QQ，占不了坑")
        return

    query = " ".join(args).strip()
    song_id, song_name = await _resolve_song(rbdx, query)
    status, row = store.claim_dib(gid, qq, song_id, song_name, query)
    if status == "already_self":
        yield event.plain_result(
            f"你已经占了 {row.song_name}，不能自己弃，叫管理员 /dib del"
        )
        return
    if status == "taken":
        yield event.plain_result(
            f"{row.song_name} 已经被 {store.display_name(row.qq)} 占了"
        )
        return
    extra = f" ({song_id})" if song_id else ""
    yield event.plain_result(f"{store.display_name(qq)} 占坑：{song_name}{extra}")


async def _resolve_song(rbdx: RbdxAPI, query: str) -> tuple[int | None, str]:
    if query.isdigit():
        song_id = int(query)
        card = await rbdx.get_song(song_id)
        if card:
            return song_id, card.get("name") or query
        return song_id, query
    hits = await rbdx.search_published(query, limit=5)
    if not hits:
        return None, query
    exact = [h for h in hits if (h.get("name") or "").lower() == query.lower()]
    song = exact[0] if exact else hits[0]
    return int(song["id"]), song.get("name") or query


def _list_text(store: BuddyStore, group_id: str) -> str:
    rows = store.list_dibs(group_id)
    if not rows:
        return "本群还没人占坑。/dib <曲名或SongID>"
    lines = []
    for row in rows:
        extra = f" ({row.song_id})" if row.song_id else ""
        lines.append(f"{store.display_name(row.qq)}  {row.song_name}{extra}")
    return f"本群占坑 {len(rows)} 首：\n" + "\n".join(lines)
