from __future__ import annotations

import re

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from .aliases import AliasStore
from .identity import group_key, is_admin, mentioned_qqs, observe, sender_qq
from .lists import short_api_error
from .rbdx import RbdxAPI, catalog_kind_label, is_wip_kind, parse_catalog_kind
from .settings import Settings
from .store import BuddyStore

HELP = (
    "RBDX\n"
    "/rb bind <四位用户ID>\n"
    "/rb who [昵称/QQ/@]\n"
    "/rb unbind [QQ或用户名]  （仅管理员）\n"
    "/rb song [custom|arcade|test|test_all] <关键词>\n"
    "/rb alias list\n"
    "/rb alias add <别名> <SongID或图片URL>\n"
    "/rb alias del <别名>  （仅管理员）"
)


class RbRuntime:
    def __init__(self, aliases: AliasStore, rbdx: RbdxAPI, settings: Settings, store: BuddyStore, context=None):
        self.aliases = aliases
        self.rbdx = rbdx
        self.settings = settings
        self.store = store
        self.context = context


async def handle_rb(event: AstrMessageEvent, runtime: RbRuntime):
    observe(event, runtime.store)
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    if not args:
        yield event.plain_result(HELP)
        return

    action = args[0].lower()
    rest = args[1:]

    if action == "bind":
        async for result in _bind(event, runtime, rest):
            yield result
        return
    if action == "unbind":
        async for result in _unbind(event, runtime, rest):
            yield result
        return
    if action == "who":
        async for result in _who(event, runtime, rest):
            yield result
        return

    if action == "alias":
        async for result in _alias(event, runtime, rest):
            yield result
        return

    if action == "song":
        async for result in _song(event, runtime, rest):
            yield result
        return

    yield event.plain_result(HELP)


def _who_line(runtime: RbRuntime, qq: str) -> str:
    nick = runtime.store.display_name(qq)
    account = runtime.store.get_bind(qq)
    label = f"{nick} ({qq})" if nick != qq else qq
    if account:
        return f"{label} → {account}"
    return f"{label} 还没绑号"


async def _who(event: AstrMessageEvent, runtime: RbRuntime, rest: list[str]):
    targets = mentioned_qqs(event)
    query = re.sub(r"@\S+", "", " ".join(rest)).strip()
    if targets:
        yield event.plain_result("\n".join(_who_line(runtime, qq) for qq in targets))
        return
    if not query:
        qq = sender_qq(event)
        if not qq:
            yield event.plain_result("拿不到你的 QQ")
            return
        account = runtime.store.get_bind(qq)
        if not account:
            yield event.plain_result("还没绑号。/rb bind 四位用户ID")
            return
        yield event.plain_result(_who_line(runtime, qq))
        return
    if query.isdigit():
        yield event.plain_result(_who_line(runtime, query))
        return
    rows = runtime.store.find_nicks(query)
    if not rows:
        yield event.plain_result(f"没找到「{query}」")
        return
    yield event.plain_result("\n".join(_who_line(runtime, row.qq) for row in rows))


async def _bind(event: AstrMessageEvent, runtime: RbRuntime, rest: list[str]):
    qq = sender_qq(event)
    if not qq:
        yield event.plain_result("拿不到你的 QQ")
        return
    player_id = "".join(rest).strip()
    if not re.fullmatch(r"\d{4}", player_id):
        yield event.plain_result("用法：/rb bind <四位用户ID>")
        return
    try:
        accounts = await runtime.rbdx.lookup_accounts_by_player_id(player_id)
    except Exception as exc:
        yield event.plain_result(short_api_error(exc))
        return
    if not accounts:
        yield event.plain_result(f"没有用户ID {player_id} 的账号")
        return
    if len(accounts) > 1:
        yield event.plain_result(
            f"用户ID {player_id} 对上 {len(accounts)} 个号，没法自动绑：\n" + "\n".join(accounts)
        )
        return
    account = accounts[0]
    runtime.store.set_bind(qq, account)
    yield event.plain_result(f"已绑 {qq} → {account}")


