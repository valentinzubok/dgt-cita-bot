"""Клиент сайта cita previa DGT: проходит шаги «центр → область → Pedir cita» и читает календарь."""
from __future__ import annotations

import html
import random
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests

from centros import CENTROS

BASE = "https://sedeclave.dgt.gob.es/WEB_CITE_CONSULTA/paginas/"
START_URL = BASE + "inicio.faces"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
AJAX_HEADERS = {"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest"}
TIMEOUT = (15, 60)
PAUSE = (0.8, 2.0)   # пауза между запросами одной проверки — сайт не любит частые обращения
MAX_MONTHS = 3       # сколько месяцев календаря просматривать

AREAS = {
    "VEH": "Vehículos",
    "CND": "Conductores",
    "MAT": "Matriculación",
    "SAN": "Sanciones",
    "CNJ": "Canjes",
}

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Статусы проверки
AVAILABLE = "available"            # в календаре есть свободные дни
FULL = "full"                      # «sin capacidad de citación»
NOT_CONFIGURED = "not_configured"  # офис не принимает этот тип записи
NO_AREA = "no_area"                # область недоступна в этом офисе
UNKNOWN = "unknown"                # страница не распознана


class DGTError(Exception):
    pass


@dataclass
class Result:
    status: str
    tramite: str = ""
    days: List[Tuple[str, str]] = field(default_factory=list)  # (YYYY-MM-DD, занятость)
    hours: List[str] = field(default_factory=list)              # свободное время на ближайший день
    address: str = ""
    schedule: str = ""


class _Browser:
    """requests.Session с паузами между запросами."""

    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.s.headers["Accept-Language"] = "es-ES,es;q=0.9"
        self._last = 0.0

    def _call(self, method: str, url: str, **kw) -> str:
        gap = random.uniform(*PAUSE) - (time.monotonic() - self._last)
        if self._last and gap > 0:
            time.sleep(gap)
        r = self.s.request(method, url, timeout=TIMEOUT, **kw)
        self._last = time.monotonic()
        r.raise_for_status()
        return r.content.decode("utf-8", "replace")

    def get(self, url: str) -> str:
        return self._call("GET", url)

    def post(self, url: str, data: dict, ajax: bool = False) -> str:
        return self._call("POST", url, data=data, headers=AJAX_HEADERS if ajax else None)


def _viewstate(t: str) -> Optional[str]:
    m = (re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', t)
         or re.search(r'<update id="[^"]*ViewState[^"]*"><!\[CDATA\[(.*?)\]\]>', t))
    return m.group(1) if m else None


def _must(pattern: str, t: str, what: str) -> str:
    m = re.search(pattern, t)
    if not m:
        raise DGTError(f"не нашёл {what} на странице — возможно, сайт изменился")
    return m.group(1)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def list_centros() -> Dict[str, str]:
    """{id: название} всех офисов прямо с сайта."""
    t = _Browser().get(START_URL)
    opts = re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', t.split('id="forminicio"')[0])
    if not opts:
        raise DGTError("не удалось получить список офисов")
    return {v: html.unescape(n).strip() for v, n in opts}


# ---------- шаг 1: центр → область → каталог ----------

def _open_catalog(b: _Browser, centro: str, area: str) -> Optional[str]:
    """Выбирает центр и область, жмёт «Continuar». Возвращает HTML каталога или None, если области нет."""
    t = b.get(START_URL)
    vs = _viewstate(t)
    sel = _must(r'<select id="(formselectorCentro:[^"]+)"', t, "список центров")

    def ajax(source: str, values: dict, vs: str) -> str:
        data = {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": source,
            "javax.faces.partial.execute": source,
            "javax.faces.partial.render": "formselectorCentro",
            "javax.faces.behavior.event": "change",
            "javax.faces.partial.event": "change",
            "formselectorCentro_SUBMIT": "1",
            "javax.faces.ViewState": vs,
        }
        data.update(values)
        return html.unescape(b.post(START_URL, data, ajax=True))

    t = ajax(sel, {sel: centro}, vs)
    vs = _viewstate(t) or vs
    area_sel = next((x for x in re.findall(r'<select id="(formselectorCentro:[^"]+)"', t) if x != sel), None)
    if not area_sel:
        raise DGTError("не появился список областей")
    if f'value="{area}"' not in t.split(area_sel, 1)[1].split("</select>", 1)[0]:
        return None

    t = ajax(area_sel, {sel: centro, area_sel: area}, vs)
    vs = _viewstate(t) or vs
    btn = re.search(r'<(?:button|input)[^>]*name="(formselectorCentro:[^"]+)"[^>]*type="submit"', t)
    if not btn:
        return None

    return b.post(START_URL, {sel: centro, area_sel: area, btn.group(1): "",
                              "formselectorCentro_SUBMIT": "1", "javax.faces.ViewState": vs})


def _tramites(catalog: str) -> List[Tuple[str, str]]:
    """[(id ссылки JSF, название)] из каталога."""
    form = catalog[catalog.find('<form id="tramites"'):]
    out = []
    for block in form.split('class="row usuarioTramite')[1:]:
        link = re.search(r"submitForm\('tramites','([^']+)'\)", block)
        if not link:
            continue
        name = re.search(r'<a class="enlace[^"]*" title="([^"]*)"', block)
        sub = re.search(r"<li>([^<]+)</li>", block)
        label = " / ".join(html.unescape(x.group(1)).strip() for x in (name, sub) if x)
        out.append((link.group(1), label))
    return out


