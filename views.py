"""Экраны и форматирование: всё, что видит пользователь."""
from __future__ import annotations

import calendar
import html
import math
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import config
import dgt
import store
from tg import btn, ikb, url

esc = html.escape
BRAND_LINE = f"🇪🇸 <b>{config.BRAND}</b> · cita previa DGT"

LOAD = {"bajaOcupacion": "🟢", "mediaOcupacion": "🟡", "altaOcupacion": "🔴"}
LOAD_TEXT = {"bajaOcupacion": "🟢 много свободных мест", "mediaOcupacion": "🟡 занято 33–66%",
             "altaOcupacion": "🔴 почти всё занято"}
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WD_LONG = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь",
          "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
MONTHS_PREP = ["январе", "феврале", "марте", "апреле", "мае", "июне",
               "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
FILTERS = [(0, "любые"), (7, "до 7 дней"), (14, "до 14 дней"), (30, "до 30 дней"), (60, "до 60 дней")]
BLANK = "⠀"  # пустая клетка календаря: Telegram не принимает кнопки с пустым текстом
PAGE = 16
HOME = btn("🏠 Меню", "home")

UA_GUIDE = "https://ucraniaurgente.inclusion.gob.es/w/tramites-proteccion-temporal-desplazados-ucrania"
UA_CANJE = ("https://sede.dgt.gob.es/es/permisos-de-conducir/canjes-de-permisos/canjes-de-permisos-extranjeros/"
            "extracomunitarios/canje-paises-G3-SL-CP-UC/?pais=ua")


# ---------- общие помощники ----------

def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def plural(n: int, one: str, few: str, many: str) -> str:
    k = n % 100
    word = many if 11 <= k <= 14 else one if k % 10 == 1 else few if 2 <= k % 10 <= 4 else many
    return f"{n} {word}"


def is_owner(chat: int) -> bool:
    return chat in config.OWNERS


def is_admin(chat: int) -> bool:
    return is_owner(chat) or store.get_chat(chat).get("role") == "admin"


def city(cid: str) -> str:
    return dgt.CENTROS.get(cid, cid).split(" de Tráfico de ", 1)[-1]


def area_label(area: str, label: Optional[str] = None) -> str:
    return (label or dgt.AREA_LABELS.get(area) or area).split(" (")[0].split(" - ")[0]


def area_emoji(label: str) -> str:
    l = fold(label)
    for key, emoji in (("canje", "🔁"), ("sancion", "💶"), ("matricul", "📝"), ("examen", "🎓"),
                       ("renovacion", "♻️"), ("conductores / veh", "🚦"), ("conductor", "🪪"), ("vehicul", "🚗")):
        if key in l:
            return emoji
    return "📄"


def area_hint(label: str) -> str:
    l = fold(label)
    for key, hint in (("canje", "обмен иностранных прав"), ("sancion", "штрафы"),
                      ("matricul", "регистрация ТС"), ("examen", "экзамены на права"),
                      ("renovacion", "продление прав ЕС"), ("conductores / veh", "права и транспорт"),
                      ("conductor", "права, водители"), ("vehicul", "транспорт")):
        if key in l:
            return hint
    return ""


def sub_area(sub: dict) -> str:
    return area_label(sub["area"], sub.get("area_label"))


def title(sub: dict) -> str:
    label = sub_area(sub)
    return f"<b>{esc(city(sub['centro']))}</b> · {area_emoji(label)} {esc(label)}"


def plain_title(sub: dict) -> str:
    return f"{city(sub['centro'])} · {sub_area(sub)}"


def today() -> date:
    return datetime.now(config.TZ).date()


def long_day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WD_LONG[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"


def short_day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS_GEN[d.month - 1][:3]}"


def day_range(days: List[Tuple[str, str]]) -> str:
    a, b = date.fromisoformat(days[0][0]), date.fromisoformat(days[-1][0])
    if a == b:
        return f"{a.day} {MONTHS_GEN[a.month - 1]}"
    if a.month == b.month:
        return f"{a.day}–{b.day} {MONTHS_GEN[a.month - 1]}"
    return f"{a.day} {MONTHS_GEN[a.month - 1][:3]} – {b.day} {MONTHS_GEN[b.month - 1][:3]}"


def fmt_ts(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, config.TZ)
    if dt.date() == today():
        return f"сегодня в {dt:%H:%M}"
    if dt.date() == today() - timedelta(days=1):
        return f"вчера в {dt:%H:%M}"
    return f"{WD[dt.weekday()]} {dt:%d.%m} в {dt:%H:%M}"


def fmt_dur(sec: int) -> str:
    m = max(1, round(sec / 60))
    if m < 60:
        return f"{m} мин"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} ч {m} мин" if m else f"{h} ч"
    return plural(round(h / 24), "день", "дня", "дней")


