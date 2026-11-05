"""Hour Star — второй бот автора: учёт рабочих часов и заработка. OkSita рекламирует его в меню, «Полезном»,
мини-приложении, на сайте, в канале и в рекламе по согласию. Имя бота задаёт админ: Админ → Канал → ⏱ Hour Star.

В ссылке метка места (?start=oksita_menu), по ней Hour Star видит, откуда пришёл человек.
Обратно люди приходят по ?start=hourstar или ?start=раздел-hourstar — это метка источника, её видно в аналитике."""
from __future__ import annotations

import re
from typing import Optional

import store

NAME = "Hour Star"
IMAGE = "post_hourstar.jpg"
TAG = "hourstar"  # метка источника для тех, кто пришёл из Hour Star
NAME_RE = re.compile(r"(?:https?://)?(?:t\.me/|@)?([A-Za-z][A-Za-z0-9_]{4,31})/?")


def username() -> str:
    return (store.setting("hourstar_bot") or "").lstrip("@")


def ready() -> bool:
    return bool(username()) and bool(store.setting("hourstar"))


def link(place: str) -> Optional[str]:
    if not ready():
        return None
    return f"https://t.me/{username()}?start=oksita_{place}"


def parse(text: str) -> Optional[str]:
    """«@HourStarBot», «t.me/HourStarBot» или просто имя → имя бота. У ботов Telegram имя всегда оканчивается на bot."""
    m = NAME_RE.fullmatch(text.strip())
    if not m or not m.group(1).lower().endswith("bot"):
        return None
    return m.group(1)


def came_from(c: dict) -> bool:
    source = c.get("source") or ""
    return source == TAG or source.endswith("-" + TAG)


def arrived() -> int:
    return sum(1 for c in store.all_chats() if came_from(c))


def seen() -> None:
    store.bump("hourstar_views")
