"""Отзывы после визита: оценка от 1 до 5 и, по желанию, пара слов.

Бот спрашивает на следующий день после визита. Публично (в канале и на сайте) отзыв появляется только если человек
сам разрешил и админ проверил текст. Имя не показываем: только город и вид записи. Низкую оценку видит только админ."""
from __future__ import annotations

import time
from datetime import date, datetime
from typing import List, Optional, Tuple

import config
import store
import views

MAX_TEXT = 300
ASK_HOUR = 11      # спрашиваем на следующий день после визита, не раньше 11:00
ASK_DAYS = 3       # и не позже чем через 3 дня: о старых визитах не спрашиваем
PUBLIC_MIN = 3     # средняя оценка на сайте — только когда отзывов хотя бы столько


def ask_due(sub: dict, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(config.TZ)
    if not sub.get("booked_date") or (sub.get("reminded") or 0) & 4:
        return False
    days = (now.date() - date.fromisoformat(sub["booked_date"])).days
    return 1 <= days <= ASK_DAYS and now.hour >= ASK_HOUR


def rate(chat: int, sub: Optional[dict], stars: int) -> dict:
    """Оценка. Одна на визит: повторное нажатие меняет её."""
    old = store.review_of_sub(sub["id"]) if sub else None
    if old and old["chat"] == chat:
        store.set_review(old["id"], stars=stars)
        return store.get_review(old["id"])
    store.bump("reviews")
    return store.add_review(chat, sub["id"] if sub else None, sub["centro"] if sub else None, views.sub_area(sub) if sub else None, stars)


def clean(text: str) -> Optional[str]:
    """Текст отзыва: без контактов и ссылок, до 300 символов."""
    import board  # board тянет за собой checker
    text = " ".join(text.split())[:MAX_TEXT]
    if len(text) < 3 or board.CONTACT_RE.search(text) or board.RESALE_RE.search(text):
        return None
    return text


def summary() -> Tuple[float, int]:
    rated = [r["stars"] for r in store.reviews()]
    return (round(sum(rated) / len(rated), 1) if rated else 0.0), len(rated)


def public(limit: int = 6) -> List[dict]:
    """Отзывы для сайта и канала: с согласием, проверенные админом, с текстом."""
    return [r for r in store.reviews() if r["consent"] and r["status"] == "approved" and r.get("text")][:limit]


def place(r: dict) -> str:
    city = views.city(r["centro"]) if r.get("centro") else ""
    return " · ".join(x for x in (city, r.get("area") or "") if x)


def post_text(r: dict) -> str:
    return (f"{'⭐' * r['stars']}\n\n<i>«{views.esc(r['text'])}»</i>\n\n"
            f"📍 {views.esc(place(r))}\n\n"
            "🇺🇦 Відгук після запису через бота · 🇷🇺 Отзыв после записи через бота\n"
            f"<i>⚡️ @{config.BOT_USERNAME}</i>")


def age(r: dict) -> int:
    return int((time.time() - r["created_at"]) // 86400)
