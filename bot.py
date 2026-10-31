"""OkSita — Telegram-бот: уведомления о свободных датах cita previa DGT.

На Render работает через webhook, локально — через long polling. Веб-часть — в webapp.py.
"""
from __future__ import annotations

import config  # noqa: F401 — первым: читает .env до остальных модулей

import hashlib
import logging
import math
import os
import re
import signal
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional, Tuple

import actions
import admin
import board
import channel
import checker
import dgt
import premium
import radar
import rewards
import signals
import store
import tg
import views
import webapp
from tg import btn, ikb
from views import tx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

SECTIONS = ("trial", "post", "partner", "stats", "tie")  # разделы с прямыми ссылками ?start=… и командами
opens: Dict[int, str] = {}  # раздел из ссылки: откроется после выбора языка
LEGACY_BUTTONS = {"➕ Добавить офис": "/add", "📋 Мои подписки": "/list", "🔄 Проверить сейчас": "/check",
                  "⚙️ Настройки": "/settings", "❓ Помощь": "/help"}  # кнопки под полем ввода из первой версии
ALLOWED_UPDATES = ["message", "callback_query", "pre_checkout_query", "subscription"]
pool = ThreadPoolExecutor(max_workers=12, thread_name_prefix="update")
last_manual: Dict[int, float] = {}
told_banned: set = set()
mode: Dict[int, str] = {}      # «radar» — пользователь выбирает офис для радара
waiting: Dict[int, dict] = {}  # ждём от пользователя текст: дату визита, промокод, вопрос по оплате
notes: Dict[int, tuple] = {}   # что показать после выбора языка
_seen: deque = deque(maxlen=5000)
_seen_set: set = set()
_flood: Dict[int, deque] = {}


# ---------- действия ----------

def home(chat: int, mid: Optional[int] = None, note: str = "") -> None:
    mode.pop(chat, None)
    waiting.pop(chat, None)
    c = store.get_chat(chat)
    if not c.get("lang"):
        tg.show(chat, *views.language_picker(), mid=mid, banner=views.banner())
        return
    tg.show(chat, *views.dashboard(chat, c.get("name") or "", checker.next_check_for(chat), note), mid=mid,
            banner=views.banner())


def refresh_screen(chat: int) -> None:
    """Язык сменили в мини-приложении: открытый экран в чате переводим сразу."""
    screen = store.get_chat(chat).get("screen")
    if screen:
        with actions.chat_lock(chat):
            home(chat, screen)


def search(chat: int, query: str, token: int) -> None:
    q = views.fold(query.strip())[:60]
    found = [c for c in dgt.CENTROS if q and q in views.fold(dgt.CENTROS[c])]
    prefix, pager = ("rb", "rp") if mode.get(chat) == "radar" else ("c", "p")
    if len(found) == 1:
        if prefix == "rb":
            tg.show(chat, *views.radar_categories(chat, found[0]))
        else:
            open_office(chat, found[0], None, token)
    elif 1 < len(found) <= views.PAGE:
        tg.show(chat, *views.search_results(chat, query, found, prefix, pager))
    else:
        header = views.too_many(chat) if found else views.not_found(chat, query[:60])
        tg.show(chat, *views.offices(chat, 0, header, prefix, pager))


def open_office(chat: int, cid: str, mid: Optional[int], token: int) -> None:
    """Типы записи офиса. У каждого офиса они свои, поэтому берём с сайта (и кэшируем на 3 дня)."""
    mode.pop(chat, None)
    cached = store.office_areas(cid)
    if cached and time.time() - cached[0] < radar.AREAS_TTL:
        tg.show(chat, *views.areas(chat, cid, cached[1]), mid=mid)
        return
    lang = views.lang_of(chat)
    if checker.site_down():
        tg.show(chat, *(views.areas(chat, cid, cached[1]) if cached else views.areas_error(chat, cid, f"c:{cid}")), mid=mid)
        return
    mid = tg.show(chat, *views.loading(tx(lang, "Загружаю услуги офиса ", "Завантажую послуги офісу ",
                                                "Cargando los servicios de la oficina ",
                                                "Loading services for the office ")
                                       + f"<b>{views.esc(views.city(cid))}</b>…"), mid=mid)

    def job() -> None:
        options = radar.office_areas(cid)
        if tg.same_screen(chat, token):
            tg.show(chat, *(views.areas(chat, cid, options) if options else views.areas_error(chat, cid, f"c:{cid}")), mid=mid)

    actions.jobs.submit(job)


def subscribe(chat: int, mid: int, cid: str, area: str, token: int) -> Optional[str]:
    lang = views.lang_of(chat)
    first = not store.task_is_done("b:sub", chat)
    status, sub = actions.add_subscription(chat, cid, area)
    if status == "exists":
        tg.show(chat, *views.card(sub, tx(lang, "ℹ️ <i>Ты уже следишь за этим офисом.</i>",
                                          "ℹ️ <i>Ти вже стежиш за цим офісом.</i>",
                                                "ℹ️ <i>Ya sigues esta oficina.</i>",
                                                "ℹ️ <i>You're already tracking this office.</i>")), mid=mid)
    elif status == "limit":
        tg.show(chat, *views.limit_view(chat), mid=mid)
    elif status == "full":
        tg.show(chat, tx(lang, "😅 Бот сейчас следит за максимальным числом офисов. Попробуй позже.",
                         "😅 Бот зараз стежить за максимальною кількістю офісів. Спробуй пізніше.",
                               "😅 El bot ya sigue el número máximo de oficinas. Inténtalo más tarde.",
                               "😅 The bot is tracking the maximum number of offices right now. Try again later."),
                ikb([[views.home_btn(lang)]]), mid=mid)
    elif status == "ok":
        if checker.site_down():
            tg.show(chat, *views.card(sub), mid=mid)
        else:
            mid = tg.show(chat, tx(lang, "✅ <b>Подписка оформлена</b>\n", "✅ <b>Підписку оформлено</b>\n",
                                         "✅ <b>Oficina añadida</b>\n",
                                         "✅ <b>Office added</b>\n")
                          + f"🏢 {views.title(sub)}\n\n"
                          + tx(lang, "⏳ Делаю первую проверку — около минуты…", "⏳ Роблю першу перевірку — близько хвилини…",
                                     "⏳ Hago la primera revisión, cerca de un minuto…",
                                     "⏳ Running the first check, about a minute…"),
                          ikb([]), mid=mid)
            actions.check_now(sub, (mid, token))
        if first:
            return tx(lang, "🎁 +6 ч Premium за первый офис", "🎁 +6 год Premium за перший офіс",
                            "🎁 +6 h de Premium por la primera oficina",
                            "🎁 +6 h of Premium for your first office")
    return None


def manual_wait(chat: int, lang: str) -> Optional[str]:
    """Подсказка, если ручная проверка пока недоступна. Бесплатно — не чаще обычной, иначе кнопка обходит лимит."""
    gap = 60 if premium.is_premium(chat) else int(store.setting("interval")) * 60
    left = last_manual.get(chat, 0) + gap - time.time()
    if left > 0:
        minutes = math.ceil(left / 60)
        return tx(lang, f"⏳ Следующая ручная проверка через {minutes} мин", f"⏳ Наступна ручна перевірка за {minutes} хв",
                        f"⏳ La próxima revisión manual, en {minutes} min",
                        f"⏳ Next manual check in {minutes} min")
    last_manual[chat] = time.time()
    return None


