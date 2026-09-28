"""Админ-панель: обзор, аналитика, система, пользователи, офисы, рассылка, экспорт, настройки, журнал."""
from __future__ import annotations

import csv
import io
import logging
import math
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import checker
import config
import dgt
import store
import tg
import views
from tg import btn, ikb
from views import esc, fmt_ts, plural

log = logging.getLogger("admin")

pending: Dict[int, dict] = {}  # ждём от админа сообщение: рассылка, письмо пользователю, поиск
UPAGE = 8
BACK = btn("⬅️ Админ-панель", "ad")
HOME = views.home_btn("ru")
ROLE_TEXT = {"user": "пользователь", "admin": "⭐️ админ", "banned": "🚫 заблокирован", "pending": "⏳ ждёт одобрения"}
SEGMENTS = {
    "all": "👥 Всем",
    "ru": "🇷🇺 Русский язык",
    "uk": "🇺🇦 Украинский язык",
    "subs": "📋 С подписками",
    "nosubs": "💤 Без подписок",
}
JOURNAL = {"all": "Все", "error": "⚠️ Ошибки", "user": "👤 Люди", "dates": "🟢 Даты"}


def uname(c: dict) -> str:
    name = esc(c.get("name") or "без имени")
    return name + (f" @{esc(c['username'])}" if c.get("username") else "")


def badge(c: dict) -> str:
    if c["chat"] in config.OWNERS:
        return "👑 "
    return {"admin": "⭐️ ", "banned": "🚫 ", "pending": "⏳ "}.get(c.get("role"), "")


def bar(n: int, top: int, width: int = 10) -> str:
    return "▇" * max(1 if n else 0, round(n / top * width)) if top else ""


# ---------- обзор ----------

def panel() -> Tuple[str, dict]:
    chats, subs, keys = store.all_chats(), store.all_subs(), store.active_keys()
    now = time.time()
    s, day = checker.status, store.today_key()
    active_week = sum(1 for c in chats if (c.get("last_seen") or 0) > now - 7 * 86400)
    open_now = sum(1 for k in keys if checker.offices.get(k, {}).get("days"))
    waiting = sum(1 for c in chats if c.get("role") == "pending")
    if store.setting("maintenance"):
        state = "🛠 режим обслуживания"
    elif store.setting("checks_paused"):
        state = "⏸ проверки остановлены"
    elif now < s["cooldown_until"]:
        state = f"🧯 пауза до {datetime.fromtimestamp(s['cooldown_until'], config.TZ):%H:%M}"
    else:
        state = "✅ работает"
    text = (
        "🛠 <b>Админ-панель</b>\n\n"
        f"<b>Сегодня</b>\n<blockquote>"
        f"👤 Новых: <b>{store.metric(day, 'new_users')}</b> · ➕ подписок: {store.metric(day, 'subs')}\n"
        f"🔔 Уведомлений: <b>{store.metric(day, 'alerts')}</b> · ✅ записались: <b>{store.metric(day, 'bookings')}</b>\n"
        f"📡 Радаров: {store.metric(day, 'radar')} · 🔎 проверок: {store.metric(day, 'checks')}</blockquote>\n"
        f"<b>Всего</b>\n<blockquote>"
        f"👥 Пользователей: <b>{len(chats)}</b> · активны за неделю: {active_week}\n"
        f"📋 Подписок: <b>{len(subs)}</b> · офисов в проверке: {len(keys)}/{config.MAX_OFFICES}\n"
        f"🟢 Офисов с датами сейчас: <b>{open_now}</b>"
        + (f"\n🙋 Ждут одобрения: <b>{waiting}</b>" if waiting else "")
        + f"</blockquote>\nСостояние: {state}"
    )
    return text, ikb([
        [btn("📈 Аналитика", "ad:an"), btn("🩺 Система", "ad:sy")],
        [btn("👥 Пользователи", "ad:u:0"), btn("🏢 Офисы", "ad:o")],
        [btn("📢 Рассылка", "ad:b"), btn("📤 Экспорт", "ad:x")],
        [btn("⚙️ Настройки", "ad:s"), btn("📜 Журнал", "ad:l:all")],
        [btn("🔄 Обновить", "ad"), HOME],
    ])


