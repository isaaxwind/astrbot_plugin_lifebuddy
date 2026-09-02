from __future__ import annotations

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from .aliases import AliasStore
from .identity import stop_event
from .messages import has_image_by_classname, has_image_by_isinstance
from .netease import NeteaseCloudMusicAPI
from .rbdx import RbdxAPI
from .settings import Settings


class SongRuntime:
    def __init__(
        self,
        aliases: AliasStore,
        netease: NeteaseCloudMusicAPI,
        rbdx: RbdxAPI,
        settings: Settings,
    ):
        self.aliases = aliases
        self.netease = netease
        self.rbdx = rbdx
        self.settings = settings


async def handle_natural_song(event: AstrMessageEvent, runtime: SongRuntime):
    msg_str = event.message_str
    if msg_str.startswith("来首") and len(msg_str) >= 2:
        async for result in _handle_lai_shou(event, runtime):
            yield result
        return
    if msg_str.endswith("是什么歌") and len(msg_str) >= 4:
        async for result in _handle_what_song(event, runtime):
            yield result


async def _handle_lai_shou(event: AstrMessageEvent, runtime: SongRuntime):
    if has_image_by_classname(event):
        stop_event(event)
        yield event.plain_result("我暂时发不了图片，操你妈的")
        return

    msg_str = event.message_str
    if len(msg_str) <= 2:
        return

    songname = msg_str[2:].strip()
    try:
        rbdx_hits = await runtime.rbdx.search_published(songname, limit=1)
    except Exception:
        rbdx_hits = []
    if rbdx_hits:
        song = rbdx_hits[0]
        image = await runtime.rbdx.image_file(runtime.rbdx.jacket_url(int(song["id"])))
        result = event.make_result()
        if image and not image.startswith("http"):
            result.chain = [Image(file=image), Plain(runtime.rbdx.format_song_text(song))]
        else:
            result.chain = [Plain(runtime.rbdx.format_song_text(song))]
        result.use_t2i(False)
        stop_event(event)
        yield result
        return

    if not runtime.settings.netease_fallback:
        stop_event(event)
        yield event.plain_result(f"未找到歌曲{songname}")
        return

    songs = await runtime.netease.fetch_song_data(songname, limit=1, pic=True)
    if not songs:
        stop_event(event)
        yield event.plain_result(f"未找到歌曲{songname}")
        return

    song = songs[0]
    song_id = song["id"]
    song_artist = ", ".join(song["artists"])
    song_album = song.get("album", "神秘未知专辑")
    album_img1v1Url = song["album_img1v1Url"]
    song_name = song["name"]
    song_link = f"https://music.163.com/#/song?id={song_id}"
    result = event.make_result()
    result.chain = [
        Image(file=album_img1v1Url),
        Plain(f"{song_name}\n{song_artist}\nfrom 《{song_album}》\n{song_link}"),
    ]
    result.use_t2i(False)
    stop_event(event)
    yield result


async def _handle_what_song(event: AstrMessageEvent, runtime: SongRuntime):
    if has_image_by_isinstance(event):
        stop_event(event)
        yield event.plain_result("图片可判断不了，另请高明吧")
        return

    msg_str = event.message_str
    if len(msg_str) <= 4:
        return

    songname = msg_str.split("是什么歌")[0]
    matches = runtime.aliases.find(songname)
    try:
        if not matches:
            stop_event(event)
            yield event.plain_result(f"未找到别名为“{songname}”的歌")
            return
        stop_event(event)
        for entry in matches:
            image = await runtime.rbdx.image_file(entry.image)
            result = event.make_result()
            result.chain = [
                Plain("您要找的是不是："),
                Image(file=image),
            ]
            result.use_t2i(False)
            yield result
    except Exception as e:
        stop_event(event)
        yield event.plain_result("出错了，傻逼！")
        yield event.plain_result(f"{e}")
