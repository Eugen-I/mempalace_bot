"""Deterministic analytics for Garmin reports.

The AI layer never computes numbers.  This module produces the report contract:
series, baselines, coverage, flags, rule-based cause candidates, weekly
aggregates, and activity summaries.  Missing values stay missing; they are
never interpolated into the report's numbers.
"""

from __future__ import annotations

import json
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
    event_correlations: list[dict[str, Any]] = field(default_factory=list)
    extended_metrics: dict[str, Any] = field(default_factory=dict)

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


def _sleep_architecture_and_consistency(rows: list[Any]) -> dict[str, Any]:
    """Parse sleep_stages_json and sleep_midpoint_min across daily rows."""
    deep_pcts: list[float] = []
    rem_pcts: list[float] = []
    light_pcts: list[float] = []
    awake_mins: list[float] = []
    shifted_midpoints: list[float] = []

    for row in rows:
        try:
            raw_stages = row["sleep_stages_json"]
        except (KeyError, IndexError):
            raw_stages = None
        if raw_stages:
            try:
                stages = (
                    json.loads(raw_stages)
                    if isinstance(raw_stages, str)
                    else raw_stages
                )
            except (TypeError, ValueError):
                stages = None
            if isinstance(stages, dict):
                deep = _num_opt(stages.get("deep") or stages.get("deep_min"))
                light = _num_opt(stages.get("light") or stages.get("light_min"))
                rem = _num_opt(stages.get("rem") or stages.get("rem_min"))
                awake = _num_opt(stages.get("awake") or stages.get("awake_min"))
                if awake is not None and awake >= 0:
                    awake_mins.append(awake)
                d_val = deep or 0.0
                l_val = light or 0.0
                r_val = rem or 0.0
                asleep = d_val + l_val + r_val
                if asleep > 0:
                    deep_pcts.append(round(d_val / asleep * 100.0, 1))
                    rem_pcts.append(round(r_val / asleep * 100.0, 1))
                    light_pcts.append(round(l_val / asleep * 100.0, 1))

        midpoint = _row_value(row, "sleep_midpoint_min")
        if midpoint is not None and 0 <= midpoint < 1440:
            shifted = midpoint - 1440.0 if midpoint >= 720.0 else midpoint
            shifted_midpoints.append(shifted)

    out: dict[str, Any] = {}
    if deep_pcts or rem_pcts or awake_mins:
        arch: dict[str, Any] = {"nights_count": max(len(deep_pcts), len(awake_mins))}
        if deep_pcts:
            arch["deep_pct_avg"] = round(statistics.fmean(deep_pcts), 1)
            arch["deep_pct_latest"] = deep_pcts[-1]
        if rem_pcts:
            arch["rem_pct_avg"] = round(statistics.fmean(rem_pcts), 1)
            arch["rem_pct_latest"] = rem_pcts[-1]
        if light_pcts:
            arch["light_pct_avg"] = round(statistics.fmean(light_pcts), 1)
        if awake_mins:
            arch["awake_min_avg"] = round(statistics.fmean(awake_mins), 1)
            arch["awake_min_latest"] = round(awake_mins[-1], 1)
        out["sleep_architecture"] = arch

    if shifted_midpoints:
        avg_shift = statistics.fmean(shifted_midpoints)
        avg_mod = int(round(avg_shift)) % 1440
        hh, mm = divmod(avg_mod, 60)
        cons: dict[str, Any] = {
            "avg_midpoint": f"{hh:02d}:{mm:02d}",
            "nights_count": len(shifted_midpoints),
        }
        if len(shifted_midpoints) >= 2:
            cons["midpoint_stdev_min"] = round(
                statistics.pstdev(shifted_midpoints), 1
            )
        out["sleep_consistency"] = cons
    return out


