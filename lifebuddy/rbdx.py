from __future__ import annotations

import random
import re
import socket
import tempfile
import time
import json
from pathlib import Path
from typing import Any

import aiohttp

from .settings import Settings

DOWNLOADALL_PATHS = (
    "/downloadall/?type=custom",
)

BOT_PATH_PREFIXES = ("/bot",)

CATALOG_TTL_SEC = 600
CATALOG_FAIL_COOLDOWN_SEC = 60


def active_levels(song: dict[str, Any]) -> list[int]:
    out: list[int] = []
    for value in song.get("level") or []:
        try:
            level = int(value)
        except (TypeError, ValueError):
            continue
        if level > 0:
            out.append(level)
    return out


def filter_by_level(songs: list[dict[str, Any]], level: int) -> list[dict[str, Any]]:
    return [song for song in songs if level in active_levels(song)]


def pick_random_song(
    songs: list[dict[str, Any]], level: int | None = None
) -> dict[str, Any] | None:
    pool = filter_by_level(songs, level) if level is not None else list(songs)
    if not pool:
        return None
    return random.choice(pool)


def parse_level_token(token: str) -> int | None:
    raw = token.strip()
    if not raw:
        return None
    lowered = raw.lower().replace("等级", "")
    lowered = lowered.replace("lvl", "").replace("lv", "").strip()
    if re.fullmatch(r"\d+", lowered):
        return int(lowered)
    return None


