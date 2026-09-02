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
    def __init__(self, entries: list[AliasEntry]):
        self.entries = entries

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
        return cls(entries)

    def find(self, text: str) -> list[AliasEntry]:
        needle = text.lower()
        return [entry for entry in self.entries if entry.alias.lower() in needle]
