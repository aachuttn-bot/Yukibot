#!/usr/bin/env python3
"""Smoke tests for Sakura AI — mocked Telegram + AI backends, no network."""
import asyncio
import os
import sys
import time

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy-token")
os.environ.setdefault("LLM_API_KEY", "dummy-llm-key")
os.environ.setdefault("IMAGE_API_KEY", "dummy-img-key")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot  # noqa: E402


# ------------------------------------------------------------------ fakes ---

class FakeUser:
    def __init__(self, uid=111):
        self.id = uid


class FakeChat:
    def __init__(self, cid=222):
        self.id = cid


class FakeMessage:
    def __init__(self, text="hi"):
        self.text = text
        self.replies = []          # ("text"|"photo", content)
        self.successful_payment = None

    async def reply_text(self, text, **kw):
        self.replies.append(("text", text))

    async def reply_chat_action(self, action):
        pass

    async def reply_photo(self, photo, caption=None, **kw):
        self.replies.append(("photo", caption))


class FakeBot:
    def __init__(self):
        self.invoices = []

    async def send_invoice(self, **kw):
        self.invoices.append(kw)


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()


class FakeQuery:
    def __init__(self, data, uid=111):
        self.data = data
        self.from_user = FakeUser(uid)
        self.message = FakeMessage()
        self.answered = None

    async def answer(self, *a, **kw):
        self.answered = (a, kw)


class FakePreCheckout:
    def __init__(self, payload, uid=111, currency="XTR", amount=300):
        self.invoice_payload = payload
        self.from_user = FakeUser(uid)
        self.currency = currency
        self.total_amount = amount
        self.answered = None

    async def answer(self, ok=None, **kw):
        self.answered = (ok, kw)


class FakePayment:
    def __init__(self, payload):
        self.total_amount = 300
        self.currency = "XTR"
        self.invoice_payload = payload


def make_update(uid=111, text="hi"):
    u = type("U", (), {})()
    u.effective_user = FakeUser(uid)
    u.effective_chat = FakeChat()
    u.message = FakeMessage(text)
    u.callback_query = None
    u.pre_checkout_query = None
    return u


# Mock the AI backends (no network, no keys needed).
async def fake_llm_chat(key, history, user_text):
    return f"[{key}] flirty reply to: {user_text}"


async def fake_make_picture(key, mood):
    return b"fakepngbytes"


async def fake_caption(key, history):
    return "a flirty caption"


bot.llm_chat = fake_llm_chat
bot.make_picture = fake_make_picture
bot.make_trial_picture = fake_make_picture
bot.llm_caption = fake_caption

passed, failed = [], []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("PASS " if cond else "FAIL ") + name)


