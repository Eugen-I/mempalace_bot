"""Tests for the adapted wellness-FIT decoder."""

from __future__ import annotations

import json
from pathlib import Path

from services.garmin import fit_wellness


def _decoded(**overrides):
    base = {
        "date": "2026-07-02",
        "heart_rate": {"min": 48, "avg": 62, "max": 120, "samples": 900},
        "steps": 9000,
        "distance_m": 7000.0,
        "stress": {"avg": 30, "max": 88},
        "sleep": {
            "start": "2026-07-01T23:10:00",
            "end": "2026-07-02T06:40:00",
            "duration_min": 450,
        },
        "sleep_stages": {
            "deep_min": 80,
            "light_min": 240,
            "rem_min": 90,
            "awake_min": 20,
            "max_logging_gap_min": 10,
        },
        "sleep_score": 86,
        "hrv": {
            "last_night_avg": 52,
            "weekly_avg": 50,
            "high_5min": 68,
            "baseline_low": 45,
            "baseline_high": 60,
            "status": "balanced",
        },
        "skin_temp": {"nightly_c": 33.9, "deviation_c": -0.2, "avg_dev_7d": 0.05},
        "rhr_on_device": 52,
        "naps": [],
    }
    base.update(overrides)
    return base


def test_clean_night_has_no_flags():
    assert fit_wellness.quality_flags(_decoded()) == []


def test_rhr_flag_fires_only_above_margin():
    at_margin = _decoded(rhr_on_device=58)
    above = _decoded(rhr_on_device=59)
    assert "rhr_far_above_hr_floor" not in fit_wellness.quality_flags(at_margin)
    assert fit_wellness.quality_flags(above) == ["rhr_far_above_hr_floor"]


def test_sparse_stage_flag_threshold():
    stages = dict(_decoded()["sleep_stages"])
    ok = _decoded(sleep_stages={**stages, "max_logging_gap_min": 44})
    sparse = _decoded(sleep_stages={**stages, "max_logging_gap_min": 45})
    assert fit_wellness.quality_flags(ok) == []
    assert fit_wellness.quality_flags(sparse) == ["sparse_sleep_stage_logging"]


def test_flags_tolerate_missing_sections():
    empty = _decoded(heart_rate=None, sleep_stages=None, rhr_on_device=None)
    assert fit_wellness.quality_flags(empty) == []


def test_daily_row_mapping():
    row = fit_wellness.to_daily_row(_decoded(), user_id=7)

    assert row["user_id"] == 7
    assert row["date"] == "2026-07-02"
    assert row["sleep_hours"] == 7.5
    assert row["sleep_score"] == 86
    assert row["sleep_efficiency"] == 95.6
    assert row["sleep_midpoint_min"] == 175  # 02:55
    assert row["hrv"] == 52
    assert row["hrv_baseline_7d"] == 50
    assert row["hrv_status"] == "balanced"
    assert row["resting_hr"] == 52
    assert (row["stress_avg"], row["stress_max"]) == (30, 88)
    assert row["steps"] == 9000

    stages = json.loads(row["sleep_stages_json"])
    assert stages["deep_min"] == 80
    assert stages["start"] == "2026-07-01T23:10:00"
    assert stages["end"] == "2026-07-02T06:40:00"

    sources = json.loads(row["data_sources_json"])
    assert sources["sleep_hours"] == "wellness_fit"
    assert sources["hrv"] == "wellness_fit"
    assert sources["resting_hr"] == "wellness_fit"
    assert json.loads(row["quality_flags_json"]) == []


def test_flagged_rhr_is_not_written():
    row = fit_wellness.to_daily_row(_decoded(rhr_on_device=69), user_id=1)
    assert row["resting_hr"] is None
    assert json.loads(row["quality_flags_json"]) == ["rhr_far_above_hr_floor"]
    assert "resting_hr" not in json.loads(row["data_sources_json"])


def test_empty_bundle_has_no_sleep_payload():
    decoded = fit_wellness.decode_bundle(Path("/tmp/Garmin 2026-01-01"))
    assert decoded["date"] == "2026-01-01"
    assert decoded["heart_rate"] is None
    assert decoded["sleep"] is None
    assert decoded["naps"] == []
    row = fit_wellness.to_daily_row(decoded, user_id=1)
    assert row["sleep_stages_json"] is None
    assert json.loads(row["data_sources_json"]) == {}


def test_date_hint_is_used_when_folder_has_no_date(tmp_path: Path):
    folder = tmp_path / "wellness-export"
    folder.mkdir()
    decoded = fit_wellness.decode_bundle(folder, date_hint="Garmin 2026-01-02")
    assert decoded["date"] == "2026-01-02"


def test_unreadable_fit_is_skipped(tmp_path: Path):
    folder = tmp_path / "Garmin 2026-01-01"
    folder.mkdir()
    (folder / "junk_WELLNESS.fit").write_bytes(b"not a fit file at all")
    decoded = fit_wellness.decode_bundle(folder)
    assert decoded["heart_rate"] is None


def test_extra_metrics_mapping():
    metrics = fit_wellness.to_extra_metrics(_decoded(), user_id=1)
    by_name = {item["metric"]: item for item in metrics}

    assert by_name["distance_m"]["value"] == 7000.0
    assert by_name["min_hr"]["value"] == 48
    assert by_name["max_hr"]["value"] == 120
    assert by_name["skin_temp_dev_c"]["value"] == -0.2
    assert by_name["hrv_weekly_avg"]["value"] == 50
    assert by_name["sleep_deep_min"]["value"] == 80
    assert all(item["source"] == "wellness_fit" for item in metrics)


def test_nap_minutes_are_summed():
    naps = [
        {"start": "2026-07-02T13:00:00", "end": "2026-07-02T13:25:00", "duration_min": 25},
        {"start": "2026-07-02T17:00:00", "end": "2026-07-02T17:35:00", "duration_min": 35},
    ]
    row = fit_wellness.to_daily_row(_decoded(naps=naps), user_id=1)
    stages = json.loads(row["sleep_stages_json"])
    assert stages["nap_min"] == 60
    metrics = {
        item["metric"]: item
        for item in fit_wellness.to_extra_metrics(_decoded(naps=naps), user_id=1)
    }
    assert metrics["nap_min"]["value"] == 60
