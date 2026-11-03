"""Telegram Bot API и «чистый чат»: у каждого пользователя один экран, который редактируется, а не множится."""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Dict, Optional

import requests

import config
import store

log = logging.getLogger("tg")

_http = requests.Session()  # одно соединение на всех: без нового TLS-рукопожатия на каждый запрос
_http.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=16))
QUIET = ("not modified", "message to delete not found", "message can't be deleted",
         "message to edit not found", "message can't be edited", "bot was blocked")


def _clean(e: Exception) -> str:
    """Текст ошибки без токена: requests кладёт полный адрес запроса в сообщение."""
    return repr(e).replace(config.TOKEN, "***") if config.TOKEN else repr(e)


def call(method: str, _timeout: int = 40, **params) -> Optional[dict]:
    for attempt in range(3):
        try:
            data = _http.post(config.API + method, json=params, timeout=_timeout).json()
        except Exception as e:
            log.warning("telegram %s: %s", method, _clean(e))
            if attempt == 2:
                return None
            time.sleep(1 + attempt)
            continue
        if data.get("error_code") == 429:  # лимит Telegram: ждём сколько просят и повторяем
            time.sleep(min(int((data.get("parameters") or {}).get("retry_after", 1)) + 0.5, 30))
            continue
        if not data.get("ok") and not any(s in data.get("description", "") for s in QUIET):
            log.warning("telegram %s: %s", method, data.get("description"))
        return data
    return None


def _preview(banner: Optional[str]) -> dict:
    if banner:
        return {"url": banner, "prefer_large_media": True, "show_above_text": True}
    return {"is_disabled": True}


def send(chat: int, text: str, kb: Optional[dict] = None, silent: bool = False, banner: Optional[str] = None,
         effect: Optional[str] = None) -> Optional[int]:
    p = {"chat_id": chat, "text": text, "parse_mode": "HTML", "link_preview_options": _preview(banner),
         "disable_notification": silent}
    if kb is not None:
        p["reply_markup"] = kb
    if effect:
        p["message_effect_id"] = effect
    data = call("sendMessage", **p)
    if data and data.get("error_code") == 403:  # пользователь заблокировал бота
        store.pause_chat(chat)
    return data["result"]["message_id"] if data and data.get("ok") else None


def edit(chat: int, mid: int, text: str, kb: Optional[dict] = None, banner: Optional[str] = None) -> bool:
    p = {"chat_id": chat, "message_id": mid, "text": text, "parse_mode": "HTML", "link_preview_options": _preview(banner)}
    if kb is not None:
        p["reply_markup"] = kb
    data = call("editMessageText", **p) or {}
    return bool(data.get("ok")) or "not modified" in data.get("description", "")


def delete(chat: int, mid: Optional[int]) -> bool:
    if not mid:
        return False
    data = call("deleteMessage", chat_id=chat, message_id=mid) or {}
    if data.get("ok") or "not found" in data.get("description", ""):
        return True
    return edit(chat, mid, "·")  # старше 48 часов бот удалить не может — хотя бы сворачиваем


def send_document(chat: int, filename: str, content: bytes, caption: str = "") -> bool:
    try:
        data = _http.post(config.API + "sendDocument", timeout=70,
                          data={"chat_id": chat, "caption": caption, "parse_mode": "HTML"},
                          files={"document": (filename, content)}).json()
    except Exception as e:
        log.warning("telegram sendDocument: %s", _clean(e))
        return False
    return bool(data.get("ok"))


def send_photo_file(chat: int, filename: str, content: bytes, caption: str = "", kb: Optional[dict] = None) -> bool:
    data = {"chat_id": chat, "caption": caption, "parse_mode": "HTML"}
    if kb:
        data["reply_markup"] = json.dumps(kb)
    try:
        res = _http.post(config.API + "sendPhoto", timeout=70, data=data, files={"photo": (filename, content)}).json()
    except Exception as e:
        log.warning("telegram sendPhoto: %s", _clean(e))
        return False
    if not res.get("ok"):
        log.warning("telegram sendPhoto: %s", res.get("description"))
    return bool(res.get("ok"))