def check_all(chat: int, mid: Optional[int], token: int) -> Optional[str]:
    lang = views.lang_of(chat)
    subs = store.subs_of(chat)
    keys = sorted({(s["centro"], s["area"]) for s in subs if not s["paused"]})
    if not keys:
        return tx(lang, "Все подписки на паузе", "Усі підписки на паузі",
                        "Todas las oficinas están en pausa",
                        "All offices are paused") if subs else \
            tx(lang, "Сначала добавь офис", "Спочатку додай офіс", "Primero añade una oficina", "Add an office first")
    if checker.site_down():
        return tx(lang, "🛠 Идут технические работы", "🛠 Тривають технічні роботи",
                        "🛠 Estamos en mantenimiento",
                        "🛠 Maintenance in progress")
    wait = manual_wait(chat, lang)
    if wait:
        return wait
    mins = max(1, round(len(keys) * 25 / 60))
    offices = views.pl(lang, len(keys), ("офис", "офиса", "офисов"), ("офіс", "офіси", "офісів"), ("oficina", "oficinas"), ("office", "offices"))
    mid = tg.show(chat, *views.dashboard(chat, "", None, tx(lang, f"🔄 <b>Проверяю {offices}…</b> около {mins} мин",
                                                              f"🔄 <b>Перевіряю {offices}…</b> близько {mins} хв",
                                                                  f"🔄 <b>Revisando {offices}…</b> unos {mins} min",
                                                                  f"🔄 <b>Checking {offices}…</b> about {mins} min")),
                  mid=mid, banner=views.banner())

    def job() -> None:
        checker.run_checks(keys)
        if tg.same_screen(chat, token):
            home(chat, mid, tx(lang, "✅ <b>Проверка завершена</b>", "✅ <b>Перевірку завершено</b>",
                                     "✅ <b>Revisión terminada</b>",
                                     "✅ <b>Check finished</b>"))

    actions.jobs.submit(job)
    return None


def save_booking(chat: int, mid: Optional[int], sub: dict, iso: str, hhmm: Optional[str]) -> None:
    actions.book(sub, iso, hhmm)
    tg.show(chat, *views.card(store.get_sub(sub["id"])), mid=mid)


DATE_RE = re.compile(r"(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?(?:\s+(\d{1,2})[:.](\d{2}))?")


def parse_booking(text: str) -> Optional[Tuple[str, Optional[str]]]:
    m = DATE_RE.search(text)
    if not m:
        return None
    d, mo, y, hh, mm = m.groups()
    today = datetime.now(config.TZ).date()
    try:
        year = int(y) + (2000 if y and len(y) == 2 else 0) if y else today.year
        day = date(year, int(mo), int(d))
        if not y and (today - day).days > 30:
            day = date(year + 1, int(mo), int(d))
    except ValueError:
        return None
    hhmm = f"{int(hh):02d}:{mm}" if hh and int(hh) < 24 and int(mm) < 60 else None
    return day.isoformat(), hhmm


def on_new_user(chat: int, c: dict) -> None:
    who = admin.uname(c) + (f" · источник <code>{views.esc(c['source'])}</code>" if c.get("source") else "")
    store.bump("new_users")
    checker.event(f"👤 Новый пользователь: {c.get('name') or chat}", "user")
    if views.is_admin(chat):
        return
    card = [btn("👤 Карточка", f"ad:uc:{chat}")]
    if store.setting("access") == "approval":
        store.set_chat(chat, role="pending")
        checker.notify_admins(f"🙋 <b>Заявка на доступ</b>\n{who} · <code>{chat}</code>",
                              [[btn("✅ Одобрить", f"ad:ap:{chat}"), btn("🚫 Отклонить", f"ad:ar:{chat}")], card],
                              silent=False)
    elif store.setting("notify_new"):
        checker.notify_admins(f"👤 <b>Новый пользователь</b>\n{who}", [card])