def analytics() -> Tuple[str, dict]:
    chats, subs = store.all_chats(), store.all_subs()
    today = datetime.now(config.TZ).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    keys = ("new_users", "subs", "alerts", "bookings", "radar")
    rows = [(d, [store.metric(d, k) for k in keys]) for d in days]
    top = max([r[1][0] for r in rows] + [1])
    table = ["день   нов подп увед зап рад"]
    for d, vals in rows:
        table.append(f"{d[8:10]}.{d[5:7]}  " + " ".join(f"{v:>4}" for v in vals))
    totals = [sum(r[1][i] for r in rows) for i in range(len(keys))]
    table.append("7 дн.  " + " ".join(f"{v:>4}" for v in totals))
    chart = "\n".join(f"{d[8:10]}.{d[5:7]} {bar(v[0], top)} {v[0]}" for d, v in rows)

    with_lang = sum(1 for c in chats if c.get("lang"))
    with_subs = len({s["chat"] for s in subs})
    alerted = sum(1 for c in chats if (c.get("alerts") or 0) > 0)
    booked = sum(1 for c in chats if (c.get("bookings") or 0) > 0)
    pct = lambda n: f"{round(n / len(chats) * 100)}%" if chats else "—"  # noqa: E731
    uk = sum(1 for c in chats if c.get("lang") == "uk")

    sources: Dict[str, int] = {}
    for c in chats:
        sources[c.get("source") or "без метки"] = sources.get(c.get("source") or "без метки", 0) + 1
    src_lines = [f"{esc(k)} — {v}" for k, v in sorted(sources.items(), key=lambda kv: -kv[1])[:8]]
    popular = sorted(store.popularity().items(), key=lambda kv: -kv[1])[:5]
    top_lines = [f"{i + 1}. {esc(views.city(cid))} · {esc(views.area_label(area))} — 👥 {n}"
                 for i, ((cid, area), n) in enumerate(popular)] or ["пока пусто"]
    text = (
        "📈 <b>Аналитика</b>\n\n"
        "<b>За 7 дней</b>\n<pre>" + "\n".join(table) + "</pre>\n"
        "<b>Новые пользователи</b>\n<pre>" + chart + "</pre>\n"
        "<b>Воронка</b> (все пользователи)\n<blockquote>"
        f"👥 Запустили бота: <b>{len(chats)}</b>\n"
        f"🌐 Выбрали язык: {with_lang} · {pct(with_lang)}\n"
        f"📋 Подписались: <b>{with_subs}</b> · {pct(with_subs)}\n"
        f"🔔 Получили уведомление: {alerted} · {pct(alerted)}\n"
        f"✅ Записались: <b>{booked}</b> · {pct(booked)}</blockquote>\n"
        f"🌐 Языки: 🇺🇦 {uk} · 🇷🇺 {with_lang - uk} · не выбран {len(chats) - with_lang}\n\n"
        "<b>Топ офисов по подпискам</b>\n<blockquote>" + "\n".join(top_lines) + "</blockquote>\n"
        "<b>Откуда пришли</b> (ссылка t.me/oksitabot?start=метка)\n<blockquote>" + "\n".join(src_lines) + "</blockquote>\n"
        "<i>нов — новые пользователи, подп — подписки, увед — уведомления, зап — записались, рад — радары.</i>"
    )
    return text, ikb([[btn("🔄 Обновить", "ad:an"), BACK]])


def memory_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    import resource
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 1024 / (1024 if rss > 10 ** 7 else 1)


