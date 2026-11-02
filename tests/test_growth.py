"""Пробный период, гарантия, объявления и канал, окна проверки, статистика: всё, что приводит новых людей и деньги."""
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.update(TELEGRAM_TOKEN="123:TEST", ADMIN_CHAT_ID="1", DATABASE_URL="", WEBHOOK_URL="", RENDER_EXTERNAL_URL="https://example.test")
os.environ.setdefault("SQLITE_PATH", tempfile.mkstemp(suffix=".db")[1])
sys.path.insert(0, str(ROOT))

import actions  # noqa: E402
import admin  # noqa: E402
import board  # noqa: E402
import bot  # noqa: E402
import channel  # noqa: E402
import checker  # noqa: E402
import config  # noqa: E402
import premium  # noqa: E402
import rewards  # noqa: E402
import signals  # noqa: E402
import stats  # noqa: E402
import store  # noqa: E402
import tg  # noqa: E402
import views  # noqa: E402
import webapp  # noqa: E402
from test_screens import check  # noqa: E402

DATES = [{"status": "available", "tramite": "x", "days": [["2030-01-07", "bajaOcupacion"], ["2030-02-11", "altaOcupacion"]],
          "hours": ["09:00"], "address": "", "schedule": ""}]
JOB = "Ищем повара в кафе в Малаге, полный день, договор. Пишите @cafe_malaga"
calls = []


def fake_call(method, _timeout=40, **p):
    calls.append((method, p))
    if method == "createInvoiceLink":
        return {"ok": True, "result": "https://t.me/$post"}
    if method in ("sendMessage", "sendPhoto"):
        return {"ok": True, "result": {"message_id": 700 + len(calls)}}
    if method == "getChatMember":
        return {"ok": True, "result": {"status": "administrator", "can_post_messages": True}}
    return {"ok": True, "result": True}


def sent(method):
    return [p for m, p in calls if m == method]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tg.call = fake_call
        store.init()

    def setUp(self):
        calls.clear()
        store.set_setting("trial_hours", 72)
        store.set_setting("channel_delay", 30)
        store.set_setting("post_job", 99)
        store.set_setting("post_ad", 249)
        channel._queue.clear()
        channel._posted.clear()
        channel._sent.update(at=0.0, day="", count=0)

    def user(self, chat, lang="ru"):
        store.touch_chat(chat, "Test", "")
        store.set_chat(chat, lang=lang)
        return chat


