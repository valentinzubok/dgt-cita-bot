"""Четыре языка и API мини-приложения: каждый текст переведён, все действия работают через webapp.api."""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.update(TELEGRAM_TOKEN="123:TEST", ADMIN_CHAT_ID="1", DATABASE_URL="", WEBHOOK_URL="", RENDER_EXTERNAL_URL="https://example.test")
os.environ.setdefault("SQLITE_PATH", tempfile.mkstemp(suffix=".db")[1])
sys.path.insert(0, str(ROOT))

import actions  # noqa: E402
import ads  # noqa: E402
import bot  # noqa: E402
import config  # noqa: E402
import dgt  # noqa: E402
import premium  # noqa: E402
import radar  # noqa: E402
import rewards  # noqa: E402
import signals  # noqa: E402
import store  # noqa: E402
import tg  # noqa: E402
import views  # noqa: E402
import webapp  # noqa: E402

CYRILLIC = re.compile("[а-яА-ЯёЁіїєґІЇЄҐ]")
USER_MODULES = ("views", "bot", "actions", "checker", "radar", "admin")
AVAILABLE = [{"status": "available", "tramite": "x", "days": [["2030-01-07", "bajaOcupacion"], ["2030-02-11", "altaOcupacion"]],
              "hours": ["09:00", "09:10"], "address": "Calle A", "schedule": "L-V"}]


def calls_of(name):
    src = (ROOT / f"{name}.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            fn = node.func
            if (fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else "") == "tx":
                yield src, node


def literal_text(node):
    return "".join(n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str))


class Sources(unittest.TestCase):
    def test_every_text_has_four_languages(self):
        for name in USER_MODULES:
            for src, node in calls_of(name):
                where = f"{name}:{node.lineno}"
                if any(isinstance(a, ast.Starred) for a in node.args):
                    continue  # tx(lang, *names): кортеж проверяет test_tables
                self.assertEqual(len(node.args), 5, where)
                for arg, code in ((node.args[3], "es"), (node.args[4], "en")):
                    self.assertIsNone(CYRILLIC.search(literal_text(arg)), f"{where} {code}: {ast.get_source_segment(src, arg)[:80]}")

    def test_tables(self):
        for row in views.CATS.values():
            self.assertEqual(len(row), 5)
        for row in signals.DOCS.values():
            self.assertEqual(len(row), 5)
        for row in rewards.BUILTIN.values():
            self.assertEqual(len(row), 5)
        for table in (premium.INVOICE, premium.CHECKOUT, ads.BUTTONS, ads.LABEL, bot.COMMANDS, bot.SHORT, bot.DESCRIPTION, views.CAL):
            self.assertEqual(set(table), set(config.LANGS))
        self.assertEqual(set(views.LANGS), set(config.LANGS))

    def test_no_russian_outside_tx_in_views(self):
        tree = ast.parse((ROOT / "views.py").read_text(encoding="utf-8"))
        inside = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id in ("tx", "pl", "plural"):
                    inside.update(id(n) for n in ast.walk(node))
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") in ("CAL", "CATS") for t in node.targets):
                inside.update(id(n) for n in ast.walk(node))
            if isinstance(node, (ast.FunctionDef, ast.Module)) and ast.get_docstring(node):
                inside.add(id(node.body[0].value))
        bad = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and CYRILLIC.search(n.value) and id(n) not in inside]
        allowed = {"🛠 Админ-панель", "🇺🇦 Українська", "🇷🇺 Русский"}
        self.assertEqual([b for b in bad if b not in allowed and "Оберіть" not in b], [])

    def test_telegram_limits(self):
        for lang in config.LANGS:
            self.assertLessEqual(len(bot.SHORT[lang]), 120, lang)
            self.assertLessEqual(len(bot.DESCRIPTION[lang]), 512, lang)
            self.assertEqual([c for c, _ in bot.COMMANDS[lang]], [c for c, _ in bot.COMMANDS["ru"]])
            for _, text in bot.COMMANDS[lang]:
                self.assertLessEqual(len(text), 256)

    def test_mini_app_texts(self):
        js = (ROOT / "webapp/app.js").read_text(encoding="utf-8")
        i18n = (ROOT / "webapp/i18n.js").read_text(encoding="utf-8")
        used = set(re.findall(r"\bL\.([a-zA-Z0-9]+)", js)) | set(re.findall(r'"(st[A-Z]\w+)"', js))
        blocks = re.split(r"\n  (uk|ru|es|en): \{\n", i18n)[1:]
        keys = {code: set(re.findall(r'(?:^|[\s,])([a-zA-Z0-9]+): "', body)) for code, body in zip(blocks[::2], blocks[1::2])}
        self.assertEqual(set(keys), set(config.LANGS))
        for code, names in keys.items():
            self.assertEqual(used - names, set(), code)
            self.assertEqual(names, keys["ru"], code)
        for code in ("es", "en"):
            body = blocks[blocks.index(code) + 1]
            self.assertIsNone(CYRILLIC.search(body), code)

    @unittest.skipUnless(shutil.which("node"), "нет node")
    def test_scripts_parse(self):
        for name in ("app.js", "i18n.js"):
            subprocess.run(["node", "--check", str(ROOT / "webapp" / name)], check=True, capture_output=True)


