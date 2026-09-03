from __future__ import annotations

import asyncio
import io
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiohttp
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image
from PIL import Image as PILImage
from PIL import ImageSequence

from .identity import sender_qq
from .image_cache import ImageCache

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_GIF_FRAMES = 80
HTTP_UA = "Mozilla/5.0 (compatible; lifebuddy/1.0)"

def _is_image(item: object) -> bool:
    return type(item).__name__ == "Image" or isinstance(item, Image)


def _is_reply(item: object) -> bool:
    return type(item).__name__ == "Reply"


def message_chain(event: AstrMessageEvent) -> list[Any]:
    getter = getattr(event, "get_messages", None)
    if callable(getter):
        try:
            chain = getter()
            if chain:
                return list(chain)
        except Exception:
            pass
    obj = getattr(event, "message_obj", None)
    return list(getattr(obj, "message", None) or [])


def event_message_id(event: AstrMessageEvent) -> str:
    obj = getattr(event, "message_obj", None)
    if obj is None:
        return ""
    for key in ("message_id", "message_seq"):
        value = getattr(obj, key, None)
        if value not in (None, "", 0):
            return str(value)
    return ""


def reply_message_id(event: AstrMessageEvent) -> str:
    for item in message_chain(event):
        if _is_reply(item):
            value = getattr(item, "id", None)
            if value not in (None, "", 0):
                return str(value)
    obj = getattr(event, "message_obj", None)
    raw = getattr(obj, "raw_message", None) if obj is not None else None
    segments = None
    if isinstance(raw, dict):
        segments = raw.get("message")
    else:
        segments = getattr(raw, "message", None)
    if isinstance(segments, list):
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            if str(seg.get("type") or "") != "reply":
                continue
            data = seg.get("data") or {}
            value = data.get("id") if isinstance(data, dict) else None
            if value not in (None, "", 0):
                return str(value)
    return ""


def _looks_like_image(data: bytes) -> bool:
    if not data or len(data) < 8:
        return False
    return data.startswith(
        (b"\x89PNG", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF")
    )


async def _read_component_bytes(image: object) -> bytes | None:
    convert = getattr(image, "convert_to_file_path", None)
    if callable(convert):
        try:
            path = await convert()
            if path:
                data = Path(path).read_bytes()
                if _looks_like_image(data):
                    return data
        except Exception:
            pass
    for attr in ("url", "file", "path"):
        value = getattr(image, attr, None)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            data = await _download(value)
            if data:
                return data
        if isinstance(value, str) and value and not value.startswith(("http", "base64://")):
            path = Path(value.removeprefix("file:///"))
            if path.is_file():
                data = path.read_bytes()
                if _looks_like_image(data):
                    return data
    return None


async def _download(url: str) -> bytes | None:
    if not url.startswith(("http://", "https://")):
        return None
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"User-Agent": HTTP_UA, "Accept": "image/*"},
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
    except Exception:
        return None
    if len(data) > MAX_INPUT_BYTES or not _looks_like_image(data):
        return None
    return data


def _avatar_url(event: AstrMessageEvent) -> str | None:
    qq = sender_qq(event)
    if not qq.isdigit():
        return None
    return f"https://q1.qlogo.cn/g?b=qq&nk={qq}&s=640"


async def _call_get_msg(event: AstrMessageEvent, reply_id: str) -> Any:
    bot = getattr(event, "bot", None)
    if bot is None:
        return None
    callers = [
        getattr(bot, "call_action", None),
        getattr(getattr(bot, "api", None), "call_action", None),
    ]
    for call in callers:
        if not callable(call):
            continue
        for message_id in (reply_id,):
            try:
                return await call("get_msg", message_id=message_id)
            except Exception:
                try:
                    return await call("get_msg", message_id=int(message_id))
                except Exception:
                    continue
    return None


def _urls_from_get_msg(payload: Any) -> list[str]:
    data = payload
    if isinstance(payload, dict) and "message" not in payload:
        data = payload.get("data") or payload
    segments = None
    if isinstance(data, dict):
        segments = data.get("message") or data.get("message_list")
    elif isinstance(data, list):
        segments = data
    if not isinstance(segments, list):
        return []
    urls: list[str] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        if str(seg.get("type") or "") not in ("image", "img", "mface"):
            continue
        body = seg.get("data") or {}
        if not isinstance(body, dict):
            continue
        for key in ("url", "file"):
            value = body.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(value)
    return urls


async def ingest_event_image(event: AstrMessageEvent, cache: ImageCache) -> None:
    mid = event_message_id(event)
    if not mid:
        return
    for item in message_chain(event):
        if not _is_image(item):
            continue
        data = await _read_component_bytes(item)
        if data:
            cache.put(mid, data)
        return


