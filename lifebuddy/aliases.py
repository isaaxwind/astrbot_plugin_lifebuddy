from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ALIASES_PATH = PLUGIN_DIR / "data" / "aliases.json"


@dataclass(frozen=True)
class AliasEntry:
    alias: str
    image: str
    song_id: int | None = None


class AliasStore:
    def __init__(self, entries: list[AliasEntry], path: Path | None = None):
        self.entries = entries
        self.path = path or DEFAULT_ALIASES_PATH

    @classmethod
    def load(cls, path: Path | None = None) -> "AliasStore":
        path = path or DEFAULT_ALIASES_PATH
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries: list[AliasEntry] = []
        for item in raw.get("aliases", []):
            song_id = item.get("song_id")
            entries.append(
                AliasEntry(
                    alias=str(item["alias"]),
                    image=str(item["image"]),
                    song_id=int(song_id) if song_id is not None else None,
                )
            )
        return cls(entries, path)

    def find(self, text: str) -> list[AliasEntry]:
        needle = text.lower()
        return [entry for entry in self.entries if entry.alias.lower() in needle]

    def add(
        self,
        alias: str,
        *,
        song_id: int | None = None,
        image: str = "",
        image_base: str = "https://chilundui.com",
    ) -> tuple[AliasEntry, bool]:
        alias = alias.strip()
        image = image.strip()
        if song_id is not None and not image:
            image = f"{image_base.rstrip('/')}/data/rbdx/image/song/{int(song_id)}.png"
        entry = AliasEntry(alias=alias, image=image, song_id=song_id)
        for i, old in enumerate(self.entries):
            if old.alias.lower() == alias.lower():
                self.entries[i] = entry
                self.save()
                return entry, True
        self.entries.append(entry)
        self.save()
        return entry, False

    def remove(self, alias: str) -> AliasEntry | None:
        needle = alias.strip().lower()
        for i, old in enumerate(self.entries):
            if old.alias.lower() == needle:
                del self.entries[i]
                self.save()
                return old
        return None

    def save(self) -> None:
        payload = {
            "version": 1,
            "aliases": [
                {
                    "alias": entry.alias,
                    "song_id": entry.song_id,
                    "image": entry.image,
                }
                for entry in self.entries
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
