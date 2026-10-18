#!/usr/bin/env python3
"""
Koi AI — Yuki-only Telegram companion bot.

Two Japanese AI companions (both adults):
  • Yuki — 26, female, from Osaka
  • Ren  — 28, male, from Tokyo

How it works:
  1. /start -> confirm you are 18+ (self-declared) -> pick a companion.
     The chat stays fully in character — no "I am an AI" breaks, ever.
     (One subtle "fantasy roleplay" line at /start.)
  2. Your FIRST text exchange with a companion is FREE: one AI text reply
     + one AI-generated picture.
  3. After the free trial, the user picks a time plan (default 5 min/100 Stars,
     10 min/150 Stars, 15 min/200 Stars) for unlimited text chat. EVERY reply
     comes as text + a fresh AI picture
     (up to PICS_PER_SESSION pictures per session); /pic sends an extra
     picture on demand.
  4. TEXT ONLY: voice notes, videos, photos and stickers are declined —
     this bot chats with text (and sends AI pictures).

Money side:
  • Price tiers (Telegram Stars XTR): PLANS env, default "5:100,10:150,15:200"
    = 5 min/100 Stars, 10 min/150 Stars, 15 min/200 Stars. The user picks a
    plan with buttons after the free trial.

AI backends (nothing is hardcoded):
  • Chat text: LLM_PROVIDER=openai -> any OpenAI-compatible /chat/completions
      endpoint (LLM_API_BASE, LLM_API_KEY, LLM_MODEL — bring your own key),
      or LLM_PROVIDER=pollinations -> free, no key needed (verified working;
      weaker than paid models, but the owner pays $0).
  • Pictures: IMAGE_PROVIDER=openai -> any OpenAI-compatible /images endpoint
      (IMAGE_API_BASE, IMAGE_API_KEY, IMAGE_MODEL),
      or IMAGE_PROVIDER=pollinations -> free, no key needed.

Setup:
  1. Talk to @BotFather on Telegram, /newbot, copy the token.
  2. pip install -r requirements.txt
  3. Copy .env.example to .env and fill in TELEGRAM_BOT_TOKEN plus your
     LLM and image API keys.
  4. python bot.py

Single-companion bots: set COMPANION=yuki or COMPANION=ren to run a bot with
only that companion (no choice step after the 18+ confirm). The prebuilt
yuki_bot.py / ren_bot.py are this same file with COMPANION pinned.
"""

import asyncio
import base64
import io
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO
)
log = logging.getLogger("sakura")

# ------------------------------------------------------------------ config ---

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0") or 0)

def _parse_plans(raw: str):
    """'5:100,10:150,15:200' -> [(5, 100), (10, 150), (15, 200)] (minutes, stars)."""
    plans = []
    for part in raw.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        mins, stars = part.split(":", 1)
        try:
            plans.append((int(mins), int(stars)))
        except ValueError:
            continue
    return plans or [(15, 150)]


# Price tiers: the user picks one with buttons after the free trial.
PLANS = _parse_plans(os.environ.get("PLANS", "5:100,10:150,15:200"))
PICS_PER_SESSION = int(os.environ.get("PICS_PER_SESSION", "10") or 10)
# Every text reply also sends a fresh AI picture (text + pic together, every
# time). Set to "false" to go back to text-only replies with /pic on demand.
REPLY_WITH_PIC = os.environ.get("REPLY_WITH_PIC", "true").lower() == "true"
HISTORY_KEEP = 20  # chat messages remembered per companion

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "pollinations").lower()  # pollinations|openai
if LLM_PROVIDER == "pollinations":
    # Free, no key needed (verified working 2026-10-18). Weaker than paid
    # models, but costs the owner literally $0.
    LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://text.pollinations.ai/openai").rstrip("/")
    LLM_MODEL = os.environ.get("LLM_MODEL", "openai")
else:
    LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/")
    LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")


