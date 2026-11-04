"""Сигналы о записях на документы: Extranjería, паспорт, консульство, padrón, Seguridad Social, SEPE.
Эти сайты закрыты капчей и антибот-защитой, бот их не проверяет. Места замечают сами пользователи и нажимают кнопку.
Текста от людей здесь нет: сигнал — это только провинция и тип документа, поэтому через него не разослать мошенническую ссылку."""
from __future__ import annotations

import time
from collections import Counter
from typing import List, Optional, Tuple

import config
import premium
import store

ICP_URL = "https://icp.administracionelectronica.gob.es/icpplus/index.html"
FREE_SUBS, TOP_SUBS = 1, 5
WINDOW = 30 * 60      # повторный сигнал за это время — подтверждение первого, а не новая рассылка
DAILY = 5             # сигналов от одного человека в сутки
BAD_LIMIT = 3         # столько опровергнутых сигналов за 30 дней — больше не принимаем
WINDOWS = (1, 8, 12, 15, 19, 23)  # часы, в которые можно попросить напоминание проверить сайт самому
FREE_WINDOWS, TOP_WINDOWS = 1, 4
DAY = 86400

PROVINCES = {
    "01": "Álava", "02": "Albacete", "03": "Alicante", "04": "Almería", "05": "Ávila", "06": "Badajoz", "07": "Illes Balears",
    "08": "Barcelona", "09": "Burgos", "10": "Cáceres", "11": "Cádiz", "12": "Castellón", "13": "Ciudad Real", "14": "Córdoba",
    "15": "A Coruña", "16": "Cuenca", "17": "Girona", "18": "Granada", "19": "Guadalajara", "20": "Gipuzkoa", "21": "Huelva",
    "22": "Huesca", "23": "Jaén", "24": "León", "25": "Lleida", "26": "La Rioja", "27": "Lugo", "28": "Madrid", "29": "Málaga",
    "30": "Murcia", "31": "Navarra", "32": "Ourense", "33": "Asturias", "34": "Palencia", "35": "Las Palmas", "36": "Pontevedra",
    "37": "Salamanca", "38": "Santa Cruz de Tenerife", "39": "Cantabria", "40": "Segovia", "41": "Sevilla", "42": "Soria",
    "43": "Tarragona", "44": "Teruel", "45": "Toledo", "46": "Valencia", "47": "Valladolid", "48": "Bizkaia", "49": "Zamora",
    "50": "Zaragoza", "51": "Ceuta", "52": "Melilla",
}
DOCS = {
    "ukr": ("🇺🇦", "TIE для украинцев", "TIE для українців", "TIE para ucranianos", "TIE for Ukrainians"),
    "tie": ("🖐", "TIE: отпечатки", "TIE: відбитки", "TIE: huellas", "TIE: fingerprints"),
    "rec": ("📥", "Получение TIE", "Отримання TIE", "Recogida de TIE", "TIE collection"),
    "nie": ("🔢", "NIE и сертификаты", "NIE і сертифікати", "NIE y certificados", "NIE and certificates"),
    "asy": ("🛡", "Убежище", "Притулок", "Asilo", "Asylum"),
    "ext": ("📄", "Другое в Extranjería", "Інше в Extranjería", "Otros en Extranjería", "Other at Extranjería"),
    "pas": ("🛂", "Паспорт Украины", "Паспорт України", "Pasaporte de Ucrania", "Ukrainian passport"),
    "con": ("🏛", "Консульство Украины", "Консульство України", "Consulado de Ucrania", "Ukrainian consulate"),
    "pad": ("🏠", "Прописка (padrón)", "Прописка (padrón)", "Empadronamiento", "Padrón registration"),
    "ss": ("🏥", "Seguridad Social", "Seguridad Social", "Seguridad Social", "Social Security"),
    "sep": ("💼", "SEPE: пособие и работа", "SEPE: допомога й робота", "SEPE: paro y empleo", "SEPE: benefits and jobs"),
}
ICP_DOCS = ("ukr", "tie", "rec", "nie", "asy", "ext")  # записываются на сайте Extranjería
# Паспортний сервіс ДП «Документ» в Испании: провинция → (город, страница очереди). Сайт закрыт Cloudflare от ботов, бот его не открывает
PASSPORT = {
    "28": ("Madrid", "https://madrid.pasport.org.ua/solutions/e-queue"),
    "08": ("Barcelona", "https://barcelona.pasport.org.ua/solutions/e-queue"),
    "46": ("València", "https://valencia.pasport.org.ua/solutions/e-queue"),
}
CONSULATES = {"28": "Madrid", "08": "Barcelona"}  # посольство и генконсульство, запись только через е-Консул
CONSUL_URL = "https://e-consul.gov.ua/"
OTHER_URLS = {  # официальные страницы записи; у padrón своя в каждом городе, поэтому ссылки нет
    "ss": "https://sede.seg-social.gob.es/wps/portal/sede/sede/Ciudadanos/CitaPrevia",
    "sep": "https://sede.sepe.gob.es/portalSede/procedimientos-y-servicios/personas/proteccion-por-desempleo/cita-previa",
}


