"""Tests for the Garmin SQLite schema and migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.garmin.db import SCHEMA_VERSION, init_db, migrate, schema_version, tables
from services.garmin.errors import GarminDatabaseError


def test_init_creates_schema(tmp_path: Path):
    conn = init_db(tmp_path / "garmin.sqlite")
    try:
        assert schema_version(conn) == SCHEMA_VERSION
        names = tables(conn)
        assert {
            "garmin_daily",
            "garmin_profile",
            "garmin_training_plans",
            "garmin_plan_sessions",
            "garmin_checkins",
            "garmin_plan_reviews",
            "garmin_adaptation_log",
        } <= names
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path: Path):
    conn = init_db(tmp_path / "garmin.sqlite")
    try:
        assert migrate(conn) == SCHEMA_VERSION
        assert migrate(conn) == SCHEMA_VERSION
        assert schema_version(conn) == SCHEMA_VERSION
    finally:
        conn.close()


def test_v1_daily_table_gets_v2_columns(tmp_path: Path):
    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE garmin_daily (user_id INTEGER NOT NULL, date TEXT NOT NULL,"
        " sleep_hours REAL, PRIMARY KEY (user_id, date))"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()

    migrate(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(garmin_daily)")}
    assert "sleep_efficiency" in columns
    assert "readiness_level" in columns
    assert "updated_at" in columns
    conn.execute(
        "INSERT INTO garmin_daily (user_id, date, sleep_hours, updated_at)"
        " VALUES (?, ?, ?, ?)",
        (1, "2026-10-27", 7.2, "2026-10-27T00:00:00Z"),
    )
    conn.commit()
    assert schema_version(conn) == SCHEMA_VERSION
    conn.close()


def test_profile_blob_roundtrip(tmp_path: Path):
    conn = init_db(tmp_path / "garmin.sqlite")
    try:
        conn.execute(
            "INSERT INTO garmin_profile"
            " (user_id, profile_blob, version, completeness, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (1, b"encrypted", 1, "partial", "2026-10-27T00:00:00Z"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT profile_blob, version, completeness FROM garmin_profile"
            " WHERE user_id = ?",
            (1,),
        ).fetchone()
        assert bytes(row["profile_blob"]) == b"encrypted"
        assert row["version"] == 1
        assert row["completeness"] == "partial"
    finally:
        conn.close()


def test_checkins_allow_morning_and_post(tmp_path: Path):
    conn = init_db(tmp_path / "garmin.sqlite")
    try:
        for kind in ("morning", "post"):
            conn.execute(
                "INSERT INTO garmin_checkins"
                " (user_id, date, kind, sleep_h, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (1, "2026-10-27", kind, 7.0, "2026-10-27T00:00:00Z"),
            )
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM garmin_checkins WHERE user_id = 1"
        ).fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_adaptation_log_roundtrip(tmp_path: Path):
    conn = init_db(tmp_path / "garmin.sqlite")
    try:
        conn.execute(
            "INSERT INTO garmin_adaptation_log"
            " (user_id, date, trigger, compared_from, compared_to, delta_json,"
            " recommendation, confidence, needs_confirm, applied, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "2026-10-27",
                "import",
                "2026-10-20",
                "2026-10-27",
                '{"changed_metrics":[]}',
                "reduce",
                "medium",
                1,
                0,
                "2026-10-27T00:00:00Z",
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT recommendation, needs_confirm FROM garmin_adaptation_log"
        ).fetchone()
        assert row["recommendation"] == "reduce"
        assert row["needs_confirm"] == 1
    finally:
        conn.close()


def test_database_file_is_private(tmp_path: Path):
    path = tmp_path / "garmin.sqlite"
    conn = init_db(path)
    conn.close()
    assert path.stat().st_mode & 0o777 == 0o600


def test_newer_schema_is_rejected(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "future.sqlite")
    conn.execute("PRAGMA user_version = 999")
    conn.commit()
    with pytest.raises(GarminDatabaseError):
        migrate(conn)
    conn.close()
