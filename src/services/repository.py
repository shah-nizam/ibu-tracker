from datetime import datetime, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select

from db.models import BloodPressureReading, GlucoseReading, InsulinDose, Reminder, User
from db.session import get_session
from core.config import get_settings


class Repository:
    def get_or_create_user(self, telegram_user_id: int, full_name: str) -> User:
        with get_session() as session:
            row = session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            ).scalar_one_or_none()
            if row:
                return row

            user = User(telegram_user_id=telegram_user_id, full_name=full_name)
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def add_glucose(self, telegram_user_id: int, full_name: str, mmol: float, note: str) -> GlucoseReading:
        with get_session() as session:
            user = self._get_or_create_user_in_session(session, telegram_user_id, full_name)
            reading = GlucoseReading(user_id=user.id, mmol=mmol, note=note)
            session.add(reading)
            session.commit()
            session.refresh(reading)
            return reading

    def add_bp(
        self,
        telegram_user_id: int,
        full_name: str,
        systolic: int,
        diastolic: int,
        note: str,
    ) -> BloodPressureReading:
        with get_session() as session:
            user = self._get_or_create_user_in_session(session, telegram_user_id, full_name)
            reading = BloodPressureReading(
                user_id=user.id,
                systolic=systolic,
                diastolic=diastolic,
                note=note,
            )
            session.add(reading)
            session.commit()
            session.refresh(reading)
            return reading

    def add_insulin(self, telegram_user_id: int, full_name: str, units: float, note: str) -> InsulinDose:
        with get_session() as session:
            user = self._get_or_create_user_in_session(session, telegram_user_id, full_name)
            dose = InsulinDose(user_id=user.id, units=units, note=note)
            session.add(dose)
            session.commit()
            session.refresh(dose)
            return dose

    def add_reminder(
        self,
        telegram_user_id: int,
        full_name: str,
        kind: str,
        at_time: time,
        dose_units: Optional[float] = None,
    ) -> Reminder:
        with get_session() as session:
            user = self._get_or_create_user_in_session(session, telegram_user_id, full_name)
            reminder = Reminder(
                user_id=user.id,
                kind=kind,
                time_of_day=at_time,
                dose_units=dose_units,
                active=1,
            )
            session.add(reminder)
            session.commit()
            session.refresh(reminder)
            return reminder

    def list_active_reminders(self, telegram_user_id: int) -> list[Reminder]:
        with get_session() as session:
            user = session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            ).scalar_one_or_none()
            if not user:
                return []

            rows = session.execute(
                select(Reminder)
                .where(Reminder.user_id == user.id, Reminder.active == 1)
                .order_by(Reminder.time_of_day.asc())
            ).scalars()
            return list(rows)

    def list_all_active_reminders(self) -> list[tuple[int, str, Reminder]]:
        with get_session() as session:
            rows = session.execute(
                select(User.telegram_user_id, User.full_name, Reminder)
                .join(Reminder, Reminder.user_id == User.id)
                .where(Reminder.active == 1)
                .order_by(Reminder.time_of_day.asc(), User.full_name.asc())
            ).all()
            return [(row[0], row[1], row[2]) for row in rows]

    def deactivate_reminder(self, reminder_id: int) -> Optional[tuple[int, str, Reminder]]:
        with get_session() as session:
            row = session.execute(
                select(User.telegram_user_id, User.full_name, Reminder)
                .join(Reminder, Reminder.user_id == User.id)
                .where(Reminder.id == reminder_id, Reminder.active == 1)
            ).first()
            if not row:
                return None

            telegram_user_id, full_name, reminder = row
            reminder.active = 0
            session.commit()
            session.refresh(reminder)
            return telegram_user_id, full_name, reminder

    def load_all_active_reminders(self) -> list[tuple[int, Reminder]]:
        with get_session() as session:
            rows = session.execute(
                select(User.telegram_user_id, Reminder)
                .join(Reminder, Reminder.user_id == User.id)
                .where(Reminder.active == 1)
            ).all()
            return [(row[0], row[1]) for row in rows]

    def recent_summary(self, telegram_user_id: int, limit: int = 5) -> dict[str, list[str]]:
        with get_session() as session:
            user = session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            ).scalar_one_or_none()
            if not user:
                return {"glucose": [], "bp": [], "insulin": []}

            glucose_rows = session.execute(
                select(GlucoseReading)
                .where(GlucoseReading.user_id == user.id)
                .order_by(desc(GlucoseReading.created_at))
                .limit(limit)
            ).scalars()

            bp_rows = session.execute(
                select(BloodPressureReading)
                .where(BloodPressureReading.user_id == user.id)
                .order_by(desc(BloodPressureReading.created_at))
                .limit(limit)
            ).scalars()

            insulin_rows = session.execute(
                select(InsulinDose)
                .where(InsulinDose.user_id == user.id)
                .order_by(desc(InsulinDose.created_at))
                .limit(limit)
            ).scalars()

            local_tz = ZoneInfo(get_settings().timezone)

            return {
                "glucose": [
                    f"{self._format_local_time(row.created_at, local_tz)} - {row.mmol:.1f} mmol/L"
                    f"{self._format_note(row.note)}"
                    for row in glucose_rows
                ],
                "bp": [
                    f"{self._format_local_time(row.created_at, local_tz)} - {row.systolic}/{row.diastolic} mmHg"
                    f"{self._format_note(row.note)}"
                    for row in bp_rows
                ],
                "insulin": [
                    f"{self._format_local_time(row.created_at, local_tz)} - {row.units:.1f} units"
                    f"{self._format_note(row.note)}"
                    for row in insulin_rows
                ],
            }

    def recent_summary_all(self, limit: int = 10) -> dict[str, list[str]]:
        with get_session() as session:
            glucose_rows = session.execute(
                select(User.full_name, User.telegram_user_id, GlucoseReading)
                .join(GlucoseReading, GlucoseReading.user_id == User.id)
                .order_by(desc(GlucoseReading.created_at))
                .limit(limit)
            ).all()

            bp_rows = session.execute(
                select(User.full_name, User.telegram_user_id, BloodPressureReading)
                .join(BloodPressureReading, BloodPressureReading.user_id == User.id)
                .order_by(desc(BloodPressureReading.created_at))
                .limit(limit)
            ).all()

            insulin_rows = session.execute(
                select(User.full_name, User.telegram_user_id, InsulinDose)
                .join(InsulinDose, InsulinDose.user_id == User.id)
                .order_by(desc(InsulinDose.created_at))
                .limit(limit)
            ).all()

            local_tz = ZoneInfo(get_settings().timezone)

            return {
                "glucose": [
                    f"{self._user_label(full_name, telegram_user_id)} - "
                    f"{self._format_local_time(row.created_at, local_tz)} - {row.mmol:.1f} mmol/L"
                    f"{self._format_note(row.note)}"
                    for full_name, telegram_user_id, row in glucose_rows
                ],
                "bp": [
                    f"{self._user_label(full_name, telegram_user_id)} - "
                    f"{self._format_local_time(row.created_at, local_tz)} - {row.systolic}/{row.diastolic} mmHg"
                    f"{self._format_note(row.note)}"
                    for full_name, telegram_user_id, row in bp_rows
                ],
                "insulin": [
                    f"{self._user_label(full_name, telegram_user_id)} - "
                    f"{self._format_local_time(row.created_at, local_tz)} - {row.units:.1f} units"
                    f"{self._format_note(row.note)}"
                    for full_name, telegram_user_id, row in insulin_rows
                ],
            }

    def _get_or_create_user_in_session(self, session, telegram_user_id: int, full_name: str) -> User:
        user = session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        ).scalar_one_or_none()
        if user:
            return user

        user = User(telegram_user_id=telegram_user_id, full_name=full_name)
        session.add(user)
        session.flush()
        return user

    def _format_local_time(self, dt: datetime, local_tz: ZoneInfo) -> str:
        # Existing records are stored as UTC-naive timestamps; treat them as UTC and render in local tz.
        utc_dt = dt.replace(tzinfo=timezone.utc)
        return utc_dt.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")

    def _user_label(self, full_name: str, telegram_user_id: int) -> str:
        name = full_name.strip() if full_name else "Unknown"
        return f"{name} ({telegram_user_id})"

    def _format_note(self, note: str) -> str:
        clean = (note or "").strip()
        return f" | note: {clean}" if clean else ""
