from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from .store import BuddyStore, NickRow


def stop_event(event: AstrMessageEvent) -> None:
    stopper = getattr(event, "stop_event", None)
    if callable(stopper):
        stopper()


def mentioned_qqs(event: AstrMessageEvent) -> list[str]:
    obj = getattr(event, "message_obj", None)
    chain = getattr(obj, "message", None) or []
    found: list[str] = []
    for item in chain:
        if type(item).__name__ != "At":
            continue
        qq = getattr(item, "qq", None) or getattr(item, "target", None)
        text = str(qq or "").strip()
        if not text or text.lower() == "all" or not text.lstrip("-").isdigit():
            continue
        if text not in found:
            found.append(text)
    return found


def sender_qq(event: AstrMessageEvent) -> str:
    getter = getattr(event, "get_sender_id", None)
    if callable(getter):
        return str(getter() or "")
    return ""


def group_key(event: AstrMessageEvent) -> str:
    getter = getattr(event, "get_group_id", None)
    if callable(getter):
        gid = str(getter() or "")
        if gid:
            return gid
    obj = getattr(event, "message_obj", None)
    gid = str(getattr(obj, "group_id", "") or "")
    return gid or "private"


def is_admin(event: AstrMessageEvent, context=None) -> bool:
    role = getattr(event, "role", None)
    if role and str(role).lower() in ("admin", "owner"):
        return True
    checker = getattr(event, "is_admin", None)
    if callable(checker):
        try:
            if checker():
                return True
        except TypeError:
            pass
    elif checker:
        return True
    qq = sender_qq(event)
    if not qq or context is None:
        return False
    getter = getattr(context, "get_config", None)
    if not callable(getter):
        return False
    try:
        conf = getter()
        admins = conf.get("admins_id") or conf.get("admins") or []
    except Exception:
        return False
    return qq in {str(x) for x in admins}


def group_card(event: AstrMessageEvent) -> str:
    getter = getattr(event, "get_sender_name", None)
    if callable(getter):
        return str(getter() or "").strip()
    return ""


def speaker_label(event: AstrMessageEvent, store: BuddyStore | None = None) -> str:
    qq = sender_qq(event)
    if store and qq:
        observe(event, store)
        row = store.get_nick(qq)
        if row and row.nick:
            return row.nick
    return group_card(event) or qq


def observe(event: AstrMessageEvent, store: BuddyStore) -> NickRow | None:
    return store.observe_speaker(sender_qq(event), group_card(event))


def attach_llm_text(req, text: str) -> None:
    parts = getattr(req, "extra_user_content_parts", None)
    if isinstance(parts, list):
        try:
            from astrbot.core.agent.message import TextPart

            parts.append(TextPart(text=text))
            return
        except Exception:
            pass
        parts.append(text)
        return
    req.system_prompt = (getattr(req, "system_prompt", None) or "") + "\n" + text


def inject_speaker_prompt(event: AstrMessageEvent, req, store: BuddyStore) -> None:
    qq = sender_qq(event)
    if not qq:
        return
    observe(event, store)
    attach_llm_text(req, f"[发言者]\nQQ: {qq}\n称呼: {speaker_label(event, store)}")


async def handle_nick(event: AstrMessageEvent, store: BuddyStore, context=None):
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    qq = sender_qq(event)
    observe(event, store)

    if not args or args[0].lower() == "me":
        row = store.get_nick(qq) if qq else None
        if not row:
            yield event.plain_result("还没记下你的 QQ")
            return
        yield event.plain_result(f"{row.qq} = {row.nick}")
        return

    if args[0].lower() == "list":
        rows = store.list_nicks()
        if not rows:
            yield event.plain_result("昵称表是空的")
            return
        lines = [f"{r.qq} = {r.nick}" for r in rows]
        yield event.plain_result("QQ 昵称表：\n" + "\n".join(lines))
        return

    if args[0].lower() == "alias":
        async for result in _nick_alias(event, store, context, args[1:]):
            yield result
        return

    if args[0].lower() == "set":
        if not is_admin(event, context):
            yield event.plain_result("只有管理员能改别人的称呼")
            return
        if len(args) < 3:
            yield event.plain_result("用法：/nick set <QQ> <称呼>")
            return
        target, nick = args[1], " ".join(args[2:]).strip()
        store.set_nick(target, nick, manual=True)
        yield event.plain_result(f"{target} = {nick}")
        return

    if not qq:
        yield event.plain_result("拿不到你的 QQ")
        return
    nick = " ".join(args).strip()
    store.set_nick(qq, nick, manual=True)
    yield event.plain_result(f"{qq} = {nick}")