# ---------- данные проверок ----------

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


def hours_for(results: Optional[list], iso: str) -> List[str]:
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
            lines.append(f"<b>{MONTHS[d.month - 1].capitalize()} {d.year}</b>")
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
    return "\n".join(lines)


def nearest_lines(results: list, days: List[Tuple[str, str]]) -> List[str]:
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
        return "🟢", f"{plural(len(days), 'день', 'дня', 'дней')}, с {short_day(days[0][0])}"
    if all_days(last):
        return "🟡", "есть даты, но позже фильтра"
    status = last[0]["status"] if last else dgt.UNKNOWN
    return {
        dgt.FULL: ("🔴", "мест нет"),
        dgt.NO_AREA: ("⚪️", "такой записи в офисе нет"),
        dgt.NOT_CONFIGURED: ("⚪️", "офис не принимает эту запись"),
    }.get(status, ("❔", "не удалось прочитать сайт"))


# ---------- главный экран ----------

def dashboard(chat: int, name: str = "", next_check: Optional[int] = None, note: str = "") -> Tuple[str, dict]:
    subs = store.subs_of(chat)
    lines = [BRAND_LINE, ""]
    if not subs:
        hello = f"Привет, {esc(name)}! 👋" if name else "Привет! 👋"
        lines += [
            hello,
            "Я слежу за свободными датами записи в <b>DGT (Tráfico)</b> и сразу присылаю уведомление, "
            "когда они появляются.",
            "",
            "<b>Как начать</b>",
            "1️⃣ Нажми «➕ Добавить офис»",
            "2️⃣ Выбери город и тип записи",
            "3️⃣ Жди уведомление 🔔",
        ]
    else:
        lines.append(f"📋 <b>Подписки</b> · {len(subs)} из {store.setting('max_subs')}")
        rows = []
        for s in subs:
            emoji, text = summary(s)
            rows.append(f"{emoji} <b>{esc(city(s['centro']))}</b> · {esc(sub_area(s))} — {text}")
        lines.append("<blockquote>" + "\n".join(rows) + "</blockquote>")
        if store.setting("checks_paused"):
            lines.append("⏸ Проверки временно остановлены администратором")
        elif next_check:
            mins = max(1, math.ceil((next_check - time.time()) / 60))
            lines.append(f"⏱ Следующая проверка через {plural(mins, 'минуту', 'минуты', 'минут')}")
    if note:
        lines += ["", note]

    rows = [[btn("➕ Добавить офис", "p:0")]]
    if subs:
        rows.append([btn(f"📋 Подписки ({len(subs)})", "l"), btn("🔄 Проверить", "ca")])
    rows.append([btn("⚙️ Настройки", "st"), btn("❓ Помощь", "hp")])
    rows.append([btn("🇺🇦 Для украинцев", "ua")])
    if is_admin(chat):
        rows.append([btn("🛠 Админ-панель", "ad")])
    return "\n".join(lines), ikb(rows)


# ---------- выбор офиса и записи ----------

