# Ibu Tracker

A private Telegram bot to track insulin doses, blood glucose (mmol/L), and blood pressure.

## Features in this MVP

- Allowlist-based access by Telegram user ID
- Guided and quick logging for insulin, glucose, and blood pressure
- Daily reminder scheduling for insulin, glucose, and blood pressure
- SQLite local storage
- FastAPI operations API for health and recent logs

## Safety note

This tool is not medical advice and not an emergency service. For dangerous symptoms or severe readings, contact local emergency services immediately.

## Setup

1. Create a virtual environment and activate it.
2. Install dependencies:
   - pip install -e .
3. Copy .env.example to .env and set values.
4. Run the bot:
   - python main.py
5. Run API (optional):
   - uvicorn api.main:app --reload

## Railway deployment

Use a worker-style start command for the bot process:

- `python main.py`

Required environment variables:

- `BOT_TOKEN` (or `TELEGRAM_BOT_TOKEN`)
- `DATABASE_URL` (optional, defaults to SQLite)

Access control variables:

- `ALLOWED_USER_IDS` as comma-separated Telegram IDs (recommended)
- `ALLOWLIST_STRICT=true` to block everyone except `ALLOWED_USER_IDS`

Notes:

- If `ALLOWED_USER_IDS` is empty and `ALLOWLIST_STRICT` is not set, the bot accepts all users.
- `postgres://...` URLs are normalized automatically for SQLAlchemy.
- On startup, the bot clears webhook mode and uses long polling.

## Commands

- /start
- /help
- /log
- /recent
- /remind <insulin|glucose|bp> <HH:MM>
- /list_reminders

## Notes

- Glucose is stored in mmol/L.
- Timezone defaults to Asia/Singapore.
- Reminders are persisted and loaded at startup.
