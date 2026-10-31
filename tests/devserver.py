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

tg.call = lambda method, _timeout=40, **p: {"ok": True, "result": "https://t.me/$demo"}
dgt.list_areas = lambda cid: [("CND", "Conductores"), ("VEH", "Vehículos"), ("CNJ", "Canjes"), ("SAN", "Sanciones")]
dgt.check = lambda cid, area: [dgt.Result("full", "demo")]
store.init()


def link(uid, name, lang):
    store.touch_chat(uid, name, "")
    store.set_chat(uid, lang=lang)
    fields = {"auth_date": str(int(time.time())), "query_id": "AAdev", "user": json.dumps({"id": uid, "first_name": name})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", b"123:DEV", hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    theme = quote(json.dumps({"bg_color": "#ffffff", "secondary_bg_color": "#f2f2f7", "text_color": "#000000", "hint_color": "#8e8e93",
                              "button_color": "#e11d48", "button_text_color": "#ffffff", "section_bg_color": "#ffffff"}))
    return f"http://localhost:8791/app#tgWebAppData={quote(urlencode(fields))}&tgWebAppVersion=9.0&tgWebAppPlatform=ios&tgWebAppThemeParams={theme}"


def seed():
    paid = 11
    premium.grant(paid, 24 * 12, "demo") if store.get_chat(paid).get("created_at") else None
    today = views.today()
    from datetime import timedelta
    days = [[(today + timedelta(days=n)).isoformat(), load] for n, load in
            ((6, "altaOcupacion"), (7, "altaOcupacion"), (9, "mediaOcupacion"), (10, "bajaOcupacion"), (13, "bajaOcupacion"), (14, "bajaOcupacion"), (41, "bajaOcupacion"))]
    a, _ = store.add_sub(paid, "486", "CYV", "Conductores / Vehículos")
    store.update_sub(a["id"], last=[{"status": "available", "tramite": "x", "days": days, "hours": ["09:20", "10:40", "11:10", "12:30"],
                                     "address": "Avda. Primero de Mayo 7, Murcia", "schedule": "L-V 9:00-14:00"}], checked_at=int(time.time()))
    b, _ = store.add_sub(paid, "526", "VEH", "Vehículos")
    store.update_sub(b["id"], last=[{"status": "full", "tramite": "x", "days": [], "hours": [], "address": "", "schedule": ""}], checked_at=int(time.time()))
    c, _ = store.add_sub(paid, "545", "CNJ", "Canjes")
    store.update_sub(c["id"], paused=1, last=[{"status": "full", "tramite": "x", "days": [], "hours": [], "address": "", "schedule": ""}])


premium_url, free_url = link(11, "Valentyn", "ru"), link(12, "Olena", "uk")
seed()
store.flush()
out = Path(os.environ.get("DEV_URLS", "/tmp/claude-501/oksita-dev-urls.json"))
out.write_text(json.dumps({"premium": premium_url, "free": free_url}))
print("mini app dev server on http://localhost:8791/app", flush=True)
webapp.serve(8791).serve_forever()
