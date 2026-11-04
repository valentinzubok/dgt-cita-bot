"""Сайт бота для поиска в Google: главная на четырёх языках, страница каждого офиса DGT (по-испански), robots.txt и sitemap.xml.

Цифры (офисы, уведомления, записи, отзывы) берутся из памяти бота, страница собирается раз в 10 минут.
Базу сайт не трогает, поэтому Neon спокойно спит, даже когда страницу обходят поисковики."""
from __future__ import annotations

import html
import json
import re
import time
from typing import Dict, List, Optional, Tuple

import config
import dgt
import group
import premium
import radar
import reviews
import signals
import stats
import store
import views

TTL = 600
PATHS = {"es": "/", "uk": "/uk", "ru": "/ru", "en": "/en"}
_pages: Dict[str, Tuple[float, bytes]] = {}
minutes = lambda paid: 0  # noqa: E731 — подставляет webapp: реальная частота проверок

T = {
    "es": {
        "title": "Cita previa DGT: aviso en Telegram cuando haya citas libres · OkSita",
        "desc": "OkSita revisa la cita previa de la DGT en las 68 oficinas de Tráfico y te avisa en Telegram en cuanto aparecen "
                "fechas libres: examen práctico, vehículos, multas, permisos. Gratis y sin dar tu NIE.",
        "badge": "Las 68 oficinas de la DGT en España",
        "h1": "Te avisamos cuando haya <em>cita en la DGT</em>",
        "lead": "OkSita revisa la web de cita previa de Tráfico por ti y te escribe en Telegram en cuanto aparecen fechas libres. "
                "Tú solo entras y reservas.",
        "cta": "Abrir en Telegram", "cta2": "Canal con citas libres", "note": "Gratis · sin NIE ni contraseñas · 4 idiomas",
        "n_alert": "¡HAY FECHAS LIBRES!", "n_office": "Málaga · Examen práctico", "n_days": "9 días · 12 nov – 28 nov",
        "s_offices": "oficinas", "s_alerts": "avisos en 60 días", "s_booked": "personas ya tienen cita", "s_langs": "idiomas",
        "how": "Cómo funciona",
        "steps": [("Elige oficina", "Cualquiera de las 68 oficinas de Tráfico y el trámite: examen, vehículos, multas, permisos."),
                  ("OkSita vigila", "El bot revisa la web de la DGT por ti, con pausas para no saturarla."),
                  ("Recibe el aviso", "Te llega un mensaje con las fechas y horas libres. La cita la pides tú en sede.dgt.gob.es.")],
        "feat": "Todo para conseguir cita antes",
        "features": [("🔔", "Avisos al instante", "Fecha más cercana, horas libres y calendario de días."),
                     ("📡", "Radar", "¿Sin fechas en tu ciudad? Busca en oficinas a 100, 150 o 250 km."),
                     ("⏰", "Recordatorio", "La víspera y la mañana de la cita, con lo que debes llevar."),
                     ("📊", "Estadística", "Dónde y a qué hora aparecen más plazas en los últimos 30 días."),
                     ("🛂", "TIE, NIE y pasaporte", "Señales de la comunidad cuando alguien ve citas de extranjería, del pasaporte ucraniano o del consulado."),
                     ("🌍", "4 idiomas", "Español, ucraniano, ruso e inglés.")],
        "plans": "Gratis para empezar", "free": "Gratis", "prem": "Premium desde {p7} ⭐",
        "free_items": ["{fs} oficinas", "Revisión cada {fm} min", "1 radar al día"],
        "prem_items": ["{ps} oficinas", "Revisión cada {pm} min, primero en la cola", "Radar sin límite, hasta 250 km", "Mini app con calendario"],
        "plans_note": "Se paga con Telegram Stars. Premium acelera los avisos, pero no garantiza una cita.",
        "school": "¿Tienes una autoescuela?", "school_text": "Código gratis para tus alumnos: 7 días de Premium, enlace, QR y cartel para imprimir.",
        "school_btn": "Pedir código", "reviews": "Lo que dicen", "rating": "{avg} de 5 · {n} opiniones",
        "faq": "Preguntas frecuentes",
        "faqs": [("¿OkSita es de la DGT?", "No. Es un servicio independiente que te avisa. La cita la pides tú en la web oficial sede.dgt.gob.es."),
                 ("¿Tengo que dar mi NIE o una contraseña?", "No. El bot solo necesita la oficina y el trámite. Nunca pide documentos ni datos personales."),
                 ("¿Cuánto cuesta?", "El plan básico es gratis: {fs} oficinas con revisión cada {fm} minutos. Premium cuesta desde {p7} estrellas de Telegram "
                                     "y también se consigue gratis con bonos."),
                 ("¿Sirve para el examen práctico?", "Sí: examen teórico y práctico, vehículos, permisos, multas y el resto de trámites de cada oficina."),
                 ("¿Y el canje del permiso extranjero?", "Desde octubre de 2026 la DGT pide una solicitud previa con NIE para ver el calendario de canje. "
                                                         "El bot no introduce datos personales: te explica los pasos."),
                 ("¿Y la cita de extranjería (TIE, NIE)?", "Esa web tiene protección anti-bots, así que no la revisamos. En su lugar, la comunidad avisa "
                                                          "cuando ve citas en tu provincia.")],
        "foot": "OkSita no tiene relación con la DGT ni con ningún organismo público.", "chat": "Chat", "offices": "Oficinas de la DGT",
    },
    "uk": {
        "title": "Cita previa DGT: сповіщення в Telegram про вільні дати · OkSita",
        "desc": "OkSita перевіряє запис (cita previa) у DGT в усіх 68 офісах Іспанії і пише в Telegram, щойно з’являються вільні дати: "
                "іспит, транспорт, штрафи, права. Безкоштовно, без NIE.",
        "badge": "Усі 68 офісів DGT в Іспанії",
        "h1": "Напишемо, щойно з’явиться <em>запис у DGT</em>",
        "lead": "OkSita перевіряє сайт cita previa замість тебе і пише в Telegram, щойно з’являються вільні дати. "
                "Тобі лишається зайти й записатися.",
        "cta": "Відкрити в Telegram", "cta2": "Канал із вільними датами", "note": "Безкоштовно · без NIE і паролів · 4 мови",
        "n_alert": "Є ВІЛЬНІ ДАТИ!", "n_office": "Málaga · Іспит з водіння", "n_days": "9 днів · 12 лис – 28 лис",
        "s_offices": "офісів", "s_alerts": "сповіщень за 60 днів", "s_booked": "людей уже записалися", "s_langs": "мови",
        "how": "Як це працює",
        "steps": [("Обери офіс", "Будь-який із 68 офісів DGT і вид запису: іспит, транспорт, штрафи, права."),
                  ("OkSita стежить", "Бот перевіряє сайт DGT замість тебе, з паузами, щоб не перевантажувати його."),
                  ("Отримай сповіщення", "Приходить повідомлення з вільними датами й часом. Записуєшся ти сам на sede.dgt.gob.es.")],
        "feat": "Усе, щоб записатися швидше",
        "features": [("🔔", "Миттєві сповіщення", "Найближча дата, вільний час і календар днів."),
                     ("📡", "Радар", "У твоєму місті немає дат? Шукай в офісах за 100, 150 або 250 км."),
                     ("⏰", "Нагадування", "Напередодні та зранку в день візиту, зі списком документів."),
                     ("📊", "Статистика", "Де і о котрій частіше з’являються місця за 30 днів."),
                     ("🛂", "TIE, NIE і паспорт", "Сигнали від людей, коли хтось бачить записи до Extranjería, ДП «Документ» чи консульства."),
                     ("🌍", "4 мови", "Українська, російська, іспанська та англійська.")],
        "plans": "Почати можна безкоштовно", "free": "Безкоштовно", "prem": "Premium від {p7} ⭐",
        "free_items": ["{fs} офіси", "Перевірка кожні {fm} хв", "1 радар на день"],
        "prem_items": ["{ps} офісів", "Перевірка кожні {pm} хв, першим у черзі", "Радар без обмежень, до 250 км", "Міні-застосунок з календарем"],
        "plans_note": "Оплата зірками Telegram. Premium пришвидшує сповіщення, але не гарантує запис.",
        "school": "Маєте автошколу?", "school_text": "Безкоштовний код для учнів: 7 днів Premium, посилання, QR і плакат для друку.",
        "school_btn": "Отримати код", "reviews": "Що кажуть", "rating": "{avg} з 5 · відгуків: {n}",
        "faq": "Питання й відповіді",
        "faqs": [("OkSita — це сервіс DGT?", "Ні. Це незалежний сервіс сповіщень. Записуєшся ти сам на офіційному сайті sede.dgt.gob.es."),
                 ("Треба давати NIE або пароль?", "Ні. Боту потрібні лише офіс і вид запису. Документів і особистих даних він не просить."),
                 ("Скільки це коштує?", "Базовий тариф безкоштовний: {fs} офіси з перевіркою кожні {fm} хвилин. Premium — від {p7} зірок Telegram, "
                                        "його можна отримати й безкоштовно в «Бонусах»."),
                 ("Підходить для іспиту з водіння?", "Так: теорія й практика, транспорт, права, штрафи та інші послуги кожного офісу."),
                 ("А обмін прав (canje)?", "З жовтня 2026 DGT показує календар canje лише після заявки з NIE. Бот не вводить особисті дані, "
                                           "але пояснює порядок."),
                 ("А запис до Extranjería (TIE, NIE)?", "Той сайт захищений від ботів, тому ми його не перевіряємо. Натомість люди самі дають сигнал, "
                                                        "коли бачать записи у твоїй провінції.")],
        "foot": "OkSita не пов’язаний з DGT чи іншими державними органами.", "chat": "Чат", "offices": "Офіси DGT", "pas": "Черга ДП «Документ»",
    },
    "ru": {
        "title": "Cita previa DGT: уведомление в Telegram о свободных датах · OkSita",
        "desc": "OkSita проверяет запись (cita previa) в DGT во всех 68 офисах Испании и пишет в Telegram, как только появляются "
                "свободные даты: экзамен, транспорт, штрафы, права. Бесплатно, без NIE.",
        "badge": "Все 68 офисов DGT в Испании",
        "h1": "Напишем, как только появится <em>запись в DGT</em>",
        "lead": "OkSita проверяет сайт cita previa вместо тебя и пишет в Telegram, как только появляются свободные даты. "
                "Остаётся зайти и записаться.",
        "cta": "Открыть в Telegram", "cta2": "Канал со свободными датами", "note": "Бесплатно · без NIE и паролей · 4 языка",
        "n_alert": "ЕСТЬ СВОБОДНЫЕ ДАТЫ!", "n_office": "Málaga · Экзамен по вождению", "n_days": "9 дней · 12 ноя – 28 ноя",
        "s_offices": "офисов", "s_alerts": "уведомлений за 60 дней", "s_booked": "человек уже записались", "s_langs": "языка",
        "how": "Как это работает",
        "steps": [("Выбери офис", "Любой из 68 офисов DGT и вид записи: экзамен, транспорт, штрафы, права."),
                  ("OkSita следит", "Бот проверяет сайт DGT вместо тебя, с паузами, чтобы не перегружать его."),
                  ("Получи уведомление", "Приходит сообщение со свободными датами и временем. Записываешься ты сам на sede.dgt.gob.es.")],
        "feat": "Всё, чтобы записаться раньше",
        "features": [("🔔", "Мгновенные уведомления", "Ближайшая дата, свободное время и календарь дней."),
                     ("📡", "Радар", "В твоём городе нет дат? Ищи в офисах в 100, 150 или 250 км."),
                     ("⏰", "Напоминание", "Накануне и утром в день визита, со списком документов."),
                     ("📊", "Статистика", "Где и во сколько чаще появляются места за 30 дней."),
                     ("🛂", "TIE, NIE и паспорт", "Сигналы от людей, когда кто-то видит записи в Extranjería, ДП «Документ» или консульство."),
                     ("🌍", "4 языка", "Украинский, русский, испанский и английский.")],
        "plans": "Начать можно бесплатно", "free": "Бесплатно", "prem": "Premium от {p7} ⭐",
        "free_items": ["{fs} офиса", "Проверка каждые {fm} мин", "1 радар в день"],
        "prem_items": ["{ps} офисов", "Проверка каждые {pm} мин, первым в очереди", "Радар без ограничений, до 250 км", "Мини-приложение с календарём"],
        "plans_note": "Оплата звёздами Telegram. Premium ускоряет уведомления, но не гарантирует запись.",
        "school": "У вас автошкола?", "school_text": "Бесплатный код для учеников: 7 дней Premium, ссылка, QR и плакат для печати.",
        "school_btn": "Получить код", "reviews": "Что говорят", "rating": "{avg} из 5 · отзывов: {n}",
        "faq": "Вопросы и ответы",
        "faqs": [("OkSita — это сервис DGT?", "Нет. Это независимый сервис уведомлений. Записываешься ты сам на официальном сайте sede.dgt.gob.es."),
                 ("Нужно давать NIE или пароль?", "Нет. Боту нужны только офис и вид записи. Документы и личные данные он не просит."),
                 ("Сколько это стоит?", "Базовый тариф бесплатный: {fs} офиса с проверкой каждые {fm} минут. Premium — от {p7} звёзд Telegram, "
                                        "его можно получить и бесплатно в «Бонусах»."),
                 ("Подходит для экзамена по вождению?", "Да: теория и практика, транспорт, права, штрафы и другие услуги каждого офиса."),
                 ("А обмен прав (canje)?", "С октября 2026 DGT показывает календарь canje только после заявки с NIE. Бот не вводит личные данные, "
                                           "но объясняет порядок."),
                 ("А запись в Extranjería (TIE, NIE)?", "Тот сайт защищён от ботов, поэтому мы его не проверяем. Зато люди сами дают сигнал, "
                                                       "когда видят записи в твоей провинции.")],
        "foot": "OkSita не связан с DGT и другими государственными органами.", "chat": "Чат", "offices": "Офисы DGT", "pas": "Очередь ДП «Документ»",
    },
    "en": {
        "title": "DGT cita previa: Telegram alerts when appointments open · OkSita",
        "desc": "OkSita watches DGT appointments (cita previa) at all 68 traffic offices in Spain and messages you on Telegram as soon as "
                "free dates appear: driving test, vehicles, fines, licences. Free, no NIE needed.",
        "badge": "All 68 DGT offices in Spain",
        "h1": "We'll tell you when there's <em>a DGT appointment</em>",
        "lead": "OkSita checks the DGT booking website for you and messages you on Telegram as soon as free dates appear. "
                "You just go in and book.",
        "cta": "Open in Telegram", "cta2": "Channel with free dates", "note": "Free · no NIE or passwords · 4 languages",
        "n_alert": "FREE DATES AVAILABLE!", "n_office": "Málaga · Driving test", "n_days": "9 days · 12 Nov – 28 Nov",
        "s_offices": "offices", "s_alerts": "alerts in 60 days", "s_booked": "people already booked", "s_langs": "languages",
        "how": "How it works",
        "steps": [("Pick an office", "Any of the 68 DGT offices and the service: tests, vehicles, fines, licences."),
                  ("OkSita watches", "The bot checks the DGT website for you, with pauses so it doesn't overload it."),
                  ("Get the alert", "You get a message with free dates and times. You book on sede.dgt.gob.es yourself.")],
        "feat": "Everything to book sooner",
        "features": [("🔔", "Instant alerts", "Nearest date, free times and a day calendar."),
                     ("📡", "Radar", "No dates in your city? Search offices within 100, 150 or 250 km."),
                     ("⏰", "Reminders", "The evening before and the morning of your visit, with what to bring."),
                     ("📊", "Statistics", "Where and when slots appear most over the last 30 days."),
                     ("🛂", "TIE, NIE and passport", "Community signals when someone sees Extranjería, Ukrainian passport or consulate appointments."),
                     ("🌍", "4 languages", "Spanish, Ukrainian, Russian and English.")],
        "plans": "Free to start", "free": "Free", "prem": "Premium from {p7} ⭐",
        "free_items": ["{fs} offices", "Checked every {fm} min", "1 radar a day"],
        "prem_items": ["{ps} offices", "Checked every {pm} min, first in line", "Unlimited radar, up to 250 km", "Mini app with calendar"],
        "plans_note": "Paid with Telegram Stars. Premium speeds up alerts but doesn't guarantee an appointment.",
        "school": "Run a driving school?", "school_text": "A free code for your students: 7 days of Premium, a link, a QR and a printable poster.",
        "school_btn": "Get a code", "reviews": "What people say", "rating": "{avg} out of 5 · {n} reviews",
        "faq": "Questions and answers",
        "faqs": [("Is OkSita run by DGT?", "No. It's an independent alert service. You book on the official website sede.dgt.gob.es yourself."),
                 ("Do I need to give my NIE or a password?", "No. The bot only needs the office and the service. It never asks for documents or personal data."),
                 ("How much does it cost?", "The basic plan is free: {fs} offices checked every {fm} minutes. Premium starts at {p7} Telegram Stars "
                                            "and you can also earn it free with bonuses."),
                 ("Does it work for the driving test?", "Yes: theory and practical tests, vehicles, licences, fines and every other service each office offers."),
                 ("What about exchanging a foreign licence (canje)?", "Since October 2026 DGT only shows the canje calendar after an application "
                                                                     "with your NIE. The bot never enters personal data, but explains the steps."),
                 ("And Extranjería appointments (TIE, NIE)?", "That website is protected against bots, so we don't check it. Instead, the community "
                                                              "signals when they see appointments in your province.")],
        "foot": "OkSita is not affiliated with DGT or any public body.", "chat": "Chat", "offices": "DGT offices",
    },
}

