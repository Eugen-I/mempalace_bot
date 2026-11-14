"""Tests for source-precedence upserts and import bookkeeping."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.garmin.db import init_db
from services.garmin.errors import GarminDatabaseError
from services.garmin.repository import (
    finish_run,
    get_daily,
    get_extra_metrics,
    record_raw_file,
    start_run,
    upsert_daily,
    upsert_extra_metric,
)


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


def _row(**overrides):
    base = {
        "user_id": 1,
        "date": "2026-10-27",
        "sleep_hours": 7.4,
        "hrv": 52,
        "resting_hr": 50,
        "data_sources_json": json.dumps(
            {"sleep_hours": "wellness_fit", "hrv": "wellness_fit", "resting_hr": "wellness_fit"}
        ),
        "quality_flags_json": "[]",
    }
    base.update(overrides)
    return base


def test_insert_and_partial_update(conn):
    assert upsert_daily(conn, _row(), source="wellness_fit") == "inserted"
    assert upsert_daily(
        conn,
        {"user_id": 1, "date": "2026-10-27", "stress_avg": 31},
        source="wellness_fit",
    ) == "updated"

    row = get_daily(conn, 1, "2026-10-27")
    assert row["sleep_hours"] == 7.4
    assert row["stress_avg"] == 31
    sources = json.loads(row["data_sources_json"])
    assert sources["stress_avg"] == "wellness_fit"


def test_lower_priority_source_does_not_overwrite(conn):
    upsert_daily(conn, _row(), source="wellness_fit")
    assert upsert_daily(
        conn,
        {"user_id": 1, "date": "2026-10-27", "sleep_hours": 5.0},
        source="full_export",
    ) == "skipped"

    row = get_daily(conn, 1, "2026-10-27")
    assert row["sleep_hours"] == 7.4
    assert json.loads(row["data_sources_json"])["sleep_hours"] == "wellness_fit"


def test_lower_priority_can_fill_empty_field(conn):
    upsert_daily(conn, _row(), source="wellness_fit")
    assert upsert_daily(
        conn,
        {"user_id": 1, "date": "2026-10-27", "weight_kg": 82.0},
        source="full_export",
    ) == "updated"

    row = get_daily(conn, 1, "2026-10-27")
    assert row["weight_kg"] == 82.0
    assert json.loads(row["data_sources_json"])["weight_kg"] == "full_export"


def test_online_overwrites_wellness(conn):
    upsert_daily(conn, _row(), source="wellness_fit")
    assert upsert_daily(
        conn,
        {"user_id": 1, "date": "2026-10-27", "sleep_hours": 7.1},
        source="online",
    ) == "updated"

    row = get_daily(conn, 1, "2026-10-27")
    assert row["sleep_hours"] == 7.1
    assert json.loads(row["data_sources_json"])["sleep_hours"] == "online"


def test_none_does_not_erase(conn):
    upsert_daily(conn, _row(), source="wellness_fit")
    upsert_daily(
        conn,
        {"user_id": 1, "date": "2026-10-27", "sleep_hours": None},
        source="online",
    )
    assert get_daily(conn, 1, "2026-10-27")["sleep_hours"] == 7.4


def test_quality_flags_are_merged(conn):
    upsert_daily(conn, _row(quality_flags_json='["a"]'), source="wellness_fit")
    upsert_daily(
        conn,
        {"user_id": 1, "date": "2026-10-27", "quality_flags_json": '["b"]'},
        source="wellness_fit",
    )
    flags = json.loads(get_daily(conn, 1, "2026-10-27")["quality_flags_json"])
    assert flags == ["a", "b"]


def test_extra_metric_precedence(conn):
    assert upsert_extra_metric(
        conn,
        {
            "user_id": 1,
            "date": "2026-10-27",
            "metric": "distance_m",
            "value": 5000,
            "unit": "m",
            "source": "wellness_fit",
        },
    ) == "inserted"
    assert upsert_extra_metric(
        conn,
        {
            "user_id": 1,
            "date": "2026-10-27",
            "metric": "distance_m",
            "value": 4000,
            "unit": "m",
            "source": "full_export",
        },
    ) == "skipped"
    assert get_extra_metrics(conn, 1, "2026-10-27")["distance_m"]["value"] == 5000


def test_raw_file_deduplication(conn):
    kwargs = dict(
        user_id=1,
        sha256="a" * 64,
        source="wellness_fit",
        filename="a.fit",
        size_bytes=3,
    )
    assert record_raw_file(conn, **kwargs) is True
    assert record_raw_file(conn, **kwargs) is False
    count = conn.execute("SELECT COUNT(*) FROM garmin_raw_files").fetchone()[0]
    assert count == 1


def test_run_lifecycle(conn):
    run_id = start_run(conn, user_id=1, kind="wellness")
    finish_run(conn, run_id, status="ok", files_total=2, files_ok=2)
    row = conn.execute("SELECT * FROM garmin_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "ok"
    assert row["files_ok"] == 2
    assert row["finished_at"]


def test_unknown_daily_column_raises(conn):
    with pytest.raises(GarminDatabaseError, match="unknown daily"):
        upsert_daily(conn, {"user_id": 1, "date": "2026-10-27", "bogus": 1})