class Trial(Base):
    def test_full_life_of_a_trial(self):
        chat = self.user(5001)
        self.assertTrue(premium.can_trial(chat))
        self.assertEqual(premium.start_trial(chat), "ok")
        c = store.get_chat(chat)
        self.assertAlmostEqual(c["premium_until"], time.time() + 72 * 3600, delta=5)
        self.assertTrue(premium.is_premium(chat) and premium.in_trial(chat))
        self.assertTrue(sent("setChatMenuButton"), "кнопка мини-приложения появилась")
        self.assertEqual(premium.start_trial(chat), "active")
        store.set_chat(chat, premium_until=int(time.time()) - 10)
        self.assertFalse(premium.can_trial(chat))
        self.assertEqual(premium.start_trial(chat), "used")

    def test_only_once_even_after_deleting_the_account(self):
        chat = self.user(5002)
        self.assertEqual(premium.start_trial(chat), "ok")
        store.set_chat(chat, premium_until=0)
        store.delete_chat(chat)
        self.user(chat)
        self.assertEqual(premium.trial_state(chat), "used")

    def test_buyers_owner_switch_and_outage(self):
        buyer = self.user(5003)
        store.set_chat(buyer, paid_at=int(time.time()) - 100)
        self.assertEqual(premium.start_trial(buyer), "paid")
        self.assertEqual(premium.trial_state(1), "active")
        chat = self.user(5004)
        store.set_setting("trial_hours", 0)
        self.assertEqual(premium.start_trial(chat), "off")
        store.set_setting("trial_hours", 72)
        self.assertEqual(premium.start_trial(chat, site_down=True), "down")
        self.assertTrue(premium.can_trial(chat), "при техработах попытка не сгорает")

    def test_bonus_hours_do_not_block_the_trial_later(self):
        chat = self.user(5005)
        premium.grant(chat, 6, "b:sub")
        self.assertEqual(premium.trial_state(chat), "active")
        store.set_chat(chat, premium_until=int(time.time()) - 1)
        self.assertTrue(premium.can_trial(chat))

    def test_buying_during_trial_keeps_the_days(self):
        chat = self.user(5006)
        premium.start_trial(chat)
        until = store.get_chat(chat)["premium_until"]
        store.add_premium(chat, 7 * 86400, "pay:p7")
        self.assertEqual(store.get_chat(chat)["premium_until"], until + 7 * 86400)

    def test_end_of_trial_message_and_paused_offices(self):
        chat = self.user(5007)
        premium.start_trial(chat)
        for cid in ("486", "526", "545"):
            store.add_sub(chat, cid, "VEH", "Vehículos")
        store.set_chat(chat, premium_until=int(time.time()) - 7200)
        self.assertIn((chat, "over"), [(c, k) for c, k, _ in premium.scan_expiring()])
        paused = premium.expired_cleanup(chat)
        self.assertEqual(paused, 1)
        text, _ = views.premium_notice(chat, "over", 0, paused)
        self.assertIn("Пробный период закончился", text)
        self.assertIn("паузе: 1", text)

    def test_api(self):
        chat = self.user(5008, "es")
        self.assertTrue(webapp.me_payload(chat)["trial"])
        self.assertEqual(webapp.api("POST", "api/trial", {}, {}, chat)[0], 200)
        data = webapp.me_payload(chat)
        self.assertTrue(data["premium"] and data["inTrial"])
        self.assertFalse(data["trial"])
        code, reply = webapp.api("POST", "api/trial", {}, {}, chat)
        self.assertEqual((code, reply["status"]), (409, "active"))

    def test_bot_buttons(self):
        chat = self.user(5009)
        labels = [b.get("callback_data") for row in views.dashboard(chat)[1]["inline_keyboard"] for b in row]
        self.assertIn("tr", labels)
        tg.show = lambda *a, **k: 1
        bot.route_callback({"id": "1", "from": {"id": chat, "first_name": "T"}}, chat, 9, "tr!")
        self.assertTrue(premium.in_trial(chat))
        labels = [b.get("callback_data") for row in views.dashboard(chat)[1]["inline_keyboard"] for b in row]
        self.assertNotIn("tr", labels)


class Guarantee(Base):
    def paid(self, chat, days_ago):
        self.user(chat)
        store.add_payment(f"gr{chat}", chat, 39, "p7", False)
        store.flush()
        store.set_chat(chat, paid_at=int(time.time()) - days_ago * 86400, paid_alerts=0)
        return chat

    def test_states(self):
        chat = self.paid(5101, 2)
        self.assertEqual(premium.guarantee_state(chat), "wait")
        store.set_chat(chat, paid_at=int(time.time()) - 8 * 86400)
        self.assertIsNone(premium.guarantee_state(chat), "без офисов гарантия не действует")
        store.add_sub(chat, "486", "VEH", "Vehículos")
        self.assertEqual(premium.guarantee_state(chat), "ready")
        store.bump_chat(chat, "alerts")
        self.assertIsNone(premium.guarantee_state(chat), "уведомление уже было")
        store.set_chat(chat, paid_alerts=1, paid_at=int(time.time()) - 20 * 86400)
        self.assertIsNone(premium.guarantee_state(chat), "срок вышел")

    def test_refund_once(self):
        chat = self.paid(5102, 8)
        store.add_sub(chat, "486", "VEH", "Vehículos")
        self.assertTrue(premium.use_guarantee(chat))
        self.assertEqual(sent("refundStarPayment")[0]["telegram_payment_charge_id"], "gr5102")
        self.assertIsNone(premium.guarantee_state(chat))
        self.assertFalse(premium.use_guarantee(chat))
        self.assertEqual(len(sent("refundStarPayment")), 1)


