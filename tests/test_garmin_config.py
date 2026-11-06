"""Tests for services.garmin.config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from services.garmin.config import GarminConfig
from services.garmin.errors import GarminConfigError

GARMIN_ENV_KEYS = [
    "GARMIN_DATA_DIR",
    "GARMIN_DB_PATH",
    "GARMIN_IMPORT_DIR",
    "GARMIN_REPORT_DIR",
    "GARMIN_RAW_DIR",
    "GARMIN_QUARANTINE_DIR",
    "GARMIN_TMP_DIR",
    "GARMIN_CHARTS_DIR",
    "GARMIN_AI_MODEL",
    "GARMIN_AI_TIMEOUT",
    "GARMIN_PLAN_HORIZON_WEEKS",
    "GARMIN_DATA_RETENTION_DAYS",
    "GARMIN_ONLINE_ENABLED",
    "GARMIN_MAX_SYNC_DAYS",
    "GARMIN_REQUEST_DELAY",
    "GARMIN_CHART_DPI",
    "GARMIN_PDF_MAX_MB",
    "GARMIN_SLEEP_TARGET_H",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in GARMIN_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


def test_defaults_use_six_week_plan(tmp_path: Path):
    cfg = GarminConfig.from_env(data_dir=tmp_path)

    assert cfg.plan_horizon_weeks == 6
    assert cfg.retention_days == 365
    assert cfg.online_enabled is False
    assert cfg.max_sync_days == 7
    assert cfg.db_path == (tmp_path / "garmin.sqlite").resolve()
    assert cfg.import_dir == (tmp_path / "import").resolve()


def test_env_overrides_relative_paths(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GARMIN_DB_PATH", "custom/db.sqlite")
    monkeypatch.setenv("GARMIN_IMPORT_DIR", "incoming")
    monkeypatch.setenv("GARMIN_ONLINE_ENABLED", "yes")
    monkeypatch.setenv("GARMIN_PLAN_HORIZON_WEEKS", "8")

    cfg = GarminConfig.from_env(data_dir=tmp_path)

    assert cfg.db_path == (tmp_path / "custom/db.sqlite").resolve()
    assert cfg.import_dir == (tmp_path / "incoming").resolve()
    assert cfg.online_enabled is True
    assert cfg.plan_horizon_weeks == 8


def test_absolute_db_path_is_preserved(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "elsewhere" / "garmin.sqlite"
    monkeypatch.setenv("GARMIN_DB_PATH", str(db_path))

    cfg = GarminConfig.from_env(data_dir=tmp_path / "data")

    assert cfg.db_path == db_path.resolve()


def test_ensure_dirs_creates_private_tree(tmp_path: Path):
    cfg = GarminConfig.from_env(data_dir=tmp_path / "garmin")
    cfg.ensure_dirs()

    assert cfg.data_dir.is_dir()
    assert cfg.import_dir.is_dir()
    assert cfg.report_dir.is_dir()
    assert cfg.raw_dir.is_dir()
    assert cfg.quarantine_dir.is_dir()
    assert cfg.tmp_dir.is_dir()
    assert cfg.charts_dir.is_dir()
    assert cfg.db_path.parent.is_dir()


@pytest.mark.parametrize(
    "key,value",
    [
        ("GARMIN_MAX_SYNC_DAYS", "8"),
        ("GARMIN_MAX_SYNC_DAYS", "0"),
        ("GARMIN_PLAN_HORIZON_WEEKS", "0"),
        ("GARMIN_DATA_RETENTION_DAYS", "0"),
        ("GARMIN_REQUEST_DELAY", "0.5"),
        ("GARMIN_CHART_DPI", "999"),
        ("GARMIN_PDF_MAX_MB", "0"),
        ("GARMIN_SLEEP_TARGET_H", "2"),
        ("GARMIN_AI_TIMEOUT", "0"),
    ],
)
def test_invalid_values_raise(tmp_path: Path, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(GarminConfigError):
        GarminConfig.from_env(data_dir=tmp_path)


def test_invalid_integer_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GARMIN_PLAN_HORIZON_WEEKS", "six")
    with pytest.raises(GarminConfigError, match="integer"):
        GarminConfig.from_env(data_dir=tmp_path)


def test_ensure_dirs_uses_restrictive_modes(tmp_path: Path):
    cfg = GarminConfig.from_env(data_dir=tmp_path / "garmin")
    cfg.ensure_dirs()

    mode = os.stat(cfg.data_dir).st_mode & 0o777
    assert mode == 0o700
