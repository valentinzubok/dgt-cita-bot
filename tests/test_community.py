"""Обязательная подписка на канал, группа, объявления из мини-приложения, автошколы, отзывы и сайт."""
import base64
import json
import os
import re
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.update(TELEGRAM_TOKEN="123:TEST", ADMIN_CHAT_ID="1", DATABASE_URL="", WEBHOOK_URL="", RENDER_EXTERNAL_URL="https://example.test")
os.environ.setdefault("SQLITE_PATH", tempfile.mkstemp(suffix=".db")[1])
sys.path.insert(0, str(ROOT))

import admin  # noqa: E402
import board  # noqa: E402
import bot  # noqa: E402
import checker  # noqa: E402
import config  # noqa: E402
import gate  # noqa: E402
import group  # noqa: E402
import landing  # noqa: E402
import reviews  # noqa: E402
import schools  # noqa: E402
import signals  # noqa: E402
import store  # noqa: E402
import tg  # noqa: E402
import views  # noqa: E402
import webapp  # noqa: E402

GROUP = -1001234
calls = []
members = {}
photos = []


def fake_call(method, _timeout=40, **p):
    calls.append((method, p))
    if method == "getChatMember":
        return {"ok": True, "result": {"status": members.get(p["user_id"], "left"), "can_delete_messages": True}}
    if method == "getChat":
        if p["chat_id"] == "@oksita_news":
            return {"ok": True, "result": {"id": -100777, "linked_chat_id": GROUP}}
        return {"ok": True, "result": {"id": GROUP, "title": "OkSita · чат", "username": "oksita_chat"}}
    if method == "getChatAdministrators":
        return {"ok": True, "result": [{"user": {"id": 900}}]}
    if method == "createInvoiceLink":
        return {"ok": True, "result": "https://t.me/$post"}
    if method in ("sendMessage", "sendPhoto"):
        return {"ok": True, "result": {"message_id": 800 + len(calls)}}
    return {"ok": True, "result": True}


def sent(method):
    return [p for m, p in calls if m == method]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (tg.call, tg.show, tg.upload_photo, tg.send_photo_file)
        tg.call = fake_call
        tg.upload_photo = lambda chat, content: photos.append(content) or "FILE123"
        tg.send_photo_file = lambda chat, name, content, caption="", kb=None: photos.append((chat, name, caption)) or True
        store.init()

    def setUp(self):
        calls.clear()
        members.clear()
        photos.clear()
        gate._cache.clear()
        gate.waiting.clear()
        gate._nudged.clear()
        group._info.update(at=0.0)
        group._admins.clear()
        group._joined.clear()
        group._welcome.clear()
        group._trash.clear()
        store.set_setting("gate", 1)
        store.set_setting("group", "")
        store.set_setting("group_guard", 1)
        store.set_setting("post_job", 99)
        store.set_setting("post_ad", 249)
        tg.show = lambda chat, text, kb=None, mid=None, banner=None: calls.append(("show", {"chat": chat, "text": text, "kb": kb, "banner": banner})) or 55

    def tearDown(self):
        store.set_setting("gate", 0)

    @classmethod
    def tearDownClass(cls):
        tg.call, tg.show, tg.upload_photo, tg.send_photo_file = cls.saved  # другие наборы тестов подставляют свои

    def user(self, chat, lang="ru", member=True):
        store.touch_chat(chat, "Test", "")
        store.set_chat(chat, lang=lang)
        if member:
            members[chat] = "member"
        return chat

    def shown(self):
        return [p for m, p in calls if m == "show"]


