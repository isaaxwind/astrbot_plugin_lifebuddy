from __future__ import annotations

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from .rbdx import RbdxAPI, parse_level_token

USAGE = "用法：/rbdx  或  /rbdx [等级]\n例如 /rbdx 12"


async def handle_rbdx(event: AstrMessageEvent, rbdx: RbdxAPI):
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    level: int | None = None
    if len(args) > 1:
        yield event.plain_result(USAGE)
        return
    if args:
        level = parse_level_token(args[0])
        if level is None or level < 1 or level > 20:
            yield event.plain_result(USAGE)
            return

    try:
        song = await rbdx.random_custom(level)
    except Exception as exc:
        yield event.plain_result(f"自制谱列表拉失败：{exc}")
        return

    if not song:
        if level is None:
            yield event.plain_result("自制谱列表是空的")
        else:
            yield event.plain_result(f"没有等级 {level} 的自制谱")
        return

    result = event.make_result()
    result.chain = [
        Image(file=rbdx.jacket_url(int(song["id"]))),
        Plain(rbdx.format_catalog_song(song, level)),
    ]
    result.use_t2i(False)
    yield result
