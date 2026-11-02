"""Канал: бесплатные даты DGT с задержкой и закреплённый пост. В боте те же даты приходят сразу, поэтому канал ведёт людей в бота."""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import config
import dgt
import posts
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
_planned: Dict[int, int] = {}               # отложенный пост → когда публиковать; в памяти, чтобы не будить базу
_plan_loaded = {"ok": False}
PROOF_DAY = 6                               # постов «ещё одна запись» в сутки
DIGEST_MIN = 3                              # итоги недели — только если даты появлялись хотя бы столько раз
notify: Callable[[str], None] = lambda text: None  # подставляет checker: письмо админам


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
    """Раз в минуту: отложенные посты, итоги недели, затем самый старый готовый пост о датах."""
    now = now or time.time()
    if username():
        if due(now) or digest_due(now):
            return
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


# ---------- отложенные посты ----------

def static_url(name: str) -> str:
    return f"{config.PUBLIC_URL}/static/{name}?v={config.VERSION}"


def send_payload(target, payload: dict, kb: Optional[dict] = None, silent: bool = False) -> Optional[int]:
    """Пост из очереди: текст или медиа. Разметка — HTML (заготовки) или entities (пост, присланный админом)."""
    p = {"chat_id": target, "disable_notification": silent}
    if kb:
        p["reply_markup"] = kb
    body = payload.get("text") or ""
    if payload.get("html"):
        p["parse_mode"] = "HTML"
    file = payload.get("file") or ""
    if file.startswith("static:"):
        file = static_url(file[7:])
    if payload["type"] == "text":
        p.update(text=body, link_preview_options={"is_disabled": True})
        if not payload.get("html"):
            p["entities"] = payload.get("entities") or []
        data = tg.call("sendMessage", **p)
    else:
        method = {"photo": "sendPhoto", "video": "sendVideo", "animation": "sendAnimation"}[payload["type"]]
        p.update(caption=body, **{payload["type"]: file})
        if not payload.get("html"):
            p["caption_entities"] = payload.get("entities") or []
        data = tg.call(method, **p)
    if not data or not data.get("ok"):
        log.warning("пост не отправлен: %s", (data or {}).get("description"))
        return None
    return data["result"]["message_id"]


def queued_kb(row: dict) -> Optional[dict]:
    return ikb([[url(row["button"] or "⚡️ OkSita", row["url"], "primary")]]) if row.get("url") else None


def load_plan() -> None:
    _planned.clear()
    _planned.update({r["id"]: r["at"] for r in store.queued(("planned",), 200)})
    _plan_loaded["ok"] = True


def planned() -> Dict[int, int]:
    if not _plan_loaded["ok"]:
        load_plan()
    return _planned


def plan(qid: int, at: int) -> None:
    store.set_queued(qid, status="planned", at=int(at))
    planned()[qid] = int(at)


def unplan(qid: int) -> None:
    store.set_queued(qid, status="draft", at=0)
    planned().pop(qid, None)


def drop(qid: int) -> None:
    store.delete_queued(qid)
    planned().pop(qid, None)


def publish_queued(qid: int, now: Optional[float] = None) -> Optional[int]:
    """Публикует пост из очереди. Возвращает номер сообщения в канале или None."""
    planned().pop(qid, None)
    row = store.get_queued(qid)
    if not row or row["status"] == "sent":
        return None
    mid = send_payload(username(), json.loads(row["payload"]), queued_kb(row), silent=row.get("tag") == "proof")
    if mid:
        store.set_queued(qid, status="sent", message=mid, at=int(now or time.time()))
        _sent["at"] = now or time.time()
        store.bump("channel_queued")
    else:
        store.set_queued(qid, status="failed")
        notify(f"⚠️ Отложенный пост №{qid} не вышел в канале {username()}: проверь права бота (Админ → Канал).")
    return mid


def due(now: float) -> bool:
    """Выпускает один созревший пост. Между любыми постами — не меньше GAP. True — что-то опубликовали."""
    ready = sorted((at, qid) for qid, at in planned().items() if at <= now)
    if not ready or now - _sent["at"] < GAP:
        return False
    publish_queued(ready[0][1], now)
    return True