class Board(Base):
    def test_texts(self):
        self.assertEqual(board.check_text("коротко"), "short")
        self.assertEqual(board.check_text("x" * 801), "long")
        self.assertEqual(board.check_text("Ищем повара в кафе, полный день, хорошая зарплата"), "contact")
        self.assertEqual(board.check_text(JOB), "ok")
        self.assertEqual(board.check_text("Официант в Валенсии, звоните +34 612 345 678 в любое время"), "ok")
        self.assertEqual(board.check_text("Запись на маникюр 20 евро в Мадриде, пишите @nails_madrid"), "ok")
        for text in ("Продаю ситу на TIE в Мадриде, пишите @seller_one, быстро", "Vendo cita para huellas en Madrid, escribe a @seller_two ya",
                     "Cita para extranjería 50€ en Barcelona, contacto @seller_three aquí"):
            self.assertEqual(board.check_text(text), "resale", text)

    def test_first_job_free_then_paid(self):
        chat = self.user(5201)
        self.assertEqual(board.cost(chat, "job"), 0)
        self.assertEqual(board.cost(chat, "ad"), 249)
        post = board.create(chat, "job", JOB, None)
        self.assertEqual(post["stars"], 0)
        board.to_moderation(post)
        self.assertEqual(store.get_post(post["id"])["status"], "review")
        self.assertEqual(board.cost(chat, "job"), 99)
        self.assertTrue(any("Новое объявление" in p["text"] for p in sent("sendMessage")))

    def test_rejected_free_job_keeps_the_free_slot(self):
        chat = self.user(5202)
        post = board.create(chat, "job", JOB, None)
        board.to_moderation(post)
        self.assertTrue(board.reject(store.get_post(post["id"]), "rules"))
        self.assertEqual(board.cost(chat, "job"), 0)

    def pay(self, chat, post, charge):
        return {"chat": {"id": chat}, "successful_payment": {"invoice_payload": f"post:{post['id']}", "total_amount": post["stars"],
                                                             "telegram_payment_charge_id": charge}}

    def test_paid_post_publish(self):
        chat = self.user(5203, "en")
        post = board.create(chat, "ad", JOB, "file-id")
        self.assertTrue(board.check_payment(f"post:{post['id']}", chat, 249))
        self.assertFalse(board.check_payment(f"post:{post['id']}", chat, 1))
        self.assertFalse(board.check_payment(f"post:{post['id']}", 999, 249))
        self.assertFalse(board.check_payment("post:abc", chat, 249))
        self.assertEqual(board.on_paid(self.pay(chat, post, "post1"))["status"], "draft")
        self.assertIsNone(board.on_paid(self.pay(chat, post, "post1")), "повтор платежа")
        post = store.get_post(post["id"])
        self.assertEqual((post["status"], post["charge"]), ("review", "post1"))
        self.assertTrue(board.publish(post))
        photo = sent("sendPhoto")[0]
        self.assertEqual(photo["chat_id"], "@oksita_news")
        self.assertIn("Publicidad", photo["caption"])
        self.assertEqual(store.get_post(post["id"])["status"], "published")
        self.assertTrue(any("Your post is live" in p["text"] for p in sent("sendMessage")))

    def test_html_in_post_is_escaped(self):
        chat = self.user(5204)
        post = board.create(chat, "job", "Нужен <b>повар</b> & помощник в кафе, пишите @cafe_malaga", None)
        board.publish(post)
        text = [p for p in sent("sendMessage") if p.get("chat_id") == "@oksita_news"][0]["text"]
        self.assertIn("&lt;b&gt;повар&lt;/b&gt; &amp;", text)

    def test_reject_refunds_stars(self):
        chat = self.user(5205)
        post = board.create(chat, "ad", JOB, None)
        board.on_paid(self.pay(chat, post, "post2"))
        self.assertTrue(board.reject(store.get_post(post["id"]), "scam"))
        self.assertEqual(sent("refundStarPayment")[0]["telegram_payment_charge_id"], "post2")
        self.assertEqual(store.get_post(post["id"])["status"], "rejected")

    def test_payment_for_cancelled_post_is_refunded(self):
        chat = self.user(5206)
        post = board.create(chat, "ad", JOB, None)
        store.set_post(post["id"], status="cancelled")
        self.assertIsNone(board.on_paid(self.pay(chat, post, "post3")))
        self.assertEqual(len(sent("refundStarPayment")), 1)

    def test_post_payment_never_gives_premium(self):
        chat = self.user(5207)
        post = board.create(chat, "ad", JOB, None)
        bot.on_paid(self.pay(chat, post, "post4"))
        self.assertFalse(premium.is_premium(chat))
        self.assertFalse(store.get_chat(chat).get("paid_at"))

    def test_precheckout(self):
        chat = self.user(5208)
        post = board.create(chat, "ad", JOB, None)
        premium.on_pre_checkout({"id": "1", "from": {"id": chat}, "currency": "XTR", "total_amount": 249, "invoice_payload": f"post:{post['id']}"}, False)
        self.assertTrue(sent("answerPreCheckoutQuery")[-1]["ok"])
        premium.on_pre_checkout({"id": "2", "from": {"id": chat}, "currency": "XTR", "total_amount": 1, "invoice_payload": f"post:{post['id']}"}, False)
        self.assertFalse(sent("answerPreCheckoutQuery")[-1]["ok"])

    def test_refund_of_premium_ignores_post_payments(self):
        chat = self.user(5209)
        store.add_payment("prem1", chat, 39, "p7", False)
        store.add_payment("post9", chat, 249, "post", False)
        store.flush()
        premium.refund_last(chat)
        self.assertEqual(sent("refundStarPayment")[0]["telegram_payment_charge_id"], "prem1")

    def test_flow_through_bot(self):
        chat = self.user(5210)
        shown = []
        tg.show = lambda c, text, kb=None, mid=None, banner=None: shown.append(text) or 1
        cb = {"id": "1", "from": {"id": chat, "first_name": "T"}}
        bot.route_callback(cb, chat, 9, "jn:job")
        self.assertEqual(bot.waiting[chat]["kind"], "post")
        bot.on_post_text(chat, "ru", bot.waiting[chat], "мало", {})
        self.assertIn(chat, bot.waiting, "ошибка в тексте: ждём снова")
        bot.on_post_text(chat, "ru", bot.waiting[chat], JOB, {"photo": [{"file_id": "s"}, {"file_id": "big"}]})
        self.assertNotIn(chat, bot.waiting)
        post = store.q("SELECT * FROM board WHERE chat = ?", (chat,))[0]
        self.assertEqual(post["photo"], "big")
        other = self.user(5211)
        bot.route_callback({"id": "2", "from": {"id": other}}, other, 9, f"js:{post['id']}")
        self.assertEqual(store.get_post(post["id"])["status"], "draft", "чужое объявление не отправить")
        bot.route_callback(cb, chat, 9, f"js:{post['id']}")
        self.assertEqual(store.get_post(post["id"])["status"], "review")

    def test_limit_of_open_posts(self):
        chat = self.user(5212)
        for _ in range(board.MAX_OPEN):
            board.to_moderation(board.create(chat, "ad", JOB, None))
        toast, popup = bot.board_action(chat, 9, "jn", "job", "ru")
        self.assertTrue(popup and toast)

    def test_deleting_account_removes_private_posts(self):
        chat = self.user(5213)
        draft = board.create(chat, "ad", JOB, None)
        live = board.create(chat, "ad", JOB, None)
        board.publish(live)
        store.delete_chat(chat)
        store.flush()
        self.assertIsNone(store.get_post(draft["id"]))
        self.assertEqual(store.get_post(live["id"])["chat"], 0)

    def test_partner_goes_to_admins(self):
        chat = self.user(5214)
        tg.show = lambda *a, **k: 1
        bot.waiting[chat] = {"kind": "partner"}
        bot.on_waited_text(chat, store.get_chat(chat), "ru", bot.waiting[chat], "Мы автошкола в Мадриде")
        self.assertTrue(any("Заявка партнёра" in p["text"] for p in sent("sendMessage")))

    def test_deep_links(self):
        chat = self.user(5215)
        bot.handle_start_arg(chat, "post", True)
        self.assertEqual(bot.opens.pop(chat), "post")
        self.assertEqual(store.get_chat(chat)["source"], "post")