class Gate(Base):
    def test_not_member_sees_the_channel_screen(self):
        chat = self.user(6001, "uk", member=False)
        bot.on_message({"chat": {"id": chat, "type": "private"}, "from": {"id": chat}, "message_id": 1, "text": "/menu"})
        screen = self.shown()[-1]
        self.assertIn("Підпишись на канал", screen["text"])
        self.assertIn("banner_gate", screen["banner"])
        self.assertIn("https://t.me/oksita_news", json.dumps(screen["kb"]))
        self.assertEqual(gate.waiting[chat], 55)

    def test_free_commands_still_work(self):
        chat = self.user(6002, member=False)
        bot.on_message({"chat": {"id": chat, "type": "private"}, "from": {"id": chat}, "message_id": 1, "text": "/privacy"})
        self.assertNotIn("Последний шаг", self.shown()[-1]["text"])
        self.assertEqual(bot.route_callback({"from": {"id": chat}}, chat, 9, "gk"), (views.gate_not_yet("ru"), True))

    def test_join_opens_the_menu_by_itself(self):
        chat = self.user(6003, member=False)
        bot.handle_start_arg(chat, "trial-bcn", False)
        bot.on_message({"chat": {"id": chat, "type": "private"}, "from": {"id": chat}, "message_id": 1, "text": "/start trial-bcn"})
        store.set_chat(chat, screen=55)
        members[chat] = "member"
        gate.on_member({"chat": {"id": -100777, "username": "oksita_news"}, "new_chat_member": {"user": {"id": chat}, "status": "member"}})
        self.assertIn("Premium", self.shown()[-1]["text"], "открылся раздел из ссылки")
        self.assertTrue(gate.allowed(chat))
        self.assertNotIn(chat, gate.waiting)

    def test_leaving_closes_the_bot_and_mutes_alerts_with_one_nudge(self):
        chat = self.user(6004)
        self.assertTrue(gate.allowed(chat))
        gate.on_member({"chat": {"username": "OKSITA_NEWS"}, "new_chat_member": {"user": {"id": chat}, "status": "left"}})
        self.assertFalse(gate.allowed(chat))
        sub, _ = store.add_sub(chat, "486", "VEH", "Vehículos")
        dates = [{"status": "available", "tramite": "x", "days": [["2030-01-07", "bajaOcupacion"]], "hours": [], "address": "", "schedule": ""}]
        checker.process("486", "VEH", dates, None, {})
        self.assertFalse([p for p in sent("sendMessage") if p["chat_id"] == chat and "СВОБОДНЫЕ" in p["text"]])
        self.assertIn("Уведомление не пришло", self.shown()[-1]["text"])
        store.update_sub(sub["id"], last=None)
        checker.process("486", "VEH", dates, None, {})
        self.assertEqual(len([s for s in self.shown() if "не пришло" in s["text"]]), 1, "напоминание раз в сутки")
        store.delete_sub(sub["id"]) if hasattr(store, "delete_sub") else None

    def test_admin_and_telegram_errors_are_never_locked(self):
        self.assertTrue(gate.allowed(1))
        chat = self.user(6005, member=False)
        old = tg.call
        tg.call = lambda method, _timeout=40, **p: None
        try:
            self.assertTrue(gate.allowed(chat, fresh=True))
        finally:
            tg.call = old
        store.set_setting("gate", 0)
        self.assertTrue(gate.allowed(chat))

    def test_mini_app(self):
        chat = self.user(6006, member=False)
        self.assertTrue(webapp.me_payload(chat)["gate"])
        self.assertEqual(webapp.api("GET", "/api/me", {}, {}, chat)[0], 200)
        self.assertEqual(webapp.api("GET", "/api/board", {}, {}, chat), (403, {"error": "gate"}))
        self.assertEqual(webapp.api("POST", "/api/gate", {}, {}, chat), (200, {"ok": False}))
        members[chat] = "member"
        self.assertEqual(webapp.api("POST", "/api/gate", {}, {}, chat), (200, {"ok": True}))
        self.assertFalse(webapp.me_payload(chat)["gate"])

    def test_screen_in_every_language(self):
        for lang in config.LANGS:
            chat = self.user(6010 + len(lang) + ord(lang[0]), lang, member=False)
            text, kb = views.gate_view(chat)
            self.assertIn("@oksita_news", text)
            self.assertLessEqual(len(text), 4096)
            self.assertIn('"gk"', json.dumps(kb))


