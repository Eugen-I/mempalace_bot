"""Deterministic data-delta engine and confirmed plan adaptation.

The engine compares the last 7 days with the previous 7 days and with the
28-day baseline.  It only recommends a change when a threshold is crossed; the
user always confirms before the stored plan is modified.
"""

from __future__ import annotations

import html
import json
import sqlite3
import statistics
import uuid
from datetime import UTC, date, datetime, timedelta

from .analytics import ReportData, build_report
from .models import (
    DeltaMetric,
    DeltaReport,
    PlanSession,
    SafetyFlag,
    TrainingPlan,
)

SLEEP_DROP_H = 0.75
HRV_DROP_PCT = -10.0
RHR_RISE = 5.0
WEIGHT_GAIN_PCT_WEEK = 0.7
WEIGHT_LOSS_PCT_WEEK = -1.5
ACWR_HIGH = 1.5
RAMP_HIGH = 0.20
ADHERENCE_LOW = 0.70


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _avg(values) -> float | None:
    present = [float(value) for value in values if value is not None]
    return statistics.fmean(present) if present else None


def _pct(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline in (None, 0):
        return None
    return (current - baseline) / baseline * 100.0


def _metric(
    name: str,
    before: float,
    after: float,
    delta: float,
    important: bool,
) -> DeltaMetric:
    return DeltaMetric.model_validate(
        {
            "metric": name,
            "from": before,
            "to": after,
            "delta": delta,
            "important": important,
        }
    )


def _window(values: list, start: int, end: int) -> list:
    return values[start:end]


def _loads(conn: sqlite3.Connection, user_id: int, today: date) -> tuple:
    def total(start: date) -> float:
        row = conn.execute(
            "SELECT COALESCE(SUM(training_load), 0) FROM garmin_activities"
            " WHERE user_id = ? AND substr(start_time, 1, 10) BETWEEN ? AND ?",
            (int(user_id), start.isoformat(), today.isoformat()),
        ).fetchone()
        return float(row[0] or 0)

    load_7 = total(today - timedelta(days=6))
    load_14 = total(today - timedelta(days=13))
    load_28 = total(today - timedelta(days=27))
    previous_7 = load_14 - load_7
    acwr = load_7 / (load_28 / 4) if load_28 > 0 else None
    ramp = (load_7 - previous_7) / previous_7 if previous_7 > 0 else None
    return load_7, acwr, ramp


def _events(conn: sqlite3.Connection, user_id: int, today: date) -> list[dict]:
    rows = conn.execute(
        "SELECT date, kind, title, severity FROM garmin_events"
        " WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date",
        (
            int(user_id),
            (today - timedelta(days=13)).isoformat(),
            today.isoformat(),
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def _checkins(conn: sqlite3.Connection, user_id: int, today: date) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM garmin_checkins WHERE user_id = ?"
        " AND date BETWEEN ? AND ? ORDER BY date DESC",
        (
            int(user_id),
            (today - timedelta(days=13)).isoformat(),
            today.isoformat(),
        ),
    ).fetchall()


def compute_delta(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: date | None = None,
) -> DeltaReport:
    """Compare recent 7 days with the previous week and the 28-day baseline."""
    end = today or date.today()
    report: ReportData = build_report(
        conn, user_id=user_id, days=42, end_date=end.isoformat()
    )
    metrics: list[DeltaMetric] = []
    context: list[str] = []

    sleep = report.series["sleep_hours"].values
    current_sleep = _avg(_window(sleep, -7, None))
    previous_sleep = _avg(_window(sleep, -14, -7))
    if current_sleep is not None and previous_sleep is not None:
        delta = current_sleep - previous_sleep
        short_nights = len(
            [
                value
                for value in _window(sleep, -7, None)
                if value is not None and value < 6
            ]
        )
        important = delta <= -SLEEP_DROP_H or short_nights >= 2
        metrics.append(
            _metric(
                "sleep_7d_avg_h",
                round(previous_sleep, 2),
                round(current_sleep, 2),
                round(delta, 2),
                important,
            )
        )
        if important:
            context.append("sleep_debt")

    hrv = report.series["hrv"].values
    current_hrv = _avg(_window(hrv, -7, None))
    baseline_hrv = _avg(_window(hrv, -42, -14))
    hrv_pct = _pct(current_hrv, baseline_hrv)
    if hrv_pct is not None:
        important = hrv_pct < HRV_DROP_PCT
        metrics.append(
            _metric(
                "hrv_7d_delta_pct",
                0.0,
                round(hrv_pct, 1),
                round(hrv_pct, 1),
                important,
            )
        )
        if important:
            context.append("hrv_low")

    rhr = report.series["resting_hr"].values
    current_rhr = _avg(_window(rhr, -7, None))
    baseline_rhr = _avg(_window(rhr, -42, -14))
    if current_rhr is not None and baseline_rhr is not None:
        delta = current_rhr - baseline_rhr
        important = delta >= RHR_RISE
        metrics.append(
            _metric(
                "resting_hr_delta",
                round(baseline_rhr, 1),
                round(current_rhr, 1),
                round(delta, 1),
                important,
            )
        )
        if important:
            context.append("rhr_high")

    weight = report.series["weight_kg"].values
    current_weight = _avg(_window(weight, -7, None))
    previous_weight = _avg(_window(weight, -14, -7))
    weight_pct = _pct(current_weight, previous_weight)
    if weight_pct is not None:
        important = weight_pct > WEIGHT_GAIN_PCT_WEEK or weight_pct < WEIGHT_LOSS_PCT_WEEK
        metrics.append(
            _metric(
                "weight_7d_trend_pct",
                round(previous_weight or 0, 1),
                round(current_weight or 0, 1),
                round(weight_pct, 2),
                important,
            )
        )
        if important:
            context.append("weight_trend")

    _load_7, acwr, ramp = _loads(conn, user_id, end)
    if acwr is not None:
        important = acwr > ACWR_HIGH or (ramp is not None and ramp > RAMP_HIGH)
        metrics.append(
            _metric(
                "acwr",
                0.0,
                round(acwr, 2),
                round(acwr - 1.0, 2),
                important,
            )
        )
        if important:
            context.append("load_spike")

    checkins = _checkins(conn, user_id, end)
    pain_scores = [
        int(row["pain_score"])
        for row in checkins
        if row["pain_score"] is not None
    ]
    if pain_scores:
        latest = pain_scores[0]
        important = latest >= 4 or (
            len(pain_scores) >= 2 and pain_scores[0] > pain_scores[1]
        )
        metrics.append(
            _metric(
                "pain_score",
                float(pain_scores[1] if len(pain_scores) > 1 else 0),
                float(latest),
                float(latest - (pain_scores[1] if len(pain_scores) > 1 else 0)),
                important,
            )
        )
        if important:
            context.append("pain")

    adherence_rows = [
        bool(row["adherence"])
        for row in checkins
        if row["adherence"] is not None
    ]
    if adherence_rows:
        adherence = sum(adherence_rows) / len(adherence_rows)
        important = adherence < ADHERENCE_LOW
        metrics.append(
            _metric(
                "adherence_7d",
                1.0,
                round(adherence, 2),
                round(adherence - 1.0, 2),
                important,
            )
        )
        if important:
            context.append("adherence_low")

    events = _events(conn, user_id, end)
    for event in events:
        if event["kind"] == "med_change":
            context.append("medication_change")
        elif event["kind"] in {"illness", "injury"}:
            context.append(event["kind"])
        elif event["kind"] in {"alcohol", "travel", "stress", "heat"}:
            context.append(event["kind"])

    important_metrics = [metric for metric in metrics if metric.important]
    red_flags = any(event["severity"] == "critical" for event in events) or (
        bool(pain_scores) and pain_scores[0] >= 4
    )
    recent_cutoff = (end - timedelta(days=6)).isoformat()
    active_illness = any(
        event["kind"] == "illness"
        and event["severity"] == "warning"
        and str(event["date"])[:10] >= recent_cutoff
        for event in events
    )
    recovering_illness = any(
        event["kind"] == "illness"
        and event["severity"] == "info"
        and str(event["date"])[:10] >= recent_cutoff
        for event in events
    )
    if red_flags:
        recommendation = "medical"
    elif active_illness or len(important_metrics) >= 3:
        recommendation = "rest"
    elif recovering_illness or important_metrics:
        recommendation = "reduce"
    else:
        recommendation = "keep"

    confidence = report.confidence
    compared_from = (end - timedelta(days=13)).isoformat()
    return DeltaReport(
        compared_from=compared_from,
        compared_to=end.isoformat(),
        new_days=sum(
            1
            for index in range(len(report.dates) - 7, len(report.dates))
            if any(
                series.values[index] is not None
                for series in report.series.values()
            )
        ),
        changed_metrics=metrics,
        likely_context=sorted(set(context)),
        recommendation_window="next_3_days",
        recommendation=recommendation,
        confidence=confidence,
        needs_confirm=True,
    )


def log_delta(
    conn: sqlite3.Connection,
    user_id: int,
    delta: DeltaReport,
    *,
    trigger: str = "manual",
    applied: bool = False,
) -> None:
    conn.execute(
        "INSERT INTO garmin_adaptation_log"
        " (user_id, date, trigger, compared_from, compared_to, delta_json,"
        "  recommendation, confidence, needs_confirm, applied, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            int(user_id),
            delta.compared_to or date.today().isoformat(),
            trigger,
            delta.compared_from,
            delta.compared_to,
            json.dumps(delta.model_dump(mode="json"), ensure_ascii=False),
            delta.recommendation,
            delta.confidence,
            int(delta.needs_confirm),
            int(applied),
            _utcnow(),
        ),
    )
    conn.commit()


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def delta_text(delta: DeltaReport) -> str:
    """Compact Russian explanation for Telegram."""
    lines = [
        "📉 <b>Что изменилось за неделю</b>",
        f"Сравнение: {_esc(delta.compared_from)} — {_esc(delta.compared_to)}",
        "",
    ]
    important = [metric for metric in delta.changed_metrics if metric.important]
    if not important:
        lines.append("Важных изменений нет. План можно не менять.")
    else:
        for metric in important:
            lines.append(
                f"• {_esc(metric.metric)}: {metric.from_value} → {metric.to_value} "
                f"({metric.delta:+})"
            )
    if delta.likely_context:
        lines.append("")
        lines.append(
            "Возможный контекст: "
            + ", ".join(_esc(item) for item in delta.likely_context)
        )
    lines.append("")
    advice = {
        "keep": "Продолжаем план без изменений.",
        "reduce": "На 3 дня снизить объём на 20–30% и убрать интенсивность.",
        "rest": "Приоритет восстановлению: отдых/лёгкая активность, без интервалов.",
        "medical": "Стоп. Есть красный флаг или боль ≥4/10 — обратитесь к врачу.",
        "deload": "Разгрузочная неделя.",
        "progress": "Можно продолжить прогрессию по плану.",
    }.get(delta.recommendation, delta.recommendation)
    lines.append(f"Рекомендация: {_esc(advice)}")
    lines.append("")
    lines.append(
        "Это вероятная связь, не диагноз. Решение всегда подтверждает пользователь."
    )
    return "\n".join(lines)


def apply_delta(
    plan: TrainingPlan,
    delta: DeltaReport,
    *,
    today: date | None = None,
) -> TrainingPlan:
    """Return a new plan with the next three days reduced; rest stays rest."""
    start = today or date.today()
    limit = start + timedelta(days=2)
    updated = plan.model_copy(deep=True)
    updated.plan_id = uuid.uuid4().hex[:16]
    changed = 0
    for week in updated.weeks:
        for index, session in enumerate(week.sessions):
            day = date.fromisoformat(session.date)
            if not (start <= day <= limit):
                continue
            if session.type == "rest":
                continue
            if delta.recommendation == "rest":
                week.sessions[index] = PlanSession(
                    date=session.date,
                    type="rest",
                    title="Отдых по состоянию",
                    duration_min=0,
                    intensity="—",
                    purpose="Восстановление из-за нескольких сигналов.",
                    citations=session.citations,
                )
            else:
                duration = session.duration_min or 0
                week.sessions[index] = session.model_copy(
                    update={
                        "duration_min": max(15, round(duration * 0.7)) if duration else 0,
                        "intensity": "Z2/RPE 5–6, без интервалов",
                        "title": session.title + " · адаптировано",
                    }
                )
            changed += 1
    updated.safety_flags.append(
        SafetyFlag(
            code="adapted",
            severity="info" if delta.recommendation != "medical" else "critical",
            text=(
                f"План адаптирован: {delta.recommendation}; "
                f"изменено сессий: {changed}."
            ),
        )
    )
    return updated
