"""Группа (чат) канала: приветствие новичков, чистый чат и защита от продавцов записей.

Группу создаёт владелец в Telegram и привязывает к каналу как обсуждение (канал → Изменить → Обсуждение).
Бот должен быть в ней администратором с правом удалять сообщения. Группу бот находит сам через getChat канала
(linked_chat_id) или берёт из настройки «group». Бот не читает и не хранит переписку: смотрит только на то,
нет ли в сообщении продажи записей или ссылок от только что вступившего."""
from __future__ import annotations

import html
import logging
import re
import threading
import time
from typing import Callable, Dict, List, Optional, Set, Tuple

import config
import store
import tg
from tg import ikb, url

log = logging.getLogger("group")

WELCOME_TTL = 10 * 60   # приветствие висит 10 минут, и в группе всегда только одно
WARN_TTL = 90           # предупреждение после удаления — полторы минуты
NEWBIE = 24 * 3600      # первые сутки после вступления ссылки нельзя: так пишут спамеры
INFO_TTL = 3600
ADMINS_TTL = 600
LINK_RE = re.compile(r"https?://|www\.|t\.me/|telegram\.me/|@[A-Za-z0-9_]{4,}", re.I)
_info: Dict[str, object] = {"at": 0.0}
_admins: Dict[int, Tuple[Set[int], float]] = {}
_joined: Dict[Tuple[int, int], float] = {}
_welcome: Dict[int, int] = {}
_trash: List[Tuple[int, int, float]] = []   # (группа, сообщение, когда удалить)
_lock = threading.Lock()
notify: Callable[[str], None] = lambda text: None  # подставляет checker: письмо админам


def _chat(target: object) -> dict:
    result = (tg.call("getChat", chat_id=target) or {}).get("result")
    return result if isinstance(result, dict) else {}


def info(force: bool = False) -> dict:
    """Группа и её ссылка. Настройка «group» важнее группы обсуждения канала. Ответ Telegram помним час."""
    if not force and time.time() - float(_info["at"]) < INFO_TTL:
        return dict(_info)
    target = str(store.setting("group") or "")
    if not target and store.setting("channel"):
        target = str(_chat(store.setting("channel")).get("linked_chat_id") or "")
    found = _chat(target) if target else {}
    _info.clear()
    _info.update(at=time.time(), id=found.get("id"), title=found.get("title") or "", username=found.get("username") or "",
                 link=(f"https://t.me/{found['username']}" if found.get("username") else found.get("invite_link") or ""))
    return dict(_info)


def link() -> str:
    return str(info().get("link") or "")


def ours(chat: dict) -> bool:
    gid = info().get("id")
    return bool(gid) and chat.get("id") == gid


def admins(gid: int) -> Set[int]:
    hit = _admins.get(gid)
    if hit and time.time() - hit[1] < ADMINS_TTL:
        return hit[0]
    data = (tg.call("getChatAdministrators", chat_id=gid) or {}).get("result")
    ids = {((m.get("user") or {}).get("id")) for m in data} if isinstance(data, list) else set()
    _admins[gid] = (ids, time.time())
    return ids


def rights() -> dict:
    """Что бот может в группе — для админки."""
    gid = info().get("id")
    if not gid:
        return {}
    me = (tg.call("getChatMember", chat_id=gid, user_id=int(config.TOKEN.split(":")[0])) or {}).get("result")
    me = me if isinstance(me, dict) else {}
    return {"status": me.get("status") or "?", "delete": bool(me.get("can_delete_messages")),
            "restrict": bool(me.get("can_restrict_members")), "invite": bool(me.get("can_invite_users"))}


def later(gid: int, mid: Optional[int], ttl: float) -> None:
    if mid:
        with _lock:
            _trash.append((gid, mid, time.time() + ttl))


def sweep(now: Optional[float] = None) -> int:
    """Раз в минуту: удаляем устаревшие приветствия и предупреждения."""
    now = now or time.time()
    with _lock:
        due = [t for t in _trash if t[2] <= now]
        _trash[:] = [t for t in _trash if t[2] > now]
    for gid, mid, _ in due:
        tg.call("deleteMessage", chat_id=gid, message_id=mid)
        if _welcome.get(gid) == mid:
            _welcome.pop(gid, None)
    return len(due)


def bot_link(start: str) -> str:
    return f"https://t.me/{config.BOT_USERNAME}?start={start}"


def name_of(user: dict) -> str:
    return html.escape(str(user.get("first_name") or user.get("username") or "🙂")[:32])


def welcome_text(people: List[dict]) -> str:
    names = ", ".join(name_of(p) for p in people[:3]) + (" …" if len(people) > 3 else "")
    return (f"👋 <b>{names}</b>, вітаємо в чаті OkSita! · добро пожаловать!\n\n"
            "🇺🇦 Питай і ділись досвідом: DGT, права, документи, життя в Іспанії.\n"
            "🇷🇺 Спрашивай и делись опытом: DGT, права, документы, жизнь в Испании.\n"
            "🇪🇸 Pregunta y comparte: DGT, carnet, papeles, vida en España.\n\n"
            "📌 <i>Без продажу записів (cita) і спаму · без продажи записей и спама. "
            "Вакансії й реклама — через бота · вакансии и реклама — через бота.</i>")


