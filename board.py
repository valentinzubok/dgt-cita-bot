"""Объявления в канале: вакансии и услуги. Текст пишут люди, поэтому каждое проходит проверку администратора.
Оплата звёздами, при отказе звёзды возвращаются. Продажа записей запрещена: запись на сайте бесплатна."""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, Optional, Tuple

import channel
import checker
import config
import premium
import store
import tg
import views
from tg import btn, ikb

log = logging.getLogger("board")

KINDS = ("job", "ad")
MIN_LEN, MAX_LEN = 30, 800
MAX_OPEN = 3   # объявлений на проверке у одного человека
LABELS = {"job": "💼 Вакансія · Вакансия · Empleo · Job", "ad": "📣 Реклама · Publicidad · Ad"}
REASONS = ("rules", "contact", "scam")
CONTACT_RE = re.compile(r"@[A-Za-z0-9_]{4,}|t\.me/\S+|https?://\S+|\S+@\S+\.\S+|\+?\d[\d\s().-]{7,}\d")
RESALE_RE = re.compile(r"(прода|куплю|помогу|запиш|vend|sell|buy|compr|consig|conseg|gestion).{0,40}(\bcit[ao]s?\b|\bсит[уыае]?\b|huellas|\btie\b|extranjer)|"
                       r"(\bcit[ao]s?\b|\bсит[уыае]?\b|huellas).{0,40}(€|eur|евро|грн)", re.I)
_prices: Dict[int, Tuple[int, int]] = {}   # объявление → (автор, цена): на проверку оплаты всего 10 секунд


def price(kind: str) -> int:
    return int(store.setting("post_job" if kind == "job" else "post_ad"))


def cost(chat: int, kind: str) -> int:
    """Сколько звёзд стоит объявление. Первая вакансия бесплатна, чтобы канал наполнялся."""
    return 0 if kind == "job" and not store.free_job_used(chat) else price(kind)


def check_text(text: str) -> str:
    """ok | short | long | contact | resale"""
    if len(text) < MIN_LEN:
        return "short"
    if len(text) > MAX_LEN:
        return "long"
    if RESALE_RE.search(text):
        return "resale"
    return "ok" if CONTACT_RE.search(text) else "contact"


def open_count(chat: int) -> int:
    return sum(1 for p in store.posts_of(chat, 20) if p["status"] == "review")


def create(chat: int, kind: str, text: str, photo: Optional[str]) -> dict:
    post = store.add_post(chat, kind, text, photo, cost(chat, kind))
    _prices[post["id"]] = (chat, post["stars"])
    return post


def invoice(post: dict, lang: str) -> Optional[str]:
    title, about = views.post_invoice(lang, post["kind"])
    data = tg.call("createInvoiceLink", title=title, description=about, payload=f"post:{post['id']}", provider_token="",
                   currency="XTR", prices=[{"label": title, "amount": post["stars"]}]) or {}
    return data.get("result")


def check_payment(payload: str, chat: int, amount: int) -> bool:
    """Telegram спрашивает, можно ли принять оплату."""
    pid = payload.partition(":")[2]
    if not pid.isdigit():
        return False
    known = _prices.get(int(pid))
    if known is None:
        post = store.get_post(int(pid))
        known = (post["chat"], post["stars"]) if post and post["status"] == "draft" else None
    return known == (chat, amount)


premium.post_check = check_payment


def to_moderation(post: dict) -> None:
    c = store.get_chat(post["chat"])
    store.set_post(post["id"], status="review")
    _prices.pop(post["id"], None)
    store.bump("posts")
    checker.event(f"📌 Объявление на проверке: {c.get('name') or post['chat']}", "user")
    checker.notify_admins(f"📌 <b>Новое объявление</b> · {LABELS[post['kind']]}\n{views.esc(c.get('name') or str(post['chat']))}"
                          f"{f' · {post_price(post)}' if post['stars'] else ''}\n\n{views.esc(post['text'])}",
                          [[btn("✅ Опубликовать", f"ad:ja:{post['id']}", "success"), btn("🚫 Отклонить", f"ad:jr:{post['id']}", "danger")]],
                          silent=False)


def post_price(post: dict) -> str:
    return f"{post['stars']} ⭐"


def on_paid(msg: dict) -> Optional[dict]:
    """Оплата объявления. Повтор того же платежа игнорируем, за отменённое сразу возвращаем звёзды."""
    pay, chat = msg["successful_payment"], msg["chat"]["id"]
    pid = (pay.get("invoice_payload") or "").partition(":")[2]
    charge = pay["telegram_payment_charge_id"]
    if not store.add_payment(charge, chat, pay["total_amount"], "post", False):
        return None
    store.bump("payments")
    store.bump("stars", pay["total_amount"])
    post = store.get_post(int(pid)) if pid.isdigit() else None
    if not post or post["chat"] != chat or post["status"] != "draft":
        refund(chat, charge)
        log.warning("оплата за недоступное объявление %s", pid)
        return None
    store.set_post(post["id"], charge=charge)
    post["charge"] = charge
    to_moderation(post)
    return post


def refund(chat: int, charge: str) -> bool:
    data = tg.call("refundStarPayment", user_id=chat, telegram_payment_charge_id=charge) or {}
    if not data.get("ok"):
        checker.event(f"⚠️ Не вернулись звёзды за объявление: {chat} ({data.get('description')})", "error")
    return bool(data.get("ok"))


def publish(post: dict) -> bool:
    """Публикует в канале и сообщает автору."""
    text = f"<b>{LABELS[post['kind']]}</b>\n\n{views.esc(post['text'])}\n\n<i>📌 @{config.BOT_USERNAME}</i>"
    mid = channel.publish(text, photo=post.get("photo"))
    if not mid:
        return False
    store.set_post(post["id"], status="published", message=mid, decided_at=int(time.time()))
    store.bump("posts_published")
    lang = views.lang_of(post["chat"])
    tg.send(post["chat"], views.post_published(lang), ikb([[tg.url(views.post_open_btn(lang), channel.link(mid))],
                                                           [btn(views.hide_label(lang), "hide")]]))
    return True


def reject(post: dict, reason: str) -> bool:
    """Отказ. Если объявление было оплачено, звёзды возвращаются. True — всё прошло без ошибок."""
    refunded = refund(post["chat"], post["charge"]) if post.get("charge") else True
    store.set_post(post["id"], status="rejected", reason=reason, decided_at=int(time.time()))
    if post.get("charge") and refunded:
        store.set_refunded(post["charge"])
    lang = views.lang_of(post["chat"])
    tg.send(post["chat"], views.post_rejected(lang, reason, bool(post.get("charge"))),
            ikb([[btn(views.board_btn(lang), "jb"), btn(views.hide_label(lang), "hide")]]))
    return refunded
