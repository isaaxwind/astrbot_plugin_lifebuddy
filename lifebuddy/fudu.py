from __future__ import annotations

import random
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from astrbot.api.event import AstrMessageEvent

from .identity import group_key, is_private_chat, is_self_message, sender_qq, stop_event
from .store import BuddyStore

TZ = ZoneInfo("Asia/Shanghai")
FUDU_ECHO_MIN = 4
FUDU_ECHO_CHANCES = (0.20, 0.60, 1.00)
FUDU_STAT_MIN = 3
JIJU_REPEAT_BLOCK = 5
JIJU_ECHO_CHANCE = 0.05
JIJU_CHAT_CHANCE = 0.0001
MAX_FUDU_LEN = 200

_SPECIAL = re.compile(r"[^\w\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")
_COMMAND = re.compile(r"^[/／!！.]")

USAGE_FUDU = (
    "/复读  本周排行\n"
    "/复读 周|月|总\n"
    "/复读 链  最近复读链\n"
    "/复读 链 <编号>  看内容和参与者"
)
USAGE_JIJU = (
    "/金句  昨日金句\n"
    "/金句 7  近7天"
)

_listed_chains: dict[str, list[int]] = {}


def now_dt() -> datetime:
    return datetime.now(TZ)


def today_str(when: datetime | None = None) -> str:
    return (when or now_dt()).date().isoformat()


def period_start(kind: str) -> int:
    now = now_dt()
    if kind == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif kind == "all":
        return 0
    else:
        monday = now.date() - timedelta(days=now.weekday())
        start = datetime.combine(monday, datetime.min.time(), TZ)
    return int(start.timestamp())


def _clip(text: str, limit: int = 40) -> str:
    raw = (text or "").replace("\n", " ").strip()
    if len(raw) <= limit:
        return raw
    return raw[: limit - 1] + "…"


def is_command_text(text: str) -> bool:
    raw = (text or "").lstrip()
    if _COMMAND.match(raw):
        return True
    if raw.startswith("来首") and len(raw) >= 2:
        return True
    if raw.endswith("是什么歌") and len(raw) >= 4:
        return True
    return False


def is_jiju_text(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or is_command_text(raw):
        return False
    if _SPECIAL.search(raw):
        return False
    return True


def _people_line(store: BuddyStore, qqs: list[str]) -> str:
    names = [store.display_name(qq) for qq in qqs]
    return "、".join(names) if names else "（无人）"


async def handle_fudu(event: AstrMessageEvent, store: BuddyStore):
    if is_private_chat(event):
        yield event.plain_result("复读统计只记群里的")
        return
    gid = group_key(event)
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    token = args[0].lower() if args else ""
    if token in ("help", "?", "帮助"):
        yield event.plain_result(USAGE_FUDU)
        return
    if token in ("链", "chain", "chains"):
        async for result in _fudu_chains(event, store, gid, args[1:]):
            yield result
        return
    kind = "week"
    if token in ("周", "week", "weekly"):
        kind = "week"
    elif token in ("月", "month", "monthly"):
        kind = "month"
    elif token in ("总", "all", "总榜"):
        kind = "all"
    elif token:
        yield event.plain_result(USAGE_FUDU)
        return
    title = {"week": "本周", "month": "本月", "all": "总"}[kind]
    rows = store.fudu_board(gid, period_start(kind))
    if not rows:
        yield event.plain_result(f"{title}还没有够格的复读链")
        return
    lines = [f"复读{title}榜（链数，每人每条链只算一次）"]
    for i, (qq, n) in enumerate(rows, 1):
        lines.append(f"{i}. {store.display_name(qq)}  {n}")
    yield event.plain_result("\n".join(lines))


async def _fudu_chains(event: AstrMessageEvent, store: BuddyStore, gid: str, rest: list[str]):
    if rest and rest[0].isdigit():
        listed = _listed_chains.get(gid) or []
        idx = int(rest[0])
        chain_id = listed[idx - 1] if 1 <= idx <= len(listed) else idx
        chain = store.get_fudu_chain(gid, chain_id)
        if not chain:
            yield event.plain_result("没有这条复读链")
            return
        lines = [
            f"复读 {chain['length']} 人",
            chain["text"],
            _people_line(store, chain["people"]),
        ]
        yield event.plain_result("\n".join(lines))
        return
    items = store.list_fudu_chains(gid)
    if not items:
        yield event.plain_result("还没有够格的复读链")
        return
    _listed_chains[gid] = [item["id"] for item in items]
    lines = ["最近复读链"]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['length']}人  {_clip(item['text'])}")
    yield event.plain_result("\n".join(lines))


