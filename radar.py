"""Радар: проверяет ближайшие офисы и показывает, где записаться раньше всего."""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import checker
import dgt
import premium
import store
import tg
import views
from centros import COORDS

log = logging.getLogger("radar")

MAX_OFFICES = 6            # базовый офис + 5 ближайших
FRESH = 30 * 60            # свежий результат можно взять из кэша, не ходя на сайт
AREAS_TTL = 3 * 86400      # типы записи офиса меняются редко
COOLDOWN = 60               # даже с Premium не чаще раза в минуту
RADII = (100, 150, 250)    # доступные радиусы, км; больше 100 — только Premium
APP_IDLE = 20              # мини-приложение закрыли: столько секунд ждём запросов и останавливаем обход

last_run: Dict[int, float] = {}
_runs: Dict[int, list] = {}
busy: set = set()
scans: Dict[int, dict] = {}  # радар из мини-приложения: ход и результат


def distance(a: str, b: str) -> float:
    (la1, lo1), (la2, lo2) = COORDS[a], COORDS[b]
    p = math.pi / 180
    h = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def nearest(cid: str, km: int) -> List[Tuple[str, int]]:
    """[(офис, км)] — сам офис и ближайшие в радиусе, не больше MAX_OFFICES."""
    near = sorted((round(distance(cid, c)), c) for c in dgt.CENTROS if c in COORDS)
    return [(c, d) for d, c in near if d <= km or c == cid][:MAX_OFFICES]


def office_areas(cid: str) -> List[Tuple[str, str]]:
    """Типы записи офиса: из кэша, а если устарел — с сайта."""
    cached = store.office_areas(cid)
    if cached and time.time() - cached[0] < AREAS_TTL:
        return cached[1]
    try:
        with checker.lock:
            options = dgt.list_areas(cid)
            checker._site_ok()
        store.save_office_areas(cid, options)
        return options
    except Exception as e:
        log.warning("типы записи %s: %s", cid, type(e).__name__)
        return cached[1] if cached else []


def pick_code(cat: str, options: List[Tuple[str, str]]) -> Optional[str]:
    """Код нужной категории в этом офисе. Точное совпадение лучше общего («Conductores / Vehículos»)."""
    matches = [(len(views.cats_of(label)), code) for code, label in options if cat in views.cats_of(label)]
    return min(matches)[1] if matches else None


def result_for(cid: str, code: str) -> Optional[list]:
    st = checker.offices.get((cid, code), {})
    if st.get("results") is not None and time.time() - st.get("at", 0) < FRESH:
        return st["results"]
    if checker.site_down():
        return None
    try:
        with checker.lock:
            results = [r.__dict__ for r in dgt.check(cid, code)]
            checker._site_ok()
        days = views.all_days(results)
        checker.offices.setdefault((cid, code), {"fails": 0}).update(
            results=results, at=int(time.time()), tried=int(time.time()),
            status=results[0]["status"] if results else dgt.UNKNOWN, days=len(days))
        return results
    except Exception as e:
        log.warning("радар %s/%s: %s", cid, code, type(e).__name__)
        with checker.lock:
            checker._site_error(e)
        return None


def sort_key(item) -> tuple:
    centro, code, results, dist = item
    days = views.all_days(results) if results else []
    if days:
        return (0, days[0][0], dist)
    return (1 if results else 2 if code else 3, "", dist)


def runs_today(chat: int) -> int:
    day = store.today_key()
    return sum(1 for t in _runs.get(chat, []) if t == day)


