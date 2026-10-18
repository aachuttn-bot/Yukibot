# Yuki 💋 — Telegram AI-companion bot

Yuki, 26, from Osaka 🇯🇵 — playful, warm and teasing. An 18+ AI companion
for flirty adult texting. (AI character, not a real person.)

## How users experience it

1. `/start` → confirm 18+ (self-declared) → straight to Yuki, no choosing.
   Her white-shirt pic arrives first 📸
2. **First exchange is FREE**: one AI text reply + one AI-generated sample pic.
3. After that: **300 ⭐ = 15 minutes** of unlimited text chat. **Every reply
   comes as text + a fresh AI picture** (up to 10 pics/session — `PICS_PER_SESSION`);
   `/pic` sends an extra picture on demand. Free trial uses sample pics
   (`TRIAL_IMAGE_*`); paid sessions use the main provider (`IMAGE_*`).
4. **Text only**: voice/video/photos/stickers get a "words only" reply.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
python bot.py
```

## Commands

- `/start` — age confirm + meet Yuki
- `/time` — minutes left in your session
- `/pic` — AI picture of Yuki (during a paid session)
- `/stats` — owner-only stats (needs `OWNER_ID`)

## Environment

- `TELEGRAM_BOT_TOKEN` — from @BotFather (required)
- `LLM_PROVIDER=pollinations` — free chat text, no key (default)
- `IMAGE_PROVIDER=pollinations` — free pics, no key (default)
- `PRICE_STARS=300`, `SESSION_MINUTES=15`, `PICS_PER_SESSION=10`
- `REPLY_WITH_PIC=true` — every reply includes a fresh AI picture
- `IMAGE_STYLE=photorealistic` — or `anime`

## Files

- `bot.py` — the whole bot (Yuki-only build)
- `assets/yuki.png`, `assets/yuki_selected.png` — her portraits
- `data/sakura_yuki_state.json` — user state (trials, sessions, history).
  On FadeHost this lives in `/data` so redeploys don't wipe it.

## Honest limits

- Pics are AI-generated and tasteful — mainstream image providers block
  explicit imagery.
- The 18+ gate is self-declared, not ID verification.
- Every reply/pic costs API usage on paid providers (free tier = $0).