CSS = """
:root{--bg:#fbfbfd;--card:#fff;--text:#16161d;--hint:#6b6b78;--line:rgba(22,22,40,.08);--brand:linear-gradient(120deg,#ff2d55,#ff5a36 55%,#ff9a2c);--ok:#0fb78a}
@media(prefers-color-scheme:dark){:root{--bg:#0d0d12;--card:#18181f;--text:#f4f4f8;--hint:#9a9aa8;--line:rgba(255,255,255,.08)}}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font:17px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
header{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 82%,transparent);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.bar{display:flex;align-items:center;gap:14px;height:60px}.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:19px;text-decoration:none;letter-spacing:-.3px}
.logo i{width:30px;height:30px;border-radius:9px;background:var(--brand);display:grid;place-items:center;color:#fff;font-style:normal;font-size:14px}.logo b{color:#ff5a36}
.langs{margin-left:auto;display:flex;gap:4px}.langs a{text-decoration:none;font-size:13px;font-weight:700;padding:6px 9px;border-radius:9px;color:var(--hint)}.langs a.on{background:var(--line);color:var(--text)}
.hero{display:grid;grid-template-columns:1.15fr .85fr;gap:48px;align-items:center;padding:64px 0 40px}.hero>*,.steps>*,.feats>*,.plans>*{min-width:0}
.badge{display:inline-flex;gap:8px;align-items:center;font-size:14px;font-weight:650;padding:7px 13px;border-radius:99px;background:var(--line)}
.badge:before{content:"";width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 4px rgba(15,183,138,.18)}
h1{overflow-wrap:break-word;font-size:clamp(34px,6vw,62px);line-height:1.02;letter-spacing:-2px;margin:18px 0 18px;font-weight:850}
h1 em{font-style:normal;background:var(--brand);-webkit-background-clip:text;background-clip:text;color:transparent}
.lead{font-size:20px;color:var(--hint);max-width:560px;margin:0}
.ctas{display:flex;flex-wrap:wrap;gap:12px;margin-top:28px}.btn{display:inline-flex;align-items:center;gap:10px;padding:15px 22px;border-radius:16px;font-weight:700;text-decoration:none;font-size:17px}
.btn.main{background:var(--brand);color:#fff;box-shadow:0 12px 30px rgba(255,61,70,.32)}.btn.alt{background:var(--card);box-shadow:0 0 0 1px var(--line)}
.note{margin-top:14px;font-size:14px;color:var(--hint)}
.phone{justify-self:center;width:300px;height:600px;border-radius:46px;padding:14px;background:#111;box-shadow:0 40px 80px rgba(22,22,40,.25),inset 0 0 0 2px #333;position:relative}
.screen{height:100%;border-radius:34px;background:linear-gradient(180deg,#1d2a44,#0e1424);overflow:hidden;padding:56px 14px 14px;position:relative}
.screen:before{content:"";position:absolute;top:12px;left:50%;width:96px;height:26px;margin-left:-48px;border-radius:20px;background:#000}
.clock{color:#fff;text-align:center;font-size:58px;font-weight:300;letter-spacing:-1px}.date{color:rgba(255,255,255,.7);text-align:center;font-size:14px;margin-bottom:26px}
.notif{background:rgba(255,255,255,.92);color:#16161d;border-radius:20px;padding:12px 14px;font-size:13.5px;line-height:1.4;animation:drop .9s .2s backwards cubic-bezier(.2,.9,.3,1.2)}
.notif+.notif{margin-top:10px;opacity:.75;animation-delay:.7s}.notif .top{display:flex;align-items:center;gap:8px;font-size:12px;color:#6b6b78;margin-bottom:4px}
.notif .top i{width:20px;height:20px;border-radius:6px;background:var(--brand);font-style:normal;color:#fff;display:grid;place-items:center;font-size:10px;font-weight:800}
.notif b{display:block}@keyframes drop{from{opacity:0;transform:translateY(-30px) scale(.96)}to{opacity:1;transform:none}}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:20px 0 10px}.stat{background:var(--card);border-radius:20px;padding:18px;box-shadow:0 0 0 1px var(--line)}
.stat b{display:block;font-size:30px;letter-spacing:-1px}.stat span{color:var(--hint);font-size:14px}
section.block{padding:56px 0 8px}h2{font-size:clamp(28px,4vw,40px);letter-spacing:-1px;line-height:1.1;margin:0 0 24px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.step{background:var(--card);border-radius:24px;padding:24px;box-shadow:0 0 0 1px var(--line)}
.step i{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;background:var(--text);color:var(--bg);font-style:normal;font-weight:800;margin-bottom:14px}
.step h3,.feat h3{margin:0 0 6px;font-size:19px}.step p,.feat p{margin:0;color:var(--hint);font-size:15.5px}
.feats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.feat{padding:22px;border-radius:24px;background:var(--card);box-shadow:0 0 0 1px var(--line)}
.feat span{font-size:28px;display:block;margin-bottom:10px}
.plans{display:grid;grid-template-columns:1fr 1fr;gap:16px}.plan{border-radius:26px;padding:26px;background:var(--card);box-shadow:0 0 0 1px var(--line)}
.plan.top{background:linear-gradient(135deg,#1a0f3a,#3b1a8f 60%,#d61c8e);color:#fff;box-shadow:none}.plan h3{margin:0 0 14px;font-size:24px}
.plan ul{margin:0;padding:0;list-style:none}.plan li{padding:7px 0 7px 28px;position:relative}.plan li:before{content:"✓";position:absolute;left:0;font-weight:800;color:var(--ok)}
.plan.top li:before{color:#ffd60a}.small{font-size:14px;color:var(--hint);margin-top:14px}
.school{display:flex;gap:24px;align-items:center;justify-content:space-between;border-radius:28px;padding:30px;background:var(--brand);color:#fff;margin-top:56px}
.school h2{margin:0 0 8px;font-size:30px}.school p{margin:0;opacity:.95}.school .btn{background:#fff;color:#16161d;flex:none}
.reviews{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.review{background:var(--card);border-radius:22px;padding:20px;box-shadow:0 0 0 1px var(--line)}
.review p{margin:8px 0;font-size:15.5px}.review small{color:var(--hint)}.rating{color:var(--hint);margin:-14px 0 20px}
details{background:var(--card);border-radius:18px;padding:18px 20px;box-shadow:0 0 0 1px var(--line);margin-bottom:10px}
summary{font-weight:700;cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:12px}summary:after{content:"+";font-size:22px;line-height:1;color:var(--hint)}
details[open] summary:after{content:"−"}details p{margin:10px 0 0;color:var(--hint)}
footer{padding:56px 0 40px;color:var(--hint);font-size:14px}footer nav{display:flex;flex-wrap:wrap;gap:18px;margin-bottom:12px}footer a{font-weight:650;text-decoration:none;color:var(--text)}
.list{columns:3 220px;gap:24px;margin:0;padding:0;list-style:none}.list li{break-inside:avoid;padding:5px 0}.list a{font-weight:600;text-decoration:none}
.list small,.crumbs{color:var(--hint);font-size:14px}.crumbs{margin:22px 0 -40px}.crumbs a{text-decoration:none}
@media(max-width:860px){.hero{grid-template-columns:1fr;padding-top:36px}.phone{display:none}.stats{grid-template-columns:repeat(2,1fr)}h1{letter-spacing:-1px}
.steps,.feats,.reviews{grid-template-columns:1fr}.plans{grid-template-columns:1fr}.school{flex-direction:column;align-items:flex-start}}
@media(prefers-reduced-motion:reduce){.notif{animation:none}}
"""


