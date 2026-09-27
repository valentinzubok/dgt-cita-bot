"""Хранилище подписок: Postgres (DATABASE_URL, на сервере) или SQLite-файл (локально).

Все данные, кроме истории, держим в памяти и пишем в базу только при изменениях:
бесплатный Neon засыпает без запросов, и частые проверки не должны его будить.
Рассчитано на один процесс бота.
"""
from __future__ import annotations

import copy
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

_mem = threading.RLock()
_subs: Dict[int, dict] = {}
_chats: Dict[int, dict] = {}
_offices: Dict[Tuple[str, str], Optional[int]] = {}


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


def _norm(value):
    """Приводит результат проверки к виду, в котором он лежит в JSON (кортежи → списки)."""
    return json.loads(json.dumps(value, ensure_ascii=False)) if value is not None else None


def init() -> None:
    for stmt in SCHEMA:
        q(stmt)
    with _mem:
        _subs.clear()
        for row in q("SELECT * FROM subs"):
            row["last"] = json.loads(row["last"]) if row.get("last") else None
            _subs[row["id"]] = row
        _chats.clear()
        _chats.update({r["chat"]: r for r in q("SELECT * FROM chats")})
        _offices.clear()
        _offices.update({(r["centro"], r["area"]): r["open_event"] for r in q("SELECT * FROM offices")})
    log.info("хранилище: %s, подписок: %d, пользователей: %d",
             "Postgres" if PG else f"SQLite ({SQLITE_PATH.name})", len(_subs), len(_chats))


# ---------- чаты ----------

def ensure_chat(chat: int, name: str) -> None:
    with _mem:
        if chat in _chats:
            return
        row = {"chat": chat, "name": name, "quiet": 0, "created_at": int(time.time())}
        q("INSERT INTO chats (chat, name, quiet, created_at) VALUES (?, ?, 0, ?) ON CONFLICT (chat) DO NOTHING",
          (chat, name, row["created_at"]))
        _chats[chat] = row


def get_chat(chat: int) -> dict:
    with _mem:
        return dict(_chats.get(chat) or {"chat": chat, "quiet": 0})


def set_quiet(chat: int, quiet: bool) -> None:
    with _mem:
        q("UPDATE chats SET quiet = ? WHERE chat = ?", (int(quiet), chat))
        if chat in _chats:
            _chats[chat]["quiet"] = int(quiet)


def forget_chat(chat: int) -> None:
    with _mem:
        if any(s["chat"] == chat for s in _subs.values()):
            q("DELETE FROM subs WHERE chat = ?", (chat,))
        for sid in [sid for sid, s in _subs.items() if s["chat"] == chat]:
            del _subs[sid]


# ---------- подписки ----------

def add_sub(chat: int, centro: str, area: str) -> Tuple[dict, bool]:
    with _mem:
        for s in _subs.values():
            if (s["chat"], s["centro"], s["area"]) == (chat, centro, area):
                return copy.deepcopy(s), False
        q("INSERT INTO subs (chat, centro, area, created_at) VALUES (?, ?, ?, ?)",
          (chat, centro, area, int(time.time())))
        row = q1("SELECT * FROM subs WHERE chat = ? AND centro = ? AND area = ?", (chat, centro, area))
        row["last"] = None
        _subs[row["id"]] = row
        return copy.deepcopy(row), True


def get_sub(sub_id: int) -> Optional[dict]:
    with _mem:
        s = _subs.get(sub_id)
        return copy.deepcopy(s) if s else None


def subs_of(chat: int) -> List[dict]:
    with _mem:
        return [copy.deepcopy(s) for sid, s in sorted(_subs.items()) if s["chat"] == chat]


def subs_for(centro: str, area: str) -> List[dict]:
    with _mem:
        return [copy.deepcopy(s) for sid, s in sorted(_subs.items()) if (s["centro"], s["area"]) == (centro, area)]


def update_sub(sub_id: int, **fields) -> None:
    """Меняет подписку. В базу пишет только то, что реально изменилось (время проверки — только вместе с другим)."""
    with _mem:
        cur = _subs.get(sub_id)
        if cur is None:
            return
        fields = {k: (_norm(v) if k == "last" else v) for k, v in fields.items() if k in SUB_FIELDS}
        changed = {k: v for k, v in fields.items() if cur.get(k) != v}
        cur.update(changed)
        persist = {k: v for k, v in changed.items() if k != "checked_at"}
        if not persist:
            return
        persist["checked_at"] = cur.get("checked_at")
        if "last" in persist:
            persist["last"] = json.dumps(persist["last"], ensure_ascii=False) if persist["last"] is not None else None
        sets = ", ".join(f"{k} = ?" for k in persist)
        q(f"UPDATE subs SET {sets} WHERE id = ?", (*persist.values(), sub_id))


def delete_sub(sub_id: int, chat: int) -> None:
    with _mem:
        if sub_id in _subs and _subs[sub_id]["chat"] == chat:
            q("DELETE FROM subs WHERE id = ?", (sub_id,))
            del _subs[sub_id]


def active_keys() -> List[Tuple[str, str]]:
    with _mem:
        return sorted({(s["centro"], s["area"]) for s in _subs.values() if not s["paused"]})


# ---------- история появления мест ----------

def office_changed(centro: str, area: str, available: bool, days: int) -> None:
    """Отмечает момент, когда в офисе появились или закончились места."""
    with _mem:
        open_event = _offices.get((centro, area))
        now = int(time.time())
        if available and not open_event:
            q("INSERT INTO events (centro, area, opened_at, days) VALUES (?, ?, ?, ?)", (centro, area, now, days))
            ev = q1("SELECT MAX(id) AS id FROM events WHERE centro = ? AND area = ?", (centro, area))["id"]
            q("INSERT INTO offices (centro, area, open_event) VALUES (?, ?, ?) "
              "ON CONFLICT (centro, area) DO UPDATE SET open_event = excluded.open_event", (centro, area, ev))
            _offices[(centro, area)] = ev
        elif not available and open_event:
            q("UPDATE events SET closed_at = ? WHERE id = ?", (now, open_event))
            q("UPDATE offices SET open_event = NULL WHERE centro = ? AND area = ?", (centro, area))
            _offices[(centro, area)] = None


def events(centro: str, area: str, limit: int = 30) -> List[dict]:
    return q("SELECT * FROM events WHERE centro = ? AND area = ? ORDER BY opened_at DESC LIMIT ?",
             (centro, area, limit))


def totals() -> Dict[str, int]:
    with _mem:
        return {"chats": len(_chats), "subs": len(_subs), "offices": len(active_keys())}