class Channel(Base):
    KEY = ("486", "VEH")

    def live(self):
        return {self.KEY: {"results": DATES}}

    def test_delay_and_format(self):
        channel.on_opened(*self.KEY)
        channel.tick(self.live())
        self.assertFalse(sent("sendMessage"), "задержка ещё идёт")
        channel.tick(self.live(), time.time() + 31 * 60)
        post = sent("sendMessage")[0]
        self.assertEqual(post["chat_id"], "@oksita_news")
        self.assertIn("07.01 – 11.02", post["text"])
        self.assertIn("start=ch", str(post["reply_markup"]))
        self.assertFalse(channel._queue)

    def test_gone_dates_are_not_posted(self):
        channel.on_opened(*self.KEY)
        channel.tick({self.KEY: {"results": []}}, time.time() + 31 * 60)
        self.assertFalse(sent("sendMessage"))
        self.assertFalse(channel._queue)

    def test_limits(self):
        now = time.time() + 31 * 60
        channel.on_opened(*self.KEY)
        channel.on_opened("526", "VEH")
        live = {**self.live(), ("526", "VEH"): {"results": DATES}}
        channel.tick(live, now)
        channel.tick(live, now + 60)
        self.assertEqual(len(sent("sendMessage")), 1, "между постами пауза")
        channel.tick(live, now + channel.GAP + 1)
        self.assertEqual(len(sent("sendMessage")), 2)
        channel.on_opened(*self.KEY)
        self.assertFalse(channel._queue, "об одном офисе не чаще раза в 6 часов")

    def test_off(self):
        store.set_setting("channel_delay", 0)
        channel.on_opened(*self.KEY)
        channel.tick(self.live(), time.time() + 3600)
        self.assertFalse(sent("sendMessage"))

    def test_checker_queues_new_dates(self):
        checker.offices.pop(self.KEY, None)
        checker.process(*self.KEY, DATES, None, {})
        self.assertIn(self.KEY, channel._queue)

    def test_pin(self):
        self.assertEqual(channel.pin_welcome(), "ok")
        self.assertTrue(sent("pinChatMessage"))
        self.assertTrue(channel.rights()["post"])


