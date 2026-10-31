"""Реклама: кампании партнёров с меткой, согласием получателя и подсчётом переходов."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import List, Optional

import config
import premium
import store
import tg
from tg import btn, ikb, url

log = logging.getLogger("ads")

SEGMENTS = {"all": "👥 Все согласившиеся", "ru": "🇷🇺 Русский язык", "uk": "🇺🇦 Украинский язык",
            "subs": "📋 С подписками", "nosubs": "💤 Без подписок"}
LABEL = {"ru": "📣 Реклама", "uk": "📣 Реклама"}


def payload_from(msg: dict) -> Optional[dict]:
    """Запоминает объявление из сообщения админа: текст или медиа по file_id."""
    if msg.get("text"):
        return {"type": "text", "text": msg["text"], "entities": msg.get("entities") or []}
    for kind in ("photo", "video", "animation"):
        media = msg.get(kind)
        if media:
            file_id = media[-1]["file_id"] if kind == "photo" else media["file_id"]
            return {"type": kind, "file": file_id, "text": msg.get("caption") or "",
                    "entities": msg.get("caption_entities") or []}
    return None


def _utf16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _labelled(payload: dict, lang: str):
    """Добавляет метку «Реклама» в начало: у разметки сдвигаются позиции."""
    prefix = f"{LABEL[lang]}\n\n"
    shift = _utf16(prefix)
    entities = [dict(e, offset=e["offset"] + shift) for e in payload.get("entities", [])]
    return prefix + payload.get("text", ""), entities


def click_url(cid: int, chat: int) -> str:
    sig = hmac.new(config.LINK_KEY, f"{cid}:{chat}".encode(), hashlib.sha256).hexdigest()[:16]
    return f"{config.PUBLIC_URL}/r/{cid}/{chat}/{sig}"


def resolve_click(cid: int, chat: int, sig: str) -> Optional[str]:
    """Проверяет подпись ссылки и считает переход. Цель берётся только из кампании — открытого редиректа нет."""
    good = hmac.new(config.LINK_KEY, f"{cid}:{chat}".encode(), hashlib.sha256).hexdigest()[:16]
    camp = store.get_campaign(cid)
    if not camp or not hmac.compare_digest(good, sig) or not camp.get("url"):
        return None
    store.ad_click(cid, chat)
    store.bump("ad_clicks")
    return camp["url"]


def keyboard(camp: dict, chat: int, lang: str) -> dict:
    rows = []
    if camp.get("url"):
        rows.append([url(camp.get("button") or ("Подробнее" if lang == "ru" else "Детальніше"),
                         click_url(camp["id"], chat), "primary")])
    rows.append([btn("🔕 Отключить" if lang == "ru" else "🔕 Вимкнути", "noads"),
                 btn("✖️ Скрыть" if lang == "ru" else "✖️ Сховати", "hide")])
    return ikb(rows)


def deliver(camp: dict, chat: int) -> bool:
    payload = json.loads(camp["payload"])
    lang = store.get_chat(chat).get("lang") or "ru"
    text, entities = _labelled(payload, lang)
    kb = keyboard(camp, chat, lang)
    if payload["type"] == "text":
        data = tg.call("sendMessage", chat_id=chat, text=text, entities=entities, reply_markup=kb,
                       link_preview_options={"is_disabled": True})
    else:
        method = {"photo": "sendPhoto", "video": "sendVideo", "animation": "sendAnimation"}[payload["type"]]
        data = tg.call(method, chat_id=chat, caption=text, caption_entities=entities, reply_markup=kb,
                       **{payload["type"]: payload["file"]})
    data = data or {}
    if data.get("error_code") == 403:
        store.pause_chat(chat)
    return bool(data.get("ok"))


def recipients(segment: str, ignore_gap: bool = False) -> List[int]:
    """Только те, кто сам согласился на предложения партнёров. Premium рекламу не получает."""
    gap = int(store.setting("ad_gap")) * 3600
    now = time.time()
    with_subs = {s["chat"] for s in store.all_subs()}
    out = []
    for c in store.all_chats():
        chat = c["chat"]
        if not c.get("ads_ok") or c.get("role") in ("banned", "pending") or premium.is_premium(chat):
            continue
        if not ignore_gap and now - (c.get("last_ad") or 0) < gap:
            continue
        if (segment in ("ru", "uk") and (c.get("lang") or "ru") != segment) or \
                (segment == "subs" and chat not in with_subs) or (segment == "nosubs" and chat in with_subs):
            continue
        out.append(chat)
    return out


def run(cid: int, admin_chat: int, screen: int, done) -> None:
    camp = store.get_campaign(cid)
    if not camp or camp["status"] == "sent":
        return
    store.set_campaign(cid, status="sending")
    targets = recipients(camp["segment"])
    sent = failed = 0
    for i, chat in enumerate(targets):
        if deliver(camp, chat):
            sent += 1
            store.set_chat(chat, last_ad=int(time.time()))
        else:
            failed += 1
        if i % 20 == 19:
            tg.edit(admin_chat, screen, f"📣 Отправляю… {i + 1} из {len(targets)}")
        time.sleep(0.05)
    store.set_campaign(cid, status="sent", sent=sent, failed=failed, sent_at=int(time.time()))
    store.bump("ads_sent", sent)
    done(cid, sent, failed)
