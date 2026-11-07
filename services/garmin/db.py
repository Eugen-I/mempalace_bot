"""SQLite schema and migrations for the Garmin integration.

The schema is intentionally explicit and migration-friendly.  There is no ORM:
the repository layer uses parameterized SQL only.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .errors import GarminDatabaseError

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS garmin_accounts (
    user_id                 INTEGER PRIMARY KEY,
    garmin_email            TEXT NOT NULL DEFAULT '',
    encrypted_session_json  BLOB,
    account_timezone        TEXT,
    last_login_at           TEXT,
    last_sync_at            TEXT,
    session_status          TEXT NOT NULL DEFAULT 'disconnected',
    session_state_updated_at TEXT,
    last_auth_error         TEXT,
    failed_auth_attempts    INTEGER NOT NULL DEFAULT 0,
    failed_fetch_attempts   INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS garmin_mfa_state (
    user_id       INTEGER PRIMARY KEY,
    state_blob    BLOB NOT NULL,
    expires_at    TEXT NOT NULL,
    attempts      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS garmin_daily (
    user_id                 INTEGER NOT NULL,
    date                    TEXT NOT NULL,
    sleep_hours             REAL,
    sleep_score             INTEGER,
    sleep_stages_json       TEXT,
    sleep_efficiency        REAL,
    sleep_latency_min       INTEGER,
    sleep_midpoint_min      INTEGER,
    hrv                     INTEGER,
    hrv_baseline_7d         INTEGER,
    hrv_baseline_28d        INTEGER,
    hrv_status              TEXT,
    hrv_cv_pct              REAL,
    resting_hr              INTEGER,
    resting_hr_baseline     INTEGER,
    stress_avg              INTEGER,
    stress_max              INTEGER,
    stress_high_min         INTEGER,
    body_battery_morning    INTEGER,
    body_battery_evening    INTEGER,
    body_battery_charged    INTEGER,
    body_battery_spent      INTEGER,
    readiness_score         INTEGER,
    readiness_level         TEXT,
    recovery_time_h         REAL,
    spo2_avg                REAL,
    spo2_min                REAL,
    respiration_avg         REAL,
    respiration_min         REAL,
    respiration_max         REAL,
    steps                   INTEGER,
    active_calories         INTEGER,
    total_calories          INTEGER,
    weight_kg               REAL,
    body_fat_pct            REAL,
    muscle_mass_kg          REAL,
    body_water_pct          REAL,
    bmi                     REAL,
    vo2max                  REAL,
    fitness_age             INTEGER,
    data_sources_json       TEXT NOT NULL DEFAULT '{}',
    quality_flags_json      TEXT NOT NULL DEFAULT '[]',
    updated_at              TEXT NOT NULL,
    PRIMARY KEY (user_id, date)
);

CREATE TABLE IF NOT EXISTS garmin_activities (
    user_id           INTEGER NOT NULL,
    activity_id       TEXT NOT NULL,
    start_time        TEXT NOT NULL,
    activity_type     TEXT,
    name              TEXT,
    duration_min      REAL,
    distance_m        REAL,
    calories          INTEGER,
    avg_hr            INTEGER,
    max_hr            INTEGER,
    training_load     REAL,
    aerobic_te        REAL,
    anaerobic_te      REAL,
    avg_pace_s_per_km REAL,
    elevation_gain_m  REAL,
    source            TEXT NOT NULL,
    raw_json          TEXT,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (user_id, activity_id)
);

CREATE TABLE IF NOT EXISTS garmin_extra_metrics (
    user_id     INTEGER NOT NULL,
    date        TEXT NOT NULL,
    metric      TEXT NOT NULL,
    value       REAL,
    unit        TEXT,
    source      TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, date, metric)
);

CREATE TABLE IF NOT EXISTS garmin_raw_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    sha256      TEXT NOT NULL,
    source      TEXT NOT NULL,
    filename    TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    imported_at TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'ok',
    error_text  TEXT,
    UNIQUE (user_id, sha256)
);

CREATE TABLE IF NOT EXISTS garmin_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    kind          TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL DEFAULT 'running',
    files_total   INTEGER NOT NULL DEFAULT 0,
    files_ok      INTEGER NOT NULL DEFAULT 0,
    files_failed  INTEGER NOT NULL DEFAULT 0,
    error_text    TEXT
);

CREATE TABLE IF NOT EXISTS garmin_analysis_cache (
    cache_key      TEXT PRIMARY KEY,
    user_id        INTEGER NOT NULL,
    kind           TEXT NOT NULL,
    payload_hash   TEXT NOT NULL,
    response_json  TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    expires_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS garmin_settings (
    user_id         INTEGER PRIMARY KEY,
    retention_days  INTEGER NOT NULL DEFAULT 365,
    retention_until TEXT,
    online_enabled  INTEGER NOT NULL DEFAULT 0,
    ai_enabled      INTEGER NOT NULL DEFAULT 1,
    charts_enabled  INTEGER NOT NULL DEFAULT 1,
    timezone        TEXT,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS garmin_profile (
    user_id       INTEGER PRIMARY KEY,
    profile_blob  BLOB NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,
    completeness  TEXT NOT NULL DEFAULT 'empty',
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS garmin_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    date        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    notes       TEXT,
    severity    TEXT NOT NULL DEFAULT 'info',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS garmin_training_plans (
    plan_id          TEXT PRIMARY KEY,
    user_id          INTEGER NOT NULL,
    status           TEXT NOT NULL,
    goal             TEXT NOT NULL,
    start_date       TEXT NOT NULL,
    end_date         TEXT NOT NULL,
    horizon_weeks    INTEGER NOT NULL,
    version          INTEGER NOT NULL DEFAULT 1,
    skeleton_json    TEXT NOT NULL,
    plan_json        TEXT NOT NULL,
    validation_json  TEXT NOT NULL,
    evidence_version TEXT NOT NULL,
    profile_version  INTEGER NOT NULL,
    prompt_version   TEXT NOT NULL,
    model            TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS garmin_plan_sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id        TEXT NOT NULL,
    user_id        INTEGER NOT NULL,
    date           TEXT NOT NULL,
    week_index     INTEGER NOT NULL,
    session_type   TEXT NOT NULL,
    title          TEXT NOT NULL,
    duration_min   INTEGER,
    intensity      TEXT,
    structure_json TEXT,
    status         TEXT NOT NULL DEFAULT 'planned',
    rpe            REAL,
    pain_score     INTEGER,
    notes          TEXT,
    updated_at     TEXT NOT NULL,
    UNIQUE (plan_id, date, session_type, title)
);

CREATE TABLE IF NOT EXISTS garmin_checkins (
    user_id        INTEGER NOT NULL,
    date           TEXT NOT NULL,
    kind           TEXT NOT NULL DEFAULT 'morning',
    sleep_h        REAL,
    sleep_quality  INTEGER,
    hrv            INTEGER,
    rhr            INTEGER,
    soreness       INTEGER,
    pain_score     INTEGER,
    pain_location  TEXT,
    mood           INTEGER,
    stress         INTEGER,
    adherence      INTEGER,
    notes          TEXT,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (user_id, date, kind)
);

CREATE TABLE IF NOT EXISTS garmin_plan_reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id      TEXT NOT NULL,
    user_id      INTEGER NOT NULL,
    week_index   INTEGER NOT NULL,
    review_date  TEXT NOT NULL,
    readiness    TEXT NOT NULL,
    decision     TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    rationale    TEXT NOT NULL,
    applied      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS garmin_adaptation_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    date            TEXT NOT NULL,
    trigger         TEXT NOT NULL,
    compared_from   TEXT,
    compared_to     TEXT,
    delta_json      TEXT NOT NULL,
    recommendation  TEXT NOT NULL,
    confidence      TEXT NOT NULL,
    needs_confirm   INTEGER NOT NULL DEFAULT 1,
    applied         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_garmin_daily_date
    ON garmin_daily (user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_garmin_activities_start
    ON garmin_activities (user_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_garmin_extra_metrics_date
    ON garmin_extra_metrics (user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_garmin_raw_files_sha
    ON garmin_raw_files (user_id, sha256);
CREATE INDEX IF NOT EXISTS idx_garmin_runs_user
    ON garmin_runs (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_garmin_events_date
    ON garmin_events (user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_garmin_plans_user
    ON garmin_training_plans (user_id, status, start_date DESC);
CREATE INDEX IF NOT EXISTS idx_garmin_sessions_plan_date
    ON garmin_plan_sessions (plan_id, date);
CREATE INDEX IF NOT EXISTS idx_garmin_reviews_plan
    ON garmin_plan_reviews (plan_id, week_index);
CREATE INDEX IF NOT EXISTS idx_garmin_checkins_user_date
    ON garmin_checkins (user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_garmin_adaptation_user_date
    ON garmin_adaptation_log (user_id, date DESC);
"""