def system() -> Tuple[str, dict]:
    s, cap, now = checker.status, checker.capacity(), time.time()
    interval = int(store.setting("interval"))
    hook = (tg.call("getWebhookInfo") or {}).get("result")
    hook = hook if isinstance(hook, dict) else {}
    site = (f"🟢 Сайт DGT отвечал {fmt_ts(s['last_ok'])}" if s["last_ok"] else "⏳ Сайт DGT ещё не проверялся")
    if now < s["cooldown_until"]:
        site += f"\n🧯 Пауза после ошибок до {datetime.fromtimestamp(s['cooldown_until'], config.TZ):%H:%M}"
    version = os.environ.get("RENDER_GIT_COMMIT", "")[:7] or "локально"
    text = (
        "🩺 <b>Система</b>\n\n<b>Проверки DGT</b>\n<blockquote>"
        f"{site}\n"
        f"⏱ Средняя проверка: {cap['avg']:.1f} с · за {interval} мин успеваем ~{cap['fits']} офисов\n"
        f"📦 Офисов в работе: {len(store.active_keys())}/{config.MAX_OFFICES} · ждут очереди: {s['queued']}\n"
        f"⚙️ Нагрузка цикла: {cap['load']}% ({s['cycle_secs']} с из {interval * 60})\n"
        f"⚠️ Ошибок сайта за час: {cap['errors_hour']} · всего с запуска: {s['errors']}</blockquote>\n"
        "<b>Сервер</b>\n<blockquote>"
        f"💾 Память: {memory_mb():.0f} МБ из 512 · потоков: {threading.active_count()}\n"
        f"🌐 Webhook: в очереди {hook.get('pending_update_count', '?')} · "
        f"{'ошибка: ' + esc(hook['last_error_message']) if hook.get('last_error_message') else 'ошибок нет'}\n"
        f"🗄 База: {'Postgres (Neon)' if store.PG else 'SQLite'} · статистика пишется раз в час\n"
        f"🚀 Версия: {version} · работает {views.fmt_dur(now - s['started'])}</blockquote>\n"
        "<i>Бесплатные лимиты: Render — 0.15 CPU, 512 МБ, 750 ч/мес; Neon — 0.5 ГБ.\n"
        "Узкое место — не сервер, а сайт DGT: он тормозит при частых запросах.</i>"
    )
    return text, ikb([[btn("🔄 Обновить", "ad:sy"), BACK]])


# ---------- пользователи ----------

def users(page: int = 0, found: Optional[List[dict]] = None, query: str = "") -> Tuple[str, dict]:
    chats = found if found is not None else store.all_chats()
    pages = max(1, math.ceil(len(chats) / UPAGE))
    page %= pages
    rows = []
    for c in chats[page * UPAGE:(page + 1) * UPAGE]:
        n = len(store.subs_of(c["chat"]))
        rows.append([btn(f"{badge(c)}{c.get('name') or c['chat']} · {plural(n, 'подписка', 'подписки', 'подписок')}",
                         f"ad:uc:{c['chat']}")])
    if pages > 1 and found is None:
        rows.append([btn("◀️", f"ad:u:{page - 1}"), btn(f"{page + 1} / {pages}", "noop"), btn("▶️", f"ad:u:{page + 1}")])
    rows.append([btn("🔎 Найти", "ad:uf"), BACK])
    if found is not None:
        head = f"🔎 <b>Поиск «{esc(query)}»</b> · найдено {len(found)}"
    else:
        head = f"👥 <b>Пользователи</b> · {len(chats)}"
    return (f"{head}\n\n👑 владелец · ⭐️ админ · 🚫 заблокирован · ⏳ ждёт одобрения\n"
            "<i>Сначала новые. Нажми на пользователя — откроется карточка.</i>"), ikb(rows)


def user_card(target: int, viewer: int, note: str = "") -> Tuple[str, dict]:
    c = store.get_chat(target)
    subs = store.subs_of(target)
    role = "👑 владелец" if target in config.OWNERS else ROLE_TEXT.get(c.get("role"), c.get("role"))
    joined = datetime.fromtimestamp(c["created_at"], config.TZ).strftime("%d.%m.%Y") if c.get("created_at") else "—"
    lines = [f"👤 <b>{uname(c)}</b>",
             "<blockquote>"
             f"🆔 <code>{target}</code> · 🎭 {role}\n"
             f"🌐 Язык: {views.LANGS.get(c.get('lang') or '', 'не выбран')}"
             + (f" · 🔗 {esc(c['source'])}" if c.get("source") else "") + "\n"
             f"📅 С нами с {joined} · 👀 был {fmt_ts(c['last_seen']) if c.get('last_seen') else '—'}\n"
             f"🔔 Уведомлений получил: {c.get('alerts') or 0} · ✅ записывался: {c.get('bookings') or 0}"
             "</blockquote>"]
    if subs:
        lines.append(f"📋 <b>Подписки</b> · {len(subs)}")
        lines.append("<blockquote>" + "\n".join(f"{views.summary(s, 'ru')[0]} {views.title(s)} — {views.summary(s, 'ru')[1]}"
                                                 for s in subs) + "</blockquote>")
    else:
        lines.append("Подписок нет.")
    if note:
        lines.append(f"\n{note}")

    rows = []
    if c.get("role") == "pending":
        rows.append([btn("✅ Одобрить", f"ad:ap:{target}"), btn("🚫 Отклонить", f"ad:ar:{target}")])
    rows.append([btn("✉️ Написать", f"ad:um:{target}")])
    protected = target in config.OWNERS or target == viewer
    if not protected:
        banned = c.get("role") == "banned"
        rows[-1].append(btn("✅ Разблокировать" if banned else "🚫 Заблокировать", f"ad:ub:{target}"))
    for s in subs[:5]:
        rows.append([btn(f"🗑 {views.plain_title(s)}", f"ad:sx:{s['id']}")])
    if len(subs) > 1:
        rows.append([btn("🗑 Удалить все подписки", f"ad:ux:{target}")])
    if viewer in config.OWNERS and not protected and c.get("role") in ("user", "admin"):
        rows.append([btn("⭐️ Снять админа" if c.get("role") == "admin" else "⭐️ Сделать админом", f"ad:ua:{target}")])
    rows.append([btn("⬅️ Пользователи", "ad:u:0"), BACK])
    return "\n".join(lines), ikb(rows)


