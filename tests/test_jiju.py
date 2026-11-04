from __future__ import annotations

import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import astrbot.api  # noqa: F401
except ImportError:
    for name in ("astrbot", "astrbot.api", "astrbot.api.event"):
        sys.modules[name] = types.ModuleType(name)
    sys.modules["astrbot.api"].logger = logging.getLogger("jiju-test")
    sys.modules["astrbot.api.event"].AstrMessageEvent = object

from lifebuddy.fudu import handle_jiju
from lifebuddy.store import BuddyStore, jiju_collapsed, jiju_score


class Event:
    def __init__(self, message: str, gid: str = "room"):
        self.message_str = message
        self.gid = gid

    def get_group_id(self):
        return self.gid

    def plain_result(self, text):
        return text


class JijuScoreTests(unittest.TestCase):
    def test_repeated_block_counts_once(self):
        spam = "123" * 7
        self.assertEqual(jiju_collapsed(spam), "123")
        self.assertEqual(jiju_score(spam), 3)
        self.assertEqual(jiju_score("哈哈" * 20), 1)
        self.assertEqual(jiju_collapsed("112112112"), "112")

    def test_real_sentence_keeps_its_length(self):
        text = "我想出去走走"
        self.assertEqual(jiju_collapsed(text), text)
        self.assertEqual(jiju_score(text), len(text))


class JijuStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = BuddyStore(Path(self.tmp.name) / "lifebuddy.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_daily_top_uses_collapsed_length(self):
        day = "2026-11-01"
        spam = "123" * 7
        real = [
            "abcdefghij",
            "abcdefghi",
            "abcdefgh",
            "abcdefg",
            "abcdef",
            "abcde",
        ]
        self.store.add_jiju_candidate("room", day, spam)
        self.store.add_jiju_candidate("room", day, "哈" * 30)
        for text in real:
            self.store.add_jiju_candidate("room", day, text)
        picked = self.store.finalize_jiju("room", day)
        self.assertEqual(picked, real[:5])
        self.assertEqual(self.store.finalize_jiju("room", day), picked)

    def test_history_keeps_every_day_and_longest_is_deduped(self):
        days = {
            "2026-10-01": ["aaaaaa", "短句甲乙丙", "历史第一名这句话很长"],
            "2026-10-02": ["bbbbbb", "另一天的句子", "第二天单独的一句"],
            "2026-10-03": ["cccccc", "第三天普通句子", "后来居上的金句确实更长一些", "历史第一名这句话很长"],
        }
        for day, texts in days.items():
            for text in texts:
                self.store.add_jiju_candidate("room", day, text)
            self.store.finalize_jiju("room", day)
        saved = [self.store.list_jiju("room", day) for day in days]
        self.assertEqual([len(items) for items in saved], [3, 3, 4])
        longest = self.store.longest_jiju("room")
        self.assertEqual(
            longest[:2],
            ["后来居上的金句确实更长一些", "历史第一名这句话很长"],
        )
        self.assertEqual(len(longest), 5)
        self.assertEqual(longest.count("历史第一名这句话很长"), 1)
        self.assertNotIn("aaaaaa", longest)


class JijuCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = BuddyStore(Path(self.tmp.name) / "lifebuddy.db")

    async def asyncTearDown(self):
        self.store.close()
        self.tmp.cleanup()

    async def test_history_command_lists_five_longest(self):
        texts = [f"金句正文号码{i:02d}" for i in range(1, 8)]
        for i, text in enumerate(texts, 1):
            day = f"2026-10-{i:02d}"
            self.store.add_jiju_candidate("room", day, text)
            self.store.add_jiju_candidate("room", day, "123" * 9)
            self.store.finalize_jiju("room", day)
        results = [item async for item in handle_jiju(Event("/金句 总"), self.store)]
        self.assertEqual(len(results), 1)
        lines = results[0].splitlines()
        self.assertEqual(lines[0], "历史最长金句")
        self.assertEqual(len(lines), 6)
        shown = [line.split(". ", 1)[1] for line in lines[1:]]
        self.assertEqual(shown, sorted(texts, key=lambda text: (-jiju_score(text), text))[:5])
        self.assertNotIn("123" * 9, results[0])

    async def test_history_aliases_and_empty(self):
        self.assertEqual(
            [item async for item in handle_jiju(Event("/金句 历史"), self.store)],
            ["还没有金句"],
        )
        self.store.add_jiju_candidate("room", "2026-10-01", "只有这一句金句")
        self.store.finalize_jiju("room", "2026-10-01")
        text = [item async for item in handle_jiju(Event("/金句 ALL"), self.store)][0]
        self.assertIn("只有这一句金句", text)
        self.assertTrue(text.startswith("历史最长金句"))

    async def test_private_chat_is_refused(self):
        results = [item async for item in handle_jiju(Event("/金句 总", gid=""), self.store)]
        self.assertEqual(results, ["金句只记群里的"])