class Group(Base):
    def msg(self, uid, text="", **extra):
        return {"chat": {"id": GROUP, "type": "supergroup"}, "from": {"id": uid, "first_name": "Ana"}, "message_id": 70, "text": text, **extra}

    def test_finds_the_discussion_group(self):
        self.assertEqual(group.info()["id"], GROUP)
        self.assertEqual(group.link(), "https://t.me/oksita_chat")
        self.assertTrue(group.ours({"id": GROUP}))

    def test_welcome_one_at_a_time_and_cleanup(self):
        bot.dispatch({"message": self.msg(5, new_chat_members=[{"id": 5, "first_name": "Ana"}])})
        bot.dispatch({"message": self.msg(6, new_chat_members=[{"id": 6, "first_name": "<b>Bo</b>"}])})
        welcomes = [p for p in sent("sendMessage") if p["chat_id"] == GROUP]
        self.assertEqual(len(welcomes), 2)
        self.assertIn("&lt;b&gt;Bo&lt;/b&gt;", welcomes[-1]["text"], "имя экранируется")
        self.assertEqual(len([p for p in sent("deleteMessage") if p["chat_id"] == GROUP]), 3, "2 служебных + прошлое приветствие")
        self.assertEqual(group.sweep(time.time() + 3600), 1)

    def test_resale_and_newbie_links_are_removed(self):
        bot.dispatch({"message": self.msg(7, "Продаю cita en extranjería 50 €")})
        self.assertTrue(sent("deleteMessage"))
        self.assertTrue(any("заборонений" in p["text"] for p in sent("sendMessage")))
        self.assertTrue(any("продаже записей" in p["text"] for p in sent("sendMessage")), "админ узнал")
        calls.clear()
        bot.dispatch({"message": self.msg(8, "Привет всем, кто записывался в Малаге?")})
        self.assertFalse(sent("deleteMessage"), "обычный вопрос не трогаем")
        group._joined[(GROUP, 8)] = time.time()
        bot.dispatch({"message": self.msg(8, "Заходите t.me/spam_channel")})
        self.assertTrue(sent("deleteMessage"))
        calls.clear()
        group._joined[(GROUP, 900)] = time.time()
        bot.dispatch({"message": self.msg(900, "Админ: t.me/oksita_news")})
        self.assertFalse(sent("deleteMessage"), "админов не трогаем")
        store.set_setting("group_guard", 0)
        bot.dispatch({"message": self.msg(7, "Продаю cita en extranjería 50 €")})
        self.assertFalse(sent("deleteMessage"))

    def test_other_groups_are_ignored(self):
        bot.dispatch({"message": {"chat": {"id": -555, "type": "group"}, "from": {"id": 7}, "message_id": 1, "text": "Продаю cita 50 €"}})
        self.assertFalse(sent("deleteMessage"))


