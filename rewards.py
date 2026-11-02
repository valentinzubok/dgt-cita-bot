"""Бонусы: приглашения друзей, задания и промокоды. Всё это начисляет Premium по часам."""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time
from typing import Callable, List, Optional, Tuple

import config
import premium
import store
import tg

log = logging.getLogger("rewards")

MEMBER = {"creator", "administrator", "member"}
BUILTIN = {  # задания, которые бот проверяет сам: ключ → (название на четырёх языках, часов Premium)
    "b:sub": ("Добавь первый офис", "Додай перший офіс", "Añade tu primera oficina", "Add your first office", 24),
    "b:ads": ("Включи предложения партнёров", "Увімкни пропозиції партнерів", "Activa las ofertas de socios", "Turn on partner offers", 24),
    "b:book": ("Запишись и нажми «✅ Я записался»", "Запишись і натисни «✅ Я записався»",
               "Pide cita y pulsa «✅ Ya tengo cita»", "Book and tap “✅ I booked it”", 24),
}
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
_tries: dict = {}
_clicked: set = set()  # кто открыл партнёрскую ссылку из задания
on_reward: Callable[[int], None] = lambda chat: None  # подставляет actions.py: после награды проверить, не открылась ли скидка


def steps(chat: int) -> Tuple[int, int]:
    """Сколько шагов бонусной лестницы пройдено: встроенные задания, задания админа и друзья (один шаг)."""
    keys = list(BUILTIN) + [f"t:{t['id']}" for t in store.tasks(active_only=True)]
    done = sum(1 for k in keys if store.task_is_done(k, chat))
    friend = store.task_is_done("ref:self", chat) or any(store.task_is_done(f"ref:{f['chat']}", chat) for f in store.friends_of(chat))
    return done + int(friend), len(keys) + 1


def unlock_discount(chat: int) -> bool:
    """Открывает скидку на месяц, когда выполнено нужное число заданий. True — открылась только что."""
    c = store.get_chat(chat)
    if not int(store.setting("discount_pct")) or c.get("discount_at") or c.get("paid_at") or store.task_is_done("discount", chat):
        return False
    if steps(chat)[0] < int(store.setting("discount_tasks")):
        return False
    store.set_chat(chat, discount_at=int(time.time()))
    store.bump("discounts")
    return True


def ref_link(chat: int) -> str:
    code = store.get_chat(chat).get("ref_code")
    if not code:
        code = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")
        store.set_chat(chat, ref_code=code)
    return f"https://t.me/{config.BOT_USERNAME}?start=r_{code}"


def promo_link(code: str) -> str:
    return f"https://t.me/{config.BOT_USERNAME}?start=promo_{code}"


def share_link(chat: int, text: str) -> str:
    from urllib.parse import quote
    return f"https://t.me/share/url?url={quote(ref_link(chat))}&text={quote(text)}"


def attach_referrer(friend: int, code: str) -> Optional[int]:
    """Новый пользователь пришёл по приглашению. Себя пригласить нельзя, вернувшийся новым другом не считается."""
    inviter = store.chat_by_ref_code(code)
    if not inviter or inviter == friend or store.was_deleted(friend):
        return None
    store.set_chat(friend, ref_by=inviter)
    return inviter


def is_member(target: str, user: int) -> Optional[bool]:
    """Подписан ли человек на канал или группу. None — бот не может это проверить (нет прав)."""
    data = tg.call("getChatMember", chat_id=target, user_id=user)
    if not data or not data.get("ok"):
        return None
    m = data["result"]
    return m.get("status") in MEMBER or (m.get("status") == "restricted" and bool(m.get("is_member")))


def required_task() -> Optional[dict]:
    """Канал, на который нужно подписаться ради награды за друзей (выбирается в админке)."""
    tid = int(store.setting("ref_task") or 0)
    task = store.get_task(tid) if tid else None
    return task if task and task["active"] and task["kind"] == "channel" else None


def _member_of_required(user: int) -> bool:
    task = required_task()
    return True if not task else is_member(task["target"], user) is True


def _rewards_last_month(inviter: int) -> int:
    month_ago = time.time() - 30 * 86400
    return sum(1 for f in store.friends_of(inviter)
               if (f.get("ref_done_at") or 0) > month_ago and store.task_is_done(f"ref:{f['chat']}", inviter))