# ---------- офисы ----------

def office_emoji(st: dict, blocked: bool = False) -> str:
    if blocked:
        return "⛔️"
    if st.get("fails", 0) >= 3:
        return "⚠️"
    if st.get("days"):
        return "🟢"
    return {dgt.FULL: "🔴", dgt.NO_AREA: "⚪️", dgt.NOT_CONFIGURED: "⚪️"}.get(st.get("status"), "⏳")


def offices_view() -> Tuple[str, dict]:
    groups: Dict[Tuple[str, str], list] = {}
    for s in store.all_subs():
        groups.setdefault((s["centro"], s["area"]), []).append(s)
    blocked = store.blocked_keys()
    rows = []
    for (cid, area), ss in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        st = checker.offices.get((cid, area), {})
        active = sum(1 for s in ss if not s["paused"])
        label = views.area_label(area, ss[0].get("area_label"))
        rows.append([btn(f"{office_emoji(st, (cid, area) in blocked)} {views.city(cid)} · {label} — 👥 {active}",
                         f"ad:oc:{cid}:{area}")])
    rows.append([BACK])
    text = ("🏢 <b>Офисы под наблюдением</b> · " + str(len(groups)) + "\n\n"
            "🟢 есть даты · 🔴 мест нет · ⚪️ нет такой записи · ⚠️ сайт не отвечает · ⛔️ отключён · ⏳ не проверялся\n"
            "<i>👥 — сколько человек следят (без пауз).</i>") if groups else "🏢 Пока никто ни на что не подписан."
    return text, ikb(rows)


def office_card(cid: str, area: str, note: str = "") -> Tuple[str, dict]:
    ss = store.subs_for(cid, area)
    st = checker.offices.get((cid, area), {})
    blocked = (cid, area) in store.blocked_keys()
    label = views.area_label(area, ss[0].get("area_label") if ss else None)
    lines = [f"🏢 <b>{esc(views.city(cid))}</b> · {views.area_emoji(label)} {esc(label)}",
             f"<i>{esc(dgt.CENTROS.get(cid, cid))}</i>", ""]
    if blocked:
        lines.append("⛔️ <b>Проверка отключена администратором</b>")
    if st.get("at"):
        state = f"{st['days']} свободных дней" if st.get("days") else {
            dgt.FULL: "мест нет", dgt.NO_AREA: "такой записи в офисе нет",
            dgt.NOT_CONFIGURED: "офис не принимает эту запись"}.get(st.get("status"), st.get("status"))
        lines.append(f"{office_emoji(st)} <b>{state}</b> · проверено {fmt_ts(st['at'])}")
    else:
        lines.append("⏳ С момента запуска ещё не проверялся")
    if ss:
        names = [f"{'⏸ ' if s['paused'] else ''}{uname(store.get_chat(s['chat']))}" for s in ss[:15]]
        lines.append(f"\n👥 <b>Следят</b> · {len(ss)}")
        lines.append("<blockquote>" + "\n".join(names) + "</blockquote>")
    evs = store.events(cid, area, 5)
    if evs:
        lines.append("<b>Последние появления мест</b>")
        lines.append("<blockquote>" + "\n".join(
            f"{fmt_ts(e['opened_at'])} — " + ("ещё есть" if not e["closed_at"]
                                              else f"держались {views.fmt_dur(e['closed_at'] - e['opened_at'])}")
            for e in evs) + "</blockquote>")
    if note:
        lines.append(note)
    return "\n".join(lines), ikb([
        [btn("🔄 Проверить сейчас", f"ad:or:{cid}:{area}"),
         btn("▶️ Включить проверку" if blocked else "⛔️ Отключить проверку", f"ad:ob:{cid}:{area}")],
        [btn("⬅️ Офисы", "ad:o"), BACK]])


