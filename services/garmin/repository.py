"""Parameterized repository helpers for Garmin imports.

The repository implements field-level source precedence.  A lower-priority
source (for example a full export) never overwrites a fresher online value or a
wellness-FIT value for the same field.  Partial imports only touch fields they
actually provide.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from .errors import GarminDatabaseError

SOURCE_PRIORITY = {
    "activities_csv": 0,
    "full_export": 1,
    "wellness_csv": 1,
    "wellness_fit": 2,
    "online": 3,
    "manual": 4,
}

DAILY_FIELDS = {
    "sleep_hours",
    "sleep_score",
    "sleep_stages_json",
    "sleep_efficiency",
    "sleep_latency_min",
    "sleep_midpoint_min",
    "hrv",
    "hrv_baseline_7d",
    "hrv_baseline_28d",
    "hrv_status",
    "hrv_cv_pct",
    "resting_hr",
    "resting_hr_baseline",
    "stress_avg",
    "stress_max",
    "stress_high_min",
    "body_battery_morning",
    "body_battery_evening",
    "body_battery_charged",
    "body_battery_spent",
    "readiness_score",
    "readiness_level",
    "recovery_time_h",
    "spo2_avg",
    "spo2_min",
    "respiration_avg",
    "respiration_min",
    "respiration_max",
    "steps",
    "active_calories",
    "total_calories",
    "weight_kg",
    "body_fat_pct",
    "muscle_mass_kg",
    "body_water_pct",
    "bmi",
    "vo2max",
    "fitness_age",
}

_DAILY_META = {"user_id", "date", "data_sources_json", "quality_flags_json", "updated_at"}

ACTIVITY_FIELDS = {
    "activity_id",
    "start_time",
    "activity_type",
    "name",
    "duration_min",
    "distance_m",
    "calories",
    "avg_hr",
    "max_hr",
    "training_load",
    "aerobic_te",
    "anaerobic_te",
    "avg_pace_s_per_km",
    "elevation_gain_m",
    "raw_json",
}

_ACTIVITY_META = {"user_id", "source", "updated_at"}


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _priority(source: str | None) -> int:
    return SOURCE_PRIORITY.get(source or "", 0)


def _json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _validate_daily_row(row: dict[str, Any]) -> None:
    unknown = set(row) - DAILY_FIELDS - _DAILY_META
    if unknown:
        raise GarminDatabaseError(f"unknown daily columns: {sorted(unknown)}")
    if "user_id" not in row or "date" not in row:
        raise GarminDatabaseError("daily row requires user_id and date")


def upsert_daily(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    source: str | None = None,
) -> str:
    """Insert/update a partial daily row; return inserted/updated/skipped."""
    _validate_daily_row(row)
    user_id = int(row["user_id"])
    date = str(row["date"])
    incoming_source = source or str(row.get("source") or "wellness_fit")
    now = _utcnow()

    values = {key: row.get(key) for key in DAILY_FIELDS if key in row}
    incoming_sources = _json_dict(row.get("data_sources_json"))
    for key, value in values.items():
        if value is not None:
            incoming_sources.setdefault(key, incoming_source)
    incoming_flags = _json_list(row.get("quality_flags_json"))

    existing = conn.execute(
        "SELECT * FROM garmin_daily WHERE user_id = ? AND date = ?",
        (user_id, date),
    ).fetchone()

    if existing is None:
        columns = ["user_id", "date", *values.keys(), "data_sources_json",
                   "quality_flags_json", "updated_at"]
        params = [
            user_id,
            date,
            *values.values(),
            json.dumps(incoming_sources, ensure_ascii=False, sort_keys=True),
            json.dumps(sorted(set(incoming_flags)), ensure_ascii=False),
            now,
        ]
        placeholders = ", ".join("?" for _ in columns)
        try:
            conn.execute(
                f"INSERT INTO garmin_daily ({', '.join(columns)})"  # nosec B608
                f" VALUES ({placeholders})",
                params,
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise GarminDatabaseError("cannot insert daily row") from exc
        return "inserted"

    existing_sources = _json_dict(existing["data_sources_json"])
    updates: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        current_source = existing_sources.get(key)
        if _priority(current_source) > _priority(incoming_source):
            continue
        if existing[key] == value and current_source == incoming_source:
            continue
        updates[key] = value
        existing_sources[key] = incoming_source

    merged_flags = sorted(
        set(_json_list(existing["quality_flags_json"])) | set(incoming_flags)
    )
    flags_changed = merged_flags != _json_list(existing["quality_flags_json"])
    if not updates and not flags_changed:
        return "skipped"

    updates["data_sources_json"] = json.dumps(
        existing_sources, ensure_ascii=False, sort_keys=True
    )
    updates["quality_flags_json"] = json.dumps(merged_flags, ensure_ascii=False)
    updates["updated_at"] = now
    assignments = ", ".join(f"{key} = ?" for key in updates)
    params = [*updates.values(), user_id, date]
    try:
        conn.execute(
            f"UPDATE garmin_daily SET {assignments}"  # nosec B608
            " WHERE user_id = ? AND date = ?",
            params,
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise GarminDatabaseError("cannot update daily row") from exc
    return "updated"


def upsert_extra_metric(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    """Insert/update one extra metric with source precedence."""
    required = {"user_id", "date", "metric", "source"}
    if not required <= set(row):
        raise GarminDatabaseError("extra metric requires user_id/date/metric/source")
    user_id = int(row["user_id"])
    date = str(row["date"])
    metric = str(row["metric"])
    source = str(row["source"])
    value = row.get("value")
    if value is None:
        return "skipped"
    now = _utcnow()

    existing = conn.execute(
        "SELECT source, value FROM garmin_extra_metrics"
        " WHERE user_id = ? AND date = ? AND metric = ?",
        (user_id, date, metric),
    ).fetchone()
    if existing is not None and _priority(existing["source"]) > _priority(source):
        return "skipped"

    try:
        conn.execute(
            "INSERT INTO garmin_extra_metrics"
            " (user_id, date, metric, value, unit, source, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id, date, metric) DO UPDATE SET"
            " value = excluded.value, unit = excluded.unit,"
            " source = excluded.source, updated_at = excluded.updated_at",
            (user_id, date, metric, value, row.get("unit"), source, now),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise GarminDatabaseError("cannot upsert extra metric") from exc
    return "inserted" if existing is None else "updated"


def _validate_activity_row(row: dict[str, Any]) -> None:
    unknown = set(row) - ACTIVITY_FIELDS - _ACTIVITY_META
    if unknown:
        raise GarminDatabaseError(f"unknown activity columns: {sorted(unknown)}")
    if not row.get("activity_id") or not row.get("start_time"):
        raise GarminDatabaseError("activity row requires activity_id and start_time")


def _serialize_raw(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def upsert_activity(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    source: str = "activities_csv",
) -> str:
    """Insert/update one activity; return inserted/updated/skipped.

    Activity provenance follows ``online > full_export > activities_csv``.
    Partial rows only update fields they actually provide.
    """
    _validate_activity_row(row)
    user_id = int(row["user_id"])
    activity_id = str(row["activity_id"])
    now = _utcnow()

    values = {
        key: _serialize_raw(row.get(key))
        for key in ACTIVITY_FIELDS
        if key in row and key not in {"activity_id", "start_time"}
    }
    values = {
        key: value
        for key, value in values.items()
        if value is not None or key == "raw_json"
    }

    existing = conn.execute(
        "SELECT * FROM garmin_activities WHERE user_id = ? AND activity_id = ?",
        (user_id, activity_id),
    ).fetchone()

    if existing is None:
        # The same workout can arrive as CSV, JSON and FIT.  Match by start
        # time + type so the better source updates one row instead of creating
        # duplicates with different synthetic ids.
        match = conn.execute(
            "SELECT activity_id FROM garmin_activities"
            " WHERE user_id = ? AND start_time = ? AND activity_type = ?",
            (user_id, str(row["start_time"]), row.get("activity_type")),
        ).fetchone()
        if match is not None:
            activity_id = str(match["activity_id"])
            existing = conn.execute(
                "SELECT * FROM garmin_activities"
                " WHERE user_id = ? AND activity_id = ?",
                (user_id, activity_id),
            ).fetchone()

    if existing is None:
        columns = ["user_id", "activity_id", "start_time", *values.keys(),
                   "source", "updated_at"]
        params = [
            user_id,
            activity_id,
            str(row["start_time"]),
            *values.values(),
            source,
            now,
        ]
        placeholders = ", ".join("?" for _ in columns)
        try:
            conn.execute(
                f"INSERT INTO garmin_activities ({', '.join(columns)})"  # nosec B608
                f" VALUES ({placeholders})",
                params,
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise GarminDatabaseError("cannot insert activity") from exc
        return "inserted"

    if _priority(existing["source"]) > _priority(source):
        return "skipped"

    updates: dict[str, Any] = {}
    for key, value in values.items():
        if value is None or key == "raw_json":
            continue
        if existing[key] == value:
            continue
        updates[key] = value
    if existing["source"] != source:
        updates["source"] = source
    if not updates:
        return "skipped"
    if values.get("raw_json") is not None:
        updates["raw_json"] = values["raw_json"]

    updates["updated_at"] = now
    assignments = ", ".join(f"{key} = ?" for key in updates)
    params = [*updates.values(), user_id, activity_id]
    try:
        conn.execute(
            f"UPDATE garmin_activities SET {assignments}"  # nosec B608
            " WHERE user_id = ? AND activity_id = ?",
            params,
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise GarminDatabaseError("cannot update activity") from exc
    return "updated"


def get_activity(
    conn: sqlite3.Connection, user_id: int, activity_id: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM garmin_activities WHERE user_id = ? AND activity_id = ?",
        (int(user_id), str(activity_id)),
    ).fetchone()


def record_raw_file(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    sha256: str,
    source: str,
    filename: str,
    size_bytes: int,
    status: str = "ok",
    error_text: str | None = None,
) -> bool:
    """Record a raw object; return True when this hash was new."""
    existing = conn.execute(
        "SELECT id FROM garmin_raw_files WHERE user_id = ? AND sha256 = ?",
        (int(user_id), sha256),
    ).fetchone()
    if existing is not None:
        conn.execute(
            "UPDATE garmin_raw_files SET status = ?, error_text = ? WHERE id = ?",
            (status, error_text, existing["id"]),
        )
        conn.commit()
        return False
    try:
        conn.execute(
            "INSERT INTO garmin_raw_files"
            " (user_id, sha256, source, filename, size_bytes, imported_at, status, error_text)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(user_id),
                sha256,
                source,
                filename,
                int(size_bytes),
                _utcnow(),
                status,
                error_text,
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise GarminDatabaseError("cannot record raw file") from exc
    return True


def start_run(conn: sqlite3.Connection, *, user_id: int, kind: str) -> int:
    try:
        cursor = conn.execute(
            "INSERT INTO garmin_runs (user_id, kind, started_at, status)"
            " VALUES (?, ?, ?, 'running')",
            (int(user_id), kind, _utcnow()),
        )
        conn.commit()
        return int(cursor.lastrowid)
    except sqlite3.Error as exc:
        conn.rollback()
        raise GarminDatabaseError("cannot start import run") from exc


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    files_total: int = 0,
    files_ok: int = 0,
    files_failed: int = 0,
    error_text: str | None = None,
) -> None:
    try:
        conn.execute(
            "UPDATE garmin_runs SET finished_at = ?, status = ?, files_total = ?,"
            " files_ok = ?, files_failed = ?, error_text = ? WHERE id = ?",
            (
                _utcnow(),
                status,
                files_total,
                files_ok,
                files_failed,
                error_text,
                run_id,
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise GarminDatabaseError("cannot finish import run") from exc


def get_daily(conn: sqlite3.Connection, user_id: int, date: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM garmin_daily WHERE user_id = ? AND date = ?",
        (int(user_id), date),
    ).fetchone()


def get_extra_metrics(
    conn: sqlite3.Connection, user_id: int, date: str
) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM garmin_extra_metrics WHERE user_id = ? AND date = ?",
        (int(user_id), date),
    ).fetchall()
    return {str(row["metric"]): row for row in rows}