async def handle_jiju(event: AstrMessageEvent, store: BuddyStore):
    if is_private_chat(event):
        yield event.plain_result("金句只记群里的")
        return
    gid = group_key(event)
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    token = args[0] if args else ""
    if token in ("help", "?", "帮助"):
        yield event.plain_result(USAGE_JIJU)
        return
    if token in ("7", "周"):
        until = today_str()
        since = (now_dt().date() - timedelta(days=6)).isoformat()
        texts = store.recent_jiju(gid, since, until)
        if not texts:
            yield event.plain_result("近7天还没有金句")
            return
        lines = ["近7天金句"]
        for i, text in enumerate(texts, 1):
            lines.append(f"{i}. {text}")
        yield event.plain_result("\n".join(lines))
        return
    yesterday = (now_dt().date() - timedelta(days=1)).isoformat()
    store.finalize_jiju(gid, yesterday)
    texts = store.list_jiju(gid, yesterday)
    if not texts:
        yield event.plain_result("昨日没有金句")
        return
    yield event.plain_result(_jiju_announce_text(yesterday, texts))


def _jiju_announce_text(day: str, texts: list[str]) -> str:
    lines = [f"{day} 金句"]
    for i, text in enumerate(texts, 1):
        lines.append(f"{i}. {text}")
    return "\n".join(lines)


def _pick_recent_jiju(store: BuddyStore, gid: str) -> str:
    until = today_str()
    since = (now_dt().date() - timedelta(days=6)).isoformat()
    texts = store.recent_jiju(gid, since, until)
    if not texts:
        return ""
    return random.choice(texts)


async def process_group_chat(event: AstrMessageEvent, store: BuddyStore):
    if is_private_chat(event) or is_self_message(event):
        return
    gid = group_key(event)
    if not gid or gid == "private":
        return
    text = (event.message_str or "").strip()
    qq = sender_qq(event)
    if not qq:
        return

    async for result in _maybe_announce_jiju(event, store, gid):
        yield result

    if not text or is_command_text(text):
        return

    echoed = False
    async for result in _handle_fudu_message(event, store, gid, qq, text):
        yield result
        checker = getattr(event, "is_stopped", None)
        if callable(checker) and checker():
            echoed = True
    if echoed:
        return

    if is_jiju_text(text):
        store.add_jiju_candidate(gid, today_str(), text)

    state = store.fudu_state(gid)
    if state and len(state.get("people") or []) > 1:
        return
    if random.random() < JIJU_CHAT_CHANCE:
        quote = _pick_recent_jiju(store, gid)
        if quote:
            stop_event(event)
            yield event.plain_result(quote)


async def _maybe_announce_jiju(event: AstrMessageEvent, store: BuddyStore, gid: str):
    today = today_str()
    yesterday = (now_dt().date() - timedelta(days=1)).isoformat()
    last = store.jiju_announced_day(gid)
    if last == today:
        return
    texts = store.finalize_jiju(gid, yesterday)
    store.mark_jiju_announced(gid, today)
    if texts:
        yield event.plain_result(_jiju_announce_text(yesterday, texts))


async def _handle_fudu_message(
    event: AstrMessageEvent,
    store: BuddyStore,
    gid: str,
    qq: str,
    text: str,
):
    now = int(time.time())
    state = store.fudu_state(gid)
    ended: dict | None = None

    if state and text == state["text"]:
        people = list(state["people"])
        if qq in people:
            return
        if len(text) > MAX_FUDU_LEN:
            ended = state
            store.clear_fudu_state(gid)
        else:
            people.append(qq)
            store.set_fudu_state(
                gid,
                text,
                people,
                bot_echoed=state["bot_echoed"],
                started_at=state["started_at"],
            )
            if len(people) > JIJU_REPEAT_BLOCK:
                store.block_jiju_text(gid, today_str(), text)
            async for result in _maybe_echo(event, store, gid, text, people, state):
                yield result
            return
    else:
        if state:
            ended = state
        if 0 < len(text) <= MAX_FUDU_LEN:
            store.set_fudu_state(gid, text, [qq], bot_echoed=False, started_at=now)
        else:
            store.clear_fudu_state(gid)

    if ended:
        async for result in _close_chain(event, store, gid, ended, now):
            yield result


async def _close_chain(event: AstrMessageEvent, store: BuddyStore, gid: str, state: dict, now: int):
    people = list(state.get("people") or [])
    text = str(state.get("text") or "")
    if len(people) < FUDU_STAT_MIN:
        return
    _chain_id, _best, broken = store.save_fudu_chain(
        gid, text, people, int(state.get("started_at") or now), now
    )
    if broken:
        yield event.plain_result(
            f"复读新纪录！{len(people)} 人\n「{_clip(text, 60)}」"
        )


async def _maybe_echo(
    event: AstrMessageEvent,
    store: BuddyStore,
    gid: str,
    text: str,
    people: list[str],
    prev: dict,
):
    if prev.get("bot_echoed"):
        return
    n = len(people)
    if n < FUDU_ECHO_MIN:
        return
    step = min(n - FUDU_ECHO_MIN, len(FUDU_ECHO_CHANCES) - 1)
    chance = FUDU_ECHO_CHANCES[step]
    if random.random() >= chance:
        return
    echoed = text
    if random.random() < JIJU_ECHO_CHANCE:
        quote = _pick_recent_jiju(store, gid)
        if quote:
            echoed = quote
    store.set_fudu_state(
        gid,
        text,
        people,
        bot_echoed=True,
        started_at=int(prev.get("started_at") or time.time()),
    )
    stop_event(event)
    yield event.plain_result(echoed)
