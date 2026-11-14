"""Persistence for generated training plans and their sessions."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from .models import TrainingPlan


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def save_plan(
    conn: sqlite3.Connection,
    user_id: int,
    plan: TrainingPlan,
    *,
    profile_version: int,
    validation_errors: list[str] | None = None,
    status: str = "proposed",
    model: str = "deterministic",
) -> None:
    """Upsert a plan and replace its session rows."""
    now = _utcnow()
    start = plan.weeks[0].sessions[0].date if plan.weeks else now[:10]
    end = plan.weeks[-1].sessions[-1].date if plan.weeks else start
    payload = plan.model_dump(mode="json")
    conn.execute(
        "INSERT INTO garmin_training_plans"
        " (plan_id, user_id, status, goal, start_date, end_date, horizon_weeks,"
        "  version, skeleton_json, plan_json, validation_json, evidence_version,"
        "  profile_version, prompt_version, model, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(plan_id) DO UPDATE SET"
        " status = excluded.status, plan_json = excluded.plan_json,"
        " validation_json = excluded.validation_json,"
        " updated_at = excluded.updated_at",
        (
            plan.plan_id,
            int(user_id),
            status,
            plan.goal,
            start,
            end,
            plan.horizon_weeks,
            1,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            json.dumps(validation_errors or [], ensure_ascii=False),
            "E1-E12",
            int(profile_version),
            "deterministic-v1",
            model,
            now,
            now,
        ),
    )
    conn.execute(
        "DELETE FROM garmin_plan_sessions WHERE plan_id = ?",
        (plan.plan_id,),
    )
    for week in plan.weeks:
        for session in week.sessions:
            conn.execute(
                "INSERT INTO garmin_plan_sessions"
                " (plan_id, user_id, date, week_index, session_type, title,"
                "  duration_min, intensity, structure_json, status, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?)",
                (
                    plan.plan_id,
                    int(user_id),
                    session.date,
                    week.week,
                    session.type,
                    session.title,
                    session.duration_min,
                    session.intensity,
                    json.dumps(
                        session.structure.model_dump(mode="json"),
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )
    conn.commit()


def latest_plan(
    conn: sqlite3.Connection,
    user_id: int,
) -> TrainingPlan | None:
    row = conn.execute(
        "SELECT plan_json FROM garmin_training_plans"
        " WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    return TrainingPlan.model_validate(json.loads(row["plan_json"]))


def load_plan(
    conn: sqlite3.Connection,
    plan_id: str,
) -> TrainingPlan | None:
    row = conn.execute(
        "SELECT plan_json FROM garmin_training_plans WHERE plan_id = ?",
        (str(plan_id),),
    ).fetchone()
    if row is None:
        return None
    return TrainingPlan.model_validate(json.loads(row["plan_json"]))


def set_plan_status(conn: sqlite3.Connection, plan_id: str, status: str) -> None:
    conn.execute(
        "UPDATE garmin_training_plans SET status = ?, updated_at = ?"
        " WHERE plan_id = ?",
        (status, _utcnow(), plan_id),
    )
    conn.commit()
