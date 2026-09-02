from __future__ import annotations

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image


def has_image_by_classname(event: AstrMessageEvent) -> bool:
    for item in event.message_obj.message:
        if type(item).__name__ == "Image":
            return True
    return False


def has_image_by_isinstance(event: AstrMessageEvent) -> bool:
    for item in event.message_obj.message:
        if isinstance(item, Image):
            return True
    return False
