"""BDD steps for the local-first Garmin integration.

The scenarios are deliberately hermetic: a temporary SQLite database, a
temporary raw archive, a fake FIT decoder and no network calls.  They exercise
the same service functions that the Telegram handlers use.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz
from behave import given, then, when

from services.garmin.analytics import build_report
from services.garmin.charts import render_charts
from services.garmin.coach import generate_causes_async, validate_coach_output
from services.garmin.db import init_db
from services.garmin.importers.full_export import import_full_export_path
from services.garmin.importers.wellness_fit import import_wellness_path
from services.garmin.models import (
    AvailabilitySlot,
    MedicationEntry,
    UserProfile,
)
from services.garmin.pdf_report import build_pdf
from services.garmin.plan_engine import (
    build_skeleton,
    clarifying_questions,
    validate_plan,
)
from services.garmin.plan_report import build_doctor_pdf, build_plan_pdf
from services.garmin.plan_review import build_review
from services.garmin.raw_store import RawStore
from services.garmin.readiness import assess_readiness
from services.garmin.repository import upsert_daily
from services.garmin.retention import cleanup, extend, status as retention_status
from services.garmin.safety import assess_request, safety_text
from services.garmin.status import DataStatus

USER_ID = 4242


def _g(context) -> SimpleNamespace:
    return context.garmin


def _cleanup(conn, root: Path) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001 - cleanup must not mask scenario failures
        pass
    shutil.rmtree(root, ignore_errors=True)


def _write_zip(path: Path, files: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return path


def _seed_days(
    g: SimpleNamespace,
    days: int,
    *,
    end: date | None = None,
    sleep: float | None = 7.5,
    sleep_score: int | None = 82,
    hrv: int | None = 55,
    rhr: int | None = 55,
    stress: int | None = 30,
    steps: int | None = 9000,
    weight: float | None = 80.0,
) -> None:
    last = end or date.today()
    for offset in range(days):
        day = last - timedelta(days=days - 1 - offset)
        row: dict = {"user_id": USER_ID, "date": day.isoformat()}
        for key, value in (
            ("sleep_hours", sleep),
            ("sleep_score", sleep_score),
            ("hrv", hrv),
            ("resting_hr", rhr),
            ("stress_avg", stress),
            ("steps", steps),
            ("weight_kg", weight),
        ):
            if value is not None:
                row[key] = value
        upsert_daily(g.conn, row, source="wellness_fit")


def _ready_status() -> DataStatus:
    return DataStatus(
        days=30,
        sleep_days=30,
        hrv_days=30,
        rhr_days=30,
        activities=6,
        activity_days=6,
        has_profile=True,
        ready_for_plan=True,
        missing=[],
    )


def _report(g: SimpleNamespace, days: int = 14) -> None:
    if g.report is None:
        g.report = build_report(
            g.conn,
            user_id=USER_ID,
            days=days,
            end_date=date.today(),
        )


def _health_pdf(g: SimpleNamespace, *, coach=None) -> Path:
    _report(g, days=14)
    g.charts = render_charts(g.report, g.tmp / "charts")
    g.pdf = build_pdf(
        g.report,
        g.charts,
        g.tmp / "health.pdf",
        coach=coach,
    )
    return g.pdf


def _pdf_text(path: Path) -> str:
    with fitz.open(path) as document:
        return "\n".join(page.get_text() for page in document)


def _valid_output() -> dict:
    return {
        "summary": "Сон и HRV ниже обычного; это может быть связано с недосыпом "
        "или нагрузкой, но причина не установлена.",
        "possible_causes": [
            {
                "text": "Недосып или поздний отход ко сну.",
                "confidence": "medium",
                "factors": ["sleep_short"],
                "citations": ["E3"],
            },
            {
                "text": "Стресс или нагрузка могли снизить HRV.",
                "confidence": "low",
                "factors": ["hrv_below_baseline"],
                "citations": ["E4"],
            },
        ],
        "what_could_help": [
            {"text": "Стабилизируйте время сна.", "citations": ["E3"]},
            {"text": "Снижайте объём при плохом самочувствии.", "citations": ["E1"]},
        ],
        "questions": ["Были ли алкоголь или болезнь?"],
        "safety_flags": [],
        "citations": ["E3", "E4"],
        "limitations": ["Это не диагноз."],
    }


# ---------------------------------------------------------------------------
# Background


@given("a clean local Garmin store")
def step_clean_store(context) -> None:
    root = Path(tempfile.mkdtemp(prefix="garmin_bdd_"))
    conn = init_db(root / "garmin.sqlite")
    context.add_cleanup(lambda: _cleanup(conn, root))
    context.garmin = SimpleNamespace(
        tmp=root,
        conn=conn,
        user_id=USER_ID,
        raw=RawStore(root / "raw"),
        result=None,
        report=None,
        pdf=None,
        charts={},
        profile=None,
        status=None,
        plan=None,
        review=None,
        readiness=None,
        safety=None,
        coach=None,
        questions=None,
        wellness_zip=None,
        full_zip=None,
        corrupt_zip=None,
        wellness_date=date(2026, 10, 1),
        validation_errors=[],
        plan_pdf=None,
        doctor_pdf=None,
        retention_before=None,
        retention_after=None,
        cleanup_result=None,
    )


# ---------------------------------------------------------------------------
# Given


@given("a wellness export with one day of data")
def step_wellness_export(context) -> None:
    g = _g(context)
    day = g.wellness_date.isoformat()
    g.wellness_zip = _write_zip(
        g.tmp / f"wellness_{day}.zip",
        {f"{day}/wellness.fit": b"FIT-PLACEHOLDER"},
    )
    decoded = {
        "date": day,
        "sleep": {
            "duration_min": 450,
            "start": f"{day}T23:10:00",
            "end": f"{day}T06:40:00",
        },
        "sleep_score": 82,
        "hrv": {
            "last_night_avg": 52,
            "weekly_avg": 55,
            "status": "balanced",
        },
        "stress": {"avg": 28, "max": 60},
        "steps": 9100,
        "rhr_on_device": 54,
        "heart_rate": {"min": 48, "max": 120},
    }
    patcher = patch(
        "services.garmin.importers.wellness_fit.decode_bundle",
        return_value=decoded,
    )
    patcher.start()
    context.add_cleanup(patcher.stop)


@given("a corrupt wellness ZIP")
def step_corrupt_zip(context) -> None:
    g = _g(context)
    g.corrupt_zip = g.tmp / "corrupt.zip"
    g.corrupt_zip.write_bytes(b"this is not a zip archive")


@given("a full export ZIP without activity files")
def step_full_export_zip(context) -> None:
    g = _g(context)
    g.full_zip = _write_zip(
        g.tmp / "full_export.zip",
        {"DI_CONNECT/notes.txt": b"no activity files here"},
    )


@given("only sleep data for fourteen days")
def step_only_sleep(context) -> None:
    g = _g(context)
    _seed_days(
        g,
        14,
        hrv=None,
        rhr=None,
        stress=None,
        steps=None,
        weight=None,
    )


@given("fourteen days of complete Garmin data")
def step_complete_data(context) -> None:
    _seed_days(_g(context), 14)


@given("an incomplete profile and insufficient data")
def step_incomplete_profile(context) -> None:
    g = _g(context)
    g.profile = UserProfile()
    g.status = DataStatus(
        days=2,
        sleep_days=2,
        hrv_days=0,
        rhr_days=0,
        has_profile=True,
        ready_for_plan=False,
        missing=["HRV: 0/14 дней", "сон: 2/14 дней"],
    )


@given("a profile with serotonergic medications")
def step_medicated_profile(context) -> None:
    g = _g(context)
    g.profile = UserProfile(
        primary_goal="fat_loss",
        medications=[
            MedicationEntry(name="миртазапин", dose="15 мг"),
            MedicationEntry(name="венлафаксин", dose="75 мг"),
        ],
        availability=[
            AvailabilitySlot(day_of_week=0, minutes=45),
            AvailabilitySlot(day_of_week=2, minutes=45),
            AvailabilitySlot(day_of_week=4, minutes=45),
        ],
        equipment=["зал", "велосипед"],
    )
    g.status = _ready_status()


@given("a user reports chest pain during exercise")
def step_chest_pain(context) -> None:
    g = _g(context)
    g.request_text = "Во время тренировки появилась боль в груди"


@given("seven days of poor sleep")
def step_poor_sleep(context) -> None:
    _seed_days(
        _g(context),
        7,
        sleep=6.5,
        sleep_score=65,
        hrv=50,
        rhr=58,
        stress=40,
    )


@given("an old and a recent Garmin day")
def step_old_and_recent(context) -> None:
    g = _g(context)
    today = date.today()
    upsert_daily(
        g.conn,
        {
            "user_id": USER_ID,
            "date": (today - timedelta(days=800)).isoformat(),
            "sleep_hours": 7.0,
            "hrv": 50,
            "resting_hr": 56,
        },
        source="wellness_fit",
    )
    upsert_daily(
        g.conn,
        {
            "user_id": USER_ID,
            "date": today.isoformat(),
            "sleep_hours": 7.4,
            "hrv": 54,
            "resting_hr": 55,
        },
        source="wellness_fit",
    )


# ---------------------------------------------------------------------------
# When


@when("I import the wellness export and build the health PDF")
def step_import_and_pdf(context) -> None:
    g = _g(context)
    g.result = import_wellness_path(
        g.wellness_zip,
        conn=g.conn,
        raw_store=g.raw,
        user_id=g.user_id,
        tmp_dir=g.tmp / "tmp",
    )
    g.report = build_report(
        g.conn,
        user_id=g.user_id,
        days=30,
        end_date=g.wellness_date,
    )
    g.charts = render_charts(g.report, g.tmp / "charts")
    g.pdf = build_pdf(g.report, g.charts, g.tmp / "health.pdf")


@when("I import the wellness export twice")
def step_import_twice(context) -> None:
    g = _g(context)
    kwargs = {
        "conn": g.conn,
        "raw_store": g.raw,
        "user_id": g.user_id,
        "tmp_dir": g.tmp / "tmp",
    }
    g.first_result = import_wellness_path(g.wellness_zip, **kwargs)
    g.result = import_wellness_path(g.wellness_zip, **kwargs)


@when("I import the wellness export")
def step_import_wellness(context) -> None:
    g = _g(context)
    g.result = import_wellness_path(
        g.corrupt_zip,
        conn=g.conn,
        raw_store=g.raw,
        user_id=g.user_id,
        tmp_dir=g.tmp / "tmp",
    )


@when("I import the full export")
def step_import_full(context) -> None:
    g = _g(context)
    g.result = import_full_export_path(
        g.full_zip,
        conn=g.conn,
        raw_store=g.raw,
        user_id=g.user_id,
        tmp_dir=g.tmp / "tmp",
    )


@when("I build the health PDF")
def step_build_pdf(context) -> None:
    _health_pdf(_g(context))


@when("I generate AI narration with a valid fake model")
def step_generate_valid_narration(context) -> None:
    g = _g(context)
    _report(g, days=14)

    async def fake_call(model, messages, timeout):
        return json.dumps(_valid_output(), ensure_ascii=False)

    g.coach = asyncio.run(
        generate_causes_async(
            g.conn,
            g.report,
            ai_call=fake_call,
            use_cache=False,
        )
    )


@when("I build the health PDF with the narration")
def step_build_pdf_with_narration(context) -> None:
    g = _g(context)
    _health_pdf(g, coach=g.coach)


@when("I ask for plan clarification")
def step_ask_clarification(context) -> None:
    g = _g(context)
    g.questions = clarifying_questions(g.profile, g.status)


@when("I build the plan and both plan PDFs")
def step_build_plan_and_pdfs(context) -> None:
    g = _g(context)
    g.plan = build_skeleton(g.profile, g.status)
    g.validation_errors = validate_plan(g.plan, g.profile)
    g.plan_pdf = build_plan_pdf(
        g.plan,
        g.profile,
        g.tmp / "plan.pdf",
        include_doctor_sheet=False,
    )
    g.doctor_pdf = build_doctor_pdf(
        g.profile,
        g.tmp / "doctor.pdf",
        plan=g.plan,
    )


@when("I assess the safety of the request")
def step_assess_safety(context) -> None:
    g = _g(context)
    g.safety = assess_request(g.request_text)
    g.plan = None


@when("I assess readiness and run the weekly review")
def step_readiness_and_review(context) -> None:
    g = _g(context)
    g.report = build_report(
        g.conn,
        user_id=g.user_id,
        days=7,
        end_date=date.today(),
    )
    g.readiness = assess_readiness(g.report)
    g.profile = UserProfile(
        primary_goal="fat_loss",
        availability=[
            AvailabilitySlot(day_of_week=0, minutes=45),
            AvailabilitySlot(day_of_week=2, minutes=45),
            AvailabilitySlot(day_of_week=4, minutes=45),
        ],
        equipment=["зал", "велосипед"],
    )
    g.status = _ready_status()
    g.plan = build_skeleton(
        g.profile,
        g.status,
        start_date=date.today(),
    )
    g.review = build_review(
        g.conn,
        g.user_id,
        g.plan,
        g.profile,
        today=date.today(),
    )


@when("I generate AI narration with a broken model")
def step_generate_broken_narration(context) -> None:
    g = _g(context)
    _report(g, days=14)

    async def broken_call(model, messages, timeout):
        raise RuntimeError("local Ollama is down")

    g.coach = asyncio.run(
        generate_causes_async(
            g.conn,
            g.report,
            ai_call=broken_call,
            use_cache=False,
        )
    )
    g.pdf = _health_pdf(g, coach=g.coach)


@when("I check retention, extend it and run cleanup")
def step_retention(context) -> None:
    g = _g(context)
    g.retention_before = retention_status(g.conn, g.user_id)
    g.retention_after = extend(g.conn, g.user_id)
    g.cleanup_result = cleanup(
        g.conn,
        g.user_id,
        cutoff=g.retention_after.cutoff,
    )


# ---------------------------------------------------------------------------
# Then


@then("the import succeeds with one day")
def step_import_ok(context) -> None:
    g = _g(context)
    assert g.result.status == "ok", g.result.issues
    assert len(g.result.days) == 1
    assert g.result.rows_ok == 1


@then("the database contains one daily row")
def step_one_daily_row(context) -> None:
    g = _g(context)
    row = g.conn.execute(
        "SELECT COUNT(*) FROM garmin_daily WHERE user_id = ?",
        (g.user_id,),
    ).fetchone()
    assert row[0] == 1


@then("the health PDF contains charts and key metrics")
def step_pdf_charts(context) -> None:
    g = _g(context)
    assert g.pdf.is_file() and g.pdf.stat().st_size > 0
    text = _pdf_text(g.pdf)
    assert "Динамика показателей" in text
    assert "Сон" in text
    with fitz.open(g.pdf) as document:
        images = sum(len(page.get_images(full=True)) for page in document)
    assert images >= 1
    assert any(path.is_file() for path in g.charts.values())


@then("the second import is skipped")
def step_second_skipped(context) -> None:
    g = _g(context)
    assert g.result.rows_skipped >= 1
    assert g.result.rows_ok == 0


@then("the import fails without daily rows")
def step_import_failed(context) -> None:
    g = _g(context)
    assert g.result.status == "failed"
    assert g.result.issues
    row = g.conn.execute(
        "SELECT COUNT(*) FROM garmin_daily WHERE user_id = ?",
        (g.user_id,),
    ).fetchone()
    assert row[0] == 0


@then("the raw export is preserved")
def step_raw_preserved(context) -> None:
    g = _g(context)
    assert g.result.raw_sha256
    files = [path for path in (g.tmp / "raw").rglob("*") if path.is_file()]
    assert files


@then("the full export reports no activity files")
def step_full_unsupported(context) -> None:
    g = _g(context)
    assert g.result.status == "failed"
    assert any(
        "no activity files" in issue.error for issue in g.result.issues
    )
    row = g.conn.execute(
        "SELECT COUNT(*) FROM garmin_activities WHERE user_id = ?",
        (g.user_id,),
    ).fetchone()
    assert row[0] == 0


@then("the report lists missing inputs")
def step_missing_inputs(context) -> None:
    g = _g(context)
    assert g.report.missing_inputs
    assert any("HRV" in item for item in g.report.missing_inputs)


@then("the health PDF marks missing values with a dash")
def step_pdf_dash(context) -> None:
    text = _pdf_text(_g(context).pdf)
    assert "—" in text
    assert "Покрытие ниже 50%" in text


@then("the health PDF contains the AI cause and citations")
def step_pdf_citations(context) -> None:
    g = _g(context)
    assert g.coach.ok
    assert not validate_coach_output(g.coach.output)
    text = _pdf_text(g.pdf)
    assert "AI-разбор (локальная модель)" in text
    assert "Недосып" in text
    assert "[E3]" in text
    assert "[E4]" in text


@then("the bot asks between one and three questions")
def step_questions(context) -> None:
    questions = _g(context).questions
    assert 1 <= len(questions) <= 3
    assert any("дни" in question for question in questions)
    assert any("HRV" in question for question in questions)


@then("the plan is conservative")
def step_plan_conservative(context) -> None:
    g = _g(context)
    assert g.validation_errors == []
    codes = {flag.code for flag in g.plan.safety_flags}
    assert "serotonergic_combination" in codes
    assert "intensity_caution" in codes
    sessions = [
        session for week in g.plan.weeks for session in week.sessions
    ]
    assert all("темп" not in session.title.lower() for session in sessions)
    strength = [session for session in sessions if session.type == "strength"]
    assert strength
    assert all("RPE 5–6" in (session.intensity or "") for session in strength)


@then("the doctor sheet contains medication details")
def step_doctor_sheet(context) -> None:
    g = _g(context)
    assert g.doctor_pdf.is_file()
    text = _pdf_text(g.doctor_pdf)
    assert "миртазапин" in text
    assert "75 мг" in text
    assert "Вопросы врачу" in text


@then("the plan PDF excludes medication doses")
def step_plan_pdf_no_doses(context) -> None:
    g = _g(context)
    text = _pdf_text(g.plan_pdf)
    assert "намеренно нет доз" in text
    assert "75 мг" not in text


@then("the red flag blocks the plan")
def step_red_flag_blocked(context) -> None:
    g = _g(context)
    assert g.safety.blocked
    assert "chest_pain" in g.safety.codes
    assert g.plan is None


@then("the escalation points to urgent help")
def step_escalation(context) -> None:
    text = safety_text(_g(context).safety)
    assert "Стоп" in text
    assert "103" in text


@then("readiness is amber")
def step_readiness_amber(context) -> None:
    assert _g(context).readiness.level == "amber"


@then("the weekly review recommends a deload")
def step_review_deload(context) -> None:
    g = _g(context)
    assert g.review.decision == "deload"
    assert any(
        change.get("action") == "deload" for change in g.review.changes
    )


@then("the narration is deterministic")
def step_narration_fallback(context) -> None:
    g = _g(context)
    assert g.coach.source == "fallback"
    assert g.coach.output["summary"]
    assert not validate_coach_output(g.coach.output)


@then("the health PDF labels the deterministic analysis")
def step_pdf_deterministic(context) -> None:
    text = _pdf_text(_g(context).pdf)
    assert "Детерминированный разбор (AI недоступен)" in text
    assert "AI-разбор (локальная модель)" not in text


@then("retention is due before the extension")
def step_retention_due(context) -> None:
    assert _g(context).retention_before.due is True


@then("the extension postpones retention")
def step_retention_extended(context) -> None:
    g = _g(context)
    assert g.retention_after.due is False
    assert g.retention_after.retention_until > date.today().isoformat()


@then("cleanup removes the old day and keeps the recent day")
def step_retention_cleanup(context) -> None:
    g = _g(context)
    assert g.cleanup_result.daily >= 1
    dates = {
        str(row["date"])
        for row in g.conn.execute(
            "SELECT date FROM garmin_daily WHERE user_id = ?",
            (g.user_id,),
        ).fetchall()
    }
    assert (date.today() - timedelta(days=800)).isoformat() not in dates
    assert date.today().isoformat() in dates
