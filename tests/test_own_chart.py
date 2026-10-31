from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import test_chart_image
from lifebuddy.own_chart import FIGHT_MEME, own_chart_result


class FightMemeTests(unittest.IsolatedAsyncioTestCase):
    def test_fight_meme_file_is_animated_gif(self):
        self.assertEqual(FIGHT_MEME.name, "fight_self.gif")
        self.assertFalse((FIGHT_MEME.parent / "fight_self.jpg").exists())
        self.assertTrue(FIGHT_MEME.is_file())
        with Image.open(FIGHT_MEME) as image:
            self.assertEqual(image.format, "GIF")
            self.assertTrue(image.is_animated)
            self.assertGreater(image.n_frames, 1)

    async def test_fight_own_chart_sends_original_gif(self):
        event = test_chart_image.Event()
        with patch("lifebuddy.own_chart.pick_meme_action", return_value=None):
            results = [item async for item in own_chart_result(event, "fight")]
        self.assertEqual(len(results), 1)
        sent = Path(results[0].chain[0].file)
        self.assertEqual(sent, FIGHT_MEME)
        self.assertTrue(sent.read_bytes().startswith(b"GIF89a"))
