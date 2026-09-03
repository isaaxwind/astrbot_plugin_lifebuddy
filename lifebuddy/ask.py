from __future__ import annotations

import binascii
import random
from datetime import date

from astrbot.api.event import AstrMessageEvent

from .identity import speaker_label
from .store import BuddyStore

# crc32 % 1000 == 0，乘积种子恒为 0，稳定触发深奥
SHENAO_QUESTION = "宇宙洪荒"


def _daily_salt() -> str:
    return date.today().isoformat()


def _crc_mod(text: str) -> int:
    return binascii.crc32(text.encode()) % 1000


def _compute_chances(user_name: str, question: str, choices: list[str]) -> dict[str, int]:
    daily = _daily_salt()
    crc_name = _crc_mod(f"{user_name}\x1f{daily}")
    crc_question = _crc_mod(question)
    chance: dict[str, int] = {}
    for choice in choices:
        if choice in chance:
            continue
        crc_choice = _crc_mod(choice)
        random.seed(crc_name * crc_question * crc_choice)
        chance[choice] = random.randint(0, 10000)
    return chance


def _is_shenao(chance: dict[str, int]) -> bool:
    if len(chance) < 2:
        return False
    return len(set(chance.values())) == 1


def _shenao_lines(user_name: str, question: str, choices: list[str]) -> list[str]:
    pct = 100.0 / len(choices)
    lines = [f"{user_name} 的 {question} 选择建议如下：", "【深奥】"]
    for choice in choices:
        lines.append(f"{choice} ({pct:.2f}%)")
    return lines


async def handle_ask(event: AstrMessageEvent, store: BuddyStore | None = None):
    user_name = speaker_label(event, store)
    args = (event.message_str or "").split()
    if len(args) < 4:
        yield event.plain_result("选项太少！")
        return

    question = args[1]
    choices = args[2:]
    if len(choices) < 2:
        yield event.plain_result("选项太少！")
        return

    chance = _compute_chances(user_name, question, choices)
    if _is_shenao(chance):
        yield event.plain_result("\n".join(_shenao_lines(user_name, question, choices)))
        yield event.plain_result("我操，深奥上了")
        return

    summary = sum(chance.values())
    result = f"{user_name} 的 {question} 选择建议如下："
    for key, value in sorted(chance.items(), key=lambda item: item[1], reverse=True):
        result += f"\n{key} ({value / summary * 100:.2f}%)"
    yield event.plain_result(result)