def esc(s: object) -> str:
    return html.escape(str(s))


def round_down(n: int) -> str:
    """«1234» → «1200+»: честно и не пляшет от каждого нового человека."""
    if n < 20:
        return str(n)
    step = 10 if n < 200 else 100 if n < 2000 else 1000
    return f"{n // step * step}+"


def numbers() -> dict:
    return {"fs": store.setting("free_subs"), "ps": store.setting("max_subs"), "fm": minutes(False), "pm": minutes(True),
            "p7": premium.plan_price("p7")}


def gsc_meta() -> str:
    code = store.setting("gsc")
    return f'<meta name="google-site-verification" content="{esc(code)}">' if code else ""


def bot(start: str) -> str:
    return f"https://t.me/{config.BOT_USERNAME}?start={start}"


def channel() -> str:
    return f"https://t.me/{str(store.setting('channel') or '').lstrip('@')}"


def render(lang: str) -> str:
    t, n = T[lang], numbers()
    base = config.PUBLIC_URL or ""
    fmt = lambda s: s.format(**n)  # noqa: E731
    offices, alerts, booked = len(dgt.CENTROS), store.metric_total("alerts"), store.metric_total("bookings")
    stats = [(str(offices), t["s_offices"])] + ([(round_down(alerts), t["s_alerts"])] if alerts >= 20 else []) \
        + ([(round_down(booked), t["s_booked"])] if booked >= 10 else []) + [("4", t["s_langs"])]
    avg, count = reviews.summary()
    shown = reviews.public(6)
    alt = "".join(f'<link rel="alternate" hreflang="{code}" href="{base}{path}">' for code, path in PATHS.items())
    langs = "".join(f'<a href="{path}" class="{"on" if code == lang else ""}" hreflang="{code}">{code.upper()}</a>' for code, path in PATHS.items())
    app = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "OkSita", "applicationCategory": "UtilitiesApplication",
           "operatingSystem": "Telegram", "url": base + PATHS[lang], "description": t["desc"], "inLanguage": lang,
           "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"}}
    if count >= 5:
        app["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": avg, "ratingCount": count, "bestRating": 5, "worstRating": 1}
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": fmt(a)}} for q, a in t["faqs"]]}
    review_block = ""
    if shown:
        cards = "".join(f'<div class="review"><div>{"⭐" * r["stars"]}</div><p>«{esc(r["text"])}»</p><small>📍 {esc(reviews.place(r))}</small></div>'
                        for r in shown)
        rating = f'<p class="rating">{esc(t["rating"].format(avg=avg, n=count))}</p>' if count >= reviews.PUBLIC_MIN else ""
        review_block = f'<section class="block"><h2>{esc(t["reviews"])}</h2>{rating}<div class="reviews">{cards}</div></section>'
    start = f"web-{lang}"
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(t['title'])}</title>
<meta name="description" content="{esc(t['desc'])}"><link rel="canonical" href="{base}{PATHS[lang]}">{alt}{gsc_meta()}
<link rel="alternate" hreflang="x-default" href="{base}/"><meta name="theme-color" content="#ff5a36">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(t['title'])}"><meta property="og:description" content="{esc(t['desc'])}">
<meta property="og:url" content="{base}{PATHS[lang]}"><meta property="og:image" content="{base}/static/cover.png"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/app/icon.png"><style>{CSS}</style>
<script type="application/ld+json">{json.dumps(app, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(faq, ensure_ascii=False)}</script></head><body>
<header><div class="wrap bar"><a class="logo" href="{PATHS[lang]}"><i>Ok</i><span><b>Ok</b>Sita</span></a><nav class="langs">{langs}</nav></div></header>
<main class="wrap">
<section class="hero"><div><span class="badge">{esc(t['badge'])}</span><h1>{t['h1']}</h1><p class="lead">{esc(t['lead'])}</p>
<div class="ctas"><a class="btn main" href="{bot(start)}">✈️ {esc(t['cta'])}</a><a class="btn alt" href="{channel()}">📢 {esc(t['cta2'])}</a></div>
<p class="note">{esc(t['note'])}</p></div>
<div class="phone" aria-hidden="true"><div class="screen"><div class="clock">9:41</div><div class="date">OkSita</div>
<div class="notif"><div class="top"><i>Ok</i>OkSita · now</div><b>🔔 {esc(t['n_alert'])}</b>🏢 {esc(t['n_office'])}<br>📅 {esc(t['n_days'])}<br>⏰ 09:30 · 10:15 · 11:00</div>
<div class="notif"><div class="top"><i>Ok</i>OkSita</div><b>⏰ DGT · 10:15</b>📋 DNI/NIE · tasa 2.3</div></div></div></section>
<div class="stats">{''.join(f'<div class="stat"><b>{esc(v)}</b><span>{esc(k)}</span></div>' for v, k in stats)}</div>
<section class="block" id="how"><h2>{esc(t['how'])}</h2><div class="steps">{''.join(f'<div class="step"><i>{i}</i><h3>{esc(a)}</h3><p>{esc(b)}</p></div>' for i, (a, b) in enumerate(t['steps'], 1))}</div></section>
<section class="block"><h2>{esc(t['feat'])}</h2><div class="feats">{''.join(f'<div class="feat"><span>{e}</span><h3>{esc(a)}</h3><p>{esc(b)}</p></div>' for e, a, b in t['features'])}</div></section>
<section class="block"><h2>{esc(t['plans'])}</h2><div class="plans">
<div class="plan"><h3>{esc(t['free'])}</h3><ul>{''.join(f'<li>{esc(fmt(x))}</li>' for x in t['free_items'])}</ul></div>
<div class="plan top"><h3>{esc(fmt(t['prem']))}</h3><ul>{''.join(f'<li>{esc(fmt(x))}</li>' for x in t['prem_items'])}</ul></div></div>
<p class="small">{esc(t['plans_note'])}</p></section>
{review_block}
<div class="school"><div><h2>🏫 {esc(t['school'])}</h2><p>{esc(t['school_text'])}</p></div><a class="btn" href="{bot('school-web')}">{esc(t['school_btn'])}</a></div>
<section class="block" id="faq"><h2>{esc(t['faq'])}</h2>{''.join(f'<details><summary>{esc(q)}</summary><p>{esc(fmt(a))}</p></details>' for q, a in t['faqs'])}</section>
</main><footer class="wrap"><nav><a href="{bot(start)}">Telegram</a><a href="/dgt">🏢 {esc(t['offices'])}</a>{'<a href="/pasport">🛂 ' + esc(t['pas']) + '</a>' if t.get('pas') else ''}<a href="{channel()}">📢 {esc(store.setting('channel'))}</a>{chat_link(t)}</nav>
<p>{esc(t['foot'])} © {time.strftime('%Y')} OkSita</p></footer></body></html>"""


def chat_link(t: dict) -> str:
    link = group.link()
    return f'<a href="{esc(link)}">💬 {esc(t["chat"])}</a>' if link else ""


# ---------- страницы офисов: «cita previa DGT Málaga» ----------

def slug(cid: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", views.fold(views.city(cid))).strip("-")


def slugs() -> Dict[str, str]:
    """Адрес страницы → офис. Список офисов бот обновляет с сайта DGT, поэтому считаем каждый раз."""
    return {slug(cid): cid for cid in dgt.CENTROS}


NAV = {"es": ("/", "Inicio", "Oficinas", "Todas las oficinas", '<a href="/uk">UK</a><a href="/ru">RU</a>'),
       "uk": ("/uk", "Головна", "Офіси DGT", "Усі офіси DGT", '<a href="/pasport">Паспорт</a>')}


def shell(title: str, desc: str, path: str, body: str, ld: List[dict], lang: str = "es") -> str:
    base = config.PUBLIC_URL or ""
    home, home_label, short, offices, extra = NAV[lang]
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in ld)
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}"><link rel="canonical" href="{base}{path}"><meta name="theme-color" content="#ff5a36">{gsc_meta()}
<meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{base}{path}"><meta property="og:image" content="{base}/static/cover.png"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/app/icon.png"><style>{CSS}</style>{scripts}</head><body>
<header><div class="wrap bar"><a class="logo" href="{home}"><i>Ok</i><span><b>Ok</b>Sita</span></a><nav class="langs"><a href="/dgt">{short}</a>{extra}</nav></div></header>
<main class="wrap">{body}</main><footer class="wrap"><nav><a href="{home}">{home_label}</a><a href="/dgt">🏢 {offices}</a><a href="{bot('web-' + lang)}">Telegram</a>{chat_link(T[lang])}</nav>
<p>{esc(T[lang]['foot'])} © {time.strftime('%Y')} OkSita</p></footer></body></html>"""


def office_page(cid: str) -> str:
    t, city, name = T["es"], views.city(cid), dgt.CENTROS[cid]
    seen = [g for g in stats.offices() if g["centro"] == cid]
    total = sum(g["opens"] for g in seen)
    rows = "".join(f'<div class="feat"><span>📅</span><h3>{esc(views.area_label(g["area"]))}</h3><p>{g["opens"]} '
                   f'{"vez" if g["opens"] == 1 else "veces"} en 30 días · sobre todo hacia las {g["best"]}:00'
                   + (f' · duran unos {esc(views.fmt_dur(g["avg"], "es"))}' if g["avg"] else "") + "</p></div>" for g in seen[:6])
    history = (f'<div class="feats">{rows}</div><p class="small">Hora de Madrid. Solo contamos los trámites que siguen los usuarios del bot.</p>' if seen else
               '<p class="lead">Aún no hay datos de esta oficina en los últimos 30 días. Las estadísticas aparecen en cuanto alguien la sigue con el bot.</p>')
    cached = store.office_areas(cid)
    areas = "".join(f"<li>{esc(views.area_label(code, label))}</li>" for code, label in (cached[1] if cached else []))
    near = [(c, km) for c, km in radar.nearest(cid, 150) if c != cid][:6] if cid in radar.COORDS else []
    near_html = "".join(f'<li><a href="/dgt/{slug(c)}">{esc(views.city(c))}</a> <small>· {km} km</small></li>' for c, km in near)
    when = (f"En los últimos 30 días hubo plazas libres {total} {'vez' if total == 1 else 'veces'}, sobre todo hacia las "
            f"{max(seen, key=lambda g: g['opens'])['best']}:00 (hora de Madrid)." if seen else
            "Las plazas salen cuando alguien anula su cita o la oficina abre días nuevos: no hay una hora fija.")
    faqs = [(f"¿Cómo pido cita en la DGT de {city}?", "En la web oficial sede.dgt.gob.es, en la app miDGT o llamando al 060. "
                                                       "Si no hay fechas, activa el aviso de OkSita: te escribe en Telegram cuando se liberan."),
            (f"¿Cuándo salen citas en {city}?", when),
            t["faqs"][0], t["faqs"][1]]
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a.format(**numbers())}} for q, a in faqs]}
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "OkSita", "item": f"{config.PUBLIC_URL}/"},
        {"@type": "ListItem", "position": 2, "name": "Oficinas de la DGT", "item": f"{config.PUBLIC_URL}/dgt"},
        {"@type": "ListItem", "position": 3, "name": city, "item": f"{config.PUBLIC_URL}/dgt/{slug(cid)}"}]}
    body = f"""<p class="crumbs"><a href="/dgt">Oficinas de la DGT</a> › {esc(city)}</p>
<section class="hero" style="grid-template-columns:1fr"><div><span class="badge">{esc(name)}</span><h1>Cita previa DGT en <em>{esc(city)}</em></h1>
<p class="lead">OkSita revisa la web de cita previa de esta oficina por ti y te escribe en Telegram en cuanto aparecen fechas libres. Tú solo entras y reservas en sede.dgt.gob.es.</p>
<div class="ctas"><a class="btn main" href="{bot('of_' + cid)}">✈️ Avisarme de citas en {esc(city)}</a><a class="btn alt" href="{channel()}">📢 {esc(t['cta2'])}</a></div>
<p class="note">{esc(t['note'])}</p></div></section>
<section class="block"><h2>Citas libres en {esc(city)}, últimos 30 días</h2>{history}</section>
{f'<section class="block"><h2>Trámites con cita en esta oficina</h2><ul class="list">{areas}</ul></section>' if areas else ''}
{f'<section class="block"><h2>Oficinas cercanas</h2><p class="small" style="margin:-12px 0 18px">Si en {esc(city)} no hay fechas, el radar del bot busca también en estas.</p><ul class="list">{near_html}</ul></section>' if near_html else ''}
<section class="block"><h2>{esc(t['how'])}</h2><div class="steps">{''.join(f'<div class="step"><i>{i}</i><h3>{esc(a)}</h3><p>{esc(b)}</p></div>' for i, (a, b) in enumerate(t['steps'], 1))}</div></section>
<section class="block"><h2>{esc(t['faq'])}</h2>{''.join(f'<details><summary>{esc(q)}</summary><p>{esc(a.format(**numbers()))}</p></details>' for q, a in faqs)}</section>"""
    return shell(f"Cita previa DGT {city}: aviso de citas libres · OkSita",
                 f"Aviso en Telegram cuando hay cita previa libre en la {name}: examen, vehículos, permisos y más. Gratis y sin dar tu NIE.",
                 f"/dgt/{slug(cid)}", body, [faq_ld, crumbs])


