"""Обязательная подписка на канал. Пока человек не подписан, бот и мини-приложение показывают один экран: «подпишись».

Подписку проверяем через getChatMember и запоминаем: подписан — на 6 часов, не подписан — на 15 секунд.
Telegram сам сообщает о вступлении и выходе из канала (апдейт chat_member), поэтому экран открывается сразу,
без кнопки «Я подписался». Если Telegram не ответил, людей не запираем: сбой не должен ломать бота."""
from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Optional, Tuple

import rewards
import store
import views

log = logging.getLogger("gate")

OK_TTL = 6 * 3600
NO_TTL = 15
NUDGE_GAP = 24 * 3600   # «уведомление не пришло» — не чаще раза в сутки
_cache: Dict[int, Tuple[bool, float]] = {}
_nudged: Dict[int, float] = {}
waiting: Dict[int, int] = {}   # кто сейчас смотрит на экран «подпишись»: чат → номер сообщения
on_joined: Callable[[int, int], None] = lambda chat, mid: None  # подставляет bot.py: открыть меню вместо экрана подписки


def channel() -> str:
    """Канал, на который нужно подписаться. Пусто — подписка не обязательна."""
    return str(store.setting("channel") or "") if store.setting("gate") else ""


def allowed(chat: int, fresh: bool = False) -> bool:
    """Можно ли пользоваться ботом. Админов пропускаем всегда."""
    target = channel()
    if not target or views.is_admin(chat):
        return True
    now = time.time()
    hit = _cache.get(chat)
    if hit and not fresh and now - hit[1] < (OK_TTL if hit[0] else NO_TTL):
        return hit[0]
    member = rewards.is_member(target, chat)
    if member is None:
        return True
    _cache[chat] = (member, now)
    return member


def ours(chat: dict) -> bool:
    target = channel().lstrip("@").lower()
    return bool(target) and (str(chat.get("username") or "").lower() == target or str(chat.get("id")) == target)


def on_member(update: dict) -> None:
    """Кто-то вступил в канал или вышел из него."""
    if not ours(update.get("chat") or {}):
        return
    new = update.get("new_chat_member") or {}
    user = (new.get("user") or {}).get("id")
    if not user:
        return
    joined = new.get("status") in rewards.MEMBER or (new.get("status") == "restricted" and bool(new.get("is_member")))
    _cache[user] = (joined, time.time())
    if not joined:
        store.bump("channel_left")
        return
    store.bump("channel_joined")
    mid = waiting.pop(user, None)
    if mid:
        store.bump("gate_joined")
        on_joined(user, mid)


def shown(chat: int, mid: Optional[int]) -> None:
    if mid:
        waiting[chat] = mid
    store.bump("gate_shown")


def nudge_due(chat: int) -> bool:
    """Уведомление не отправили, потому что человек вышел из канала. Сказать об этом — раз в сутки."""
    now = time.time()
    if now - _nudged.get(chat, 0) < NUDGE_GAP:
        return False
    _nudged[chat] = now
    return True


def forget(chat: int) -> None:
    _cache.pop(chat, None)
    waiting.pop(chat, None)
