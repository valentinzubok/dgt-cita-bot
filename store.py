"""Хранилище: Postgres (DATABASE_URL, на сервере) или SQLite-файл (локально).

Всё, что нужно часто, живёт в памяти. Запись в базу идёт фоновой очередью одним потоком:
чтения и ответы пользователям никогда не ждут базу, а бесплатный Neon может спать между изменениями.
Рассчитано на один процесс бота.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import queue
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import config

log = logging.getLogger("store")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = Path(os.environ.get("SQLITE_PATH") or Path(__file__).resolve().parent / "bot.db")
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
    """CREATE TABLE IF NOT EXISTS metrics (
        day TEXT NOT NULL,
        key TEXT NOT NULL,
        value BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (day, key))""",
    """CREATE TABLE IF NOT EXISTS office_areas (
        centro TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS payments (
        charge_id TEXT PRIMARY KEY,
        chat BIGINT NOT NULL,
        stars INTEGER NOT NULL,
        plan TEXT NOT NULL,
        recurring INTEGER NOT NULL DEFAULT 0,
        refunded INTEGER NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS premium_log (
        id {_PK},
        chat BIGINT NOT NULL,
        seconds BIGINT NOT NULL,
        reason TEXT NOT NULL,
        created_at BIGINT NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS tasks (
        id {_PK},
        kind TEXT NOT NULL,
        title_ru TEXT NOT NULL,
        title_uk TEXT NOT NULL,
        target TEXT NOT NULL,
        link TEXT,
        hours INTEGER NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS task_done (
        task TEXT NOT NULL,
        chat BIGINT NOT NULL,
        created_at BIGINT NOT NULL,
        PRIMARY KEY (task, chat))""",
    """CREATE TABLE IF NOT EXISTS signal_subs (
        chat BIGINT NOT NULL,
        province TEXT NOT NULL,
        doc TEXT NOT NULL,
        created_at BIGINT NOT NULL,
        PRIMARY KEY (chat, province, doc))""",
    f"""CREATE TABLE IF NOT EXISTS signals (
        id {_PK},
        chat BIGINT NOT NULL,
        province TEXT NOT NULL,
        doc TEXT NOT NULL,
        ok_votes INTEGER NOT NULL DEFAULT 0,
        no_votes INTEGER NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS signal_votes (
        sig BIGINT NOT NULL,
        chat BIGINT NOT NULL,
        PRIMARY KEY (sig, chat))""",
    """CREATE TABLE IF NOT EXISTS reward_ledger (
        key TEXT PRIMARY KEY,
        created_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS promos (
        code TEXT PRIMARY KEY,
        hours INTEGER NOT NULL,
        max_uses INTEGER NOT NULL DEFAULT 0,
        uses INTEGER NOT NULL DEFAULT 0,
        expires_at BIGINT NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        note TEXT,
        created_at BIGINT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS promo_uses (
        code TEXT NOT NULL,
        chat BIGINT NOT NULL,
        created_at BIGINT NOT NULL,
        PRIMARY KEY (code, chat))""",
    f"""CREATE TABLE IF NOT EXISTS campaigns (
        id {_PK},
        name TEXT NOT NULL,
        payload TEXT NOT NULL,
        button TEXT,
        url TEXT,
        segment TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        sent INTEGER NOT NULL DEFAULT 0,
        failed INTEGER NOT NULL DEFAULT 0,
        clicks INTEGER NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL,
        sent_at BIGINT)""",
    """CREATE TABLE IF NOT EXISTS ad_clicks (
        campaign BIGINT NOT NULL,
        chat BIGINT NOT NULL,
        created_at BIGINT NOT NULL,
        PRIMARY KEY (campaign, chat))""",
]
# Колонки, добавленные после первой версии
MIGRATIONS = [
    ("chats", "username", "TEXT"),
    ("tasks", "title_es", "TEXT"),
    ("tasks", "title_en", "TEXT"),
    ("chats", "role", "TEXT NOT NULL DEFAULT 'user'"),
    ("chats", "screen", "BIGINT"),
    ("chats", "last_seen", "BIGINT"),
    ("subs", "area_label", "TEXT"),
    ("subs", "alert_msg", "BIGINT"),
    ("chats", "lang", "TEXT"),
    ("subs", "booked_date", "TEXT"),
    ("subs", "booked_time", "TEXT"),
    ("subs", "reminded", "INTEGER NOT NULL DEFAULT 0"),
    ("chats", "alerts", "INTEGER NOT NULL DEFAULT 0"),
    ("chats", "bookings", "INTEGER NOT NULL DEFAULT 0"),
    ("chats", "source", "TEXT"),
    ("chats", "premium_until", "BIGINT NOT NULL DEFAULT 0"),
    ("chats", "prem_notice", "INTEGER NOT NULL DEFAULT 0"),
    ("chats", "sub_charge", "TEXT"),
    ("chats", "sub_active", "INTEGER NOT NULL DEFAULT 0"),
    ("chats", "ref_code", "TEXT"),
    ("chats", "ref_by", "BIGINT"),
    ("chats", "ref_done_at", "BIGINT"),
    ("chats", "ads_ok", "INTEGER NOT NULL DEFAULT 0"),
    ("chats", "last_ad", "BIGINT NOT NULL DEFAULT 0"),
]
SUB_FIELDS = {"max_days", "paused", "last", "checked_at", "fails", "alert_msg", "area_label",
              "booked_date", "booked_time", "reminded"}
CHAT_FIELDS = {"name", "username", "quiet", "role", "screen", "last_seen", "lang", "alerts", "bookings", "source",
               "premium_until", "prem_notice", "sub_charge", "sub_active", "ref_code", "ref_by", "ref_done_at",
               "ads_ok", "last_ad"}
INT_SETTINGS = {"interval", "interval_premium", "free_subs", "max_subs", "checks_paused", "notify_new", "maintenance",
                "daily_report", "price_7", "price_30", "price_90", "ref_hours", "ref_cap", "ref_task", "ad_gap",
                "free_radar_day"}
DEFAULTS = {
    "interval": 30,                # минут между проверками офиса (бесплатно)
    "interval_premium": 5,         # минут между проверками офиса, за которым следит подписчик Premium
    "free_subs": 2,                # офисов на бесплатном тарифе
    "max_subs": 10,                # офисов с Premium
    "free_radar_day": 1,           # радаров в день на бесплатном тарифе
    "checks_paused": 0,            # 1 — проверки остановлены
    "access": "open",              # open | approval
    "notify_new": 1,               # писать админам о новых пользователях
    "maintenance": 0,              # 1 — пользователи видят «технические работы»
    "daily_report": 1,             # вечерний отчёт владельцам
    "last_report": "",             # за какой день уже отправлен отчёт
    "blocked": "",                 # офисы, которые не проверяем: "centro:area,centro:area"
    "price_7": 39,                 # цена в звёздах: 7 дней
    "price_30": 99,                # 30 дней, автопродление
    "price_90": 249,               # 90 дней
    "ref_hours": 24,               # награда за приглашённого друга, часов Premium
    "ref_cap": 10,                 # максимум наград за друзей за 30 дней
    "ref_task": 0,                 # id задания-канала, обязательного для награды за друзей
    "ad_gap": 24,                  # минимум часов между рекламой одному человеку
    "avatar_sha": "",              # какая картинка уже стоит на аватаре бота
    "ledger_salt": "",             # ключ хешей в reward_ledger, создаётся при первом запуске
}

_mem = threading.RLock()
_subs: Dict[int, dict] = {}
_by_chat: Dict[int, Set[int]] = {}
_by_key: Dict[Tuple[str, str], Set[int]] = {}
_chats: Dict[int, dict] = {}
_ref_codes: Dict[str, int] = {}
_offices: Dict[Tuple[str, str], Optional[int]] = {}
_settings: Dict[str, object] = dict(DEFAULTS)
_areas: Dict[str, Tuple[int, list]] = {}
_metrics: Dict[Tuple[str, str], int] = {}
_pending: Dict[Tuple[str, str], int] = {}
_charges: Set[str] = set()
_tasks: Dict[int, dict] = {}
_done: Set[Tuple[str, int]] = set()
_promos: Dict[str, dict] = {}
_promo_uses: Set[Tuple[str, int]] = set()
_sig_subs: Set[Tuple[int, str, str]] = set()
_signals: Dict[int, dict] = {}  # сигналы за последние 30 дней
_sig_votes: Set[Tuple[int, int]] = set()
_ledger: Set[str] = set()  # хеши наград удалённых аккаунтов: удаление данных не даёт получить их заново
_campaigns: Dict[int, dict] = {}
_ad_clicks: Set[Tuple[int, int]] = set()


# ---------- база ----------

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
            c = sqlite3.connect(SQLITE_PATH, timeout=30)
            try:
                yield c
                c.commit()
            finally:
                c.close()


def _fix(sql: str) -> str:
    return sql.replace("?", "%s") if PG else sql


def q(sql: str, params: tuple = ()) -> List[dict]:
    """Синхронный запрос. Только для редких операций: он идёт в сеть до базы."""
    with _conn() as c:
        cur = c.cursor()
        cur.execute(_fix(sql), params)
        if not cur.description:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def q1(sql: str, params: tuple = ()) -> Optional[dict]:
    rows = q(sql, params)
    return rows[0] if rows else None


_wq: "queue.Queue[Tuple[str, tuple]]" = queue.Queue()


def write(sql: str, params: tuple = ()) -> None:
    """Запись в фоне, по порядку. Вызывающий поток не ждёт базу."""
    _wq.put((sql, params))


def _writer() -> None:
    while True:
        batch = [_wq.get()]
        time.sleep(0.05)
        while len(batch) < 200:
            try:
                batch.append(_wq.get_nowait())
            except queue.Empty:
                break
        _store_batch(batch)
        for _ in batch:
            _wq.task_done()


def _store_batch(batch: List[Tuple[str, tuple]]) -> None:
    """Пропавшая связь с базой — не повод терять оплату: ждём до 10 минут. Плохой запрос выполняем отдельно от остальных."""
    for attempt in range(40):
        try:
            with _conn() as c:
                cur = c.cursor()
                for sql, params in batch:
                    cur.execute(_fix(sql), params)
            return
        except Exception as e:
            if type(e).__name__ not in ("OperationalError", "InterfaceError"):
                break
            log.warning("база недоступна, записей в очереди: %d", len(batch))
            time.sleep(15)
    for sql, params in batch:
        try:
            q(sql, params)
        except Exception:
            log.exception("запись не прошла: %s", sql[:80])


def flush(timeout: float = 20) -> bool:
    """Ждёт, пока очередь записей опустеет. True — всё записано."""
    end = time.time() + timeout
    while _wq.unfinished_tasks and time.time() < end:
        time.sleep(0.02)
    return not _wq.unfinished_tasks


def _columns(table: str) -> set:
    if PG:
        return {r["column_name"] for r in
                q("SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,))}
    return {r["name"] for r in q(f"PRAGMA table_info({table})")}


def _norm(value):
    """Приводит результат проверки к виду, в котором он лежит в JSON (кортежи → списки)."""
    return json.loads(json.dumps(value, ensure_ascii=False)) if value is not None else None


def _index_sub(row: dict) -> None:
    _subs[row["id"]] = row
    _by_chat.setdefault(row["chat"], set()).add(row["id"])
    _by_key.setdefault((row["centro"], row["area"]), set()).add(row["id"])


def _unindex_sub(sid: int) -> None:
    row = _subs.pop(sid, None)
    if row:
        _by_chat.get(row["chat"], set()).discard(sid)
        _by_key.get((row["centro"], row["area"]), set()).discard(sid)


_started = False


def init() -> None:
    global _started
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
        _by_chat.clear()
        _by_key.clear()
        for row in q("SELECT * FROM subs"):
            row["last"] = json.loads(row["last"]) if row.get("last") else None
            _index_sub(row)
        _chats.clear()
        _chats.update({r["chat"]: r for r in q("SELECT * FROM chats")})
        _ref_codes.clear()
        _ref_codes.update({r["ref_code"]: c for c, r in _chats.items() if r.get("ref_code")})
        _offices.clear()
        _offices.update({(r["centro"], r["area"]): r["open_event"] for r in q("SELECT * FROM offices")})
        _areas.clear()
        _areas.update({r["centro"]: (r["updated_at"], json.loads(r["data"])) for r in q("SELECT * FROM office_areas")})
        since = (datetime.now(config.TZ).date() - timedelta(days=60)).isoformat()
        _metrics.clear()
        _metrics.update({(r["day"], r["key"]): int(r["value"]) for r in q("SELECT * FROM metrics WHERE day >= ?", (since,))})
        _charges.clear()
        _charges.update(r["charge_id"] for r in q("SELECT charge_id FROM payments"))
        _tasks.clear()
        _tasks.update({r["id"]: r for r in q("SELECT * FROM tasks")})
        _done.clear()
        _done.update((r["task"], r["chat"]) for r in q("SELECT task, chat FROM task_done"))
        _promos.clear()
        _promos.update({r["code"]: r for r in q("SELECT * FROM promos")})
        _promo_uses.clear()
        _promo_uses.update((r["code"], r["chat"]) for r in q("SELECT code, chat FROM promo_uses"))
        _sig_subs.clear()
        _sig_subs.update((r["chat"], r["province"], r["doc"]) for r in q("SELECT chat, province, doc FROM signal_subs"))
        _signals.clear()
        _signals.update({r["id"]: r for r in q("SELECT * FROM signals WHERE created_at >= ?", (int(time.time()) - 30 * 86400,))})
        _sig_votes.clear()
        _sig_votes.update((r["sig"], r["chat"]) for r in q("SELECT sig, chat FROM signal_votes"))
        _ledger.clear()
        _ledger.update(r["key"] for r in q("SELECT key FROM reward_ledger"))
        _campaigns.clear()
        _campaigns.update({r["id"]: r for r in q("SELECT * FROM campaigns")})
        _ad_clicks.clear()
        _ad_clicks.update((r["campaign"], r["chat"]) for r in q("SELECT campaign, chat FROM ad_clicks"))
        _settings.clear()
        _settings.update(DEFAULTS)
        for r in q("SELECT * FROM settings"):
            if r["key"] in DEFAULTS:
                _settings[r["key"]] = int(r["value"]) if r["key"] in INT_SETTINGS else r["value"]
    if not _started:
        _started = True
        threading.Thread(target=_writer, daemon=True, name="db-writer").start()
    if not setting("ledger_salt"):
        set_setting("ledger_salt", secrets.token_hex(16))
    log.info("хранилище: %s, подписок: %d, пользователей: %d",
             "Postgres" if PG else f"SQLite ({SQLITE_PATH.name})", len(_subs), len(_chats))


# ---------- настройки бота ----------

def setting(key: str):
    with _mem:
        return _settings.get(key, DEFAULTS.get(key))


def set_setting(key: str, value) -> None:
    with _mem:
        _settings[key] = value
    write("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
          (key, str(value)))


# ---------- пользователи ----------

def touch_chat(chat: int, name: str, username: str) -> Tuple[dict, bool]:
    """Регистрирует пользователя или обновляет имя. Возвращает (chat, новый ли)."""
    now = int(time.time())
    with _mem:
        row = _chats.get(chat)
        if row is None:
            row = {"chat": chat, "name": name, "username": username or None, "quiet": 0, "role": "user", "screen": None,
                   "last_seen": now, "created_at": now, "lang": None, "alerts": 0, "bookings": 0, "source": None,
                   "premium_until": 0, "prem_notice": 0, "sub_charge": None, "sub_active": 0, "ref_code": None,
                   "ref_by": None, "ref_done_at": None, "ads_ok": 0, "last_ad": 0}
            _chats[chat] = row
            write("INSERT INTO chats (chat, name, username, quiet, role, last_seen, created_at) "
                  "VALUES (?, ?, ?, 0, 'user', ?, ?) ON CONFLICT (chat) DO NOTHING",
                  (chat, name, username or None, now, now))
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
        if not changed:
            return
        row.update(changed)
        if "ref_code" in changed and changed["ref_code"]:
            _ref_codes[changed["ref_code"]] = chat
    sets = ", ".join(f"{k} = ?" for k in changed)
    write(f"UPDATE chats SET {sets} WHERE chat = ?", (*changed.values(), chat))


def chat_by_ref_code(code: str) -> Optional[int]:
    with _mem:
        return _ref_codes.get(code)


def all_chats() -> List[dict]:
    with _mem:
        return sorted((dict(c) for c in _chats.values()), key=lambda c: -(c.get("created_at") or 0))


def friends_of(chat: int) -> List[dict]:
    with _mem:
        return [dict(c) for c in _chats.values() if c.get("ref_by") == chat]


def bump_chat(chat: int, field: str) -> None:
    """Счётчик пользователя: сколько уведомлений получил, сколько раз записался."""
    with _mem:
        row = _chats.get(chat)
        if row is not None and field in ("alerts", "bookings"):
            set_chat(chat, **{field: (row.get(field) or 0) + 1})


def _ledger_key(kind: str, item: str, chat: int) -> str:
    return hmac.new(str(setting("ledger_salt")).encode(), f"{kind}:{item}:{chat}".encode(), hashlib.sha256).hexdigest()


def was_deleted(chat: int) -> bool:
    return _ledger_key("seen", "", chat) in _ledger


def delete_chat(chat: int) -> None:
    """Удаляет пользователя и его подписки (по его просьбе). От наград остаются только хеши:
    иначе удаление и новый /start давали бы их снова."""
    forget_chat(chat)
    for friend in friends_of(chat):
        set_chat(friend["chat"], ref_by=None)
    with _mem:
        row = _chats.pop(chat, None)
        if row and row.get("ref_code"):
            _ref_codes.pop(row["ref_code"], None)
        hashes = {_ledger_key("seen", "", chat)}
        for key in [k for k in _done if k[1] == chat]:
            _done.discard(key)
            hashes.add(_ledger_key("task", key[0], chat))
        for key in [k for k in _promo_uses if k[1] == chat]:
            _promo_uses.discard(key)
            hashes.add(_ledger_key("promo", key[0], chat))
        _ledger.update(hashes)
        for key in [k for k in _sig_subs if k[0] == chat]:
            _sig_subs.discard(key)
        for key in [k for k in _sig_votes if k[1] == chat]:
            _sig_votes.discard(key)
        for sig in _signals.values():
            if sig["chat"] == chat:
                sig["chat"] = 0
    write("DELETE FROM signal_subs WHERE chat = ?", (chat,))
    write("DELETE FROM signal_votes WHERE chat = ?", (chat,))
    write("UPDATE signals SET chat = 0 WHERE chat = ?", (chat,))
    now = int(time.time())
    for key in hashes:
        write("INSERT INTO reward_ledger (key, created_at) VALUES (?, ?) ON CONFLICT (key) DO NOTHING", (key, now))
    write("DELETE FROM chats WHERE chat = ?", (chat,))
    write("DELETE FROM task_done WHERE chat = ?", (chat,))
    write("DELETE FROM promo_uses WHERE chat = ?", (chat,))
    write("DELETE FROM ad_clicks WHERE chat = ?", (chat,))
    write("DELETE FROM premium_log WHERE chat = ?", (chat,))


def forget_chat(chat: int) -> None:
    """Удаляет все подписки пользователя."""
    with _mem:
        for sid in list(_by_chat.get(chat, ())):
            _unindex_sub(sid)
    write("DELETE FROM subs WHERE chat = ?", (chat,))


# ---------- подписки ----------

def add_sub(chat: int, centro: str, area: str, area_label: str) -> Tuple[dict, bool]:
    with _mem:
        for sid in _by_chat.get(chat, ()):
            s = _subs[sid]
            if s["centro"] == centro and s["area"] == area:
                return dict(s), False
    flush()  # подписка могла только что удаляться — новая запись должна идти после этого
    now = int(time.time())
    row = q1("INSERT INTO subs (chat, centro, area, area_label, created_at) VALUES (?, ?, ?, ?, ?) "
             "ON CONFLICT (chat, centro, area) DO UPDATE SET area_label = excluded.area_label RETURNING id",
             (chat, centro, area, area_label, now))
    sub = {"id": row["id"], "chat": chat, "centro": centro, "area": area, "area_label": area_label, "max_days": None,
           "paused": 0, "last": None, "checked_at": None, "fails": 0, "created_at": now, "alert_msg": None,
           "booked_date": None, "booked_time": None, "reminded": 0}
    with _mem:
        _index_sub(sub)
    return dict(sub), True


def get_sub(sub_id: int) -> Optional[dict]:
    with _mem:
        s = _subs.get(sub_id)
        return dict(s) if s else None


def all_subs() -> List[dict]:
    with _mem:
        return [dict(s) for _, s in sorted(_subs.items())]


def subs_of(chat: int) -> List[dict]:
    with _mem:
        return [dict(_subs[sid]) for sid in sorted(_by_chat.get(chat, ()))]


def subs_for(centro: str, area: str) -> List[dict]:
    with _mem:
        return [dict(_subs[sid]) for sid in sorted(_by_key.get((centro, area), ()))]


def update_sub(sub_id: int, **fields) -> None:
    """Меняет подписку. В базу пишет только то, что реально изменилось (время проверки — только вместе с другим)."""
    fields = {k: (_norm(v) if k == "last" else v) for k, v in fields.items() if k in SUB_FIELDS}
    with _mem:
        cur = _subs.get(sub_id)
        if cur is None:
            return
        changed = {k: v for k, v in fields.items() if cur.get(k) != v}
        cur.update(changed)
        persist = {k: v for k, v in changed.items() if k != "checked_at"}
        if not persist:
            return
        persist["checked_at"] = cur.get("checked_at")
    if "last" in persist:
        persist["last"] = json.dumps(persist["last"], ensure_ascii=False) if persist["last"] is not None else None
    sets = ", ".join(f"{k} = ?" for k in persist)
    write(f"UPDATE subs SET {sets} WHERE id = ?", (*persist.values(), sub_id))


def delete_sub(sub_id: int) -> None:
    with _mem:
        _unindex_sub(sub_id)
    write("DELETE FROM subs WHERE id = ?", (sub_id,))


def pause_chat(chat: int) -> None:
    for s in subs_of(chat):
        update_sub(s["id"], paused=1)


def blocked_keys() -> set:
    return {tuple(x.split(":", 1)) for x in str(setting("blocked") or "").split(",") if ":" in x}


def key_groups() -> Dict[Tuple[str, str], List[dict]]:
    """Офисы, которые надо проверять, и активные подписки на них."""
    with _mem:
        blocked = blocked_keys()
        out: Dict[Tuple[str, str], List[dict]] = {}
        for key, ids in _by_key.items():
            if key in blocked:
                continue
            for sid in ids:
                s = _subs[sid]
                if not s["paused"] and _chats.get(s["chat"], {}).get("role") not in ("banned", "pending"):
                    out.setdefault(key, []).append(s)
        return out


def active_keys() -> List[Tuple[str, str]]:
    return sorted(key_groups())


def popularity() -> Dict[Tuple[str, str], int]:
    """Сколько активных подписок на каждый офис."""
    return {k: len(v) for k, v in key_groups().items()}


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
        _areas[centro] = (now, [list(x) for x in areas])
    write("INSERT INTO office_areas (centro, data, updated_at) VALUES (?, ?, ?) ON CONFLICT (centro) "
          "DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
          (centro, json.dumps(areas, ensure_ascii=False), now))


# ---------- статистика по дням ----------

def today_key() -> str:
    return datetime.now(config.TZ).date().isoformat()


def bump(key: str, n: int = 1) -> None:
    """Считает событие за сегодня. В базу пишется раз в час пачкой, чтобы не будить Neon."""
    with _mem:
        k = (today_key(), key)
        _pending[k] = _pending.get(k, 0) + n


def flush_metrics() -> None:
    with _mem:
        items = list(_pending.items())
        _pending.clear()
        for k, n in items:
            _metrics[k] = _metrics.get(k, 0) + n
    for (day, key), n in items:
        write("INSERT INTO metrics (day, key, value) VALUES (?, ?, ?) ON CONFLICT (day, key) "
              "DO UPDATE SET value = metrics.value + excluded.value", (day, key, n))


def metric(day: str, key: str) -> int:
    with _mem:
        return _metrics.get((day, key), 0) + _pending.get((day, key), 0)


# ---------- история появления мест ----------

def office_changed(centro: str, area: str, available: bool, days: int) -> None:
    """Отмечает момент, когда в офисе появились или закончились места. Меняется редко, поэтому синхронно."""
    with _mem:
        open_event = _offices.get((centro, area))
    now = int(time.time())
    if available and not open_event:
        flush()
        ev = q1("INSERT INTO events (centro, area, opened_at, days) VALUES (?, ?, ?, ?) RETURNING id",
                (centro, area, now, days))["id"]
        with _mem:
            _offices[(centro, area)] = ev
        write("INSERT INTO offices (centro, area, open_event) VALUES (?, ?, ?) "
              "ON CONFLICT (centro, area) DO UPDATE SET open_event = excluded.open_event", (centro, area, ev))
    elif not available and open_event:
        with _mem:
            _offices[(centro, area)] = None
        write("UPDATE events SET closed_at = ? WHERE id = ?", (now, open_event))
        write("UPDATE offices SET open_event = NULL WHERE centro = ? AND area = ?", (centro, area))


def events(centro: str, area: str, limit: int = 30) -> List[dict]:
    flush(3)
    return q("SELECT * FROM events WHERE centro = ? AND area = ? ORDER BY opened_at DESC LIMIT ?",
             (centro, area, limit))


# ---------- Premium и оплаты ----------

def add_premium(chat: int, seconds: int, reason: str) -> int:
    """Добавляет Premium и возвращает новую дату окончания (отрицательные секунды — забрать)."""
    now = int(time.time())
    with _mem:
        row = _chats.get(chat)
        if row is None:
            return 0
        until = max(now, row.get("premium_until") or 0) + seconds
        set_chat(chat, premium_until=max(until, now if seconds < 0 else until), prem_notice=0)
        result = _chats[chat]["premium_until"]
    write("INSERT INTO premium_log (chat, seconds, reason, created_at) VALUES (?, ?, ?, ?)", (chat, seconds, reason, now))
    return result


def is_premium(chat: int) -> bool:
    with _mem:
        return (_chats.get(chat, {}).get("premium_until") or 0) > time.time()


def premium_log(chat: int, limit: int = 15) -> List[dict]:
    flush(3)
    return q("SELECT * FROM premium_log WHERE chat = ? ORDER BY created_at DESC LIMIT ?", (chat, limit))


def add_payment(charge_id: str, chat: int, stars: int, plan: str, recurring: bool) -> bool:
    """Записывает оплату. False — такая оплата уже была (Telegram прислал повтор)."""
    with _mem:
        if charge_id in _charges:
            return False
        _charges.add(charge_id)
    write("INSERT INTO payments (charge_id, chat, stars, plan, recurring, created_at) VALUES (?, ?, ?, ?, ?, ?) "
          "ON CONFLICT (charge_id) DO NOTHING", (charge_id, chat, stars, plan, int(recurring), int(time.time())))
    return True


def payment(charge_id: str) -> Optional[dict]:
    flush(3)
    return q1("SELECT * FROM payments WHERE charge_id = ?", (charge_id,))


def set_refunded(charge_id: str) -> None:
    write("UPDATE payments SET refunded = 1 WHERE charge_id = ?", (charge_id,))


def payments_recent(limit: int = 20) -> List[dict]:
    flush(3)
    return q("SELECT * FROM payments ORDER BY created_at DESC LIMIT ?", (limit,))


def payments_total() -> dict:
    flush(3)
    return q1("SELECT COUNT(*) AS n, COALESCE(SUM(stars), 0) AS stars FROM payments WHERE refunded = 0") or {"n": 0, "stars": 0}


# ---------- задания ----------

def tasks(active_only: bool = False) -> List[dict]:
    with _mem:
        return [dict(t) for _, t in sorted(_tasks.items()) if t["active"] or not active_only]


def get_task(tid: int) -> Optional[dict]:
    with _mem:
        t = _tasks.get(tid)
        return dict(t) if t else None


def add_task(kind: str, title_ru: str, title_uk: str, target: str, link: str, hours: int, title_es: str = "", title_en: str = "") -> dict:
    flush()
    now = int(time.time())
    row = q1("INSERT INTO tasks (kind, title_ru, title_uk, title_es, title_en, target, link, hours, created_at) "
             "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id", (kind, title_ru, title_uk, title_es, title_en, target, link, hours, now))
    task = {"id": row["id"], "kind": kind, "title_ru": title_ru, "title_uk": title_uk, "title_es": title_es, "title_en": title_en,
            "target": target, "link": link, "hours": hours, "active": 1, "created_at": now}
    with _mem:
        _tasks[task["id"]] = task
    return dict(task)


def set_task(tid: int, **fields) -> None:
    fields = {k: v for k, v in fields.items() if k in ("active", "hours", "title_ru", "title_uk", "title_es", "title_en", "link")}
    with _mem:
        if tid not in _tasks or not fields:
            return
        _tasks[tid].update(fields)
    sets = ", ".join(f"{k} = ?" for k in fields)
    write(f"UPDATE tasks SET {sets} WHERE id = ?", (*fields.values(), tid))


def delete_task(tid: int) -> None:
    with _mem:
        _tasks.pop(tid, None)
    write("DELETE FROM tasks WHERE id = ?", (tid,))


def task_is_done(task: str, chat: int) -> bool:
    with _mem:
        return (task, chat) in _done or _ledger_key("task", task, chat) in _ledger


def claim_task(task: str, chat: int) -> bool:
    """Отмечает задание выполненным. False — уже было (защита от двойной награды)."""
    with _mem:
        if task_is_done(task, chat):
            return False
        _done.add((task, chat))
    write("INSERT INTO task_done (task, chat, created_at) VALUES (?, ?, ?) ON CONFLICT (task, chat) DO NOTHING",
          (task, chat, int(time.time())))
    return True


def task_count(task: str) -> int:
    with _mem:
        return sum(1 for t, _ in _done if t == task)


# ---------- сигналы о документах ----------

def signal_subs_of(chat: int) -> List[Tuple[str, str]]:
    with _mem:
        return sorted((p, d) for c, p, d in _sig_subs if c == chat)


def signal_audience(province: str, doc: str) -> List[int]:
    with _mem:
        return [c for c, p, d in _sig_subs if p == province and d == doc]


def signal_sub_count() -> int:
    with _mem:
        return len(_sig_subs)


def add_signal_sub(chat: int, province: str, doc: str) -> None:
    with _mem:
        _sig_subs.add((chat, province, doc))
    write("INSERT INTO signal_subs (chat, province, doc, created_at) VALUES (?, ?, ?, ?) ON CONFLICT (chat, province, doc) DO NOTHING",
          (chat, province, doc, int(time.time())))


def del_signal_sub(chat: int, province: str, doc: str) -> None:
    with _mem:
        _sig_subs.discard((chat, province, doc))
    write("DELETE FROM signal_subs WHERE chat = ? AND province = ? AND doc = ?", (chat, province, doc))


def add_signal(chat: int, province: str, doc: str) -> dict:
    flush()
    now = int(time.time())
    row = q1("INSERT INTO signals (chat, province, doc, created_at) VALUES (?, ?, ?, ?) RETURNING id", (chat, province, doc, now))
    sig = {"id": row["id"], "chat": chat, "province": province, "doc": doc, "ok_votes": 0, "no_votes": 0, "created_at": now}
    with _mem:
        _signals[sig["id"]] = sig
    return dict(sig)


def get_signal(sid: int) -> Optional[dict]:
    with _mem:
        sig = _signals.get(sid)
        return dict(sig) if sig else None


def recent_signals(province: str, doc: str, since: float) -> List[dict]:
    with _mem:
        return sorted((dict(s) for s in _signals.values() if s["province"] == province and s["doc"] == doc and s["created_at"] >= since),
                      key=lambda s: -s["created_at"])


def signals_by(chat: int, since: float) -> List[dict]:
    with _mem:
        return [dict(s) for s in _signals.values() if s["chat"] == chat and s["created_at"] >= since]


def signal_vote(sid: int, chat: int, ok: bool) -> bool:
    """Один человек — один голос, за свой сигнал голосовать нельзя."""
    field = "ok_votes" if ok else "no_votes"
    with _mem:
        sig = _signals.get(sid)
        if not sig or sig["chat"] == chat or (sid, chat) in _sig_votes:
            return False
        _sig_votes.add((sid, chat))
        sig[field] += 1
    write("INSERT INTO signal_votes (sig, chat) VALUES (?, ?) ON CONFLICT (sig, chat) DO NOTHING", (sid, chat))
    write(f"UPDATE signals SET {field} = {field} + 1 WHERE id = ?", (sid,))
    return True


# ---------- промокоды ----------

def promos() -> List[dict]:
    with _mem:
        return sorted((dict(p) for p in _promos.values()), key=lambda p: -p["created_at"])


def get_promo(code: str) -> Optional[dict]:
    with _mem:
        p = _promos.get(code)
        return dict(p) if p else None


def add_promo(code: str, hours: int, max_uses: int, expires_at: int, note: str) -> Optional[dict]:
    now = int(time.time())
    with _mem:
        if code in _promos:
            return None
        promo = {"code": code, "hours": hours, "max_uses": max_uses, "uses": 0, "expires_at": expires_at, "active": 1,
                 "note": note, "created_at": now}
        _promos[code] = promo
    write("INSERT INTO promos (code, hours, max_uses, expires_at, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
          (code, hours, max_uses, expires_at, note, now))
    return dict(promo)


def set_promo_active(code: str, active: bool) -> None:
    with _mem:
        if code in _promos:
            _promos[code]["active"] = int(active)
    write("UPDATE promos SET active = ? WHERE code = ?", (int(active), code))


def delete_promo(code: str) -> None:
    with _mem:
        _promos.pop(code, None)
        for key in [k for k in _promo_uses if k[0] == code]:
            _promo_uses.discard(key)
    write("DELETE FROM promos WHERE code = ?", (code,))
    write("DELETE FROM promo_uses WHERE code = ?", (code,))


def use_promo(code: str, chat: int) -> str:
    """Активирует промокод атомарно: ok | none | off | expired | limit | used."""
    now = int(time.time())
    with _mem:
        p = _promos.get(code)
        if not p:
            return "none"
        if not p["active"]:
            return "off"
        if p["expires_at"] and now > p["expires_at"]:
            return "expired"
        if p["max_uses"] and p["uses"] >= p["max_uses"]:
            return "limit"
        if (code, chat) in _promo_uses or _ledger_key("promo", code, chat) in _ledger:
            return "used"
        _promo_uses.add((code, chat))
        p["uses"] += 1
    write("INSERT INTO promo_uses (code, chat, created_at) VALUES (?, ?, ?) ON CONFLICT (code, chat) DO NOTHING",
          (code, chat, now))
    write("UPDATE promos SET uses = uses + 1 WHERE code = ?", (code,))
    return "ok"


# ---------- реклама ----------

def campaigns() -> List[dict]:
    with _mem:
        return sorted((dict(c) for c in _campaigns.values()), key=lambda c: -c["id"])


def get_campaign(cid: int) -> Optional[dict]:
    with _mem:
        c = _campaigns.get(cid)
        return dict(c) if c else None


def add_campaign(name: str, payload: dict, button: str, url: str, segment: str) -> dict:
    flush()
    now = int(time.time())
    text = json.dumps(payload, ensure_ascii=False)
    row = q1("INSERT INTO campaigns (name, payload, button, url, segment, created_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
             (name, text, button, url, segment, now))
    camp = {"id": row["id"], "name": name, "payload": text, "button": button, "url": url, "segment": segment,
            "status": "draft", "sent": 0, "failed": 0, "clicks": 0, "created_at": now, "sent_at": None}
    with _mem:
        _campaigns[camp["id"]] = camp
    return dict(camp)


def set_campaign(cid: int, **fields) -> None:
    fields = {k: v for k, v in fields.items() if k in ("status", "sent", "failed", "sent_at", "segment")}
    with _mem:
        if cid not in _campaigns or not fields:
            return
        _campaigns[cid].update(fields)
    sets = ", ".join(f"{k} = ?" for k in fields)
    write(f"UPDATE campaigns SET {sets} WHERE id = ?", (*fields.values(), cid))


def delete_campaign(cid: int) -> None:
    with _mem:
        _campaigns.pop(cid, None)
        for key in [k for k in _ad_clicks if k[0] == cid]:
            _ad_clicks.discard(key)
    write("DELETE FROM campaigns WHERE id = ?", (cid,))
    write("DELETE FROM ad_clicks WHERE campaign = ?", (cid,))


def ad_click(cid: int, chat: int) -> None:
    with _mem:
        if (cid, chat) in _ad_clicks or cid not in _campaigns:
            return
        _ad_clicks.add((cid, chat))
        _campaigns[cid]["clicks"] += 1
    write("INSERT INTO ad_clicks (campaign, chat, created_at) VALUES (?, ?, ?) ON CONFLICT (campaign, chat) DO NOTHING",
          (cid, chat, int(time.time())))
    write("UPDATE campaigns SET clicks = clicks + 1 WHERE id = ?", (cid,))
