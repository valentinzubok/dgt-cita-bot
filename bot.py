"""OkSita — Telegram-бот: уведомления о свободных датах cita previa DGT.

На Render работает через webhook (+ health-эндпоинт на $PORT), локально — через long polling.
"""
from __future__ import annotations

import config  # noqa: F401 — первым: читает .env до остальных модулей

import json
import logging
import re
import signal
import sys
import threading
import time
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional, Tuple

import admin
import checker
import dgt
import radar
import store
import tg
import views
from tg import btn, ikb
from views import tx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

LEGACY_BUTTONS = {"➕ Добавить офис": "/add", "📋 Мои подписки": "/list", "🔄 Проверить сейчас": "/check",
                  "⚙️ Настройки": "/settings", "❓ Помощь": "/help"}  # кнопки под полем ввода из первой версии
last_manual: Dict[int, float] = {}
told_banned: set = set()
mode: Dict[int, str] = {}      # «radar» — пользователь выбирает офис для радара
waiting: Dict[int, dict] = {}  # ждём от пользователя текст (дату визита)


# ---------- действия ----------

def home(chat: int, mid: Optional[int] = None, note: str = "") -> None:
    mode.pop(chat, None)
    waiting.pop(chat, None)
    c = store.get_chat(chat)
    if not c.get("lang"):
        tg.show(chat, *views.language_picker(), mid=mid)
        return
    tg.show(chat, *views.dashboard(chat, c.get("name") or "", checker.status.get("next_cycle"), note), mid=mid)


def search(chat: int, query: str) -> None:
    q = views.fold(query.strip())
    found = [c for c in dgt.CENTROS if q and q in views.fold(dgt.CENTROS[c])]
    prefix, pager = ("rb", "rp") if mode.get(chat) == "radar" else ("c", "p")
    if len(found) == 1:
        if prefix == "rb":
            tg.show(chat, *views.radar_categories(chat, found[0]))
        else:
            open_office(chat, found[0])
    elif 1 < len(found) <= views.PAGE:
        tg.show(chat, *views.search_results(chat, query, found, prefix, pager))
    else:
        header = views.too_many(chat) if found else views.not_found(chat, query)
        tg.show(chat, *views.offices(chat, 0, header, prefix, pager))


def open_office(chat: int, cid: str, mid: Optional[int] = None) -> None:
    """Типы записи офиса. У каждого офиса они свои, поэтому берём с сайта (и кэшируем на 3 дня)."""
    mode.pop(chat, None)
    cached = store.office_areas(cid)
    if cached and time.time() - cached[0] < radar.AREAS_TTL:
        tg.show(chat, *views.areas(chat, cid, cached[1]), mid=mid)
        return
    lang = views.lang_of(chat)
    mid = tg.show(chat, *views.loading(tx(lang, "Загружаю услуги офиса ", "Завантажую послуги офісу ")
                                       + f"<b>{views.esc(views.city(cid))}</b>…"), mid=mid)

    def job() -> None:
        try:
            options = dgt.list_areas(cid)
            store.save_office_areas(cid, options)
            tg.show(chat, *views.areas(chat, cid, options), mid=mid)
        except Exception as e:
            log.warning("услуги офиса %s: %r", cid, e)
            tg.show(chat, *(views.areas(chat, cid, cached[1]) if cached else views.areas_error(chat, cid, f"c:{cid}")),
                    mid=mid)

    threading.Thread(target=job, daemon=True).start()


