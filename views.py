"""Экраны и тексты для пользователей на четырёх языках: украинский, русский, испанский, английский. Админка — только по-русски."""
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
import premium
import rewards
import signals
import store
from tg import btn, copy, ikb, url, webapp

esc = html.escape
BRAND_LINE = f"🇪🇸 <b>{config.BRAND}</b> · cita previa DGT"
LANGS = {"uk": "🇺🇦 Українська", "ru": "🇷🇺 Русский", "es": "🇪🇸 Español", "en": "🇬🇧 English"}

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
    "es": {
        "wd": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
        "wd_long": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
        "months": ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                   "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
        "gen": ["de enero", "de febrero", "de marzo", "de abril", "de mayo", "de junio",
                "de julio", "de agosto", "de septiembre", "de octubre", "de noviembre", "de diciembre"],
        "prep": ["en enero", "en febrero", "en marzo", "en abril", "en mayo", "en junio",
                 "en julio", "en agosto", "en septiembre", "en octubre", "en noviembre", "en diciembre"],
        "head": ["L", "M", "X", "J", "V", "S", "D"],
        "short": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
    },
    "en": {
        "wd": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "wd_long": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "months": ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"],
        "gen": ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"],
        "prep": ["in January", "in February", "in March", "in April", "in May", "in June",
                 "in July", "in August", "in September", "in October", "in November", "in December"],
        "head": ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
        "short": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    },
}
for _c in CAL.values():
    _c.setdefault("short", [m[:3] for m in _c["gen"]])
outage = lambda: False  # checker подставляет сюда проверку «сайт DGT недоступен»  # noqa: E731
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
    "lic": ("🪪", "Права, водители", "Права, водії", "Permisos y conductores", "Licences and drivers"),
    "veh": ("🚗", "Транспорт", "Транспорт", "Vehículos", "Vehicles"),
    "cnj": ("🔁", "Canje — обмен прав", "Canje — обмін прав", "Canje — cambio de permiso", "Canje — licence exchange"),
    "exm": ("🎓", "Экзамены на права", "Іспити на права", "Exámenes de conducir", "Driving tests"),
    "san": ("💶", "Штрафы", "Штрафи", "Multas", "Fines"),
    "mat": ("📝", "Регистрация ТС", "Реєстрація ТЗ", "Matriculación", "Vehicle registration"),
    "rpc": ("♻️", "Продление прав ЕС", "Продовження прав ЄС", "Renovación de permiso UE", "EU licence renewal"),
}


# ---------- язык и общие помощники ----------

def tx(lang: str, ru: str, uk: str, es: str, en: str) -> str:
    return uk if lang == "uk" else es if lang == "es" else en if lang == "en" else ru


def cap(s: str) -> str:
    """Заглавная первая буква. str.capitalize() портит остальное: «in January» → «In january»."""
    return s[:1].upper() + s[1:]


def task_title(lang: str, task: dict) -> str:
    return task.get(f"title_{lang}") or task.get("title_en") or task["title_ru"]


def lang_of(chat: int) -> str:
    return store.get_chat(chat).get("lang") or "ru"


def home_btn(lang: str) -> dict:
    return btn(tx(lang, "🏠 Меню", "🏠 Меню", "🏠 Menú", "🏠 Menu"), "home")


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def plural(n: int, one: str, few: str, many: str) -> str:
    k = n % 100
    word = many if 11 <= k <= 14 else one if k % 10 == 1 else few if 2 <= k % 10 <= 4 else many
    return f"{n} {word}"


def pl(lang: str, n: int, ru: Tuple[str, str, str], uk: Tuple[str, str, str], es: Tuple[str, str], en: Tuple[str, str]) -> str:
    if lang in ("es", "en"):
        one, many = es if lang == "es" else en
        return f"{n} {one if n == 1 else many}"
    return plural(n, *(uk if lang == "uk" else ru))


def days_word(lang: str, n: int) -> str:
    return pl(lang, n, ("день", "дня", "дней"), ("день", "дні", "днів"), ("día", "días"), ("day", "days"))


def free_days_word(lang: str, n: int) -> str:
    return pl(lang, n, ("свободный день", "свободных дня", "свободных дней"),
              ("вільний день", "вільні дні", "вільних днів"), ("día libre", "días libres"), ("free day", "free days"))


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
        return tx(lang, "права и транспорт", "права і транспорт", "permisos y vehículos", "licences and vehicles")
    if not cats:
        return ""
    _, *names = CATS[next(iter(cats))]
    return tx(lang, *names).split(" — ")[-1].lower()


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
    return f"{d.day} {CAL[lang]['short'][d.month - 1]}"


def wd_day(lang: str, iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{CAL[lang]['wd'][d.weekday()]} {d.day} {CAL[lang]['short'][d.month - 1]}"


def day_range(lang: str, days: List[Tuple[str, str]]) -> str:
    a, b = date.fromisoformat(days[0][0]), date.fromisoformat(days[-1][0])
    gen, short = CAL[lang]["gen"], CAL[lang]["short"]
    if a == b:
        return f"{a.day} {gen[a.month - 1]}"
    if a.month == b.month:
        return f"{a.day}–{b.day} {gen[a.month - 1]}"
    return f"{a.day} {short[a.month - 1]} – {b.day} {short[b.month - 1]}"


def fmt_ts(ts: int, lang: str = "ru") -> str:
    dt = datetime.fromtimestamp(ts, config.TZ)
    if dt.date() == today():
        return tx(lang, f"сегодня в {dt:%H:%M}", f"сьогодні о {dt:%H:%M}", f"hoy a las {dt:%H:%M}", f"today at {dt:%H:%M}")
    if dt.date() == today() - timedelta(days=1):
        return tx(lang, f"вчера в {dt:%H:%M}", f"вчора о {dt:%H:%M}", f"ayer a las {dt:%H:%M}", f"yesterday at {dt:%H:%M}")
    return f"{CAL[lang]['wd'][dt.weekday()]} {dt:%d.%m} " + tx(lang, f"в {dt:%H:%M}", f"о {dt:%H:%M}",
                                                                     f"a las {dt:%H:%M}",
                                                                     f"at {dt:%H:%M}")


def fmt_dur(sec: int, lang: str = "ru") -> str:
    m = max(1, round(sec / 60))
    if m < 60:
        return tx(lang, f"{m} мин", f"{m} хв", f"{m} min", f"{m} min")
    h, m = divmod(m, 60)
    if h < 24:
        return tx(lang, f"{h} ч", f"{h} год", f"{h} h", f"{h} h") + (tx(lang, f" {m} мин", f" {m} хв", f" {m} min", f" {m} min") if m else "")
    return days_word(lang, round(h / 24))


def filter_label(lang: str, max_days: Optional[int]) -> str:
    return tx(lang, "любые", "будь-які",
                    "cualquiera",
                    "any") if not max_days else tx(lang, f"до {max_days} дней", f"до {max_days} днів",
                                                                       f"hasta {max_days} días",
                                                                       f"up to {max_days} days")


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
            lines.append(f"<b>{cap(c['months'][d.month - 1])} {d.year}</b>")
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
        lines.append(tx(lang, "…и ещё ", "…і ще ", "…y ", "…and ") + days_word(lang, len(days) - limit))
    return "\n".join(lines)


def nearest_lines(lang: str, results: list, days: List[Tuple[str, str]]) -> List[str]:
    iso = days[0][0]
    lines = [tx(lang, "⭐️ Ближайшая: ", "⭐️ Найближча: ", "⭐️ La más próxima: ", "⭐️ Earliest: ") + f"<b>{long_day(lang, iso)}</b>"]
    hours = hours_for(results, iso)
    if hours:
        lines.append("⏰ " + " · ".join(hours[:12]) + (f" <i>+{len(hours) - 12}</i>" if len(hours) > 12 else ""))
    return lines


def booked_label(lang: str, sub: dict) -> str:
    return long_day(lang, sub["booked_date"]) + (tx(lang, f" в {sub['booked_time']}", f" о {sub['booked_time']}",
                                                          f" a las {sub['booked_time']}",
                                                          f" at {sub['booked_time']}")
                                                 if sub.get("booked_time") else "")


def summary(sub: dict, lang: Optional[str] = None) -> Tuple[str, str]:
    """Короткий статус подписки: (эмодзи, текст)."""
    lang = lang or lang_of(sub["chat"])
    last = sub.get("last")
    if sub.get("booked_date"):
        when = short_day(lang, sub["booked_date"]) + (f" {sub['booked_time']}" if sub.get("booked_time") else "")
        return "✅", tx(lang, f"записан на {when}", f"записаний на {when}", f"cita el {when}", f"booked for {when}")
    if sub.get("paused"):
        return "⏸", tx(lang, "на паузе", "на паузі", "en pausa", "paused")
    if last is None:
        return "⏳", tx(lang, "ещё не проверялось", "ще не перевірялося", "aún sin revisar", "not checked yet")
    if (sub.get("fails") or 0) >= 3:
        return "⚠️", tx(lang, "сайт DGT не отвечает", "сайт DGT не відповідає",
                              "la web de la DGT no responde",
                              "DGT website isn't responding")
    days = all_days(last, sub.get("max_days"))
    if days:
        return "🟢", days_word(lang, len(days)) + tx(lang, ", с ", ", з ", ", desde el ", ", from ") + short_day(lang, days[0][0])
    if all_days(last):
        return "🟡", tx(lang, "есть даты, но позже фильтра", "є дати, але пізніше фільтра",
                             "hay fechas, pero más allá del filtro",
                             "dates exist, but past your filter")
    if any(r.get("status") == dgt.NEEDS_DATA for r in last or []):
        return "🔐", tx(lang, "запись через заявку на сайте DGT", "запис через заявку на сайті DGT",
                             "cita mediante solicitud en la web de la DGT",
                             "booking by application on the DGT website")
    status = last[0]["status"] if last else dgt.UNKNOWN
    return {
        dgt.FULL: ("🔴", tx(lang, "мест нет", "місць немає", "sin plazas", "no slots")),
        dgt.NO_AREA: ("⚪️", tx(lang, "такой записи в офисе нет", "такого запису в офісі немає",
                                     "la oficina no tiene esta cita",
                                     "office has no such appointment")),
        dgt.NOT_CONFIGURED: ("⚪️", tx(lang, "офис не принимает эту запись", "офіс не приймає цей запис",
                                            "la oficina no admite esta cita",
                                            "office doesn't accept this appointment")),
    }.get(status, ("❔", tx(lang, "не удалось прочитать сайт", "не вдалося прочитати сайт",
                                 "no se pudo leer la web",
                                 "couldn't read the website")))


# ---------- язык ----------

def language_picker(back: str = "") -> Tuple[str, dict]:
    items = [btn(label, f"lg:{code}" + (f":{back}" if back else "")) for code, label in LANGS.items()]
    return (f"{BRAND_LINE}\n\n🌐 <b>Оберіть мову</b>\n🌐 <b>Выберите язык</b>\n🌐 <b>Elige tu idioma</b>\n🌐 <b>Choose your language</b>",
            ikb([items[:2], items[2:]]))


# ---------- главный экран ----------

def banner(kind: str = "") -> Optional[str]:
    """Картинка над экраном. Версия в адресе: Telegram кэширует превью по ссылке."""
    if not config.PUBLIC_URL:
        return None
    return f"{config.PUBLIC_URL}/static/banner{'_' + kind if kind else ''}.jpg?v={config.VERSION}"


def short_date(lang: str, ts: int) -> str:
    dt = datetime.fromtimestamp(ts, config.TZ)
    return f"{dt.day} {CAL[lang]['short'][dt.month - 1]}"


def hours_text(lang: str, hours: int) -> str:
    if hours < 24:
        return tx(lang, f"{hours} ч", f"{hours} год", f"{hours} h", f"{hours} h")
    return days_word(lang, hours // 24)


def tier_line(chat: int, lang: str) -> str:
    if premium.is_premium(chat):
        until = store.get_chat(chat).get("premium_until") or 0
        when = tx(lang, " до ", " до ", " hasta el ", " until ") + short_date(lang, until) if until > time.time() else ""
        label = tx(lang, " · пробный период", " · пробний період", " · prueba", " · trial") if premium.in_trial(chat) else ""
        return f"💎 <b>{config.BRAND} Premium</b>{when}{label}"
    return BRAND_LINE


def progress(done: int, total: int) -> str:
    return "▰" * done + "▱" * max(0, total - done) + f" {done}/{total}"


def outage_note(lang: str) -> str:
    return tx(lang, "🛠 <b>Идут технические работы.</b> Даты могут быть неактуальны, "
                    "уведомления придут, когда закончим.",
              "🛠 <b>Тривають технічні роботи.</b> Дати можуть бути неактуальні, "
              "сповіщення надійдуть, коли закінчимо.",
                    "🛠 <b>Estamos en mantenimiento.</b> Las fechas pueden no estar al día; "
                    "los avisos llegarán cuando terminemos.",
                    "🛠 <b>Maintenance in progress.</b> Dates may be out of date; "
                    "alerts will resume when we finish.")


def dashboard(chat: int, name: str = "", next_check: Optional[int] = None, note: str = "") -> Tuple[str, dict]:
    lang = lang_of(chat)
    subs = store.subs_of(chat)
    paid = premium.is_premium(chat)
    lines = [tier_line(chat, lang), ""]
    if not subs:
        lines += [
            tx(lang, "Привет", "Привіт", "Hola", "Hi") + (f", <b>{esc(name)}</b>" if name else "") + "! 👋",
            tx(lang, "Ловлю свободные даты записи в <b>DGT (Tráfico)</b> и пишу сразу, как они появляются. "
                     "Сайт обновлять больше не нужно.",
               "Ловлю вільні дати запису в <b>DGT (Tráfico)</b> і пишу одразу, щойно вони з’являються. "
               "Сайт оновлювати більше не треба.",
                     "Busco fechas libres de cita en la <b>DGT (Tráfico)</b> y te escribo en cuanto aparecen. "
                     "Ya no hace falta recargar la web.",
                     "I catch free appointment dates at <b>DGT (Tráfico)</b> and message you as soon as they appear. "
                     "No more refreshing the website."),
            "",
            "<blockquote>" + tx(lang, "1️⃣ Выбери офис\n2️⃣ Выбери тип записи\n3️⃣ Получи уведомление 🔔",
                                "1️⃣ Обери офіс\n2️⃣ Обери тип запису\n3️⃣ Отримай сповіщення 🔔",
                                      "1️⃣ Elige una oficina\n2️⃣ Elige el tipo de cita\n3️⃣ Recibe el aviso 🔔",
                                      "1️⃣ Choose an office\n2️⃣ Choose an appointment type\n3️⃣ Get an alert 🔔") + "</blockquote>",
            tx(lang, "📡 Не знаешь, куда ехать? <b>Радар</b> найдёт офис рядом, где запись раньше всего.",
               "📡 Не знаєш, куди їхати? <b>Радар</b> знайде офіс поруч, де запис найшвидше.",
                     "📡 ¿No sabes adónde ir? El <b>Radar</b> encuentra la oficina cercana con la cita más próxima.",
                     "📡 Not sure where to go? <b>Radar</b> finds the nearby office with the earliest appointment."),
        ]
    else:
        minutes = store.setting("interval_premium" if paid else "interval")
        strip = [f"🏢 <b>{premium.active_subs_count(chat)}/{premium.limit_subs(chat)}</b>"]
        if store.setting("checks_paused"):
            strip.append(tx(lang, "⏸ проверки остановлены", "⏸ перевірки зупинені", "⏸ revisiones detenidas", "⏸ checks stopped"))
        elif next_check and next_check > time.time():
            mins = max(1, math.ceil((next_check - time.time()) / 60))
            strip.append(tx(lang, f"⏱ через <b>{mins} мин</b>", f"⏱ за <b>{mins} хв</b>",
                                  f"⏱ en <b>{mins} min</b>",
                                  f"⏱ in <b>{mins} min</b>"))
        strip.append(tx(lang, f"⚡️ каждые {minutes} мин", f"⚡️ кожні {minutes} хв",
                              f"⚡️ cada {minutes} min",
                              f"⚡️ every {minutes} min"))
        lines.append(" · ".join(strip))
        rows = []
        for s in subs:
            emoji, text = summary(s, lang)
            rows.append(f"{emoji} <b>{esc(city(s['centro']))}</b> · {esc(sub_area(s))}\n<i>{text}</i>")
        lines.append("<blockquote>" + "\n".join(rows) + "</blockquote>")
        if not paid:
            lines.append(tx(lang, f"💎 Premium от {premium.plan_price('p7')} ⭐ или бесплатно в «Бонусах»",
                            f"💎 Premium від {premium.plan_price('p7')} ⭐ або безкоштовно в «Бонусах»",
                                  f"💎 Premium desde {premium.plan_price('p7')} ⭐ o gratis en «Bonos»",
                                  f"💎 Premium from {premium.plan_price('p7')} ⭐ or free in “Bonuses”"))
    if outage():
        lines += ["", outage_note(lang)]
    if note:
        lines += ["", note]

    rows = [[btn(tx(lang, "➕ Добавить офис", "➕ Додати офіс", "➕ Añadir oficina", "➕ Add office"), "p:0", "primary")]]
    if premium.can_trial(chat):
        rows.append([trial_btn(lang)])
    rows.append([btn(tx(lang, "📋 Мои офисы", "📋 Мої офіси",
                              "📋 Mis oficinas",
                              "📋 My offices") + (f" · {len(subs)}" if subs else ""), "l"),
                 btn("📡 " + tx(lang, "Радар", "Радар", "Radar", "Radar"), "rd")])
    rows.append([btn("💎 Premium", "pr", None if paid else "success"),
                 btn(tx(lang, "🎁 Бонусы", "🎁 Бонуси", "🎁 Bonos", "🎁 Bonuses"), "bn")])
    if paid and premium.app_url():
        rows.append([webapp(tx(lang, "📱 Приложение", "📱 Застосунок", "📱 Miniapp", "📱 Mini app"), premium.app_url(), "primary")])
    rows.append([btn(tx(lang, "⚙️ Настройки", "⚙️ Налаштування",
                              "⚙️ Ajustes",
                              "⚙️ Settings"), "st"), btn(tx(lang, "❓ Помощь", "❓ Допомога",
                                                                                      "❓ Ayuda",
                                                                                      "❓ Help"), "hp")])
    rows.append([btn(tx(lang, "🛂 Документы", "🛂 Документи",
                              "🛂 Documentos",
                              "🛂 Documents"), "dc"), btn(tx(lang, "🇺🇦 Для украинцев", "🇺🇦 Для українців",
                                                                                 "🇺🇦 Para ucranianos",
                                                                                 "🇺🇦 For Ukrainians"), "ua")])
    rows.append([btn(board_btn(lang), "jb")])
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
    text = (header or tx(lang, "🏢 <b>Выбери офис DGT</b> · шаг 1 из 2", "🏢 <b>Обери офіс DGT</b> · крок 1 з 2",
                               "🏢 <b>Elige una oficina de la DGT</b> · paso 1 de 2",
                               "🏢 <b>Choose a DGT office</b> · step 1 of 2")) + "\n\n" + \
        tx(lang, "🔎 Или просто напиши город, например <i>Valencia</i>.",
           "🔎 Або просто напиши місто, наприклад <i>Valencia</i>.",
                 "🔎 O escribe la ciudad, por ejemplo <i>Valencia</i>.",
                 "🔎 Or just type a city, for example <i>Valencia</i>.")
    return text, ikb(rows)


def search_results(chat: int, query: str, found: List[str], prefix: str = "c", pager: str = "p") -> Tuple[str, dict]:
    lang = lang_of(chat)
    rows = [[btn(city(c), f"{prefix}:{c}")] for c in sorted(found, key=lambda c: fold(city(c)))]
    rows.append([btn(tx(lang, "🏢 Все офисы", "🏢 Усі офіси",
                              "🏢 Todas las oficinas",
                              "🏢 All offices"), f"{pager}:0"), home_btn(lang)])
    return tx(lang, "🔎 Офисы по запросу", "🔎 Офіси за запитом",
                    "🔎 Oficinas para",
                    "🔎 Offices matching") + f" «{esc(query)}»:", ikb(rows)


def not_found(chat: int, query: str) -> str:
    lang = lang_of(chat)
    return tx(lang, f"😕 Не нашёл офис «{esc(query)}».\n\n🏢 <b>Выбери из списка</b>",
              f"😕 Не знайшов офіс «{esc(query)}».\n\n🏢 <b>Обери зі списку</b>",
                    f"😕 No encuentro la oficina «{esc(query)}».\n\n🏢 <b>Elige de la lista</b>",
                    f"😕 I couldn't find the office “{esc(query)}”.\n\n🏢 <b>Pick one from the list</b>")


def too_many(chat: int) -> str:
    return tx(lang_of(chat), "🔎 Слишком много совпадений — уточни название или выбери из списка.",
              "🔎 Забагато збігів — уточни назву або обери зі списку.",
                             "🔎 Demasiadas coincidencias: afina el nombre o elige de la lista.",
                             "🔎 Too many matches: narrow the name down or pick from the list.")


def loading(text: str) -> Tuple[str, dict]:
    return f"⏳ {text}", ikb([])


def areas(chat: int, cid: str, options: List[Tuple[str, str]]) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = (f"🏢 <b>{esc(city(cid))}</b> · " + tx(lang, "шаг 2 из 2", "крок 2 з 2",
                                                       "paso 2 de 2",
                                                       "step 2 of 2") + f"\n<i>{esc(dgt.CENTROS[cid])}</i>\n\n"
            + tx(lang, "Какой тип записи нужен?", "Який тип запису потрібен?",
                       "¿Qué tipo de cita necesitas?",
                       "What type of appointment do you need?"))
    rows = []
    for code, label in options:
        hint = area_hint(lang, label)
        lock = " 🔐" if cats_of(label) == {"cnj"} else ""
        rows.append([btn(f"{area_emoji(label)} {area_label(code, label)}" + (f" — {hint}" if hint else "") + lock,
                         f"a:{cid}:{code}")])
    rows.append([btn(tx(lang, "⬅️ Офисы", "⬅️ Офіси", "⬅️ Oficinas", "⬅️ Offices"), "p:0"), home_btn(lang)])
    return text, ikb(rows)


def areas_error(chat: int, cid: str, retry: str) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, f"😕 Сайт DGT не ответил, не могу получить список услуг для <b>{esc(city(cid))}</b>.\n"
                     "Попробуй ещё раз через минуту.",
               f"😕 Сайт DGT не відповів, не можу отримати список послуг для <b>{esc(city(cid))}</b>.\n"
               "Спробуй ще раз за хвилину.",
                     f"😕 La web de la DGT no ha respondido y no puedo obtener los servicios de <b>{esc(city(cid))}</b>.\n"
                     "Inténtalo de nuevo en un minuto.",
                     f"😕 The DGT website didn't respond, so I can't get the services for <b>{esc(city(cid))}</b>.\n"
                     "Try again in a minute."),
            ikb([[btn(tx(lang, "🔄 Повторить", "🔄 Повторити", "🔄 Reintentar", "🔄 Retry"), retry)], [home_btn(lang)]]))


