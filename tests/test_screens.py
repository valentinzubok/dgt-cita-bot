"""Обходит все экраны: разметка, которую примет Telegram, длина текста, данные кнопок, оба языка."""
import os
import sys
import tempfile
import time
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.update(TELEGRAM_TOKEN="123:TEST", ADMIN_CHAT_ID="1", DATABASE_URL="", WEBHOOK_URL="", RENDER_EXTERNAL_URL="https://example.test")
os.environ.setdefault("SQLITE_PATH", tempfile.mkstemp(suffix=".db")[1])
sys.path.insert(0, str(ROOT))

import admin  # noqa: E402
import ads  # noqa: E402
import checker  # noqa: E402
import dgt  # noqa: E402
import premium  # noqa: E402
import rewards  # noqa: E402
import signals  # noqa: E402
import store  # noqa: E402
import tg  # noqa: E402
import views  # noqa: E402

ALLOWED = {"b", "i", "u", "s", "code", "pre", "a", "blockquote", "tg-spoiler"}


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED:
            self.errors.append(f"тег {tag}")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.errors.append(f"закрытие {tag}")


def check(testcase, screen, where):
    text, kb = screen if isinstance(screen, tuple) else (screen, None)
    p = Tags()
    p.feed(text)
    testcase.assertFalse(p.errors or p.stack, f"{where}: разметка {p.errors} {p.stack}\n{text[:300]}")
    plain = text
    testcase.assertLess(len(plain), 4096, where)
    testcase.assertTrue(plain.strip(), where)
    rows = (kb or {}).get("inline_keyboard", [])
    testcase.assertLessEqual(sum(len(r) for r in rows), 100, where)
    for row in rows:
        testcase.assertLessEqual(len(row), 8, where)
        for b in row:
            testcase.assertTrue(b["text"].strip(), f"{where}: пустая кнопка")
            kinds = [k for k in ("callback_data", "url", "web_app", "copy_text") if k in b]
            testcase.assertEqual(len(kinds), 1, f"{where}: {b}")
            if "callback_data" in b:
                testcase.assertLessEqual(len(b["callback_data"].encode()), 64, f"{where}: {b}")
            if "style" in b:
                testcase.assertIn(b["style"], ("primary", "success", "danger"), where)


