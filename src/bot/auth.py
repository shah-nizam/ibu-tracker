from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from core.config import get_settings


async def _reject(update: Update) -> None:
    message = "Access denied. Your Telegram ID is not allowlisted."
    if update.effective_message:
        await update.effective_message.reply_text(message)


def allowlisted(handler):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return

        allowlist = get_settings().allowlist
        if not allowlist or user.id not in allowlist:
            await _reject(update)
            return

        return await handler(update, context)

    return wrapper
