"""Радар: проверяет ближайшие офисы и показывает, где записаться раньше всего."""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Dict, List, Optional, Tuple

import checker
import dgt
import premium
import store
import tg
import views
from centros import COORDS

log = logging.getLogger("radar")

MAX_OFFICES = 6            # базовый офис + 5 ближайших
FRESH = 15 * 60            # свежий результат можно взять из кэша, не ходя на сайт
AREAS_TTL = 3 * 86400      # типы записи офиса меняются редко
COOLDOWN = 60               # даже с Premium не чаще раза в минуту
RADII = (100, 150, 250)    # доступные радиусы, км; больше 100 — только Premium

last_run: Dict[int, float] = {}
_runs: Dict[int, list] = {}
busy: set = set()


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


def start(chat: int, mid: int, cid: str, cat: str, km: int, token: Optional[int] = None) -> Optional[str]:
    """Запускает радар в фоне. Возвращает текст подсказки, если запустить нельзя."""
    lang = views.lang_of(chat)
    paid = premium.is_premium(chat)
    if checker.site_down():
        return views.tx(lang, "🛠 Идут технические работы, радар временно не работает",
                        "🛠 Тривають технічні роботи, радар тимчасово не працює")
    if chat in busy:
        return views.tx(lang, "📡 Радар уже работает — подожди результат", "📡 Радар уже працює — зачекай на результат")
    if not paid and km > RADII[0]:
        return views.tx(lang, "💎 Поиск дальше 100 км — в Premium", "💎 Пошук далі 100 км — у Premium")
    if not paid and runs_today(chat) >= int(store.setting("free_radar_day")):
        return views.tx(lang, "💎 Бесплатно — один радар в день. Без ограничений — в Premium",
                        "💎 Безкоштовно — один радар на день. Без обмежень — у Premium")
    if time.time() - last_run.get(chat, 0) < COOLDOWN:
        return views.tx(lang, "📡 Подожди минуту перед новым поиском", "📡 Зачекай хвилину перед новим пошуком")
    busy.add(chat)
    last_run[chat] = time.time()
    _runs.setdefault(chat, []).append(store.today_key())
    _runs[chat] = _runs[chat][-8:]
    store.bump("radar")
    threading.Thread(target=run, args=(chat, mid, cid, cat, km, token), daemon=True).start()
    checker.event(f"📡 Радар: {views.city(cid)}, {cat}, {km} км ({store.get_chat(chat).get('name') or chat})")
    return None


def run(chat: int, mid: int, cid: str, cat: str, km: int, token: Optional[int] = None) -> None:
    try:
        offices = nearest(cid, km)
        found = []
        for i, (centro, dist) in enumerate(offices):
            if not tg.same_screen(chat, token):
                return  # человек ушёл с экрана — не тратим запросы к DGT
            tg.show(chat, *views.radar_progress(chat, cid, cat, km, i, len(offices), views.city(centro)), mid=mid)
            code = pick_code(cat, office_areas(centro))
            found.append((centro, code, result_for(centro, code) if code else [], dist))
        found.sort(key=sort_key)
        if tg.same_screen(chat, token):
            tg.show(chat, *views.radar_results(chat, cid, cat, km, found), mid=mid)
    except Exception:
        log.exception("радар упал")
        lang = views.lang_of(chat)
        tg.show(chat, views.tx(lang, "😕 Радар не смог закончить поиск, попробуй позже.",
                               "😕 Радар не зміг завершити пошук, спробуй пізніше."),
                tg.ikb([[views.home_btn(lang)]]), mid=mid)
    finally:
        busy.discard(chat)
