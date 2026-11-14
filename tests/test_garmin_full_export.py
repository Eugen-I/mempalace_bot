"""Tests for full Garmin export, JSON, TCX and import routing."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from services.garmin.db import init_db
from services.garmin.importers import detect_import_kind, import_any_path
from services.garmin.importers.full_export import (
    _from_fit_session,
    import_full_export_path,
    looks_like_full_export,
)
from services.garmin.raw_store import RawStore
from services.garmin.repository import get_activity


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


def _import(conn, tmp_path: Path, path: Path):
    return import_full_export_path(
        path,
        conn=conn,
        raw_store=RawStore(tmp_path / "raw"),
        user_id=1,
        tmp_dir=tmp_path / "tmp",
    )


def _zip(path: Path, members: dict[str, str | bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def _json_activity(activity_id: int = 111) -> dict:
    return {
        "activityId": activity_id,
        "activityName": "Morning ride",
        "activityType": {"typeKey": "cycling"},
        "startTimeLocal": "2026-10-01T07:30:00.0",
        "duration": 3600.0,
        "distance": 25400.0,
        "calories": 600,
        "averageHR": 135,
        "maxHR": 170,
        "activityTrainingLoad": 85.5,
        "aerobicTrainingEffect": 3.2,
        "anaerobicTrainingEffect": 0.4,
        "elevationGain": 120.0,
    }


def test_json_summarized_activities(conn, tmp_path):
    path = tmp_path / "0_summarizedActivities.json"
    path.write_text(
        json.dumps({"summarizedActivitiesExport": [_json_activity()]}),
        encoding="utf-8",
    )

    result = _import(conn, tmp_path, path)

    assert result.status == "ok"
    assert result.rows_ok == 1
    row = get_activity(conn, 1, "111")
    assert row is not None
    assert row["activity_type"] == "cycling"
    assert row["name"] == "Morning ride"
    assert row["duration_min"] == pytest.approx(60.0)
    assert row["distance_m"] == pytest.approx(25400.0)
    assert row["training_load"] == pytest.approx(85.5)
    assert row["source"] == "full_export"


def test_corrupt_json_fails_without_crash(conn, tmp_path):
    path = tmp_path / "0_summarizedActivities.json"
    path.write_text("{not json", encoding="utf-8")

    result = _import(conn, tmp_path, path)

    assert result.status == "failed"
    assert result.files_failed == 1
    assert result.issues


def test_tcx_activity_is_imported(conn, tmp_path):
    path = tmp_path / "ride.tcx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
  xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Biking">
      <Id>2026-10-02T18:00:00Z</Id>
      <Lap>
        <TotalTimeSeconds>2700</TotalTimeSeconds>
        <DistanceMeters>15000</DistanceMeters>
        <Calories>300</Calories>
        <AverageHeartRateBpm><Value>130</Value></AverageHeartRateBpm>
        <MaximumHeartRateBpm><Value>165</Value></MaximumHeartRateBpm>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
""",
        encoding="utf-8",
    )

    result = _import(conn, tmp_path, path)

    assert result.status == "ok"
    assert result.rows_ok == 1
    row = conn.execute("SELECT * FROM garmin_activities").fetchone()
    assert row is not None
    assert row["activity_type"] == "cycling"
    assert row["duration_min"] == pytest.approx(45.0)
    assert row["distance_m"] == pytest.approx(15000.0)
    assert row["avg_hr"] == 130
    assert row["max_hr"] == 165
    assert row["avg_pace_s_per_km"] == pytest.approx(180.0)


def test_full_zip_imports_csv_json_and_ignores_unknown(conn, tmp_path):
    second = _json_activity(2)
    second["startTimeLocal"] = "2026-10-02T07:30:00.0"
    archive = _zip(
        tmp_path / "export.zip",
        {
            "DI_CONNECT/DI-Connect-Fitness/Activities.csv": (
                "Activity ID,Activity Type,Date,Time,Distance\n"
                "1,Cycling,2026-10-01 07:30:00,1:00:00,20\n"
            ),
            "DI_CONNECT/DI-Connect-Fitness/0_summarizedActivities.json": (
                json.dumps([second])
            ),
            "DI_CONNECT/DI-Connect-Fitness/broken_summarizedActivities.json": (
                "{broken"
            ),
            "DI_CONNECT/DI-Connect-Fitness/readme.bin": b"unknown",
        },
    )

    result = _import(conn, tmp_path, archive)

    assert result.status == "partial"
    assert result.rows_ok == 2
    assert result.files_failed == 1
    assert get_activity(conn, 1, "1") is not None
    assert get_activity(conn, 1, "2") is not None
    assert any("broken" in issue.file for issue in result.issues)


