from __future__ import annotations

import asyncio

_engine = None


def _ocr_sync(data: bytes) -> str:
    global _engine
    if not data:
        return ""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        try:
            from rapidocr import RapidOCR
        except Exception:
            return ""
    try:
        if _engine is None:
            _engine = RapidOCR()
        result = _engine(data)
    except Exception:
        return ""
    lines: list[str] = []
    payload = result
    if isinstance(result, tuple):
        payload = result[0]
    if not payload:
        return ""
    for item in payload:
        text = ""
        if isinstance(item, str):
            text = item
        elif isinstance(item, (list, tuple)):
            for part in item:
                if isinstance(part, str) and part.strip():
                    text = part
                    break
            if not text and len(item) >= 2 and isinstance(item[1], str):
                text = item[1]
        if text.strip():
            lines.append(text.strip())
    return "".join(lines)


async def ocr_bytes(data: bytes) -> str:
    return await asyncio.to_thread(_ocr_sync, data)
