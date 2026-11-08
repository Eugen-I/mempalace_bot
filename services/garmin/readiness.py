"""Transparent green/amber/red readiness heuristic.

This is not a diagnosis and not a medical algorithm.  It combines Garmin
signals with the latest subjective check-in; any red signal blocks hard
training and points to rest or medical advice.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .analytics import ReportData
from .models import Checkin, Event
from .quadrants import QuadrantAssessment, assess_autonomic_quadrants


@dataclass
class ReadinessResult:
    level: str
    reasons: list[str] = field(default_factory=list)
    advice: str = ""
    quadrant: QuadrantAssessment | None = None

    @property
    def emoji(self) -> str:
        return {"green": "🟢", "amber": "🟡", "red": "🔴"}.get(self.level, "⚪")


def _pct_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline in (None, 0):
        return None
    return (current - baseline) / baseline * 100.0


def assess_readiness(
    report: ReportData,
    *,
    checkin: Checkin | None = None,
    events: Iterable[Event | dict[str, Any]] | None = None,
) -> ReadinessResult:
    """Return readiness plus the exact reasons that produced it."""
    reasons: list[str] = []
    level = "green"

    def escalate(target: str) -> None:
        nonlocal level
        order = {"green": 0, "amber": 1, "red": 2}
        if order[target] > order[level]:
            level = target

    sleep = report.series.get("sleep_hours")
    if sleep is not None:
        recent = [value for value in sleep.values[-7:] if value is not None]
        short_nights = sum(1 for value in recent if value < 6.0)
        if sleep.latest is not None and sleep.latest < 6.0:
            escalate("red")
            reasons.append(f"сон {sleep.latest:.1f} ч — меньше 6 ч")
        elif short_nights >= 2:
            escalate("red")
            reasons.append(f"{short_nights} ночи короче 6 ч за неделю")
        elif sleep.avg_7d is not None and sleep.avg_7d < 6.0:
            escalate("red")
            reasons.append(f"средний сон {sleep.avg_7d:.1f} ч — меньше 6 ч")
        elif sleep.avg_7d is not None and sleep.avg_7d < 7.0:
            escalate("amber")
            reasons.append(f"средний сон {sleep.avg_7d:.1f} ч — ниже 7 ч")

    hrv = report.series.get("hrv")
    if hrv is not None:
        change = _pct_change(hrv.avg_7d, hrv.baseline)
        if change is not None:
            if change <= -20:
                escalate("red")
                reasons.append(f"HRV на {abs(change):.0f}% ниже базовой нормы")
            elif change < -10:
                escalate("amber")
                reasons.append(f"HRV на {abs(change):.0f}% ниже базовой нормы")

    rhr = report.series.get("resting_hr")
    if rhr is not None and rhr.baseline is not None:
        if rhr.avg_7d is not None:
            delta = rhr.avg_7d - rhr.baseline
            if delta >= 10:
                escalate("red")
                reasons.append(f"пульс покоя +{delta:.0f} уд/мин к базовой норме")
            elif delta >= 6:
                escalate("amber")
                reasons.append(f"пульс покоя +{delta:.0f} уд/мин к базовой норме")

    stress = report.series.get("stress_avg")
    if stress is not None and stress.avg_7d is not None and stress.avg_7d >= 60:
        escalate("amber")
        reasons.append(f"высокий стресс {stress.avg_7d:.0f} баллов")

    if checkin is not None:
        if checkin.pain_score is not None:
            if checkin.pain_score >= 4:
                escalate("red")
                location = f" ({checkin.pain_location})" if checkin.pain_location else ""
                reasons.append(f"боль {checkin.pain_score}/10{location}")
            elif checkin.pain_score >= 1:
                escalate("amber")
                reasons.append(f"боль {checkin.pain_score}/10 — модифицировать нагрузку")
        if checkin.soreness is not None:
            if checkin.soreness >= 7:
                escalate("red")
                reasons.append(f"выраженная болезненность {checkin.soreness}/10")
            elif checkin.soreness >= 4:
                escalate("amber")
                reasons.append(f"болезненность {checkin.soreness}/10")
        if checkin.stress is not None and checkin.stress >= 4:
            escalate("amber")
            reasons.append(f"субъективный стресс {checkin.stress}/5")
        if checkin.mood is not None and checkin.mood <= 2:
            escalate("amber")
            reasons.append("настроение низкое — снизить требования к себе")

    try:
        end_day = date.fromisoformat(str(report.end)[:10])
    except ValueError:
        end_day = date.today()
    raw_events = list(events) if events is not None else list(report.events or [])
    for item in raw_events:
        ev_date_str: str
        ev_kind: str
        ev_title: str
        ev_sev: str
        if isinstance(item, Event):
            ev_date_str = item.date
            ev_kind = str(item.kind)
            ev_title = item.title
            ev_sev = str(item.severity)
        elif isinstance(item, dict):
            ev_date_str = str(item.get("date") or "")
            ev_kind = str(item.get("kind") or "")
            ev_title = str(item.get("title") or ev_kind)
            ev_sev = str(item.get("severity") or "info")
        else:
            continue
        try:
            ev_day = date.fromisoformat(ev_date_str[:10])
        except ValueError:
            continue
        if (end_day - ev_day).days > 7 or (end_day - ev_day).days < -1:
            continue
        if ev_kind == "illness":
            if ev_sev in {"critical", "warning"}:
                escalate("red")
                reasons.append(f"болезнь/простуда («{ev_title[:80]}»)")
            else:
                escalate("amber")
                reasons.append(f"восстановление после болезни («{ev_title[:80]}»)")
        elif ev_kind == "injury" and ev_sev in {"critical", "warning"}:
            escalate("amber")
            reasons.append(f"травма/ограничение («{ev_title[:80]}»)")

    quadrant_assessment: QuadrantAssessment | None = None
    if hrv is not None and rhr is not None:
        has_alcohol = any(
            (
                getattr(item, "kind", None) == "alcohol"
                if isinstance(item, Event)
                else (isinstance(item, dict) and item.get("kind") == "alcohol")
            )
            for item in raw_events
        )
        sleep_series = report.series.get("sleep_hours")
        sleep_debt = 0.0
        if sleep_series is not None and sleep_series.avg_7d is not None and sleep_series.target:
            sleep_debt = max(0.0, (sleep_series.target - sleep_series.avg_7d) * 7.0)

        load_high = False
        if report.activities and getattr(report.activities, "total_load", 0) > 0:
            load_flags = getattr(report, "flags", [])
            load_high = any(f.code in {"acwr_high", "load_spike"} for f in load_flags)

        quadrant_assessment = assess_autonomic_quadrants(
            hrv.values,
            rhr.values,
            hrv_baseline=hrv.baseline,
            rhr_baseline=rhr.baseline,
            acute_load_high=load_high,
            sleep_debt_h=sleep_debt,
            has_alcohol_event=has_alcohol,
        )
        if quadrant_assessment.readiness_modifier == "red":
            escalate("red")
            reasons.append(quadrant_assessment.description)
        elif quadrant_assessment.readiness_modifier == "amber":
            escalate("amber")
            reasons.append(f"вегетативный статус: {quadrant_assessment.title}")

    has_data = any(
        report.series.get(key) is not None
        and any(value is not None for value in report.series[key].values)
        for key in ("sleep_hours", "hrv", "resting_hr")
    )
    if not reasons and not has_data:
        level = "unknown"
        reasons.append("недостаточно данных для оценки восстановления")
    elif level == "amber" and len(reasons) >= 3:
        level = "red"
        reasons.append("несколько сигналов восстановления совпали")

    advice = {
        "green": "Можно выполнять план; прогрессия остаётся недельной, без резких добавок.",
        "amber": "Снизить объём на 20–40%, убрать интенсивность, оставить Z2/технику.",
        "red": "Отдых или активное восстановление; тренировку не выполнять.",
        "unknown": "Консервативный режим: лёгкая сессия или отдых до подтверждения самочувствия.",
    }[level]
    return ReadinessResult(
        level=level,
        reasons=reasons,
        advice=advice,
        quadrant=quadrant_assessment,
    )
