"""Фоновые проверки сайта DGT, уведомления пользователям и сигналы админам."""
from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests

import config
import dgt
import store
import tg
import views

log = logging.getLogger("checker")

lock = threading.Lock()  # к сайту DGT ходим строго по очереди
status = {"started": int(time.time()), "last_cycle": None, "cycle_secs": 0, "next_cycle": None,
          "cycles": 0, "checks": 0, "errors": 0, "alerts": 0, "last_ok": None, "cooldown_until": 0,
          "queued": 0}
durations: deque = deque(maxlen=50)         # сколько секунд заняли последние проверки
error_times: deque = deque(maxlen=200)      # когда были ошибки сайта — для «ошибок за час»
offices: Dict[Tuple[str, str], dict] = {}   # последний результат по каждому офису
journal: deque = deque(maxlen=300)          # события для админки (с последнего запуска)
BREAKER_ERRORS = 5                           # столько ошибок подряд — сайт, видимо, нас притормозил
BREAKER_PAUSE = 15 * 60


def event(text: str, kind: str = "info") -> None:
    """kind: info | user | dates | error — для фильтра журнала в админке."""
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


def run_checks(keys: List[Tuple[str, str]], cards: Optional[Dict[int, int]] = None) -> None:
    """Проверяет офисы по очереди. cards: {chat: message_id} — где показать карточку после проверки."""
    streak = 0
    with lock:
        for i, (cid, area) in enumerate(keys):
            if i:
                time.sleep(random.uniform(4, 10))
            if time.time() < status["cooldown_until"] and not cards:
                break  # сайт недавно отвечал ошибками — даём ему отдохнуть
            results, err = None, None
            started = time.time()
            try:
                results = [r.__dict__ for r in dgt.check(cid, area)]
                status["checks"] += 1
                status["last_ok"] = int(time.time())
                durations.append(time.time() - started)
                store.bump("checks")
                streak = 0
                log.info("%s: %s", office_name(cid, area), [(r["status"], len(r["days"])) for r in results])
            except Exception as e:
                err = e
                status["errors"] += 1
                error_times.append(time.time())
                store.bump("errors")
                streak += 1
                log.warning("%s: ошибка %r", office_name(cid, area), e)
                if streak >= BREAKER_ERRORS:
                    status["cooldown_until"] = time.time() + BREAKER_PAUSE
                    event(f"🧯 {streak} ошибок сайта подряд — пауза проверок на 15 мин", "error")
                    notify_admins(f"🧯 <b>Сайт DGT {streak} раз подряд не ответил</b>\n"
                                  "Ставлю проверки на паузу на 15 минут, чтобы нас не заблокировали.")
            try:
                process(cid, area, results, err, cards or {})
            except Exception:
                log.exception("ошибка обработки результата")


def process(cid: str, area: str, results: Optional[list], err, cards: Dict[int, int]) -> None:
    name = office_name(cid, area)
    st = offices.setdefault((cid, area), {"fails": 0})
    if err is not None:
        st["fails"] += 1
        if st["fails"] == 3:
            event(f"⚠️ Сайт не отвечает: {name}", "error")
            notify_admins(f"⚠️ <b>Сайт DGT не отвечает</b>\n{views.esc(name)} — 3 проверки подряд.\n"
                          f"<code>{views.esc(repr(err))[:200]}</code>")
    else:
        if st["fails"] >= 3:
            event(f"✅ Сайт снова отвечает: {name}", "error")
            notify_admins(f"✅ Сайт DGT снова отвечает ({views.esc(name)}).")
        days = views.all_days(results)
        if days and not st.get("days"):
            event(f"🟢 Появились даты: {name} — {len(days)} дн.", "dates")
        st.update(fails=0, status=results[0]["status"] if results else dgt.UNKNOWN, days=len(days),
                  at=int(time.time()), results=results)
        store.office_changed(cid, area, bool(days), len(days))

    now = int(time.time())
    for sub in store.subs_for(cid, area):
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
                tg.show(chat, *views.card(sub, "⚠️ <i>Сайт DGT не ответил — попробую при следующей проверке.</i>"),
                        mid=cards[chat])
            continue

        prev_days = {iso for iso, _ in views.all_days(sub["last"], sub["max_days"])}
        now_days = {iso for iso, _ in views.all_days(results, sub["max_days"])}
        new = now_days - prev_days
        sub.update(last=results, checked_at=now, fails=0)
        store.update_sub(sub["id"], last=results, checked_at=now, fails=0)

        if watching:
            tg.show(chat, *views.card(sub), mid=cards[chat])
        elif sub["paused"]:
            continue
        elif new:
            tg.delete(chat, sub.get("alert_msg"))  # в чате остаётся только свежее уведомление
            mid = tg.send(chat, *views.alert(sub, results, new), silent=is_quiet(chat))
            store.update_sub(sub["id"], alert_msg=mid)
            status["alerts"] += 1
            store.bump("alerts")
            store.bump_chat(chat, "alerts")
        elif prev_days and not now_days and sub.get("alert_msg"):
            tg.edit(chat, sub["alert_msg"], *views.gone(sub))  # не новое сообщение, а правка старого


