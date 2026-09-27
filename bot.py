"""OkSita — Telegram-бот: уведомления о свободных датах cita previa DGT.

На Render работает через webhook (+ health-эндпоинт на $PORT), локально — через long polling.
"""
from __future__ import annotations

import config  # noqa: F401 — первым: читает .env до остальных модулей

import json
import logging
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Tuple

import admin
import checker
import dgt
import store
import tg
import views
from tg import btn, ikb

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

LEGACY_BUTTONS = {"➕ Добавить офис": "/add", "📋 Мои подписки": "/list", "🔄 Проверить сейчас": "/check",
                  "⚙️ Настройки": "/settings", "❓ Помощь": "/help"}  # кнопки под полем ввода из прошлой версии
area_cache: Dict[str, Tuple[float, list]] = {}
last_manual: Dict[int, float] = {}
told_banned: set = set()


# ---------- действия ----------

def home(chat: int, mid: Optional[int] = None, note: str = "") -> None:
    c = store.get_chat(chat)
    tg.show(chat, *views.dashboard(chat, c.get("name") or "", checker.status.get("next_cycle"), note), mid=mid)


def search(chat: int, query: str) -> None:
    q = views.fold(query.strip())
    found = [c for c in dgt.CENTROS if q and q in views.fold(dgt.CENTROS[c])]
    if len(found) == 1:
        open_office(chat, found[0])
    elif 1 < len(found) <= views.PAGE:
        tg.show(chat, *views.search_results(query, found))
    elif found:
        tg.show(chat, *views.offices(0, "🔎 Слишком много совпадений — уточни название или выбери из списка."))
    else:
        tg.show(chat, *views.offices(0, f"😕 Не нашёл офис «{views.esc(query)}».\n\n🏢 <b>Выбери из списка</b>"))


def open_office(chat: int, cid: str, mid: Optional[int] = None) -> None:
    """Список типов записи офиса. У каждого офиса он свой, поэтому берём его с сайта (и кэшируем)."""
    cached = area_cache.get(cid)
    if cached and time.time() - cached[0] < 12 * 3600:
        tg.show(chat, *views.areas(cid, cached[1]), mid=mid)
        return
    mid = tg.show(chat, *views.loading(f"Загружаю услуги офиса <b>{views.esc(views.city(cid))}</b>…"), mid=mid)

    def job() -> None:
        try:
            options = dgt.list_areas(cid)
            area_cache[cid] = (time.time(), options)
            tg.show(chat, *views.areas(cid, options), mid=mid)
        except Exception as e:
            log.warning("услуги офиса %s: %r", cid, e)
            tg.show(chat, *(views.areas(cid, cached[1]) if cached else views.areas_error(cid)), mid=mid)

    threading.Thread(target=job, daemon=True).start()


def subscribe(chat: int, mid: int, cid: str, area: str) -> None:
    mine = store.subs_of(chat)
    exists = next((s for s in mine if s["centro"] == cid and s["area"] == area), None)
    if exists:
        tg.show(chat, *views.card(exists, "ℹ️ <i>Ты уже следишь за этим офисом.</i>"), mid=mid)
        return
    limit = store.setting("max_subs")
    if len(mine) >= limit:
        tg.show(chat, f"😅 Можно следить максимум за {views.plural(limit, 'офисом', 'офисами', 'офисами')}.\n"
                      "Удали ненужную подписку и добавь новую.", ikb([[btn("📋 Подписки", "l"), views.HOME]]), mid=mid)
        return
    keys = store.active_keys()
    if (cid, area) not in keys and len(keys) >= config.MAX_OFFICES:
        tg.show(chat, "😅 Бот сейчас следит за максимальным числом офисов. Попробуй позже.", ikb([[views.HOME]]),
                mid=mid)
        return
    sub, _ = store.add_sub(chat, cid, area, dgt.AREA_LABELS.get(area, area))
    mid = tg.show(chat, f"✅ <b>Подписка оформлена</b>\n🏢 {views.title(sub)}\n\n"
                        "⏳ Делаю первую проверку — около минуты…", ikb([]), mid=mid)
    checker.event(f"➕ Подписка: {views.plain_title(sub)} ({store.get_chat(chat).get('name') or chat})")
    threading.Thread(target=checker.run_checks, args=([(cid, area)], {chat: mid}), daemon=True).start()


