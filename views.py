"""Экраны и тексты для пользователей — на русском и украинском. Админка — только по-русски."""
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
LANGS = {"uk": "🇺🇦 Українська", "ru": "🇷🇺 Русский"}

CAL = {
    "ru": {
        "wd": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
        "wd_long": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
        "months": ["январь", "февраль", "март", "апрель", "май", "июнь",
                   "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"],
        "gen": ["января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"],
        "prep": ["в январе", "в феврале", "в марте", "в апреле", "в мае", "в июне",
                 "в июле", "в августе", "в сентябре", "в октябре", "в ноябре", "в декабре"],
        "head": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
    },
    "uk": {
        "wd": ["пн", "вт", "ср", "чт", "пт", "сб", "нд"],
        "wd_long": ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"],
        "months": ["січень", "лютий", "березень", "квітень", "травень", "червень",
                   "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"],
        "gen": ["січня", "лютого", "березня", "квітня", "травня", "червня",
                "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"],
        "prep": ["у січні", "у лютому", "у березні", "у квітні", "у травні", "у червні",
                 "у липні", "у серпні", "у вересні", "у жовтні", "у листопаді", "у грудні"],
        "head": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
    },
}
LOAD = {"bajaOcupacion": "🟢", "mediaOcupacion": "🟡", "altaOcupacion": "🔴"}
FILTER_DAYS = (0, 7, 14, 30, 60)
BLANK = "⠀"  # пустая клетка календаря: Telegram не принимает кнопки с пустым текстом
PAGE = 16

DGT_SEDE = "https://sede.dgt.gob.es/es/"
UA_GUIDE = "https://ucraniaurgente.inclusion.gob.es/w/tramites-proteccion-temporal-desplazados-ucrania"
UA_CANJE = ("https://sede.dgt.gob.es/es/permisos-de-conducir/canjes-de-permisos/canjes-de-permisos-extranjeros/"
            "extracomunitarios/canje-paises-G3-SL-CP-UC/?pais=ua")

# Категории записи — общие для всех офисов (у офисов разные коды, см. dgt.AREA_LABELS)
CATS = {
    "lic": ("🪪", "Права, водители", "Права, водії"),
    "veh": ("🚗", "Транспорт", "Транспорт"),
    "cnj": ("🔁", "Canje — обмен прав", "Canje — обмін прав"),
    "exm": ("🎓", "Экзамены на права", "Іспити на права"),
    "san": ("💶", "Штрафы", "Штрафи"),
    "mat": ("📝", "Регистрация ТС", "Реєстрація ТЗ"),
    "rpc": ("♻️", "Продление прав ЕС", "Продовження прав ЄС"),
}


# ---------- язык и общие помощники ----------

def tx(lang: str, ru: str, uk: str) -> str:
    return uk if lang == "uk" else ru


def lang_of(chat: int) -> str:
    return store.get_chat(chat).get("lang") or "ru"


def home_btn(lang: str) -> dict:
    return btn(tx(lang, "🏠 Меню", "🏠 Меню"), "home")


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def plural(n: int, one: str, few: str, many: str) -> str:
    k = n % 100
    word = many if 11 <= k <= 14 else one if k % 10 == 1 else few if 2 <= k % 10 <= 4 else many
    return f"{n} {word}"


def pl(lang: str, n: int, ru: Tuple[str, str, str], uk: Tuple[str, str, str]) -> str:
    return plural(n, *(uk if lang == "uk" else ru))


def days_word(lang: str, n: int) -> str:
    return pl(lang, n, ("день", "дня", "дней"), ("день", "дні", "днів"))


def free_days_word(lang: str, n: int) -> str:
    return pl(lang, n, ("свободный день", "свободных дня", "свободных дней"),
              ("вільний день", "вільні дні", "вільних днів"))


def is_owner(chat: int) -> bool:
    return chat in config.OWNERS


def is_admin(chat: int) -> bool:
    return is_owner(chat) or store.get_chat(chat).get("role") == "admin"


def city(cid: str) -> str:
    return dgt.CENTROS.get(cid, cid).split(" de Tráfico de ", 1)[-1]


def area_label(area: str, label: Optional[str] = None) -> str:
    return (label or dgt.AREA_LABELS.get(area) or area).split(" (")[0].split(" - ")[0]


def cats_of(label: str) -> Set[str]:
    """К каким общим категориям относится тип записи офиса."""
    l = fold(label)
    for key, cats in (("canje", {"cnj"}), ("sancion", {"san"}), ("matricul", {"mat"}), ("examen", {"exm"}),
                      ("renovacion", {"rpc"}), ("conductores / veh", {"lic", "veh"}), ("conductor", {"lic"}),
                      ("vehicul", {"veh"})):
        if key in l:
            return cats
    return set()


def area_emoji(label: str) -> str:
    cats = cats_of(label)
    if cats == {"lic", "veh"}:
        return "🚦"
    return CATS[next(iter(cats))][0] if cats else "📄"


def area_hint(lang: str, label: str) -> str:
    cats = cats_of(label)
    if cats == {"lic", "veh"}:
        return tx(lang, "права и транспорт", "права і транспорт")
    if not cats:
        return ""
    _, ru, uk = CATS[next(iter(cats))]
    return tx(lang, ru, uk).split(" — ")[-1].lower()


def sub_area(sub: dict) -> str:
    return area_label(sub["area"], sub.get("area_label"))


def title(sub: dict) -> str:
    label = sub_area(sub)
    return f"<b>{esc(city(sub['centro']))}</b> · {area_emoji(label)} {esc(label)}"


def plain_title(sub: dict) -> str:
    return f"{city(sub['centro'])} · {sub_area(sub)}"


def today() -> date:
    return datetime.now(config.TZ).date()


def long_day(lang: str, iso: str) -> str:
    d, c = date.fromisoformat(iso), CAL[lang]
    return f"{c['wd_long'][d.weekday()]}, {d.day} {c['gen'][d.month - 1]}"


