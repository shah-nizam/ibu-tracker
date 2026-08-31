from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from bot.auth import allowlisted
from bot.handlers import command_handlers
from core.config import get_settings
from db.session import init_db
from services.reminders import load_persisted_reminders, remove_scheduled_reminder, schedule_daily_reminder
from services.repository import Repository

repo = Repository()
logger = logging.getLogger(__name__)


def _user_label(full_name: str, telegram_user_id: int) -> str:
    return f"{(full_name or 'Unknown').strip()} ({telegram_user_id})"


def _parse_appointment_payload(raw: str) -> tuple[str, str, str]:
    parts = [segment.strip() for segment in raw.split("|")]
    title = parts[0] if parts else ""
    location = parts[1] if len(parts) > 1 else ""
    notes = parts[2] if len(parts) > 2 else ""
    return title, location, notes


def _parse_remind_args(args: list[str]) -> tuple[str, datetime.time, float | None] | None:
    if len(args) < 2:
        return None

    kind = args[0].strip().lower()
    if kind not in {"insulin", "glucose", "bp"}:
        return None

    if kind == "insulin" and len(args) not in {2, 3}:
        return None
    if kind != "insulin" and len(args) != 2:
        return None

    try:
        parsed = datetime.strptime(args[1].strip(), "%H:%M").time()
    except ValueError:
        return None

    dose_units = None
    if kind == "insulin" and len(args) == 3:
        try:
            dose_units = float(args[2].strip())
            if dose_units <= 0:
                return None
        except ValueError:
            return None

    return kind, parsed, dose_units


@allowlisted
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    parsed_args = _parse_remind_args(context.args)
    if not parsed_args:
        await update.message.reply_text("Usage: /remind <insulin|glucose|bp> <HH:MM> [dose_units]")
        return

    kind, parsed, dose_units = parsed_args

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
async def remind_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parsed_args = _parse_remind_args(context.args)
    if not parsed_args:
        await update.message.reply_text("Usage: /remind_all <insulin|glucose|bp> <HH:MM> [dose_units]")
        return

    kind, parsed, dose_units = parsed_args
    allowlist = sorted(get_settings().allowlist)
    if not allowlist:
        await update.message.reply_text("Broadcast failed: ALLOWED_USER_IDS is empty.")
        return

    created_count = 0
    for telegram_user_id in allowlist:
        reminder = repo.add_reminder(
            telegram_user_id=telegram_user_id,
            full_name=f"User {telegram_user_id}",
            kind=kind,
            at_time=parsed,
            dose_units=dose_units,
        )
        schedule_daily_reminder(
            context.application,
            telegram_user_id,
            reminder.id,
            kind,
            parsed,
            dose_units=dose_units,
        )
        created_count += 1

    dose_text = f" ({dose_units:g} units)" if kind == "insulin" and dose_units is not None else ""
    await update.message.reply_text(
        f"Broadcast reminder created for {created_count} user(s): {kind} at {parsed.strftime('%H:%M')}{dose_text}"
    )


@allowlisted
async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reminders = repo.list_all_active_reminders()
    if not reminders:
        await update.message.reply_text("No active reminders.")
        return

    lines = [
        f"- #{row.id} {full_name or 'Unknown'} ({telegram_user_id}): "
        f"{row.kind} at {row.time_of_day.strftime('%H:%M')}"
        f"{f' ({row.dose_units:g} units)' if row.kind == 'insulin' and row.dose_units is not None else ''}"
        for telegram_user_id, full_name, row in reminders
    ]
    await update.message.reply_text("Active reminders (all users):\n" + "\n".join(lines))


@allowlisted
async def appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = repo.list_upcoming_appointments(limit=30)
    if not rows:
        await update.message.reply_text("No upcoming appointments.")
        return

    settings = get_settings()
    local_tz = ZoneInfo(settings.timezone)

    lines: list[str] = []
    for telegram_user_id, full_name, row in rows:
        local_dt = row.appointment_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(local_tz)
        lines.append(
            f"- #{row.id} {_user_label(full_name, telegram_user_id)}\n"
            f"  {local_dt.strftime('%a, %d %b %Y %I:%M %p')} - {row.title}"
            f"{f'\n  Location: {row.location}' if row.location else ''}"
            f"{f'\n  Notes: {row.notes}' if row.notes else ''}"
        )

    await update.message.reply_text("Upcoming appointments:\n" + "\n\n".join(lines))


@allowlisted
async def add_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /add_appointment <YYYY-MM-DD> <HH:MM> <title> [| location] [| notes]"
        )
        return

    date_str = context.args[0].strip()
    time_str = context.args[1].strip()
    payload = " ".join(context.args[2:]).strip()
    if not payload:
        await update.message.reply_text("Title is required.")
        return

    try:
        local_naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text("Invalid date/time. Use YYYY-MM-DD HH:MM, for example 2026-09-17 08:20")
        return

    title, location, notes = _parse_appointment_payload(payload)
    if not title:
        await update.message.reply_text("Title is required before optional | location | notes.")
        return

    settings = get_settings()
    local_tz = ZoneInfo(settings.timezone)
    utc_naive = local_naive.replace(tzinfo=local_tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    user = update.effective_user
    created = repo.add_appointment(
        telegram_user_id=user.id,
        full_name=user.full_name,
        appointment_at_utc_naive=utc_naive,
        title=title,
        location=location,
        notes=notes,
    )

    await update.message.reply_text(
        f"Saved appointment #{created.id}: {local_naive.strftime('%Y-%m-%d %H:%M')} - {title}"
    )


@allowlisted
async def delete_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /delete_appointment <appointment_id>")
        return

    try:
        appointment_id = int(context.args[0].strip())
        if appointment_id <= 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("Appointment ID must be a positive number.")
        return

    deleted = repo.deactivate_appointment(appointment_id)
    if not deleted:
        await update.message.reply_text("Appointment not found or already deleted.")
        return

    telegram_user_id, full_name, row = deleted
    settings = get_settings()
    local_tz = ZoneInfo(settings.timezone)
    local_dt = row.appointment_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(local_tz)
    await update.message.reply_text(
        f"Deleted appointment #{row.id}: {_user_label(full_name, telegram_user_id)} - "
        f"{local_dt.strftime('%Y-%m-%d %H:%M')} - {row.title}"
    )


@allowlisted
async def delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /delete_reminder <reminder_id>")
        return

    try:
        reminder_id = int(context.args[0].strip())
        if reminder_id <= 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("Reminder ID must be a positive number. Use /list_reminders to find it.")
        return

    deactivated = repo.deactivate_reminder(reminder_id)
    if not deactivated:
        await update.message.reply_text("Reminder not found or already deleted.")
        return

    telegram_user_id, full_name, reminder = deactivated
    remove_scheduled_reminder(context.application, telegram_user_id, reminder.id)

    dose_text = f" ({reminder.dose_units:g} units)" if reminder.kind == "insulin" and reminder.dose_units is not None else ""
    await update.message.reply_text(
        f"Deleted reminder #{reminder.id}: {full_name or 'Unknown'} ({telegram_user_id}) - "
        f"{reminder.kind} at {reminder.time_of_day.strftime('%H:%M')}{dose_text}"
    )


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
    application.add_handler(CommandHandler("remind_all", remind_all))
    application.add_handler(CommandHandler("list_reminders", list_reminders))
    application.add_handler(CommandHandler("delete_reminder", delete_reminder))
    application.add_handler(CommandHandler("appointment", appointment))
    application.add_handler(CommandHandler("add_appointment", add_appointment))
    application.add_handler(CommandHandler("delete_appointment", delete_appointment))

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
