from __future__ import annotations

import asyncio
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

BOT_PATH_PREFIXES = ("/bot",)

# arcade/test 匿名会被 downloadall 清掉；ayulsam 的 AccessLevel 足够看这两类
CATALOG_USER = "ayulsam"
CATALOG_KINDS = frozenset({"custom", "arcade", "test", "test_all", "brit"})
CATALOG_TYPE_BY_KIND = {
    "custom": "custom",
    "arcade": "arcade",
    "test": "test_inner",
    "test_all": "test",
}
CATALOG_KIND_ALIASES = {
    "custom": "custom",
    "arcade": "arcade",
    "test": "test",
    "test_all": "test_all",
    "testall": "test_all",
    "自制": "custom",
    "街机": "arcade",
    "内测": "test",
    "wip": "test",
    "全内测": "test_all",
    "brit": "brit",
    "英国人": "brit",
    "mendes": "brit",
}
CATALOG_KIND_LABELS = {
    "custom": "自制谱",
    "arcade": "街机谱",
    "test": "内测谱",
    "test_all": "全部内测谱",
    "brit": "英国人谱面",
}
SEARCH_KIND_ORDER = ("custom", "arcade", "test", "brit")
CATALOG_TTL_SEC = 600
CATALOG_FAIL_COOLDOWN_SEC = 60
HTTP_UA = "Mozilla/5.0 (compatible; lifebuddy/1.0)"


def parse_catalog_kind(token: str) -> str | None:
    return CATALOG_KIND_ALIASES.get((token or "").strip().lower())


def hide_charter(kind: str) -> bool:
    return kind in ("brit", "arcade")


def catalog_kind_label(kind: str) -> str:
    return CATALOG_KIND_LABELS.get(kind, "自制谱")


def is_wip_kind(kind: str) -> bool:
    return kind in ("test", "test_all", "brit")


def song_matches_query(song: dict[str, Any], query: str) -> bool:
    needle = (query or "").strip().lower()
    if not needle:
        return True
    ext = special_ext_id(song)
    blob = (
        f"{song.get('name', '')} {song.get('artist', '')} {song.get('id', '')} "
        f"{ext or ''} {song_charter(song)}"
    ).lower()
    return needle in blob


def song_charter(song: dict[str, Any]) -> str:
    for key in ("Charter", "charter", "chart_author", "ChartAuthor"):
        value = str(song.get(key) or "").strip()
        if value:
            return value
    return ""


def _log_warning(message: str, *args: Any) -> None:
    try:
        from astrbot.api import logger

        logger.warning(message, *args)
    except Exception:
        print(message % args if args else message)


def _looks_like_image(data: bytes) -> bool:
    return data.startswith((b"\x89PNG", b"\xff\xd8\xff", b"RIFF", b"GIF8"))


def song_sp_level(song: dict[str, Any]) -> int | None:
    special = song.get("special")
    if not isinstance(special, dict):
        return None
    try:
        n = int(special.get("ExtLevel") or 0)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def special_ext_id(song: dict[str, Any]) -> int | None:
    special = song.get("special")
    if not isinstance(special, dict):
        return None
    try:
        n = int(special.get("ExtID") or 0)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def is_standalone_special(song: dict[str, Any], special_ids: set[int]) -> bool:
    try:
        sid = int(song.get("id") or 0)
    except (TypeError, ValueError):
        sid = 0
    if sid and sid in special_ids:
        return True
    name = str(song.get("name") or "").strip().upper()
    return name.endswith("(SPECIAL)") and not song.get("special")


def active_levels(song: dict[str, Any]) -> list[int]:
    out: list[int] = []
    for value in song.get("level") or []:
        try:
            level = int(value)
        except (TypeError, ValueError):
            continue
        if level > 0:
            out.append(level)
    sp = song_sp_level(song)
    if sp:
        out.append(sp)
    return out


def filter_by_level(songs: list[dict[str, Any]], level: int) -> list[dict[str, Any]]:
    return [song for song in songs if level in active_levels(song)]


