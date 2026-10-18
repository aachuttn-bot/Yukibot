# Sakura AI — Telegram AI-companion bot 💋

Two Japanese AI companions (both adults, fictional characters):
- 👩 **Yuki** — 26, female, from Osaka — playful, warm, teasing
- 👨 **Ren** — 28, male, from Tokyo — charming, confident, flirty

**How users experience it**
1. `/start` → 18+ confirmation (self-declared) → pick Yuki or Ren.
   The bot clearly says the companions are **AI characters, not real people**.
2. **First exchange with a companion is FREE** — 1 AI text reply + 1 AI-generated picture.
3. After that: **300 ⭐ = 15 minutes** of unlimited text chat. **Every reply comes as
   text + a fresh AI picture** (up to 10 pictures per session — `PICS_PER_SESSION`);
   `/pic` sends an extra picture on demand.
   **Two-tier pics:** the free trial sends "sample" pics (`TRIAL_IMAGE_*`, free by
   default) while paid sessions use the main provider (`IMAGE_*`) — point the main
   one at a paid realistic endpoint later and paying users get better pics than
   free triallers. Every prompt carries a fixed face description so the companion
   keeps the same face across pictures (as much as the provider allows).
4. **Text only** — voice notes, videos, photos and stickers get a polite "words only" reply.
5. **Reliability** — picture generation and photo sending retry automatically
   (3 attempts) before giving up, so a hiccup doesn't eat the user's reply.

## What you need (all free to start except API usage)

| Thing | Where | Cost |
|---|---|---|
| Bot token | @BotFather on Telegram → `/newbot` | free |
| Hosting | Your own PC (free), or FadeHost paid/swap — see DEPLOY.md | free option |
| Chat AI | **Free by default** (`LLM_PROVIDER=pollinations`, no key — owner pays $0). Or set `LLM_PROVIDER=openai` + your key for better quality. | free by default |
| Images | **Free by default** (`IMAGE_PROVIDER=pollinations`, no key). Or set `IMAGE_PROVIDER=openai` + your key. | free by default |

## Honest notes before you launch

- **Pictures:** the bot sends whatever your image provider returns. Pictures are
  always **AI-generated fictional characters** — never real people's photos
  (using a real person's face/body for a paid chat service without consent is
  off the table). Style is set by `IMAGE_STYLE`: `photorealistic` (photo-like)
  or `anime` (illustrated). Mainstream providers **block explicit sexual
  imagery** — you'll get tasteful/flirty pics, not explicit ones. If you want
  spicier pictures you need a provider that allows adult content (usually a
  self-hosted image model); the bot accepts *any* OpenAI-compatible images
  endpoint, so you can point `IMAGE_API_BASE` at your own server later. No code
  changes needed.
- **Age gate:** the 18+ check is self-declared (a button). Telegram bots can't do
  real ID verification — this is the standard approach, but know its limit.
- **Your costs:** every chat reply calls your LLM API, and with `REPLY_WITH_PIC=true`
  every reply *also* calls your image API. `PICS_PER_SESSION=10` caps pictures per
  session (text keeps flowing after the cap); the free trial is 1 exchange per
  companion per user. Image calls are the expensive part — watch usage in your
  provider dashboard, and lower `PICS_PER_SESSION` or set `REPLY_WITH_PIC=false`
  if the bill gets spicy.
- **Telegram's cut:** Stars payouts go through Telegram's system; check their
  current terms for digital-goods payouts in your region.
- **Keep the token secret:** `TELEGRAM_BOT_TOKEN` lives only in hosting
  environment variables, never in the repo (keep the GitHub repo private).

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
python bot.py
```

## Commands

- `/start` — age confirm + choose companion
- `/switch` — change companion (free trial is per companion)
- `/time` — minutes left in your session
- `/pic` — AI picture of your companion (during a paid session)
- `/stats` — owner-only stats (needs `OWNER_ID`)

## Files

- `bot.py` — the whole bot
- `assets/yuki.png`, `assets/ren.png` — companion portraits shown on selection
- `data/sakura_state.json` — user state (free trials, sessions, history).
  On FadeHost this lives in `/data` so redeploys don't wipe it.