# ---------- рассылка ----------

def recipients(segment: str = "all") -> List[int]:
    with_subs = {s["chat"] for s in store.all_subs()}
    out = []
    for c in store.all_chats():
        if c.get("role") in ("banned", "pending"):
            continue
        if (segment in ("ru", "uk") and (c.get("lang") or "ru") != segment) or \
                (segment == "subs" and c["chat"] not in with_subs) or \
                (segment == "nosubs" and c["chat"] in with_subs):
            continue
        out.append(c["chat"])
    return out


def broadcast_segments() -> Tuple[str, dict]:
    rows = [[btn(f"{label} ({len(recipients(key))})", f"ad:bg:{key}")] for key, label in SEGMENTS.items()]
    rows.append([BACK])
    return ("📢 <b>Рассылка</b>\n\nКому отправить? Число в скобках — сколько человек получат.\n"
            "<i>Заблокированные и ждущие одобрения не получают рассылку.</i>"), ikb(rows)


def broadcast_prompt(segment: str) -> Tuple[str, dict]:
    return (f"📢 <b>Рассылка</b> · {SEGMENTS[segment]} ({len(recipients(segment))})\n\n"
            "Пришли сообщение — текст с форматированием, фото или видео с подписью.\n\n"
            "<i>Перед отправкой покажу подтверждение.</i>", ikb([[btn("✖️ Отмена", "ad:bx")]]))


def run_broadcast(admin_chat: int, draft: int, screen: int, segment: str) -> None:
    targets = [c for c in recipients(segment) if c != admin_chat]
    ok = fail = 0
    hide = ikb([[btn("✖️", "hide")]])
    for i, chat in enumerate(targets):
        data = tg.call("copyMessage", chat_id=chat, from_chat_id=admin_chat, message_id=draft, reply_markup=hide) or {}
        if data.get("ok"):
            ok += 1
        else:
            fail += 1
            if data.get("error_code") == 403:
                store.pause_chat(chat)
        if i % 20 == 19:
            tg.edit(admin_chat, screen, f"📢 Отправляю… {i + 1} из {len(targets)}")
        time.sleep(0.05)  # лимит Telegram — около 30 сообщений в секунду
    tg.call("deleteMessage", chat_id=admin_chat, message_id=draft)
    checker.event(f"📢 Рассылка ({SEGMENTS[segment]}): доставлено {ok}, не доставлено {fail}")
    tg.show(admin_chat, f"✅ <b>Рассылка завершена</b> · {SEGMENTS[segment]}\n\nДоставлено: <b>{ok}</b>\nНе доставлено: {fail}"
                        + ("\n<i>Не доставлено — обычно те, кто заблокировал бота.</i>" if fail else ""),
            ikb([[BACK]]), mid=screen)


# ---------- экспорт ----------

def export(chat: int) -> None:
    def to_csv(header: list, rows: list) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        w.writerows(rows)
        return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM — чтобы Excel понял кириллицу

    day = lambda ts: datetime.fromtimestamp(ts, config.TZ).strftime("%Y-%m-%d %H:%M") if ts else ""  # noqa: E731
    subs = store.all_subs()
    per_chat: Dict[int, int] = {}
    for s in subs:
        per_chat[s["chat"]] = per_chat.get(s["chat"], 0) + 1
    users_csv = to_csv(["chat_id", "name", "username", "lang", "role", "source", "joined", "last_seen", "subs", "alerts", "bookings"],
                       [[c["chat"], c.get("name") or "", c.get("username") or "", c.get("lang") or "", c.get("role"),
                         c.get("source") or "", day(c.get("created_at")), day(c.get("last_seen")), per_chat.get(c["chat"], 0),
                         c.get("alerts") or 0, c.get("bookings") or 0] for c in store.all_chats()])
    subs_csv = to_csv(["id", "chat_id", "office", "area", "status", "paused", "max_days", "booked_date", "booked_time", "created"],
                      [[s["id"], s["chat"], views.city(s["centro"]), views.sub_area(s), views.summary(s, "ru")[1],
                        s["paused"], s.get("max_days") or "", s.get("booked_date") or "", s.get("booked_time") or "",
                        day(s.get("created_at"))] for s in subs])
    stamp = datetime.now(config.TZ).strftime("%Y-%m-%d")
    tg.send_document(chat, f"oksita-users-{stamp}.csv", users_csv, "👥 Пользователи")
    tg.send_document(chat, f"oksita-subs-{stamp}.csv", subs_csv, "📋 Подписки")
    checker.event("📤 Экспорт данных в CSV", "user")


