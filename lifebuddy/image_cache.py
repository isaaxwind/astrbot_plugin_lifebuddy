from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from .store import data_dir

MAX_FILES = 250
MAX_AGE_SEC = 3 * 24 * 3600
_SAFE = re.compile(r"[^\w.-]+")


class ImageCache:
    def __init__(self, root: Path | None = None):
        self.root = root or (data_dir() / "images")
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, message_id: str) -> Path:
        safe = _SAFE.sub("_", str(message_id or "").strip())[:80]
        return self.root / safe

    def put(self, message_id: str, data: bytes) -> Path | None:
        if not message_id or not data:
            return None
        path = self.path_for(message_id)
        path.write_bytes(data)
        self.prune()
        return path

    def put_file(self, message_id: str, src: str | Path) -> Path | None:
        if not message_id:
            return None
        src_path = Path(src)
        if not src_path.is_file():
            return None
        dest = self.path_for(message_id)
        if src_path.resolve() != dest.resolve():
            shutil.copyfile(src_path, dest)
        self.prune()
        return dest

    def get_path(self, message_id: str) -> Path | None:
        if not message_id:
            return None
        path = self.path_for(message_id)
        return path if path.is_file() else None

    def get(self, message_id: str) -> bytes | None:
        path = self.get_path(message_id)
        if path is None:
            return None
        return path.read_bytes()

    def prune(self) -> None:
        files = [p for p in self.root.iterdir() if p.is_file()]
        if not files:
            return
        now = time.time()
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for i, path in enumerate(files):
            try:
                stale = now - path.stat().st_mtime > MAX_AGE_SEC
                if i >= MAX_FILES or stale:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