def too_often(chat: int) -> bool:
    if time.time() - last_manual.get(chat, 0) < 60:
        return True
    last_manual[chat] = time.time()
    return False


def check_all(chat: int, mid: Optional[int]) -> Optional[str]:
    subs = store.subs_of(chat)
    keys = sorted({(s["centro"], s["area"]) for s in subs if not s["paused"]})
    if not keys:
        return "Все подписки на паузе" if subs else "Сначала добавь офис"
    if too_often(chat):
        return "⏳ Только что проверял — попробуй через минуту"
    mins = max(1, round(len(keys) * 25 / 60))
    mid = tg.show(chat, *views.dashboard(chat, "", None, f"🔄 <b>Проверяю "
                  f"{views.plural(len(keys), 'офис', 'офиса', 'офисов')}…</b> около {mins} мин"), mid=mid)

    def job() -> None:
        checker.run_checks(keys)
        home(chat, mid, "✅ <b>Проверка завершена</b>")

    threading.Thread(target=job, daemon=True).start()
    return None


def on_new_user(chat: int, c: dict) -> None:
    who = admin.uname(c)
    checker.event(f"👤 Новый пользователь: {c.get('name') or chat}")
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
        on_new_user(chat, c)
        c = store.get_chat(chat)
    if views.is_admin(chat) and admin.handle_input(msg):
        return

    text = (msg.get("text") or "").strip()
    tg.call("deleteMessage", chat_id=chat, message_id=msg["message_id"])  # чат остаётся чистым
    role = c.get("role")
    if not views.is_admin(chat):
        if role == "banned":
            if chat not in told_banned:
                told_banned.add(chat)
                tg.show(chat, *views.banned_view())
            return
        if role == "pending":
            tg.show(chat, *views.pending_view())
            return

    if text in LEGACY_BUTTONS or text.startswith("/start"):
        tg.remove_reply_keyboard(chat)
        text = LEGACY_BUTTONS.get(text, text)
    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
    else:
        cmd, arg = "", text

    if cmd in ("/start", "/menu"):
        home(chat)
    elif cmd in ("/add", "/centros"):
        search(chat, arg) if arg.strip() else tg.show(chat, *views.offices(0))
    elif cmd == "/list":
        tg.show(chat, *views.subs_list(chat))
    elif cmd == "/check":
        note = check_all(chat, None)
        if note:
            home(chat, note=note)
    elif cmd == "/settings":
        tg.show(chat, *views.settings_view(chat))
    elif cmd == "/help":
        tg.show(chat, *views.help_view())
    elif cmd == "/ua":
        tg.show(chat, *views.ukraine_view())
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
    role = store.get_chat(chat).get("role")
    if role in ("banned", "pending") and not views.is_admin(chat):
        return tg.answer(cb["id"])
    toast, popup = None, False
    kind, _, rest = data.partition(":")

    if kind == "ad":
        toast = admin.on_callback(chat, mid, rest) if views.is_admin(chat) else None
    elif data == "noop":
        pass
    elif data == "hide":
        if not (tg.call("deleteMessage", chat_id=chat, message_id=mid) or {}).get("ok"):
            tg.edit(chat, mid, "·")
        if store.get_chat(chat).get("screen") == mid:
            store.set_chat(chat, screen=None)
    elif data == "home":
        home(chat, mid)
    elif kind == "p":
        tg.show(chat, *views.offices(int(rest or 0)), mid=mid)
    elif kind == "c" and rest in dgt.CENTROS:
        open_office(chat, rest, mid)
    elif kind == "a":
        cid, _, area = rest.partition(":")
        if cid in dgt.CENTROS and area:
            subscribe(chat, mid, cid, area)
    elif data == "l":
        tg.show(chat, *views.subs_list(chat), mid=mid)
    elif data == "ca":
        toast = check_all(chat, mid)
    elif data == "st":
        tg.show(chat, *views.settings_view(chat), mid=mid)
    elif data == "hp":
        tg.show(chat, *views.help_view(), mid=mid)
    elif data == "ua":
        tg.show(chat, *views.ukraine_view(), mid=mid)
    elif data == "q":
        store.set_chat(chat, quiet=0 if store.get_chat(chat).get("quiet") else 1)
        tg.show(chat, *views.settings_view(chat), mid=mid)
    elif data == "xa":
        tg.show(chat, "🗑 <b>Удалить все подписки?</b>\nУведомления перестанут приходить.",
                ikb([[btn("Да, удалить всё", "xa!"), btn("Отмена", "st")]]), mid=mid)
    elif data == "xa!":
        for s in store.subs_of(chat):
            tg.delete(chat, s.get("alert_msg"))
        store.forget_chat(chat)
        home(chat, mid, "🗑 Все подписки удалены.")
    elif kind in ("s", "r", "h", "f", "fs", "z", "x", "xx", "k", "d"):
        toast, popup = sub_action(chat, mid, kind, rest)
    tg.answer(cb["id"], toast or "", popup)