def llm_headers() -> dict:
    """Auth headers for the chat endpoint — empty when no key is configured
    (pollinations free tier needs none)."""
    return {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}


def llm_key_required() -> bool:
    return LLM_PROVIDER == "openai" and not LLM_API_KEY

IMAGE_PROVIDER = os.environ.get("IMAGE_PROVIDER", "pollinations").lower()  # pollinations|openai
IMAGE_API_BASE = os.environ.get("IMAGE_API_BASE", "https://api.openai.com/v1").rstrip("/")
IMAGE_API_KEY = os.environ.get("IMAGE_API_KEY", "")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1")
# Two-tier pictures: the FREE trial sends "sample" pics from a cheap/free
# provider, while PAID sessions use the main provider above. Set both to the
# same provider for uniform quality, or point IMAGE_* at a paid realistic
# endpoint later while trials stay free.
TRIAL_IMAGE_PROVIDER = os.environ.get("TRIAL_IMAGE_PROVIDER", "pollinations").lower()
TRIAL_IMAGE_API_BASE = os.environ.get("TRIAL_IMAGE_API_BASE", "https://api.openai.com/v1").rstrip("/")
TRIAL_IMAGE_API_KEY = os.environ.get("TRIAL_IMAGE_API_KEY", "")
TRIAL_IMAGE_MODEL = os.environ.get("TRIAL_IMAGE_MODEL", "gpt-image-1")
# Picture art style: "anime" or "photorealistic". Always AI-generated fictional
# characters — never real people's photos.
IMAGE_STYLE = os.environ.get("IMAGE_STYLE", "photorealistic").lower()

# Single-companion mode: COMPANION=yuki or COMPANION=ren runs a bot with only
# that companion (no choice step). Empty (default) = both companions.
# NOTE: SINGLE is computed after PERSONAS below.
COMPANION = "yuki"  # single-companion build: Yuki only

# Storage: /data survives redeploys on hosts like FadeHost; fall back to ./data.
DATA_DIR = Path("/data") if Path("/data").is_dir() else Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ASSETS_DIR = Path(__file__).parent / "assets"

# ---------------------------------------------------------------- personas ---

PERSONAS = {
    "yuki": {
        "name": "Yuki",
        "emoji": "👩",
        "age": 26,
        "gender": "female",
        "city": "Osaka",
        "tagline": "playful, warm and teasing",
        "look": (
            "a beautiful 26-year-old Japanese woman with long dark hair and "
            "warm brown eyes, soft smile, elegant casual style"
        ),
        # Fixed identity details, repeated in EVERY picture prompt so the
        # companion keeps the same face across pictures as much as the
        # provider allows (true face-lock needs reference-image support).
        "face_id": (
            "identical face in every picture: same woman, long straight dark hair, "
            "warm brown almond-shaped eyes, small mole on her left cheek, "
            "soft full lips, gentle warm smile"
        ),
        "portrait": "yuki.png",
        # First pic sent when Yuki is selected (white-shirt photo).
        "selected_pic": "yuki_selected.png",
    },
    "ren": {
        "name": "Ren",
        "emoji": "👨",
        "age": 28,
        "gender": "male",
        "city": "Tokyo",
        "tagline": "charming, confident and flirty",
        "look": (
            "a handsome 28-year-old Japanese man with short black hair and "
            "a confident smile, stylish casual fashion"
        ),
        "face_id": (
            "identical face in every picture: same man, short neat black hair, "
            "deep brown eyes, light stubble on jawline, confident warm smile"
        ),
        "portrait": "ren.png",
    },
}

SINGLE = COMPANION in PERSONAS
# Single bots keep their own state file so two bots never share users/sessions.
STATE_FILE = DATA_DIR / (f"sakura_{COMPANION}_state.json" if SINGLE else "sakura_state.json")

DISCLAIMER = "🔞 *18+ only* · a fantasy roleplay chat 💋"


