from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, timedelta
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
            CREATE TABLE IF NOT EXISTS fudu_state (
                group_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                people TEXT NOT NULL,
                bot_echoed INTEGER NOT NULL DEFAULT 0,
                started_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fudu_chains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                text TEXT NOT NULL,
                length INTEGER NOT NULL,
                started_at INTEGER NOT NULL,
                ended_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fudu_chain_people (
                chain_id INTEGER NOT NULL,
                qq TEXT NOT NULL,
                PRIMARY KEY (chain_id, qq)
            );
            CREATE TABLE IF NOT EXISTS fudu_records (
                group_id TEXT PRIMARY KEY,
                best_length INTEGER NOT NULL,
                best_chain_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS jiju_candidates (
                group_id TEXT NOT NULL,
                day TEXT NOT NULL,
                text TEXT NOT NULL,
                length INTEGER NOT NULL,
                PRIMARY KEY (group_id, day, text)
            );
            CREATE TABLE IF NOT EXISTS jiju_blocked (
                group_id TEXT NOT NULL,
                day TEXT NOT NULL,
                text TEXT NOT NULL,
                PRIMARY KEY (group_id, day, text)
            );
            CREATE TABLE IF NOT EXISTS jiju_daily (
                group_id TEXT NOT NULL,
                day TEXT NOT NULL,
                rank INTEGER NOT NULL,
                text TEXT NOT NULL,
                PRIMARY KEY (group_id, day, rank)
            );
            CREATE TABLE IF NOT EXISTS jiju_announce (
                group_id TEXT PRIMARY KEY,
                last_day TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fudu_chains_group_ended
                ON fudu_chains(group_id, ended_at);
            CREATE INDEX IF NOT EXISTS idx_jiju_daily_group_day
                ON jiju_daily(group_id, day);
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

    def set_bind(self, qq: str, account_name: str) -> str | None:
        existing = self.get_bind(qq)
        if existing:
            return "你已经绑过了，要换绑找管理员"
        owner = self.get_bind_qq(account_name)
        if owner:
            return "这个号已经绑过别的 QQ 了"
        now = int(time.time())
        self._conn.execute(
            "INSERT INTO binds(qq, account_name, created_at) VALUES (?,?,?)",
            (str(qq), account_name, now),
        )
        self._conn.commit()
        return None

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

    def clear_charter_aliases(self, qq: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM charter_aliases WHERE qq = ?", (str(qq).strip(),)
        )
        self._conn.commit()
        return int(cur.rowcount or 0)

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

    def fudu_state(self, group_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM fudu_state WHERE group_id = ?", (group_id,)
        ).fetchone()
        if not row:
            return None
        people = _json_list(row["people"])
        return {
            "text": str(row["text"] or ""),
            "people": people,
            "bot_echoed": bool(row["bot_echoed"]),
            "started_at": int(row["started_at"]),
        }

    def set_fudu_state(
        self,
        group_id: str,
        text: str,
        people: list[str],
        *,
        bot_echoed: bool,
        started_at: int,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO fudu_state(group_id, text, people, bot_echoed, started_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(group_id) DO UPDATE SET
                text = excluded.text,
                people = excluded.people,
                bot_echoed = excluded.bot_echoed,
                started_at = excluded.started_at
            """,
            (group_id, text, json.dumps(people, ensure_ascii=False), 1 if bot_echoed else 0, started_at),
        )
        self._conn.commit()

    def clear_fudu_state(self, group_id: str) -> None:
        self._conn.execute("DELETE FROM fudu_state WHERE group_id = ?", (group_id,))
        self._conn.commit()

    def save_fudu_chain(
        self,
        group_id: str,
        text: str,
        people: list[str],
        started_at: int,
        ended_at: int,
    ) -> tuple[int, int, bool]:
        length = len(people)
        self._conn.execute(
            """
            INSERT INTO fudu_chains(group_id, text, length, started_at, ended_at)
            VALUES (?,?,?,?,?)
            """,
            (group_id, text, length, started_at, ended_at),
        )
        chain_id = int(self._conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        self._conn.executemany(
            "INSERT OR IGNORE INTO fudu_chain_people(chain_id, qq) VALUES (?,?)",
            [(chain_id, qq) for qq in people],
        )
        rec = self._conn.execute(
            "SELECT best_length FROM fudu_records WHERE group_id = ?",
            (group_id,),
        ).fetchone()
        broken = False
        if rec is None:
            self._conn.execute(
                "INSERT INTO fudu_records(group_id, best_length, best_chain_id) VALUES (?,?,?)",
                (group_id, length, chain_id),
            )
        elif length > int(rec["best_length"]):
            self._conn.execute(
                "UPDATE fudu_records SET best_length = ?, best_chain_id = ? WHERE group_id = ?",
                (length, chain_id, group_id),
            )
            broken = True
        self._conn.commit()
        best = int(
            (
                self._conn.execute(
                    "SELECT best_length FROM fudu_records WHERE group_id = ?",
                    (group_id,),
                ).fetchone()
                or {"best_length": length}
            )["best_length"]
        )
        return chain_id, best, broken

    def fudu_board(self, group_id: str, since: int, limit: int = 20) -> list[tuple[str, int]]:
        rows = self._conn.execute(
            """
            SELECT p.qq AS qq, COUNT(*) AS n
            FROM fudu_chain_people p
            JOIN fudu_chains c ON c.id = p.chain_id
            WHERE c.group_id = ? AND c.ended_at >= ?
            GROUP BY p.qq
            ORDER BY n DESC, p.qq
            LIMIT ?
            """,
            (group_id, since, limit),
        ).fetchall()
        return [(str(r["qq"]), int(r["n"])) for r in rows]

    def list_fudu_chains(self, group_id: str, limit: int = 15) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT id, text, length, started_at, ended_at
            FROM fudu_chains
            WHERE group_id = ?
            ORDER BY ended_at DESC
            LIMIT ?
            """,
            (group_id, limit),
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "text": str(r["text"] or ""),
                "length": int(r["length"]),
                "started_at": int(r["started_at"]),
                "ended_at": int(r["ended_at"]),
            }
            for r in rows
        ]

    def get_fudu_chain(self, group_id: str, chain_id: int) -> dict | None:
        row = self._conn.execute(
            """
            SELECT id, text, length, started_at, ended_at
            FROM fudu_chains
            WHERE group_id = ? AND id = ?
            """,
            (group_id, chain_id),
        ).fetchone()
        if not row:
            return None
        people = self._conn.execute(
            "SELECT qq FROM fudu_chain_people WHERE chain_id = ? ORDER BY qq",
            (chain_id,),
        ).fetchall()
        return {
            "id": int(row["id"]),
            "text": str(row["text"] or ""),
            "length": int(row["length"]),
            "started_at": int(row["started_at"]),
            "ended_at": int(row["ended_at"]),
            "people": [str(r["qq"]) for r in people],
        }

    def add_jiju_candidate(self, group_id: str, day: str, text: str) -> None:
        if self.is_jiju_blocked(group_id, day, text):
            return
        if self.is_yesterday_jiju(group_id, day, text):
            return
        self._conn.execute(
            """
            INSERT OR IGNORE INTO jiju_candidates(group_id, day, text, length)
            VALUES (?,?,?,?)
            """,
            (group_id, day, text, len(text)),
        )
        self._conn.commit()

    def is_jiju_blocked(self, group_id: str, day: str, text: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM jiju_blocked WHERE group_id = ? AND day = ? AND text = ?",
            (group_id, day, text),
        ).fetchone()
        return row is not None

    def block_jiju_text(self, group_id: str, day: str, text: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO jiju_blocked(group_id, day, text) VALUES (?,?,?)",
            (group_id, day, text),
        )
        self._conn.execute(
            "DELETE FROM jiju_candidates WHERE group_id = ? AND day = ? AND text = ?",
            (group_id, day, text),
        )
        self._conn.commit()

    def is_yesterday_jiju(self, group_id: str, today: str, text: str) -> bool:
        try:
            prev = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
        except ValueError:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM jiju_daily WHERE group_id = ? AND day = ? AND text = ?",
            (group_id, prev, text),
        ).fetchone()
        return row is not None

    def jiju_announced_day(self, group_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT last_day FROM jiju_announce WHERE group_id = ?", (group_id,)
        ).fetchone()
        return str(row["last_day"]) if row else None

    def mark_jiju_announced(self, group_id: str, day: str) -> None:
        self._conn.execute(
            """
            INSERT INTO jiju_announce(group_id, last_day) VALUES (?,?)
            ON CONFLICT(group_id) DO UPDATE SET last_day = excluded.last_day
            """,
            (group_id, day),
        )
        self._conn.commit()

    def finalize_jiju(self, group_id: str, day: str) -> list[str]:
        existing = self.list_jiju(group_id, day)
        if existing:
            return existing
        rows = self._conn.execute(
            """
            SELECT c.text AS text
            FROM jiju_candidates c
            WHERE c.group_id = ? AND c.day = ?
              AND NOT EXISTS (
                  SELECT 1 FROM jiju_blocked b
                  WHERE b.group_id = c.group_id AND b.day = c.day AND b.text = c.text
              )
            ORDER BY c.length, c.text
            LIMIT 5
            """,
            (group_id, day),
        ).fetchall()
        texts = [str(r["text"]) for r in rows]
        for i, text in enumerate(texts, 1):
            self._conn.execute(
                "INSERT OR IGNORE INTO jiju_daily(group_id, day, rank, text) VALUES (?,?,?,?)",
                (group_id, day, i, text),
            )
        self._conn.commit()
        return texts

    def list_jiju(self, group_id: str, day: str) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT text FROM jiju_daily
            WHERE group_id = ? AND day = ?
            ORDER BY rank
            """,
            (group_id, day),
        ).fetchall()
        return [str(r["text"]) for r in rows]

    def recent_jiju(self, group_id: str, since_day: str, until_day: str) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT text FROM jiju_daily
            WHERE group_id = ? AND day >= ? AND day <= ?
            ORDER BY day DESC, rank
            """,
            (group_id, since_day, until_day),
        ).fetchall()
        return [str(r["text"]) for r in rows]


def _json_list(raw) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if str(x)]


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
