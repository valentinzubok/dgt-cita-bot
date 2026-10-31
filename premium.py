"""Premium: тарифы, лимиты, оплата Telegram Stars, продление и окончание подписки."""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import config
import store
import tg

log = logging.getLogger("premium")

DAY = 86400
SUBSCRIPTION_PERIOD = 2592000  # Telegram принимает только 30 дней
PLANS = {
    "p7": {"days": 7, "price": "price_7", "recurring": False},
    "p30": {"days": 30, "price": "price_30", "recurring": True},
    "p90": {"days": 90, "price": "price_90", "recurring": False},
}
BOOKED_EFFECT = "5046509860389126442"  # 🎉
_links: Dict[Tuple[str, int, str], str] = {}  # ссылка на оплату живёт долго — не создаём её на каждое нажатие


def is_premium(chat: int) -> bool:
    return store.is_premium(chat) or chat in config.OWNERS


def plan_price(plan: str) -> int:
    return int(store.setting(PLANS[plan]["price"]))


def limit_subs(chat: int) -> int:
    return int(store.setting("max_subs" if is_premium(chat) else "free_subs"))


def active_subs_count(chat: int) -> int:
    """Занятые места: подписки с записью на визит и на паузе из-за окончания Premium не считаем."""
    return sum(1 for s in store.subs_of(chat) if not s.get("booked_date") and not s["paused"])


def app_url() -> Optional[str]:
    return config.PUBLIC_URL + "/app" if config.PUBLIC_URL else None


def apply_menu_button(chat: int) -> None:
    """Кнопка мини-приложения рядом с полем ввода — только у Premium."""
    url = app_url()
    if url:
        tg.set_menu_button(chat, url if is_premium(chat) else None)


def grant(chat: int, hours: int, reason: str) -> int:
    was = store.is_premium(chat)
    until = store.add_premium(chat, hours * 3600, reason)
    store.bump("premium_hours", hours)
    if not was:
        apply_menu_button(chat)
    return until


def invoice_link(plan: str, lang: str) -> Optional[str]:
    """Ссылка на оплату. В ней нет данных пользователя: Premium получает тот, кто заплатил."""
    info, price = PLANS[plan], plan_price(plan)
    key = (plan, price, lang)
    if key in _links:
        return _links[key]
    days = info["days"]
    if lang == "uk":
        title = f"{config.BRAND} Premium — {days} днів"
        text = "До 10 офісів, перевірка кожні 5 хвилин, радар без обмежень, міні-застосунок, без реклами."
    else:
        title = f"{config.BRAND} Premium — {days} дней"
        text = "До 10 офисов, проверка каждые 5 минут, радар без ограничений, мини-приложение, без рекламы."
    params = {"title": title, "description": text, "payload": f"plan:{plan}", "provider_token": "", "currency": "XTR",
              "prices": [{"label": title, "amount": price}]}
    if info["recurring"]:
        params["subscription_period"] = SUBSCRIPTION_PERIOD
    data = tg.call("createInvoiceLink", **params) or {}
    link = data.get("result")
    if link:
        _links[key] = link
    return link


def plan_of(payload: str) -> Optional[str]:
    plan = (payload or "").partition(":")[2]
    return plan if (payload or "").startswith("plan:") and plan in PLANS else None


def on_pre_checkout(query: dict, site_down: bool) -> None:
    """Telegram даёт 10 секунд на ответ: здесь только проверки в памяти."""
    plan = plan_of(query.get("invoice_payload"))
    lang = store.get_chat(query["from"]["id"]).get("lang") or "ru"
    error = None
    if not plan or query.get("currency") != "XTR" or query.get("total_amount") != plan_price(plan):
        error = "Цена изменилась. Открой оплату заново." if lang == "ru" else "Ціна змінилася. Відкрий оплату знову."
    elif site_down:
        error = ("Сейчас проверки DGT не работают, оплату принимать нечестно. Попробуй позже."
                 if lang == "ru" else "Зараз перевірки DGT не працюють, приймати оплату нечесно. Спробуй пізніше.")
    p = {"pre_checkout_query_id": query["id"], "ok": error is None}
    if error:
        p["error_message"] = error
    tg.call("answerPreCheckoutQuery", _timeout=8, **p)