class Windows(Base):
    def test_limits(self):
        chat = self.user(5301)
        self.assertEqual(signals.toggle_window(chat, 8), "ok")
        self.assertEqual(signals.toggle_window(chat, 12), "limit")
        self.assertEqual(signals.toggle_window(chat, 9), "bad")
        premium.grant(chat, 24, "t")
        self.assertEqual(signals.toggle_window(chat, 12), "ok")
        self.assertEqual(signals.windows_of(chat), [8, 12])
        self.assertEqual(signals.toggle_window(chat, 8), "ok")
        self.assertEqual(signals.windows_of(chat), [12])

    def test_reminder_once_an_hour(self):
        chat = self.user(5302)
        hour = datetime.now(config.TZ).hour
        store.set_chat(chat, windows=str(hour))
        signals.WINDOWS, keep = (hour,), signals.WINDOWS
        try:
            checker.send_windows()
            self.assertFalse([p for p in sent("sendMessage") if p["chat_id"] == chat], "без подписки на документ не пишем")
            store.add_signal_sub(chat, "28", "tie")
            checker.send_windows()
            checker.send_windows()
            self.assertEqual(len([p for p in sent("sendMessage") if p["chat_id"] == chat]), 1)
        finally:
            signals.WINDOWS = keep

    def test_api(self):
        chat = self.user(5303)
        premium.grant(chat, 24, "t")
        self.assertEqual(webapp.api("POST", "api/docs/windows", {}, {"hour": 8}, chat)[1], {"mine": [8]})
        self.assertEqual(webapp.api("POST", "api/docs/windows", {}, {"hour": "8"}, chat)[0], 400)
        self.assertEqual(webapp.api("POST", "api/docs/windows", {}, {"hour": 7}, chat)[0], 400)
        self.assertEqual(webapp.api("GET", "api/docs", {}, {}, chat)[1]["windows"]["mine"], [8])


class Stats(Base):
    def test_summary(self):
        now = int(time.time())
        for hours, lasted in ((5, 600), (29, 1200)):
            store.write("INSERT INTO events (centro, area, opened_at, closed_at, days) VALUES (?, ?, ?, ?, ?)",
                        ("486", "SAN", now - hours * 3600, now - hours * 3600 + lasted, 3))
        stats._cache["at"] = 0
        item = stats.office("486", "SAN")
        self.assertEqual((item["opens"], item["avg"], sum(item["hours"])), (2, 900, 2))
        chat = self.user(5401, "es")
        premium.grant(chat, 24, "t")
        code, data = webapp.api("GET", "api/stats", {}, {}, chat)
        self.assertEqual(code, 200)
        self.assertTrue(any(i["city"] == "Murcia" for i in data["items"]))


