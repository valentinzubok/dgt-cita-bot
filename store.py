"""Хранилище подписок: Postgres (DATABASE_URL, на сервере) или SQLite-файл (локально)."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("store")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = Path(__file__).resolve().parent / "bot.db"
_sqlite_lock = threading.Lock()

_PK = "BIGSERIAL PRIMARY KEY" if PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
SCHEMA = [
    f"""CREATE TABLE IF NOT EXISTS subs (
        id {_PK},
        chat BIGINT NOT NULL,
        centro TEXT NOT NULL,
        area TEXT NOT NULL,
        max_days INTEGER,
        paused INTEGER NOT NULL DEFAULT 0,
        last TEXT,
        checked_at BIGINT,
        fails INTEGER NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL,
        UNIQUE (chat, centro, area))""",
    """CREATE TABLE IF NOT EXISTS chats (
        chat BIGINT PRIMARY KEY,
        name TEXT,
        quiet INTEGER NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS offices (
        centro TEXT NOT NULL,
        area TEXT NOT NULL,
        open_event BIGINT,
        PRIMARY KEY (centro, area))""",
    f"""CREATE TABLE IF NOT EXISTS events (
        id {_PK},
        centro TEXT NOT NULL,
        area TEXT NOT NULL,
        opened_at BIGINT NOT NULL,
        closed_at BIGINT,
        days INTEGER)""",
]
SUB_FIELDS = {"max_days", "paused", "last", "checked_at", "fails"}


@contextmanager
def _conn():
    if PG:
        import psycopg2
        for attempt in range(3):
            try:
                c = psycopg2.connect(DATABASE_URL, connect_timeout=15)
                break
            except psycopg2.OperationalError:
                if attempt == 2:
                    raise
                time.sleep(2)  # Neon мог уснуть — даём ему проснуться
        try:
            yield c
            c.commit()
        finally:
            c.close()
    else:
        with _sqlite_lock:
            c = sqlite3.connect(SQLITE_PATH)
            try:
                yield c
                c.commit()
            finally:
                c.close()


def q(sql: str, params: tuple = ()) -> List[dict]:
    if PG:
        sql = sql.replace("?", "%s")
    with _conn() as c:
        cur = c.cursor()
        cur.execute(sql, params)
        if not cur.description:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def q1(sql: str, params: tuple = ()) -> Optional[dict]:
    rows = q(sql, params)
    return rows[0] if rows else None


def init() -> None:
    for stmt in SCHEMA:
        q(stmt)
    log.info("хранилище: %s", "Postgres" if PG else f"SQLite ({SQLITE_PATH.name})")


def _sub(row: Optional[dict]) -> Optional[dict]:
    if row is not None:
        row["last"] = json.loads(row["last"]) if row.get("last") else None
    return row


# ---------- чаты ----------

def ensure_chat(chat: int, name: str) -> None:
    q("INSERT INTO chats (chat, name, created_at) VALUES (?, ?, ?) ON CONFLICT (chat) DO NOTHING",
      (chat, name, int(time.time())))


def get_chat(chat: int) -> dict:
    return q1("SELECT * FROM chats WHERE chat = ?", (chat,)) or {"chat": chat, "quiet": 0}


def set_quiet(chat: int, quiet: bool) -> None:
    q("UPDATE chats SET quiet = ? WHERE chat = ?", (int(quiet), chat))


def forget_chat(chat: int) -> None:
    q("DELETE FROM subs WHERE chat = ?", (chat,))


# ---------- подписки ----------

def add_sub(chat: int, centro: str, area: str) -> Tuple[dict, bool]:
    existing = q1("SELECT * FROM subs WHERE chat = ? AND centro = ? AND area = ?", (chat, centro, area))
    if existing:
        return _sub(existing), False
    q("INSERT INTO subs (chat, centro, area, created_at) VALUES (?, ?, ?, ?)",
      (chat, centro, area, int(time.time())))
    return _sub(q1("SELECT * FROM subs WHERE chat = ? AND centro = ? AND area = ?", (chat, centro, area))), True


def get_sub(sub_id: int) -> Optional[dict]:
    return _sub(q1("SELECT * FROM subs WHERE id = ?", (sub_id,)))


def subs_of(chat: int) -> List[dict]:
    return [_sub(r) for r in q("SELECT * FROM subs WHERE chat = ? ORDER BY id", (chat,))]


def subs_for(centro: str, area: str) -> List[dict]:
    return [_sub(r) for r in q("SELECT * FROM subs WHERE centro = ? AND area = ?", (centro, area))]


def update_sub(sub_id: int, **fields) -> None:
    fields = {k: v for k, v in fields.items() if k in SUB_FIELDS}
    if "last" in fields:
        fields["last"] = json.dumps(fields["last"], ensure_ascii=False) if fields["last"] is not None else None
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        q(f"UPDATE subs SET {sets} WHERE id = ?", (*fields.values(), sub_id))


def delete_sub(sub_id: int, chat: int) -> None:
    q("DELETE FROM subs WHERE id = ? AND chat = ?", (sub_id, chat))


def active_keys() -> List[Tuple[str, str]]:
    return [(r["centro"], r["area"]) for r in
            q("SELECT DISTINCT centro, area FROM subs WHERE paused = 0 ORDER BY centro, area")]


# ---------- история появления мест ----------

def office_changed(centro: str, area: str, available: bool, days: int) -> None:
    """Отмечает момент, когда в офисе появились или закончились места."""
    now = int(time.time())
    row = q1("SELECT open_event FROM offices WHERE centro = ? AND area = ?", (centro, area))
    open_event = row["open_event"] if row else None
    if available and not open_event:
        q("INSERT INTO events (centro, area, opened_at, days) VALUES (?, ?, ?, ?)", (centro, area, now, days))
        ev = q1("SELECT MAX(id) AS id FROM events WHERE centro = ? AND area = ?", (centro, area))
        q("INSERT INTO offices (centro, area, open_event) VALUES (?, ?, ?) "
          "ON CONFLICT (centro, area) DO UPDATE SET open_event = excluded.open_event", (centro, area, ev["id"]))
    elif not available and open_event:
        q("UPDATE events SET closed_at = ? WHERE id = ?", (now, open_event))
        q("UPDATE offices SET open_event = NULL WHERE centro = ? AND area = ?", (centro, area))


def events(centro: str, area: str, limit: int = 30) -> List[dict]:
    return q("SELECT * FROM events WHERE centro = ? AND area = ? ORDER BY opened_at DESC LIMIT ?",
             (centro, area, limit))


def totals() -> Dict[str, int]:
    return {
        "chats": q1("SELECT COUNT(*) AS n FROM chats")["n"],
        "subs": q1("SELECT COUNT(*) AS n FROM subs")["n"],
        "offices": len(active_keys()),
    }
