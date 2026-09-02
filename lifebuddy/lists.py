from __future__ import annotations

from typing import Any

DIFF_LABEL = {0: "B", 1: "M", 2: "H", 3: "SP"}


class NumberedCache:
    def __init__(self):
        self._items: dict[str, list[Any]] = {}

    def put(self, key: str, items: list[Any]) -> list[Any]:
        self._items[key] = list(items)
        return self._items[key]

    def get(self, key: str) -> list[Any]:
        return self._items.get(key) or []

    def resolve_index(self, key: str, token: str) -> Any | None:
        if not token.isdigit():
            return None
        items = self.get(key)
        n = int(token)
        if 1 <= n <= len(items):
            return items[n - 1]
        return None


def parse_is_ok(token: str) -> int | None:
    raw = token.strip().lower()
    if raw in ("0", "ng", "要改", "不通过", "fail"):
        return 0
    if raw in ("1", "ok", "过", "通过", "pass"):
        return 1
    return None


def short_api_error(_exc: Exception) -> str:
    return "接口失败，等会再试"


def require_account(event, store) -> tuple[str | None, str | None]:
    from .identity import sender_qq

    qq = sender_qq(event)
    if not qq:
        return None, "拿不到你的 QQ"
    account = store.get_bind(qq)
    if not account:
        return None, "先 /rb bind 四位用户ID"
    return account, None