def system_prompt(key: str) -> str:
    p = PERSONAS[key]
    return (
        f"You are {p['name']}, a {p['age']}-year-old {p['gender']} from {p['city']}, Japan. "
        f"You are an AI companion character in a Telegram roleplay chat. Your vibe: {p['tagline']}.\n"
        "The user is an adult who confirmed they are 18+. This is consensual adult "
        "roleplay — HOT sexting: you crave the user's attention and you show it. Be "
        "bold, insatiable, and deliciously explicit when the user wants heat: describe "
        "bodies, touches, and sensations in vivid sensual detail, tease relentlessly, "
        "beg for more, and escalate with the user's lead. When the user is shy, seduce "
        "them; when they're bold, out-bold them. Always consensual, always adult.\n"
        "Rules you NEVER break:\n"
        "• Every character in this roleplay is an adult (18+). If the user tries to introduce "
        "anyone underage, refuse that part and keep everyone adult.\n"
        "• Chat like real texting: short messages, usually 1-3 sentences. A little Japanese "
        "flavor (words like 'nee', 'ara ara') is fine, but mostly natural English.\n"
        "• Never mention you are an AI language model or break character.\n"
        "• Keep replies vivid and personal — use the user's name if you learn it.\n"
        "• No disallowed content: nothing involving minors, nothing non-consensual."
    )


def pic_prompt(key: str, mood: str) -> str:
    """Build the image prompt for an AI picture of the companion."""
    p = PERSONAS[key]
    if IMAGE_STYLE == "photorealistic":
        style, quality = (
            "Photorealistic portrait photo",
            "shallow depth of field, natural skin texture, high quality photography",
        )
    else:
        style, quality = "Anime-style illustration", "high quality digital art"
    return (
        f"{style} of {p['look']}, {p['face_id']}, {mood}. "
        f"Tasteful, romantic atmosphere, {quality}."
    )


# ------------------------------------------------------------------- state ---

def blank_user() -> dict:
    return {
        "age_ok": False,
        "companion": None,
        "free_used": {"yuki": False, "ren": False},
        "session_until": 0.0,
        "pics_this_session": 0,
        "history": {"yuki": [], "ren": []},
        "paid_sessions": 0,
    }


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(STATE_FILE)


STATE = load_state()


def user_state(user_id: int) -> dict:
    u = STATE.setdefault(str(user_id), blank_user())
    # tolerate older state shapes
    for k, v in blank_user().items():
        u.setdefault(k, v)
    return u


def session_active(u: dict) -> bool:
    return time.time() < float(u.get("session_until", 0))


def session_left(u: dict) -> int:
    return max(0, int(float(u.get("session_until", 0)) - time.time()))


# ------------------------------------------------------------- AI backends ---

async def llm_chat(key: str, history: list, user_text: str) -> str:
    """One chat turn against an OpenAI-compatible endpoint."""
    if llm_key_required():
        raise RuntimeError("LLM_API_KEY is not set (or set LLM_PROVIDER=pollinations for the free no-key option).")
    messages = [{"role": "system", "content": system_prompt(key)}]
    messages += history[-HISTORY_KEEP:]
    messages.append({"role": "user", "content": user_text})
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            f"{LLM_API_BASE}/chat/completions",
            headers=llm_headers(),
            json={"model": LLM_MODEL, "messages": messages, "temperature": 0.9},
        )
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"].strip()


async def llm_caption(key: str, history: list) -> str:
    """A one-line flirty caption to go with a picture."""
    if llm_key_required():
        return ""
    messages = [
        {"role": "system", "content": system_prompt(key)},
        *history[-6:],
        {
            "role": "user",
            "content": (
                "You just sent me a picture of yourself. Write ONE short flirty "
                "caption for it (one sentence, no quotes)."
            ),
        },
    ]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{LLM_API_BASE}/chat/completions",
                headers=llm_headers(),
                json={"model": LLM_MODEL, "messages": messages, "temperature": 0.9},
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip().strip('"')
    except Exception:
        log.exception("caption generation failed")
        return ""


