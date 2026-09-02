from __future__ import annotations

import re

from astrbot.api.event import AstrMessageEvent

from .aliases import AliasStore
from .identity import group_key, is_admin, observe, sender_qq
from .lists import short_api_error
from .rbdx import RbdxAPI
from .settings import Settings
from .store import BuddyStore

HELP = (
    "RBDX\n"
    "/rb bind <四位用户ID>\n"
    "/rb who\n"
    "/rb unbind [QQ或用户名]  （仅管理员）\n"
    "/rb song <关键词>\n"
    "/rb alias list"
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
        qq = sender_qq(event)
        account = runtime.store.get_bind(qq) if qq else None
        if not account:
            yield event.plain_result("还没绑号。/rb bind 四位用户ID")
            return
        yield event.plain_result(f"{qq} → {account}")
        return

    if action == "alias" and (not rest or rest[0].lower() == "list"):
        names = "、".join(entry.alias for entry in runtime.aliases.entries)
        yield event.plain_result(f"已登记别名 {len(runtime.aliases.entries)} 条：\n{names}")
        return

    if action == "song":
        query = " ".join(rest).strip()
        if not query:
            yield event.plain_result("用法：/rb song <关键词>")
            return
        kinds = ["custom", "arcade"]
        if runtime.settings.allow_wip(group_key(event)):
            kinds.append("test")
        groups = await runtime.rbdx.search_grouped(query, kinds)
        if not any(groups.values()):
            yield event.plain_result(f"没搜到「{query}」")
            return
        yield event.plain_result(runtime.rbdx.format_grouped_search(groups))
        return

    yield event.plain_result(HELP)


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
