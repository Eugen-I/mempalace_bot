"""Tests for the Garmin Pydantic contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.garmin.models import (
    AdaptationLogEntry,
    Checkin,
    DeltaMetric,
    DeltaReport,
    MedicationEntry,
    PlanSession,
    PlanWeek,
    TrainingPlan,
    UserProfile,
)


def test_default_profile_is_six_week_weight_strength_cycling():
    profile = UserProfile()

    assert profile.horizon_weeks == 6
    assert profile.primary_goal == "fat_loss"
    assert profile.secondary_goals == ["strength", "cycling", "health"]
    assert profile.goals == ["fat_loss", "strength", "cycling", "health"]


def test_medication_entry_accepts_current_prescriptions():
    meds = [
        MedicationEntry(name="миртазапин", dose="15 мг", timing="на ночь"),
        MedicationEntry(name="венлафаксин", dose="75 мг", timing="утром"),
    ]
    profile = UserProfile(medications=meds)

    assert [m.name for m in profile.medications] == ["миртазапин", "венлафаксин"]


def test_profile_completeness():
    assert UserProfile().completeness == "minimal"
    profile = UserProfile(
        availability=[{"day_of_week": 0, "minutes": 45}],
        equipment=["gym"],
    )
    assert profile.completeness == "complete"


def test_plan_session_and_week():
    session = PlanSession(
        date="2026-10-27",
        type="strength",
        title="Full body A",
        duration_min=45,
        intensity="RPE 7",
    )
    week = PlanWeek(week=1, focus="base", sessions=[session])
    plan = TrainingPlan(
        plan_id="plan-1",
        goal="fat_loss",
        horizon_weeks=6,
        weeks=[week],
    )

    assert plan.weeks[0].sessions[0].title == "Full body A"
    assert plan.horizon_weeks == 6


def test_delta_metric_accepts_from_to_aliases():
    metric = DeltaMetric(metric="sleep_h", **{"from": 7.4, "to": 6.6, "delta": -0.8})
    report = DeltaReport(
        compared_from="2026-10-20",
        compared_to="2026-10-27",
        changed_metrics=[metric],
        recommendation="reduce",
    )

    assert metric.from_value == 7.4
    assert metric.to_value == 6.6
    assert report.recommendation == "reduce"


def test_adaptation_log_entry():
    entry = AdaptationLogEntry(
        date="2026-10-27",
        trigger="import",
        delta=DeltaReport(recommendation="keep"),
        recommendation="keep",
    )
    assert entry.trigger == "import"
    assert entry.applied is False


def test_checkin_rejects_impossible_values():
    with pytest.raises(ValidationError):
        Checkin(date="2026-10-27", sleep_h=30)
    with pytest.raises(ValidationError):
        Checkin(date="2026-10-27", pain_score=11)


def test_legacy_account_record_has_no_password_or_cookie_fields():
    from models.garmin import GarminAccountRecord

    fields = set(GarminAccountRecord.model_fields)
    assert "encrypted_password" not in fields
    assert "encrypted_cookies" not in fields
    assert "encrypted_session_json" in fields
