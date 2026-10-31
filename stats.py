"""Статистика офисов DGT за 30 дней: сколько раз появлялись места, сколько держались, в какие часы. Считается раз в час."""
from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional

import config
import store

PERIOD = 30 * 86400
TTL = 3600
_cache: dict = {"at": 0.0, "items": []}


def offices() -> List[dict]:
    if time.time() - _cache["at"] > TTL:
        groups: dict = {}
        for e in store.recent_events(int(time.time()) - PERIOD):
            g = groups.setdefault((e["centro"], e["area"]), {"centro": e["centro"], "area": e["area"], "opens": 0, "hours": [0] * 24, "held": []})
            g["opens"] += 1
            g["hours"][datetime.fromtimestamp(e["opened_at"], config.TZ).hour] += 1
            if e["closed_at"]:
                g["held"].append(e["closed_at"] - e["opened_at"])
        for g in groups.values():
            g["avg"] = sum(g["held"]) // len(g["held"]) if g["held"] else None
            g["best"] = g["hours"].index(max(g["hours"]))
            del g["held"]
        _cache.update(at=time.time(), items=sorted(groups.values(), key=lambda g: -g["opens"]))
    return _cache["items"]


def office(centro: str, area: str) -> Optional[dict]:
    return next((g for g in offices() if g["centro"] == centro and g["area"] == area), None)
