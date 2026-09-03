from __future__ import annotations

from pathlib import Path

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from .aliases import AliasStore
from .identity import stop_event
from .messages import has_image_by_isinstance
from .netease import NeteaseCloudMusicAPI
from .ocr import ocr_bytes
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


async def _handle_lai_shou(event: AstrMessageEvent, runtime: SongRuntime):
    songname, local_images = await _lai_shou_query(event)
    if songname is None:
        return

    if not songname:
        stop_event(event)
        result = event.make_result()
        chain = [Image(file=path) for path in local_images]
        chain.append(Plain("未找到歌曲"))
        result.chain = chain
        result.use_t2i(False)
        yield result
        return

    songs = await runtime.netease.fetch_song_data(songname, limit=1, pic=True)
    if not songs:
        stop_event(event)
        text = f"未找到歌曲{songname}" if songname else "未找到歌曲"
        result = event.make_result()
        chain = [Image(file=path) for path in local_images]
        chain.append(Plain(text))
        result.chain = chain
        result.use_t2i(False)
        yield result
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


async def _lai_shou_query(event: AstrMessageEvent) -> tuple[str | None, list[str]]:
    parts: list[str] = []
    images: list[str] = []
    for item in message_chain(event):
        if _is_reply(item):
            continue
        if _is_image(item):
            path = ""
            data = b""
            convert = getattr(item, "convert_to_file_path", None)
            if callable(convert):
                try:
                    path = str(await convert() or "")
                except Exception:
                    path = ""
            if path:
                try:
                    data = Path(path).read_bytes()
                except Exception:
                    data = b""
            if not data:
                data = await _read_component_bytes(item) or b""
                if data:
                    path = _write_temp(data, ".png")
            if path:
                images.append(path)
            parts.append(await ocr_bytes(data) if data else "")
            continue
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
    combined = "".join(parts).strip()
    raw = (event.message_str or "").strip()
    if not combined.startswith("来首") and raw.startswith("来首"):
        rest = raw[2:]
        ocr_bits = "".join(parts)
        combined = "来首" + rest + ocr_bits
    if not combined.startswith("来首") and not raw.startswith("来首"):
        return None, []
    songname = combined[2:].strip() if combined.startswith("来首") else raw[2:].strip()
    if not songname and not images:
        return None, []
    return songname, images


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