_DAILY_V2_COLUMNS: dict[str, str] = {
    "sleep_hours": "REAL",
    "sleep_score": "INTEGER",
    "sleep_stages_json": "TEXT",
    "sleep_efficiency": "REAL",
    "sleep_latency_min": "INTEGER",
    "sleep_midpoint_min": "INTEGER",
    "hrv": "INTEGER",
    "hrv_baseline_7d": "INTEGER",
    "hrv_baseline_28d": "INTEGER",
    "hrv_status": "TEXT",
    "hrv_cv_pct": "REAL",
    "resting_hr": "INTEGER",
    "resting_hr_baseline": "INTEGER",
    "stress_avg": "INTEGER",
    "stress_max": "INTEGER",
    "stress_high_min": "INTEGER",
    "body_battery_morning": "INTEGER",
    "body_battery_evening": "INTEGER",
    "body_battery_charged": "INTEGER",
    "body_battery_spent": "INTEGER",
    "readiness_score": "INTEGER",
    "readiness_level": "TEXT",
    "recovery_time_h": "REAL",
    "spo2_avg": "REAL",
    "spo2_min": "REAL",
    "respiration_avg": "REAL",
    "respiration_min": "REAL",
    "respiration_max": "REAL",
    "steps": "INTEGER",
    "active_calories": "INTEGER",
    "total_calories": "INTEGER",
    "weight_kg": "REAL",
    "body_fat_pct": "REAL",
    "muscle_mass_kg": "REAL",
    "body_water_pct": "REAL",
    "bmi": "REAL",
    "vo2max": "REAL",
    "fitness_age": "INTEGER",
    "data_sources_json": "TEXT NOT NULL DEFAULT '{}'",
    "quality_flags_json": "TEXT NOT NULL DEFAULT '[]'",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}