# ---------- подписки ----------

def subs_list(chat: int, header: str = "") -> Tuple[str, dict]:
    lang = lang_of(chat)
    subs = store.subs_of(chat)
    if not subs:
        return (tx(lang, "📋 <b>Пока пусто</b>\n\nДобавь офис — и я начну следить за свободными датами.",
                   "📋 <b>Поки порожньо</b>\n\nДодай офіс — і я почну стежити за вільними датами.",
                         "📋 <b>Aún no hay nada</b>\n\nAñade una oficina y empezaré a vigilar las fechas libres.",
                         "📋 <b>Nothing here yet</b>\n\nAdd an office and I'll start watching for free dates."),
                ikb([[btn(tx(lang, "➕ Добавить офис", "➕ Додати офіс",
                                   "➕ Añadir oficina",
                                   "➕ Add office"), "p:0", "primary")], [home_btn(lang)]]))
    lines = [header or tx(lang, "📋 <b>Мои офисы</b> · ", "📋 <b>Мої офіси</b> · ",
                                "📋 <b>Mis oficinas</b> · ",
                                "📋 <b>My offices</b> · ")
             + f"{premium.active_subs_count(chat)}/{premium.limit_subs(chat)}", ""]
    rows = []
    items = []
    for s in subs:
        emoji, text = summary(s, lang)
        items.append(f"{emoji} {title(s)}\n<i>{text}</i>")
        rows.append([btn(f"{emoji} {plain_title(s)}", f"s:{s['id']}")])
    lines[-1:] = ["<blockquote>" + "\n".join(items) + "</blockquote>"]
    lines.append(tx(lang, "Нажми на офис — покажу подробности.", "Натисни на офіс — покажу подробиці.",
                          "Pulsa una oficina para ver los detalles.",
                          "Tap an office to see the details."))
    rows.append([btn(tx(lang, "➕ Добавить", "➕ Додати",
                              "➕ Añadir",
                              "➕ Add"), "p:0", "primary"), btn(tx(lang, "🔄 Проверить все", "🔄 Перевірити всі",
                                                                                         "🔄 Revisar todas",
                                                                                         "🔄 Check all"), "ca")])
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


def canje_note(lang: str) -> str:
    return tx(lang, "<blockquote>DGT изменил порядок canje: сначала заявка на сайте с NIE, датой рождения и страной. "
                    "DGT проверит права и через несколько дней сообщит результат, только потом можно выбрать дату.</blockquote>\n"
                    "Личные данные бот не вводит, поэтому этот календарь не видит и о датах canje написать не сможет.",
              "<blockquote>DGT змінив порядок canje: спершу заявка на сайті з NIE, датою народження й країною. "
              "DGT перевірить права й за кілька днів повідомить результат, лише потім можна обрати дату.</blockquote>\n"
              "Особисті дані бот не вводить, тому цей календар не бачить і про дати canje написати не зможе.",
                    "<blockquote>La DGT ha cambiado el canje: primero se presenta una solicitud en su web con NIE, fecha de nacimiento y país. "
                    "La DGT revisa el permiso y en unos días comunica el resultado; solo después se puede elegir fecha.</blockquote>\n"
                    "El bot no introduce datos personales, así que no ve ese calendario y no podrá avisarte de fechas de canje.",
                    "<blockquote>DGT changed the canje process: first you apply on its website with your NIE, date of birth and country. "
                    "DGT reviews the licence and replies within a few days; only then can you choose a date.</blockquote>\n"
                    "The bot doesn't enter personal data, so it can't see that calendar and can't alert you about canje dates.")


def card(sub: dict, note: str = "") -> Tuple[str, dict]:
    if sub.get("booked_date"):
        return booked_card(sub, note)
    lang, last, sid = lang_of(sub["chat"]), sub.get("last"), sub["id"]
    lines = [f"🏢 {title(sub)}", where_block(lang, last)]

    days = all_days(last, sub.get("max_days"))
    if sub.get("paused"):
        lines.append(tx(lang, "⏸ <b>Подписка на паузе</b> — уведомления не приходят\n",
                        "⏸ <b>Підписка на паузі</b> — сповіщення не надходять\n",
                              "⏸ <b>Oficina en pausa</b>: no llegan avisos\n",
                              "⏸ <b>Office paused</b>: no alerts are sent\n"))
    if days:
        lines.append(f"🟢 <b>{free_days_word(lang, len(days))}</b> · {day_range(lang, days)}")
        lines += nearest_lines(lang, last, days)
        lines.append(f"<blockquote expandable>{days_block(lang, days)}</blockquote>")
    elif not sub.get("paused"):
        emoji, text = summary(sub, lang)
        lines.append(f"{emoji} <b>{cap(text)}</b>")
        if emoji in ("🔴", "🟡", "⏳"):
            lines.append(tx(lang, "Напишу, как только появятся подходящие даты.",
                            "Напишу, щойно з’являться відповідні дати.",
                                  "Te escribiré en cuanto aparezcan fechas que te sirvan.",
                                  "I'll message you as soon as suitable dates appear."))
        elif emoji == "🔐":
            lines.append(canje_note(lang))
        elif emoji == "⚪️":
            lines.append(tx(lang, "Похоже, в этом офисе такой тип записи называется иначе — выбери его заново.",
                            "Схоже, в цьому офісі такий тип запису називається інакше — обери його знову.",
                                  "Parece que en esta oficina ese tipo de cita tiene otro nombre: elígelo de nuevo.",
                                  "It looks like this office calls that appointment type something else: choose it again."))
    lines.append("")
    lines.append(tx(lang, "📅 Даты: ", "📅 Дати: ", "📅 Fechas: ", "📅 Dates: ") + f"<b>{filter_label(lang, sub.get('max_days'))}</b>"
                 + (f" · 🕐 {fmt_ts(sub['checked_at'], lang)}" if sub.get("checked_at") else ""))
    if note:
        lines.append(f"\n{note}")

    status = (last or [{}])[0].get("status")
    if outage():
        lines.insert(2, outage_note(lang) + "\n")
    rows = [[url(tx(lang, "📝 Записаться на сайте DGT", "📝 Записатися на сайті DGT",
                          "📝 Pedir cita en la web de la DGT",
                          "📝 Book on the DGT website"), dgt.START_URL, "primary")]]
    if status == dgt.NO_AREA:
        rows.append([btn(tx(lang, "🔁 Выбрать тип записи заново", "🔁 Обрати тип запису знову",
                                  "🔁 Elegir de nuevo el tipo de cita",
                                  "🔁 Choose the appointment type again"), f"c:{sub['centro']}")])
    if days:
        rows.append([btn(tx(lang, "✅ Я записался", "✅ Я записався", "✅ Ya tengo cita", "✅ I booked it"), f"bk:{sid}", "success")])
    rows += [
        [btn(tx(lang, "🗓 Календарь", "🗓 Календар",
                      "🗓 Calendario",
                      "🗓 Calendar"), f"k:{sid}:0"), btn(tx(lang, "🔄 Обновить", "🔄 Оновити",
                                                                                "🔄 Actualizar",
                                                                                "🔄 Refresh"), f"r:{sid}")],
        [btn("📡 " + tx(lang, "Радар рядом", "Радар поруч", "Radar cercano", "Nearby radar"), f"rs:{sid}"),
         btn("📅 " + cap(filter_label(lang, sub.get("max_days"))), f"f:{sid}")],
        [btn(tx(lang, "▶️ Возобновить", "▶️ Відновити",
                      "▶️ Reanudar",
                      "▶️ Resume") if sub.get("paused") else "⏸ " + tx(lang, "Пауза", "Пауза",
                                                                                                  "Pausa",
                                                                                                  "Pause"), f"z:{sid}"),
         btn(tx(lang, "📊 История", "📊 Історія", "📊 Historial", "📊 History"), f"h:{sid}"), btn("🗑", f"x:{sid}", "danger")],
        [btn(tx(lang, "⬅️ Подписки", "⬅️ Підписки", "⬅️ Mis oficinas", "⬅️ My offices"), "l"), home_btn(lang)],
    ]
    return "\n".join(l for l in lines if l is not None), ikb(rows)