def handle_start_arg(chat: int, arg: str, is_new: bool) -> None:
    """Пригласительная ссылка (r_…), промо-ссылка (promo_…) или метка рекламного источника."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", arg):
        return
    if arg in SECTIONS:
        opens[chat] = arg
        if is_new:
            store.set_chat(chat, source=arg)
    elif arg.startswith("promo_"):
        status, hours = rewards.apply_promo(chat, arg[6:])
        notes[chat] = ("promo", status, hours)
        if is_new:
            store.set_chat(chat, source=arg[:40])
    elif arg.startswith("r_"):
        if is_new and rewards.attach_referrer(chat, arg[2:]):
            store.set_chat(chat, source="ref")
            notes[chat] = ("ref",)
    elif is_new:
        store.set_chat(chat, source=arg[:40])


def open_section(chat: int, section: str, mid: Optional[int] = None) -> None:
    """Раздел по прямой ссылке или команде."""
    if section == "trial":
        tg.show(chat, *views.trial_view(chat), mid=mid, banner=views.banner("trial"))
    elif section == "post":
        tg.show(chat, *views.board_view(chat), mid=mid, banner=views.banner("board"))
    elif section == "partner":
        waiting[chat] = {"kind": "partner"}
        tg.show(chat, *views.partner_view(chat), mid=mid, banner=views.banner("board"))
    elif section == "stats":
        tg.show(chat, *views.stats_view(chat), mid=mid)
    elif section == "tie":
        tg.show(chat, *views.tie_guide(chat), mid=mid, banner=views.banner("docs"))


def consume_note(chat: int) -> str:
    note = notes.pop(chat, None)
    lang = views.lang_of(chat)
    if not note:
        return ""
    return views.ref_welcome(lang) if note[0] == "ref" else views.promo_result(lang, note[1], note[2])


# ---------- обработчики ----------

def on_message(msg: dict) -> None:
    chat_info = msg.get("chat") or {}
    if chat_info.get("type") != "private":
        return
    chat = chat_info["id"]
    frm = msg.get("from") or {}
    c, is_new = store.touch_chat(chat, str(frm.get("first_name") or "")[:64], str(frm.get("username") or "")[:64])
    if msg.get("successful_payment"):
        return on_paid(msg)
    if msg.get("refunded_payment"):
        premium.on_refund(msg)
        store.bump("refunds")
        checker.event(f"💸 Возврат: {c.get('name') or chat}", "money")
        return None
    text = (msg.get("text") or "").strip()
    if text.startswith("/start "):
        handle_start_arg(chat, text[7:].strip(), is_new)
        c = store.get_chat(chat)
    if is_new:
        on_new_user(chat, c)
        c = store.get_chat(chat)
    if views.is_admin(chat) and admin.handle_input(msg):
        return None

    tg.call("deleteMessage", chat_id=chat, message_id=msg["message_id"])  # чат остаётся чистым
    lang = c.get("lang") or "ru"
    token = tg.navigate(chat)
    if not views.is_admin(chat):
        if c.get("role") == "banned":
            if chat not in told_banned:
                told_banned.add(chat)
                tg.show(chat, *views.banned_view(lang))
            return None
        if c.get("role") == "pending":
            tg.show(chat, *views.pending_view(lang))
            return None
        if store.setting("maintenance"):
            tg.show(chat, *views.maintenance_view(lang), banner=views.banner())
            return None

    if text in LEGACY_BUTTONS or text.startswith("/start"):
        tg.remove_reply_keyboard(chat)
        text = LEGACY_BUTTONS.get(text, text)
    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        waiting.pop(chat, None)
    else:
        cmd, arg = "", text

    if not c.get("lang") and cmd != "/lang":
        tg.show(chat, *views.language_picker(), banner=views.banner())
        return None

    w = waiting.get(chat)
    if w and w["kind"] == "post" and not cmd:
        return on_post_text(chat, lang, w, text or (msg.get("caption") or "").strip(), msg)
    if w and not cmd and text:
        return on_waited_text(chat, c, lang, w, text)

    if cmd in ("/start", "/menu"):
        section = opens.pop(chat, None)
        open_section(chat, section) if section else home(chat, note=consume_note(chat))
    elif cmd[1:] in SECTIONS:
        open_section(chat, cmd[1:])
    elif cmd in ("/add", "/centros"):
        mode.pop(chat, None)
        search(chat, arg, token) if arg.strip() else tg.show(chat, *views.offices(chat, 0))
    elif cmd == "/radar":
        mode[chat] = "radar"
        tg.show(chat, *views.radar_start(chat), banner=views.banner("radar"))
    elif cmd == "/list":
        tg.show(chat, *views.subs_list(chat))
    elif cmd == "/check":
        note = check_all(chat, None, token)
        if note:
            home(chat, note=note)
    elif cmd == "/premium":
        tg.show(chat, *views.premium_view(chat), banner=views.banner("premium"))
    elif cmd == "/bonus":
        tg.show(chat, *views.bonus_view(chat), banner=views.banner("bonus"))
    elif cmd == "/docs":
        tg.show(chat, *views.docs_view(chat), banner=views.banner("docs"))
    elif cmd == "/promo":
        if arg.strip():
            status, hours = rewards.apply_promo(chat, arg.strip())
            tg.show(chat, *views.premium_view(chat, views.promo_result(lang, status, hours)), banner=views.banner("premium"))
        else:
            waiting[chat] = {"kind": "promo"}
            tg.show(chat, *views.promo_prompt(chat))
    elif cmd == "/settings":
        tg.show(chat, *views.settings_view(chat))
    elif cmd == "/help":
        tg.show(chat, *views.help_view(chat))
    elif cmd == "/terms":
        tg.show(chat, *views.terms_view(chat))
    elif cmd in ("/paysupport", "/support"):
        waiting[chat] = {"kind": "support"}
        tg.show(chat, *views.paysupport_view(chat))
    elif cmd == "/ua":
        tg.show(chat, *views.ukraine_view(chat))
    elif cmd == "/lang":
        tg.show(chat, *views.language_picker(), banner=views.banner())
    elif cmd == "/privacy":
        tg.show(chat, *views.privacy_view(chat))
    elif cmd == "/admin" and views.is_admin(chat):
        tg.show(chat, *admin.panel(), banner=views.banner("admin"))
    elif not cmd and arg:
        search(chat, arg, token)
    else:
        home(chat)
    return None


def on_post_text(chat: int, lang: str, w: dict, text: str, msg: dict) -> None:
    """Текст объявления. Фото не обязательно, берём самое большое."""
    status = board.check_text(text)
    if status != "ok":
        tg.show(chat, views.post_error(lang, status), ikb([[btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), "jb")]]))
        return
    waiting.pop(chat, None)
    photo = (msg.get("photo") or [{}])[-1].get("file_id")
    post = board.create(chat, w["post_kind"], text, photo)
    tg.show(chat, *views.post_preview(chat, post, board.invoice(post, lang) if post["stars"] else None))


def board_action(chat: int, mid: int, kind: str, rest: str, lang: str) -> Tuple[Optional[str], bool]:
    """Объявления: jb — раздел, jn — новое, js — отправить бесплатное, jx — отменить, jm — мои."""
    post = store.get_post(int(rest)) if rest.isdigit() else None
    mine = bool(post) and post["chat"] == chat and post["status"] == "draft"
    if kind == "jb":
        tg.show(chat, *views.board_view(chat), mid=mid, banner=views.banner("board"))
    elif kind == "jn" and rest in board.KINDS:
        if board.open_count(chat) >= board.MAX_OPEN:
            return views.post_error(lang, "many"), True
        waiting[chat] = {"kind": "post", "post_kind": rest}
        tg.show(chat, *views.post_prompt(chat, rest), mid=mid)
    elif kind == "js" and mine and not post["stars"]:
        board.to_moderation(post)
        tg.show(chat, *views.board_view(chat, views.post_sent(lang)), mid=mid, banner=views.banner("board"))
    elif kind == "jx":
        if mine:
            store.set_post(post["id"], status="cancelled")
        tg.show(chat, *views.board_view(chat), mid=mid, banner=views.banner("board"))
    elif kind == "jm":
        tg.show(chat, *views.my_posts(chat), mid=mid)
    return None, False


def on_waited_text(chat: int, c: dict, lang: str, w: dict, text: str) -> None:
    if w["kind"] == "book":
        sub = store.get_sub(w["sid"])
        parsed = parse_booking(text)
        if sub and sub["chat"] == chat and parsed:
            waiting.pop(chat, None)
            save_booking(chat, w["screen"], sub, *parsed)
        elif sub:
            tg.show(chat, tx(lang, "🤔 Не понял дату. Напиши, например, <code>10.10 10:30</code>",
                             "🤔 Не зрозумів дату. Напиши, наприклад, <code>10.10 10:30</code>",
                                   "🤔 No entiendo la fecha. Escribe, por ejemplo, <code>10.10 10:30</code>",
                                   "🤔 I didn't get that date. Try, for example, <code>10.10 10:30</code>"),
                    ikb([[btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), f"bk:{sub['id']}")]]), mid=w["screen"])
    elif w["kind"] == "promo":
        waiting.pop(chat, None)
        status, hours = rewards.apply_promo(chat, text)
        if status == "ok":
            checker.event(f"🎟 Промокод: {text[:32]} ({c.get('name') or chat})", "user")
        tg.show(chat, *views.premium_view(chat, views.promo_result(lang, status, hours)), banner=views.banner("premium"))
    elif w["kind"] == "partner":
        waiting.pop(chat, None)
        checker.event(f"🤝 Заявка партнёра: {c.get('name') or chat}", "user")
        checker.notify_admins(f"🤝 <b>Заявка партнёра</b>\n{admin.uname(c)} · <code>{chat}</code>\n\n{views.esc(text[:1500])}",
                              [[btn("✉️ Ответить", f"ad:um:{chat}"), btn("👤 Карточка", f"ad:uc:{chat}")]], silent=False)
        tg.show(chat, *views.board_view(chat, views.partner_sent(lang)), banner=views.banner("board"))
    elif w["kind"] == "support":
        waiting.pop(chat, None)
        checker.notify_admins(f"💳 <b>Вопрос по оплате</b>\n{admin.uname(c)} · <code>{chat}</code>\n\n{views.esc(text[:1000])}",
                              [[btn("✉️ Ответить", f"ad:um:{chat}"), btn("👤 Карточка", f"ad:uc:{chat}")]], silent=False)
        home(chat, note=tx(lang, "✅ Передал администратору. Ответ придёт сюда.", "✅ Передав адміністратору. Відповідь надійде сюди.",
                                 "✅ Se lo he pasado al administrador. La respuesta llegará aquí.",
                                 "✅ Sent to the administrator. The reply will come here."))


def on_paid(msg: dict) -> None:
    chat = msg["chat"]["id"]
    if (msg["successful_payment"].get("invoice_payload") or "").startswith("post:"):
        if board.on_paid(msg):
            lang = views.lang_of(chat)
            tg.show(chat, *views.board_view(chat, views.post_sent(lang)), banner=views.banner("board"))
        return
    done = premium.on_payment(msg)
    if not done:
        return
    plan, stars = done
    c = store.get_chat(chat)
    lang = c.get("lang") or "ru"
    checker.event(f"💰 Оплата: {c.get('name') or chat} — {plan}, {stars} ⭐", "money")
    checker.notify_admins(f"💰 <b>Оплата</b>\n{admin.uname(c)} — {premium.PLANS[plan]['days']} дн., {stars} ⭐",
                          [[btn("👤 Карточка", f"ad:uc:{chat}")]])
    tg.send(chat, views.thanks_text(lang, plan, c.get("premium_until") or 0), ikb([[views.home_btn(lang)]]),
            effect=premium.BOOKED_EFFECT)


def on_callback(cb: dict) -> None:
    msg = cb.get("message") or {}
    chat, mid, data = (msg.get("chat") or {}).get("id"), msg.get("message_id"), cb.get("data") or ""
    if not chat or not mid:
        return tg.answer(cb["id"])
    toast, popup = None, False
    try:
        toast, popup = route_callback(cb, chat, mid, data)
    except Exception:
        log.exception("ошибка кнопки %s", data[:24])
        lang = views.lang_of(chat)
        toast = tx(lang, "😕 Что-то пошло не так, попробуй ещё раз", "😕 Щось пішло не так, спробуй ще раз",
                         "😕 Algo ha fallado, inténtalo de nuevo",
                         "😕 Something went wrong, try again")
    tg.answer(cb["id"], toast or "", popup)


def route_callback(cb: dict, chat: int, mid: int, data: str) -> Tuple[Optional[str], bool]:
    frm = cb.get("from") or {}
    store.touch_chat(chat, str(frm.get("first_name") or "")[:64], str(frm.get("username") or "")[:64])
    c = store.get_chat(chat)
    if c.get("role") in ("banned", "pending") and not views.is_admin(chat):
        return None, False
    lang = views.lang_of(chat)
    if store.setting("maintenance") and not views.is_admin(chat) and data != "hide":
        tg.show(chat, *views.maintenance_view(lang), mid=mid, banner=views.banner())
        return None, False
    if data == "noop":
        return None, False
    kind, _, rest = data.partition(":")
    token = tg.navigate(chat) if kind != "d" else 0
    if kind != "bo":
        waiting.pop(chat, None)

    if kind == "ad":
        return (admin.on_callback(chat, mid, rest) if views.is_admin(chat) else None), False
    if kind == "lg" and rest[:2] in views.LANGS:
        store.set_chat(chat, lang=rest[:2])
        premium.apply_menu_button(chat)
        if rest.endswith(":st"):
            tg.show(chat, *views.settings_view(chat), mid=mid)
        elif chat in opens:
            open_section(chat, opens.pop(chat), mid)
        else:
            home(chat, mid, consume_note(chat))
    elif data == "lp":
        tg.show(chat, *views.language_picker("st"), mid=mid)
    elif not c.get("lang"):
        tg.show(chat, *views.language_picker(), mid=mid, banner=views.banner())
    elif data == "hide":
        if not (tg.call("deleteMessage", chat_id=chat, message_id=mid) or {}).get("ok"):
            tg.edit(chat, mid, "·")
        if store.get_chat(chat).get("screen") == mid:
            store.set_chat(chat, screen=None)
    elif data == "home":
        home(chat, mid)
    elif kind == "p" and re.fullmatch(r"-?\d{1,3}", rest):
        mode.pop(chat, None)
        tg.show(chat, *views.offices(chat, int(rest)), mid=mid)
    elif kind == "c" and rest in dgt.CENTROS:
        open_office(chat, rest, mid, token)
    elif kind == "a":
        cid, _, area = rest.partition(":")
        return subscribe(chat, mid, cid, area, token), False
    elif data == "rd":
        mode[chat] = "radar"
        tg.show(chat, *views.radar_start(chat), mid=mid, banner=views.banner("radar"))
    elif kind == "rp" and re.fullmatch(r"-?\d{1,3}", rest):
        mode[chat] = "radar"
        tg.show(chat, *views.offices(chat, int(rest), tx(lang, "📡 <b>Радар</b> · от какого офиса искать?",
                                                          "📡 <b>Радар</b> · від якого офісу шукати?",
                                                               "📡 <b>Radar</b> · ¿desde qué oficina busco?",
                                                               "📡 <b>Radar</b> · which office should I search from?"), "rb", "rp"), mid=mid)
    elif kind == "rb" and rest in dgt.CENTROS:
        tg.show(chat, *views.radar_categories(chat, rest), mid=mid)
    elif kind == "rr":
        cid, cat, km = (rest.split(":") + ["", "", ""])[:3]
        if cid in dgt.CENTROS and cat in views.CATS and km.isdigit() and int(km) in radar.RADII:
            mode.pop(chat, None)
            toast = radar.start(chat, mid, cid, cat, int(km), token)
            return toast, bool(toast)
    elif data == "l":
        tg.show(chat, *views.subs_list(chat), mid=mid)
    elif data == "ca":
        return check_all(chat, mid, token), False
    elif data == "st":
        tg.show(chat, *views.settings_view(chat), mid=mid)
    elif data == "hp":
        tg.show(chat, *views.help_view(chat), mid=mid)
    elif data == "ua":
        tg.show(chat, *views.ukraine_view(chat), mid=mid)
    elif data == "tm":
        tg.show(chat, *views.terms_view(chat), mid=mid)
    elif data == "pr":
        tg.show(chat, *views.premium_view(chat), mid=mid, banner=views.banner("premium"))
    elif data == "pc":
        ok = premium.cancel(chat)
        checker.event(f"🚫 Автопродление отключено ({c.get('name') or chat})", "money")
        tg.show(chat, *views.premium_view(chat, tx(lang, "✅ Автопродление отключено. Premium работает до конца срока.",
                                                   "✅ Автопродовження вимкнено. Premium працює до кінця терміну.",
                                                         "✅ Renovación desactivada. Premium sigue activo hasta el final del periodo.",
                                                         "✅ Auto-renewal is off. Premium stays active until the end of the period.") if ok else
                                          tx(lang, "😕 Не получилось отключить, попробуй позже.",
                                             "😕 Не вдалося вимкнути, спробуй пізніше.",
                                                   "😕 No se pudo desactivar, inténtalo más tarde.",
                                                   "😕 Couldn't turn it off, try again later.")), mid=mid, banner=views.banner("premium"))
    elif data == "tr":
        tg.show(chat, *views.trial_view(chat), mid=mid, banner=views.banner("trial"))
    elif data == "tr!":
        status = premium.start_trial(chat, checker.site_down())
        if status == "ok":
            checker.event(f"🎁 Пробный период: {c.get('name') or chat}", "user")
            tg.show(chat, *views.trial_started(chat), mid=mid, banner=views.banner("premium"))
        else:
            tg.show(chat, *views.trial_view(chat, views.trial_note(lang, status)), mid=mid, banner=views.banner("trial"))
    elif data == "gr":
        if premium.guarantee_state(chat) == "ready":
            tg.show(chat, *views.guarantee_confirm(chat), mid=mid)
        else:
            tg.show(chat, *views.premium_view(chat), mid=mid, banner=views.banner("premium"))
    elif data == "gr!":
        ok = premium.use_guarantee(chat)
        checker.event(f"🛡 Гарантия: {c.get('name') or chat}, {'возврат' if ok else 'не вышло'}", "money")
        tg.show(chat, *views.premium_view(chat, views.guarantee_result(lang, ok)), mid=mid, banner=views.banner("premium"))
    elif data == "ost":
        tg.show(chat, *views.stats_view(chat), mid=mid)
    elif data == "pn":
        waiting[chat] = {"kind": "partner"}
        tg.show(chat, *views.partner_view(chat), mid=mid, banner=views.banner("board"))
    elif kind in ("jb", "jn", "js", "jx", "jm"):
        return board_action(chat, mid, kind, rest, lang)
    elif kind == "dg":
        tg.show(chat, *views.tie_guide(chat), mid=mid, banner=views.banner("docs"))
    elif data == "dw":
        tg.show(chat, *views.windows_view(chat), mid=mid)
    elif kind == "dw" and rest.isdigit():
        if signals.toggle_window(chat, int(rest)) == "limit":
            return views.window_limit_note(lang), True
        tg.show(chat, *views.windows_view(chat), mid=mid)
    elif data == "pm":
        waiting[chat] = {"kind": "promo"}
        tg.show(chat, *views.promo_prompt(chat), mid=mid)
    elif data == "bn":
        tg.show(chat, *views.bonus_view(chat), mid=mid, banner=views.banner("bonus"))
    elif data == "bc":
        status, count = rewards.collect(chat)
        note = views.collect_text(lang, status, count)
        if status == "channel":
            return note, True
        tg.show(chat, *views.bonus_view(chat, note), mid=mid, banner=views.banner("bonus"))
    elif kind == "tc" and rest.isdigit():
        return check_task(chat, mid, int(rest), lang), True
    elif kind == "adt":
        on = not c.get("ads_ok")
        actions.set_ads(chat, on)
        tg.show(chat, *(views.bonus_view(chat) if rest == "b" else views.settings_view(chat)), mid=mid,
                banner=views.banner("bonus") if rest == "b" else None)
        return views.ads_note(lang) if on else None, False
    elif data == "noads":
        store.set_chat(chat, ads_ok=0)
        tg.delete(chat, mid)
        return tx(lang, "🔕 Реклама отключена", "🔕 Рекламу вимкнено", "🔕 Publicidad desactivada", "🔕 Ads turned off"), False
    elif data == "q":
        store.set_chat(chat, quiet=0 if c.get("quiet") else 1)
        tg.show(chat, *views.settings_view(chat), mid=mid)
    elif data == "pv":
        tg.show(chat, *views.privacy_view(chat), mid=mid)
    elif data == "dm":
        tg.show(chat, *views.delete_me_confirm(chat), mid=mid)
    elif data == "dm!":
        for s in store.subs_of(chat):
            tg.delete(chat, s.get("alert_msg"))
        premium.cancel(chat)
        store.delete_chat(chat)
        tg.set_menu_button(chat, None)
        checker.event(f"🗑 Пользователь удалил свои данные ({chat})", "user")
        tg.edit(chat, mid, views.deleted_text(lang), ikb([]))
    elif data == "xa":
        tg.show(chat, tx(lang, "🗑 <b>Удалить все подписки?</b>\nУведомления перестанут приходить.",
                         "🗑 <b>Видалити всі підписки?</b>\nСповіщення перестануть надходити.",
                               "🗑 <b>¿Quitar todas las oficinas?</b>\nDejarán de llegar avisos.",
                               "🗑 <b>Remove all offices?</b>\nAlerts will stop."),
                ikb([[btn(tx(lang, "Да, удалить всё", "Так, видалити все", "Sí, quitar todo", "Yes, remove all"), "xa!", "danger"),
                      btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), "st")]]), mid=mid)
    elif data == "xa!":
        for s in store.subs_of(chat):
            tg.delete(chat, s.get("alert_msg"))
        store.forget_chat(chat)
        home(chat, mid, tx(lang, "🗑 Все подписки удалены.", "🗑 Усі підписки видалено.",
                                 "🗑 Se han quitado todas las oficinas.",
                                 "🗑 All offices removed."))
    elif kind in ("s", "r", "h", "f", "fs", "z", "x", "xx", "k", "d", "rs", "bk", "bd", "bt", "bo", "ub"):
        return sub_action(chat, mid, kind, rest, lang, token)
    elif kind in ("dc", "dp", "dt", "dd", "dr", "dx", "dv"):
        return docs_action(chat, mid, kind, rest, lang)
    return None, False


def check_task(chat: int, mid: int, tid: int, lang: str) -> str:
    status, hours = rewards.check_task(chat, tid)
    if status == "ok":
        tg.show(chat, *views.bonus_view(chat, views.reward_text(lang, hours)), mid=mid, banner=views.banner("bonus"))
        actions.after_task(chat)
    return views.task_result(lang, status)


def docs_action(chat: int, mid: int, kind: str, rest: str, lang: str) -> Tuple[Optional[str], bool]:
    """Сигналы о документах. dc — раздел; dp/dt/dd — выбор (s — следить, r — сообщить); dr, dx, dv — действия."""
    parts = rest.split(":")
    screen = lambda note="": tg.show(chat, *views.docs_view(chat, note), mid=mid, banner=views.banner("docs"))  # noqa: E731
    if kind == "dc":
        screen()
    elif kind == "dp" and len(parts) == 2 and parts[0] in ("s", "r") and re.fullmatch(r"-?\d{1,3}", parts[1]):
        tg.show(chat, *views.doc_provinces(chat, parts[0], int(parts[1])), mid=mid)
    elif kind == "dt" and len(parts) == 2 and parts[0] in ("s", "r") and parts[1] in signals.PROVINCES:
        tg.show(chat, *views.doc_types(chat, parts[0], parts[1]), mid=mid)
    elif kind == "dd" and len(parts) == 3 and parts[0] in ("s", "r") and signals.valid(parts[1], parts[2]):
        if parts[0] == "r":
            tg.show(chat, *views.doc_confirm(chat, parts[1], parts[2]), mid=mid)
            return None, False
        status = signals.subscribe(chat, parts[1], parts[2])
        if status == "limit":
            return views.signal_limit(lang), True
        screen(views.signal_added(lang))
    elif kind == "dr" and len(parts) == 2 and signals.valid(parts[0], parts[1]):
        status, sent = actions.report_signal(chat, parts[0], parts[1])
        screen(views.signal_result(lang, status, sent))
    elif kind == "dx" and len(parts) == 2:
        store.del_signal_sub(chat, parts[0], parts[1])
        screen()
    elif kind == "dv" and len(parts) == 2 and parts[0].isdigit() and parts[1] in ("0", "1"):
        sig = store.get_signal(int(parts[0]))
        if not sig or not store.signal_vote(sig["id"], chat, parts[1] == "1"):
            return tx(lang, "Этот сигнал уже закрыт", "Цей сигнал уже закрито",
                            "Esta señal ya está cerrada",
                            "This signal is already closed"), False
        tg.edit(chat, mid, *views.signal_alert(chat, sig, voted=True))
        return tx(lang, "Спасибо!", "Дякую!", "¡Gracias!", "Thanks!"), False
    return None, False


def sub_action(chat: int, mid: int, kind: str, rest: str, lang: str, token: int) -> Tuple[Optional[str], bool]:
    sid, _, extra = rest.partition(":")
    sub = store.get_sub(int(sid)) if sid.isdigit() else None
    if not sub or sub["chat"] != chat:
        tg.show(chat, tx(lang, "Эта подписка уже удалена.", "Цю підписку вже видалено.",
                               "Esta oficina ya se ha quitado.",
                               "This office has already been removed."),
                ikb([[btn(tx(lang, "📋 Мои офисы", "📋 Мої офіси",
                                   "📋 Mis oficinas",
                                   "📋 My offices"), "l"), views.home_btn(lang)]]), mid=mid)
        return None, False
    if kind == "s":
        tg.show(chat, *views.card(sub), mid=mid)
    elif kind == "r":
        if checker.site_down():
            return tx(lang, "🛠 Идут технические работы", "🛠 Тривають технічні роботи",
                            "🛠 Estamos en mantenimiento",
                            "🛠 Maintenance in progress"), False
        wait = manual_wait(chat, lang)
        if wait:
            return wait, False
        tg.show(chat, *views.card(sub, tx(lang, "🔄 <i>Проверяю… около минуты</i>", "🔄 <i>Перевіряю… близько хвилини</i>",
                                                "🔄 <i>Revisando… cerca de un minuto</i>",
                                                "🔄 <i>Checking… about a minute</i>")), mid=mid)
        actions.check_now(sub, (mid, token))
    elif kind == "h":
        tg.show(chat, *views.history_view(sub), mid=mid)
    elif kind == "f":
        tg.show(chat, *views.filter_view(sub), mid=mid)
    elif kind == "fs" and extra.isdigit():
        if actions.set_filter(sub, int(extra)):
            tg.show(chat, *views.card(store.get_sub(sub["id"])), mid=mid)
    elif kind == "z":
        status = actions.set_paused(sub, not sub["paused"])
        if status == "limit":
            tg.show(chat, *views.limit_view(chat), mid=mid)
            return None, False
        tg.show(chat, *views.card(store.get_sub(sub["id"])), mid=mid)
        if status == "booked":
            return None, False
        return (tx(lang, "▶️ Снова слежу", "▶️ Знову стежу", "▶️ Sigo vigilando", "▶️ Watching again") if sub["paused"]
                else tx(lang, "⏸ Подписка на паузе", "⏸ Підписка на паузі", "⏸ Oficina en pausa", "⏸ Office paused")), False
    elif kind == "x":
        tg.show(chat, *views.delete_confirm(sub), mid=mid)
    elif kind == "xx":
        actions.remove_sub(sub)
        tg.show(chat, *views.subs_list(chat, tx(lang, "🗑 Подписка удалена: ", "🗑 Підписку видалено: ",
                                                      "🗑 Oficina quitada: ",
                                                      "🗑 Office removed: ") + views.title(sub)), mid=mid)
    elif kind == "k":
        tg.show(chat, *views.calendar_view(sub, int(extra) if re.fullmatch(r"-?\d{1,3}", extra) else 0), mid=mid)
    elif kind == "d":
        if actions.valid_iso(extra):
            return views.day_popup(sub, extra), True
    elif kind == "rs":
        cats = views.cats_of(views.sub_area(sub))
        cat = "lic" if "lic" in cats else next(iter(cats), "lic")
        toast = radar.start(chat, mid, sub["centro"], cat, 100, token)
        return toast, bool(toast)
    elif kind == "bk":
        if views.all_days(sub.get("last")):
            tg.show(chat, *views.booking_dates(sub), mid=mid)
        else:
            waiting[chat] = {"kind": "book", "sid": sub["id"], "screen": mid}
            tg.show(chat, *views.booking_prompt(sub), mid=mid)
    elif kind == "bd" and actions.valid_iso(extra):
        if views.hours_for(sub.get("last"), extra):
            tg.show(chat, *views.booking_times(sub, extra), mid=mid)
        else:
            save_booking(chat, mid, sub, extra, None)
    elif kind == "bt":
        iso, _, hhmm = extra.partition(":")
        if actions.valid_iso(iso) and re.fullmatch(r"\d{4}|-", hhmm):
            save_booking(chat, mid, sub, iso, f"{hhmm[:2]}:{hhmm[2:]}" if hhmm != "-" else None)
    elif kind == "bo":
        waiting[chat] = {"kind": "book", "sid": sub["id"], "screen": mid}
        tg.show(chat, *views.booking_prompt(sub), mid=mid)
    elif kind == "ub":
        tg.delete(chat, sub.get("alert_msg"))
        note = (tx(lang, "▶️ <i>Снова ищу свободные даты.</i>", "▶️ <i>Знову шукаю вільні дати.</i>",
                         "▶️ <i>Vuelvo a buscar fechas libres.</i>",
                         "▶️ <i>Looking for free dates again.</i>") if actions.unbook(sub) else
                tx(lang, "⏸ <i>Запись отменена. Подписка на паузе: по тарифу нет свободного места.</i>",
                   "⏸ <i>Запис скасовано. Підписка на паузі: за тарифом немає вільного місця.</i>",
                         "⏸ <i>Cita cancelada. La oficina queda en pausa: tu plan no tiene plazas libres.</i>",
                         "⏸ <i>Appointment cancelled. The office stays paused: your plan has no free spot.</i>"))
        tg.show(chat, *views.card(store.get_sub(sub["id"]), note), mid=mid)
    return None, False


def on_subscription(update: dict) -> None:
    state = premium.on_subscription_update(update)
    chat = (update.get("user") or {}).get("id")
    if not chat or state not in ("canceled", "failed"):
        return
    lang = views.lang_of(chat)
    checker.event(f"🔁 Подписка {state}: {store.get_chat(chat).get('name') or chat}", "money")
    if state == "failed":
        tg.send(chat, tx(lang, "😕 Не удалось продлить Premium: не хватило звёзд. Пополни баланс и продли вручную.",
                         "😕 Не вдалося продовжити Premium: не вистачило зірок. Поповни баланс і продовж вручну.",
                               "😕 No se pudo renovar Premium: no había estrellas suficientes. Recarga el saldo y renuévalo a mano.",
                               "😕 Couldn't renew Premium: not enough Stars. Top up your balance and renew manually."),
                ikb([[btn("💎 Premium", "pr", "success"), btn(tx(lang, "✖️ Скрыть", "✖️ Сховати",
                                                                      "✖️ Ocultar",
                                                                      "✖️ Hide"), "hide")]]))


def chat_of(update: dict) -> Optional[int]:
    if "message" in update:
        return (update["message"].get("chat") or {}).get("id")
    if "callback_query" in update:
        return ((update["callback_query"].get("message") or {}).get("chat") or {}).get("id")
    return None


def flooded(chat: int) -> bool:
    """Больше 20 действий за 10 секунд от одного человека — лишние отбрасываем."""
    now = time.time()
    q = _flood.setdefault(chat, deque())
    while q and q[0] < now - 10:
        q.popleft()
    q.append(now)
    return len(q) > 20


def dispatch(update: dict) -> None:
    try:
        if "subscription" in update:
            return on_subscription(update["subscription"])
        chat = chat_of(update)
        if chat is None:
            return None
        payment = "message" in update and (update["message"].get("successful_payment") or update["message"].get("refunded_payment"))
        if flooded(chat) and not payment:
            if "callback_query" in update:
                tg.answer(update["callback_query"]["id"])
            return None
        with actions.chat_lock(chat):
            if "message" in update:
                on_message(update["message"])
            else:
                on_callback(update["callback_query"])
    except Exception:
        log.exception("ошибка обработки апдейта")
    return None


def enqueue(update: dict) -> None:
    """Принимает апдейт от Telegram. Повторы отбрасываем: Telegram мог прислать один и тот же дважды."""
    uid = update.get("update_id")
    if uid is not None:
        if uid in _seen_set:
            return
        if len(_seen) == _seen.maxlen:
            _seen_set.discard(_seen[0])
        _seen.append(uid)
        _seen_set.add(uid)
    if "pre_checkout_query" in update:  # на него есть только 10 секунд — вне общей очереди
        threading.Thread(target=premium.on_pre_checkout, args=(update["pre_checkout_query"], checker.site_down()),
                         daemon=True).start()
    else:
        pool.submit(dispatch, update)


COMMANDS = {
    "ru": [("menu", "🏠 Главное меню"), ("add", "➕ Добавить офис"), ("radar", "📡 Радар — где раньше"),
           ("list", "📋 Мои офисы"), ("docs", "🛂 Документы: TIE, NIE, паспорт"), ("tie", "📋 Как записаться на TIE"),
           ("premium", "💎 Premium"), ("trial", "🎁 Попробовать Premium"), ("bonus", "🎁 Бонусы"), ("stats", "📊 Где чаще появляются места"),
           ("post", "💼 Вакансии и реклама"), ("partner", "🤝 Партнёрам"), ("ua", "🇺🇦 Для украинцев"),
           ("lang", "🌐 Язык"), ("help", "❓ Как это работает"), ("terms", "📄 Условия"),
           ("paysupport", "💳 Поддержка по оплате"), ("privacy", "🔒 Мои данные")],
    "uk": [("menu", "🏠 Головне меню"), ("add", "➕ Додати офіс"), ("radar", "📡 Радар — де швидше"),
           ("list", "📋 Мої офіси"), ("docs", "🛂 Документи: TIE, NIE, паспорт"), ("tie", "📋 Як записатися на TIE"),
           ("premium", "💎 Premium"), ("trial", "🎁 Спробувати Premium"), ("bonus", "🎁 Бонуси"), ("stats", "📊 Де частіше з’являються місця"),
           ("post", "💼 Вакансії та реклама"), ("partner", "🤝 Партнерам"), ("ua", "🇺🇦 Для українців"),
           ("lang", "🌐 Мова"), ("help", "❓ Як це працює"), ("terms", "📄 Умови"),
           ("paysupport", "💳 Підтримка щодо оплати"), ("privacy", "🔒 Мої дані")],
    "es": [("menu", "🏠 Menú principal"), ("add", "➕ Añadir oficina"), ("radar", "📡 Radar: dónde hay cita antes"),
           ("list", "📋 Mis oficinas"), ("docs", "🛂 Documentos: TIE, NIE, pasaporte"), ("tie", "📋 Cómo pedir cita TIE"),
           ("premium", "💎 Premium"), ("trial", "🎁 Probar Premium"), ("bonus", "🎁 Bonos"), ("stats", "📊 Dónde aparecen más plazas"),
           ("post", "💼 Empleo y publicidad"), ("partner", "🤝 Socios"), ("ua", "🇺🇦 Para ucranianos"),
           ("lang", "🌐 Idioma"), ("help", "❓ Cómo funciona"), ("terms", "📄 Condiciones"),
           ("paysupport", "💳 Ayuda con pagos"), ("privacy", "🔒 Mis datos")],
    "en": [("menu", "🏠 Main menu"), ("add", "➕ Add office"), ("radar", "📡 Radar: earliest appointment"),
           ("list", "📋 My offices"), ("docs", "🛂 Documents: TIE, NIE, passport"), ("tie", "📋 How to book a TIE"),
           ("premium", "💎 Premium"), ("trial", "🎁 Try Premium"), ("bonus", "🎁 Bonuses"), ("stats", "📊 Where slots appear most"),
           ("post", "💼 Jobs and ads"), ("partner", "🤝 Partners"), ("ua", "🇺🇦 For Ukrainians"),
           ("lang", "🌐 Language"), ("help", "❓ How it works"), ("terms", "📄 Terms"),
           ("paysupport", "💳 Payment support"), ("privacy", "🔒 My data")],
}
SHORT = {
    "ru": "🔔 Свободные citas DGT (Tráfico) — сразу напишу, когда в твоём офисе появятся даты. Все 68 офисов Испании.",
    "uk": "🔔 Вільні citas DGT (Tráfico) — одразу напишу, щойно у твоєму офісі з’являться дати. Усі 68 офісів Іспанії.",
    "es": "🔔 Citas libres de la DGT (Tráfico): te escribo en cuanto haya fechas en tu oficina. Las 68 oficinas de España.",
    "en": "🔔 Free DGT (Tráfico) appointments: I message you as soon as your office has dates. All 68 offices in Spain.",
}
DESCRIPTION = {
    "ru": (f"🇪🇸 {config.BRAND} следит за записью (cita previa) в DGT — Tráfico — и сразу присылает уведомление, "
           "когда появляются свободные даты.\n\n"
           "✅ все 68 офисов DGT в Испании\n📡 радар: где записаться раньше всего\n"
           "🪪 права, транспорт, экзамены, штрафы\n🗓 календарь со свободным временем\n"
           "🛂 сигналы от людей о записях на TIE, NIE и паспорт\n"
           "⏰ напоминание о визите и что взять с собой\n🇺🇦 памятка для украинцев\n\n"
           "Базовый тариф бесплатный. Бот не связан с DGT. Нажми «Старт» 👇"),
    "uk": (f"🇪🇸 {config.BRAND} стежить за записом (cita previa) у DGT — Tráfico — і одразу надсилає сповіщення, "
           "щойно з’являються вільні дати.\n\n"
           "✅ усі 68 офісів DGT в Іспанії\n📡 радар: де записатися найшвидше\n"
           "🪪 права, транспорт, іспити, штрафи\n🗓 календар із вільним часом\n"
           "🛂 сигнали від людей про записи на TIE, NIE і паспорт\n"
           "⏰ нагадування про візит і що взяти з собою\n🇺🇦 пам’ятка для українців\n\n"
           "Базовий тариф безкоштовний. Бот не пов’язаний з DGT. Натисни «Почати» 👇"),
    "es": (f"🇪🇸 {config.BRAND} vigila las citas previas de la DGT (Tráfico) y te avisa en cuanto aparecen fechas libres.\n\n"
           "✅ las 68 oficinas de la DGT en España\n📡 radar: dónde hay cita antes\n"
           "🪪 permisos, vehículos, exámenes y multas\n🗓 calendario con horas libres\n"
           "🛂 señales de usuarios sobre citas de TIE, NIE y pasaporte\n"
           "⏰ recordatorio de la visita y qué llevar\n🇺🇦 guía para ucranianos\n\n"
           "El plan básico es gratis. El bot no tiene relación con la DGT. Pulsa «Iniciar» 👇"),
    "en": (f"🇪🇸 {config.BRAND} watches DGT (Tráfico) appointments, cita previa, and alerts you as soon as free dates appear.\n\n"
           "✅ all 68 DGT offices in Spain\n📡 radar: where to get the earliest appointment\n"
           "🪪 licences, vehicles, tests and fines\n🗓 calendar with free times\n"
           "🛂 signals from people about TIE, NIE and passport appointments\n"
           "⏰ visit reminders and what to bring\n🇺🇦 guide for Ukrainians\n\n"
           "The basic plan is free. The bot is not affiliated with DGT. Tap “Start” 👇"),
}


def setup_profile() -> None:
    for lang, code in (("en", {}), *((lang, {"language_code": lang}) for lang in config.LANGS)):  # без кода — для всех остальных языков
        tg.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMMANDS[lang]], **code)
        tg.call("setMyShortDescription", short_description=SHORT[lang], **code)
        tg.call("setMyDescription", description=DESCRIPTION[lang], **code)
    for owner in config.OWNERS:  # владельцам — ещё и /admin в меню
        lang = store.get_chat(owner).get("lang") or "ru"
        tg.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMMANDS[lang]]
                + [{"command": "admin", "description": "🛠 Админ-панель"}], scope={"type": "chat", "chat_id": owner})
    photo = (config.ROOT / "assets/avatar.jpg").read_bytes()
    digest = hashlib.sha256(photo).hexdigest()
    if store.setting("avatar_sha") != digest and tg.set_profile_photo(photo):  # только при смене картинки
        store.set_setting("avatar_sha", digest)
    log.info("канал %s: %s", channel.username(), channel.rights())
    for c in store.all_chats():  # кнопка мини-приложения у тех, у кого есть Premium
        if premium.is_premium(c["chat"]):
            premium.apply_menu_button(c["chat"])


def start_background() -> None:
    threading.Thread(target=checker.loop, daemon=True, name="checks").start()
    threading.Thread(target=checker.reminders, daemon=True, name="reminders").start()
    threading.Thread(target=checker.channel_loop, daemon=True, name="channel").start()
    threading.Thread(target=checker.housekeeping, daemon=True, name="housekeeping").start()

    def on_stop(*_) -> None:  # Render останавливает сервис сигналом SIGTERM — сохраняем всё незаписанное
        store.flush_metrics()
        store.flush(8)
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_stop)


def parked() -> None:
    """Бот переехал на другой сервис. Здесь только открытый порт для Render: без входящих запросов сервис засыпает."""
    class Moved(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(410)
            self.end_headers()

        do_HEAD = do_GET

        def log_message(self, *args) -> None:
            pass

    log.info("сервис отключён: BOT_DISABLED")
    HTTPServer(("0.0.0.0", config.PORT), Moved).serve_forever()


def main() -> None:
    if os.environ.get("BOT_DISABLED"):
        parked()
        return
    store.init()
    dgt.AREA_LABELS.update(store.area_labels())
    threading.Thread(target=checker.refresh_centros, daemon=True).start()
    webapp.on_update = enqueue
    webapp.on_lang = refresh_screen

    if config.PUBLIC_URL:
        server = webapp.serve(config.PORT)
        if not config.TOKEN:
            log.error("TELEGRAM_TOKEN не задан — добавь его в Environment на Render. Жду…")
            server.serve_forever()
        if not store.PG:
            log.warning("DATABASE_URL не задан — подписки пропадут при перезапуске сервера")
        me = (tg.call("getMe") or {}).get("result")
        if not me:
            log.error("Telegram не принял TELEGRAM_TOKEN")
            server.serve_forever()
        tg.call("setWebhook", url=config.PUBLIC_URL + "/telegram", secret_token=config.SECRET, allowed_updates=ALLOWED_UPDATES)
        threading.Thread(target=setup_profile, daemon=True).start()
        log.info("Бот @%s запущен (webhook %s, версия %s), владельцы: %s", me["username"], config.PUBLIC_URL,
                 config.VERSION, sorted(config.OWNERS) or "не заданы")
        start_background()
        threading.Thread(target=checker.keepalive, daemon=True, name="keepalive").start()
        server.serve_forever()
        return

    if not config.TOKEN:
        raise SystemExit("Нет TELEGRAM_TOKEN. Скопируй .env.example в .env и вставь токен от @BotFather.")
    me = (tg.call("getMe") or {}).get("result")
    if not me:
        raise SystemExit("Telegram не принял токен — проверь TELEGRAM_TOKEN в .env")
    hook = ((tg.call("getWebhookInfo") or {}).get("result") or {}).get("url")
    if hook and "--force" not in sys.argv:
        raise SystemExit("Бот уже работает на сервере. Локальный запуск отключит его.\n"
                         "Если это нужно — запусти: python3 bot.py --force")
    tg.call("deleteWebhook")
    setup_profile()
    log.info("Бот @%s запущен локально", me["username"])
    start_background()

    offset = 0
    while True:
        data = tg.call("getUpdates", _timeout=70, offset=offset, timeout=50, allowed_updates=ALLOWED_UPDATES)
        if not data or not data.get("ok"):
            time.sleep(5)
            continue
        for upd in data["result"]:
            offset = upd["update_id"] + 1
            enqueue(upd)


if __name__ == "__main__":
    main()
