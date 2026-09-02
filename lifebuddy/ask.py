from __future__ import annotations

import binascii
import random

from astrbot.api.event import AstrMessageEvent


async def handle_ask(event: AstrMessageEvent):
    user_name = event.get_sender_name()
    message_str = event.message_str
    args = message_str.split()
    if len(args) < 4:
        yield event.plain_result("选项太少！")
        return

    summary = 0
    chance = {}
    for i in range(2, len(args)):
        crc_name = binascii.crc32(user_name.encode()) % 1000
        crc_question = binascii.crc32(args[1].encode()) % 1000
        crc_choice = binascii.crc32(args[i].encode()) % 1000
        random.seed(crc_name * crc_question * crc_choice)
        a = random.randint(0, 10000)
        if args[i] not in chance:
            chance[args[i]] = a
            summary += a

    if len(chance) < 2:
        yield event.plain_result("选项太少！")
        return

    result = f"{user_name} 的 {args[1]} 选择建议如下："
    result_pair = sorted(chance.items(), key=lambda d: d[1], reverse=True)
    for key, value in result_pair:
        result += f"\n{key} ({value / summary * 100:.2f}%)"
    yield event.plain_result(result)
