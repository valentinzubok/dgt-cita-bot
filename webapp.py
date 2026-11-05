"""Веб-сервер бота: webhook Telegram, мини-приложение и его API, переходы по рекламным ссылкам."""
from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import logging
import re
import threading
import time
from collections import Counter, deque
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, parse_qsl, urlsplit

import actions
import ads
import agenda
import board
import channel
import checker
import config
import dgt
import gate
import group
import hourstar
import landing
import premium
import radar
import rewards
import schools
import signals
import stats
import store
import tg
import views
from centros import COORDS

log = logging.getLogger("web")

MAX_WEBHOOK_BODY = 1024 * 1024
MAX_API_BODY = 8 * 1024
MAX_PHOTO_BODY = 3 * 1024 * 1024  # фото объявления приходит в base64, уже сжатое приложением до 1280 px
INIT_MAX_AGE = 24 * 3600
CSP = ("default-src 'none'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors https://web.telegram.org https://*.telegram.org https://t.me")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml"}
FILES = {"/app": "webapp/index.html", "/app/app.js": "webapp/app.js", "/app/i18n.js": "webapp/i18n.js", "/app/style.css": "webapp/style.css",
         "/app/icon.png": "assets/avatar.png", "/app/mark.svg": "assets/mark.svg", "/static/banner.jpg": "assets/banner.jpg",
         "/static/banner_premium.jpg": "assets/banner_premium.jpg", "/static/banner_bonus.jpg": "assets/banner_bonus.jpg",
         "/static/banner_radar.jpg": "assets/banner_radar.jpg", "/static/banner_admin.jpg": "assets/banner_admin.jpg",
         "/static/banner_docs.jpg": "assets/banner_docs.jpg", "/static/banner_board.jpg": "assets/banner_board.jpg",
         "/static/banner_trial.jpg": "assets/banner_trial.jpg", "/static/banner_gate.jpg": "assets/banner_gate.jpg",
         "/static/cover.png": "assets/cover.png"}
FILES.update({f"/static/{f.name}": f"assets/{f.name}" for f in sorted((config.ROOT / "assets").glob("post_*.jpg"))})  # картинки постов канала
STATES = {"🟢": "free", "🟡": "later", "🔴": "full", "⏸": "paused", "✅": "booked", "⏳": "pending",
          "⚠️": "error", "🔐": "locked", "⚪️": "none", "❔": "error"}
LOADS = {"bajaOcupacion": "many", "mediaOcupacion": "mid", "altaOcupacion": "few"}
_cache: Dict[str, Tuple[bytes, bytes, str]] = {}
_photos: Dict[int, str] = {}
landing.minutes = checker.check_minutes  # последнее фото объявления, загруженное из приложения: чат → file_id
_hits: Dict[int, deque] = {}
_hits_lock = threading.Lock()
on_update: Callable[[dict], None] = lambda update: None  # подставляет bot.py
on_lang: Callable[[int], None] = lambda chat: None  # подставляет bot.py: перерисовать экран в чате на новом языке


def validate_init_data(raw: str, now: Optional[float] = None) -> Optional[dict]:
    """Проверяет подпись Telegram у данных мини-приложения. Возвращает пользователя или None."""
    if not raw or len(raw) > 4096 or not config.TOKEN:
        return None
    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    received = pairs.pop("hash", "")
    if not received:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", config.TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    now = now or time.time()
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        user = json.loads(pairs.get("user", "null"))
    except ValueError:
        return None
    if not user or not isinstance(user.get("id"), int) or now - auth_date > INIT_MAX_AGE or auth_date - now > 300:
        return None
    return user


def rate_ok(chat: int, limit: int = 40, window: int = 10) -> bool:
    now = time.time()
    with _hits_lock:
        q = _hits.setdefault(chat, deque())
        while q and q[0] < now - window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def area_icon(label: str) -> str:
    cats = views.cats_of(label)
    return "mix" if cats == {"lic", "veh"} else next(iter(cats)) if cats else "doc"


