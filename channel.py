"""Канал: бесплатные даты DGT с задержкой и закреплённый пост. В боте те же даты приходят сразу, поэтому канал ведёт людей в бота."""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Dict, Optional, Tuple

import config
import dgt
import store
import tg
import views
from tg import ikb, url

log = logging.getLogger("channel")

GAP = 10 * 60          # минимум между постами о датах
MAX_DAY = 24           # постов о датах в сутки
REPEAT = 6 * 3600      # об одном офисе — не чаще
_queue: Dict[Tuple[str, str], float] = {}   # офис → когда появились даты
_posted: Dict[Tuple[str, str], float] = {}  # офис → когда писали о нём
_sent = {"at": 0.0, "day": "", "count": 0}


def username() -> str:
    return str(store.setting("channel") or "")


def link(message: Optional[int] = None) -> str:
    name = username().lstrip("@")
    return f"https://t.me/{name}" + (f"/{message}" if message else "")


def enabled() -> bool:
    return bool(username() and store.setting("channel_delay"))


def on_opened(cid: str, area: str) -> None:
    """В офисе появились даты. В канал они попадут после задержки, если их ещё не разобрали."""
    if enabled() and time.time() - _posted.get((cid, area), 0) > REPEAT:
        _queue.setdefault((cid, area), time.time())


def publish(text: str, kb: Optional[dict] = None, photo: Optional[str] = None, silent: bool = False) -> Optional[int]:
    """Публикует пост. Возвращает номер сообщения или None."""
    p = {"chat_id": username(), "parse_mode": "HTML", "disable_notification": silent}
    if kb:
        p["reply_markup"] = kb
    if photo:
        data = tg.call("sendPhoto", photo=photo, caption=text, **p)
    else:
        data = tg.call("sendMessage", text=text, link_preview_options={"is_disabled": True}, **p)
    if not data or not data.get("ok"):
        log.warning("канал не принял пост: %s", (data or {}).get("description"))
        return None
    return data["result"]["message_id"]


def dates_post(cid: str, area: str, days: list) -> str:
    first, last = date.fromisoformat(days[0][0]), date.fromisoformat(days[-1][0])
    span = f"{first:%d.%m}" + (f" – {last:%d.%m}" if first != last else "")
    return (f"🟢 <b>{views.esc(views.city(cid))}</b> · {views.esc(views.area_label(area))}\n"
            f"📅 <b>{span}</b> · {len(days)}\n\n"
            "<i>🇺🇦 Є вільні дати · 🇷🇺 Есть свободные даты\n🇪🇸 Hay fechas libres · 🇬🇧 Free dates available</i>\n"
            f"⏱ +{store.setting('channel_delay')} min")


def bot_link(start: str) -> str:
    return f"https://t.me/{config.BOT_USERNAME}?start={start}"


def tick(offices: dict, now: Optional[float] = None) -> None:
    """Раз в минуту: публикует самый старый готовый пост, если даты ещё есть и лимит не исчерпан."""
    now = now or time.time()
    if not enabled():
        _queue.clear()
        return
    wait, today = int(store.setting("channel_delay")) * 60, store.today_key()
    if _sent["day"] != today:
        _sent.update(day=today, count=0)
    for key, opened in sorted(_queue.items(), key=lambda kv: kv[1]):
        if now - opened < wait:
            continue
        days = views.all_days(offices.get(key, {}).get("results"))
        if not days:
            _queue.pop(key, None)  # уже разобрали: пост устарел бы сразу
            continue
        if now - _sent["at"] < GAP or _sent["count"] >= MAX_DAY:
            return
        _queue.pop(key, None)
        kb = ikb([[url("⚡️ OkSita", bot_link("ch"), "primary"), url("📝 DGT", dgt.START_URL)]])
        if publish(dates_post(*key, days), kb):
            _posted[key] = now
            _sent.update(at=now, count=_sent["count"] + 1)
            store.bump("channel_posts")
        return


def welcome_text() -> str:
    return ("🇪🇸 <b>OkSita</b>\n\n"
            "🇺🇦 Вільні дати DGT, вакансії та корисне для життя в Іспанії.\n"
            "🇷🇺 Свободные даты DGT, вакансии и полезное для жизни в Испании.\n"
            "🇪🇸 Citas libres de la DGT, empleo y utilidades para vivir en España.\n"
            "🇬🇧 Free DGT dates, jobs and useful tips for life in Spain.\n\n"
            "<i>⚡️ @" + config.BOT_USERNAME + "</i>")


def welcome_kb() -> dict:
    return ikb([[url("🤖 OkSita", bot_link("ch"), "primary")],
                [url("💼 Empleo · Вакансии", bot_link("post")), url("🤝 Partners", bot_link("partner"))]])


def pin_welcome() -> str:
    """Закреплённый пост: ok | post — не смог опубликовать | pin — опубликовал, но не закрепил."""
    mid = publish(welcome_text(), welcome_kb(), silent=True)
    if not mid:
        return "post"
    data = tg.call("pinChatMessage", chat_id=username(), message_id=mid, disable_notification=True)
    return "ok" if data and data.get("ok") else "pin"


def rights() -> dict:
    """Что бот может в канале: post, pin и подпись для админки."""
    data = tg.call("getChatMember", chat_id=username(), user_id=int(config.TOKEN.split(":")[0]))
    me = (data or {}).get("result") or {}
    return {"post": bool(me.get("can_post_messages")), "pin": bool(me.get("can_pin_messages") or me.get("can_edit_messages")),
            "status": me.get("status") or "?"}