def offices_page() -> str:
    links = "".join(f'<li><a href="/dgt/{s_}">{esc(views.city(cid))}</a></li>'
                    for s_, cid in sorted(slugs().items(), key=lambda x: views.fold(views.city(x[1]))))
    body = f"""<section class="hero" style="grid-template-columns:1fr"><div><span class="badge">{len(dgt.CENTROS)} oficinas</span>
<h1>Cita previa DGT: <em>todas las oficinas</em></h1><p class="lead">Elige tu Jefatura u Oficina de Tráfico para ver cuándo salen citas y activar el aviso en Telegram.</p></div></section>
<section class="block" style="padding-top:8px"><ul class="list">{links}</ul></section>"""
    return shell("Cita previa DGT en todas las oficinas de Tráfico · OkSita",
                 "Las 68 Jefaturas y Oficinas de Tráfico: cuándo salen citas libres en cada una y aviso gratis en Telegram.", "/dgt", body, [])


# ---------- паспорт Украины: «черга ДП Документ Мадрид» ----------

PASSPORT_ADDR = {"28": "Blvr. de José Prat, 35 (Vicálvaro)", "08": "Av. del Segle XXI, 6 (Viladecans)", "46": "Av. de Pius XII, 2, local 117"}
PASSPORT_CITY = {"28": "Мадрид", "08": "Барселона", "46": "Валенсія"}


