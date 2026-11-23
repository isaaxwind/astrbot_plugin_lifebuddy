from __future__ import annotations

import logging
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import astrbot.api  # noqa: F401
except ImportError:
    for name in ("astrbot", "astrbot.api", "astrbot.api.event"):
        sys.modules[name] = types.ModuleType(name)
    sys.modules["astrbot.api"].logger = logging.getLogger("ask-test")
    sys.modules["astrbot.api.event"].AstrMessageEvent = object

from lifebuddy.ask import handle_ask


class Event:
    def __init__(self, message: str, name: str = "垃圾大鹅"):
        self.message_str = message
        self.name = name

    def get_sender_name(self):
        return self.name

    def get_sender_id(self):
        return "100"

    def plain_result(self, text):
        return text


class AskTests(unittest.IsolatedAsyncioTestCase):
    async def ask(self, message: str):
        return [item async for item in handle_ask(Event(message))]

    async def test_repeated_option_counts_as_one(self):
        self.assertEqual(await self.ask("/ask 晚上吃啥 屎 屎 屎"), ["选项太少！"])

    async def test_one_option_is_too_few(self):
        self.assertEqual(await self.ask("/ask 晚上吃啥 屎"), ["选项太少！"])

    async def test_duplicates_beside_a_second_option_still_answer(self):
        text = (await self.ask("/ask 晚上吃啥 屎 屎 饭"))[0]
        self.assertIn("垃圾大鹅 的 晚上吃啥 选择建议如下：", text)
        self.assertIn("屎 (", text)
        self.assertIn("饭 (", text)
        self.assertEqual(text.count("屎 ("), 1)
        self.assertNotIn("选项太少", text)