def offices(page: int = 0, header: str = "") -> Tuple[str, dict]:
    ids = sorted(dgt.CENTROS, key=lambda c: fold(city(c)))
    pages = math.ceil(len(ids) / PAGE)
    page %= pages
    chunk = ids[page * PAGE:(page + 1) * PAGE]
    rows = [[btn(city(c), f"c:{c}") for c in chunk[i:i + 2]] for i in range(0, len(chunk), 2)]
    rows.append([btn("◀️", f"p:{page - 1}"), btn(f"{page + 1} / {pages}", "noop"), btn("▶️", f"p:{page + 1}")])
    rows.append([HOME])
    text = (header or "🏢 <b>Выбери офис DGT</b>") + "\n\nИли просто напиши название города, например <i>Valencia</i>."
    return text, ikb(rows)


def search_results(query: str, found: List[str]) -> Tuple[str, dict]:
    rows = [[btn(city(c), f"c:{c}")] for c in sorted(found, key=lambda c: fold(city(c)))]
    rows.append([btn("🏢 Все офисы", "p:0"), HOME])
    return f"🔎 Офисы по запросу «{esc(query)}»:", ikb(rows)


def loading(text: str) -> Tuple[str, dict]:
    return f"⏳ {text}", ikb([])


def areas(cid: str, options: List[Tuple[str, str]]) -> Tuple[str, dict]:
    text = f"🏢 <b>{esc(city(cid))}</b>\n<i>{esc(dgt.CENTROS[cid])}</i>\n\nКакой тип записи нужен?"
    rows = []
    for code, label in options:
        short = area_label(code, label)
        hint = area_hint(label)
        rows.append([btn(f"{area_emoji(label)} {short}" + (f" — {hint}" if hint else ""), f"a:{cid}:{code}")])
    rows.append([btn("⬅️ Офисы", "p:0"), HOME])
    return text, ikb(rows)


def areas_error(cid: str) -> Tuple[str, dict]:
    return (f"😕 Сайт DGT не ответил, не могу получить список услуг для <b>{esc(city(cid))}</b>.\n"
            "Попробуй ещё раз через минуту.",
            ikb([[btn("🔄 Повторить", f"c:{cid}")], [btn("⬅️ Офисы", "p:0"), HOME]]))


# ---------- подписки ----------

def subs_list(chat: int, header: str = "") -> Tuple[str, dict]:
    subs = store.subs_of(chat)
    if not subs:
        return ("📋 <b>Подписок пока нет</b>\n\nНажми «➕ Добавить офис» — и я начну следить за свободными датами.",
                ikb([[btn("➕ Добавить офис", "p:0")], [HOME]]))
    lines = [header or f"📋 <b>Твои подписки</b> · {len(subs)} из {store.setting('max_subs')}", ""]
    rows = []
    for s in subs:
        emoji, text = summary(s)
        lines.append(f"{emoji} {title(s)}\n      <i>{text}</i>")
        rows.append([btn(f"{emoji} {plain_title(s)}", f"s:{s['id']}")])
    lines.append("\nНажми на подписку — покажу подробности.")
    rows.append([btn("➕ Добавить", "p:0"), btn("🔄 Проверить все", "ca")])
    rows.append([HOME])
    return "\n".join(lines), ikb(rows)


