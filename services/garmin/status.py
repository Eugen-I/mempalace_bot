"""Data coverage and import status for the Garmin Telegram screen."""

from __future__ import annotations

import html
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

MIN_SLEEP_DAYS = 14
MIN_HRV_DAYS = 14
MIN_RHR_DAYS = 14
MIN_ACTIVITY_SPAN_DAYS = 28


@dataclass
class DataStatus:
    first_day: str | None = None
    last_day: str | None = None
    days: int = 0
    sleep_days: int = 0
    hrv_days: int = 0
    rhr_days: int = 0
    activity_days: int = 0
    activities: int = 0
    last_activity_day: str | None = None
    last_import_at: str | None = None
    last_import_kind: str | None = None
    sources: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    has_profile: bool = False
    ready_for_plan: bool = False

    @property
    def span_days(self) -> int:
        if not self.first_day or not self.last_day:
            return 0
        try:
            return (
                date.fromisoformat(self.last_day)
                - date.fromisoformat(self.first_day)
            ).days + 1
        except ValueError:
            return 0

    @property
    def coverage_label(self) -> str:
        if not self.days:
            return "нет данных"
        key = min(
            self.sleep_days,
            self.hrv_days,
            self.rhr_days,
        )
        ratio = key / max(self.days, 1)
        if ratio >= 0.8:
            return "высокое"
        if ratio >= 0.5:
            return "среднее"
        return "низкое"


def _count_daily(conn: sqlite3.Connection, user_id: int) -> tuple:
    return conn.execute(
        "SELECT MIN(date), MAX(date), COUNT(*),"
        " SUM(CASE WHEN sleep_hours IS NOT NULL THEN 1 ELSE 0 END),"
        " SUM(CASE WHEN hrv IS NOT NULL THEN 1 ELSE 0 END),"
        " SUM(CASE WHEN resting_hr IS NOT NULL THEN 1 ELSE 0 END)"
        " FROM garmin_daily WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()


def data_status(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: date | None = None,
    has_profile: bool | None = None,
) -> DataStatus:
    """Return coverage plus the minimum-data gate for a safe plan."""
    first, last, days, sleep_days, hrv_days, rhr_days = _count_daily(conn, user_id)
    status = DataStatus(
        first_day=str(first) if first else None,
        last_day=str(last) if last else None,
        days=int(days or 0),
        sleep_days=int(sleep_days or 0),
        hrv_days=int(hrv_days or 0),
        rhr_days=int(rhr_days or 0),
    )

    activity = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT substr(start_time, 1, 10)),"
        " MAX(substr(start_time, 1, 10))"
        " FROM garmin_activities WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    status.activities = int(activity[0] or 0)
    status.activity_days = int(activity[1] or 0)
    status.last_activity_day = str(activity[2]) if activity[2] else None

    run = conn.execute(
        "SELECT kind, finished_at FROM garmin_runs"
        " WHERE user_id = ? AND status IN ('ok', 'partial')"
        " ORDER BY id DESC LIMIT 1",
        (int(user_id),),
    ).fetchone()
    if run is not None:
        status.last_import_kind = str(run["kind"])
        status.last_import_at = str(run["finished_at"]) if run["finished_at"] else None

    status.sources = [
        str(row[0])
        for row in conn.execute(
            "SELECT DISTINCT source FROM garmin_raw_files WHERE user_id = ?"
            " ORDER BY source",
            (int(user_id),),
        ).fetchall()
    ]

    if has_profile is None:
        has_profile = (
            conn.execute(
                "SELECT 1 FROM garmin_profile WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            is not None
        )
    status.has_profile = bool(has_profile)

    missing: list[str] = []
    if status.sleep_days < MIN_SLEEP_DAYS:
        missing.append(f"сон: {status.sleep_days}/{MIN_SLEEP_DAYS} дней")
    if status.hrv_days < MIN_HRV_DAYS:
        missing.append(f"HRV: {status.hrv_days}/{MIN_HRV_DAYS} дней")
    if status.rhr_days < MIN_RHR_DAYS:
        missing.append(f"пульс покоя: {status.rhr_days}/{MIN_RHR_DAYS} дней")
    if status.activities == 0:
        missing.append("нет тренировок за последние 28 дней")
    else:
        reference = today or date.today()
        try:
            last_activity = date.fromisoformat(status.last_activity_day or "")
        except ValueError:
            last_activity = None
        if last_activity is None or (reference - last_activity).days > MIN_ACTIVITY_SPAN_DAYS:
            missing.append("активности: нет свежих данных за 28 дней")
    if not status.has_profile:
        missing.append("профиль не заполнен")
    status.missing = missing
    status.ready_for_plan = not missing
    return status


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def status_text(status: DataStatus) -> str:
    """Compact Russian summary for Telegram."""
    if not status.days:
        period = "данных пока нет"
    else:
        period = f"{status.first_day} — {status.last_day} ({status.days} дн.)"
    lines = [
        "🏃 <b>Garmin</b>",
        f"Данные: {_esc(period)}",
        f"Сон: {status.sleep_days} дн. · HRV: {status.hrv_days} дн. · "
        f"Пульс покоя: {status.rhr_days} дн.",
        f"Тренировки: {status.activities} (дней с активностью: {status.activity_days})",
        f"Coverage: {_esc(status.coverage_label)}",
        f"Профиль: {'заполнен' if status.has_profile else 'не заполнен'}",
        f"Последний импорт: {_esc(status.last_import_at or '—')}",
    ]
    if status.missing:
        lines.append("")
        lines.append("⚠️ Для плана не хватает:")
        lines.extend(f"• {_esc(item)}" for item in status.missing)
    return "\n".join(lines)


def default_start(today: date | None = None) -> date:
    """Next Monday (or today when today is Monday)."""
    current = today or date.today()
    return current + timedelta(days=(7 - current.weekday()) % 7)