def upload_photo(chat: int, content: bytes) -> Optional[str]:
    """Загружает картинку в Telegram и возвращает file_id. Сообщение с ней в чате сразу удаляется."""
    try:
        data = _http.post(config.API + "sendPhoto", timeout=70, data={"chat_id": chat, "disable_notification": "true"},
                          files={"photo": ("photo.jpg", content, "image/jpeg")}).json()
    except Exception as e:
        log.warning("telegram sendPhoto: %s", _clean(e))
        return None
    if not data.get("ok"):
        log.warning("telegram sendPhoto: %s", data.get("description"))
        return None
    call("deleteMessage", chat_id=chat, message_id=data["result"]["message_id"])
    return data["result"]["photo"][-1]["file_id"]


def set_profile_photo(content: bytes) -> bool:
    try:
        data = _http.post(config.API + "setMyProfilePhoto", timeout=70,
                          data={"photo": json.dumps({"type": "static", "photo": "attach://file"})},
                          files={"file": ("avatar.jpg", content, "image/jpeg")}).json()
    except Exception as e:
        log.warning("telegram setMyProfilePhoto: %s", _clean(e))
        return False
    if not data.get("ok"):
        log.warning("telegram setMyProfilePhoto: %s", data.get("description"))
    return bool(data.get("ok"))


def answer(cb_id: str, text: str = "", alert: bool = False) -> None:
    p = {"callback_query_id": cb_id}
    if text:
        p.update(text=text[:200], show_alert=alert)
    call("answerCallbackQuery", **p)


def ikb(rows: list) -> dict:
    return {"inline_keyboard": [r for r in rows if r]}


def btn(text: str, data: str, style: Optional[str] = None) -> dict:
    """style: primary (синяя), success (зелёная), danger (красная)."""
    b = {"text": text, "callback_data": data}
    if style:
        b["style"] = style
    return b


def url(text: str, link: str, style: Optional[str] = None) -> dict:
    b = {"text": text, "url": link}
    if style:
        b["style"] = style
    return b


def webapp(text: str, link: str, style: Optional[str] = None) -> dict:
    b = {"text": text, "web_app": {"url": link}}
    if style:
        b["style"] = style
    return b


def copy(text: str, value: str) -> dict:
    return {"text": text, "copy_text": {"text": value[:256]}}


# Фоновая работа (проверка, радар) показывает результат, только если человек остался на том же экране.
_nav: Dict[int, int] = {}
_nav_lock = threading.Lock()


def navigate(chat: int) -> int:
    """Отмечает новое действие пользователя и возвращает его номер."""
    with _nav_lock:
        _nav[chat] = _nav.get(chat, 0) + 1
        return _nav[chat]


def same_screen(chat: int, token: Optional[int]) -> bool:
    with _nav_lock:
        return token is None or _nav.get(chat, 0) == token


def show(chat: int, text: str, kb: Optional[dict] = None, mid: Optional[int] = None,
         banner: Optional[str] = None) -> Optional[int]:
    """Показывает экран пользователю.

    mid — сообщение, на котором нажали кнопку: его и редактируем. Без mid (пользователь что-то написал)
    старый экран удаляется, а новый появляется внизу чата. На экране всегда одно сообщение бота.
    """
    screen = store.get_chat(chat).get("screen")
    if mid and edit(chat, mid, text, kb, banner):
        if screen != mid:
            delete(chat, screen)
            store.set_chat(chat, screen=mid)
            for s in store.subs_of(chat):  # уведомление стало экраном — больше не трогаем его как уведомление
                if s.get("alert_msg") == mid:
                    store.update_sub(s["id"], alert_msg=None)
        return mid
    new = send(chat, text, kb, banner=banner)
    if new:
        if screen and screen != new:
            delete(chat, screen)
        store.set_chat(chat, screen=new)
    return new


def remove_reply_keyboard(chat: int) -> None:
    """Убирает старую клавиатуру под полем ввода (была в первой версии бота)."""
    mid = send(chat, "·", {"remove_keyboard": True}, silent=True)
    if mid:
        call("deleteMessage", chat_id=chat, message_id=mid)


def set_menu_button(chat: int, app_url: Optional[str], text: str = config.BRAND) -> None:
    """Кнопка рядом с полем ввода: мини-приложение для Premium, обычное меню команд для остальных."""
    button = {"type": "web_app", "text": text, "web_app": {"url": app_url}} if app_url else {"type": "commands"}
    call("setChatMenuButton", chat_id=chat, menu_button=button)
