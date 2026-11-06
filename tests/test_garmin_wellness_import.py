"""Tests for the export-first wellness importer."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from services.garmin.db import init_db
from services.garmin.errors import GarminImportError
from services.garmin.importers import wellness_fit as importer
from services.garmin.raw_store import RawStore
from services.garmin.repository import get_daily


def _sample():
    return {
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


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


def test_import_zip_saves_raw_and_upserts(conn, tmp_path, monkeypatch):
    archive = _zip(
        tmp_path / "Garmin 2026-07-02.zip",
        {"Garmin 2026-07-02/WELLNESS.fit": b"fit"},
    )
    monkeypatch.setattr(
        importer,
        "decode_bundle",
        lambda folder, date_hint=None: _sample(),
    )
    store = RawStore(tmp_path / "raw")

    result = importer.import_wellness_path(
        archive,
        conn=conn,
        raw_store=store,
        user_id=1,
        tmp_dir=tmp_path / "tmp",
    )

    assert result.status == "ok"
    assert result.days == ["2026-07-02"]
    assert result.files_total == 1
    assert result.files_ok == 1
    assert result.files_failed == 0
    assert result.issues == []

    row = get_daily(conn, 1, "2026-07-02")
    assert row["sleep_hours"] == 7.5
    assert row["hrv"] == 52
    assert json.loads(row["data_sources_json"])["sleep_hours"] == "wellness_fit"

    raw = conn.execute("SELECT COUNT(*) FROM garmin_raw_files").fetchone()[0]
    assert raw == 2  # ZIP + FIT
    run = conn.execute(
        "SELECT status, files_total, files_ok FROM garmin_runs WHERE id = ?",
        (result.run_id,),
    ).fetchone()
    assert run["status"] == "ok"
    assert run["files_total"] == 1
    assert run["files_ok"] == 1


def test_import_junk_fit_fails_without_empty_row(conn, tmp_path):
    archive = _zip(
        tmp_path / "Garmin 2026-07-02.zip",
        {"Garmin 2026-07-02/WELLNESS.fit": b"not a fit"},
    )
    result = importer.import_wellness_path(
        archive,
        conn=conn,
        raw_store=RawStore(tmp_path / "raw"),
        user_id=1,
        tmp_dir=tmp_path / "tmp",
    )

    assert result.status == "failed"
    assert result.days == []
    assert result.issues
    assert get_daily(conn, 1, "2026-07-02") is None
    run = conn.execute(
        "SELECT status FROM garmin_runs WHERE id = ?", (result.run_id,)
    ).fetchone()
    assert run["status"] == "failed"


def test_import_bad_zip_records_failed_run(conn, tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"not a zip")
    result = importer.import_wellness_path(
        path,
        conn=conn,
        raw_store=RawStore(tmp_path / "raw"),
        user_id=1,
        tmp_dir=tmp_path / "tmp",
    )

    assert result.status == "failed"
    assert result.issues
    assert result.run_id is not None


def test_import_single_fit_uses_isolated_temp_folder(conn, tmp_path, monkeypatch):
    fit = tmp_path / "Garmin 2026-07-02.fit"
    fit.write_bytes(b"fit")
    monkeypatch.setattr(
        importer,
        "decode_bundle",
        lambda folder, date_hint=None: _sample(),
    )

    result = importer.import_wellness_path(
        fit,
        conn=conn,
        raw_store=RawStore(tmp_path / "raw"),
        user_id=1,
        tmp_dir=tmp_path / "tmp",
    )

    assert result.status == "ok"
    assert result.days == ["2026-07-02"]
    assert get_daily(conn, 1, "2026-07-02")["sleep_hours"] == 7.5


def test_missing_path_raises(conn, tmp_path):
    with pytest.raises(GarminImportError, match="does not exist"):
        importer.import_wellness_path(
            tmp_path / "missing.zip",
            conn=conn,
            raw_store=RawStore(tmp_path / "raw"),
            user_id=1,
            tmp_dir=tmp_path / "tmp",
        )
