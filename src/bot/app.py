from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from bot.auth import allowlisted
from bot.handlers import command_handlers
from core.config import get_settings
from db.session import init_db
from services.reminders import load_persisted_reminders, schedule_daily_reminder
from services.repository import Repository

repo = Repository()
logger = logging.getLogger(__name__)


@allowlisted
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /remind <insulin|glucose|bp> <HH:MM> [dose_units]")
        return

    kind = args[0].strip().lower()
    if kind not in {"insulin", "glucose", "bp"}:
        await update.message.reply_text("Kind must be one of: insulin, glucose, bp")
        return

    if kind == "insulin" and len(args) not in {2, 3}:
        await update.message.reply_text("Usage: /remind insulin <HH:MM> [dose_units]")
        return
    if kind != "insulin" and len(args) != 2:
        await update.message.reply_text(f"Usage: /remind {kind} <HH:MM>")
        return

    try:
        parsed = datetime.strptime(args[1].strip(), "%H:%M").time()
    except ValueError:
        await update.message.reply_text("Invalid time format. Use HH:MM, for example 07:30")
        return

    dose_units = None
    if kind == "insulin" and len(args) == 3:
        try:
            dose_units = float(args[2].strip())
            if dose_units <= 0:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("Invalid insulin dose. Use a positive number, for example 10 or 8.5")
            return

    reminder = repo.add_reminder(user.id, user.full_name, kind, parsed, dose_units=dose_units)
    schedule_daily_reminder(
        context.application,
        user.id,
        reminder.id,
        kind,
        parsed,
        dose_units=dose_units,
    )

    if kind == "insulin" and dose_units is not None:
        await update.message.reply_text(
            f"Saved daily insulin reminder at {parsed.strftime('%H:%M')} ({dose_units:g} units)"
        )
    else:
        await update.message.reply_text(f"Saved daily {kind} reminder at {parsed.strftime('%H:%M')}")


@allowlisted
async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reminders = repo.list_all_active_reminders()
    if not reminders:
        await update.message.reply_text("No active reminders.")
        return

    lines = [
        f"- {full_name or 'Unknown'} ({telegram_user_id}): "
        f"{row.kind} at {row.time_of_day.strftime('%H:%M')}"
        f"{f' ({row.dose_units:g} units)' if row.kind == 'insulin' and row.dose_units is not None else ''}"
        for telegram_user_id, full_name, row in reminders
    ]
    await update.message.reply_text("Active reminders (all users):\n" + "\n".join(lines))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = get_settings()
    if not settings.bot_token.strip():
        raise RuntimeError(
            "BOT_TOKEN (or TELEGRAM_BOT_TOKEN) is required. Set it in environment variables."
        )

    init_db()

    _ = ZoneInfo(settings.timezone)

    async def on_startup(app):
        me = await app.bot.get_me()
        logger.info("Bot authenticated as @%s (id=%s)", me.username or "<no-username>", me.id)

        # Polling and webhooks cannot be active at the same time.
        await app.bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook cleared. Starting Telegram long polling.")

    application = ApplicationBuilder().token(settings.bot_token).post_init(on_startup).build()

    for handler in command_handlers():
        application.add_handler(handler)

    application.add_handler(CommandHandler("remind", remind))
    application.add_handler(CommandHandler("list_reminders", list_reminders))

    load_persisted_reminders(application)

    if settings.allowlist:
        logger.info("Allowlist enabled for %d user(s).", len(settings.allowlist))
    elif settings.allowlist_strict:
        logger.warning("ALLOWLIST_STRICT is true but ALLOWED_USER_IDS is empty. All users will be rejected.")
    else:
        logger.warning("ALLOWED_USER_IDS is empty. Bot is accepting all users.")

    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception:
        logger.exception("Bot polling crashed")
        raise
