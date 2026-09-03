from __future__ import annotations

import asyncio
import random
from pathlib import Path

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image

from .store import BuddyStore
from .symmetry import process_image, _write_temp

PLUGIN_DIR = Path(__file__).resolve().parent.parent
MEME_DIR = PLUGIN_DIR / "data" / "memes"
ADVICE_MEME = MEME_DIR / "advice_self.jpg"
FIGHT_MEME = MEME_DIR / "fight_self.jpg"


def _norm(value: str) -> str:
    return (value or "").strip().casefold()


def names_match(left: str, right: str) -> bool:
    a, b = _norm(left), _norm(right)
    return bool(a) and a == b


def is_own_by_charter(store: BuddyStore, qq: str, chart_author: str) -> bool:
    author = (chart_author or "").strip()
    if not author or not qq:
        return False
    return any(names_match(author, name) for name in store.charter_names(qq))


def is_own_by_uploader(account: str | None, creator: str | None) -> bool:
    return names_match(account or "", creator or "")


def pick_meme_action(kind: str) -> str | None:
    roll = random.random()
    if kind == "advice":
        if roll < 0.10:
            return "left"
        if roll < 0.20:
            return "right"
        return None
    if roll < 0.10:
        return "reverse"
    if roll < 0.20:
        return "left"
    if roll < 0.30:
        return "right"
    return None


async def own_chart_result(event: AstrMessageEvent, kind: str):
    path = ADVICE_MEME if kind == "advice" else FIGHT_MEME
    if not path.is_file():
        yield event.plain_result("不能对自己的谱面下手")
        return
    data = path.read_bytes()
    action = pick_meme_action(kind)
    send = str(path)
    if action:
        try:
            out, suffix = await asyncio.to_thread(process_image, data, action)
            send = _write_temp(out, suffix)
        except Exception:
            send = str(path)
    result = event.make_result()
    result.chain = [Image(file=send)]
    result.use_t2i(False)
    yield result
