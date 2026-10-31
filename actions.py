"""Действия с подписками, общие для бота и мини-приложения, и фоновые задачи."""
from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Dict, Optional, Tuple

import checker
import config
import dgt
import premium
import radar
import rewards
import store
import tg
import views

log = logging.getLogger("actions")

jobs = ThreadPoolExecutor(max_workers=4, thread_name_prefix="job")  # проверки по кнопке, загрузка услуг
_locks: Dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()
AREA_RE = re.compile(r"^[A-Z0-9]{2,8}$")


def chat_lock(chat: int) -> threading.Lock:
    """Действия одного пользователя выполняются по очереди: двойное нажатие не создаст дублей."""
    with _locks_guard:
        return _locks.setdefault(chat, threading.Lock())


def valid_iso(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return len(value) == 10
    except (TypeError, ValueError):
        return False


def office_options(cid: str, allow_fetch: bool = True) -> Optional[list]:
    """Типы записи офиса: из кэша, при необходимости с сайта. None — получить не удалось."""
    return radar.office_areas(cid) or None if allow_fetch else (store.office_areas(cid) or (0, None))[1]


def add_subscription(chat: int, cid: str, area: str) -> Tuple[str, Optional[dict]]:
    """Статус: ok | exists | limit | full | bad."""
    if cid not in dgt.CENTROS or not AREA_RE.match(area or ""):
        return "bad", None
    mine = store.subs_of(chat)
    same = next((s for s in mine if s["centro"] == cid and s["area"] == area), None)
    if same:
        return "exists", same
    open_subs = [s for s in mine if not s.get("booked_date")]
    if premium.active_subs_count(chat) >= premium.limit_subs(chat) or len(open_subs) >= int(store.setting("max_subs")):
        return "limit", None
    keys = store.active_keys()
    if (cid, area) not in keys and len(keys) >= config.MAX_OFFICES:
        return "full", None
    sub, _ = store.add_sub(chat, cid, area, dgt.AREA_LABELS.get(area, area))
    store.bump("subs")
    checker.event(f"➕ Подписка: {views.plain_title(sub)} ({store.get_chat(chat).get('name') or chat})", "user")
    after_subscribed(chat)
    return "ok", sub


def after_subscribed(chat: int) -> None:
    rewards.complete_builtin(chat, "b:sub")
    inviter = rewards.try_activate_friend(chat)
    if inviter:
        notify_inviter(inviter)


def notify_inviter(inviter: int) -> None:
    lang = views.lang_of(inviter)
    tg.send(inviter, views.tx(lang, "🎉 Твой друг выполнил условия! Забери награду в «🎁 Бонусах».",
                              "🎉 Твій друг виконав умови! Забери нагороду в «🎁 Бонусах»."),
            tg.ikb([[tg.btn(views.tx(lang, "🎁 Бонусы", "🎁 Бонуси"), "bn", "success"),
                     tg.btn(views.tx(lang, "✖️ Скрыть", "✖️ Сховати"), "hide")]]))


def set_paused(sub: dict, paused: bool) -> str:
    """Снять с паузы можно, только если есть свободное место по тарифу. Запись на визит снимается отдельно: unbook."""
    if sub.get("booked_date"):
        return "booked"
    if not paused and sub["paused"] and premium.active_subs_count(sub["chat"]) >= premium.limit_subs(sub["chat"]):
        return "limit"
    store.update_sub(sub["id"], paused=1 if paused else 0)
    return "ok"


def unbook(sub: dict) -> bool:
    """Отменяет запись на визит. Нет места по тарифу — подписка остаётся на паузе. True — проверки снова идут."""
    free = premium.active_subs_count(sub["chat"]) < premium.limit_subs(sub["chat"])
    store.update_sub(sub["id"], booked_date=None, booked_time=None, reminded=0, paused=0 if free else 1, alert_msg=None)
    return free


def set_filter(sub: dict, days: int) -> bool:
    if days not in views.FILTER_DAYS:
        return False
    store.update_sub(sub["id"], max_days=days or None)
    return True


def remove_sub(sub: dict) -> None:
    tg.delete(sub["chat"], sub.get("alert_msg"))
    store.delete_sub(sub["id"])


def check_now(sub: dict, target: Optional[Tuple[int, int]] = None) -> None:
    """Проверка одной подписки по просьбе пользователя, в фоне."""
    cards = {sub["chat"]: target} if target else None
    jobs.submit(checker.run_checks, [(sub["centro"], sub["area"])], cards)
