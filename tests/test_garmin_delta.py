"""Tests for the deterministic data-delta and adaptation flow."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from services.garmin.db import init_db
from services.garmin.delta import (
    apply_delta,
    compute_delta,
    delta_text,
    log_delta,
)
from services.garmin.models import DeltaReport, UserProfile
from services.garmin.plan_engine import build_skeleton
from services.garmin.repository import upsert_daily
from services.garmin.status import DataStatus


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


END = date(2026, 10, 7)
START = END - timedelta(days=41)


def _seed(conn, *, sleep=7.5, hrv=60, rhr=50, weight=80.0, days=42):
    for offset in range(days):
        day = (START + timedelta(days=offset)).isoformat()
        upsert_daily(
            conn,
            {
                "user_id": 1,
                "date": day,
                "sleep_hours": sleep,
                "hrv": hrv,
                "resting_hr": rhr,
                "weight_kg": weight,
            },
            source="manual",
        )


def _set_week(conn, start_offset: int, **values):
    for offset in range(7):
        day = (START + timedelta(days=start_offset + offset)).isoformat()
        upsert_daily(
            conn,
            {"user_id": 1, "date": day, **values},
            source="manual",
        )


def test_delta_keep_when_stable(conn):
    _seed(conn)
    delta = compute_delta(conn, 1, today=END)
    assert delta.recommendation == "keep"
    assert not [m for m in delta.changed_metrics if m.important]


def test_delta_detects_sleep_and_hrv_drop(conn):
    _seed(conn)
    _set_week(conn, 28, sleep_hours=7.4, hrv=60, resting_hr=50)
    _set_week(conn, 35, sleep_hours=6.4, hrv=48, resting_hr=57)
    delta = compute_delta(conn, 1, today=END)
    important = {m.metric for m in delta.changed_metrics if m.important}
    assert "sleep_7d_avg_h" in important
    assert "hrv_7d_delta_pct" in important
    assert "resting_hr_delta" in important
    assert delta.recommendation == "rest"
    assert "sleep_debt" in delta.likely_context


def test_delta_medical_on_pain(conn):
    _seed(conn)
    conn.execute(
        "INSERT INTO garmin_checkins"
        " (user_id, date, kind, pain_score, created_at)"
        " VALUES (1, ?, 'morning', 6, 'x')",
        (END.isoformat(),),
    )
    conn.commit()
    delta = compute_delta(conn, 1, today=END)
    assert delta.recommendation == "medical"
    assert "pain" in delta.likely_context


def test_log_delta(conn):
    _seed(conn)
    delta = compute_delta(conn, 1, today=END)
    log_delta(conn, 1, delta, trigger="import", applied=False)
    row = conn.execute("SELECT * FROM garmin_adaptation_log").fetchone()
    assert row["trigger"] == "import"
    assert row["recommendation"] == "keep"
    assert row["applied"] == 0


def test_apply_delta_reduces_next_three_days():
    profile = UserProfile()
    status = DataStatus(
        days=30,
        sleep_days=30,
        hrv_days=30,
        rhr_days=30,
        activities=5,
        activity_days=5,
        has_profile=True,
        ready_for_plan=True,
    )
    plan = build_skeleton(profile, status, start_date=date(2026, 11, 9))
    delta = DeltaReport(recommendation="reduce", confidence="medium")
    adapted = apply_delta(plan, delta, today=date(2026, 11, 9))
    assert adapted.plan_id != plan.plan_id
    changed = [
        session
        for session in adapted.weeks[0].sessions
        if "адаптировано" in session.title
    ]
    assert len(changed) == 3
    for session in changed:
        original = next(
            item for item in plan.weeks[0].sessions if item.date == session.date
        )
        assert (session.duration_min or 0) <= (original.duration_min or 0)


def test_delta_text_has_no_silent_change_claim(conn):
    _seed(conn)
    delta = compute_delta(conn, 1, today=END)
    text = delta_text(delta)
    assert "Важных изменений нет" in text
    assert "не диагноз" in text
