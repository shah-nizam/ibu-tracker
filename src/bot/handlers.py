from datetime import datetime

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.auth import allowlisted
from bot.keyboards import metric_keyboard
from services.alerts import bp_warning_text, glucose_warning_text
from services.repository import Repository

repo = Repository()

CHOOSE_METRIC, ENTER_FIRST, ENTER_SECOND, ENTER_NOTE = range(4)


@allowlisted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.full_name if update.effective_user else "there"
    await update.message.reply_text(
        f"Hello {name}. I can track glucose, blood pressure, and insulin. Use /log to add data."
    )


@allowlisted
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commands:\n"
        "/log - Add a new reading\n"
        "/recent - Show recent readings for all users\n"
        "/remind <insulin|glucose|bp> <HH:MM> - Add daily reminder\n"
        "/list_reminders - Show daily reminders for all users"
    )


@allowlisted
async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    summary = repo.recent_summary_all(limit=10)

    def section(title: str, rows: list[str]) -> str:
        if not rows:
            return f"{title}: none"
        return title + ":\n- " + "\n- ".join(rows)

    text = "\n\n".join(
        [
            section("Glucose", summary["glucose"]),
            section("Blood pressure", summary["bp"]),
            section("Insulin", summary["insulin"]),
        ]
    )
    await update.message.reply_text("Recent readings (all users):\n\n" + text)


@allowlisted
async def log_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Select what you want to log:", reply_markup=metric_keyboard())
    return CHOOSE_METRIC


@allowlisted
async def metric_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    _, metric = query.data.split(":", 1)
    context.user_data["metric"] = metric

    if metric == "glucose":
        await query.edit_message_text("Enter glucose in mmol/L, for example 6.2")
        return ENTER_FIRST
    if metric == "bp":
        await query.edit_message_text("Enter systolic BP, for example 128")
        return ENTER_FIRST

    await query.edit_message_text("Enter insulin dose in units, for example 8")
    return ENTER_FIRST


@allowlisted
async def enter_first(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    metric = context.user_data.get("metric")
    text = update.message.text.strip()

    if metric == "glucose":
        try:
            value = float(text)
        except ValueError:
            await update.message.reply_text("Please enter a valid number, for example 6.2")
            return ENTER_FIRST

        context.user_data["glucose"] = value
        await update.message.reply_text("Optional note, or type - to skip")
        return ENTER_NOTE

    if metric == "bp":
        if not text.isdigit():
            await update.message.reply_text("Please enter a valid whole number, for example 128")
            return ENTER_FIRST

        context.user_data["systolic"] = int(text)
        await update.message.reply_text("Enter diastolic BP, for example 82")
        return ENTER_SECOND

    try:
        value = float(text)
    except ValueError:
        await update.message.reply_text("Please enter a valid insulin dose, for example 8")
        return ENTER_FIRST

    context.user_data["insulin"] = value
    await update.message.reply_text("Optional note, or type - to skip")
    return ENTER_NOTE


@allowlisted
async def enter_second(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Please enter a valid whole number, for example 82")
        return ENTER_SECOND

    context.user_data["diastolic"] = int(text)
    await update.message.reply_text("Optional note, or type - to skip")
    return ENTER_NOTE


@allowlisted
async def enter_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    metric = context.user_data.get("metric")
    note = update.message.text.strip()
    if note == "-":
        note = ""

    warning = ""
    if metric == "glucose":
        value = float(context.user_data["glucose"])
        repo.add_glucose(user.id, user.full_name, value, note)
        warning = glucose_warning_text(value)
        summary = f"Saved glucose: {value:.1f} mmol/L"
    elif metric == "bp":
        systolic = int(context.user_data["systolic"])
        diastolic = int(context.user_data["diastolic"])
        repo.add_bp(user.id, user.full_name, systolic, diastolic, note)
        warning = bp_warning_text(systolic, diastolic)
        summary = f"Saved blood pressure: {systolic}/{diastolic} mmHg"
    else:
        units = float(context.user_data["insulin"])
        repo.add_insulin(user.id, user.full_name, units, note)
        summary = f"Saved insulin: {units:.1f} units"

    text = summary
    if warning:
        text += "\n\n" + warning

    await update.message.reply_text(text)
    context.user_data.clear()
    return ConversationHandler.END


@allowlisted
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


def log_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("log", log_entry)],
        states={
            CHOOSE_METRIC: [CallbackQueryHandler(metric_selected, pattern=r"^metric:")],
            ENTER_FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_first)],
            ENTER_SECOND: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_second)],
            ENTER_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_note)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )


def command_handlers() -> list:
    return [
        CommandHandler("start", start),
        CommandHandler("help", help_cmd),
        CommandHandler("recent", recent),
        log_conversation(),
    ]