def _num_opt(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _workout_to_sleep_lag(
    rows: list[Any],
    activity_rows: list[Any] | None,
) -> dict[str, Any] | None:
    """Compare recovery metrics on nights following workouts vs rest days."""
    if not rows or not activity_rows:
        return None
    rows_by_date = {str(r["date"]): r for r in rows}
    workout_dates: set[str] = set()
    for act in activity_rows:
        day_str = str(act["start_time"] or "")[:10]
        dur = float(act["duration_min"] or 0.0)
        load = float(act["training_load"] or 0.0)
        if day_str and (dur >= 15.0 or load > 0.0):
            workout_dates.add(day_str)
    if not workout_dates:
        return None

    post_workout_dates: set[str] = set()
    for w_day_str in workout_dates:
        try:
            next_day = (date.fromisoformat(w_day_str) + timedelta(days=1)).isoformat()
        except ValueError:
            continue
        if next_day in rows_by_date:
            post_workout_dates.add(next_day)
        elif w_day_str in rows_by_date:
            post_workout_dates.add(w_day_str)

    post_rows = [rows_by_date[d] for d in sorted(post_workout_dates) if d in rows_by_date]
    rest_rows = [r for d, r in rows_by_date.items() if d not in post_workout_dates]
    if not post_rows or not rest_rows:
        return None

    lag: dict[str, Any] = {
        "workout_nights": len(post_rows),
        "rest_nights": len(rest_rows),
    }
    summary_parts: list[str] = []

    hrv_w = _mean([_row_value(r, "hrv") for r in post_rows])
    hrv_r = _mean([_row_value(r, "hrv") for r in rest_rows])
    if hrv_w is not None and hrv_r is not None:
        delta = round(hrv_w - hrv_r, 1)
        lag["hrv_after_workout_avg"] = hrv_w
        lag["hrv_after_rest_avg"] = hrv_r
        lag["hrv_delta"] = delta
        summary_parts.append(f"HRV {hrv_w:.0f} мс ({delta:+.1f} к отдыху)")

    rhr_w = _mean([_row_value(r, "resting_hr") for r in post_rows])
    rhr_r = _mean([_row_value(r, "resting_hr") for r in rest_rows])
    if rhr_w is not None and rhr_r is not None:
        delta = round(rhr_w - rhr_r, 1)
        lag["rhr_after_workout_avg"] = rhr_w
        lag["rhr_after_rest_avg"] = rhr_r
        lag["rhr_delta"] = delta
        summary_parts.append(f"пульс покоя {rhr_w:.0f} ({delta:+.1f} к отдыху)")

    score_w = _mean([_row_value(r, "sleep_score") for r in post_rows])
    score_r = _mean([_row_value(r, "sleep_score") for r in rest_rows])
    if score_w is not None and score_r is not None:
        delta = round(score_w - score_r, 1)
        lag["sleep_score_after_workout_avg"] = score_w
        lag["sleep_score_after_rest_avg"] = score_r
        lag["sleep_score_delta"] = delta
        summary_parts.append(f"Sleep Score {score_w:.0f} ({delta:+.1f})")

    stress_w = _mean([_row_value(r, "stress_avg") for r in post_rows])
    stress_r = _mean([_row_value(r, "stress_avg") for r in rest_rows])
    if stress_w is not None and stress_r is not None:
        delta = round(stress_w - stress_r, 1)
        lag["stress_after_workout_avg"] = stress_w
        lag["stress_after_rest_avg"] = stress_r
        lag["stress_delta"] = delta

    if not summary_parts:
        return None
    lag["summary"] = "После тренировок vs дни отдыха: " + ", ".join(summary_parts)
    return lag


def _extended_metrics(
    rows: list[Any],
    series: dict[str, MetricSeries],
    activity_rows: list[Any] | None = None,
) -> dict[str, Any]:
    """Extract secondary physiological metrics from garmin_daily for AI context."""
    def _col_values(col: str) -> list[float]:
        out: list[float] = []
        for row in rows:
            val = _row_value(row, col)
            if val is not None:
                out.append(val)
        return out

    result: dict[str, Any] = {}
    for col in (
        "respiration_avg",
        "spo2_avg",
        "spo2_min",
        "body_battery_charged",
        "body_battery_spent",
        "recovery_time_h",
        "sleep_efficiency",
        "vo2max",
        "fitness_age",
    ):
        vals = _col_values(col)
        if vals:
            result[col] = {
                "latest": round(vals[-1], 1),
                "avg": round(statistics.fmean(vals), 1),
                "max": round(max(vals), 1),
                "min": round(min(vals), 1),
            }

    hrv_series = series.get("hrv")
    if hrv_series is not None:
        recent_hrv = [float(v) for v in hrv_series.values[-7:] if v is not None]
        if len(recent_hrv) >= 3:
            mean_hrv = statistics.fmean(recent_hrv)
            if mean_hrv > 0:
                cv_pct = round(statistics.pstdev(recent_hrv) / mean_hrv * 100.0, 1)
                result["hrv_cv_7d_pct"] = cv_pct

    result.update(_sleep_architecture_and_consistency(rows))
    lag = _workout_to_sleep_lag(rows, activity_rows)
    if lag is not None:
        result["workout_to_sleep_lag"] = lag
    return result


def _correlate_events(
    *,
    rows_by_date: dict[str, Any],
    series: dict[str, MetricSeries],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Correlate recorded events (illness/cold/stress/injury) with daily metrics."""
    correlations: list[dict[str, Any]] = []
    hrv_base = series["hrv"].baseline if "hrv" in series else None
    rhr_base = series["resting_hr"].baseline if "resting_hr" in series else None
    sleep_base = series["sleep_hours"].baseline if "sleep_hours" in series else None
    stress_base = series["stress_avg"].baseline if "stress_avg" in series else None
    bb_base = (
        series["body_battery_morning"].baseline
        if "body_battery_morning" in series
        else None
    )

    for event in events:
        raw_day = str(event.get("date") or "")[:10]
        try:
            ev_day = date.fromisoformat(raw_day)
        except ValueError:
            continue
        window_days = [
            (ev_day + timedelta(days=offset)).isoformat() for offset in (0, 1, 2)
        ]
        window_rows = [rows_by_date[d] for d in window_days if d in rows_by_date]
        metrics_on_day: dict[str, float] = {}
        deviations: list[str] = []

        hrv_val = _mean([_row_value(r, "hrv") for r in window_rows])
        if hrv_val is not None:
            metrics_on_day["hrv"] = round(hrv_val, 1)
            if hrv_base:
                pct = round((hrv_val - hrv_base) / hrv_base * 100.0, 0)
                metrics_on_day["hrv_delta_pct"] = pct
                if pct <= -8:
                    deviations.append(f"HRV {hrv_val:.0f} мс ({pct:+.0f}% к baseline)")

        rhr_val = _mean([_row_value(r, "resting_hr") for r in window_rows])
        if rhr_val is not None:
            metrics_on_day["resting_hr"] = round(rhr_val, 1)
            if rhr_base is not None:
                diff = round(rhr_val - rhr_base, 0)
                metrics_on_day["resting_hr_delta"] = diff
                if diff >= 3:
                    deviations.append(
                        f"пульс покоя {rhr_val:.0f} уд/мин ({diff:+.0f} к baseline)"
                    )

        sleep_val = _mean([_row_value(r, "sleep_hours") for r in window_rows])
        if sleep_val is not None:
            metrics_on_day["sleep_hours"] = round(sleep_val, 1)
            if sleep_base is not None and sleep_val - sleep_base <= -0.7:
                deviations.append(f"сон {sleep_val:.1f} ч")

        stress_val = _mean([_row_value(r, "stress_avg") for r in window_rows])
        if stress_val is not None:
            metrics_on_day["stress_avg"] = round(stress_val, 0)
            if (stress_base is not None and stress_val - stress_base >= 8) or stress_val >= 45:
                deviations.append(f"стресс {stress_val:.0f}")

        bb_val = _mean([_row_value(r, "body_battery_morning") for r in window_rows])
        if bb_val is not None:
            metrics_on_day["body_battery_morning"] = round(bb_val, 0)
            if (bb_base is not None and bb_val - bb_base <= -12) or bb_val <= 45:
                deviations.append(f"Body Battery утром {bb_val:.0f}")

        resp_val = _mean([_row_value(r, "respiration_avg") for r in window_rows])
        if resp_val is not None:
            metrics_on_day["respiration_avg"] = round(resp_val, 1)
            if resp_val >= 16.5:
                deviations.append(f"дыхание {resp_val:.1f} вд/мин")

        kind = str(event.get("kind") or "other")
        title = str(event.get("title") or kind)
        severity = str(event.get("severity") or "info")
        if deviations:
            summary = f"{raw_day} («{title}»): " + ", ".join(deviations)
        elif metrics_on_day:
            summary = f"{raw_day} («{title}»): без резких отклонений метрик от baseline"
        else:
            summary = f"{raw_day} («{title}»): нет дневных метрик Garmin за эту дату"

        correlations.append(
            {
                "date": raw_day,
                "kind": kind,
                "title": title,
                "severity": severity,
                "metrics": metrics_on_day,
                "deviations": deviations,
                "summary": summary,
            }
        )
    return correlations


def _flags(
    series: dict[str, MetricSeries],
    *,
    activities: ActivitySummary,
    events: list[dict[str, Any]] | None = None,
    event_correlations: list[dict[str, Any]] | None = None,
) -> list[Flag]:
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
                Flag(
                    "hrv_below_baseline",
                    "warning",
                    f"HRV 7д на {abs(delta):.0f}% ниже базовой нормы.",
                )
            )

    if rhr.avg_7d is not None and rhr.baseline is not None:
        delta = rhr.avg_7d - rhr.baseline
        if delta >= 5:
            flags.append(
                Flag(
                    "rhr_above_baseline",
                    "warning",
                    f"Пульс покоя 7д выше базовой нормы на {delta:.0f}.",
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

    illness_corrs = [
        item for item in (event_correlations or []) if item.get("kind") == "illness"
    ]
    if illness_corrs:
        latest_ill = illness_corrs[-1]
        sev = "warning" if latest_ill.get("severity") in {"critical", "warning"} else "info"
        flags.append(
            Flag(
                "illness_context",
                sev,
                f"Отмечена болезнь/простуда: {latest_ill['summary']}.",
            )
        )

    return flags


def _causes(
    series: dict[str, MetricSeries],
    flags: list[Flag],
    *,
    event_correlations: list[dict[str, Any]] | None = None,
    extended_metrics: dict[str, Any] | None = None,
) -> list[str]:
    codes = {flag.code for flag in flags}
    causes: list[str] = []
    for corr in (event_correlations or [])[-3:]:
        kind = corr.get("kind")
        devs = corr.get("deviations") or []
        if kind == "illness":
            if devs:
                causes.append(
                    f"Связь с болезнью/простудой ({corr['date']}, «{corr['title']}»): "
                    f"в эти дни зафиксированы {', '.join(devs)}."
                )
            else:
                causes.append(
                    f"Отмечена болезнь/простуда ({corr['date']}, «{corr['title']}») — "
                    "учитывайте её при оценке восстановления и нагрузки."
                )
        elif devs:
            causes.append(
                f"Контекст события ({corr['date']}, «{corr['title']}»): "
                f"совпал с изменением метрик ({', '.join(devs)})."
            )
    ext = extended_metrics or {}
    arch = ext.get("sleep_architecture") or {}
    deep_avg = arch.get("deep_pct_avg")
    if isinstance(deep_avg, (int, float)) and deep_avg < 13.0:
        causes.append(
            f"Доля глубокого сна снижена (ср. {deep_avg:.1f}%) — возможны поздняя нагрузка, "
            "стресс или влияние препаратов на структуру сна."
        )
    cons = ext.get("sleep_consistency") or {}
    stdev_min = cons.get("midpoint_stdev_min")
    if isinstance(stdev_min, (int, float)) and stdev_min >= 60.0:
        causes.append(
            f"Разброс середины сна ±{stdev_min:.0f} мин («социальный джетлаг») "
            "снижает качество ночного восстановления."
        )
    lag = ext.get("workout_to_sleep_lag") or {}
    hrv_delta = lag.get("hrv_delta")
    rhr_delta = lag.get("rhr_delta")
    if (isinstance(hrv_delta, (int, float)) and hrv_delta <= -5.0) or (
        isinstance(rhr_delta, (int, float)) and rhr_delta >= 3.0
    ):
        causes.append(f"Лаг-эффект тренировок на сон: {lag.get('summary')}.")

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

    events = [
        dict(row)
        for row in conn.execute(
            "SELECT date, kind, title, notes, severity FROM garmin_events"
            " WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date",
            (int(user_id), start.isoformat(), end.isoformat()),
        ).fetchall()
    ]
    event_correlations = _correlate_events(
        rows_by_date=rows_by_date,
        series=series,
        events=events,
    )
    activity_rows = _activity_rows(conn, user_id=user_id, start=start, end=end)
    extended_metrics = _extended_metrics(rows, series, activity_rows)
    activities = _activities(activity_rows)
    flags = _flags(
        series,
        activities=activities,
        events=events,
        event_correlations=event_correlations,
    )
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

    return ReportData(
        user_id=int(user_id),
        start=start.isoformat(),
        end=end.isoformat(),
        dates=[day.isoformat() for day in dates],
        series=series,
        flags=flags,
        causes=_causes(
            series,
            flags,
            event_correlations=event_correlations,
            extended_metrics=extended_metrics,
        ),
        weekly=weekly,
        activities=activities,
        missing_inputs=missing,
        confidence=confidence,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        events=events,
        event_correlations=event_correlations,
        extended_metrics=extended_metrics,
    )


def workout_comparison(
    conn,
    *,
    user_id: int,
    activity_row: Any | None = None,
    days: int = BASELINE_DAYS,
) -> dict[str, Any] | None:
    """Compare an activity against same-type activities in the prior `days` window."""
    if activity_row is None:
        activity_row = conn.execute(
            "SELECT activity_id, activity_type, name, start_time, duration_min,"
            " distance_m, calories, avg_hr, max_hr, training_load,"
            " aerobic_te, anaerobic_te"
            " FROM garmin_activities WHERE user_id = ?"
            " ORDER BY start_time DESC LIMIT 1",
            (int(user_id),),
        ).fetchone()
    if activity_row is None:
        return None

    act_type = str(activity_row["activity_type"] or "other")
    start_time_str = str(activity_row["start_time"] or "")
    try:
        act_day = date.fromisoformat(start_time_str[:10])
    except ValueError:
        act_day = date.today()
    window_start = (act_day - timedelta(days=days)).isoformat()

    peers = conn.execute(
        "SELECT duration_min, distance_m, avg_hr, training_load, aerobic_te, anaerobic_te"
        " FROM garmin_activities"
        " WHERE user_id = ? AND activity_type = ?"
        " AND date(start_time) >= ? AND start_time < ?"
        " ORDER BY start_time DESC",
        (int(user_id), act_type, window_start, start_time_str),
    ).fetchall()

    cur_dur = _row_value(activity_row, "duration_min")
    cur_dist = _row_value(activity_row, "distance_m")
    cur_hr = _row_value(activity_row, "avg_hr")
    cur_load = _row_value(activity_row, "training_load")
    cur_aer = _row_value(activity_row, "aerobic_te")
    cur_ana = _row_value(activity_row, "anaerobic_te")

    peer_dur = _mean([_row_value(p, "duration_min") for p in peers])
    peer_dist = _mean([_row_value(p, "distance_m") for p in peers])
    peer_hr = _mean([_row_value(p, "avg_hr") for p in peers])
    peer_load = _mean([_row_value(p, "training_load") for p in peers])

    dur_delta_pct = _pct_change(peer_dur, cur_dur)
    hr_delta = (
        round(cur_hr - peer_hr, 1)
        if cur_hr is not None and peer_hr is not None
        else None
    )
    load_delta_pct = _pct_change(peer_load, cur_load)

    parts: list[str] = []
    if dur_delta_pct is not None:
        parts.append(f"длительность {dur_delta_pct:+.0f}% (к ср. {peer_dur:.0f} мин)")
    if hr_delta is not None:
        parts.append(f"ЧСС ср. {hr_delta:+.0f} уд/мин (к ср. {peer_hr:.0f})")
    if load_delta_pct is not None:
        parts.append(f"нагрузка {load_delta_pct:+.0f}% (к ср. {peer_load:.0f})")

    if peers and parts:
        summary = (
            f"К среднему по {len(peers)} тренировкам «{act_type}» за {days} дн.: "
            + ", ".join(parts)
        )
    elif peers:
        summary = f"Найдено {len(peers)} тренировок «{act_type}» за {days} дн."
    else:
        summary = f"Первая тренировка типа «{act_type}» за последние {days} дн."

    return {
        "activity_type": act_type,
        "name": str(activity_row["name"] or act_type),
        "start_time": start_time_str,
        "duration_min": cur_dur,
        "distance_m": cur_dist,
        "avg_hr": cur_hr,
        "training_load": cur_load,
        "aerobic_te": cur_aer,
        "anaerobic_te": cur_ana,
        "peer_count": len(peers),
        "peer_duration_min_avg": peer_dur,
        "peer_distance_m_avg": peer_dist,
        "peer_avg_hr": peer_hr,
        "peer_training_load_avg": peer_load,
        "duration_delta_pct": dur_delta_pct,
        "hr_delta_bpm": hr_delta,
        "load_delta_pct": load_delta_pct,
        "summary": summary,
    }


def latest_extra_metric(conn, *, user_id: int, day: str, metric: str) -> float | None:
    """Small helper used by reports for optional metrics."""
    row = get_extra_metrics(conn, user_id, day).get(metric)
    return float(row["value"]) if row and isinstance(row["value"], (int, float)) else None