def short_day(lang: str, iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {CAL[lang]['gen'][d.month - 1][:3]}"


def wd_day(lang: str, iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{CAL[lang]['wd'][d.weekday()]} {d.day} {CAL[lang]['gen'][d.month - 1][:3]}"


def day_range(lang: str, days: List[Tuple[str, str]]) -> str:
    a, b = date.fromisoformat(days[0][0]), date.fromisoformat(days[-1][0])
    gen = CAL[lang]["gen"]
    if a == b:
        return f"{a.day} {gen[a.month - 1]}"
    if a.month == b.month:
        return f"{a.day}–{b.day} {gen[a.month - 1]}"
    return f"{a.day} {gen[a.month - 1][:3]} – {b.day} {gen[b.month - 1][:3]}"


def fmt_ts(ts: int, lang: str = "ru") -> str:
    dt = datetime.fromtimestamp(ts, config.TZ)
    if dt.date() == today():
        return tx(lang, f"сегодня в {dt:%H:%M}", f"сьогодні о {dt:%H:%M}")
    if dt.date() == today() - timedelta(days=1):
        return tx(lang, f"вчера в {dt:%H:%M}", f"вчора о {dt:%H:%M}")
    return f"{CAL[lang]['wd'][dt.weekday()]} {dt:%d.%m} " + tx(lang, f"в {dt:%H:%M}", f"о {dt:%H:%M}")


def fmt_dur(sec: int, lang: str = "ru") -> str:
    m = max(1, round(sec / 60))
    if m < 60:
        return tx(lang, f"{m} мин", f"{m} хв")
    h, m = divmod(m, 60)
    if h < 24:
        return tx(lang, f"{h} ч", f"{h} год") + (tx(lang, f" {m} мин", f" {m} хв") if m else "")
    return days_word(lang, round(h / 24))


def filter_label(lang: str, max_days: Optional[int]) -> str:
    return tx(lang, "любые", "будь-які") if not max_days else tx(lang, f"до {max_days} дней", f"до {max_days} днів")


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


def days_block(lang: str, days: List[Tuple[str, str]], new: Set[str] = frozenset(), limit: int = 45) -> str:
    """Дни по месяцам, одна строка — одна неделя. Новые дни выделены жирным."""
    c = CAL[lang]
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
            lines.append(f"<b>{c['months'][d.month - 1].capitalize()} {d.year}</b>")
        week = d.isocalendar()[1]
        if week != cur_week and row:
            lines.append("  ".join(row))
            row = []
        cur_week = week
        label = f"{c['wd'][d.weekday()]} {d.day}"
        row.append(f"<b>{label}</b>{LOAD.get(load, '▫️')}" if iso in new else f"{label}{LOAD.get(load, '▫️')}")
    if row:
        lines.append("  ".join(row))
    if len(days) > limit:
        lines.append(tx(lang, "…и ещё ", "…і ще ") + days_word(lang, len(days) - limit))
    return "\n".join(lines)


def nearest_lines(lang: str, results: list, days: List[Tuple[str, str]]) -> List[str]:
    iso = days[0][0]
    lines = [tx(lang, "⭐️ Ближайшая: ", "⭐️ Найближча: ") + f"<b>{long_day(lang, iso)}</b>"]
    hours = hours_for(results, iso)
    if hours:
        lines.append("⏰ " + " · ".join(hours[:12]) + (f" <i>+{len(hours) - 12}</i>" if len(hours) > 12 else ""))
    return lines


def booked_label(lang: str, sub: dict) -> str:
    return long_day(lang, sub["booked_date"]) + (tx(lang, f" в {sub['booked_time']}", f" о {sub['booked_time']}")
                                                 if sub.get("booked_time") else "")


def summary(sub: dict, lang: Optional[str] = None) -> Tuple[str, str]:
    """Короткий статус подписки: (эмодзи, текст)."""
    lang = lang or lang_of(sub["chat"])
    last = sub.get("last")
    if sub.get("booked_date"):
        when = short_day(lang, sub["booked_date"]) + (f" {sub['booked_time']}" if sub.get("booked_time") else "")
        return "✅", tx(lang, f"записан на {when}", f"записаний на {when}")
    if sub.get("paused"):
        return "⏸", tx(lang, "на паузе", "на паузі")
    if last is None:
        return "⏳", tx(lang, "ещё не проверялось", "ще не перевірялося")
    if (sub.get("fails") or 0) >= 3:
        return "⚠️", tx(lang, "сайт DGT не отвечает", "сайт DGT не відповідає")
    days = all_days(last, sub.get("max_days"))
    if days:
        return "🟢", days_word(lang, len(days)) + tx(lang, ", с ", ", з ") + short_day(lang, days[0][0])
    if all_days(last):
        return "🟡", tx(lang, "есть даты, но позже фильтра", "є дати, але пізніше фільтра")
    status = last[0]["status"] if last else dgt.UNKNOWN
    return {
        dgt.FULL: ("🔴", tx(lang, "мест нет", "місць немає")),
        dgt.NO_AREA: ("⚪️", tx(lang, "такой записи в офисе нет", "такого запису в офісі немає")),
        dgt.NOT_CONFIGURED: ("⚪️", tx(lang, "офис не принимает эту запись", "офіс не приймає цей запис")),
    }.get(status, ("❔", tx(lang, "не удалось прочитать сайт", "не вдалося прочитати сайт")))


# ---------- язык ----------

def language_picker(back: str = "") -> Tuple[str, dict]:
    rows = [[btn(label, f"lg:{code}" + (f":{back}" if back else ""))] for code, label in LANGS.items()]
    return f"{BRAND_LINE}\n\n🌐 <b>Оберіть мову</b>\n🌐 <b>Выберите язык</b>", ikb(rows)


# ---------- главный экран ----------

def dashboard(chat: int, name: str = "", next_check: Optional[int] = None, note: str = "") -> Tuple[str, dict]:
    lang = lang_of(chat)
    subs = store.subs_of(chat)
    lines = [BRAND_LINE, ""]
    if not subs:
        hello = tx(lang, "Привет", "Привіт") + (f", {esc(name)}" if name else "") + "! 👋"
        lines += [
            hello,
            tx(lang, "Я слежу за свободными датами записи в <b>DGT (Tráfico)</b> и сразу присылаю уведомление, "
                     "когда они появляются.",
               "Я стежу за вільними датами запису в <b>DGT (Tráfico)</b> і одразу надсилаю сповіщення, "
               "щойно вони з’являються."),
            "",
            tx(lang, "<b>Как начать</b>", "<b>Як почати</b>"),
            tx(lang, "1️⃣ Нажми «➕ Добавить офис»", "1️⃣ Натисни «➕ Додати офіс»"),
            tx(lang, "2️⃣ Выбери город и тип записи", "2️⃣ Обери місто і тип запису"),
            tx(lang, "3️⃣ Жди уведомление 🔔", "3️⃣ Чекай на сповіщення 🔔"),
            "",
            tx(lang, "📡 Или запусти <b>радар</b> — найду ближайший офис, где записаться можно раньше всего.",
               "📡 Або запусти <b>радар</b> — знайду найближчий офіс, де записатися можна найшвидше."),
        ]
    else:
        lines.append(tx(lang, "📋 <b>Подписки</b> · ", "📋 <b>Підписки</b> · ") + f"{len(subs)}/{store.setting('max_subs')}")
        rows = []
        for s in subs:
            emoji, text = summary(s, lang)
            rows.append(f"{emoji} <b>{esc(city(s['centro']))}</b> · {esc(sub_area(s))} — {text}")
        lines.append("<blockquote>" + "\n".join(rows) + "</blockquote>")
        if store.setting("checks_paused"):
            lines.append(tx(lang, "⏸ Проверки временно остановлены", "⏸ Перевірки тимчасово зупинені"))
        elif next_check:
            mins = max(1, math.ceil((next_check - time.time()) / 60))
            lines.append(tx(lang, "⏱ Следующая проверка через ", "⏱ Наступна перевірка за ")
                         + pl(lang, mins, ("минуту", "минуты", "минут"), ("хвилину", "хвилини", "хвилин")))
    if note:
        lines += ["", note]

    rows = [[btn(tx(lang, "➕ Добавить офис", "➕ Додати офіс"), "p:0"), btn("📡 " + tx(lang, "Радар", "Радар"), "rd")]]
    if subs:
        rows.append([btn(tx(lang, "📋 Подписки", "📋 Підписки") + f" ({len(subs)})", "l"),
                     btn(tx(lang, "🔄 Проверить", "🔄 Перевірити"), "ca")])
    rows.append([btn(tx(lang, "⚙️ Настройки", "⚙️ Налаштування"), "st"), btn(tx(lang, "❓ Помощь", "❓ Допомога"), "hp")])
    rows.append([btn(tx(lang, "🇺🇦 Для украинцев", "🇺🇦 Для українців"), "ua")])
    if is_admin(chat):
        rows.append([btn("🛠 Админ-панель", "ad")])
    return "\n".join(lines), ikb(rows)


# ---------- выбор офиса и записи ----------

def offices(chat: int, page: int = 0, header: str = "", prefix: str = "c", pager: str = "p") -> Tuple[str, dict]:
    lang = lang_of(chat)
    ids = sorted(dgt.CENTROS, key=lambda c: fold(city(c)))
    pages = math.ceil(len(ids) / PAGE)
    page %= pages
    chunk = ids[page * PAGE:(page + 1) * PAGE]
    rows = [[btn(city(c), f"{prefix}:{c}") for c in chunk[i:i + 2]] for i in range(0, len(chunk), 2)]
    rows.append([btn("◀️", f"{pager}:{page - 1}"), btn(f"{page + 1} / {pages}", "noop"), btn("▶️", f"{pager}:{page + 1}")])
    rows.append([home_btn(lang)])
    text = (header or tx(lang, "🏢 <b>Выбери офис DGT</b>", "🏢 <b>Обери офіс DGT</b>")) + "\n\n" + \
        tx(lang, "Или просто напиши название города, например <i>Valencia</i>.",
           "Або просто напиши назву міста, наприклад <i>Valencia</i>.")
    return text, ikb(rows)


def search_results(chat: int, query: str, found: List[str], prefix: str = "c", pager: str = "p") -> Tuple[str, dict]:
    lang = lang_of(chat)
    rows = [[btn(city(c), f"{prefix}:{c}")] for c in sorted(found, key=lambda c: fold(city(c)))]
    rows.append([btn(tx(lang, "🏢 Все офисы", "🏢 Усі офіси"), f"{pager}:0"), home_btn(lang)])
    return tx(lang, "🔎 Офисы по запросу", "🔎 Офіси за запитом") + f" «{esc(query)}»:", ikb(rows)


def not_found(chat: int, query: str) -> str:
    lang = lang_of(chat)
    return tx(lang, f"😕 Не нашёл офис «{esc(query)}».\n\n🏢 <b>Выбери из списка</b>",
              f"😕 Не знайшов офіс «{esc(query)}».\n\n🏢 <b>Обери зі списку</b>")


def too_many(chat: int) -> str:
    return tx(lang_of(chat), "🔎 Слишком много совпадений — уточни название или выбери из списка.",
              "🔎 Забагато збігів — уточни назву або обери зі списку.")


def loading(text: str) -> Tuple[str, dict]:
    return f"⏳ {text}", ikb([])


def areas(chat: int, cid: str, options: List[Tuple[str, str]]) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = (f"🏢 <b>{esc(city(cid))}</b>\n<i>{esc(dgt.CENTROS[cid])}</i>\n\n"
            + tx(lang, "Какой тип записи нужен?", "Який тип запису потрібен?"))
    rows = []
    for code, label in options:
        hint = area_hint(lang, label)
        rows.append([btn(f"{area_emoji(label)} {area_label(code, label)}" + (f" — {hint}" if hint else ""),
                         f"a:{cid}:{code}")])
    rows.append([btn(tx(lang, "⬅️ Офисы", "⬅️ Офіси"), "p:0"), home_btn(lang)])
    return text, ikb(rows)


def areas_error(chat: int, cid: str, retry: str) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, f"😕 Сайт DGT не ответил, не могу получить список услуг для <b>{esc(city(cid))}</b>.\n"
                     "Попробуй ещё раз через минуту.",
               f"😕 Сайт DGT не відповів, не можу отримати список послуг для <b>{esc(city(cid))}</b>.\n"
               "Спробуй ще раз за хвилину."),
            ikb([[btn(tx(lang, "🔄 Повторить", "🔄 Повторити"), retry)], [home_btn(lang)]]))