def passport_page() -> str:
    cards = "".join(f'<div class="feat"><span>🛂</span><h3>{PASSPORT_CITY[p]}</h3><p>{esc(PASSPORT_ADDR[p])}<br>'
                    f'<a href="{esc(link)}" rel="nofollow">Електронна черга ↗</a></p></div>' for p, (_, link) in signals.PASSPORT.items())
    faqs = [("Коли з’являються талони?", "У випадковий час: так вирішив сам Паспортний сервіс, щоб талони не перепродували. "
                                          "Однієї години немає, тому допомагають сигнали від тих, хто теж чекає."),
            ("Чи можна прийти без запису?", "Зазвичай без запису приймають людей з інвалідністю, вагітних, літніх і опікуна з дитиною до 3 років. "
                                            "Точні правила дивись на сторінці свого центру."),
            ("Що потрібно для запису?", "Сайт черги може попросити Дія.Підпис або BankID, а код підтвердження приходить SMS або у Viber. "
                                        "Приходь за 10 хвилин і показуй оригінальне підтвердження: скриншоти не приймають."),
            ("Чому бот сам не перевіряє сайт?", "Сайт черги закритий від автоматичних перевірок. Обходити захист ми не будемо, "
                                                "тому талони помічають люди: один натиснув «бачу талони» — інші одразу отримали сигнал."),
            ("Скільки це коштує?", f"Сигнали безкоштовні: {signals.FREE_SUBS} центр без оплати, з Premium — до {signals.TOP_SUBS} сигналів. "
                                   "Сам запис теж безкоштовний: нікому не плати за талон."),
            ("Як записатися до консульства?", "Посольство в Мадриді й генконсульство в Барселоні приймають лише через е-Консул. "
                                              "Якщо вільного часу немає, стань у лист очікування в е-Консулі: система надішле email, коли з’явиться місце.")]
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}
    body = f"""<section class="hero" style="grid-template-columns:1fr"><div><span class="badge">Мадрид · Барселона · Валенсія</span>
<h1>Черга <em>ДП «Документ»</em> в Іспанії</h1>
<p class="lead">Талони в Паспортний сервіс з’являються у випадковий час і швидко зникають. В OkSita ті, хто чекає, діляться сигналом: один побачив талони — інші одразу отримують повідомлення в Telegram.</p>
<div class="ctas"><a class="btn main" href="{bot('passport-web')}">✈️ Отримувати сигнали</a><a class="btn alt" href="{channel()}">📢 Канал OkSita</a></div>
<p class="note">Безкоштовно · бот не просить паспортні дані · запис лише на офіційному сайті</p></div></section>
<section class="block"><h2>Три центри в Іспанії</h2><div class="feats">{cards}</div>
<p class="small">Дані на листопад 2026. Адресу й вихідні перевіряй на сторінці центру перед візитом.</p></section>
<section class="block"><h2>Як працюють сигнали</h2><div class="steps">
<div class="step"><i>1</i><h3>Обери центр</h3><p>У боті: 🇺🇦 Для українців → 🛂 Паспорт України → 🔔 біля свого міста.</p></div>
<div class="step"><i>2</i><h3>Хтось бачить талони</h3><p>Людина на сайті черги бачить вільні місця й натискає «🟢 Я бачу талони».</p></div>
<div class="step"><i>3</i><h3>Ти отримуєш сигнал</h3><p>Одразу приходить повідомлення з кнопкою на офіційну чергу твого центру.</p></div></div></section>
<section class="block"><h2>Питання</h2>{''.join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faqs)}</section>"""
    return shell("Черга ДП «Документ» в Іспанії: Мадрид, Барселона, Валенсія · OkSita",
                 "Як записатися в Паспортний сервіс ДП «Документ» у Мадриді, Барселоні та Валенсії і отримувати в Telegram сигнал, "
                 "коли люди бачать вільні талони. Безкоштовно.", "/pasport", body, [faq_ld], "uk")


