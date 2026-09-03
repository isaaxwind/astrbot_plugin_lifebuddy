from __future__ import annotations

import re

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At, Image, Plain

from .aliases import AliasStore
from .identity import group_key, is_admin, is_private_chat, mentioned_qqs, observe, sender_qq
from .lists import require_account, short_api_error
from .rbdx import RbdxAPI, catalog_kind_label, hide_charter, parse_catalog_kind
from .settings import Settings
from .store import BuddyStore


def _rb_help(event: AstrMessageEvent, runtime: RbRuntime) -> str:
    restricted = runtime.settings.allow_restricted(group_key(event))
    private = is_private_chat(event)
    if private:
        bind = "/rb bind <用户ID或用户名> <密码>"
        song = "/rb song <关键词>  只搜自制谱"
    elif restricted:
        bind = "/rb bind <用户ID或用户名>"
        song = "/rb song [custom|arcade|test|test_all] <关键词>"
    else:
        bind = "/rb bind  群里不能绑，请私聊机器人"
        song = "/rb song <关键词>  只搜自制谱"
    return (
        "RBDX\n"
        f"{bind}\n"
        "/rb who [昵称/QQ/@]\n"
        "/rb recent  （/rb r）\n"
        "/rb unbind [QQ或用户名]  （仅管理员）\n"
        f"{song}\n"
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
        yield event.plain_result(_rb_help(event, runtime))
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
    if action in ("recent", "r"):
        async for result in _recent(event, runtime):
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

    yield event.plain_result(_rb_help(event, runtime))


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


def _recent_text(play: dict) -> str:
    title = str(play.get("title") or play.get("songId") or "???")
    artist = str(play.get("artist") or "")
    diff = str(play.get("difficultyLabel") or play.get("difficulty") or "?")
    level = play.get("level")
    if level:
        diff = f"{diff}{level}"
    score = play.get("score", 0)
    ar = play.get("ar", 0)
    rank = str(play.get("rank") or "")
    lines = [title]
    if artist:
        lines.append(artist)
    lines.append(f"{diff}  {score}  AR {ar}  {rank}".rstrip())
    return "\n".join(lines)


def _recent_chain(event: AstrMessageEvent, *parts):
    qq = sender_qq(event)
    chain: list = []
    if qq:
        chain.append(At(qq=qq))
        chain.append(Plain("\n"))
    chain.extend(parts)
    result = event.make_result()
    result.chain = chain or [Plain("")]
    result.use_t2i(False)
    return result


async def _recent(event: AstrMessageEvent, runtime: RbRuntime):
    account, err = require_account(event, runtime.store)
    if err:
        yield event.plain_result(err)
        return
    try:
        play = await runtime.rbdx.fetch_recent_play(account)
    except Exception as exc:
        yield event.plain_result(short_api_error(exc))
        return
    if not play:
        yield _recent_chain(event, Plain("没有游玩记录"))
        return
    text = _recent_text(play)
    song_id = play.get("songId")
    image = ""
    arcade = False
    if song_id:
        image = await runtime.rbdx.image_file(runtime.rbdx.jacket_url(int(song_id)))
        arcade = await runtime.rbdx.catalog_has_id("arcade", int(song_id))
    parts: list = []
    if image and not image.startswith("http"):
        parts.append(Image(file=image))
    parts.append(Plain(text))
    yield _recent_chain(event, *parts)
    if arcade:
        yield event.plain_result("【被我发现你在偷偷玩年了，hso】")


async def _bind(event: AstrMessageEvent, runtime: RbRuntime, rest: list[str]):
    qq = sender_qq(event)
    if not qq:
        yield event.plain_result("拿不到你的 QQ")
        return
    private = is_private_chat(event)
    in_admin_group = runtime.settings.allow_restricted(group_key(event))
    if not private and not in_admin_group:
        yield event.plain_result("群里不能绑，请私聊机器人")
        return
    if runtime.store.get_bind(qq):
        yield event.plain_result("你已经绑过了，要换绑找管理员")
        return
    if not rest:
        if private:
            yield event.plain_result("用法：/rb bind <用户ID或用户名> <密码>")
        else:
            yield event.plain_result("用法：/rb bind <用户ID或用户名>")
        return
    token = rest[0].strip()
    password = " ".join(rest[1:]).strip()
    if private and not password:
        yield event.plain_result("用法：/rb bind <用户ID或用户名> <密码>")
        return
    try:
        accounts = await runtime.rbdx.lookup_accounts(token)
    except Exception as exc:
        yield event.plain_result(short_api_error(exc))
        return
    if not accounts:
        yield event.plain_result(f"没有这个号：{token}")
        return
    if len(accounts) > 1:
        yield event.plain_result(
            "对上多个号，请用用户名绑：\n" + "\n".join(accounts)
        )
        return
    account = accounts[0]
    if runtime.store.get_bind_qq(account):
        yield event.plain_result("这个号已经绑过别的 QQ 了")
        return
    if password:
        try:
            ok = await runtime.rbdx.verify_password(account, password)
        except Exception as exc:
            yield event.plain_result(short_api_error(exc))
            return
        if not ok:
            yield event.plain_result("密码不对")
            return
    err = runtime.store.set_bind(qq, account)
    if err:
        yield event.plain_result(err)
        return
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
    gid = group_key(event)
    kinds = ["custom"]
    query_parts = list(rest)
    explicit = False
    if rest:
        parsed_kind = parse_catalog_kind(rest[0])
        if parsed_kind:
            kinds = [parsed_kind]
            query_parts = rest[1:]
            explicit = True
    query = " ".join(query_parts).strip()
    if not query:
        if runtime.settings.allow_restricted(gid):
            yield event.plain_result("用法：/rb song [custom|arcade|test|test_all] <关键词>")
        else:
            yield event.plain_result("用法：/rb song <关键词>")
        return
    if explicit:
        kind = kinds[0]
        if not runtime.settings.allow_catalog(gid, kind):
            yield event.plain_result("本群未开这类谱")
            return
    else:
        if runtime.settings.allow_catalog(gid, "arcade"):
            kinds.append("arcade")
        if runtime.settings.allow_catalog(gid, "test"):
            kinds.extend(["test", "brit"])
    groups = await runtime.rbdx.search_grouped(query, kinds)
    flat: list[tuple[str, dict]] = []
    for kind, hits in groups.items():
        for song in hits:
            flat.append((kind, song))
    if not flat:
        yield event.plain_result(f"没搜到「{query}」")
        return
    if len(flat) > 20:
        yield event.plain_result("曲子太多了！")
        return
    if len(flat) == 1:
        kind, song = flat[0]
        text = (
            f"{catalog_kind_label(kind)}\n"
            f"{runtime.rbdx.format_song_text(song, show_charter=not hide_charter(kind))}"
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
    yield event.plain_result(_rb_help(event, runtime))


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