def test_full_export_folder_without_activities_fails(conn, tmp_path):
    folder = tmp_path / "empty-export"
    folder.mkdir()
    (folder / "readme.txt").write_text("no activities", encoding="utf-8")

    result = _import(conn, tmp_path, folder)

    assert result.status == "failed"
    assert "no activity files" in result.issues[0].error


def test_detection_distinguishes_full_and_wellness(conn, tmp_path):
    full = _zip(
        tmp_path / "full.zip",
        {"DI_CONNECT/DI-Connect-Fitness/Activities.csv": "a,b\n"},
    )
    wellness = _zip(
        tmp_path / "wellness.zip",
        {"2026-10-01/WELLNESS.fit": b"fit"},
    )

    assert looks_like_full_export(full) is True
    assert looks_like_full_export(wellness) is False
    assert detect_import_kind(full) == "full_export"
    assert detect_import_kind(wellness) == "wellness"
    assert detect_import_kind(tmp_path / "Activities.csv") == "activities_csv"


def test_detection_recognizes_single_activity_zip_and_fit(tmp_path):
    activity_zip = _zip(
        tmp_path / "24812238238.zip",
        {"24812238238_ACTIVITY.fit": b"fit"},
    )
    activity_fit = tmp_path / "24812238238_ACTIVITY.fit"
    activity_fit.write_bytes(b"fit")
    wellness_fit = tmp_path / "2026-10-01_WELLNESS.fit"
    wellness_fit.write_bytes(b"fit")

    assert looks_like_full_export(activity_zip) is True
    assert detect_import_kind(activity_zip) == "full_export"
    assert looks_like_full_export(activity_fit) is True
    assert detect_import_kind(activity_fit) == "full_export"
    assert looks_like_full_export(wellness_fit) is False
    assert detect_import_kind(wellness_fit) == "wellness"


def test_import_any_path_routes_csv(conn, tmp_path):
    path = tmp_path / "Activities.csv"
    path.write_text(
        "Activity ID,Activity Type,Date,Time\n"
        "5,Running,2026-10-03 09:00:00,0:20:00\n",
        encoding="utf-8",
    )

    result = import_any_path(
        path,
        conn=conn,
        raw_store=RawStore(tmp_path / "raw"),
        user_id=1,
        tmp_dir=tmp_path / "tmp",
    )

    assert result.status == "ok"
    row = get_activity(conn, 1, "5")
    assert row is not None
    assert row["source"] == "activities_csv"


def test_fit_session_mapping():
    from datetime import datetime
    from pathlib import Path as P

    activity = _from_fit_session(
        {
            "start_time": datetime(2026, 10, 4, 8, 0, 0),
            "sport": "running",
            "total_timer_time": 1800.0,
            "total_distance": 5000.0,
            "total_calories": 320,
            "avg_heart_rate": 140,
            "max_heart_rate": 172,
            "training_stress_score": 45.0,
            "total_training_effect": 2.8,
            "total_anaerobic_training_effect": 0.1,
            "total_ascent": 40.0,
        },
        path=P("run.fit"),
        user_id=1,
    )

    assert activity is not None
    assert activity["activity_type"] == "running"
    assert activity["duration_min"] == pytest.approx(30.0)
    assert activity["distance_m"] == pytest.approx(5000.0)
    assert activity["avg_hr"] == 140
    assert activity["training_load"] == pytest.approx(45.0)


def test_fit_session_prefers_specific_subsport():
    from datetime import datetime
    from pathlib import Path as P

    activity = _from_fit_session(
        {
            "start_time": datetime(2026, 10, 22, 9, 33, 39),
            "sport": "training",
            "sub_sport": "strength_training",
            "total_timer_time": 2259.123,
            "total_distance": 0.0,
            "total_calories": 293,
            "avg_heart_rate": 109,
            "max_heart_rate": 159,
        },
        path=P("24812238238_ACTIVITY.fit"),
        user_id=1,
    )

    assert activity is not None
    assert activity["activity_type"] == "strength"
    assert activity["duration_min"] == pytest.approx(37.65)
    assert activity["avg_hr"] == 109
    assert activity["max_hr"] == 159


