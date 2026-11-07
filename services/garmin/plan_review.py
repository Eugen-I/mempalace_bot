"""Weekly plan review and explicit, user-confirmed adaptation.

The review is deterministic: it reads the last seven days of Garmin data,
check-ins and training load, derives adherence/readiness/ACWR, and proposes at
most one conservative change.  Nothing is applied until the user confirms.
"""

from __future__ import annotations

import html
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .analytics import build_report
from .models import (
    Checkin,
    PlanSession,
    SafetyFlag,
    TrainingPlan,
    UserProfile,
)
from .readiness import assess_readiness


@dataclass
class PlanReview:
    plan_id: str
    user_id: int
    week_index: int
    review_date: str
    readiness: str
    decision: str
    changes: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    review_id: int | None = None
    applied: bool = False


DECISION_LABELS = {
    "keep": "оставить план без изменений",
    "reduce": "снизить объём на 30%",
    "deload": "разгрузочная неделя (−35% объёма)",
    "progress": "продолжать прогрессию по плану",
    "rest": "отдых и активное восстановление",
    "medical": "остановиться и обсудить с врачом",
}

READINESS_EMOJI = {"green": "🟢", "amber": "🟡", "red": "🔴", "unknown": "⚪"}
READINESS_LABELS = {
    "green": "можно тренироваться",
    "amber": "снизить нагрузку",
    "red": "нужно восстановление",
    "unknown": "недостаточно данных",
}


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _week_index(plan: TrainingPlan, today: date) -> int:
    if not plan.weeks:
        return 1
    iso = today.isoformat()
    for week in plan.weeks:
        dates = sorted(session.date for session in week.sessions)
        if dates and dates[0] <= iso <= dates[-1]:
            return week.week
    first = min(
        (session.date for week in plan.weeks for session in week.sessions),
        default=iso,
    )
    if iso < first:
        return 1
    return plan.weeks[-1].week


def _window_start(today: date, days: int = 7) -> str:
    return (today - timedelta(days=days - 1)).isoformat()


def _checkins(
    conn: sqlite3.Connection, user_id: int, today: date, days: int = 7
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM garmin_checkins"
        " WHERE user_id = ? AND date BETWEEN ? AND ?"
        " ORDER BY date DESC, created_at DESC",
        (int(user_id), _window_start(today, days), today.isoformat()),
    ).fetchall()


def _adherence(
    conn: sqlite3.Connection,
    user_id: int,
    plan: TrainingPlan,
    week_index: int,
    today: date,
    rows: list[sqlite3.Row],
) -> tuple[int | None, str | None]:
    values = [
        bool(row["adherence"])
        for row in rows
        if row["adherence"] is not None
    ]
    if values:
        return round(100 * sum(values) / len(values)), "чек-ины"

    week = next((item for item in plan.weeks if item.week == week_index), None)
    if week is None:
        return None, None
    planned = sum(
        1
        for session in week.sessions
        if session.type != "rest" and session.date <= today.isoformat()
    )
    if planned <= 0:
        return None, None
    activity = conn.execute(
        "SELECT COUNT(*) FROM garmin_activities"
        " WHERE user_id = ? AND date(start_time) BETWEEN ? AND ?",
        (int(user_id), _window_start(today), today.isoformat()),
    ).fetchone()
    done = int(activity[0] or 0)
    if done == 0:
        return None, None
    return round(100 * min(done, planned) / planned), "активности (оценка)"


def _training(
    conn: sqlite3.Connection, user_id: int, today: date
) -> dict[str, Any]:
    week = conn.execute(
        "SELECT COALESCE(SUM(training_load), 0),"
        " COALESCE(SUM(duration_min), 0), COUNT(*)"
        " FROM garmin_activities"
        " WHERE user_id = ? AND date(start_time) BETWEEN ? AND ?",
        (int(user_id), _window_start(today), today.isoformat()),
    ).fetchone()
    chronic = conn.execute(
        "SELECT COALESCE(SUM(training_load), 0)"
        " FROM garmin_activities"
        " WHERE user_id = ? AND date(start_time) BETWEEN ? AND ?",
        (
            int(user_id),
            (today - timedelta(days=27)).isoformat(),
            (today - timedelta(days=7)).isoformat(),
        ),
    ).fetchone()
    week_load = float(week[0] or 0)
    chronic_load = float(chronic[0] or 0)
    chronic_weekly = chronic_load / 3.0
    acwr = round(week_load / chronic_weekly, 2) if chronic_weekly > 0 else None
    return {
        "week_load": round(week_load, 1),
        "week_minutes": round(float(week[1] or 0), 1),
        "activities": int(week[2] or 0),
        "chronic_weekly_load": round(chronic_weekly, 1),
        "acwr": acwr,
    }