class RbdxAPI:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._session: aiohttp.ClientSession | None = None
        self._catalog: list[dict[str, Any]] = []
        self._catalog_at: float = 0.0
        self._catalog_url: str | None = None
        self._fail_until: float = 0.0

    def jacket_url(self, song_id: int) -> str:
        return f"{self.settings.rbdx_image_base}/data/rbdx/image/song/{song_id}.png"

    async def _reset_session(self) -> None:
        session = self._session
        self._session = None
        if session and not session.closed:
            try:
                await session.close()
            except Exception:
                pass

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                family=socket.AF_INET,
                ttl_dns_cache=300,
                ssl=True,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                trust_env=True,
            )
        return self._session

    def _proxy(self) -> str | None:
        raw = (self.settings.rbdx_http_proxy or "").strip()
        return raw or None

    async def image_file(self, url: str) -> str:
        """Download chilundui images through the same proxy; otherwise keep the URL."""
        if not url or "chilundui.com" not in url:
            return url
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            session = await self._session_get()
            async with session.get(url, timeout=timeout, proxy=self._proxy()) as response:
                if response.status != 200:
                    return url
                data = await response.read()
        except Exception:
            return url
        suffix = ".png"
        if url.lower().endswith(".jpg") or url.lower().endswith(".jpeg"):
            suffix = ".jpg"
        path = Path(tempfile.gettempdir()) / f"lifebuddy_{abs(hash(url)) % 10**10}{suffix}"
        path.write_bytes(data)
        return str(path)

    def _catalog_urls(self) -> list[str]:
        urls = [f"{self.settings.rbdx_api_base}{path}" for path in DOWNLOADALL_PATHS]
        if self._catalog_url:
            urls = [self._catalog_url] + [u for u in urls if u != self._catalog_url]
        return urls

    async def fetch_custom_catalog(self, *, force: bool = False) -> list[dict[str, Any]]:
        now = time.monotonic()
        if (
            not force
            and self._catalog
            and (now - self._catalog_at) < CATALOG_TTL_SEC
        ):
            return self._catalog
        if not force and now < self._fail_until:
            return self._catalog

        timeout = aiohttp.ClientTimeout(total=15)
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; lifebuddy/1.0)",
            "Accept": "application/json",
        }
        last_error: Exception | None = None
        for url in self._catalog_urls():
            try:
                session = await self._session_get()
                async with session.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    proxy=self._proxy(),
                ) as response:
                    if response.status != 200:
                        last_error = RuntimeError(f"{url} HTTP {response.status}")
                        continue
                    data = await response.json(content_type=None)
            except Exception as exc:
                last_error = exc
                await self._reset_session()
                continue
            songs = data.get("songs") if isinstance(data, dict) else None
            if not isinstance(songs, list):
                last_error = RuntimeError(f"{url} 没有 songs 列表")
                continue
            self._catalog = [song for song in songs if isinstance(song, dict) and song.get("id")]
            self._catalog_at = now
            self._catalog_url = url
            self._fail_until = 0.0
            return self._catalog

        self._fail_until = now + CATALOG_FAIL_COOLDOWN_SEC
        if last_error:
            try:
                from astrbot.api import logger

                logger.warning("RBDX catalog skip: %s", last_error)
            except Exception:
                print(f"RBDX catalog skip: {last_error}")
        return self._catalog

    async def random_custom(self, level: int | None = None) -> dict[str, Any] | None:
        songs = await self.fetch_custom_catalog()
        return pick_random_song(songs, level)

    async def search_published(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        needle = (query or "").strip().lower()
        if not needle:
            return []
        songs = await self.fetch_custom_catalog()
        hits: list[dict[str, Any]] = []
        for song in songs:
            blob = f"{song.get('name', '')} {song.get('artist', '')} {song.get('id', '')}".lower()
            if needle not in blob:
                continue
            hits.append(self._to_search_card(song))
            if len(hits) >= limit:
                break
        return hits

    def _to_search_card(self, song: dict[str, Any]) -> dict[str, Any]:
        levels = active_levels(song)
        padded = (song.get("level") or []) + [0, 0, 0]
        return {
            "id": int(song["id"]),
            "name": song.get("name") or "",
            "artist": song.get("artist") or "",
            "chart_author": "",
            "pack_id": None,
            "pack_name": "",
            "levels": {
                "b": padded[0] or None,
                "n": padded[1] or None,
                "h": padded[2] or None,
                "sp": None,
            },
            "matched_levels": levels,
        }

    def _bot_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; lifebuddy/1.0)",
            "Accept": "application/json",
        }
        token = (self.settings.rbdx_bot_token or "").strip()
        if token:
            headers["X-Bot-Token"] = token
        return headers

    async def _bot_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        session = await self._session_get()
        timeout = aiohttp.ClientTimeout(total=30)
        headers = self._bot_headers()
        last_error: Exception | None = None
        for prefix in BOT_PATH_PREFIXES:
            url = f"{self.settings.rbdx_api_base}{prefix}{path}"
            try:
                async with session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=timeout,
                    proxy=self._proxy(),
                ) as response:
                    text = await response.text()
                    if response.status >= 400:
                        last_error = RuntimeError(f"{url} HTTP {response.status}: {text[:300]}")
                        if response.status == 404:
                            continue
                        raise last_error
                    if not text:
                        return {}
                    data = json.loads(text)
            except RuntimeError:
                raise
            except Exception as exc:
                last_error = exc
                await self._reset_session()
                continue
            if isinstance(data, dict) and data.get("ok") is False:
                raise RuntimeError(str(data.get("error") or data))
            return data
        if last_error:
            raise last_error
        raise RuntimeError(f"bot api {path} failed")

    async def lookup_accounts_by_player_id(self, player_id: str) -> list[str]:
        data = await self._bot_request("GET", "/accounts", params={"playerId": player_id})
        accounts = data.get("accounts") if isinstance(data, dict) else None
        if not isinstance(accounts, list):
            return []
        return [str(name) for name in accounts if str(name).strip()]

    async def list_advice(self, account_name: str | None = None) -> list[dict[str, Any]]:
        params = {}
        if account_name:
            params["accountName"] = account_name
        data = await self._bot_request("GET", "/advice", params=params or None)
        items = data.get("items") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []

    async def list_advice_comments(self, song_id: int) -> list[dict[str, Any]]:
        data = await self._bot_request(
            "GET", "/advice/comments", params={"songId": int(song_id)}
        )
        comments = data.get("comments") if isinstance(data, dict) else None
        return comments if isinstance(comments, list) else []

    async def upsert_advice_comment(
        self,
        account_name: str,
        song_id: int,
        comment: str,
        is_ok: int = 1,
    ) -> dict[str, Any]:
        data = await self._bot_request(
            "POST",
            "/advice/comments",
            json_body={
                "accountName": account_name,
                "songId": int(song_id),
                "comment": comment,
                "isOk": int(is_ok),
            },
        )
        return data if isinstance(data, dict) else {"ok": True}

    async def delete_advice_comment(
        self,
        *,
        comment_id: int | None = None,
        account_name: str | None = None,
        song_id: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if comment_id is not None:
            body["id"] = int(comment_id)
        if account_name:
            body["accountName"] = account_name
        if song_id is not None:
            body["songId"] = int(song_id)
        data = await self._bot_request("DELETE", "/advice/comments", json_body=body)
        return data if isinstance(data, dict) else {"ok": True}

    async def list_subdiff(self, account_name: str | None = None) -> list[dict[str, Any]]:
        params = {}
        if account_name:
            params["accountName"] = account_name
        data = await self._bot_request("GET", "/subdiff", params=params or None)
        items = data.get("items") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []

    async def vote_subdiff(
        self,
        account_name: str,
        song_id: int,
        difficulty: int,
        subdiff: int,
    ) -> dict[str, Any]:
        data = await self._bot_request(
            "POST",
            "/subdiff/votes",
            json_body={
                "accountName": account_name,
                "songId": int(song_id),
                "difficulty": int(difficulty),
                "subdiff": int(subdiff),
            },
        )
        return data if isinstance(data, dict) else {"ok": True}

    async def get_song(self, song_id: int) -> dict[str, Any] | None:
        songs = await self.fetch_custom_catalog()
        for song in songs:
            if int(song.get("id") or 0) == int(song_id):
                return self._to_search_card(song)
        return None

    async def get_pack(self, pack_id_or_name: str) -> dict[str, Any] | None:
        _ = pack_id_or_name
        return None

    async def latest_packs(self, limit: int = 5) -> list[dict[str, Any]]:
        _ = limit
        return []

    async def search_author(self, name: str, include_wip: bool = False) -> dict[str, Any] | None:
        _ = (name, include_wip)
        return None

    def format_catalog_song(self, song: dict[str, Any], level: int | None = None) -> str:
        name = song.get("name") or ""
        artist = song.get("artist") or ""
        padded = (song.get("level") or []) + [0, 0, 0]
        bits = []
        for label, value in zip(("B", "M", "H"), padded):
            try:
                n = int(value)
            except (TypeError, ValueError):
                n = 0
            if n > 0:
                bits.append(f"{label}{n}")
        header = "随机自制谱" + (f" · Lv.{level}" if level is not None else "")
        lines = [header, name, artist]
        if bits:
            lines.append(" / ".join(bits))
        return "\n".join(lines)

    def format_song_text(self, song: dict[str, Any]) -> str:
        name = song.get("name", "")
        artist = song.get("artist", "")
        chart_author = song.get("chart_author") or ""
        pack_name = song.get("pack_name") or ""
        pack_id = song.get("pack_id")
        levels = song.get("levels") or {}
        lines = [name, artist]
        if chart_author:
            lines.append(f"谱师 {chart_author}")
        pack_bit = pack_name
        if pack_id is not None:
            pack_bit = f"{pack_name} ({pack_id})".strip()
        level_bits = []
        for key, label in (("b", "B"), ("n", "N"), ("h", "H"), ("sp", "SP")):
            value = levels.get(key)
            if value:
                level_bits.append(f"{label}{value}")
        extra = "  ".join(x for x in (pack_bit, " ".join(level_bits)) if x)
        if extra:
            lines.append(extra)
        return "\n".join(lines)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
