from __future__ import annotations

import asyncio
import io
import shutil
import subprocess
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

try:
    from astrbot.api.message_components import Video as VideoComp
except Exception:
    VideoComp = None  # type: ignore

HTTP_UA = "Mozilla/5.0 (compatible; lifebuddy/1.0)"
_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp", ".m4v"}
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _is_image(item: object) -> bool:
    return type(item).__name__ == "Image" or isinstance(item, Image)


def _is_video(item: object) -> bool:
    name = type(item).__name__
    if name.lower() in {"video", "shortvideo", "short_video"}:
        return True
    if VideoComp is not None and isinstance(item, VideoComp):
        return True
    if name == "File":
        raw = str(getattr(item, "name", None) or getattr(item, "file", None) or "")
        return Path(raw.split("?")[0]).suffix.lower() in _VIDEO_EXT
    return False


def _is_media(item: object) -> bool:
    return _is_image(item) or _is_video(item)


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


def event_message_ids(event: AstrMessageEvent) -> list[str]:
    found: list[str] = []
    obj = getattr(event, "message_obj", None)
    if obj is not None:
        for key in ("message_id", "message_seq", "id"):
            value = getattr(obj, key, None)
            if value not in (None, "", 0):
                text = str(value)
                if text not in found:
                    found.append(text)
        raw = getattr(obj, "raw_message", None)
        if isinstance(raw, dict):
            for key in ("message_id", "message_seq", "id"):
                value = raw.get(key)
                if value not in (None, "", 0):
                    text = str(value)
                    if text not in found:
                        found.append(text)
    return found


def reply_message_ids(event: AstrMessageEvent) -> list[str]:
    found: list[str] = []

    def add(value) -> None:
        if value not in (None, "", 0):
            text = str(value)
            if text not in found:
                found.append(text)

    for item in message_chain(event):
        if not _is_reply(item):
            continue
        add(getattr(item, "id", None))
        add(getattr(item, "message_id", None))
        add(getattr(item, "message_seq", None))
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
            if isinstance(data, dict):
                add(data.get("id"))
                add(data.get("message_id"))
                add(data.get("message_seq"))
    return found


def reply_message_id(event: AstrMessageEvent) -> str:
    ids = reply_message_ids(event)
    return ids[0] if ids else ""


def sniff_media(data: bytes) -> str:
    if not data or len(data) < 8:
        return ""
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith((b"\x89PNG", b"\xff\xd8\xff")):
        return "image"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image"
    if data.startswith(b"RIFF") and b"AVI" in data[:16]:
        return "video"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "video"
    return ""


def sniff_file(path: str | Path) -> str:
    try:
        with Path(path).open("rb") as fh:
            kind = sniff_media(fh.read(32))
        if kind:
            return kind
    except OSError:
        return ""
    suffix = Path(path).suffix.lower()
    if suffix in _VIDEO_EXT:
        return "video"
    if suffix == ".gif":
        return "gif"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return "image"
    return ""


def _looks_like_image(data: bytes) -> bool:
    return sniff_media(data) in ("image", "gif")


def _looks_like_media(data: bytes) -> bool:
    return sniff_media(data) in ("image", "gif", "video")


def _ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or ""


def _open_local_ref(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw or raw.startswith(("http://", "https://", "base64://")):
        return None
    candidates = [Path(raw)]
    if raw.startswith("file://"):
        stripped = raw[7:]
        if stripped.startswith("/") and len(stripped) >= 3 and stripped[2] == ":":
            stripped = stripped[1:]
        candidates.append(Path(stripped))
        candidates.append(Path(raw.replace("file:///", "").replace("file://", "")))
    for path in candidates:
        try:
            if path.is_file():
                return str(path)
        except OSError:
            continue
    return None


async def _read_component_path(item: object) -> str | None:
    convert = getattr(item, "convert_to_file_path", None)
    if callable(convert):
        try:
            path = await convert()
            if path and Path(path).is_file():
                return str(Path(path))
        except Exception:
            pass
    for attr in ("url", "file", "path"):
        value = getattr(item, attr, None)
        if not isinstance(value, str) or not value:
            continue
        if value.startswith(("http://", "https://")):
            path = await _download_file(value)
            if path:
                return path
        local = _open_local_ref(value)
        if local:
            return local
    return None


async def _read_component_bytes(image: object) -> bytes | None:
    path = await _read_component_path(image)
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if _looks_like_image(data):
        return data
    return None


async def _download_file(url: str) -> str | None:
    if not url.startswith(("http://", "https://")):
        return None
    dest = Path(tempfile.gettempdir()) / f"lifebuddy_dl_{uuid4().hex}"
    timeout = aiohttp.ClientTimeout(total=180, sock_connect=20)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"User-Agent": HTTP_UA, "Accept": "*/*"},
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    return None
                with dest.open("wb") as fh:
                    async for chunk in resp.content.iter_chunked(256 * 1024):
                        fh.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        return None
    if not dest.is_file() or dest.stat().st_size < 8:
        dest.unlink(missing_ok=True)
        return None
    if not sniff_file(dest):
        dest.unlink(missing_ok=True)
        return None
    return str(dest)


