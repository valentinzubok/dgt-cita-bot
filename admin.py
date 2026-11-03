"""Админ-панель: обзор, аналитика, система, пользователи, офисы, доход, промо, задания, реклама, рассылка, настройки."""
from __future__ import annotations

import csv
import io
import json
import logging
import math
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import ads
import board
import channel
import checker
import config
import dgt
import group
import posts
import premium
import reviews
import rewards
import schools
import store
import tg
import views
from tg import btn, copy, ikb, url
from views import esc, fmt_ts, plural

log = logging.getLogger("admin")

pending: Dict[int, dict] = {}  # ждём от админа сообщение: рассылка, письмо, поиск, данные для промо и заданий
UPAGE = 8
BACK = btn("⬅️ Админ-панель", "ad")
HOME = views.home_btn("ru")
ROLE_TEXT = {"user": "пользователь", "admin": "⭐️ админ", "banned": "🚫 заблокирован", "pending": "⏳ ждёт одобрения"}
SEGMENTS = {
    "all": "👥 Всем",
    "ru": "🇷🇺 Русский язык",
    "uk": "🇺🇦 Украинский язык",
    "es": "🇪🇸 Испанский язык",
    "en": "🇬🇧 Английский язык",
    "subs": "📋 С подписками",
    "nosubs": "💤 Без подписок",
    "free": "🆓 Без Premium",
    "paid": "💎 С Premium",
}
JOURNAL = {"all": "Все", "error": "⚠️ Ошибки", "money": "💰 Доход", "user": "👤 Люди", "dates": "🟢 Даты"}
URL_RE = re.compile(r"^https://[^\s<>\"']{4,300}$")


def uname(c: dict) -> str:
    name = esc(c.get("name") or "без имени")
    return name + (f" @{esc(c['username'])}" if c.get("username") else "")


def badge(c: dict) -> str:
    if c["chat"] in config.OWNERS:
        return "👑 "
    if c.get("role") in ("admin", "banned", "pending"):
        return {"admin": "⭐️ ", "banned": "🚫 ", "pending": "⏳ "}[c["role"]]
    return "💎 " if (c.get("premium_until") or 0) > time.time() else ""


def bar(n: int, top: int, width: int = 10) -> str:
    return "▇" * max(1 if n else 0, round(n / top * width)) if top else ""


