"""Проверки сайта DGT: очередь офисов, уведомления, сбои сайта, напоминания, вечерний отчёт."""
from __future__ import annotations

import logging
import random
import socket
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests

import channel
import config
import dgt
import gate
import group
import premium
import reviews
import signals
import store
import tg
import views

log = logging.getLogger("checker")

lock = threading.Lock()  # к сайту DGT ходим строго по очереди
status = {"started": int(time.time()), "last_ok": None, "checks": 0, "errors": 0, "alerts": 0, "streak": 0, "trouble_since": None, "cool_until": 0,
          "down_since": None, "probe_at": 0, "probes": 0, "backlog": 0, "due_next": None}
durations: deque = deque(maxlen=50)         # сколько секунд заняли последние проверки
error_times: deque = deque(maxlen=200)      # когда были ошибки сайта — для «ошибок за час»
offices: Dict[Tuple[str, str], dict] = {}   # последний результат по каждому офису
journal: deque = deque(maxlen=300)          # события для админки (с последнего запуска)
OUTAGE_AFTER = 15 * 60                       # столько секунд без единого ответа — сбой: людям предупреждение, админам письмо
COOLDOWN = 3 * 60                            # после ошибки сайта пауза перед следующей проверкой, растёт с каждой ошибкой
REVERIFY = 24 * 3600                         # запись только через заявку с личными данными (canje): перепроверяем раз в сутки
SHARE = 0.85                                 # какую часть пропускной способности отдаём плановым проверкам; остальное — радар и кнопки
_scale = {"at": 0.0, "paid": 1.0, "free": 1.0}
PROBE_MIN, PROBE_MAX = 5 * 60, 60 * 60       # пауза между пробами при сбое: от 5 минут до часа
PACE = (8, 14)                               # пауза между офисами, секунд
_window_sent: Dict[int, Tuple[str, int]] = {}  # кому уже напомнили в этот час
_window_msg: Dict[int, int] = {}               # прошлое напоминание: в чате остаётся только свежее


def event(text: str, kind: str = "info") -> None:
    """kind: info | user | dates | error | money — для фильтра журнала в админке."""
    journal.appendleft((int(time.time()), text, kind))
    log.info("событие: %s", text)


def admins() -> List[int]:
    return sorted(set(config.OWNERS) | {c["chat"] for c in store.all_chats() if c.get("role") == "admin"})


def notify_admins(text: str, rows: Optional[list] = None, silent: bool = True, skip: Optional[int] = None) -> None:
    kb = tg.ikb((rows or []) + [[tg.btn("✖️ Скрыть", "hide")]])
    for chat in admins():
        if chat != skip:
            tg.send(chat, text, kb, silent=silent)


def is_quiet(chat: int) -> bool:
    return bool(store.get_chat(chat).get("quiet")) and datetime.now(config.TZ).hour < 8


def office_name(cid: str, area: str) -> str:
    return f"{views.city(cid)} · {views.area_label(area)}"


# ---------- доступность сайта ----------

def site_down() -> bool:
    return status["down_since"] is not None


def diagnose() -> str:
    """Что видно с сервера: помогает отличить сбой DGT от блокировки адреса сервера."""
    lines = []
    for host in ("sedeclave.dgt.gob.es", "sede.dgt.gob.es", "www.dgt.es", "www.boe.es", "api.telegram.org"):
        started = time.time()
        try:
            socket.create_connection((host, 443), 8).close()
            lines.append(f"{host}: ok {(time.time() - started) * 1000:.0f} мс")
        except OSError as e:
            lines.append(f"{host}: нет ({type(e).__name__})")
    try:
        lines.append("исходящий адрес: " + requests.get("https://api.ipify.org", timeout=8).text[:45])
    except requests.RequestException:
        lines.append("исходящий адрес: неизвестен")
    return "\n".join(lines)


def _site_ok() -> None:
    status.update(streak=0, last_ok=int(time.time()), trouble_since=None, cool_until=0)
    dgt.relax()
    if site_down():
        minutes = round((time.time() - status["down_since"]) / 60)
        status.update(down_since=None, probes=0, probe_at=0)
        event(f"✅ Сайт DGT снова доступен (сбой {minutes} мин)", "error")
        notify_admins(f"✅ <b>Сайт DGT снова доступен</b>\nСбой длился {views.fmt_dur(minutes * 60)}.")