class BoardApp(Base):
    JOB = "Ищем повара в кафе в Малаге, полный день, договор. Пишите @cafe_malaga"

    def test_free_job_from_the_app(self):
        chat = self.user(6101)
        board_ = webapp.api("GET", "/api/board", {}, {}, chat)[1]
        self.assertTrue(board_["freeJob"])
        self.assertEqual(board_["min"], board.MIN_LEN)
        code, data = webapp.api("POST", "/api/board/draft", {}, {"kind": "job", "text": self.JOB}, chat)
        self.assertEqual((code, data["stars"], data["invoice"]), (200, 0, None))
        code, data = webapp.api("POST", f"/api/board/{data['id']}/send", {}, {}, chat)
        self.assertEqual((code, data["status"]), (200, "review"))
        self.assertEqual(webapp.api("GET", "/api/board", {}, {}, chat)[1]["mine"][0]["status"], "review")

    def test_paid_ad_with_photo(self):
        chat = self.user(6102)
        jpeg = base64.b64encode(b"\xff\xd8\xff" + b"0" * 100).decode()
        self.assertEqual(webapp.api("POST", "/api/board/photo", {}, {"data": "data:image/jpeg;base64," + jpeg}, chat)[0], 200)
        code, data = webapp.api("POST", "/api/board/draft", {}, {"kind": "ad", "text": self.JOB, "photo": True}, chat)
        self.assertEqual((code, data["stars"], data["invoice"]), (200, 249, "https://t.me/$post"))
        self.assertEqual(store.get_post(data["id"])["photo"], "FILE123")
        self.assertEqual(webapp.api("POST", f"/api/board/{data['id']}/send", {}, {}, chat)[0], 409, "платное без оплаты не уходит")

    def test_bad_input(self):
        chat = self.user(6103)
        self.assertEqual(webapp.api("POST", "/api/board/photo", {}, {"data": base64.b64encode(b"<svg>").decode()}, chat)[0], 400)
        self.assertEqual(webapp.api("POST", "/api/board/photo", {}, {"data": "%%%"}, chat)[0], 400)
        code, data = webapp.api("POST", "/api/board/draft", {}, {"kind": "job", "text": "коротко"}, chat)
        self.assertEqual((code, data["status"]), (400, "short"))
        code, data = webapp.api("POST", "/api/board/draft", {}, {"kind": "ad", "text": "Помогу записаться на cita в extranjería, пишите @fast"}, chat)
        self.assertEqual(data["status"], "resale")
        self.assertEqual(webapp.api("POST", "/api/board/draft", {}, {"kind": "x", "text": self.JOB}, chat)[0], 400)
        other = self.user(6104)
        _, data = webapp.api("POST", "/api/board/draft", {}, {"kind": "ad", "text": self.JOB}, other)
        self.assertEqual(webapp.api("POST", f"/api/board/{data['id']}/cancel", {}, {}, chat)[0], 404, "чужое не трогаем")

    def test_bot_offers_the_app(self):
        chat = self.user(6105)
        self.assertIn("/app?screen=post", json.dumps(views.board_view(chat)[1]))


class Schools(Base):
    def test_code_poster_and_stats(self):
        school = schools.create("Autoescuela Sol", "Málaga")
        promo = store.get_promo(school["code"])
        self.assertEqual((promo["hours"], promo["max_uses"]), (schools.DAYS * 24, schools.SEATS))
        self.assertTrue(re.fullmatch(r"SOL\d{3}", school["code"]))
        page = schools.poster(school["code"])
        self.assertIn("<svg", page)
        self.assertIn(school["code"], page)
        self.assertIsNone(schools.poster("NOPE"))
        chat = self.user(6201)
        bot.handle_start_arg(chat, f"promo_{school['code']}", True)
        stats = schools.stats(school)
        self.assertEqual((stats["uses"], stats["came"]), (1, 1))

    def test_request_from_the_bot_to_kit(self):
        chat = self.user(6202, "es")
        bot.waiting[chat] = {"kind": "school"}
        bot.on_waited_text(chat, store.get_chat(chat), "es", bot.waiting[chat], "Autoescuela Luna, Valencia, +34 600 000 000")
        self.assertIn("Autoescuela Luna", sent("sendMessage")[-1]["text"], "заявка у админа")
        self.assertIn("ad:hn:6202", json.dumps(sent("sendMessage")[-1]["reply_markup"]))
        admin.on_callback(1, 5, "hn:6202")
        target, name, caption = photos[-1]
        self.assertEqual(target, chat)
        self.assertIn("código", caption)
        self.assertTrue(store.school_by_code(re.search(r"<code>(\w+)</code>", caption).group(1)))
        self.assertIsNotNone(admin.on_callback(1, 5, "hn:6202"), "второй раз не создаём")

    def test_poster_is_served(self):
        school = schools.create("Autoescola Mar", "")
        self.assertEqual(school["code"][:3], "MAR")
        self.assertIn(school["code"], schools.kit_text(school, "uk"))