def valid(province: str, doc: str) -> bool:
    if province not in PROVINCES or doc not in DOCS:
        return False
    return province in PASSPORT if doc == "pas" else province in CONSULATES if doc == "con" else True


def booking_url(province: str, doc: str) -> Optional[str]:
    """Официальный сайт записи для сигнала."""
    if doc in ICP_DOCS:
        return ICP_URL
    if doc == "pas":
        return PASSPORT[province][1] if province in PASSPORT else None
    return CONSUL_URL if doc == "con" else OTHER_URLS.get(doc)


def places(doc: str) -> dict:
    """Где вообще бывает запись: паспорт и консульство — только в своих городах."""
    if doc == "pas":
        return {p: city for p, (city, _) in PASSPORT.items()}
    return CONSULATES if doc == "con" else {p: name for p, name in PROVINCES.items()}


def limit(chat: int) -> int:
    return TOP_SUBS if premium.is_premium(chat) else FREE_SUBS


def window_limit(chat: int) -> int:
    return TOP_WINDOWS if premium.is_premium(chat) else FREE_WINDOWS


def windows_of(chat: int) -> List[int]:
    raw = store.get_chat(chat).get("windows") or ""
    return [int(h) for h in raw.split(",") if h.isdigit() and int(h) in WINDOWS]


def toggle_window(chat: int, hour: int) -> str:
    """Статус: ok | limit | bad."""
    if hour not in WINDOWS:
        return "bad"
    mine = windows_of(chat)
    if hour in mine:
        mine.remove(hour)
    elif len(mine) >= window_limit(chat):
        return "limit"
    else:
        mine.append(hour)
    store.set_chat(chat, windows=",".join(str(h) for h in sorted(mine)))
    return "ok"


def subs_of(chat: int) -> List[Tuple[str, str]]:
    return store.signal_subs_of(chat)


def subscribe(chat: int, province: str, doc: str) -> str:
    """Статус: ok | exists | limit | bad."""
    if not valid(province, doc):
        return "bad"
    mine = subs_of(chat)
    if (province, doc) in mine:
        return "exists"
    if len(mine) >= limit(chat):
        return "limit"
    store.add_signal_sub(chat, province, doc)
    return "ok"


def refuted(sig: dict) -> bool:
    return sig["no_votes"] >= 2 and sig["no_votes"] > sig["ok_votes"]


def report(chat: int, province: str, doc: str) -> Tuple[str, Optional[dict]]:
    """Статус: ok | merged | daily | muted | bad. При ok — новый сигнал, его надо разослать."""
    if not valid(province, doc):
        return "bad", None
    now = time.time()
    mine = store.signals_by(chat, now - 30 * DAY)
    if sum(1 for s in mine if refuted(s)) >= BAD_LIMIT:
        return "muted", None
    fresh = store.recent_signals(province, doc, now - WINDOW)
    if fresh:
        store.signal_vote(fresh[0]["id"], chat, True)
        return "merged", None
    if sum(1 for s in mine if s["created_at"] > now - DAY) >= DAILY:
        return "daily", None
    store.bump("signals")
    return "ok", store.add_signal(chat, province, doc)


def audience(sig: dict) -> List[int]:
    return [c for c in store.signal_audience(sig["province"], sig["doc"]) if c != sig["chat"]]


def best_hour(province: str, doc: str) -> Optional[int]:
    """Час, когда места замечают чаще всего. Нужно хотя бы 3 неопровергнутых сигнала."""
    from datetime import datetime
    hours = [datetime.fromtimestamp(s["created_at"], config.TZ).hour
             for s in store.recent_signals(province, doc, time.time() - 30 * DAY) if not refuted(s)]
    return Counter(hours).most_common(1)[0][0] if len(hours) >= 3 else None