def _previous_green_weeks(
    conn: sqlite3.Connection, plan_id: str, week_index: int
) -> int:
    rows = conn.execute(
        "SELECT readiness, decision FROM garmin_plan_reviews"
        " WHERE plan_id = ? AND week_index < ?"
        " ORDER BY week_index DESC LIMIT 2",
        (plan_id, int(week_index)),
    ).fetchall()
    if len(rows) < 2:
        return 0
    return sum(
        1
        for row in rows
        if row["readiness"] == "green" and row["decision"] in {"keep", "progress"}
    )


def _decision(
    *,
    readiness: str,
    adherence: int | None,
    acwr: float | None,
    pain: int,
    sleep_debt: float,
    green_weeks: int,
) -> str:
    if pain >= 4:
        return "medical"
    if readiness == "red" or sleep_debt > 5.0:
        return "deload"
    if adherence is not None and adherence < 70:
        return "reduce"
    if acwr is not None and acwr > 1.5:
        return "reduce"
    if (
        readiness == "green"
        and (adherence is None or adherence >= 70)
        and (acwr is None or acwr <= 1.3)
        and green_weeks >= 2
    ):
        return "progress"
    return "keep"


def _changes(decision: str) -> list[dict[str, Any]]:
    if decision == "medical":
        return [{"action": "medical_stop", "scope": "now"}]
    if decision == "deload":
        return [{"action": "deload", "percent": 35, "scope": "current_or_next_week"}]
    if decision == "reduce":
        return [
            {"action": "reduce_volume", "percent": 30, "scope": "current_or_next_week"}
        ]
    if decision == "progress":
        return [{"action": "progress", "percent": 5, "scope": "as_planned"}]
    return []


def build_review(
    conn: sqlite3.Connection,
    user_id: int,
    plan: TrainingPlan,
    profile: UserProfile,
    *,
    today: date | None = None,
) -> PlanReview:
    """Build a deterministic weekly review without changing the plan."""
    day = today or date.today()
    week_index = _week_index(plan, day)
    rows = _checkins(conn, user_id, day)

    latest_checkin: Checkin | None = None
    if rows:
        row = rows[0]
        latest_checkin = Checkin(
            date=str(row["date"]),
            kind=str(row["kind"]),
            sleep_h=row["sleep_h"],
            sleep_quality=row["sleep_quality"],
            hrv=row["hrv"],
            rhr=row["rhr"],
            soreness=row["soreness"],
            pain_score=row["pain_score"],
            pain_location=row["pain_location"],
            mood=row["mood"],
            stress=row["stress"],
            adherence=(
                None if row["adherence"] is None else bool(row["adherence"])
            ),
            notes=row["notes"],
        )

    report = build_report(conn, user_id=user_id, days=7, end_date=day)
    readiness = assess_readiness(report, checkin=latest_checkin)
    sleep_series = report.series.get("sleep_hours")
    sleep_values = [
        float(value)
        for value in (sleep_series.values if sleep_series else [])
        if value is not None
    ]
    sleep_avg = round(sum(sleep_values) / len(sleep_values), 2) if sleep_values else None
    sleep_debt = round(
        sum(max(0.0, profile.sleep_target_h - value) for value in sleep_values), 2
    )
    short_nights = sum(1 for value in sleep_values if value < 6.0)

    hrv = report.series.get("hrv")
    hrv_delta = None
    if hrv is not None and hrv.avg_7d is not None and hrv.baseline:
        hrv_delta = round((hrv.avg_7d - hrv.baseline) / hrv.baseline * 100, 1)
    rhr = report.series.get("resting_hr")
    rhr_delta = None
    if rhr is not None and rhr.avg_7d is not None and rhr.baseline is not None:
        rhr_delta = round(rhr.avg_7d - rhr.baseline, 1)

    adherence, adherence_source = _adherence(
        conn, user_id, plan, week_index, day, rows
    )
    training = _training(conn, user_id, day)
    pain = max(
        (int(row["pain_score"] or 0) for row in rows),
        default=0,
    )
    green_weeks = _previous_green_weeks(conn, plan.plan_id, week_index)
    decision = _decision(
        readiness=readiness.level,
        adherence=adherence,
        acwr=training["acwr"],
        pain=pain,
        sleep_debt=sleep_debt,
        green_weeks=green_weeks,
    )

    reasons: list[str] = list(readiness.reasons)
    if sleep_avg is not None:
        reasons.append(f"сон {sleep_avg:.1f} ч за 7 дней")
    if sleep_debt:
        reasons.append(f"долг сна {sleep_debt:.1f} ч")
    if short_nights:
        reasons.append(f"{short_nights} ночи короче 6 ч")
    if hrv_delta is not None:
        reasons.append(f"HRV {hrv_delta:+.0f}% к baseline")
    if rhr_delta is not None:
        reasons.append(f"пульс покоя {rhr_delta:+.0f} к baseline")
    if adherence is not None:
        reasons.append(f"выполнено {adherence}% ({adherence_source})")
    if training["acwr"] is not None:
        reasons.append(f"ACWR {training['acwr']:.2f}")
    if pain:
        reasons.append(f"боль {pain}/10")
    rationale = "; ".join(dict.fromkeys(reasons)) or "значимых отклонений нет"

    return PlanReview(
        plan_id=plan.plan_id,
        user_id=int(user_id),
        week_index=week_index,
        review_date=day.isoformat(),
        readiness=readiness.level,
        decision=decision,
        changes=_changes(decision),
        rationale=rationale,
        metrics={
            "sleep_avg_h": sleep_avg,
            "sleep_debt_h": sleep_debt,
            "short_nights": short_nights,
            "hrv_delta_pct": hrv_delta,
            "rhr_delta": rhr_delta,
            "adherence_pct": adherence,
            "adherence_source": adherence_source,
            "pain": pain,
            "green_weeks": green_weeks,
            **training,
        },
    )


