"""Tests for the Garmin activities CSV importer."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.garmin.db import init_db
from services.garmin.importers.activities_csv import import_activities_csv
from services.garmin.raw_store import RawStore
from services.garmin.repository import get_activity, upsert_activity


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


def _csv(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _import(conn, tmp_path: Path, path: Path):
    return import_activities_csv(
        path,
        conn=conn,
        raw_store=RawStore(tmp_path / "raw"),
        user_id=1,
    )


def test_english_headers_import_activities(conn, tmp_path):
    path = _csv(
        tmp_path / "Activities.csv",
        "Activity ID,Activity Type,Date,Title,Distance,Calories,Time,"
        "Avg HR,Max HR,Activity Training Load,Aerobic TE,Anaerobic TE,"
        "Total Ascent\n"
        "12345,Cycling,2026-10-01 07:30:00,Morning ride,25.4,600,"
        "1:00:00,135,170,85.5,3.2,0.4,120\n"
        "12346,Strength Training,2026-10-02 18:00:00,Gym,,250,"
        "0:45:00,110,150,40,2.1,0.1,\n",
    )

    result = _import(conn, tmp_path, path)

    assert result.status == "ok"
    assert result.files_total == 1
    assert result.files_ok == 1
    assert result.rows_total == 2
    assert result.rows_ok == 2
    assert result.days == ["2026-10-01", "2026-10-02"]

    ride = get_activity(conn, 1, "12345")
    assert ride is not None
    assert ride["activity_type"] == "cycling"
    assert ride["name"] == "Morning ride"
    assert ride["duration_min"] == pytest.approx(60.0)
    assert ride["distance_m"] == pytest.approx(25400.0)
    assert ride["calories"] == 600
    assert ride["avg_hr"] == 135
    assert ride["max_hr"] == 170
    assert ride["training_load"] == pytest.approx(85.5)
    assert ride["aerobic_te"] == pytest.approx(3.2)
    assert ride["anaerobic_te"] == pytest.approx(0.4)
    assert ride["avg_pace_s_per_km"] == pytest.approx(3600 / 25.4, rel=1e-3)
    assert ride["elevation_gain_m"] == pytest.approx(120.0)

    gym = get_activity(conn, 1, "12346")
    assert gym is not None
    assert gym["activity_type"] == "strength"
    assert gym["distance_m"] is None
    assert gym["elevation_gain_m"] is None


def test_russian_headers_and_semicolon(conn, tmp_path):
    path = _csv(
        tmp_path / "Activities.csv",
        "ID активности;Тип активности;Дата;Название;Дистанция;Калории;"
        "Время;Средний пульс;Макс пульс;Тренировочная нагрузка\n"
        "77;Велосипед;01.10.2026 07:30;Поездка;12,5;300;1:00:00;130;165;50\n",
    )

    result = _import(conn, tmp_path, path)

    assert result.status == "ok"
    row = get_activity(conn, 1, "77")
    assert row is not None
    assert row["activity_type"] == "cycling"
    assert row["distance_m"] == pytest.approx(12500.0)
    assert row["duration_min"] == pytest.approx(60.0)
    assert row["avg_hr"] == 130


def test_repeat_import_is_idempotent(conn, tmp_path):
    path = _csv(
        tmp_path / "Activities.csv",
        "Activity ID,Activity Type,Date,Time\n"
        "1,Cycling,2026-10-01 07:30:00,1:00:00\n",
    )

    first = _import(conn, tmp_path, path)
    second = _import(conn, tmp_path, path)

    assert first.rows_ok == 1
    assert second.rows_ok == 0
    assert second.rows_skipped == 1
    assert second.status == "ok"
    count = conn.execute("SELECT COUNT(*) FROM garmin_activities").fetchone()[0]
    assert count == 1


def test_missing_id_gets_stable_synthetic_id(conn, tmp_path):
    path = _csv(
        tmp_path / "Activities.csv",
        "Activity Type,Date,Time,Distance\n"
        "Cycling,2026-10-01 07:30:00,1:00:00,20\n",
    )

    first = _import(conn, tmp_path, path)
    second = _import(conn, tmp_path, path)

    assert first.rows_ok == 1
    assert second.rows_skipped == 1
    row = conn.execute("SELECT activity_id FROM garmin_activities").fetchone()
    assert str(row["activity_id"]).startswith("csv_")


def test_missing_start_column_fails_without_crash(conn, tmp_path):
    path = _csv(
        tmp_path / "Activities.csv",
        "Activity Type,Time,Distance\nCycling,1:00:00,20\n",
    )

    result = _import(conn, tmp_path, path)

    assert result.status == "failed"
    assert result.files_failed == 1
    assert result.issues
    assert "start date" in result.issues[0].error


def test_empty_csv_fails_without_crash(conn, tmp_path):
    path = _csv(tmp_path / "Activities.csv", "")

    result = _import(conn, tmp_path, path)

    assert result.status == "failed"
    assert result.files_failed == 1


def test_bad_row_is_partial_but_good_row_is_imported(conn, tmp_path):
    path = _csv(
        tmp_path / "Activities.csv",
        "Activity ID,Activity Type,Date,Time\n"
        "1,Cycling,not-a-date,1:00:00\n"
        "2,Running,2026-10-01 08:00:00,0:30:00\n",
    )

    result = _import(conn, tmp_path, path)

    assert result.status == "partial"
    assert result.rows_ok == 1
    assert result.rows_failed == 1
    assert get_activity(conn, 1, "1") is None
    assert get_activity(conn, 1, "2") is not None


def test_online_source_wins_over_csv(conn, tmp_path):
    path = _csv(
        tmp_path / "Activities.csv",
        "Activity ID,Activity Type,Date,Time\n"
        "1,Cycling,2026-10-01 07:30:00,1:00:00\n",
    )
    _import(conn, tmp_path, path)

    upsert_activity(
        conn,
        {
            "user_id": 1,
            "activity_id": "1",
            "start_time": "2026-10-01T07:30:00",
            "activity_type": "cycling",
            "duration_min": 75.0,
        },
        source="online",
    )
    result = _import(conn, tmp_path, path)

    assert result.rows_skipped == 1
    row = get_activity(conn, 1, "1")
    assert row is not None
    assert row["duration_min"] == pytest.approx(75.0)
    assert row["source"] == "online"


def test_csv_dedupes_by_start_and_type(conn, tmp_path):
    first = _csv(
        tmp_path / "Activities.csv",
        "Activity Type,Date,Time\nCycling,2026-10-01 07:30:00,1:00:00\n",
    )
    second = _csv(
        tmp_path / "Activities-2.csv",
        "Activity ID,Activity Type,Date,Time\n"
        "garmin-99,Cycling,2026-10-01 07:30:00,1:00:00\n",
    )

    _import(conn, tmp_path, first)
    result = _import(conn, tmp_path, second)

    count = conn.execute("SELECT COUNT(*) FROM garmin_activities").fetchone()[0]
    assert count == 1
    assert result.rows_ok == 0
    assert result.rows_skipped == 1
