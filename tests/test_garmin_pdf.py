"""Tests for charts and the Garmin PDF report."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import fitz
import pytest

from services.garmin.analytics import build_report
from services.garmin.charts import render_charts
from services.garmin.coach import CoachResult
from services.garmin.db import init_db
from services.garmin.pdf_report import build_pdf
from services.garmin.repository import upsert_daily


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    for offset in range(7):
        day = (date(2026, 10, 1) + timedelta(days=offset)).isoformat()
        upsert_daily(
            connection,
            {
                "user_id": 1,
                "date": day,
                "sleep_hours": 6.8 + offset * 0.1,
                "sleep_score": 72 + offset,
                "hrv": 45 + offset,
                "resting_hr": 55 - offset,
                "stress_avg": 42 - offset,
                "steps": 7000 + offset * 100,
                "weight_kg": 80.0 - offset * 0.05,
            },
            source="manual",
        )
    yield connection
    connection.close()


def test_render_charts_creates_pngs(conn, tmp_path):
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    charts = render_charts(report, tmp_path / "charts", dpi=100)

    assert "sleep_hours" in charts
    assert "hrv" in charts
    assert "resting_hr" in charts
    assert "weight_kg" in charts
    for path in charts.values():
        assert path.is_file()
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_build_pdf_with_charts(conn, tmp_path):
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    charts = render_charts(report, tmp_path / "charts", dpi=100)
    pdf = build_pdf(report, charts, tmp_path / "report.pdf")

    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")
    assert pdf.stat().st_size > 10_000

    with fitz.open(pdf) as document:
        assert document.page_count >= 3
        text = "\n".join(page.get_text() for page in document)
    assert "Garmin" in text
    assert "2026-10-01" in text
    assert "Все дни периода" in text


def test_build_pdf_without_charts(conn, tmp_path):
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    pdf = build_pdf(report, {}, tmp_path / "report_no_charts.pdf")

    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")


def test_build_pdf_with_coach_section(conn, tmp_path):
    report = build_report(conn, user_id=1, days=7, end_date="2026-10-07")
    output = {
        "summary": "Сон и HRV ниже обычного; это может быть связано с недосыпом.",
        "possible_causes": [
            {
                "text": "Недосып или поздний отход ко сну.",
                "confidence": "medium",
                "factors": ["sleep_short"],
                "citations": ["E3"],
            }
        ],
        "what_could_help": [
            {"text": "Стабилизируйте время сна.", "citations": ["E3"]}
        ],
        "questions": ["Были ли алкоголь или болезнь?"],
        "safety_flags": [],
        "citations": ["E3"],
        "limitations": ["Это не диагноз."],
    }
    coach = CoachResult(source="fallback", output=output)
    pdf = build_pdf(report, {}, tmp_path / "report_coach.pdf", coach=coach)

    with fitz.open(pdf) as document:
        text = "\n".join(page.get_text() for page in document)
    assert "Детерминированный разбор" in text
    assert "Источники" in text


@pytest.mark.parametrize("days", [7, 30, 90, 365])
def test_pdf_common_windows(conn, tmp_path, days):
    report = build_report(conn, user_id=1, days=days, end_date="2026-10-07")
    charts = render_charts(report, tmp_path / f"charts_{days}", dpi=80)
    pdf = build_pdf(report, charts, tmp_path / f"report_{days}.pdf")

    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")
    assert pdf.stat().st_size > 10_000