# ---------- шаг 2: календарь ----------

DAY_RE = re.compile(r'<div class="diaInter"><input id="([^"]+)" name="[^"]+" type="submit" value="(\d+)"[^>]*/>'
                    r'\s*<span class="(\w*)"')
HOUR_RE = re.compile(r'<div class="notranslate"><input id="[^"]+" name="[^"]+" type="submit" value="(\d{1,2}:\d{2})"')


def _calendar(t: str) -> str:
    start = t.find('id="formcita:calendarioJefatura"')
    if start < 0:
        return ""
    end = t.find('formcita:horasJefatura"', start)
    return t[start:end if end > 0 else None]


def _month(cal: str) -> Optional[Tuple[int, int]]:
    m = re.search(r'cite-calendario-cabecera">.*?<div>\s*([^\s<]+)\s+(\d{4})\s*</div>', cal, re.S)
    if not m or m.group(1).lower() not in MONTHS_ES:
        return None
    return int(m.group(2)), MONTHS_ES[m.group(1).lower()]


def _days(cal: str) -> List[Tuple[str, str, str, str]]:
    """[(YYYY-MM-DD, занятость, id кнопки, значение кнопки)]"""
    ym = _month(cal)
    if not ym:
        return []
    return [(f"{ym[0]:04d}-{ym[1]:02d}-{int(v):02d}", load, bid, v) for bid, v, load in DAY_RE.findall(cal)]


def _office_info(t: str) -> Tuple[str, str]:
    addr = re.search(r"<strong>Dirección:</strong>\s*<p>(.*?)</p>", t, re.S)
    sched = re.search(r"<strong>Horario:</strong>\s*<p>(.*?)</p>", t, re.S)
    return (_clean(addr.group(1)) if addr else ""), (_clean(sched.group(1)) if sched else "")


def _read_calendar(b: _Browser, t: str, tramite: str) -> Result:
    if "PF('sinCapacidad').show()" in t:
        return Result(FULL, tramite)
    if "PF('noConfigurado').show()" in t:
        return Result(NOT_CONFIGURED, tramite)
    cal = _calendar(t)
    if not cal:
        return Result(UNKNOWN, tramite)

    address, schedule = _office_info(t)
    form = re.search(r'<form id="formcita"[^>]*action="([^"]+)"', t)
    action = urljoin(BASE, form.group(1)) if form else BASE + "cita.faces"
    hidden = dict(re.findall(r'<input type="hidden" id="[^"]*" name="(formcita:[^"]+)" value="([^"]*)"', t))
    vs = _viewstate(t)

    def click(src: str, value: str) -> str:
        nonlocal vs
        data = dict(hidden)
        data.update({
            src: value, "formcita_SUBMIT": "1", "javax.faces.ViewState": vs,
            "javax.faces.source": src, "javax.faces.partial.ajax": "true",
            "javax.faces.partial.execute": "formcita",
            "javax.faces.partial.render": "formcita:calendarioJefatura formcita:horasJefatura",
            "javax.faces.behavior.event": "action", "javax.faces.partial.event": "click",
        })
        r = b.post(action, data, ajax=True)
        if "ViewExpiredException" in r:
            raise DGTError("сессия на сайте истекла")
        vs = _viewstate(r) or vs
        return r

    days: List[Tuple[str, str]] = []
    hours: List[str] = []
    for n in range(MAX_MONTHS):
        found = _days(cal)
        if found and not hours:
            iso, _, bid, value = found[0]
            hours = HOUR_RE.findall(click(bid, value))
        days += [(iso, load) for iso, load, _, _ in found]
        if n == MAX_MONTHS - 1 or (days and not found):
            break  # следующий месяц ещё не открыт
        nxt = re.search(r'<input id="([^"]+)" name="[^"]+" type="submit" value="(?:»|&raquo;)"', cal)
        if not nxt:
            break
        cal = _calendar(click(nxt.group(1), "»"))

    if not days:
        return Result(FULL, tramite, address=address, schedule=schedule)
    return Result(AVAILABLE, tramite, days, hours, address, schedule)


def check(centro: str, area: str) -> List[Result]:
    """Проверяет все виды записи в области. Для каждого — отдельная сессия (так ведёт себя и браузер)."""
    b = _Browser()
    catalog = _open_catalog(b, centro, area)
    if catalog is None:
        return [Result(NO_AREA)]
    tramites = _tramites(catalog)
    if not tramites:
        return [Result(UNKNOWN)]

    results = []
    for i, (link, label) in enumerate(tramites):
        if i > 0:
            b = _Browser()
            catalog = _open_catalog(b, centro, area) or ""
        t = b.post(BASE + "catalogo.faces", {
            "tramites_SUBMIT": "1",
            "javax.faces.ViewState": _viewstate(catalog),
            "tramites:_idcl": link,
        })
        results.append(_read_calendar(b, t, label))
    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: python3 dgt.py <centro_id> <VEH|CND|MAT|SAN|CNJ>")
        sys.exit(1)
    for r in check(sys.argv[1], sys.argv[2]):
        print(r)