async def main():
    bot.STATE.clear()
    ctx = FakeContext()

    # 1. Age gate blocks chat before 18+ confirm.
    u = make_update(text="hello")
    await bot.on_text(u, ctx)
    check("age gate blocks chat", any("18+" in t for k, t in u.message.replies if k == "text"))

    # 2. Age confirm -> companion choice offered.
    uq = make_update()
    uq.callback_query = FakeQuery("age:yes")
    await bot.on_choice(uq, ctx)
    qreplies = uq.callback_query.message.replies
    check("age confirm offers companions", any("who do you want" in t.lower() for k, t in qreplies if k == "text"))

    # 3. Pick Yuki -> portrait intro mentions FREE trial.
    uq2 = make_update()
    uq2.callback_query = FakeQuery("comp:yuki")
    await bot.on_choice(uq2, ctx)
    qreplies2 = uq2.callback_query.message.replies
    kinds = [k for k, _ in qreplies2]
    check("companion pick sends portrait", "photo" in kinds)
    check("intro mentions free trial", any("FREE" in (t or "") for k, t in qreplies2))

    # 4. First message = FREE: text reply + 1 picture, no invoice.
    m1 = make_update(text="hi yuki")
    await bot.on_text(m1, ctx)
    kinds = [k for k, _ in m1.message.replies]
    check("free trial: text reply sent", "text" in kinds)
    check("free trial: picture sent", "photo" in kinds)
    check("free trial: no invoice", not ctx.bot.invoices)
    check("free trial marked used", bot.user_state(111)["free_used"]["yuki"] is True)

    # 5. Second message -> 300 Stars invoice, no chat reply.
    m2 = make_update(text="second message")
    await bot.on_text(m2, ctx)
    check("2nd message triggers invoice", len(ctx.bot.invoices) == 1)
    inv = ctx.bot.invoices[0]
    check("invoice is 300 XTR", inv["currency"] == "XTR" and inv["prices"][0].amount == 300)
    check("invoice payload format", inv["payload"].startswith("session:111:"))
    check("2nd message gets no chat reply", not m2.message.replies)

    # 6. Pre-checkout: valid OK, tampered amount rejected.
    pc = FakePreCheckout(inv["payload"])
    upc = make_update()
    upc.pre_checkout_query = pc
    await bot.on_precheckout(upc, ctx)
    check("precheckout accepts valid", pc.answered[0] is True)
    pc2 = FakePreCheckout(inv["payload"], amount=999)
    upc.pre_checkout_query = pc2
    await bot.on_precheckout(upc, ctx)
    check("precheckout rejects wrong amount", pc2.answered[0] is False)

    # 7. Successful payment -> 5-min session active.
    mp = make_update()
    mp.message.successful_payment = FakePayment(inv["payload"])
    await bot.on_successful_payment(mp, ctx)
    st = bot.user_state(111)
    check("payment activates session", bot.session_active(st))
    check("session lasts ~15 min", 14 * 60 < bot.session_left(st) <= 15 * 60)

    # 8. Chat during session -> reply, no new invoice.
    before = len(ctx.bot.invoices)
    m3 = make_update(text="tell me something sweet")
    await bot.on_text(m3, ctx)
    check("session chat replies", any("flirty reply" in t for k, t in m3.message.replies if k == "text"))
    check("session chat: no new invoice", len(ctx.bot.invoices) == before)

    # 9. /pic during session works; cap enforced.
    await bot.cmd_pic(make_update(text="/pic"), ctx)  # fresh update to capture replies
    up = make_update(text="/pic")
    await bot.cmd_pic(up, ctx)
    check("/pic sends photo in session", any(k == "photo" for k, _ in up.message.replies))
    st["pics_this_session"] = bot.PICS_PER_SESSION
    up2 = make_update(text="/pic")
    await bot.cmd_pic(up2, ctx)
    check("/pic cap enforced", not any(k == "photo" for k, _ in up2.message.replies))

    # 10. Expired session -> invoice again.
    st["session_until"] = time.time() - 1
    m4 = make_update(text="are you still there")
    await bot.on_text(m4, ctx)
    check("expired session re-invoices", len(ctx.bot.invoices) == before + 1)

    # 11. Non-text -> text-only reply.
    mn = make_update()
    await bot.on_non_text(mn, ctx)
    check("voice/video declined as text-only", any("words only" in t for k, t in mn.message.replies if k == "text"))

    # 12. Personas are adults; free trial is per companion.
    check("yuki prompt says 26-year-old adult", "26-year-old" in bot.system_prompt("yuki") and "18+" in bot.system_prompt("yuki"))
    check("ren prompt says 28-year-old adult", "28-year-old" in bot.system_prompt("ren"))
    check("free trial per companion (ren unused)", bot.user_state(111)["free_used"]["ren"] is False)

    # 13. /time reports remaining minutes during session.
    st["session_until"] = time.time() + 25 * 60 + 30  # buffer vs int() truncation
    mt = make_update(text="/time")
    await bot.cmd_time(mt, ctx)
    check("/time shows remaining", any("25m" in t for k, t in mt.message.replies if k == "text"))

    # 14. Paid-session reply comes as text + fresh picture (auto-pic).
    st["session_until"] = time.time() + 10 * 60
    st["pics_this_session"] = 0
    m5 = make_update(text="another sweet thing")
    await bot.on_text(m5, ctx)
    kinds5 = [k for k, _ in m5.message.replies]
    check("session reply: text sent", "text" in kinds5)
    check("session reply: picture sent too", "photo" in kinds5)
    check("auto-pic counted", bot.user_state(111)["pics_this_session"] == 1)

    # 15. Picture cap reached -> text still flows, no picture, no crash.
    st["pics_this_session"] = bot.PICS_PER_SESSION
    m6 = make_update(text="still here?")
    await bot.on_text(m6, ctx)
    kinds6 = [k for k, _ in m6.message.replies]
    check("cap reached: text still sent", "text" in kinds6)
    check("cap reached: no picture", "photo" not in kinds6)

    # 16. make_picture_retry: fails twice, succeeds on the third try.
    calls = {"n": 0}

    async def flaky_pic(key, mood):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return b"ok-bytes"

    bot.make_picture = flaky_pic
    got = await bot.make_picture_retry("yuki", "mood", attempts=3)
    check("picture retry succeeds on 3rd try", got == b"ok-bytes" and calls["n"] == 3)
    bot.make_picture = fake_make_picture  # restore

    # 17. send_photo_retry: fails twice, succeeds on the third try.
    class FlakyMessage(FakeMessage):
        def __init__(self):
            super().__init__()
            self.tries = 0

        async def reply_photo(self, photo, caption=None, **kw):
            self.tries += 1
            if self.tries < 3:
                raise RuntimeError("tg hiccup")
            await super().reply_photo(photo, caption=caption, **kw)

    fm = FlakyMessage()
    ok = await bot.send_photo_retry(fm, b"bytes", "cap")
    check("send_photo retry succeeds on 3rd try", ok is True and fm.tries == 3)

    # 18. REPLY_WITH_PIC=false -> text only, no picture.
    bot.REPLY_WITH_PIC = False
    st["pics_this_session"] = 0
    m7 = make_update(text="quiet one")
    await bot.on_text(m7, ctx)
    kinds7 = [k for k, _ in m7.message.replies]
    check("REPLY_WITH_PIC=false: text only", "text" in kinds7 and "photo" not in kinds7)
    bot.REPLY_WITH_PIC = True

    # 19. Free no-key mode: pollinations provider needs no API key.
    _prov, _key = bot.LLM_PROVIDER, bot.LLM_API_KEY
    bot.LLM_PROVIDER, bot.LLM_API_KEY = "pollinations", ""
    check("pollinations: no key required", bot.llm_key_required() is False and bot.llm_headers() == {})
    bot.LLM_PROVIDER, bot.LLM_API_KEY = "openai", ""
    check("openai without key: key required", bot.llm_key_required() is True)
    bot.LLM_PROVIDER, bot.LLM_API_KEY = _prov, _key

    # 20. Two-tier pics: free trial uses the trial (sample) provider.
    used = {"trial": False, "main": False}

    async def spy_trial(key, mood):
        used["trial"] = True
        return b"trial-bytes"

    async def spy_main(key, mood):
        used["main"] = True
        return b"main-bytes"

    bot.make_trial_picture = spy_trial
    bot.make_picture = spy_main
    bot.STATE.clear()
    u20 = make_update(uid=222)
    u20a = make_update(uid=222)
    u20a.callback_query = FakeQuery("age:yes", uid=222)
    await bot.on_choice(u20a, ctx)
    u20b = make_update(uid=222)
    u20b.callback_query = FakeQuery("comp:yuki", uid=222)
    await bot.on_choice(u20b, ctx)
    await bot.on_text(make_update(uid=222, text="hi"), ctx)
    check("free trial pic uses trial provider", used["trial"] is True and used["main"] is False)
    bot.make_trial_picture = fake_make_picture
    bot.make_picture = fake_make_picture

    # 21. Same-face prompt + hotter system prompt + trial defaults.
    check("pic prompt carries face identity", "identical face" in bot.pic_prompt("yuki", "x"))
    check("system prompt is explicit-hot", "explicit" in bot.system_prompt("yuki").lower())
    check("trial provider defaults to pollinations", bot.TRIAL_IMAGE_PROVIDER == "pollinations")

    # 22. Age confirm sends BOTH portraits before the choice.
    bot.STATE.clear()
    u22 = make_update(uid=333)
    u22.callback_query = FakeQuery("age:yes", uid=333)
    await bot.on_choice(u22, ctx)
    pics22 = [c for k, c in u22.callback_query.message.replies if k == "photo"]
    check("both portraits sent first", len(pics22) == 2)
    check("portraits named", any("Yuki" in (c or "") for c in pics22) and any("Ren" in (c or "") for c in pics22))

    # 23. Selecting Yuki sends her white-shirt pic (selected_pic), not the portrait.
    check("yuki has selected_pic", bot.PERSONAS["yuki"].get("selected_pic") == "yuki_selected.png")
    check("ren falls back to portrait", "selected_pic" not in bot.PERSONAS["ren"])

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    # clean up test state file
    try:
        os.remove(bot.STATE_FILE)
    except OSError:
        pass
    sys.exit(1 if failed else 0)


asyncio.run(main())