def pending_friends(inviter: int) -> List[dict]:
    """Друзья выполнили условия, но награду пригласивший ещё не забрал."""
    return [f for f in store.friends_of(inviter)
            if f.get("ref_done_at") and not store.task_is_done(f"ref:{f['chat']}", inviter)]


def try_activate_friend(friend: int) -> Optional[int]:
    """Друг считается приглашённым, когда выбрал язык, добавил офис и подписался на канал.
    Он сразу получает бонус. Возвращает id пригласившего, если условия только что выполнены."""
    c = store.get_chat(friend)
    if not c.get("ref_by") or c.get("ref_done_at") or not c.get("lang") or not store.subs_of(friend):
        return None
    if not _member_of_required(friend):
        return None
    store.set_chat(friend, ref_done_at=int(time.time()))
    if store.claim_task("ref:self", friend):
        premium.grant(friend, int(store.setting("ref_hours")), "ref:friend")
        on_reward(friend)
    store.bump("ref_activated")
    return c["ref_by"]


def collect(inviter: int) -> Tuple[str, int]:
    """Пригласивший забирает награду. Статус: ok | channel | cap | none. Второе значение — сколько друзей засчитано."""
    pending = pending_friends(inviter)
    if not pending:
        return "none", 0
    if not _member_of_required(inviter):
        return "channel", len(pending)
    cap, got = int(store.setting("ref_cap")), _rewards_last_month(inviter)
    paid = 0
    for f in pending:
        if got + paid >= cap:
            break
        if store.claim_task(f"ref:{f['chat']}", inviter):
            premium.grant(inviter, int(store.setting("ref_hours")), "ref:invite")
            paid += 1
    if paid:
        on_reward(inviter)
    return ("ok", paid) if paid else ("cap", 0)


def complete_builtin(chat: int, key: str) -> Optional[int]:
    """Встроенное задание выполнено. Возвращает часы награды, если начислено впервые."""
    hours = BUILTIN[key][-1]
    if store.claim_task(key, chat):
        premium.grant(chat, hours, key)
        on_reward(chat)
        return hours
    return None


def check_task(chat: int, tid: int) -> Tuple[str, int]:
    """Проверка задания: done | ok | no | bot | gone. Второе значение — часы награды."""
    task = store.get_task(tid)
    if not task or not task["active"]:
        return "gone", 0
    key = f"t:{tid}"
    if store.task_is_done(key, chat):
        return "done", 0
    if task["kind"] == "channel":
        member = is_member(task["target"], chat)
        if member is None:
            return "bot", 0
        if not member:
            return "no", 0
    elif (tid, chat) not in _clicked:
        return "no", 0
    if store.claim_task(key, chat):
        premium.grant(chat, task["hours"], key)
        store.bump("tasks_done")
        on_reward(chat)
        return "ok", task["hours"]
    return "done", 0


def apply_promo(chat: int, code: str) -> Tuple[str, int]:
    """Активирует промокод. Не больше 6 попыток за 10 минут — перебрать коды нельзя."""
    code = code.strip()
    now = time.time()
    tries = [t for t in _tries.get(chat, []) if t > now - 600]
    if len(tries) >= 6:
        return "wait", 0
    _tries[chat] = tries + [now]
    if not CODE_RE.match(code):
        return "none", 0
    status = store.use_promo(code, chat)
    if status != "ok":
        return status, 0
    hours = store.get_promo(code)["hours"]
    premium.grant(chat, hours, f"promo:{code}")
    store.bump("promo_used")
    return "ok", hours


def task_url(task: dict, chat: int) -> str:
    """Ссылка задания. Переход по партнёрской ссылке идёт через бота — так видно, что человек её открыл."""
    if task["kind"] == "link" and config.PUBLIC_URL:
        return f"{config.PUBLIC_URL}/t/{task['id']}/{chat}/{sign('t', task['id'], chat)}"
    return task.get("link") or task["target"]


def sign(kind: str, item: int, chat: int) -> str:
    return hmac.new(config.LINK_KEY, f"{kind}:{item}:{chat}".encode(), hashlib.sha256).hexdigest()[:16]


def task_click(tid: int, chat: int, sig: str) -> Optional[str]:
    task = store.get_task(tid)
    if not task or not hmac.compare_digest(sign("t", tid, chat), sig):
        return None
    _clicked.add((tid, chat))
    return task["target"]


def new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))