def calendar_view(sub: dict, idx: int = 0) -> Tuple[str, dict]:
    lang, sid = lang_of(sub["chat"]), sub["id"]
    c = CAL[lang]
    days = all_days(sub.get("last"))
    back = [btn(tx(lang, "⬅️ К подписке", "⬅️ До підписки", "⬅️ A la oficina", "⬅️ Back to office"), f"s:{sid}"), home_btn(lang)]
    head = tx(lang, "🗓 <b>Календарь</b> · ", "🗓 <b>Календар</b> · ", "🗓 <b>Calendario</b> · ", "🗓 <b>Calendar</b> · ") + title(sub)
    if not days:
        return (head + "\n\n" + tx(lang, "Свободных дат сейчас нет. Напишу, как только появятся.",
                                   "Вільних дат зараз немає. Напишу, щойно з’являться.",
                                         "Ahora no hay fechas libres. Te escribiré en cuanto aparezcan.",
                                         "No free dates right now. I'll message you as soon as they appear."), ikb([back]))
    months = sorted({iso[:7] for iso, _ in days})
    idx %= len(months)
    y, m = map(int, months[idx].split("-"))
    loads = dict(days)
    in_month = [d for d in days if d[0].startswith(months[idx])]
    rows = [[
        btn("◀️", f"k:{sid}:{idx - 1}") if len(months) > 1 else btn(BLANK, "noop"),
        btn(f"{cap(c['months'][m - 1])} {y}", "noop"),
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
    rows.append([btn(tx(lang, "✅ Я записался", "✅ Я записався", "✅ Ya tengo cita", "✅ I booked it"), f"bk:{sid}")])
    rows.append(back)
    text = (f"{head}\n\n{cap(c['prep'][m - 1])}: <b>{free_days_word(lang, len(in_month))}</b>\n"
            + tx(lang, "🟢 много мест · 🟡 средне · 🔴 мало\n<i>Нажми на день — покажу подробности</i>",
                 "🟢 багато місць · 🟡 середньо · 🔴 мало\n<i>Натисни на день — покажу подробиці</i>",
                       "🟢 muchas plazas · 🟡 medio · 🔴 pocas\n<i>Pulsa un día para ver los detalles</i>",
                       "🟢 plenty · 🟡 some · 🔴 few\n<i>Tap a day to see the details</i>"))
    return text, ikb(rows)


def day_popup(sub: dict, iso: str) -> str:
    lang = lang_of(sub["chat"])
    loads = dict(all_days(sub.get("last")))
    head = cap(long_day(lang, iso))
    if iso not in loads:
        return head + "\n" + tx(lang, "В этот день свободных мест нет", "Цього дня вільних місць немає",
                                      "Ese día no hay plazas libres",
                                      "No free slots on this day")
    load_text = {
        "bajaOcupacion": tx(lang, "🟢 много свободных мест", "🟢 багато вільних місць",
                                  "🟢 muchas plazas libres",
                                  "🟢 plenty of free slots"),
        "mediaOcupacion": tx(lang, "🟡 занято 33–66%", "🟡 зайнято 33–66%", "🟡 ocupado al 33–66 %", "🟡 33–66% taken"),
        "altaOcupacion": tx(lang, "🔴 почти всё занято", "🔴 майже все зайнято", "🔴 casi todo ocupado", "🔴 almost full"),
    }.get(loads[iso], "")
    text = f"{head}\n{load_text}"
    hours = hours_for(sub.get("last"), iso)
    if hours:
        text += "\n⏰ " + " · ".join(hours[:10]) + (" …" if len(hours) > 10 else "")
    return text


def filter_view(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    text = (tx(lang, "📅 <b>Какие даты присылать?</b>", "📅 <b>Які дати надсилати?</b>",
                     "📅 <b>¿Qué fechas te aviso?</b>",
                     "📅 <b>Which dates should I send?</b>") + f"\n{title(sub)}\n\n"
            + tx(lang, "Например, если у тебя уже есть запись через месяц, выбери «до 30 дней» — "
                       "и я напишу только о более ранних датах.",
                 "Наприклад, якщо в тебе вже є запис через місяць, обери «до 30 днів» — "
                 "і я напишу лише про раніші дати.",
                       "Por ejemplo, si ya tienes cita dentro de un mes, elige «hasta 30 días» "
                       "y solo te avisaré de fechas anteriores.",
                       "For example, if you already have an appointment in a month, choose “up to 30 days” "
                       "and I'll only tell you about earlier dates."))
    cur = sub.get("max_days") or 0
    rows = [[btn(("✅ " if v == cur else "") + cap(filter_label(lang, v)), f"fs:{sub['id']}:{v}")]
            for v in FILTER_DAYS]
    rows.append([btn(tx(lang, "⬅️ К подписке", "⬅️ До підписки", "⬅️ A la oficina", "⬅️ Back to office"), f"s:{sub['id']}")])
    return text, ikb(rows)


def history_view(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    evs = store.events(sub["centro"], sub["area"], 30)
    lines = [tx(lang, "📊 <b>История</b> · ", "📊 <b>Історія</b> · ",
                      "📊 <b>Historial</b> · ",
                      "📊 <b>History</b> · ") + title(sub), ""]
    if not evs:
        lines.append(tx(lang, "Пока ни разу не видел здесь свободных мест.\nИстория начнёт копиться, как только они появятся.",
                        "Поки жодного разу не бачив тут вільних місць.\nІсторія почне накопичуватися, щойно вони з’являться.",
                              "Todavía no he visto plazas libres aquí.\nEl historial empezará a llenarse cuando aparezcan.",
                              "I haven't seen free slots here yet.\nHistory will build up once they appear."))
    else:
        if not evs[0]["closed_at"]:
            lines.append(tx(lang, "🟢 Места есть прямо сейчас — появились ", "🟢 Місця є просто зараз — з’явилися ",
                                  "🟢 Hay plazas ahora mismo: aparecieron ",
                                  "🟢 Slots are open right now: they appeared ")
                         + fmt_ts(evs[0]["opened_at"], lang) + "\n")
        lines.append(tx(lang, "<b>Когда появлялись места</b> (время Мадрида):", "<b>Коли з’являлися місця</b> (час Мадрида):",
                              "<b>Cuándo aparecieron plazas</b> (hora de Madrid):",
                              "<b>When slots appeared</b> (Madrid time):"))
        items = []
        for e in evs[:10]:
            dur = (tx(lang, "ещё есть", "ще є", "siguen ahí", "still open") if not e["closed_at"]
                   else tx(lang, "держались ", "трималися ",
                                 "duraron ",
                                 "lasted ") + fmt_dur(e["closed_at"] - e["opened_at"], lang))
            items.append(f"• {fmt_ts(e['opened_at'], lang)} — {dur}, {days_word(lang, e['days'] or 0)}")
        lines.append("<blockquote>" + "\n".join(items) + "</blockquote>")
        if len(evs) >= 3:
            hour, _ = Counter(datetime.fromtimestamp(e["opened_at"], config.TZ).hour for e in evs).most_common(1)[0]
            lines.append(tx(lang, f"⏰ Чаще всего появляются между {hour}:00 и {hour + 1}:00",
                            f"⏰ Найчастіше з’являються між {hour}:00 і {hour + 1}:00",
                                  f"⏰ Suelen aparecer entre las {hour}:00 y las {hour + 1}:00",
                                  f"⏰ They usually appear between {hour}:00 and {hour + 1}:00"))
        closed = [e["closed_at"] - e["opened_at"] for e in evs if e["closed_at"]]
        if closed:
            lines.append(tx(lang, "⌛️ В среднем держатся ", "⌛️ У середньому тримаються ",
                                  "⌛️ De media duran ",
                                  "⌛️ On average they last ")
                         + fmt_dur(sum(closed) // len(closed), lang))
        lines.append(tx(lang, "\n<i>Точность — интервал проверки.</i>", "\n<i>Точність — інтервал перевірки.</i>",
                              "\n<i>La precisión depende del intervalo de revisión.</i>",
                              "\n<i>Accuracy depends on the check interval.</i>"))
    return "\n".join(lines), ikb([[btn(tx(lang, "⬅️ К подписке", "⬅️ До підписки",
                                                "⬅️ A la oficina",
                                                "⬅️ Back to office"), f"s:{sub['id']}")]])


def delete_confirm(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    return (tx(lang, "🗑 <b>Удалить подписку?</b>\n", "🗑 <b>Видалити підписку?</b>\n",
                     "🗑 <b>¿Quitar esta oficina?</b>\n",
                     "🗑 <b>Remove this office?</b>\n") + title(sub),
            ikb([[btn(tx(lang, "Да, удалить", "Так, видалити", "Sí, quitar", "Yes, delete"), f"xx:{sub['id']}", "danger"),
                  btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), f"s:{sub['id']}")]]))


# ---------- «Я записался» ----------

def checklist(lang: str, sub: dict) -> List[str]:
    cats = cats_of(sub_area(sub))
    items = [tx(lang, "Документ: DNI, NIE/TIE или паспорт (оригинал)", "Документ: DNI, NIE/TIE або паспорт (оригінал)",
                      "Documento: DNI, NIE/TIE o pasaporte (original)",
                      "ID: DNI, NIE/TIE or passport (original)"),
             tx(lang, "Подтверждение записи (номер cita)", "Підтвердження запису (номер cita)",
                      "Confirmación de la cita (número de cita)",
                      "Appointment confirmation (cita number)"),
             tx(lang, "Оплаченная пошлина DGT (tasa), если она нужна для твоего trámite",
                "Сплачений збір DGT (tasa), якщо він потрібен для твого trámite",
                      "Tasa de la DGT pagada, si tu trámite la requiere",
                      "Paid DGT fee (tasa), if your trámite requires one")]
    if "cnj" in cats:
        items += [tx(lang, "Оригинал иностранных прав и их копия", "Оригінал іноземних прав і їх копія",
                           "Permiso extranjero original y una copia",
                           "Original foreign licence and a copy"),
                  tx(lang, "Цветное фото 32×26 мм", "Кольорове фото 32×26 мм",
                           "Foto en color de 32×26 mm",
                           "Colour photo, 32×26 mm"),
                  tx(lang, "Медсправка из Centro de Reconocimiento de Conductores",
                     "Медична довідка з Centro de Reconocimiento de Conductores",
                           "Informe de un Centro de Reconocimiento de Conductores",
                           "Medical report from a Centro de Reconocimiento de Conductores"),
                  tx(lang, "Заявление (solicitud) — бланк на сайте DGT", "Заява (solicitud) — бланк на сайті DGT",
                           "Solicitud: impreso en la web de la DGT",
                           "Application (solicitud): form on the DGT website"),
                  tx(lang, "Для украинских прав присяжный перевод не нужен",
                     "Для українських прав присяжний переклад не потрібен",
                           "Para permisos ucranianos no hace falta traducción jurada",
                           "Ukrainian licences don't need a sworn translation")]
    elif "rpc" in cats:
        items += [tx(lang, "Права страны ЕС/ЕЭЗ", "Права країни ЄС/ЄЕЗ", "Permiso de un país de la UE/EEE", "EU/EEA licence"),
                  tx(lang, "Цветное фото 32×26 мм", "Кольорове фото 32×26 мм",
                           "Foto en color de 32×26 mm",
                           "Colour photo, 32×26 mm"),
                  tx(lang, "Медсправка из Centro de Reconocimiento de Conductores",
                     "Медична довідка з Centro de Reconocimiento de Conductores",
                           "Informe de un Centro de Reconocimiento de Conductores",
                           "Medical report from a Centro de Reconocimiento de Conductores")]
    elif "san" in cats:
        items += [tx(lang, "Уведомление о штрафе (número de expediente)", "Повідомлення про штраф (número de expediente)",
                           "Notificación de la multa (número de expediente)",
                           "Fine notice (número de expediente)"),
                  tx(lang, "Документы в свою пользу, если обжалуешь", "Документи на свою користь, якщо оскаржуєш",
                           "Documentos a tu favor, si recurres",
                           "Supporting documents, if you're appealing")]
    elif "exm" in cats:
        items += [tx(lang, "Для практического экзамена обычно нужна автошкола и её машина",
                     "Для практичного іспиту зазвичай потрібна автошкола і її авто",
                           "Para el examen práctico suele hacer falta autoescuela y su coche",
                           "The practical test usually requires a driving school and its car"),
                  tx(lang, "Уточни в автошколе, что ещё взять", "Уточни в автошколі, що ще взяти",
                           "Pregunta en la autoescuela qué más llevar",
                           "Ask your driving school what else to bring")]
    if cats & {"veh", "mat"}:
        items += [tx(lang, "Permiso de circulación и ficha técnica (карточка ITV)",
                     "Permiso de circulación і ficha técnica (картка ITV)",
                           "Permiso de circulación y ficha técnica",
                           "Permiso de circulación and ficha técnica (ITV card)"),
                  tx(lang, "Договор купли-продажи — при смене владельца", "Договір купівлі-продажу — при зміні власника",
                           "Contrato de compraventa, si cambia el titular",
                           "Sale contract, if the owner changes"),
                  tx(lang, "Налог на транспорт (IVTM) и действующий ITV", "Податок на транспорт (IVTM) і чинний ITV",
                           "Impuesto de circulación (IVTM) e ITV en vigor",
                           "Vehicle tax (IVTM) and a valid ITV")]
    if "lic" in cats:
        items += [tx(lang, "Текущие права, если есть", "Чинні права, якщо є",
                           "Permiso actual, si lo tienes",
                           "Current licence, if you have one"),
                  tx(lang, "Фото 32×26 мм и медсправка — для продления или дубликата",
                     "Фото 32×26 мм і медична довідка — для продовження або дубліката",
                           "Foto de 32×26 mm e informe médico, para renovación o duplicado",
                           "32×26 mm photo and medical report, for renewal or a duplicate")]
    return items


def booking_dates(sub: dict) -> Tuple[str, dict]:
    lang, sid = lang_of(sub["chat"]), sub["id"]
    days = all_days(sub.get("last"))[:8]
    rows = [[btn(cap(wd_day(lang, iso)), f"bd:{sid}:{iso}") for iso, _ in days[i:i + 2]]
            for i in range(0, len(days), 2)]
    rows.append([btn(tx(lang, "📅 Другая дата", "📅 Інша дата", "📅 Otra fecha", "📅 Another date"), f"bo:{sid}")])
    rows.append([btn(tx(lang, "⬅️ Назад", "⬅️ Назад", "⬅️ Atrás", "⬅️ Back"), f"s:{sid}")])
    return (tx(lang, "🎉 <b>Отлично!</b> На какую дату записался?\n", "🎉 <b>Чудово!</b> На яку дату записався?\n",
                     "🎉 <b>¡Genial!</b> ¿Para qué fecha tienes cita?\n",
                     "🎉 <b>Great!</b> What date did you book?\n")
            + title(sub) + "\n\n" + tx(lang, "Напомню накануне и покажу, что взять с собой.",
                                       "Нагадаю напередодні і підкажу, що взяти з собою.",
                                             "Te lo recordaré la víspera y te diré qué llevar.",
                                             "I'll remind you the day before and tell you what to bring."), ikb(rows))


def booking_times(sub: dict, iso: str) -> Tuple[str, dict]:
    lang, sid = lang_of(sub["chat"]), sub["id"]
    hours = hours_for(sub.get("last"), iso)[:16]
    rows = [[btn(h, f"bt:{sid}:{iso}:{h.replace(':', '')}") for h in hours[i:i + 4]] for i in range(0, len(hours), 4)]
    rows.append([btn(tx(lang, "Без времени", "Без часу", "Sin hora", "No time"), f"bt:{sid}:{iso}:-")])
    rows.append([btn(tx(lang, "⬅️ Назад", "⬅️ Назад", "⬅️ Atrás", "⬅️ Back"), f"bk:{sid}")])
    return (tx(lang, "⏰ Во сколько визит?\n", "⏰ О котрій візит?\n",
                     "⏰ ¿A qué hora es la visita?\n",
                     "⏰ What time is the visit?\n") + f"<b>{long_day(lang, iso)}</b>", ikb(rows))


def booking_prompt(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    return (tx(lang, "📅 Напиши дату и время визита, например <code>10.10 10:30</code>",
               "📅 Напиши дату й час візиту, наприклад <code>10.10 10:30</code>",
                     "📅 Escribe la fecha y la hora de la visita, por ejemplo <code>10.10 10:30</code>",
                     "📅 Type the date and time of the visit, for example <code>10.10 10:30</code>"),
            ikb([[btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), f"bk:{sub['id']}")]]))


def booked_card(sub: dict, note: str = "") -> Tuple[str, dict]:
    lang, sid = lang_of(sub["chat"]), sub["id"]
    past = date.fromisoformat(sub["booked_date"]) < today()
    lines = [tx(lang, "✅ <b>Ты записан!</b>", "✅ <b>Ти записаний!</b>",
                      "✅ <b>¡Ya tienes cita!</b>",
                      "✅ <b>You're booked!</b>") if not past
             else tx(lang, "✅ <b>Визит состоялся</b>", "✅ <b>Візит відбувся</b>",
                           "✅ <b>Visita realizada</b>",
                           "✅ <b>Visit completed</b>"),
             f"🏢 {title(sub)}",
             f"📅 <b>{booked_label(lang, sub)}</b>",
             where_block(lang, sub.get("last"))]
    if not past:
        lines.append(tx(lang, "🔔 Напомню накануне в 19:00 и утром в день визита.",
                        "🔔 Нагадаю напередодні о 19:00 і вранці в день візиту.",
                              "🔔 Te lo recordaré la víspera a las 19:00 y la mañana de la visita.",
                              "🔔 I'll remind you at 19:00 the day before and on the morning of your visit."))
        lines.append("")
        lines.append(tx(lang, "📋 <b>Что взять с собой</b>", "📋 <b>Що взяти з собою</b>",
                              "📋 <b>Qué llevar</b>",
                              "📋 <b>What to bring</b>"))
        lines.append("<blockquote expandable>" + "\n".join(f"• {i}" for i in checklist(lang, sub)) + "</blockquote>")
        lines.append(tx(lang, "<i>Список общий — точный перечень для своего trámite проверь на сайте DGT.</i>",
                        "<i>Список загальний — точний перелік для свого trámite перевір на сайті DGT.</i>",
                              "<i>Lista general: comprueba en la web de la DGT lo exacto para tu trámite.</i>",
                              "<i>This is a general list: check the DGT website for your exact trámite.</i>"))
    if note:
        lines.append(f"\n{note}")
    share = url(tx(lang, "🎁 Рассказать другу", "🎁 Розповісти другові", "🎁 Contárselo a un amigo", "🎁 Tell a friend"),
                rewards.share_link(sub["chat"], invite_text(lang)))
    rows = [[share], [url(tx(lang, "📋 Требования на сайте DGT", "📋 Вимоги на сайті DGT",
                          "📋 Requisitos en la web de la DGT",
                          "📋 Requirements on the DGT website"), DGT_SEDE)],
            [btn(tx(lang, "↩️ Запись отменилась — искать снова", "↩️ Запис скасовано — шукати знову",
                          "↩️ Cita cancelada: buscar de nuevo",
                          "↩️ Appointment cancelled: search again"), f"ub:{sid}")],
            [btn(tx(lang, "🗑 Удалить", "🗑 Видалити", "🗑 Quitar", "🗑 Remove"), f"x:{sid}"),
             btn(tx(lang, "⬅️ Подписки", "⬅️ Підписки", "⬅️ Mis oficinas", "⬅️ My offices"), "l"), home_btn(lang)]]
    return "\n".join(l for l in lines if l), ikb(rows)


def reminder(sub: dict, when: str) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    head = (tx(lang, "⏰ <b>Завтра визит в DGT</b>", "⏰ <b>Завтра візит до DGT</b>",
                     "⏰ <b>Mañana tienes cita en la DGT</b>",
                     "⏰ <b>DGT visit tomorrow</b>") if when == "eve"
            else tx(lang, "⏰ <b>Сегодня визит в DGT</b>", "⏰ <b>Сьогодні візит до DGT</b>",
                          "⏰ <b>Hoy tienes cita en la DGT</b>",
                          "⏰ <b>DGT visit today</b>"))
    lines = [head, f"🏢 {title(sub)}", f"📅 <b>{booked_label(lang, sub)}</b>", where_block(lang, sub.get("last")),
             tx(lang, "📋 <b>Не забудь</b>", "📋 <b>Не забудь</b>", "📋 <b>No olvides</b>", "📋 <b>Don't forget</b>"),
             "<blockquote expandable>" + "\n".join(f"• {i}" for i in checklist(lang, sub)) + "</blockquote>",
             tx(lang, "Удачи! 🍀", "Успіху! 🍀", "¡Suerte! 🍀", "Good luck! 🍀")]
    return "\n".join(l for l in lines if l), ikb([[btn(tx(lang, "✖️ Скрыть", "✖️ Сховати", "✖️ Ocultar", "✖️ Hide"), "hide")]])


# ---------- уведомления ----------

def alert(sub: dict, results: list, new: Set[str]) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    days = all_days(results, sub.get("max_days"))
    fresh = len([d for d in days if d[0] in new])
    lines = [tx(lang, "🔔🔔🔔 <b>ЕСТЬ СВОБОДНЫЕ ДАТЫ!</b>", "🔔🔔🔔 <b>Є ВІЛЬНІ ДАТИ!</b>",
                      "🔔🔔🔔 <b>¡HAY FECHAS LIBRES!</b>",
                      "🔔🔔🔔 <b>FREE DATES AVAILABLE!</b>"), f"🏢 {title(sub)}", ""]
    lines += nearest_lines(lang, results, days)
    lines.append("")
    lines.append(f"📅 <b>{days_word(lang, len(days))}</b> · {day_range(lang, days)}"
                 + (tx(lang, f" · новых {fresh}", f" · нових {fresh}",
                             f" · nuevos {fresh}",
                             f" · {fresh} new") if fresh and fresh != len(days) else ""))
    lines.append(f"<blockquote expandable>{days_block(lang, days, new)}</blockquote>")
    if sub.get("max_days"):
        lines.append(tx(lang, f"<i>Показаны даты в пределах {sub['max_days']} дней</i>",
                        f"<i>Показано дати в межах {sub['max_days']} днів</i>",
                              f"<i>Fechas dentro de {sub['max_days']} días</i>",
                              f"<i>Showing dates within {sub['max_days']} days</i>"))
    lines.append(tx(lang, "<i>На сайте: ", "<i>На сайті: ", "<i>En la web: ", "<i>On the website: ")
                 + f"{esc(city(sub['centro']))} → {esc(sub_area(sub))} → Continuar → Pedir cita</i>")
    stamp = datetime.now(config.TZ)
    lines.append(tx(lang, f"🕐 Проверено в {stamp:%H:%M:%S}", f"🕐 Перевірено о {stamp:%H:%M:%S}", f"🕐 Revisado a las {stamp:%H:%M:%S}", f"🕐 Checked at {stamp:%H:%M:%S}"))
    kb = ikb([
        [url(tx(lang, "📝 Записаться на сайте DGT", "📝 Записатися на сайті DGT",
                      "📝 Pedir cita en la web de la DGT",
                      "📝 Book on the DGT website"), dgt.START_URL, "primary")],
        [btn(tx(lang, "✅ Я записался", "✅ Я записався", "✅ Ya tengo cita", "✅ I booked it"), f"bk:{sub['id']}", "success"),
         btn(tx(lang, "🗓 Календарь", "🗓 Календар", "🗓 Calendario", "🗓 Calendar"), f"k:{sub['id']}:0")],
        [btn(tx(lang, "✖️ Скрыть", "✖️ Сховати", "✖️ Ocultar", "✖️ Hide"), "hide")],
    ])
    return "\n".join(lines), kb


def gone(sub: dict) -> Tuple[str, dict]:
    lang = lang_of(sub["chat"])
    now = datetime.now(config.TZ)
    return (f"😔 {title(sub)}\n" + tx(lang, f"Свободные даты разобрали ({now:%H:%M}). Слежу дальше — напишу, как только появятся.",
                                      f"Вільні дати розібрали ({now:%H:%M}). Стежу далі — напишу, щойно з’являться.",
                                           f"Las fechas libres ya se han agotado ({now:%H:%M}). Sigo vigilando: te escribiré en cuanto aparezcan.",
                                           f"The free dates are gone ({now:%H:%M}). I'm still watching and will message you when new ones appear."),
            ikb([[btn(tx(lang, "✖️ Скрыть", "✖️ Сховати", "✖️ Ocultar", "✖️ Hide"), "hide")]]))


# ---------- радар ----------

def radar_start(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    rows, seen = [], set()
    for s in store.subs_of(chat):
        if s["centro"] not in seen:
            seen.add(s["centro"])
            rows.append([btn(f"📍 {city(s['centro'])}", f"rb:{s['centro']}")])
    rows.append([btn(tx(lang, "🏢 Выбрать другой офис", "🏢 Обрати інший офіс",
                              "🏢 Elegir otra oficina",
                              "🏢 Choose another office") if seen
                     else tx(lang, "🏢 Выбрать офис", "🏢 Обрати офіс", "🏢 Elegir oficina", "🏢 Choose an office"), "rp:0")])
    rows.append([btn(tx(lang, "📊 Где чаще появляются места", "📊 Де частіше з’являються місця", "📊 Dónde aparecen más plazas", "📊 Where slots appear most"), "ost")])
    rows.append([home_btn(lang)])
    text = (tx(lang, "📡 <b>Радар</b>\n\nПроверю офисы рядом и покажу, где можно записаться раньше всего.\n\n"
                     "От какого офиса искать?",
               "📡 <b>Радар</b>\n\nПеревірю офіси поруч і покажу, де можна записатися найшвидше.\n\n"
               "Від якого офісу шукати?",
                     "📡 <b>Radar</b>\n\nReviso las oficinas cercanas y te muestro dónde puedes pedir cita antes.\n\n"
                     "¿Desde qué oficina busco?",
                     "📡 <b>Radar</b>\n\nI'll check nearby offices and show you where you can get the earliest appointment.\n\n"
                     "Which office should I search from?"))
    return text, ikb(rows)


def radar_categories(chat: int, cid: str) -> Tuple[str, dict]:
    lang = lang_of(chat)
    rows = [[btn(f"{emoji} {tx(lang, *names)}", f"rr:{cid}:{cat}:100")] for cat, (emoji, *names) in CATS.items() if cat != "cnj"]
    rows.append([btn(tx(lang, "⬅️ Назад", "⬅️ Назад", "⬅️ Atrás", "⬅️ Back"), "rd"), home_btn(lang)])
    return (f"📡 <b>{tx(lang, 'Радар', 'Радар', 'Radar', 'Radar')}</b> · 📍 {esc(city(cid))}\n\n"
            + tx(lang, "Какая запись нужна?", "Який запис потрібен?",
                       "¿Qué cita necesitas?",
                       "Which appointment do you need?"), ikb(rows))


def radar_progress(chat: int, cid: str, cat: str, km: int, done: int, total: int, current: str) -> Tuple[str, dict]:
    lang = lang_of(chat)
    bar = "▰" * done + "▱" * (total - done)
    emoji, *names = CATS[cat]
    return (f"📡 <b>{tx(lang, 'Радар', 'Радар', 'Radar', 'Radar')}</b> · {emoji} {tx(lang, *names)}\n"
            + tx(lang, f"до {km} км от {esc(city(cid))}\n\n", f"до {km} км від {esc(city(cid))}\n\n",
                       f"hasta {km} km de {esc(city(cid))}\n\n",
                       f"within {km} km of {esc(city(cid))}\n\n")
            + f"{bar}  {done}/{total}\n"
            + tx(lang, f"⏳ Проверяю <b>{esc(current)}</b>…", f"⏳ Перевіряю <b>{esc(current)}</b>…",
                       f"⏳ Revisando <b>{esc(current)}</b>…",
                       f"⏳ Checking <b>{esc(current)}</b>…")
            + tx(lang, "\n\n<i>Проверяю офисы по одному, это займёт пару минут.</i>",
                 "\n\n<i>Перевіряю офіси по одному, це займе кілька хвилин.</i>",
                       "\n\n<i>Reviso las oficinas una a una, tardaré un par de minutos.</i>",
                       "\n\n<i>I check offices one at a time, this takes a couple of minutes.</i>"), ikb([]))


def radar_failed(lang: str) -> str:
    return tx(lang, "😕 Радар не смог закончить поиск, попробуй позже.", "😕 Радар не зміг завершити пошук, спробуй пізніше.",
              "😕 El radar no pudo terminar la búsqueda, inténtalo más tarde.", "😕 Radar couldn't finish the search, try again later.")


def radar_results(chat: int, cid: str, cat: str, km: int, found: list) -> Tuple[str, dict]:
    """found: [(centro, код или None, results или None, км)] — уже отсортировано."""
    lang = lang_of(chat)
    emoji, *names = CATS[cat]
    lines = [f"📡 <b>{tx(lang, 'Радар', 'Радар', 'Radar', 'Radar')}</b> · {emoji} {tx(lang, *names)}",
             tx(lang, f"до {km} км от {esc(city(cid))}", f"до {km} км від {esc(city(cid))}",
                      f"hasta {km} km de {esc(city(cid))}",
                      f"within {km} km of {esc(city(cid))}"), ""]
    medals = iter(["🥇", "🥈", "🥉"])
    rows, items = [], []
    subscribed = {(s["centro"], s["area"]) for s in store.subs_of(chat)}
    for centro, code, results, dist in found:
        name = f"<b>{esc(city(centro))}</b>" + (tx(lang, f" · {dist} км", f" · {dist} км", f" · {dist} km", f" · {dist} km") if dist else "")
        days = all_days(results) if results else []
        if days:
            medal = next(medals, "🟢")
            items.append(f"{medal} {name} — " + tx(lang, "с ", "з ",
                                                         "desde el ",
                                                         "from ") + f"<b>{short_day(lang, days[0][0])}</b> "
                         f"({days_word(lang, len(days))})")
            if (centro, code) not in subscribed and len(rows) < 4:
                rows.append([btn(tx(lang, f"🔔 Следить: {city(centro)}", f"🔔 Стежити: {city(centro)}",
                                          f"🔔 Seguir: {city(centro)}",
                                          f"🔔 Track: {city(centro)}"),
                                 f"a:{centro}:{code}")])
        elif code is None:
            items.append(f"⚪️ {name} — " + tx(lang, "нет такой записи", "немає такого запису",
                                                    "no tiene esta cita",
                                                    "no such appointment"))
        elif results and any(r.get("status") == dgt.NEEDS_DATA for r in results):
            items.append(f"🔐 {name} — " + tx(lang, "запись через заявку на сайте DGT", "запис через заявку на сайті DGT",
                                                   "cita mediante solicitud en la web de la DGT",
                                                   "booking by application on the DGT website"))
        elif results is None:
            items.append(f"⚠️ {name} — " + tx(lang, "сайт не ответил", "сайт не відповів",
                                                    "la web no respondió",
                                                    "site didn't respond"))
        else:
            items.append(f"🔴 {name} — " + tx(lang, "мест нет", "місць немає", "sin plazas", "no slots"))
    lines.append("<blockquote>" + "\n".join(items) + "</blockquote>")
    if not any(all_days(r) for _, _, r, _ in found if r):
        lines.append(tx(lang, "😔 Рядом свободных дат нет. Подпишись на ближайший офис — напишу, когда появятся.",
                        "😔 Поруч вільних дат немає. Підпишися на найближчий офіс — напишу, щойно з’являться.",
                              "😔 No hay fechas libres cerca. Sigue la oficina más próxima y te avisaré cuando aparezcan.",
                              "😔 No free dates nearby. Track the closest office and I'll message you when they appear."))
    lines.append(tx(lang, "<i>Расстояние — по прямой между городами.</i>", "<i>Відстань — по прямій між містами.</i>",
                          "<i>Distancia en línea recta entre ciudades.</i>",
                          "<i>Straight-line distance between cities.</i>"))
    if rows:
        rows.insert(0, [url(tx(lang, "📝 Записаться на сайте DGT", "📝 Записатися на сайті DGT",
                                     "📝 Pedir cita en la web de la DGT",
                                     "📝 Book on the DGT website"), dgt.START_URL)])
    wider = [k for k in (150, 250) if k > km]
    if wider:
        lock = "" if premium.is_premium(chat) else " 💎"
        rows.append([btn(tx(lang, f"🔭 Искать до {wider[0]} км", f"🔭 Шукати до {wider[0]} км",
                                  f"🔭 Buscar hasta {wider[0]} km",
                                  f"🔭 Search up to {wider[0]} km") + lock,
                         f"rr:{cid}:{cat}:{wider[0]}")])
    rows.append([btn(tx(lang, "📡 Новый поиск", "📡 Новий пошук", "📡 Nueva búsqueda", "📡 New search"), "rd"), home_btn(lang)])
    return "\n".join(lines), ikb(rows)


# ---------- настройки, помощь ----------

def settings_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    c = store.get_chat(chat)
    quiet, ads = c.get("quiet"), c.get("ads_ok")
    minutes = store.setting("interval_premium" if premium.is_premium(chat) else "interval")
    state = lambda on: tx(lang, "вкл", "увімк", "sí", "on") if on else tx(lang, "выкл", "вимк", "no", "off")  # noqa: E731
    text = (tx(lang, "⚙️ <b>Настройки</b>\n\n", "⚙️ <b>Налаштування</b>\n\n",
                     "⚙️ <b>Ajustes</b>\n\n",
                     "⚙️ <b>Settings</b>\n\n") + "<blockquote>"
            + tx(lang, f"🌐 Язык: {LANGS[lang]}\n⏱ Проверка каждые <b>{minutes} мин</b>\n"
                       f"🏢 Офисов: до <b>{premium.limit_subs(chat)}</b>",
                 f"🌐 Мова: {LANGS[lang]}\n⏱ Перевірка кожні <b>{minutes} хв</b>\n"
                 f"🏢 Офісів: до <b>{premium.limit_subs(chat)}</b>",
                       f"🌐 Idioma: {LANGS[lang]}\n⏱ Revisión cada <b>{minutes} min</b>\n"
                       f"🏢 Oficinas: hasta <b>{premium.limit_subs(chat)}</b>",
                       f"🌐 Language: {LANGS[lang]}\n⏱ Check every <b>{minutes} min</b>\n"
                       f"🏢 Offices: up to <b>{premium.limit_subs(chat)}</b>") + "</blockquote>\n"
            + tx(lang, "🌙 <b>Тихий режим</b>: с 00:00 до 08:00 по Мадриду уведомления приходят без звука.",
                 "🌙 <b>Тихий режим</b>: з 00:00 до 08:00 за Мадридом сповіщення надходять без звуку.",
                       "🌙 <b>Modo silencio</b>: de 00:00 a 08:00, hora de Madrid, los avisos llegan sin sonido.",
                       "🌙 <b>Quiet mode</b>: from 00:00 to 08:00 Madrid time, alerts arrive without sound."))
    return text, ikb([
        [btn(f"{'🟢' if quiet else '⚪️'} " + tx(lang, "Тихий режим: ", "Тихий режим: ",
                                                     "Modo silencio: ",
                                                     "Quiet mode: ") + state(quiet), "q")],
        [btn(f"{'🟢' if ads else '⚪️'} " + tx(lang, "Предложения партнёров: ", "Пропозиції партнерів: ",
                                                   "Ofertas de socios: ",
                                                   "Partner offers: ") + state(ads), "adt")],
        [btn(tx(lang, "🌐 Язык", "🌐 Мова", "🌐 Idioma", "🌐 Language"), "lp"), btn(tx(lang, "🔒 Данные", "🔒 Дані", "🔒 Datos", "🔒 Data"), "pv")],
        [btn(tx(lang, "🗑 Удалить все подписки", "🗑 Видалити всі підписки",
                      "🗑 Quitar todas las oficinas",
                      "🗑 Remove all offices"), "xa", "danger")],
        [home_btn(lang)],
    ])


def help_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = tx(lang,
              "❓ <b>Как это работает</b>\n\n"
              "Я смотрю календарь DGT по твоему офису и типу записи. Как только появляются свободные дни, "
              "присылаю уведомление с датами и временем.\n\n"
              "🎨 <b>Цвета</b>\n<blockquote>🟢 много свободных мест\n🟡 занято 33–66%\n🔴 почти всё занято</blockquote>\n"
              "🧰 <b>Что умею</b>\n<blockquote>📡 Радар: ближайший офис, где запись раньше всего\n"
              "🛂 Сигналы от людей о записях на TIE, NIE и паспорт\n"
              "🗓 Календарь со свободным временем\n"
              "✅ «Я записался»: напомню о визите и подскажу, что взять\n"
              "📅 Только даты раньше нужной, ⏸ пауза, 📊 история\n"
              "🌙 Тихий режим ночью\n"
              "🎁 Бесплатный Premium за задания и друзей\n"
              "💼 Вакансии и объявления в канале</blockquote>\n"
              "💡 <b>Советы</b>\n<blockquote>Места быстро разбирают: открывай сайт сразу после уведомления\n"
              "Держи под рукой DNI/NIE: сайт спросит данные при записи</blockquote>\n"
              "<i>Записываешься ты сам, я только сообщаю о местах. Бот не связан с DGT.</i>",
              "❓ <b>Як це працює</b>\n\n"
              "Я дивлюся календар DGT за твоїм офісом і типом запису. Щойно з’являються вільні дні, "
              "надсилаю сповіщення з датами й часом.\n\n"
              "🎨 <b>Кольори</b>\n<blockquote>🟢 багато вільних місць\n🟡 зайнято 33–66%\n🔴 майже все зайнято</blockquote>\n"
              "🧰 <b>Що вмію</b>\n<blockquote>📡 Радар: найближчий офіс, де запис найшвидше\n"
              "🛂 Сигнали від людей про записи на TIE, NIE і паспорт\n"
              "🗓 Календар із вільним часом\n"
              "✅ «Я записався»: нагадаю про візит і підкажу, що взяти\n"
              "📅 Лише дати раніше потрібної, ⏸ пауза, 📊 історія\n"
              "🌙 Тихий режим уночі\n"
              "🎁 Безкоштовний Premium за завдання й друзів\n"
              "💼 Вакансії та оголошення в каналі</blockquote>\n"
              "💡 <b>Поради</b>\n<blockquote>Місця швидко розбирають: відкривай сайт одразу після сповіщення\n"
              "Тримай під рукою DNI/NIE: сайт спитає дані під час запису</blockquote>\n"
              "<i>Записуєшся ти сам, я лише повідомляю про місця. Бот не пов’язаний з DGT.</i>",
              "❓ <b>Cómo funciona</b>\n\n"
              "Miro el calendario de la DGT de tu oficina y tipo de cita. En cuanto aparecen días libres, "
              "te envío un aviso con las fechas y horas.\n\n"
              "🎨 <b>Colores</b>\n<blockquote>🟢 muchas plazas libres\n🟡 ocupado al 33–66 %\n🔴 casi todo ocupado</blockquote>\n"
              "🧰 <b>Qué sé hacer</b>\n<blockquote>📡 Radar: la oficina cercana con la cita más próxima\n"
              "🛂 Señales de otros usuarios sobre citas de TIE, NIE y pasaporte\n"
              "🗓 Calendario con horas libres\n"
              "✅ «Ya tengo cita»: te recuerdo la visita y qué llevar\n"
              "📅 Solo fechas anteriores a la que necesitas, ⏸ pausa, 📊 historial\n"
              "🌙 Modo silencio por la noche\n"
              "🎁 Premium gratis por tareas y amigos\n"
              "💼 Empleo y anuncios en el canal</blockquote>\n"
              "💡 <b>Consejos</b>\n<blockquote>Las plazas vuelan: abre la web nada más recibir el aviso\n"
              "Ten a mano tu DNI/NIE: la web te pedirá los datos al reservar</blockquote>\n"
              "<i>La cita la pides tú; yo solo aviso de las plazas. El bot no tiene relación con la DGT.</i>",
              "❓ <b>How it works</b>\n\n"
              "I watch the DGT calendar for your office and appointment type. As soon as free days appear, "
              "I send you an alert with the dates and times.\n\n"
              "🎨 <b>Colours</b>\n<blockquote>🟢 plenty of free slots\n🟡 33–66% taken\n🔴 almost full</blockquote>\n"
              "🧰 <b>What I can do</b>\n<blockquote>📡 Radar: the nearby office with the earliest appointment\n"
              "🛂 Signals from other users about TIE, NIE and passport appointments\n"
              "🗓 Calendar with free times\n"
              "✅ “I booked it”: I'll remind you of the visit and tell you what to bring\n"
              "📅 Only dates earlier than you need, ⏸ pause, 📊 history\n"
              "🌙 Quiet mode at night\n"
              "🎁 Free Premium for tasks and friends\n"
              "💼 Jobs and posts in the channel</blockquote>\n"
              "💡 <b>Tips</b>\n<blockquote>Slots go fast: open the site right after the alert\n"
              "Keep your DNI/NIE handy: the site asks for it when booking</blockquote>\n"
              "<i>You make the booking yourself; I only tell you about free slots. The bot is not affiliated with DGT.</i>")
    return text, ikb([[btn(tx(lang, "🇺🇦 Для украинцев", "🇺🇦 Для українців", "🇺🇦 Para ucranianos", "🇺🇦 For Ukrainians"), "ua"),
                       btn(tx(lang, "📄 Условия", "📄 Умови", "📄 Condiciones", "📄 Terms"), "tm")], [home_btn(lang)]])


# ---------- сигналы о документах ----------

def doc_name(lang: str, doc: str) -> str:
    return tx(lang, *signals.DOCS[doc][1:])


def doc_title(lang: str, doc: str) -> str:
    return f"{signals.DOCS[doc][0]} {doc_name(lang, doc)}"


def docs_view(chat: int, note: str = "") -> Tuple[str, dict]:
    lang = lang_of(chat)
    mine = signals.subs_of(chat)
    lines = [tx(lang, "🛂 <b>Документы</b> · сигналы от людей", "🛂 <b>Документи</b> · сигнали від людей",
                      "🛂 <b>Documentos</b> · señales de usuarios",
                      "🛂 <b>Documents</b> · signals from people"), "",
             tx(lang, "Записи на TIE, NIE, паспорт и в консульство закрыты от автоматических проверок, поэтому бот их не смотрит. "
                      "Места замечают сами пользователи: один увидел запись и нажал кнопку, остальные сразу получили сигнал.",
                "Записи на TIE, NIE, паспорт і в консульство закриті від автоматичних перевірок, тому бот їх не дивиться. "
                "Місця помічають самі користувачі: один побачив запис і натиснув кнопку, решта одразу отримали сигнал.",
                      "Las citas de TIE, NIE, pasaporte y consulado están cerradas a las revisiones automáticas, por eso el bot no las mira. "
                      "Las plazas las detectan los propios usuarios: uno ve una cita y pulsa el botón, y los demás reciben la señal al momento.",
                      "TIE, NIE, passport and consulate appointments are closed to automated checks, so the bot doesn't look at them. "
                      "Users spot the slots themselves: one person sees an appointment and taps the button, and everyone else gets a signal right away."), ""]
    if mine:
        items = []
        for province, doc in mine:
            hour = signals.best_hour(province, doc)
            items.append(f"{doc_title(lang, doc)} · <b>{esc(signals.PROVINCES[province])}</b>"
                         + (tx(lang, f"\n<i>чаще всего около {hour}:00</i>", f"\n<i>найчастіше близько {hour}:00</i>",
                                     f"\n<i>sobre todo hacia las {hour}:00</i>",
                                     f"\n<i>most often around {hour}:00</i>") if hour is not None else ""))
        lines.append(tx(lang, "🔔 <b>Мои сигналы</b> · ", "🔔 <b>Мої сигнали</b> · ",
                              "🔔 <b>Mis señales</b> · ",
                              "🔔 <b>My signals</b> · ") + f"{len(mine)}/{signals.limit(chat)}")
        lines.append("<blockquote>" + "\n".join(items) + "</blockquote>")
    lines.append(tx(lang, "<i>Сигналы присылают люди, бот их не проверяет. Запись бесплатна, никому не плати за неё.</i>",
                    "<i>Сигнали надсилають люди, бот їх не перевіряє. Запис безкоштовний, нікому за нього не плати.</i>",
                          "<i>Las señales las envían personas y el bot no las verifica. La cita es gratis: no pagues a nadie por ella.</i>",
                          "<i>Signals come from people and the bot doesn't verify them. Appointments are free: don't pay anyone for one.</i>"))
    if note:
        lines += ["", note]
    rows = [[btn(tx(lang, "🟢 Я вижу свободные места", "🟢 Я бачу вільні місця",
                          "🟢 Veo plazas libres",
                          "🟢 I see free slots"), "dp:r:0", "success")],
            [btn(tx(lang, "➕ Следить за записью", "➕ Стежити за записом",
                          "➕ Seguir una cita",
                          "➕ Track an appointment"), "dp:s:0", "primary")]]
    for province, doc in mine:
        rows.append([btn(f"🗑 {signals.DOCS[doc][0]} {signals.PROVINCES[province]}", f"dx:{province}:{doc}")])
    rows.append([btn(tx(lang, "📋 Как записаться на TIE", "📋 Як записатися на TIE", "📋 Cómo pedir cita TIE", "📋 How to book a TIE"), "dg"),
                 btn(tx(lang, "⏰ Окна проверки", "⏰ Вікна перевірки", "⏰ Ventanas", "⏰ Check windows"), "dw")])
    rows.append([url(tx(lang, "📝 Сайт записи Extranjería", "📝 Сайт запису Extranjería",
                              "📝 Web de citas de Extranjería",
                              "📝 Extranjería booking site"), signals.ICP_URL)])
    rows.append([btn(tx(lang, "🇺🇦 Для украинцев", "🇺🇦 Для українців",
                              "🇺🇦 Para ucranianos",
                              "🇺🇦 For Ukrainians"), "ua"), home_btn(lang)])
    return "\n".join(lines), ikb(rows)


def doc_provinces(chat: int, act: str, page: int = 0) -> Tuple[str, dict]:
    lang = lang_of(chat)
    ids = sorted(signals.PROVINCES, key=lambda c: fold(signals.PROVINCES[c]))
    pages = math.ceil(len(ids) / PAGE)
    page %= pages
    chunk = ids[page * PAGE:(page + 1) * PAGE]
    rows = [[btn(signals.PROVINCES[c], f"dt:{act}:{c}") for c in chunk[i:i + 2]] for i in range(0, len(chunk), 2)]
    rows.append([btn("◀️", f"dp:{act}:{page - 1}"), btn(f"{page + 1} / {pages}", "noop"), btn("▶️", f"dp:{act}:{page + 1}")])
    rows.append([btn(tx(lang, "⬅️ Документы", "⬅️ Документи", "⬅️ Documentos", "⬅️ Documents"), "dc"), home_btn(lang)])
    head = (tx(lang, "🟢 <b>Где ты видишь места?</b>", "🟢 <b>Де ти бачиш місця?</b>",
                     "🟢 <b>¿Dónde ves plazas?</b>",
                     "🟢 <b>Where do you see slots?</b>") if act == "r"
            else tx(lang, "➕ <b>Выбери провинцию</b>", "➕ <b>Обери провінцію</b>",
                          "➕ <b>Elige la provincia</b>",
                          "➕ <b>Choose a province</b>"))
    return head + tx(lang, " · шаг 1 из 2", " · крок 1 з 2", " · paso 1 de 2", " · step 1 of 2"), ikb(rows)


def doc_types(chat: int, act: str, province: str) -> Tuple[str, dict]:
    lang = lang_of(chat)
    rows = [[btn(doc_title(lang, doc), f"dd:{act}:{province}:{doc}")] for doc in signals.DOCS]
    rows.append([btn(tx(lang, "⬅️ Провинции", "⬅️ Провінції", "⬅️ Provincias", "⬅️ Provinces"), f"dp:{act}:0"), home_btn(lang)])
    return (f"📍 <b>{esc(signals.PROVINCES[province])}</b> · " + tx(lang, "шаг 2 из 2", "крок 2 з 2",
                                                                         "paso 2 de 2",
                                                                         "step 2 of 2") + "\n\n"
            + tx(lang, "Какой документ?", "Який документ?", "¿Qué documento?", "Which document?"), ikb(rows))


def doc_confirm(chat: int, province: str, doc: str) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, "🟢 <b>Ты сейчас видишь свободные места?</b>\n", "🟢 <b>Ти зараз бачиш вільні місця?</b>\n",
                     "🟢 <b>¿Ves plazas libres ahora mismo?</b>\n",
                     "🟢 <b>Do you see free slots right now?</b>\n")
            + f"{doc_title(lang, doc)} · <b>{esc(signals.PROVINCES[province])}</b>\n\n"
            + tx(lang, "Я сразу сообщу всем, кто их ждёт. Ложные сигналы отключают эту кнопку.",
                 "Я одразу повідомлю всіх, хто на них чекає. Хибні сигнали вимикають цю кнопку.",
                       "Avisaré enseguida a quienes las esperan. Las señales falsas desactivan este botón.",
                       "I'll tell everyone waiting right away. False signals disable this button."),
            ikb([[btn(tx(lang, "✅ Да, вижу", "✅ Так, бачу",
                               "✅ Sí, las veo",
                               "✅ Yes, I see them"), f"dr:{province}:{doc}", "success"),
                  btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), "dc")]]))


def signal_result(lang: str, status: str, sent: int = 0) -> str:
    return {
        "ok": tx(lang, f"✅ Спасибо! Сигнал получат: <b>{sent}</b>.", f"✅ Дякую! Сигнал отримають: <b>{sent}</b>.",
                       f"✅ ¡Gracias! Recibirán la señal: <b>{sent}</b>.",
                       f"✅ Thanks! People who'll get the signal: <b>{sent}</b>."),
        "merged": tx(lang, "✅ Спасибо! Об этом уже сообщили, твой голос учтён.", "✅ Дякую! Про це вже повідомили, твій голос враховано.",
                           "✅ ¡Gracias! Ya lo habían avisado y tu voto cuenta.",
                           "✅ Thanks! Someone already reported this, and your vote counts."),
        "daily": tx(lang, "⏳ На сегодня сигналов достаточно, спасибо!", "⏳ На сьогодні сигналів досить, дякую!",
                          "⏳ Por hoy ya hay suficientes señales, ¡gracias!",
                          "⏳ That's enough signals for today, thanks!"),
        "muted": tx(lang, "🔕 Твои сигналы часто не подтверждались, поэтому кнопка пока отключена.",
                    "🔕 Твої сигнали часто не підтверджувалися, тому кнопку поки вимкнено.",
                          "🔕 Tus señales no se han confirmado a menudo, así que el botón está desactivado por ahora.",
                          "🔕 Your signals were often not confirmed, so this button is disabled for now."),
    }.get(status, "")


def signal_alert(chat: int, sig: dict, voted: bool = False) -> Tuple[str, dict]:
    lang, province, doc = lang_of(chat), sig["province"], sig["doc"]
    text = (tx(lang, "🟢 <b>Сигнал о свободных местах</b>\n", "🟢 <b>Сигнал про вільні місця</b>\n",
                     "🟢 <b>Señal de plazas libres</b>\n",
                     "🟢 <b>Free slots signal</b>\n")
            + f"{doc_title(lang, doc)} · <b>{esc(signals.PROVINCES[province])}</b>\n\n"
            + tx(lang, "Пользователь только что увидел запись. Бот этого не проверял, места быстро исчезают.",
                 "Користувач щойно побачив запис. Бот цього не перевіряв, місця швидко зникають.",
                       "Un usuario acaba de ver una cita. El bot no lo ha comprobado y las plazas desaparecen rápido.",
                       "A user just saw an appointment. The bot hasn't verified this, and slots disappear fast."))
    rows = []
    if doc in signals.ICP_DOCS:
        rows.append([url(tx(lang, "📝 Открыть сайт записи", "📝 Відкрити сайт запису",
                                  "📝 Abrir la web de citas",
                                  "📝 Open the booking site"), signals.ICP_URL, "primary")])
    if not voted:
        rows.append([btn(tx(lang, "✅ Тоже вижу", "✅ Теж бачу", "✅ Yo también", "✅ I see it too"), f"dv:{sig['id']}:1", "success"),
                     btn(tx(lang, "❌ Уже нет", "❌ Вже немає", "❌ Ya no hay", "❌ Gone already"), f"dv:{sig['id']}:0")])
    rows.append([btn(tx(lang, "✖️ Скрыть", "✖️ Сховати", "✖️ Ocultar", "✖️ Hide"), "hide")])
    return text, ikb(rows)


def ukraine_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = tx(lang,
              "🇺🇦 <b>Для украинцев в Испании</b>\n\n"
              "🪪 <b>Украинские права</b>\n"
              "<blockquote>• Действуют в Испании, пока у тебя есть временная защита — сейчас до <b>4 марта 2027</b>.\n"
              "• Обмен на испанские (<b>canje</b>): теперь сначала заявка на сайте DGT с NIE, датой рождения и страной. "
              "Через несколько дней DGT сообщит результат, и только потом можно выбрать дату. "
              "Бот вводить личные данные не может, поэтому даты canje не отслеживает.\n"
              "• С TIE обмен можно делать сразу, с резолюцией о защите — через 6 месяцев после въезда или выдачи. "
              "Присяжный перевод не нужен.</blockquote>\n"
              "📄 <b>Временная защита и TIE</b>\n"
              "<blockquote>• Все TIE по временной защите продлены автоматически до 4 марта 2027 "
              "(Orden INT/96/2026) — никуда идти не нужно.\n"
              "• ЕС продлил временную защиту до <b>4 марта 2028</b> (решение 2026/1912). Срок TIE после 4 марта 2027 "
              "зависит от новой испанской нормы, следи за официальными сайтами.\n"
              "• Новая заявка: центры CREADE по телефону — Pozuelo (Madrid) +34 666 800 194, "
              "Málaga +34 628 216 478, Barcelona +34 93 238 21 99; в других провинциях — в полиции.\n"
              "• С августа 2026 для новой защиты нужно подтвердить исполнение воинской обязанности "
              "Украины или освобождение от неё.</blockquote>\n"
              "<i>Информация на октябрь 2026, перед визитом сверяйся с официальными сайтами.</i>",
              "🇺🇦 <b>Для українців в Іспанії</b>\n\n"
              "🪪 <b>Українські права</b>\n"
              "<blockquote>• Діють в Іспанії, поки в тебе є тимчасовий захист — зараз до <b>4 березня 2027</b>.\n"
              "• Обмін на іспанські (<b>canje</b>): тепер спершу заявка на сайті DGT з NIE, датою народження й країною. "
              "За кілька днів DGT повідомить результат, і лише потім можна обрати дату. "
              "Бот не може вводити особисті дані, тому дати canje не відстежує.\n"
              "• З TIE обмін можна робити одразу, з резолюцією про захист — через 6 місяців після в’їзду або видачі. "
              "Присяжний переклад не потрібен.</blockquote>\n"
              "📄 <b>Тимчасовий захист і TIE</b>\n"
              "<blockquote>• Усі TIE за тимчасовим захистом продовжено автоматично до 4 березня 2027 "
              "(Orden INT/96/2026) — нікуди йти не треба.\n"
              "• ЄС продовжив тимчасовий захист до <b>4 березня 2028</b> (рішення 2026/1912). Строк TIE після 4 березня 2027 "
              "залежить від нової іспанської норми, стеж за офіційними сайтами.\n"
              "• Нова заява: центри CREADE за телефоном — Pozuelo (Madrid) +34 666 800 194, "
              "Málaga +34 628 216 478, Barcelona +34 93 238 21 99; в інших провінціях — у поліції.\n"
              "• З серпня 2026 для нового захисту треба підтвердити виконання військового обов’язку "
              "України або звільнення від нього.</blockquote>\n"
              "<i>Інформація на жовтень 2026, перед візитом звіряйся з офіційними сайтами.</i>",
              "🇺🇦 <b>Para ucranianos en España</b>\n\n"
              "🪪 <b>Permisos de conducir ucranianos</b>\n"
              "<blockquote>• Son válidos en España mientras tengas protección temporal: ahora, hasta el <b>4 de marzo de 2027</b>.\n"
              "• Canje por el permiso español: ahora primero hay que presentar una solicitud en la web de la DGT con NIE, fecha de nacimiento y país. "
              "En unos días la DGT comunica el resultado y solo después se puede elegir fecha. "
              "El bot no puede introducir datos personales, por eso no sigue las fechas de canje.\n"
              "• Con TIE, el canje se puede hacer enseguida; con la resolución de protección, a los 6 meses de la entrada o de su concesión. "
              "No hace falta traducción jurada.</blockquote>\n"
              "📄 <b>Protección temporal y TIE</b>\n"
              "<blockquote>• Todas las TIE de protección temporal se han prorrogado automáticamente hasta el 4 de marzo de 2027 "
              "(Orden INT/96/2026): no hay que ir a ningún sitio.\n"
              "• La UE ha prorrogado la protección temporal hasta el <b>4 de marzo de 2028</b> (Decisión 2026/1912). La validez de la TIE después del 4 de marzo de 2027 "
              "depende de una nueva norma española: consulta las webs oficiales.\n"
              "• Nueva solicitud: centros CREADE por teléfono: Pozuelo (Madrid) +34 666 800 194, "
              "Málaga +34 628 216 478, Barcelona +34 93 238 21 99; en otras provincias, en la policía.\n"
              "• Desde agosto de 2026, para la nueva protección hay que acreditar el cumplimiento del servicio militar "
              "de Ucrania o la exención.</blockquote>\n"
              "<i>Información a octubre de 2026; antes de ir, compruébala en las webs oficiales.</i>",
              "🇺🇦 <b>For Ukrainians in Spain</b>\n\n"
              "🪪 <b>Ukrainian driving licences</b>\n"
              "<blockquote>• Valid in Spain while you hold temporary protection: currently until <b>4 March 2027</b>.\n"
              "• Exchange for a Spanish licence (<b>canje</b>): you now apply first on the DGT website with your NIE, date of birth and country. "
              "DGT replies within a few days, and only then can you choose a date. "
              "The bot can't enter personal data, so it doesn't track canje dates.\n"
              "• With a TIE you can exchange straight away; with the protection resolution, 6 months after entry or issue. "
              "No sworn translation is needed.</blockquote>\n"
              "📄 <b>Temporary protection and TIE</b>\n"
              "<blockquote>• All temporary protection TIE cards were automatically extended until 4 March 2027 "
              "(Orden INT/96/2026): you don't need to go anywhere.\n"
              "• The EU extended temporary protection until <b>4 March 2028</b> (Decision 2026/1912). TIE validity after 4 March 2027 "
              "depends on a new Spanish rule, so keep an eye on official websites.\n"
              "• New application: CREADE centres by phone: Pozuelo (Madrid) +34 666 800 194, "
              "Málaga +34 628 216 478, Barcelona +34 93 238 21 99; in other provinces, at the police.\n"
              "• Since August 2026, new protection requires proof that you met Ukrainian military service duties "
              "or are exempt.</blockquote>\n"
              "<i>Information as of October 2026; check official websites before your visit.</i>")
    return text, ikb([
        [btn(tx(lang, "🛂 Записи на TIE и документы", "🛂 Записи на TIE і документи",
                      "🛂 Citas de TIE y documentos",
                      "🛂 TIE appointments and documents"), "dc")],
        [url(tx(lang, "🪪 Canje прав — DGT", "🪪 Canje прав — DGT",
                      "🪪 Canje de permiso: DGT",
                      "🪪 Licence canje: DGT"), UA_CANJE), url("🌐 Ucrania Urgente", UA_GUIDE)],
        [home_btn(lang)],
    ])


def privacy_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = tx(lang,
              "🔒 <b>Конфиденциальность</b>\n\n"
              "<b>Что я храню</b>\n<blockquote>• Telegram ID, имя и @username\n• язык и настройки\n"
              "• подписки: офис, тип записи, фильтр дат и дату визита, если ты её указал\n"
              "• тариф, оплаты, приглашения и выполненные задания\n• твои объявления для канала\n"
              "• согласие на предложения партнёров</blockquote>\n"
              "<b>Зачем</b> — чтобы присылать уведомления и напоминания и вести твой тариф. "
              "Данные не продаются и не передаются третьим лицам.\n"
              "<b>Где</b> — база данных в ЕС (Франкфурт), сам бот работает на сервере в США (Орегон).\n\n"
              "Бот не связан с DGT и не записывает тебя сам — запись делаешь ты на официальном сайте.\n\n"
              "Удалить свои данные можно кнопкой ниже. Записи об оплатах хранятся столько, сколько требует закон. "
              "От бонусов и промокодов остаётся только хеш, без имени и открытого ID: он нужен, чтобы их нельзя было получить повторно.",
              "🔒 <b>Конфіденційність</b>\n\n"
              "<b>Що я зберігаю</b>\n<blockquote>• Telegram ID, ім’я та @username\n• мову й налаштування\n"
              "• підписки: офіс, тип запису, фільтр дат і дату візиту, якщо ти її вказав\n"
              "• тариф, оплати, запрошення й виконані завдання\n• твої оголошення для каналу\n"
              "• згоду на пропозиції партнерів</blockquote>\n"
              "<b>Навіщо</b> — щоб надсилати сповіщення й нагадування та вести твій тариф. "
              "Дані не продаються і не передаються третім особам.\n"
              "<b>Де</b> — база даних у ЄС (Франкфурт), сам бот працює на сервері в США (Орегон).\n\n"
              "Бот не пов’язаний з DGT і не записує тебе сам — запис робиш ти на офіційному сайті.\n\n"
              "Видалити свої дані можна кнопкою нижче. Записи про оплати зберігаються стільки, скільки вимагає закон. "
              "Від бонусів і промокодів лишається тільки хеш, без імені й відкритого ID: він потрібен, щоб їх не можна було отримати повторно.",
              "🔒 <b>Privacidad</b>\n\n"
              "<b>Qué guardo</b>\n<blockquote>• ID de Telegram, nombre y @usuario\n• idioma y ajustes\n"
              "• oficinas seguidas: oficina, tipo de cita, filtro de fechas y fecha de la visita, si la has indicado\n"
              "• plan, pagos, invitaciones y tareas completadas\n• tus anuncios para el canal\n"
              "• consentimiento para ofertas de socios</blockquote>\n"
              "<b>Para qué</b>: para enviarte avisos y recordatorios y gestionar tu plan. "
              "Los datos no se venden ni se ceden a terceros.\n"
              "<b>Dónde</b>: la base de datos está en la UE (Fráncfort) y el bot funciona en un servidor en EE. UU. (Oregón).\n\n"
              "El bot no tiene relación con la DGT y no pide citas por ti: la cita la pides tú en la web oficial.\n\n"
              "Puedes borrar tus datos con el botón de abajo. Los registros de pagos se conservan el tiempo que exige la ley. "
              "De bonos y códigos promocionales solo queda un hash, sin nombre ni ID visible: sirve para que no se puedan obtener dos veces.",
              "🔒 <b>Privacy</b>\n\n"
              "<b>What I store</b>\n<blockquote>• Telegram ID, name and @username\n• language and settings\n"
              "• tracked offices: office, appointment type, date filter and visit date, if you gave one\n"
              "• plan, payments, invitations and completed tasks\n• your channel posts\n"
              "• consent to partner offers</blockquote>\n"
              "<b>Why</b>: to send you alerts and reminders and manage your plan. "
              "Data is not sold or shared with third parties.\n"
              "<b>Where</b>: the database is in the EU (Frankfurt) and the bot runs on a server in the USA (Oregon).\n\n"
              "The bot is not affiliated with DGT and doesn't book for you: you book on the official website.\n\n"
              "You can delete your data with the button below. Payment records are kept for as long as the law requires. "
              "For bonuses and promo codes only a hash remains, with no name or readable ID: it prevents claiming them twice.")
    return text, ikb([[btn(tx(lang, "🗑 Удалить мои данные", "🗑 Видалити мої дані",
                                    "🗑 Borrar mis datos",
                                    "🗑 Delete my data"), "dm")],
                      [btn(tx(lang, "⬅️ Настройки", "⬅️ Налаштування", "⬅️ Ajustes", "⬅️ Settings"), "st"), home_btn(lang)]])


def delete_me_confirm(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, "🗑 <b>Удалить все мои данные?</b>\nПодписки, настройки и история пропадут. Отменить нельзя.",
               "🗑 <b>Видалити всі мої дані?</b>\nПідписки, налаштування й історія зникнуть. Скасувати не можна.",
                     "🗑 <b>¿Borrar todos mis datos?</b>\nSe perderán las oficinas, los ajustes y el historial. No se puede deshacer.",
                     "🗑 <b>Delete all my data?</b>\nOffices, settings and history will be lost. This can't be undone."),
            ikb([[btn(tx(lang, "Да, удалить", "Так, видалити",
                               "Sí, quitar",
                               "Yes, delete"), "dm!"), btn(tx(lang, "Отмена", "Скасувати",
                                                                                     "Cancelar",
                                                                                     "Cancel"), "pv")]]))


