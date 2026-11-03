"""Автотесты самого рискованного: оплата, подпись мини-приложения, бонусы, разбор сайта. Запуск: python3 -m unittest discover tests"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
os.environ.update(TELEGRAM_TOKEN="123:TEST", ADMIN_CHAT_ID="1", DATABASE_URL="", WEBHOOK_URL="", RENDER_EXTERNAL_URL="https://example.test")
os.environ["SQLITE_PATH"] = tempfile.mkstemp(suffix=".db")[1]
sys.path.insert(0, str(ROOT))

import actions  # noqa: E402
import admin  # noqa: E402
import ads  # noqa: E402
import bot  # noqa: E402
import checker  # noqa: E402
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

FIX = ROOT / "tests" / "fixtures"
calls = []
members = {}


def fake_call(method, _timeout=40, **p):
    calls.append((method, p))
    if method == "getChatMember":
        return {"ok": True, "result": {"status": members.get((p["chat_id"], p["user_id"]), "left")}}
    if method == "createInvoiceLink":
        return {"ok": True, "result": "https://t.me/$invoice"}
    if method == "sendMessage":
        return {"ok": True, "result": {"message_id": len(calls) + 1000}}
    return {"ok": True, "result": True}


tg.call = fake_call
checker.time.sleep = lambda s: None
store.init()
store.set_setting("gate", 0)  # обязательную подписку на канал проверяют отдельные тесты


def user(chat, name="Test", lang="ru"):
    store.touch_chat(chat, name, "")
    if lang:
        store.set_chat(chat, lang=lang)
    return chat


def pay(chat, plan="p30", charge="c1", amount=99, recurring=False):
    return {"chat": {"id": chat, "type": "private"}, "from": {"id": chat}, "message_id": 1, "successful_payment": {
        "currency": "XTR", "total_amount": amount, "invoice_payload": f"plan:{plan}", "telegram_payment_charge_id": charge,
        "provider_payment_charge_id": "", "is_recurring": recurring or None}}


def init_data(uid=42, age=0, token="123:TEST", **extra):
    fields = {"auth_date": str(int(time.time()) - age), "query_id": "AA", "user": json.dumps({"id": uid, "first_name": "A"}), **extra}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class Parser(unittest.TestCase):
    class Fake:
        def __init__(self):
            self.sources = []

        def post(self, url, data, ajax=False):
            self.sources.append(data["javax.faces.source"])
            name = "hours" if "j_id_3m" in data["javax.faces.source"] else "next_month"
            return (FIX / f"{name}.html").read_text()

    def test_calendar(self):
        r = dgt._read_calendar(self.Fake(), (FIX / "calendar.html").read_text(), "x")
        self.assertEqual(r.status, dgt.AVAILABLE)
        self.assertTrue(r.days and r.hours and r.address)
        self.assertRegex(r.days[0][0], r"^\d{4}-\d{2}-\d{2}$")

    def test_full_and_unknown(self):
        self.assertEqual(dgt._read_calendar(self.Fake(), "x PF('sinCapacidad').show() y", "x").status, dgt.FULL)
        self.assertEqual(dgt._read_calendar(self.Fake(), "<html>капча</html>", "x").status, dgt.UNKNOWN)


class MiniAppAuth(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(webapp.validate_init_data(init_data())["id"], 42)

    def test_signature_field_is_part_of_hash(self):
        self.assertEqual(webapp.validate_init_data(init_data(signature="abc"))["id"], 42)

    def test_forged(self):
        self.assertIsNone(webapp.validate_init_data(init_data(token="999:OTHER")))
        self.assertIsNone(webapp.validate_init_data(init_data().replace("%22id%22%3A+42", "%22id%22%3A+1")))
        self.assertIsNone(webapp.validate_init_data(""))

    def test_old(self):
        self.assertIsNone(webapp.validate_init_data(init_data(age=2 * 86400)))

    def test_premium_gate(self):
        user(700)
        self.assertEqual(webapp.api("GET", "/api/offices", {}, {}, 700)[0], 402)
        self.assertEqual(webapp.api("GET", "/api/me", {}, {}, 700)[0], 200)
        self.assertNotIn("subs", webapp.api("GET", "/api/me", {}, {}, 700)[1])

    def test_cannot_touch_foreign_sub(self):
        user(701), user(702)
        sub, _ = store.add_sub(701, "536", "CND", "Conductores")
        premium.grant(702, 24, "test")
        self.assertEqual(webapp.api("POST", f"/api/subs/{sub['id']}/delete", {}, {}, 702)[0], 404)
        self.assertIsNotNone(store.get_sub(sub["id"]))


class Payments(unittest.TestCase):
    def test_grant_once(self):
        user(100)
        bot.on_paid(pay(100, charge="dup"))
        first = store.get_chat(100)["premium_until"]
        bot.on_paid(pay(100, charge="dup"))
        self.assertEqual(store.get_chat(100)["premium_until"], first)
        self.assertAlmostEqual(first, time.time() + 30 * 86400, delta=10)

    def test_extend(self):
        user(101)
        bot.on_paid(pay(101, "p7", "e1", 39))
        bot.on_paid(pay(101, "p7", "e2", 39))
        self.assertAlmostEqual(store.get_chat(101)["premium_until"], time.time() + 14 * 86400, delta=10)

    def test_recurring_saved(self):
        user(102)
        bot.on_paid(pay(102, charge="r1", recurring=True))
        self.assertEqual(store.get_chat(102)["sub_charge"], "r1")
        self.assertEqual(store.get_chat(102)["sub_active"], 1)

    def test_refund_takes_back(self):
        user(103)
        bot.on_paid(pay(103, "p7", "rf1", 39))
        store.flush()
        premium.on_refund({"chat": {"id": 103}, "refunded_payment": {"telegram_payment_charge_id": "rf1", "invoice_payload": "plan:p7"}})
        self.assertLessEqual(store.get_chat(103)["premium_until"], time.time() + 2)
        self.assertFalse(store.is_premium(103))

    def test_pre_checkout_rejects_wrong_price(self):
        user(104)
        calls.clear()
        premium.on_pre_checkout({"id": "q", "from": {"id": 104}, "currency": "XTR", "total_amount": 1, "invoice_payload": "plan:p30"}, False)
        self.assertFalse(calls[-1][1]["ok"])
        premium.on_pre_checkout({"id": "q", "from": {"id": 104}, "currency": "XTR", "total_amount": 99, "invoice_payload": "plan:p30"}, False)
        self.assertTrue(calls[-1][1]["ok"])
        premium.on_pre_checkout({"id": "q", "from": {"id": 104}, "currency": "XTR", "total_amount": 99, "invoice_payload": "plan:p30"}, True)
        self.assertFalse(calls[-1][1]["ok"])  # сайт DGT недоступен — деньги не берём

    def test_unknown_plan(self):
        user(105)
        msg = pay(105, charge="x")
        msg["successful_payment"]["invoice_payload"] = "plan:hack"
        self.assertIsNone(premium.on_payment(msg))

    def test_expiry_pauses_extra_offices(self):
        user(106)
        store.set_setting("free_subs", 2)
        for i, cid in enumerate(("536", "545", "587", "565")):
            store.add_sub(106, cid, "CND", "Conductores")
        store.set_chat(106, premium_until=int(time.time()) - 10)
        self.assertEqual(premium.expired_cleanup(106), 2)
        self.assertEqual(premium.active_subs_count(106), 2)


class Referral(unittest.TestCase):
    def setUp(self):
        store.set_setting("ref_task", 0)

    def activate(self, friend):
        store.add_sub(friend, "536", "CND", "Conductores")
        return rewards.try_activate_friend(friend)

    def test_basic(self):
        inviter, friend = user(200), user(201)
        code = rewards.ref_link(inviter).rsplit("r_", 1)[1]
        self.assertEqual(rewards.attach_referrer(friend, code), inviter)
        self.assertEqual(self.activate(friend), inviter)
        self.assertTrue(store.is_premium(friend))
        self.assertEqual(rewards.collect(inviter), ("ok", 1))
        self.assertTrue(store.is_premium(inviter))
        self.assertEqual(rewards.collect(inviter)[0], "none")  # второй раз не начисляется

    def test_self_invite(self):
        me = user(202)
        code = rewards.ref_link(me).rsplit("r_", 1)[1]
        self.assertIsNone(rewards.attach_referrer(me, code))

    def test_requires_channel(self):
        inviter, friend = user(210), user(211)
        task = store.add_task("channel", "К", "К", "@chan", "https://t.me/chan", 24)
        store.set_setting("ref_task", task["id"])
        rewards.attach_referrer(friend, rewards.ref_link(inviter).rsplit("r_", 1)[1])
        self.assertIsNone(self.activate(friend))  # друг не подписан
        members[("@chan", friend)] = "member"
        self.assertEqual(rewards.try_activate_friend(friend), inviter)
        self.assertEqual(rewards.collect(inviter)[0], "channel")  # пригласивший не подписан
        members[("@chan", inviter)] = "member"
        self.assertEqual(rewards.collect(inviter), ("ok", 1))

    def test_cap(self):
        inviter = user(220)
        store.set_setting("ref_cap", 1)
        code = rewards.ref_link(inviter).rsplit("r_", 1)[1]
        for friend in (221, 222):
            user(friend)
            rewards.attach_referrer(friend, code)
            self.activate(friend)
        self.assertEqual(rewards.collect(inviter), ("ok", 1))
        store.set_setting("ref_cap", 10)


class Promo(unittest.TestCase):
    def test_flow(self):
        store.add_promo("TEST3", 72, 2, 0, "")
        user(300), user(301), user(302)
        self.assertEqual(rewards.apply_promo(300, "TEST3"), ("ok", 72))
        self.assertAlmostEqual(store.get_chat(300)["premium_until"], time.time() + 3 * 86400, delta=10)
        self.assertEqual(rewards.apply_promo(300, "TEST3")[0], "used")
        self.assertEqual(rewards.apply_promo(301, "TEST3")[0], "ok")
        self.assertEqual(rewards.apply_promo(302, "TEST3")[0], "limit")

    def test_expired_off_unknown(self):
        store.add_promo("OLD", 24, 0, int(time.time()) - 5, "")
        store.add_promo("OFF", 24, 0, 0, "")
        store.set_promo_active("OFF", False)
        user(310)
        self.assertEqual(rewards.apply_promo(310, "OLD")[0], "expired")
        self.assertEqual(rewards.apply_promo(310, "OFF")[0], "off")
        self.assertEqual(rewards.apply_promo(310, "NOPE")[0], "none")
        self.assertEqual(rewards.apply_promo(310, "<b>")[0], "none")

    def test_bruteforce_limit(self):
        user(311)
        results = [rewards.apply_promo(311, f"BAD{i}")[0] for i in range(8)]
        self.assertEqual(results[-1], "wait")

    def test_deep_link(self):
        store.add_promo("LINK3", 72, 0, 0, "")
        user(320, lang=None)
        bot.handle_start_arg(320, "promo_LINK3", True)
        self.assertTrue(store.is_premium(320))
        self.assertEqual(store.get_chat(320)["source"], "promo_LINK3")


class Tasks(unittest.TestCase):
    def test_channel(self):
        task = store.add_task("channel", "К", "К", "@task", "https://t.me/task", 24)
        user(400)
        self.assertEqual(rewards.check_task(400, task["id"])[0], "no")
        members[("@task", 400)] = "member"
        self.assertEqual(rewards.check_task(400, task["id"]), ("ok", 24))
        self.assertEqual(rewards.check_task(400, task["id"])[0], "done")

    def test_link_needs_click(self):
        task = store.add_task("link", "С", "С", "https://example.org", "https://example.org", 6)
        user(401)
        self.assertEqual(rewards.check_task(401, task["id"])[0], "no")
        sig = rewards.sign("t", task["id"], 401)
        self.assertIsNone(rewards.task_click(task["id"], 401, "0" * 16))
        self.assertEqual(rewards.task_click(task["id"], 401, sig), "https://example.org")
        self.assertEqual(rewards.check_task(401, task["id"])[0], "ok")

    def test_builtin_once(self):
        user(402)
        self.assertEqual(rewards.complete_builtin(402, "b:ads"), 24)
        self.assertIsNone(rewards.complete_builtin(402, "b:ads"))


class Ads(unittest.TestCase):
    def test_consent_only(self):
        user(500), user(501), user(502)
        store.set_chat(501, ads_ok=1)
        store.set_chat(502, ads_ok=1)
        premium.grant(502, 24, "test")
        got = ads.recipients("all")
        self.assertIn(501, got)
        self.assertNotIn(500, got)  # нет согласия
        self.assertNotIn(502, got)  # Premium без рекламы

    def test_label_shifts_entities(self):
        text, entities = ads._labelled({"text": "Привет", "entities": [{"type": "bold", "offset": 0, "length": 6}]}, "ru")
        self.assertTrue(text.startswith("📣 Реклама"))
        self.assertEqual(entities[0]["offset"], ads._utf16("📣 Реклама\n\n"))

    def test_signed_click(self):
        camp = store.add_campaign("c", {"type": "text", "text": "t"}, "b", "https://partner.example", "all")
        user(510)
        good = ads.click_url(camp["id"], 510).rsplit("/", 1)[1]
        self.assertIsNone(ads.resolve_click(camp["id"], 510, "0" * 16))
        self.assertEqual(ads.resolve_click(camp["id"], 510, good), "https://partner.example")
        ads.resolve_click(camp["id"], 510, good)
        self.assertEqual(store.get_campaign(camp["id"])["clicks"], 1)


class Limits(unittest.TestCase):
    def test_free_limit(self):
        user(600)
        store.claim_task("b:sub", 600)  # подарок за первый офис уже получен, иначе лимит поднимется
        store.set_setting("free_subs", 2)
        self.assertEqual(actions.add_subscription(600, "536", "CND")[0], "ok")
        self.assertEqual(actions.add_subscription(600, "545", "CND")[0], "ok")
        self.assertEqual(actions.add_subscription(600, "587", "CND")[0], "limit")
        self.assertEqual(actions.add_subscription(600, "536", "CND")[0], "exists")
        self.assertEqual(actions.add_subscription(600, "999", "CND")[0], "bad")
        self.assertEqual(actions.add_subscription(600, "536", "<x>")[0], "bad")

    def test_manual_check_follows_plan(self):
        user(610), user(611)
        premium.grant(611, 24, "t")
        bot.last_manual.clear()
        self.assertIsNone(bot.manual_wait(610, "ru"))
        self.assertIn("30 мин", bot.manual_wait(610, "ru"))
        self.assertIsNone(bot.manual_wait(611, "ru"))
        self.assertIn("1 мин", bot.manual_wait(611, "ru"))

    def test_cannot_hoard_with_pause(self):
        user(603)
        store.claim_task("b:sub", 603)
        store.set_setting("free_subs", 1)
        store.set_setting("max_subs", 3)
        for cid in ("536", "545", "587"):
            _, sub = actions.add_subscription(603, cid, "CND")
            store.update_sub(sub["id"], paused=1)
        self.assertEqual(actions.add_subscription(603, "565", "CND")[0], "limit")
        store.set_setting("free_subs", 2)
        store.set_setting("max_subs", 10)

    def test_resume_respects_limit(self):
        user(601)
        store.set_setting("free_subs", 1)
        a, _ = store.add_sub(601, "536", "CND", "x")
        b, _ = store.add_sub(601, "545", "CND", "x")
        store.update_sub(b["id"], paused=1)
        self.assertEqual(actions.set_paused(store.get_sub(b["id"]), False), "limit")
        store.set_setting("free_subs", 2)

    def test_filter_validated(self):
        user(602)
        a, _ = store.add_sub(602, "536", "CND", "x")
        self.assertFalse(actions.set_filter(a, 12345))
        self.assertTrue(actions.set_filter(a, 14))


class Catalog(unittest.TestCase):
    def test_rows_with_extra_classes(self):
        page = ("""<form id="tramites" name="tramites">
        <div class="row border-bottom usuarioTramite Ciudadano"><a class="enlace me-2" title="Canje de permisos" href="#">x</a>
        <a onclick="return myfaces.oam.submitForm('tramites','tramites:items:0:j_id_1u');">Pedir cita</a></div>
        <div class="row usuarioTramite Ciudadano"><a class="enlace" title="Otro" href="#">y</a>
        <a onclick="return myfaces.oam.submitForm('tramites','tramites:items:1:j_id_1u');">Pedir cita</a></div></form>""")
        self.assertEqual(dgt._tramites(page), [("tramites:items:0:j_id_1u", "Canje de permisos"), ("tramites:items:1:j_id_1u", "Otro")])


class CanjeForm(unittest.TestCase):
    def test_needs_personal_data(self):
        result = dgt._read_calendar(None, '<form action="/WEB_CITE_CONSULTA/paginas/canjes/inicio.faces">', "Canje de permisos")
        self.assertEqual(result.status, dgt.NEEDS_DATA)

    def test_card_explains_it(self):
        user(1300)
        sub, _ = store.add_sub(1300, "486", "CNJ", "Canjes")
        store.update_sub(sub["id"], last=[{"status": dgt.NEEDS_DATA, "tramite": "Canje", "days": [], "hours": [], "address": "", "schedule": ""}],
                         checked_at=int(time.time()))
        fresh = store.get_sub(sub["id"])
        self.assertEqual(views.summary(fresh)[0], "🔐")
        self.assertIn("NIE", views.card(fresh)[0])


class Abuse(unittest.TestCase):
    """Находки аудита: повторные награды через удаление аккаунта, обход лимита через запись на визит, права админа."""

    def rejoin(self, chat):
        store.delete_chat(chat)
        user(chat)

    def test_delete_does_not_repeat_task_or_promo(self):
        user(9001)
        store.add_promo("AGAIN", 72, 0, 0, "")
        self.assertTrue(store.claim_task("b:sub", 9001))
        self.assertEqual(store.use_promo("AGAIN", 9001), "ok")
        self.rejoin(9001)
        self.assertFalse(store.claim_task("b:sub", 9001))
        self.assertTrue(store.task_is_done("b:sub", 9001))
        self.assertEqual(store.use_promo("AGAIN", 9001), "used")
        store.init()  # после перезапуска отметки на месте
        store.flush()
        store.init()
        self.assertFalse(store.claim_task("b:sub", 9001))

    def test_inviter_delete_does_not_repay_friends(self):
        user(9010), user(9011)
        store.set_chat(9011, ref_by=9010, ref_done_at=int(time.time()))
        self.assertEqual(rewards.collect(9010)[0], "ok")
        self.rejoin(9010)
        self.assertEqual(rewards.pending_friends(9010), [])
        self.assertIsNone(store.get_chat(9011).get("ref_by"))

    def test_returning_user_is_not_a_new_friend(self):
        user(9020), user(9021)
        code = rewards.ref_link(9020).rsplit("r_", 1)[1]
        self.rejoin(9021)
        self.assertIsNone(rewards.attach_referrer(9021, code))
        user(9022)
        self.assertEqual(rewards.attach_referrer(9022, code), 9020)

    def test_unbook_respects_limit(self):
        user(9030)
        a, _ = store.add_sub(9030, "606", "CND", "x")
        b, _ = store.add_sub(9030, "486", "CND", "x")
        c, _ = store.add_sub(9030, "545", "CND", "x")
        store.update_sub(c["id"], booked_date="2030-01-02", paused=1)
        self.assertFalse(actions.unbook(store.get_sub(c["id"])))
        self.assertEqual(store.get_sub(c["id"])["paused"], 1)
        self.assertIsNone(store.get_sub(c["id"])["booked_date"])
        self.assertEqual(premium.active_subs_count(9030), 2)
        self.assertEqual(store.get_sub(a["id"])["paused"] + store.get_sub(b["id"])["paused"], 0)

    def test_booked_sub_cannot_be_resumed(self):
        user(9040)
        a, _ = store.add_sub(9040, "606", "CND", "x")
        store.update_sub(a["id"], booked_date="2030-01-01", paused=1)
        self.assertEqual(actions.set_paused(store.get_sub(a["id"]), False), "booked")
        self.assertEqual(store.get_sub(a["id"])["paused"], 1)

    def test_admin_cannot_reject_owner_or_peer(self):
        user(9050), user(9051)
        store.set_chat(9051, role="admin")
        owner = next(iter(config.OWNERS))
        user(owner)
        role = store.get_chat(owner).get("role")
        admin.user_action(9050, 1, "ar", owner)
        self.assertEqual(store.get_chat(owner).get("role"), role)
        admin.user_action(9050, 1, "ap", 9051)
        self.assertEqual(store.get_chat(9051).get("role"), "admin")
        user(9052)
        store.set_chat(9052, role="pending")
        admin.user_action(9050, 1, "ar", 9052)
        self.assertEqual(store.get_chat(9052).get("role"), "banned")


class Signals(unittest.TestCase):
    def setUp(self):
        for table in (store._sig_subs, store._signals, store._sig_votes):
            table.clear()
        for chat in (1200, 1201, 1202, 1203):
            user(chat)

    def test_free_limit(self):
        self.assertEqual(signals.subscribe(1200, "28", "ukr"), "ok")
        self.assertEqual(signals.subscribe(1200, "28", "ukr"), "exists")
        self.assertEqual(signals.subscribe(1200, "08", "tie"), "limit")
        self.assertEqual(signals.subscribe(1200, "99", "tie"), "bad")
        self.assertEqual(signals.subscribe(1200, "28", "xxx"), "bad")

    def test_report_reaches_others_and_merges(self):
        signals.subscribe(1200, "28", "ukr")
        signals.subscribe(1201, "28", "ukr")
        status, sig = signals.report(1200, "28", "ukr")
        self.assertEqual(status, "ok")
        self.assertEqual(signals.audience(sig), [1201])
        self.assertEqual(signals.report(1201, "28", "ukr"), ("merged", None))
        self.assertEqual(store.get_signal(sig["id"])["ok_votes"], 1)

    def test_vote_once_and_not_own(self):
        _, sig = signals.report(1200, "46", "nie")
        self.assertFalse(store.signal_vote(sig["id"], 1200, True))
        self.assertTrue(store.signal_vote(sig["id"], 1201, False))
        self.assertFalse(store.signal_vote(sig["id"], 1201, False))

    def test_refuted_reporter_is_muted(self):
        for province in ("01", "02", "03"):
            _, sig = signals.report(1200, province, "nie")
            store.signal_vote(sig["id"], 1201, False)
            store.signal_vote(sig["id"], 1202, False)
        self.assertEqual(signals.report(1200, "04", "nie"), ("muted", None))

    def test_daily_limit(self):
        for province in ("01", "02", "03", "04", "05"):
            self.assertEqual(signals.report(1203, province, "tie")[0], "ok")
        self.assertEqual(signals.report(1203, "06", "tie"), ("daily", None))

    def test_delete_clears_personal_data(self):
        signals.subscribe(1200, "28", "ukr")
        _, sig = signals.report(1200, "28", "ukr")
        store.delete_chat(1200)
        self.assertEqual(signals.subs_of(1200), [])
        self.assertEqual(store.get_signal(sig["id"])["chat"], 0)


class Tramites(unittest.TestCase):
    def test_canje_checks_only_the_exchange(self):
        """В «Canjes» запись для полиции (FFCCS) давала людям с canje ложное «есть свободные даты»."""
        self.assertTrue(dgt.wanted("CNJ", "Canje de permisos"))
        self.assertFalse(dgt.wanted("CNJ", "Canjes de Fuerzas y Cuerpos de Seguridad Españoles (FFCCS)"))
        self.assertFalse(dgt.wanted("CNJ", "Inscripción, sustitución y renovación de permisos europeos"))
        self.assertTrue(dgt.wanted("CYV", "Duplicados / Renovaciones"))
        self.assertFalse(dgt.wanted("CYV", "Algo para Fuerzas y Cuerpos de Seguridad"))

    def test_sessions_are_spaced(self):
        keep, sleep, slept = dict(dgt._gate), dgt.time.sleep, []
        dgt._gate.update(at=0.0, slow=1.0)
        dgt.time.sleep = slept.append  # во всех тестах сон отключён, здесь только считаем, сколько бы ждали
        try:
            for _ in range(3):
                dgt._wait_turn()
            dgt.slow_down()
            dgt._wait_turn()
        finally:
            dgt.time.sleep = sleep
            dgt._gate.update(keep)
        self.assertEqual(len(slept), 3)
        self.assertTrue(all(dgt.SESSION_GAP - 1 < s <= dgt.SESSION_GAP for s in slept[:2]))
        self.assertGreater(slept[2], dgt.SESSION_GAP * 1.9, "после ошибки сессии вдвое реже")


class Outage(unittest.TestCase):
    def setUp(self):
        self.notify = checker.notify_admins

    def tearDown(self):
        checker.notify_admins = self.notify
        checker.status.update(down_since=None, streak=0, probes=0, probe_at=0, trouble_since=None, cool_until=0)
        dgt._gate["slow"] = 1.0

    def test_short_errors_only_slow_down(self):
        """02.11.2026: DGT отвечал 500 после частых сессий, и каждые 8 минут шли письма «сайт недоступен»."""
        checker.diagnose = lambda: "test"
        sent = []
        checker.notify_admins = lambda *a, **k: sent.append(a)
        for _ in range(5):
            checker._site_error(TimeoutError())
        self.assertFalse(checker.site_down())
        self.assertEqual(sent, [])
        self.assertGreater(checker.status["cool_until"], time.time())
        self.assertEqual(dgt._gate["slow"], dgt.SLOW_MAX)
        checker._site_ok()
        self.assertEqual(sent, [], "о восстановлении пишем, только если писали о сбое")
        self.assertLess(dgt._gate["slow"], dgt.SLOW_MAX)

    def test_enters_and_leaves(self):
        checker.diagnose = lambda: "test"
        sent = []
        checker.notify_admins = lambda *a, **k: sent.append(a)
        checker._site_error(TimeoutError())
        checker.status["trouble_since"] = time.time() - checker.OUTAGE_AFTER
        checker._site_error(TimeoutError())
        self.assertTrue(checker.site_down())
        self.assertEqual(len(sent), 1)
        first_probe = checker.status["probe_at"]
        checker._site_error(TimeoutError())
        self.assertGreater(checker.status["probe_at"], first_probe)  # пауза растёт
        checker._site_ok()
        self.assertFalse(checker.site_down())
        self.assertEqual(len(sent), 2)

    def test_canje_waiting_for_data_is_checked_daily(self):
        user(802)
        premium.grant(802, 24, "test")
        store.add_sub(802, "506", "CNJ", "Canjes")
        key = ("506", "CNJ")
        checker.offices[key] = {"tried": time.time() - 6 * 60, "results": [{"status": dgt.NEEDS_DATA, "days": []}]}
        self.assertNotIn(key, checker.plan())
        self.assertIsNone(checker.next_check_for(802))
        checker.offices[key]["tried"] = time.time() - checker.REVERIFY - 1
        self.assertIn(key, checker.plan())

    def test_premium_first_in_queue(self):
        user(800), user(801)
        store.add_sub(800, "606", "CND", "x")
        store.add_sub(801, "591", "CND", "x")
        premium.grant(801, 24, "test")
        checker.offices.clear()
        due = checker.plan()
        self.assertLess(due.index(("591", "CND")), due.index(("606", "CND")))
        checker.offices[("591", "CND")] = {"tried": time.time() - 6 * 60}
        checker.offices[("606", "CND")] = {"tried": time.time() - 6 * 60}
        due = checker.plan()
        self.assertIn(("591", "CND"), due)  # Premium — каждые 5 минут
        self.assertNotIn(("606", "CND"), due)  # бесплатно — каждые 15


class Database(unittest.TestCase):
    def test_writes_survive_outage(self):
        real, state = store._conn, {"fails": 2}

        class OperationalError(Exception):
            pass

        def flaky():
            if state["fails"]:
                state["fails"] -= 1
                raise OperationalError()
            return real()

        store._conn = flaky
        try:
            store._store_batch([("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", ("probe", "1"))])
        finally:
            store._conn = real
        self.assertEqual(store.q1("SELECT value FROM settings WHERE key = 'probe'")["value"], "1")

    def test_reload_keeps_everything(self):
        user(950)
        premium.grant(950, 48, "test")
        store.add_promo("KEEP", 24, 0, 0, "")
        rewards.apply_promo(950, "KEEP")
        store.flush()
        store.init()
        self.assertTrue(store.is_premium(950))
        self.assertEqual(store.get_promo("KEEP")["uses"], 1)
        self.assertEqual(rewards.apply_promo(950, "KEEP")[0], "used")


class Safety(unittest.TestCase):
    def test_token_not_logged(self):
        err = ConnectionError(f"https://api.telegram.org/bot{config.TOKEN}/sendMessage")
        self.assertNotIn(config.TOKEN, tg._clean(err))

    def test_csv_formula(self):
        import admin
        self.assertEqual(admin.csv_safe("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(admin.csv_safe("Иван"), "Иван")

    def test_name_escaped(self):
        import admin
        user(900, "<b>x</b>")
        self.assertNotIn("<b>x", admin.uname(store.get_chat(900)))

    def test_bad_callback_data(self):
        user(901)
        for data in ("p:abc", "fs:1:999", "d:1:zzz", "bt:1:x:y", "rr:536:lic:99999", "a:536:<script>", "k:x:y", "tc:abc",
                     "ad:u:0", "ad:gp:901:720", "lg:xx", "c:999", "xx:999999", "ad:ux!:1"):
            bot.on_callback({"id": "1", "from": {"id": 901}, "data": data, "message": {"chat": {"id": 901}, "message_id": 5}})
        self.assertFalse(store.is_premium(901))  # не-админ не может выдать себе Premium через поддельную кнопку

    def test_duplicate_update_ignored(self):
        seen = []
        bot.pool.submit = lambda fn, *a: seen.append(a)
        bot.enqueue({"update_id": 777, "message": {}})
        bot.enqueue({"update_id": 777, "message": {}})
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
