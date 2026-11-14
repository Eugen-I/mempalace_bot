"""Tests for local Ollama narration, validation, cache and fallback."""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from services.garmin.analytics import build_report
from services.garmin.coach import (
    CoachResult,
    build_payload,
    coach_text,
    generate_causes_async,
    validate_coach_output,
)
from services.garmin.db import init_db
from services.garmin.evidence import CITATION_IDS
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
                "sleep_hours": 6.2 + offset * 0.1,
                "sleep_score": 70,
                "hrv": 42,
                "resting_hr": 58,
                "stress_avg": 55,
                "steps": 4500,
                "weight_kg": 81.0,
            },
            source="manual",
        )
    yield connection
    connection.close()


def _report(conn):
    return build_report(conn, user_id=1, days=7, end_date="2026-10-07")


def _valid_output():
    return {
        "summary": "Сон и HRV выглядят ниже обычного; это может быть связано с "
        "недосыпом или нагрузкой, но причина не установлена.",
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


def test_valid_output_passes_schema():
    assert validate_coach_output(_valid_output()) == []


def test_unknown_citation_is_rejected():
    output = _valid_output()
    output["possible_causes"][0]["citations"] = ["E99"]
    assert validate_coach_output(output)


def test_medication_advice_is_rejected():
    output = _valid_output()
    output["what_could_help"][0]["text"] = "Отмените препарат и измените дозу."
    assert validate_coach_output(output)


def test_payload_is_deidentified(conn):
    payload = build_payload(_report(conn), medications=["mirtazapine"])
    assert "user_id" not in payload
    assert payload["period"]["days"] == 7
    assert payload["medications"] == ["mirtazapine"]
    assert "sleep_hours" in payload["series"]


def test_ollama_output_is_validated_and_cached(conn):
    report = _report(conn)
    calls = {"count": 0}

    async def fake_ai(model, messages, timeout):
        calls["count"] += 1
        return json.dumps(_valid_output())

    first = asyncio.run(
        generate_causes_async(conn, report, ai_call=fake_ai, use_cache=True)
    )
    assert first.source == "ollama"
    assert first.ok
    assert calls["count"] == 1

    async def should_not_be_called(model, messages, timeout):
        raise AssertionError("cache should have been used")

    second = asyncio.run(
        generate_causes_async(conn, report, ai_call=should_not_be_called, use_cache=True)
    )
    assert second.source == "cache"
    assert second.cached
    assert calls["count"] == 1


def test_invalid_citation_falls_back(conn):
    report = _report(conn)
    output = _valid_output()
    output["citations"] = ["E99"]

    async def fake_ai(model, messages, timeout):
        return json.dumps(output)

    result = asyncio.run(
        generate_causes_async(conn, report, ai_call=fake_ai, use_cache=False)
    )
    assert result.source == "fallback"
    assert result.errors


def test_ai_disabled_falls_back(conn):
    result = asyncio.run(
        generate_causes_async(conn, _report(conn), ai_enabled=False, use_cache=False)
    )
    assert result.source == "fallback"
    assert "AI disabled" in result.errors


def test_ai_exception_falls_back(conn):
    async def broken(model, messages, timeout):
        raise RuntimeError("ollama is down")

    result = asyncio.run(
        generate_causes_async(conn, _report(conn), ai_call=broken, use_cache=False)
    )
    assert result.source == "fallback"
    assert "RuntimeError" in result.errors[0]


def test_invalid_primary_uses_fallback_model(conn, monkeypatch):
    report = _report(conn)
    calls = []

    async def fake_default(model, messages, timeout):
        calls.append((model, timeout))
        if model == "primary:latest":
            return "not a json object"
        return json.dumps(_valid_output())

    monkeypatch.setattr("services.garmin.coach._default_ai_call", fake_default)
    result = asyncio.run(
        generate_causes_async(
            conn,
            report,
            model="primary:latest",
            timeout=10,
            fallback_model="fallback:7b",
            fallback_timeout=20,
            use_cache=False,
        )
    )

    assert result.source == "ollama"
    assert result.model == "fallback:7b"
    assert [model for model, _ in calls] == ["primary:latest", "fallback:7b"]
    assert calls[0][1] == 10
    assert calls[1][1] == 20


def test_broken_primary_and_fallback_returns_deterministic(conn, monkeypatch):
    async def fake_default(model, messages, timeout):
        raise RuntimeError(f"{model} is down")

    monkeypatch.setattr("services.garmin.coach._default_ai_call", fake_default)
    result = asyncio.run(
        generate_causes_async(
            conn,
            _report(conn),
            model="primary:latest",
            fallback_model="fallback:7b",
            use_cache=False,
        )
    )

    assert result.source == "fallback"
    assert any("primary:latest" in error for error in result.errors)
    assert any("fallback:7b" in error for error in result.errors)


def test_empty_nested_citations_are_repaired(conn):
    output = _valid_output()
    output["citations"] = []
    output["limitations"] = []
    output["possible_causes"][0]["citations"] = []
    output["what_could_help"][0]["citations"] = []

    async def fake_ai(model, messages, timeout):
        return json.dumps(output)

    result = asyncio.run(
        generate_causes_async(conn, _report(conn), ai_call=fake_ai, use_cache=False)
    )

    assert result.source == "ollama"
    assert result.output["citations"]
    assert result.output["limitations"]
    assert result.output["possible_causes"][0]["citations"]
    assert result.output["what_could_help"][0]["citations"]
    repaired = (
        result.output["citations"]
        + result.output["possible_causes"][0]["citations"]
        + result.output["what_could_help"][0]["citations"]
    )
    assert all(citation in CITATION_IDS for citation in repaired)


def test_custom_ai_call_skips_fallback_model(conn, monkeypatch):
    async def should_not_run(model, messages, timeout):
        raise AssertionError("fallback model must not run with custom ai_call")

    monkeypatch.setattr("services.garmin.coach._default_ai_call", should_not_run)

    async def broken(model, messages, timeout):
        raise RuntimeError("primary failed")

    result = asyncio.run(
        generate_causes_async(
            conn,
            _report(conn),
            ai_call=broken,
            model="primary:latest",
            fallback_model="fallback:7b",
            use_cache=False,
        )
    )

    assert result.source == "fallback"
    assert "RuntimeError" in result.errors[0]


def test_fallback_output_is_cached_under_both_models(conn, monkeypatch):
    report = _report(conn)
    calls = []

    async def fake_default(model, messages, timeout):
        calls.append(model)
        if model == "primary:latest":
            return "not a json object"
        return json.dumps(_valid_output())

    monkeypatch.setattr("services.garmin.coach._default_ai_call", fake_default)
    first = asyncio.run(
        generate_causes_async(
            conn,
            report,
            model="primary:latest",
            fallback_model="fallback:7b",
            use_cache=True,
        )
    )
    assert first.source == "ollama"
    assert first.model == "fallback:7b"
    assert calls == ["primary:latest", "fallback:7b"]

    async def should_not_run(model, messages, timeout):
        raise AssertionError("cache should have been used")

    monkeypatch.setattr("services.garmin.coach._default_ai_call", should_not_run)
    second = asyncio.run(
        generate_causes_async(
            conn,
            report,
            model="primary:latest",
            fallback_model="fallback:7b",
            use_cache=True,
        )
    )
    assert second.source == "cache"
    assert second.cached


def test_coach_text_contains_sections(conn):
    result = CoachResult(source="fallback", output=_valid_output())
    text = coach_text(result)
    assert "Возможные причины" in text
    assert "Что может помочь" in text
    assert "Источники" in text