def _resolve_alias_qq(store: BuddyStore, token: str) -> list[str]:
    token = token.strip()
    if token.isdigit():
        return [token]
    return [row.qq for row in store.find_nicks(token)]


def _alias_lines(store: BuddyStore, qq: str) -> list[str]:
    names = [name for _, name in store.list_charter_aliases(qq)]
    label = f"{store.display_name(qq)} ({qq})"
    if not names:
        return [f"{label} 没有做谱人对照"]
    return [f"{label}："] + [f"  {name}" for name in names]


async def _nick_alias(event: AstrMessageEvent, store: BuddyStore, context, args: list[str]):
    if not args or args[0].lower() == "list":
        rest = args[1:] if args else []
        if rest:
            if not is_admin(event, context):
                yield event.plain_result("只有管理员能看别人的对照")
                return
            targets = _resolve_alias_qq(store, rest[0])
            if not targets:
                yield event.plain_result(f"没找到「{rest[0]}」")
                return
            if len(targets) > 1:
                yield event.plain_result("对上多个人，改用 QQ")
                return
            yield event.plain_result("\n".join(_alias_lines(store, targets[0])))
            return
        rows = store.list_charter_aliases()
        if not rows:
            yield event.plain_result("做谱人对照是空的")
            return
        grouped: dict[str, list[str]] = {}
        for qq, charter in rows:
            grouped.setdefault(qq, []).append(charter)
        blocks = []
        for qq, names in grouped.items():
            blocks.append("\n".join(_alias_lines(store, qq)))
        yield event.plain_result("做谱人对照：\n" + "\n".join(blocks))
        return
    if not is_admin(event, context):
        yield event.plain_result("只有管理员能改做谱人对照")
        return
    sub = args[0].lower()
    rest = args[1:]
    if sub == "add":
        if len(rest) < 2:
            yield event.plain_result("用法：/nick alias add <称呼或QQ> <做谱人> [做谱人…]")
            return
        targets = _resolve_alias_qq(store, rest[0])
        names = [x.strip() for x in rest[1:] if x.strip()]
        if not targets:
            yield event.plain_result(f"没找到「{rest[0]}」")
            return
        if len(targets) > 1:
            yield event.plain_result("对上多个人，改用 QQ")
            return
        for name in names:
            store.add_charter_alias(targets[0], name)
        yield event.plain_result("\n".join(_alias_lines(store, targets[0])))
        return
    if sub in ("del", "rm", "remove"):
        if len(rest) < 2:
            yield event.plain_result("用法：/nick alias del <称呼或QQ> <做谱人> [做谱人…]")
            return
        targets = _resolve_alias_qq(store, rest[0])
        names = [x.strip() for x in rest[1:] if x.strip()]
        if not targets:
            yield event.plain_result(f"没找到「{rest[0]}」")
            return
        removed = [name for name in names if store.remove_charter_alias(targets[0], name)]
        if not removed:
            yield event.plain_result("没有这些对照")
            return
        yield event.plain_result("已删 " + "、".join(removed))
        return
    if sub in ("clear", "clr", "wipe"):
        if not rest:
            yield event.plain_result("用法：/nick alias clear <称呼或QQ>")
            return
        targets = _resolve_alias_qq(store, rest[0])
        if not targets:
            yield event.plain_result(f"没找到「{rest[0]}」")
            return
        if len(targets) > 1:
            yield event.plain_result("对上多个人，改用 QQ")
            return
        n = store.clear_charter_aliases(targets[0])
        yield event.plain_result(f"已清 {store.display_name(targets[0])} 的 {n} 条对照")
        return
    yield event.plain_result(
        "用法：\n"
        "/nick alias list [称呼或QQ]\n"
        "/nick alias add <称呼或QQ> <做谱人> [做谱人…]\n"
        "/nick alias del <称呼或QQ> <做谱人> [做谱人…]\n"
        "/nick alias clear <称呼或QQ>"
    )