# ---------- подписки ----------

def subs_list(chat: int, header: str = "") -> Tuple[str, dict]:
    lang = lang_of(chat)
    subs = store.subs_of(chat)
    if not subs:
        return (tx(lang, "📋 <b>Подписок пока нет</b>\n\nНажми «➕ Добавить офис» — и я начну следить за свободными датами.",
                   "📋 <b>Підписок поки немає</b>\n\nНатисни «➕ Додати офіс» — і я почну стежити за вільними датами."),
                ikb([[btn(tx(lang, "➕ Добавить офис", "➕ Додати офіс"), "p:0")], [home_btn(lang)]]))
    lines = [header or tx(lang, "📋 <b>Твои подписки</b> · ", "📋 <b>Твої підписки</b> · ")
             + f"{len(subs)}/{store.setting('max_subs')}", ""]
    rows = []
    for s in subs:
        emoji, text = summary(s, lang)
        lines.append(f"{emoji} {title(s)}\n      <i>{text}</i>")
        rows.append([btn(f"{emoji} {plain_title(s)}", f"s:{s['id']}")])
    lines.append(tx(lang, "\nНажми на подписку — покажу подробности.", "\nНатисни на підписку — покажу подробиці."))
    rows.append([btn(tx(lang, "➕ Добавить", "➕ Додати"), "p:0"), btn(tx(lang, "🔄 Проверить все", "🔄 Перевірити всі"), "ca")])
    rows.append([home_btn(lang)])
    return "\n".join(lines), ikb(rows)


def where_block(lang: str, results: Optional[list]) -> str:
    info = next((r for r in results or [] if r.get("address")), None)
    if not info:
        return ""
    where = [f"📍 {esc(info['address'])}"]
    if info.get("schedule"):
        where.append(f"🕘 {esc(info['schedule'])}")
    return "<blockquote>" + "\n".join(where) + "</blockquote>"