def sub_payload(sub: dict, lang: str) -> dict:
    days = views.all_days(sub.get("last"), sub.get("max_days"))
    emoji, text = views.summary(sub, lang)
    last = sub.get("last") or []
    info = next((r for r in last if r.get("address")), {})
    area = views.sub_area(sub)
    data = {
        "id": sub["id"], "city": views.city(sub["centro"]), "centro": sub["centro"], "area": sub["area"],
        "type": area, "hint": views.area_hint(lang, area), "icon": area_icon(area),
        "state": STATES.get(emoji, "error"), "statusText": views.cap(text), "paused": bool(sub["paused"]), "filter": sub.get("max_days") or 0,
        "booked": sub.get("booked_date"), "bookedTime": sub.get("booked_time"),
        "days": [[iso, LOADS.get(load, "")] for iso, load in views.all_days(last)],
        "visible": [iso for iso, _ in days], "nearest": days[0][0] if days else None,
        "hoursBy": {r["days"][0][0]: r.get("hours") or [] for r in last if r.get("status") == dgt.AVAILABLE and r.get("days")},
        "address": info.get("address") or "", "schedule": info.get("schedule") or "",
        "checked": views.fmt_ts(sub["checked_at"], lang) if sub.get("checked_at") else "",
    }
    if sub.get("booked_date"):
        data.update(bookedLabel=views.booked_label(lang, sub), checklist=views.checklist(lang, sub),
                    past=date.fromisoformat(sub["booked_date"]) < views.today())
    if data["state"] == "locked":
        data["note"] = views.canje_note(lang)
    return data


def bonus_payload(chat: int, lang: str) -> dict:
    friends = store.friends_of(chat)
    tasks = [{"key": key, "title": views.tx(lang, *names), "reward": views.hours_text(lang, hours), "done": store.task_is_done(key, chat)}
             for key, (*names, hours) in rewards.BUILTIN.items()]
    tasks += [{"key": f"t:{t['id']}", "id": t["id"], "title": views.task_title(lang, t), "reward": views.hours_text(lang, t["hours"]),
               "done": store.task_is_done(f"t:{t['id']}", chat), "url": rewards.task_url(t, chat)} for t in store.tasks(active_only=True)]
    return {"refLink": rewards.ref_link(chat), "shareText": views.invite_text(lang), "deal": views.ref_deal(lang), "friends": len(friends),
            "ladder": views.discount_line(chat),
            "friendsCounted": sum(1 for f in friends if f.get("ref_done_at")), "pending": len(rewards.pending_friends(chat)), "tasks": tasks}


def plans_payload(chat: int) -> list:
    until = premium.discount_until(chat)
    plans = [{"id": p, "days": premium.PLANS[p]["days"], "stars": premium.plan_price(p), "recurring": premium.PLANS[p]["recurring"]}
             for p in ("p30d", "p30", "p7", "p90") if p != "p30d" or until]
    if until:
        plans[0].update(discount=int(store.setting("discount_pct")), until=until, full=premium.plan_price("p30"))
    return plans


def me_payload(chat: int) -> dict:
    c = store.get_chat(chat)
    lang = c.get("lang") or "ru"
    paid = premium.is_premium(chat)
    data = {"lang": lang, "langSet": bool(c.get("lang")), "name": c.get("name") or "", "premium": paid, "premiumUntil": c.get("premium_until") or 0,
            "autoRenew": bool(c.get("sub_active")), "limit": premium.limit_subs(chat), "bot": config.BOT_USERNAME, "bookUrl": dgt.START_URL,
            "trial": premium.can_trial(chat), "trialDays": views.trial_days(lang), "inTrial": premium.in_trial(chat),
            "guarantee": premium.guarantee_state(chat), "channel": channel.link(), "channelName": channel.username(),
            "gate": not gate.allowed(chat), "group": group.link(), "hourstar": hourstar.link("app"),
            "outage": checker.site_down(), "quiet": bool(c.get("quiet")), "adsOk": bool(c.get("ads_ok")), "plans": plans_payload(chat),
            "free": {"subs": store.setting("free_subs"), "interval": checker.check_minutes(False), "signals": signals.FREE_SUBS},
            "top": {"subs": store.setting("max_subs"), "interval": checker.check_minutes(True), "signals": signals.TOP_SUBS}}
    if paid:
        data.update(subs=[sub_payload(s, lang) for s in store.subs_of(chat)], nextCheck=checker.next_check_for(chat),
                    used=premium.active_subs_count(chat), alerts=c.get("alerts") or 0, checksPaused=bool(store.setting("checks_paused")),
                    **bonus_payload(chat, lang))
    return data


