"""Автошколы: у каждой свой промокод на Premium для учеников, ссылка, QR и плакат для печати.

Ученик сканирует QR → открывает бота с промокодом → источник promo_КОД, поэтому видно, сколько учеников пришло
и сколько потом заплатило. Заявку автошкола оставляет в боте, код выдаёт админ одной кнопкой."""
from __future__ import annotations

import html
import io
import random
import re
import time
from typing import Dict, Optional

import segno

import config
import rewards
import store
import views

DAYS = 7            # Premium для ученика
SEATS = 100         # учеников на один код
VALID_DAYS = 365
requests: Dict[int, str] = {}   # заявки автошкол: чат → текст (до решения админа)


def slug(name: str) -> str:
    words = re.sub(r"\b(autoescuela|autoescola|auto escuela|автошкола|автошкола)\b", " ", views.fold(name), flags=re.I)
    return re.sub(r"[^A-Z0-9]", "", words.upper())[:10] or "SCHOOL"


def create(name: str, city: str = "", chat: Optional[int] = None) -> dict:
    """Новая автошкола и её промокод: 7 дней Premium, 100 учеников, год."""
    base = slug(name)
    code = f"{base}{random.randint(100, 999)}"
    while store.get_promo(code):
        code = f"{base}{random.randint(100, 999)}"
    store.add_promo(code, DAYS * 24, SEATS, int(time.time()) + VALID_DAYS * 86400, f"🏫 {name[:40]}")
    store.bump("schools")
    return store.add_school(name[:60], city[:40], code, chat)


def parse_request(text: str) -> tuple:
    """«Autoescuela Sol, Málaga, +34…» → (название, город). Берём первые две части первой строки."""
    parts = [p.strip() for p in re.split(r"[,;\n·|]", text.strip()) if p.strip()]
    return (parts[0][:60] if parts else "Autoescuela"), (parts[1][:40] if len(parts) > 1 else "")


def link(code: str) -> str:
    return rewards.promo_link(code)


def poster_url(code: str) -> str:
    return f"{config.PUBLIC_URL}/s/{code}"


def qr(code: str) -> segno.QRCode:
    return segno.make(link(code), error="m")


def qr_png(code: str) -> bytes:
    out = io.BytesIO()
    qr(code).save(out, kind="png", scale=14, border=3, dark="#16161d")
    return out.getvalue()


def qr_svg(code: str) -> str:
    out = io.BytesIO()
    qr(code).save(out, kind="svg", scale=10, border=0, dark="#16161d", xmldecl=False, svgns=True, omitsize=True)
    return out.getvalue().decode()


def stats(school: dict) -> dict:
    promo = store.get_promo(school["code"]) or {}
    came = [c for c in store.all_chats() if c.get("source") == f"promo_{school['code']}"]
    return {"uses": promo.get("uses", 0), "seats": promo.get("max_uses", 0), "active": bool(promo.get("active")),
            "came": len(came), "paid": sum(1 for c in came if c.get("paid_at"))}


def kit_text(school: dict, lang: str) -> str:
    code, name = school["code"], views.esc(school["name"])
    return views.tx(
        lang,
        f"🏫 <b>{name}: код для учеников готов</b>\n\n<blockquote>🎟 Код: <code>{code}</code>\n"
        f"🎁 {DAYS} дней Premium бесплатно, до {SEATS} учеников</blockquote>\n"
        f"🔗 Ссылка: {link(code)}\n🖨 Плакат для печати с QR: {poster_url(code)}\n\n"
        "Ученик сканирует QR или открывает ссылку — бот сам включит Premium. Даты экзамена придут в Telegram, "
        "записывается ученик сам на сайте DGT.",
        f"🏫 <b>{name}: код для учнів готовий</b>\n\n<blockquote>🎟 Код: <code>{code}</code>\n"
        f"🎁 {DAYS} днів Premium безкоштовно, до {SEATS} учнів</blockquote>\n"
        f"🔗 Посилання: {link(code)}\n🖨 Плакат для друку з QR: {poster_url(code)}\n\n"
        "Учень сканує QR або відкриває посилання — бот сам увімкне Premium. Дати іспиту прийдуть у Telegram, "
        "записується учень сам на сайті DGT.",
        f"🏫 <b>{name}: el código para tus alumnos está listo</b>\n\n<blockquote>🎟 Código: <code>{code}</code>\n"
        f"🎁 {DAYS} días de Premium gratis, hasta {SEATS} alumnos</blockquote>\n"
        f"🔗 Enlace: {link(code)}\n🖨 Cartel para imprimir con QR: {poster_url(code)}\n\n"
        "El alumno escanea el QR o abre el enlace y el bot activa Premium solo. Las fechas de examen le llegan por Telegram; "
        "la cita la pide él mismo en la web de la DGT.",
        f"🏫 <b>{name}: your students' code is ready</b>\n\n<blockquote>🎟 Code: <code>{code}</code>\n"
        f"🎁 {DAYS} days of Premium free, up to {SEATS} students</blockquote>\n"
        f"🔗 Link: {link(code)}\n🖨 Printable poster with QR: {poster_url(code)}\n\n"
        "Students scan the QR or open the link and the bot turns Premium on by itself. Exam dates arrive in Telegram; "
        "students book on the DGT website themselves.")