def guard(chat: int, km: int) -> Optional[str]:
    """Текст подсказки, если запустить радар нельзя."""
    lang = views.lang_of(chat)
    paid = premium.is_premium(chat)
    if checker.site_down():
        return views.tx(lang, "🛠 Идут технические работы, радар временно не работает",
                        "🛠 Тривають технічні роботи, радар тимчасово не працює",
                              "🛠 Estamos en mantenimiento, el radar no funciona temporalmente",
                              "🛠 Maintenance in progress, radar is temporarily unavailable")
    if chat in busy:
        return views.tx(lang, "📡 Радар уже работает — подожди результат", "📡 Радар уже працює — зачекай на результат",
                              "📡 El radar ya está en marcha, espera el resultado",
                              "📡 Radar is already running, wait for the result")
    if not paid and km > RADII[0]:
        return views.tx(lang, "💎 Поиск дальше 100 км — в Premium", "💎 Пошук далі 100 км — у Premium",
                              "💎 Buscar a más de 100 km es de Premium",
                              "💎 Searching beyond 100 km is a Premium feature")
    if not paid and runs_today(chat) >= int(store.setting("free_radar_day")):
        return views.tx(lang, "💎 Бесплатно — один радар в день. Без ограничений — в Premium",
                        "💎 Безкоштовно — один радар на день. Без обмежень — у Premium",
                              "💎 Gratis: un radar al día. Sin límites con Premium",
                              "💎 Free: one radar a day. Unlimited with Premium")
    if time.time() - last_run.get(chat, 0) < COOLDOWN:
        return views.tx(lang, "📡 Подожди минуту перед новым поиском", "📡 Зачекай хвилину перед новим пошуком",
                              "📡 Espera un minuto antes de otra búsqueda",
                              "📡 Wait a minute before a new search")
    return None


def _begin(chat: int, cid: str, cat: str, km: int) -> None:
    busy.add(chat)
    last_run[chat] = time.time()
    _runs.setdefault(chat, []).append(store.today_key())
    _runs[chat] = _runs[chat][-8:]
    store.bump("radar")
    checker.event(f"📡 Радар: {views.city(cid)}, {cat}, {km} км ({store.get_chat(chat).get('name') or chat})")


def scan(cid: str, cat: str, km: int, step: Callable[[int, int, str], None], alive: Callable[[], bool]) -> Optional[list]:
    """Обход офисов: step показывает прогресс, alive — нужен ли ещё результат. None — результат уже никому не нужен."""
    offices = nearest(cid, km)
    found = []
    for i, (centro, dist) in enumerate(offices):
        if not alive():
            return None  # человек ушёл — не тратим запросы к DGT
        step(i, len(offices), views.city(centro))
        code = pick_code(cat, office_areas(centro))
        found.append((centro, code, result_for(centro, code) if code else [], dist))
    found.sort(key=sort_key)
    return found


def start(chat: int, mid: int, cid: str, cat: str, km: int, token: Optional[int] = None) -> Optional[str]:
    """Радар в чате. Возвращает текст подсказки, если запустить нельзя."""
    hint = guard(chat, km)
    if hint:
        return hint
    _begin(chat, cid, cat, km)
    threading.Thread(target=run, args=(chat, mid, cid, cat, km, token), daemon=True).start()
    return None


def run(chat: int, mid: int, cid: str, cat: str, km: int, token: Optional[int] = None) -> None:
    alive = lambda: tg.same_screen(chat, token)  # noqa: E731
    step = lambda i, total, name: tg.show(chat, *views.radar_progress(chat, cid, cat, km, i, total, name), mid=mid)  # noqa: E731
    try:
        found = scan(cid, cat, km, step, alive)
        if found is not None and alive():
            tg.show(chat, *views.radar_results(chat, cid, cat, km, found), mid=mid)
    except Exception:
        log.exception("радар упал")
        lang = views.lang_of(chat)
        tg.show(chat, views.radar_failed(lang), tg.ikb([[views.home_btn(lang)]]), mid=mid)
    finally:
        busy.discard(chat)


def start_app(chat: int, cid: str, cat: str, km: int) -> Optional[str]:
    """Радар в мини-приложении: без сообщений в чате, ход смотрим через API."""
    hint = guard(chat, km)
    if hint:
        return hint
    _begin(chat, cid, cat, km)
    scans[chat] = {"cat": cat, "km": km, "done": 0, "total": 0, "current": "", "found": None, "failed": False,
                   "over": False, "seen": time.time()}
    threading.Thread(target=run_app, args=(chat, cid), daemon=True).start()
    return None


def run_app(chat: int, cid: str) -> None:
    job = scans[chat]
    try:
        job["found"] = scan(cid, job["cat"], job["km"], lambda i, total, name: job.update(done=i, total=total, current=name),
                            lambda: time.time() - job["seen"] < APP_IDLE)
        job["done"] = job["total"]
    except Exception:
        log.exception("радар упал")
        job["failed"] = True
    finally:
        job["over"] = True
        busy.discard(chat)