def deleted_text(lang: str) -> str:
    return tx(lang, "✅ Твои данные удалены. Если захочешь вернуться — нажми /start.",
              "✅ Твої дані видалено. Якщо захочеш повернутися — натисни /start.",
                    "✅ Tus datos se han borrado. Si quieres volver, pulsa /start.",
                    "✅ Your data has been deleted. If you want to come back, tap /start.")


def maintenance_view(lang: str) -> Tuple[str, dict]:
    return (f"{BRAND_LINE}\n\n" + tx(lang, "🛠 <b>Технические работы</b>\n\nСейчас бот не проверяет даты. "
                                           "Твои подписки сохранены, вернусь, как только закончу.",
                                     "🛠 <b>Технічні роботи</b>\n\nЗараз бот не перевіряє дати. "
                                     "Твої підписки збережено, повернуся, щойно закінчу.",
                                           "🛠 <b>Mantenimiento</b>\n\nAhora mismo el bot no revisa fechas. "
                                           "Tus oficinas siguen guardadas; volveré en cuanto termine.",
                                           "🛠 <b>Maintenance</b>\n\nThe bot isn't checking dates right now. "
                                           "Your offices are saved, and I'll be back as soon as I'm done."), ikb([]))


def pending_view(lang: str) -> Tuple[str, dict]:
    return (f"{BRAND_LINE}\n\n" + tx(lang, "⏳ <b>Заявка на доступ отправлена</b>\nБот сейчас работает по приглашениям. "
                                           "Как только администратор одобрит заявку — я напишу.",
                                     "⏳ <b>Заявку на доступ надіслано</b>\nБот зараз працює за запрошеннями. "
                                     "Щойно адміністратор схвалить заявку — я напишу.",
                                           "⏳ <b>Solicitud de acceso enviada</b>\nAhora el bot funciona por invitación. "
                                           "Te escribiré en cuanto el administrador la apruebe.",
                                           "⏳ <b>Access request sent</b>\nThe bot is invite-only right now. "
                                           "I'll message you as soon as the administrator approves it."), ikb([]))