def welcome_kb() -> dict:
    return ikb([[url("⚡️ Вільні дати DGT · Свободные даты", bot_link("group"), "primary")],
                [url("💼 Вакансія · Вакансия", bot_link("post-group")), url("📢 Канал", channel_link())]])


def channel_link() -> str:
    return f"https://t.me/{str(store.setting('channel') or '').lstrip('@')}"


def welcome(gid: int, people: List[dict]) -> None:
    old = _welcome.pop(gid, None)
    if old:
        tg.call("deleteMessage", chat_id=gid, message_id=old)
        with _lock:
            _trash[:] = [t for t in _trash if t[:2] != (gid, old)]
    data = tg.call("sendMessage", chat_id=gid, text=welcome_text(people), parse_mode="HTML", reply_markup=welcome_kb(),
                   disable_notification=True, link_preview_options={"is_disabled": True}) or {}
    mid = (data.get("result") or {}).get("message_id")
    if mid:
        _welcome[gid] = mid
        later(gid, mid, WELCOME_TTL)


def warn_text(reason: str, user: dict) -> str:
    who = name_of(user)
    if reason == "resale":
        return (f"🚫 {who}, продаж записів (cita) тут заборонений · продажа записей здесь запрещена. "
                f"Запис безкоштовний, а вільні дати шукає @{config.BOT_USERNAME}.")
    return (f"⏳ {who}, посилання — через добу після вступу · ссылки — через сутки после вступления. "
            "Вакансії й рекламу публікуємо через бота · вакансии и рекламу — через бота.")


def verdict(msg: dict, gid: int) -> Optional[str]:
    """resale — продажа записей, newbie — ссылка от вступившего меньше суток назад, None — всё в порядке."""
    import board  # board тянет за собой checker, поэтому здесь
    text = msg.get("text") or msg.get("caption") or ""
    if board.RESALE_RE.search(text):
        return "resale"
    user = (msg.get("from") or {}).get("id")
    fresh = time.time() - _joined.get((gid, user), 0) < NEWBIE
    links = LINK_RE.search(text) or any(e.get("type") in ("url", "text_link", "mention", "text_mention")
                                         for e in (msg.get("entities") or []) + (msg.get("caption_entities") or []))
    return "newbie" if fresh and links else None


def on_message(msg: dict) -> None:
    chat = msg.get("chat") or {}
    if not store.setting("group_guard") or not ours(chat):
        return
    gid, mid = chat["id"], msg["message_id"]
    if msg.get("new_chat_members"):
        tg.call("deleteMessage", chat_id=gid, message_id=mid)
        people = [m for m in msg["new_chat_members"] if not m.get("is_bot")]
        now = time.time()
        for m in people:
            _joined[(gid, m["id"])] = now
        if people:
            welcome(gid, people)
            store.bump("group_joined", len(people))
        return
    if msg.get("left_chat_member"):
        tg.call("deleteMessage", chat_id=gid, message_id=mid)
        return
    frm = msg.get("from") or {}
    if msg.get("is_automatic_forward") or msg.get("sender_chat") or frm.get("is_bot") or not frm.get("id"):
        return  # посты канала, анонимные админы и боты
    text = msg.get("text") or ""
    if re.match(rf"/(start|oksita|bot)(@{re.escape(config.BOT_USERNAME)})?\b", text, re.I):
        tg.call("deleteMessage", chat_id=gid, message_id=mid)
        data = tg.call("sendMessage", chat_id=gid, text=f"⚡️ @{config.BOT_USERNAME}", reply_markup=welcome_kb(),
                       disable_notification=True) or {}
        later(gid, (data.get("result") or {}).get("message_id"), WARN_TTL)
        return
    if frm["id"] in admins(gid):
        return
    reason = verdict(msg, gid)
    if not reason:
        return
    tg.call("deleteMessage", chat_id=gid, message_id=mid)
    extra = {"reply_markup": ikb([[url("💼 Через бота", bot_link("post-group"))]])} if reason == "newbie" else {}
    data = tg.call("sendMessage", chat_id=gid, text=warn_text(reason, frm), parse_mode="HTML", disable_notification=True, **extra) or {}
    later(gid, (data.get("result") or {}).get("message_id"), WARN_TTL)
    store.bump("group_deleted")
    if reason == "resale":
        notify(f"🚫 <b>Группа:</b> удалено сообщение о продаже записей от {name_of(frm)} (<code>{frm['id']}</code>)\n\n"
               f"<blockquote>{html.escape((msg.get('text') or msg.get('caption') or '')[:400])}</blockquote>")