def card(sub: dict, note: str = "") -> Tuple[str, dict]:
    if sub.get("booked_date"):
        return booked_card(sub, note)
    lang, last, sid = lang_of(sub["chat"]), sub.get("last"), sub["id"]
    lines = [f"🏢 {title(sub)}", where_block(lang, last)]

    days = all_days(last, sub.get("max_days"))
    if sub.get("paused"):
        lines.append(tx(lang, "⏸ <b>Подписка на паузе</b> — уведомления не приходят\n",
                        "⏸ <b>Підписка на паузі</b> — сповіщення не надходять\n"))
    if days:
        lines.append(f"🟢 <b>{free_days_word(lang, len(days))}</b> · {day_range(lang, days)}")
        lines += nearest_lines(lang, last, days)
        lines.append(f"<blockquote expandable>{days_block(lang, days)}</blockquote>")
    elif not sub.get("paused"):
        emoji, text = summary(sub, lang)
        lines.append(f"{emoji} <b>{text[0].upper() + text[1:]}</b>")
        if emoji in ("🔴", "🟡", "⏳"):
            lines.append(tx(lang, "Напишу, как только появятся подходящие даты.",
                            "Напишу, щойно з’являться відповідні дати."))
        elif emoji == "⚪️":
            lines.append(tx(lang, "Похоже, в этом офисе такой тип записи называется иначе — выбери его заново.",
                            "Схоже, в цьому офісі такий тип запису називається інакше — обери його знову."))
    lines.append("")
    lines.append(tx(lang, "📅 Даты: ", "📅 Дати: ") + f"<b>{filter_label(lang, sub.get('max_days'))}</b>"
                 + (f" · 🕐 {fmt_ts(sub['checked_at'], lang)}" if sub.get("checked_at") else ""))
    if note:
        lines.append(f"\n{note}")

    status = (last or [{}])[0].get("status")
    rows = [[url(tx(lang, "📝 Записаться на сайте DGT", "📝 Записатися на сайті DGT"), dgt.START_URL)]]
    if status == dgt.NO_AREA:
        rows.append([btn(tx(lang, "🔁 Выбрать тип записи заново", "🔁 Обрати тип запису знову"), f"c:{sub['centro']}")])
    if days:
        rows.append([btn(tx(lang, "✅ Я записался", "✅ Я записався"), f"bk:{sid}")])
    rows += [
        [btn(tx(lang, "🗓 Календарь", "🗓 Календар"), f"k:{sid}:0"), btn(tx(lang, "🔄 Обновить", "🔄 Оновити"), f"r:{sid}")],
        [btn("📡 " + tx(lang, "Радар рядом", "Радар поруч"), f"rs:{sid}"),
         btn("📅 " + filter_label(lang, sub.get("max_days")).capitalize(), f"f:{sid}")],
        [btn(tx(lang, "▶️ Возобновить", "▶️ Відновити") if sub.get("paused") else "⏸ " + tx(lang, "Пауза", "Пауза"), f"z:{sid}"),
         btn(tx(lang, "📊 История", "📊 Історія"), f"h:{sid}"), btn("🗑", f"x:{sid}")],
        [btn(tx(lang, "⬅️ Подписки", "⬅️ Підписки"), "l"), home_btn(lang)],
    ]
    return "\n".join(l for l in lines if l is not None), ikb(rows)


def calendar_view(sub: dict, idx: int = 0) -> Tuple[str, dict]:
    lang, sid = lang_of(sub["chat"]), sub["id"]
    c = CAL[lang]
    days = all_days(sub.get("last"))
    back = [btn(tx(lang, "⬅️ К подписке", "⬅️ До підписки"), f"s:{sid}"), home_btn(lang)]
    head = tx(lang, "🗓 <b>Календарь</b> · ", "🗓 <b>Календар</b> · ") + title(sub)
    if not days:
        return (head + "\n\n" + tx(lang, "Свободных дат сейчас нет. Напишу, как только появятся.",
                                   "Вільних дат зараз немає. Напишу, щойно з’являться."), ikb([back]))
    months = sorted({iso[:7] for iso, _ in days})
    idx %= len(months)
    y, m = map(int, months[idx].split("-"))
    loads = dict(days)
    in_month = [d for d in days if d[0].startswith(months[idx])]
    rows = [[
        btn("◀️", f"k:{sid}:{idx - 1}") if len(months) > 1 else btn(BLANK, "noop"),
        btn(f"{c['months'][m - 1].capitalize()} {y}", "noop"),
        btn("▶️", f"k:{sid}:{idx + 1}") if len(months) > 1 else btn(BLANK, "noop"),
    ], [btn(w, "noop") for w in c["head"]]]
    for week in calendar.Calendar().monthdayscalendar(y, m):
        row = []
        for d in week:
            if not d:
                row.append(btn(BLANK, "noop"))
                continue
            iso = f"{y:04d}-{m:02d}-{d:02d}"
            row.append(btn(f"{d}{LOAD.get(loads[iso], '')}" if iso in loads else str(d), f"d:{sid}:{iso}"))
        rows.append(row)
    rows.append([btn(tx(lang, "✅ Я записался", "✅ Я записався"), f"bk:{sid}")])
    rows.append(back)
    text = (f"{head}\n\n{c['prep'][m - 1].capitalize()}: <b>{free_days_word(lang, len(in_month))}</b>\n"
            + tx(lang, "🟢 много мест · 🟡 средне · 🔴 мало\n<i>Нажми на день — покажу подробности</i>",
                 "🟢 багато місць · 🟡 середньо · 🔴 мало\n<i>Натисни на день — покажу подробиці</i>"))
    return text, ikb(rows)


def day_popup(sub: dict, iso: str) -> str:
    lang = lang_of(sub["chat"])
    loads = dict(all_days(sub.get("last")))
    head = long_day(lang, iso).capitalize()
    if iso not in loads:
        return head + "\n" + tx(lang, "В этот день свободных мест нет", "Цього дня вільних місць немає")
    load_text = {
        "bajaOcupacion": tx(lang, "🟢 много свободных мест", "🟢 багато вільних місць"),
        "mediaOcupacion": tx(lang, "🟡 занято 33–66%", "🟡 зайнято 33–66%"),
        "altaOcupacion": tx(lang, "🔴 почти всё занято", "🔴 майже все зайнято"),
    }.get(loads[iso], "")
    text = f"{head}\n{load_text}"
    hours = hours_for(sub.get("last"), iso)
    if hours:
        text += "\n⏰ " + " · ".join(hours[:10]) + (" …" if len(hours) > 10 else "")
    return text


