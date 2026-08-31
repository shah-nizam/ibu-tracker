from datetime import time
from zoneinfo import ZoneInfo

from telegram.ext import Application

from core.config import get_settings
from services.repository import Repository

repo = Repository()


def _job_name(user_id: int, reminder_id: int) -> str:
    return f"reminder:{user_id}:{reminder_id}"


async def reminder_callback(context):
    job = context.job
    data = job.data
    kind = data["kind"]
    chat_id = data["chat_id"]

    text_map = {
        "insulin": "Reminder: Please record insulin now.",
        "glucose": "Reminder: Please check and record glucose now.",
        "bp": "Reminder: Please check and record blood pressure now.",
    }
    await context.bot.send_message(chat_id=chat_id, text=text_map.get(kind, "Reminder"))


def schedule_daily_reminder(app: Application, user_id: int, reminder_id: int, kind: str, when: time) -> None:
    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    when_local = when if when.tzinfo else when.replace(tzinfo=tz)
    app.job_queue.run_daily(
        callback=reminder_callback,
        time=when_local,
        days=(0, 1, 2, 3, 4, 5, 6),
        chat_id=user_id,
        name=_job_name(user_id, reminder_id),
        data={"kind": kind, "chat_id": user_id},
        job_kwargs={"misfire_grace_time": 300},
    )


def load_persisted_reminders(app: Application) -> None:
    _ = ZoneInfo(get_settings().timezone)
    for telegram_user_id, reminder in repo.load_all_active_reminders():
        schedule_daily_reminder(
            app=app,
            user_id=telegram_user_id,
            reminder_id=reminder.id,
            kind=reminder.kind,
            when=reminder.time_of_day,
        )
