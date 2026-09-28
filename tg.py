"""Telegram Bot API и «чистый чат»: у каждого пользователя один экран, который редактируется, а не множится."""
from __future__ import annotations

import logging
from typing import Optional

import requests

import config
import store

log = logging.getLogger("tg")


def call(method: str, **params) -> Optional[dict]:
    try:
        data = requests.post(config.API + method, json=params, timeout=70).json()
    except Exception as e:
        log.warning("telegram %s: %r", method, e)
        return None
    if not data.get("ok") and not any(s in data.get("description", "") for s in
                                      ("not modified", "message to delete not found", "message can't be deleted",
                                       "message to edit not found", "message can't be edited")):
        log.warning("telegram %s: %s", method, data.get("description"))
    return data


def send(chat: int, text: str, kb: Optional[dict] = None, silent: bool = False) -> Optional[int]:
    p = {"chat_id": chat, "text": text, "parse_mode": "HTML",
         "link_preview_options": {"is_disabled": True}, "disable_notification": silent}
    if kb is not None:
        p["reply_markup"] = kb
    data = call("sendMessage", **p)
    if data and data.get("error_code") == 403:  # пользователь заблокировал бота
        store.pause_chat(chat)
    return data["result"]["message_id"] if data and data.get("ok") else None


def edit(chat: int, mid: int, text: str, kb: Optional[dict] = None) -> bool:
    p = {"chat_id": chat, "message_id": mid, "text": text, "parse_mode": "HTML",
         "link_preview_options": {"is_disabled": True}}
    if kb is not None:
        p["reply_markup"] = kb
    data = call("editMessageText", **p) or {}
    return bool(data.get("ok")) or "not modified" in data.get("description", "")


def delete(chat: int, mid: Optional[int]) -> bool:
    if not mid:
        return False
    data = call("deleteMessage", chat_id=chat, message_id=mid) or {}
    if data.get("ok"):
        return True
    # Старше 48 часов бот удалить не может — хотя бы сворачиваем
    return edit(chat, mid, "·")


def send_document(chat: int, filename: str, content: bytes, caption: str = "") -> bool:
    try:
        data = requests.post(config.API + "sendDocument", timeout=70,
                             data={"chat_id": chat, "caption": caption, "parse_mode": "HTML"},
                             files={"document": (filename, content)}).json()
    except Exception as e:
        log.warning("telegram sendDocument: %r", e)
        return False
    return bool(data.get("ok"))


def answer(cb_id: str, text: str = "", alert: bool = False) -> None:
    p = {"callback_query_id": cb_id}
    if text:
        p.update(text=text, show_alert=alert)
    call("answerCallbackQuery", **p)


def ikb(rows: list) -> dict:
    return {"inline_keyboard": [r for r in rows if r]}


def btn(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}


def url(text: str, link: str) -> dict:
    return {"text": text, "url": link}


def show(chat: int, text: str, kb: Optional[dict] = None, mid: Optional[int] = None) -> Optional[int]:
    """Показывает экран пользователю.

    mid — сообщение, на котором нажали кнопку: его и редактируем. Без mid (пользователь что-то написал)
    старый экран удаляется, а новый появляется внизу чата. На экране всегда одно сообщение бота.
    """
    screen = store.get_chat(chat).get("screen")
    if mid and edit(chat, mid, text, kb):
        if screen != mid:
            delete(chat, screen)
            store.set_chat(chat, screen=mid)
            for s in store.subs_of(chat):  # уведомление превратилось в экран — больше не трогаем его как уведомление
                if s.get("alert_msg") == mid:
                    store.update_sub(s["id"], alert_msg=None)
        return mid
    new = send(chat, text, kb)
    if new:
        if screen and screen != new:
            delete(chat, screen)
        store.set_chat(chat, screen=new)
    return new


def remove_reply_keyboard(chat: int) -> None:
    """Убирает старую клавиатуру под полем ввода (была в прошлой версии бота)."""
    mid = send(chat, "·", {"remove_keyboard": True}, silent=True)
    if mid:
        call("deleteMessage", chat_id=chat, message_id=mid)