class Formats(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(views.long_day("es", "2030-01-07"), "lunes, 7 de enero")
        self.assertEqual(views.long_day("en", "2030-01-07"), "Monday, 7 January")
        self.assertEqual(views.short_day("es", "2030-05-02"), "2 may")
        self.assertEqual(views.short_day("en", "2030-05-02"), "2 May")
        self.assertEqual(views.short_day("ru", "2030-05-02"), "2 мая")
        days = [("2030-01-07", "x"), ("2030-02-11", "x")]
        self.assertEqual(views.day_range("es", days), "7 ene – 11 feb")
        self.assertEqual(views.day_range("en", days[:1]), "7 January")

    def test_plurals(self):
        self.assertEqual(views.days_word("en", 1), "1 day")
        self.assertEqual(views.days_word("en", 2), "2 days")
        self.assertEqual(views.days_word("es", 1), "1 día")
        self.assertEqual(views.free_days_word("es", 5), "5 días libres")
        self.assertEqual(views.days_word("ru", 5), "5 дней")

    def test_capitalize_keeps_names(self):
        self.assertEqual(views.cap("in January"), "In January")


def post(chat, path, body=None):
    return webapp.api("POST", path, {}, body or {}, chat)


def get(chat, path, query=None):
    return webapp.api("GET", path, query or {}, {}, chat)


class App(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tg.call = lambda method, _timeout=40, **p: {"ok": True, "result": "https://t.me/$inv" if method == "createInvoiceLink" else {"message_id": 9, "status": "member"}}
        store.init()
        webapp.on_lang = lambda chat: None
        actions.check_now = lambda sub, target=None: None

    def fresh(self, chat, lang="en", paid=True):
        store.touch_chat(chat, "Test", "")
        store.set_chat(chat, lang=lang)
        for s in store.subs_of(chat):
            store.delete_sub(s["id"])
        if paid:
            premium.grant(chat, 240, "t")
        return chat

    def test_language_switch(self):
        chat = self.fresh(9100, "ru", paid=False)
        self.assertEqual(post(chat, "api/lang", {"lang": "es"})[0], 200)
        self.assertEqual(views.lang_of(chat), "es")
        self.assertEqual(post(chat, "api/lang", {"lang": "de"})[0], 400)
        self.assertEqual(views.lang_of(chat), "es")
        self.assertEqual(get(chat, "api/me")[1]["lang"], "es")

    def test_free_user_is_limited_but_can_read_and_pay(self):
        chat = self.fresh(9101, "en", paid=False)
        self.assertEqual(get(chat, "api/me")[0], 200)
        self.assertEqual(post(chat, "api/promo", {"code": "NOPE"})[0], 200)
        self.assertEqual(get(chat, "api/page/terms")[0], 200)
        for path in ("api/offices", "api/docs", "api/radar"):
            self.assertEqual(get(chat, path)[0], 402, path)
        self.assertEqual(post(chat, "api/radar", {"centro": "486", "cat": "lic", "km": 100})[0], 402)

    def test_pages_are_translated(self):
        chat = self.fresh(9102, "en")
        for page in webapp.PAGES:
            code, data = get(chat, f"api/page/{page}")
            self.assertEqual(code, 200)
            self.assertIsNone(CYRILLIC.search(data["text"]), page)
        self.assertEqual(get(chat, "api/page/secret")[0], 404)

    def test_office_flow_in_every_language(self):
        for i, lang in enumerate(config.LANGS):
            chat = self.fresh(9110 + i, lang)
            store.save_office_areas("486", [("CYV", "Conductores / Vehículos")])
            self.assertEqual(post(chat, "api/subs", {"centro": "486", "area": "CYV"})[0], 200)
            sub = store.subs_of(chat)[0]
            store.update_sub(sub["id"], last=AVAILABLE, checked_at=int(time.time()))
            data = get(chat, "api/me")[1]
            item = data["subs"][0]
            self.assertEqual((item["state"], item["nearest"], item["icon"]), ("free", "2030-01-07", "mix"))
            self.assertEqual(item["hoursBy"]["2030-01-07"], ["09:00", "09:10"])
            sid = f"api/subs/{sub['id']}"
            self.assertEqual(post(chat, f"{sid}/filter", {"days": 30})[0], 200)
            self.assertEqual(post(chat, f"{sid}/filter", {"days": 31})[0], 400)
            self.assertEqual(post(chat, f"{sid}/pause", {"paused": True})[0], 200)
            self.assertEqual(get(chat, "api/me")[1]["subs"][0]["state"], "paused")
            self.assertEqual(post(chat, f"{sid}/pause", {"paused": False})[0], 200)
            self.assertEqual(post(chat, f"{sid}/book", {"date": "nonsense"})[0], 400)
            self.assertEqual(post(chat, f"{sid}/book", {"date": "2030-01-07", "time": "9am"})[0], 400)
            self.assertEqual(post(chat, f"{sid}/book", {"date": "2030-01-07", "time": "09:10"})[0], 200)
            item = get(chat, "api/me")[1]["subs"][0]
            self.assertEqual((item["state"], item["bookedTime"]), ("booked", "09:10"))
            self.assertTrue(item["checklist"])
            self.assertTrue(store.task_is_done("b:book", chat))
            self.assertEqual(post(chat, f"{sid}/unbook")[1], {"status": "ok", "resumed": True})
            self.assertEqual(get(chat, f"{sid}/history")[0], 200)
            self.assertEqual(post(chat, f"{sid}/delete")[0], 200)
            self.assertEqual(store.subs_of(chat), [])

    def test_other_users_subs_are_closed(self):
        owner, other = self.fresh(9120), self.fresh(9121)
        sub, _ = store.add_sub(owner, "486", "CYV", "Conductores / Vehículos")
        self.assertEqual(post(other, f"api/subs/{sub['id']}/delete")[0], 404)
        self.assertEqual(post(other, f"api/subs/{sub['id']}/book", {"date": "2030-01-07"})[0], 404)
        self.assertIsNotNone(store.get_sub(sub["id"]))

    def test_settings(self):
        chat = self.fresh(9122)
        post(chat, "api/settings", {"quiet": True, "ads": True})
        data = get(chat, "api/me")[1]
        self.assertTrue(data["quiet"] and data["adsOk"])
        self.assertTrue(store.task_is_done("b:ads", chat))
        post(chat, "api/settings", {"quiet": "yes"})
        self.assertTrue(get(chat, "api/me")[1]["quiet"])

    def test_docs(self):
        chat = self.fresh(9123, "es")
        data = get(chat, "api/docs")[1]
        self.assertEqual(len(data["provinces"]), 52)
        self.assertEqual(data["limit"], signals.TOP_SUBS)
        self.assertIsNone(CYRILLIC.search(json.dumps(data, ensure_ascii=False)))
        self.assertEqual(post(chat, "api/docs/sub", {"province": "28", "doc": "tie"})[0], 200)
        self.assertEqual(post(chat, "api/docs/sub", {"province": "99", "doc": "tie"})[0], 400)
        self.assertEqual(get(chat, "api/docs")[1]["mine"][0]["name"], "Madrid")
        code, data = post(chat, "api/docs/report", {"province": "08", "doc": "nie"})
        self.assertEqual((code, data["status"]), (200, "ok"))
        self.assertEqual(post(chat, "api/docs/unsub", {"province": "28", "doc": "tie"})[0], 200)
        self.assertEqual(get(chat, "api/docs")[1]["mine"], [])

    def test_bonus(self):
        chat = self.fresh(9124, "en")
        data = get(chat, "api/me")[1]
        self.assertEqual(len([t for t in data["tasks"] if "id" not in t]), 3)
        self.assertIn(rewards.ref_link(chat), data["refLink"])
        self.assertEqual(post(chat, "api/bonus/collect")[1]["status"], "none")
        task = store.add_task("link", "Открой", "Відкрий", "https://example.org", "https://example.org", 6, "", "Open it")
        listed = next(t for t in get(chat, "api/me")[1]["tasks"] if t.get("id") == task["id"])
        self.assertEqual(listed["title"], "Open it")
        self.assertEqual(post(chat, f"api/tasks/{task['id']}/check")[1]["status"], "no")
        self.assertEqual(views.task_title("es", task), "Open it")
        self.assertEqual(views.task_title("uk", task), "Відкрий")

    def test_radar(self):
        chat = self.fresh(9125, "en")
        radar.office_areas = lambda cid: [("CND", "Conductores")]
        radar.result_for = lambda cid, code: AVAILABLE if cid == "486" else []
        radar.COOLDOWN = 0
        self.assertEqual(get(chat, "api/radar")[1], {"state": "idle"})
        self.assertEqual(post(chat, "api/radar", {"centro": "nope", "cat": "lic", "km": 100})[0], 400)
        self.assertEqual(post(chat, "api/radar", {"centro": "486", "cat": "zzz", "km": 100})[0], 400)
        self.assertEqual(post(chat, "api/radar", {"centro": "486", "cat": "lic", "km": 99})[0], 400)
        self.assertEqual(post(chat, "api/radar", {"centro": "486", "cat": "lic", "km": 100})[0], 200)
        for _ in range(100):
            data = get(chat, "api/radar")[1]
            if data["state"] != "running":
                break
            time.sleep(0.02)
        self.assertEqual(data["state"], "done")
        self.assertEqual(data["items"][0]["centro"], "486")
        self.assertEqual(data["items"][0]["state"], "free")
        self.assertEqual({i["state"] for i in data["items"][1:]}, {"full"})

    def test_radar_stops_when_app_is_closed(self):
        steps = []
        job = radar.scan("486", "lic", 100, lambda i, total, name: steps.append(name), lambda: not steps)
        self.assertIsNone(job)
        self.assertEqual(len(steps), 1)


class Notes(unittest.TestCase):
    def test_privacy_names_real_places(self):
        store.touch_chat(9130, "T", "")
        for lang in config.LANGS:
            store.set_chat(9130, lang=lang)
            text = views.privacy_view(9130)[0]
            self.assertRegex(text, "Франкфурт|Fráncfort|Frankfurt")
            self.assertRegex(text, "Орегон|Oregón|Oregon")

    def test_invoices(self):
        premium._links.clear()
        sent = []
        tg.call = lambda method, _timeout=40, **p: sent.append(p) or {"ok": True, "result": "https://t.me/$inv"}
        for lang in config.LANGS:
            self.assertTrue(premium.invoice_link("p7", lang))
        self.assertEqual(len(sent), 4)
        self.assertIn("7 days", sent[-1]["title"])
        self.assertIn("7 días", sent[-2]["title"])
        self.assertNotIn("{", "".join(p["description"] for p in sent))


if __name__ == "__main__":
    unittest.main()