async def _download(url: str) -> bytes | None:
    path = await _download_file(url)
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if not _looks_like_image(data):
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
        try:
            return await call("get_msg", message_id=reply_id)
        except Exception:
            try:
                return await call("get_msg", message_id=int(reply_id))
            except Exception:
                continue
    return None


def _urls_from_get_msg(payload: Any) -> list[str]:
    return [ref for kind, ref in _media_refs_from_get_msg(payload) if kind == "url"]


def _media_refs_from_get_msg(payload: Any) -> list[tuple[str, str]]:
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
    refs: list[tuple[str, str]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        kind = str(seg.get("type") or "").lower()
        if kind not in ("image", "img", "mface", "video", "shortvideo", "short_video", "file"):
            continue
        body = seg.get("data") or {}
        if not isinstance(body, dict):
            continue
        if kind == "file":
            name = str(body.get("name") or body.get("file") or "")
            if Path(name.split("?")[0]).suffix.lower() not in _VIDEO_EXT | {".gif", ".png", ".jpg", ".jpeg", ".webp"}:
                continue
        for key in ("url", "file", "path"):
            value = body.get(key)
            if not isinstance(value, str) or not value:
                continue
            if value.startswith(("http://", "https://")):
                refs.append(("url", value))
            local = _open_local_ref(value)
            if local:
                refs.append(("file", local))
    return refs


async def _call_get_file(event: AstrMessageEvent, file_id: str) -> str | None:
    bot = getattr(event, "bot", None)
    if bot is None or not file_id:
        return None
    callers = [
        getattr(bot, "call_action", None),
        getattr(getattr(bot, "api", None), "call_action", None),
    ]
    payload = None
    for call in callers:
        if not callable(call):
            continue
        try:
            payload = await call("get_file", file_id=file_id)
            break
        except Exception:
            continue
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("file", "path", "url"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return await _download_file(value)
        local = _open_local_ref(str(value or ""))
        if local:
            return local
    return None


def _file_ids_from_get_msg(payload: Any) -> list[str]:
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
    ids: list[str] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        kind = str(seg.get("type") or "").lower()
        if kind not in ("video", "shortvideo", "short_video", "file", "image", "img"):
            continue
        body = seg.get("data") or {}
        if not isinstance(body, dict):
            continue
        for key in ("file_id", "fileId"):
            value = body.get(key)
            if isinstance(value, str) and value and value not in ids:
                ids.append(value)
        file_val = body.get("file")
        if isinstance(file_val, str) and file_val and not file_val.startswith(("http://", "https://", "file://", "/")):
            if file_val not in ids:
                ids.append(file_val)
    return ids


async def _media_from_get_msg(event: AstrMessageEvent, msg_id: str) -> str | None:
    payload = await _call_get_msg(event, msg_id)
    for kind, ref in _media_refs_from_get_msg(payload):
        if kind == "file":
            return ref
        path = await _download_file(ref)
        if path:
            return path
    for file_id in _file_ids_from_get_msg(payload):
        path = await _call_get_file(event, file_id)
        if path:
            return path
    return None


def _cache_put(cache: ImageCache, path: str, ids: list[str]) -> None:
    for mid in ids:
        if mid:
            cache.put_file(mid, path)


async def ingest_event_image(event: AstrMessageEvent, cache: ImageCache) -> None:
    ids = event_message_ids(event)
    path = None
    for item in message_chain(event):
        if not _is_media(item):
            continue
        path = await _read_component_path(item)
        if path:
            break
    if not path:
        for mid in ids:
            path = await _media_from_get_msg(event, mid)
            if path:
                break
    if path:
        _cache_put(cache, path, ids)


async def resolve_media_path(event: AstrMessageEvent, cache: ImageCache) -> str | None:
    for item in message_chain(event):
        if _is_media(item):
            path = await _read_component_path(item)
            if path:
                return path
        if _is_reply(item):
            nested = getattr(item, "chain", None) or []
            for sub in nested:
                if _is_media(sub):
                    path = await _read_component_path(sub)
                    if path:
                        return path
    reply_ids = reply_message_ids(event)
    if reply_ids:
        for reply_id in reply_ids:
            cached = cache.get_path(reply_id)
            if cached:
                return str(cached)
        for reply_id in reply_ids:
            path = await _media_from_get_msg(event, reply_id)
            if path:
                _cache_put(cache, path, reply_ids)
                return path
        return None
    url = _avatar_url(event)
    if url:
        return await _download_file(url)
    return None


async def resolve_image_bytes(event: AstrMessageEvent, cache: ImageCache) -> bytes | None:
    path = await resolve_media_path(event, cache)
    if not path:
        return None
    kind = sniff_file(path)
    if kind == "video":
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return data if _looks_like_image(data) else None


def _keep_size(total: int, ratio: int) -> int:
    return max(1, total * max(0, min(100, ratio)) // 100)


def parse_symmetry_ratio(event: AstrMessageEvent) -> int:
    for token in (event.message_str or "").split()[1:]:
        if token.isdigit():
            value = int(token)
            if 0 <= value <= 100:
                return value
    return 50


def _mirror_left(img: PILImage.Image, ratio: int = 50) -> PILImage.Image:
    w, h = img.size
    keep_w = _keep_size(w, ratio)
    keep = img.crop((0, 0, keep_w, h))
    mirror = keep.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
    out = PILImage.new("RGBA", (keep_w * 2, h))
    out.paste(keep, (0, 0))
    out.paste(mirror, (keep_w, 0))
    return out


def _mirror_right(img: PILImage.Image, ratio: int = 50) -> PILImage.Image:
    w, h = img.size
    keep_w = _keep_size(w, ratio)
    keep = img.crop((w - keep_w, 0, w, h))
    mirror = keep.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
    out = PILImage.new("RGBA", (keep_w * 2, h))
    out.paste(mirror, (0, 0))
    out.paste(keep, (keep_w, 0))
    return out


def _mirror_top(img: PILImage.Image, ratio: int = 50) -> PILImage.Image:
    w, h = img.size
    keep_h = _keep_size(h, ratio)
    keep = img.crop((0, 0, w, keep_h))
    mirror = keep.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    out = PILImage.new("RGBA", (w, keep_h * 2))
    out.paste(keep, (0, 0))
    out.paste(mirror, (0, keep_h))
    return out


def _mirror_bottom(img: PILImage.Image, ratio: int = 50) -> PILImage.Image:
    w, h = img.size
    keep_h = _keep_size(h, ratio)
    keep = img.crop((0, h - keep_h, w, h))
    mirror = keep.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    out = PILImage.new("RGBA", (w, keep_h * 2))
    out.paste(mirror, (0, 0))
    out.paste(keep, (0, keep_h))
    return out


_MIRROR = {
    "left": _mirror_left,
    "right": _mirror_right,
    "top": _mirror_top,
    "bottom": _mirror_bottom,
}


def _load_frames(data: bytes) -> tuple[list[PILImage.Image], list[int], bool, int]:
    src = PILImage.open(io.BytesIO(data))
    animated = bool(getattr(src, "is_animated", False)) and (src.format or "").upper() == "GIF"
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


def process_image(data: bytes, action: str, ratio: int = 50) -> tuple[bytes, str]:
    ratio = max(0, min(100, int(ratio)))
    frames, durations, animated, loop = _load_frames(data)
    if action == "reverse":
        if animated:
            frames.reverse()
            durations.reverse()
            return _save_gif(frames, durations, loop), ".gif"
        action = "flip"
    if action == "flip":
        flipped = [frame.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT) for frame in frames]
        if animated:
            return _save_gif(flipped, durations, loop), ".gif"
        return _save_png(flipped[0]), ".png"
    fn = _MIRROR[action]
    processed = [fn(frame, ratio) for frame in frames]
    if animated:
        return _save_gif(processed, durations, loop), ".gif"
    return _save_png(processed[0]), ".png"


def _keep_even(dim: str, ratio: int) -> str:
    r = max(0, min(100, int(ratio))) / 100.0
    return f"max(2\\,trunc({dim}*{r}/2)*2)"


def _ffmpeg_vf(action: str, ratio: int) -> str:
    if action == "reverse":
        return "reverse"
    if action == "flip":
        return "hflip"
    kw = _keep_even("iw", ratio)
    kh = _keep_even("ih", ratio)
    if action == "left":
        return f"crop={kw}:ih:0:0,split[a][b];[b]hflip[c];[a][c]hstack"
    if action == "right":
        return f"crop={kw}:ih:iw-ow:0,split[a][b];[b]hflip[c];[c][a]hstack"
    if action == "top":
        return f"crop=iw:{kh}:0:0,split[a][b];[b]vflip[c];[a][c]vstack"
    if action == "bottom":
        return f"crop=iw:{kh}:0:ih-oh,split[a][b];[b]vflip[c];[c][a]vstack"
    raise ValueError("unknown action")


def _run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=300,
        creationflags=_CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", "ignore")[-400:]
        raise ValueError(err.strip() or "ffmpeg 失败")


def process_ffmpeg(src: str, action: str, ratio: int, kind: str) -> tuple[str, str]:
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        raise ValueError("没装 ffmpeg，视频和大动图做不了")
    ratio = max(0, min(100, int(ratio)))
    vf = _ffmpeg_vf(action, ratio)
    suffix = ".gif" if kind == "gif" else ".mp4"
    out = str(Path(tempfile.gettempdir()) / f"lifebuddy_sym_{uuid4().hex}{suffix}")
    if kind == "gif":
        _run_ffmpeg([ffmpeg, "-y", "-i", src, "-vf", vf, "-an", out])
        return out, suffix
    cmd = [ffmpeg, "-y", "-i", src, "-vf", vf]
    if action == "reverse":
        cmd += ["-af", "areverse"]
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        out,
    ]
    try:
        _run_ffmpeg(cmd)
    except ValueError:
        if action != "reverse":
            raise
        Path(out).unlink(missing_ok=True)
        _run_ffmpeg(
            [
                ffmpeg,
                "-y",
                "-i",
                src,
                "-vf",
                vf,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                out,
            ]
        )
    return out, suffix


def _write_temp(data: bytes, suffix: str) -> str:
    path = Path(tempfile.gettempdir()) / f"lifebuddy_sym_{uuid4().hex}{suffix}"
    path.write_bytes(data)
    return str(path)


def _send_path(event: AstrMessageEvent, path: str, suffix: str):
    result = event.make_result()
    if suffix == ".mp4" and VideoComp is not None:
        factory = getattr(VideoComp, "fromFileSystem", None)
        if callable(factory):
            result.chain = [factory(path=path)]
        else:
            result.chain = [VideoComp(file=path)]
    else:
        result.chain = [Image(file=path)]
    result.use_t2i(False)
    return result


async def handle_symmetry(event: AstrMessageEvent, cache: ImageCache, action: str):
    ratio = parse_symmetry_ratio(event)
    try:
        src = await resolve_media_path(event, cache)
    except Exception:
        src = None
    if not src:
        if reply_message_ids(event):
            yield event.plain_result("这张图我没存到")
            return
        yield event.plain_result("头像拿不到")
        return
    kind = sniff_file(src) or "image"
    try:
        if kind == "video" and not _ffmpeg_bin():
            yield event.plain_result("没装 ffmpeg，视频做不了")
            return
        if kind in ("video", "gif") and _ffmpeg_bin():
            out, suffix = await asyncio.to_thread(process_ffmpeg, src, action, ratio, kind)
            yield _send_path(event, out, suffix)
            return
        data = Path(src).read_bytes()
        out, suffix = await asyncio.to_thread(process_image, data, action, ratio)
    except ValueError as exc:
        text = str(exc)
        if "没装 ffmpeg" in text:
            yield event.plain_result(text)
        else:
            yield event.plain_result("视频没做成" if kind == "video" else "图没做成")
        return
    except Exception:
        yield event.plain_result("图没做成" if kind != "video" else "视频没做成")
        return
    path = _write_temp(out, suffix)
    yield _send_path(event, path, suffix)
