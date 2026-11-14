"""Rolling 365-day retention and explicit extension.

The bot keeps raw exports and derived rows for one year by default.  A user can
extend storage by another year; without an extension old rows and raw objects
are removed on the next import/report/cleanup call.  Plans, check-ins and the
profile are not historical metrics and are left untouched.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .repository import _utcnow

DEFAULT_RETENTION_DAYS = 365
PROMPT_BEFORE_DAYS = 30


@dataclass(frozen=True)
class RetentionStatus:
    retention_days: int
    retention_until: str | None
    cutoff: str
    oldest_day: str | None
    due: bool
    days_left: int | None


@dataclass
class CleanupResult:
    daily: int = 0
    activities: int = 0
    extra_metrics: int = 0
    raw_files: int = 0
    runs: int = 0
    cache: int = 0
    files_removed: int = 0
    pdf_removed: int = 0

    @property
    def total_rows(self) -> int:
        return (
            self.daily
            + self.activities
            + self.extra_metrics
            + self.raw_files
            + self.runs
            + self.cache
        )


def _today(now: date | datetime | None) -> date:
    if now is None:
        return datetime.now(UTC).date()
    if isinstance(now, datetime):
        return now.date()
    return now


def _parse_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _settings_row(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM garmin_settings WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()


def ensure_settings(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> sqlite3.Row:
    conn.execute(
        "INSERT OR IGNORE INTO garmin_settings"
        " (user_id, retention_days, updated_at) VALUES (?, ?, ?)",
        (int(user_id), int(retention_days), _utcnow()),
    )
    conn.commit()
    row = _settings_row(conn, user_id)
    if row is None:  # pragma: no cover - INSERT OR IGNORE guarantees a row
        raise RuntimeError("cannot create Garmin settings")
    return row


def _oldest_day(conn: sqlite3.Connection, user_id: int) -> str | None:
    values = []
    daily = conn.execute(
        "SELECT MIN(date) FROM garmin_daily WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if daily and daily[0]:
        values.append(str(daily[0]))
    activity = conn.execute(
        "SELECT MIN(substr(start_time, 1, 10)) FROM garmin_activities"
        " WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if activity and activity[0]:
        values.append(str(activity[0]))
    return min(values) if values else None


def status(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    default_days: int = DEFAULT_RETENTION_DAYS,
    now: date | datetime | None = None,
) -> RetentionStatus:
    today = _today(now)
    row = ensure_settings(conn, user_id, retention_days=default_days)
    days = int(row["retention_days"] or default_days)
    until = _parse_date(row["retention_until"])
    effective_end = until if until is not None and until >= today else today
    cutoff = (effective_end - timedelta(days=days)).isoformat()
    oldest = _oldest_day(conn, user_id)
    oldest_date = _parse_date(oldest)

    due = False
    if (until is None or until < today) and oldest_date is not None:
        due = oldest_date <= today - timedelta(
            days=max(days - PROMPT_BEFORE_DAYS, 0)
        )
    days_left = (until - today).days if until is not None else None
    return RetentionStatus(
        retention_days=days,
        retention_until=until.isoformat() if until is not None else None,
        cutoff=cutoff,
        oldest_day=oldest,
        due=due,
        days_left=days_left,
    )


def extend(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    days: int = DEFAULT_RETENTION_DAYS,
    now: date | datetime | None = None,
) -> RetentionStatus:
    today = _today(now)
    row = ensure_settings(conn, user_id, retention_days=days)
    current = _parse_date(row["retention_until"])
    base = current if current is not None and current > today else today
    until = base + timedelta(days=days)
    conn.execute(
        "UPDATE garmin_settings SET retention_until = ?, updated_at = ?"
        " WHERE user_id = ?",
        (until.isoformat(), _utcnow(), int(user_id)),
    )
    conn.commit()
    return status(conn, user_id, default_days=days, now=now)


def _delete_raw_objects(raw_dir: Path, user_id: int, shas: list[str]) -> int:
    removed = 0
    user_root = raw_dir / str(int(user_id))
    for sha in shas:
        directory = user_root / sha[:2]
        for path in directory.glob(f"{sha}*"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        try:
            directory.rmdir()
        except OSError:
            pass
    return removed


def _delete_old_files(directory: Path | None, cutoff: date, pattern: str) -> int:
    if directory is None or not directory.is_dir():
        return 0
    removed = 0
    for path in directory.glob(pattern):
        if not path.is_file():
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC).date()
        except OSError:
            continue
        if modified >= cutoff:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def cleanup(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cutoff: date | str,
    raw_dir: str | Path | None = None,
    charts_dir: str | Path | None = None,
    report_dir: str | Path | None = None,
) -> CleanupResult:
    """Delete rows and files older than ``cutoff`` for one user."""
    cutoff_date = _parse_date(cutoff)
    if cutoff_date is None:
        raise ValueError("invalid retention cutoff")
    cutoff_text = cutoff_date.isoformat()
    result = CleanupResult()

    raw_rows = conn.execute(
        "SELECT sha256 FROM garmin_raw_files"
        " WHERE user_id = ? AND substr(imported_at, 1, 10) < ?",
        (int(user_id), cutoff_text),
    ).fetchall()
    shas = [str(row["sha256"]) for row in raw_rows]

    statements = (
        ("daily", "DELETE FROM garmin_daily WHERE user_id = ? AND date < ?"),
        (
            "activities",
            "DELETE FROM garmin_activities"
            " WHERE user_id = ? AND substr(start_time, 1, 10) < ?",
        ),
        (
            "extra_metrics",
            "DELETE FROM garmin_extra_metrics WHERE user_id = ? AND date < ?",
        ),
        (
            "raw_files",
            "DELETE FROM garmin_raw_files"
            " WHERE user_id = ? AND substr(imported_at, 1, 10) < ?",
        ),
        (
            "runs",
            "DELETE FROM garmin_runs"
            " WHERE user_id = ? AND substr(started_at, 1, 10) < ?",
        ),
        (
            "cache",
            "DELETE FROM garmin_analysis_cache"
            " WHERE user_id = ? AND substr(created_at, 1, 10) < ?",
        ),
    )
    for field, sql in statements:
        cursor = conn.execute(sql, (int(user_id), cutoff_text))
        setattr(result, field, max(cursor.rowcount, 0))
    conn.commit()

    if raw_dir is not None and shas:
        result.files_removed += _delete_raw_objects(
            Path(raw_dir).expanduser().resolve(), user_id, shas
        )
    result.pdf_removed += _delete_old_files(
        Path(report_dir).expanduser().resolve() if report_dir else None,
        cutoff_date,
        f"garmin_{int(user_id)}_*.pdf",
    )
    _delete_old_files(
        Path(charts_dir).expanduser().resolve() if charts_dir else None,
        cutoff_date,
        "chart_*.png",
    )
    return result


def apply_rolling(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    default_days: int = DEFAULT_RETENTION_DAYS,
    raw_dir: str | Path | None = None,
    charts_dir: str | Path | None = None,
    report_dir: str | Path | None = None,
    now: date | datetime | None = None,
) -> tuple[RetentionStatus, CleanupResult]:
    current = status(conn, user_id, default_days=default_days, now=now)
    result = cleanup(
        conn,
        user_id,
        cutoff=current.cutoff,
        raw_dir=raw_dir,
        charts_dir=charts_dir,
        report_dir=report_dir,
    )
    return current, result
