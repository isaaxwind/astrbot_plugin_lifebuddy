from __future__ import annotations

from dataclasses import dataclass, field


def _get(config, key, default):
    if config is None:
        return default
    try:
        value = config.get(key, default)
    except Exception:
        return default
    return default if value is None else value


def _as_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x) for x in value]


_LEGACY_IMAGE_BASES = {
    "https://www.chilundui.com",
    "http://www.chilundui.com",
}


def _normalize_api_base(raw) -> str:
    base = str(raw or "").strip().rstrip("/")
    if not base or base in _LEGACY_API_BASES:
        return Settings.rbdx_api_base
    return base


def _normalize_image_base(raw) -> str:
    base = str(raw or "").strip().rstrip("/")
    if not base or base in _LEGACY_IMAGE_BASES:
        return Settings.rbdx_image_base
    return base


def normalize_http_proxy(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if value.isdigit():
        return f"http://127.0.0.1:{value}"
    if "://" not in value:
        return f"http://{value}"
    return value


_LEGACY_API_BASES = {
    "https://rbdx.chilundui.com",
    "http://rbdx.chilundui.com",
}


@dataclass
class Settings:
    rbdx_api_base: str = "https://chilundui.com/api"
    rbdx_image_base: str = "https://chilundui.com"
    rbdx_bot_token: str = ""
    rbdx_http_proxy: str = ""
    netease_fallback: bool = True
    wip_group_ids: list[str] = field(default_factory=list)
    advice_group_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, config) -> "Settings":
        wip = _as_str_list(_get(config, "wip_group_ids", []))
        return cls(
            rbdx_api_base=_normalize_api_base(_get(config, "rbdx_api_base", cls.rbdx_api_base)),
            rbdx_image_base=_normalize_image_base(_get(config, "rbdx_image_base", cls.rbdx_image_base)),
            rbdx_bot_token=str(_get(config, "rbdx_bot_token", "")),
            rbdx_http_proxy=normalize_http_proxy(str(_get(config, "rbdx_http_proxy", ""))),
            netease_fallback=bool(_get(config, "netease_fallback", True)),
            wip_group_ids=[str(x) for x in wip],
            advice_group_ids=[str(x) for x in _as_str_list(_get(config, "advice_group_ids", []))],
        )

    def allow_wip(self, group_id: str | None) -> bool:
        if not group_id:
            return False
        return str(group_id) in self.wip_group_ids

    def allow_advice(self, group_id: str | None) -> bool:
        if not self.advice_group_ids:
            return False
        return str(group_id or "") in self.advice_group_ids