def pick_random_song(
    songs: list[dict[str, Any]], level: int | None = None
) -> tuple[dict[str, Any], bool] | None:
    pool: list[tuple[dict[str, Any], bool]] = []
    for song in songs:
        bmh: list[int] = []
        for value in song.get("level") or []:
            try:
                n = int(value)
            except (TypeError, ValueError):
                continue
            if n > 0:
                bmh.append(n)
        sp = song_sp_level(song)
        if level is None:
            pool.append((song, False))
            if sp:
                pool.append((song, True))
            continue
        if level in bmh:
            pool.append((song, False))
        if sp == level:
            pool.append((song, True))
    if not pool:
        return None
    return random.choice(pool)


def jacket_id_for_song(song: dict[str, Any], *, sp: bool = False) -> int:
    if sp:
        ext = special_ext_id(song)
        if ext:
            return ext
    return int(song["id"])


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
        self._catalogs: dict[str, list[dict[str, Any]]] = {}
        self._catalog_at: dict[str, float] = {}
        self._catalog_url: dict[str, str] = {}
        self._fail_until: dict[str, float] = {}

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

    def _jacket_proxy(self, url: str) -> str | None:
        base = (self.settings.rbdx_image_base or "").rstrip("/")
        if base and "chilundui.com" not in base and url.startswith(base):
            return None
        return self._proxy()

    def _http_headers(self, *, accept: str = "*/*") -> dict[str, str]:
        return {
            "User-Agent": HTTP_UA,
            "Accept": accept,
        }

    def _can_fetch_jacket(self, url: str) -> bool:
        base = (self.settings.rbdx_image_base or "").rstrip("/")
        if base and url.startswith(base):
            return True
        return "chilundui.com" in url

    def _is_remywiki(self, url: str) -> bool:
        return "remywiki.com" in (url or "").lower()

    async def image_file(self, url: str, *, external: bool = False) -> str:
        """把夹克拉到本地。CDN 夹克走常驻会话；remywiki / 自定义链接只试一次，失败回原 URL。"""
        if not url or not url.startswith(("http://", "https://")):
            return url
        remy = self._is_remywiki(url)
        if not remy and not self._can_fetch_jacket(url) and not external:
            return url
        isolated = remy or (external and not self._can_fetch_jacket(url))
        timeout = aiohttp.ClientTimeout(
            total=8 if isolated else 12,
            sock_connect=3 if isolated else 4,
        )
        if remy:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "image/png,image/jpeg,image/webp,image/*,*/*;q=0.8",
                "Referer": "https://remywiki.com/",
            }
        else:
            headers = self._http_headers(accept="image/png,image/jpeg,image/webp,*/*")
        try:
            data = await self._read_image_bytes(url, headers, timeout, isolated=isolated)
        except Exception as exc:
            _log_warning("RBDX jacket fail: %s (%s)", exc, url)
            return url
        if not data or not _looks_like_image(data):
            _log_warning("RBDX jacket not an image (%s bytes): %s", len(data or b""), url)
            return url
        suffix = ".jpg" if data.startswith(b"\xff\xd8\xff") else ".png"
        path = Path(tempfile.gettempdir()) / f"lifebuddy_{abs(hash(url)) % 10**10}{suffix}"
        path.write_bytes(data)
        return str(path)

    async def _read_image_bytes(
        self,
        url: str,
        headers: dict[str, str],
        timeout: aiohttp.ClientTimeout,
        *,
        isolated: bool,
    ) -> bytes:
        proxy = self._jacket_proxy(url)
        if isolated:
            connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=True)
            async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
                async with session.get(
                    url, headers=headers, timeout=timeout, proxy=proxy
                ) as response:
                    if response.status != 200:
                        _log_warning("RBDX jacket HTTP %s: %s", response.status, url)
                        return b""
                    return await response.read()
        session = await self._session_get()
        async with session.get(
            url, headers=headers, timeout=timeout, proxy=proxy
        ) as response:
            if response.status != 200:
                _log_warning("RBDX jacket HTTP %s: %s", response.status, url)
                return b""
            return await response.read()

    def _catalog_url_for(self, kind: str) -> str:
        if kind not in CATALOG_TYPE_BY_KIND:
            kind = "custom"
        type_name = CATALOG_TYPE_BY_KIND.get(kind, "custom")
        url = f"{self.settings.rbdx_api_base}/downloadall/?type={type_name}"
        if kind in ("arcade", "test", "test_all"):
            url += f"&user={CATALOG_USER}"
        return url

    async def fetch_custom_catalog(self, *, force: bool = False) -> list[dict[str, Any]]:
        return await self.fetch_catalog("custom", force=force)

    async def fetch_brit_catalog(self, *, force: bool = False) -> list[dict[str, Any]]:
        all_test, inner = await asyncio.gather(
            self.fetch_catalog("test_all", force=force),
            self.fetch_catalog("test", force=force),
        )
        inner_ids: set[int] = set()
        for song in inner:
            try:
                inner_ids.add(int(song["id"]))
            except (TypeError, ValueError, KeyError):
                continue
        return [
            song
            for song in all_test
            if int(song.get("id") or 0) not in inner_ids
        ]

    async def fetch_catalog(self, kind: str = "custom", *, force: bool = False) -> list[dict[str, Any]]:
        if kind == "brit":
            return await self.fetch_brit_catalog(force=force)
        if kind not in CATALOG_TYPE_BY_KIND:
            kind = "custom"
        now = time.monotonic()
        cached = self._catalogs.get(kind) or []
        at = self._catalog_at.get(kind, 0.0)
        fail_until = self._fail_until.get(kind, 0.0)
        if not force and cached and (now - at) < CATALOG_TTL_SEC:
            return cached
        if not force and now < fail_until:
            return cached

        timeout = aiohttp.ClientTimeout(total=15)
        headers = self._http_headers(accept="application/json")
        url = self._catalog_url_for(kind)
        last_error: Exception | None = None
        data: Any = None
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
                else:
                    data = await response.json(content_type=None)
        except Exception as exc:
            last_error = exc
            await self._reset_session()

        songs = data.get("songs") if isinstance(data, dict) else None
        if isinstance(songs, list):
            raw = [song for song in songs if isinstance(song, dict) and song.get("id")]
            special_ids = {
                ext for song in raw if (ext := special_ext_id(song)) is not None
            }
            catalog = [
                song for song in raw if not is_standalone_special(song, special_ids)
            ]
            self._catalogs[kind] = catalog
            self._catalog_at[kind] = now
            self._catalog_url[kind] = url
            self._fail_until[kind] = 0.0
            return catalog

        if last_error is None:
            last_error = RuntimeError(f"{url} 没有 songs 列表")
        self._fail_until[kind] = now + CATALOG_FAIL_COOLDOWN_SEC
        if last_error:
            _log_warning("RBDX catalog skip: %s", last_error)
        return cached

    async def random_custom(
        self,
        level: int | None = None,
        kind: str = "custom",
        query: str = "",
    ) -> tuple[dict[str, Any], bool] | None:
        songs = await self.fetch_catalog(kind)
        if query.strip():
            songs = [song for song in songs if song_matches_query(song, query)]
        return pick_random_song(songs, level)

    async def search_published(
        self, query: str, limit: int | None = None, kind: str = "custom"
    ) -> list[dict[str, Any]]:
        needle = (query or "").strip().lower()
        if not needle:
            return []
        songs = await self.fetch_catalog(kind)
        hits: list[dict[str, Any]] = []
        for song in songs:
            if not song_matches_query(song, needle):
                continue
            hits.append(self._to_search_card(song))
            if limit is not None and len(hits) >= limit:
                break
        return hits

    async def search_grouped(
        self, query: str, kinds: list[str], limit: int | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        fetched = await asyncio.gather(
            *[self.search_published(query, limit=limit, kind=kind) for kind in kinds]
        )
        return {kind: hits for kind, hits in zip(kinds, fetched)}

    def _to_search_card(self, song: dict[str, Any]) -> dict[str, Any]:
        levels = active_levels(song)
        padded = (song.get("level") or []) + [0, 0, 0]
        return {
            "id": int(song["id"]),
            "name": song.get("name") or "",
            "artist": song.get("artist") or "",
            "chart_author": song_charter(song),
            "pack_id": None,
            "pack_name": "",
            "levels": {
                "b": padded[0] or None,
                "n": padded[1] or None,
                "h": padded[2] or None,
                "sp": song_sp_level(song),
            },
            "matched_levels": levels,
        }

    def _bot_headers(self) -> dict[str, str]:
        headers = self._http_headers(accept="application/json")
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

    async def fetch_song_meta(
        self, song_id: int, difficulty: int | None = None
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {"songId": int(song_id)}
        if difficulty is not None:
            params["difficulty"] = int(difficulty)
        data = await self._bot_request("GET", "/song", params=params)
        song = data.get("song") if isinstance(data, dict) else None
        return song if isinstance(song, dict) else None

    async def fetch_recent_play(self, account_name: str) -> dict[str, Any] | None:
        data = await self._bot_request(
            "GET", "/recent", params={"accountName": account_name}
        )
        play = data.get("play") if isinstance(data, dict) else None
        return play if isinstance(play, dict) else None

    async def lookup_accounts_by_player_id(self, player_id: str) -> list[str]:
        data = await self._bot_request("GET", "/accounts", params={"playerId": player_id})
        accounts = data.get("accounts") if isinstance(data, dict) else None
        if not isinstance(accounts, list):
            return []
        return [str(name) for name in accounts if str(name).strip()]

    async def lookup_accounts(self, token: str) -> list[str]:
        token = (token or "").strip()
        if not token:
            return []
        if re.fullmatch(r"\d{4}", token):
            return await self.lookup_accounts_by_player_id(token)
        data = await self._bot_request("GET", "/accounts", params={"accountName": token})
        accounts = data.get("accounts") if isinstance(data, dict) else None
        if not isinstance(accounts, list):
            return []
        return [str(name) for name in accounts if str(name).strip()]

    async def verify_password(self, account_name: str, password: str) -> bool:
        try:
            data = await self._bot_request(
                "POST",
                "/verify",
                json_body={"accountName": account_name, "password": password},
            )
        except RuntimeError as exc:
            text = str(exc)
            if "401" in text or "403" in text:
                return False
            raise
        if not isinstance(data, dict):
            return False
        return bool(data.get("ok")) and bool(data.get("accountName"))

    async def catalog_has_id(self, kind: str, song_id: int) -> bool:
        try:
            songs = await self.fetch_catalog(kind)
        except Exception:
            return False
        target = int(song_id)
        return any(int(song.get("id") or 0) == target for song in songs)

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

    def format_catalog_song(
        self, song: dict[str, Any], level: int | None = None, *, show_charter: bool = True
    ) -> str:
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
        sp = song_sp_level(song)
        if sp:
            bits.append(f"SP{sp}")
        lines = [name, artist]
        charter = song_charter(song)
        if show_charter and charter:
            lines.append(f"谱师 {charter}")
        if bits:
            lines.append(" / ".join(bits))
        return "\n".join(lines)

    def format_song_text(self, song: dict[str, Any], *, show_charter: bool = True) -> str:
        name = song.get("name", "")
        artist = song.get("artist", "")
        chart_author = song_charter(song) or (song.get("chart_author") or "")
        pack_name = song.get("pack_name") or ""
        pack_id = song.get("pack_id")
        levels = song.get("levels") or {}
        lines = [name, artist]
        song_id = song.get("id")
        if song_id not in (None, ""):
            lines.append(f"ID {song_id}")
        if show_charter and chart_author:
            lines.append(f"谱师 {chart_author}")
        pack_bit = pack_name
        if pack_id is not None:
            pack_bit = f"{pack_name} ({pack_id})".strip()
        level_bits = []
        for key, label in (("b", "B"), ("n", "M"), ("h", "H"), ("sp", "SP")):
            value = levels.get(key)
            if value:
                level_bits.append(f"{label}{value}")
        extra = "  ".join(x for x in (pack_bit, " ".join(level_bits)) if x)
        if extra:
            lines.append(extra)
        return "\n".join(lines)

    def format_grouped_search(self, groups: dict[str, list[dict[str, Any]]]) -> str:
        blocks: list[str] = []
        seen: set[str] = set()
        for kind in list(SEARCH_KIND_ORDER) + [k for k in groups if k not in SEARCH_KIND_ORDER]:
            if kind in seen:
                continue
            seen.add(kind)
            hits = groups.get(kind) or []
            if not hits:
                continue
            body = "\n\n".join(
                self.format_song_text(song, show_charter=not hide_charter(kind)) for song in hits
            )
            blocks.append(f"{catalog_kind_label(kind)}：\n{body}")
        return "\n\n".join(blocks)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