def docs_payload(chat: int, lang: str) -> dict:
    names = sorted(signals.PROVINCES.items(), key=lambda kv: views.fold(kv[1]))
    mine = [{"province": p, "doc": d, "name": signals.PROVINCES[p], "title": views.doc_name(lang, d), "hour": signals.best_hour(p, d)}
            for p, d in signals.subs_of(chat)]
    return {"mine": mine, "limit": signals.limit(chat), "site": signals.ICP_URL, "provinces": [{"id": k, "name": v} for k, v in names],
            "docs": [{"id": d, "title": views.doc_name(lang, d)} for d in signals.DOCS],
            "windows": {"options": signals.WINDOWS, "mine": signals.windows_of(chat), "limit": signals.window_limit(chat)}}


def radar_payload(chat: int, lang: str) -> dict:
    job = radar.scans.get(chat)
    if not job:
        return {"state": "idle"}
    job["seen"] = time.time()
    if job["failed"] or (job["over"] and job["found"] is None):
        return {"state": "failed", "text": views.radar_failed(lang)}
    if not job["over"]:
        return {"state": "running", "done": job["done"], "total": job["total"], "current": job["current"]}
    tracked = {(s["centro"], s["area"]) for s in store.subs_of(chat)}
    items = []
    for centro, code, results, dist in job["found"]:
        days = views.all_days(results) if results else []
        state = "free" if days else "none" if code is None else "error" if results is None else \
            "locked" if any(r.get("status") == dgt.NEEDS_DATA for r in results) else "full"
        items.append({"centro": centro, "city": views.city(centro), "km": dist, "code": code, "state": state,
                      "nearest": days[0][0] if days else None, "days": len(days), "tracked": (centro, code) in tracked})
    return {"state": "done", "km": job["km"], "cat": job["cat"], "items": items}


def stats_payload(lang: str) -> dict:
    return {"items": [{"city": views.city(g["centro"]), "type": views.area_label(g["area"]), "opens": g["opens"], "best": g["best"],
                       "held": views.fmt_dur(g["avg"], lang) if g["avg"] else ""} for g in stats.offices()[:20]]}


def board_payload(chat: int) -> dict:
    posts = [{"kind": p["kind"], "text": p["text"], "link": channel.link(p["message"]), "at": p["decided_at"]} for p in store.posts("published", 20)]
    mine = [{"id": p["id"], "kind": p["kind"], "text": p["text"], "status": p["status"], "photo": bool(p.get("photo")),
             "link": channel.link(p["message"]) if p.get("message") else None} for p in store.posts_of(chat, 10) if p["status"] != "cancelled"]
    return {"posts": posts, "mine": mine, "job": store.setting("post_job"), "ad": store.setting("post_ad"), "freeJob": not store.free_job_used(chat),
            "min": board.MIN_LEN, "max": board.MAX_LEN, "busy": board.open_count(chat) >= board.MAX_OPEN, "channel": channel.username(),
            "group": group.link()}


def photo_upload(chat: int, raw: object) -> Tuple[int, dict]:
    """Фото для объявления: base64 JPEG или PNG. Загружаем в Telegram и запоминаем, в базе храним только file_id."""
    try:
        content = base64.b64decode(str(raw or "").split(",")[-1], validate=True)
    except ValueError:
        return 400, {"error": "photo"}
    if not content.startswith((b"\xff\xd8\xff", b"\x89PNG")) or len(content) > 2 * 1024 * 1024:
        return 400, {"error": "photo"}
    if not rate_ok(-chat - 1, 6, 600):
        return 429, {"error": "wait"}
    file_id = tg.upload_photo(chat, content)
    if not file_id:
        return 502, {"error": "telegram"}
    _photos[chat] = file_id
    return 200, {"status": "ok"}