def on_payment(msg: dict) -> Optional[Tuple[str, int]]:
    """Начисляет Premium за оплату. Повтор того же платежа игнорируется. Возвращает (тариф, звёзд)."""
    pay, chat = msg["successful_payment"], msg["chat"]["id"]
    plan = plan_of(pay.get("invoice_payload"))
    charge = pay["telegram_payment_charge_id"]
    if not plan:
        log.error("оплата с неизвестным тарифом: %s", pay.get("invoice_payload"))
        return None
    recurring = bool(pay.get("is_recurring"))
    if not store.add_payment(charge, chat, pay["total_amount"], plan, recurring):
        return None
    store.add_premium(chat, PLANS[plan]["days"] * DAY, f"pay:{plan}")
    if recurring:
        known = store.get_chat(chat).get("sub_charge")
        store.set_chat(chat, sub_charge=charge if pay.get("is_first_recurring") or not known else known, sub_active=1)
    store.bump("payments")
    store.bump("stars", pay["total_amount"])
    apply_menu_button(chat)
    return plan, pay["total_amount"]


def on_refund(msg: dict) -> None:
    pay, chat = msg["refunded_payment"], msg["chat"]["id"]
    charge = pay["telegram_payment_charge_id"]
    row = store.payment(charge)
    if not row or row["refunded"]:
        return
    store.set_refunded(charge)
    plan = plan_of(pay.get("invoice_payload")) or row["plan"]
    if plan in PLANS:
        store.add_premium(chat, -PLANS[plan]["days"] * DAY, f"refund:{plan}")
    if store.get_chat(chat).get("sub_charge") == charge:
        store.set_chat(chat, sub_active=0, sub_charge=None)
    apply_menu_button(chat)


def on_subscription_update(update: dict) -> Optional[str]:
    """Изменение подписки со стороны Telegram: отмена или неудачное продление."""
    chat, state = update.get("user", {}).get("id"), update.get("state")
    if not chat:
        return None
    if state == "active":
        store.set_chat(chat, sub_active=1)
    elif state in ("canceled", "failed"):
        store.set_chat(chat, sub_active=0)
    return state


def cancel(chat: int) -> bool:
    charge = store.get_chat(chat).get("sub_charge")
    if not charge:
        return False
    data = tg.call("editUserStarSubscription", user_id=chat, telegram_payment_charge_id=charge, is_canceled=True) or {}
    if data.get("ok"):
        store.set_chat(chat, sub_active=0)
    return bool(data.get("ok"))


def refund_last(chat: int) -> Tuple[bool, str]:
    rows = store.q("SELECT * FROM payments WHERE chat = ? AND refunded = 0 ORDER BY created_at DESC LIMIT 1", (chat,))
    if not rows:
        return False, "Нет оплат для возврата"
    data = tg.call("refundStarPayment", user_id=chat, telegram_payment_charge_id=rows[0]["charge_id"]) or {}
    if not data.get("ok"):
        return False, data.get("description") or "Telegram отказал"
    store.bump("refunds")
    return True, f"Возвращено {rows[0]['stars']} ⭐"


def expired_cleanup(chat: int) -> int:
    """Premium закончился: остаются работать первые офисы в пределах бесплатного лимита. Возвращает, сколько на паузе."""
    keep = int(store.setting("free_subs"))
    paused = 0
    for s in store.subs_of(chat):
        if s["paused"] or s.get("booked_date"):
            continue
        if keep > 0:
            keep -= 1
        else:
            store.update_sub(s["id"], paused=1)
            paused += 1
    apply_menu_button(chat)
    return paused


def scan_expiring() -> list:
    """Кому пора написать: [(chat, 'soon'|'over', дата окончания)]. Подписка с автопродлением получает час запаса."""
    now, out = time.time(), []
    for c in store.all_chats():
        until = c.get("premium_until") or 0
        if not until or c["chat"] in config.OWNERS:
            continue
        notice = c.get("prem_notice") or 0
        if until <= now - (3600 if c.get("sub_active") else 0) and not notice & 2:
            store.set_chat(c["chat"], prem_notice=notice | 3, sub_active=0)
            out.append((c["chat"], "over", until))
        elif now < until < now + DAY and not notice & 1 and not c.get("sub_active"):
            store.set_chat(c["chat"], prem_notice=notice | 1)
            out.append((c["chat"], "soon", until))
    return out