async def _unbind(event: AstrMessageEvent, runtime: RbRuntime, rest: list[str]):
    if not is_admin(event, runtime.context):
        yield event.plain_result("只有管理员能解绑")
        return
    target = " ".join(rest).strip()
    if not target:
        qq = sender_qq(event)
        name = runtime.store.clear_bind(qq=qq) if qq else None
        if not name:
            yield event.plain_result("你没有绑号")
            return
        yield event.plain_result(f"已解绑 {qq} （{name}）")
        return
    if target.isdigit() and runtime.store.get_bind(target):
        name = runtime.store.clear_bind(qq=target)
        yield event.plain_result(f"已解绑 {target} （{name}）")
        return
    name = runtime.store.clear_bind(account_name=target)
    if name:
        yield event.plain_result(f"已解绑 {name}")
        return
    yield event.plain_result(f"没找到绑定：{target}")


async def _song(event: AstrMessageEvent, runtime: RbRuntime, rest: list[str]):
    kinds = ["custom", "arcade"]
    query_parts = list(rest)
    if rest:
        parsed_kind = parse_catalog_kind(rest[0])
        if parsed_kind:
            kinds = [parsed_kind]
            query_parts = rest[1:]
    query = " ".join(query_parts).strip()
    if not query:
        yield event.plain_result("用法：/rb song [custom|arcade|test|test_all] <关键词>")
        return
    if any(is_wip_kind(kind) for kind in kinds) and not runtime.settings.allow_wip(
        group_key(event)
    ):
        yield event.plain_result("本群未开内测谱")
        return
    if kinds == ["custom", "arcade"] and runtime.settings.allow_wip(group_key(event)):
        kinds.extend(["test", "brit"])
    groups = await runtime.rbdx.search_grouped(query, kinds)
    flat: list[tuple[str, dict]] = []
    for kind, hits in groups.items():
        for song in hits:
            flat.append((kind, song))
    if not flat:
        yield event.plain_result(f"没搜到「{query}」")
        return
    if len(flat) == 1:
        kind, song = flat[0]
        text = (
            f"{catalog_kind_label(kind)}\n"
            f"{runtime.rbdx.format_song_text(song, show_charter=kind != 'brit')}"
        )
        image = await runtime.rbdx.image_file(
            runtime.rbdx.jacket_url(int(song["id"]))
        )
        result = event.make_result()
        if image and not image.startswith("http"):
            result.chain = [Image(file=image), Plain(text)]
        else:
            result.chain = [Plain(text)]
        result.use_t2i(False)
        yield result
        return
    yield event.plain_result(runtime.rbdx.format_grouped_search(groups))


async def _alias(event: AstrMessageEvent, runtime: RbRuntime, rest: list[str]):
    if not rest or rest[0].lower() == "list":
        names = "、".join(entry.alias for entry in runtime.aliases.entries)
        yield event.plain_result(f"已登记别名 {len(runtime.aliases.entries)} 条：\n{names}")
        return

    sub = rest[0].lower()
    args = rest[1:]
    if sub == "add":
        async for result in _alias_add(event, runtime, args):
            yield result
        return
    if sub in ("del", "rm", "remove"):
        if not is_admin(event, runtime.context):
            yield event.plain_result("只有管理员能删别名")
            return
        name = " ".join(args).strip()
        if not name:
            yield event.plain_result("用法：/rb alias del <别名>")
            return
        old = runtime.aliases.remove(name)
        if not old:
            yield event.plain_result(f"没有别名「{name}」")
            return
        yield event.plain_result(f"已删别名 {old.alias}")
        return
    yield event.plain_result(HELP)


async def _alias_add(event: AstrMessageEvent, runtime: RbRuntime, args: list[str]):
    if len(args) < 2:
        yield event.plain_result("用法：/rb alias add <别名> <SongID或图片URL>")
        return
    tail = args[-1]
    name = " ".join(args[:-1]).strip()
    song_id: int | None = None
    image = ""
    if tail.startswith("http://") or tail.startswith("https://"):
        image = tail
    elif re.fullmatch(r"\d+", tail):
        song_id = int(tail)
    else:
        yield event.plain_result("用法：/rb alias add <别名> <SongID或图片URL>")
        return
    if not name:
        yield event.plain_result("用法：/rb alias add <别名> <SongID或图片URL>")
        return
    entry, updated = runtime.aliases.add(
        name,
        song_id=song_id,
        image=image,
        image_base=runtime.settings.rbdx_image_base,
    )
    verb = "更新" if updated else "已加"
    extra = f" {entry.song_id}" if entry.song_id is not None else ""
    yield event.plain_result(f"{verb}别名 {entry.alias}{extra}")