def subscribe(chat: int, mid: int, cid: str, area: str) -> None:
    lang = views.lang_of(chat)
    mine = store.subs_of(chat)
    exists = next((s for s in mine if s["centro"] == cid and s["area"] == area), None)
    if exists:
        tg.show(chat, *views.card(exists, tx(lang, "ℹ️ <i>Ты уже следишь за этим офисом.</i>",
                                             "ℹ️ <i>Ти вже стежиш за цим офісом.</i>")), mid=mid)
        return
    limit = store.setting("max_subs")
    if len(mine) >= limit:
        tg.show(chat, tx(lang, f"😅 Можно следить максимум за {limit} офисами.\nУдали ненужную подписку и добавь новую.",
                         f"😅 Можна стежити максимум за {limit} офісами.\nВидали непотрібну підписку й додай нову."),
                ikb([[btn(tx(lang, "📋 Подписки", "📋 Підписки"), "l"), views.home_btn(lang)]]), mid=mid)
        return
    keys = store.active_keys()
    if (cid, area) not in keys and len(keys) >= config.MAX_OFFICES:
        tg.show(chat, tx(lang, "😅 Бот сейчас следит за максимальным числом офисов. Попробуй позже.",
                         "😅 Бот зараз стежить за максимальною кількістю офісів. Спробуй пізніше."),
                ikb([[views.home_btn(lang)]]), mid=mid)
        return
    sub, _ = store.add_sub(chat, cid, area, dgt.AREA_LABELS.get(area, area))
    mid = tg.show(chat, tx(lang, "✅ <b>Подписка оформлена</b>\n", "✅ <b>Підписку оформлено</b>\n")
                  + f"🏢 {views.title(sub)}\n\n"
                  + tx(lang, "⏳ Делаю первую проверку — около минуты…", "⏳ Роблю першу перевірку — близько хвилини…"),
                  ikb([]), mid=mid)
    store.bump("subs")
    checker.event(f"➕ Подписка: {views.plain_title(sub)} ({store.get_chat(chat).get('name') or chat})", "user")
    threading.Thread(target=checker.run_checks, args=([(cid, area)], {chat: mid}), daemon=True).start()


def too_often(chat: int) -> bool:
    if time.time() - last_manual.get(chat, 0) < 60:
        return True
    last_manual[chat] = time.time()
    return False


def check_all(chat: int, mid: Optional[int]) -> Optional[str]:
    lang = views.lang_of(chat)
    subs = store.subs_of(chat)
    keys = sorted({(s["centro"], s["area"]) for s in subs if not s["paused"]})
    if not keys:
        return tx(lang, "Все подписки на паузе", "Усі підписки на паузі") if subs else \
            tx(lang, "Сначала добавь офис", "Спочатку додай офіс")
    if too_often(chat):
        return tx(lang, "⏳ Только что проверял — попробуй через минуту", "⏳ Щойно перевіряв — спробуй за хвилину")
    mins = max(1, round(len(keys) * 25 / 60))
    offices = views.pl(lang, len(keys), ("офис", "офиса", "офисов"), ("офіс", "офіси", "офісів"))
    mid = tg.show(chat, *views.dashboard(chat, "", None, tx(lang, f"🔄 <b>Проверяю {offices}…</b> около {mins} мин",
                                                              f"🔄 <b>Перевіряю {offices}…</b> близько {mins} хв")),
                  mid=mid)

    def job() -> None:
        checker.run_checks(keys)
        home(chat, mid, tx(lang, "✅ <b>Проверка завершена</b>", "✅ <b>Перевірку завершено</b>"))

    threading.Thread(target=job, daemon=True).start()
    return None


def save_booking(chat: int, mid: Optional[int], sub: dict, iso: str, hhmm: Optional[str]) -> None:
    now = datetime.now(config.TZ)
    day = date.fromisoformat(iso)
    bits = 3 if day <= now.date() else 1 if (day - now.date()).days == 1 and now.hour >= 19 else 0
    tg.delete(chat, sub.get("alert_msg"))
    store.update_sub(sub["id"], booked_date=iso, booked_time=hhmm, reminded=bits, paused=1, alert_msg=None)
    store.bump("bookings")
    store.bump_chat(chat, "bookings")
    checker.event(f"✅ Записался: {store.get_chat(chat).get('name') or chat} — {views.plain_title(sub)} {iso}", "user")
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


# ---------- обработчики ----------

