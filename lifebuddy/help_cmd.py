from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from .identity import group_key, is_private_chat, is_public_group
from .settings import Settings

OVERVIEW = (
    "生活好基友\n"
    "/help <指令>  看某一条的用法\n"
    "\n"
    "/ask  /rbdx  /rb  /nick  /dib  /advice  /fight\n"
    "来首XXX  XXX是什么歌"
)

OVERVIEW_PUBLIC = (
    "生活好基友\n"
    "/help <指令>  看某一条的用法\n"
    "\n"
    "/rbdx  /rb bind  /rb user  /rb song"
)

TOPICS: dict[str, str] = {
    "help": (
        "/help  总表\n"
        "/help <指令>  某一条的用法\n"
        "例如 /help rbdx  /help 来首"
    ),
    "help_public": (
        "/help  总表\n"
        "/help <指令>  某一条的用法\n"
        "例如 /help rbdx  /help rb"
    ),
    "ask": (
        "/ask <问题> <选项A> <选项B> …\n"
        "至少两个选项。至于怎么算的，不问为好。\n"
        "每天结果会变；问「宇宙洪荒」有惊喜"
    ),
    "rbdx": (
        "/rbdx  随机一首自制谱\n"
        "/rbdx 12  指定等级"
    ),
    "rbdx_admin": (
        "/rbdx  随机一首自制谱\n"
        "/rbdx 12  指定等级\n"
        "/rbdx arcade  /rbdx test  /rbdx test_all  /rbdx 英国人\n"
        "/rbdx arcade ryu  随机带 ryu 的街机谱，可再加等级\n"
        "test / test_all / 英国人 要在管理页填 wip_group_ids"
    ),
    "rb": (
        "/rb bind  群里不能绑，请私聊机器人\n"
        "/rb who  看自己绑的号\n"
        "/rb who <昵称/QQ/@>  查别人绑的号\n"
        "/rb user <用户名或四位ID>  查 SKP / 总 PC\n"
        "/rb recent  最近一局（也可 /rb r）\n"
        "/rb unbind [QQ或用户名]  仅管理员\n"
        "/rb song <关键词>  只搜自制谱\n"
        "  只中一首时带夹克；超过 20 首不列\n"
        "/rb alias list\n"
        "/rb alias add <别名> <SongID或图片URL>\n"
        "/rb alias del <别名>  仅管理员"
    ),
    "rb_admin": (
        "/rb bind <用户ID或用户名>  管理群可直接绑，一对一不能自己换\n"
        "/rb who  看自己绑的号\n"
        "/rb who <昵称/QQ/@>  查别人绑的号\n"
        "/rb user <用户名或四位ID>  查 SKP / 总 PC\n"
        "/rb recent  最近一局（也可 /rb r）\n"
        "/rb unbind [QQ或用户名]  仅管理员\n"
        "/rb song [custom|arcade|test|test_all] <关键词>\n"
        "  默认搜自制+街机；开了内测群再加内测和英国人谱面\n"
        "  只中一首时带夹克；超过 20 首不列\n"
        "/rb alias list\n"
        "/rb alias add <别名> <SongID或图片URL>\n"
        "/rb alias del <别名>  仅管理员"
    ),
    "rb_private": (
        "/rb bind <用户ID或用户名> <密码>  一对一，绑过不能自己换\n"
        "/rb who  看自己绑的号\n"
        "/rb user <用户名或四位ID>  查 SKP / 总 PC\n"
        "/rb recent  最近一局（也可 /rb r）\n"
        "/rb song <关键词>  只搜自制谱"
    ),
    "rb_public": (
        "/rb bind  群里不能绑，请私聊机器人\n"
        "/rb user <用户名或四位ID>  查 SKP / 总 PC\n"
        "/rb song <关键词>  只搜自制谱\n"
        "  只中一首时带夹克；超过 20 首不列"
    ),
    "nick": (
        "/nick 上帝  给自己设称呼\n"
        "/nick list  看本群称呼\n"
        "/nick set <QQ> 上帝  管理员改别人\n"
        "/nick alias add <称呼或QQ> <做谱人> [做谱人…]  管理员对齐，可多条\n"
        "/nick alias list [称呼或QQ]  看对照\n"
        "/nick alias clear <称呼或QQ>  清掉某人全部对照"
    ),
    "dib": (
        "/dib  看自己口香了几天\n"
        "/dib <曲名或SongID>  口香（占了不能吐，别人不能抢）\n"
        "/dib list  本群口香列表\n"
        "/dib del <QQ或曲名>  管理员删除"
    ),
    "advice": (
        "/advice  审核列表\n"
        "/advice <编号或SongID>  看评\n"
        "/advice <编号或SongID> <0|1> [正文]  写评\n"
        "1/ok 可空评；0/ng 必须写评\n"
        "要在管理页把群号填进 advice_group_ids，并先 /rb bind"
    ),
    "fight": (
        "/fight  要打的谱面列表（按谱面编号，不是按歌）\n"
        "/fight <编号> <展示值>  投票\n"
        "先 /rb bind"
    ),
    "来首": (
        "来首XXX  搜网易云；带图直接回未找到，原图留在原位置"
    ),
    "是什么歌": (
        "XXX是什么歌  查群梗别名\n"
        "有自制谱 SongID 的回夹克；remywiki 先试抓图，失败再回链接\n"
        "别名用 /rb alias add 加"
    ),
}