def banned_view(lang: str) -> Tuple[str, dict]:
    return f"{BRAND_LINE}\n\n" + tx(lang, "🚫 Доступ к боту закрыт.", "🚫 Доступ до бота закрито.",
                                          "🚫 El acceso al bot está cerrado.",
                                          "🚫 Access to the bot is closed."), ikb([])


# ---------- Premium ----------

def plan_buttons(chat: int, lang: str) -> list:
    month, quarter = premium.plan_price("p30"), premium.plan_price("p90")
    saving = round((1 - quarter / (3 * month)) * 100) if month else 0
    labels = {"p30": tx(lang, "месяц · автопродление", "місяць · автопродовження",
                              "mes · renovación automática",
                              "month · auto-renewal"), "p7": tx(lang, "неделя", "тиждень",
                                                                                                   "semana",
                                                                                                   "week"),
              "p90": tx(lang, "3 месяца", "3 місяці", "3 meses", "3 months") + (f" · −{saving}%" if saving > 0 else "")}
    rows = []
    for plan in ("p30", "p7", "p90"):
        link = premium.invoice_link(plan, lang)
        if link:
            rows.append([url(f"⭐️ {premium.plan_price(plan)} · {labels[plan]}", link, "success" if plan == "p30" else None)])
    return rows


def premium_view(chat: int, note: str = "") -> Tuple[str, dict]:
    lang = lang_of(chat)
    c = store.get_chat(chat)
    paid = premium.is_premium(chat)
    free, top = store.setting("free_subs"), store.setting("max_subs")
    slow, fast = store.setting("interval"), store.setting("interval_premium")
    per_day = max(1, round(premium.plan_price("p30") / 30))
    lines = ["💎 <b>OkSita Premium</b>"]
    if paid:
        until = c.get("premium_until") or 0
        if until > time.time():
            days_left = max(1, math.ceil((until - time.time()) / 86400))
            lines.append(tx(lang, "✅ Активен до ", "✅ Активний до ",
                                  "✅ Activo hasta el ",
                                  "✅ Active until ") + f"<b>{datetime.fromtimestamp(until, config.TZ):%d.%m.%Y}</b>"
                         + f" · {days_word(lang, days_left)}")
            if c.get("sub_active"):
                lines.append(tx(lang, "🔁 Автопродление включено", "🔁 Автопродовження увімкнено",
                                      "🔁 Renovación automática activada",
                                      "🔁 Auto-renewal is on"))
        else:
            lines.append(tx(lang, "✅ Активен без срока", "✅ Активний без терміну",
                                  "✅ Activo sin fecha de fin",
                                  "✅ Active with no end date"))
    else:
        lines.append(tx(lang, f"Около {per_day} ⭐ в день — дешевле чашки кофе ☕️",
                        f"Близько {per_day} ⭐ на день — дешевше за чашку кави ☕️",
                              f"Unas {per_day} ⭐ al día: menos que un café ☕️",
                              f"About {per_day} ⭐ a day: less than a cup of coffee ☕️"))
    lines += ["", tx(lang, "<b>Бесплатно → Premium</b>", "<b>Безкоштовно → Premium</b>",
                           "<b>Gratis → Premium</b>",
                           "<b>Free → Premium</b>")]
    lines.append("<blockquote>" + tx(
        lang,
        f"🏢 Офисов: {free} → <b>{top}</b>\n"
        f"⚡️ Проверка: {slow} → <b>{fast} мин</b>\n"
        "📡 Радар: 1 в день → <b>без лимита</b>\n"
        "📏 Радиус радара: 100 → <b>250 км</b>\n"
        f"🛂 Сигналы о документах: {signals.FREE_SUBS} → <b>{signals.TOP_SUBS}</b>\n"
        "🚀 Очередь проверок: <b>первым</b>\n"
        "📱 Мини-приложение: <b>есть</b>\n"
        "🔕 Реклама: <b>нет</b>",
        f"🏢 Офісів: {free} → <b>{top}</b>\n"
        f"⚡️ Перевірка: {slow} → <b>{fast} хв</b>\n"
        "📡 Радар: 1 на день → <b>без ліміту</b>\n"
        "📏 Радіус радара: 100 → <b>250 км</b>\n"
        f"🛂 Сигнали про документи: {signals.FREE_SUBS} → <b>{signals.TOP_SUBS}</b>\n"
        "🚀 Черга перевірок: <b>першим</b>\n"
        "📱 Міні-застосунок: <b>є</b>\n"
        "🔕 Реклама: <b>немає</b>",
        f"🏢 Oficinas: {free} → <b>{top}</b>\n"
        f"⚡️ Revisión: {slow} → <b>{fast} min</b>\n"
        "📡 Radar: 1 al día → <b>sin límite</b>\n"
        "📏 Alcance del radar: 100 → <b>250 km</b>\n"
        f"🛂 Señales de documentos: {signals.FREE_SUBS} → <b>{signals.TOP_SUBS}</b>\n"
        "🚀 Cola de revisiones: <b>primero</b>\n"
        "📱 Miniapp: <b>sí</b>\n"
        "🔕 Publicidad: <b>no</b>",
        f"🏢 Offices: {free} → <b>{top}</b>\n"
        f"⚡️ Checks: {slow} → <b>{fast} min</b>\n"
        "📡 Radar: 1 a day → <b>unlimited</b>\n"
        "📏 Radar range: 100 → <b>250 km</b>\n"
        f"🛂 Document signals: {signals.FREE_SUBS} → <b>{signals.TOP_SUBS}</b>\n"
        "🚀 Check queue: <b>first</b>\n"
        "📱 Mini app: <b>yes</b>\n"
        "🔕 Ads: <b>none</b>") + "</blockquote>")
    state = premium.guarantee_state(chat)
    if state == "wait" or (not paid and not c.get("paid_at")):
        lines.append(guarantee_note(lang))
    if outage():
        lines.append(tx(lang, "🛠 Идут технические работы, поэтому оплата временно закрыта. Бонусы и промокоды работают.",
                        "🛠 Тривають технічні роботи, тому оплату тимчасово закрито. Бонуси й промокоди працюють.",
                              "🛠 Estamos en mantenimiento y los pagos están cerrados temporalmente. Los bonos y códigos funcionan.",
                              "🛠 Maintenance in progress, so payments are temporarily closed. Bonuses and promo codes still work."))
    else:
        lines.append(tx(lang, "<i>Оплата звёздами Telegram. Premium ускоряет уведомления, но не гарантирует запись.</i>",
                        "<i>Оплата зірками Telegram. Premium пришвидшує сповіщення, але не гарантує запис.</i>",
                              "<i>Pago con estrellas de Telegram. Premium agiliza los avisos, pero no garantiza una cita.</i>",
                              "<i>Paid with Telegram Stars. Premium speeds up alerts but doesn't guarantee an appointment.</i>"))
    if note:
        lines += ["", note]
    rows = [] if outage() else plan_buttons(chat, lang)
    if premium.can_trial(chat):
        rows.insert(0, [trial_btn(lang)])
    if state == "ready":
        rows.append([btn(tx(lang, "🛡 Вернуть звёзды по гарантии", "🛡 Повернути зірки за гарантією", "🛡 Devolver estrellas (garantía)", "🛡 Refund Stars (guarantee)"), "gr")])
    if paid and premium.app_url():
        rows.append([webapp(tx(lang, "📱 Открыть приложение", "📱 Відкрити застосунок",
                                     "📱 Abrir la miniapp",
                                     "📱 Open the mini app"), premium.app_url(), "primary")])
    if c.get("sub_active"):
        rows.append([btn(tx(lang, "🚫 Отключить автопродление", "🚫 Вимкнути автопродовження",
                                  "🚫 Desactivar la renovación",
                                  "🚫 Turn off auto-renewal"), "pc")])
    rows.append([btn(tx(lang, "🎁 Получить бесплатно", "🎁 Отримати безкоштовно", "🎁 Conseguir gratis", "🎁 Get it free"), "bn"),
                 btn(tx(lang, "🎟 Промокод", "🎟 Промокод", "🎟 Código promocional", "🎟 Promo code"), "pm")])
    rows.append([btn(tx(lang, "📄 Условия", "📄 Умови", "📄 Condiciones", "📄 Terms"), "tm"), home_btn(lang)])
    return "\n".join(lines), ikb(rows)