def next_slots(now: Optional[datetime] = None) -> List[Tuple[str, int]]:
    """Готовые варианты времени для админки: (подпись, unix)."""
    now = now or datetime.now(config.TZ)
    out = []
    for days, hour in ((0, 19), (1, 10), (1, 19), (2, 19), (3, 19), (7, 19)):
        at = (now + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
        if at > now + timedelta(minutes=5):
            label = ("Сегодня" if days == 0 else "Завтра" if days == 1 else f"{at:%d.%m}") + f" {at:%H:%M}"
            out.append((label, int(at.timestamp())))
    return out[:5]


def plan_drafts(now: Optional[datetime] = None) -> int:
    """Расставляет все черновики по одному в день в 19:00, после уже запланированных. Возвращает, сколько расставили."""
    now = now or datetime.now(config.TZ)
    taken = {datetime.fromtimestamp(at, config.TZ).date() for at in planned().values()}
    day = now.date() + timedelta(days=1)
    n = 0
    for row in store.queued(("draft",), 50):
        while day in taken:
            day += timedelta(days=1)
        at = datetime(day.year, day.month, day.day, 19, tzinfo=config.TZ)
        plan(row["id"], int(at.timestamp()))
        taken.add(day)
        n += 1
    return n


def add_templates() -> int:
    """Кладёт в черновики готовые посты, которых ещё не было. Сами посты не выходят, пока админ не выберет время."""
    have = store.queued_tags()
    values = {"free": store.setting("free_subs"), "top": store.setting("max_subs"), "trial": int(store.setting("trial_hours")) // 24,
              "ad": store.setting("post_ad"), "steps": store.setting("discount_tasks"), "pct": store.setting("discount_pct")}
    n = 0
    for t in posts.TEMPLATES:
        if t["tag"] not in have:
            store.add_queued({"type": "photo", "file": "static:" + t["image"], "text": posts.fill(t["text"], values), "html": True},
                             t["button"], bot_link(t["start"]), t["tag"])
            n += 1
    return n


def preview_line(row: dict) -> str:
    payload = json.loads(row["payload"])
    first = next((l for l in (payload.get("text") or "").splitlines() if l.strip()), "")
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        first = first.replace(tag, "")
    kind = {"photo": "🖼", "video": "🎬", "animation": "🎞"}.get(payload["type"], "📝")
    return f"{kind} {first[:40] or 'без текста'}"


# ---------- итоги недели ----------

def digest_text(events: List[dict], start: date, end: date) -> Optional[str]:
    if len(events) < DIGEST_MIN:
        return None
    by_office: Dict[Tuple[str, str], int] = {}
    hours = [0] * 24
    held = []
    for e in events:
        by_office[(e["centro"], e["area"])] = by_office.get((e["centro"], e["area"]), 0) + 1
        hours[datetime.fromtimestamp(e["opened_at"], config.TZ).hour] += 1
        if e.get("closed_at"):
            held.append(e["closed_at"] - e["opened_at"])
    best = hours.index(max(hours))
    avg = sum(held) // len(held) // 60 if held else None
    lasting = (f"{avg} min" if avg < 120 else f"{avg // 60} h") if avg is not None else "—"
    top = sorted(by_office.items(), key=lambda kv: -kv[1])[:5]
    lines = [f"{i + 1}. <b>{views.esc(views.city(cid))}</b> · {views.esc(views.area_label(area))} — {n}"
             for i, ((cid, area), n) in enumerate(top)]
    return (f"📊 <b>DGT · {start:%d.%m} – {end:%d.%m}</b>\n\n"
            f"🟢 <b>{len(events)}</b> × · 🏢 <b>{len(by_office)}</b>\n"
            f"⏱ ~<b>{lasting}</b> · 🕗 <b>{best:02d}:00–{(best + 1) % 24:02d}:00</b>\n\n"
            "🏆\n" + "\n".join(lines) + "\n\n"
            "<i>🇺🇦 Скільки разів за тиждень з'являлися вільні дати, у скількох офісах, скільки трималися і о котрій частіше.\n"
            "🇷🇺 Сколько раз за неделю появлялись свободные даты, в скольких офисах, сколько держались и в какое время чаще.\n"
            "🇪🇸 Cuántas veces hubo citas libres esta semana, en cuántas oficinas, cuánto duraron y a qué hora más.\n"
            "🇬🇧 How often free dates appeared this week, in how many offices, how long they lasted and when.</i>")


def digest_due(now: float) -> bool:
    """Итоги недели: воскресенье, 19:00 по Мадриду, один раз за неделю."""
    dt = datetime.fromtimestamp(now, config.TZ)
    week = f"{dt.isocalendar()[0]}-{dt.isocalendar()[1]}"
    if not store.setting("channel_digest") or dt.weekday() != 6 or dt.hour != 19 or store.setting("last_digest") == week:
        return False
    if now - _sent["at"] < GAP:
        return False
    store.set_setting("last_digest", week)
    text = digest_text(store.recent_events(int(now) - 7 * 86400), (dt - timedelta(days=6)).date(), dt.date())
    if not text:
        return False
    kb = ikb([[url("⚡️ OkSita", bot_link("digest"), "primary"), url("📊", bot_link("stats"))]])
    if publish(text, kb, silent=True):
        _sent["at"] = now
        store.bump("channel_digests")
        return True
    return False


# ---------- «ещё одна запись» ----------

def proof_text(cid: str, area: str, waited: int) -> str:
    days = max(1, round(waited / 86400))
    if waited < 86400:
        hours = max(1, round(waited / 3600))
        span = (f"{hours} год.", f"{hours} ч.", f"{hours} h", f"{hours} h")
    else:
        span = (f"{days} дн.", f"{days} дн.", f"{days} días" if days > 1 else "1 día", f"{days} days" if days > 1 else "1 day")
    return (f"🎉 <b>{views.esc(views.city(cid))}</b> · {views.esc(views.area_label(area))}\n\n"
            f"<i>🇺🇦 Ще один запис через OkSita — шукали {span[0]}\n"
            f"🇷🇺 Ещё одна запись через OkSita — искали {span[1]}\n"
            f"🇪🇸 Otra cita conseguida con OkSita en {span[2]}\n"
            f"🇬🇧 One more booking with OkSita in {span[3]}</i>")


def proof_allowed() -> bool:
    return bool(store.setting("channel_proof") and username() and
                store.metric(store.today_key(), "channel_proofs") < PROOF_DAY)


def share_booking(sub: dict, now: Optional[float] = None) -> bool:
    """Человек сам разрешил анонимный пост: только город, вид записи и сколько искали. True — пост в очереди."""
    now = now or time.time()
    if not proof_allowed():
        return False
    waited = int(now - (sub.get("created_at") or now))
    row = store.add_queued({"type": "text", "text": proof_text(sub["centro"], sub["area"], waited), "html": True},
                           "⚡️ OkSita", bot_link("proof"), "proof")
    plan(row["id"], int(now))
    store.bump("channel_proofs")
    return True