def on_message(msg: dict) -> None:
    if msg.get("chat", {}).get("type") != "private":
        return
    chat = msg["chat"]["id"]
    frm = msg.get("from", {})
    c, is_new = store.touch_chat(chat, frm.get("first_name", ""), frm.get("username", ""))
    if is_new:
        start_arg = (msg.get("text") or "").partition(" ")[2].strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", start_arg):  # t.me/oksitabot?start=fb_alicante — откуда пришёл
            store.set_chat(chat, source=start_arg)
            c = store.get_chat(chat)
        on_new_user(chat, c)
        c = store.get_chat(chat)
    if views.is_admin(chat) and admin.handle_input(msg):
        return

    text = (msg.get("text") or "").strip()
    tg.call("deleteMessage", chat_id=chat, message_id=msg["message_id"])  # чат остаётся чистым
    lang = c.get("lang") or "ru"
    if not views.is_admin(chat):
        if c.get("role") == "banned":
            if chat not in told_banned:
                told_banned.add(chat)
                tg.show(chat, *views.banned_view(lang))
            return
        if c.get("role") == "pending":
            tg.show(chat, *views.pending_view(lang))
            return
        if store.setting("maintenance"):
            tg.show(chat, *views.maintenance_view(lang))
            return

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
        tg.show(chat, *views.language_picker())
        return

    w = waiting.get(chat)
    if w and not cmd:
        sub = store.get_sub(w["sid"])
        parsed = parse_booking(arg)
        if sub and parsed:
            waiting.pop(chat, None)
            save_booking(chat, w["screen"], sub, *parsed)
        elif sub:
            tg.show(chat, tx(lang, "🤔 Не понял дату. Напиши, например, <code>10.10 10:30</code>",
                             "🤔 Не зрозумів дату. Напиши, наприклад, <code>10.10 10:30</code>"),
                    ikb([[btn(tx(lang, "Отмена", "Скасувати"), f"bk:{sub['id']}")]]), mid=w["screen"])
        return

    if cmd in ("/start", "/menu"):
        home(chat)
    elif cmd in ("/add", "/centros"):
        mode.pop(chat, None)
        search(chat, arg) if arg.strip() else tg.show(chat, *views.offices(chat, 0))
    elif cmd == "/radar":
        mode[chat] = "radar"
        tg.show(chat, *views.radar_start(chat))
    elif cmd == "/list":
        tg.show(chat, *views.subs_list(chat))
    elif cmd == "/check":
        note = check_all(chat, None)
        if note:
            home(chat, note=note)
    elif cmd == "/settings":
        tg.show(chat, *views.settings_view(chat))
    elif cmd == "/help":
        tg.show(chat, *views.help_view(chat))
    elif cmd == "/ua":
        tg.show(chat, *views.ukraine_view(chat))
    elif cmd == "/lang":
        tg.show(chat, *views.language_picker())
    elif cmd == "/privacy":
        tg.show(chat, *views.privacy_view(chat))
    elif cmd == "/admin" and views.is_admin(chat):
        tg.show(chat, *admin.panel())
    elif not cmd and arg:
        search(chat, arg)
    else:
        home(chat)