def board_api(method: str, parts: list, body: dict, chat: int, lang: str) -> Optional[Tuple[int, dict]]:
    """Объявления из приложения: черновик, фото, оплата звёздами или бесплатная отправка на проверку.
    Доступно без Premium: разместить вакансию может кто угодно."""
    if parts == ["board"] and method == "GET":
        return 200, board_payload(chat)
    if parts == ["board", "photo"] and method == "POST":
        return photo_upload(chat, body.get("data"))
    if parts == ["board", "draft"] and method == "POST":
        kind, text = body.get("kind"), str(body.get("text") or "").strip()
        if kind not in board.KINDS:
            return 400, {"error": "kind"}
        if board.open_count(chat) >= board.MAX_OPEN:
            return 409, {"status": "many", "text": views.post_error(lang, "many")}
        status = board.check_text(text)
        if status != "ok":
            return 400, {"status": status, "text": views.post_error(lang, status)}
        post = board.create(chat, kind, text, _photos.pop(chat, None) if body.get("photo") else None)
        link = board.invoice(post, lang) if post["stars"] else None
        if post["stars"] and not link:
            return 502, {"error": "telegram"}
        return 200, {"id": post["id"], "stars": post["stars"], "invoice": link}
    if len(parts) == 3 and parts[0] == "board" and parts[1].isdigit() and method == "POST":
        post = store.get_post(int(parts[1]))
        if not post or post["chat"] != chat or post["status"] != "draft":
            return 404, {"error": "not found"}
        if parts[2] == "send":
            if post["stars"]:
                return 409, {"status": "pay"}  # платное уходит на проверку только после оплаты
            board.to_moderation(post)
            return 200, {"status": "review", "text": views.post_sent(lang)}
        if parts[2] == "cancel":
            store.set_post(post["id"], status="cancelled")
            return 200, {"status": "cancelled"}
        return 404, {"error": "not found"}
    return None


PAGES = {"help": views.help_view, "terms": views.terms_view, "privacy": views.privacy_view, "ukraine": views.ukraine_view,
         "tie": views.tie_guide}


def account_api(method: str, parts: list, body: dict, chat: int, c: dict) -> Optional[Tuple[int, dict]]:
    """Запросы, доступные без Premium: язык, настройки, оплата, страницы с текстами."""
    lang = c.get("lang") or "ru"
    if parts == ["me"] and method == "GET":
        return 200, me_payload(chat)
    if parts == ["lang"] and method == "POST":
        code = body.get("lang")
        if code not in config.LANGS:
            return 400, {"error": "lang"}
        store.set_chat(chat, lang=code)
        actions.jobs.submit(on_lang, chat)  # экран в чате переводим сразу, а не при следующем нажатии
        return 200, {"status": "ok"}
    if parts == ["settings"] and method == "POST":
        if isinstance(body.get("quiet"), bool):
            store.set_chat(chat, quiet=int(body["quiet"]))
        if isinstance(body.get("ads"), bool):
            actions.set_ads(chat, body["ads"])
        return 200, {"status": "ok"}
    if len(parts) == 2 and parts[0] == "page" and parts[1] in PAGES and method == "GET":
        return 200, {"text": PAGES[parts[1]](chat)[0]}
    if parts == ["invoice"] and method == "POST":
        plan = body.get("plan")
        if plan not in premium.PLANS or checker.site_down():
            return 400, {"error": "unavailable"}
        link = premium.invoice_link(plan, lang)
        return (200, {"link": link}) if link else (502, {"error": "telegram"})
    if parts == ["trial"] and method == "POST":
        status = premium.start_trial(chat, checker.site_down())
        if status == "ok":
            checker.event(f"🎁 Пробный период: {c.get('name') or chat}", "user")
            return 200, {"status": status}
        return 409, {"status": status, "text": views.trial_note(lang, status)}
    if parts == ["gate"] and method == "POST":
        return 200, {"ok": gate.allowed(chat, fresh=True)}
    if parts == ["promo"] and method == "POST":
        status, hours = rewards.apply_promo(chat, str(body.get("code") or "")[:40])
        return 200, {"status": status, "text": views.promo_result(lang, status, hours)}
    return None


