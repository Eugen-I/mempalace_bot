"""Tests for the training-plan PDF and the standalone doctor sheet."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import fitz

from services.garmin.models import Checkin, Event, MedicationEntry, UserProfile
from services.garmin.plan_engine import build_skeleton
from services.garmin.plan_report import (
    DISCLAIMER,
    DOCTOR_TITLE,
    PLAN_TITLE,
    RED_FLAGS,
    build_doctor_pdf,
    build_plan_pdf,
)
from services.garmin.status import DataStatus


def _status() -> DataStatus:
    return DataStatus(
        days=30,
        sleep_days=30,
        hrv_days=30,
        rhr_days=30,
        activities=5,
        activity_days=5,
        has_profile=True,
        ready_for_plan=True,
        missing=[],
    )


def _profile(**kwargs) -> UserProfile:
    return UserProfile(**kwargs)


def _plan(profile: UserProfile | None = None):
    return build_skeleton(profile or _profile(), _status(), start_date=date(2026, 11, 9))


def _text(path: Path) -> str:
    with fitz.open(path) as document:
        raw = "\n".join(page.get_text() for page in document)
    # PDF line wrapping differs between platforms/font metrics; compare words.
    return " ".join(raw.split())


def test_plan_pdf_contains_sections_and_citations(tmp_path):
    profile = _profile(
        medications=[
            MedicationEntry(
                name="миртазапин",
                dose="15 мг",
                frequency="на ночь",
            ),
            MedicationEntry(name="венлафаксин", dose="75 мг"),
        ]
    )
    plan = _plan(profile)

    output = tmp_path / "plan.pdf"
    pdf = build_plan_pdf(
        plan,
        profile,
        output,
        include_doctor_sheet=False,
    )

    assert pdf == output
    assert pdf.read_bytes().startswith(b"%PDF")
    text = _text(pdf)
    assert PLAN_TITLE in text
    assert "Обзор недель" in text
    assert "Первая неделя подробно" in text
    assert "Правила адаптации" in text
    assert "Препараты: только предосторожности" in text
    assert "Вопросы врачу" in text
    assert "Красные флаги" in text
    assert RED_FLAGS.split(",")[0] in text
    assert "Источники" in text
    assert "[E1]" in text
    assert DISCLAIMER in text
    assert "локальные данные" in text
    # The plan PDF must never contain doses, even though the doctor sheet does.
    assert "15 мг" not in text
    assert "75 мг" not in text


def test_plan_pdf_without_medications_has_no_medication_section(tmp_path):
    plan = _plan()

    pdf = build_plan_pdf(
        plan,
        _profile(),
        tmp_path / "plan_no_meds.pdf",
        include_doctor_sheet=False,
    )
    text = _text(pdf)

    assert "Препараты: только предосторожности" not in text
    assert "Обзор недель" in text


def test_plan_pdf_can_include_doctor_sheet(tmp_path):
    plan = _plan()
    profile = _profile(medications=[MedicationEntry(name="миртазапин", dose="15 мг")])

    pdf = build_plan_pdf(plan, profile, tmp_path / "plan_with_doctor.pdf")
    text = _text(pdf)

    assert PLAN_TITLE in text
    assert DOCTOR_TITLE in text
    assert "15 мг" in text


def test_plan_pdf_creates_parent_directory(tmp_path):
    output = tmp_path / "nested" / "reports" / "plan.pdf"

    pdf = build_plan_pdf(
        _plan(),
        _profile(),
        output,
        include_doctor_sheet=False,
    )

    assert pdf.is_file()
    assert output.parent.is_dir()


def test_doctor_pdf_contains_meds_symptoms_and_questions(tmp_path):
    profile = _profile(
        primary_goal="fat_loss",
        conditions=["гипертония"],
        injuries=["колено"],
        doctor_clearance="yes",
        supplements=["витамин D"],
        medications=[
            MedicationEntry(
                name="миртазапин",
                dose="15 мг",
                frequency="на ночь",
                reason="сон",
            )
        ],
    )
    checkins = [
        Checkin(
            date="2026-11-01",
            pain_score=3,
            pain_location="колено",
            soreness=5,
            stress=4,
            mood=2,
        ),
        Checkin(date="2026-11-02", sleep_h=7.5, mood=4),
    ]
    events = [
        Event(
            date="2026-11-03",
            kind="illness",
            title="простуда",
            severity="warning",
        ),
        Event(
            date="2026-11-04",
            kind="travel",
            title="поездка",
            severity="info",
        ),
    ]

    pdf = build_doctor_pdf(
        profile,
        tmp_path / "doctor.pdf",
        plan=_plan(profile),
        checkins=checkins,
        events=events,
    )

    assert pdf.read_bytes().startswith(b"%PDF")
    text = _text(pdf)
    assert DOCTOR_TITLE in text
    assert "Профиль" in text
    assert "снижение веса" in text
    assert "Состояния (со слов пользователя)" in text
    assert "гипертония" in text
    assert "Травмы/ограничения (со слов пользователя)" in text
    assert "Допуск врача: есть" in text
    assert "Текущие препараты и БАДы" in text
    assert "миртазапин" in text
    assert "15 мг" in text
    assert "на ночь" in text
    assert "NaSSA" in text
    assert "БАДы: витамин D" in text
    assert "Симптомы и события за период" in text
    assert "боль 3/10 (колено)" in text
    assert "болезненность 5/10" in text
    assert "стресс 4/5" in text
    assert "настроение 2/5" in text
    assert "простуда" in text
    assert "поездка" not in text
    assert "План нагрузок вкратце" in text
    assert "Вопросы врачу" in text
    assert "Влияет ли текущая комбинация препаратов" in text
    assert "Красные флаги" in text
    assert DISCLAIMER in text
    assert "Не является диагнозом или назначением" in text


def test_doctor_pdf_without_profile_data_uses_placeholders(tmp_path):
    pdf = build_doctor_pdf(_profile(), tmp_path / "doctor_empty.pdf")
    text = _text(pdf)

    assert "Не указаны." in text
    assert "Значимых симптомов в чек-инах и событиях нет." in text
    assert "План нагрузок вкратце" not in text
    assert "Вопросы врачу" in text
    assert DISCLAIMER in text


def test_doctor_pdf_red_flags_are_listed(tmp_path):
    pdf = build_doctor_pdf(
        _profile(medications=[MedicationEntry(name="венлафаксин")]),
        tmp_path / "doctor_flags.pdf",
    )
    text = _text(pdf)

    for part in ("боль в груди", "обморок", "суицидальные мысли"):
        assert part in text


def test_doctor_pdf_does_not_prescribe_doses(tmp_path):
    profile = _profile(
        medications=[MedicationEntry(name="венлафаксин", dose="75 мг")]
    )
    pdf = build_doctor_pdf(profile, tmp_path / "doctor_no_advice.pdf")
    text = _text(pdf)

    assert "75 мг" in text
    for phrase in ("увеличьте дозу", "снизьте дозу", "прекратите приём"):
        assert phrase not in text.lower()
