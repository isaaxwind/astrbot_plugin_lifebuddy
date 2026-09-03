from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

OVERVIEW = (
    "生活好基友\n"
    "/help <指令>  看某一条的用法\n"
    "\n"
    "/ask  /rbdx  /rb  /nick  /dib  /advice  /fight\n"
    "/左对称  /倒放\n"
    "来首XXX  XXX是什么歌"
)

TOPICS: dict[str, str] = {
    "help": (
        "/help  总表\n"
        "/help <指令>  某一条的用法\n"
        "例如 /help rbdx  /help 来首"
    ),
    "ask": (
        "/ask <问题> <选项A> <选项B> …\n"
        "至少两个选项。至于怎么算的，不问为好。"
    ),
    "对称": (
        "回复一张图后发：\n"
        "/左对称  /右对称  /上对称  /下对称\n"
        "左对称 = 左半边原样，右半边是左半边的镜像。其余方向同理。\n"
        "动图会对每一帧做一次。\n"
        "/倒放  动图倒着播。\n"
        "单独发指令（不回图）就是对你头像下手。"
    ),
    "倒放": (
        "回复一张动图后发 /倒放，帧序倒过来。\n"
        "单独发就是对你头像下手，但头像一般不是动图。"
    ),
    "rbdx": (
        "/rbdx  随机一首自制谱\n"
        "/rbdx 12  指定等级\n"
        "/rbdx arcade  /rbdx test  /rbdx test_all  /rbdx 英国人\n"
        "/rbdx arcade ryu  随机带 ryu 的街机谱，可再加等级\n"
        "test / test_all / 英国人 要在管理页填 wip_group_ids"
    ),
    "rb": (
        "/rb bind <四位用户ID>  绑号，须唯一\n"
        "/rb who  看自己绑的号\n"
        "/rb unbind [QQ或用户名]  仅管理员\n"
        "/rb song [custom|arcade|test|test_all] <关键词>\n"
        "  默认搜自制+街机；开了内测群再加内测和英国人谱面\n"
        "  只中一首时带夹克\n"
        "/rb alias list\n"
        "/rb alias add <别名> <SongID或图片URL>\n"
        "/rb alias del <别名>  仅管理员"
    ),
    "nick": (
        "/nick 上帝  给自己设称呼\n"
        "/nick list  看本群称呼\n"
        "/nick set <QQ> 上帝  管理员改别人"
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
        "来首XXX  先搜自制谱，没有再回网易云\n"
        "回夹克 + 曲名 / 艺术家 / 等级或专辑链接"
    ),
    "是什么歌": (
        "XXX是什么歌  查群梗别名，回夹克\n"
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
    "对称": "对称",
    "左对称": "对称",
    "右对称": "对称",
    "上对称": "对称",
    "下对称": "对称",
    "对称左": "对称",
    "对称右": "对称",
    "对称上": "对称",
    "对称下": "对称",
    "倒放": "倒放",
}


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


async def handle_help(event: AstrMessageEvent):
    parts = event.message_str.split()
    args = parts[1:] if parts else []
    if not args:
        yield event.plain_result(OVERVIEW)
        return
    key = _topic_key(args)
    text = TOPICS.get(key or "")
    if text:
        yield event.plain_result(text)
        return
    yield event.plain_result(f"没有「{' '.join(args)}」这条。\n{OVERVIEW}")
