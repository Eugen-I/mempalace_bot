"""Tests for encrypted profile storage, check-ins, status and medications."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from services.garmin.crypto import GarminCipher
from services.garmin.db import init_db
from services.garmin.medications import build_layer, enrich, lookup
from services.garmin.models import (
    AvailabilitySlot,
    Checkin,
    MedicationEntry,
    UserProfile,
)
from services.garmin.profile_store import (
    load_profile,
    recent_checkins,
    save_checkin,
    save_profile,
)
from services.garmin.repository import upsert_daily
from services.garmin.status import data_status


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


@pytest.fixture
def cipher():
    return GarminCipher(key=Fernet.generate_key())


def test_profile_roundtrip_is_encrypted(conn, cipher):
    profile = UserProfile(
        primary_goal="fat_loss",
        medications=[MedicationEntry(name="миртазапин")],
        equipment=["gym"],
        availability=[AvailabilitySlot(day_of_week=0, minutes=45)],
    )
    stored = save_profile(conn, 1, profile, cipher=cipher)
    assert stored.version == 1
    assert stored.completeness == "complete"

    loaded = load_profile(conn, 1, cipher=cipher)
    assert loaded is not None
    assert loaded.profile.primary_goal == "fat_loss"
    assert loaded.profile.medications[0].name == "миртазапин"

    raw = conn.execute("SELECT profile_blob FROM garmin_profile").fetchone()[0]
    assert "миртазапин" not in str(raw)

    updated = save_profile(conn, 1, profile, cipher=cipher)
    assert updated.version == 2


def test_checkin_upsert_and_recent(conn):
    checkin = Checkin(date="2026-11-01", kind="morning", sleep_h=6.5, pain_score=2)
    save_checkin(conn, 1, checkin)
    save_checkin(conn, 1, checkin.model_copy(update={"pain_score": 4}))
    rows = recent_checkins(conn, 1)
    assert len(rows) == 1
    assert rows[0].pain_score == 4


def test_status_gate_reports_missing(conn):
    status = data_status(conn, 1)
    assert status.ready_for_plan is False
    assert any("сон" in item for item in status.missing)
    assert any("профиль" in item for item in status.missing)


def test_status_ready(conn):
    start = date.today() - timedelta(days=29)
    for offset in range(30):
        day = (start + timedelta(days=offset)).isoformat()
        upsert_daily(
            conn,
            {
                "user_id": 1,
                "date": day,
                "sleep_hours": 7.5,
                "hrv": 55,
                "resting_hr": 50,
            },
            source="manual",
        )
    conn.execute(
        "INSERT INTO garmin_activities"
        " (user_id, activity_id, start_time, activity_type, source, updated_at)"
        " VALUES (1, 'a1', ?, 'cycling', 'manual', 'x')",
        (date.today().isoformat() + "T10:00:00",),
    )
    conn.commit()
    status = data_status(conn, 1, has_profile=True)
    assert status.sleep_days == 30
    assert status.ready_for_plan is True
    assert status.missing == []


def test_medication_knowledge_and_layer():
    mirt = enrich(MedicationEntry(name="Миртазапин"))
    assert "NaSSA" in (mirt.class_name or "")
    assert mirt.precautions

    venla = enrich(MedicationEntry(name="венлафаксин 75 мг"))
    assert "SNRI" in (venla.class_name or "")

    unknown = enrich(MedicationEntry(name="неизвестное"))
    assert unknown.class_name == "неизвестный препарат"

    layer = build_layer(
        UserProfile(
            medications=[
                MedicationEntry(name="миртазапин"),
                MedicationEntry(name="венлафаксин"),
            ]
        )
    )
    codes = {flag.code for flag in layer.safety_flags}
    assert "serotonergic_combination" in codes
    assert layer.intensity_caution is True
    assert "E9" in layer.citations and "E10" in layer.citations


def test_lookup_does_not_match_random_text():
    assert lookup("совершенно другой препарат").class_name == "неизвестный препарат"


def test_anticoagulant_and_hypoglycemia_layers_are_conservative():
    anticoagulant = lookup("варфарин")
    assert anticoagulant.contact_caution is True
    assert "кровотечение" in anticoagulant.red_flags

    insulin = lookup("инсулин")
    assert insulin.hypoglycemia_caution is True

    layer = build_layer(
        UserProfile(
            medications=[
                MedicationEntry(name="варфарин"),
                MedicationEntry(name="гликлазид"),
            ]
        )
    )
    codes = {flag.code for flag in layer.safety_flags}
    assert "contact_caution" in codes
    assert "hypoglycemia_caution" in codes


def test_medication_sleep_and_emotional_effects_context():
    from services.garmin.medications import medication_ai_context

    layer = build_layer(
        UserProfile(
            medications=[
                MedicationEntry(name="мелатонин"),
                MedicationEntry(name="магний"),
            ]
        )
    )
    assert layer.sleep_effects
    assert layer.emotional_effects

    ctx = medication_ai_context(["мелатонин", "магний"])
    assert ctx["has_medications"] is True
    assert ctx["count"] == 2
    assert len(ctx["classes"]) == 2
    assert ctx["sleep_effects"]
    assert ctx["emotional_effects"]
