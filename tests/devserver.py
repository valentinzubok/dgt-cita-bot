"""Локальный просмотр мини-приложения без Telegram: своя база, настоящая проверка подписи, сайт DGT не трогаем."""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parent.parent
os.environ.update(TELEGRAM_TOKEN="123:DEV", ADMIN_CHAT_ID="", DATABASE_URL="", WEBHOOK_URL="http://localhost:8791", PORT="8791")
os.environ["SQLITE_PATH"] = tempfile.mkstemp(suffix=".db")[1]
sys.path.insert(0, str(ROOT))

import dgt  # noqa: E402
import premium  # noqa: E402
import store  # noqa: E402
import tg  # noqa: E402
import views  # noqa: E402
import webapp  # noqa: E402

OUTSIDE = {15}  # не подписан на канал: показывает экран подписки


def fake_call(method, _timeout=40, **p):
    if method == "getChatMember":
        return {"ok": True, "result": {"status": "left" if p.get("user_id") in OUTSIDE else "member"}}
    if method == "getChat":
        return {"ok": True, "result": {"id": -1001, "title": "OkSita · чат", "username": "oksita_chat"}}
    return {"ok": True, "result": "https://t.me/$demo"}


tg.call = fake_call
tg.upload_photo = lambda chat, content: "DEMO_FILE"
dgt.list_areas = lambda cid: [("CND", "Conductores"), ("VEH", "Vehículos"), ("CNJ", "Canjes"), ("SAN", "Sanciones")]
dgt.check = lambda cid, area: [dgt.Result("full", "demo")]
store.init()


DARK = {"bg_color": "#17212b", "secondary_bg_color": "#0e1621", "section_bg_color": "#17212b", "text_color": "#f5f5f5", "hint_color": "#708499",
        "button_color": "#5288c1", "button_text_color": "#ffffff"}
LIGHT = {"bg_color": "#ffffff", "secondary_bg_color": "#f2f2f7", "text_color": "#000000", "hint_color": "#8e8e93",
         "button_color": "#e11d48", "button_text_color": "#ffffff", "section_bg_color": "#ffffff"}


def link(uid, name, lang, dark=False):
    store.touch_chat(uid, name, "")
    store.set_chat(uid, lang=lang)
    fields = {"auth_date": str(int(time.time())), "query_id": "AAdev", "user": json.dumps({"id": uid, "first_name": name})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", b"123:DEV", hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    theme = quote(json.dumps(DARK if dark else LIGHT))
    return f"http://localhost:8791/app#tgWebAppData={quote(urlencode(fields))}&tgWebAppVersion=9.0&tgWebAppPlatform=ios&tgWebAppThemeParams={theme}"


def seed(paid):
    from datetime import timedelta
    premium.grant(paid, 24 * 12, "demo")
    today = views.today()
    days = [[(today + timedelta(days=n)).isoformat(), load] for n, load in
            ((6, "altaOcupacion"), (7, "altaOcupacion"), (9, "mediaOcupacion"), (10, "bajaOcupacion"), (13, "bajaOcupacion"), (14, "bajaOcupacion"), (41, "bajaOcupacion"))]
    empty = {"status": "full", "tramite": "x", "days": [], "hours": [], "address": "", "schedule": ""}
    a, _ = store.add_sub(paid, "486", "CYV", "Conductores / Vehículos")
    store.update_sub(a["id"], last=[{"status": "available", "tramite": "x", "days": days, "hours": ["09:20", "10:40", "11:10", "12:30"],
                                     "address": "Avda. Primero de Mayo 7, Murcia", "schedule": "L-V 9:00-14:00"}], checked_at=int(time.time()))
    b, _ = store.add_sub(paid, "526", "VEH", "Vehículos")
    store.update_sub(b["id"], last=[empty], checked_at=int(time.time()))
    c, _ = store.add_sub(paid, "545", "CNJ", "Canjes")
    store.update_sub(c["id"], last=[{**empty, "status": "needs_data"}], checked_at=int(time.time()))
    d, _ = store.add_sub(paid, "491", "SAN", "Sanciones")
    store.update_sub(d["id"], booked_date=(today + timedelta(days=9)).isoformat(), booked_time="10:40", paused=1, last=[empty])
    store.add_signal_sub(paid, "28", "tie")
    now = int(time.time())
    for hours, lasted, count in ((5, 26, 3), (29, 14, 1), (53, 41, 6)):
        store.write("INSERT INTO events (centro, area, opened_at, closed_at, days) VALUES (?, ?, ?, ?, ?)",
                    ("486", "CYV", now - hours * 3600, now - hours * 3600 + lasted * 60, count))


urls = {"premium": link(11, "Valentyn", "ru"), "free": link(12, "Olena", "uk"), "dark": link(13, "María", "es", True), "en": link(14, "Anna", "en"),
        "gate": link(15, "Petro", "uk")}
for chat in (11, 13, 14):
    seed(chat)
now = int(time.time())
for centro, area, count, hour in (("486", "CYV", 12, 9), ("526", "VEH", 7, 12), ("545", "CND", 4, 8), ("491", "SAN", 2, 20)):
    for i in range(count):
        store.write("INSERT INTO events (centro, area, opened_at, closed_at, days) VALUES (?, ?, ?, ?, ?)",
                    (centro, area, now - (i + 1) * 86400 - (i % 3) * 3600, now - (i + 1) * 86400 + 900, 3))
for kind, text in (("job", "Ищем повара в кафе в Малаге, полный день, договор и выходные по графику. Пишите @cafe_malaga"),
                   ("ad", "Автошкола в Мадриде: занятия на русском и украинском, подготовка к экзамену DGT. Запись: +34 612 345 678")):
    post = store.add_post(99, kind, text, None, 99)
    store.set_post(post["id"], status="published", message=post["id"], decided_at=now)
store.add_task("channel", "Подпишись на канал OkSita News", "Підпишись на канал OkSita News", "@oksita_news", "https://t.me/oksita_news", 12,
               "Suscríbete al canal OkSita News", "Join the OkSita News channel")
store.set_chat(14, discount_at=int(time.time()))
store.set_chat(14, premium_until=0)
store.flush()
out = Path(os.environ.get("DEV_URLS", "/tmp/claude-501/oksita-dev-urls.json"))
out.write_text(json.dumps(urls))
print("mini app dev server on http://localhost:8791/app", flush=True)
webapp.serve(8791).serve_forever()