def test_full_export_wellness_files_imported(conn, tmp_path):
    archive = _zip(
        tmp_path / "export_wellness.zip",
        {
            "DI_CONNECT/DI-Connect-Aggregator/UDSFile_2026-10-01.json": json.dumps([
                {
                    "calendarDate": "2026-10-01",
                    "totalSteps": 8500,
                    "restingHeartRate": 58,
                    "activeKilocalories": 450.0,
                    "totalKilocalories": 2100.0,
                    "allDayStress": {
                        "aggregatorList": [
                            {
                                "type": "TOTAL",
                                "averageStressLevel": 28,
                                "maxStressLevel": 75,
                                "highDuration": 1800,
                            }
                        ]
                    },
                    "bodyBattery": {
                        "chargedValue": 65,
                        "drainedValue": 60,
                        "bodyBatteryStatList": [
                            {"bodyBatteryStatType": "STARTOFDAY", "statsValue": 85},
                            {"bodyBatteryStatType": "ENDOFDAY", "statsValue": 25},
                        ],
                    },
                    "respiration": {
                        "avgWakingRespirationValue": 14.5,
                        "lowestRespirationValue": 11.0,
                        "highestRespirationValue": 18.0,
                    },
                    "averageSpo2Value": 97.0,
                    "lowestSpo2Value": 94.0,
                }
            ]),
            "DI_CONNECT/DI-Connect-Wellness/sleepData.json": json.dumps([
                {
                    "calendarDate": "2026-10-01",
                    "deepSleepSeconds": 5400,
                    "lightSleepSeconds": 14400,
                    "remSleepSeconds": 7200,
                    "awakeSleepSeconds": 1200,
                    "sleepScores": {"overallScore": 84},
                }
            ]),
            "DI_CONNECT/DI-Connect-Wellness/healthStatusData.json": json.dumps([
                {
                    "calendarDate": "2026-10-01",
                    "metrics": [
                        {
                            "type": "HRV",
                            "value": 52.0,
                            "status": "BALANCED",
                            "baselineUpperLimit": 58.0,
                            "baselineLowerLimit": 46.0,
                        }
                    ],
                }
            ]),
            "DI_CONNECT/DI-Connect-Metrics/TrainingReadinessDTO.json": json.dumps([
                {
                    "calendarDate": "2026-10-01",
                    "score": 78,
                    "level": "HIGH",
                    "recoveryTime": 12,
                    "hrvWeeklyAverage": 50.5,
                }
            ]),
            "DI_CONNECT/DI-Connect-Wellness/userBioMetrics.json": json.dumps([
                {
                    "metaData": {"calendarDate": "2026-10-01T08:00:00.0"},
                    "weight": {"weight": 82500},
                }
            ]),
            "DI_CONNECT/DI-Connect-Fitness/summarizedActivities.json": json.dumps([
                {
                    "summarizedActivitiesExport": [
                        {
                            "activityId": 999,
                            "name": "Evening Run",
                            "activityType": "running",
                            "startTimeLocal": 1790899200000.0,
                            "duration": 1800000.0,
                            "distance": 500000.0,
                            "calories": 350.0,
                            "averageHR": 145.0,
                            "maxHR": 170.0,
                            "activityTrainingLoad": 42.0,
                            "elevationGain": 3500.0,
                        }
                    ]
                }
            ]),
        },
    )

    result = _import(conn, tmp_path, archive)

    assert result.status == "ok"
    assert result.rows_ok >= 6

    daily = conn.execute(
        "SELECT * FROM garmin_daily WHERE user_id = 1 AND date = '2026-10-01'"
    ).fetchone()
    assert daily is not None
    assert daily["steps"] == 8500
    assert daily["resting_hr"] == pytest.approx(58.0)
    assert daily["stress_avg"] == pytest.approx(28.0)
    assert daily["body_battery_morning"] == 85
    assert daily["body_battery_evening"] == 25
    assert daily["sleep_hours"] == pytest.approx(7.5)  # (5400+14400+7200)/3600
    assert daily["sleep_score"] == 84
    assert daily["hrv"] == pytest.approx(52.0)
    assert daily["hrv_status"] == "BALANCED"
    assert daily["readiness_score"] == 78
    assert daily["recovery_time_h"] == pytest.approx(12.0)
    assert daily["weight_kg"] == pytest.approx(82.5)

    activity = conn.execute(
        "SELECT * FROM garmin_activities WHERE user_id = 1 AND activity_id = '999'"
    ).fetchone()
    assert activity is not None
    assert activity["name"] == "Evening Run"
    assert activity["duration_min"] == pytest.approx(30.0)
    assert activity["distance_m"] == pytest.approx(5000.0)
    assert activity["elevation_gain_m"] == pytest.approx(35.0)
    assert activity["training_load"] == pytest.approx(42.0)