def card(sub: dict, note: str = "") -> Tuple[str, dict]:
    last, sid = sub.get("last"), sub["id"]
    lines = [f"🏢 {title(sub)}"]
    info = next((r for r in last or [] if r.get("address")), None)
    if info:
        where = [f"📍 {esc(info['address'])}"]
        if info.get("schedule"):
            where.append(f"🕘 {esc(info['schedule'])}")
        lines.append("<blockquote>" + "\n".join(where) + "</blockquote>")
    else:
        lines.append("")

    days = all_days(last, sub.get("max_days"))
    if sub.get("paused"):
        lines.append("⏸ <b>Подписка на паузе</b> — уведомления не приходят\n")
    if days:
        lines.append(f"🟢 <b>{plural(len(days), 'свободный день', 'свободных дня', 'свободных дней')}</b> · {day_range(days)}")
        lines += nearest_lines(last, days)
        lines.append(f"<blockquote expandable>{days_block(days)}</blockquote>")
    elif not sub.get("paused"):
        emoji, text = summary(sub)
        lines.append(f"{emoji} <b>{text[0].upper() + text[1:]}</b>")
        if emoji in ("🔴", "🟡", "⏳"):
            lines.append("Напишу, как только появятся подходящие даты.")
        elif emoji == "⚪️":
            lines.append("Похоже, в этом офисе такой тип записи называется иначе — выбери его заново.")
    lines.append("")
    lines.append(f"📅 Даты: <b>{filter_label(sub.get('max_days'))}</b>"
                 + (f" · 🕐 {fmt_ts(sub['checked_at'])}" if sub.get("checked_at") else ""))
    if note:
        lines.append(f"\n{note}")

    status = (last or [{}])[0].get("status")
    rows = [[url("📝 Записаться на сайте DGT", dgt.START_URL)]]
    if status == dgt.NO_AREA:
        rows.append([btn("🔁 Выбрать тип записи заново", f"c:{sub['centro']}")])
    rows += [
        [btn("🗓 Календарь", f"k:{sid}:0"), btn("🔄 Обновить", f"r:{sid}")],
        [btn(f"📅 {filter_label(sub.get('max_days')).capitalize()}", f"f:{sid}"),
         btn("▶️ Возобновить" if sub.get("paused") else "⏸ Пауза", f"z:{sid}")],
        [btn("📊 История", f"h:{sid}"), btn("🗑 Удалить", f"x:{sid}")],
        [btn("⬅️ Подписки", "l"), HOME],
    ]
    return "\n".join(lines), ikb(rows)