def office_api(method: str, parts: list, query: dict, body: dict, chat: int, lang: str) -> Optional[Tuple[int, dict]]:
    """Офисы и подписки."""
    if parts == ["offices"] and method == "GET":
        items = sorted(((views.city(k), k) for k in dgt.CENTROS), key=lambda x: views.fold(x[0]))
        cats = [{"id": cat, "label": views.tx(lang, *names)} for cat, (_, *names) in views.CATS.items() if cat != "cnj"]
        return 200, {"offices": [{"id": k, "city": name} for name, k in items], "cats": cats}
    if parts == ["areas"] and method == "GET":
        cid = (query.get("office") or [""])[0]
        if cid not in dgt.CENTROS:
            return 400, {"error": "office"}
        options = actions.office_options(cid, allow_fetch=not checker.site_down())
        if not options:
            return 503, {"error": "site"}
        return 200, {"areas": [{"code": code, "label": views.area_label(code, label), "icon": area_icon(label),
                                "hint": views.area_hint(lang, label)} for code, label in options]}
    if parts == ["subs"] and method == "POST":
        status, sub = actions.add_subscription(chat, str(body.get("centro") or ""), str(body.get("area") or ""))
        if status == "ok" and not checker.site_down():
            actions.check_now(sub)
        return (200 if status in ("ok", "exists") else 409), {"status": status}
    if len(parts) < 2 or parts[0] != "subs" or not parts[1].isdigit():
        return None
    sub = store.get_sub(int(parts[1]))
    if not sub or sub["chat"] != chat:
        return 404, {"error": "not found"}
    action = parts[2] if len(parts) > 2 else ""
    if method == "POST" and action == "pause":
        status = actions.set_paused(sub, bool(body.get("paused")))
        return (200 if status == "ok" else 409), {"status": status}
    if method == "POST" and action == "filter":
        days = body.get("days")
        return (200, {"status": "ok"}) if isinstance(days, int) and actions.set_filter(sub, days) else (400, {"error": "days"})
    if method == "POST" and action == "delete":
        actions.remove_sub(sub)
        return 200, {"status": "ok"}
    if method == "POST" and action == "check":
        if checker.site_down():
            return 503, {"error": "site"}
        if not rate_ok(-chat, 1, 60):
            return 429, {"error": "wait"}
        actions.check_now(sub)
        return 200, {"status": "ok"}
    if method == "POST" and action == "book":
        iso, hhmm = body.get("date"), body.get("time")
        if not actions.valid_iso(iso) or not (hhmm is None or re.fullmatch(r"\d{2}:\d{2}", str(hhmm))):
            return 400, {"error": "date"}
        actions.book(sub, iso, hhmm)
        return 200, {"status": "ok"}
    if method == "POST" and action == "unbook":
        tg.delete(chat, sub.get("alert_msg"))
        return 200, {"status": "ok", "resumed": actions.unbook(sub)}
    if method == "GET" and action == "history":
        evs = store.events(sub["centro"], sub["area"], 10)
        hours = Counter(datetime.fromtimestamp(e["opened_at"], config.TZ).hour for e in evs).most_common(1) if len(evs) >= 3 else []
        closed = [e["closed_at"] - e["opened_at"] for e in evs if e["closed_at"]]
        return 200, {"events": [{"at": views.fmt_ts(e["opened_at"], lang), "lasted": views.fmt_dur(e["closed_at"] - e["opened_at"], lang) if e["closed_at"] else "",
                                 "days": views.days_word(lang, e["days"] or 0)} for e in evs],
                     "bestHour": hours[0][0] if hours else None, "average": views.fmt_dur(sum(closed) // len(closed), lang) if closed else "",
                     "hours": (stats.office(sub["centro"], sub["area"]) or {}).get("hours")}
    return None


def extras_api(method: str, parts: list, body: dict, chat: int, lang: str) -> Optional[Tuple[int, dict]]:
    """Радар, документы, бонусы и автопродление."""
    if parts == ["radar"] and method == "GET":
        return 200, radar_payload(chat, lang)
    if parts == ["radar"] and method == "POST":
        cid, cat, km = str(body.get("centro") or ""), body.get("cat"), body.get("km")
        if cid not in COORDS or cid not in dgt.CENTROS or cat not in views.CATS or km not in radar.RADII:
            return 400, {"error": "radar"}
        hint = radar.start_app(chat, cid, cat, km)
        return (409, {"text": hint}) if hint else (200, {"status": "ok"})
    if parts == ["docs"] and method == "GET":
        return 200, docs_payload(chat, lang)
    if parts == ["docs", "windows"] and method == "POST":
        hour = body.get("hour")
        status = signals.toggle_window(chat, hour) if isinstance(hour, int) else "bad"
        if status == "limit":
            return 409, {"text": views.window_limit_note(lang)}
        return (200, {"mine": signals.windows_of(chat)}) if status == "ok" else (400, {"error": "hour"})
    if parts == ["stats"] and method == "GET":
        return 200, stats_payload(lang)
    if parts == ["guarantee"] and method == "POST":
        ok = premium.use_guarantee(chat)
        checker.event(f"🛡 Гарантия: {store.get_chat(chat).get('name') or chat}, {'возврат' if ok else 'не вышло'}", "money")
        return (200 if ok else 409), {"text": views.guarantee_result(lang, ok)}
    if len(parts) == 2 and parts[0] == "docs" and method == "POST":
        province, doc = str(body.get("province") or ""), str(body.get("doc") or "")
        if not signals.valid(province, doc):
            return 400, {"error": "doc"}
        if parts[1] == "sub":
            status = signals.subscribe(chat, province, doc)
            return (409, {"text": views.signal_limit(lang)}) if status == "limit" else (200, {"text": views.signal_added(lang)})
        if parts[1] == "unsub":
            store.del_signal_sub(chat, province, doc)
            return 200, {"status": "ok"}
        if parts[1] == "report":
            status, sent = actions.report_signal(chat, province, doc)
            return 200, {"status": status, "text": views.signal_result(lang, status, sent)}
    if parts == ["bonus", "collect"] and method == "POST":
        status, count = rewards.collect(chat)
        return 200, {"status": status, "text": views.collect_text(lang, status, count)}
    if len(parts) == 3 and parts[0] == "tasks" and parts[1].isdigit() and parts[2] == "check" and method == "POST":
        status, hours = rewards.check_task(chat, int(parts[1]))
        if status == "ok":
            actions.after_task(chat)
        return 200, {"status": status, "text": views.reward_text(lang, hours) if status == "ok" else views.task_result(lang, status)}
    if parts == ["premium", "cancel"] and method == "POST":
        ok = premium.cancel(chat)
        if ok:
            checker.event(f"🚫 Автопродление отключено ({store.get_chat(chat).get('name') or chat})", "money")
        return (200 if ok else 502), {"status": "ok" if ok else "failed"}
    return None


def api(method: str, path: str, query: dict, body: dict, chat: int) -> Tuple[int, dict]:
    c = store.get_chat(chat)
    if c.get("role") in ("banned", "pending"):
        return 403, {"error": "forbidden"}
    parts = [p for p in path.split("/") if p][1:]  # без «api»
    if parts not in (["me"], ["lang"], ["gate"]) and not gate.allowed(chat):
        return 403, {"error": "gate"}
    lang = c.get("lang") or "ru"
    reply = account_api(method, parts, body, chat, c) or board_api(method, parts, body, chat, lang)
    if reply:
        return reply
    if not premium.is_premium(chat):
        return 402, {"error": "premium"}
    return office_api(method, parts, query, body, chat, lang) or extras_api(method, parts, body, chat, lang) or (404, {"error": "not found"})


class Handler(BaseHTTPRequestHandler):
    server_version = "OkSita"
    sys_version = ""
    timeout = 20  # медленные клиенты не держат поток вечно

    def _send(self, code: int, body: bytes = b"", ctype: str = "application/json", headers: Optional[dict] = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Strict-Transport-Security", "max-age=31536000")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, data: dict) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode(), headers={"Cache-Control": "no-store"})

    def _file(self, path: str) -> None:
        if path not in _cache:
            target = config.ROOT / FILES[path]
            raw = target.read_bytes().replace(b"__V__", config.VERSION.encode())  # версия в адресах: обновления приходят сразу
            _cache[path] = (raw, gzip.compress(raw, 6), TYPES[target.suffix])
        raw, packed, ctype = _cache[path]
        fresh = path == "/app" or config.VERSION == "dev"
        headers = {"Cache-Control": "no-cache" if fresh else "public, max-age=86400"}
        if path == "/app":
            headers["Content-Security-Policy"] = CSP
        if "gzip" in self.headers.get("Accept-Encoding", "") and not ctype.startswith("image"):
            headers["Content-Encoding"] = "gzip"
            raw = packed
        self._send(200, raw, ctype, headers)

    def _page(self, raw: bytes, ctype: str, age: int = 600) -> None:
        """Сайт и плакат автошколы: обычные страницы, сжатые, с кэшем на 10 минут."""
        headers = {"Cache-Control": f"public, max-age={age}", "X-Frame-Options": "DENY"}  # сайт не встраивают в чужие страницы
        if "gzip" in self.headers.get("Accept-Encoding", ""):
            headers["Content-Encoding"] = "gzip"
            raw = gzip.compress(raw, 6)
        self._send(200, raw, ctype, headers)

    def _redirect(self, target: Optional[str]) -> None:
        if target:
            self._send(302, headers={"Location": target, "Cache-Control": "no-store"})
        else:
            self._send(404)

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        path = url.path.rstrip("/") or "/"
        if path == "/health":
            return self._json(200, {"ok": True, "version": config.VERSION, "started": checker.status["started"], "ready": bool(config.TOKEN)})
        site = landing.page(path)
        if site:
            return self._page(*site)
        cal = re.fullmatch(r"/cal/(\d{1,9})/(-?\d{1,20})/([0-9a-f]{16})\.ics", path)
        if cal:
            body = agenda.ics(int(cal.group(1)), int(cal.group(2)), cal.group(3))
            if not body:
                return self._send(404)
            return self._send(200, body.encode(), "text/calendar; charset=utf-8",
                              {"Content-Disposition": f'inline; filename="cita-dgt-{cal.group(1)}.ics"', "Cache-Control": "no-store"})
        poster = re.fullmatch(r"/s/([A-Za-z0-9_-]{3,32})", path)
        if poster:
            body = schools.poster(poster.group(1))
            return self._page(body.encode(), "text/html; charset=utf-8", 600) if body else self._send(404)
        if path in FILES and (config.ROOT / FILES[path]).exists():
            return self._file(path)
        link = re.fullmatch(r"/([rt])/(\d{1,9})/(-?\d{1,20})/([0-9a-f]{16})", path)
        if link:
            kind, item, chat, sig = link.groups()
            resolve = ads.resolve_click if kind == "r" else rewards.task_click
            return self._redirect(resolve(int(item), int(chat), sig))
        if path.startswith("/api/"):
            return self._api("GET", path, parse_qs(url.query))
        self._send(404)

    do_HEAD = do_GET

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        length = self._length()
        if path == "/telegram":
            if not hmac.compare_digest(self.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), config.SECRET):
                return self._send(403)
            if length is None or length > MAX_WEBHOOK_BODY:
                return self._send(413)
            body = self.rfile.read(length)
            self._send(200, b"{}")
            try:
                update = json.loads(body)
            except ValueError:
                return None
            if isinstance(update, dict):
                on_update(update)
            return None
        if path.startswith("/api/"):
            return self._api("POST", path, {})
        self._send(404)

    def _length(self) -> Optional[int]:
        try:
            value = int(self.headers.get("Content-Length") or 0)
            return value if value >= 0 else None
        except ValueError:
            return None

    def _api(self, method: str, path: str, query: dict) -> None:
        user = validate_init_data(self.headers.get("X-Init-Data", ""))
        if not user:
            return self._json(401, {"error": "auth"})
        chat = user["id"]
        if not rate_ok(chat):
            return self._json(429, {"error": "rate"})
        body = {}
        if method == "POST":
            length = self._length()
            if length is None or length > (MAX_PHOTO_BODY if path == "/api/board/photo" else MAX_API_BODY):
                return self._json(413, {"error": "too large"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json(400, {"error": "json"})
            if not isinstance(body, dict):
                return self._json(400, {"error": "json"})
        _, is_new = store.touch_chat(chat, str(user.get("first_name") or "")[:64], str(user.get("username") or "")[:64])
        if is_new and store.setting("access") == "approval" and chat not in config.OWNERS:
            store.set_chat(chat, role="pending")
        try:
            with actions.chat_lock(chat):
                code, data = api(method, path, query, body, chat)
        except Exception:
            log.exception("ошибка API %s", path)
            code, data = 500, {"error": "server"}
        self._json(code, data)

    def log_message(self, *args) -> None:
        pass


def serve(port: int) -> ThreadingHTTPServer:
    slots = threading.BoundedSemaphore(64)  # не больше 64 соединений сразу — поток на каждое не держим

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 64

        def process_request(self, request, client_address):
            if not slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            super().process_request(request, client_address)

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                slots.release()

    return Server(("0.0.0.0", port), Handler)
