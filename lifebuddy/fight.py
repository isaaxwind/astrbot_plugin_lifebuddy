from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from .identity import group_key, observe, sender_qq
from .lists import DIFF_LABEL, NumberedCache, require_account, short_api_error
from .own_chart import is_own_by_charter, own_chart_result
from .rbdx import RbdxAPI
from .store import BuddyStore

USAGE = (
    "用法：\n"
    "/fight  要打的谱面列表（按谱面编号，不是按歌）\n"
    "/fight <编号> <展示值>  投票"
)


def _fight_count(item: dict) -> int:
    votes = item.get("votes") or []
    names: set[str] = set()
    for vote in votes:
        if not isinstance(vote, dict):
            continue
        name = str(vote.get("accountName") or vote.get("AccountName") or "").strip()
        if name:
            names.add(name.casefold())
    return len(names) if names else len(votes)


async def handle_fight(
    event: AstrMessageEvent,
    store: BuddyStore,
    rbdx: RbdxAPI,
    cache: NumberedCache,
):
    observe(event, store)
    gid = group_key(event)
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

    if len(args) < 2 or not args[1].lstrip("-").isdigit():
        yield event.plain_result(USAGE)
        return

    try:
        items = cache.get(gid) or await _load_list(rbdx, account, cache, gid)
        chart = cache.resolve_index(gid, args[0])
        if chart is None:
            yield event.plain_result("编号对不上，先 /fight 看列表")
            return
        author = str(chart.get("chartAuthor") or chart.get("chart_author") or "")
        if not author:
            try:
                meta = await rbdx.fetch_song_meta(
                    int(chart["songId"]), int(chart.get("difficulty") or 0)
                )
            except Exception:
                meta = None
            if meta:
                author = str(meta.get("chartAuthor") or "")
        if is_own_by_charter(store, sender_qq(event), author):
            async for result in own_chart_result(event, "fight"):
                yield result
            return
        display = int(args[1])
        vote_range = [int(x) for x in (chart.get("voteRange") or [])]
        if display != 0 and vote_range and display not in vote_range:
            yield event.plain_result(f"这档可投 {min(vote_range)}-{max(vote_range)}")
            return
        await rbdx.vote_subdiff(
            account,
            int(chart["songId"]),
            int(chart["difficulty"]),
            display,
        )
        items = await _load_list(rbdx, account, cache, gid)
        idx = int(args[0])
        refreshed = items[idx - 1] if 1 <= idx <= len(items) else chart
        label = DIFF_LABEL.get(int(refreshed.get("difficulty") or 0), "?")
        title = refreshed.get("title") or chart.get("title")
        avg = refreshed.get("avgLevel")
        mine = refreshed.get("myVote")
        yield event.plain_result(
            f"已投 #{idx} {title} {label}{refreshed.get('level')} → {display}\n"
            f"均分 {avg}  你的票 {mine if mine is not None else display}"
        )
    except Exception as exc:
        yield event.plain_result(short_api_error(exc))


async def _load_list(rbdx: RbdxAPI, account: str, cache: NumberedCache, gid: str) -> list:
    items = await rbdx.list_subdiff(account)
    return cache.put(gid, items)


async def _render_list(rbdx: RbdxAPI, account: str, cache: NumberedCache, gid: str) -> str:
    items = await _load_list(rbdx, account, cache, gid)
    if not items:
        return "现在没有要打的谱面"
    pending = sum(1 for item in items if item.get("myVote") is None)
    lines = [f"打架 {len(items)} 张谱（未投 {pending}）"]
    for i, item in enumerate(items, 1):
        title = item.get("title") or "?"
        label = DIFF_LABEL.get(int(item.get("difficulty") or 0), "?")
        level = item.get("level")
        avg = item.get("avgLevel")
        mine = item.get("myVote")
        mine_text = str(mine) if mine is not None else "-"
        vr = item.get("voteRange") or []
        span = f"{min(vr)}-{max(vr)}" if vr else "?"
        fighters = _fight_count(item)
        lines.append(
            f"{i}. {title}  {label}{level}  均分{avg}  {fighters}人打架  你:{mine_text}  可投{span}"
        )
    return "\n".join(lines)