def loop() -> None:
    time.sleep(20)
    while True:
        started = time.time()
        if not store.setting("checks_paused") and time.time() >= status["cooldown_until"]:
            try:
                keys = queue()
                if keys:
                    run_checks(keys)
                status["last_cycle"] = int(time.time())
                status["cycle_secs"] = int(time.time() - started)
                status["cycles"] += 1
            except Exception:
                log.exception("ошибка цикла проверки")
        wait = max(60.0, int(store.setting("interval")) * 60 * random.uniform(0.9, 1.1) - (time.time() - started))
        status["next_cycle"] = int(time.time() + wait)
        time.sleep(wait)


def queue() -> List[Tuple[str, str]]:
    """Офисы на этот цикл. Если их больше лимита — сначала те, что дольше всех не проверялись,
    при равенстве — популярные. Так при перегрузке все офисы проверяются по кругу, а не часть навсегда."""
    keys, popular = store.active_keys(), store.popularity()
    keys.sort(key=lambda k: (offices.get(k, {}).get("at", 0), -popular.get(k, 0)))
    status["queued"] = max(0, len(keys) - config.MAX_OFFICES)
    return keys[:config.MAX_OFFICES]


def capacity() -> dict:
    """Нагрузка: сколько офисов успеваем проверить за один интервал."""
    avg = sum(durations) / len(durations) if durations else 12.0
    per_office = avg + 7  # + пауза между офисами
    interval = int(store.setting("interval")) * 60
    return {"avg": avg, "per_office": per_office, "fits": int(interval // per_office),
            "load": min(999, round(status["cycle_secs"] / interval * 100)) if status["cycle_secs"] else 0,
            "errors_hour": sum(1 for t in error_times if t > time.time() - 3600)}


def daily_report_text() -> str:
    day = store.today_key()
    m = lambda k: store.metric(day, k)  # noqa: E731
    chats = store.all_chats()
    cap = capacity()
    return (f"📊 <b>Итоги дня</b> · {datetime.now(config.TZ):%d.%m}\n\n<blockquote>"
            f"👥 Новых пользователей: <b>{m('new_users')}</b> (всего {len(chats)})\n"
            f"➕ Новых подписок: {m('subs')}\n"
            f"🔔 Уведомлений: <b>{m('alerts')}</b>\n"
            f"✅ Записались: <b>{m('bookings')}</b>\n"
            f"📡 Радаров: {m('radar')}\n"
            f"🔎 Проверок: {m('checks')} · ошибок сайта: {m('errors')}</blockquote>\n"
            f"⚙️ Нагрузка цикла: {cap['load']}% · в очереди: {status['queued']}")


def housekeeping() -> None:
    """Раз в 5 минут: сохранить статистику раз в час, отправить вечерний отчёт в 21:00."""
    last_flush = time.time()
    while True:
        time.sleep(300)
        try:
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


def reminders() -> None:
    """Напоминания о визите: накануне в 19:00 и утром в день визита."""
    while True:
        try:
            send_reminders()
        except Exception:
            log.exception("ошибка напоминаний")
        time.sleep(300)


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
        else:
            continue
        tg.delete(sub["chat"], sub.get("alert_msg"))
        mid = tg.send(sub["chat"], *views.reminder(sub, when))
        store.update_sub(sub["id"], reminded=bits, alert_msg=mid)


def keepalive() -> None:
    """Бесплатный Render усыпляет сервис без входящих запросов — стучимся к себе раз в 9 минут."""
    while True:
        time.sleep(9 * 60)
        try:
            requests.get(config.PUBLIC_URL + "/health", timeout=30)
        except Exception as e:
            log.warning("keepalive: %r", e)


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
        log.warning("список офисов не обновился: %r", e)