def on_callback(cb: dict) -> None:
    msg = cb.get("message") or {}
    chat, mid, data = msg.get("chat", {}).get("id"), msg.get("message_id"), cb.get("data") or ""
    if not chat:
        return tg.answer(cb["id"])
    c = store.get_chat(chat)
    if c.get("role") in ("banned", "pending") and not views.is_admin(chat):
        return tg.answer(cb["id"])
    lang = views.lang_of(chat)
    if store.setting("maintenance") and not views.is_admin(chat) and cb.get("data") != "hide":
        tg.show(chat, *views.maintenance_view(lang), mid=mid)
        return tg.answer(cb["id"])
    toast, popup = None, False
    kind, _, rest = data.partition(":")
    if kind not in ("bo", "noop"):
        waiting.pop(chat, None)

    if kind == "ad":
        toast = admin.on_callback(chat, mid, rest) if views.is_admin(chat) else None
    elif data == "noop":
        pass
    elif kind == "lg" and rest[:2] in views.LANGS:
        store.set_chat(chat, lang=rest[:2])
        if rest.endswith(":st"):
            tg.show(chat, *views.settings_view(chat), mid=mid)
        else:
            home(chat, mid)
    elif data == "lp":
        tg.show(chat, *views.language_picker("st"), mid=mid)
    elif not c.get("lang"):
        tg.show(chat, *views.language_picker(), mid=mid)
    elif data == "hide":
        if not (tg.call("deleteMessage", chat_id=chat, message_id=mid) or {}).get("ok"):
            tg.edit(chat, mid, "·")
        if store.get_chat(chat).get("screen") == mid:
            store.set_chat(chat, screen=None)
    elif data == "home":
        home(chat, mid)
    elif kind == "p":
        mode.pop(chat, None)
        tg.show(chat, *views.offices(chat, int(rest or 0)), mid=mid)
    elif kind == "c" and rest in dgt.CENTROS:
        open_office(chat, rest, mid)
    elif kind == "a":
        cid, _, area = rest.partition(":")
        if cid in dgt.CENTROS and area:
            subscribe(chat, mid, cid, area)
    elif data == "rd":
        mode[chat] = "radar"
        tg.show(chat, *views.radar_start(chat), mid=mid)
    elif kind == "rp":
        mode[chat] = "radar"
        tg.show(chat, *views.offices(chat, int(rest or 0), tx(lang, "📡 <b>Радар</b> · от какого офиса искать?",
                                                               "📡 <b>Радар</b> · від якого офісу шукати?"), "rb", "rp"),
                mid=mid)
    elif kind == "rb" and rest in dgt.CENTROS:
        tg.show(chat, *views.radar_categories(chat, rest), mid=mid)
    elif kind == "rr":
        cid, cat, km = (rest.split(":") + ["", "", ""])[:3]
        if cid in dgt.CENTROS and cat in views.CATS and km.isdigit():
            mode.pop(chat, None)
            toast = radar.start(chat, mid, cid, cat, int(km))
            popup = bool(toast)
    elif data == "l":
        tg.show(chat, *views.subs_list(chat), mid=mid)
    elif data == "ca":
        toast = check_all(chat, mid)
    elif data == "st":
        tg.show(chat, *views.settings_view(chat), mid=mid)
    elif data == "hp":
        tg.show(chat, *views.help_view(chat), mid=mid)
    elif data == "ua":
        tg.show(chat, *views.ukraine_view(chat), mid=mid)
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
        store.delete_chat(chat)
        checker.event(f"🗑 Пользователь удалил свои данные ({chat})", "user")
        tg.edit(chat, mid, views.deleted_text(lang), ikb([]))
    elif data == "xa":
        tg.show(chat, tx(lang, "🗑 <b>Удалить все подписки?</b>\nУведомления перестанут приходить.",
                         "🗑 <b>Видалити всі підписки?</b>\nСповіщення перестануть надходити."),
                ikb([[btn(tx(lang, "Да, удалить всё", "Так, видалити все"), "xa!"), btn(tx(lang, "Отмена", "Скасувати"), "st")]]),
                mid=mid)
    elif data == "xa!":
        for s in store.subs_of(chat):
            tg.delete(chat, s.get("alert_msg"))
        store.forget_chat(chat)
        home(chat, mid, tx(lang, "🗑 Все подписки удалены.", "🗑 Усі підписки видалено."))
    elif kind in ("s", "r", "h", "f", "fs", "z", "x", "xx", "k", "d", "rs", "bk", "bd", "bt", "bo", "ub"):
        toast, popup = sub_action(chat, mid, kind, rest, lang)
    tg.answer(cb["id"], toast or "", popup)