ALIASES = {
    "help": "help",
    "帮助": "help",
    "ask": "ask",
    "rbdx": "rbdx",
    "rb": "rb",
    "bind": "rb",
    "绑号": "rb",
    "song": "rb",
    "alias": "rb",
    "别名": "rb",
    "nick": "nick",
    "称呼": "nick",
    "dib": "dib",
    "口香": "dib",
    "占坑": "dib",
    "advice": "advice",
    "审核": "advice",
    "fight": "fight",
    "打架": "fight",
    "来首": "来首",
    "是什么歌": "是什么歌",
    "laishou": "来首",
}

PUBLIC_TOPIC_KEYS = frozenset({"help", "rbdx", "rb"})


def _normalize(token: str) -> str:
    raw = (token or "").strip().lower()
    raw = raw.lstrip("/")
    return ALIASES.get(raw, raw)


def _topic_key(args: list[str]) -> str | None:
    joined = " ".join(args).strip()
    compact = "".join(args)
    if "是什么歌" in compact:
        return "是什么歌"
    if compact.startswith("来首"):
        return "来首"
    key = _normalize(joined)
    if key in TOPICS:
        return key
    first = _normalize(args[0]) if args else ""
    if first in TOPICS:
        return first
    return None


async def handle_help(event: AstrMessageEvent, settings: Settings | None = None):
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    public = bool(settings and is_public_group(event, settings))
    overview = OVERVIEW_PUBLIC if public else OVERVIEW
    if not args:
        yield event.plain_result(overview)
        return
    key = _topic_key(args)
    if public:
        if key not in PUBLIC_TOPIC_KEYS:
            yield event.plain_result(f"没有「{' '.join(args)}」这条。\n{overview}")
            return
        if key == "help":
            key = "help_public"
        elif key == "rb":
            key = "rb_public"
        # rbdx stays public-facing docs
    elif key == "rb":
        if is_private_chat(event):
            key = "rb_private"
        elif settings and settings.allow_restricted(group_key(event)):
            key = "rb_admin"
    elif key == "rbdx" and settings and settings.allow_restricted(group_key(event)):
        key = "rbdx_admin"
    text = TOPICS.get(key or "")
    if text:
        yield event.plain_result(text)
        return
    yield event.plain_result(f"没有「{' '.join(args)}」这条。\n{overview}")
