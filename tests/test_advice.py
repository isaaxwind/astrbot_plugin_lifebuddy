from __future__ import annotations

import types
import unittest
from unittest.mock import AsyncMock, patch

import test_chart_image
from lifebuddy.advice import handle_advice
from lifebuddy.lists import NumberedCache


def chart(index: int, *, reviewed: bool) -> dict:
    return {
        "songId": 500100000 + index,
        "title": f"Chart-{index:02d}",
        "difficulty": 2,
        "diff": 12,
        "chartAuthor": f"Author-{index:02d}",
        "reviewedByMe": reviewed,
    }


def queue() -> list[dict]:
    reviewed_at = {2, 5, 8, 11}
    return [chart(i, reviewed=i in reviewed_at) for i in range(1, 20)]


class Event(test_chart_image.Event):
    def __init__(self, message):
        super().__init__("review")
        self.message_str = message

    def get_sender_id(self):
        return "12345"


class AdvicePendingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cache = NumberedCache()
        self.items = queue()
        self.store = types.SimpleNamespace(charter_names=lambda qq: [])
        self.api = types.SimpleNamespace(
            list_advice=AsyncMock(return_value=self.items),
            upsert_advice_comment=AsyncMock(return_value={"ok": True}),
        )
        self.settings = types.SimpleNamespace(allow_advice=lambda gid: gid == "review")

    async def run_command(self, message, account="Bob", error=None):
        with (
            patch("lifebuddy.advice.observe"),
            patch("lifebuddy.advice.require_account", return_value=(account, error)),
        ):
            return [
                r
                async for r in handle_advice(
                    Event(message), self.store, self.api, self.settings, self.cache
                )
            ]

    async def test_pending_lists_only_unreviewed_with_original_numbers(self):
        text = (await self.run_command("/advice 未评"))[0]
        lines = text.splitlines()
        self.assertEqual(lines[0], "未评 15 / 19")
        self.assertEqual(lines[1], "1. Chart-01  H12  500100001  Author-01")
        self.assertNotIn("Chart-02", text)
        self.assertNotIn("Chart-05", text)
        self.assertNotIn("Chart-08", text)
        self.assertNotIn("Chart-11", text)
        self.assertIn("3. Chart-03  H12  500100003  Author-03", text)
        self.assertIn("19. Chart-19  H12  500100019  Author-19", text)
        self.assertEqual(len(lines), 17)
        self.assertIn("编号跟 /advice 一样", lines[-1])
        self.api.list_advice.assert_awaited_once_with("Bob")
        self.assertEqual(len(self.cache.get("review")), 19)
        self.assertEqual(self.cache.resolve_index("review", "2")["title"], "Chart-02")

    async def test_pending_aliases(self):
        for command in ("/advice 没评", "/advice todo", "/advice TODO", "/advice pending"):
            self.api.list_advice.reset_mock()
            text = (await self.run_command(command))[0]
            self.assertTrue(text.startswith("未评 15 / 19"), command)
            self.api.list_advice.assert_awaited_once_with("Bob")

    async def test_original_number_still_writes_that_chart(self):
        await self.run_command("/advice 未评")
        text = (await self.run_command("/advice 2 1"))[0]
        self.assertIn("已评 Chart-02 (500100002)", text)
        self.api.upsert_advice_comment.assert_awaited_once_with("Bob", 500100002, "ok.", 1)

    async def test_full_list_still_marks_reviewed(self):
        text = (await self.run_command("/advice"))[0]
        self.assertTrue(text.startswith("审核队列 19 首（未评 15）"))
        self.assertIn("2. Chart-02  H12  500100002  Author-02  已评", text)
        self.assertIn("1. Chart-01  H12  500100001  Author-01  未评", text)

    async def test_all_reviewed(self):
        self.api.list_advice.return_value = [chart(1, reviewed=True)]
        self.assertEqual(await self.run_command("/advice 未评"), ["都评过了（1 首）"])

    async def test_empty_queue(self):
        self.api.list_advice.return_value = []
        self.assertEqual(await self.run_command("/advice 未评"), ["审核队列是空的"])

    async def test_api_failure(self):
        self.api.list_advice.side_effect = RuntimeError("offline")
        self.assertEqual(await self.run_command("/advice 未评"), ["接口失败，等会再试"])

    async def test_closed_group_and_unbound(self):
        self.settings.allow_advice = lambda gid: False
        self.assertEqual(await self.run_command("/advice 未评"), ["本群未开审核"])
        self.api.list_advice.assert_not_awaited()
        self.settings.allow_advice = lambda gid: True
        self.assertEqual(
            await self.run_command("/advice 未评", error="先私聊 /rb bind"),
            ["先私聊 /rb bind"],
        )
