"""Premium: тарифы, лимиты, оплата Telegram Stars, продление и окончание подписки."""
from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Optional, Tuple

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
INVOICE = {  # заголовок счёта и описание: подставляются срок, офисы и интервал проверки
    "ru": ("{days} дней", "До {subs} офисов, проверка каждые {mins} минут, радар без ограничений, мини-приложение, без рекламы."),
    "uk": ("{days} днів", "До {subs} офісів, перевірка кожні {mins} хвилин, радар без обмежень, міні-застосунок, без реклами."),
    "es": ("{days} días", "Hasta {subs} oficinas, revisión cada {mins} minutos, radar sin límites, miniapp y sin publicidad."),
    "en": ("{days} days", "Up to {subs} offices, checks every {mins} minutes, unlimited radar, mini app, no ads."),
}
CHECKOUT = {  # ответ Telegram на оплату: цена изменилась, технические работы
    "ru": ("Цена изменилась. Открой оплату заново.", "Идут технические работы, оплата временно закрыта. Попробуй позже."),
    "uk": ("Ціна змінилася. Відкрий оплату знову.", "Тривають технічні роботи, оплату тимчасово закрито. Спробуй пізніше."),
    "es": ("El precio ha cambiado. Vuelve a abrir el pago.", "Estamos en mantenimiento y los pagos están cerrados. Inténtalo más tarde."),
    "en": ("The price has changed. Open the payment again.", "Maintenance in progress, payments are temporarily closed. Try again later."),
}
GUARANTEE_FROM, GUARANTEE_TO = 7, 14          # возврат первой оплаты: с какого по какой день после неё
_links: Dict[Tuple[str, int, str], str] = {}  # ссылка на оплату живёт долго — не создаём её на каждое нажатие
post_check: Callable[[str, int, int], bool] = lambda payload, chat, amount: False  # подставляет board.py


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


def trial_state(chat: int) -> str:
    """Можно ли начать пробный период: open | off | active | paid | used."""
    if not int(store.setting("trial_hours")):
        return "off"
    if is_premium(chat):
        return "active"
    if store.get_chat(chat).get("paid_at"):
        return "paid"
    return "used" if store.task_is_done("trial", chat) else "open"


def can_trial(chat: int) -> bool:
    return trial_state(chat) == "open"


def start_trial(chat: int, site_down: bool = False) -> str:
    """Пробный Premium: один раз на человека, запись остаётся и после удаления аккаунта.
    Пока идут технические работы не начинаем, иначе дни сгорят без проверок. Статус: ok | down | как в trial_state."""
    state = trial_state(chat)
    if state != "open":
        return state
    if site_down:
        return "down"
    if not store.claim_task("trial", chat):
        return "used"
    store.set_chat(chat, trial_at=int(time.time()))
    grant(chat, int(store.setting("trial_hours")), "trial")
    store.bump("trials")
    return "ok"


def in_trial(chat: int) -> bool:
    """Сейчас идёт пробный период: бонусы поверх него уже считаются обычным Premium."""
    c = store.get_chat(chat)
    at, until = c.get("trial_at") or 0, c.get("premium_until") or 0
    return bool(at) and not c.get("paid_at") and time.time() < until <= at + int(store.setting("trial_hours")) * 3600 + 60


def after_trial(chat: int) -> bool:
    """Premium, который заканчивается сейчас, был пробным: ему нужно другое письмо."""
    c = store.get_chat(chat)
    return bool(c.get("trial_at")) and not c.get("paid_at") and time.time() - c["trial_at"] < 14 * DAY


def guarantee_state(chat: int) -> Optional[str]:
    """Гарантия на первую оплату: wait — неделя ещё идёт, ready — можно вернуть звёзды, None — не действует."""
    c = store.get_chat(chat)
    paid = c.get("paid_at") or 0
    if not paid or store.task_is_done("guarantee", chat):
        return None
    age = time.time() - paid
    if age > GUARANTEE_TO * DAY or (c.get("alerts") or 0) > (c.get("paid_alerts") or 0):
        return None
    if age < GUARANTEE_FROM * DAY:
        return "wait"
    return "ready" if store.subs_of(chat) else None


def use_guarantee(chat: int) -> bool:
    """Возвращает звёзды за первую оплату. Premium снимет on_refund, когда Telegram подтвердит возврат."""
    if guarantee_state(chat) != "ready":
        return False
    if store.get_chat(chat).get("sub_active"):
        cancel(chat)
    ok, _ = refund_last(chat)
    if ok:
        store.claim_task("guarantee", chat)
    return ok


def invoice_link(plan: str, lang: str) -> Optional[str]:
    """Ссылка на оплату. В ней нет данных пользователя: Premium получает тот, кто заплатил."""
    info, price = PLANS[plan], plan_price(plan)
    key = (plan, price, lang)
    if key in _links:
        return _links[key]
    period, about = INVOICE.get(lang, INVOICE["ru"])
    title = f"{config.BRAND} Premium — " + period.format(days=info["days"])
    text = about.format(subs=store.setting("max_subs"), mins=store.setting("interval_premium"))
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
    payload, chat = query.get("invoice_payload") or "", query["from"]["id"]
    plan = plan_of(payload)
    lang = store.get_chat(chat).get("lang") or "ru"
    changed, closed = CHECKOUT.get(lang, CHECKOUT["ru"])
    error = None
    if payload.startswith("post:"):
        if query.get("currency") != "XTR" or not post_check(payload, chat, query.get("total_amount")):
            error = changed
    elif not plan or query.get("currency") != "XTR" or query.get("total_amount") != plan_price(plan):
        error = changed
    elif site_down:
        error = closed
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
    c = store.get_chat(chat)
    if not c.get("paid_at"):
        store.set_chat(chat, paid_at=int(time.time()), paid_alerts=c.get("alerts") or 0)
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
    rows = store.q("SELECT * FROM payments WHERE chat = ? AND refunded = 0 AND plan <> 'post' ORDER BY created_at DESC LIMIT 1", (chat,))
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