def apply_review(
    plan: TrainingPlan,
    review: PlanReview,
    *,
    today: date | None = None,
) -> TrainingPlan:
    """Return a new plan with the confirmed weekly change, or the same plan."""
    if review.decision in {"keep", "progress"}:
        return plan

    day = today or date.today()
    updated = plan.model_copy(deep=True)
    updated.plan_id = uuid.uuid4().hex[:16]

    index = max(0, min(review.week_index - 1, len(updated.weeks) - 1))
    week = updated.weeks[index]
    remaining = [
        session
        for session in week.sessions
        if date.fromisoformat(session.date) >= day
    ]
    if not remaining and index + 1 < len(updated.weeks):
        index += 1
        week = updated.weeks[index]

    changed = 0
    for position, session in enumerate(week.sessions):
        session_day = date.fromisoformat(session.date)
        if session_day < day or session.type == "rest":
            continue
        if review.decision in {"rest", "medical"}:
            if session.type == "mobility":
                continue
            week.sessions[position] = PlanSession(
                date=session.date,
                type="rest",
                title=(
                    "Пауза до консультации врача"
                    if review.decision == "medical"
                    else "Отдых по состоянию"
                ),
                duration_min=0,
                intensity="—",
                purpose=review.rationale,
                citations=list(session.citations),
            )
        else:
            factor = 0.65 if review.decision == "deload" else 0.7
            duration = session.duration_min or 0
            week.sessions[position] = session.model_copy(
                update={
                    "duration_min": (
                        max(15, round(duration * factor)) if duration else 0
                    ),
                    "intensity": (
                        "RPE 4–5, техника"
                        if review.decision == "deload"
                        else "Z2/RPE 5–6, без интервалов"
                    ),
                    "title": session.title
                    + (
                        " · разгрузка"
                        if review.decision == "deload"
                        else " · адаптировано"
                    ),
                }
            )
        changed += 1

    severity = "critical" if review.decision == "medical" else "info"
    updated.safety_flags.append(
        SafetyFlag(
            code="weekly_review",
            severity=severity,
            text=(
                f"Недельный обзор, неделя {review.week_index}: "
                f"{DECISION_LABELS.get(review.decision, review.decision)}. "
                f"{review.rationale}"
            ),
        )
    )
    if changed == 0:
        updated.safety_flags.append(
            SafetyFlag(
                code="weekly_review_no_sessions",
                severity="info",
                text="В периоде обзора не осталось сессий для изменения.",
            )
        )
    return updated


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def review_text(review: PlanReview) -> str:
    """Compact Russian diff for Telegram."""
    metrics = review.metrics
    lines = [
        f"📈 <b>Недельный обзор · неделя {review.week_index}</b>",
        f"Готовность: {READINESS_EMOJI.get(review.readiness, '⚪')} "
        f"{_esc(READINESS_LABELS.get(review.readiness, review.readiness))}",
    ]
    parts = []
    if metrics.get("sleep_avg_h") is not None:
        parts.append(f"сон {metrics['sleep_avg_h']:.1f} ч")
    if metrics.get("hrv_delta_pct") is not None:
        parts.append(f"HRV {metrics['hrv_delta_pct']:+.0f}%")
    if metrics.get("rhr_delta") is not None:
        parts.append(f"пульс {metrics['rhr_delta']:+.0f}")
    if parts:
        lines.append(" · ".join(parts))
    load = []
    if metrics.get("acwr") is not None:
        load.append(f"ACWR {metrics['acwr']:.2f}")
    if metrics.get("adherence_pct") is not None:
        load.append(f"выполнено {metrics['adherence_pct']}%")
    if metrics.get("week_minutes"):
        load.append(f"{metrics['week_minutes']:.0f} мин")
    if load:
        lines.append("Нагрузка: " + " · ".join(load))
    if metrics.get("pain"):
        lines.append(f"Боль: {metrics['pain']}/10")
    lines.append("")
    lines.append(
        "Решение: "
        + _esc(DECISION_LABELS.get(review.decision, review.decision))
        + "."
    )
    if review.changes:
        change = review.changes[0]
        if change.get("percent"):
            lines.append(
                f"Изменение: {_esc(change['action'])} · {change['percent']}% · "
                f"{_esc(change['scope'])}"
            )
    lines.append(f"Почему: {_esc(review.rationale)}.")
    lines.append("")
    lines.append(
        "Это вероятная связь, не диагноз. Без вашего подтверждения план "
        "не меняется."
    )
    return "\n".join(lines)


