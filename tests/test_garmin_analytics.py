"""Tests for deterministic Garmin report analytics."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from services.garmin.analytics import (
    build_report,
    latest_extra_metric,
    workout_comparison,
)
from services.garmin.db import init_db
from services.garmin.repository import upsert_daily, upsert_extra_metric


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


def _seed(conn, start: date, days: int, **values):
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        row = {"user_id": 1, "date": day, **values}
        upsert_daily(conn, row, source="manual")


def _seed_report_data(conn):
    baseline = date(2026, 9, 3)
    _seed(conn, baseline, 28, hrv=60, resting_hr=50, sleep_hours=7.8, stress_avg=25)
    period = date(2026, 10, 1)
    for offset in range(7):
        day = (period + timedelta(days=offset)).isoformat()
        upsert_daily(
            conn,
            {
                "user_id": 1,
                "date": day,
                "sleep_hours": 5.0 if offset < 2 else 7.2,
                "sleep_score": 70,
                "hrv": 40,
                "resting_hr": 58,
                "stress_avg": 60,
                "steps": 3000,
                "weight_kg": 80.0 + offset * 0.4,
            },
            source="manual",
        )


def test_report_series_and_flags(conn):
    _seed_report_data(conn)
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")

    assert report.start == "2026-10-01"
    assert report.end == "2026-10-07"
    assert len(report.dates) == 7
    assert len(report.series["sleep_hours"].values) == 7
    assert report.series["sleep_hours"].avg_7d == pytest.approx(6.57, abs=0.01)
    assert report.series["hrv"].baseline == 60
    assert report.series["hrv"].avg_7d == 40
    assert report.series["resting_hr"].baseline == 50
    assert report.series["weight_kg"].latest == 82.4

    codes = {flag.code for flag in report.flags}
    assert {"sleep_short", "sleep_debt", "hrv_below_baseline", "rhr_above_baseline",
            "stress_high", "steps_low", "weight_change"} <= codes
    assert report.causes
    assert report.confidence in {"medium", "high"}


def test_weekly_summary(conn):
    _seed_report_data(conn)
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")

    assert len(report.weekly) == 2
    assert report.weekly[0].week_start == "2026-09-28"
    assert report.weekly[0].week_end == "2026-10-04"
    assert report.weekly[0].sleep_hours is not None


def test_activity_summary_and_weekly_count(conn):
    _seed_report_data(conn)
    conn.execute(
        "INSERT INTO garmin_activities"
        " (user_id, activity_id, start_time, activity_type, name, duration_min,"
        " training_load, source, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1, "a1", "2026-10-02T10:00:00", "cycling", "Ride", 60, 80, "manual", "x"),
    )
    conn.commit()
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")

    assert report.activities.count == 1
    assert report.activities.total_min == 60
    assert report.activities.by_type == {"cycling": 1}
    assert sum(week.activities for week in report.weekly) == 1


def test_empty_report_is_low_confidence(conn):
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    assert report.confidence == "low"
    assert report.missing_inputs
    assert all(value is None for value in report.series["sleep_hours"].values)
    assert any(flag.code == "no_activities" for flag in report.flags)


def test_invalid_window(conn):
    with pytest.raises(ValueError):
        build_report(conn, user_id=1, days=0)
    with pytest.raises(ValueError):
        build_report(conn, user_id=1, days=4000)


def test_latest_extra_metric(conn):
    upsert_extra_metric(
        conn,
        {
            "user_id": 1,
            "date": "2026-10-01",
            "metric": "distance_m",
            "value": 1234.5,
            "unit": "m",
            "source": "manual",
        },
    )
    assert latest_extra_metric(conn, user_id=1, day="2026-10-01", metric="distance_m") == 1234.5
    assert latest_extra_metric(conn, user_id=1, day="2026-10-01", metric="missing") is None


def test_event_correlations_and_extended_metrics(conn):
    _seed_report_data(conn)
    upsert_daily(
        conn,
        {
            "user_id": 1,
            "date": "2026-10-05",
            "hrv": 36,
            "resting_hr": 61,
            "sleep_hours": 5.8,
            "stress_avg": 65,
            "body_battery_morning": 35,
            "respiration_avg": 17.2,
            "vo2max": 44.0,
        },
        source="manual",
    )
    conn.execute(
        "INSERT INTO garmin_events"
        " (user_id, date, kind, title, notes, severity, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "2026-10-05",
            "illness",
            "Простуда / ОРВИ",
            "насморк",
            "warning",
            "2026-10-05T08:00:00Z",
        ),
    )
    conn.commit()

    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    assert len(report.event_correlations) == 1
    corr = report.event_correlations[0]
    assert corr["kind"] == "illness"
    assert "HRV" in corr["summary"]
    assert "пульс покоя" in corr["summary"]
    assert any(flag.code == "illness_context" for flag in report.flags)
    assert any("Простуда / ОРВИ" in cause for cause in report.causes)
    assert "respiration_avg" in report.extended_metrics
    assert "vo2max" in report.extended_metrics


def test_sleep_architecture_consistency_and_workout_lag(conn):
    _seed_report_data(conn)
    upsert_daily(
        conn,
        {
            "user_id": 1,
            "date": "2026-10-03",
            "sleep_hours": 7.0,
            "sleep_score": 68,
            "sleep_stages_json": '{"deep": 40, "light": 280, "rem": 100, "awake": 25}',
            "sleep_midpoint_min": 180,
            "hrv": 34,
            "resting_hr": 62,
        },
        source="manual",
    )
    upsert_daily(
        conn,
        {
            "user_id": 1,
            "date": "2026-10-04",
            "sleep_hours": 7.5,
            "sleep_score": 82,
            "sleep_stages_json": '{"deep": 45, "light": 300, "rem": 105, "awake": 15}',
            "sleep_midpoint_min": 310,
            "hrv": 48,
            "resting_hr": 54,
        },
        source="manual",
    )
    conn.execute(
        "INSERT INTO garmin_activities"
        " (user_id, activity_id, start_time, activity_type, name, duration_min,"
        " training_load, source, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1, "w1", "2026-10-02T18:00:00", "strength", "Gym", 65, 110, "manual", "x"),
    )
    conn.commit()

    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    arch = report.extended_metrics.get("sleep_architecture")
    assert arch is not None
    assert arch["deep_pct_avg"] < 13.0
    assert arch["rem_pct_avg"] > 20.0
    assert arch["awake_min_avg"] == 20.0

    cons = report.extended_metrics.get("sleep_consistency")
    assert cons is not None
    assert cons["midpoint_stdev_min"] >= 60.0

    lag = report.extended_metrics.get("workout_to_sleep_lag")
    assert lag is not None
    assert lag["hrv_delta"] < 0
    assert "HRV" in lag["summary"]
    assert any("Доля глубокого сна" in c for c in report.causes)
    assert any("Разброс середины сна" in c for c in report.causes)


def test_workout_comparison_against_peers(conn):
    for idx, day in enumerate(("2026-09-20", "2026-09-25", "2026-10-01")):
        conn.execute(
            "INSERT INTO garmin_activities"
            " (user_id, activity_id, start_time, activity_type, name, duration_min,"
            " distance_m, avg_hr, training_load, source, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                f"run_{idx}",
                f"{day}T09:00:00",
                "running",
                "Morning Run",
                40.0 if idx < 2 else 50.0,
                7000.0 if idx < 2 else 9000.0,
                145 if idx < 2 else 152,
                80.0 if idx < 2 else 100.0,
                "manual",
                "x",
            ),
        )
    conn.commit()

    comp = workout_comparison(conn, user_id=1)
    assert comp is not None
    assert comp["activity_type"] == "running"
    assert comp["peer_count"] == 2
    assert comp["duration_delta_pct"] == 25.0
    assert comp["hr_delta_bpm"] == 7.0
    assert comp["load_delta_pct"] == 25.0
    assert "running" in comp["summary"]