def calendar_view(sub: dict, idx: int = 0) -> Tuple[str, dict]:
    sid = sub["id"]
    days = all_days(sub.get("last"))
    back = [btn("⬅️ К подписке", f"s:{sid}"), HOME]
    if not days:
        return (f"🗓 <b>Календарь</b> · {title(sub)}\n\nСвободных дат сейчас нет. Напишу, как только появятся.",
                ikb([back]))
    months = sorted({iso[:7] for iso, _ in days})
    idx %= len(months)
    y, m = map(int, months[idx].split("-"))
    loads = dict(days)
    in_month = [d for d in days if d[0].startswith(months[idx])]
    rows = [[
        btn("◀️", f"k:{sid}:{idx - 1}") if len(months) > 1 else btn(BLANK, "noop"),
        btn(f"{MONTHS[m - 1].capitalize()} {y}", "noop"),
        btn("▶️", f"k:{sid}:{idx + 1}") if len(months) > 1 else btn(BLANK, "noop"),
    ], [btn(w, "noop") for w in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")]]
    for week in calendar.Calendar().monthdayscalendar(y, m):
        row = []
        for d in week:
            if not d:
                row.append(btn(BLANK, "noop"))
                continue
            iso = f"{y:04d}-{m:02d}-{d:02d}"
            row.append(btn(f"{d}{LOAD.get(loads[iso], '')}" if iso in loads else str(d), f"d:{sid}:{iso}"))
        rows.append(row)
    rows.append(back)
    text = (f"🗓 <b>Календарь</b> · {title(sub)}\n\n"
            f"В {MONTHS_PREP[m - 1]}: "
            f"<b>{plural(len(in_month), 'свободный день', 'свободных дня', 'свободных дней')}</b>\n"
            "🟢 много мест · 🟡 средне · 🔴 мало\n"
            "<i>Нажми на день — покажу подробности</i>")
    return text, ikb(rows)


def day_popup(sub: dict, iso: str) -> str:
    loads = dict(all_days(sub.get("last")))
    head = long_day(iso).capitalize()
    if iso not in loads:
        return f"{head}\nВ этот день свободных мест нет"
    text = f"{head}\n{LOAD_TEXT.get(loads[iso], '')}"
    hours = hours_for(sub.get("last"), iso)
    if hours:
        text += "\n⏰ " + " · ".join(hours[:10]) + (" …" if len(hours) > 10 else "")
    return text


def filter_view(sub: dict) -> Tuple[str, dict]:
    text = (f"📅 <b>Какие даты присылать?</b>\n{title(sub)}\n\n"
            "Например, если у тебя уже есть запись через месяц, выбери «до 30 дней» — "
            "и я напишу только о более ранних датах.")
    cur = sub.get("max_days") or 0
    rows = [[btn(("✅ " if v == cur else "") + label.capitalize(), f"fs:{sub['id']}:{v}")] for v, label in FILTERS]
    rows.append([btn("⬅️ К подписке", f"s:{sub['id']}")])
    return text, ikb(rows)


def history_view(sub: dict) -> Tuple[str, dict]:
    evs = store.events(sub["centro"], sub["area"], 30)
    lines = [f"📊 <b>История</b> · {title(sub)}", ""]
    if not evs:
        lines.append("Пока ни разу не видел здесь свободных мест.\n"
                     "История начнёт копиться, как только они появятся.")
    else:
        if not evs[0]["closed_at"]:
            lines.append(f"🟢 Места есть прямо сейчас — появились {fmt_ts(evs[0]['opened_at'])}\n")
        lines.append("<b>Когда появлялись места</b> (время Мадрида):")
        items = []
        for e in evs[:10]:
            dur = "ещё есть" if not e["closed_at"] else f"держались {fmt_dur(e['closed_at'] - e['opened_at'])}"
            items.append(f"• {fmt_ts(e['opened_at'])} — {dur}, {plural(e['days'] or 0, 'день', 'дня', 'дней')}")
        lines.append("<blockquote>" + "\n".join(items) + "</blockquote>")
        if len(evs) >= 3:
            hour, _ = Counter(datetime.fromtimestamp(e["opened_at"], config.TZ).hour for e in evs).most_common(1)[0]
            lines.append(f"⏰ Чаще всего появляются между {hour}:00 и {hour + 1}:00")
        closed = [e["closed_at"] - e["opened_at"] for e in evs if e["closed_at"]]
        if closed:
            lines.append(f"⌛️ В среднем держатся {fmt_dur(sum(closed) // len(closed))}")
        lines.append(f"\n<i>Точность — интервал проверки, {store.setting('interval')} мин.</i>")
    return "\n".join(lines), ikb([[btn("⬅️ К подписке", f"s:{sub['id']}")]])


def delete_confirm(sub: dict) -> Tuple[str, dict]:
    return (f"🗑 <b>Удалить подписку?</b>\n{title(sub)}",
            ikb([[btn("Да, удалить", f"xx:{sub['id']}"), btn("Отмена", f"s:{sub['id']}")]]))


# ---------- уведомления ----------

def alert(sub: dict, results: list, new: Set[str]) -> Tuple[str, dict]:
    days = all_days(results, sub.get("max_days"))
    fresh = len([d for d in days if d[0] in new])
    lines = ["🔔 <b>Есть свободные даты!</b>", f"🏢 {title(sub)}", ""]
    lines += nearest_lines(results, days)
    lines.append("")
    lines.append(f"📅 <b>{plural(len(days), 'день', 'дня', 'дней')}</b> · {day_range(days)}"
                 + (f" · новых {fresh}" if fresh and fresh != len(days) else ""))
    lines.append(f"<blockquote expandable>{days_block(days, new)}</blockquote>")
    if sub.get("max_days"):
        lines.append(f"<i>Показаны даты в пределах {sub['max_days']} дней</i>")
    lines.append(f"<i>На сайте: {esc(city(sub['centro']))} → {esc(sub_area(sub))} → Continuar → Pedir cita</i>")
    kb = ikb([
        [url("📝 Записаться на сайте DGT", dgt.START_URL)],
        [btn("🗓 Календарь", f"k:{sub['id']}:0"), btn("✖️ Скрыть", "hide")],
    ])
    return "\n".join(lines), kb


def gone(sub: dict) -> Tuple[str, dict]:
    now = datetime.now(config.TZ)
    return (f"😔 {title(sub)}\nСвободные даты разобрали ({now:%H:%M}). Слежу дальше — напишу, как только появятся.",
            ikb([[btn("✖️ Скрыть", "hide")]]))


# ---------- настройки, помощь ----------

def settings_view(chat: int) -> Tuple[str, dict]:
    quiet = store.get_chat(chat).get("quiet")
    text = ("⚙️ <b>Настройки</b>\n\n"
            f"🌙 <b>Тихий режим ночью</b>: {'включён' if quiet else 'выключен'}\n"
            "<i>С 00:00 до 08:00 по Мадриду уведомления приходят без звука.</i>\n\n"
            f"⏱ Проверка каждые {store.setting('interval')} мин\n"
            f"🏢 До {store.setting('max_subs')} офисов одновременно")
    return text, ikb([
        [btn(f"🌙 Тихий режим: {'вкл' if quiet else 'выкл'}", "q")],
        [btn("🗑 Удалить все подписки", "xa")],
        [HOME],
    ])


def help_view() -> Tuple[str, dict]:
    text = (
        "❓ <b>Как это работает</b>\n\n"
        "Я захожу на сайт DGT так же, как это сделал бы ты: выбираю офис и тип записи и смотрю календарь. "
        "Как только появляются свободные дни — присылаю уведомление с датами и временем.\n\n"
        "<b>Цвета</b>\n"
        "<blockquote>🟢 много свободных мест\n🟡 занято 33–66%\n🔴 почти всё занято</blockquote>\n"
        "<b>Что умею</b>\n"
        "• следить за несколькими офисами сразу\n"
        "• показывать календарь и свободное время\n"
        "• присылать только даты раньше нужной — «📅» в подписке\n"
        "• пауза, история появления мест, тихий режим ночью\n\n"
        "<b>Советы</b>\n"
        "• Места быстро разбирают — открывай сайт сразу после уведомления\n"
        "• Держи под рукой DNI/NIE: сайт спросит данные при записи\n\n"
        "Записываешься ты сам — я только сообщаю, когда есть места."
    )
    return text, ikb([[btn("🇺🇦 Для украинцев", "ua")], [HOME]])


def ukraine_view() -> Tuple[str, dict]:
    text = (
        "🇺🇦 <b>Для украинцев в Испании</b>\n\n"
        "🪪 <b>Украинские права</b>\n"
        "<blockquote>• Действуют в Испании, пока у тебя есть временная защита — сейчас до <b>4 марта 2027</b>.\n"
        "• Их можно обменять на испанские (<b>canje</b>) в DGT: выбери офис → «Canjes», "
        "и я напишу, когда появится запись.\n"
        "• С TIE обмен можно делать сразу, с резолюцией о защите — через 6 месяцев после въезда или выдачи. "
        "Присяжный перевод не нужен.</blockquote>\n"
        "📄 <b>Временная защита и TIE</b>\n"
        "<blockquote>• Все TIE по временной защите продлены автоматически до 4 марта 2027 "
        "(Orden INT/96/2026) — никуда идти не нужно.\n"
        "• Еврокомиссия предложила продлить защиту до 4 марта 2028 — пока не утверждено.\n"
        "• Новая заявка: центры CREADE по телефону — Pozuelo (Madrid) +34 666 800 194, "
        "Málaga +34 628 216 478, Barcelona +34 93 238 21 99; в других провинциях — в полиции.\n"
        "• С августа 2026 для новой защиты нужно подтвердить исполнение воинской обязанности "
        "Украины или освобождение от неё.</blockquote>\n"
        "<i>Информация на сентябрь 2026 — перед визитом сверяйся с официальными сайтами.</i>"
    )
    return text, ikb([
        [btn("🔁 Следить за записью на canje", "p:0")],
        [url("🪪 Canje прав — DGT", UA_CANJE), url("🌐 Ucrania Urgente", UA_GUIDE)],
        [HOME],
    ])


def pending_view() -> Tuple[str, dict]:
    return (f"{BRAND_LINE}\n\n⏳ <b>Заявка на доступ отправлена</b>\n"
            "Бот сейчас работает по приглашениям. Как только администратор одобрит заявку — я напишу.", ikb([]))


def banned_view() -> Tuple[str, dict]:
    return f"{BRAND_LINE}\n\n🚫 Доступ к боту закрыт.", ikb([])