def days_text(hours: int) -> str:
    return plural(hours // 24, "день", "дня", "дней") if hours >= 24 and hours % 24 == 0 else f"{hours} ч"


def csv_safe(value) -> object:
    """Excel выполняет ячейки, начинающиеся с = + - @ — имя пользователя не должно стать формулой."""
    return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


# ---------- обзор ----------

def state_line() -> str:
    s = checker.status
    if checker.site_down():
        return f"🔴 <b>нет связи с DGT</b> с {datetime.fromtimestamp(s['down_since'], config.TZ):%d.%m %H:%M}"
    if store.setting("checks_paused"):
        return "🟡 <b>проверки остановлены</b>"
    return "🟢 <b>работает</b>"


def panel() -> Tuple[str, dict]:
    chats, subs, keys = store.all_chats(), store.all_subs(), store.active_keys()
    now = time.time()
    day = store.today_key()
    active_week = sum(1 for c in chats if (c.get("last_seen") or 0) > now - 7 * 86400)
    open_now = sum(1 for k in keys if checker.offices.get(k, {}).get("days"))
    waiting = sum(1 for c in chats if c.get("role") == "pending")
    paid_now = sum(1 for c in chats if (c.get("premium_until") or 0) > now)
    maint = store.setting("maintenance")
    review = len(store.posts("review"))
    fresh_reviews = sum(1 for r in store.reviews() if r["consent"] and r["status"] == "new" and r.get("text"))
    text = (
        f"🛠 <b>Админ-панель</b> · {state_line()}"
        + ("\n🚧 Пользователи видят «Технические работы»" if maint else "") + "\n\n"
        "📅 <b>Сегодня</b>\n<blockquote>"
        f"👤 Новых: <b>{store.metric(day, 'new_users')}</b> · ➕ подписок: <b>{store.metric(day, 'subs')}</b>\n"
        f"🔔 Уведомлений: <b>{store.metric(day, 'alerts')}</b> · ✅ записались: <b>{store.metric(day, 'bookings')}</b>\n"
        f"💰 Оплат: <b>{store.metric(day, 'payments')}</b> на <b>{store.metric(day, 'stars')}</b> ⭐\n"
        f"🎁 Промо: {store.metric(day, 'promo_used')} · заданий: {store.metric(day, 'tasks_done')} · "
        f"друзей: {store.metric(day, 'ref_activated')}\n"
        f"🛂 Сигналов о документах: <b>{store.metric(day, 'signals')}</b></blockquote>\n"
        "📊 <b>Всего</b>\n<blockquote>"
        f"👥 Пользователей: <b>{len(chats)}</b> · за неделю: <b>{active_week}</b>\n"
        f"💎 Premium: <b>{paid_now}</b>\n"
        f"📋 Подписок: <b>{len(subs)}</b> · офисов: <b>{len(keys)}/{config.MAX_OFFICES}</b>\n"
        f"🟢 Офисов с датами: <b>{open_now}</b>\n"
        f"🛂 Подписок на сигналы: <b>{store.signal_sub_count()}</b>"
        + (f"\n🙋 Ждут одобрения: <b>{waiting}</b>" if waiting else "") + "</blockquote>"
    )
    return text, ikb([
        [btn("📈 Аналитика", "ad:an"), btn("🩺 Система", "ad:sy", "danger" if checker.site_down() else None)],
        [btn("👥 Пользователи", "ad:u:0"), btn("🏢 Офисы", "ad:o")],
        [btn("💰 Доход", "ad:mn", "success"), btn("🎟 Промо", "ad:pm")],
        [btn("📝 Задания", "ad:ts"), btn("📣 Реклама", "ad:ca")],
        [btn("🎁 Пробный период", "ad:ty"), btn("📌 Объявления" + (f" · {review}" if review else ""), "ad:jq", "primary" if review else None)],
        [btn("📢 Канал", "ad:cl"), btn("🏫 Автошколы", "ad:hl"),
         btn("⭐ Отзывы" + (f" · {fresh_reviews}" if fresh_reviews else ""), "ad:vw", "primary" if fresh_reviews else None)],
        [btn("📢 Рассылка", "ad:b", "primary"), btn("📜 Журнал", "ad:l:all")],
        [btn("⚙️ Настройки", "ad:s"), btn("📤 Экспорт", "ad:x")],
        [btn("🚧 Выключить техработы" if maint else "🚧 Включить техработы", "ad:pw", "danger" if maint else None)],
        [btn("🔄 Обновить", "ad"), HOME],
    ])


def analytics() -> Tuple[str, dict]:
    chats, subs = store.all_chats(), store.all_subs()
    today = datetime.now(config.TZ).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    keys = ("new_users", "subs", "alerts", "bookings", "payments")
    rows = [(d, [store.metric(d, k) for k in keys]) for d in days]
    top = max([r[1][0] for r in rows] + [1])
    table = ["день   нов подп увед зап опл"]
    for d, vals in rows:
        table.append(f"{d[8:10]}.{d[5:7]}  " + " ".join(f"{v:>4}" for v in vals))
    totals = [sum(r[1][i] for r in rows) for i in range(len(keys))]
    table.append("7 дн.  " + " ".join(f"{v:>4}" for v in totals))
    chart = "\n".join(f"{d[8:10]}.{d[5:7]} {bar(v[0], top)} {v[0]}" for d, v in rows)

    with_lang = sum(1 for c in chats if c.get("lang"))
    subscribed = {s["chat"] for s in subs}
    with_subs = len(subscribed)
    alerted = sum(1 for c in chats if (c.get("alerts") or 0) > 0)
    booked = sum(1 for c in chats if (c.get("bookings") or 0) > 0)
    payers = {p["chat"] for p in store.q("SELECT DISTINCT chat FROM payments WHERE refunded = 0")}
    paid = len(payers)
    pct = lambda n: f"{round(n / len(chats) * 100)}%" if chats else "—"  # noqa: E731
    by_lang = {code: sum(1 for c in chats if c.get("lang") == code) for code in config.LANGS}

    sources: Dict[str, List[int]] = {}  # метка → пришли, подписались, заплатили
    for c in chats:
        row = sources.setdefault(c.get("source") or "без метки", [0, 0, 0])
        row[0] += 1
        row[1] += c["chat"] in subscribed
        row[2] += c["chat"] in payers
    src_lines = [f"{esc(k)} — 👥 {n} · 📋 {s} · 💰 {p}" for k, (n, s, p) in sorted(sources.items(), key=lambda kv: -kv[1][0])[:10]]
    popular = sorted(store.popularity().items(), key=lambda kv: -kv[1])[:5]
    top_lines = [f"{i + 1}. {esc(views.city(cid))} · {esc(views.area_label(area))} — 👥 {n}"
                 for i, ((cid, area), n) in enumerate(popular)] or ["пока пусто"]
    text = (
        "📈 <b>Аналитика</b>\n\n"
        "📅 <b>За 7 дней</b>\n<pre>" + "\n".join(table) + "</pre>\n"
        "👤 <b>Новые пользователи</b>\n<pre>" + chart + "</pre>\n"
        "🔻 <b>Воронка</b>\n<blockquote>"
        f"👥 Запустили бота: <b>{len(chats)}</b>\n"
        f"🌐 Выбрали язык: {with_lang} · {pct(with_lang)}\n"
        f"📋 Подписались: <b>{with_subs}</b> · {pct(with_subs)}\n"
        f"🔔 Получили уведомление: {alerted} · {pct(alerted)}\n"
        f"✅ Записались: <b>{booked}</b> · {pct(booked)}\n"
        f"💰 Заплатили: <b>{paid}</b> · {pct(paid)}</blockquote>\n"
        f"🌐 Языки: 🇺🇦 {by_lang['uk']} · 🇷🇺 {by_lang['ru']} · 🇪🇸 {by_lang['es']} · 🇬🇧 {by_lang['en']} · не выбран {len(chats) - with_lang}\n\n"
        "🏆 <b>Топ офисов</b>\n<blockquote>" + "\n".join(top_lines) + "</blockquote>\n"
        "🔗 <b>Откуда пришли</b> (t.me/" + config.BOT_USERNAME + "?start=метка)\n<blockquote>" + "\n".join(src_lines) + "</blockquote>\n"
        "<i>нов — новые, подп — подписки, увед — уведомления, зап — записались, опл — оплаты. "
        "У меток: 👥 пришли · 📋 подписались · 💰 заплатили.</i>"
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


def system(note: str = "") -> Tuple[str, dict]:
    s, cap, now = checker.status, checker.capacity(), time.time()
    hook = (tg.call("getWebhookInfo") or {}).get("result")
    hook = hook if isinstance(hook, dict) else {}
    site = f"🟢 Сайт DGT отвечал {fmt_ts(s['last_ok'])}" if s["last_ok"] else "⏳ С запуска сайт DGT не отвечал"
    if checker.site_down():
        site = (f"🔴 Нет связи с DGT с {datetime.fromtimestamp(s['down_since'], config.TZ):%d.%m %H:%M}\n"
                f"Следующая проба: {datetime.fromtimestamp(s['probe_at'], config.TZ):%H:%M}\n" + site)
    text = (
        f"🩺 <b>Система</b> · {state_line()}\n\n🔎 <b>Проверки DGT</b>\n<blockquote>"
        f"{site}\n"
        f"⏱ Средняя проверка: {cap['avg']:.1f} с · за 10 мин успеваем ~{cap['fits']} офисов\n"
        f"📦 Офисов в работе: {cap['offices']}/{config.MAX_OFFICES} · ждут очереди: {s['backlog']}\n"
        f"⚙️ Загрузка очереди: {cap['load']}%\n"
        f"⚠️ Ошибок за час: {cap['errors_hour']} · с запуска: {s['errors']} · проверок: {s['checks']}</blockquote>\n"
        "🖥 <b>Сервер</b>\n<blockquote>"
        f"💾 Память: {memory_mb():.0f} МБ из 512 · потоков: {threading.active_count()}\n"
        f"🌐 Webhook: в очереди {hook.get('pending_update_count', '?')} · "
        f"{'ошибка: ' + esc(hook['last_error_message']) if hook.get('last_error_message') else 'ошибок нет'}\n"
        f"🗄 База: {'Postgres (Neon)' if store.PG else 'SQLite'} · очередь записи: {store._wq.unfinished_tasks}\n"
        f"🚀 Версия: {config.VERSION} · работает {views.fmt_dur(now - s['started'])}</blockquote>"
        + (f"\n{note}" if note else "")
    )
    return text, ikb([[btn("🔌 Проверить связь с DGT", "ad:dg")], [btn("🔄 Обновить", "ad:sy"), BACK]])


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
    head = f"🔎 <b>Поиск «{esc(query)}»</b> · найдено {len(found)}" if found is not None else f"👥 <b>Пользователи</b> · {len(chats)}"
    return (f"{head}\n\n<blockquote>👑 владелец · ⭐️ админ · 💎 Premium\n🚫 заблокирован · ⏳ ждёт одобрения</blockquote>\n"
            "<i>Сначала новые. Нажми на пользователя, чтобы открыть карточку.</i>"), ikb(rows)


def user_card(target: int, viewer: int, note: str = "") -> Tuple[str, dict]:
    c = store.get_chat(target)
    subs = store.subs_of(target)
    role = "👑 владелец" if target in config.OWNERS else ROLE_TEXT.get(c.get("role"), c.get("role"))
    joined = datetime.fromtimestamp(c["created_at"], config.TZ).strftime("%d.%m.%Y") if c.get("created_at") else "—"
    until = c.get("premium_until") or 0
    friends = store.friends_of(target)
    inviter = store.get_chat(c["ref_by"]) if c.get("ref_by") else None
    lines = [f"👤 <b>{uname(c)}</b>",
             "<blockquote>"
             f"🆔 <code>{target}</code> · 🎭 {role}\n"
             f"🌐 Язык: {views.LANGS.get(c.get('lang') or '', 'не выбран')}"
             + (f" · 🔗 {esc(c['source'])}" if c.get("source") else "") + "\n"
             f"📅 С нами с {joined} · 👀 был {fmt_ts(c['last_seen']) if c.get('last_seen') else '—'}\n"
             f"💎 Premium: {'до ' + datetime.fromtimestamp(until, config.TZ).strftime('%d.%m.%Y %H:%M') if until > time.time() else 'нет'}"
             + (" · автопродление" if c.get("sub_active") else "") + "\n"
             f"🔔 Уведомлений: {c.get('alerts') or 0} · ✅ записывался: {c.get('bookings') or 0}\n"
             f"👥 Пригласил: {len(friends)}" + (f" · его пригласил: {uname(inviter)}" if inviter else "") + "\n"
             f"📣 Реклама: {'согласен' if c.get('ads_ok') else 'нет согласия'}"
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
        rows.append([btn("✅ Одобрить", f"ad:ap:{target}", "success"), btn("🚫 Отклонить", f"ad:ar:{target}", "danger")])
    rows.append([btn("💎 +1 день", f"ad:gp:{target}:24"), btn("+7", f"ad:gp:{target}:168"), btn("+30", f"ad:gp:{target}:720")])
    if until > time.time():
        rows.append([btn("➖ Снять Premium", f"ad:gx:{target}"), btn("💸 Вернуть оплату", f"ad:rf:{target}")])
    rows.append([btn("✉️ Написать", f"ad:um:{target}")])
    protected = target in config.OWNERS or target == viewer
    if not protected:
        banned = c.get("role") == "banned"
        rows[-1].append(btn("✅ Разблокировать" if banned else "🚫 Заблокировать", f"ad:ub:{target}", None if banned else "danger"))
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
    return {dgt.FULL: "🔴", dgt.NO_AREA: "⚪️", dgt.NOT_CONFIGURED: "⚪️", dgt.NEEDS_DATA: "🔐"}.get(st.get("status"), "⏳")


def offices_view() -> Tuple[str, dict]:
    groups: Dict[Tuple[str, str], list] = {}
    for s in store.all_subs():
        groups.setdefault((s["centro"], s["area"]), []).append(s)
    blocked = store.blocked_keys()
    rows = []
    for (cid, area), ss in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:40]:
        st = checker.offices.get((cid, area), {})
        active = sum(1 for s in ss if not s["paused"])
        label = views.area_label(area, ss[0].get("area_label"))
        rows.append([btn(f"{office_emoji(st, (cid, area) in blocked)} {views.city(cid)} · {label} — 👥 {active}",
                         f"ad:oc:{cid}:{area}")])
    rows.append([BACK])
    text = ("🏢 <b>Офисы под наблюдением</b> · " + str(len(groups)) + "\n\n<blockquote>"
            "🟢 есть даты · 🔴 мест нет · ⚪️ нет такой записи\n🔐 нужна заявка · ⚠️ сайт не отвечает · ⛔️ отключён · ⏳ не проверялся</blockquote>\n"
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
            dgt.FULL: "мест нет", dgt.NO_AREA: "такой записи в офисе нет", dgt.NEEDS_DATA: "запись через заявку с личными данными",
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


# ---------- доход ----------

def money(note: str = "") -> Tuple[str, dict]:
    total = store.payments_total()
    chats = store.all_chats()
    now = time.time()
    paid_now = sum(1 for c in chats if (c.get("premium_until") or 0) > now)
    auto = sum(1 for c in chats if c.get("sub_active"))
    balance = ((tg.call("getMyStarBalance") or {}).get("result") or {})
    recent = store.payments_recent(8)
    lines = [f"{datetime.fromtimestamp(p['created_at'], config.TZ):%d.%m %H:%M} · {esc(store.get_chat(p['chat']).get('name') or str(p['chat']))} · "
             f"{p['stars']} ⭐ · {p['plan']}{' · возврат' if p['refunded'] else ''}" for p in recent]
    text = ("💰 <b>Доход</b>\n\n<blockquote>"
            f"⭐️ Баланс бота: <b>{balance.get('amount', '?')}</b>\n"
            f"🧾 Оплат всего: {total['n']} на <b>{total['stars']}</b> ⭐\n"
            f"💎 Premium сейчас: <b>{paid_now}</b> · с автопродлением: {auto}</blockquote>\n"
            "🏷 <b>Цены</b>\n<blockquote>"
            f"7 дней — <b>{store.setting('price_7')}</b> ⭐\n30 дней — <b>{store.setting('price_30')}</b> ⭐\n"
            f"90 дней — <b>{store.setting('price_90')}</b> ⭐</blockquote>\n"
            "🧾 <b>Последние оплаты</b>\n" + ("<blockquote>" + "\n".join(lines) + "</blockquote>" if lines else "пока нет")
            + (f"\n\n{note}" if note else ""))
    return text, ikb([[btn("✏️ Изменить цены", "ad:pp")], [btn("🔄 Обновить", "ad:mn"), BACK]])


# ---------- пробный период ----------

def trial_admin(note: str = "") -> Tuple[str, dict]:
    hours = int(store.setting("trial_hours"))
    chats = store.all_chats()
    used = [c for c in chats if c.get("trial_at")]
    active = sum(1 for c in used if premium.in_trial(c["chat"]))
    bought = sum(1 for c in used if c.get("paid_at"))
    rate = f"{round(bought / len(used) * 100)}%" if used else "—"
    text = ("🎁 <b>Пробный период</b>\n\n<blockquote>"
            f"Срок: <b>{days_text(hours) if hours else 'выключен'}</b>\n"
            f"Начали: <b>{len(used)}</b> · идёт сейчас: <b>{active}</b>\n"
            f"Купили после него: <b>{bought}</b> · конверсия: <b>{rate}</b></blockquote>\n"
            "<i>Один раз на человека, запись остаётся и после удаления аккаунта. Не даётся тем, кто уже покупал Premium или имеет его сейчас. "
            "У владельца Premium включён всегда, поэтому кнопку видно только со второго аккаунта.</i>"
            + (f"\n\n{note}" if note else ""))
    return text, ikb([
        [btn("Срок", "noop")],
        [btn(("✅ " if h == hours else "") + (days_text(h) if h else "Выкл"), f"ad:ty:{h}") for h in (0, 24, 72, 168)],
        [btn("👀 Что видит пользователь", "ad:tp")],
        [BACK],
    ])


# ---------- объявления ----------

def board_admin(note: str = "") -> Tuple[str, dict]:
    counts = store.post_counts()
    queue = store.posts("review", 10)
    job, ad = board.price("job"), board.price("ad")
    text = ("📌 <b>Объявления в канале</b>\n\n<blockquote>"
            f"⏳ На проверке: <b>{counts.get('review', 0)}</b>\n"
            f"✅ Опубликовано: <b>{counts.get('published', 0)}</b> · 🚫 отклонено: <b>{counts.get('rejected', 0)}</b>\n"
            f"💼 Вакансия: <b>{job}</b> ⭐ · 📣 реклама: <b>{ad}</b> ⭐</blockquote>"
            + (f"\n\n{note}" if note else ""))
    rows = [[btn(f"{'💼' if p['kind'] == 'job' else '📣'} {p['text'][:36]}", f"ad:jc:{p['id']}")] for p in queue]
    rows.append([btn("💼 Цена вакансии", "noop")])
    rows.append([btn(("✅ " if n == job else "") + str(n), f"ad:jp:post_job:{n}") for n in (0, 49, 99, 199)])
    rows.append([btn("📣 Цена рекламы", "noop")])
    rows.append([btn(("✅ " if n == ad else "") + str(n), f"ad:jp:post_ad:{n}") for n in (99, 249, 499, 999)])
    rows.append([btn("🔄 Обновить", "ad:jq"), BACK])
    return text, ikb(rows)


def board_card(pid: int, note: str = "") -> Tuple[str, dict]:
    post = store.get_post(pid)
    if not post:
        return board_admin()
    c = store.get_chat(post["chat"])
    text = (f"📌 <b>Объявление</b> · {board.LABELS[post['kind']]}\n{uname(c)} · <code>{post['chat']}</code>"
            + (f" · {post['stars']} ⭐" if post["stars"] else " · бесплатно") + ("\n🖼 с фото" if post.get("photo") else "")
            + f"\n\n<blockquote>{esc(post['text'])}</blockquote>" + (f"\n{note}" if note else ""))
    rows = []
    if post["status"] == "review":
        rows.append([btn("✅ Опубликовать", f"ad:ja:{pid}", "success"), btn("🚫 Отклонить", f"ad:jr:{pid}", "danger")])
    rows.append([btn("👤 Автор", f"ad:uc:{post['chat']}"), btn("⬅️ Объявления", "ad:jq")])
    return text, ikb(rows)


# ---------- канал ----------

def channel_admin(note: str = "") -> Tuple[str, dict]:
    r = channel.rights()
    delay = int(store.setting("channel_delay"))
    yes = lambda on: "да" if on else "нет"  # noqa: E731
    text = (f"📢 <b>Канал {esc(channel.username())}</b>\n\n<blockquote>"
            f"Бот в канале: <b>{esc(r['status'])}</b>\nМожет публиковать: <b>{yes(r['post'])}</b> · закреплять: <b>{yes(r['pin'])}</b>\n"
            f"Посты о датах: <b>{f'через {delay} мин' if delay else 'выключены'}</b>\n"
            f"Сегодня постов о датах: <b>{store.metric(store.today_key(), 'channel_posts')}</b>\n"
            f"Подписались за сегодня: <b>{store.metric(store.today_key(), 'channel_joined')}</b> · "
            f"отписались: <b>{store.metric(store.today_key(), 'channel_left')}</b> · "
            f"через экран подписки: <b>{store.metric(store.today_key(), 'gate_joined')}</b></blockquote>\n"
            + ("🔒 Ботом пользуются только подписчики канала: без подписки — экран «подпишись», уведомления не приходят.\n"
               if store.setting("gate") else "🔓 Подписка на канал не обязательна.\n")
            + "<i>В боте даты приходят сразу, в канале с задержкой: это ведёт людей в бота.</i>"
            + (f"\n\n{note}" if note else ""))
    plan, drafts = len(channel.planned()), len(store.queued(("draft",)))
    on = lambda key: "✅" if store.setting(key) else "⬜️"  # noqa: E731
    return text, ikb([
        [btn("Задержка, мин", "noop")],
        [btn(("✅ " if n == delay else "") + (str(n) if n else "Выкл"), f"ad:cm:{n}") for n in (0, 15, 30, 60)],
        [btn(f"🗓 Отложенные посты · {plan} в плане · {drafts} черновиков", "ad:kq", "primary")],
        [btn(f"{on('channel_digest')} Итоги недели (вс 19:00)", "ad:kx"), btn(f"{on('channel_proof')} «Ещё одна запись»", "ad:ky")],
        [btn(f"{on('gate')} Ботом — только с подпиской на канал", "ad:gk")],
        [btn("💬 Группа канала" + (f" · {group.info().get('title')}" if group.info().get("id") else " · не найдена"), "ad:gg")],
        [btn("📌 Опубликовать и закрепить пост о канале", "ad:cw")],
        [url("📢 Открыть канал", channel.link()), BACK],
    ])


# ---------- автошколы и отзывы ----------

def schools_admin(note: str = "") -> Tuple[str, dict]:
    items = store.schools()
    lines = []
    for x in items[:20]:
        st = schools.stats(x)
        lines.append(f"{'🟢' if st['active'] else '⏸'} <b>{esc(x['name'])}</b>" + (f" · {esc(x['city'])}" if x.get("city") else "")
                     + f"\n   <code>{x['code']}</code>: {st['uses']}/{st['seats']} · пришли {st['came']} · оплатили {st['paid']}")
    text = ("🏫 <b>Автошколы</b>\n\nКаждая получает код: 7 дней Premium для учеников (до 100), ссылку, QR и плакат для печати. "
            "Ученики приходят с меткой <code>promo_КОД</code>, поэтому видно, кто пришёл и кто заплатил.\n\n"
            + ("<blockquote>" + "\n".join(lines) + "</blockquote>" if lines else
               "Пока нет. Автошкола оставляет заявку в боте: «💼 Вакансии» → «🤝 Партнёрам» → «🏫 Мы автошкола».")
            + (f"\n\n{note}" if note else ""))
    rows = [[btn(f"🏫 {x['name'][:30]}", f"ad:hc:{x['id']}")] for x in items[:12]]
    rows += [[btn("➕ Добавить автошколу", "ad:ha", "primary")], [BACK, HOME]]
    return text, ikb(rows)


def school_card(sid: int, note: str = "") -> Tuple[str, dict]:
    x = store.get_school(sid)
    if not x:
        return schools_admin("Этой автошколы уже нет.")
    st = schools.stats(x)
    text = (f"🏫 <b>{esc(x['name'])}</b>" + (f" · {esc(x['city'])}" if x.get("city") else "") + "\n\n<blockquote>"
            f"🎟 Код: <code>{x['code']}</code> · {'работает' if st['active'] else 'выключен'}\n"
            f"👥 Активировали: <b>{st['uses']}/{st['seats']}</b>\n"
            f"🆕 Пришли новыми: <b>{st['came']}</b> · 💰 оплатили: <b>{st['paid']}</b>\n"
            f"🔗 {schools.link(x['code'])}\n🖨 {schools.poster_url(x['code'])}</blockquote>"
            + (f"\n\n{note}" if note else ""))
    return text, ikb([
        [url("🖨 Плакат", schools.poster_url(x["code"])), btn("🖼 QR сюда", f"ad:hq:{sid}")],
        [btn("📨 Отправить комплект автошколе", f"ad:hs:{sid}")] if x.get("chat") else [],
        [btn("⏸ Выключить код" if st["active"] else "▶️ Включить код", f"ad:ht:{sid}")],
        [btn("⬅️ Автошколы", "ad:hl"), HOME],
    ])


def send_school_kit(target: int, school: dict, lang: str) -> bool:
    ok = tg.send_photo_file(target, f"qr_{school['code']}.png", schools.qr_png(school["code"]), schools.kit_text(school, lang),
                            ikb([[url("🖨 " + views.tx(lang, "Плакат", "Плакат", "Cartel", "Poster"), schools.poster_url(school["code"]))]]))
    return ok


def reviews_admin(note: str = "") -> Tuple[str, dict]:
    avg, count = reviews.summary()
    items = store.reviews()
    marks = {"new": "🆕", "approved": "✅", "hidden": "🙈"}
    lines = [f"{marks.get(r['status'], '•')} {'⭐' * r['stars']} {esc(reviews.place(r))}"
             + (f"\n   <i>{esc(r['text'][:120])}</i>" if r.get("text") else "")
             + ("" if r["consent"] else " · без согласия") for r in items[:12]]
    text = (f"⭐ <b>Отзывы</b> · средняя <b>{avg}</b> из {count}\n\n"
            "Бот спрашивает на следующий день после визита. На сайт и в канал — только с согласия человека и после твоей проверки, без имени."
            + ("\n\n<blockquote>" + "\n".join(lines) + "</blockquote>" if lines else "\n\nПока отзывов нет.")
            + (f"\n\n{note}" if note else ""))
    rows = [[btn(f"{'⭐' * r['stars']} {reviews.place(r)[:24]}", f"ad:vc:{r['id']}")]
            for r in items if r["consent"] and r.get("text") and r["status"] == "new"][:8]
    return text, ikb(rows + [[BACK, HOME]])


def review_card(rid: int) -> Tuple[str, dict]:
    r = store.get_review(rid)
    if not r:
        return reviews_admin("Этого отзыва уже нет.")
    text = (f"{'⭐' * r['stars']} · {esc(reviews.place(r))} · {reviews.age(r)} дн. назад\n\n<blockquote>{esc(r.get('text') or '—')}</blockquote>\n"
            + ("✅ Человек разрешил показывать без имени." if r["consent"] else "🙈 Человек не разрешил показывать."))
    rows = [[btn("✅ На сайт", f"ad:va:{rid}", "success"), btn("📢 В канал", f"ad:vp:{rid}")]] if r["consent"] and r.get("text") else []
    return text, ikb(rows + [[btn("🙈 Скрыть", f"ad:vh:{rid}")], [btn("⬅️ Отзывы", "ad:vw"), HOME]])


def group_admin(note: str = "") -> Tuple[str, dict]:
    g = group.info(force=True)
    yes = lambda on: "да" if on else "нет"  # noqa: E731
    on = "✅" if store.setting("group_guard") else "⬜️"
    if g.get("id"):
        r = group.rights()
        text = (f"💬 <b>Группа {esc(g['title'])}</b>\n\n<blockquote>"
                f"Ссылка: {esc(g['link']) or 'нет — дай боту право приглашать или сделай группу публичной'}\n"
                f"Бот в группе: <b>{esc(r.get('status', '?'))}</b> · удалять сообщения: <b>{yes(r.get('delete'))}</b>\n"
                f"Вступили сегодня: <b>{store.metric(store.today_key(), 'group_joined')}</b> · "
                f"удалено сообщений: <b>{store.metric(store.today_key(), 'group_deleted')}</b></blockquote>\n"
                "Что делает бот: здоровается с новичками (одно приветствие, через 10 минут исчезает), удаляет «вступил / вышел», "
                "удаляет продажу записей и ссылки от тех, кто вступил меньше суток назад. Переписку не хранит."
                + ("" if r.get("delete") else "\n\n⚠️ Дай боту право <b>удалять сообщения</b>, иначе порядок наводить он не сможет."))
    else:
        text = ("💬 <b>Группа канала не найдена</b>\n\n"
                "1. Создай группу в Telegram, например «OkSita · чат».\n"
                f"2. Канал {esc(channel.username())} → Изменить → <b>Обсуждение</b> → выбери эту группу. "
                "Посты канала будут появляться в группе, под ними — комментарии.\n"
                "3. Добавь @" + config.BOT_USERNAME + " в группу администратором с правом удалять сообщения.\n"
                "4. Нажми «🔄 Найти группу».\n\n<i>Или укажи группу вручную: @username или id.</i>")
    if note:
        text += f"\n\n{note}"
    rows = [[btn(f"{on} Порядок в группе", "ad:gz"), btn("🔄 Найти группу", "ad:gg")],
            [btn("✏️ Указать вручную", "ad:gs")] + ([btn("↩️ Брать из обсуждения канала", "ad:g0")] if store.setting("group") else [])]
    if g.get("link"):
        rows.append([url("💬 Открыть группу", g["link"])])
    rows.append([btn("⬅️ Канал", "ad:cl"), HOME])
    return text, ikb(rows)


def when(ts: int) -> str:
    return datetime.fromtimestamp(ts, config.TZ).strftime("%d.%m %H:%M")


def queue_view(note: str = "") -> Tuple[str, dict]:
    items = store.queued(("planned", "draft", "failed"))
    fresh = len([t for t in posts.TEMPLATES if t["tag"] not in store.queued_tags()])
    mark = lambda r: f"🕒 {when(r['at'])}" if r["status"] == "planned" else "⚠️" if r["status"] == "failed" else "📝"  # noqa: E731
    lines = [f"{mark(r)} · {esc(channel.preview_line(r))}" for r in items]
    text = ("🗓 <b>Отложенные посты</b>\n\n"
            + ("<blockquote>" + "\n".join(lines) + "</blockquote>\n" if lines else "Пока пусто.\n\n")
            + "<i>Пост выходит в канал в выбранное время, между постами не меньше 10 минут. "
              "Черновики никуда не уходят, пока ты не выберешь время.</i>"
            + (f"\n\n{note}" if note else ""))
    rows = [[btn(f"{mark(r)} {channel.preview_line(r)[:34]}", f"ad:ki:{r['id']}")] for r in items[:12]]
    rows.append([btn("➕ Новый пост", "ad:kn", "success")])
    if fresh:
        rows.append([btn(f"📥 Готовые посты с картинками · {fresh}", "ad:kt")])
    if any(r["status"] == "draft" for r in items):
        rows.append([btn("🗓 Расставить черновики: по одному в день, 19:00", "ad:ka")])
    rows.append([btn("⬅️ Канал", "ad:cl"), BACK])
    return text, ikb(rows)


def queued_card(qid: int, note: str = "") -> Tuple[str, dict]:
    row = store.get_queued(qid)
    if not row:
        return queue_view("Этого поста уже нет.")
    state = {"draft": "📝 Черновик — никуда не уйдёт, пока не выберешь время",
             "planned": f"🕒 Выйдет <b>{when(row['at'])}</b>",
             "sent": f"✅ Вышел {when(row['at'])}" if row.get("at") else "✅ Вышел",
             "failed": "⚠️ Не вышел: проверь права бота в канале"}.get(row["status"], row["status"])
    button = f"🔘 Кнопка: {esc(row['button'] or '')} → {esc(row['url'])}" if row.get("url") else "🔘 Без кнопки"
    text = (f"🗓 <b>Пост №{qid}</b>\n\n{state}\n{esc(channel.preview_line(row))}\n{button}"
            + (f"\n\n{note}" if note else ""))
    rows = [[btn("👁 Показать мне", f"ad:kp:{qid}")]]
    if row["status"] != "sent":
        slots = [btn(label, f"ad:ks:{qid}:{ts}") for label, ts in channel.next_slots()]
        rows += [slots[i:i + 3] for i in range(0, len(slots), 3)]
        rows.append([btn("✏️ Своё время", f"ad:kw:{qid}"), btn("🚀 Сейчас", f"ad:kg:{qid}")])
        if row["status"] == "planned":
            rows.append([btn("⏸ Снять с плана", f"ad:ku:{qid}")])
    rows.append([btn("🗑 Удалить", f"ad:kd:{qid}"), btn("⬅️ Отложенные", "ad:kq")])
    return text, ikb(rows)


QTIME_RE = re.compile(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\s+(\d{1,2})[:.](\d{2})")


def parse_when(text: str, now: Optional[datetime] = None) -> Optional[int]:
    """«05.11 19:00» → unix по Мадриду. Только будущее время, не дальше года."""
    now = now or datetime.now(config.TZ)
    m = QTIME_RE.search(text)
    if not m:
        return None
    d, mo, y, hh, mm = m.groups()
    try:
        year = int(y) + (2000 if len(y) == 2 else 0) if y else now.year
        at = datetime(year, int(mo), int(d), int(hh), int(mm), tzinfo=config.TZ)
        if not y and at < now - timedelta(days=1):
            at = at.replace(year=year + 1)
    except ValueError:
        return None
    return int(at.timestamp()) if now < at < now + timedelta(days=366) else None


def add_queued_post(chat: int, screen: int, p: dict, button: Optional[str], link: Optional[str]) -> None:
    pending.pop(chat, None)
    row = store.add_queued(p["payload"], button, link)
    tg.show(chat, *queued_card(row["id"], "✅ Черновик готов. Выбери время или опубликуй сейчас."), mid=screen)


# ---------- промокоды ----------

def promo_line(p: dict) -> str:
    state = "⏸ " if not p["active"] else "⌛️ " if p["expires_at"] and time.time() > p["expires_at"] else ""
    limit = p["max_uses"] or "∞"
    return f"{state}{p['code']} · {days_text(p['hours'])} · {p['uses']}/{limit}"


def promos_view() -> Tuple[str, dict]:
    items = store.promos()
    rows = [[btn(promo_line(p), f"ad:pi:{p['code']}")] for p in items[:20]]
    rows.append([btn("➕ Новый промокод", "ad:pn", "success")])
    rows.append([BACK])
    return (f"🎟 <b>Промокоды</b> · {len(items)}\n\nСсылка вида <code>t.me/{config.BOT_USERNAME}?start=promo_КОД</code> "
            "сразу дарит Premium. Один человек — одно использование."), ikb(rows)


def promo_card(code: str, note: str = "") -> Tuple[str, dict]:
    p = store.get_promo(code)
    if not p:
        return promos_view()
    link = rewards.promo_link(code)
    until = datetime.fromtimestamp(p["expires_at"], config.TZ).strftime("%d.%m.%Y") if p["expires_at"] else "без срока"
    text = (f"🎟 <b>{esc(code)}</b>\n\n<blockquote>🎁 Даёт: {days_text(p['hours'])} Premium\n"
            f"👥 Использовали: {p['uses']} из {p['max_uses'] or '∞'}\n📅 Действует: {until}\n"
            f"{'✅ Включён' if p['active'] else '⏸ Выключен'}" + (f"\n📝 {esc(p['note'])}" if p.get("note") else "")
            + f"</blockquote>\n<code>{link}</code>" + (f"\n\n{note}" if note else ""))
    return text, ikb([[copy("🔗 Копировать ссылку", link), url("📤 Поделиться", f"https://t.me/share/url?url={link}")],
                      [btn("⏸ Выключить" if p["active"] else "▶️ Включить", f"ad:pt:{code}"),
                       btn("🗑 Удалить", f"ad:pz:{code}", "danger")],
                      [btn("⬅️ Промокоды", "ad:pm"), BACK]])


def promo_step(params: List[str]) -> Tuple[str, dict]:
    """Мастер: срок Premium → лимит использований → срок действия → создать."""
    back = [btn("✖️ Отмена", "ad:pm")]
    if len(params) == 0:
        return "🎟 <b>Новый промокод</b> · шаг 1 из 3\n\nСколько Premium дарит?", ikb([
            [btn(days_text(h), f"ad:pn:{h}") for h in (24, 72, 168)], [btn(days_text(h), f"ad:pn:{h}") for h in (336, 720)], back])
    if len(params) == 1:
        h = params[0]
        return "🎟 <b>Новый промокод</b> · шаг 2 из 3\n\nСколько человек может использовать?", ikb([
            [btn(str(n), f"ad:pn:{h}:{n}") for n in (10, 50, 100)], [btn(str(n), f"ad:pn:{h}:{n}") for n in (500, 1000)],
            [btn("∞ без лимита", f"ad:pn:{h}:0")], back])
    if len(params) == 2:
        h, n = params
        return "🎟 <b>Новый промокод</b> · шаг 3 из 3\n\nСколько дней действует ссылка?", ikb([
            [btn(f"{d} дн.", f"ad:pn:{h}:{n}:{d}") for d in (7, 14, 30)], [btn("∞ без срока", f"ad:pn:{h}:{n}:0")], back])
    return promos_view()


# ---------- задания ----------

def tasks_view() -> Tuple[str, dict]:
    items = store.tasks()
    req = int(store.setting("ref_task") or 0)
    rows = []
    for t in items[:15]:
        mark = "⏸ " if not t["active"] else "🔑 " if t["id"] == req else ""
        rows.append([btn(f"{mark}{t['title_ru'][:32]} · +{days_text(t['hours'])} · ✅ {store.task_count('t:' + str(t['id']))}", f"ad:ti:{t['id']}")])
    rows.append([btn("➕ Канал или группа", "ad:tn:channel", "success"), btn("➕ Ссылка", "ad:tn:link")])
    rows.append([btn(f"👥 Награда за друга: {days_text(int(store.setting('ref_hours')))}", "ad:rh")])
    pct, need = int(store.setting("discount_pct")), int(store.setting("discount_tasks"))
    rows.append([btn("🏷 Скидка на месяц за задания, %", "noop")])
    rows.append([btn(("✅ " if n == pct else "") + (f"−{n}%" if n else "Выкл"), f"ad:dk:pct:{n}") for n in (0, 10, 15, 20)])
    rows.append([btn("🏷 Сколько заданий нужно", "noop")])
    rows.append([btn(("✅ " if n == need else "") + str(n), f"ad:dk:need:{n}") for n in (1, 2, 3)])
    rows.append([BACK])
    done = " · ".join(f"{store.task_count(k)} — {v[0][:18]}" for k, v in rewards.BUILTIN.items())
    return ("📝 <b>Задания</b>\n\n<blockquote>"
            "🔑 Канал, обязательный для награды за друзей. Бот проверяет подписку сам, поэтому его надо сделать "
            "администратором канала (для группы достаточно участника).</blockquote>\n"
            f"<i>Встроенные: {esc(done)}</i>\n"
            f"<i>Скидок открыто: {sum(1 for c in store.all_chats() if c.get('discount_at'))} · использовано: {store.task_count('discount')}</i>"), ikb(rows)


def task_card(tid: int, note: str = "") -> Tuple[str, dict]:
    t = store.get_task(tid)
    if not t:
        return tasks_view()
    required = int(store.setting("ref_task") or 0) == tid
    kind = "канал или группа" if t["kind"] == "channel" else "ссылка"
    text = (f"📝 <b>{esc(t['title_ru'])}</b>\n🇺🇦 {esc(t['title_uk'])}\n🇪🇸 {esc(t.get('title_es') or '—')}\n🇬🇧 {esc(t.get('title_en') or '—')}\n\n<blockquote>Тип: {kind}\n"
            f"Цель: <code>{esc(t['target'])}</code>\nНаграда: {days_text(t['hours'])}\n"
            f"Выполнили: {store.task_count('t:' + str(tid))}\n{'✅ Включено' if t['active'] else '⏸ Выключено'}</blockquote>"
            + (f"\n\n{note}" if note else ""))
    rows = [[btn("⏸ Выключить" if t["active"] else "▶️ Включить", f"ad:tt:{tid}"), btn("🗑 Удалить", f"ad:tz:{tid}", "danger")]]
    if t["kind"] == "channel":
        rows.insert(0, [btn("🔑 Убрать из условия для друзей" if required else "🔑 Обязателен для награды за друзей", f"ad:tr:{tid}")])
    rows.append([btn("⬅️ Задания", "ad:ts"), BACK])
    return text, ikb(rows)


def resolve_target(msg: dict) -> Tuple[Optional[str], Optional[str], str]:
    """Канал или группа из сообщения админа: @name, ссылка t.me или пересланный пост. (цель, ссылка, ошибка)."""
    origin = (msg.get("forward_origin") or {}).get("chat")
    text = (msg.get("text") or "").strip()
    if origin:
        target = str(origin["id"])
    else:
        m = re.fullmatch(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,32})/?|@?([A-Za-z0-9_]{4,32})", text)
        if not m:
            return None, None, "Пришли @username, ссылку t.me/… или перешли пост из канала."
        target = "@" + (m.group(1) or m.group(2))
    info = tg.call("getChat", chat_id=target) or {}
    if not info.get("ok"):
        return None, None, "Бот не видит этот чат. Добавь его туда и повтори."
    chat = info["result"]
    me = (tg.call("getMe") or {}).get("result") or {}
    member = tg.call("getChatMember", chat_id=target, user_id=me.get("id")) or {}
    status = (member.get("result") or {}).get("status")
    if chat.get("type") == "channel" and status != "administrator":
        return None, None, "Сделай бота администратором канала: иначе он не сможет проверять подписку."
    if status not in ("administrator", "creator", "member"):
        return None, None, "Добавь бота в группу и повтори."
    link = f"https://t.me/{chat['username']}" if chat.get("username") else chat.get("invite_link")
    if not link:
        created = tg.call("createChatInviteLink", chat_id=target) or {}
        link = (created.get("result") or {}).get("invite_link")
    if not link:
        return None, None, "Нет ссылки-приглашения: дай боту право приглашать пользователей."
    return target, link, ""


# ---------- реклама ----------

def ads_view() -> Tuple[str, dict]:
    items = store.campaigns()
    audience = len(ads.recipients("all", ignore_gap=True))
    rows = []
    for c in items[:12]:
        ctr = f"{round(c['clicks'] / c['sent'] * 100)}%" if c["sent"] else "—"
        rows.append([btn(f"{'✅' if c['status'] == 'sent' else '📝'} {c['name'][:24]} · {c['sent']} · CTR {ctr}", f"ad:cd:{c['id']}")])
    rows.append([btn("➕ Новая кампания", "ad:cn", "success")])
    rows.append([BACK])
    return ("📣 <b>Реклама</b>\n\n<blockquote>"
            f"👥 Аудитория: <b>{audience}</b> — согласились на предложения партнёров и без Premium\n"
            f"⏱ Не чаще раза в {store.setting('ad_gap')} ч на человека</blockquote>\n"
            "Метка «Реклама» и кнопка отказа добавляются сами. По закону ЕС рекламу можно слать только с согласия: "
            "его дают в настройках или за задание в бонусах."), ikb(rows)


def ad_card(cid: int, note: str = "") -> Tuple[str, dict]:
    c = store.get_campaign(cid)
    if not c:
        return ads_view()
    ctr = f"{round(c['clicks'] / c['sent'] * 100, 1)}%" if c["sent"] else "—"
    audience = len(ads.recipients(c["segment"]))
    text = (f"📣 <b>{esc(c['name'])}</b>\n\n<blockquote>Сегмент: {ads.SEGMENTS.get(c['segment'], c['segment'])}\n"
            f"Кнопка: {esc(c.get('button') or '—')}\nСсылка: {esc(c.get('url') or '—')}\n"
            f"Статус: {'отправлена' if c['status'] == 'sent' else 'черновик'}\n"
            f"Доставлено: {c['sent']} · ошибок: {c['failed']}\nПереходы: <b>{c['clicks']}</b> · CTR {ctr}</blockquote>"
            + (f"\n\n{note}" if note else ""))
    rows = []
    if c["status"] == "draft":
        rows.append([btn("👀 Пример мне", f"ad:cp:{cid}")])
        rows.append([btn(f"🚀 Отправить · {audience}", f"ad:cs:{cid}", "success")])
    rows.append([btn("🗑 Удалить", f"ad:cz:{cid}", "danger"), btn("⬅️ Реклама", "ad:ca")])
    return text, ikb(rows)


# ---------- рассылка ----------

def recipients(segment: str = "all") -> List[int]:
    with_subs = {s["chat"] for s in store.all_subs()}
    out = []
    for c in store.all_chats():
        chat = c["chat"]
        if c.get("role") in ("banned", "pending"):
            continue
        if (segment in config.LANGS and (c.get("lang") or "ru") != segment) or \
                (segment == "subs" and chat not in with_subs) or (segment == "nosubs" and chat in with_subs) or \
                (segment == "paid" and not premium.is_premium(chat)) or (segment == "free" and premium.is_premium(chat)):
            continue
        out.append(chat)
    return out


def broadcast_segments() -> Tuple[str, dict]:
    rows = [[btn(f"{label} ({len(recipients(key))})", f"ad:bg:{key}")] for key, label in SEGMENTS.items()]
    rows.append([BACK])
    return ("📢 <b>Рассылка</b>\n\nНовости самого бота. Для предложений партнёров используй «📣 Реклама».\n"
            "Кому отправить? Число в скобках — сколько человек получат."), ikb(rows)


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
        w.writerows([[csv_safe(v) for v in row] for row in rows])
        return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM — чтобы Excel понял кириллицу

    day = lambda ts: datetime.fromtimestamp(ts, config.TZ).strftime("%Y-%m-%d %H:%M") if ts else ""  # noqa: E731
    subs = store.all_subs()
    per_chat: Dict[int, int] = {}
    for s in subs:
        per_chat[s["chat"]] = per_chat.get(s["chat"], 0) + 1
    users_csv = to_csv(["chat_id", "name", "username", "lang", "role", "source", "joined", "last_seen", "premium_until",
                        "subs", "alerts", "bookings", "ads_ok"],
                       [[c["chat"], c.get("name") or "", c.get("username") or "", c.get("lang") or "", c.get("role"),
                         c.get("source") or "", day(c.get("created_at")), day(c.get("last_seen")), day(c.get("premium_until")),
                         per_chat.get(c["chat"], 0), c.get("alerts") or 0, c.get("bookings") or 0, c.get("ads_ok") or 0]
                        for c in store.all_chats()])
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
    s = store.setting
    interval, fast, free, top = s("interval"), s("interval_premium"), s("free_subs"), s("max_subs")
    paused, approval, notify, maint, report = s("checks_paused"), s("access") == "approval", s("notify_new"), s("maintenance"), s("daily_report")
    mark = lambda on: "🟢" if on else "⚪️"  # noqa: E731
    text = ("⚙️ <b>Настройки бота</b>\n\n<blockquote>"
            f"⏱ Проверка: бесплатно <b>{interval} мин</b> · Premium <b>{fast} мин</b>\n"
            f"🏢 Офисов: бесплатно <b>{free}</b> · Premium <b>{top}</b>\n"
            f"{mark(not paused)} Проверки: <b>{'остановлены' if paused else 'работают'}</b>\n"
            f"{mark(not maint)} Техработы: <b>{'включены' if maint else 'выключены'}</b>\n"
            f"🚪 Доступ: <b>{'по одобрению' if approval else 'открытый'}</b></blockquote>\n"
            "<i>Чем чаще проверки, тем выше риск блокировки сайтом DGT.</i>")
    return text, ikb([
        [btn("⏱ Проверка бесплатно, мин", "noop")],
        [btn(("✅ " if n == interval else "") + f"{n}", f"ad:si:{n}") for n in (15, 30, 45, 60)],
        [btn("⚡️ Проверка Premium, мин", "noop")],
        [btn(("✅ " if n == fast else "") + f"{n}", f"ad:sf:{n}") for n in (5, 7, 10, 15)],
        [btn("🏢 Офисов бесплатно", "noop")],
        [btn(("✅ " if n == free else "") + f"{n}", f"ad:sg:{n}") for n in (1, 2, 3, 5)],
        [btn("💎 Офисов Premium", "noop")],
        [btn(("✅ " if n == top else "") + f"{n}", f"ad:sm:{n}") for n in (5, 10, 15, 20)],
        [btn("▶️ Запустить проверки" if paused else "⏸ Остановить проверки", "ad:sp"),
         btn("🚧 Выключить техработы" if maint else "🚧 Включить техработы", "ad:sw", "danger" if maint else None)],
        [btn("🚪 Сделать открытым" if approval else "🔐 Доступ по одобрению", "ad:sa")],
        [btn(f"{mark(notify)} Новые", "ad:sn"), btn(f"{mark(report)} Отчёт в 21:00", "ad:sr")],
        [BACK],
    ])


def journal_view(kind: str = "all") -> Tuple[str, dict]:
    items = [(ts, text) for ts, text, k in checker.journal if kind == "all" or k == kind][:30]
    lines = [f"{datetime.fromtimestamp(ts, config.TZ):%d.%m %H:%M} {esc(text)}" for ts, text in items]
    body = "<blockquote expandable>" + "\n".join(lines) + "</blockquote>" if lines else "Пока пусто."
    filters = [btn(("• " if key == kind else "") + label, f"ad:l:{key}") for key, label in JOURNAL.items()]
    return (f"📜 <b>Журнал</b> · {JOURNAL[kind]}\n<i>События с последнего перезапуска сервера</i>\n\n{body}",
            ikb([filters[:3], filters[3:], [btn("🔄 Обновить", f"ad:l:{kind}"), BACK]]))


# ---------- ввод от админа ----------

def handle_input(msg: dict) -> bool:
    """Сообщение от админа, которого мы ждали. True — обработано."""
    chat = msg["chat"]["id"]
    p = pending.get(chat)
    if not p or (msg.get("text") or "").startswith("/"):
        return False
    kind, screen = p["kind"], p["screen"]
    if kind == "broadcast":
        p["draft"] = msg["message_id"]
        n = len([c for c in recipients(p["segment"]) if c != chat])
        tg.show(chat, f"📢 Отправить сообщение выше — {SEGMENTS[p['segment']]}: "
                      f"<b>{plural(n, 'пользователю', 'пользователям', 'пользователям')}</b>?",
                ikb([[btn("✅ Отправить", "ad:bs", "success"), btn("✖️ Отмена", "ad:bx")]]), mid=screen)
        return True
    tg.call("deleteMessage", chat_id=chat, message_id=msg["message_id"])
    text = (msg.get("text") or "").strip()
    if kind == "find":
        q = views.fold(text.lstrip("@"))
        found = [c for c in store.all_chats()
                 if q and (q in views.fold(c.get("name") or "") or q in views.fold(c.get("username") or "") or q == str(c["chat"]))][:UPAGE]
        pending.pop(chat, None)
        tg.show(chat, *users(0, found, text[:40]), mid=screen)
    elif kind == "msg":
        target = p["target"]
        hide = ikb([[btn("✖️", "hide")]])
        lang = views.lang_of(target)
        if text:
            sent = tg.send(target, views.tx(lang, "📩 <b>Сообщение от администратора</b>", "📩 <b>Повідомлення від адміністратора</b>",
                                                  "📩 <b>Mensaje del administrador</b>",
                                                  "📩 <b>Message from the administrator</b>")
                           + f"\n\n{esc(text)}", hide) is not None
        else:
            data = tg.call("copyMessage", chat_id=target, from_chat_id=chat, message_id=msg["message_id"], reply_markup=hide) or {}
            sent = bool(data.get("ok"))
        pending.pop(chat, None)
        checker.event(f"✉️ Сообщение пользователю {store.get_chat(target).get('name') or target}", "user")
        tg.show(chat, *user_card(target, chat, "✅ Сообщение отправлено" if sent else "⚠️ Не доставлено — "
                                 "возможно, пользователь заблокировал бота"), mid=screen)
    elif kind == "prices":
        parts = text.split()
        if len(parts) == 3 and all(x.isdigit() and 1 <= int(x) <= 10000 for x in parts):
            for key, value in zip(("price_7", "price_30", "price_90"), parts):
                store.set_setting(key, int(value))
            premium._links.clear()
            pending.pop(chat, None)
            checker.event(f"⚙️ Новые цены: {text}", "money")
            tg.show(chat, *money("✅ Цены обновлены"), mid=screen)
        else:
            tg.show(chat, "✏️ Нужно три числа от 1 до 10000 через пробел, например <code>39 99 249</code>",
                    ikb([[btn("✖️ Отмена", "ad:mn")]]), mid=screen)
    elif kind == "promo_code":
        code = text.upper()
        if not rewards.CODE_RE.match(code):
            tg.show(chat, "Код: 3–32 символа, буквы, цифры, _ и -. Пришли другой или нажми «Создать».", p["kb"], mid=screen)
            return True
        make_promo(chat, screen, p, code)
    elif kind == "task_target":
        target, link, error = resolve_target(msg) if p["task_kind"] == "channel" else (text, text, "") if URL_RE.match(text) else (None, None, "Нужна ссылка https://…")
        if not target:
            tg.show(chat, f"😕 {error}", ikb([[btn("✖️ Отмена", "ad:ts")]]), mid=screen)
            return True
        p.update(kind="task_title", target=target, link=link)
        tg.show(chat, "📝 Название задания одной строкой: <code>Русский | Українською | Español | English</code>\n"
                      "Например: <code>Подпишись на канал | Підпишись на канал | Suscríbete al canal | Join the channel</code>\n"
                      "<i>Если языка нет, покажем английский или русский.</i>",
                ikb([[btn("✖️ Отмена", "ad:ts")]]), mid=screen)
    elif kind == "task_title":
        ru, uk, es, en = ([part.strip()[:60] for part in text.split("|")] + ["", "", ""])[:4]
        p.update(kind="task_hours", ru=ru, uk=uk or ru, es=es, en=en)
        tg.show(chat, "🎁 Какая награда за задание?", ikb([[btn(days_text(h), f"ad:th:{h}") for h in (6, 12, 24)],
                                                           [btn(days_text(h), f"ad:th:{h}") for h in (48, 72)],
                                                           [btn("✖️ Отмена", "ad:ts")]]), mid=screen)
    elif kind == "queue_content":
        payload = ads.payload_from(msg)
        if not payload:
            tg.show(chat, "Пришли текст, фото, видео или GIF.", ikb([[btn("✖️ Отмена", "ad:kq")]]), mid=screen)
            return True
        p.update(kind="queue_button", payload=payload)
        tg.show(chat, "🔘 Кнопка под постом одной строкой: <code>Текст | https://ссылка</code>\n"
                      "Или кнопка бота — откроет @" + config.BOT_USERNAME + ".",
                ikb([[btn("⚡️ Кнопка бота", "ad:kb:bot", "primary"), btn("Без кнопки", "ad:kb:none")],
                     [btn("✖️ Отмена", "ad:kq")]]), mid=screen)
    elif kind == "queue_button":
        label, _, link = text.partition("|")
        if not URL_RE.match(link.strip()):
            tg.show(chat, "Нужно так: <code>Текст | https://ссылка</code>",
                    ikb([[btn("⚡️ Кнопка бота", "ad:kb:bot"), btn("Без кнопки", "ad:kb:none")], [btn("✖️ Отмена", "ad:kq")]]), mid=screen)
            return True
        add_queued_post(chat, screen, p, label.strip()[:32] or "⚡️ OkSita", link.strip())
    elif kind == "school_add":
        name, city = schools.parse_request(text)
        if len(name) < 3:
            tg.show(chat, "Нужно так: <code>Autoescuela Sol, Málaga</code>", ikb([[btn("✖️ Отмена", "ad:hl")]]), mid=screen)
            return True
        pending.pop(chat, None)
        school = schools.create(name, city)
        checker.event(f"🏫 Автошкола: {name}, код {school['code']}", "user")
        tg.show(chat, *school_card(school["id"], "✅ Готово. Открой плакат или пришли QR сюда, чтобы переслать автошколе."), mid=screen)
    elif kind == "group_set":
        value = text.strip()
        if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}|-100\d{6,14}", value):
            tg.show(chat, "Нужно так: <code>@username</code> или <code>-1001234567890</code>", ikb([[btn("✖️ Отмена", "ad:gg")]]), mid=screen)
            return True
        pending.pop(chat, None)
        store.set_setting("group", value)
        tg.show(chat, *group_admin("✅ Группа указана"), mid=screen)
    elif kind == "queue_time":
        at = parse_when(text)
        if not at:
            tg.show(chat, "🕒 Нужно будущее время так: <code>05.11 19:00</code> (по Мадриду)",
                    ikb([[btn("✖️ Отмена", f"ad:ki:{p['qid']}")]]), mid=screen)
            return True
        pending.pop(chat, None)
        channel.plan(p["qid"], at)
        tg.show(chat, *queued_card(p["qid"], f"✅ Выйдет {when(at)}"), mid=screen)
    elif kind == "ad_content":
        payload = ads.payload_from(msg)
        if not payload:
            tg.show(chat, "Пришли текст, фото, видео или GIF.", ikb([[btn("✖️ Отмена", "ad:ca")]]), mid=screen)
            return True
        p.update(kind="ad_button", payload=payload)
        tg.show(chat, "🔗 Кнопка объявления одной строкой: <code>Текст | https://ссылка</code>\nИли пропусти.",
                ikb([[btn("Без кнопки", "ad:cb"), btn("✖️ Отмена", "ad:ca")]]), mid=screen)
    elif kind == "ad_button":
        label, _, link = text.partition("|")
        if not URL_RE.match(link.strip()):
            tg.show(chat, "Нужно так: <code>Текст | https://ссылка</code>", ikb([[btn("Без кнопки", "ad:cb"), btn("✖️ Отмена", "ad:ca")]]), mid=screen)
            return True
        p.update(button=label.strip()[:32], url=link.strip())
        ad_segments(chat, screen)
    return True


def ad_segments(chat: int, screen: int) -> None:
    pending[chat]["kind"] = "ad_segment"
    tg.show(chat, "👥 Кому показать?", ikb([[btn(f"{label} ({len(ads.recipients(key, True))})", f"ad:cg:{key}")]
                                             for key, label in ads.SEGMENTS.items()] + [[btn("✖️ Отмена", "ad:ca")]]), mid=screen)


def make_promo(chat: int, mid: int, p: dict, code: Optional[str]) -> None:
    code = code or rewards.new_code()
    expires = int(time.time()) + p["days"] * 86400 if p["days"] else 0
    made = store.add_promo(code, p["hours"], p["uses"], expires, "")
    pending.pop(chat, None)
    if not made:
        tg.show(chat, "😕 Такой код уже есть.", ikb([[btn("⬅️ Промокоды", "ad:pm")]]), mid=mid)
        return
    checker.event(f"🎟 Новый промокод {code}: {days_text(p['hours'])}", "user")
    tg.show(chat, *promo_card(code, "✅ Готово! Ссылку можно отправлять."), mid=mid)


# ---------- кнопки ----------

def on_callback(chat: int, mid: int, data: str) -> Optional[str]:
    """data — всё после «ad:». Возвращает текст всплывающей подсказки или None."""
    kind, _, rest = data.partition(":")
    keep = kind in ("bs", "th", "cb", "cg", "pc", "bx", "kb")
    p = pending.get(chat)
    if p and not keep:
        pending.pop(chat, None)

    if kind == "":
        tg.show(chat, *panel(), mid=mid, banner=views.banner("admin"))
    elif kind == "bx":
        p = pending.pop(chat, None)
        if p and p.get("draft"):
            tg.call("deleteMessage", chat_id=chat, message_id=p["draft"])
        tg.show(chat, *panel(), mid=mid, banner=views.banner("admin"))
    elif kind == "dk":
        what, _, value = rest.partition(":")
        if what == "pct" and value in ("0", "10", "15", "20"):
            store.set_setting("discount_pct", int(value))
            premium._links.clear()
        elif what == "need" and value in ("1", "2", "3"):
            store.set_setting("discount_tasks", int(value))
        tg.show(chat, *tasks_view(), mid=mid)
    elif kind == "ty":
        if rest.isdigit() and int(rest) in (0, 24, 72, 168):
            store.set_setting("trial_hours", int(rest))
            checker.event(f"⚙️ Пробный период: {rest} ч")
        tg.show(chat, *trial_admin(), mid=mid)
    elif kind == "tp":
        text, _ = views.trial_view(chat)
        tg.show(chat, text, ikb([[btn("⬅️ Пробный период", "ad:ty")]]), mid=mid, banner=views.banner("trial"))
    elif kind == "jq":
        tg.show(chat, *board_admin(), mid=mid)
    elif kind == "jc" and rest.isdigit():
        tg.show(chat, *board_card(int(rest)), mid=mid)
    elif kind == "jp":
        key, _, value = rest.partition(":")
        if key in ("post_job", "post_ad") and value.isdigit():
            store.set_setting(key, int(value))
        tg.show(chat, *board_admin(), mid=mid)
    elif kind == "ja" and rest.isdigit():
        post = store.get_post(int(rest))
        if not post or post["status"] != "review":
            return "Уже решено"
        if not board.publish(post):
            return "Канал не принял пост: проверь права бота"
        checker.event(f"📌 Опубликовано объявление {rest}", "user")
        tg.show(chat, *board_admin("✅ Опубликовано"), mid=mid)
    elif kind == "jr" and rest.isdigit():
        tg.show(chat, f"🚫 Почему отклоняем объявление {rest}?", ikb([
            [btn("Не по правилам", f"ad:jd:{rest}:rules"), btn("Нет контакта", f"ad:jd:{rest}:contact")],
            [btn("Обман или продажа записей", f"ad:jd:{rest}:scam")], [btn("⬅️ Назад", f"ad:jc:{rest}")]]), mid=mid)
    elif kind == "jd":
        pid, _, reason = rest.partition(":")
        post = store.get_post(int(pid)) if pid.isdigit() else None
        if not post or post["status"] != "review" or reason not in board.REASONS:
            return "Уже решено"
        ok = board.reject(post, reason)
        checker.event(f"📌 Отклонено объявление {pid}", "user")
        tg.show(chat, *board_admin("🚫 Отклонено" + ("" if ok else ". ⚠️ Звёзды вернуть не вышло, сделай это вручную")), mid=mid)
    elif kind == "cl":
        tg.show(chat, *channel_admin(), mid=mid)
    elif kind == "cm" and rest.isdigit():
        if int(rest) in (0, 15, 30, 60):
            store.set_setting("channel_delay", int(rest))
        tg.show(chat, *channel_admin(), mid=mid)
    elif kind == "kq":
        tg.show(chat, *queue_view(), mid=mid)
    elif kind == "hl":
        tg.show(chat, *schools_admin(), mid=mid)
    elif kind == "ha":
        pending[chat] = {"kind": "school_add", "screen": mid}
        tg.show(chat, "🏫 Пришли название и город автошколы через запятую: <code>Autoescuela Sol, Málaga</code>",
                ikb([[btn("✖️ Отмена", "ad:hl")]]), mid=mid)
    elif kind == "hn" and rest.lstrip("-").isdigit():
        target = int(rest)
        request = schools.requests.pop(target, None)
        if request is None:
            return "Заявка уже обработана или потерялась при перезапуске — добавь вручную"
        name, city = schools.parse_request(request)
        school = schools.create(name, city, target)
        sent = send_school_kit(target, school, views.lang_of(target))
        checker.event(f"🏫 Автошкола: {name}, код {school['code']}", "user")
        tg.show(chat, *school_card(school["id"], "✅ Код создан, комплект отправлен автошколе" if sent else
                                   "✅ Код создан. ⚠️ Автошколе отправить не вышло — перешли QR сам"), mid=mid)
    elif kind in ("hc", "hq", "hs", "ht") and rest.isdigit():
        school = store.get_school(int(rest))
        if not school:
            tg.show(chat, *schools_admin("Этой автошколы уже нет."), mid=mid)
        elif kind == "hc":
            tg.show(chat, *school_card(school["id"]), mid=mid)
        elif kind == "hq":
            return "🖼 QR отправлен ниже" if send_school_kit(chat, school, "ru") else "⚠️ Не получилось отправить QR"
        elif kind == "hs" and school.get("chat"):
            ok = send_school_kit(school["chat"], school, views.lang_of(school["chat"]))
            return "📨 Отправлено" if ok else "⚠️ Не доставлено"
        elif kind == "ht":
            promo = store.get_promo(school["code"]) or {}
            store.set_promo_active(school["code"], not promo.get("active"))
            tg.show(chat, *school_card(school["id"]), mid=mid)
    elif kind == "vw":
        tg.show(chat, *reviews_admin(), mid=mid)
    elif kind in ("vc", "va", "vp", "vh") and rest.isdigit():
        r = store.get_review(int(rest))
        if not r:
            tg.show(chat, *reviews_admin("Этого отзыва уже нет."), mid=mid)
        elif kind == "vc":
            tg.show(chat, *review_card(r["id"]), mid=mid)
        elif kind == "vh":
            store.set_review(r["id"], status="hidden")
            tg.show(chat, *reviews_admin("🙈 Скрыт"), mid=mid)
        elif not (r["consent"] and r.get("text")):
            return "Человек не разрешил показывать этот отзыв"
        elif kind == "va":
            store.set_review(r["id"], status="approved")
            tg.show(chat, *reviews_admin("✅ Отзыв появится на сайте"), mid=mid)
        elif kind == "vp":
            message = channel.publish(reviews.post_text(r), ikb([[url("⚡️ OkSita", channel.bot_link("review"), "primary")]]))
            if not message:
                return "Канал не принял пост: проверь права бота"
            store.set_review(r["id"], status="approved", message=message)
            tg.show(chat, *reviews_admin("📢 Опубликовано в канале и на сайте"), mid=mid)
    elif kind == "gk":
        store.set_setting("gate", 0 if store.setting("gate") else 1)
        checker.event(f"⚙️ Обязательная подписка на канал: {'вкл' if store.setting('gate') else 'выкл'}")
        tg.show(chat, *channel_admin(), mid=mid)
    elif kind == "gg":
        tg.show(chat, *group_admin(), mid=mid)
    elif kind == "gz":
        store.set_setting("group_guard", 0 if store.setting("group_guard") else 1)
        tg.show(chat, *group_admin(), mid=mid)
    elif kind == "g0":
        store.set_setting("group", "")
        tg.show(chat, *group_admin("↩️ Группа берётся из обсуждения канала"), mid=mid)
    elif kind == "gs":
        pending[chat] = {"kind": "group_set", "screen": mid}
        tg.show(chat, "✏️ Пришли группу: <code>@username</code> или id вида <code>-1001234567890</code>.", ikb([[btn("✖️ Отмена", "ad:gg")]]), mid=mid)
    elif kind in ("kx", "ky"):
        key = "channel_digest" if kind == "kx" else "channel_proof"
        store.set_setting(key, 0 if store.setting(key) else 1)
        tg.show(chat, *channel_admin(), mid=mid)
    elif kind == "kt":
        n = channel.add_templates()
        tg.show(chat, *queue_view(f"📥 Добавлено черновиков: {n}. Открой любой, посмотри и выбери время."), mid=mid)
    elif kind == "ka":
        n = channel.plan_drafts()
        tg.show(chat, *queue_view(f"🗓 Запланировано: {n}, по одному в день в 19:00."), mid=mid)
    elif kind == "kn":
        pending[chat] = {"kind": "queue_content", "screen": mid}
        tg.show(chat, "✍️ Пришли пост для канала: текст, фото, видео или GIF с подписью. Оформление сохранится.",
                ikb([[btn("✖️ Отмена", "ad:kq")]]), mid=mid)
    elif kind == "kb" and p and p.get("kind") == "queue_button":
        if rest == "bot":
            add_queued_post(chat, mid, p, "⚡️ OkSita", channel.bot_link("ch"))
        else:
            add_queued_post(chat, mid, p, None, None)
    elif kind in ("ki", "kp", "kw", "kg", "ku", "kd", "ks"):
        qid_s, _, extra = rest.partition(":")
        row = store.get_queued(int(qid_s)) if qid_s.isdigit() else None
        if not row:
            tg.show(chat, *queue_view("Этого поста уже нет."), mid=mid)
            return None
        qid = row["id"]
        if kind == "ki":
            tg.show(chat, *queued_card(qid), mid=mid)
        elif kind == "kp":
            ok = channel.send_payload(chat, json.loads(row["payload"]), channel.queued_kb(row))
            return "👆 Так пост будет выглядеть в канале" if ok else "⚠️ Не получилось показать пост"
        elif kind == "kw" and row["status"] != "sent":
            pending[chat] = {"kind": "queue_time", "screen": mid, "qid": qid}
            tg.show(chat, "🕒 Когда опубликовать? Например: <code>05.11 19:00</code> (по Мадриду)",
                    ikb([[btn("✖️ Отмена", f"ad:ki:{qid}")]]), mid=mid)
        elif kind == "ks" and extra.isdigit() and row["status"] != "sent":
            channel.plan(qid, int(extra))
            tg.show(chat, *queued_card(qid, f"✅ Выйдет {when(int(extra))}"), mid=mid)
        elif kind == "kg" and row["status"] != "sent":
            ok = channel.publish_queued(qid)
            checker.event(f"📢 Пост №{qid} в канале" + ("" if ok else " — не вышел"), "user")
            tg.show(chat, *queued_card(qid, "✅ Опубликовано" if ok else "⚠️ Канал не принял пост: проверь права бота"), mid=mid)
        elif kind == "ku":
            channel.unplan(qid)
            tg.show(chat, *queued_card(qid, "⏸ Снято с плана, лежит в черновиках"), mid=mid)
        elif kind == "kd":
            channel.drop(qid)
            tg.show(chat, *queue_view("🗑 Удалено"), mid=mid)
    elif kind == "cw":
        status = channel.pin_welcome()
        tg.show(chat, *channel_admin({"ok": "✅ Пост опубликован и закреплён", "pin": "⚠️ Пост опубликован, но закрепить не вышло",
                                      "post": "⚠️ Канал не принял пост: проверь права бота"}[status]), mid=mid)
    elif kind == "pw":
        store.set_setting("maintenance", 0 if store.setting("maintenance") else 1)
        checker.event(f"🚧 Техработы: {'включены' if store.setting('maintenance') else 'выключены'}")
        tg.show(chat, *panel(), mid=mid, banner=views.banner("admin"))
    elif kind == "an":
        tg.show(chat, *analytics(), mid=mid)
    elif kind == "sy":
        tg.show(chat, *system(), mid=mid)
    elif kind == "dg":
        tg.show(chat, "🔌 Проверяю связь…", ikb([]), mid=mid)

        def job() -> None:
            tg.show(chat, *system(f"<pre>{esc(checker.diagnose())}</pre>"), mid=mid)
        threading.Thread(target=job, daemon=True).start()
    elif kind == "u" and re.fullmatch(r"-?\d{1,6}", rest):
        tg.show(chat, *users(int(rest)), mid=mid)
    elif kind == "uf":
        pending[chat] = {"kind": "find", "screen": mid}
        tg.show(chat, "🔎 <b>Поиск пользователя</b>\n\nНапиши имя, @username или chat id.", ikb([[btn("✖️ Отмена", "ad:u:0")]]), mid=mid)
    elif kind == "uc" and rest.lstrip("-").isdigit():
        tg.show(chat, *user_card(int(rest), chat), mid=mid)
    elif kind in ("ub", "ua", "ux", "ux!", "ap", "ar", "um", "gx", "rf") and rest.lstrip("-").isdigit():
        return user_action(chat, mid, kind, int(rest))
    elif kind == "gp":
        target, _, hours = rest.partition(":")
        if target.lstrip("-").isdigit() and hours in ("24", "168", "720"):
            premium.grant(int(target), int(hours), f"admin:{chat}")
            checker.event(f"💎 Выдан Premium {days_text(int(hours))}: {store.get_chat(int(target)).get('name')}", "money")
            tg.show(chat, *user_card(int(target), chat, f"✅ Добавлено {days_text(int(hours))}"), mid=mid)
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
        blocked = store.blocked_keys() ^ {(cid, area)}
        store.set_setting("blocked", ",".join(f"{c}:{a}" for c, a in sorted(blocked)))
        checker.event(f"{'⛔️ Отключена' if (cid, area) in blocked else '▶️ Включена'} проверка: {views.city(cid)} · {views.area_label(area)}")
        tg.show(chat, *office_card(cid, area), mid=mid)
    elif kind == "or":
        cid, _, area = rest.partition(":")
        if checker.site_down():
            return "🔴 Нет связи с сайтом DGT"
        tg.show(chat, *office_card(cid, area, "\n🔄 <i>Проверяю…</i>"), mid=mid)

        def job() -> None:
            checker.run_checks([(cid, area)])
            tg.show(chat, *office_card(cid, area, "\n✅ <i>Проверено только что</i>"), mid=mid)
        threading.Thread(target=job, daemon=True).start()
    elif kind == "mn":
        tg.show(chat, *money(), mid=mid)
    elif kind == "pp":
        if chat not in config.OWNERS:
            return "Цены меняет только владелец"
        pending[chat] = {"kind": "prices", "screen": mid}
        tg.show(chat, "✏️ Новые цены в звёздах: 7, 30 и 90 дней через пробел.\nНапример: <code>39 99 249</code>",
                ikb([[btn("✖️ Отмена", "ad:mn")]]), mid=mid)
    elif kind == "pm":
        tg.show(chat, *promos_view(), mid=mid)
    elif kind == "pn":
        params = [x for x in rest.split(":") if x]
        if not all(x.isdigit() for x in params):
            return None
        if len(params) < 3:
            tg.show(chat, *promo_step(params), mid=mid)
        else:
            kb = ikb([[btn("✨ Создать со случайным кодом", "ad:pc", "success")], [btn("✖️ Отмена", "ad:pm")]])
            pending[chat] = {"kind": "promo_code", "screen": mid, "hours": int(params[0]), "uses": int(params[1]),
                             "days": int(params[2]), "kb": kb}
            tg.show(chat, "🎟 Пришли свой код (например <code>WELCOME3</code>) или создай случайный.", kb, mid=mid)
    elif kind == "pc":
        p = pending.get(chat)
        if p and p["kind"] == "promo_code":
            make_promo(chat, mid, p, None)
    elif kind == "pi":
        tg.show(chat, *promo_card(rest), mid=mid)
    elif kind == "pt":
        promo = store.get_promo(rest)
        if promo:
            store.set_promo_active(rest, not promo["active"])
        tg.show(chat, *promo_card(rest), mid=mid)
    elif kind == "pz":
        store.delete_promo(rest)
        tg.show(chat, *promos_view(), mid=mid)
    elif kind == "ts":
        tg.show(chat, *tasks_view(), mid=mid)
    elif kind == "tn" and rest in ("channel", "link"):
        pending[chat] = {"kind": "task_target", "screen": mid, "task_kind": rest}
        tg.show(chat, ("📝 Пришли @username канала или группы, ссылку t.me/… или перешли пост из канала.\n"
                       "<i>Бот должен быть администратором канала или участником группы.</i>" if rest == "channel"
                       else "📝 Пришли ссылку https://… Награда начисляется после перехода по ней."),
                ikb([[btn("✖️ Отмена", "ad:ts")]]), mid=mid)
    elif kind == "th" and rest.isdigit():
        p = pending.pop(chat, None)
        if p and p["kind"] == "task_hours":
            task = store.add_task(p["task_kind"], p["ru"], p["uk"], p["target"], p["link"], int(rest), p["es"], p["en"])
            checker.event(f"📝 Новое задание: {p['ru']}")
            tg.show(chat, *task_card(task["id"], "✅ Задание создано"), mid=mid)
    elif kind == "ti" and rest.isdigit():
        tg.show(chat, *task_card(int(rest)), mid=mid)
    elif kind == "tt" and rest.isdigit():
        t = store.get_task(int(rest))
        if t:
            store.set_task(t["id"], active=0 if t["active"] else 1)
        tg.show(chat, *task_card(int(rest)), mid=mid)
    elif kind == "tr" and rest.isdigit():
        current = int(store.setting("ref_task") or 0)
        store.set_setting("ref_task", 0 if current == int(rest) else int(rest))
        tg.show(chat, *task_card(int(rest)), mid=mid)
    elif kind == "tz" and rest.isdigit():
        if int(store.setting("ref_task") or 0) == int(rest):
            store.set_setting("ref_task", 0)
        store.delete_task(int(rest))
        tg.show(chat, *tasks_view(), mid=mid)
    elif kind == "rh":
        hours = {24: 48, 48: 72, 72: 12, 12: 24}.get(int(store.setting("ref_hours")), 24)
        store.set_setting("ref_hours", hours)
        tg.show(chat, *tasks_view(), mid=mid)
    elif kind == "ca":
        tg.show(chat, *ads_view(), mid=mid)
    elif kind == "cn":
        pending[chat] = {"kind": "ad_content", "screen": mid}
        tg.show(chat, "📣 <b>Новая кампания</b>\n\nПришли объявление: текст, фото, видео или GIF.\n"
                      "<i>Метку «Реклама» бот добавит сам.</i>", ikb([[btn("✖️ Отмена", "ad:ca")]]), mid=mid)
    elif kind == "cb":
        if pending.get(chat, {}).get("kind") == "ad_button":
            pending[chat].update(button=None, url=None)
            ad_segments(chat, mid)
    elif kind == "cg" and rest in ads.SEGMENTS:
        p = pending.pop(chat, None)
        if p and p["kind"] == "ad_segment":
            stamp = datetime.now(config.TZ).strftime("%d.%m %H:%M")
            camp = store.add_campaign(f"Кампания {stamp}", p["payload"], p.get("button"), p.get("url"), rest)
            tg.show(chat, *ad_card(camp["id"], "Посмотри пример и отправляй."), mid=mid)
    elif kind == "cd" and rest.isdigit():
        tg.show(chat, *ad_card(int(rest)), mid=mid)
    elif kind == "cp" and rest.isdigit():
        camp = store.get_campaign(int(rest))
        if camp and ads.deliver(camp, chat):
            return "👀 Пример отправлен тебе"
    elif kind == "cs" and rest.isdigit():
        camp = store.get_campaign(int(rest))
        if camp and camp["status"] == "draft":
            tg.show(chat, "📣 Отправляю…", ikb([]), mid=mid)

            def done(cid: int, sent: int, failed: int) -> None:
                checker.event(f"📣 Кампания {cid}: доставлено {sent}, ошибок {failed}", "money")
                tg.show(chat, *ad_card(cid, f"✅ Отправлено: {sent}"), mid=mid)
            threading.Thread(target=ads.run, args=(camp["id"], chat, mid, done), daemon=True).start()
    elif kind == "cz" and rest.isdigit():
        store.delete_campaign(int(rest))
        tg.show(chat, *ads_view(), mid=mid)
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
        if chat not in config.OWNERS:
            return "Выгрузка данных — только для владельца"
        threading.Thread(target=export, args=(chat,), daemon=True).start()
        return "📤 Отправляю два CSV-файла…"
    elif kind == "s":
        tg.show(chat, *settings(), mid=mid)
    elif kind in ("si", "sf", "sg", "sm") and rest.isdigit():
        key = {"si": "interval", "sf": "interval_premium", "sg": "free_subs", "sm": "max_subs"}[kind]
        store.set_setting(key, int(rest))
        checker.event(f"⚙️ {key}: {rest}")
        tg.show(chat, *settings(), mid=mid)
    elif kind in ("sp", "sw", "sn", "sr"):
        key = {"sp": "checks_paused", "sw": "maintenance", "sn": "notify_new", "sr": "daily_report"}[kind]
        store.set_setting(key, 0 if store.setting(key) else 1)
        checker.event(f"⚙️ {key}: {'да' if store.setting(key) else 'нет'}")
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
    elif kind == "gx":
        store.set_chat(target, premium_until=int(time.time()), sub_active=0)
        premium.apply_menu_button(target)
        checker.event(f"➖ Снят Premium: {who}", "money")
    elif kind == "rf":
        if chat not in config.OWNERS:
            return "Возврат делает только владелец"
        ok, info = premium.refund_last(target)
        checker.event(f"💸 Возврат {who}: {info}", "money")
        tg.show(chat, *user_card(target, chat, ("✅ " if ok else "😕 ") + esc(info)), mid=mid)
        return None
    elif kind == "ux":
        tg.show(chat, f"🗑 <b>Удалить все подписки {uname(c)}?</b>",
                ikb([[btn("Да, удалить", f"ad:ux!:{target}", "danger"), btn("Отмена", f"ad:uc:{target}")]]), mid=mid)
        return None
    elif kind == "ux!":
        store.forget_chat(target)
        checker.event(f"🗑 Удалены подписки: {who}", "user")
    elif kind in ("ap", "ar") and not protected and c.get("role") == "pending":
        approved = kind == "ap"
        store.set_chat(target, role="user" if approved else "banned")
        checker.event(f"{'✅ Одобрен' if approved else '🚫 Отклонён'}: {who}", "user")
        lang = views.lang_of(target)
        if approved:
            tg.show(target, *views.dashboard(target, c.get("name") or "", None,
                                             views.tx(lang, "✅ <b>Доступ открыт!</b> Добро пожаловать.",
                                                      "✅ <b>Доступ відкрито!</b> Ласкаво просимо.",
                                                            "✅ <b>¡Acceso concedido!</b> Bienvenido.",
                                                            "✅ <b>Access granted!</b> Welcome.")))
        else:
            tg.show(target, *views.banned_view(lang))
    tg.show(chat, *user_card(target, chat), mid=mid)
    return None
