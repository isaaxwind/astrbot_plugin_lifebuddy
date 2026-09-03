from __future__ import annotations

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from .identity import group_key
from .rbdx import (
    RbdxAPI,
    catalog_kind_label,
    hide_charter,
    is_wip_kind,
    jacket_id_for_song,
    parse_catalog_kind,
    parse_level_token,
)
from .settings import Settings

USAGE = (
    "用法：/rbdx [arcade|test|test_all] [等级] [关键词]\n"
    "例如 /rbdx 12  /rbdx arcade ryu  /rbdx test 12  /rbdx arcade 10 ryu"
)


def parse_rbdx_args(args: list[str]) -> tuple[str, int | None, str]:
    kind = "custom"
    level: int | None = None
    query_parts: list[str] = []
    for tok in args:
        parsed_kind = parse_catalog_kind(tok)
        if parsed_kind:
            kind = parsed_kind
            continue
        parsed_level = parse_level_token(tok)
        if parsed_level is not None and 1 <= parsed_level <= 20 and level is None:
            level = parsed_level
            continue
        query_parts.append(tok)
    return kind, level, " ".join(query_parts).strip()


async def handle_rbdx(event: AstrMessageEvent, rbdx: RbdxAPI, settings: Settings):
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    kind, level, query = parse_rbdx_args(args)
    label = catalog_kind_label(kind)

    if is_wip_kind(kind) and not settings.allow_wip(group_key(event)):
        yield event.plain_result("本群未开内测谱")
        return

    try:
        picked = await rbdx.random_custom(level, kind=kind, query=query)
    except Exception:
        yield event.plain_result(f"{label}列表暂时连不上")
        return

    if not picked:
        extra = f"「{query}」" if query else ""
        if level is None and extra:
            yield event.plain_result(f"没有带 {extra} 的{label}")
        elif extra:
            yield event.plain_result(f"没有等级 {level} 且带 {extra} 的{label}")
        elif level is None:
            yield event.plain_result(f"{label}列表是空的")
        else:
            yield event.plain_result(f"没有等级 {level} 的{label}")
        return

    song, is_sp = picked
    text = rbdx.format_catalog_song(song, level, show_charter=not hide_charter(kind))
    image = await rbdx.image_file(rbdx.jacket_url(jacket_id_for_song(song, sp=is_sp)))
    result = event.make_result()
    if image and not image.startswith("http"):
        result.chain = [Image(file=image), Plain(text)]
    else:
        result.chain = [Plain(text)]
    result.use_t2i(False)
    yield result
