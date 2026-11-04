"""Визит в календарь телефона: ссылка Google Calendar и файл .ics для iPhone и Outlook.

Файл отдаёт сервер по подписанной ссылке /cal/подписка/чат/подпись.ics: чужую запись по номеру не открыть."""
from __future__ import annotations

import hmac
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import urlencode

import config
import dgt
import rewards
import store
import views

DURATION = timedelta(hours=1)


def window(sub: dict) -> Tuple[datetime, datetime, bool]:
    """(начало, конец, весь день). Без времени визита — событие на весь день."""
    day = date.fromisoformat(sub["booked_date"])
    hhmm = re.fullmatch(r"(\d{1,2}):(\d{2})", sub.get("booked_time") or "")
    if not hhmm:
        start = datetime(day.year, day.month, day.day, tzinfo=config.TZ)
        return start, start + timedelta(days=1), True
    start = datetime(day.year, day.month, day.day, int(hhmm.group(1)), int(hhmm.group(2)), tzinfo=config.TZ)
    return start, start + DURATION, False


def title(sub: dict) -> str:
    return f"Cita DGT · {views.plain_title(sub)}"


def details(sub: dict, lang: str) -> str:
    items = "\n".join(f"• {re.sub(r'<[^>]+>', '', i)}" for i in views.checklist(lang, sub))
    return f"{items}\n\n{views.DGT_SEDE}\n⚡️ @{config.BOT_USERNAME}"


def place(sub: dict) -> str:
    return f"{dgt.CENTROS.get(sub['centro'], views.city(sub['centro']))}, España"


def google_link(sub: dict, lang: str) -> str:
    start, end, whole = window(sub)
    fmt = "%Y%m%d" if whole else "%Y%m%dT%H%M%S"
    return "https://calendar.google.com/calendar/render?" + urlencode({
        "action": "TEMPLATE", "text": title(sub), "dates": f"{start.strftime(fmt)}/{end.strftime(fmt)}",
        "ctz": "Europe/Madrid", "location": place(sub), "details": details(sub, lang)})


def ics_link(sub: dict) -> Optional[str]:
    if not config.PUBLIC_URL:
        return None
    return f"{config.PUBLIC_URL}/cal/{sub['id']}/{sub['chat']}/{rewards.sign('cal', sub['id'], sub['chat'])}.ics"


def _text(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Строки длиннее 75 байт переносим, как требует RFC 5545."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > 74:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    return "\r\n".join(out + [cur])


def ics(sid: int, chat: int, sig: str) -> Optional[str]:
    sub = store.get_sub(sid)
    if not sub or sub["chat"] != chat or not sub.get("booked_date") or not hmac.compare_digest(rewards.sign("cal", sid, chat), sig):
        return None
    lang = views.lang_of(chat)
    start, end, whole = window(sub)
    utc = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: E731
    when = ([f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{end:%Y%m%d}"] if whole
            else [f"DTSTART:{utc(start)}", f"DTEND:{utc(end)}"])
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//OkSita//Cita DGT//ES", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "BEGIN:VEVENT", f"UID:oksita-{sid}-{sub['booked_date']}@{config.BOT_USERNAME}", f"DTSTAMP:{utc(datetime.now(timezone.utc))}",
             *when, f"SUMMARY:{_text(title(sub))}", f"LOCATION:{_text(place(sub))}", f"DESCRIPTION:{_text(details(sub, lang))}",
             "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_text(title(sub))}", f"TRIGGER:{'-PT12H' if whole else '-PT2H'}", "END:VALARM",
             "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