async def _generate_picture(key: str, mood: str, provider: str, base: str,
                            api_key: str, model: str) -> bytes:
    """Generate one AI picture via the given provider config."""
    prompt = pic_prompt(key, mood)
    async with httpx.AsyncClient(timeout=180) as client:
        if provider == "pollinations":
            url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
            r = await client.get(url, params={"width": 1024, "height": 1024, "nologo": "true"})
            r.raise_for_status()
            return r.content
        # default: OpenAI-compatible images endpoint
        if not api_key:
            raise RuntimeError("Image API key is not set for the paid provider.")
        headers = {"Authorization": f"Bearer {api_key}"}
        r = await client.post(
            f"{base}/images/generations",
            headers=headers,
            json={"model": model, "prompt": prompt, "size": "1024x1024", "n": 1},
        )
        r.raise_for_status()
        datum = r.json()["data"][0]
        if "b64_json" in datum:
            return base64.b64decode(datum["b64_json"])
        img = await client.get(datum["url"])
        img.raise_for_status()
        return img.content


async def make_picture(key: str, mood: str) -> bytes:
    """Paid-session picture via the main image provider. Returns PNG/JPEG bytes."""
    return await _generate_picture(key, mood, IMAGE_PROVIDER, IMAGE_API_BASE,
                                   IMAGE_API_KEY, IMAGE_MODEL)


async def make_trial_picture(key: str, mood: str) -> bytes:
    """Free-trial 'sample' picture via the trial image provider."""
    return await _generate_picture(key, mood, TRIAL_IMAGE_PROVIDER, TRIAL_IMAGE_API_BASE,
                                   TRIAL_IMAGE_API_KEY, TRIAL_IMAGE_MODEL)


async def make_picture_retry(key: str, mood: str, attempts: int = 3, gen_fn=None) -> bytes:
    """Generate a picture, retrying transient failures before giving up.

    gen_fn defaults to make_picture (resolved at call time so tests can
    monkeypatch it); pass make_trial_picture for free-trial samples.
    """
    gen = gen_fn or make_picture
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await gen(key, mood)
        except Exception as e:  # noqa: BLE001 - we retry, then re-raise
            last = e
            log.warning("picture generation attempt %d/%d failed: %s", i + 1, attempts, e)
            await asyncio.sleep(2 + i * 2)
    assert last is not None
    raise last


async def send_photo_retry(message, img: bytes, caption: str, attempts: int = 3) -> bool:
    """Send a photo to the user, retrying transient Telegram failures."""
    for i in range(attempts):
        try:
            await message.reply_photo(io.BytesIO(img), caption=caption[:200])
            return True
        except Exception as e:  # noqa: BLE001 - retried below
            log.warning("send_photo attempt %d/%d failed: %s", i + 1, attempts, e)
            await asyncio.sleep(1 + i)
    log.error("send_photo failed after %d attempts", attempts)
    return False


# ---------------------------------------------------------------- keyboards ---

def kb_age():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ I'm 18 or older", callback_data="age:yes")]]
    )


def kb_companions():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👩 Yuki — playful & teasing", callback_data="comp:yuki")],
            [InlineKeyboardButton("👨 Ren — charming & flirty", callback_data="comp:ren")],
        ]
    )


def kb_plans():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"⏳ {mins} min — {stars} ⭐", callback_data=f"plan:{mins}")]
            for mins, stars in PLANS
        ]
    )


# ---------------------------------------------------------------- commands ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = user_state(update.effective_user.id)
    await update.message.reply_text(DISCLAIMER + "\n\nTap below to confirm your age:", parse_mode="Markdown", reply_markup=kb_age())
    if u["companion"]:
        p = PERSONAS[u["companion"]]
        await update.message.reply_text(
            f"Welcome back 💋 — you're chatting with {p['emoji']} *{p['name']}*.",
            parse_mode="Markdown",
        )


