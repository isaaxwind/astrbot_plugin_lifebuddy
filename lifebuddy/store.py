from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


def data_dir() -> Path:
    try:
        from astrbot.api.star import StarTools

        getter = getattr(StarTools, "get_data_dir", None)
        if getter:
            try:
                root = Path(getter("lifebuddy"))
            except TypeError:
                root = Path(getter())
            root.mkdir(parents=True, exist_ok=True)
            return root
    except Exception:
        pass
    fallback = Path("data/plugin_data/lifebuddy")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


@dataclass(frozen=True)
class NickRow:
    qq: str
    nick: str
    last_seen_name: str
    manual: bool


@dataclass(frozen=True)
class DibRow:
    group_id: str
    qq: str
    song_id: int | None
    song_name: str
    song_query: str
    created_at: int


class BuddyStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "lifebuddy.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init()

    def _init(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nicks (
                qq TEXT PRIMARY KEY,
                nick TEXT NOT NULL,
                last_seen_name TEXT NOT NULL DEFAULT '',
                manual INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dibs (
                group_id TEXT NOT NULL,
                qq TEXT NOT NULL,
                song_id INTEGER,
                song_name TEXT NOT NULL,
                song_query TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (group_id, qq)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_dibs_song_id
                ON dibs(group_id, song_id) WHERE song_id IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_dibs_song_name
                ON dibs(group_id, song_name COLLATE NOCASE);
            CREATE TABLE IF NOT EXISTS binds (
                qq TEXT PRIMARY KEY,
                account_name TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS charter_aliases (
                qq TEXT NOT NULL,
                charter TEXT NOT NULL,
                PRIMARY KEY (qq, charter)
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def observe_speaker(self, qq: str, seen_name: str) -> NickRow | None:
        qq = str(qq or "").strip()
        if not qq:
            return None
        seen_name = (seen_name or "").strip()
        now = int(time.time())
        row = self._conn.execute("SELECT * FROM nicks WHERE qq = ?", (qq,)).fetchone()
        if row is None:
            nick = seen_name or qq
            self._conn.execute(
                "INSERT INTO nicks(qq, nick, last_seen_name, manual, updated_at) VALUES (?,?,?,?,?)",
                (qq, nick, seen_name, 0, now),
            )
            self._conn.commit()
            return NickRow(qq, nick, seen_name, False)
        if seen_name and seen_name != row["last_seen_name"]:
            if int(row["manual"]) == 0:
                self._conn.execute(
                    "UPDATE nicks SET nick = ?, last_seen_name = ?, updated_at = ? WHERE qq = ?",
                    (seen_name, seen_name, now, qq),
                )
            else:
                self._conn.execute(
                    "UPDATE nicks SET last_seen_name = ?, updated_at = ? WHERE qq = ?",
                    (seen_name, now, qq),
                )
            self._conn.commit()
        return self.get_nick(qq)

    def set_nick(self, qq: str, nick: str, *, manual: bool = True) -> NickRow:
        qq = str(qq).strip()
        nick = nick.strip()
        now = int(time.time())
        existing = self.get_nick(qq)
        last_seen = existing.last_seen_name if existing else ""
        self._conn.execute(
            """
            INSERT INTO nicks(qq, nick, last_seen_name, manual, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(qq) DO UPDATE SET
                nick = excluded.nick,
                manual = excluded.manual,
                updated_at = excluded.updated_at
            """,
            (qq, nick, last_seen, 1 if manual else 0, now),
        )
        self._conn.commit()
        return NickRow(qq, nick, last_seen, manual)

    def get_nick(self, qq: str) -> NickRow | None:
        row = self._conn.execute("SELECT * FROM nicks WHERE qq = ?", (str(qq),)).fetchone()
        if not row:
            return None
        return NickRow(row["qq"], row["nick"], row["last_seen_name"], bool(row["manual"]))

    def display_name(self, qq: str) -> str:
        row = self.get_nick(qq)
        if row and row.nick:
            return row.nick
        return str(qq)

    def list_nicks(self) -> list[NickRow]:
        rows = self._conn.execute("SELECT * FROM nicks ORDER BY nick COLLATE NOCASE").fetchall()
        return [NickRow(r["qq"], r["nick"], r["last_seen_name"], bool(r["manual"])) for r in rows]

    def find_nicks(self, query: str) -> list[NickRow]:
        needle = (query or "").strip()
        if not needle:
            return []
        exact = self._conn.execute(
            """
            SELECT * FROM nicks
            WHERE qq = ?
               OR nick = ? COLLATE NOCASE
               OR last_seen_name = ? COLLATE NOCASE
            ORDER BY nick COLLATE NOCASE
            """,
            (needle, needle, needle),
        ).fetchall()
        if exact:
            return [NickRow(r["qq"], r["nick"], r["last_seen_name"], bool(r["manual"])) for r in exact]
        if len(needle) < 2:
            return []
        like = f"%{needle}%"
        rows = self._conn.execute(
            """
            SELECT * FROM nicks
            WHERE nick LIKE ? ESCAPE '\\' COLLATE NOCASE
               OR last_seen_name LIKE ? ESCAPE '\\' COLLATE NOCASE
            ORDER BY nick COLLATE NOCASE
            LIMIT 8
            """,
            (like, like),
        ).fetchall()
        return [NickRow(r["qq"], r["nick"], r["last_seen_name"], bool(r["manual"])) for r in rows]

    def get_dib(self, group_id: str, qq: str) -> DibRow | None:
        row = self._conn.execute(
            "SELECT * FROM dibs WHERE group_id = ? AND qq = ?",
            (group_id, str(qq)),
        ).fetchone()
        return _dib(row) if row else None

    def find_dib_by_song(self, group_id: str, song_id: int | None, song_name: str) -> DibRow | None:
        if song_id is not None:
            row = self._conn.execute(
                "SELECT * FROM dibs WHERE group_id = ? AND song_id = ?",
                (group_id, song_id),
            ).fetchone()
            if row:
                return _dib(row)
        row = self._conn.execute(
            "SELECT * FROM dibs WHERE group_id = ? AND song_name = ? COLLATE NOCASE",
            (group_id, song_name),
        ).fetchone()
        return _dib(row) if row else None

    def list_dibs(self, group_id: str) -> list[DibRow]:
        rows = self._conn.execute(
            "SELECT * FROM dibs WHERE group_id = ? ORDER BY created_at",
            (group_id,),
        ).fetchall()
        return [_dib(r) for r in rows]

    def claim_dib(
        self,
        group_id: str,
        qq: str,
        song_id: int | None,
        song_name: str,
        song_query: str,
    ) -> tuple[str, DibRow | None]:
        qq = str(qq)
        existing = self.get_dib(group_id, qq)
        if existing:
            return "already_self", existing
        taken = self.find_dib_by_song(group_id, song_id, song_name)
        if taken:
            return "taken", taken
        now = int(time.time())
        try:
            self._conn.execute(
                "INSERT INTO dibs(group_id, qq, song_id, song_name, song_query, created_at) VALUES (?,?,?,?,?,?)",
                (group_id, qq, song_id, song_name, song_query, now),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            taken = self.find_dib_by_song(group_id, song_id, song_name) or self.get_dib(group_id, qq)
            return "taken", taken
        return "ok", self.get_dib(group_id, qq)

    def clear_dib(self, group_id: str, qq: str) -> DibRow | None:
        row = self.get_dib(group_id, qq)
        if not row:
            return None
        self._conn.execute("DELETE FROM dibs WHERE group_id = ? AND qq = ?", (group_id, str(qq)))
        self._conn.commit()
        return row

    def clear_dib_by_song(self, group_id: str, song_name: str) -> DibRow | None:
        row = self.find_dib_by_song(group_id, None, song_name)
        if not row:
            return None
        self._conn.execute(
            "DELETE FROM dibs WHERE group_id = ? AND qq = ?",
            (group_id, row.qq),
        )
        self._conn.commit()
        return row

    def get_bind(self, qq: str) -> str | None:
        row = self._conn.execute(
            "SELECT account_name FROM binds WHERE qq = ?", (str(qq),)
        ).fetchone()
        return str(row["account_name"]) if row else None

    def get_bind_qq(self, account_name: str) -> str | None:
        row = self._conn.execute(
            "SELECT qq FROM binds WHERE account_name = ? COLLATE NOCASE",
            (account_name,),
        ).fetchone()
        return str(row["qq"]) if row else None

    def set_bind(self, qq: str, account_name: str) -> None:
        now = int(time.time())
        self._conn.execute(
            "DELETE FROM binds WHERE qq = ? OR account_name = ? COLLATE NOCASE",
            (str(qq), account_name),
        )
        self._conn.execute(
            "INSERT INTO binds(qq, account_name, created_at) VALUES (?,?,?)",
            (str(qq), account_name, now),
        )
        self._conn.commit()

    def clear_bind(self, *, qq: str | None = None, account_name: str | None = None) -> str | None:
        if qq:
            row = self._conn.execute(
                "SELECT account_name FROM binds WHERE qq = ?", (str(qq),)
            ).fetchone()
            if not row:
                return None
            name = str(row["account_name"])
            self._conn.execute("DELETE FROM binds WHERE qq = ?", (str(qq),))
            self._conn.commit()
            return name
        if account_name:
            row = self._conn.execute(
                "SELECT account_name FROM binds WHERE account_name = ? COLLATE NOCASE",
                (account_name,),
            ).fetchone()
            if not row:
                return None
            name = str(row["account_name"])
            self._conn.execute(
                "DELETE FROM binds WHERE account_name = ? COLLATE NOCASE",
                (account_name,),
            )
            self._conn.commit()
            return name
        return None

    def add_charter_alias(self, qq: str, charter: str) -> bool:
        qq = str(qq).strip()
        charter = charter.strip()
        if not qq or not charter:
            return False
        self._conn.execute(
            "INSERT OR IGNORE INTO charter_aliases(qq, charter) VALUES (?, ?)",
            (qq, charter),
        )
        self._conn.commit()
        return True

    def remove_charter_alias(self, qq: str, charter: str) -> bool:
        qq = str(qq).strip()
        charter = charter.strip()
        cur = self._conn.execute(
            "DELETE FROM charter_aliases WHERE qq = ? AND charter = ? COLLATE NOCASE",
            (qq, charter),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_charter_aliases(self, qq: str | None = None) -> list[tuple[str, str]]:
        if qq:
            rows = self._conn.execute(
                "SELECT qq, charter FROM charter_aliases WHERE qq = ? ORDER BY charter COLLATE NOCASE",
                (str(qq),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT qq, charter FROM charter_aliases ORDER BY qq, charter COLLATE NOCASE"
            ).fetchall()
        return [(str(r["qq"]), str(r["charter"])) for r in rows]

    def charter_names(self, qq: str) -> list[str]:
        names: list[str] = []
        row = self.get_nick(qq)
        if row:
            if row.nick:
                names.append(row.nick)
            if row.last_seen_name and row.last_seen_name not in names:
                names.append(row.last_seen_name)
        for _, charter in self.list_charter_aliases(qq):
            if charter not in names:
                names.append(charter)
        return names


def _dib(row: sqlite3.Row) -> DibRow:
    song_id = row["song_id"]
    return DibRow(
        group_id=row["group_id"],
        qq=row["qq"],
        song_id=int(song_id) if song_id is not None else None,
        song_name=row["song_name"],
        song_query=row["song_query"],
        created_at=int(row["created_at"]),
    )
