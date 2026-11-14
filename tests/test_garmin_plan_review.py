"""Tests for deterministic weekly reviews and confirmed plan adaptation."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from services.garmin.db import init_db
from services.garmin.models import Checkin, UserProfile
from services.garmin.plan_engine import build_skeleton, week_volume
from services.garmin.plan_review import (
    PlanReview,
    apply_review,
    build_review,
    get_review,
    latest_review,
    mark_review_applied,
    review_from_row,
    review_text,
    save_review,
)
from services.garmin.profile_store import save_checkin
from services.garmin.repository import upsert_daily
from services.garmin.status import DataStatus

START = date(2026, 11, 9)
TODAY = date(2026, 11, 10)


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


def _plan(start: date = START):
    return build_skeleton(UserProfile(), _status(), start_date=start)


def _seed_daily(conn, start: date, days: int, **values):
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        upsert_daily(conn, {"user_id": 1, "date": day, **values}, source="manual")


def _activity(conn, activity_id: str, day: date, load: float, minutes: float = 40):
    conn.execute(
        "INSERT INTO garmin_activities"
        " (user_id, activity_id, start_time, activity_type, duration_min,"
        "  training_load, source, updated_at)"
        " VALUES (1, ?, ?, 'cycling', ?, ?, 'manual', 'x')",
        (activity_id, f"{day.isoformat()}T10:00:00", minutes, load),
    )
    conn.commit()


def _review(plan, **kwargs) -> PlanReview:
    values = {
        "plan_id": plan.plan_id,
        "user_id": 1,
        "week_index": 1,
        "review_date": TODAY.isoformat(),
        "readiness": "amber",
        "decision": "reduce",
        "changes": [{"action": "reduce_volume", "percent": 30}],
        "rationale": "низкая приверженность",
        "metrics": {"adherence_pct": 50},
    }
    values.update(kwargs)
    return PlanReview(**values)


# ---------------------------------------------------------------------------
# decision matrix


def test_keep_when_no_signals(conn):
    plan = _plan()
    _seed_daily(conn, TODAY - timedelta(days=34), 35, sleep_hours=7.6, hrv=60, resting_hr=50)

    review = build_review(conn, 1, plan, UserProfile(), today=TODAY)

    assert review.readiness == "green"
    assert review.decision == "keep"
    assert review.changes == []
    assert review.metrics["adherence_pct"] is None


def test_reduce_on_low_adherence_from_checkins(conn):
    plan = _plan()
    save_checkin(
        conn,
        1,
        Checkin(date=TODAY.isoformat(), adherence=False, mood=4),
    )

    review = build_review(conn, 1, plan, UserProfile(), today=TODAY)

    assert review.decision == "reduce"
    assert review.metrics["adherence_pct"] == 0
    assert review.metrics["adherence_source"] == "чек-ины"
    assert review.changes == [
        {"action": "reduce_volume", "percent": 30, "scope": "current_or_next_week"}
    ]


def test_reduce_on_high_acwr(conn):
    plan = _plan()
    # Chronic 21-day load = 210 -> weekly chronic = 70. Current week 140 -> ACWR 2.0.
    for offset in range(21):
        day = TODAY - timedelta(days=27 - offset)
        _activity(conn, f"c{offset}", day, load=10)
    for offset in range(7):
        day = TODAY - timedelta(days=6 - offset)
        _activity(conn, f"w{offset}", day, load=20)

    review = build_review(conn, 1, plan, UserProfile(), today=TODAY)

    assert review.metrics["acwr"] == 2.0
    assert review.decision == "reduce"
    assert any("ACWR 2.00" in reason for reason in [review.rationale])


def test_deload_on_sleep_debt(conn):
    plan = _plan()
    _seed_daily(conn, TODAY - timedelta(days=6), 7, sleep_hours=6.5)

    review = build_review(conn, 1, plan, UserProfile(), today=TODAY)

    assert review.readiness == "amber"
    assert review.metrics["sleep_debt_h"] == 7.0
    assert review.decision == "deload"
    assert review.changes[0]["percent"] == 35


def test_deload_on_red_readiness(conn):
    plan = _plan()
    _seed_daily(conn, TODAY - timedelta(days=6), 7, sleep_hours=5.4)

    review = build_review(conn, 1, plan, UserProfile(), today=TODAY)

    assert review.readiness == "red"
    assert review.decision == "deload"


def test_medical_on_pain(conn):
    plan = _plan()
    save_checkin(
        conn,
        1,
        Checkin(
            date=TODAY.isoformat(),
            pain_score=5,
            pain_location="колено",
            mood=3,
        ),
    )

    review = build_review(conn, 1, plan, UserProfile(), today=TODAY)

    assert review.readiness == "red"
    assert review.decision == "medical"
    assert review.changes == [{"action": "medical_stop", "scope": "now"}]
    assert "боль 5/10" in review.rationale


def test_progress_after_two_green_weeks(conn):
    plan = _plan()
    today = START + timedelta(days=14)
    _seed_daily(
        conn, today - timedelta(days=34), 35, sleep_hours=7.6, hrv=60, resting_hr=50
    )
    for week in (1, 2):
        save_review(
            conn,
            1,
            _review(plan, week_index=week, readiness="green", decision="keep"),
        )
    review = build_review(conn, 1, plan, UserProfile(), today=today)

    assert review.week_index == 3
    assert review.readiness == "green"
    assert review.metrics["green_weeks"] == 2
    assert review.decision == "progress"
    assert review.changes == [
        {"action": "progress", "percent": 5, "scope": "as_planned"}
    ]


def test_one_green_week_is_not_enough_to_progress(conn):
    plan = _plan()
    today = START + timedelta(days=7)
    _seed_daily(
        conn, today - timedelta(days=34), 35, sleep_hours=7.6, hrv=60, resting_hr=50
    )
    save_review(
        conn,
        1,
        _review(plan, week_index=1, readiness="green", decision="keep"),
    )
    review = build_review(conn, 1, plan, UserProfile(), today=today)

    assert review.week_index == 2
    # Two prior reviews are required before the metric is trusted.
    assert review.metrics["green_weeks"] == 0
    assert review.decision == "keep"


# ---------------------------------------------------------------------------
# applying a review


def test_keep_and_progress_return_same_plan():
    plan = _plan()
    assert apply_review(plan, _review(plan, decision="keep")) is plan
    assert apply_review(plan, _review(plan, decision="progress")) is plan


def test_reduce_changes_remaining_sessions_only():
    plan = _plan()
    review = _review(plan, decision="reduce")

    adapted = apply_review(plan, review, today=TODAY)

    assert adapted.plan_id != plan.plan_id
    changed = 0
    for session in adapted.weeks[0].sessions:
        if session.date < TODAY.isoformat() or session.type == "rest":
            continue
        changed += 1
        assert session.title.endswith("· адаптировано")
        assert session.intensity == "Z2/RPE 5–6, без интервалов"
        original = next(
            item for item in plan.weeks[0].sessions if item.date == session.date
        )
        assert session.duration_min == max(15, round((original.duration_min or 0) * 0.7))
    assert changed > 0
    assert adapted.safety_flags[-1].code == "weekly_review"
    assert adapted.safety_flags[-1].severity == "info"
    # The original plan is immutable.
    assert all(
        not session.title.endswith("· адаптировано")
        for session in plan.weeks[0].sessions
    )


def test_deload_reduces_volume_and_marks_sessions():
    plan = _plan()
    review = _review(plan, decision="deload")

    adapted = apply_review(plan, review, today=TODAY)

    assert adapted.plan_id != plan.plan_id
    assert week_volume(adapted.weeks[0]) < week_volume(plan.weeks[0])
    for session in adapted.weeks[0].sessions:
        if session.date < TODAY.isoformat() or session.type == "rest":
            continue
        assert session.title.endswith("· разгрузка")
        assert session.intensity == "RPE 4–5, техника"
    assert "разгрузочная неделя" in adapted.safety_flags[-1].text.lower()


def test_medical_turns_sessions_into_rest_but_keeps_mobility():
    plan = _plan()
    review = _review(plan, decision="medical")

    adapted = apply_review(plan, review, today=TODAY)

    assert adapted.plan_id != plan.plan_id
    converted = 0
    for original, session in zip(plan.weeks[0].sessions, adapted.weeks[0].sessions):
        if original.date < TODAY.isoformat() or original.type == "rest":
            continue
        if original.type == "mobility":
            assert session.title == "Мобилити и прогулка"
            continue
        converted += 1
        assert session.type == "rest"
        assert session.title == "Пауза до консультации врача"
        assert session.duration_min == 0
    assert converted > 0
    assert adapted.safety_flags[-1].severity == "critical"


def test_rest_uses_recovery_title():
    plan = _plan()
    review = _review(plan, decision="rest")

    adapted = apply_review(plan, review, today=TODAY)

    titles = {
        session.title
        for session in adapted.weeks[0].sessions
        if session.date >= TODAY.isoformat()
    }
    assert "Отдых по состоянию" in titles


def test_review_moves_to_next_week_when_current_is_over():
    plan = _plan()
    review = _review(plan, week_index=1, decision="reduce")
    next_monday = START + timedelta(days=7)

    adapted = apply_review(plan, review, today=next_monday)

    assert any(
        session.title.endswith("· адаптировано")
        for session in adapted.weeks[1].sessions
    )
    assert all(
        not session.title.endswith("· адаптировано")
        for session in adapted.weeks[0].sessions
    )


def test_no_remaining_sessions_adds_flag():
    plan = _plan()
    review = _review(plan, week_index=6, decision="reduce")

    adapted = apply_review(plan, review, today=date(2026, 12, 31))

    codes = [flag.code for flag in adapted.safety_flags]
    assert "weekly_review_no_sessions" in codes


# ---------------------------------------------------------------------------
# persistence and text


def test_review_persistence_roundtrip(conn):
    plan = _plan()
    review = _review(plan)

    review_id = save_review(conn, 1, review)
    assert review_id > 0
    assert review.review_id == review_id

    row = get_review(conn, review_id)
    assert row is not None
    loaded = review_from_row(row)
    assert loaded.plan_id == plan.plan_id
    assert loaded.user_id == 1
    assert loaded.week_index == 1
    assert loaded.decision == "reduce"
    assert loaded.changes == [{"action": "reduce_volume", "percent": 30}]
    assert loaded.metrics == {"adherence_pct": 50}
    assert loaded.applied is False


def test_mark_review_applied_updates_column_and_payload(conn):
    plan = _plan()
    review_id = save_review(conn, 1, _review(plan))

    mark_review_applied(conn, review_id)

    row = get_review(conn, review_id)
    assert row["applied"] == 1
    loaded = review_from_row(row)
    assert loaded.applied is True
    assert loaded.changes == [{"action": "reduce_volume", "percent": 30}]


def test_mark_unknown_review_is_noop(conn):
    mark_review_applied(conn, 9999)
    assert get_review(conn, 9999) is None


def test_saved_applied_flag_is_persisted(conn):
    plan = _plan()
    review = _review(plan, applied=True)

    review_id = save_review(conn, 1, review)

    assert get_review(conn, review_id)["applied"] == 1


def test_review_from_row_tolerates_bad_payload(conn):
    conn.execute(
        "INSERT INTO garmin_plan_reviews"
        " (plan_id, user_id, week_index, review_date, readiness, decision,"
        "  changes_json, rationale, applied, created_at)"
        " VALUES ('p1', 1, 1, '2026-11-10', 'green', 'keep', 'not-json',"
        "  'ok', 0, 'x')"
    )
    conn.commit()
    row = conn.execute("SELECT * FROM garmin_plan_reviews").fetchone()

    loaded = review_from_row(row)

    assert loaded.changes == []
    assert loaded.metrics == {}


def test_latest_review_uses_highest_week(conn):
    plan = _plan()
    save_review(conn, 1, _review(plan, week_index=1, decision="keep"))
    save_review(conn, 1, _review(plan, week_index=3, decision="reduce"))
    save_review(conn, 1, _review(plan, week_index=2, decision="deload"))

    row = latest_review(conn, plan.plan_id)

    assert row is not None
    assert row["week_index"] == 3
    assert row["decision"] == "reduce"


def test_review_text_contains_metrics_and_disclaimer():
    review = PlanReview(
        plan_id="p1",
        user_id=1,
        week_index=2,
        review_date="2026-11-10",
        readiness="amber",
        decision="reduce",
        changes=[
            {"action": "reduce_volume", "percent": 30, "scope": "current_or_next_week"}
        ],
        rationale="низкая приверженность",
        metrics={
            "sleep_avg_h": 6.5,
            "hrv_delta_pct": -12.4,
            "rhr_delta": 3.0,
            "adherence_pct": 60,
            "week_minutes": 90,
            "pain": 2,
            "acwr": 1.62,
        },
    )

    text = review_text(review)

    assert "Недельный обзор · неделя 2" in text
    assert "🟡" in text
    assert "сон 6.5 ч" in text
    assert "HRV -12%" in text
    assert "пульс +3" in text
    assert "ACWR): 1.62" in text
    assert "выполнено 60%" in text
    assert "90 мин" in text
    assert "Боль: 2/10" in text
    assert "снизить объём на 30%" in text
    assert "снижение объёма · 30%" in text
    assert "Это вероятная связь, не диагноз" in text
    assert "Без вашего подтверждения план" in text


def test_review_text_medical_and_unknown_readiness():
    review = PlanReview(
        plan_id="p1",
        user_id=1,
        week_index=1,
        review_date="2026-11-10",
        readiness="unknown",
        decision="medical",
        rationale="боль 5/10",
    )

    text = review_text(review)

    assert "⚪" in text
    assert "недостаточно данных" in text
    assert "остановиться и обсудить с врачом" in text
    assert "Почему: боль 5/10." in text