# ---------- настройки и журнал ----------

def settings() -> Tuple[str, dict]:
    interval, max_subs = store.setting("interval"), store.setting("max_subs")
    paused, approval = store.setting("checks_paused"), store.setting("access") == "approval"
    notify, maint, report = store.setting("notify_new"), store.setting("maintenance"), store.setting("daily_report")
    text = ("⚙️ <b>Настройки бота</b>\n\n<blockquote>"
            f"⏱ Проверка каждые <b>{interval} мин</b>\n"
            f"📋 Подписок на человека: <b>{max_subs}</b>\n"
            f"🔎 Проверки: <b>{'остановлены' if paused else 'работают'}</b>\n"
            f"🚪 Доступ: <b>{'по одобрению' if approval else 'открытый'}</b>\n"
            f"🛠 Режим обслуживания: <b>{'включён' if maint else 'выключен'}</b>\n"
            f"🔔 О новых пользователях: <b>{'сообщать' if notify else 'нет'}</b>\n"
            f"📊 Вечерний отчёт в 21:00: <b>{'да' if report else 'нет'}</b></blockquote>\n"
            "<i>Проверять чаще 10 минут не советую — сайт DGT начинает тормозить.\n"
            "Режим обслуживания: пользователи видят «технические работы», проверки продолжаются.</i>")
    return text, ikb([
        [btn(("✅ " if n == interval else "") + f"{n} мин", f"ad:si:{n}") for n in (5, 10, 15, 20, 30)],
        [btn(("✅ " if n == max_subs else "") + f"{n} подп.", f"ad:sm:{n}") for n in (1, 3, 5, 10)],
        [btn("▶️ Запустить проверки" if paused else "⏸ Остановить проверки", "ad:sp")],
        [btn("🚪 Сделать открытым" if approval else "🔐 Доступ по одобрению", "ad:sa")],
        [btn("🛠 Выключить обслуживание" if maint else "🛠 Режим обслуживания", "ad:sw")],
        [btn(f"🔔 Новые пользователи: {'вкл' if notify else 'выкл'}", "ad:sn"),
         btn(f"📊 Отчёт: {'вкл' if report else 'выкл'}", "ad:sr")],
        [BACK],
    ])


def journal_view(kind: str = "all") -> Tuple[str, dict]:
    items = [(ts, text) for ts, text, k in checker.journal if kind == "all" or k == kind][:30]
    lines = [f"{datetime.fromtimestamp(ts, config.TZ):%d.%m %H:%M} {esc(text)}" for ts, text in items]
    body = "<blockquote expandable>" + "\n".join(lines) + "</blockquote>" if lines else "Пока пусто."
    filters = [btn(("• " if key == kind else "") + label, f"ad:l:{key}") for key, label in JOURNAL.items()]
    return (f"📜 <b>Журнал</b> · {JOURNAL[kind]}\n<i>События с последнего перезапуска сервера</i>\n\n{body}",
            ikb([filters[:2], filters[2:], [btn("🔄 Обновить", f"ad:l:{kind}"), BACK]]))


# ---------- ввод от админа ----------

