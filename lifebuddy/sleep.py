from __future__ import annotations

import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from astrbot.api.event import AstrMessageEvent

from .identity import sender_qq
from .store import BuddyStore

TZ = ZoneInfo("Asia/Shanghai")

USAGE = "用法：/sleep  去睡觉，下次说话再叫你"

_QUIPS = (
    (0, 60, ("你睡了个蛋啊？？", "这就醒了？眼睛都没闭上吧")),
    (60, 180, ("这叫睡？闭个眼罢了", "闹钟是不是装了弹簧")),
    (180, 360, ("这觉有点短啊", "还能再躺一会儿的")),
    (360, 600, ("睡得还行", "精神点了没")),
    (600, 720, ("补觉补得可以", "这下能干活了吧")),
    (720, 1080, ("你是猪吗？？", "被窝把你吞了？")),
    (1080, 1440, ("冬眠结束了？", "太阳都晒屁股三轮了")),
    (1440, 10**9, ("挖坟挖到你了", "以为你没了")),
)


def _now() -> datetime:
    return datetime.now(TZ)


def _hello(when: datetime | None = None) -> str:
    hour = (when or _now()).hour
    if 5 <= hour < 11:
        return "早上好"
    if 11 <= hour < 13:
        return "中午好"
    if 13 <= hour < 18:
        return "下午好"
    if 18 <= hour < 23:
        return "晚上好"
    return "这么晚还好"


def _duration_text(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    return f"{hours}小时{minutes}分"


def _quip(minutes: int) -> str:
    for low, high, lines in _QUIPS:
        if low <= minutes < high:
            return random.choice(lines)
    return "你是猪吗？？"


def _is_sleep_command(text: str) -> bool:
    raw = (text or "").strip().lstrip("/／").lower()
    head = raw.split()[0] if raw else ""
    return head in ("sleep", "睡觉")


def wake_text(slept_at: int, now: int | None = None) -> str:
    current = int(now if now is not None else time.time())
    seconds = max(0, current - int(slept_at))
    minutes = seconds // 60
    return f"{_hello()}，你睡了{_duration_text(seconds)}，{_quip(minutes)}"


async def handle_sleep(event: AstrMessageEvent, store: BuddyStore):
    qq = sender_qq(event)
    if not qq:
        yield event.plain_result("拿不到你的 QQ")
        return
    store.set_sleep(qq)
    yield event.plain_result("晚安")


async def handle_sleep_wake(event: AstrMessageEvent, store: BuddyStore):
    qq = sender_qq(event)
    if not qq:
        return
    if _is_sleep_command(event.message_str or ""):
        return
    slept_at = store.peek_sleep(qq)
    if slept_at is None:
        return
    store.take_sleep(qq)
    yield event.plain_result(wake_text(slept_at))