def premium_notice(chat: int, kind: str, until: int, paused: int = 0) -> Tuple[str, dict]:
    lang = lang_of(chat)
    trial = premium.after_trial(chat)
    if trial and kind == "soon":
        text = tx(lang, f"🎁 Пробный период закончится {datetime.fromtimestamp(until, config.TZ):%d.%m в %H:%M}. Продли Premium, чтобы офисы не встали на паузу.",
                  f"🎁 Пробний період закінчиться {datetime.fromtimestamp(until, config.TZ):%d.%m о %H:%M}. Продовж Premium, щоб офіси не стали на паузу.",
                  f"🎁 La prueba termina el {datetime.fromtimestamp(until, config.TZ):%d.%m a las %H:%M}. Amplía Premium para que tus oficinas no se pausen.",
                  f"🎁 Your trial ends on {datetime.fromtimestamp(until, config.TZ):%d.%m at %H:%M}. Extend Premium so your offices don't pause.")
    elif trial:
        text = tx(lang, f"🎁 <b>Пробный период закончился.</b>\nНеделя Premium стоит {premium.plan_price('p7')} ⭐, а бесплатно его можно получить в «🎁 Бонусах».",
                  f"🎁 <b>Пробний період закінчився.</b>\nТиждень Premium коштує {premium.plan_price('p7')} ⭐, а безкоштовно його можна отримати в «🎁 Бонусах».",
                  f"🎁 <b>La prueba ha terminado.</b>\nUna semana de Premium cuesta {premium.plan_price('p7')} ⭐, y gratis puedes conseguirlo en «🎁 Bonos».",
                  f"🎁 <b>Your trial has ended.</b>\nA week of Premium costs {premium.plan_price('p7')} ⭐, or get it free in “🎁 Bonuses”.")
        if paused:
            text += tx(lang, f"\nОфисов на паузе: {paused}.", f"\nОфісів на паузі: {paused}.", f"\nOficinas en pausa: {paused}.", f"\nOffices paused: {paused}.")
    elif kind == "soon":
        text = tx(lang, f"💎 Premium закончится {datetime.fromtimestamp(until, config.TZ):%d.%m в %H:%M}. "
                        "Продли или получи бесплатно в «🎁 Бонусах».",
                  f"💎 Premium закінчиться {datetime.fromtimestamp(until, config.TZ):%d.%m о %H:%M}. "
                  "Продовж або отримай безкоштовно в «🎁 Бонусах».",
                        f"💎 Premium termina el {datetime.fromtimestamp(until, config.TZ):%d.%m a las %H:%M}. "
                        "Renuévalo o consíguelo gratis en «🎁 Bonos».",
                        f"💎 Premium ends on {datetime.fromtimestamp(until, config.TZ):%d.%m at %H:%M}. "
                        "Renew it or get it free in “🎁 Bonuses”.")
    else:
        text = tx(lang, "💎 <b>Premium закончился.</b>", "💎 <b>Premium закінчився.</b>",
                        "💎 <b>Premium ha terminado.</b>",
                        "💎 <b>Premium has ended.</b>")
        if paused:
            text += tx(lang, f"\nОфисов на паузе: {paused}. Включить их снова можно с Premium или освободив место.",
                       f"\nОфісів на паузі: {paused}. Увімкнути їх знову можна з Premium або звільнивши місце.",
                             f"\nOficinas en pausa: {paused}. Puedes reactivarlas con Premium o liberando plazas.",
                             f"\nOffices paused: {paused}. You can turn them back on with Premium or by freeing up a spot.")
    return text, ikb([[btn("💎 Premium", "pr", "success"), btn(tx(lang, "🎁 Бонусы", "🎁 Бонуси", "🎁 Bonos", "🎁 Bonuses"), "bn")],
                      [btn(tx(lang, "✖️ Скрыть", "✖️ Сховати", "✖️ Ocultar", "✖️ Hide"), "hide")]])


def limit_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    limit = premium.limit_subs(chat)
    if premium.is_premium(chat):
        return (tx(lang, f"😅 Максимум — {limit} офисов. Удали ненужный и добавь новый.",
                   f"😅 Максимум — {limit} офісів. Видали непотрібний і додай новий.",
                         f"😅 El máximo son {limit} oficinas. Quita una que no necesites y añade la nueva.",
                         f"😅 The maximum is {limit} offices. Remove one you don't need and add the new one."),
                ikb([[btn(tx(lang, "📋 Мои офисы", "📋 Мої офіси", "📋 Mis oficinas", "📋 My offices"), "l"), home_btn(lang)]]))
    return (tx(lang, f"🔒 На бесплатном тарифе — {limit} офиса.\n\n"
                     f"💎 С Premium до {store.setting('max_subs')} офисов и проверка чаще. "
                     "Premium можно получить бесплатно — за задания и друзей.",
               f"🔒 На безкоштовному тарифі — {limit} офіси.\n\n"
               f"💎 З Premium до {store.setting('max_subs')} офісів і перевірка частіше. "
               "Premium можна отримати безкоштовно — за завдання й друзів.",
                     f"🔒 El plan gratis incluye {limit} oficinas.\n\n"
                     f"💎 Con Premium, hasta {store.setting('max_subs')} oficinas y revisiones más frecuentes. "
                     "Premium se puede conseguir gratis con tareas y amigos.",
                     f"🔒 The free plan includes {limit} offices.\n\n"
                     f"💎 Premium gives you up to {store.setting('max_subs')} offices and more frequent checks. "
                     "You can get Premium free through tasks and friends."),
            ikb([[btn("💎 Premium", "pr", "success"), btn(tx(lang, "🎁 Бонусы", "🎁 Бонуси", "🎁 Bonos", "🎁 Bonuses"), "bn")],
                 [btn(tx(lang, "📋 Мои офисы", "📋 Мої офіси", "📋 Mis oficinas", "📋 My offices"), "l"), home_btn(lang)]]))


def app_locked(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, "📱 <b>Мини-приложение</b> — только для Premium.", "📱 <b>Міні-застосунок</b> — лише для Premium.",
                     "📱 <b>La miniapp</b> es solo para Premium.",
                     "📱 <b>The mini app</b> is for Premium only."),
            ikb(([[trial_btn(lang)]] if premium.can_trial(chat) else []) + [[btn("💎 Premium", "pr", "success"), home_btn(lang)]]))


def thanks_text(lang: str, plan: str, until: int) -> str:
    return tx(lang, f"🎉 <b>Спасибо!</b> Premium активен до {datetime.fromtimestamp(until, config.TZ):%d.%m.%Y}.",
              f"🎉 <b>Дякуємо!</b> Premium активний до {datetime.fromtimestamp(until, config.TZ):%d.%m.%Y}.",
                    f"🎉 <b>¡Gracias!</b> Premium activo hasta el {datetime.fromtimestamp(until, config.TZ):%d.%m.%Y}.",
                    f"🎉 <b>Thank you!</b> Premium is active until {datetime.fromtimestamp(until, config.TZ):%d.%m.%Y}.")


def terms_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = tx(lang,
              "📄 <b>Условия</b>\n\n"
              "<blockquote>• OkSita — независимый сервис, не связан с DGT и не продаёт записи.\n"
              "• Бот только уведомляет о свободных датах. Записываешься ты сам на официальном сайте.\n"
              "• Запись через сайт DGT бесплатна. Premium — плата за удобство бота: больше офисов и более частые проверки.\n"
              "• Мы не гарантируем, что запись появится, и не отвечаем за сбои сайта DGT.\n"
              "• Подписка на 30 дней продлевается автоматически, отключить можно в любой момент в «💎 Premium».\n"
              "• Цифровая услуга начинается сразу после оплаты.\n"
              "• Гарантия: если за 7 дней после первой оплаты Premium не будет ни одного уведомления, звёзды можно вернуть один раз.\n"
              "• Объявления в канале публикуются после проверки. Если отказываем, звёзды возвращаем. Продажа записей запрещена.</blockquote>\n"
              "Вопросы по оплате: /paysupport",
              "📄 <b>Умови</b>\n\n"
              "<blockquote>• OkSita — незалежний сервіс, не пов’язаний з DGT і не продає записи.\n"
              "• Бот лише сповіщає про вільні дати. Записуєшся ти сам на офіційному сайті.\n"
              "• Запис через сайт DGT безкоштовний. Premium — плата за зручність бота: більше офісів і частіші перевірки.\n"
              "• Ми не гарантуємо, що запис з’явиться, і не відповідаємо за збої сайту DGT.\n"
              "• Підписка на 30 днів продовжується автоматично, вимкнути можна будь-коли в «💎 Premium».\n"
              "• Цифрова послуга починається одразу після оплати.\n"
              "• Гарантія: якщо за 7 днів після першої оплати Premium не буде жодного сповіщення, зірки можна повернути один раз.\n"
              "• Оголошення в каналі публікуються після перевірки. Якщо відмовляємо, зірки повертаємо. Продаж записів заборонено.</blockquote>\n"
              "Питання щодо оплати: /paysupport",
              "📄 <b>Condiciones</b>\n\n"
              "<blockquote>• OkSita es un servicio independiente, no tiene relación con la DGT y no vende citas.\n"
              "• El bot solo avisa de fechas libres. La cita la pides tú en la web oficial.\n"
              "• Pedir cita en la web de la DGT es gratis. Premium paga la comodidad del bot: más oficinas y revisiones más frecuentes.\n"
              "• No garantizamos que aparezca una cita ni respondemos de los fallos de la web de la DGT.\n"
              "• La suscripción de 30 días se renueva automáticamente; puedes cancelarla cuando quieras en «💎 Premium».\n"
              "• El servicio digital empieza justo después del pago.\n"
              "• Garantía: si en 7 días desde el primer pago de Premium no llega ningún aviso, puedes recuperar las estrellas una vez.\n"
              "• Los anuncios del canal se publican tras la revisión. Si los rechazamos, devolvemos las estrellas. Se prohíbe vender citas.</blockquote>\n"
              "Dudas sobre pagos: /paysupport",
              "📄 <b>Terms</b>\n\n"
              "<blockquote>• OkSita is an independent service, not affiliated with DGT, and it doesn't sell appointments.\n"
              "• The bot only alerts you about free dates. You book yourself on the official website.\n"
              "• Booking on the DGT website is free. Premium pays for the bot's convenience: more offices and more frequent checks.\n"
              "• We don't guarantee an appointment will appear and aren't responsible for DGT website outages.\n"
              "• The 30-day subscription renews automatically; you can turn it off anytime in “💎 Premium”.\n"
              "• The digital service starts right after payment.\n"
              "• Guarantee: if there isn't a single alert within 7 days of your first Premium payment, you can get your Stars back once.\n"
              "• Channel posts are published after review. If we reject one, we refund the Stars. Selling appointments is banned.</blockquote>\n"
              "Payment questions: /paysupport")
    return text, ikb([[btn("💎 Premium", "pr"), home_btn(lang)]])


def paysupport_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, "💳 <b>Поддержка по оплате</b>\n\nОпиши проблему одним сообщением: что купил и что пошло не так. "
                     "Я передам администратору, он ответит здесь же.",
               "💳 <b>Підтримка щодо оплати</b>\n\nОпиши проблему одним повідомленням: що купив і що пішло не так. "
               "Я передам адміністратору, він відповість тут же.",
                     "💳 <b>Ayuda con pagos</b>\n\nDescribe el problema en un solo mensaje: qué compraste y qué ha fallado. "
                     "Se lo pasaré al administrador, que te responderá aquí.",
                     "💳 <b>Payment support</b>\n\nDescribe the problem in one message: what you bought and what went wrong. "
                     "I'll pass it to the administrator, who will reply here."),
            ikb([[btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), "home")]]))


# ---------- бонусы ----------

def bonus_view(chat: int, note: str = "") -> Tuple[str, dict]:
    lang = lang_of(chat)
    friends = store.friends_of(chat)
    counted = sum(1 for f in friends if f.get("ref_done_at"))
    lines = [tx(lang, "🎁 <b>Бонусы</b>\nPremium бесплатно — за друзей и задания",
                "🎁 <b>Бонуси</b>\nPremium безкоштовно — за друзів і завдання",
                      "🎁 <b>Bonos</b>\nPremium gratis por amigos y tareas",
                      "🎁 <b>Bonuses</b>\nFree Premium for friends and tasks"), ""]
    lines.append(tx(lang, "👥 <b>Пригласи друга</b>", "👥 <b>Запроси друга</b>",
                          "👥 <b>Invita a un amigo</b>",
                          "👥 <b>Invite a friend</b>"))
    deal = ref_deal(lang)
    lines.append("<blockquote>" + deal + "\n"
                 + tx(lang, f"Приглашено: <b>{len(friends)}</b> · засчитано: <b>{counted}</b>",
                      f"Запрошено: <b>{len(friends)}</b> · зараховано: <b>{counted}</b>",
                            f"Invitados: <b>{len(friends)}</b> · contados: <b>{counted}</b>",
                            f"Invited: <b>{len(friends)}</b> · counted: <b>{counted}</b>") + "</blockquote>")
    items, rows = [], []
    finished = 0
    for key, (*names, hours) in rewards.BUILTIN.items():
        done = store.task_is_done(key, chat)
        finished += done
        items.append(f"{'✅' if done else '▫️'} {esc(tx(lang, *names))} · <b>+{hours_text(lang, hours)}</b>")
        if key == "b:ads" and not done:
            rows.append([btn(tx(lang, "📣 Включить предложения партнёров", "📣 Увімкнути пропозиції партнерів",
                                      "📣 Activar ofertas de socios",
                                      "📣 Turn on partner offers"), "adt:b")])
    for t in store.tasks(active_only=True):
        done = store.task_is_done(f"t:{t['id']}", chat)
        finished += done
        task = esc(task_title(lang, t))
        items.append(f"{'✅' if done else '▫️'} {task} · <b>+{hours_text(lang, t['hours'])}</b>")
        if not done:
            rows.append([url(f"➡️ {task_title(lang, t)[:40]}", rewards.task_url(t, chat)),
                         btn(tx(lang, "✅ Проверить", "✅ Перевірити", "✅ Comprobar", "✅ Check"), f"tc:{t['id']}", "success")])
    lines.append(tx(lang, "📝 <b>Задания</b> ", "📝 <b>Завдання</b> ",
                          "📝 <b>Tareas</b> ",
                          "📝 <b>Tasks</b> ") + progress(finished, len(items)))
    lines.append("<blockquote>" + "\n".join(items) + "</blockquote>")
    if note:
        lines += ["", note]
    pending = rewards.pending_friends(chat)
    head = []
    if pending:
        head.append([btn(tx(lang, f"🎁 Забрать за друзей · {len(pending)}", f"🎁 Забрати за друзів · {len(pending)}",
                                  f"🎁 Recoger por amigos · {len(pending)}",
                                  f"🎁 Collect for friends · {len(pending)}"), "bc", "success")])
    head.append([url(tx(lang, "📤 Пригласить", "📤 Запросити", "📤 Invitar", "📤 Invite"), rewards.share_link(chat, invite_text(lang)), "primary"),
                 copy(tx(lang, "🔗 Копировать", "🔗 Копіювати", "🔗 Copiar", "🔗 Copy"), rewards.ref_link(chat))])
    return "\n".join(lines), ikb(head + rows + [[btn(tx(lang, "🎟 Промокод", "🎟 Промокод",
                                                              "🎟 Código promocional",
                                                              "🎟 Promo code"), "pm"), btn("💎 Premium", "pr")],
                                                 [home_btn(lang)]])


def ref_deal(lang: str) -> str:
    """Условия награды за друга."""
    ref = store.setting("ref_hours")
    req = rewards.required_task()
    deal = tx(lang, f"+{hours_text(lang, ref)} Premium тебе и другу, когда он добавит офис",
              f"+{hours_text(lang, ref)} Premium тобі й другові, коли він додасть офіс",
              f"+{hours_text(lang, ref)} de Premium para ti y tu amigo cuando añada una oficina",
              f"+{hours_text(lang, ref)} of Premium for you and your friend when they add an office")
    if req:
        channel = esc(task_title(lang, req))
        deal += tx(lang, f" и вы оба подпишетесь: {channel}", f" і ви обидва підпишетеся: {channel}",
                   f" y os suscribáis los dos: {channel}", f" and you both subscribe: {channel}")
    return deal


def invite_text(lang: str) -> str:
    return tx(lang, "Ловлю свободные даты DGT с этим ботом — попробуй:", "Ловлю вільні дати DGT із цим ботом — спробуй:",
              "Pillo fechas libres de la DGT con este bot, pruébalo:", "I catch free DGT dates with this bot, give it a try:")


def reward_text(lang: str, hours: int) -> str:
    return tx(lang, f"🎉 +{hours_text(lang, hours)} Premium!", f"🎉 +{hours_text(lang, hours)} Premium!",
              f"🎉 +{hours_text(lang, hours)} de Premium.", f"🎉 +{hours_text(lang, hours)} of Premium!")