class Reviews(Base):
    def booked(self, chat, days_ago):
        sub, _ = store.add_sub(chat, "486", "VEH", "Vehículos")
        day = (datetime.now(config.TZ).date() - timedelta(days=days_ago)).isoformat()
        store.update_sub(sub["id"], booked_date=day, reminded=3)
        return store.get_sub(sub["id"])

    def test_ask_once_the_day_after(self):
        chat = self.user(6301)
        noon = datetime.now(config.TZ).replace(hour=12)
        self.assertTrue(reviews.ask_due(self.booked(chat, 1), noon))
        self.assertFalse(reviews.ask_due(self.booked(self.user(6302), 0), noon))
        self.assertFalse(reviews.ask_due(self.booked(self.user(6303), 9), noon), "о старых визитах не спрашиваем")
        self.assertFalse(reviews.ask_due(self.booked(self.user(6304), 1), noon.replace(hour=9)))

    def test_good_review_goes_public_only_with_consent_and_approval(self):
        chat = self.user(6305, "uk")
        sub = self.booked(chat, 1)
        bot.review_action(chat, 9, "rv", f"{sub['id']}:5", "uk")
        review = store.review_of_sub(sub["id"])
        self.assertEqual(review["stars"], 5)
        bot.waiting[chat] = {"kind": "review", "rid": review["id"], "screen": 9}
        bot.on_waited_text(chat, store.get_chat(chat), "uk", bot.waiting[chat], "Пиши @mememe")
        self.assertIsNone(store.get_review(review["id"])["text"], "контакты не пропускаем")
        bot.on_waited_text(chat, store.get_chat(chat), "uk", bot.waiting[chat], "Записався на іспит за два дні, дякую!")
        self.assertEqual(reviews.public(), [], "без согласия не показываем")
        bot.review_action(chat, 9, "ry", str(review["id"]), "uk")
        self.assertEqual(reviews.public(), [], "без проверки админом не показываем")
        admin.on_callback(1, 5, f"va:{review['id']}")
        self.assertEqual(reviews.public()[0]["text"], "Записався на іспит за два дні, дякую!")
        landing._pages.clear()
        self.assertIn("за два дні", landing.page("/")[0].decode())
        admin.on_callback(1, 5, f"vp:{review['id']}")
        self.assertIn("⭐⭐⭐⭐⭐", sent("sendMessage")[-1]["text"])
        self.assertNotIn("Test", sent("sendMessage")[-1]["text"])
        store.delete_chat(chat)
        self.assertEqual(reviews.public(), [], "удалил данные — отзыв пропал")

    def test_low_rating_goes_to_the_admin_only(self):
        chat = self.user(6306)
        sub = self.booked(chat, 2)
        bot.review_action(chat, 9, "rv", f"{sub['id']}:2", "ru")
        self.assertIn("Оценка 2", sent("sendMessage")[-1]["text"])
        self.assertIn("Что пошло не так", sent("editMessageText")[-1]["text"])
        self.assertEqual(bot.review_action(6999, 9, "rv", f"{sub['id']}:5", "ru"), (None, False), "чужой визит не оценить")
        self.assertEqual(store.review_of_sub(sub["id"])["stars"], 2)


