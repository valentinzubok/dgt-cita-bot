"""Хранилище: Postgres (DATABASE_URL, на сервере) или SQLite-файл (локально).

Пользователи, подписки и настройки лежат в памяти, в базу пишутся только изменения:
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

import config

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
    """CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT)""",
    """CREATE TABLE IF NOT EXISTS office_areas (
        centro TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at BIGINT NOT NULL)""",
]
# Колонки, добавленные после первой версии
MIGRATIONS = [
    ("chats", "username", "TEXT"),
    ("chats", "role", "TEXT NOT NULL DEFAULT 'user'"),
    ("chats", "screen", "BIGINT"),
    ("chats", "last_seen", "BIGINT"),
    ("subs", "area_label", "TEXT"),
    ("subs", "alert_msg", "BIGINT"),
    ("chats", "lang", "TEXT"),
    ("subs", "booked_date", "TEXT"),
    ("subs", "booked_time", "TEXT"),
    ("subs", "reminded", "INTEGER NOT NULL DEFAULT 0"),
]
SUB_FIELDS = {"max_days", "paused", "last", "checked_at", "fails", "alert_msg", "area_label",
              "booked_date", "booked_time", "reminded"}
CHAT_FIELDS = {"name", "username", "quiet", "role", "screen", "last_seen", "lang"}
DEFAULTS = {
    "interval": config.DEFAULT_INTERVAL,  # минут между проверками
    "max_subs": 5,                         # подписок на человека
    "checks_paused": 0,                    # 1 — проверки остановлены
    "access": "open",                      # open | approval
    "notify_new": 1,                       # писать админам о новых пользователях
}

_mem = threading.RLock()
_subs: Dict[int, dict] = {}
_chats: Dict[int, dict] = {}
_offices: Dict[Tuple[str, str], Optional[int]] = {}
_settings: Dict[str, object] = dict(DEFAULTS)
_areas: Dict[str, Tuple[int, list]] = {}


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


def _columns(table: str) -> set:
    if PG:
        return {r["column_name"] for r in
                q("SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,))}
    return {r["name"] for r in q(f"PRAGMA table_info({table})")}


def _norm(value):
    """Приводит результат проверки к виду, в котором он лежит в JSON (кортежи → списки)."""
    return json.loads(json.dumps(value, ensure_ascii=False)) if value is not None else None


def init() -> None:
    for stmt in SCHEMA:
        q(stmt)
    existing: Dict[str, set] = {}
    for table, col, decl in MIGRATIONS:
        if table not in existing:
            existing[table] = _columns(table)
        if col not in existing[table]:
            q(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    with _mem:
        _subs.clear()
        for row in q("SELECT * FROM subs"):
            row["last"] = json.loads(row["last"]) if row.get("last") else None
            _subs[row["id"]] = row
        _chats.clear()
        _chats.update({r["chat"]: r for r in q("SELECT * FROM chats")})
        _offices.clear()
        _offices.update({(r["centro"], r["area"]): r["open_event"] for r in q("SELECT * FROM offices")})
        _areas.clear()
        _areas.update({r["centro"]: (r["updated_at"], json.loads(r["data"])) for r in q("SELECT * FROM office_areas")})
        _settings.clear()
        _settings.update(DEFAULTS)
        for r in q("SELECT * FROM settings"):
            default = DEFAULTS.get(r["key"])
            _settings[r["key"]] = int(r["value"]) if isinstance(default, int) else r["value"]
    log.info("хранилище: %s, подписок: %d, пользователей: %d",
             "Postgres" if PG else f"SQLite ({SQLITE_PATH.name})", len(_subs), len(_chats))


# ---------- настройки бота ----------

def setting(key: str):
    with _mem:
        return _settings.get(key, DEFAULTS.get(key))


def set_setting(key: str, value) -> None:
    with _mem:
        q("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
          (key, str(value)))
        _settings[key] = value


# ---------- пользователи ----------

def touch_chat(chat: int, name: str, username: str) -> Tuple[dict, bool]:
    """Регистрирует пользователя или обновляет имя. Возвращает (chat, новый ли)."""
    now = int(time.time())
    with _mem:
        row = _chats.get(chat)
        if row is None:
            row = {"chat": chat, "name": name, "username": username, "quiet": 0, "role": "user",
                   "screen": None, "last_seen": now, "created_at": now, "lang": None}
            q("INSERT INTO chats (chat, name, username, quiet, role, last_seen, created_at) "
              "VALUES (?, ?, ?, 0, 'user', ?, ?) ON CONFLICT (chat) DO NOTHING",
              (chat, name, username, now, now))
            _chats[chat] = row
            return dict(row), True
        changes = {}
        if name and row.get("name") != name:
            changes["name"] = name
        if (username or None) != row.get("username"):
            changes["username"] = username or None
        if now - (row.get("last_seen") or 0) > 3600:  # «был в сети» — с точностью до часа
            changes["last_seen"] = now
        if changes:
            set_chat(chat, **changes)
        return dict(_chats[chat]), False


def get_chat(chat: int) -> dict:
    with _mem:
        return dict(_chats.get(chat) or {"chat": chat, "quiet": 0, "role": "user"})


def set_chat(chat: int, **fields) -> None:
    fields = {k: v for k, v in fields.items() if k in CHAT_FIELDS}
    with _mem:
        row = _chats.get(chat)
        if row is None or not fields:
            return
        changed = {k: v for k, v in fields.items() if row.get(k) != v}
        if changed:
            row.update(changed)
            sets = ", ".join(f"{k} = ?" for k in changed)
            q(f"UPDATE chats SET {sets} WHERE chat = ?", (*changed.values(), chat))


def all_chats() -> List[dict]:
    with _mem:
        return sorted((dict(c) for c in _chats.values()), key=lambda c: -(c.get("created_at") or 0))


def forget_chat(chat: int) -> None:
    """Удаляет все подписки пользователя."""
    with _mem:
        if any(s["chat"] == chat for s in _subs.values()):
            q("DELETE FROM subs WHERE chat = ?", (chat,))
        for sid in [sid for sid, s in _subs.items() if s["chat"] == chat]:
            del _subs[sid]


# ---------- подписки ----------

def add_sub(chat: int, centro: str, area: str, area_label: str) -> Tuple[dict, bool]:
    with _mem:
        for s in _subs.values():
            if (s["chat"], s["centro"], s["area"]) == (chat, centro, area):
                return copy.deepcopy(s), False
        q("INSERT INTO subs (chat, centro, area, area_label, created_at) VALUES (?, ?, ?, ?, ?)",
          (chat, centro, area, area_label, int(time.time())))
        row = q1("SELECT * FROM subs WHERE chat = ? AND centro = ? AND area = ?", (chat, centro, area))
        row["last"] = None
        _subs[row["id"]] = row
        return copy.deepcopy(row), True


def get_sub(sub_id: int) -> Optional[dict]:
    with _mem:
        s = _subs.get(sub_id)
        return copy.deepcopy(s) if s else None


def all_subs() -> List[dict]:
    with _mem:
        return [copy.deepcopy(s) for _, s in sorted(_subs.items())]


def subs_of(chat: int) -> List[dict]:
    return [s for s in all_subs() if s["chat"] == chat]


def subs_for(centro: str, area: str) -> List[dict]:
    return [s for s in all_subs() if (s["centro"], s["area"]) == (centro, area)]


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


def delete_sub(sub_id: int) -> None:
    with _mem:
        if sub_id in _subs:
            q("DELETE FROM subs WHERE id = ?", (sub_id,))
            del _subs[sub_id]


def pause_chat(chat: int) -> None:
    for s in subs_of(chat):
        update_sub(s["id"], paused=1)


def active_keys() -> List[Tuple[str, str]]:
    with _mem:
        banned = {c for c, row in _chats.items() if row.get("role") in ("banned", "pending")}
        return sorted({(s["centro"], s["area"]) for s in _subs.values()
                       if not s["paused"] and s["chat"] not in banned})


def area_labels() -> Dict[str, str]:
    """Названия областей из подписок — чтобы после перезапуска не терять подписи."""
    with _mem:
        return {s["area"]: s["area_label"] for s in _subs.values() if s.get("area_label")}


def office_areas(centro: str) -> Optional[Tuple[int, list]]:
    """Типы записи офиса из кэша: (когда получены, [(код, название)])."""
    with _mem:
        cached = _areas.get(centro)
        return (cached[0], [tuple(x) for x in cached[1]]) if cached else None


def save_office_areas(centro: str, areas: list) -> None:
    now = int(time.time())
    with _mem:
        q("INSERT INTO office_areas (centro, data, updated_at) VALUES (?, ?, ?) ON CONFLICT (centro) "
          "DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
          (centro, json.dumps(areas, ensure_ascii=False), now))
        _areas[centro] = (now, [list(x) for x in areas])


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
