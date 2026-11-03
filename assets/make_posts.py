"""Картинки постов: для канала (assets/post_*.jpg, 1280×720, украинский) и для рекламы в чатах (promo/img/*_uk.jpg, *_ru.jpg, 1080×1080).
Запуск: python3 assets/make_posts.py, только нужные: python3 assets/make_posts.py trial radar"""
import sys
from pathlib import Path

from make_brand import BRIEFCASE, CARD, GEM, GIFT, LOGO, RADAR, shot

HERE = Path(__file__).resolve().parent
PROMO = HERE.parent / "promo" / "img"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}html,body{margin:0}
.c{position:relative;overflow:hidden;color:#fff;font-family:-apple-system,"SF Pro Display","Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
.deco{position:absolute;inset:0}
.brand{position:absolute;display:flex;align-items:center;font-weight:800;letter-spacing:-.5px}
.logo{border-radius:24%;overflow:hidden;box-shadow:0 10px 26px rgba(0,0,0,.28);flex:none}.logo svg{display:block;width:100%;height:100%}
.txt{position:absolute}
.h{font-weight:800;letter-spacing:-.035em;line-height:1.03}.h b{color:var(--accent);font-weight:800}
.sub{font-weight:600;opacity:.93;line-height:1.24;margin-top:.55em}
.chips{display:flex;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;border-radius:999px;background:rgba(255,255,255,.16);border:2px solid rgba(255,255,255,.24);font-weight:700;white-space:nowrap}
.cta{position:absolute;display:inline-flex;align-items:center;background:#fff;color:#17121F;font-weight:800;border-radius:999px;box-shadow:0 16px 36px rgba(0,0,0,.28);white-space:nowrap}
.cta i{font-style:normal;color:var(--cta)}
.art{position:absolute;width:560px;height:600px}
.phone{position:absolute;left:70px;top:0;width:420px;height:860px;border-radius:64px;background:#0D0E13;border:12px solid #23242C;box-shadow:0 30px 80px rgba(0,0,0,.45)}
.phone .isl{position:absolute;left:50%;top:18px;width:120px;height:34px;margin-left:-60px;border-radius:20px;background:#000}
.phone .clock{position:absolute;left:0;right:0;top:78px;text-align:center;font-size:92px;font-weight:700;letter-spacing:-2px;color:#fff}
.phone .day{position:absolute;left:0;right:0;top:66px;text-align:center;font-size:20px;font-weight:600;opacity:.75}
.nf{position:absolute;left:18px;right:18px;border-radius:28px;background:rgba(245,245,250,.95);color:#121217;padding:18px 20px;box-shadow:0 10px 30px rgba(0,0,0,.3)}
.nf .top{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:600;color:#6B6B76}
.nf .top .ic{width:30px;height:30px;border-radius:8px;overflow:hidden}.nf .top .ic svg{width:100%;height:100%;display:block}
.nf .top .app{flex:1;text-transform:uppercase;letter-spacing:.5px}
.nf .t{margin-top:8px;font-size:22px;font-weight:800}
.nf .b{margin-top:4px;font-size:20px;font-weight:500;color:#33333C;line-height:1.3}
.card{position:absolute;border-radius:30px;background:rgba(255,255,255,.96);color:#14141B;box-shadow:0 20px 50px rgba(0,0,0,.35)}
.row{display:flex;align-items:center;gap:16px;font-weight:700}
.ok{width:40px;height:40px;border-radius:50%;background:#16C784;display:grid;place-items:center;flex:none}
.ok svg{width:22px;height:22px}
.pill{position:absolute;display:flex;align-items:center;gap:14px;border-radius:24px;background:rgba(255,255,255,.95);color:#14141B;font-weight:700;box-shadow:0 14px 34px rgba(0,0,0,.3)}
.pill .d{margin-left:auto;font-weight:800}
.badge{position:absolute;display:grid;place-items:center;text-align:center;border-radius:50%;font-weight:800;line-height:1;box-shadow:0 16px 40px rgba(0,0,0,.3)}
/* квадрат 1080 */
.sq{width:1080px;height:1080px}
.sq .brand{left:72px;top:64px;gap:18px;font-size:40px}.sq .logo{width:72px;height:72px}
.sq .txt{left:72px;right:72px;top:180px}.sq .h{font-size:88px}.sq .sub{font-size:38px;max-width:900px}
.sq .chips{position:absolute;left:72px;top:600px;width:470px;flex-direction:column;gap:16px;align-items:flex-start}.sq .chip{font-size:30px;padding:14px 24px;gap:10px}
.sq .cta{left:72px;bottom:64px;font-size:34px;padding:24px 38px;gap:12px}
.sq .art{right:20px;top:500px}.sq .phone{left:110px}
/* пост в канале 1280×720 */
.ls{width:1280px;height:720px}
.ls .brand{left:60px;top:50px;gap:16px;font-size:34px}.ls .logo{width:60px;height:60px}
.ls .txt{left:64px;top:140px;width:640px}.ls .h{font-size:60px}.ls .sub{font-size:28px}
.ls .chips{margin-top:26px;gap:10px}.ls .chip{font-size:22px;padding:10px 18px;gap:8px}
.ls .cta{left:60px;bottom:52px;font-size:28px;padding:20px 32px;gap:10px}
.ls .art{right:40px;top:96px}
"""

CHECK = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg>'
RINGS = ('<svg class="deco" viewBox="0 0 1000 1000" preserveAspectRatio="xMaxYMax slice"><g fill="none" stroke="#fff" stroke-opacity=".10" stroke-width="14">'
         '<circle cx="760" cy="760" r="230"/><circle cx="760" cy="760" r="360"/><circle cx="760" cy="760" r="500"/><circle cx="760" cy="760" r="660"/></g></svg>')
GLOW = '<div class="deco" style="background:radial-gradient(circle at 14% 10%,rgba(255,255,255,.30),rgba(255,255,255,0) 50%)"></div>'

THEMES = {
    "hero": ("linear-gradient(135deg,#FF2D55 0%,#FF6B2C 55%,#FFB627 100%)", "#FFE34D", "#FF2D55"),
    "trial": ("linear-gradient(135deg,#160B33 0%,#3B1A8F 52%,#0FB78A 100%)", "#7CF5C8", "#3B1A8F"),
    "radar": ("linear-gradient(135deg,#07142B 0%,#0B2A4A 55%,#0E5A5E 100%)", "#2EE6A6", "#0B7A5E"),
    "tips": ("linear-gradient(135deg,#2B124C 0%,#7A1FA2 55%,#FF2D55 100%)", "#FFD60A", "#7A1FA2"),
    "docs": ("linear-gradient(135deg,#07225E 0%,#1646B8 58%,#14A7D8 100%)", "#FFD60A", "#1646B8"),
    "jobs": ("linear-gradient(135deg,#1B1147 0%,#4A1FB8 55%,#FF6B2C 100%)", "#FFB627", "#4A1FB8"),
    "friends": ("linear-gradient(135deg,#047A62 0%,#0FB78A 55%,#6EE7B7 100%)", "#FFE34D", "#047A62"),
    "school": ("linear-gradient(135deg,#FF2D55 0%,#FF6B2C 50%,#7A1FA2 100%)", "#FFE34D", "#FF2D55"),
    "app": ("linear-gradient(135deg,#0B3C8C 0%,#1C7CE0 55%,#2AABEE 100%)", "#FFE34D", "#1C7CE0"),
}

TEXT = {
    "hero": {
        "uk": dict(h="Вільна дата в DGT?<br><b>Дізнаєшся першим</b>", sub="Бот перевіряє сайт DGT і пише, щойно з'являються місця",
                   chips=["🎓 Іспити", "🚗 Транспорт", "💶 Штрафи", "🪪 Права"], cta="Безкоштовно · <i>@oksitabot</i>"),
        "ru": dict(h="Свободная дата в DGT?<br><b>Узнаешь первым</b>", sub="Бот проверяет сайт DGT и пишет, как только появляются места",
                   chips=["🎓 Экзамены", "🚗 Транспорт", "💶 Штрафы", "🪪 Права"], cta="Бесплатно · <i>@oksitabot</i>"),
    },
    "trial": {
        "uk": dict(h="<b>3 дні Premium</b><br>безкоштовно", sub="Один раз на людину. Без оплати і автопродовження",
                   chips=["⚡️ Перевірка першочергово", "🏢 До 10 офісів", "📡 Радар до 250 км", "📱 Міні-застосунок"], cta="Спробувати · <i>@oksitabot</i>"),
        "ru": dict(h="<b>3 дня Premium</b><br>бесплатно", sub="Один раз на человека. Без оплаты и автопродления",
                   chips=["⚡️ Проверка в первую очередь", "🏢 До 10 офисов", "📡 Радар до 250 км", "📱 Мини-приложение"], cta="Попробовать · <i>@oksitabot</i>"),
    },
    "radar": {
        "uk": dict(h="Немає дат у місті?<br><b>Подивись поруч</b>", sub="Офіси DGT у радіусі 100–250 км від тебе",
                   chips=["📍 100 км", "📍 150 км", "📍 250 км"], cta="Радар · <i>@oksitabot</i>"),
        "ru": dict(h="Нет дат в городе?<br><b>Посмотри рядом</b>", sub="Офисы DGT в радиусе 100–250 км от тебя",
                   chips=["📍 100 км", "📍 150 км", "📍 250 км"], cta="Радар · <i>@oksitabot</i>"),
    },
    "tips": {
        "uk": dict(h="<b>5 порад</b><br>для швидкої cita", sub="Збережи, щоб не загубити",
                   chips=[], cta="<i>@oksitabot</i>",
                   list=["Кілька офісів поруч", "Сповіщення увімкнені", "Фільтр «найближчі дні»", "Прийшло — заходь одразу", "Тисни «Я записався»"]),
        "ru": dict(h="<b>5 советов</b><br>для быстрой cita", sub="Сохрани, чтобы не потерять",
                   chips=[], cta="<i>@oksitabot</i>",
                   list=["Несколько офисов рядом", "Уведомления включены", "Фильтр «ближайшие дни»", "Пришло — заходи сразу", "Жми «Я записался»"]),
    },
    "docs": {
        "uk": dict(h="Запис на TIE?<br><b>Сигнали від людей</b>", sub="Хтось побачив вільний запис у твоїй провінції — тобі приходить сигнал",
                   chips=["🇺🇦 TIE", "🛂 Паспорт", "🏛 Консульство"], cta="Документи · <i>@oksitabot</i>",
                   sig=("🛂 TIE для українців · Málaga", "🟢 Є вільний запис · 3 хв тому")),
        "ru": dict(h="Запись на TIE?<br><b>Сигналы от людей</b>", sub="Кто-то увидел свободную запись в твоей провинции — тебе приходит сигнал",
                   chips=["🇺🇦 TIE", "🛂 Паспорт", "🏛 Консульство"], cta="Документы · <i>@oksitabot</i>",
                   sig=("🛂 TIE для украинцев · Málaga", "🟢 Есть свободная запись · 3 мин назад")),
    },
    "jobs": {
        "uk": dict(h="Вакансії<br><b>в Іспанії</b>", sub="Перша вакансія в каналі — безкоштовно",
                   chips=["💼 Робота", "🤝 Партнери", "🚫 Без продажу записів"], cta="<i>@oksita_news</i>", badge=("1-ша", "0 ⭐")),
        "ru": dict(h="Вакансии<br><b>в Испании</b>", sub="Первая вакансия в канале — бесплатно",
                   chips=["💼 Работа", "🤝 Партнёры", "🚫 Без продажи записей"], cta="<i>@oksita_news</i>", badge=("1-я", "0 ⭐")),
    },
    "friends": {
        "uk": dict(h="Premium<br><b>за завдання</b>", sub="+1 день за завдання і за кожного друга",
                   chips=["✅ Завдання +1 день", "👥 Друг +1 день", "🏷 Знижка −10%"], cta="Бонуси · <i>@oksitabot</i>", badge=("+1", "день")),
        "ru": dict(h="Premium<br><b>за задания</b>", sub="+1 день за задание и за каждого друга",
                   chips=["✅ Задание +1 день", "👥 Друг +1 день", "🏷 Скидка −10%"], cta="Бонусы · <i>@oksitabot</i>", badge=("+1", "день")),
    },
}

TEXT.update({
    "school": {
        "uk": dict(h="Автошколам —<br><b>код для учнів</b>", sub="7 днів Premium для учнів, QR і плакат для друку — безкоштовно",
                   chips=["🏫 До 100 учнів", "🖨 Плакат з QR", "📊 Видно, хто прийшов"], cta="Автошколам · <i>@oksitabot</i>", badge=("7", "днів")),
        "ru": dict(h="Автошколам —<br><b>код для учеников</b>", sub="7 дней Premium для учеников, QR и плакат для печати — бесплатно",
                   chips=["🏫 До 100 учеников", "🖨 Плакат с QR", "📊 Видно, кто пришёл"], cta="Автошколам · <i>@oksitabot</i>", badge=("7", "дней")),
    },
    "app": {
        "uk": dict(h="Оголошення<br><b>з телефона</b>", sub="Текст, фото і попередній перегляд — у міні-застосунку",
                   chips=["💼 Вакансія", "📣 Послуга", "📸 З фото"], cta="Подати · <i>@oksitabot</i>",
                   post=("💼 Вакансія", "Шукаємо кухаря в кафе в Малазі. Повний день, договір. Пишіть @cafe_malaga")),
        "ru": dict(h="Объявление<br><b>с телефона</b>", sub="Текст, фото и предпросмотр — в мини-приложении",
                   chips=["💼 Вакансия", "📣 Услуга", "📸 С фото"], cta="Подать · <i>@oksitabot</i>",
                   post=("💼 Вакансия", "Ищем повара в кафе в Малаге. Полный день, договор. Пишите @cafe_malaga")),
    },
})


def qr_svg(link: str, size: int) -> str:
    import io
    import segno
    out = io.BytesIO()
    segno.make(link, error="m").save(out, kind="svg", scale=8, border=0, dark="#16161d", xmldecl=False, svgns=True, omitsize=True)
    return out.getvalue().decode().replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)


NOTE = {  # уведомления на экране телефона: как их присылает бот
    "uk": ("зараз", "🔔 Є ВІЛЬНІ ДАТИ!", "🏢 Murcia · Exámenes<br>📅 3 дати · 12–14 листопада", "🏢 Alicante · Vehículos<br>📅 1 дата · 19 листопада",
           "понеділок, 3 листопада"),
    "ru": ("сейчас", "🔔 ЕСТЬ СВОБОДНЫЕ ДАТЫ!", "🏢 Murcia · Exámenes<br>📅 3 даты · 12–14 ноября", "🏢 Alicante · Vehículos<br>📅 1 дата · 19 ноября",
           "понедельник, 3 ноября"),
}
NEAR = [("🟢", "Cartagena", "07.11"), ("🟢", "Murcia", "12.11"), ("🟡", "Alicante", "21.11")]
RADAR_SMALL = RADAR.replace('width="440" height="440"', 'width="420" height="420"')


def art(kind: str, lang: str, t: dict) -> str:
    if kind == "hero":
        now, title, one, two, day = NOTE[lang]
        nf = lambda top, body: (f'<div class="nf" style="top:{top}px"><div class="top"><span class="ic">{LOGO}</span><span class="app">OkSita</span>'  # noqa: E731
                                f'<span>{now}</span></div><div class="t">{title}</div><div class="b">{body}</div></div>')
        return (f'<div class="phone"><div class="isl"></div><div class="day">{day}</div><div class="clock" style="top:96px">9:41</div>'
                + nf(250, one) + nf(420, two) + '</div>')
    if kind == "trial":
        return (f'<div style="position:absolute;left:40px;top:40px">{GEM}</div>'
                '<div class="badge" style="left:360px;top:300px;width:170px;height:170px;background:#fff;color:#3B1A8F;font-size:60px"><div>72<span style="font-size:34px"> h</span></div></div>')
    if kind == "radar":
        pills = "".join(f'<div class="pill" style="left:{30 + i * 14}px;top:{340 + i * 72}px;width:470px;height:64px;padding:0 22px;font-size:26px">'
                        f'<span>{dot}</span><span>{city}</span><span class="d">{when}</span></div>' for i, (dot, city, when) in enumerate(NEAR))
        return f'<div style="position:absolute;left:60px;top:0">{RADAR_SMALL}</div>{pills}'
    if kind == "tips":
        rows = "".join(f'<div class="row" style="font-size:28px;padding:15px 0;border-top:{"0" if i == 0 else "2px solid #EDEDF2"}">'
                       f'<span class="ok">{CHECK}</span><span>{item}</span></div>' for i, item in enumerate(t["list"]))
        return (f'<div class="card" style="left:40px;top:20px;width:480px;padding:18px 30px">{rows}</div>'
                '<div class="badge" style="left:420px;top:-10px;width:120px;height:120px;background:#FFD60A;color:#2B124C;font-size:64px">5</div>')
    if kind == "docs":
        a, b = t["sig"]
        return (f'<div style="position:absolute;left:60px;top:10px">{CARD}</div>'
                '<svg style="position:absolute;left:0;top:250px" width="560" height="330"><g fill="none" stroke="#FFD60A" stroke-opacity=".5" stroke-width="5">'
                '<ellipse cx="280" cy="170" rx="250" ry="120"/><ellipse cx="280" cy="170" rx="190" ry="88" stroke-opacity=".7"/></g></svg>'
                f'<div class="card" style="left:20px;top:340px;width:520px;padding:22px 26px"><div style="font-size:24px;font-weight:800">{a}</div>'
                f'<div style="font-size:22px;font-weight:600;margin-top:8px;color:#0B8A5A">{b}</div></div>')
    if kind == "jobs":
        top, bottom = t["badge"]
        return (f'<div style="position:absolute;left:60px;top:60px">{BRIEFCASE}</div>'
                f'<div class="badge" style="left:370px;top:20px;width:170px;height:170px;background:#FFB627;color:#1B1147;font-size:44px">'
                f'<div>{top}<div style="font-size:34px;margin-top:8px">{bottom}</div></div></div>')
    if kind == "friends":
        top, bottom = t["badge"]
        return (f'<div style="position:absolute;left:60px;top:40px">{GIFT}</div>'
                f'<div class="badge" style="left:380px;top:20px;width:170px;height:170px;background:#FFE34D;color:#047A62;font-size:64px">'
                f'<div>{top}<div style="font-size:30px;margin-top:6px">{bottom}</div></div></div>'
                '<div class="badge" style="left:20px;top:330px;width:140px;height:140px;background:#fff;color:#047A62;font-size:44px">−10%</div>')
    if kind == "school":
        top, bottom = t["badge"]
        return (f'<div class="card" style="left:70px;top:40px;width:380px;padding:30px;text-align:center">'
                f'{qr_svg("https://t.me/oksitabot?start=school-ch", 320)}'
                '<div style="font:800 26px ui-monospace,Menlo,monospace;letter-spacing:3px;margin-top:14px;color:#16161d">SOL482</div></div>'
                f'<div class="badge" style="left:400px;top:0;width:160px;height:160px;background:#FFE34D;color:#FF2D55;font-size:64px">'
                f'<div>{top}<div style="font-size:28px;margin-top:4px">{bottom}</div></div></div>')
    if kind == "app":
        label, text = t["post"]
        return (f'<div class="card" style="left:30px;top:30px;width:500px;padding:0;overflow:hidden">'
                '<div style="height:170px;background:linear-gradient(135deg,#FFB627,#FF6B2C);display:grid;place-items:center;font-size:84px">🍳</div>'
                f'<div style="padding:22px 26px"><div style="font-size:24px;font-weight:800;color:#16161d">{label}</div>'
                f'<div style="font-size:23px;line-height:1.35;margin-top:10px;color:#2a2a35">{text}</div>'
                '<div style="font-size:20px;margin-top:12px;color:#8a8a93;font-style:italic">📌 @oksitabot</div></div></div>'
                '<div class="badge" style="left:430px;top:0;width:130px;height:130px;background:#16C784;color:#fff;font-size:64px">✓</div>')
    return ""


def page(kind: str, lang: str, layout: str) -> str:
    bg, accent, cta = THEMES[kind]
    t = TEXT[kind][lang]
    chips = '<div class="chips">' + "".join(f'<span class="chip">{c}</span>' for c in t["chips"]) + "</div>"
    sub = f'<div class="sub">{t["sub"]}</div>' if t.get("sub") else ""
    return (f'<!doctype html><meta charset="utf-8"><style>{CSS}</style>'
            f'<div class="c {layout}" style="background:{bg};--accent:{accent};--cta:{cta}">{GLOW}{RINGS}'
            f'<div class="brand"><span class="logo">{LOGO}</span>OkSita</div>'
            f'<div class="txt"><div class="h">{t["h"]}</div>{sub}{chips if layout == "ls" else ""}</div>'
            f'{chips if layout == "sq" else ""}<div class="art">{art(kind, lang, t)}</div>'
            f'<div class="cta">{t["cta"]}</div></div>')


CHANNEL = {"post_how": "hero", "post_trial": "trial", "post_radar": "radar", "post_tips": "tips", "post_docs": "docs",
           "post_jobs": "jobs", "post_friends": "friends", "post_school": "school", "post_app": "app"}
PROMOS = ("hero", "trial", "radar", "docs", "tips", "jobs", "school", "app")


def main(only):
    pick = lambda kind: not only or kind in only  # noqa: E731
    for name, kind in CHANNEL.items():
        if pick(kind):
            shot(page(kind, "uk", "ls"), HERE / f"{name}.jpg", 1280, 720, 88)
    PROMO.mkdir(parents=True, exist_ok=True)
    for kind in PROMOS:
        for lang in ("uk", "ru"):
            if pick(kind):
                shot(page(kind, lang, "sq"), PROMO / f"{kind}_{lang}.jpg", 1080, 1080, 90)
    print("готово")


if __name__ == "__main__":
    main(sys.argv[1:])