class Ladder(Base):
    def setUp(self):
        super().setUp()
        store.set_setting("discount_pct", 10)
        store.set_setting("discount_tasks", 2)

    def test_day_per_task_then_discount(self):
        chat = self.user(5601)
        self.assertEqual(rewards.BUILTIN["b:sub"][-1], 24)
        rewards.complete_builtin(chat, "b:sub")
        self.assertAlmostEqual(store.get_chat(chat)["premium_until"], time.time() + 86400, delta=5)
        self.assertEqual(premium.discount_until(chat), 0)
        self.assertIn("Ещё 1 задание", views.discount_line(chat))
        actions.set_ads(chat, True)
        self.assertAlmostEqual(store.get_chat(chat)["premium_until"], time.time() + 2 * 86400, delta=5)
        self.assertAlmostEqual(premium.discount_until(chat), time.time() + 30 * 86400, delta=5)
        self.assertTrue(any("Скидка −10% открыта" in p["text"] for p in sent("sendMessage")), "человек узнаёт о скидке сразу")
        self.assertIn("открыта до", views.discount_line(chat))

    def test_discount_price_and_one_purchase(self):
        chat = self.user(5602)
        store.set_chat(chat, discount_at=int(time.time()))
        self.assertEqual(premium.plan_price("p30d"), 89)
        premium.on_pre_checkout({"id": "1", "from": {"id": chat}, "currency": "XTR", "total_amount": 89, "invoice_payload": "plan:p30d"}, False)
        self.assertTrue(sent("answerPreCheckoutQuery")[-1]["ok"])
        other = self.user(5603)
        premium.on_pre_checkout({"id": "2", "from": {"id": other}, "currency": "XTR", "total_amount": 89, "invoice_payload": "plan:p30d"}, False)
        self.assertFalse(sent("answerPreCheckoutQuery")[-1]["ok"], "по чужой ссылке скидку не купить")
        msg = {"chat": {"id": chat}, "successful_payment": {"currency": "XTR", "total_amount": 89, "invoice_payload": "plan:p30d",
                                                           "telegram_payment_charge_id": "disc1"}}
        self.assertEqual(premium.on_payment(msg), ("p30d", 89))
        self.assertAlmostEqual(store.get_chat(chat)["premium_until"], time.time() + 30 * 86400, delta=5)
        self.assertEqual(premium.discount_until(chat), 0, "скидка одноразовая")
        premium.on_pre_checkout({"id": "3", "from": {"id": chat}, "currency": "XTR", "total_amount": 89, "invoice_payload": "plan:p30d"}, False)
        self.assertFalse(sent("answerPreCheckoutQuery")[-1]["ok"])

    def test_expiry_buyers_and_switch(self):
        chat = self.user(5604)
        store.set_chat(chat, discount_at=int(time.time()) - 31 * 86400)
        self.assertEqual(premium.discount_until(chat), 0)
        buyer = self.user(5605)
        store.set_chat(buyer, paid_at=int(time.time()))
        store.claim_task("b:sub", buyer)
        store.claim_task("b:ads", buyer)
        self.assertFalse(rewards.unlock_discount(buyer), "скидка — для тех, кто ещё не покупал")
        store.set_setting("discount_pct", 0)
        fresh = self.user(5606)
        store.claim_task("b:sub", fresh)
        store.claim_task("b:ads", fresh)
        self.assertFalse(rewards.unlock_discount(fresh))
        self.assertEqual(views.discount_line(fresh), "")

    def test_friend_counts_as_a_step(self):
        inviter, friend = self.user(5607), self.user(5608)
        store.set_chat(friend, ref_by=inviter, ref_done_at=int(time.time()))
        store.claim_task(f"ref:{friend}", inviter)
        self.assertEqual(rewards.steps(inviter)[0], 1)

    def test_app_and_bot_show_the_offer(self):
        chat = self.user(5609, "en")
        store.set_chat(chat, discount_at=int(time.time()))
        plans = webapp.me_payload(chat)["plans"]
        self.assertEqual((plans[0]["id"], plans[0]["stars"], plans[0]["discount"], plans[0]["full"]), ("p30d", 89, 10, 99))
        self.assertTrue(any("month −10%" in b.get("text", "") for row in views.plan_buttons(chat, "en") for b in row))
        self.assertNotIn("p30d", [p["id"] for p in webapp.me_payload(self.user(5610))["plans"]])