def _site_error(err: Exception) -> None:
    status["errors"] += 1
    status["streak"] += 1
    error_times.append(time.time())
    store.bump("errors")
    now = time.time()
    status["trouble_since"] = status["trouble_since"] or now
    if site_down():
        status["probes"] += 1
        status["probe_at"] = now + min(PROBE_MAX, PROBE_MIN * 2 ** status["probes"])
        return
    # Ошибка 500 после частых запросов — это сайт просит притормозить, а не сбой. Пауза и реже сессии, людей не тревожим.
    slow = dgt.slow_down()
    status["cool_until"] = now + COOLDOWN * min(4, status["streak"])
    if status["streak"] == 1:
        log.info("сайт DGT ответил ошибкой (%s), пауза %d мин, сессии реже в %.0f раз", type(err).__name__, COOLDOWN // 60, slow)
    if now - status["trouble_since"] >= OUTAGE_AFTER:
        status.update(down_since=int(status["trouble_since"]), probes=0, probe_at=now + PROBE_MIN)
        report = diagnose()
        log.warning("сайт DGT недоступен: %r\n%s", err, report)
        event("🛑 Сайт DGT недоступен с сервера — проверки перешли в редкие пробы", "error")
        notify_admins("🛑 <b>Сайт DGT недоступен с сервера</b> уже 15 минут\n"
                      "Проверки перешли в редкие пробы (от 5 минут до часа), пользователи видят предупреждение, "
                      f"оплата закрыта.\n\n<pre>{views.esc(report)}</pre>", silent=False)


# ---------- очередь ----------

def _base(paid: bool) -> int:
    return int(store.setting("interval_premium" if paid else "interval")) * 60


def scales() -> Tuple[float, float]:
    """Во сколько раз растягиваем интервалы (Premium, бесплатно), чтобы не выходить за лимит сайта DGT.
    Premium получает пропускную способность первым, бесплатные — остаток, но не меньше 15%. Пересчёт раз в минуту."""
    if time.time() - _scale["at"] < 60:
        return _scale["paid"], _scale["free"]
    per = per_office()
    need = {True: 0.0, False: 0.0}
    for key, subs in store.key_groups().items():
        if not waits_for_data(key):
            paid = any(premium.is_premium(s["chat"]) for s in subs)
            need[paid] += per / _base(paid)
    paid_scale = max(1.0, need[True] / SHARE)
    free_scale = max(1.0, need[False] / max(SHARE - need[True] / paid_scale, 0.15))
    _scale.update(at=time.time(), paid=paid_scale, free=free_scale)
    return paid_scale, free_scale


def check_minutes(paid: bool) -> int:
    """Сколько минут на самом деле между проверками сейчас. Это число видят люди."""
    return max(1, round(_base(paid) * scales()[0 if paid else 1] / 60))


views.check_minutes = check_minutes
channel.notify = lambda text: notify_admins(text, silent=False)
group.notify = lambda text: notify_admins(text, silent=False)


def _intervals(chats: List[int]) -> int:
    paid = any(premium.is_premium(c) for c in chats)
    return int(_base(paid) * scales()[0 if paid else 1])


def waits_for_data(key: Tuple[str, str]) -> bool:
    """Офис отвечает только «заявка с личными данными»: календаря нет, часто проверять бессмысленно."""
    results = offices.get(key, {}).get("results")
    return bool(results) and all(r.get("status") == dgt.NEEDS_DATA for r in results)


def every(key: Tuple[str, str], chats: List[int]) -> int:
    return REVERIFY if waits_for_data(key) else _intervals(chats)


def plan() -> List[Tuple[str, str]]:
    """Офисы, которым пора на проверку: сначала Premium, затем те, что ждут дольше всех."""
    now = time.time()
    due, soonest = [], None
    groups = store.key_groups()
    for key, subs in groups.items():
        chats = [s["chat"] for s in subs]
        period = every(key, chats)
        last = offices.get(key, {}).get("tried", 0)
        wait = last + period - now
        if wait <= 0:
            is_paid = any(premium.is_premium(c) for c in chats)
            due.append((0 if is_paid else 1, last, -len(subs), key))
        elif soonest is None or wait < soonest:
            soonest = wait
    due.sort()
    status["backlog"] = max(0, len(due) - 1)
    status["due_next"] = int(now + (soonest or 0)) if soonest is not None else None
    return [d[3] for d in due]


def next_check_for(chat: int) -> Optional[int]:
    """Когда ближайшая проверка офисов этого человека."""
    times = []
    for s in store.subs_of(chat):
        if s["paused"]:
            continue
        key = (s["centro"], s["area"])
        if waits_for_data(key):
            continue
        chats = [x["chat"] for x in store.subs_for(*key) if not x["paused"]]
        times.append(offices.get(key, {}).get("tried", 0) + _intervals(chats or [chat]))
    return int(min(times)) if times else None


def per_office() -> float:
    """Секунд на проверку одного офиса вместе с паузами: в замер входит и ожидание очереди сессий."""
    avg = sum(durations) / len(durations) if durations else 25.0
    return max(avg + sum(PACE) / 2, dgt.SESSION_GAP * dgt._gate["slow"])


def capacity() -> dict:
    """Нагрузка: сколько офисов успеваем проверить за интервал."""
    avg = sum(durations) / len(durations) if durations else 25.0
    per = per_office()
    groups = store.key_groups()
    need = 0.0  # секунд работы в минуту
    for key, subs in groups.items():
        need += per / (every(key, [s["chat"] for s in subs]) / 60)
    paid_scale, free_scale = scales()
    return {"avg": avg, "per_office": per, "fits": int(600 // per), "offices": len(groups), "paid_scale": paid_scale, "free_scale": free_scale,
            "load": round(need / 60 * 100), "errors_hour": sum(1 for t in error_times if t > time.time() - 3600)}


def loop() -> None:
    time.sleep(15)
    while True:
        try:
            if store.setting("checks_paused"):
                time.sleep(20)
                continue
            if site_down():
                if time.time() >= status["probe_at"]:
                    probe()
                time.sleep(10)
                continue
            if time.time() < status["cool_until"]:
                time.sleep(5)
                continue
            keys = plan()
            if keys:
                run_checks(keys[:1])
                time.sleep(random.uniform(*PACE))
            else:
                time.sleep(5)
        except Exception:
            log.exception("ошибка очереди проверок")
            time.sleep(30)


def probe() -> None:
    """Проба при сбое: один лёгкий запрос, без обработки результатов."""
    with lock:
        try:
            dgt.list_centros()
            _site_ok()
        except Exception as e:
            _site_error(e)


def run_checks(keys: List[Tuple[str, str]], cards: Optional[Dict[int, Tuple[int, int]]] = None) -> None:
    """Проверяет офисы по очереди. cards: {chat: (message_id, номер действия)} — где показать карточку."""
    for i, (cid, area) in enumerate(keys):
        if i:
            time.sleep(random.uniform(*PACE))
        results, err = None, None
        started = time.time()
        with lock:
            offices.setdefault((cid, area), {"fails": 0})["tried"] = int(started)
            try:
                results = [r.__dict__ for r in dgt.check(cid, area)]
                status["checks"] += 1
                durations.append(time.time() - started)
                store.bump("checks")
                _site_ok()
                log.info("%s: %s", office_name(cid, area), [(r["status"], len(r["days"])) for r in results])
            except Exception as e:
                err = e
                log.warning("%s: ошибка %s", office_name(cid, area), type(e).__name__)
                _site_error(e)
        try:
            process(cid, area, results, err, cards or {})
        except Exception:
            log.exception("ошибка обработки результата")


def _show_card(chat: int, sub: dict, target: Tuple[int, int], note: str = "") -> None:
    if tg.same_screen(chat, target[1]):
        tg.show(chat, *views.card(sub, note), mid=target[0])


def process(cid: str, area: str, results: Optional[list], err, cards: Dict[int, Tuple[int, int]], fresh: bool = True) -> None:
    """fresh=False — результат взят из недавней проверки для другого человека: состояние офиса не трогаем."""
    name = office_name(cid, area)
    st = offices.setdefault((cid, area), {"fails": 0})
    if err is not None:
        st["fails"] += 1
    elif fresh:
        days = views.all_days(results)
        if days and not st.get("days"):
            event(f"🟢 Появились даты: {name} — {len(days)} дн.", "dates")
            channel.on_opened(cid, area)
        current = results[0]["status"] if results else dgt.UNKNOWN
        if current == dgt.UNKNOWN and not st.get("unknown"):
            st["unknown"] = True
            event(f"❔ Страница не распознана: {name}", "error")
            notify_admins(f"❔ <b>Страница DGT не распознана</b>\n{views.esc(name)}\nВозможно, сайт изменился.")
        elif current != dgt.UNKNOWN:
            st["unknown"] = False
        st.update(fails=0, status=current, days=len(days), at=int(time.time()), results=results)
        store.office_changed(cid, area, bool(days), len(days))

    now = int(time.time())
    subs = sorted(store.subs_for(cid, area), key=lambda s: not premium.is_premium(s["chat"]))
    for sub in subs:
        chat = sub["chat"]
        if store.get_chat(chat).get("role") in ("banned", "pending"):
            continue
        watching = chat in cards  # пользователь сам нажал «проверить» и смотрит на карточку
        if sub["paused"] and not watching:
            continue
        if err is not None:
            sub["fails"] = (sub["fails"] or 0) + 1
            store.update_sub(sub["id"], fails=sub["fails"])
            if watching:
                lang = views.lang_of(chat)
                _show_card(chat, sub, cards[chat], views.tx(lang, "⚠️ <i>Сайт DGT не ответил — попробую позже.</i>",
                                                            "⚠️ <i>Сайт DGT не відповів — спробую пізніше.</i>",
                                                                  "⚠️ <i>La web de la DGT no ha respondido; volveré a intentarlo más tarde.</i>",
                                                                  "⚠️ <i>The DGT website didn't respond; I'll try again later.</i>"))
            continue

        prev_days = {iso for iso, _ in views.all_days(sub["last"], sub["max_days"])}
        now_days = {iso for iso, _ in views.all_days(results, sub["max_days"])}
        new = now_days - prev_days
        sub.update(last=results, checked_at=now, fails=0)
        store.update_sub(sub["id"], last=results, checked_at=now, fails=0)

        if watching:
            _show_card(chat, sub, cards[chat])
        elif sub["paused"]:
            continue
        elif new and not gate.allowed(chat):  # вышел из канала: уведомление не шлём, раз в сутки напоминаем почему
            if gate.nudge_due(chat):
                gate.shown(chat, tg.show(chat, *views.gate_view(chat, missed=True), banner=views.banner("gate")))
        elif new:
            tg.delete(chat, sub.get("alert_msg"))  # в чате остаётся только свежее уведомление
            mid = tg.send(chat, *views.alert(sub, results, new), silent=is_quiet(chat), effect="fire")
            store.update_sub(sub["id"], alert_msg=mid)
            status["alerts"] += 1
            store.bump("alerts")
            store.bump_chat(chat, "alerts")
        elif prev_days and not now_days and sub.get("alert_msg"):
            tg.edit(chat, sub["alert_msg"], *views.gone(sub))  # не новое сообщение, а правка старого


# ---------- напоминания и обслуживание ----------

def reminders() -> None:
    """Напоминания о визите: накануне в 19:00 и утром в день визита."""
    while True:
        try:
            send_reminders()
            send_windows()
            send_canje()
        except Exception:
            log.exception("ошибка напоминаний")
        time.sleep(300)


def channel_loop() -> None:
    """Посты о датах в канале: готовый пост проверяем раз в минуту."""
    while True:
        time.sleep(60)
        try:
            channel.tick(offices)
            group.sweep()
        except Exception:
            log.exception("ошибка канала")


def send_windows() -> None:
    """Просьбы проверить сайт записи самому в выбранные часы. Бот к этому сайту не обращается."""
    now = datetime.now(config.TZ)
    stamp = (store.today_key(), now.hour)
    for c in store.all_chats():
        chat = c["chat"]
        if not c.get("windows") or _window_sent.get(chat) == stamp or c.get("role") in ("banned", "pending"):
            continue
        hours = signals.windows_of(chat)[:signals.window_limit(chat)]
        if now.hour in hours and signals.subs_of(chat):
            _window_sent[chat] = stamp
            tg.delete(chat, _window_msg.pop(chat, None))
            mid = tg.send(chat, *views.window_alert(chat), silent=is_quiet(chat))
            if mid:
                _window_msg[chat] = mid


def send_canje(now: Optional[float] = None) -> None:
    """Через CANJE_WAIT дней после заявки на canje — напомнить проверить ответ DGT. Один раз, дальше по кнопке."""
    now = now or time.time()
    for c in store.all_chats():
        at = c.get("canje_at") or 0
        if not at or now - at < views.CANJE_WAIT * 86400 or c.get("role") in ("banned", "pending"):
            continue
        store.set_chat(c["chat"], canje_at=0)
        tg.send(c["chat"], *views.canje_reminder(c["chat"]), silent=is_quiet(c["chat"]))


def send_reminders() -> None:
    now = datetime.now(config.TZ)
    for sub in store.all_subs():
        if not sub.get("booked_date") or store.get_chat(sub["chat"]).get("role") in ("banned", "pending"):
            continue
        day, bits = date.fromisoformat(sub["booked_date"]), sub.get("reminded") or 0
        if day - timedelta(days=1) == now.date() and now.hour >= 19 and not bits & 1:
            when, bits = "eve", bits | 1
        elif day == now.date() and now.hour >= 8 and not bits & 2:
            when, bits = "day", bits | 3
            if sub.get("booked_time") and sub["booked_time"] <= now.strftime("%H:%M"):
                store.update_sub(sub["id"], reminded=bits)  # визит уже прошёл — не напоминаем
                continue
        elif reviews.ask_due(sub, now):
            when, bits = "review", bits | 7
        else:
            continue
        tg.delete(sub["chat"], sub.get("alert_msg"))
        mid = tg.send(sub["chat"], *(views.review_ask(sub) if when == "review" else views.reminder(sub, when)), silent=when == "review",
                      effect="like" if when == "day" else None)
        store.update_sub(sub["id"], reminded=bits, alert_msg=mid)


def daily_report_text() -> str:
    day = store.today_key()
    m = lambda k: store.metric(day, k)  # noqa: E731
    chats = store.all_chats()
    cap = capacity()
    premium_now = sum(1 for c in chats if (c.get("premium_until") or 0) > time.time())
    return (f"📊 <b>Итоги дня</b> · {datetime.now(config.TZ):%d.%m}\n\n<blockquote>"
            f"👥 Новых пользователей: <b>{m('new_users')}</b> (всего {len(chats)})\n"
            f"💎 Premium сейчас: <b>{premium_now}</b> · оплат: {m('payments')} на {m('stars')} ⭐\n"
            f"➕ Новых подписок: {m('subs')}\n"
            f"🔔 Уведомлений: <b>{m('alerts')}</b> · ✅ записались: <b>{m('bookings')}</b>\n"
            f"🎁 Промокодов: {m('promo_used')} · заданий: {m('tasks_done')} · друзей: {m('ref_activated')}\n"
            f"📡 Радаров: {m('radar')}\n"
            f"🔎 Проверок: {m('checks')} · ошибок сайта: {m('errors')}</blockquote>\n"
            f"⚙️ Загрузка очереди: {cap['load']}% · ждут: {status['backlog']}"
            + ("\n🛑 Сайт DGT сейчас недоступен" if site_down() else ""))


def housekeeping() -> None:
    """Раз в 5 минут: окончание Premium, статистика раз в час, вечерний отчёт в 21:00."""
    last_flush = time.time()
    while True:
        time.sleep(300)
        try:
            for chat, kind, until in premium.scan_expiring():
                paused = premium.expired_cleanup(chat) if kind == "over" else 0
                tg.send(chat, *views.premium_notice(chat, kind, until, paused))
            if time.time() - last_flush > 3600:
                store.flush_metrics()
                last_flush = time.time()
            now = datetime.now(config.TZ)
            if store.setting("daily_report") and now.hour >= 21 and store.setting("last_report") != store.today_key():
                store.set_setting("last_report", store.today_key())
                store.flush_metrics()
                for owner in config.OWNERS:
                    tg.send(owner, daily_report_text(), tg.ikb([[tg.btn("🛠 Админ-панель", "ad"), tg.btn("✖️ Скрыть", "hide")]]),
                            silent=True)
        except Exception:
            log.exception("ошибка обслуживания")


def keepalive() -> None:
    """Бесплатный Render усыпляет сервис без входящих запросов — стучимся к себе раз в 9 минут."""
    while True:
        time.sleep(9 * 60)
        try:
            requests.get(config.PUBLIC_URL + "/health", timeout=30)
        except requests.RequestException as e:
            log.warning("keepalive: %s", type(e).__name__)


def refresh_centros() -> None:
    try:
        started = time.time()
        fresh = dgt.list_centros()
        log.info("сайт DGT доступен (%.1f с), офисов: %d", time.time() - started, len(fresh))
        added = set(fresh) - set(dgt.CENTROS)
        dgt.CENTROS.update(fresh)
        if added:
            event("🏢 Новые офисы на сайте: " + ", ".join(fresh[c] for c in added))
    except Exception as e:
        log.warning("список офисов не обновился: %s\n%s", type(e).__name__, diagnose())


views.outage = site_down