def save_review(
    conn: sqlite3.Connection,
    user_id: int,
    review: PlanReview,
) -> int:
    payload = {
        "changes": review.changes,
        "metrics": review.metrics,
        "applied": review.applied,
    }
    cursor = conn.execute(
        "INSERT INTO garmin_plan_reviews"
        " (plan_id, user_id, week_index, review_date, readiness, decision,"
        "  changes_json, rationale, applied, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            review.plan_id,
            int(user_id),
            int(review.week_index),
            review.review_date,
            review.readiness,
            review.decision,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            review.rationale,
            int(review.applied),
            _utcnow(),
        ),
    )
    conn.commit()
    review.review_id = int(cursor.lastrowid or 0)
    return review.review_id


def mark_review_applied(
    conn: sqlite3.Connection,
    review_id: int,
    *,
    applied: bool = True,
) -> None:
    row = conn.execute(
        "SELECT changes_json FROM garmin_plan_reviews WHERE id = ?",
        (int(review_id),),
    ).fetchone()
    if row is None:
        return
    try:
        payload = json.loads(row["changes_json"])
    except (TypeError, ValueError):
        payload = {}
    payload["applied"] = bool(applied)
    conn.execute(
        "UPDATE garmin_plan_reviews SET changes_json = ?, applied = ? WHERE id = ?",
        (json.dumps(payload, ensure_ascii=False, sort_keys=True), int(applied), int(review_id)),
    )
    conn.commit()


def latest_review(
    conn: sqlite3.Connection, plan_id: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM garmin_plan_reviews WHERE plan_id = ?"
        " ORDER BY week_index DESC, id DESC LIMIT 1",
        (plan_id,),
    ).fetchone()


def get_review(
    conn: sqlite3.Connection, review_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM garmin_plan_reviews WHERE id = ?",
        (int(review_id),),
    ).fetchone()


def review_from_row(row: sqlite3.Row) -> PlanReview:
    """Rebuild a review from its persisted row."""
    try:
        payload = json.loads(row["changes_json"])
    except (TypeError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return PlanReview(
        plan_id=str(row["plan_id"]),
        user_id=int(row["user_id"]),
        week_index=int(row["week_index"]),
        review_date=str(row["review_date"]),
        readiness=str(row["readiness"]),
        decision=str(row["decision"]),
        changes=list(payload.get("changes") or []),
        rationale=str(row["rationale"]),
        metrics=dict(payload.get("metrics") or {}),
        review_id=int(row["id"]),
        applied=bool(row["applied"]),
    )
