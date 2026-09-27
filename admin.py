"""Админ-панель: статистика, пользователи, офисы, рассылка, настройки бота, журнал."""
from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

import checker
import config
import dgt
import store
import tg
import views
from tg import btn, ikb
from views import esc, fmt_ts, plural

log = logging.getLogger("admin")

pending: Dict[int, dict] = {}  # ждём от админа сообщение: рассылка или личное сообщение пользователю
UPAGE = 8
BACK = btn("⬅️ Админ-панель", "ad")
ROLE_TEXT = {"user": "пользователь", "admin": "⭐️ админ", "banned": "🚫 заблокирован", "pending": "⏳ ждёт одобрения"}


def uname(c: dict) -> str:
    name = esc(c.get("name") or "без имени")
    return name + (f" @{esc(c['username'])}" if c.get("username") else "")


def badge(c: dict) -> str:
    if c["chat"] in config.OWNERS:
        return "👑 "
    return {"admin": "⭐️ ", "banned": "🚫 ", "pending": "⏳ "}.get(c.get("role"), "")


# ---------- экраны ----------

def panel() -> Tuple[str, dict]:
    chats, subs, keys = store.all_chats(), store.all_subs(), store.active_keys()
    now = time.time()
    s = checker.status
    new_day = sum(1 for c in chats if (c.get("created_at") or 0) > now - 86400)
    active_week = sum(1 for c in chats if (c.get("last_seen") or 0) > now - 7 * 86400)
    open_now = sum(1 for k in keys if checker.offices.get(k, {}).get("days"))
    waiting = sum(1 for c in chats if c.get("role") == "pending")
    booked = sum(1 for x in subs if x.get("booked_date"))
    langs = sum(1 for c in chats if c.get("lang") == "uk")
    if store.setting("checks_paused"):
        timing = "⏸ проверки остановлены"
    elif s["next_cycle"]:
        timing = f"следующая через {max(1, math.ceil((s['next_cycle'] - now) / 60))} мин"
    else:
        timing = "первая проверка скоро"
    text = (
        "🛠 <b>Админ-панель</b>\n\n"
        "<blockquote>"
        f"👥 Пользователи: <b>{len(chats)}</b> · +{new_day} за сутки · активны за неделю: {active_week}\n"
        f"📋 Подписки: <b>{len(subs)}</b> · офисов в проверке: {len(keys)}/{config.MAX_OFFICES}\n"
        f"🟢 Офисов с датами сейчас: <b>{open_now}</b>\n"
        f"🔔 Уведомлений отправлено: {s['alerts']}\n"
        f"✅ Записались через бота: <b>{booked}</b>\n"
        f"🌐 Язык: 🇺🇦 {langs} · 🇷🇺 {len(chats) - langs}"
        + (f"\n🙋 Ждут одобрения: <b>{waiting}</b>" if waiting else "")
        + "</blockquote>\n"
        "<blockquote>"
        f"⏱ Каждые {store.setting('interval')} мин · {timing}\n"
        f"✅ Последний цикл: {fmt_ts(s['last_cycle']) if s['last_cycle'] else 'ещё не было'}"
        + (f" ({s['cycle_secs']} с)" if s["last_cycle"] else "") + "\n"
        f"🔎 Проверок: {s['checks']} · ошибок сайта: {s['errors']}\n"
        f"🗄 {'Postgres' if store.PG else 'SQLite'} · {'webhook' if config.PUBLIC_URL else 'polling'}"
        f" · работает {views.fmt_dur(now - s['started'])}"
        "</blockquote>\n"
        "<i>Счётчики — с последнего перезапуска сервера.</i>"
    )
    return text, ikb([
        [btn("👥 Пользователи", "ad:u:0"), btn("🏢 Офисы", "ad:o")],
        [btn("📢 Рассылка", "ad:b"), btn("⚙️ Настройки", "ad:s")],
        [btn("📜 Журнал", "ad:l"), btn("🔄 Обновить", "ad")],
        [views.home_btn("ru")],
    ])


def users(page: int = 0) -> Tuple[str, dict]:
    chats = store.all_chats()
    pages = max(1, math.ceil(len(chats) / UPAGE))
    page %= pages
    rows = []
    for c in chats[page * UPAGE:(page + 1) * UPAGE]:
        n = len(store.subs_of(c["chat"]))
        rows.append([btn(f"{badge(c)}{c.get('name') or c['chat']} · {plural(n, 'подписка', 'подписки', 'подписок')}",
                         f"ad:uc:{c['chat']}")])
    if pages > 1:
        rows.append([btn("◀️", f"ad:u:{page - 1}"), btn(f"{page + 1} / {pages}", "noop"), btn("▶️", f"ad:u:{page + 1}")])
    rows.append([BACK])
    return (f"👥 <b>Пользователи</b> · {len(chats)}\n\n"
            "👑 владелец · ⭐️ админ · 🚫 заблокирован · ⏳ ждёт одобрения\n"
            "<i>Сначала новые. Нажми на пользователя — откроется карточка.</i>"), ikb(rows)


