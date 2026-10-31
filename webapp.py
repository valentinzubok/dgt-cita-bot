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
from collections import deque
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
import store
import views

log = logging.getLogger("web")

MAX_WEBHOOK_BODY = 1024 * 1024
MAX_API_BODY = 8 * 1024
INIT_MAX_AGE = 24 * 3600
CSP = ("default-src 'none'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors https://web.telegram.org https://*.telegram.org https://t.me")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml"}
FILES = {"/app": "webapp/index.html", "/app/app.js": "webapp/app.js", "/app/style.css": "webapp/style.css",
         "/app/icon.png": "assets/avatar.png", "/app/mark.svg": "assets/mark.svg", "/static/banner.jpg": "assets/banner.jpg",
         "/static/banner_premium.jpg": "assets/banner_premium.jpg", "/static/banner_bonus.jpg": "assets/banner_bonus.jpg",
         "/static/banner_radar.jpg": "assets/banner_radar.jpg", "/static/banner_admin.jpg": "assets/banner_admin.jpg"}
_cache: Dict[str, Tuple[bytes, bytes, str]] = {}
_hits: Dict[int, deque] = {}
_hits_lock = threading.Lock()
on_update: Callable[[dict], None] = lambda update: None  # подставляет bot.py


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


def sub_payload(sub: dict, lang: str) -> dict:
    days = views.all_days(sub.get("last"), sub.get("max_days"))
    emoji, text = views.summary(sub, lang)
    info = next((r for r in sub.get("last") or [] if r.get("address")), {})
    return {
        "id": sub["id"], "city": views.city(sub["centro"]), "centro": sub["centro"], "area": sub["area"],
        "type": views.sub_area(sub), "emoji": views.area_emoji(views.sub_area(sub)),
        "status": emoji, "statusText": text, "paused": bool(sub["paused"]), "filter": sub.get("max_days") or 0,
        "booked": sub.get("booked_date"), "bookedTime": sub.get("booked_time"),
        "days": [[iso, views.LOAD.get(load, "")] for iso, load in views.all_days(sub.get("last"))],
        "nearest": days[0][0] if days else None, "hours": views.hours_for(sub.get("last"), days[0][0]) if days else [],
        "address": info.get("address") or "", "schedule": info.get("schedule") or "",
        "checkedAt": sub.get("checked_at"),
    }


def me_payload(chat: int) -> dict:
    c = store.get_chat(chat)
    lang = c.get("lang") or "ru"
    paid = premium.is_premium(chat)
    data = {"lang": lang, "name": c.get("name") or "", "premium": paid, "premiumUntil": c.get("premium_until") or 0,
            "autoRenew": bool(c.get("sub_active")), "limit": premium.limit_subs(chat), "bot": config.BOT_USERNAME,
            "outage": checker.site_down(), "plans": [
                {"id": p, "days": premium.PLANS[p]["days"], "stars": premium.plan_price(p),
                 "recurring": premium.PLANS[p]["recurring"]} for p in ("p30", "p7", "p90")],
            "free": {"subs": store.setting("free_subs"), "interval": store.setting("interval")},
            "top": {"subs": store.setting("max_subs"), "interval": store.setting("interval_premium")}}
    if paid:
        subs = store.subs_of(chat)
        friends = store.friends_of(chat)
        data.update(subs=[sub_payload(s, lang) for s in subs], nextCheck=checker.next_check_for(chat),
                    used=premium.active_subs_count(chat), refLink=rewards.ref_link(chat), friends=len(friends),
                    friendsCounted=sum(1 for f in friends if f.get("ref_done_at")), alerts=c.get("alerts") or 0)
    return data


def api(method: str, path: str, query: dict, body: dict, chat: int) -> Tuple[int, dict]:
    c = store.get_chat(chat)
    if c.get("role") in ("banned", "pending"):
        return 403, {"error": "forbidden"}
    parts = [p for p in path.split("/") if p][1:]  # без «api»
    if parts == ["me"] and method == "GET":
        return 200, me_payload(chat)
    if parts == ["invoice"] and method == "POST":
        plan = body.get("plan")
        if plan not in premium.PLANS or checker.site_down():
            return 400, {"error": "unavailable"}
        link = premium.invoice_link(plan, c.get("lang") or "ru")
        return (200, {"link": link}) if link else (502, {"error": "telegram"})
    if not premium.is_premium(chat):
        return 402, {"error": "premium"}

    if parts == ["offices"] and method == "GET":
        items = sorted(((views.city(k), k) for k in dgt.CENTROS), key=lambda x: views.fold(x[0]))
        return 200, {"offices": [{"id": k, "city": name} for name, k in items]}
    if parts == ["areas"] and method == "GET":
        cid = (query.get("office") or [""])[0]
        if cid not in dgt.CENTROS:
            return 400, {"error": "office"}
        options = actions.office_options(cid, allow_fetch=not checker.site_down())
        if not options:
            return 503, {"error": "site"}
        lang = c.get("lang") or "ru"
        return 200, {"areas": [{"code": code, "label": views.area_label(code, label), "emoji": views.area_emoji(label),
                                "hint": views.area_hint(lang, label)} for code, label in options]}
    if parts == ["subs"] and method == "POST":
        status, sub = actions.add_subscription(chat, str(body.get("centro") or ""), str(body.get("area") or ""))
        if status == "ok":
            actions.check_now(sub)
        return (200 if status in ("ok", "exists") else 409), {"status": status}
    if len(parts) >= 2 and parts[0] == "subs" and parts[1].isdigit():
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
        if method == "GET" and action == "history":
            evs = store.events(sub["centro"], sub["area"], 10)
            return 200, {"events": [{"at": e["opened_at"], "closed": e["closed_at"], "days": e["days"]} for e in evs]}
    return 404, {"error": "not found"}


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