POSTER = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{name} · OkSita</title><style>
@page{{size:A4;margin:0}}*{{box-sizing:border-box}}
body{{margin:0;background:#eceef3;font:16px/1.4 -apple-system,"SF Pro Text","Segoe UI",Roboto,Arial,sans-serif;color:#16161d}}
.sheet{{width:210mm;min-height:297mm;margin:16px auto;background:#fff;position:relative;overflow:hidden;display:flex;flex-direction:column}}
.top{{background:linear-gradient(120deg,#ff2d55,#ff6b2c 58%,#ffb627);color:#fff;padding:16mm 16mm 30mm;position:relative}}
.top:after{{content:"";position:absolute;left:-10%;right:-10%;bottom:-34mm;height:50mm;background:#fff;border-radius:50% 50% 0 0}}
.top>*{{position:relative;z-index:1}}
.brand{{font-weight:800;font-size:18pt;letter-spacing:-.5px;opacity:.95}}.brand b{{color:#ffe34d}}
.school{{margin-top:10mm;font-size:14pt;font-weight:600;opacity:.95}}
h1{{margin:3mm 0 0;font-size:34pt;line-height:1.02;letter-spacing:-1.5px;font-weight:850}}
.mid{{display:grid;grid-template-columns:76mm 1fr;gap:12mm;padding:0 16mm;align-items:center;position:relative;z-index:1;margin-top:-6mm}}
.qr{{background:#fff;border-radius:8mm;padding:6mm;box-shadow:0 6mm 16mm rgba(22,22,40,.14),0 0 0 .4mm #ececf2}}
.qr svg{{width:100%;height:auto;display:block}}
.code{{margin-top:4mm;text-align:center;font:700 15pt ui-monospace,Menlo,monospace;letter-spacing:2px}}
.gift{{display:inline-block;background:#0fb78a;color:#fff;font-weight:800;border-radius:99px;padding:2.5mm 6mm;font-size:15pt}}
ol{{margin:6mm 0 0;padding:0;list-style:none;counter-reset:s}}li{{counter-increment:s;display:flex;gap:4mm;align-items:center;margin:0 0 4.5mm;font-size:13pt}}
li:before{{content:counter(s);flex:none;width:9mm;height:9mm;border-radius:3mm;background:#16161d;color:#fff;display:grid;place-items:center;font-weight:800}}
.demo{{padding:14mm 16mm 0}}.notif{{display:flex;gap:5mm;align-items:center;background:#f4f5f9;border-radius:7mm;padding:6mm 7mm;max-width:140mm;margin:0 auto}}
.ava{{flex:none;width:14mm;height:14mm;border-radius:4mm;background:linear-gradient(135deg,#ff2d55,#ffb627);color:#fff;display:grid;place-items:center;font-weight:850;font-size:15pt}}
.notif small{{color:#8a8a93;float:right}}.notif p{{margin:1mm 0 0;font-size:12.5pt}}
.langs{{margin:auto 16mm 0;padding:7mm 0;border-top:.4mm solid #ececf2;display:grid;grid-template-columns:1fr 1fr 1fr;gap:6mm;font-size:10.5pt;color:#55556a}}
.langs b{{display:block;color:#16161d;margin-bottom:1mm}}
.foot{{padding:0 16mm 10mm;font-size:9pt;color:#8a8a93}}
.print{{position:fixed;right:16px;bottom:16px;border:0;border-radius:99px;padding:14px 22px;background:#16161d;color:#fff;font:600 16px system-ui;cursor:pointer}}
@media print{{body{{background:#fff}}.sheet{{margin:0}}.print{{display:none}}}}
@media screen and (max-width:600px){{.sheet{{width:100%;min-height:0;margin:0}}.mid{{grid-template-columns:1fr}}.langs{{grid-template-columns:1fr}}h1{{font-size:28pt}}}}
</style></head><body><main class="sheet">
<section class="top"><div class="brand"><b>Ok</b>Sita · cita previa DGT</div><div class="school">🏫 {name}{city}</div>
<h1>¿Esperando fecha de examen?<br>Te avisamos en Telegram.</h1></section>
<section class="mid"><div><div class="qr">{qr}</div><div class="code">{code}</div></div>
<div><span class="gift">🎁 {days} días Premium gratis</span>
<ol><li>Escanea el código con la cámara</li><li>Elige tu oficina de la DGT y el trámite</li><li>Recibe un aviso cuando haya fechas libres</li></ol>
<p style="margin:2mm 0 0;color:#55556a;font-size:11pt">Sin recargar la web. La cita la pides tú en sede.dgt.gob.es: OkSita solo avisa.</p></div></section>
<section class="demo"><div class="notif"><span class="ava">Ok</span><div style="flex:1"><b>OkSita</b><small>ahora</small>
<p>🟢 <b>{demo} · Examen práctico</b><br>📅 12 nov – 28 nov · 9 días libres</p></div></div></section>
<section class="langs"><div><b>🇺🇦 Українською</b>Скануй QR — {days} днів Premium безкоштовно. Бот напише, щойно з’являться дати іспиту.</div>
<div><b>🇷🇺 По-русски</b>Сканируй QR — {days} дней Premium бесплатно. Бот напишет, как только появятся даты экзамена.</div>
<div><b>🇬🇧 English</b>Scan the QR: {days} days of Premium free. The bot messages you as soon as exam dates appear.</div></section>
<div class="foot">OkSita no tiene relación con la DGT · t.me/{bot}</div></main>
<button class="print" onclick="print()">🖨 Imprimir</button></body></html>"""


def poster(code: str) -> Optional[str]:
    school = store.school_by_code(code)
    if not school:
        return None
    city = f" · {html.escape(school['city'])}" if school.get("city") else ""
    return POSTER.format(name=html.escape(school["name"]), city=city, qr=qr_svg(code), code=code, days=DAYS, bot=config.BOT_USERNAME,
                         demo=html.escape(school.get("city") or "Madrid"))
