"""Tests for Garmin 365-day retention and explicit extension."""

from __future__ import annotations

from datetime import date, datetime, UTC
from pathlib import Path

import pytest

from services.garmin.db import init_db
from services.garmin.raw_store import RawStore
from services.garmin.retention import (
    apply_rolling,
    cleanup,
    ensure_settings,
    extend,
    status,
)


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


def _daily(conn, day: str) -> None:
    conn.execute(
        "INSERT INTO garmin_daily (user_id, date, sleep_hours, updated_at)"
        " VALUES (1, ?, 7.0, ?)",
        (day, f"{day}T12:00:00+00:00"),
    )


def _activity(conn, activity_id: str, day: str) -> None:
    conn.execute(
        "INSERT INTO garmin_activities"
        " (user_id, activity_id, start_time, activity_type, source, updated_at)"
        " VALUES (1, ?, ?, 'cycling', 'full_export', ?)",
        (activity_id, f"{day}T10:00:00", f"{day}T12:00:00+00:00"),
    )


def _extra(conn, day: str, metric: str = "skin_temp") -> None:
    conn.execute(
        "INSERT INTO garmin_extra_metrics"
        " (user_id, date, metric, value, source, updated_at)"
        " VALUES (1, ?, ?, 33.5, 'wellness_fit', ?)",
        (day, metric, f"{day}T12:00:00+00:00"),
    )


def _raw(conn, day: str, sha: str) -> None:
    conn.execute(
        "INSERT INTO garmin_raw_files"
        " (user_id, sha256, source, filename, size_bytes, imported_at)"
        " VALUES (1, ?, 'wellness_fit', 'day.fit', 10, ?)",
        (sha, f"{day}T12:00:00+00:00"),
    )


def _run(conn, day: str, status_value: str = "ok") -> None:
    conn.execute(
        "INSERT INTO garmin_runs (user_id, kind, started_at, status)"
        " VALUES (1, 'wellness', ?, ?)",
        (f"{day}T12:00:00+00:00", status_value),
    )


def _cache(conn, key: str, day: str) -> None:
    conn.execute(
        "INSERT INTO garmin_analysis_cache"
        " (cache_key, user_id, kind, payload_hash, response_json, created_at,"
        "  expires_at)"
        " VALUES (?, 1, 'causes', 'hash', '{}', ?, ?)",
        (key, f"{day}T12:00:00+00:00", f"{day}T12:00:00+00:00"),
    )


def test_rolling_status_and_due_prompt(conn):
    _daily(conn, "2025-11-01")

    current = status(conn, 1, default_days=365, now=date(2026, 11, 4))

    assert current.retention_days == 365
    assert current.retention_until is None
    assert current.cutoff == "2025-11-04"
    assert current.oldest_day == "2025-11-01"
    assert current.due is True
    assert current.days_left is None


def test_young_data_is_not_due(conn):
    _daily(conn, "2026-06-01")

    current = status(conn, 1, default_days=365, now=date(2026, 11, 4))

    assert current.due is False


def test_custom_retention_days(conn):
    ensure_settings(conn, 1, retention_days=30)
    _daily(conn, "2026-09-01")

    current = status(conn, 1, default_days=365, now=date(2026, 11, 4))

    assert current.retention_days == 30
    assert current.cutoff == "2026-10-05"


def test_cleanup_deletes_only_old_rows_and_files(conn, tmp_path):
    raw_dir = tmp_path / "raw"
    store = RawStore(raw_dir)
    old = store.save_bytes(1, b"old", source="wellness_fit", filename="old.fit")
    new = store.save_bytes(1, b"new", source="wellness_fit", filename="new.fit")

    _daily(conn, "2025-01-01")
    _daily(conn, "2026-10-01")
    _activity(conn, "old", "2025-01-02")
    _activity(conn, "new", "2026-10-02")
    _extra(conn, "2025-01-03")
    _extra(conn, "2026-10-03")
    _raw(conn, "2025-01-04", old.sha256)
    _raw(conn, "2026-10-04", new.sha256)
    _run(conn, "2025-01-05")
    _run(conn, "2026-10-05")
    _cache(conn, "old", "2025-01-06")
    _cache(conn, "new", "2026-10-06")
    conn.commit()

    result = cleanup(conn, 1, cutoff="2025-11-04", raw_dir=raw_dir)

    assert result.daily == 1
    assert result.activities == 1
    assert result.extra_metrics == 1
    assert result.raw_files == 1
    assert result.runs == 1
    assert result.cache == 1
    assert result.files_removed == 1
    assert old.path.exists() is False
    assert new.path.exists() is True
    assert conn.execute("SELECT COUNT(*) FROM garmin_daily").fetchone()[0] == 1
    assert conn.execute(
        "SELECT activity_id FROM garmin_activities"
    ).fetchone()[0] == "new"


def test_extend_sets_future_until_and_stops_due_prompt(conn):
    _daily(conn, "2025-11-01")

    extended = extend(conn, 1, days=365, now=date(2026, 11, 4))

    assert extended.retention_until == "2027-11-04"
    assert extended.due is False
    assert extended.days_left == 365
    assert extended.cutoff == "2026-11-04"

    again = extend(conn, 1, days=365, now=date(2026, 11, 4))
    assert again.retention_until == "2028-11-03"


def test_expired_extension_makes_data_due_again(conn):
    ensure_settings(conn, 1)
    _daily(conn, "2025-01-01")
    conn.execute(
        "UPDATE garmin_settings SET retention_until = '2025-06-01'"
        " WHERE user_id = 1"
    )
    conn.commit()

    current = status(conn, 1, default_days=365, now=date(2026, 11, 4))

    assert current.retention_until == "2025-06-01"
    assert current.days_left < 0
    assert current.due is True
    assert current.cutoff == "2025-11-04"


def test_apply_rolling_uses_status_cutoff(conn, tmp_path):
    _daily(conn, "2025-01-01")
    _daily(conn, "2026-10-01")
    conn.commit()

    current, result = apply_rolling(
        conn,
        1,
        default_days=365,
        raw_dir=tmp_path / "raw",
        now=date(2026, 11, 4),
    )

    assert current.cutoff == "2025-11-04"
    assert result.daily == 1
    assert conn.execute("SELECT COUNT(*) FROM garmin_daily").fetchone()[0] == 1


def test_cleanup_removes_old_pdf_but_keeps_recent(conn, tmp_path):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    old_pdf = report_dir / "garmin_1_2025-01-01_7d.pdf"
    new_pdf = report_dir / "garmin_1_2026-10-01_7d.pdf"
    old_pdf.write_bytes(b"old")
    new_pdf.write_bytes(b"new")
    old_ts = datetime(2025, 1, 1, tzinfo=UTC).timestamp()
    new_ts = datetime(2026, 10, 1, tzinfo=UTC).timestamp()
    import os

    os.utime(old_pdf, (old_ts, old_ts))
    os.utime(new_pdf, (new_ts, new_ts))

    result = cleanup(conn, 1, cutoff="2025-11-04", report_dir=report_dir)

    assert result.pdf_removed == 1
    assert old_pdf.exists() is False
    assert new_pdf.exists() is True


def test_invalid_cutoff_is_rejected(conn):
    with pytest.raises(ValueError):
        cleanup(conn, 1, cutoff="not-a-date")
