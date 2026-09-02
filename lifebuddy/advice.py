from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from .identity import group_key, observe
from .lists import DIFF_LABEL, NumberedCache, parse_is_ok, require_account, short_api_error
from .rbdx import RbdxAPI
from .settings import Settings
from .store import BuddyStore

USAGE = (
    "用法：\n"
    "/advice  审核列表\n"
    "/advice <编号或SongID>  看评语\n"
    "/advice <编号或SongID> <0|1> 正文  写评（1过 / 0要改，也认 ok/ng）"
)


async def handle_advice(
    event: AstrMessageEvent,
    store: BuddyStore,
    rbdx: RbdxAPI,
    settings: Settings,
    cache: NumberedCache,
):
    observe(event, store)
    gid = group_key(event)
    if not settings.allow_advice(gid):
        yield event.plain_result("本群未开审核")
        return

    parts = event.message_str.split()
    args = parts[1:] if parts else []
    account, err = require_account(event, store)
    if err:
        yield event.plain_result(err)
        return

    if not args or args[0].lower() in ("list", "ls"):
        try:
            text = await _render_list(rbdx, account, cache, gid)
        except Exception as exc:
            yield event.plain_result(short_api_error(exc))
            return
        yield event.plain_result(text)
        return

    if args[0].lower() in ("help", "?"):
        yield event.plain_result(USAGE)
        return

    try:
        items = cache.get(gid) or await _load_list(rbdx, account, cache, gid)
        song_id, title = _resolve_song(args[0], items)
        if song_id is None:
            yield event.plain_result("编号或 SongID 对不上，先 /advice 看列表")
            return
        rest = args[1:]
        if not rest:
            text = await _render_comments(rbdx, song_id, title)
            yield event.plain_result(text)
            return
        flag = parse_is_ok(rest[0])
        if flag is None:
            is_ok, comment = 1, " ".join(rest).strip()
        else:
            is_ok, comment = flag, " ".join(rest[1:]).strip()
        if not comment:
            yield event.plain_result("评语不能空。例如 /advice 2 0 节奏要改")
            return
        await rbdx.upsert_advice_comment(account, song_id, comment, is_ok)
        mark = "过" if is_ok == 1 else "要改"
        yield event.plain_result(f"已评 {title} ({song_id}) [{mark}]")
    except Exception as exc:
        yield event.plain_result(short_api_error(exc))


async def _load_list(rbdx: RbdxAPI, account: str, cache: NumberedCache, gid: str) -> list:
    items = await rbdx.list_advice(account)
    return cache.put(gid, items)


async def _render_list(rbdx: RbdxAPI, account: str, cache: NumberedCache, gid: str) -> str:
    items = await _load_list(rbdx, account, cache, gid)
    if not items:
        return "审核队列是空的"
    pending = sum(1 for item in items if not item.get("reviewedByMe"))
    lines = [f"审核队列 {len(items)} 首（未评 {pending}）"]
    for i, item in enumerate(items, 1):
        title = item.get("title") or "?"
        song_id = item.get("songId")
        diff = DIFF_LABEL.get(int(item.get("difficulty") or 0), "?")
        level = item.get("diff")
        mark = "已评" if item.get("reviewedByMe") else "未评"
        lines.append(f"{i}. {title}  {diff}{level}  {song_id}  {mark}")
    return "\n".join(lines)


def _resolve_song(token: str, items: list) -> tuple[int | None, str]:
    token = token.strip()
    if token.isdigit():
        n = int(token)
        if 1 <= n <= len(items):
            item = items[n - 1]
            return int(item["songId"]), str(item.get("title") or item["songId"])
        if n >= 1000:
            for item in items:
                if int(item.get("songId") or 0) == n:
                    return n, str(item.get("title") or n)
            return n, str(n)
    return None, ""


async def _render_comments(rbdx: RbdxAPI, song_id: int, title: str) -> str:
    comments = await rbdx.list_advice_comments(song_id)
    if not comments:
        return f"{title} ({song_id}) 还没人评"
    lines = [f"{title} ({song_id})"]
    for row in comments:
        mark = "过" if int(row.get("isOk") or 0) == 1 else "要改"
        who = row.get("accountName") or "?"
        text = (row.get("comment") or "").strip()
        lines.append(f"- {who} [{mark}] {text}")
    return "\n".join(lines)