async def resolve_image_bytes(event: AstrMessageEvent, cache: ImageCache) -> bytes | None:
    for item in message_chain(event):
        if _is_image(item):
            data = await _read_component_bytes(item)
            if data:
                return data
        if _is_reply(item):
            nested = getattr(item, "chain", None) or []
            for sub in nested:
                if _is_image(sub):
                    data = await _read_component_bytes(sub)
                    if data:
                        return data
    reply_id = reply_message_id(event)
    if reply_id:
        cached = cache.get(reply_id)
        if cached:
            return cached
        payload = await _call_get_msg(event, reply_id)
        for url in _urls_from_get_msg(payload):
            data = await _download(url)
            if data:
                cache.put(reply_id, data)
                return data
    if reply_id:
        return None
    url = _avatar_url(event)
    if url:
        return await _download(url)
    return None


def _mirror_left(img: PILImage.Image) -> PILImage.Image:
    w, h = img.size
    keep_w = max(1, (w + 1) // 2)
    keep = img.crop((0, 0, keep_w, h))
    mirror = keep.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
    out = PILImage.new("RGBA", (w, h))
    out.paste(keep, (0, 0))
    out.paste(mirror, (w - keep_w, 0))
    return out


def _mirror_right(img: PILImage.Image) -> PILImage.Image:
    w, h = img.size
    keep_w = max(1, (w + 1) // 2)
    keep = img.crop((w - keep_w, 0, w, h))
    mirror = keep.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
    out = PILImage.new("RGBA", (w, h))
    out.paste(mirror, (0, 0))
    out.paste(keep, (w - keep_w, 0))
    return out


def _mirror_top(img: PILImage.Image) -> PILImage.Image:
    w, h = img.size
    keep_h = max(1, (h + 1) // 2)
    keep = img.crop((0, 0, w, keep_h))
    mirror = keep.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    out = PILImage.new("RGBA", (w, h))
    out.paste(keep, (0, 0))
    out.paste(mirror, (0, h - keep_h))
    return out


def _mirror_bottom(img: PILImage.Image) -> PILImage.Image:
    w, h = img.size
    keep_h = max(1, (h + 1) // 2)
    keep = img.crop((0, h - keep_h, w, h))
    mirror = keep.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    out = PILImage.new("RGBA", (w, h))
    out.paste(mirror, (0, 0))
    out.paste(keep, (0, h - keep_h))
    return out


_MIRROR = {
    "left": _mirror_left,
    "right": _mirror_right,
    "top": _mirror_top,
    "bottom": _mirror_bottom,
}


def _load_frames(data: bytes) -> tuple[list[PILImage.Image], list[int], bool, int]:
    src = PILImage.open(io.BytesIO(data))
    w, h = src.size
    if w * h > MAX_PIXELS:
        raise ValueError("图太大了")
    animated = bool(getattr(src, "is_animated", False)) and (src.format or "").upper() == "GIF"
    n_frames = int(getattr(src, "n_frames", 1) or 1)
    if animated and n_frames > MAX_GIF_FRAMES:
        raise ValueError("动图帧数太多")
    frames: list[PILImage.Image] = []
    durations: list[int] = []
    if animated:
        for frame in ImageSequence.Iterator(src):
            frames.append(frame.convert("RGBA"))
            durations.append(max(20, int(frame.info.get("duration") or 100)))
    else:
        frames.append(src.convert("RGBA"))
        durations.append(100)
    loop = int(src.info.get("loop", 0) or 0)
    src.close()
    return frames, durations, animated, loop


def _save_gif(frames: list[PILImage.Image], durations: list[int], loop: int) -> bytes:
    out = io.BytesIO()
    first, *rest = frames
    first.save(
        out,
        format="GIF",
        save_all=True,
        append_images=rest,
        duration=durations,
        loop=loop,
        disposal=2,
        optimize=False,
    )
    return out.getvalue()


def _save_png(img: PILImage.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def process_image(data: bytes, action: str) -> tuple[bytes, str]:
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("图太大了")
    frames, durations, animated, loop = _load_frames(data)
    if action == "reverse":
        if not animated:
            raise ValueError("这不是动图")
        frames.reverse()
        durations.reverse()
        return _save_gif(frames, durations, loop), ".gif"
    fn = _MIRROR[action]
    processed = [fn(frame) for frame in frames]
    if animated:
        return _save_gif(processed, durations, loop), ".gif"
    return _save_png(processed[0]), ".png"


def _write_temp(data: bytes, suffix: str) -> str:
    path = Path(tempfile.gettempdir()) / f"lifebuddy_sym_{uuid4().hex}{suffix}"
    path.write_bytes(data)
    return str(path)


async def handle_symmetry(event: AstrMessageEvent, cache: ImageCache, action: str):
    try:
        raw = await resolve_image_bytes(event, cache)
    except Exception:
        raw = None
    if not raw:
        if reply_message_id(event):
            yield event.plain_result("这张图我没存到")
            return
        yield event.plain_result("头像拿不到")
        return
    try:
        out, suffix = await asyncio.to_thread(process_image, raw, action)
    except ValueError as exc:
        yield event.plain_result(str(exc))
        return
    except Exception:
        yield event.plain_result("图没做成")
        return
    path = _write_temp(out, suffix)
    result = event.make_result()
    result.chain = [Image(file=path)]
    result.use_t2i(False)
    yield result
