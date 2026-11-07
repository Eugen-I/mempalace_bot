"""Tests for readiness, deterministic plans, validation and persistence."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from services.garmin.analytics import build_report
from services.garmin.db import init_db
from services.garmin.models import (
    AvailabilitySlot,
    Checkin,
    MedicationEntry,
    UserProfile,
)
from services.garmin.plan_engine import (
    build_skeleton,
    clarifying_questions,
    plan_summary,
    validate_plan,
    week_volume,
)
from services.garmin.plan_store import latest_plan, save_plan
from services.garmin.readiness import assess_readiness
from services.garmin.repository import upsert_daily
from services.garmin.status import DataStatus


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


def _status(ready: bool = True) -> DataStatus:
    return DataStatus(
        days=30,
        sleep_days=30,
        hrv_days=30,
        rhr_days=30,
        activities=5,
        activity_days=5,
        has_profile=True,
        ready_for_plan=ready,
        missing=[] if ready else ["HRV: 2/14 дней"],
    )


def _profile(**kwargs) -> UserProfile:
    return UserProfile(**kwargs)


def test_six_week_skeleton_is_valid_and_has_rest():
    plan = build_skeleton(_profile(), _status(), start_date=date(2026, 11, 9))
    assert plan.horizon_weeks == 6
    assert len(plan.weeks) == 6
    assert validate_plan(plan, _profile()) == []
    for week in plan.weeks:
        assert len(week.sessions) == 7
        assert any(session.type == "rest" for session in week.sessions)
        assert sum(1 for s in week.sessions if s.type == "strength") == 3


def test_deload_and_consolidation_reduce_volume():
    plan = build_skeleton(_profile(), _status(), start_date=date(2026, 11, 9))
    volumes = [week_volume(week) for week in plan.weeks]
    assert volumes[3] < volumes[2] * 0.75
    assert volumes[5] < volumes[4]
    assert plan.weeks[3].focus == "deload"
    assert plan.weeks[5].focus == "consolidation"


def test_medication_caution_removes_tempo():
    profile = _profile(
        medications=[
            MedicationEntry(name="миртазапин"),
            MedicationEntry(name="венлафаксин"),
        ]
    )
    plan = build_skeleton(profile, _status(), start_date=date(2026, 11, 9))
    assert validate_plan(plan, profile) == []
    for week in plan.weeks:
        for session in week.sessions:
            assert "темп" not in (session.title or "").lower()
            if session.type == "strength":
                assert "5–6" in (session.intensity or "")


def test_validator_catches_missing_rest_and_bad_citation():
    plan = build_skeleton(_profile(), _status(), start_date=date(2026, 11, 9))
    broken = plan.model_copy(deep=True)
    broken.weeks[0].sessions = [
        session for session in broken.weeks[0].sessions if session.type != "rest"
    ]
    broken.citations = ["E1", "NOT_REAL"]
    errors = validate_plan(broken, _profile())
    assert any("7 дней" in error for error in errors)
    assert any("неизвестные источники" in error for error in errors)


def test_plan_store_roundtrip(conn):
    plan = build_skeleton(_profile(), _status(), start_date=date(2026, 11, 9))
    save_plan(conn, 1, plan, profile_version=3, validation_errors=[])
    loaded = latest_plan(conn, 1)
    assert loaded is not None
    assert loaded.plan_id == plan.plan_id
    assert len(loaded.weeks) == 6
    sessions = conn.execute(
        "SELECT COUNT(*) FROM garmin_plan_sessions WHERE plan_id = ?",
        (plan.plan_id,),
    ).fetchone()[0]
    assert sessions == 42


def _seed(conn, start: date, days: int, **values):
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        upsert_daily(conn, {"user_id": 1, "date": day, **values}, source="manual")


def test_readiness_green(conn):
    _seed(conn, date(2026, 9, 3), 28, hrv=60, resting_hr=50, sleep_hours=7.6)
    _seed(conn, date(2026, 10, 1), 7, hrv=60, resting_hr=50, sleep_hours=7.6)
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    result = assess_readiness(report)
    assert result.level == "green"
    assert result.reasons == []


def test_readiness_red_on_short_sleep(conn):
    _seed(conn, date(2026, 9, 3), 28, hrv=60, resting_hr=50, sleep_hours=7.6)
    _seed(conn, date(2026, 10, 1), 7, hrv=60, resting_hr=50, sleep_hours=5.4)
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    result = assess_readiness(report)
    assert result.level == "red"
    assert any("6 ч" in reason for reason in result.reasons)


def test_readiness_red_on_pain(conn):
    _seed(conn, date(2026, 9, 3), 28, hrv=60, resting_hr=50, sleep_hours=7.6)
    _seed(conn, date(2026, 10, 1), 7, hrv=60, resting_hr=50, sleep_hours=7.6)
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    result = assess_readiness(
        report, checkin=Checkin(date="2026-10-07", pain_score=5, pain_location="колено")
    )
    assert result.level == "red"
    assert any("колено" in reason for reason in result.reasons)


def test_plan_summary_mentions_weeks():
    plan = build_skeleton(_profile(), _status(), start_date=date(2026, 11, 9))
    text = plan_summary(plan)
    assert "Неделя 1" in text
    assert "Неделя 6" in text


def test_clarifying_questions_are_limited_and_actionable():
    profile = _profile(
        medications=[MedicationEntry(name="миртазапин")],
    )
    status = _status(ready=False)
    status.missing = ["HRV: 2/14 дней", "сон: 3/14 дней"]
    questions = clarifying_questions(profile, status)
    assert 1 <= len(questions) <= 3
    assert any("дни" in question for question in questions)
    assert any("HRV" in question for question in questions)


def test_clarifying_questions_empty_for_complete_profile():
    profile = _profile(
        availability=[AvailabilitySlot(day_of_week=0, minutes=45)],
        equipment=["зал"],
    )
    assert clarifying_questions(profile, _status()) == []


def test_post_illness_skeleton_deloads_week1():
    normal = build_skeleton(
        _profile(),
        _status(),
        start_date=date(2026, 11, 9),
        today=date(2026, 11, 6),
    )
    illness_events = [
        {
            "date": "2026-11-04",
            "kind": "illness",
            "title": "Простуда / ОРВИ",
            "severity": "info",
        }
    ]
    post_ill = build_skeleton(
        _profile(),
        _status(),
        start_date=date(2026, 11, 9),
        today=date(2026, 11, 6),
        events=illness_events,
    )
    assert post_ill.weeks[0].focus == "deload"
    assert week_volume(post_ill.weeks[0]) < week_volume(normal.weeks[0])
    assert any(flag.code == "post_illness_week1" for flag in post_ill.safety_flags)
    assert validate_plan(post_ill, _profile()) == []


def test_readiness_reflects_illness_and_recovery(conn):
    _seed(conn, date(2026, 9, 3), 28, hrv=60, resting_hr=50, sleep_hours=7.6)
    _seed(conn, date(2026, 10, 1), 7, hrv=60, resting_hr=50, sleep_hours=7.6)
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")

    active = assess_readiness(
        report,
        events=[{"date": "2026-10-06", "kind": "illness", "title": "ОРВИ", "severity": "warning"}],
    )
    assert active.level == "red"
    assert any("ОРВИ" in r for r in active.reasons)

    recovered = assess_readiness(
        report,
        events=[{"date": "2026-10-06", "kind": "illness", "title": "ОРВИ", "severity": "info"}],
    )
    assert recovered.level == "amber"
    assert any("восстановление после болезни" in r for r in recovered.reasons)