_ACCOUNT_V2_COLUMNS: dict[str, str] = {
    "garmin_email": "TEXT NOT NULL DEFAULT ''",
    "encrypted_session_json": "BLOB",
    "account_timezone": "TEXT",
    "last_login_at": "TEXT",
    "last_sync_at": "TEXT",
    "session_status": "TEXT NOT NULL DEFAULT 'disconnected'",
    "session_state_updated_at": "TEXT",
    "last_auth_error": "TEXT",
    "failed_auth_attempts": "INTEGER NOT NULL DEFAULT 0",
    "failed_fetch_attempts": "INTEGER NOT NULL DEFAULT 0",
    "created_at": "TEXT NOT NULL DEFAULT ''",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}


def _is_memory(path: str | Path) -> bool:
    return str(path) == ":memory:"


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a connection with the project's SQLite pragmas."""
    try:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn
    except sqlite3.Error as exc:
        raise GarminDatabaseError("cannot open Garmin database") from exc


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    if column not in _column_names(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def migrate(conn: sqlite3.Connection) -> int:
    """Create/upgrade the schema and return the resulting version."""
    try:
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current > SCHEMA_VERSION:
            raise GarminDatabaseError(
                f"database schema v{current} is newer than supported v{SCHEMA_VERSION}"
            )
        conn.executescript(SCHEMA_SQL)
        existing_tables = _table_names(conn)
        if "garmin_daily" in existing_tables:
            for column, definition in _DAILY_V2_COLUMNS.items():
                _ensure_column(conn, "garmin_daily", column, definition)
        if "garmin_accounts" in existing_tables:
            for column, definition in _ACCOUNT_V2_COLUMNS.items():
                _ensure_column(conn, "garmin_accounts", column, definition)
        if "garmin_plan_reviews" in existing_tables:
            _ensure_column(
                conn,
                "garmin_plan_reviews",
                "applied",
                "INTEGER NOT NULL DEFAULT 0",
            )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        return SCHEMA_VERSION
    except GarminDatabaseError:
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise GarminDatabaseError("Garmin database migration failed") from exc


def init_db(path: str | Path, *, ensure_parent: bool = True) -> sqlite3.Connection:
    """Create/open a database and apply migrations."""
    db_path = Path(path).expanduser()
    if not _is_memory(path) and ensure_parent:
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = connect(db_path)
    migrate(conn)
    if not _is_memory(path):
        for candidate in (
            db_path,
            Path(f"{db_path}-wal"),
            Path(f"{db_path}-shm"),
        ):
            if candidate.exists():
                try:
                    os.chmod(candidate, 0o600)
                except OSError:
                    pass
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def tables(conn: sqlite3.Connection) -> set[str]:
    """Expose table names for diagnostics/tests."""
    return _table_names(conn)
