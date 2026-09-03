from __future__ import annotations

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from .aliases import AliasStore
from .identity import stop_event
from .messages import has_image_by_isinstance
from .netease import NeteaseCloudMusicAPI
from .rbdx import RbdxAPI
from .settings import Settings
from .symmetry import _is_image, _is_reply, _read_component_bytes, _write_temp, message_chain


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


async def _image_path(item: object) -> str:
    convert = getattr(item, "convert_to_file_path", None)
    if callable(convert):
        try:
            path = str(await convert() or "")
            if path:
                return path
        except Exception:
            pass
    data = await _read_component_bytes(item) or b""
    if data:
        return _write_temp(data, ".png")
    return ""


async def _not_found_with_original(event: AstrMessageEvent, songname: str):
    replaced = False
    chain: list = []
    for item in message_chain(event):
        if _is_reply(item):
            continue
        if _is_image(item):
            path = await _image_path(item)
            if path:
                chain.append(Image(file=path))
            continue
        text = str(getattr(item, "text", None) or "")
        if not text:
            continue
        if not replaced and "来首" in text:
            text = text.replace("来首", "未找到歌曲", 1)
            replaced = True
        if text:
            chain.append(Plain(text))
    if not replaced:
        prefix = f"未找到歌曲{songname}" if songname else "未找到歌曲"
        chain.insert(0, Plain(prefix))
    result = event.make_result()
    result.chain = chain or [Plain("未找到歌曲")]
    result.use_t2i(False)
    return result


async def _handle_lai_shou(event: AstrMessageEvent, runtime: SongRuntime):
    has_image = any(_is_image(item) for item in message_chain(event) if not _is_reply(item))
    songname = (event.message_str or "")[2:].strip()
    if has_image:
        stop_event(event)
        yield await _not_found_with_original(event, songname)
        return
    if not songname:
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
    if not matches:
        stop_event(event)
        yield event.plain_result(f"未找到别名为“{songname}”的歌")
        return
    stop_event(event)
    for entry in matches:
        try:
            yield _alias_result(event, await _alias_image(runtime, entry), entry)
        except Exception:
            yield event.plain_result(f"您要找的是不是：{entry.alias}")


async def _alias_image(runtime: SongRuntime, entry) -> str:
    url = (entry.image or "").strip()
    if not url:
        return ""
    return await runtime.rbdx.image_file(url, external=True)


def _alias_result(event: AstrMessageEvent, image: str, entry):
    text = f"您要找的是不是：{entry.alias}"
    if image and not image.startswith("http"):
        result = event.make_result()
        result.chain = [Plain(text), Image(file=image)]
        result.use_t2i(False)
        return result
    if (entry.image or "").startswith("http"):
        text = f"{text}\n{entry.image}"
    return event.plain_result(text)
