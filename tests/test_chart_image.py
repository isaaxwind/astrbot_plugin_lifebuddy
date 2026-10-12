from __future__ import annotations

import asyncio
import io
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Command tests need only AstrBot's message data types, not a running bot.
try:
    import astrbot.api
except ImportError:
    for name in ("astrbot", "astrbot.api", "astrbot.api.event", "astrbot.api.message_components"):
        sys.modules[name] = types.ModuleType(name)
    sys.modules["astrbot.api"].logger = logging.getLogger("chart-test")
    sys.modules["astrbot.api.event"].AstrMessageEvent = object
    class Plain:
        def __init__(self, text): self.text = text
    class Image:
        def __init__(self, *, file): self.file = file
    sys.modules["astrbot.api.message_components"].Plain = Plain
    sys.modules["astrbot.api.message_components"].Image = Image

from PIL import Image as PILImage
from aiohttp import web
from lifebuddy.chart_cmd import handle_chart
from lifebuddy.chart_image import chart_song_id, parse_chart_args, split_chart_image
from lifebuddy.image_cache import ImageCache
from lifebuddy.rbdx import RbdxAPI
from lifebuddy.settings import Settings


def png(columns=3, width=800, height=512):
    image = PILImage.new("RGB", (columns * (width + 16) - 16, height))
    for i in range(columns):
        image.paste((30 * i, 40, 70), (i * (width + 16), 0, i * (width + 16) + width, height))
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


class ImageTests(unittest.TestCase):
    def test_argument_parsing_and_special(self):
        self.assertEqual(parse_chart_args(["A", "song", "m"]), ("A song", "M"))
        self.assertEqual(parse_chart_args(["H"]), ("H", "H"))
        self.assertEqual(parse_chart_args([]), ("", "H"))
        self.assertEqual(chart_song_id({"id": 1, "special": {"ExtID": 2}}, "SP"), 2)
        self.assertEqual(chart_song_id({"id": 1, "special": {"ExtID": 2}}, "H"), 1)

    def test_pagination_keeps_all_columns(self):
        with tempfile.TemporaryDirectory() as root:
            paths = split_chart_image(png(3), 3, 800, 16, ImageCache(Path(root)))
            self.assertEqual(len(paths), 2)
            with PILImage.open(paths[0]) as first, PILImage.open(paths[1]) as last:
                self.assertEqual(first.size, (1616, 512))
                self.assertEqual(last.size, (800, 512))
                self.assertEqual(first.getpixel((820, 10)), (30, 40, 70))
                self.assertEqual(last.getpixel((10, 10)), (60, 40, 70))

    def test_layout_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                split_chart_image(png(3), 2, 800, 16, ImageCache(Path(root)))


class Event:
    def __init__(self, gid="public"): self.gid = gid
    def get_group_id(self): return self.gid
    def plain_result(self, text): return text
    def make_result(self):
        class Result:
            chain = []
            def use_t2i(self, value): self.t2i = value
        return Result()


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.catalogs = {
            "custom": [{"id": 123, "name": "Alpha", "special": {"ExtID": 124}}, {"id": 1234, "name": "Alpha II"}],
            "arcade": [{"id": 456, "name": "Arcade"}],
            "test": [{"id": 789, "name": "Hidden"}],
            "brit": [],
        }
    async def fetch_catalog(self, kind): return self.catalogs.get(kind, [])
    async def fetch_chart_images(self, song_id, difficulty, *, restricted=False):
        self.calls.append((song_id, difficulty, restricted))
        return ["page1.png", "page2.png"]


class CommandTests(unittest.IsolatedAsyncioTestCase):
    def runtime(self):
        return types.SimpleNamespace(
            settings=Settings(admin_group_ids=["admin"], wip_group_ids=["admin"]),
            rbdx=FakeAPI(), aliases=types.SimpleNamespace(entries=[]),
        )

    async def test_public_cannot_fetch_hidden_id_or_explicit_catalog(self):
        runtime = self.runtime()
        for parts in (["789"], ["test", "789"], ["arcade", "456"]):
            results = [r async for r in handle_chart(Event(), runtime, list(parts))]
            self.assertEqual(len(results), 1)
            self.assertIsInstance(results[0], str)
        self.assertEqual(runtime.rbdx.calls, [])

    async def test_exact_id_does_not_match_id_substring(self):
        runtime = self.runtime()
        result = [r async for r in handle_chart(Event(), runtime, ["123", "M"])]
        self.assertEqual(runtime.rbdx.calls, [(123, "M", False)])
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0].t2i)

    async def test_special_id_and_exact_title(self):
        runtime = self.runtime()
        await self.consume(Event(), runtime, ["124"])
        await self.consume(Event(), runtime, ["Alpha", "SP"])
        self.assertEqual(runtime.rbdx.calls, [(124, "SP", False), (124, "SP", False)])

    async def test_alias_to_special_id_keeps_permission_filter(self):
        runtime = self.runtime()
        runtime.aliases.entries = [types.SimpleNamespace(alias="SP别名", song_id=124)]
        await self.consume(Event(), runtime, ["SP别名"])
        self.assertEqual(runtime.rbdx.calls, [(124, "SP", False)])
        runtime.aliases.entries = [types.SimpleNamespace(alias="隐藏别名", song_id=789)]
        await self.consume(Event(), runtime, ["隐藏别名"])
        self.assertEqual(len(runtime.rbdx.calls), 1)

    async def test_admin_restricted_catalog(self):
        runtime = self.runtime()
        await self.consume(Event("admin"), runtime, ["test", "789", "H"])
        self.assertEqual(runtime.rbdx.calls, [(789, "H", True)])

    async def test_ambiguous_search_does_not_download(self):
        runtime = self.runtime()
        results = [r async for r in handle_chart(Event(), runtime, ["Alp"])]
        self.assertIn("SongID", results[0])
        self.assertEqual(runtime.rbdx.calls, [])

    async def consume(self, event, runtime, parts):
        return [r async for r in handle_chart(event, runtime, parts)]


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.seen = []
        async def endpoint(request):
            self.seen.append((dict(request.query), request.headers.get("X-Bot-Token")))
            if request.query["songId"] == "404":
                return web.json_response({"ok": False}, status=404)
            return web.Response(body=png(), content_type="image/png", headers={
                "X-Chart-Columns": "3", "X-Chart-Column-Width": "800", "X-Chart-Gap": "16",
            })
        app = web.Application()
        app.router.add_get("/bot/chart-image/", endpoint)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.api = RbdxAPI(Settings(rbdx_api_base=f"http://127.0.0.1:{port}", rbdx_bot_token="test-token"))

    async def asyncTearDown(self):
        await self.api.close()
        await self.runner.cleanup()
        self.temp.cleanup()

    async def test_download_png_headers_and_restricted_user(self):
        with patch("lifebuddy.image_cache.ImageCache", side_effect=lambda: ImageCache(Path(self.temp.name))):
            paths = await self.api.fetch_chart_images(123, "SP", restricted=True)
        self.assertEqual(len(paths), 2)
        self.assertEqual(self.seen[0], ({"songId": "123", "difficulty": "SP", "user": "ayulsam"}, "test-token"))

    async def test_missing_difficulty_is_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "raw"):
            await self.api.fetch_chart_images(404)


if __name__ == "__main__":
    unittest.main()