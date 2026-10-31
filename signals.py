"""Сигналы о записях на документы: Extranjería, паспорт, консульство.
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
    "ukr": ("🇺🇦", "TIE для украинцев", "TIE для українців"),
    "tie": ("🖐", "TIE: отпечатки", "TIE: відбитки"),
    "rec": ("📥", "Получение TIE", "Отримання TIE"),
    "nie": ("🔢", "NIE и сертификаты", "NIE і сертифікати"),
    "asy": ("🛡", "Убежище", "Притулок"),
    "ext": ("📄", "Другое в Extranjería", "Інше в Extranjería"),
    "pas": ("🛂", "Паспорт Украины", "Паспорт України"),
    "con": ("🏛", "Консульство Украины", "Консульство України"),
}
ICP_DOCS = ("ukr", "tie", "rec", "nie", "asy", "ext")  # записываются на сайте Extranjería


def valid(province: str, doc: str) -> bool:
    return province in PROVINCES and doc in DOCS


def limit(chat: int) -> int:
    return TOP_SUBS if premium.is_premium(chat) else FREE_SUBS


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