def filter_view(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    text = (tx(lang, "📅 <b>Какие даты присылать?</b>", "📅 <b>Які дати надсилати?</b>") + f"\n{title(sub)}\n\n"
            + tx(lang, "Например, если у тебя уже есть запись через месяц, выбери «до 30 дней» — "
                       "и я напишу только о более ранних датах.",
                 "Наприклад, якщо в тебе вже є запис через місяць, обери «до 30 днів» — "
                 "і я напишу лише про раніші дати."))
    cur = sub.get("max_days") or 0
    rows = [[btn(("✅ " if v == cur else "") + filter_label(lang, v).capitalize(), f"fs:{sub['id']}:{v}")]
            for v in FILTER_DAYS]
    rows.append([btn(tx(lang, "⬅️ К подписке", "⬅️ До підписки"), f"s:{sub['id']}")])
    return text, ikb(rows)


def history_view(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    evs = store.events(sub["centro"], sub["area"], 30)
    lines = [tx(lang, "📊 <b>История</b> · ", "📊 <b>Історія</b> · ") + title(sub), ""]
    if not evs:
        lines.append(tx(lang, "Пока ни разу не видел здесь свободных мест.\nИстория начнёт копиться, как только они появятся.",
                        "Поки жодного разу не бачив тут вільних місць.\nІсторія почне накопичуватися, щойно вони з’являться."))
    else:
        if not evs[0]["closed_at"]:
            lines.append(tx(lang, "🟢 Места есть прямо сейчас — появились ", "🟢 Місця є просто зараз — з’явилися ")
                         + fmt_ts(evs[0]["opened_at"], lang) + "\n")
        lines.append(tx(lang, "<b>Когда появлялись места</b> (время Мадрида):", "<b>Коли з’являлися місця</b> (час Мадрида):"))
        items = []
        for e in evs[:10]:
            dur = (tx(lang, "ещё есть", "ще є") if not e["closed_at"]
                   else tx(lang, "держались ", "трималися ") + fmt_dur(e["closed_at"] - e["opened_at"], lang))
            items.append(f"• {fmt_ts(e['opened_at'], lang)} — {dur}, {days_word(lang, e['days'] or 0)}")
        lines.append("<blockquote>" + "\n".join(items) + "</blockquote>")
        if len(evs) >= 3:
            hour, _ = Counter(datetime.fromtimestamp(e["opened_at"], config.TZ).hour for e in evs).most_common(1)[0]
            lines.append(tx(lang, f"⏰ Чаще всего появляются между {hour}:00 и {hour + 1}:00",
                            f"⏰ Найчастіше з’являються між {hour}:00 і {hour + 1}:00"))
        closed = [e["closed_at"] - e["opened_at"] for e in evs if e["closed_at"]]
        if closed:
            lines.append(tx(lang, "⌛️ В среднем держатся ", "⌛️ У середньому тримаються ")
                         + fmt_dur(sum(closed) // len(closed), lang))
        lines.append(tx(lang, f"\n<i>Точность — интервал проверки, {store.setting('interval')} мин.</i>",
                        f"\n<i>Точність — інтервал перевірки, {store.setting('interval')} хв.</i>"))
    return "\n".join(lines), ikb([[btn(tx(lang, "⬅️ К подписке", "⬅️ До підписки"), f"s:{sub['id']}")]])


def delete_confirm(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    return (tx(lang, "🗑 <b>Удалить подписку?</b>\n", "🗑 <b>Видалити підписку?</b>\n") + title(sub),
            ikb([[btn(tx(lang, "Да, удалить", "Так, видалити"), f"xx:{sub['id']}"),
                  btn(tx(lang, "Отмена", "Скасувати"), f"s:{sub['id']}")]]))


# ---------- «Я записался» ----------

def checklist(lang: str, sub: dict) -> List[str]:
    cats = cats_of(sub_area(sub))
    items = [tx(lang, "Документ: DNI, NIE/TIE или паспорт (оригинал)", "Документ: DNI, NIE/TIE або паспорт (оригінал)"),
             tx(lang, "Подтверждение записи (номер cita)", "Підтвердження запису (номер cita)"),
             tx(lang, "Оплаченная пошлина DGT (tasa), если она нужна для твоего trámite",
                "Сплачений збір DGT (tasa), якщо він потрібен для твого trámite")]
    if "cnj" in cats:
        items += [tx(lang, "Оригинал иностранных прав и их копия", "Оригінал іноземних прав і їх копія"),
                  tx(lang, "Цветное фото 32×26 мм", "Кольорове фото 32×26 мм"),
                  tx(lang, "Медсправка из Centro de Reconocimiento de Conductores",
                     "Медична довідка з Centro de Reconocimiento de Conductores"),
                  tx(lang, "Заявление (solicitud) — бланк на сайте DGT", "Заява (solicitud) — бланк на сайті DGT"),
                  tx(lang, "Для украинских прав присяжный перевод не нужен",
                     "Для українських прав присяжний переклад не потрібен")]
    elif "rpc" in cats:
        items += [tx(lang, "Права страны ЕС/ЕЭЗ", "Права країни ЄС/ЄЕЗ"),
                  tx(lang, "Цветное фото 32×26 мм", "Кольорове фото 32×26 мм"),
                  tx(lang, "Медсправка из Centro de Reconocimiento de Conductores",
                     "Медична довідка з Centro de Reconocimiento de Conductores")]
    elif "san" in cats:
        items += [tx(lang, "Уведомление о штрафе (número de expediente)", "Повідомлення про штраф (número de expediente)"),
                  tx(lang, "Документы в свою пользу, если обжалуешь", "Документи на свою користь, якщо оскаржуєш")]
    elif "exm" in cats:
        items += [tx(lang, "Для практического экзамена обычно нужна автошкола и её машина",
                     "Для практичного іспиту зазвичай потрібна автошкола і її авто"),
                  tx(lang, "Уточни в автошколе, что ещё взять", "Уточни в автошколі, що ще взяти")]
    if cats & {"veh", "mat"}:
        items += [tx(lang, "Permiso de circulación и ficha técnica (карточка ITV)",
                     "Permiso de circulación і ficha técnica (картка ITV)"),
                  tx(lang, "Договор купли-продажи — при смене владельца", "Договір купівлі-продажу — при зміні власника"),
                  tx(lang, "Налог на транспорт (IVTM) и действующий ITV", "Податок на транспорт (IVTM) і чинний ITV")]
    if "lic" in cats:
        items += [tx(lang, "Текущие права, если есть", "Чинні права, якщо є"),
                  tx(lang, "Фото 32×26 мм и медсправка — для продления или дубликата",
                     "Фото 32×26 мм і медична довідка — для продовження або дубліката")]
    return items


def booking_dates(sub: dict) -> Tuple[str, dict]:
    lang, sid = lang_of(sub["chat"]), sub["id"]
    days = all_days(sub.get("last"))[:8]
    rows = [[btn(wd_day(lang, iso).capitalize(), f"bd:{sid}:{iso}") for iso, _ in days[i:i + 2]]
            for i in range(0, len(days), 2)]
    rows.append([btn(tx(lang, "📅 Другая дата", "📅 Інша дата"), f"bo:{sid}")])
    rows.append([btn(tx(lang, "⬅️ Назад", "⬅️ Назад"), f"s:{sid}")])
    return (tx(lang, "🎉 <b>Отлично!</b> На какую дату записался?\n", "🎉 <b>Чудово!</b> На яку дату записався?\n")
            + title(sub) + "\n\n" + tx(lang, "Напомню накануне и покажу, что взять с собой.",
                                       "Нагадаю напередодні і підкажу, що взяти з собою."), ikb(rows))


def booking_times(sub: dict, iso: str) -> Tuple[str, dict]:
    lang, sid = lang_of(sub["chat"]), sub["id"]
    hours = hours_for(sub.get("last"), iso)[:16]
    rows = [[btn(h, f"bt:{sid}:{iso}:{h.replace(':', '')}") for h in hours[i:i + 4]] for i in range(0, len(hours), 4)]
    rows.append([btn(tx(lang, "Без времени", "Без часу"), f"bt:{sid}:{iso}:-")])
    rows.append([btn(tx(lang, "⬅️ Назад", "⬅️ Назад"), f"bk:{sid}")])
    return (tx(lang, "⏰ Во сколько визит?\n", "⏰ О котрій візит?\n") + f"<b>{long_day(lang, iso)}</b>", ikb(rows))


def booking_prompt(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    return (tx(lang, "📅 Напиши дату и время визита, например <code>10.10 10:30</code>",
               "📅 Напиши дату й час візиту, наприклад <code>10.10 10:30</code>"),
            ikb([[btn(tx(lang, "Отмена", "Скасувати"), f"bk:{sub['id']}")]]))


def booked_card(sub: dict, note: str = "") -> Tuple[str, dict]:
    lang, sid = lang_of(sub["chat"]), sub["id"]
    past = date.fromisoformat(sub["booked_date"]) < today()
    lines = [tx(lang, "✅ <b>Ты записан!</b>", "✅ <b>Ти записаний!</b>") if not past
             else tx(lang, "✅ <b>Визит состоялся</b>", "✅ <b>Візит відбувся</b>"),
             f"🏢 {title(sub)}",
             f"📅 <b>{booked_label(lang, sub)}</b>",
             where_block(lang, sub.get("last"))]
    if not past:
        lines.append(tx(lang, "🔔 Напомню накануне в 19:00 и утром в день визита.",
                        "🔔 Нагадаю напередодні о 19:00 і вранці в день візиту."))
        lines.append("")
        lines.append(tx(lang, "📋 <b>Что взять с собой</b>", "📋 <b>Що взяти з собою</b>"))
        lines.append("<blockquote expandable>" + "\n".join(f"• {i}" for i in checklist(lang, sub)) + "</blockquote>")
        lines.append(tx(lang, "<i>Список общий — точный перечень для своего trámite проверь на сайте DGT.</i>",
                        "<i>Список загальний — точний перелік для свого trámite перевір на сайті DGT.</i>"))
    if note:
        lines.append(f"\n{note}")
    rows = [[url(tx(lang, "📋 Требования на сайте DGT", "📋 Вимоги на сайті DGT"), DGT_SEDE)],
            [btn(tx(lang, "↩️ Запись отменилась — искать снова", "↩️ Запис скасовано — шукати знову"), f"ub:{sid}")],
            [btn(tx(lang, "🗑 Удалить", "🗑 Видалити"), f"x:{sid}"),
             btn(tx(lang, "⬅️ Подписки", "⬅️ Підписки"), "l"), home_btn(lang)]]
    return "\n".join(l for l in lines if l), ikb(rows)


def reminder(sub: dict, when: str) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    head = (tx(lang, "⏰ <b>Завтра визит в DGT</b>", "⏰ <b>Завтра візит до DGT</b>") if when == "eve"
            else tx(lang, "⏰ <b>Сегодня визит в DGT</b>", "⏰ <b>Сьогодні візит до DGT</b>"))
    lines = [head, f"🏢 {title(sub)}", f"📅 <b>{booked_label(lang, sub)}</b>", where_block(lang, sub.get("last")),
             tx(lang, "📋 <b>Не забудь</b>", "📋 <b>Не забудь</b>"),
             "<blockquote expandable>" + "\n".join(f"• {i}" for i in checklist(lang, sub)) + "</blockquote>",
             tx(lang, "Удачи! 🍀", "Успіху! 🍀")]
    return "\n".join(l for l in lines if l), ikb([[btn(tx(lang, "✖️ Скрыть", "✖️ Сховати"), "hide")]])


# ---------- уведомления ----------

def alert(sub: dict, results: list, new: Set[str]) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    days = all_days(results, sub.get("max_days"))
    fresh = len([d for d in days if d[0] in new])
    lines = [tx(lang, "🔔 <b>Есть свободные даты!</b>", "🔔 <b>Є вільні дати!</b>"), f"🏢 {title(sub)}", ""]
    lines += nearest_lines(lang, results, days)
    lines.append("")
    lines.append(f"📅 <b>{days_word(lang, len(days))}</b> · {day_range(lang, days)}"
                 + (tx(lang, f" · новых {fresh}", f" · нових {fresh}") if fresh and fresh != len(days) else ""))
    lines.append(f"<blockquote expandable>{days_block(lang, days, new)}</blockquote>")
    if sub.get("max_days"):
        lines.append(tx(lang, f"<i>Показаны даты в пределах {sub['max_days']} дней</i>",
                        f"<i>Показано дати в межах {sub['max_days']} днів</i>"))
    lines.append(tx(lang, "<i>На сайте: ", "<i>На сайті: ")
                 + f"{esc(city(sub['centro']))} → {esc(sub_area(sub))} → Continuar → Pedir cita</i>")
    kb = ikb([
        [url(tx(lang, "📝 Записаться на сайте DGT", "📝 Записатися на сайті DGT"), dgt.START_URL)],
        [btn(tx(lang, "✅ Я записался", "✅ Я записався"), f"bk:{sub['id']}"),
         btn(tx(lang, "🗓 Календарь", "🗓 Календар"), f"k:{sub['id']}:0")],
        [btn(tx(lang, "✖️ Скрыть", "✖️ Сховати"), "hide")],
    ])
    return "\n".join(lines), kb


def gone(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    now = datetime.now(config.TZ)
    return (f"😔 {title(sub)}\n" + tx(lang, f"Свободные даты разобрали ({now:%H:%M}). Слежу дальше — напишу, как только появятся.",
                                      f"Вільні дати розібрали ({now:%H:%M}). Стежу далі — напишу, щойно з’являться."),
            ikb([[btn(tx(lang, "✖️ Скрыть", "✖️ Сховати"), "hide")]]))


# ---------- радар ----------

def radar_start(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    rows, seen = [], set()
    for s in store.subs_of(chat):
        if s["centro"] not in seen:
            seen.add(s["centro"])
            rows.append([btn(f"📍 {city(s['centro'])}", f"rb:{s['centro']}")])
    rows.append([btn(tx(lang, "🏢 Выбрать другой офис", "🏢 Обрати інший офіс") if seen
                     else tx(lang, "🏢 Выбрать офис", "🏢 Обрати офіс"), "rp:0")])
    rows.append([home_btn(lang)])
    text = (tx(lang, "📡 <b>Радар</b>\n\nПроверю офисы рядом и покажу, где можно записаться раньше всего.\n\n"
                     "От какого офиса искать?",
               "📡 <b>Радар</b>\n\nПеревірю офіси поруч і покажу, де можна записатися найшвидше.\n\n"
               "Від якого офісу шукати?"))
    return text, ikb(rows)


def radar_categories(chat: int, cid: str) -> Tuple[str, dict]:
    lang = lang_of(chat)
    rows = [[btn(f"{emoji} {tx(lang, ru, uk)}", f"rr:{cid}:{cat}:100")] for cat, (emoji, ru, uk) in CATS.items()]
    rows.append([btn(tx(lang, "⬅️ Назад", "⬅️ Назад"), "rd"), home_btn(lang)])
    return (f"📡 <b>{tx(lang, 'Радар', 'Радар')}</b> · 📍 {esc(city(cid))}\n\n"
            + tx(lang, "Какая запись нужна?", "Який запис потрібен?"), ikb(rows))


def radar_progress(chat: int, cid: str, cat: str, km: int, done: int, total: int, current: str) -> Tuple[str, dict]:
    lang = lang_of(chat)
    bar = "▰" * done + "▱" * (total - done)
    emoji, ru, uk = CATS[cat]
    return (f"📡 <b>{tx(lang, 'Радар', 'Радар')}</b> · {emoji} {tx(lang, ru, uk)}\n"
            + tx(lang, f"до {km} км от {esc(city(cid))}\n\n", f"до {km} км від {esc(city(cid))}\n\n")
            + f"{bar}  {done}/{total}\n"
            + tx(lang, f"⏳ Проверяю <b>{esc(current)}</b>…", f"⏳ Перевіряю <b>{esc(current)}</b>…")
            + tx(lang, "\n\n<i>Проверяю по одному офису, чтобы сайт DGT не заблокировал — это займёт пару минут.</i>",
                 "\n\n<i>Перевіряю по одному офісу, щоб сайт DGT не заблокував — це займе кілька хвилин.</i>"), ikb([]))


def radar_results(chat: int, cid: str, cat: str, km: int, found: list) -> Tuple[str, dict]:
    """found: [(centro, код или None, results или None, км)] — уже отсортировано."""
    lang = lang_of(chat)
    emoji, ru, uk = CATS[cat]
    lines = [f"📡 <b>{tx(lang, 'Радар', 'Радар')}</b> · {emoji} {tx(lang, ru, uk)}",
             tx(lang, f"до {km} км от {esc(city(cid))}", f"до {km} км від {esc(city(cid))}"), ""]
    medals = iter(["🥇", "🥈", "🥉"])
    rows, items = [], []
    subscribed = {(s["centro"], s["area"]) for s in store.subs_of(chat)}
    for centro, code, results, dist in found:
        name = f"<b>{esc(city(centro))}</b>" + (f" · {dist} км" if dist else "")
        days = all_days(results) if results else []
        if days:
            medal = next(medals, "🟢")
            items.append(f"{medal} {name} — " + tx(lang, "с ", "з ") + f"<b>{short_day(lang, days[0][0])}</b> "
                         f"({days_word(lang, len(days))})")
            if (centro, code) not in subscribed and len(rows) < 4:
                rows.append([btn(tx(lang, f"🔔 Следить: {city(centro)}", f"🔔 Стежити: {city(centro)}"),
                                 f"a:{centro}:{code}")])
        elif code is None:
            items.append(f"⚪️ {name} — " + tx(lang, "нет такой записи", "немає такого запису"))
        elif results is None:
            items.append(f"⚠️ {name} — " + tx(lang, "сайт не ответил", "сайт не відповів"))
        else:
            items.append(f"🔴 {name} — " + tx(lang, "мест нет", "місць немає"))
    lines.append("<blockquote>" + "\n".join(items) + "</blockquote>")
    if not any(all_days(r) for _, _, r, _ in found if r):
        lines.append(tx(lang, "😔 Рядом свободных дат нет. Подпишись на ближайший офис — напишу, когда появятся.",
                        "😔 Поруч вільних дат немає. Підпишися на найближчий офіс — напишу, щойно з’являться."))
    lines.append(tx(lang, "<i>Расстояние — по прямой между городами.</i>", "<i>Відстань — по прямій між містами.</i>"))
    if rows:
        rows.insert(0, [url(tx(lang, "📝 Записаться на сайте DGT", "📝 Записатися на сайті DGT"), dgt.START_URL)])
    wider = [k for k in (150, 250) if k > km]
    if wider:
        rows.append([btn(tx(lang, f"🔭 Искать до {wider[0]} км", f"🔭 Шукати до {wider[0]} км"),
                         f"rr:{cid}:{cat}:{wider[0]}")])
    rows.append([btn(tx(lang, "📡 Новый поиск", "📡 Новий пошук"), "rd"), home_btn(lang)])
    return "\n".join(lines), ikb(rows)


# ---------- настройки, помощь ----------

def settings_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    quiet = store.get_chat(chat).get("quiet")
    text = (tx(lang, "⚙️ <b>Настройки</b>\n\n", "⚙️ <b>Налаштування</b>\n\n")
            + tx(lang, f"🌙 <b>Тихий режим ночью</b>: {'включён' if quiet else 'выключен'}\n"
                       "<i>С 00:00 до 08:00 по Мадриду уведомления приходят без звука.</i>\n\n",
                 f"🌙 <b>Тихий режим уночі</b>: {'увімкнено' if quiet else 'вимкнено'}\n"
                 "<i>З 00:00 до 08:00 за Мадридом сповіщення надходять без звуку.</i>\n\n")
            + tx(lang, f"🌐 Язык: {LANGS[lang]}\n", f"🌐 Мова: {LANGS[lang]}\n")
            + tx(lang, f"⏱ Проверка каждые {store.setting('interval')} мин\n", f"⏱ Перевірка кожні {store.setting('interval')} хв\n")
            + tx(lang, f"🏢 До {store.setting('max_subs')} офисов одновременно", f"🏢 До {store.setting('max_subs')} офісів одночасно"))
    return text, ikb([
        [btn(tx(lang, f"🌙 Тихий режим: {'вкл' if quiet else 'выкл'}", f"🌙 Тихий режим: {'увімк' if quiet else 'вимк'}"), "q")],
        [btn(tx(lang, "🌐 Язык / Мова", "🌐 Мова / Язык"), "lp"),
         btn(tx(lang, "🔒 Данные", "🔒 Дані"), "pv")],
        [btn(tx(lang, "🗑 Удалить все подписки", "🗑 Видалити всі підписки"), "xa")],
        [home_btn(lang)],
    ])


def help_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = tx(lang,
              "❓ <b>Как это работает</b>\n\n"
              "Я захожу на сайт DGT так же, как это сделал бы ты: выбираю офис и тип записи и смотрю календарь. "
              "Как только появляются свободные дни — присылаю уведомление с датами и временем.\n\n"
              "<b>Цвета</b>\n<blockquote>🟢 много свободных мест\n🟡 занято 33–66%\n🔴 почти всё занято</blockquote>\n"
              "<b>Что умею</b>\n"
              "• 📡 радар: ищу ближайший офис, где можно записаться раньше всего\n"
              "• 🗓 календарь со свободным временем\n"
              "• ✅ «Я записался»: напомню о визите и подскажу, что взять\n"
              "• 📅 присылать только даты раньше нужной, ⏸ пауза, 📊 история\n"
              "• 🌙 тихий режим ночью\n\n"
              "<b>Советы</b>\n"
              "• Места быстро разбирают — открывай сайт сразу после уведомления\n"
              "• Держи под рукой DNI/NIE: сайт спросит данные при записи\n\n"
              "Записываешься ты сам — я только сообщаю, когда есть места.",
              "❓ <b>Як це працює</b>\n\n"
              "Я заходжу на сайт DGT так само, як це зробив би ти: обираю офіс і тип запису та дивлюся календар. "
              "Щойно з’являються вільні дні — надсилаю сповіщення з датами й часом.\n\n"
              "<b>Кольори</b>\n<blockquote>🟢 багато вільних місць\n🟡 зайнято 33–66%\n🔴 майже все зайнято</blockquote>\n"
              "<b>Що вмію</b>\n"
              "• 📡 радар: шукаю найближчий офіс, де можна записатися найшвидше\n"
              "• 🗓 календар із вільним часом\n"
              "• ✅ «Я записався»: нагадаю про візит і підкажу, що взяти\n"
              "• 📅 надсилати лише дати раніше потрібної, ⏸ пауза, 📊 історія\n"
              "• 🌙 тихий режим уночі\n\n"
              "<b>Поради</b>\n"
              "• Місця швидко розбирають — відкривай сайт одразу після сповіщення\n"
              "• Тримай під рукою DNI/NIE: сайт спитає дані під час запису\n\n"
              "Записуєшся ти сам — я лише повідомляю, коли є місця.")
    return text, ikb([[btn(tx(lang, "🇺🇦 Для украинцев", "🇺🇦 Для українців"), "ua")], [home_btn(lang)]])


def ukraine_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = tx(lang,
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
              "<i>Информация на сентябрь 2026 — перед визитом сверяйся с официальными сайтами.</i>",
              "🇺🇦 <b>Для українців в Іспанії</b>\n\n"
              "🪪 <b>Українські права</b>\n"
              "<blockquote>• Діють в Іспанії, поки в тебе є тимчасовий захист — зараз до <b>4 березня 2027</b>.\n"
              "• Їх можна обміняти на іспанські (<b>canje</b>) у DGT: обери офіс → «Canjes», "
              "і я напишу, щойно з’явиться запис.\n"
              "• З TIE обмін можна робити одразу, з резолюцією про захист — через 6 місяців після в’їзду або видачі. "
              "Присяжний переклад не потрібен.</blockquote>\n"
              "📄 <b>Тимчасовий захист і TIE</b>\n"
              "<blockquote>• Усі TIE за тимчасовим захистом продовжено автоматично до 4 березня 2027 "
              "(Orden INT/96/2026) — нікуди йти не треба.\n"
              "• Єврокомісія запропонувала продовжити захист до 4 березня 2028 — поки не затверджено.\n"
              "• Нова заява: центри CREADE за телефоном — Pozuelo (Madrid) +34 666 800 194, "
              "Málaga +34 628 216 478, Barcelona +34 93 238 21 99; в інших провінціях — у поліції.\n"
              "• З серпня 2026 для нового захисту треба підтвердити виконання військового обов’язку "
              "України або звільнення від нього.</blockquote>\n"
              "<i>Інформація на вересень 2026 — перед візитом звіряйся з офіційними сайтами.</i>")
    return text, ikb([
        [btn(tx(lang, "🔁 Следить за записью на canje", "🔁 Стежити за записом на canje"), "p:0")],
        [url(tx(lang, "🪪 Canje прав — DGT", "🪪 Canje прав — DGT"), UA_CANJE), url("🌐 Ucrania Urgente", UA_GUIDE)],
        [home_btn(lang)],
    ])


def privacy_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = tx(lang,
              "🔒 <b>Конфиденциальность</b>\n\n"
              "<b>Что я храню</b>\n<blockquote>• Telegram ID, имя и @username\n• язык и настройки\n"
              "• подписки: офис, тип записи, фильтр дат и дату визита, если ты её указал</blockquote>\n"
              "<b>Зачем</b> — только чтобы присылать уведомления и напоминания. "
              "Данные не продаются и не передаются третьим лицам.\n"
              "<b>Где</b> — на серверах в ЕС (Франкфурт).\n\n"
              "Бот не связан с DGT и не записывает тебя сам — запись делаешь ты на официальном сайте.\n\n"
              "Удалить все свои данные можно кнопкой ниже.",
              "🔒 <b>Конфіденційність</b>\n\n"
              "<b>Що я зберігаю</b>\n<blockquote>• Telegram ID, ім’я та @username\n• мову й налаштування\n"
              "• підписки: офіс, тип запису, фільтр дат і дату візиту, якщо ти її вказав</blockquote>\n"
              "<b>Навіщо</b> — лише щоб надсилати сповіщення й нагадування. "
              "Дані не продаються і не передаються третім особам.\n"
              "<b>Де</b> — на серверах у ЄС (Франкфурт).\n\n"
              "Бот не пов’язаний з DGT і не записує тебе сам — запис робиш ти на офіційному сайті.\n\n"
              "Видалити всі свої дані можна кнопкою нижче.")
    return text, ikb([[btn(tx(lang, "🗑 Удалить мои данные", "🗑 Видалити мої дані"), "dm")],
                      [btn(tx(lang, "⬅️ Настройки", "⬅️ Налаштування"), "st"), home_btn(lang)]])


def delete_me_confirm(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, "🗑 <b>Удалить все мои данные?</b>\nПодписки, настройки и история пропадут. Отменить нельзя.",
               "🗑 <b>Видалити всі мої дані?</b>\nПідписки, налаштування й історія зникнуть. Скасувати не можна."),
            ikb([[btn(tx(lang, "Да, удалить", "Так, видалити"), "dm!"), btn(tx(lang, "Отмена", "Скасувати"), "pv")]]))


def deleted_text(lang: str) -> str:
    return tx(lang, "✅ Все твои данные удалены. Если захочешь вернуться — нажми /start.",
              "✅ Усі твої дані видалено. Якщо захочеш повернутися — натисни /start.")


def maintenance_view(lang: str) -> Tuple[str, dict]:
    return (f"{BRAND_LINE}\n\n" + tx(lang, "🛠 <b>Технические работы</b>\nБот обновляется, скоро вернусь. "
                                           "Подписки сохранены, уведомления продолжат приходить.",
                                     "🛠 <b>Технічні роботи</b>\nБот оновлюється, скоро повернуся. "
                                     "Підписки збережено, сповіщення надходитимуть і далі."), ikb([]))


def pending_view(lang: str) -> Tuple[str, dict]:
    return (f"{BRAND_LINE}\n\n" + tx(lang, "⏳ <b>Заявка на доступ отправлена</b>\nБот сейчас работает по приглашениям. "
                                           "Как только администратор одобрит заявку — я напишу.",
                                     "⏳ <b>Заявку на доступ надіслано</b>\nБот зараз працює за запрошеннями. "
                                     "Щойно адміністратор схвалить заявку — я напишу."), ikb([]))


def banned_view(lang: str) -> Tuple[str, dict]:
    return f"{BRAND_LINE}\n\n" + tx(lang, "🚫 Доступ к боту закрыт.", "🚫 Доступ до бота закрито."), ikb([])