def handle_input(msg: dict) -> bool:
    """Сообщение от админа, которого мы ждали. True — обработано."""
    chat = msg["chat"]["id"]
    p = pending.get(chat)
    if not p or (msg.get("text") or "").startswith("/"):
        return False
    if p["kind"] == "broadcast":
        p["draft"] = msg["message_id"]
        n = len([c for c in recipients(p["segment"]) if c != chat])
        tg.show(chat, f"📢 Отправить сообщение выше — {SEGMENTS[p['segment']]}: "
                      f"<b>{plural(n, 'пользователю', 'пользователям', 'пользователям')}</b>?",
                ikb([[btn("✅ Отправить", "ad:bs"), btn("✖️ Отмена", "ad:bx")]]), mid=p["screen"])
        return True
    tg.call("deleteMessage", chat_id=chat, message_id=msg["message_id"])
    if p["kind"] == "find":
        query = (msg.get("text") or "").strip()
        q = views.fold(query.lstrip("@"))
        found = [c for c in store.all_chats()
                 if q and (q in views.fold(c.get("name") or "") or q in views.fold(c.get("username") or "")
                           or q == str(c["chat"]))][:UPAGE]
        pending.pop(chat, None)
        tg.show(chat, *users(0, found, query), mid=p["screen"])
        return True
    if p["kind"] == "msg":
        target = p["target"]
        hide = ikb([[btn("✖️", "hide")]])
        lang = views.lang_of(target)
        if msg.get("text"):
            sent = tg.send(target, views.tx(lang, "📩 <b>Сообщение от администратора</b>",
                                            "📩 <b>Повідомлення від адміністратора</b>") + f"\n\n{esc(msg['text'])}",
                           hide) is not None
        else:
            data = tg.call("copyMessage", chat_id=target, from_chat_id=chat, message_id=msg["message_id"],
                           reply_markup=hide) or {}
            sent = bool(data.get("ok"))
        pending.pop(chat, None)
        checker.event(f"✉️ Сообщение пользователю {store.get_chat(target).get('name') or target}", "user")
        tg.show(chat, *user_card(target, chat, "✅ Сообщение отправлено" if sent else "⚠️ Не доставлено — "
                                 "возможно, пользователь заблокировал бота"), mid=p["screen"])
        return True
    return False


# ---------- кнопки ----------

def on_callback(chat: int, mid: int, data: str) -> Optional[str]:
    """data — всё после «ad:». Возвращает текст всплывающей подсказки или None."""
    kind, _, rest = data.partition(":")
    if kind != "bs":
        p = pending.pop(chat, None)
        if p and p.get("draft") and kind == "bx":
            tg.call("deleteMessage", chat_id=chat, message_id=p["draft"])

    if kind in ("", "bx"):
        tg.show(chat, *panel(), mid=mid)
    elif kind == "an":
        tg.show(chat, *analytics(), mid=mid)
    elif kind == "sy":
        tg.show(chat, *system(), mid=mid)
    elif kind == "u":
        tg.show(chat, *users(int(rest or 0)), mid=mid)
    elif kind == "uf":
        pending[chat] = {"kind": "find", "screen": mid}
        tg.show(chat, "🔎 <b>Поиск пользователя</b>\n\nНапиши имя, @username или chat id.",
                ikb([[btn("✖️ Отмена", "ad:u:0")]]), mid=mid)
    elif kind == "uc" and rest.lstrip("-").isdigit():
        tg.show(chat, *user_card(int(rest), chat), mid=mid)
    elif kind in ("ub", "ua", "ux", "ux!", "ap", "ar", "um") and rest.lstrip("-").isdigit():
        return user_action(chat, mid, kind, int(rest))
    elif kind == "sx" and rest.isdigit():
        sub = store.get_sub(int(rest))
        if sub:
            tg.delete(sub["chat"], sub.get("alert_msg"))
            store.delete_sub(sub["id"])
            checker.event(f"🗑 Админ удалил подписку: {views.plain_title(sub)}", "user")
            tg.show(chat, *user_card(sub["chat"], chat, f"🗑 Удалена подписка: {views.title(sub)}"), mid=mid)
    elif kind == "o":
        tg.show(chat, *offices_view(), mid=mid)
    elif kind == "oc":
        cid, _, area = rest.partition(":")
        tg.show(chat, *office_card(cid, area), mid=mid)
    elif kind == "ob":
        cid, _, area = rest.partition(":")
        blocked = store.blocked_keys()
        blocked ^= {(cid, area)}
        store.set_setting("blocked", ",".join(f"{c}:{a}" for c, a in sorted(blocked)))
        checker.event(f"{'⛔️ Отключена' if (cid, area) in blocked else '▶️ Включена'} проверка: "
                      f"{views.city(cid)} · {views.area_label(area)}")
        tg.show(chat, *office_card(cid, area), mid=mid)
    elif kind == "or":
        cid, _, area = rest.partition(":")
        tg.show(chat, *office_card(cid, area, "\n🔄 <i>Проверяю…</i>"), mid=mid)

        def job() -> None:
            checker.run_checks([(cid, area)])
            tg.show(chat, *office_card(cid, area, "\n✅ <i>Проверено только что</i>"), mid=mid)
        threading.Thread(target=job, daemon=True).start()
    elif kind == "b":
        tg.show(chat, *broadcast_segments(), mid=mid)
    elif kind == "bg" and rest in SEGMENTS:
        pending[chat] = {"kind": "broadcast", "screen": mid, "segment": rest}
        tg.show(chat, *broadcast_prompt(rest), mid=mid)
    elif kind == "bs":
        p = pending.pop(chat, None)
        if not p or not p.get("draft"):
            return "Сначала пришли сообщение для рассылки"
        tg.show(chat, "📢 Отправляю…", ikb([]), mid=mid)
        threading.Thread(target=run_broadcast, args=(chat, p["draft"], mid, p["segment"]), daemon=True).start()
    elif kind == "x":
        threading.Thread(target=export, args=(chat,), daemon=True).start()
        return "📤 Отправляю два CSV-файла…"
    elif kind == "s":
        tg.show(chat, *settings(), mid=mid)
    elif kind in ("si", "sm") and rest.isdigit():
        store.set_setting("interval" if kind == "si" else "max_subs", int(rest))
        checker.event(f"⚙️ {'Интервал' if kind == 'si' else 'Лимит подписок'}: {rest}")
        tg.show(chat, *settings(), mid=mid)
    elif kind in ("sp", "sw", "sn", "sr"):
        key = {"sp": "checks_paused", "sw": "maintenance", "sn": "notify_new", "sr": "daily_report"}[kind]
        store.set_setting(key, 0 if store.setting(key) else 1)
        label = {"checks_paused": "Проверки остановлены", "maintenance": "Режим обслуживания",
                 "notify_new": "Сообщать о новых", "daily_report": "Вечерний отчёт"}[key]
        checker.event(f"⚙️ {label}: {'да' if store.setting(key) else 'нет'}")
        tg.show(chat, *settings(), mid=mid)
    elif kind == "sa":
        store.set_setting("access", "open" if store.setting("access") == "approval" else "approval")
        checker.event(f"🚪 Доступ: {'по одобрению' if store.setting('access') == 'approval' else 'открытый'}")
        tg.show(chat, *settings(), mid=mid)
    elif kind == "l":
        tg.show(chat, *journal_view(rest if rest in JOURNAL else "all"), mid=mid)
    return None


