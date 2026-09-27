"""Фоновые проверки сайта DGT, уведомления пользователям и сигналы админам."""
from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from datetime import datetime
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
          "cycles": 0, "checks": 0, "errors": 0, "alerts": 0}
offices: Dict[Tuple[str, str], dict] = {}   # последний результат по каждому офису
journal: deque = deque(maxlen=100)          # события для админки (с последнего запуска)


def event(text: str) -> None:
    journal.appendleft((int(time.time()), text))
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
    with lock:
        for i, (cid, area) in enumerate(keys):
            if i:
                time.sleep(random.uniform(4, 10))
            results, err = None, None
            try:
                results = [r.__dict__ for r in dgt.check(cid, area)]
                status["checks"] += 1
                log.info("%s: %s", office_name(cid, area), [(r["status"], len(r["days"])) for r in results])
            except Exception as e:
                err = e
                status["errors"] += 1
                log.warning("%s: ошибка %r", office_name(cid, area), e)
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
            event(f"⚠️ Сайт не отвечает: {name}")
            notify_admins(f"⚠️ <b>Сайт DGT не отвечает</b>\n{views.esc(name)} — 3 проверки подряд.\n"
                          f"<code>{views.esc(repr(err))[:200]}</code>")
    else:
        if st["fails"] >= 3:
            event(f"✅ Сайт снова отвечает: {name}")
            notify_admins(f"✅ Сайт DGT снова отвечает ({views.esc(name)}).")
        days = views.all_days(results)
        if days and not st.get("days"):
            event(f"🟢 Появились даты: {name} — {len(days)} дн.")
        st.update(fails=0, status=results[0]["status"] if results else dgt.UNKNOWN, days=len(days),
                  at=int(time.time()))
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
        elif prev_days and not now_days and sub.get("alert_msg"):
            tg.edit(chat, sub["alert_msg"], *views.gone(sub))  # не новое сообщение, а правка старого


def loop() -> None:
    time.sleep(20)
    while True:
        started = time.time()
        if not store.setting("checks_paused"):
            try:
                keys = store.active_keys()[:config.MAX_OFFICES]
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
