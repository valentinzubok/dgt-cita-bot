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

import config
import dgt
import premium
import store
import tg
import views

log = logging.getLogger("checker")

lock = threading.Lock()  # к сайту DGT ходим строго по очереди
status = {"started": int(time.time()), "last_ok": None, "checks": 0, "errors": 0, "alerts": 0, "streak": 0,
          "down_since": None, "probe_at": 0, "probes": 0, "backlog": 0, "due_next": None}
durations: deque = deque(maxlen=50)         # сколько секунд заняли последние проверки
error_times: deque = deque(maxlen=200)      # когда были ошибки сайта — для «ошибок за час»
offices: Dict[Tuple[str, str], dict] = {}   # последний результат по каждому офису
journal: deque = deque(maxlen=300)          # события для админки (с последнего запуска)
DOWN_AFTER = 3                               # столько ошибок подряд — считаем, что сайт недоступен
PROBE_MIN, PROBE_MAX = 5 * 60, 60 * 60       # пауза между пробами при сбое: от 5 минут до часа
PACE = (8, 14)                               # пауза между офисами, секунд


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
    status["streak"] = 0
    status["last_ok"] = int(time.time())
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
    if site_down():
        status["probes"] += 1
        status["probe_at"] = time.time() + min(PROBE_MAX, PROBE_MIN * 2 ** status["probes"])
    elif status["streak"] >= DOWN_AFTER:
        status.update(down_since=int(time.time()), probes=0, probe_at=time.time() + PROBE_MIN)
        report = diagnose()
        log.warning("сайт DGT недоступен: %r\n%s", err, report)
        event("🛑 Сайт DGT недоступен с сервера — проверки перешли в редкие пробы", "error")
        notify_admins("🛑 <b>Сайт DGT недоступен с сервера</b>\n"
                      "Проверки перешли в редкие пробы (от 5 минут до часа), пользователи видят предупреждение, "
                      f"оплата закрыта.\n\n<pre>{views.esc(report)}</pre>", silent=False)


# ---------- очередь ----------

def _intervals(chats: List[int]) -> int:
    key = "interval_premium" if any(premium.is_premium(c) for c in chats) else "interval"
    return int(store.setting(key)) * 60


def plan() -> List[Tuple[str, str]]:
    """Офисы, которым пора на проверку: сначала Premium, затем те, что ждут дольше всех."""
    now = time.time()
    due, soonest = [], None
    groups = store.key_groups()
    for key, subs in groups.items():
        every = _intervals([s["chat"] for s in subs])
        last = offices.get(key, {}).get("tried", 0)
        wait = last + every - now
        if wait <= 0:
            is_paid = every == int(store.setting("interval_premium")) * 60
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
        chats = [x["chat"] for x in store.subs_for(*key) if not x["paused"]]
        times.append(offices.get(key, {}).get("tried", 0) + _intervals(chats or [chat]))
    return int(min(times)) if times else None


def capacity() -> dict:
    """Нагрузка: сколько офисов успеваем проверить за интервал."""
    avg = sum(durations) / len(durations) if durations else 11.0
    per_office = avg + sum(PACE) / 2
    groups = store.key_groups()
    need = 0.0  # секунд работы в минуту
    for subs in groups.values():
        need += per_office / (_intervals([s["chat"] for s in subs]) / 60)
    return {"avg": avg, "per_office": per_office, "fits": int(600 // per_office), "offices": len(groups),
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


def process(cid: str, area: str, results: Optional[list], err, cards: Dict[int, Tuple[int, int]]) -> None:
    name = office_name(cid, area)
    st = offices.setdefault((cid, area), {"fails": 0})
    if err is not None:
        st["fails"] += 1
    else:
        days = views.all_days(results)
        if days and not st.get("days"):
            event(f"🟢 Появились даты: {name} — {len(days)} дн.", "dates")
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
                                                            "⚠️ <i>Сайт DGT не відповів — спробую пізніше.</i>"))
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
        elif new:
            tg.delete(chat, sub.get("alert_msg"))  # в чате остаётся только свежее уведомление
            mid = tg.send(chat, *views.alert(sub, results, new), silent=is_quiet(chat))
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