class Screens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tg.call = lambda method, _timeout=40, **p: {"ok": True, "result": "https://t.me/$inv" if method == "createInvoiceLink" else {"amount": 5, "message_id": 9, "status": "member"}}
        store.init()
        for chat, lang in ((1, "ru"), (2, "uk"), (3, "ru"), (4, "uk")):
            store.touch_chat(chat, "<Имя> & Co", "user_name")
            store.set_chat(chat, lang=lang)
        premium.grant(3, 240, "t")
        premium.grant(4, 240, "t")
        res = [{"status": "available", "tramite": "x", "days": [["2030-01-07", "bajaOcupacion"], ["2030-02-11", "altaOcupacion"]],
                "hours": ["09:00", "09:10"], "address": "Calle <A> & B", "schedule": "L-V"}]
        for chat in (1, 2, 3, 4):
            a, _ = store.add_sub(chat, "486", "CYV", "Conductores / Vehículos")
            store.update_sub(a["id"], last=res, checked_at=int(time.time()))
            b, _ = store.add_sub(chat, "545", "CNJ", "Canjes")
            store.update_sub(b["id"], last=[{"status": "full", "tramite": "", "days": [], "hours": [], "address": "", "schedule": ""}])
            c, _ = store.add_sub(chat, "587", "RPC", "Renovación de permisos de conducción (solo UE/EE)")
            store.update_sub(c["id"], booked_date="2030-01-07", booked_time="10:30", paused=1)
        store.add_task("channel", "Подпишись", "Підпишись", "@chan", "https://t.me/chan", 24)
        store.add_task("link", "Открой", "Відкрий", "https://example.org", "https://example.org", 6)
        store.add_promo("CODE3", 72, 10, 0, "заметка")
        store.add_campaign("Кампания", {"type": "text", "text": "Текст"}, "Кнопка", "https://example.org", "all")

    def test_user_screens(self):
        for chat in (1, 2, 3, 4):
            lang = views.lang_of(chat)
            for name, screen in {
                "dashboard": views.dashboard(chat, "<Имя>", int(time.time()) + 300, "заметка"), "offices": views.offices(chat, 2),
                "offices radar": views.offices(chat, 0, "шапка", "rb", "rp"), "found": views.search_results(chat, "<q>", list(dgt.CENTROS)[:5]),
                "areas": views.areas(chat, "486", [("CYV", "Conductores / Vehículos"), ("RPC", "Renovación de permisos de conducción (solo UE/EE)"), ("ZZZ", "Otros")]),
                "error": views.areas_error(chat, "486", "c:486"), "list": views.subs_list(chat), "settings": views.settings_view(chat),
                "help": views.help_view(chat), "ua": views.ukraine_view(chat), "premium": views.premium_view(chat, "заметка"),
                "bonus": views.bonus_view(chat, "заметка"), "promo": views.promo_prompt(chat), "terms": views.terms_view(chat),
                "support": views.paysupport_view(chat), "privacy": views.privacy_view(chat), "del": views.delete_me_confirm(chat),
                "limit": views.limit_view(chat), "radar": views.radar_start(chat), "cats": views.radar_categories(chat, "486"),
                "progress": views.radar_progress(chat, "486", "lic", 100, 2, 6, "Elche"), "locked": views.app_locked(chat),
                "results": views.radar_results(chat, "486", "lic", 100, [("486", "CYV", store.subs_of(chat)[0]["last"], 0), ("526", None, [], 45),
                                                                         ("607", "CND", None, 50), ("565", "CND", [{"status": "full", "days": []}], 70)]),
                "soon": views.premium_notice(chat, "soon", int(time.time()) + 3600), "over": views.premium_notice(chat, "over", 0, 3),
                "pending": views.pending_view(lang), "banned": views.banned_view(lang), "maintenance": views.maintenance_view(lang),
            }.items():
                check(self, screen, f"{name}/{chat}")
            for s in store.subs_of(chat):
                for name, screen in {"card": views.card(s, "заметка"), "calendar": views.calendar_view(s, 1), "filter": views.filter_view(s),
                                     "del": views.delete_confirm(s), "dates": views.booking_dates(s), "times": views.booking_times(s, "2030-01-07"),
                                     "ask": views.booking_prompt(s), "gone": views.gone(s), "eve": views.reminder(s, "eve") if s.get("booked_date") else "x"}.items():
                    check(self, screen, f"{name}/{s['id']}")
                if views.all_days(s.get("last")):
                    check(self, views.alert(s, s["last"], {"2030-01-07"}), "alert")
                self.assertTrue(views.day_popup(s, "2030-01-07"))

    def test_signal_screens(self):
        sig = {"id": 7, "chat": 9, "province": "38", "doc": "ukr", "ok_votes": 0, "no_votes": 0, "created_at": 1}
        for chat in (1, 2, 3, 4):
            signals.subscribe(chat, "38", "ukr")
            lang = views.lang_of(chat)
            for name, screen in {
                "docs": views.docs_view(chat, "заметка"), "prov": views.doc_provinces(chat, "r", 3), "types": views.doc_types(chat, "s", "38"),
                "confirm": views.doc_confirm(chat, "38", "pas"), "alert": views.signal_alert(chat, sig), "voted": views.signal_alert(chat, sig, True),
                "passport": views.signal_alert(chat, dict(sig, doc="pas")),
            }.items():
                check(self, screen, f"{name}/{chat}")
            for status in ("ok", "merged", "daily", "muted"):
                self.assertTrue(views.signal_result(lang, status, 3))

    def test_outage_screens(self):
        views.outage = lambda: True
        try:
            check(self, views.dashboard(3, "x", None), "outage dash")
            text, kb = views.premium_view(1)
            check(self, (text, kb), "outage premium")
            self.assertFalse([b for r in kb["inline_keyboard"] for b in r if "url" in b and "$inv" in b["url"]], "оплата при сбое")
            check(self, views.card(store.subs_of(1)[0]), "outage card")
        finally:
            views.outage = lambda: False

    def test_admin_screens(self):
        for name, screen in {
            "panel": admin.panel(), "analytics": admin.analytics(), "system": admin.system("заметка"), "users": admin.users(0),
            "found": admin.users(0, store.all_chats()[:2], "<q>"), "card": admin.user_card(3, 1, "заметка"), "offices": admin.offices_view(),
            "office": admin.office_card("486", "CYV", "заметка"), "money": admin.money("заметка"), "promos": admin.promos_view(),
            "promo": admin.promo_card("CODE3", "заметка"), "tasks": admin.tasks_view(), "ads": admin.ads_view(),
            "segments": admin.broadcast_segments(), "prompt": admin.broadcast_prompt("all"), "settings": admin.settings(),
            "journal": admin.journal_view("all"), "step0": admin.promo_step([]), "step1": admin.promo_step(["72"]), "step2": admin.promo_step(["72", "10"]),
        }.items():
            check(self, screen, name)
        check(self, admin.task_card(store.tasks()[0]["id"], "заметка"), "task")
        check(self, admin.ad_card(store.campaigns()[0]["id"], "заметка"), "ad")
        check(self, checker.daily_report_text(), "report")

    def test_ad_keyboard(self):
        camp = store.campaigns()[0]
        check(self, ("x", ads.keyboard(camp, 1, "ru")), "ad kb")
        self.assertIn("/r/", ads.keyboard(camp, 1, "ru")["inline_keyboard"][0][0]["url"])


if __name__ == "__main__":
    unittest.main()