class Honesty(Base):
    def test_intervals_shown_are_the_real_ones(self):
        checker._scale.update(at=0.0)
        keep = checker.per_office
        checker.per_office = lambda: 40.0
        try:
            for i in range(12):
                chat = self.user(5700 + i)
                premium.grant(chat, 24, "t")
                store.add_sub(chat, str(480 + i), "VEH", "Vehículos")
            paid, free = checker.scales()
            self.assertGreater(paid, 1.0, "12 офисов раз в 5 минут не помещаются в лимит сайта")
            self.assertEqual(checker.check_minutes(True), round(5 * paid))
            self.assertIn(f"каждые {checker.check_minutes(True)} мин", views.dashboard(5700)[0])
        finally:
            checker.per_office = keep
            checker._scale.update(at=0.0)
            for i in range(12):
                for s in store.subs_of(5700 + i):
                    store.delete_sub(s["id"])

    def test_invoice_promises_no_exact_interval(self):
        premium._links.clear()
        premium.invoice_link("p7", "ru")
        about = [p for m, p in calls if m == "createInvoiceLink"][-1]["description"]
        self.assertNotRegex(about, r"\d+ минут")
        self.assertIn("в первую очередь", about)

    def test_new_subscriber_reuses_a_fresh_check(self):
        chat = self.user(5720)
        sub, _ = store.add_sub(chat, "486", "VEH", "Vehículos")
        key = ("486", "VEH")
        checker.offices[key] = {"results": DATES, "at": time.time() - 30, "tried": time.time() - 30, "fails": 0}
        ran = []
        keep = checker.run_checks
        checker.run_checks = lambda *a, **k: ran.append(a)
        try:
            actions.check_now(sub)
            actions.jobs.submit(lambda: None).result()
            time.sleep(0.2)
        finally:
            checker.run_checks = keep
        self.assertEqual(ran, [], "к сайту не ходили")
        self.assertEqual(store.get_sub(sub["id"])["last"], DATES)
        self.assertLess(checker.offices[key]["at"], time.time() - 20, "время проверки офиса не подменяется")


class Screens(Base):
    def test_all_new_screens_in_every_language(self):
        for i, lang in enumerate(config.LANGS):
            chat = self.user(5500 + i, lang)
            post = board.create(chat, "ad", JOB, "file")
            store.add_signal_sub(chat, "28", "tie")
            for name, screen in {
                "trial": views.trial_view(chat, "заметка"), "started": views.trial_started(chat), "board": views.board_view(chat, "заметка"),
                "prompt": views.post_prompt(chat, "job"), "preview": views.post_preview(chat, post, "https://t.me/$x"),
                "free": views.post_preview(chat, {**post, "stars": 0}, None), "mine": views.my_posts(chat), "partner": views.partner_view(chat),
                "tie": views.tie_guide(chat), "windows": views.windows_view(chat, "заметка"), "window": views.window_alert(chat),
                "stats": views.stats_view(chat), "guarantee": views.guarantee_confirm(chat),
                "discount": (views.discount_line(chat) or "x", None),
            }.items():
                check(self, screen, f"{name}/{lang}")
            store.set_chat(chat, discount_at=int(time.time()))
            check(self, views.discount_unlocked(chat), f"unlocked/{lang}")
            check(self, (views.discount_line(chat), None), f"line/{lang}")
            for status in ("used", "paid", "active", "down", "off"):
                self.assertTrue(views.trial_note(lang, status))
            for status in ("short", "long", "contact", "resale", "many"):
                self.assertTrue(views.post_error(lang, status))
            for reason in board.REASONS:
                self.assertTrue(views.post_rejected(lang, reason, True))

    def test_admin_screens(self):
        premium.start_trial(self.user(5510))
        post = board.create(self.user(5511), "job", JOB, None)
        for name, screen in {"trial": admin.trial_admin("заметка"), "board": admin.board_admin("заметка"), "card": admin.board_card(post["id"]),
                             "channel": admin.channel_admin("заметка"), "panel": admin.panel()}.items():
            check(self, screen, name)

    def test_admin_actions(self):
        tg.show = lambda *a, **k: 1
        chat = self.user(5512)
        post = board.create(chat, "job", JOB, None)
        board.to_moderation(post)
        self.assertEqual(admin.on_callback(1, 9, f"ad:ja:{post['id']}"[3:]), None)
        self.assertEqual(store.get_post(post["id"])["status"], "published")
        self.assertEqual(admin.on_callback(1, 9, f"ja:{post['id']}"), "Уже решено")
        admin.on_callback(1, 9, "ty:24")
        self.assertEqual(store.setting("trial_hours"), 24)
        admin.on_callback(1, 9, "ty:13")
        self.assertEqual(store.setting("trial_hours"), 24)
        admin.on_callback(1, 9, "cm:15")
        self.assertEqual(store.setting("channel_delay"), 15)
        admin.on_callback(1, 9, "jp:post_job:49")
        self.assertEqual(store.setting("post_job"), 49)


if __name__ == "__main__":
    unittest.main()
