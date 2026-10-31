"""Веб-сервер бота: webhook Telegram, мини-приложение и его API, переходы по рекламным ссылкам."""
from __future__ import annotations

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
import checker
import config
import dgt
import premium
import radar
import rewards
import signals
import store
import tg
import views
from centros import COORDS

log = logging.getLogger("web")

MAX_WEBHOOK_BODY = 1024 * 1024
MAX_API_BODY = 8 * 1024
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
         "/static/banner_docs.jpg": "assets/banner_docs.jpg"}
STATES = {"🟢": "free", "🟡": "later", "🔴": "full", "⏸": "paused", "✅": "booked", "⏳": "pending",
          "⚠️": "error", "🔐": "locked", "⚪️": "none", "❔": "error"}
LOADS = {"bajaOcupacion": "many", "mediaOcupacion": "mid", "altaOcupacion": "few"}
_cache: Dict[str, Tuple[bytes, bytes, str]] = {}
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
            "friendsCounted": sum(1 for f in friends if f.get("ref_done_at")), "pending": len(rewards.pending_friends(chat)), "tasks": tasks}


def me_payload(chat: int) -> dict:
    c = store.get_chat(chat)
    lang = c.get("lang") or "ru"
    paid = premium.is_premium(chat)
    data = {"lang": lang, "langSet": bool(c.get("lang")), "name": c.get("name") or "", "premium": paid, "premiumUntil": c.get("premium_until") or 0,
            "autoRenew": bool(c.get("sub_active")), "limit": premium.limit_subs(chat), "bot": config.BOT_USERNAME, "bookUrl": dgt.START_URL,
            "outage": checker.site_down(), "quiet": bool(c.get("quiet")), "adsOk": bool(c.get("ads_ok")), "plans": [
                {"id": p, "days": premium.PLANS[p]["days"], "stars": premium.plan_price(p),
                 "recurring": premium.PLANS[p]["recurring"]} for p in ("p30", "p7", "p90")],
            "free": {"subs": store.setting("free_subs"), "interval": store.setting("interval"), "signals": signals.FREE_SUBS},
            "top": {"subs": store.setting("max_subs"), "interval": store.setting("interval_premium"), "signals": signals.TOP_SUBS}}
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
            "docs": [{"id": d, "title": views.doc_name(lang, d)} for d in signals.DOCS]}


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


PAGES = {"help": views.help_view, "terms": views.terms_view, "privacy": views.privacy_view, "ukraine": views.ukraine_view}


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
                     "bestHour": hours[0][0] if hours else None, "average": views.fmt_dur(sum(closed) // len(closed), lang) if closed else ""}
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
    reply = account_api(method, parts, body, chat, c)
    if reply:
        return reply
    if not premium.is_premium(chat):
        return 402, {"error": "premium"}
    lang = c.get("lang") or "ru"
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

    def _redirect(self, target: Optional[str]) -> None:
        if target:
            self._send(302, headers={"Location": target, "Cache-Control": "no-store"})
        else:
            self._send(404)

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        path = url.path.rstrip("/") or "/"
        if path in ("/", "/health"):
            return self._json(200, {"ok": True, "version": config.VERSION, "started": checker.status["started"], "ready": bool(config.TOKEN)})
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
            if length is None or length > MAX_API_BODY:
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