def sub_action(chat: int, mid: int, kind: str, rest: str) -> Tuple[Optional[str], bool]:
    sid, _, extra = rest.partition(":")
    sub = store.get_sub(int(sid)) if sid.isdigit() else None
    if not sub or sub["chat"] != chat:
        tg.show(chat, "Эта подписка уже удалена.", ikb([[btn("📋 Подписки", "l"), views.HOME]]), mid=mid)
        return None, False
    if kind == "s":
        tg.show(chat, *views.card(sub), mid=mid)
    elif kind == "r":
        if too_often(chat):
            return "⏳ Только что проверял — попробуй через минуту", False
        tg.show(chat, *views.card(sub, "🔄 <i>Проверяю… около минуты</i>"), mid=mid)
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
        return ("▶️ Снова слежу" if sub["paused"] else "⏸ Подписка на паузе"), False
    elif kind == "x":
        tg.show(chat, *views.delete_confirm(sub), mid=mid)
    elif kind == "xx":
        tg.delete(chat, sub.get("alert_msg"))
        store.delete_sub(sub["id"])
        tg.show(chat, *views.subs_list(chat, f"🗑 Подписка удалена: {views.title(sub)}"), mid=mid)
    elif kind == "k":
        tg.show(chat, *views.calendar_view(sub, int(extra) if extra.lstrip("-").isdigit() else 0), mid=mid)
    elif kind == "d":
        return views.day_popup(sub, extra), True
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
            self._reply(200, json.dumps({"ok": True, "token": bool(config.TOKEN), **checker.status}).encode())
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


COMMANDS = [
    {"command": "menu", "description": "🏠 Главное меню"},
    {"command": "add", "description": "➕ Добавить офис"},
    {"command": "list", "description": "📋 Мои подписки"},
    {"command": "check", "description": "🔄 Проверить сейчас"},
    {"command": "ua", "description": "🇺🇦 Для украинцев"},
    {"command": "help", "description": "❓ Как это работает"},
]


def setup_profile() -> None:
    tg.call("setMyCommands", commands=COMMANDS)
    for owner in config.OWNERS:  # владельцам — ещё и /admin в меню
        tg.call("setMyCommands", commands=COMMANDS + [{"command": "admin", "description": "🛠 Админ-панель"}],
                scope={"type": "chat", "chat_id": owner})
    tg.call("setMyShortDescription", short_description=(
        "🔔 Свободные citas DGT (Tráfico) — сразу напишу, когда в твоём офисе появятся даты. Все 68 офисов Испании."))
    tg.call("setMyDescription", description=(
        f"🇪🇸 {config.BRAND} следит за записью (cita previa) в DGT — Tráfico — и сразу присылает уведомление, "
        "когда появляются свободные даты.\n\n"
        "✅ все 68 офисов DGT в Испании\n"
        "🪪 права, транспорт, canje (обмен прав), экзамены, штрафы\n"
        "🗓 календарь с загрузкой дней и свободным временем\n"
        "📅 фильтр ближайших дат, пауза, история\n"
        "🇺🇦 памятка для украинцев\n\n"
        "Бесплатно. Нажми «Старт» 👇"))


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
        me = ((tg.call("getMe") or {}).get("result"))
        if not me:
            log.error("Telegram не принял TELEGRAM_TOKEN")
            server.serve_forever()
        setup_profile()
        tg.call("setWebhook", url=config.PUBLIC_URL + "/telegram", secret_token=config.SECRET,
                allowed_updates=["message", "callback_query"])
        log.info("Бот @%s запущен (webhook %s), владельцы: %s", me["username"], config.PUBLIC_URL,
                 sorted(config.OWNERS) or "не заданы")
        threading.Thread(target=checker.loop, daemon=True).start()
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
    threading.Thread(target=checker.loop, daemon=True).start()

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
