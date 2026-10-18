# Deploying Sakura AI

## Hosting reality (checked 2026-10-17)

FadeHost allows **exactly one free app per account** — and yours is already
taken by ShortyLinkBot. So Sakura AI can't go on FadeHost's free tier; if you
try, you'll hit a wall asking for a paid tier. Your real options:

1. **Your own PC — free.** Works fine: the bot calls your LLM and image
   providers over the internet, so the host only needs to run the Python
   process. The bot stops when the PC sleeps or the terminal closes.
2. **FadeHost Starter — $2/month.** Only once the bot starts earning.
3. **Swap the free slot.** Give FadeHost's free app to Sakura AI and move
   ShortyLinkBot elsewhere (e.g. your PC).

FadeHost facts (verified 2026-10-16): 256 MB RAM / 0.25 vCPU, 1 GB traffic/day,
polling, deploys straight from GitHub, every push auto-redeploys, always-on
(no sleep timer). Paid tiers: $2/1 bot, $3/2, $6/4.

## 1. Create the bot on Telegram
1. Open Telegram, talk to **@BotFather** → `/newbot`.
2. Name it (e.g. `Sakura AI`) and a username ending in `bot` (e.g. `sakura_ai_companion_bot`).
3. Copy the token. **One token = one bot** — use a NEW bot, not the token of
   your other bots.

## 2. Put the code on GitHub (private repo)
1. On github.com → New repository → name it `sakura-ai-bot` → **Private**.
2. Upload these files from `~/workspace/telegram-ai-companion-bot/`:
   `bot.py`, `requirements.txt`, `.env.example`, `README.md`, `DEPLOY.md`,
   and the `assets/` folder (both portraits).
3. **Do NOT upload** `.env` or any file with real keys. The token and API keys
   go in FadeHost's environment variables only.

## 3. Host the bot (PC, or FadeHost paid/swap — see "Hosting reality" above)
1. FadeHost dashboard → create app → connect your `sakura-ai-bot` repo.
2. Start command: `python bot.py` (or whatever FadeHost asks for the run command).
3. Environment variables — add each of these in the FadeHost dashboard:
   - `TELEGRAM_BOT_TOKEN` = the BotFather token
   - `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`
   - `IMAGE_PROVIDER` = `pollinations` (free, no key) **or** `openai` + `IMAGE_API_KEY`
   - `OWNER_ID` = your Telegram user id (from @userinfobot) — optional, enables /stats
   - `PRICE_STARS=300`, `SESSION_MINUTES=15`, `PICS_PER_SESSION=10`
   - Optional: `TRIAL_IMAGE_PROVIDER` (default `pollinations`) — the free trial's
     sample-pic provider; keep it free while `IMAGE_PROVIDER` can later point at
     a paid realistic endpoint for paying users
   - For the single-companion bots: deploy `yuki_bot.py` / `ren_bot.py` instead
     of `bot.py` (same env vars, own BotFather token per bot)
4. Deploy. Open your bot on Telegram and send `/start`.

On your own PC instead: create a venv, `pip install -r requirements.txt`, copy
`.env.example` to `.env` with your token and keys, then `python bot.py`.
Keep the terminal open — the bot stops when the PC sleeps or the terminal closes.

## 4. Test the money flow yourself
1. `/start` → confirm 18+ → pick Yuki → send one message → you should get a
   text reply **+ 1 picture, free**.
2. Send a second message → you should get a **300 ⭐ invoice**.
3. Pay it with Stars (you'll need Stars in your Telegram account) → chat freely
   for 15 minutes, try `/pic`.
4. After 15 minutes, the next message should ask for payment again.

## If something breaks
- Bot doesn't reply at all → wrong `TELEGRAM_BOT_TOKEN`, or another app/PC is
  running the same token (Telegram allows **one active connection per token** —
  stop the old one).
- Replies but no pictures → image provider/key problem; check logs, or switch
  `IMAGE_PROVIDER=pollinations` (free, no key).
- Weird/blank replies → LLM key or model name wrong; check `LLM_API_BASE`.
