"""Короткое вертикальное видео для Reels, TikTok и Shorts (1080×1920, 14 секунд, без музыки — её добавляют в приложении).
Кадры рисует Chrome через Playwright, видео собирает ffmpeg. Результат: promo/video/oksita_uk.mp4, _ru, _es,
а про очередь ДП «Документ» — oksita_uk_pas.mp4 и oksita_ru_pas.mp4.
Запуск: python3 assets/make_video.py [uk ru es uk_pas ru_pas]   (нужны pip install playwright, Google Chrome и ffmpeg)"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from make_brand import LOGO

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "promo" / "video"
FPS, SECONDS = 30, 14

TEXT = {
    "uk": dict(hook="Місяцями чекаєш<br><b>cita в DGT?</b>", empty="No hay citas disponibles", refresh="Оновлюєш сайт щодня…",
               alert="🔔 Є ВІЛЬНІ ДАТИ!", office="🏢 Málaga · Іспит з водіння", days="📅 9 днів · 12–28 листопада", hours="⏰ 09:30 · 10:15 · 11:00",
               now="зараз", day="понеділок, 3 листопада", how="OkSita перевіряє<br><b>сайт DGT за тебе</b>",
               points=["68 офісів по всій Іспанії", "Безкоштовно, без NIE", "Сповіщення прямо в Telegram"], cta="Знайди в Telegram", free="Безкоштовно"),
    "ru": dict(hook="Месяцами ждёшь<br><b>cita в DGT?</b>", empty="No hay citas disponibles", refresh="Обновляешь сайт каждый день…",
               alert="🔔 ЕСТЬ СВОБОДНЫЕ ДАТЫ!", office="🏢 Málaga · Экзамен по вождению", days="📅 9 дней · 12–28 ноября", hours="⏰ 09:30 · 10:15 · 11:00",
               now="сейчас", day="понедельник, 3 ноября", how="OkSita проверяет<br><b>сайт DGT за тебя</b>",
               points=["68 офисов по всей Испании", "Бесплатно, без NIE", "Уведомление прямо в Telegram"], cta="Найди в Telegram", free="Бесплатно"),
    "es": dict(hook="¿Meses esperando<br><b>cita en la DGT?</b>", empty="No hay citas disponibles", refresh="Recargando la web cada día…",
               alert="🔔 ¡HAY FECHAS LIBRES!", office="🏢 Málaga · Examen práctico", days="📅 9 días · 12–28 de noviembre", hours="⏰ 09:30 · 10:15 · 11:00",
               now="ahora", day="lunes, 3 de noviembre", how="OkSita revisa<br><b>la web de la DGT por ti</b>",
               points=["68 oficinas en toda España", "Gratis, sin NIE", "Aviso directo en Telegram"], cta="Búscalo en Telegram", free="Gratis"),
}

DGT = dict(site="sede.dgt.gob.es", empty_sub="Cita previa · Jefatura de Tráfico")
TEXT.update({
    "uk_pas": dict(hook="Чекаєш талон<br><b>у ДП «Документ»?</b>", empty="Наразі всі місця зайняті", site="pasport.org.ua",
                   empty_sub="Електронна черга · Паспортний сервіс", refresh="Оновлюєш сторінку щодня…",
                   alert="🟢 БАЧАТЬ ТАЛОНИ!", office="🛂 Паспорт України · Madrid", days="👤 Сигнал від того, хто теж чекає",
                   hours="👉 Відкрий офіційну чергу", now="зараз", day="понеділок, 3 листопада",
                   how="Люди діляться<br><b>сигналом про талони</b>",
                   points=["Мадрид · Барселона · Валенсія", "Безкоштовно, без даних паспорта", "Запис лише на офіційному сайті"],
                   cta="Знайди в Telegram", free="Безкоштовно"),
    "ru_pas": dict(hook="Ждёшь талон<br><b>в ДП «Документ»?</b>", empty="Наразі всі місця зайняті", site="pasport.org.ua",
                   empty_sub="Электронная очередь · Паспортный сервис", refresh="Обновляешь страницу каждый день…",
                   alert="🟢 ВИДЯТ ТАЛОНЫ!", office="🛂 Паспорт Украины · Madrid", days="👤 Сигнал от того, кто тоже ждёт",
                   hours="👉 Открой официальную очередь", now="сейчас", day="понедельник, 3 ноября",
                   how="Люди делятся<br><b>сигналом о талонах</b>",
                   points=["Мадрид · Барселона · Валенсия", "Бесплатно, без данных паспорта", "Запись только на официальном сайте"],
                   cta="Найди в Telegram", free="Бесплатно"),
})

PAGE = """<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}html,body{width:1080px;height:1920px;overflow:hidden;background:#0d0d12}
body{font-family:-apple-system,"SF Pro Display","Helvetica Neue",Arial,sans-serif;color:#fff;-webkit-font-smoothing:antialiased}
.bg{position:absolute;inset:0;background:linear-gradient(160deg,#1a0f3a 0%,#3b1a8f 45%,#ff2d55 100%)}
.glow{position:absolute;width:1400px;height:1400px;left:-160px;top:-300px;border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.22),rgba(255,255,255,0) 60%)}
.s{position:absolute;left:0;right:0;opacity:0}
h1{font-size:118px;line-height:1.02;letter-spacing:-4px;font-weight:850;text-align:center}h1 b{color:#ffe34d}
.browser{position:absolute;left:110px;right:110px;top:820px;border-radius:40px;background:#fff;color:#16161d;overflow:hidden;box-shadow:0 40px 90px rgba(0,0,0,.45)}
.bar{display:flex;align-items:center;gap:14px;padding:26px 30px;background:#f1f1f5;font-size:30px;color:#6b6b78}
.bar i{width:20px;height:20px;border-radius:50%;background:#ff5f57;display:block}.bar i+i{background:#febc2e}.bar i+i+i{background:#28c840}
.url{margin-left:14px;flex:1;background:#fff;border-radius:16px;padding:10px 20px}
.empty{padding:70px 40px;text-align:center;font-size:44px;font-weight:700}.empty small{display:block;font-size:30px;color:#9a9aa8;margin-top:16px;font-weight:500}
.f5{position:absolute;right:150px;top:740px;width:150px;height:150px;border-radius:50%;background:#ffe34d;color:#16161d;display:grid;place-items:center;font-size:86px;box-shadow:0 20px 50px rgba(0,0,0,.35)}
.caption{position:absolute;left:0;right:0;top:1500px;text-align:center;font-size:52px;font-weight:700;opacity:.9}
.phone{position:absolute;left:190px;top:330px;width:700px;height:1440px;border-radius:110px;background:#0b0c12;border:22px solid #26272f;box-shadow:0 60px 140px rgba(0,0,0,.55);overflow:hidden}
.phone .wall{position:absolute;inset:0;background:linear-gradient(180deg,#22345a,#0e1424)}
.isl{position:absolute;left:50%;top:26px;width:200px;height:56px;margin-left:-100px;border-radius:30px;background:#000}
.day{position:absolute;left:0;right:0;top:130px;text-align:center;font-size:34px;font-weight:600;opacity:.75}
.clock{position:absolute;left:0;right:0;top:170px;text-align:center;font-size:190px;font-weight:700;letter-spacing:-6px}
.nf{position:absolute;left:30px;right:30px;top:520px;border-radius:44px;background:rgba(245,245,250,.96);color:#121217;padding:30px 34px;box-shadow:0 20px 50px rgba(0,0,0,.35)}
.nf .top{display:flex;align-items:center;gap:16px;font-size:28px;font-weight:600;color:#6b6b76}.nf .top span:last-child{margin-left:auto}
.nf .ic{width:56px;height:56px;border-radius:14px;overflow:hidden}.nf .ic svg{width:100%;height:100%;display:block}
.nf .t{font-size:40px;font-weight:850;margin-top:16px}.nf .b{font-size:36px;line-height:1.38;margin-top:8px}
.how{top:300px}.points{position:absolute;left:120px;right:120px;top:760px;display:grid;gap:34px}
.pt{display:flex;align-items:center;gap:30px;font-size:54px;font-weight:750;opacity:0}
.pt i{flex:none;width:96px;height:96px;border-radius:30px;background:#fff;color:#16c784;display:grid;place-items:center;font-style:normal;font-size:60px;font-weight:900}
.end{top:0;bottom:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:40px}
.logo{width:300px;height:300px;border-radius:72px;overflow:hidden;box-shadow:0 40px 90px rgba(0,0,0,.4)}.logo svg{width:100%;height:100%;display:block}
.name{font-size:150px;font-weight:850;letter-spacing:-5px}.name b{color:#ffe34d}
.handle{font-size:72px;font-weight:800;background:#fff;color:#16161d;border-radius:999px;padding:24px 60px}
.sub{font-size:48px;font-weight:650;opacity:.9}
</style><div class="bg"></div><div class="glow"></div>
<div class="s" id="hook" style="top:300px"><h1>{hook}</h1></div>
<div class="s" id="site"><div class="browser"><div class="bar"><i></i><i></i><i></i><span class="url">{site}</span></div>
<div class="empty">😕 {empty}<small>{empty_sub}</small></div></div><div class="f5" id="f5">↻</div>
<div class="caption">{refresh}</div></div>
<div class="s" id="lock" style="top:0;bottom:0"><div class="phone"><div class="wall"></div><div class="isl"></div><div class="day">{day}</div><div class="clock">9:41</div>
<div class="nf" id="nf"><div class="top"><span class="ic">{logo}</span><span>OkSita</span><span>{now}</span></div><div class="t">{alert}</div>
<div class="b">{office}<br>{days}<br>{hours}</div></div></div></div>
<div class="s how" id="how"><h1>{how}</h1></div>
<div class="points" id="points">{points}</div>
<div class="s end" id="end"><div class="logo">{logo}</div><div class="name"><b>Ok</b>Sita</div><div class="handle">@oksitabot</div>
<div class="sub">{cta} · {free}</div></div>
<script>
const $ = (id) => document.getElementById(id);
const clamp = (x) => Math.max(0, Math.min(1, x));
const ease = (x) => 1 - Math.pow(1 - clamp(x), 3);
const back = (x) => { x = clamp(x); const c = 1.7; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
function show(el, t, a, b, fade) {  // элемент виден с a до b секунд, плавно появляется и исчезает
  const f = fade || .35;
  const v = Math.min(ease((t - a) / f), 1 - ease((t - b + f) / f));
  el.style.opacity = t < a || t > b ? 0 : v;
  return clamp((t - a) / f);
}
window.seek = (t) => {
  const k1 = show($("hook"), t, 0, 3.1);
  $("hook").style.transform = `translateY(${(1 - ease(k1)) * 60}px)`;
  show($("site"), t, 0.6, 3.1);
  $("f5").style.transform = `rotate(${t * 300}deg) scale(${1 + 0.08 * Math.sin(t * 9)})`;
  show($("lock"), t, 3.1, 8.2);
  const n = back((t - 4.0) / 0.6);
  $("nf").style.transform = `translateY(${(1 - n) * -420}px) scale(${0.9 + 0.1 * n})`;
  $("nf").style.opacity = clamp((t - 4.0) / 0.25);
  const k2 = show($("how"), t, 8.2, 11.6);
  $("how").style.transform = `translateY(${(1 - ease(k2)) * 60}px)`;
  [...document.querySelectorAll(".pt")].forEach((p, i) => {
    const k = ease((t - 9.0 - i * 0.45) / 0.4);
    p.style.opacity = t > 11.6 ? Math.max(0, 1 - (t - 11.6) / 0.35) : k;
    p.style.transform = `translateX(${(1 - k) * 80}px)`;
  });
  const k3 = show($("end"), t, 11.7, 99);
  $("end").style.transform = `scale(${0.92 + 0.08 * back(k3)})`;
};
seek(0);
</script>"""


def page(lang: str) -> str:
    t = {**DGT, **TEXT[lang]}
    points = "".join(f'<div class="pt"><i>✓</i><span>{p}</span></div>' for p in t["points"])
    html = PAGE
    for key, value in {**t, "points": points, "logo": LOGO}.items():
        html = html.replace("{" + key + "}", value)
    return html


def render(lang: str) -> Path:
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"oksita_{lang}.mp4"
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
        src = Path(tmp) / "v.html"
        src.write_text(page(lang), encoding="utf-8")
        browser = pw.chromium.launch(channel="chrome")
        tab = browser.new_page(viewport={"width": 1080, "height": 1920})
        tab.goto(src.as_uri())
        for i in range(FPS * SECONDS):
            tab.evaluate(f"seek({json.dumps(i / FPS)})")
            tab.screenshot(path=str(Path(tmp) / f"f{i:04d}.jpg"), type="jpeg", quality=92)
        browser.close()
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(Path(tmp) / "f%04d.jpg"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(out)], check=True)
    return out


def main(langs):
    for lang in langs or list(TEXT):
        print(render(lang))


if __name__ == "__main__":
    main(sys.argv[1:])
