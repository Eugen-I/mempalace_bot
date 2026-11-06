"""Deterministic analytics for Garmin reports.

The AI layer never computes numbers.  This module produces the report contract:
series, baselines, coverage, flags, rule-based cause candidates, weekly
aggregates, and activity summaries.  Missing values stay missing; they are
never interpolated into the report's numbers.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .repository import get_extra_metrics

DEFAULT_REPORT_DAYS = 30
BASELINE_DAYS = 28


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    unit: str
    chart: bool = True
    higher_is_better: bool | None = None
    target: float | None = None


METRICS: tuple[MetricDef, ...] = (
    MetricDef("sleep_hours", "Сон", "ч", higher_is_better=True, target=7.5),
    MetricDef("sleep_score", "Sleep score", "баллы", higher_is_better=True),
    MetricDef("hrv", "HRV", "мс", higher_is_better=True),
    MetricDef("resting_hr", "Пульс покоя", "уд/мин", higher_is_better=False),
    MetricDef("stress_avg", "Стресс", "баллы", higher_is_better=False),
    MetricDef("steps", "Шаги", "шаги", higher_is_better=True),
    MetricDef("weight_kg", "Вес", "кг", higher_is_better=None),
    MetricDef("readiness_score", "Readiness", "баллы", higher_is_better=True),
    MetricDef("body_battery_morning", "Body Battery", "баллы", higher_is_better=True),
)

METRIC_BY_KEY = {metric.key: metric for metric in METRICS}


@dataclass
class MetricSeries:
    key: str
    label: str
    unit: str
    values: list[float | None]
    baseline: float | None
    avg_7d: float | None
    avg_28d: float | None
    latest: float | None
    coverage: float
    higher_is_better: bool | None = None
    target: float | None = None


@dataclass
class WeeklySummary:
    week_start: str
    week_end: str
    sleep_hours: float | None
    hrv: float | None
    resting_hr: float | None
    stress_avg: float | None
    steps: float | None
    weight_kg: float | None
    activities: int = 0
    training_min: float = 0.0


@dataclass
class ActivitySummary:
    count: int = 0
    total_min: float = 0.0
    total_load: float = 0.0
    by_type: dict[str, int] = field(default_factory=dict)


@dataclass
class Flag:
    code: str
    severity: str
    text: str


@dataclass
class ReportData:
    user_id: int
    start: str
    end: str
    dates: list[str]
    series: dict[str, MetricSeries]
    flags: list[Flag]
    causes: list[str]
    weekly: list[WeeklySummary]
    activities: ActivitySummary
    missing_inputs: list[str]
    confidence: str
    generated_at: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def values(self, key: str) -> list[float | None]:
        return self.series[key].values if key in self.series else []


def _mean(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(statistics.fmean(present), 2) if present else None


def _pct_change(first: float | None, last: float | None) -> float | None:
    if first in (None, 0) or last is None:
        return None
    return round((last - first) / first * 100, 2)


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _query_rows(
    conn,
    *,
    user_id: int,
    start: date,
    end: date,
) -> list[Any]:
    return conn.execute(
        "SELECT * FROM garmin_daily WHERE user_id = ? AND date BETWEEN ? AND ?"
        " ORDER BY date",
        (int(user_id), start.isoformat(), end.isoformat()),
    ).fetchall()


def _row_value(row: Any, key: str) -> float | None:
    try:
        value = row[key]
    except (KeyError, IndexError):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _series(
    *,
    key: str,
    rows_by_date: dict[str, Any],
    dates: list[date],
    baseline_rows: list[Any],
) -> MetricSeries:
    metric = METRIC_BY_KEY[key]
    values = [
        _row_value(rows_by_date[day.isoformat()], key)
        if day.isoformat() in rows_by_date
        else None
        for day in dates
    ]
    baseline_values = [_row_value(row, key) for row in baseline_rows]
    baseline = _mean(baseline_values)
    if baseline is None:
        baseline = _mean(values)
    latest = next((value for value in reversed(values) if value is not None), None)
    present = [value for value in values if value is not None]
    return MetricSeries(
        key=key,
        label=metric.label,
        unit=metric.unit,
        values=values,
        baseline=baseline,
        avg_7d=_mean(values[-7:]),
        avg_28d=_mean(values[-28:]),
        latest=latest,
        coverage=round(len(present) / len(values), 2) if values else 0.0,
        higher_is_better=metric.higher_is_better,
        target=metric.target,
    )


def _week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def _weekly(
    *,
    dates: list[date],
    rows_by_date: dict[str, Any],
    activities: list[Any],
) -> list[WeeklySummary]:
    weeks: dict[date, list[date]] = {}
    for day in dates:
        weeks.setdefault(_week_bounds(day)[0], []).append(day)

    result: list[WeeklySummary] = []
    for week_start, week_days in sorted(weeks.items()):
        week_end = week_start + timedelta(days=6)
        rows = [rows_by_date[d.isoformat()] for d in week_days if d.isoformat() in rows_by_date]
        acts = [
            activity
            for activity in activities
            if week_start.isoformat() <= str(activity["start_time"])[:10] <= week_end.isoformat()
        ]
        result.append(
            WeeklySummary(
                week_start=week_start.isoformat(),
                week_end=week_end.isoformat(),
                sleep_hours=_mean([_row_value(row, "sleep_hours") for row in rows]),
                hrv=_mean([_row_value(row, "hrv") for row in rows]),
                resting_hr=_mean([_row_value(row, "resting_hr") for row in rows]),
                stress_avg=_mean([_row_value(row, "stress_avg") for row in rows]),
                steps=_mean([_row_value(row, "steps") for row in rows]),
                weight_kg=_mean([_row_value(row, "weight_kg") for row in rows]),
                activities=len(acts),
                training_min=round(
                    sum(float(activity["duration_min"] or 0) for activity in acts), 1
                ),
            )
        )
    return result


def _activity_rows(conn, *, user_id: int, start: date, end: date) -> list[Any]:
    return conn.execute(
        "SELECT activity_type, start_time, duration_min, training_load"
        " FROM garmin_activities"
        " WHERE user_id = ? AND date(start_time) BETWEEN ? AND ?",
        (int(user_id), start.isoformat(), end.isoformat()),
    ).fetchall()


def _activities(rows: list[Any]) -> ActivitySummary:
    by_type: dict[str, int] = {}
    for row in rows:
        key = str(row["activity_type"] or "other")
        by_type[key] = by_type.get(key, 0) + 1
    return ActivitySummary(
        count=len(rows),
        total_min=round(sum(float(row["duration_min"] or 0) for row in rows), 1),
        total_load=round(sum(float(row["training_load"] or 0) for row in rows), 1),
        by_type=by_type,
    )


def _flags(series: dict[str, MetricSeries], *, activities: ActivitySummary) -> list[Flag]:
    flags: list[Flag] = []
    sleep = series["sleep_hours"]
    hrv = series["hrv"]
    rhr = series["resting_hr"]
    stress = series["stress_avg"]
    steps = series["steps"]
    weight = series["weight_kg"]

    sleep_values = [v for v in sleep.values[-7:] if v is not None]
    if len([v for v in sleep_values if v < 6]) >= 2:
        flags.append(
            Flag("sleep_short", "warning", "2+ ночи сном <6 ч за последние 7 дней.")
        )
    if sleep.avg_7d is not None and sleep.target is not None:
        debt = sum(max(sleep.target - v, 0) for v in sleep_values)
        if debt > 5:
            flags.append(
                Flag("sleep_debt", "warning", f"Накопленный долг сна за 7 дней: {debt:.1f} ч.")
            )

    if hrv.avg_7d is not None and hrv.baseline:
        delta = (hrv.avg_7d - hrv.baseline) / hrv.baseline * 100
        if delta <= -10:
            flags.append(
                Flag("hrv_below_baseline", "warning", f"HRV 7д на {abs(delta):.0f}% ниже baseline.")
            )

    if rhr.avg_7d is not None and rhr.baseline is not None:
        delta = rhr.avg_7d - rhr.baseline
        if delta >= 5:
            flags.append(
                Flag(
                    "rhr_above_baseline",
                    "warning",
                    f"Пульс покоя 7д выше baseline на {delta:.0f}.",
                )
            )

    if stress.avg_7d is not None and stress.avg_7d > 50:
        flags.append(Flag("stress_high", "info", "Средний стресс за 7 дней выше 50."))

    if steps.avg_7d is not None and steps.avg_7d < 5000:
        flags.append(Flag("steps_low", "info", "Среднее число шагов за 7 дней ниже 5000."))

    weight_values = [v for v in weight.values if v is not None]
    if len(weight_values) >= 2:
        change = _pct_change(weight_values[0], weight_values[-1])
        if change is not None and abs(change) > 2.0:
            direction = "рост" if change > 0 else "снижение"
            flags.append(
                Flag("weight_change", "info", f"Вес: {direction} на {abs(change):.1f}% за период.")
            )

    if activities.count == 0:
        flags.append(Flag("no_activities", "info", "В периоде нет импортированных тренировок."))

    return flags


def _causes(series: dict[str, MetricSeries], flags: list[Flag]) -> list[str]:
    codes = {flag.code for flag in flags}
    causes: list[str] = []
    if "sleep_short" in codes or "sleep_debt" in codes:
        causes.append("Недосып или поздний отход ко сну — самый частый бытовой фактор.")
    if "hrv_below_baseline" in codes or "rhr_above_baseline" in codes:
        causes.append(
            "Стресс, болезнь, алкоголь, обезвоживание, жара или тяжёлая нагрузка "
            "могут снижать HRV и повышать пульс покоя."
        )
    if "stress_high" in codes:
        causes.append("Высокий стресс/рабочая нагрузка может ухудшать сон и восстановление.")
    if "weight_change" in codes:
        causes.append(
            "Колебания веса часто связаны с водой, солью, углеводами, циклом, "
            "тренировками и аппетитом; смотрите 7-дневное среднее, а не одну цифру."
        )
    if "no_activities" in codes:
        causes.append("Нет данных тренировок: выводы о нагрузке пока ограничены.")
    if not causes:
        causes.append("Значимых отклонений по доступным метрикам не видно.")
    return causes


def build_report(
    conn,
    *,
    user_id: int,
    days: int = DEFAULT_REPORT_DAYS,
    end_date: str | date | None = None,
) -> ReportData:
    """Build a deterministic report contract from local Garmin data."""
    if days < 1 or days > 3650:
        raise ValueError("days must be 1..3650")
    end = (
        date.fromisoformat(end_date)
        if isinstance(end_date, str)
        else end_date
        if isinstance(end_date, date)
        else date.today()
    )
    start = end - timedelta(days=days - 1)
    dates = _date_range(start, end)
    rows = _query_rows(conn, user_id=user_id, start=start, end=end)
    rows_by_date = {str(row["date"]): row for row in rows}

    baseline_start = start - timedelta(days=BASELINE_DAYS)
    baseline_rows = _query_rows(
        conn,
        user_id=user_id,
        start=baseline_start,
        end=start - timedelta(days=1),
    )
    series = {
        metric.key: _series(
            key=metric.key,
            rows_by_date=rows_by_date,
            dates=dates,
            baseline_rows=baseline_rows,
        )
        for metric in METRICS
    }

    activity_rows = _activity_rows(conn, user_id=user_id, start=start, end=end)
    activities = _activities(activity_rows)
    flags = _flags(series, activities=activities)
    weekly = _weekly(dates=dates, rows_by_date=rows_by_date, activities=activity_rows)
    missing = [
        metric.label
        for metric in METRICS
        if series[metric.key].coverage < 0.5
    ]
    key_coverage = [series[key].coverage for key in ("sleep_hours", "hrv", "resting_hr")]
    minimum_coverage = min(key_coverage)
    if minimum_coverage >= 0.8:
        confidence = "high"
    elif minimum_coverage >= 0.5:
        confidence = "medium"
    else:
        confidence = "low"

    events = [
        dict(row)
        for row in conn.execute(
            "SELECT date, kind, title, notes, severity FROM garmin_events"
            " WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date",
            (int(user_id), start.isoformat(), end.isoformat()),
        ).fetchall()
    ]

    return ReportData(
        user_id=int(user_id),
        start=start.isoformat(),
        end=end.isoformat(),
        dates=[day.isoformat() for day in dates],
        series=series,
        flags=flags,
        causes=_causes(series, flags),
        weekly=weekly,
        activities=activities,
        missing_inputs=missing,
        confidence=confidence,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        events=events,
    )


def latest_extra_metric(conn, *, user_id: int, day: str, metric: str) -> float | None:
    """Small helper used by reports for optional metrics."""
    row = get_extra_metrics(conn, user_id, day).get(metric)
    return float(row["value"]) if row and isinstance(row["value"], (int, float)) else None