def sub_action(chat: int, mid: int, kind: str, rest: str, lang: str) -> Tuple[Optional[str], bool]:
    sid, _, extra = rest.partition(":")
    sub = store.get_sub(int(sid)) if sid.isdigit() else None
    if not sub or sub["chat"] != chat:
        tg.show(chat, tx(lang, "Эта подписка уже удалена.", "Цю підписку вже видалено."),
                ikb([[btn(tx(lang, "📋 Подписки", "📋 Підписки"), "l"), views.home_btn(lang)]]), mid=mid)
        return None, False
    if kind == "s":
        tg.show(chat, *views.card(sub), mid=mid)
    elif kind == "r":
        if too_often(chat):
            return tx(lang, "⏳ Только что проверял — попробуй через минуту", "⏳ Щойно перевіряв — спробуй за хвилину"), False
        tg.show(chat, *views.card(sub, tx(lang, "🔄 <i>Проверяю… около минуты</i>", "🔄 <i>Перевіряю… близько хвилини</i>")),
                mid=mid)
        threading.Thread(target=checker.run_checks, args=([(sub["centro"], sub["area"])], {chat: mid}),
                         daemon=True).start()
    elif kind == "h":
        tg.show(chat, *views.history_view(sub), mid=mid)
    elif kind == "f":
        tg.show(chat, *views.filter_view(sub), mid=mid)
    elif kind == "fs" and extra.isdigit():
        store.update_sub(sub["id"], max_days=int(extra) or None)
        tg.show(chat, *views.card(store.get_sub(sub["id"])), mid=mid)
    elif kind == "z":
        store.update_sub(sub["id"], paused=0 if sub["paused"] else 1)
        tg.show(chat, *views.card(store.get_sub(sub["id"])), mid=mid)
        return (tx(lang, "▶️ Снова слежу", "▶️ Знову стежу") if sub["paused"]
                else tx(lang, "⏸ Подписка на паузе", "⏸ Підписка на паузі")), False
    elif kind == "x":
        tg.show(chat, *views.delete_confirm(sub), mid=mid)
    elif kind == "xx":
        tg.delete(chat, sub.get("alert_msg"))
        store.delete_sub(sub["id"])
        tg.show(chat, *views.subs_list(chat, tx(lang, "🗑 Подписка удалена: ", "🗑 Підписку видалено: ")
                                       + views.title(sub)), mid=mid)
    elif kind == "k":
        tg.show(chat, *views.calendar_view(sub, int(extra) if extra.lstrip("-").isdigit() else 0), mid=mid)
    elif kind == "d":
        return views.day_popup(sub, extra), True
    elif kind == "rs":
        cats = views.cats_of(views.sub_area(sub))
        cat = "lic" if "lic" in cats else next(iter(cats), "lic")
        return radar.start(chat, mid, sub["centro"], cat, 100), True
    elif kind == "bk":
        if views.all_days(sub.get("last")):
            tg.show(chat, *views.booking_dates(sub), mid=mid)
        else:
            waiting[chat] = {"sid": sub["id"], "screen": mid}
            tg.show(chat, *views.booking_prompt(sub), mid=mid)
    elif kind == "bd":
        if views.hours_for(sub.get("last"), extra):
            tg.show(chat, *views.booking_times(sub, extra), mid=mid)
        else:
            save_booking(chat, mid, sub, extra, None)
    elif kind == "bt":
        iso, _, hhmm = extra.partition(":")
        save_booking(chat, mid, sub, iso, f"{hhmm[:2]}:{hhmm[2:]}" if hhmm.isdigit() else None)
    elif kind == "bo":
        waiting[chat] = {"sid": sub["id"], "screen": mid}
        tg.show(chat, *views.booking_prompt(sub), mid=mid)
    elif kind == "ub":
        tg.delete(chat, sub.get("alert_msg"))
        store.update_sub(sub["id"], booked_date=None, booked_time=None, reminded=0, paused=0, alert_msg=None)
        tg.show(chat, *views.card(store.get_sub(sub["id"]), tx(lang, "▶️ <i>Снова ищу свободные даты.</i>",
                                                                "▶️ <i>Знову шукаю вільні дати.</i>")), mid=mid)
    return None, False


def dispatch(update: dict) -> None:
    try:
        if "message" in update:
            on_message(update["message"])
        elif "callback_query" in update:
            on_callback(update["callback_query"])
    except Exception:
        log.exception("ошибка обработки апдейта")


# ---------- запуск ----------

class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: bytes = b"") -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.split("?")[0] in ("/", "/health"):
            status = {k: v for k, v in checker.status.items()}
            self._reply(200, json.dumps({"ok": True, "token": bool(config.TOKEN), **status}).encode())
        else:
            self._reply(404)

    do_HEAD = do_GET

    def do_POST(self) -> None:
        if self.path != "/telegram":
            return self._reply(404)
        if self.headers.get("X-Telegram-Bot-Api-Secret-Token") != config.SECRET:
            return self._reply(403)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._reply(200, b"{}")
        try:
            update = json.loads(body)
        except ValueError:
            return
        threading.Thread(target=dispatch, args=(update,), daemon=True).start()

    def log_message(self, *args) -> None:
        pass


COMMANDS = {
    "ru": [("menu", "🏠 Главное меню"), ("add", "➕ Добавить офис"), ("radar", "📡 Радар — где раньше"),
           ("list", "📋 Мои подписки"), ("check", "🔄 Проверить сейчас"), ("ua", "🇺🇦 Для украинцев"),
           ("lang", "🌐 Язык / Мова"), ("help", "❓ Как это работает"), ("privacy", "🔒 Мои данные")],
    "uk": [("menu", "🏠 Головне меню"), ("add", "➕ Додати офіс"), ("radar", "📡 Радар — де швидше"),
           ("list", "📋 Мої підписки"), ("check", "🔄 Перевірити зараз"), ("ua", "🇺🇦 Для українців"),
           ("lang", "🌐 Мова / Язык"), ("help", "❓ Як це працює"), ("privacy", "🔒 Мої дані")],
}
SHORT = {
    "ru": "🔔 Свободные citas DGT (Tráfico) — сразу напишу, когда в твоём офисе появятся даты. Все 68 офисов Испании.",
    "uk": "🔔 Вільні citas DGT (Tráfico) — одразу напишу, щойно у твоєму офісі з’являться дати. Усі 68 офісів Іспанії.",
}
DESCRIPTION = {
    "ru": (f"🇪🇸 {config.BRAND} следит за записью (cita previa) в DGT — Tráfico — и сразу присылает уведомление, "
           "когда появляются свободные даты.\n\n"
           "✅ все 68 офисов DGT в Испании\n📡 радар: где записаться раньше всего\n"
           "🪪 права, транспорт, canje (обмен прав), экзамены, штрафы\n🗓 календарь со свободным временем\n"
           "⏰ напоминание о визите и что взять с собой\n🇺🇦 памятка для украинцев\n\n"
           "Бесплатно. Нажми «Старт» 👇"),
    "uk": (f"🇪🇸 {config.BRAND} стежить за записом (cita previa) у DGT — Tráfico — і одразу надсилає сповіщення, "
           "щойно з’являються вільні дати.\n\n"
           "✅ усі 68 офісів DGT в Іспанії\n📡 радар: де записатися найшвидше\n"
           "🪪 права, транспорт, canje (обмін прав), іспити, штрафи\n🗓 календар із вільним часом\n"
           "⏰ нагадування про візит і що взяти з собою\n🇺🇦 пам’ятка для українців\n\n"
           "Безкоштовно. Натисни «Почати» 👇"),
}