class Site(Base):
    def test_pages(self):
        landing._pages.clear()
        for lang, path in landing.PATHS.items():
            body = landing.page(path)[0].decode()
            self.assertIn(f'<html lang="{lang}">', body)
            self.assertIn('hreflang="x-default"', body)
            self.assertIn(f"start=web-{lang}", body)
            for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body):
                json.loads(block)
        self.assertIn("Sitemap:", landing.page("/robots.txt")[0].decode())
        self.assertIn("/uk</loc>", landing.page("/sitemap.xml")[0].decode())
        self.assertIsNone(landing.page("/nope"))

    def test_numbers_are_honest(self):
        self.assertEqual(landing.round_down(7), "7")
        self.assertEqual(landing.round_down(57), "50+")
        self.assertEqual(landing.round_down(1234), "1200+")

    def test_office_pages(self):
        landing._pages.clear()
        store.save_office_areas("565", [["EXM", "Exámenes"], ["VEH", "Vehículos"]])
        body = landing.page("/dgt/alicante")[0].decode()
        self.assertIn("Cita previa DGT en <em>Alicante</em>", body)
        self.assertIn("start=of_565", body)
        self.assertIn('href="/dgt/elche"', body)  # соседний офис
        self.assertIn("Vehículos", body)
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body):
            json.loads(block)
        index = landing.page("/dgt")[0].decode()
        self.assertEqual(index.count('<li><a href="/dgt/'), len(landing.dgt.CENTROS))
        self.assertIn("/dgt/a-coruna</loc>", landing.page("/sitemap.xml")[0].decode())
        self.assertIsNone(landing.page("/dgt/nope"))

    def test_office_link_opens_the_office(self):
        chat = self.user(6301)
        store.save_office_areas("565", [["EXM", "Exámenes"]])
        bot.handle_start_arg(chat, "of_565", True)
        self.assertEqual(store.get_chat(chat)["source"], "of_565")
        bot.on_message({"chat": {"id": chat, "type": "private"}, "from": {"id": chat}, "message_id": 1, "text": "/start of_565"})
        self.assertIn("Alicante", self.shown()[-1]["text"])



class UkrainianDocs(Base):
    """Паспорт ДП «Документ» и консульство: только свои города, ссылки на официальные очереди, сигналы от людей."""

    def setUp(self):
        super().setUp()
        for table in (store._sig_subs, store._signals, store._sig_votes):
            table.clear()

    def test_passport_only_in_its_three_centres(self):
        self.assertEqual(signals.subscribe(self.user(6201), "29", "pas"), "bad")
        self.assertEqual(signals.subscribe(6201, "46", "pas"), "ok")
        self.assertEqual(signals.subscribe(self.user(6202), "46", "con"), "bad")
        self.assertEqual(signals.booking_url("08", "pas"), "https://barcelona.pasport.org.ua/solutions/e-queue")
        self.assertEqual(signals.booking_url("28", "con"), signals.CONSUL_URL)
        self.assertNotIn("dd:s:29:pas", json.dumps(views.doc_types(6201, "s", "29")[1]))
        self.assertIn("dd:s:28:pas", json.dumps(views.doc_types(6201, "s", "28")[1]))

    def test_bell_toggles_the_centre(self):
        chat = self.user(6203, "uk")
        bot.route_callback({"from": {"id": chat}}, chat, 9, "pz:28")
        self.assertEqual(signals.subs_of(chat), [("28", "pas")])
        self.assertIn("✅ Madrid", json.dumps(self.shown()[-1]["kb"], ensure_ascii=False))
        self.assertEqual(bot.route_callback({"from": {"id": chat}}, chat, 9, "pz:08"), (views.signal_limit("uk"), True))
        bot.route_callback({"from": {"id": chat}}, chat, 9, "pz:28")
        self.assertEqual(signals.subs_of(chat), [])

    def test_report_from_passport_screen_reaches_others_with_the_official_link(self):
        reporter, waiter = self.user(6204), self.user(6205, "uk")
        signals.subscribe(waiter, "46", "pas")
        bot.route_callback({"from": {"id": reporter}}, reporter, 9, "pz:r")
        self.assertIn("dd:r:46:pas", json.dumps(self.shown()[-1]["kb"]))
        bot.route_callback({"from": {"id": reporter}}, reporter, 9, "dr:46:pas")
        self.assertIn("Паспорт Украины в Испании", self.shown()[-1]["text"])
        alert = [p for p in sent("sendMessage") if p.get("chat_id") == waiter][-1]
        self.assertIn("valencia.pasport.org.ua", json.dumps(alert["reply_markup"]))

    def test_window_reminder_links_the_sites_people_follow(self):
        chat = self.user(6206)
        signals.subscribe(chat, "28", "pas")
        kb = json.dumps(views.window_alert(chat)[1])
        self.assertIn("madrid.pasport.org.ua", kb)
        self.assertNotIn(signals.ICP_URL, kb)

if __name__ == "__main__":
    unittest.main()
