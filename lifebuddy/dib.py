from __future__ import annotations

import time

from astrbot.api.event import AstrMessageEvent

from .identity import group_key, is_admin, observe, sender_qq
from .rbdx import RbdxAPI
from .store import BuddyStore

STALE_DAYS = 100

USAGE = (
    "用法：\n"
    "/dib  看自己口香了几天\n"
    "/dib <曲名或SongID>  口香（占了不能吐，别人不能抢）\n"
    "/dib list  本群口香列表\n"
    "/dib del <QQ或曲名>  管理员删除"
)


def dib_elapsed_days(created_at: int, now: int | None = None) -> int:
    now = int(time.time() if now is None else now)
    return max(0, (now - int(created_at)) // 86400)


def _self_status(store: BuddyStore, qq: str, gid: str) -> str:
    if not qq:
        return "拿不到你的 QQ"
    row = store.get_dib(gid, qq)
    if not row:
        return "你还没有口香。/dib <曲名或SongID>"
    days = dib_elapsed_days(row.created_at)
    title = row.song_name
    if days >= STALE_DAYS:
        return f"你已经口香「{title}」{days}天了，快要变成口臭了！"
    if days == 0:
        return f"你已经口香「{title}」了，今天刚咬上，记得做谱哦"
    return f"你已经口香「{title}」{days}天了，记得做谱哦"


async def handle_dib(event: AstrMessageEvent, store: BuddyStore, rbdx: RbdxAPI, context=None):
    observe(event, store)
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    gid = group_key(event)
    qq = sender_qq(event)

    if not args:
        yield event.plain_result(_self_status(store, qq, gid))
        return

    head = args[0].lower()
    if head in ("list", "ls"):
        yield event.plain_result(_list_text(store, gid))
        return

    if head in ("cancel", "drop", "undib"):
        yield event.plain_result("口香了就不能吐，叫管理员 /dib del")
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
        yield event.plain_result("拿不到你的 QQ，口香不了")
        return

    query = " ".join(args).strip()
    song_id, song_name = await _resolve_song(rbdx, query)
    status, row = store.claim_dib(gid, qq, song_id, song_name, query)
    if status == "already_self":
        yield event.plain_result(_self_status(store, qq, gid) + "\n不能自己吐，叫管理员 /dib del")
        return
    if status == "taken":
        days = dib_elapsed_days(row.created_at) if row else 0
        who = store.display_name(row.qq) if row else "?"
        title = row.song_name if row else song_name
        yield event.plain_result(f"「{title}」已经被 {who} 口香 {days} 天了")
        return
    extra = f" ({song_id})" if song_id else ""
    yield event.plain_result(f"{store.display_name(qq)} 口香：{song_name}{extra}，记得做谱哦")


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
        return "本群还没人口香。/dib <曲名或SongID>"
    lines = []
    for row in rows:
        extra = f" ({row.song_id})" if row.song_id else ""
        days = dib_elapsed_days(row.created_at)
        stale = " 口臭预警" if days >= STALE_DAYS else ""
        lines.append(f"{store.display_name(row.qq)}  {row.song_name}{extra}  {days}天{stale}")
    return f"本群口香 {len(rows)} 首：\n" + "\n".join(lines)
