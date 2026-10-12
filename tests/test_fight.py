from __future__ import annotations

import copy
import types
import unittest
from unittest.mock import AsyncMock, patch

# Reuse the lightweight AstrBot message types installed by the chart tests.
import test_chart_image
from lifebuddy.fight import handle_fight
from lifebuddy.lists import NumberedCache

ROW = {
    "songId": 500100001, "title": "Target", "artist": "Artist", "chartAuthor": "Author",
    "difficulty": 2, "level": 12, "avgLevel": "6.5", "myVote": 0, "voteRange": [1, 2, 3, 4, 5, 6, 7, 8],
    "votes": [{"accountName": "Alice", "subdiff": 5}, {"accountName": "Bob", "subdiff": 0}],
}


class Event(test_chart_image.Event):
    def __init__(self, message):
        super().__init__("admin")
        self.message_str = message
    def get_sender_id(self): return "12345"


class FightTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.row = copy.deepcopy(ROW)
        self.cache = NumberedCache()
        self.store = types.SimpleNamespace(charter_names=lambda qq: ["Author"])
        self.api = types.SimpleNamespace(
            list_subdiff=AsyncMock(return_value=[self.row]),
            vote_subdiff=AsyncMock(return_value={"ok": True}),
            fetch_song_meta=AsyncMock(return_value={}),
        )

    async def run_command(self, message, account="Bob", error=None):
        with patch("lifebuddy.fight.observe"), patch("lifebuddy.fight.require_account", return_value=(account, error)):
            return [r async for r in handle_fight(Event(message), self.store, self.api, self.cache)]

    async def test_single_number_returns_details_without_voting(self):
        results = await self.run_command("/fight 1")
        self.assertEqual(len(results), 1)
        text = results[0]
        for expected in ("#1 Target", "H12", "500100001", "谱师 Author", "均分 6.5", "2人打架", "你的票 0", "Alice: 5", "Bob: 0", "/fight 1 <展示值>"):
            self.assertIn(expected, text)
        self.assertIn("\n", text)
        self.api.list_subdiff.assert_awaited_once_with("Bob")
        self.api.vote_subdiff.assert_not_awaited()

    async def test_fresh_votes_keep_last_displayed_chart_identity(self):
        stale = copy.deepcopy(self.row)
        stale["myVote"] = 8
        self.cache.put("admin", [stale])
        wrong = {**self.row, "songId": 500100002, "title": "Unrelated", "myVote": 4}
        wrong_difficulty = {**self.row, "difficulty": 0, "avgLevel": "wrong"}
        self.row["avgLevel"] = "7"
        self.row["myVote"] = None
        self.api.list_subdiff.return_value = [wrong, wrong_difficulty, self.row]
        text = (await self.run_command("/fight 1"))[0]
        self.assertIn("Target", text)
        self.assertIn("均分 7", text)
        self.assertIn("你的票 未投", text)
        self.assertNotIn("Unrelated", text)
        self.assertNotIn("wrong", text)
        self.assertEqual(self.cache.resolve_index("admin", "1")["songId"], self.row["songId"])

    async def test_removed_chart_does_not_show_new_row_at_same_number(self):
        self.cache.put("admin", [self.row])
        self.api.list_subdiff.return_value = [{**self.row, "songId": 999, "title": "Wrong"}]
        text = (await self.run_command("/fight 1"))[0]
        self.assertIn("已不在打架列表", text)
        self.assertNotIn("Wrong", text)

    async def test_empty_votes_are_reported(self):
        self.row["votes"] = []
        self.row["myVote"] = None
        self.row["avgLevel"] = "?"
        text = (await self.run_command("/fight 1"))[0]
        self.assertIn("0人打架", text)
        self.assertIn("还没人投票", text)

    async def test_invalid_number_returns_number_hint(self):
        self.cache.put("admin", [self.row])
        for command in ("/fight 0", "/fight 99", "/fight abc"):
            self.assertIn("编号对不上", (await self.run_command(command))[0])
        self.api.list_subdiff.assert_not_awaited()
        self.api.vote_subdiff.assert_not_awaited()

    async def test_author_can_read_own_chart(self):
        with patch("lifebuddy.fight.is_own_by_charter", return_value=True) as owns:
            text = (await self.run_command("/fight 1"))[0]
        self.assertIn("谱师 Author", text)
        owns.assert_not_called()

    async def test_api_failure_returns_message(self):
        self.api.list_subdiff.side_effect = RuntimeError("offline")
        self.assertEqual(await self.run_command("/fight 1"), ["接口失败，等会再试"])

    async def test_binding_requirement_stays(self):
        self.assertEqual(await self.run_command("/fight 1", account=None, error="先私聊 /rb bind"), ["先私聊 /rb bind"])
        self.api.list_subdiff.assert_not_awaited()

    async def test_vote_command_still_votes(self):
        self.cache.put("admin", [self.row])
        self.row["myVote"] = 3
        with patch("lifebuddy.fight.is_own_by_charter", return_value=False):
            results = await self.run_command("/fight 1 3")
        self.api.vote_subdiff.assert_awaited_once_with("Bob", 500100001, 2, 3)
        self.assertIn("已投 #1", results[0])


if __name__ == "__main__":
    unittest.main()