def setup_profile() -> None:
    for lang, cmds in COMMANDS.items():
        code = {"language_code": lang} if lang == "uk" else {}
        tg.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in cmds], **code)
        tg.call("setMyShortDescription", short_description=SHORT[lang], **code)
        tg.call("setMyDescription", description=DESCRIPTION[lang], **code)
    for owner in config.OWNERS:  # владельцам — ещё и /admin в меню
        lang = store.get_chat(owner).get("lang") or "ru"
        tg.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMMANDS[lang]]
                + [{"command": "admin", "description": "🛠 Админ-панель"}], scope={"type": "chat", "chat_id": owner})


def start_background() -> None:
    threading.Thread(target=checker.loop, daemon=True).start()
    threading.Thread(target=checker.reminders, daemon=True).start()
    threading.Thread(target=checker.housekeeping, daemon=True).start()

    def on_stop(*_) -> None:  # Render останавливает сервис сигналом SIGTERM — сохраняем статистику
        store.flush_metrics()
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_stop)


def main() -> None:
    store.init()
    dgt.AREA_LABELS.update(store.area_labels())
    threading.Thread(target=checker.refresh_centros, daemon=True).start()

    if config.PUBLIC_URL:
        server = ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler)
        if not config.TOKEN:
            log.error("TELEGRAM_TOKEN не задан — добавь его в Environment на Render. Жду…")
            server.serve_forever()
        if not store.PG:
            log.warning("DATABASE_URL не задан — подписки пропадут при перезапуске сервера")
        me = (tg.call("getMe") or {}).get("result")
        if not me:
            log.error("Telegram не принял TELEGRAM_TOKEN")
            server.serve_forever()
        setup_profile()
        tg.call("setWebhook", url=config.PUBLIC_URL + "/telegram", secret_token=config.SECRET,
                allowed_updates=["message", "callback_query"])
        log.info("Бот @%s запущен (webhook %s), владельцы: %s", me["username"], config.PUBLIC_URL,
                 sorted(config.OWNERS) or "не заданы")
        start_background()
        threading.Thread(target=checker.keepalive, daemon=True).start()
        server.serve_forever()
        return

    if not config.TOKEN:
        raise SystemExit("Нет TELEGRAM_TOKEN. Скопируй .env.example в .env и вставь токен от @BotFather.")
    me = (tg.call("getMe") or {}).get("result")
    if not me:
        raise SystemExit("Telegram не принял токен — проверь TELEGRAM_TOKEN в .env")
    hook = ((tg.call("getWebhookInfo") or {}).get("result") or {}).get("url")
    if hook and "--force" not in sys.argv:
        raise SystemExit(f"Бот уже работает на сервере ({hook}). Локальный запуск отключит его.\n"
                         "Если это нужно — запусти: python3 bot.py --force")
    tg.call("deleteWebhook")
    setup_profile()
    log.info("Бот @%s запущен локально", me["username"])
    start_background()

    offset = 0
    while True:
        data = tg.call("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
        if not data or not data.get("ok"):
            time.sleep(5)
            continue
        for upd in data["result"]:
            offset = upd["update_id"] + 1
            threading.Thread(target=dispatch, args=(upd,), daemon=True).start()


if __name__ == "__main__":
    main()