def user_card(target: int, viewer: int, note: str = "") -> Tuple[str, dict]:
    c = store.get_chat(target)
    subs = store.subs_of(target)
    role = "👑 владелец" if target in config.OWNERS else ROLE_TEXT.get(c.get("role"), c.get("role"))
    joined = datetime.fromtimestamp(c["created_at"], config.TZ).strftime("%d.%m.%Y") if c.get("created_at") else "—"
    lines = [f"👤 <b>{uname(c)}</b>",
             "<blockquote>"
             f"🆔 <code>{target}</code>\n🎭 Роль: {role}\n🌐 Язык: {views.LANGS.get(c.get('lang') or '', 'не выбран')}\n"
             f"📅 С нами с {joined}\n"
             f"👀 Был в боте {fmt_ts(c['last_seen']) if c.get('last_seen') else '—'}"
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
    if subs:
        rows.append([btn("🗑 Удалить все подписки", f"ad:ux:{target}")])
    if viewer in config.OWNERS and not protected and c.get("role") in ("user", "admin"):
        rows.append([btn("⭐️ Снять админа" if c.get("role") == "admin" else "⭐️ Сделать админом", f"ad:ua:{target}")])
    rows.append([btn("⬅️ Пользователи", "ad:u:0"), BACK])
    return "\n".join(lines), ikb(rows)


def office_emoji(st: dict) -> str:
    if st.get("fails", 0) >= 3:
        return "⚠️"
    if st.get("days"):
        return "🟢"
    return {dgt.FULL: "🔴", dgt.NO_AREA: "⚪️", dgt.NOT_CONFIGURED: "⚪️"}.get(st.get("status"), "⏳")


def offices_view() -> Tuple[str, dict]:
    groups: Dict[Tuple[str, str], list] = {}
    for s in store.all_subs():
        groups.setdefault((s["centro"], s["area"]), []).append(s)
    rows = []
    for (cid, area), ss in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        st = checker.offices.get((cid, area), {})
        active = sum(1 for s in ss if not s["paused"])
        label = views.area_label(area, ss[0].get("area_label"))
        rows.append([btn(f"{office_emoji(st)} {views.city(cid)} · {label} — 👥 {active}", f"ad:oc:{cid}:{area}")])
    rows.append([BACK])
    text = ("🏢 <b>Офисы под наблюдением</b> · " + str(len(groups)) + "\n\n"
            "🟢 есть даты · 🔴 мест нет · ⚪️ нет такой записи · ⚠️ сайт не отвечает · ⏳ не проверялся\n"
            "<i>👥 — сколько человек следят (без пауз).</i>") if groups else "🏢 Пока никто ни на что не подписан."
    return text, ikb(rows)


def office_card(cid: str, area: str, note: str = "") -> Tuple[str, dict]:
    ss = store.subs_for(cid, area)
    st = checker.offices.get((cid, area), {})
    label = views.area_label(area, ss[0].get("area_label") if ss else None)
    lines = [f"🏢 <b>{esc(views.city(cid))}</b> · {views.area_emoji(label)} {esc(label)}",
             f"<i>{esc(dgt.CENTROS.get(cid, cid))}</i>", ""]
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
    return "\n".join(lines), ikb([[btn("🔄 Проверить сейчас", f"ad:or:{cid}:{area}")],
                                  [btn("⬅️ Офисы", "ad:o"), BACK]])


def broadcast_prompt() -> Tuple[str, dict]:
    n = len(recipients())
    return (f"📢 <b>Рассылка</b>\n\nПришли сообщение — его получат все пользователи ({n}).\n"
            "Можно текст с форматированием, фото или видео с подписью.\n\n"
            "<i>Перед отправкой покажу подтверждение.</i>", ikb([[btn("✖️ Отмена", "ad:bx")]]))


def settings() -> Tuple[str, dict]:
    interval, max_subs = store.setting("interval"), store.setting("max_subs")
    paused, approval, notify = store.setting("checks_paused"), store.setting("access") == "approval", store.setting("notify_new")
    text = ("⚙️ <b>Настройки бота</b>\n\n<blockquote>"
            f"⏱ Проверка каждые <b>{interval} мин</b>\n"
            f"📋 Подписок на человека: <b>{max_subs}</b>\n"
            f"🔎 Проверки: <b>{'остановлены' if paused else 'работают'}</b>\n"
            f"🚪 Доступ: <b>{'по одобрению' if approval else 'открытый'}</b>\n"
            f"🔔 Сообщать о новых пользователях: <b>{'да' if notify else 'нет'}</b></blockquote>\n"
            "<i>Проверять чаще 10 минут не советую — сайт DGT начинает тормозить.\n"
            "«По одобрению» — новые пользователи ждут, пока админ их пустит.</i>")
    return text, ikb([
        [btn(("✅ " if n == interval else "") + f"{n} мин", f"ad:si:{n}") for n in (5, 10, 15, 20, 30)],
        [btn(("✅ " if n == max_subs else "") + f"{n} подп.", f"ad:sm:{n}") for n in (1, 3, 5, 10)],
        [btn("▶️ Запустить проверки" if paused else "⏸ Остановить проверки", "ad:sp")],
        [btn("🚪 Сделать открытым" if approval else "🔐 Доступ по одобрению", "ad:sa")],
        [btn(f"🔔 Новые пользователи: {'вкл' if notify else 'выкл'}", "ad:sn")],
        [BACK],
    ])


def journal_view() -> Tuple[str, dict]:
    items = [f"{datetime.fromtimestamp(ts, config.TZ):%d.%m %H:%M} {esc(text)}" for ts, text in list(checker.journal)[:25]]
    body = "<blockquote expandable>" + "\n".join(items) + "</blockquote>" if items else "Пока пусто."
    return (f"📜 <b>Журнал</b>\n<i>События с последнего перезапуска сервера</i>\n\n{body}",
            ikb([[btn("🔄 Обновить", "ad:l"), BACK]]))


# ---------- действия ----------

def recipients() -> list:
    return [c["chat"] for c in store.all_chats() if c.get("role") not in ("banned", "pending")]


def run_broadcast(admin_chat: int, draft: int, screen: int) -> None:
    targets = [c for c in recipients() if c != admin_chat]
    ok = fail = 0
    hide = ikb([[btn("✖️ Скрыть", "hide")]])
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
    checker.event(f"📢 Рассылка: доставлено {ok}, не доставлено {fail}")
    tg.show(admin_chat, f"✅ <b>Рассылка завершена</b>\n\nДоставлено: <b>{ok}</b>\nНе доставлено: {fail}"
                        + ("\n<i>Не доставлено — обычно те, кто заблокировал бота.</i>" if fail else ""),
            ikb([[BACK]]), mid=screen)


def handle_input(msg: dict) -> bool:
    """Сообщение от админа, которого мы ждали (рассылка или письмо пользователю). True — обработано."""
    chat = msg["chat"]["id"]
    p = pending.get(chat)
    if not p or (msg.get("text") or "").startswith("/"):
        return False
    if p["kind"] == "broadcast":
        p["draft"] = msg["message_id"]
        n = len([c for c in recipients() if c != chat])
        tg.show(chat, f"📢 Отправить сообщение выше <b>{plural(n, 'пользователю', 'пользователям', 'пользователям')}</b>?",
                ikb([[btn("✅ Отправить", "ad:bs"), btn("✖️ Отмена", "ad:bx")]]), mid=p["screen"])
        return True
    if p["kind"] == "msg":
        target = p["target"]
        hide = ikb([[btn("✖️ Скрыть", "hide")]])
        if msg.get("text"):
            sent = tg.send(target, f"📩 <b>Сообщение от администратора</b>\n\n{esc(msg['text'])}", hide) is not None
        else:
            data = tg.call("copyMessage", chat_id=target, from_chat_id=chat, message_id=msg["message_id"],
                           reply_markup=hide) or {}
            sent = bool(data.get("ok"))
        tg.call("deleteMessage", chat_id=chat, message_id=msg["message_id"])
        pending.pop(chat, None)
        checker.event(f"✉️ Сообщение пользователю {store.get_chat(target).get('name') or target}")
        tg.show(chat, *user_card(target, chat, "✅ Сообщение отправлено" if sent else "⚠️ Не доставлено — "
                                 "возможно, пользователь заблокировал бота"), mid=p["screen"])
        return True
    return False


def on_callback(chat: int, mid: int, data: str) -> Optional[str]:
    """data — всё после «ad:». Возвращает текст всплывающей подсказки или None."""
    kind, _, rest = data.partition(":")
    if kind != "bs":
        p = pending.pop(chat, None)
        if p and p.get("draft") and kind == "bx":
            tg.call("deleteMessage", chat_id=chat, message_id=p["draft"])

    if kind in ("", "bx"):
        tg.show(chat, *panel(), mid=mid)
    elif kind == "u":
        tg.show(chat, *users(int(rest or 0)), mid=mid)
    elif kind == "uc" and rest.lstrip("-").isdigit():
        tg.show(chat, *user_card(int(rest), chat), mid=mid)
    elif kind in ("ub", "ua", "ux", "ux!", "ap", "ar", "um") and rest.lstrip("-").isdigit():
        return user_action(chat, mid, kind, int(rest))
    elif kind == "o":
        tg.show(chat, *offices_view(), mid=mid)
    elif kind == "oc":
        cid, _, area = rest.partition(":")
        tg.show(chat, *office_card(cid, area), mid=mid)
    elif kind == "or":
        cid, _, area = rest.partition(":")
        tg.show(chat, *office_card(cid, area, "\n🔄 <i>Проверяю…</i>"), mid=mid)

        def job() -> None:
            checker.run_checks([(cid, area)])
            tg.show(chat, *office_card(cid, area, "\n✅ <i>Проверено только что</i>"), mid=mid)
        threading.Thread(target=job, daemon=True).start()
    elif kind == "b":
        pending[chat] = {"kind": "broadcast", "screen": mid}
        tg.show(chat, *broadcast_prompt(), mid=mid)
    elif kind == "bs":
        p = pending.pop(chat, None)
        if not p or not p.get("draft"):
            return "Сначала пришли сообщение для рассылки"
        tg.show(chat, "📢 Отправляю…", ikb([]), mid=mid)
        threading.Thread(target=run_broadcast, args=(chat, p["draft"], mid), daemon=True).start()
    elif kind == "s":
        tg.show(chat, *settings(), mid=mid)
    elif kind in ("si", "sm") and rest.isdigit():
        store.set_setting("interval" if kind == "si" else "max_subs", int(rest))
        checker.event(f"⚙️ {'Интервал' if kind == 'si' else 'Лимит подписок'}: {rest}")
        tg.show(chat, *settings(), mid=mid)
    elif kind == "sp":
        store.set_setting("checks_paused", 0 if store.setting("checks_paused") else 1)
        checker.event("⏸ Проверки остановлены" if store.setting("checks_paused") else "▶️ Проверки запущены")
        tg.show(chat, *settings(), mid=mid)
    elif kind == "sa":
        store.set_setting("access", "open" if store.setting("access") == "approval" else "approval")
        checker.event(f"🚪 Доступ: {'по одобрению' if store.setting('access') == 'approval' else 'открытый'}")
        tg.show(chat, *settings(), mid=mid)
    elif kind == "sn":
        store.set_setting("notify_new", 0 if store.setting("notify_new") else 1)
        tg.show(chat, *settings(), mid=mid)
    elif kind == "l":
        tg.show(chat, *journal_view(), mid=mid)
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
            checker.event(f"✅ Разблокирован: {who}")
        else:
            store.set_chat(target, role="banned")
            store.pause_chat(target)
            checker.event(f"🚫 Заблокирован: {who}")
    elif kind == "ua" and chat in config.OWNERS and not protected:
        store.set_chat(target, role="user" if c.get("role") == "admin" else "admin")
        checker.event(f"⭐️ {'Снят админ' if c.get('role') == 'admin' else 'Новый админ'}: {who}")
    elif kind == "ux":
        tg.show(chat, f"🗑 <b>Удалить все подписки {uname(c)}?</b>",
                ikb([[btn("Да, удалить", f"ad:ux!:{target}"), btn("Отмена", f"ad:uc:{target}")]]), mid=mid)
        return None
    elif kind == "ux!":
        store.forget_chat(target)
        checker.event(f"🗑 Удалены подписки: {who}")
    elif kind in ("ap", "ar"):
        approved = kind == "ap"
        store.set_chat(target, role="user" if approved else "banned")
        checker.event(f"{'✅ Одобрен' if approved else '🚫 Отклонён'}: {who}")
        if approved:
            lang = views.lang_of(target)
            tg.show(target, *views.dashboard(target, c.get("name") or "", checker.status.get("next_cycle"),
                                             views.tx(lang, "✅ <b>Доступ открыт!</b> Добро пожаловать.",
                                                      "✅ <b>Доступ відкрито!</b> Ласкаво просимо.")))
        else:
            tg.show(target, *views.banned_view(views.lang_of(target)))
    tg.show(chat, *user_card(target, chat), mid=mid)
    return None
