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


@dataclass
class Settings:
    rbdx_api_base: str = "https://rbdx.chilundui.com"
    rbdx_image_base: str = "https://www.chilundui.com"
    rbdx_bot_token: str = ""
    netease_fallback: bool = True
    wip_group_ids: list[str] = field(default_factory=list)
    advice_group_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, config) -> "Settings":
        wip = _as_str_list(_get(config, "wip_group_ids", []))
        return cls(
            rbdx_api_base=str(_get(config, "rbdx_api_base", cls.rbdx_api_base)).rstrip("/"),
            rbdx_image_base=str(_get(config, "rbdx_image_base", cls.rbdx_image_base)).rstrip("/"),
            rbdx_bot_token=str(_get(config, "rbdx_bot_token", "")),
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
