from __future__ import annotations

import binascii
import random
import zlib

from astrbot.api.event import AstrMessageEvent

from .identity import speaker_label
from .store import BuddyStore

_SHENAO_MARK = 0x5E4E414F  # "深奥" in ASCII-ish marker for stable easter egg


def _crc_mod(text: str) -> int:
    return binascii.crc32(text.encode()) % 1000


def _choice_weight(user_name: str, question: str, choice: str) -> int:
    crc_name = _crc_mod(user_name)
    crc_question = _crc_mod(question)
    crc_choice = _crc_mod(choice)
    seed = (
        (crc_name * 1_000_003 + crc_question * 1_009 + crc_choice) & 0xFFFFFFFF
    ) or 1
    rng = random.Random(seed)
    return rng.randint(1, 10000)


def _shenao_trigger(user_name: str, question: str, choices: list[str]) -> bool:
    blob = "\x1f".join([user_name, question, *choices]).encode()
    return (zlib.crc32(blob) ^ _SHENAO_MARK) % 97 == 0


async def handle_ask(event: AstrMessageEvent, store: BuddyStore | None = None):
    user_name = speaker_label(event, store)
    message_str = event.message_str
    args = message_str.split()
    if len(args) < 4:
        yield event.plain_result("选项太少！")
        return

    question = args[1]
    choices = args[2:]
    if len(choices) < 2:
        yield event.plain_result("选项太少！")
        return

    if _shenao_trigger(user_name, question, choices):
        pct = 100.0 / len(choices)
        lines = [f"{user_name} 的 {question} 选择建议如下：", "【深奥】"]
        for choice in choices:
            lines.append(f"{choice} ({pct:.2f}%)")
        yield event.plain_result("\n".join(lines))
        return

    chance: dict[str, int] = {}
    summary = 0
    for choice in choices:
        if choice in chance:
            continue
        weight = _choice_weight(user_name, question, choice)
        chance[choice] = weight
        summary += weight

    result = f"{user_name} 的 {question} 选择建议如下："
    result_pair = sorted(chance.items(), key=lambda d: d[1], reverse=True)
    for key, value in result_pair:
        result += f"\n{key} ({value / summary * 100:.2f}%)"
    yield event.plain_result(result)