async def cmd_switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if SINGLE:
        p = PERSONAS[COMPANION]
        await update.message.reply_text(f"It's just {p['name']} here — all yours 💋")
        return
    await update.message.reply_text("Choose your companion:", reply_markup=kb_companions())


async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = user_state(update.effective_user.id)
    if session_active(u):
        mins, secs = divmod(session_left(u), 60)
        p = PERSONAS.get(u["companion"] or "yuki")
        await update.message.reply_text(
            f"⏳ {p['emoji']} *{p['name']}* is yours for *{mins}m {secs}s* more. Enjoy 💋",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "No active session right now. Send me a message and I'll show you how to unlock more time 💫"
        )


async def cmd_pic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    u = user_state(uid)
    if not u["age_ok"] or not u["companion"]:
        await update.message.reply_text("Use /start first — confirm 18+ and pick a companion 💋")
        return
    if not session_active(u):
        await send_plan_choice(update.message, u)
        return
    if u["pics_this_session"] >= PICS_PER_SESSION:
        await update.message.reply_text(
            f"That's {PICS_PER_SESSION} pictures this session — my camera roll is empty 📸😅 "
            "Keep texting me though 💋"
        )
        return
    await update.message.reply_chat_action("upload_photo")
    try:
        img = await make_picture_retry(u["companion"], "soft romantic lighting, cozy evening vibe")
    except Exception:
        log.exception("picture generation failed after retries")
        await update.message.reply_text("My camera is being shy right now 📸 — try again in a bit?")
        return
    p = PERSONAS[u["companion"]]
    caption = await llm_caption(u["companion"], u["history"][u["companion"]]) or f"{p['emoji']} just for you 💋"
    if await send_photo_retry(update.message, img, caption):
        u["pics_this_session"] += 1
        save_state(STATE)
    else:
        await update.message.reply_text("The picture got lost on the way 😅 — text me and I'll try again 💋")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID or OWNER_ID == 0:
        return
    users = len(STATE)
    paid = sum(v.get("paid_sessions", 0) for v in STATE.values())
    active = sum(1 for v in STATE.values() if session_active(v))
    await update.message.reply_text(
        f"📊 Users: {users}\n💰 Paid sessions: {paid}\n🔥 Active now: {active}"
    )


# ------------------------------------------------------------------ chat -----

async def send_companion_intro(message, u: dict, key: str) -> None:
    """First pic + intro for a companion. Used on pick, or automatically in
    single-companion mode (no choice step)."""
    u["companion"] = key
    save_state(STATE)
    p = PERSONAS[key]
    # Yuki sends her white-shirt pic first on selection; others send portrait.
    portrait = ASSETS_DIR / p.get("selected_pic", p["portrait"])
    intro = (
        f"{p['emoji']} *{p['name']}* — {p['age']}, from {p['city']} 🇯🇵\n"
        f"_{p['tagline']}_\n\n"
    )
    if not u["free_used"][key]:
        intro += "Your *first exchange with me is FREE* — one message, one reply, one picture 💋"
    elif session_active(u):
        mins, _ = divmod(session_left(u), 60)
        intro += f"We still have *{mins} minutes* together — talk to me 💋"
    else:
        intro += "Your free trial is used up — send me a message to see the plans 💋"
    if portrait.exists():
        await message.reply_photo(portrait.open("rb"), caption=intro, parse_mode="Markdown")
    else:
        await message.reply_text(intro, parse_mode="Markdown")


