from __future__ import annotations

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from .identity import group_key
from .rbdx import (
    RbdxAPI,
    catalog_kind_label,
    hide_charter,
    jacket_id_for_song,
    parse_catalog_kind,
    parse_level_spec,
)
from .settings import Settings

USAGE = (
    "用法：/rbdx [等级] [关键词]\n"
    "等级可写 12 或 14.2；会同时按难度和曲名匹配\n"
    "管理群还可 /rbdx arcade|test|test_all [等级] [关键词]"
)


def parse_rbdx_args(
    args: list[str], *, recognize_kinds: bool = True
) -> tuple[str, int | str | None, str]:
    kind = "custom"
    level_spec: int | str | None = None
    query_parts: list[str] = []
    for tok in args:
        if recognize_kinds:
            parsed_kind = parse_catalog_kind(tok)
            if parsed_kind:
                kind = parsed_kind
                continue
        parsed_level = parse_level_spec(tok)
        if parsed_level is not None:
            if level_spec is None:
                level_spec = parsed_level
            query_parts.append(str(parsed_level))
            continue
        query_parts.append(tok)
    return kind, level_spec, " ".join(query_parts).strip()


def _no_match_text(label: str, level_spec: int | str | None, query: str) -> str:
    if level_spec is not None and query:
        return f"没有等级 {level_spec} 或曲名带「{query}」的{label}"
    if query:
        return f"没有曲名带「{query}」的{label}"
    if level_spec is not None:
        return f"没有等级 {level_spec} 的{label}"
    return f"{label}列表是空的"


async def handle_rbdx(event: AstrMessageEvent, rbdx: RbdxAPI, settings: Settings):
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    gid = group_key(event)
    recognize_kinds = settings.allow_restricted(gid)
    kind, level_spec, query = parse_rbdx_args(args, recognize_kinds=recognize_kinds)
    label = catalog_kind_label(kind)

    if not settings.allow_catalog(gid, kind):
        yield event.plain_result("本群未开这类谱")
        return

    try:
        picked = await rbdx.random_custom(level_spec, kind=kind, query=query)
    except Exception:
        yield event.plain_result(f"{label}列表暂时连不上")
        return

    if not picked:
        yield event.plain_result(_no_match_text(label, level_spec, query))
        return

    song, is_sp = picked
    display_level = level_spec if isinstance(level_spec, int) else None
    text = rbdx.format_catalog_song(
        song, display_level, show_charter=not hide_charter(kind)
    )
    image = await rbdx.image_file(rbdx.jacket_url(jacket_id_for_song(song, sp=is_sp)))
    result = event.make_result()
    if image and not image.startswith("http"):
        result.chain = [Image(file=image), Plain(text)]
    else:
        result.chain = [Plain(text)]
    result.use_t2i(False)
    yield result