def collect_text(lang: str, status: str, count: int) -> str:
    """Итог «забрать награду за друзей»."""
    if status == "channel":
        task = rewards.required_task()
        title = task_title(lang, task) if task else ""
        return tx(lang, f"Сначала подпишись: {title}", f"Спочатку підпишись: {title}",
                  f"Primero suscríbete: {title}", f"Subscribe first: {title}")
    if status == "ok":
        return reward_text(lang, int(store.setting("ref_hours")) * count)
    return tx(lang, "Лимит наград за друзей на этот месяц исчерпан.", "Ліміт нагород за друзів на цей місяць вичерпано.",
              "Se ha alcanzado el límite de premios por amigos de este mes.", "You've reached this month's limit of friend rewards.")


def task_result(lang: str, status: str) -> str:
    return {
        "ok": tx(lang, "Задание выполнено!", "Завдання виконано!", "¡Tarea completada!", "Task completed!"),
        "done": tx(lang, "Это задание уже выполнено", "Це завдання вже виконано",
                   "Esta tarea ya está completada", "This task is already completed"),
        "no": tx(lang, "Пока не вижу выполнения. Сделай задание и нажми ещё раз.", "Поки не бачу виконання. Зроби завдання й натисни ще раз.",
                 "Aún no la veo hecha. Completa la tarea y vuelve a pulsar.", "I can't see it done yet. Complete the task and tap again."),
        "bot": tx(lang, "Не могу проверить, напиши администратору", "Не можу перевірити, напиши адміністратору",
                  "No puedo comprobarlo, escribe al administrador", "I can't verify this, please contact the administrator"),
    }.get(status, tx(lang, "Задание больше не действует", "Завдання більше не діє",
                     "Esta tarea ya no está disponible", "This task is no longer available"))


def ads_note(lang: str) -> str:
    return tx(lang, "Можно отключить в настройках в любой момент", "Можна вимкнути в налаштуваннях будь-коли",
              "Puedes desactivarlo en ajustes cuando quieras", "You can turn this off in settings anytime")


def signal_limit(lang: str) -> str:
    return tx(lang, f"💎 Бесплатно — {signals.FREE_SUBS} сигнал, с Premium — до {signals.TOP_SUBS}",
              f"💎 Безкоштовно — {signals.FREE_SUBS} сигнал, із Premium — до {signals.TOP_SUBS}",
              f"💎 Gratis: {signals.FREE_SUBS} señal; con Premium, hasta {signals.TOP_SUBS}",
              f"💎 Free: {signals.FREE_SUBS} signal; with Premium, up to {signals.TOP_SUBS}")


def signal_added(lang: str) -> str:
    return tx(lang, "✅ Готово! Напишу, как только кто-то заметит места.", "✅ Готово! Напишу, щойно хтось помітить місця.",
              "✅ ¡Listo! Te escribiré en cuanto alguien vea plazas.", "✅ Done! I'll message you as soon as someone spots slots.")


def promo_prompt(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, "🎟 <b>Промокод</b>\n\nПришли код одним сообщением.", "🎟 <b>Промокод</b>\n\nНадішли код одним повідомленням.",
                     "🎟 <b>Código promocional</b>\n\nEnvía el código en un mensaje.",
                     "🎟 <b>Promo code</b>\n\nSend the code in one message."),
            ikb([[btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), "pr")]]))


def promo_result(lang: str, status: str, hours: int = 0) -> str:
    return {
        "ok": tx(lang, f"🎉 Промокод принят: +{hours_text(lang, hours)} Premium!", f"🎉 Промокод прийнято: +{hours_text(lang, hours)} Premium!",
                       f"🎉 Código aceptado: +{hours_text(lang, hours)} de Premium.",
                       f"🎉 Code accepted: +{hours_text(lang, hours)} of Premium!"),
        "used": tx(lang, "Этот промокод ты уже использовал.", "Цей промокод ти вже використав.",
                         "Ya has usado este código.",
                         "You've already used this code."),
        "expired": tx(lang, "😕 Срок промокода истёк.", "😕 Термін промокоду минув.",
                            "😕 El código ha caducado.",
                            "😕 This code has expired."),
        "limit": tx(lang, "😕 Промокод закончился.", "😕 Промокод закінчився.",
                          "😕 El código se ha agotado.",
                          "😕 This code has run out."),
        "wait": tx(lang, "⏳ Слишком много попыток. Попробуй через 10 минут.", "⏳ Забагато спроб. Спробуй за 10 хвилин.",
                         "⏳ Demasiados intentos. Prueba dentro de 10 minutos.",
                         "⏳ Too many attempts. Try again in 10 minutes."),
    }.get(status, tx(lang, "😕 Такого промокода нет.", "😕 Такого промокоду немає.",
                           "😕 Ese código no existe.",
                           "😕 That code doesn't exist."))


def ref_welcome(lang: str) -> str:
    return tx(lang, f"🎁 Тебя пригласил друг! Добавь офис — и вы оба получите +{hours_text(lang, store.setting('ref_hours'))} Premium.",
              f"🎁 Тебе запросив друг! Додай офіс — і ви обидва отримаєте +{hours_text(lang, store.setting('ref_hours'))} Premium.",
                    f"🎁 ¡Te ha invitado un amigo! Añade una oficina y los dos recibiréis +{hours_text(lang, store.setting('ref_hours'))} de Premium.",
                    f"🎁 A friend invited you! Add an office and you'll both get +{hours_text(lang, store.setting('ref_hours'))} of Premium.")


# ---------- пробный период ----------

def trial_days(lang: str) -> str:
    return hours_text(lang, int(store.setting("trial_hours")))


def trial_btn(lang: str) -> dict:
    d = trial_days(lang)
    return btn(tx(lang, f"🎁 Попробовать Premium · {d}", f"🎁 Спробувати Premium · {d}", f"🎁 Probar Premium · {d}", f"🎁 Try Premium · {d}"),
               "tr", "success")


def trial_note(lang: str, status: str) -> str:
    return {
        "used": tx(lang, "Пробный период уже был: он даётся один раз.", "Пробний період уже був: він надається один раз.",
                   "Ya usaste la prueba: solo se puede una vez.", "You've already used the trial: it's one per person."),
        "paid": tx(lang, "Пробный период только для тех, кто ещё не покупал Premium.", "Пробний період лише для тих, хто ще не купував Premium.",
                   "La prueba es solo para quien aún no ha comprado Premium.", "The trial is only for people who haven't bought Premium yet."),
        "active": tx(lang, "Premium уже включён.", "Premium уже увімкнено.", "Premium ya está activo.", "Premium is already on."),
        "down": tx(lang, "🛠 Идут технические работы. Запусти пробный период позже, чтобы дни не сгорели.",
                   "🛠 Тривають технічні роботи. Запусти пробний період пізніше, щоб дні не згоріли.",
                   "🛠 Estamos en mantenimiento. Empieza la prueba más tarde para no perder días.",
                   "🛠 Maintenance in progress. Start the trial later so you don't lose days."),
    }.get(status, tx(lang, "Пробный период сейчас недоступен.", "Пробний період зараз недоступний.",
                     "La prueba no está disponible ahora.", "The trial isn't available right now."))


def trial_view(chat: int, note: str = "") -> Tuple[str, dict]:
    lang = lang_of(chat)
    d, slow, fast = trial_days(lang), store.setting("interval"), store.setting("interval_premium")
    free, top = store.setting("free_subs"), store.setting("max_subs")
    text = (tx(lang, f"🎁 <b>{d} Premium бесплатно</b>\n\nПолный доступ ко всему, включая мини-приложение.",
               f"🎁 <b>{d} Premium безкоштовно</b>\n\nПовний доступ до всього, зокрема до міні-застосунку.",
               f"🎁 <b>{d} de Premium gratis</b>\n\nAcceso completo a todo, también a la miniapp.",
               f"🎁 <b>{d} of Premium for free</b>\n\nFull access to everything, including the mini app.")
            + "\n<blockquote>" + tx(lang,
                                    f"📱 Мини-приложение: календарь, радар, статистика\n⚡️ Проверка каждые {fast} мин вместо {slow}\n"
                                    f"🏢 До {top} офисов вместо {free}\n📡 Радар без лимита, до 250 км\n🛂 До {signals.TOP_SUBS} сигналов о документах",
                                    f"📱 Міні-застосунок: календар, радар, статистика\n⚡️ Перевірка кожні {fast} хв замість {slow}\n"
                                    f"🏢 До {top} офісів замість {free}\n📡 Радар без ліміту, до 250 км\n🛂 До {signals.TOP_SUBS} сигналів про документи",
                                    f"📱 Miniapp: calendario, radar, estadísticas\n⚡️ Revisión cada {fast} min en vez de {slow}\n"
                                    f"🏢 Hasta {top} oficinas en vez de {free}\n📡 Radar sin límite, hasta 250 km\n🛂 Hasta {signals.TOP_SUBS} señales de documentos",
                                    f"📱 Mini app: calendar, radar, statistics\n⚡️ Checks every {fast} min instead of {slow}\n"
                                    f"🏢 Up to {top} offices instead of {free}\n📡 Unlimited radar, up to 250 km\n🛂 Up to {signals.TOP_SUBS} document signals")
            + "</blockquote>\n"
            + tx(lang, "<i>Только один раз на человека. Отсчёт идёт с момента нажатия. Ничего не спишется, автопродления нет. "
                       "Когда срок закончится, лишние офисы встанут на паузу.</i>",
                 "<i>Лише один раз на людину. Відлік іде з моменту натискання. Нічого не спишеться, автопродовження немає. "
                 "Коли строк закінчиться, зайві офіси стануть на паузу.</i>",
                 "<i>Solo una vez por persona. Empieza al pulsar. No se cobra nada ni se renueva sola. "
                 "Al terminar, las oficinas de más quedan en pausa.</i>",
                 "<i>One time per person. It starts when you tap. Nothing is charged and nothing renews. "
                 "When it ends, extra offices are paused.</i>"))
    if note:
        text += f"\n\n{note}"
    rows = []
    if premium.can_trial(chat):
        rows.append([btn(tx(lang, f"✅ Начать: {d} бесплатно", f"✅ Почати: {d} безкоштовно", f"✅ Empezar: {d} gratis", f"✅ Start: {d} free"), "tr!", "success")])
    rows.append([btn("💎 Premium", "pr"), home_btn(lang)])
    return text, ikb(rows)


def trial_started(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    until = datetime.fromtimestamp(store.get_chat(chat).get("premium_until") or 0, config.TZ)
    text = tx(lang, f"🎉 <b>Premium включён до {until:%d.%m в %H:%M}</b>\n\nМини-приложение теперь рядом с полем ввода. "
                    "Добавь офисы, и бот будет проверять их каждые несколько минут.",
              f"🎉 <b>Premium увімкнено до {until:%d.%m о %H:%M}</b>\n\nМіні-застосунок тепер поруч із полем введення. "
              "Додай офіси, і бот перевірятиме їх кожні кілька хвилин.",
              f"🎉 <b>Premium activo hasta el {until:%d.%m a las %H:%M}</b>\n\nLa miniapp ya está junto al campo de texto. "
              "Añade oficinas y el bot las revisará cada pocos minutos.",
              f"🎉 <b>Premium is on until {until:%d.%m at %H:%M}</b>\n\nThe mini app is now next to the message field. "
              "Add offices and the bot will check them every few minutes.")
    rows = []
    if premium.app_url():
        rows.append([webapp(tx(lang, "📱 Открыть приложение", "📱 Відкрити застосунок", "📱 Abrir la miniapp", "📱 Open the mini app"), premium.app_url(), "primary")])
    rows.append([btn(tx(lang, "➕ Добавить офис", "➕ Додати офіс", "➕ Añadir oficina", "➕ Add office"), "p:0"), home_btn(lang)])
    return text, ikb(rows)


# ---------- вакансии, реклама и партнёры ----------

def hide_label(lang: str) -> str:
    return tx(lang, "✖️ Скрыть", "✖️ Сховати", "✖️ Ocultar", "✖️ Hide")


def board_btn(lang: str) -> str:
    return tx(lang, "💼 Вакансии и партнёры", "💼 Вакансії та партнери", "💼 Empleo y socios", "💼 Jobs and partners")


def channel_name() -> str:
    return str(store.setting("channel") or "")


def channel_url() -> str:
    return f"https://t.me/{channel_name().lstrip('@')}"


def board_view(chat: int, note: str = "") -> Tuple[str, dict]:
    import board
    lang = lang_of(chat)
    name, job, ad = channel_name(), board.price("job"), board.price("ad")
    free = not store.free_job_used(chat)
    job_line = tx(lang, f"💼 Вакансия: {'первая бесплатно, дальше ' if free else ''}{job} ⭐",
                  f"💼 Вакансія: {'перша безкоштовно, далі ' if free else ''}{job} ⭐",
                  f"💼 Empleo: {'la primera gratis, luego ' if free else ''}{job} ⭐",
                  f"💼 Job: {'first one free, then ' if free else ''}{job} ⭐")
    text = (tx(lang, f"💼 <b>Вакансии и реклама</b>\n\nПубликуем объявления в канале {name}: работа, услуги и предложения для людей в Испании.",
               f"💼 <b>Вакансії та реклама</b>\n\nПублікуємо оголошення в каналі {name}: робота, послуги й пропозиції для людей в Іспанії.",
               f"💼 <b>Empleo y publicidad</b>\n\nPublicamos anuncios en el canal {name}: empleo, servicios y ofertas para quienes viven en España.",
               f"💼 <b>Jobs and ads</b>\n\nWe publish posts in the {name} channel: jobs, services and offers for people in Spain.")
            + f"\n<blockquote>{job_line}\n"
            + tx(lang, f"📣 Услуга или реклама: {ad} ⭐", f"📣 Послуга або реклама: {ad} ⭐", f"📣 Servicio o publicidad: {ad} ⭐", f"📣 Service or ad: {ad} ⭐")
            + "</blockquote>\n"
            + tx(lang, "<i>Каждое объявление проверяет администратор. Если откажем, звёзды вернутся. "
                       "Нельзя продавать записи (cita): запись бесплатна. Нельзя публиковать обман и незаконные предложения.</i>",
                 "<i>Кожне оголошення перевіряє адміністратор. Якщо відмовимо, зірки повернуться. "
                 "Не можна продавати записи (cita): запис безкоштовний. Не можна публікувати обман і незаконні пропозиції.</i>",
                 "<i>Un administrador revisa cada anuncio. Si lo rechazamos, devolvemos las estrellas. "
                 "No se pueden vender citas: son gratis. Tampoco se admiten engaños ni ofertas ilegales.</i>",
                 "<i>An administrator reviews every post. If we reject it, your Stars come back. "
                 "Selling appointments is banned: they're free. No scams or illegal offers.</i>"))
    if note:
        text += f"\n\n{note}"
    rows = [[btn(tx(lang, "💼 Разместить вакансию", "💼 Розмістити вакансію", "💼 Publicar empleo", "💼 Post a job"), "jn:job", "primary")],
            [btn(tx(lang, "📣 Разместить услугу", "📣 Розмістити послугу", "📣 Publicar servicio", "📣 Post a service"), "jn:ad")],
            [btn(tx(lang, "🤝 Партнёрам", "🤝 Партнерам", "🤝 Socios", "🤝 Partners"), "pn"),
             btn(tx(lang, "📋 Мои объявления", "📋 Мої оголошення", "📋 Mis anuncios", "📋 My posts"), "jm")],
            [url(tx(lang, "📢 Открыть канал", "📢 Відкрити канал", "📢 Abrir el canal", "📢 Open the channel"), channel_url())],
            [home_btn(lang)]]
    return text, ikb(rows)


def post_prompt(chat: int, kind: str) -> Tuple[str, dict]:
    lang = lang_of(chat)
    head = (tx(lang, "💼 <b>Новая вакансия</b>", "💼 <b>Нова вакансія</b>", "💼 <b>Nuevo empleo</b>", "💼 <b>New job</b>") if kind == "job"
            else tx(lang, "📣 <b>Новое объявление</b>", "📣 <b>Нове оголошення</b>", "📣 <b>Nuevo anuncio</b>", "📣 <b>New post</b>"))
    return (head + tx(lang, "\n\nПришли его одним сообщением, можно с фото. Напиши город, что предлагаешь, условия и контакт: "
                            "@ник, телефон или ссылку. От 30 до 800 символов.",
                      "\n\nНадішли його одним повідомленням, можна з фото. Напиши місто, що пропонуєш, умови й контакт: "
                      "@нік, телефон або посилання. Від 30 до 800 символів.",
                      "\n\nEnvíalo en un solo mensaje, puede llevar foto. Indica ciudad, qué ofreces, condiciones y contacto: "
                      "@usuario, teléfono o enlace. De 30 a 800 caracteres.",
                      "\n\nSend it in one message, a photo is fine. Include the city, what you offer, the terms and a contact: "
                      "@username, phone or link. 30 to 800 characters."),
            ikb([[btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), "jb")]]))


def post_error(lang: str, status: str) -> str:
    return {
        "short": tx(lang, "✏️ Слишком коротко: нужно хотя бы 30 символов. Напиши ещё раз.", "✏️ Занадто коротко: потрібно хоча б 30 символів. Напиши ще раз.",
                    "✏️ Demasiado corto: mínimo 30 caracteres. Escríbelo de nuevo.", "✏️ Too short: at least 30 characters. Please write it again."),
        "long": tx(lang, "✏️ Слишком длинно: максимум 800 символов. Сократи и пришли снова.", "✏️ Занадто довго: максимум 800 символів. Скороти й надішли знову.",
                   "✏️ Demasiado largo: máximo 800 caracteres. Acórtalo y envíalo otra vez.", "✏️ Too long: 800 characters at most. Shorten it and send again."),
        "contact": tx(lang, "✏️ Добавь контакт: @ник, телефон или ссылку, и пришли снова.", "✏️ Додай контакт: @нік, телефон або посилання, і надішли знову.",
                      "✏️ Añade un contacto: @usuario, teléfono o enlace, y envíalo otra vez.", "✏️ Add a contact: @username, phone or link, and send it again."),
        "resale": tx(lang, "🚫 Продавать записи (cita) и помощь с их получением здесь нельзя: запись бесплатна.",
                     "🚫 Продавати записи (cita) і допомогу з їх отриманням тут не можна: запис безкоштовний.",
                     "🚫 Aquí no se pueden vender citas ni ayuda para conseguirlas: son gratis.",
                     "🚫 Selling appointments or help getting them isn't allowed here: they're free."),
        "many": tx(lang, "⏳ У тебя уже 3 объявления на проверке. Дождись решения.", "⏳ У тебе вже 3 оголошення на перевірці. Дочекайся рішення.",
                   "⏳ Ya tienes 3 anuncios en revisión. Espera la decisión.", "⏳ You already have 3 posts under review. Please wait for a decision."),
    }.get(status, "")


def post_preview(chat: int, post: dict, invoice: Optional[str]) -> Tuple[str, dict]:
    lang = lang_of(chat)
    pid, stars = post["id"], post["stars"]
    text = (tx(lang, "👀 <b>Проверь объявление</b>", "👀 <b>Перевір оголошення</b>", "👀 <b>Revisa el anuncio</b>", "👀 <b>Check your post</b>")
            + ("\n🖼" if post.get("photo") else "") + f"\n<blockquote>{esc(post['text'])}</blockquote>\n"
            + (tx(lang, f"Стоимость: <b>{stars} ⭐</b>", f"Вартість: <b>{stars} ⭐</b>", f"Precio: <b>{stars} ⭐</b>", f"Price: <b>{stars} ⭐</b>") if stars
               else tx(lang, "Бесплатно: первая вакансия.", "Безкоштовно: перша вакансія.", "Gratis: tu primer empleo.", "Free: your first job post.")))
    rows = []
    if stars and invoice:
        rows.append([url(tx(lang, f"⭐️ Оплатить {stars}", f"⭐️ Сплатити {stars}", f"⭐️ Pagar {stars}", f"⭐️ Pay {stars}"), invoice, "success")])
    elif not stars:
        rows.append([btn(tx(lang, "✅ Отправить на проверку", "✅ Надіслати на перевірку", "✅ Enviar a revisión", "✅ Send for review"), f"js:{pid}", "success")])
    rows.append([btn(tx(lang, "✏️ Написать заново", "✏️ Написати заново", "✏️ Escribir de nuevo", "✏️ Rewrite"), f"jn:{post['kind']}"),
                 btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), f"jx:{pid}")])
    return text, ikb(rows)


def post_sent(lang: str) -> str:
    return tx(lang, "✅ Объявление на проверке. Обычно отвечаем в течение суток.", "✅ Оголошення на перевірці. Зазвичай відповідаємо протягом доби.",
              "✅ Anuncio en revisión. Solemos responder en un día.", "✅ Your post is under review. We usually reply within a day.")