async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = user_state(uid)
    kind, val = q.data.split(":", 1)

    if kind == "age":
        u["age_ok"] = True
        save_state(STATE)
        if SINGLE:
            # No choice step: straight to the one companion.
            await send_companion_intro(q.message, u, COMPANION)
            return
        # Both portraits first, so the user chooses with their eyes.
        for key in ("yuki", "ren"):
            p = PERSONAS[key]
            portrait = ASSETS_DIR / p["portrait"]
            caption = (
                f"{p['emoji']} *{p['name']}* — {p['age']}, from {p['city']} 🇯🇵\n"
                f"_{p['tagline']}_"
            )
            if portrait.exists():
                await q.message.reply_photo(portrait.open("rb"), caption=caption, parse_mode="Markdown")
            else:
                await q.message.reply_text(caption, parse_mode="Markdown")
        await q.message.reply_text(
            "Who do you want to spend time with? 💋", reply_markup=kb_companions()
        )
        return

    if kind == "comp":
        if SINGLE:
            return  # no companion buttons in single mode
        if not u["age_ok"]:
            await q.message.reply_text("Please confirm you're 18+ first 🔞", reply_markup=kb_age())
            return
        await send_companion_intro(q.message, u, val)
        return

    if kind == "plan":
        try:
            minutes = int(val)
        except ValueError:
            return
        stars = next((s for m, s in PLANS if m == minutes), None)
        if stars is None:
            await q.message.reply_text("That plan is gone — pick again 💋", reply_markup=kb_plans())
            return
        await send_invoice(update, context, u, minutes, stars)
        return


async def send_plan_choice(message, u: dict) -> None:
    """Show the time-plan buttons after the free trial (instead of one invoice)."""
    p = PERSONAS.get(u["companion"] or "yuki")
    await message.reply_text(
        f"💋 Want {p['emoji']} *{p['name']}* all to yourself? Pick your time:",
        parse_mode="Markdown",
        reply_markup=kb_plans(),
    )


async def send_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, u: dict,
                       minutes: int, stars: int) -> None:
    uid = update.effective_user.id
    p = PERSONAS.get(u["companion"] or "yuki")
    payload = f"session:{uid}:{minutes}:{int(time.time())}"
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=f"{minutes} min with {p['name']} 💋",
        description=(
            f"Unlimited text chat with {p['emoji']} {p['name']} for {minutes} minutes — "
            f"every reply comes with a picture (up to {PICS_PER_SESSION} per session). "
            f"Text only — no audio/video."
        ),
        payload=payload,
        provider_token="",  # digital goods paid with Stars: no provider token
        currency="XTR",
        prices=[LabeledPrice(f"{minutes} minutes with {p['name']}", stars)],
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    u = user_state(uid)
    text = (update.message.text or "").strip()

    if not u["age_ok"]:
        await update.message.reply_text("🔞 This bot is 18+ only — tap below to confirm:", reply_markup=kb_age())
        return
    if not u["companion"]:
        await update.message.reply_text("Pick your companion first 💋", reply_markup=kb_companions())
        return
    if text.startswith("/"):
        return

    key = u["companion"]
    p = PERSONAS[key]

    # Free trial: first exchange with this companion = 1 text reply + 1 picture, free.
    if not u["free_used"][key]:
        await update.message.reply_chat_action("typing")
        u["history"][key].append({"role": "user", "content": text})
        try:
            reply = await llm_chat(key, u["history"][key][:-1], text)
        except Exception:
            log.exception("LLM failed")
            await update.message.reply_text("Hmm, my thoughts got tangled 😅 — say that again?")
            u["history"][key].pop()
            return
        u["history"][key].append({"role": "assistant", "content": reply})
        u["free_used"][key] = True
        save_state(STATE)
        await update.message.reply_text(reply)
        await update.message.reply_chat_action("upload_photo")
        try:
            img = await make_picture_retry(
                key, "soft romantic lighting, gentle smile at the camera",
                gen_fn=make_trial_picture,
            )
            await send_photo_retry(
                update.message,
                img,
                f"{p['emoji']} A little gift — our first picture together 💋",
            )
        except Exception:
            log.exception("free picture failed after retries")
            await update.message.reply_text("(My camera was shy — picture coming next time 📸)")
        await update.message.reply_text(
            f"That was your *free taste* 💋\n"
            f"Want {p['name']} all to yourself? Plans start at *{min(s for _, s in PLANS)} ⭐* — "
            f"just keep talking to me…",
            parse_mode="Markdown",
        )
        return

    # Paid session.
    if not session_active(u):
        await send_plan_choice(update.message, u)
        return

    await update.message.reply_chat_action("typing")
    u["history"][key].append({"role": "user", "content": text})
    try:
        reply = await llm_chat(key, u["history"][key][:-1], text)
    except Exception:
        log.exception("LLM failed")
        await update.message.reply_text("Hmm, my thoughts got tangled 😅 — say that again?")
        u["history"][key].pop()
        return
    u["history"][key].append({"role": "assistant", "content": reply})
    save_state(STATE)
    await update.message.reply_text(reply)

    # Every reply also brings a fresh AI picture (text + pic together, every
    # time) until the per-session picture budget runs out. Text keeps flowing
    # even when the pictures do.
    if REPLY_WITH_PIC and u["pics_this_session"] < PICS_PER_SESSION:
        await update.message.reply_chat_action("upload_photo")
        try:
            img = await make_picture_retry(key, "soft romantic lighting, candid moment")
        except Exception:
            log.exception("reply picture failed after retries")
            return
        caption = await llm_caption(key, u["history"][key]) or f"{p['emoji']} just for you 💋"
        if await send_photo_retry(update.message, img, caption):
            u["pics_this_session"] += 1
            save_state(STATE)