def page(path: str) -> Optional[Tuple[bytes, str]]:
    """Готовая страница по адресу или None. Собираем раз в 10 минут."""
    lang = next((code for code, p in PATHS.items() if p == path), None)
    if path in ("/dgt", "/pasport") or path.startswith("/dgt/"):
        cid = slugs().get(path[5:]) if path.startswith("/dgt/") else None
        if path.startswith("/dgt/") and not cid:
            return None
        hit = _pages.get(path)  # страницы офисов и паспорта лежат в кэше по своему адресу
        if not hit or time.time() - hit[0] > TTL:
            build = office_page(cid) if cid else offices_page() if path == "/dgt" else passport_page()
            hit = (time.time(), build.encode())
            _pages[path] = hit
        return hit[1], "text/html; charset=utf-8"
    if path == "/robots.txt":
        return f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /app\nSitemap: {config.PUBLIC_URL}/sitemap.xml\n".encode(), "text/plain; charset=utf-8"
    if path == "/sitemap.xml":
        urls = "".join(f"<url><loc>{config.PUBLIC_URL}{p}</loc>"
                       + "".join(f'<xhtml:link rel="alternate" hreflang="{c}" href="{config.PUBLIC_URL}{q}"/>' for c, q in PATHS.items())
                       + "</url>" for p in PATHS.values())
        urls += "".join(f"<url><loc>{config.PUBLIC_URL}{p}</loc></url>" for p in ["/dgt", "/pasport"] + [f"/dgt/{x}" for x in sorted(slugs())])
        return (f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{urls}</urlset>').encode(), "application/xml; charset=utf-8"
    if not lang:
        return None
    hit = _pages.get(lang)
    if not hit or time.time() - hit[0] > TTL:
        hit = (time.time(), render(lang).encode())
        _pages[lang] = hit
    return hit[1], "text/html; charset=utf-8"
