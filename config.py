"""Настройки из окружения: .env локально, Environment на Render."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent


def _load_env() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


_load_env()

BRAND = "OkSita"
LANGS = ("uk", "ru", "es", "en")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "oksitabot").lstrip("@")
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}/"
SECRET = hashlib.sha256(("dgt-webhook:" + TOKEN).encode()).hexdigest()[:40]
LINK_KEY = hashlib.sha256(("oksita-links:" + TOKEN).encode()).digest()  # подпись ссылок в рекламе
PUBLIC_URL = (os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
VERSION = os.environ.get("RENDER_GIT_COMMIT", "")[:7] or "dev"
# Владельцы бота (chat id через запятую): полный доступ к админке, назначают админов
OWNERS = {int(x) for x in os.environ.get("ADMIN_CHAT_ID", "").replace(" ", "").split(",") if x.lstrip("-").isdigit()}
MAX_OFFICES = int(os.environ.get("MAX_OFFICES", "30"))
TZ = ZoneInfo("Europe/Madrid")