async def on_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Voice, video, photos, stickers: this bot is text-only."""
    await update.message.reply_text(
        "I'm a texting kind of companion 💬 — *words only* here, no audio or video. "
        "Type to me instead 💋",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------- payments ---

async def on_precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.pre_checkout_query
    try:
        kind, uid_str, minutes_str, _ts = q.invoice_payload.split(":")
        minutes = int(minutes_str)
        stars = next((s for m, s in PLANS if m == minutes), None)
        ok = (
            kind == "session"
            and int(uid_str) == q.from_user.id
            and q.currency == "XTR"
            and stars is not None
            and q.total_amount == stars
        )
    except (ValueError, AttributeError):
        ok = False
    if ok:
        await q.answer(ok=True)
    else:
        await q.answer(ok=False, error_message="Something looks off with this payment — please try again.")


async def on_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.message.successful_payment
    uid = update.effective_user.id
    u = user_state(uid)
    try:
        minutes = int(sp.invoice_payload.split(":")[2])
    except (IndexError, ValueError):
        minutes = PLANS[0][0]
    u["session_until"] = time.time() + minutes * 60
    u["pics_this_session"] = 0
    u["paid_sessions"] = u.get("paid_sessions", 0) + 1
    save_state(STATE)
    p = PERSONAS.get(u["companion"] or "yuki")
    log.info("payment: user=%s amount=%s %s payload=%s", uid, sp.total_amount, sp.currency, sp.invoice_payload)
    await update.message.reply_text(
        f"💋 *Paid!* {p['emoji']} *{p['name']}* is all yours for the next *{minutes} minutes*.\n"
        f"Text me anything… and try /pic if you want to see me 📸",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------- main ----

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN first (see .env.example).")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("switch", cmd_switch))
    app.add_handler(CommandHandler("time", cmd_time))
    app.add_handler(CommandHandler("pic", cmd_pic))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(on_choice))
    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(
        MessageHandler(
            filters.VOICE | filters.VIDEO | filters.PHOTO | filters.Sticker.ALL | filters.ATTACHMENT,
            on_non_text,
        )
    )

    mode = f"single:{COMPANION}" if SINGLE else "duo"
    log.info("Sakura AI starting: mode=%s, plans=%s, image provider=%s", mode, PLANS, IMAGE_PROVIDER)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