def post_invoice(lang: str, kind: str) -> Tuple[str, str]:
    title = (tx(lang, "Вакансия в канале", "Вакансія в каналі", "Empleo en el canal", "Job post in the channel") if kind == "job"
             else tx(lang, "Объявление в канале", "Оголошення в каналі", "Anuncio en el canal", "Post in the channel"))
    return (f"{config.BRAND}: {title}",
            tx(lang, "Публикация после проверки. Если откажем, звёзды вернутся.", "Публікація після перевірки. Якщо відмовимо, зірки повернуться.",
               "Se publica tras la revisión. Si lo rechazamos, devolvemos las estrellas.", "Published after review. If we reject it, your Stars come back."))


def post_published(lang: str) -> str:
    return tx(lang, "✅ <b>Объявление опубликовано</b>", "✅ <b>Оголошення опубліковано</b>", "✅ <b>Anuncio publicado</b>", "✅ <b>Your post is live</b>")


def post_open_btn(lang: str) -> str:
    return tx(lang, "📢 Открыть пост", "📢 Відкрити пост", "📢 Abrir la publicación", "📢 Open the post")


def post_rejected(lang: str, reason: str, paid: bool) -> str:
    why = {"contact": tx(lang, "нет понятного контакта", "немає зрозумілого контакту", "falta un contacto claro", "no clear contact"),
           "scam": tx(lang, "похоже на обман или продажу записей", "схоже на обман або продаж записів",
                      "parece un engaño o venta de citas", "it looks like a scam or appointment resale"),
           }.get(reason, tx(lang, "не подходит под правила канала", "не відповідає правилам каналу", "no cumple las normas del canal", "it doesn't fit the channel rules"))
    return (tx(lang, f"🚫 <b>Объявление отклонено</b>: {why}.", f"🚫 <b>Оголошення відхилено</b>: {why}.", f"🚫 <b>Anuncio rechazado</b>: {why}.", f"🚫 <b>Post rejected</b>: {why}.")
            + (tx(lang, "\nЗвёзды возвращаются на твой баланс.", "\nЗірки повертаються на твій баланс.", "\nTus estrellas vuelven a tu saldo.", "\nYour Stars are going back to your balance.") if paid else ""))


def my_posts(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    marks = {"review": "⏳", "published": "✅", "rejected": "🚫"}
    items = [f"{marks.get(p['status'], '•')} {esc(p['text'][:60])}…" for p in store.posts_of(chat)]
    text = tx(lang, "📋 <b>Мои объявления</b>", "📋 <b>Мої оголошення</b>", "📋 <b>Mis anuncios</b>", "📋 <b>My posts</b>") + "\n\n"
    text += ("<blockquote>" + "\n".join(items) + "</blockquote>\n"
             + tx(lang, "⏳ на проверке · ✅ опубликовано · 🚫 отклонено", "⏳ на перевірці · ✅ опубліковано · 🚫 відхилено",
                  "⏳ en revisión · ✅ publicado · 🚫 rechazado", "⏳ under review · ✅ published · 🚫 rejected")) if items else \
        tx(lang, "Пока объявлений нет.", "Поки оголошень немає.", "Aún no hay anuncios.", "No posts yet.")
    return text, ikb([[btn(tx(lang, "⬅️ Назад", "⬅️ Назад", "⬅️ Atrás", "⬅️ Back"), "jb"), home_btn(lang)]])


def partner_view(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, "🤝 <b>Партнёрам и рекламодателям</b>\n\nНаша аудитория: люди в Испании, которые оформляют права, документы и ищут работу и услуги."
                     "\n<blockquote>📢 Посты в канале\n💬 Предложения в боте, только тем, кто согласился\n🎟 Совместные акции и промокоды</blockquote>\n"
                     "Напиши одним сообщением: кто вы, что предлагаете и как с вами связаться.",
               "🤝 <b>Партнерам і рекламодавцям</b>\n\nНаша аудиторія: люди в Іспанії, які оформлюють права й документи та шукають роботу й послуги."
               "\n<blockquote>📢 Пости в каналі\n💬 Пропозиції в боті, лише тим, хто погодився\n🎟 Спільні акції та промокоди</blockquote>\n"
               "Напиши одним повідомленням: хто ви, що пропонуєте і як із вами зв’язатися.",
               "🤝 <b>Socios y anunciantes</b>\n\nNuestro público: personas en España que tramitan permisos y documentos y buscan empleo y servicios."
               "\n<blockquote>📢 Publicaciones en el canal\n💬 Ofertas en el bot, solo a quien las acepta\n🎟 Promociones y códigos conjuntos</blockquote>\n"
               "Escribe en un mensaje quiénes sois, qué ofrecéis y cómo contactaros.",
               "🤝 <b>Partners and advertisers</b>\n\nOur audience: people in Spain sorting out licences and documents and looking for jobs and services."
               "\n<blockquote>📢 Channel posts\n💬 Offers in the bot, only to people who agreed\n🎟 Joint promotions and promo codes</blockquote>\n"
               "Tell us in one message who you are, what you offer and how to reach you."),
            ikb([[btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), "jb")]]))


def partner_sent(lang: str) -> str:
    return tx(lang, "✅ Заявка передана. Ответим здесь же.", "✅ Заявку передано. Відповімо тут же.", "✅ Solicitud enviada. Responderemos aquí.", "✅ Request sent. We'll reply here.")


# ---------- памятка по TIE ----------

TAX_URL = "https://sede.policia.gob.es:38089/Tasa790_012/"


def tie_guide(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    text = tx(lang,
              "📋 <b>Запись на TIE: как не потерять время</b>\n\n"
              "<b>1. Где записываться</b>\n<blockquote>Официальный сайт → твоя провинция → Trámites Policía Nacional → "
              "<b>POLICÍA-TOMA DE HUELLAS</b>. Для временной защиты бывает отдельный пункт: POLICÍA TARJETA CONFLICTO UCRANIA.</blockquote>\n"
              "<b>2. Что держать под рукой</b>\n<blockquote>NIE или паспорт, имя точно как в документе, страна, телефон и email. "
              "Кнопку «назад» в браузере не нажимай: при ошибке начни сначала. Если есть «Cualquier oficina», выбирай его: мест больше.</blockquote>\n"
              "<b>3. Что взять на визит</b>\n<blockquote>• оригинал паспорта или cédula\n• прежняя TIE, если есть\n• свежее цветное фото на белом фоне\n"
              "• empadronamiento, если сменился адрес\n• бланк EX-17\n• оплаченная пошлина: модель 790, код 012</blockquote>\n"
              "<b>4. Если не можешь прийти</b>\n<blockquote>Отмени на том же сайте: «Anular Cita» и номер justificante. В день визита отменить уже нельзя.</blockquote>\n"
              "<b>Málaga</b>\n<blockquote>С 8 октября 2026 после положительной резолюции запись на TIE назначается автоматически, приглашение приходит по SMS или email. "
              "Если его нет около 20 дней, запишись сам. Для условных разрешений это не работает.</blockquote>\n"
              "<i>По записке Extranjería Málaga. В других провинциях детали могут отличаться, сверяйся с официальным сайтом. Запись бесплатна: никому не плати за неё.</i>",
              "📋 <b>Запис на TIE: як не втратити час</b>\n\n"
              "<b>1. Де записуватися</b>\n<blockquote>Офіційний сайт → твоя провінція → Trámites Policía Nacional → "
              "<b>POLICÍA-TOMA DE HUELLAS</b>. Для тимчасового захисту буває окремий пункт: POLICÍA TARJETA CONFLICTO UCRANIA.</blockquote>\n"
              "<b>2. Що тримати під рукою</b>\n<blockquote>NIE або паспорт, ім’я точно як у документі, країна, телефон і email. "
              "Кнопку «назад» у браузері не натискай: при помилці почни спочатку. Якщо є «Cualquier oficina», обирай його: місць більше.</blockquote>\n"
              "<b>3. Що взяти на візит</b>\n<blockquote>• оригінал паспорта або cédula\n• попередня TIE, якщо є\n• свіже кольорове фото на білому тлі\n"
              "• empadronamiento, якщо змінилася адреса\n• бланк EX-17\n• сплачений збір: модель 790, код 012</blockquote>\n"
              "<b>4. Якщо не можеш прийти</b>\n<blockquote>Скасуй на тому ж сайті: «Anular Cita» і номер justificante. У день візиту скасувати вже не можна.</blockquote>\n"
              "<b>Málaga</b>\n<blockquote>З 8 жовтня 2026 після позитивної резолюції запис на TIE призначається автоматично, запрошення надходить через SMS або email. "
              "Якщо його немає близько 20 днів, запишися сам. Для умовних дозволів це не працює.</blockquote>\n"
              "<i>За запискою Extranjería Málaga. В інших провінціях деталі можуть відрізнятися, звіряйся з офіційним сайтом. Запис безкоштовний: нікому за нього не плати.</i>",
              "📋 <b>Cita para la TIE: cómo no perder tiempo</b>\n\n"
              "<b>1. Dónde pedirla</b>\n<blockquote>Web oficial → tu provincia → Trámites Policía Nacional → "
              "<b>POLICÍA-TOMA DE HUELLAS</b>. Para la protección temporal puede haber una opción propia: POLICÍA TARJETA CONFLICTO UCRANIA.</blockquote>\n"
              "<b>2. Qué tener a mano</b>\n<blockquote>NIE o pasaporte, nombre exacto como en el documento, país, teléfono y email. "
              "No uses el botón «atrás» del navegador: si hay error, empieza de nuevo. Si aparece «Cualquier oficina», elígela: hay más plazas.</blockquote>\n"
              "<b>3. Qué llevar a la cita</b>\n<blockquote>• pasaporte o cédula originales\n• TIE anterior, si la tienes\n• foto reciente en color con fondo blanco\n"
              "• empadronamiento, si cambiaste de domicilio\n• impreso EX-17\n• tasa pagada: modelo 790, código 012</blockquote>\n"
              "<b>4. Si no puedes ir</b>\n<blockquote>Anúlala en la misma web: «Anular Cita» y número de justificante. El mismo día ya no se puede anular.</blockquote>\n"
              "<b>Málaga</b>\n<blockquote>Desde el 8 de octubre de 2026, tras una resolución favorable, la cita para la TIE se asigna sola y llega por SMS o email. "
              "Si en unos 20 días no llega, pídela tú. No vale para concesiones condicionadas.</blockquote>\n"
              "<i>Según la nota de la Oficina de Extranjería de Málaga. En otras provincias puede variar: compruébalo en la web oficial. La cita es gratis: no pagues a nadie por ella.</i>",
              "📋 <b>TIE appointment: how not to lose time</b>\n\n"
              "<b>1. Where to book</b>\n<blockquote>Official website → your province → Trámites Policía Nacional → "
              "<b>POLICÍA-TOMA DE HUELLAS</b>. Temporary protection may have its own option: POLICÍA TARJETA CONFLICTO UCRANIA.</blockquote>\n"
              "<b>2. What to have ready</b>\n<blockquote>NIE or passport, your name exactly as in the document, country, phone and email. "
              "Don't use the browser's back button: if there's an error, start over. If “Cualquier oficina” is offered, pick it: more slots.</blockquote>\n"
              "<b>3. What to bring</b>\n<blockquote>• original passport or cédula\n• previous TIE, if any\n• recent colour photo on a white background\n"
              "• empadronamiento, if your address changed\n• EX-17 form\n• paid fee: form 790, code 012</blockquote>\n"
              "<b>4. If you can't go</b>\n<blockquote>Cancel on the same website: “Anular Cita” and your justificante number. You can't cancel on the day itself.</blockquote>\n"
              "<b>Málaga</b>\n<blockquote>Since 8 October 2026, after a favourable resolution the TIE appointment is assigned automatically and arrives by SMS or email. "
              "If nothing comes in about 20 days, book it yourself. Conditional permits are not covered.</blockquote>\n"
              "<i>Based on the note from the Extranjería office in Málaga. Details may differ in other provinces, so check the official website. Appointments are free: don't pay anyone for one.</i>")
    return text, ikb([[url(tx(lang, "📝 Сайт записи", "📝 Сайт запису", "📝 Web de citas", "📝 Booking site"), signals.ICP_URL, "primary"),
                       url(tx(lang, "💶 Пошлина 790", "💶 Збір 790", "💶 Tasa 790", "💶 Fee 790"), TAX_URL)],
                      [btn(tx(lang, "⬅️ Документы", "⬅️ Документи", "⬅️ Documentos", "⬅️ Documents"), "dc"), home_btn(lang)]])


# ---------- окна проверки ----------

def windows_view(chat: int, note: str = "") -> Tuple[str, dict]:
    lang = lang_of(chat)
    mine, limit = signals.windows_of(chat), signals.window_limit(chat)
    text = (tx(lang, "⏰ <b>Окна проверки</b>\n\nСайт записи бот не смотрит, но может напоминать тебе проверить его самому в выбранные часы (время Мадрида). "
                     "Чем чаще смотришь, тем выше шанс: места разбирают за минуты.",
               "⏰ <b>Вікна перевірки</b>\n\nСайт запису бот не дивиться, але може нагадувати тобі перевірити його самому у вибрані години (час Мадрида). "
               "Що частіше дивишся, то вищий шанс: місця розбирають за лічені хвилини.",
               "⏰ <b>Ventanas de revisión</b>\n\nEl bot no mira la web de citas, pero puede recordarte que la revises tú a las horas que elijas (hora de Madrid). "
               "Cuanto más la mires, más opciones: las plazas vuelan en minutos.",
               "⏰ <b>Check windows</b>\n\nThe bot doesn't look at the booking site, but it can remind you to check it yourself at the hours you choose (Madrid time). "
               "The more often you look, the better: slots go within minutes.")
            + "\n\n" + tx(lang, f"Выбрано: <b>{len(mine)}/{limit}</b>", f"Вибрано: <b>{len(mine)}/{limit}</b>", f"Elegidas: <b>{len(mine)}/{limit}</b>", f"Chosen: <b>{len(mine)}/{limit}</b>"))
    if not signals.subs_of(chat):
        text += "\n" + tx(lang, "<i>Сначала выбери запись, за которой следишь.</i>", "<i>Спочатку обери запис, за яким стежиш.</i>",
                          "<i>Primero elige la cita que quieres seguir.</i>", "<i>First choose the appointment you're tracking.</i>")
    if note:
        text += f"\n\n{note}"
    cells = [btn(("✅ " if h in mine else "") + f"{h:02d}:00", f"dw:{h}") for h in signals.WINDOWS]
    return text, ikb([cells[:3], cells[3:], [btn(tx(lang, "⬅️ Документы", "⬅️ Документи", "⬅️ Documentos", "⬅️ Documents"), "dc"), home_btn(lang)]])


def window_limit_note(lang: str) -> str:
    return tx(lang, f"💎 Бесплатно — {signals.FREE_WINDOWS} окно, с Premium — до {signals.TOP_WINDOWS}",
              f"💎 Безкоштовно — {signals.FREE_WINDOWS} вікно, із Premium — до {signals.TOP_WINDOWS}",
              f"💎 Gratis: {signals.FREE_WINDOWS} ventana; con Premium, hasta {signals.TOP_WINDOWS}",
              f"💎 Free: {signals.FREE_WINDOWS} window; with Premium, up to {signals.TOP_WINDOWS}")


def window_alert(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    items = "\n".join(f"{doc_title(lang, doc)} · <b>{esc(signals.PROVINCES[province])}</b>" for province, doc in signals.subs_of(chat)[:5])
    return (tx(lang, "⏰ <b>Время проверить запись</b>", "⏰ <b>Час перевірити запис</b>", "⏰ <b>Hora de mirar las citas</b>", "⏰ <b>Time to check appointments</b>")
            + f"\n{items}\n\n"
            + tx(lang, "Если увидишь места, нажми кнопку: все, кто ждёт, сразу получат сигнал.", "Якщо побачиш місця, натисни кнопку: усі, хто чекає, одразу отримають сигнал.",
                 "Si ves plazas, pulsa el botón: quienes esperan recibirán la señal al momento.", "If you see slots, tap the button: everyone waiting gets a signal right away."),
            ikb([[url(tx(lang, "📝 Открыть сайт записи", "📝 Відкрити сайт запису", "📝 Abrir la web de citas", "📝 Open the booking site"), signals.ICP_URL, "primary")],
                 [btn(tx(lang, "🟢 Я вижу свободные места", "🟢 Я бачу вільні місця", "🟢 Veo plazas libres", "🟢 I see free slots"), "dp:r:0", "success")],
                 [btn(tx(lang, "⏰ Настроить", "⏰ Налаштувати", "⏰ Ajustar", "⏰ Adjust"), "dw"), btn(hide_label(lang), "hide")]]))


# ---------- статистика офисов ----------

def stats_view(chat: int) -> Tuple[str, dict]:
    import stats
    lang = lang_of(chat)
    head = tx(lang, "📊 <b>Где чаще появляются места</b> · 30 дней", "📊 <b>Де частіше з’являються місця</b> · 30 днів",
              "📊 <b>Dónde aparecen más plazas</b> · 30 días", "📊 <b>Where slots appear most</b> · 30 days")
    items = []
    for i, g in enumerate(stats.offices()[:10], 1):
        times = pl(lang, g["opens"], ("раз", "раза", "раз"), ("раз", "рази", "разів"), ("vez", "veces"), ("time", "times"))
        held = fmt_dur(g["avg"], lang) if g["avg"] else "—"
        items.append(f"{i}. <b>{esc(city(g['centro']))}</b> · {esc(area_label(g['area']))}\n{times} · ~{g['best']}:00 · ⌛️ {held}")
    body = ("<blockquote>" + "\n".join(items) + "</blockquote>\n"
            + tx(lang, "<i>Считаем только офисы, за которыми следят пользователи. Время Мадрида.</i>", "<i>Рахуємо лише офіси, за якими стежать користувачі. Час Мадрида.</i>",
                 "<i>Solo cuentan las oficinas que siguen los usuarios. Hora de Madrid.</i>", "<i>Only offices our users track are counted. Madrid time.</i>")) if items else \
        tx(lang, "Пока мало данных. Статистика появится, как только в офисах откроются места.", "Поки мало даних. Статистика з’явиться, щойно в офісах відкриються місця.",
           "Aún hay pocos datos. Las estadísticas llegarán cuando aparezcan plazas.", "Not enough data yet. Statistics will appear once slots open up.")
    return f"{head}\n\n{body}", ikb([[btn("📡 " + tx(lang, "Радар", "Радар", "Radar", "Radar"), "rd"), home_btn(lang)]])


# ---------- гарантия ----------

def guarantee_note(lang: str) -> str:
    return tx(lang, f"🛡 Гарантия: если за {premium.GUARANTEE_FROM} дней после первой оплаты не будет ни одного уведомления, верну звёзды.",
              f"🛡 Гарантія: якщо за {premium.GUARANTEE_FROM} днів після першої оплати не буде жодного сповіщення, поверну зірки.",
              f"🛡 Garantía: si en {premium.GUARANTEE_FROM} días desde el primer pago no llega ningún aviso, te devuelvo las estrellas.",
              f"🛡 Guarantee: if there isn't a single alert within {premium.GUARANTEE_FROM} days of your first payment, I'll refund your Stars.")


def guarantee_confirm(chat: int) -> Tuple[str, dict]:
    lang = lang_of(chat)
    return (tx(lang, "🛡 <b>Вернуть звёзды?</b>\nЗа это время бот не нашёл дат по твоим офисам. Premium отключится, автопродление тоже. Вернуть можно один раз.",
               "🛡 <b>Повернути зірки?</b>\nЗа цей час бот не знайшов дат за твоїми офісами. Premium вимкнеться, автопродовження теж. Повернути можна один раз.",
               "🛡 <b>¿Devolver las estrellas?</b>\nEn este tiempo el bot no encontró fechas en tus oficinas. Premium y la renovación se desactivarán. Solo se puede una vez.",
               "🛡 <b>Refund your Stars?</b>\nThe bot found no dates for your offices in this time. Premium and auto-renewal will turn off. This works only once."),
            ikb([[btn(tx(lang, "Да, вернуть", "Так, повернути", "Sí, devolver", "Yes, refund"), "gr!", "danger"),
                  btn(tx(lang, "Отмена", "Скасувати", "Cancelar", "Cancel"), "pr")]]))


def guarantee_result(lang: str, ok: bool) -> str:
    return (tx(lang, "✅ Звёзды возвращаются на твой баланс.", "✅ Зірки повертаються на твій баланс.", "✅ Tus estrellas vuelven a tu saldo.", "✅ Your Stars are going back to your balance.") if ok
            else tx(lang, "😕 Вернуть не получилось. Напиши в /paysupport.", "😕 Повернути не вдалося. Напиши в /paysupport.",
                    "😕 No se pudo devolver. Escribe a /paysupport.", "😕 The refund didn't work. Please write to /paysupport."))
