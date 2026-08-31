from functools import wraps
import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.config import get_settings


logger = logging.getLogger(__name__)


async def _reject(update: Update) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    message = (
        "Access denied. Your Telegram ID is not allowlisted. "
        f"Your ID: {user_id}. Set ALLOWED_USER_IDS to include this value."
    )
    if update.effective_message:
        await update.effective_message.reply_text(message)


def allowlisted(handler):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return

        settings = get_settings()
        allowlist = settings.allowlist

        # Default to open access when no allowlist is configured.
        if not allowlist and not settings.allowlist_strict:
            logger.info("Allowlist bypassed (open mode) for user_id=%s", user.id)
            return await handler(update, context)

        if user.id not in allowlist:
            logger.warning("Blocked user_id=%s by allowlist", user.id)
            await _reject(update)
            return

        logger.info("Allowlisted user_id=%s", user.id)
        return await handler(update, context)

    return wrapper
