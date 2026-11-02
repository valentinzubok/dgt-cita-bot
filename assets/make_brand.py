"""Рисует логотип и баннеры разделов: SVG/HTML → PNG через Chrome → JPG.
Запуск: python3 assets/make_brand.py, только нужные баннеры: python3 assets/make_brand.py banner_board banner_trial"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

MARK = '''
<defs>
  <linearGradient id="chk" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2EE6A6"/><stop offset="1" stop-color="#06A96B"/></linearGradient>
  <linearGradient id="band" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#FF2D55"/><stop offset="1" stop-color="#FF6B2C"/></linearGradient>
  <filter id="sh" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="16" stdDeviation="22" flood-color="#7A0E2A" flood-opacity=".38"/></filter>
</defs>
<g filter="url(#sh)"><rect x="112" y="124" width="288" height="276" rx="70" fill="#fff"/></g>
<path d="M112 204 v-10 a70 70 0 0 1 70 -70 h148 a70 70 0 0 1 70 70 v10 z" fill="url(#band)"/>
<rect x="178" y="88" width="40" height="78" rx="20" fill="#fff"/><rect x="294" y="88" width="40" height="78" rx="20" fill="#fff"/>
<path d="M186 302 l52 52 l96 -108" fill="none" stroke="url(#chk)" stroke-width="44" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="404" cy="130" r="40" fill="#FFD60A" stroke="#fff" stroke-width="13"/>
'''
BG = '''
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FF2D55"/><stop offset=".55" stop-color="#FF6B2C"/><stop offset="1" stop-color="#FFB627"/></linearGradient>
  <radialGradient id="gl" cx=".22" cy=".12" r=".95"><stop offset="0" stop-color="#fff" stop-opacity=".38"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
</defs>
<rect width="512" height="512" fill="url(#bg)"/><rect width="512" height="512" fill="url(#gl)"/>
<g fill="none" stroke="#fff" stroke-opacity=".13" stroke-width="10"><circle cx="256" cy="262" r="216"/><circle cx="256" cy="262" r="268"/><circle cx="256" cy="262" r="326"/></g>
'''
LOGO = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">{BG}{MARK}</svg>'
MARK_ONLY = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">{MARK}</svg>'

GEM = '''<svg viewBox="0 0 400 360" width="430" height="387"><defs>
<linearGradient id="a" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#E0F7FF"/><stop offset="1" stop-color="#67D4FF"/></linearGradient>
<linearGradient id="b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8FE3FF"/><stop offset="1" stop-color="#3B9EFF"/></linearGradient>
<linearGradient id="c" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4FB6FF"/><stop offset="1" stop-color="#7C5CFF"/></linearGradient>
<filter id="g" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="26"/></filter></defs>
<ellipse cx="200" cy="190" rx="170" ry="130" fill="#7CC8FF" opacity=".5" filter="url(#g)"/>
<path d="M92 34 H308 L388 134 L200 340 L12 134 Z" fill="url(#c)"/>
<path d="M92 34 H308 L388 134 H12 Z" fill="url(#b)"/>
<path d="M92 34 L134 134 H12 Z" fill="url(#a)"/><path d="M200 34 L134 134 H266 Z" fill="url(#a)"/><path d="M308 34 L266 134 H388 Z" fill="#BFEFFF"/>
<path d="M134 134 L200 340 L12 134 Z" fill="#5AA8FF"/><path d="M266 134 L200 340 L388 134 Z" fill="#6C7BFF"/><path d="M134 134 H266 L200 340 Z" fill="#9EE0FF"/>
</svg>'''
GIFT = '''<svg viewBox="0 0 400 400" width="420" height="420"><defs>
<linearGradient id="a" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#E9FFF6"/></linearGradient>
<linearGradient id="r" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFD60A"/><stop offset="1" stop-color="#FFA51F"/></linearGradient>
<filter id="s" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="16" stdDeviation="20" flood-color="#04453A" flood-opacity=".4"/></filter></defs>
<g filter="url(#s)"><rect x="66" y="176" width="268" height="186" rx="30" fill="url(#a)"/><rect x="42" y="118" width="316" height="82" rx="26" fill="#fff"/></g>
<rect x="172" y="118" width="56" height="244" fill="url(#r)"/>
<path d="M200 118 C150 118 92 92 106 54 C120 18 180 40 200 118 Z" fill="none" stroke="url(#r)" stroke-width="28" stroke-linejoin="round"/>
<path d="M200 118 C250 118 308 92 294 54 C280 18 220 40 200 118 Z" fill="none" stroke="url(#r)" stroke-width="28" stroke-linejoin="round"/>
</svg>'''
RADAR = '''<svg viewBox="0 0 440 440" width="440" height="440"><defs>
<radialGradient id="p" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#2EE6A6"/><stop offset="1" stop-color="#2EE6A6" stop-opacity="0"/></radialGradient>
<linearGradient id="sw" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2EE6A6" stop-opacity="0"/><stop offset="1" stop-color="#2EE6A6" stop-opacity=".75"/></linearGradient></defs>
<g fill="none" stroke="#2EE6A6" stroke-opacity=".5" stroke-width="4"><circle cx="220" cy="220" r="60"/><circle cx="220" cy="220" r="120"/><circle cx="220" cy="220" r="180"/><path d="M220 30 V410 M30 220 H410"/></g>
<path d="M220 220 L396 150 A190 190 0 0 1 410 220 Z" fill="url(#sw)"/>
<circle cx="220" cy="220" r="10" fill="#2EE6A6"/>
<circle cx="316" cy="132" r="46" fill="url(#p)"/><circle cx="316" cy="132" r="13" fill="#fff"/>
<circle cx="136" cy="290" r="34" fill="url(#p)"/><circle cx="136" cy="290" r="10" fill="#FFD60A"/>
<circle cx="150" cy="130" r="26" fill="url(#p)"/><circle cx="150" cy="130" r="8" fill="#FF6B6B"/>
</svg>'''


PANEL = '''<svg viewBox="0 0 440 400" width="440" height="400"><defs>
<linearGradient id="a" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFB627"/><stop offset="1" stop-color="#FF2D55"/></linearGradient>
<linearGradient id="b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6EE7B7"/><stop offset="1" stop-color="#0FB78A"/></linearGradient>
<filter id="s" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#000" flood-opacity=".45"/></filter></defs>
<g filter="url(#s)"><rect x="20" y="34" width="400" height="332" rx="36" fill="#1E2436"/></g>
<rect x="20" y="34" width="400" height="58" rx="30" fill="#2A3147"/><rect x="20" y="62" width="400" height="30" fill="#2A3147"/>
<circle cx="58" cy="64" r="10" fill="#FF5F57"/><circle cx="90" cy="64" r="10" fill="#FEBC2E"/><circle cx="122" cy="64" r="10" fill="#28C840"/>
<rect x="66" y="238" width="48" height="92" rx="12" fill="url(#b)"/><rect x="138" y="190" width="48" height="140" rx="12" fill="url(#b)"/>
<rect x="210" y="218" width="48" height="112" rx="12" fill="url(#a)"/><rect x="282" y="150" width="48" height="180" rx="12" fill="url(#a)"/>
<path d="M70 196 L152 146 L228 176 L306 110 L372 124" fill="none" stroke="#fff" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="306" cy="110" r="13" fill="#fff"/></svg>'''


def page(bg, art, title, sub, accent="#fff", extra=""):
    return f'''<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0}}.c{{width:1280px;height:640px;position:relative;overflow:hidden;background:{bg};color:#fff;
font-family:-apple-system,"SF Pro Display","Helvetica Neue",Arial,sans-serif}}
.art{{position:absolute;left:96px;top:50%;transform:translateY(-50%);width:460px;height:460px;display:grid;place-items:center}}
.txt{{position:absolute;left:600px;top:50%;transform:translateY(-50%);right:50px}}
.t{{font-size:128px;font-weight:800;letter-spacing:-4px;line-height:1.02}}.t b{{color:{accent};font-weight:800}}
.s{{margin-top:24px;font-size:40px;font-weight:600;opacity:.92;line-height:1.2}}{extra}</style>
<div class="c">{{DECOR}}<div class="art">{art}</div><div class="txt"><div class="t">{title}</div><div class="s">{sub}</div></div></div>'''


RINGS = '<svg style="position:absolute;inset:0" width="1280" height="640"><g fill="none" stroke="#fff" stroke-opacity=".10" stroke-width="16"><circle cx="326" cy="320" r="300"/><circle cx="326" cy="320" r="420"/><circle cx="326" cy="320" r="560"/><circle cx="326" cy="320" r="720"/></g></svg>'
GLOW = '<div style="position:absolute;inset:0;background:radial-gradient(circle at 16% 18%,rgba(255,255,255,.34),rgba(255,255,255,0) 52%)"></div>'
HOME = page("linear-gradient(120deg,#FF2D55 0%,#FF6B2C 58%,#FFB627 100%)", MARK_ONLY.replace('width="512" height="512"', 'width="470" height="470"'),
            "<b>Ok</b>Sita", "cita previa DGT 🇪🇸", "#FFE34D").replace("{DECOR}", GLOW + RINGS)
PREMIUM = page("linear-gradient(120deg,#160B33 0%,#3B1A8F 55%,#D61C8E 100%)", GEM, "Premium", "⚡️ 5 min · 🏢 10 · 📡 250 km", "#fff").replace(
    "{DECOR}", '<div style="position:absolute;inset:0;background:radial-gradient(circle at 26% 50%,rgba(120,200,255,.3),rgba(0,0,0,0) 50%)"></div>' + RINGS)
BONUS = page("linear-gradient(120deg,#047A62 0%,#0FB78A 55%,#6EE7B7 100%)", GIFT, "Bonus", "👥 🎟 📝 → 💎", "#fff").replace("{DECOR}", GLOW + RINGS)
RADAR_P = page("linear-gradient(120deg,#07142B 0%,#0B2A4A 55%,#0E5A5E 100%)", RADAR, "Radar", "📍 100 · 150 · 250 km", "#fff").replace(
    "{DECOR}", '<div style="position:absolute;inset:0;background:radial-gradient(circle at 26% 50%,rgba(46,230,166,.22),rgba(0,0,0,0) 52%)"></div>')


CARD = '''<svg viewBox="0 0 440 320" width="440" height="320"><defs>
<linearGradient id="d" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#DCE9FF"/></linearGradient>
<linearGradient id="h" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2F6BFF"/><stop offset="1" stop-color="#1BC8E8"/></linearGradient>
<filter id="s" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="16" stdDeviation="20" flood-color="#04163F" flood-opacity=".5"/></filter></defs>
<g filter="url(#s)"><rect x="20" y="24" width="400" height="260" rx="30" fill="url(#d)"/></g>
<path d="M20 86 V54 a30 30 0 0 1 30 -30 H390 a30 30 0 0 1 30 30 V86 Z" fill="url(#h)"/>
<rect x="52" y="118" width="110" height="136" rx="16" fill="#C9DBFF"/><circle cx="107" cy="166" r="28" fill="#6E9BFF"/><path d="M66 244 a41 41 0 0 1 82 0 Z" fill="#6E9BFF"/>
<rect x="190" y="128" width="190" height="20" rx="10" fill="#9DB9EA"/><rect x="190" y="170" width="150" height="20" rx="10" fill="#C9DBFF"/><rect x="190" y="212" width="120" height="20" rx="10" fill="#C9DBFF"/>
<circle cx="372" cy="238" r="44" fill="#16C784"/><path d="M350 238 l16 16 l30 -34" fill="none" stroke="#fff" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/></svg>'''
DOCS = page("linear-gradient(120deg,#07225E 0%,#1646B8 58%,#14A7D8 100%)", CARD, "TIE · NIE", "🛂 👥 🟢", "#fff").replace(
    "{DECOR}", GLOW + RINGS)
ADMIN = page("linear-gradient(120deg,#0C1020 0%,#1B2442 55%,#3A2A7A 100%)", PANEL, "Admin", "📈 🩺 👥 💰 📣", "#fff").replace(
    "{DECOR}", '<div style="position:absolute;inset:0;background:radial-gradient(circle at 26% 50%,rgba(120,120,255,.25),rgba(0,0,0,0) 52%)"></div>' + RINGS)


BRIEFCASE = '''<svg viewBox="0 0 440 380" width="440" height="380"><defs>
<linearGradient id="b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#FFE7C2"/></linearGradient>
<linearGradient id="s" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#FF6B2C"/><stop offset="1" stop-color="#FFB627"/></linearGradient>
<filter id="f" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="16" stdDeviation="20" flood-color="#2A1A5E" flood-opacity=".5"/></filter></defs>
<path d="M150 96 V70 a26 26 0 0 1 26 -26 H264 a26 26 0 0 1 26 26 V96" fill="none" stroke="#fff" stroke-width="22"/>
<g filter="url(#f)"><rect x="34" y="92" width="372" height="244" rx="38" fill="url(#b)"/></g>
<path d="M34 186 a38 38 0 0 0 38 34 H368 a38 38 0 0 0 38 -34 V130 a38 38 0 0 0 -38 -38 H72 a38 38 0 0 0 -38 38 Z" fill="url(#s)"/>
<rect x="186" y="196" width="68" height="50" rx="14" fill="#fff"/><circle cx="220" cy="221" r="9" fill="#FF6B2C"/></svg>'''
BOARD = page("linear-gradient(120deg,#1B1147 0%,#4A1FB8 55%,#FF6B2C 100%)", BRIEFCASE, "Empleo", "💼 Jobs · 🤝 Partners", "#fff").replace("{DECOR}", GLOW + RINGS)
TRIAL = page("linear-gradient(120deg,#160B33 0%,#3B1A8F 50%,#0FB78A 100%)", GEM, "Premium", "🎁 72 h · 0 ⭐", "#fff").replace(
    "{DECOR}", '<div style="position:absolute;inset:0;background:radial-gradient(circle at 26% 50%,rgba(120,240,200,.3),rgba(0,0,0,0) 50%)"></div>' + RINGS)


def shot(html, out, w, h, quality=86):
    with tempfile.TemporaryDirectory() as tmp:
        src, png = Path(tmp) / "p.html", Path(tmp) / "p.png"
        src.write_text(html, encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        f"--window-size={w},{h}", f"--screenshot={png}", f"file://{src}"], check=True, capture_output=True)
        im = Image.open(png).convert("RGB")
        if out.suffix == ".png":
            im.save(out, optimize=True)
        else:
            im.save(out, quality=quality, optimize=True, progressive=True)


BANNERS = {"banner": HOME, "banner_premium": PREMIUM, "banner_bonus": BONUS, "banner_radar": RADAR_P, "banner_admin": ADMIN, "banner_docs": DOCS,
           "banner_board": BOARD, "banner_trial": TRIAL}


def main(only):
    for name, html in BANNERS.items():
        if not only or name in only:
            shot(html, HERE / f"{name}.jpg", 1280, 640)
    if not only:
        (HERE / "logo.svg").write_text(LOGO, encoding="utf-8")
        (HERE / "mark.svg").write_text(MARK_ONLY, encoding="utf-8")
        avatar = f'<!doctype html><style>html,body{{margin:0}}svg{{display:block;width:640px;height:640px}}</style>{LOGO}'
        shot(avatar, HERE / "avatar.png", 640, 640)
        shot(avatar, HERE / "avatar.jpg", 640, 640, 92)
        shot(HOME.replace("height:640px", "height:720px"), HERE / "cover.png", 1280, 720)  # картинка в описании бота: 640x360 в BotFather
        Image.open(HERE / "cover.png").resize((640, 360), Image.LANCZOS).save(HERE / "cover-640x360.png", optimize=True)
    print("готово")


if __name__ == "__main__":
    main(sys.argv[1:])
