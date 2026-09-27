"""DGT Cita Bot: следит за свободными датами cita previa DGT и присылает уведомления в Telegram.

Режимы:
  python3 bot.py          — локально (long polling), если не задан WEBHOOK_URL / RENDER_EXTERNAL_URL
  на Render               — webhook + health-эндпоинт на $PORT, проверки в фоне
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import math
import os
import random
import sys
import threading
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent


def _load_env() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


_load_env()

import dgt  # noqa: E402
import store  # noqa: E402

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
INTERVAL = max(5, int(os.environ.get("CHECK_INTERVAL_MIN", "10"))) * 60
ALLOWED = {x.strip() for x in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if x.strip()}
ADMIN = os.environ.get("ADMIN_CHAT_ID", "").strip()
MAX_SUBS_PER_CHAT = 5
MAX_OFFICES = int(os.environ.get("MAX_OFFICES", "30"))
PUBLIC_URL = (os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
TZ = ZoneInfo("Europe/Madrid")
API = f"https://api.telegram.org/bot{TOKEN}/"
SECRET = hashlib.sha256(("dgt-webhook:" + TOKEN).encode()).hexdigest()[:40]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

# ---------- оформление ----------

AREA_UI = {
    "CND": ("🪪", "права, водители"),
    "VEH": ("🚗", "транспорт"),
    "MAT": ("📝", "регистрация ТС"),
    "SAN": ("💶", "штрафы"),
    "CNJ": ("🔁", "обмен прав"),
}
LOAD = {"bajaOcupacion": "🟢", "mediaOcupacion": "🟡", "altaOcupacion": "🔴"}
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WD_LONG = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь",
          "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
FILTERS = [(0, "любые"), (7, "до 7 дней"), (14, "до 14 дней"), (30, "до 30 дней"), (60, "до 60 дней")]

BTN_ADD, BTN_LIST, BTN_CHECK, BTN_SETTINGS, BTN_HELP = (
    "➕ Добавить офис", "📋 Мои подписки", "🔄 Проверить сейчас", "⚙️ Настройки", "❓ Помощь")
MENU = {
    "keyboard": [[{"text": BTN_ADD}, {"text": BTN_LIST}],
                 [{"text": BTN_CHECK}, {"text": BTN_SETTINGS}],
                 [{"text": BTN_HELP}]],
    "resize_keyboard": True,
    "is_persistent": True,
}
PAGE = 16

esc = html.escape


# ---------- Telegram ----------

def tg(method: str, **params) -> Optional[dict]:
    try:
        data = requests.post(API + method, json=params, timeout=70).json()
    except Exception as e:
        log.warning("telegram %s: %r", method, e)
        return None
    if not data.get("ok") and "not modified" not in data.get("description", ""):
        log.warning("telegram %s: %s", method, data.get("description"))
    return data


def send(chat: int, text: str, kb: Optional[dict] = None, silent: bool = False) -> Optional[int]:
    p = {"chat_id": chat, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True, "disable_notification": silent}
    if kb is not None:
        p["reply_markup"] = kb
    data = tg("sendMessage", **p)
    if data and data.get("error_code") == 403:  # пользователь заблокировал бота
        store.forget_chat(chat)
    return data["result"]["message_id"] if data and data.get("ok") else None


def edit(chat: int, msg_id: int, text: str, kb: Optional[dict] = None) -> None:
    p = {"chat_id": chat, "message_id": msg_id, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if kb is not None:
        p["reply_markup"] = kb
    tg("editMessageText", **p)


def inline(rows: list) -> dict:
    return {"inline_keyboard": rows}


def b(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}


def u(text: str, url: str) -> dict:
    return {"text": text, "url": url}


# ---------- форматирование ----------

def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def plural(n: int, one: str, few: str, many: str) -> str:
    k = n % 100
    word = many if 11 <= k <= 14 else one if k % 10 == 1 else few if 2 <= k % 10 <= 4 else many
    return f"{n} {word}"


def city(cid: str) -> str:
    name = dgt.CENTROS.get(cid, cid)
    return name.split(" de Tráfico de ", 1)[-1]


def title(cid: str, area: str) -> str:
    return f"<b>{esc(city(cid))}</b> · {AREA_UI[area][0]} {dgt.AREAS[area]}"


def plain_title(cid: str, area: str) -> str:
    return f"{city(cid)} · {dgt.AREAS[area]}"


def today() -> date:
    return datetime.now(TZ).date()


def long_day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WD_LONG[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"


def short_day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS_GEN[d.month - 1][:3]}"


def fmt_ts(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, TZ)
    if dt.date() == today():
        return f"сегодня в {dt:%H:%M}"
    return f"{WD[dt.weekday()]} {dt:%d.%m} в {dt:%H:%M}"


def fmt_dur(sec: int) -> str:
    m = max(1, round(sec / 60))
    if m < 60:
        return f"{m} мин"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} ч {m} мин" if m else f"{h} ч"
    return plural(round(h / 24), "день", "дня", "дней")


def all_days(results: Optional[list], max_days: Optional[int] = None) -> List[Tuple[str, str]]:
    """Свободные дни по всем видам записи, без повторов, по возрастанию, с учётом фильтра."""
    limit = today() + timedelta(days=max_days) if max_days else None
    seen: Dict[str, str] = {}
    for r in results or []:
        if r["status"] == dgt.AVAILABLE:
            for iso, load in r["days"]:
                if (limit is None or date.fromisoformat(iso) <= limit) and iso not in seen:
                    seen[iso] = load
    return sorted(seen.items())


def hours_for(results: list, iso: str) -> List[str]:
    for r in results or []:
        if r["status"] == dgt.AVAILABLE and r["days"] and r["days"][0][0] == iso:
            return r.get("hours") or []
    return []


def days_block(days: List[Tuple[str, str]], new: Set[str] = frozenset(), limit: int = 45) -> str:
    """Дни по месяцам, одна строка — одна неделя. Новые дни выделены жирным."""
    lines: List[str] = []
    row: List[str] = []
    cur_month = cur_week = None
    for iso, load in days[:limit]:
        d = date.fromisoformat(iso)
        if (d.year, d.month) != cur_month:
            if row:
                lines.append("  ".join(row))
                row = []
            cur_month, cur_week = (d.year, d.month), None
            lines.append(f"\n📅 <b>{MONTHS[d.month - 1].capitalize()} {d.year}</b>")
        week = d.isocalendar()[1]
        if week != cur_week and row:
            lines.append("  ".join(row))
            row = []
        cur_week = week
        label = f"{WD[d.weekday()]} {d.day}"
        row.append(f"<b>{label}</b>{LOAD.get(load, '▫️')}" if iso in new else f"{label}{LOAD.get(load, '▫️')}")
    if row:
        lines.append("  ".join(row))
    if len(days) > limit:
        lines.append(f"…и ещё {plural(len(days) - limit, 'день', 'дня', 'дней')}")
    return "\n".join(lines).strip()


def nearest_block(results: list, days: List[Tuple[str, str]]) -> List[str]:
    iso = days[0][0]
    lines = [f"⭐️ Ближайшая: <b>{long_day(iso)}</b>"]
    hours = hours_for(results, iso)
    if hours:
        shown = " · ".join(hours[:12]) + (f" <i>+{len(hours) - 12}</i>" if len(hours) > 12 else "")
        lines.append(f"⏰ {shown}")
    return lines


def filter_label(max_days: Optional[int]) -> str:
    return dict(FILTERS).get(max_days or 0, f"до {max_days} дней")


def summary(sub: dict) -> Tuple[str, str]:
    """Короткий статус подписки: (эмодзи, текст)."""
    last = sub.get("last")
    if sub.get("paused"):
        return "⏸", "на паузе"
    if last is None:
        return "⏳", "ещё не проверялось"
    if (sub.get("fails") or 0) >= 3:
        return "⚠️", "сайт DGT не отвечает"
    days = all_days(last, sub.get("max_days"))
    if days:
        return "🟢", f"{plural(len(days), 'свободный день', 'свободных дня', 'свободных дней')}, ближайший {short_day(days[0][0])}"
    if all_days(last):
        return "🟡", "есть даты, но позже твоего фильтра"
    status = last[0]["status"] if last else dgt.UNKNOWN
    return {
        dgt.FULL: ("🔴", "мест нет"),
        dgt.NO_AREA: ("⚪️", "в этом офисе нет такой записи"),
        dgt.NOT_CONFIGURED: ("⚪️", "офис не принимает эту запись"),
    }.get(status, ("❔", "не удалось прочитать страницу"))


# ---------- экраны ----------

def welcome(name: str) -> str:
    hello = f"👋 <b>Привет, {esc(name)}!</b>" if name else "👋 <b>Привет!</b>"
    return (
        f"{hello}\n\n"
        "Я слежу за свободными датами <b>cita previa DGT</b> (Tráfico) и сразу пишу, когда они появляются. 🇪🇸\n\n"
        "<b>Как начать</b>\n"
        "1️⃣ Нажми «➕ Добавить офис»\n"
        "2️⃣ Выбери город и тип записи\n"
        "3️⃣ Жди уведомление 🔔\n\n"
        f"⏱ Проверяю каждые {INTERVAL // 60} минут, до {MAX_SUBS_PER_CHAT} офисов одновременно.\n"
        "📝 Записываешься ты сам на сайте DGT — я только сообщаю, когда есть места."
    )


HELP = (
    "❓ <b>Как это работает</b>\n\n"
    "Я захожу на сайт DGT так же, как это сделал бы ты: выбираю офис и тип записи и смотрю календарь. "
    "Как только появляются свободные дни — присылаю уведомление с датами и временем.\n\n"
    "<b>Цвета</b>\n"
    "🟢 много свободных мест\n"
    "🟡 занято 33–66%\n"
    "🔴 почти всё занято\n\n"
    "<b>Что умею</b>\n"
    "• следить за несколькими офисами сразу\n"
    "• присылать только даты раньше нужной — «📅 Даты» в карточке подписки\n"
    "• ставить подписку на паузу\n"
    "• показывать историю: когда в офисе появлялись места\n"
    "• тихий режим ночью — в «⚙️ Настройки»\n\n"
    "<b>Советы</b>\n"
    "• Места быстро разбирают — открывай сайт сразу после уведомления\n"
    "• Держи под рукой DNI/NIE: сайт спросит данные при записи\n\n"
    "Команды: /add, /list, /check, /settings, /help"
)


def offices_view(page: int = 0, header: str = "") -> Tuple[str, dict]:
    ids = sorted(dgt.CENTROS, key=lambda c: fold(city(c)))
    pages = math.ceil(len(ids) / PAGE)
    page %= pages
    chunk = ids[page * PAGE:(page + 1) * PAGE]
    rows = [[b(city(c), f"c:{c}") for c in chunk[i:i + 2]] for i in range(0, len(chunk), 2)]
    rows.append([b("◀️", f"p:{page - 1}"), b(f"{page + 1} / {pages}", "noop"), b("▶️", f"p:{page + 1}")])
    text = (header or "🏢 <b>Выбери офис DGT</b>") + \
        "\n\nИли просто напиши название города, например <i>Valencia</i>."
    return text, inline(rows)


def areas_view(cid: str) -> Tuple[str, dict]:
    text = f"🏢 <b>{esc(city(cid))}</b>\n<i>{esc(dgt.CENTROS[cid])}</i>\n\nКакой тип записи нужен?"
    rows = [[b(f"{emoji} {dgt.AREAS[code]} — {desc}", f"a:{cid}:{code}")] for code, (emoji, desc) in AREA_UI.items()]
    rows.append([b("⬅️ К списку офисов", "p:0")])
    return text, inline(rows)


def list_view(chat: int, header: str = "") -> Tuple[str, dict]:
    subs = store.subs_of(chat)
    if not subs:
        return ("📋 <b>Подписок пока нет</b>\n\nНажми «➕ Добавить офис» — и я начну следить за свободными датами.",
                inline([[b("➕ Добавить офис", "p:0")]]))
    lines = [header or f"📋 <b>Твои подписки</b> · {len(subs)}/{MAX_SUBS_PER_CHAT}", ""]
    rows = []
    for s in subs:
        emoji, text = summary(s)
        lines.append(f"{emoji} {title(s['centro'], s['area'])}\n      <i>{text}</i>")
        rows.append([b(f"{emoji} {plain_title(s['centro'], s['area'])}", f"s:{s['id']}")])
    lines.append("\nНажми на подписку, чтобы открыть подробности.")
    rows.append([b("➕ Добавить", "p:0"), b("🔄 Проверить все", "ca")])
    return "\n".join(lines), inline(rows)


def sub_card(sub: dict, note: str = "") -> Tuple[str, dict]:
    cid, area, last = sub["centro"], sub["area"], sub.get("last")
    lines = [f"🏢 {title(cid, area)}"]
    info = next((r for r in last or [] if r.get("address")), None)
    if info:
        lines.append(f"📍 {esc(info['address'])}")
        if info.get("schedule"):
            lines.append(f"🕘 {esc(info['schedule'])}")
    lines.append("")

    days = all_days(last, sub.get("max_days"))
    if sub.get("paused"):
        lines.append("⏸ <b>Подписка на паузе</b> — уведомления не приходят")
    if days:
        lines.append(f"🟢 <b>Есть свободные даты: {len(days)}</b>")
        lines += nearest_block(last, days)
        lines += ["", days_block(days)]
    elif not sub.get("paused"):
        emoji, text = summary(sub)
        lines.append(f"{emoji} <b>{text[0].upper() + text[1:]}</b>")
        if emoji in ("🔴", "🟡"):
            lines.append("Напишу, как только появятся подходящие даты.")
        elif emoji == "⚪️":
            lines.append("Проверь офис и тип записи — возможно, стоит выбрать другой.")

    lines.append("")
    lines.append(f"📅 Даты: <b>{filter_label(sub.get('max_days'))}</b>")
    if sub.get("checked_at"):
        lines.append(f"🕐 Проверено {fmt_ts(sub['checked_at'])}")
    if note:
        lines.append(f"\n{note}")

    sid = sub["id"]
    kb = inline([
        [u("📝 Записаться на сайте DGT", dgt.START_URL)],
        [b("🔄 Обновить", f"r:{sid}"), b("📊 История", f"h:{sid}")],
        [b(f"📅 Даты: {filter_label(sub.get('max_days'))}", f"f:{sid}"),
         b("▶️ Возобновить" if sub.get("paused") else "⏸ Пауза", f"z:{sid}")],
        [b("🗑 Удалить", f"x:{sid}"), b("⬅️ Все подписки", "l")],
    ])
    return "\n".join(lines), kb


def alert_view(sub: dict, results: list, new: Set[str]) -> Tuple[str, dict]:
    cid, area = sub["centro"], sub["area"]
    days = all_days(results, sub.get("max_days"))
    lines = ["🔔 <b>Появились свободные даты!</b>", "", f"🏢 {title(cid, area)}", ""]
    lines += nearest_block(results, days)
    lines += ["", days_block(days, new)]
    if sub.get("max_days"):
        lines.append(f"\n<i>Показаны даты в пределах {sub['max_days']} дней</i>")
    lines.append("\n🟢 много мест · 🟡 средне · 🔴 мало")
    lines.append(f"<i>На сайте: {esc(city(cid))} → {dgt.AREAS[area]} → Continuar → Pedir cita</i>")
    kb = inline([
        [u("📝 Записаться на сайте DGT", dgt.START_URL)],
        [b("🔄 Обновить", f"r:{sub['id']}"), b("⏸ Пауза", f"z:{sub['id']}")],
    ])
    return "\n".join(lines), kb


def filter_view(sub: dict) -> Tuple[str, dict]:
    text = (f"📅 <b>Какие даты присылать?</b>\n{title(sub['centro'], sub['area'])}\n\n"
            "Например, если у тебя уже есть запись через месяц, выбери «до 30 дней» — "
            "и я напишу только о более ранних датах.")
    cur = sub.get("max_days") or 0
    rows = [[b(("✅ " if v == cur else "") + label.capitalize(), f"fs:{sub['id']}:{v}")] for v, label in FILTERS]
    rows.append([b("⬅️ Назад", f"s:{sub['id']}")])
    return text, inline(rows)


def history_view(sub: dict) -> Tuple[str, dict]:
    cid, area = sub["centro"], sub["area"]
    evs = store.events(cid, area, 30)
    lines = [f"📊 <b>История</b> · {title(cid, area)}", ""]
    if not evs:
        lines.append("Пока ни разу не видел здесь свободных мест.\n"
                     "История начнёт копиться, как только они появятся.")
    else:
        if not evs[0]["closed_at"]:
            lines.append(f"🟢 Места есть прямо сейчас — появились {fmt_ts(evs[0]['opened_at'])}\n")
        lines.append("<b>Когда появлялись места</b> (время Мадрида):")
        for e in evs[:10]:
            dur = "ещё есть" if not e["closed_at"] else f"держались {fmt_dur(e['closed_at'] - e['opened_at'])}"
            days = plural(e["days"] or 0, "день", "дня", "дней")
            lines.append(f"• {fmt_ts(e['opened_at'])} — {dur}, {days}")
        if len(evs) >= 3:
            hour, _ = Counter(datetime.fromtimestamp(e["opened_at"], TZ).hour for e in evs).most_common(1)[0]
            lines.append(f"\n⏰ Чаще всего места появляются между {hour}:00 и {hour + 1}:00")
        closed = [e["closed_at"] - e["opened_at"] for e in evs if e["closed_at"]]
        if closed:
            lines.append(f"⌛️ В среднем держатся {fmt_dur(sum(closed) // len(closed))}")
        lines.append(f"\n<i>Точность — интервал проверки, {INTERVAL // 60} мин.</i>")
    return "\n".join(lines), inline([[b("⬅️ Назад", f"s:{sub['id']}")]])


def settings_view(chat: int) -> Tuple[str, dict]:
    quiet = store.get_chat(chat).get("quiet")
    text = ("⚙️ <b>Настройки</b>\n\n"
            f"🌙 <b>Тихий режим ночью</b>: {'включён' if quiet else 'выключен'}\n"
            "<i>С 00:00 до 08:00 по Мадриду уведомления приходят без звука.</i>\n\n"
            f"⏱ Проверка каждые {INTERVAL // 60} мин\n"
            f"🏢 До {MAX_SUBS_PER_CHAT} офисов одновременно")
    return text, inline([
        [b(f"🌙 Тихий режим: {'вкл' if quiet else 'выкл'}", "q")],
        [b("🗑 Удалить все подписки", "xa")],
    ])


def is_quiet(chat: int) -> bool:
    return bool(store.get_chat(chat).get("quiet")) and datetime.now(TZ).hour < 8


# ---------- проверки ----------

check_lock = threading.Lock()
status = {"started": int(time.time()), "last_cycle": None, "cycles": 0, "errors": 0}
last_manual: Dict[int, float] = {}


def run_checks(keys: List[Tuple[str, str]], cards: Optional[Dict[int, int]] = None) -> None:
    """Проверяет офисы по очереди. cards: {chat: message_id} — где показать обновлённую карточку."""
    with check_lock:
        for i, (cid, area) in enumerate(keys):
            if i:
                time.sleep(random.uniform(4, 10))
            results, err = None, None
            try:
                results = [r.__dict__ for r in dgt.check(cid, area)]
                log.info("%s: %s", plain_title(cid, area), [(r["status"], len(r["days"])) for r in results])
            except Exception as e:
                err = e
                status["errors"] += 1
                log.warning("%s: ошибка %r", plain_title(cid, area), e)
            try:
                process(cid, area, results, err, cards or {})
            except Exception:
                log.exception("ошибка обработки результата")


def process(cid: str, area: str, results: Optional[list], err, cards: Dict[int, int]) -> None:
    if results is not None:
        days = all_days(results)
        store.office_changed(cid, area, bool(days), len(days))
    now = int(time.time())
    for sub in store.subs_for(cid, area):
        chat, head = sub["chat"], title(cid, area)
        if sub["paused"] and chat not in cards:
            continue
        if err is not None:
            fails = (sub["fails"] or 0) + 1
            store.update_sub(sub["id"], fails=fails)
            if fails == 3:
                send(chat, f"⚠️ {head}\nСайт DGT не отвечает уже 3 проверки подряд. "
                           "Продолжаю пробовать — напишу, когда заработает.", silent=True)
            if chat in cards:
                sub["fails"] = fails
                edit(chat, cards[chat], *sub_card(sub, "⚠️ <i>Сайт DGT не ответил, попробую позже.</i>"))
            continue
        if (sub["fails"] or 0) >= 3:
            send(chat, f"✅ {head}\nСайт DGT снова отвечает, слежу дальше.", silent=True)

        prev_days = {iso for iso, _ in all_days(sub["last"], sub["max_days"])}
        now_days = {iso for iso, _ in all_days(results, sub["max_days"])}
        new = now_days - prev_days
        sub.update(last=results, checked_at=now, fails=0)
        store.update_sub(sub["id"], last=results, checked_at=now, fails=0)

        alerted = False
        if new and not sub["paused"]:
            alerted = send(chat, *alert_view(sub, results, new), silent=is_quiet(chat)) is not None
        elif prev_days and not now_days and not sub["paused"]:
            send(chat, f"😔 {head}\nСвободные даты разобрали. Слежу дальше — напишу, как только появятся снова.",
                 silent=True)
        if chat in cards:
            if alerted:
                edit(chat, cards[chat], f"✅ {head}\nНашёл свободные даты — смотри сообщение ниже 👇",
                     inline([[b("📋 Открыть подписку", f"s:{sub['id']}")]]))
            else:
                edit(chat, cards[chat], *sub_card(sub))


def checker_loop() -> None:
    time.sleep(20)
    while True:
        started = time.time()
        try:
            keys = store.active_keys()
            if keys:
                run_checks(keys)
            status["last_cycle"] = int(time.time())
            status["cycles"] += 1
        except Exception:
            log.exception("ошибка цикла проверки")
        time.sleep(max(60.0, INTERVAL * random.uniform(0.85, 1.15) - (time.time() - started)))


def keepalive_loop() -> None:
    """Бесплатный Render усыпляет сервис без входящих запросов — стучимся к себе раз в 9 минут."""
    while True:
        time.sleep(9 * 60)
        try:
            requests.get(PUBLIC_URL + "/health", timeout=30)
        except Exception as e:
            log.warning("keepalive: %r", e)


def refresh_centros() -> None:
    try:
        fresh = dgt.list_centros()
        added = set(fresh) - set(dgt.CENTROS)
        dgt.CENTROS.update(fresh)
        if added:
            log.info("новые офисы на сайте: %s", ", ".join(fresh[c] for c in added))
    except Exception as e:
        log.warning("список офисов не обновился: %r", e)


# ---------- действия ----------

def search(chat: int, query: str) -> None:
    q = fold(query.strip())
    found = [c for c in dgt.CENTROS if q and q in fold(dgt.CENTROS[c])]
    if len(found) == 1:
        send(chat, *areas_view(found[0]))
    elif 1 < len(found) <= PAGE:
        rows = [[b(city(c), f"c:{c}")] for c in sorted(found, key=lambda c: fold(city(c)))]
        send(chat, f"🏢 Нашёл несколько офисов по запросу «{esc(query)}»:", inline(rows))
    elif found:
        send(chat, "Слишком много совпадений — уточни название города.")
    else:
        send(chat, *offices_view(0, f"😕 Не нашёл офис «{esc(query)}».\n\n🏢 <b>Выбери из списка</b>"))


def subscribe(chat: int, mid: int, cid: str, area: str) -> None:
    mine = store.subs_of(chat)
    exists = next((s for s in mine if s["centro"] == cid and s["area"] == area), None)
    if exists:
        edit(chat, mid, *sub_card(exists, "ℹ️ <i>Ты уже следишь за этим офисом.</i>"))
        return
    if len(mine) >= MAX_SUBS_PER_CHAT:
        edit(chat, mid, f"😅 Можно следить максимум за {MAX_SUBS_PER_CHAT} офисами.\n"
                        "Удали ненужную подписку в «📋 Мои подписки».", inline([[b("📋 Мои подписки", "l")]]))
        return
    keys = store.active_keys()
    if (cid, area) not in keys and len(keys) >= MAX_OFFICES:
        edit(chat, mid, "😅 Бот сейчас следит за максимальным числом офисов. Попробуй позже.")
        return
    store.add_sub(chat, cid, area)
    edit(chat, mid, f"✅ <b>Подписка оформлена</b>\n\n🏢 {title(cid, area)}\n\n"
                    "⏳ Делаю первую проверку — это займёт около минуты…")
    threading.Thread(target=run_checks, args=([(cid, area)], {chat: mid}), daemon=True).start()


def too_often(chat: int) -> bool:
    if time.time() - last_manual.get(chat, 0) < 60:
        return True
    last_manual[chat] = time.time()
    return False


def check_all(chat: int) -> None:
    subs = store.subs_of(chat)
    keys = sorted({(s["centro"], s["area"]) for s in subs if not s["paused"]})
    if not keys:
        if subs:
            send(chat, "⏸ Все подписки на паузе — нечего проверять.", inline([[b("📋 Мои подписки", "l")]]))
        else:
            send(chat, *list_view(chat))
        return
    if too_often(chat):
        send(chat, "⏳ Только что проверял — попробуй через минуту.")
        return
    mins = max(1, round(len(keys) * 25 / 60))
    mid = send(chat, f"🔄 Проверяю {plural(len(keys), 'офис', 'офиса', 'офисов')}… это займёт около {mins} мин")

    def job() -> None:
        run_checks(keys)
        if mid:
            edit(chat, mid, *list_view(chat, "✅ <b>Проверка завершена</b>"))

    threading.Thread(target=job, daemon=True).start()


def admin_view() -> str:
    t = store.totals()
    last = fmt_ts(status["last_cycle"]) if status["last_cycle"] else "ещё не было"
    return (f"🛠 <b>Админка</b>\n\nПользователей: {t['chats']}\nПодписок: {t['subs']}\n"
            f"Офисов в проверке: {t['offices']}/{MAX_OFFICES}\n\n"
            f"Последний цикл: {last}\nЦиклов: {status['cycles']}, ошибок сайта: {status['errors']}\n"
            f"Режим: {'webhook' if PUBLIC_URL else 'polling'}, база: {'Postgres' if store.PG else 'SQLite'}")


# ---------- обработчики ----------

def on_message(msg: dict) -> None:
    chat = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    name = msg.get("from", {}).get("first_name", "")
    if ALLOWED and str(chat) not in ALLOWED:
        send(chat, f"🔒 Это приватный бот. Твой chat id: <code>{chat}</code>")
        return
    store.ensure_chat(chat, name)
    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
    else:
        cmd, arg = text, ""

    if cmd == "/start":
        send(chat, welcome(name), MENU)
    elif cmd in (BTN_ADD, "/add", "/centros"):
        search(chat, arg) if arg.strip() else send(chat, *offices_view(0))
    elif cmd in (BTN_LIST, "/list"):
        send(chat, *list_view(chat))
    elif cmd in (BTN_CHECK, "/check"):
        check_all(chat)
    elif cmd in (BTN_SETTINGS, "/settings"):
        send(chat, *settings_view(chat))
    elif cmd in (BTN_HELP, "/help"):
        send(chat, HELP, MENU)
    elif cmd == "/admin" and ADMIN and str(chat) == ADMIN:
        send(chat, admin_view())
    elif text and not text.startswith("/"):
        search(chat, text)
    else:
        send(chat, HELP, MENU)


def on_callback(cb: dict) -> None:
    chat = cb["message"]["chat"]["id"]
    mid = cb["message"]["message_id"]
    data = cb.get("data") or ""
    kind, _, rest = data.partition(":")
    toast = None

    if ALLOWED and str(chat) not in ALLOWED:
        tg("answerCallbackQuery", callback_query_id=cb["id"])
        return

    if kind == "p":
        edit(chat, mid, *offices_view(int(rest or 0)))
    elif kind == "c" and rest in dgt.CENTROS:
        edit(chat, mid, *areas_view(rest))
    elif kind == "a":
        cid, _, area = rest.partition(":")
        if cid in dgt.CENTROS and area in dgt.AREAS:
            subscribe(chat, mid, cid, area)
    elif kind == "l":
        edit(chat, mid, *list_view(chat))
    elif kind == "ca":
        check_all(chat)
    elif kind == "q":
        store.set_quiet(chat, not store.get_chat(chat).get("quiet"))
        edit(chat, mid, *settings_view(chat))
    elif kind == "xa":
        edit(chat, mid, "🗑 <b>Удалить все подписки?</b>\nУведомления перестанут приходить.",
             inline([[b("Да, удалить всё", "xa!"), b("Отмена", "st")]]))
    elif kind == "xa!":
        store.forget_chat(chat)
        edit(chat, mid, "🗑 Все подписки удалены.", inline([[b("➕ Добавить офис", "p:0")]]))
    elif kind == "st":
        edit(chat, mid, *settings_view(chat))
    elif kind in ("s", "r", "h", "f", "fs", "z", "x", "xx"):
        sid, _, extra = rest.partition(":")
        sub = store.get_sub(int(sid)) if sid.isdigit() else None
        if not sub or sub["chat"] != chat:
            edit(chat, mid, "Эта подписка уже удалена.", inline([[b("📋 Мои подписки", "l")]]))
        elif kind == "s":
            edit(chat, mid, *sub_card(sub))
        elif kind == "r":
            if too_often(chat):
                toast = "⏳ Только что проверял — попробуй через минуту"
            else:
                edit(chat, mid, *sub_card(sub, "🔄 <i>Проверяю… около минуты</i>"))
                threading.Thread(target=run_checks, args=([(sub["centro"], sub["area"])], {chat: mid}),
                                 daemon=True).start()
        elif kind == "h":
            edit(chat, mid, *history_view(sub))
        elif kind == "f":
            edit(chat, mid, *filter_view(sub))
        elif kind == "fs":
            store.update_sub(sub["id"], max_days=int(extra) or None)
            edit(chat, mid, *sub_card(store.get_sub(sub["id"])))
        elif kind == "z":
            store.update_sub(sub["id"], paused=0 if sub["paused"] else 1)
            toast = "▶️ Снова слежу" if sub["paused"] else "⏸ Подписка на паузе"
            edit(chat, mid, *sub_card(store.get_sub(sub["id"])))
        elif kind == "x":
            edit(chat, mid, f"🗑 <b>Удалить подписку?</b>\n{title(sub['centro'], sub['area'])}",
                 inline([[b("Да, удалить", f"xx:{sub['id']}"), b("Отмена", f"s:{sub['id']}")]]))
        elif kind == "xx":
            store.delete_sub(sub["id"], chat)
            edit(chat, mid, f"🗑 Подписка удалена: {title(sub['centro'], sub['area'])}",
                 inline([[b("📋 Мои подписки", "l"), b("➕ Добавить", "p:0")]]))

    p = {"callback_query_id": cb["id"]}
    if toast:
        p["text"] = toast
    tg("answerCallbackQuery", **p)


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
            self._reply(200, json.dumps({"ok": True, "token": bool(TOKEN), **status}).encode())
        else:
            self._reply(404)

    do_HEAD = do_GET

    def do_POST(self) -> None:
        if self.path != "/telegram":
            return self._reply(404)
        if self.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
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


def setup_profile() -> None:
    tg("setMyCommands", commands=[
        {"command": "add", "description": "➕ Добавить офис"},
        {"command": "list", "description": "📋 Мои подписки"},
        {"command": "check", "description": "🔄 Проверить сейчас"},
        {"command": "settings", "description": "⚙️ Настройки"},
        {"command": "help", "description": "❓ Как это работает"},
    ])
    tg("setMyShortDescription",
       short_description="🔔 Уведомляю о свободных датах cita previa DGT (Tráfico) в любом офисе Испании")
    tg("setMyDescription", description=(
        "🇪🇸 Слежу за свободными датами cita previa DGT (Tráfico) и сразу пишу, когда они появляются.\n\n"
        "• любой из 68 офисов DGT\n• права, транспорт, регистрация, штрафы, обмен прав\n"
        "• даты на несколько месяцев вперёд и свободное время\n• фильтр дат, пауза, история\n\n"
        "Нажми «Старт» и выбери офис 👇"))


def main() -> None:
    store.init()
    threading.Thread(target=refresh_centros, daemon=True).start()

    if PUBLIC_URL:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
        if not TOKEN:
            log.error("TELEGRAM_TOKEN не задан — добавь его в Environment на Render. Жду…")
            server.serve_forever()
        if not store.PG:
            log.warning("DATABASE_URL не задан — подписки пропадут при перезапуске сервера")
        me = (tg("getMe") or {}).get("result")
        if not me:
            log.error("Telegram не принял TELEGRAM_TOKEN")
            server.serve_forever()
        setup_profile()
        tg("setWebhook", url=PUBLIC_URL + "/telegram", secret_token=SECRET,
           allowed_updates=["message", "callback_query"])
        log.info("Бот @%s запущен (webhook %s), проверка каждые %d мин", me["username"], PUBLIC_URL, INTERVAL // 60)
        threading.Thread(target=checker_loop, daemon=True).start()
        threading.Thread(target=keepalive_loop, daemon=True).start()
        server.serve_forever()
        return

    if not TOKEN:
        raise SystemExit("Нет TELEGRAM_TOKEN. Скопируй .env.example в .env и вставь токен от @BotFather.")
    me = (tg("getMe") or {}).get("result")
    if not me:
        raise SystemExit("Telegram не принял токен — проверь TELEGRAM_TOKEN в .env")
    hook = ((tg("getWebhookInfo") or {}).get("result") or {}).get("url")
    if hook and "--force" not in sys.argv:
        raise SystemExit(f"Бот уже работает на сервере ({hook}). Локальный запуск отключит его.\n"
                         "Если это нужно — запусти: python3 bot.py --force")
    tg("deleteWebhook")
    setup_profile()
    log.info("Бот @%s запущен локально, проверка каждые %d мин", me["username"], INTERVAL // 60)
    threading.Thread(target=checker_loop, daemon=True).start()

    offset = 0
    while True:
        data = tg("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
        if not data or not data.get("ok"):
            time.sleep(5)
            continue
        for upd in data["result"]:
            offset = upd["update_id"] + 1
            threading.Thread(target=dispatch, args=(upd,), daemon=True).start()


if __name__ == "__main__":
    main()