def user_action(chat: int, mid: int, kind: str, target: int) -> Optional[str]:
    c = store.get_chat(target)
    who = c.get("name") or str(target)
    protected = target in config.OWNERS or target == chat
    if kind == "um":
        pending[chat] = {"kind": "msg", "target": target, "screen": mid}
        tg.show(chat, f"✉️ <b>Сообщение для {uname(c)}</b>\n\nПришли текст или фото — я перешлю его от имени бота.",
                ikb([[btn("✖️ Отмена", f"ad:uc:{target}")]]), mid=mid)
        return None
    if kind == "ub" and not protected:
        if c.get("role") == "banned":
            store.set_chat(target, role="user")
            checker.event(f"✅ Разблокирован: {who}", "user")
        else:
            store.set_chat(target, role="banned")
            store.pause_chat(target)
            checker.event(f"🚫 Заблокирован: {who}", "user")
    elif kind == "ua" and chat in config.OWNERS and not protected:
        store.set_chat(target, role="user" if c.get("role") == "admin" else "admin")
        checker.event(f"⭐️ {'Снят админ' if c.get('role') == 'admin' else 'Новый админ'}: {who}", "user")
    elif kind == "ux":
        tg.show(chat, f"🗑 <b>Удалить все подписки {uname(c)}?</b>",
                ikb([[btn("Да, удалить", f"ad:ux!:{target}"), btn("Отмена", f"ad:uc:{target}")]]), mid=mid)
        return None
    elif kind == "ux!":
        store.forget_chat(target)
        checker.event(f"🗑 Удалены подписки: {who}", "user")
    elif kind in ("ap", "ar"):
        approved = kind == "ap"
        store.set_chat(target, role="user" if approved else "banned")
        checker.event(f"{'✅ Одобрен' if approved else '🚫 Отклонён'}: {who}", "user")
        lang = views.lang_of(target)
        if approved:
            tg.show(target, *views.dashboard(target, c.get("name") or "", checker.status.get("next_cycle"),
                                             views.tx(lang, "✅ <b>Доступ открыт!</b> Добро пожаловать.",
                                                      "✅ <b>Доступ відкрито!</b> Ласкаво просимо.")))
        else:
            tg.show(target, *views.banned_view(lang))
    tg.show(chat, *user_card(target, chat), mid=mid)
    return None
