"""Autonomic regulation quadrants combining HRV (RMSSD) and Resting Heart Rate (RHR).

Scientific foundation:
- HRV and RHR represent distinct branches/grain of the autonomic nervous system.
- Q1 (HRV↑, RHR↓): Parasympathetic dominance, optimal recovery and training readiness.
- Q2 (HRV↓, RHR↑): Sympathetic stress activation (fatigue, sleep debt, alcohol, acute illness).
- Q3 (HRV↓, RHR↓): Parasympathetic saturation (in endurance athletes under heavy load) or fatigue.
- Q4 (HRV↑, RHR↑): Mixed autonomic instability, illness/fever prodrome, artifact, or rebound.

Uses individualized Smallest Worthwhile Change (SWC = 0.5 * SD) or robust z-scores on
a rolling baseline (up to 60 days), detects streaks, and produces structured seeds for
the local LLM and training plan adaptation engine.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

QUADRANT_Q1 = "Q1_RECOVERY"
QUADRANT_Q2 = "Q2_SYMPATHETIC_STRESS"
QUADRANT_Q3 = "Q3_SATURATION"
QUADRANT_Q4 = "Q4_MIXED_INSTABILITY"
QUADRANT_UNKNOWN = "UNKNOWN"

QUADRANT_TITLES: dict[str, str] = {
    QUADRANT_Q1: "Оптимальное восстановление (вагусный тонус)",
    QUADRANT_Q2: "Симпатический стресс (нагрузка / недосып / стресс)",
    QUADRANT_Q3: "Сатурация / скрытое утомление",
    QUADRANT_Q4: "Вегетативная нестабильность (риск ОРВИ / рикошет)",
    QUADRANT_UNKNOWN: "Недостаточно данных",
}

QUADRANT_EMOJI: dict[str, str] = {
    QUADRANT_Q1: "🟢",
    QUADRANT_Q2: "🟡",
    QUADRANT_Q3: "🟠",
    QUADRANT_Q4: "🔴",
    QUADRANT_UNKNOWN: "⚪",
}


@dataclass
class QuadrantAssessment:
    quadrant: str
    title: str
    emoji: str
    description: str
    action_advice: str
    hrv_latest: float | None = None
    hrv_baseline: float | None = None
    hrv_delta_pct: float | None = None
    hrv_z_score: float | None = None
    rhr_latest: float | None = None
    rhr_baseline: float | None = None
    rhr_delta_bpm: float | None = None
    rhr_z_score: float | None = None
    streak_days: int = 1
    weekly_counts: dict[str, int] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    readiness_modifier: str = "green"  # green | amber | red
    ascii_matrix: str = ""
    seeds: dict[str, Any] = field(default_factory=dict)


def _safe_fmean(vals: Sequence[float | None]) -> float | None:
    valid = [float(v) for v in vals if v is not None and not math.isnan(v)]
    return round(statistics.fmean(valid), 2) if valid else None


def _safe_stdev(vals: Sequence[float | None]) -> float | None:
    valid = [float(v) for v in vals if v is not None and not math.isnan(v)]
    if len(valid) < 2:
        return None
    return round(statistics.stdev(valid), 2)


def compute_baseline_and_swc(
    values: Sequence[float | None],
    *,
    min_days: int = 7,
    fallback_pct: float = 0.10,
    min_swc_absolute: float = 2.0,
) -> tuple[float | None, float | None, float | None]:
    """Calculate (baseline, stdev, swc) from historical values.

    SWC (Smallest Worthwhile Change) is standardly 0.5 * SD in sports science.
    If variance is insufficient or sample is small, fallback_pct is used.
    """
    valid = [float(v) for v in values if v is not None and not math.isnan(v)]
    if len(valid) < min_days:
        if not valid:
            return None, None, None
        base = round(statistics.fmean(valid), 2)
        swc = max(round(base * fallback_pct, 2), min_swc_absolute)
        return base, None, swc

    base = round(statistics.fmean(valid), 2)
    sd = _safe_stdev(valid)
    if sd is not None and sd > 0.01:
        swc = max(round(0.5 * sd, 2), min_swc_absolute)
    else:
        swc = max(round(base * fallback_pct, 2), min_swc_absolute)
    return base, sd, swc


def classify_single_day(
    hrv: float | None,
    rhr: float | None,
    hrv_base: float | None,
    rhr_base: float | None,
    hrv_swc: float | None,
    rhr_swc: float | None,
) -> str:
    """Classify a single day into one of the four quadrants."""
    if hrv is None or rhr is None or hrv_base is None or rhr_base is None:
        return QUADRANT_UNKNOWN

    h_swc = hrv_swc if hrv_swc is not None else max(hrv_base * 0.10, 2.0)
    r_swc = rhr_swc if rhr_swc is not None else 3.0

    delta_hrv = hrv - hrv_base
    delta_rhr = rhr - rhr_base

    # HRV high vs low (relative to threshold)
    hrv_high = delta_hrv >= h_swc
    hrv_low = delta_hrv <= -h_swc

    # RHR high vs low
    rhr_high = delta_rhr >= r_swc
    rhr_low = delta_rhr <= -r_swc

    # Quadrant 1: HRV high / normal-high and RHR low / normal-low
    if (hrv_high and not rhr_high) or (rhr_low and not hrv_low):
        return QUADRANT_Q1

    # Quadrant 2: HRV low and RHR high (or significant shift in both stress directions)
    if (hrv_low and rhr_high) or (hrv_low and not rhr_low and delta_rhr >= 0):
        return QUADRANT_Q2

    # Quadrant 3: HRV low and RHR low (or neutral-low RHR with suppressed HRV)
    if hrv_low and (rhr_low or delta_rhr < 0):
        return QUADRANT_Q3

    # Quadrant 4: HRV high and RHR high
    if hrv_high and rhr_high:
        return QUADRANT_Q4

    # If within normal bounds
    if not hrv_low and not rhr_high:
        return QUADRANT_Q1

    return QUADRANT_Q2


def render_ascii_quadrant_matrix(active_quadrant: str, streak: int = 1) -> str:
    """Render a clean 2x2 ASCII matrix showing the athlete's current state."""
    q4_mark = f"[{streak}д]" if active_quadrant == QUADRANT_Q4 else "   "
    q1_mark = f"[{streak}д]" if active_quadrant == QUADRANT_Q1 else "   "
    q2_mark = f"[{streak}д]" if active_quadrant == QUADRANT_Q2 else "   "
    q3_mark = f"[{streak}д]" if active_quadrant == QUADRANT_Q3 else "   "

    lines = [
        "┌──────────────┬──────────────┐",
        "│ Q4 Нестабил. │ Q1 Восстанов.│",
        f"│ HRV↑ RHR↑{q4_mark}│ HRV↑ RHR↓{q1_mark}│",
        "├──────────────┼──────────────┤",
        "│ Q2 Стресс    │ Q3 Сатурация │",
        f"│ HRV↓ RHR↑{q2_mark}│ HRV↓ RHR↓{q3_mark}│",
        "└──────────────┴──────────────┘",
    ]
    return "\n".join(lines)


def assess_autonomic_quadrants(
    hrv_values: Sequence[float | None],
    rhr_values: Sequence[float | None],
    *,
    hrv_baseline: float | None = None,
    rhr_baseline: float | None = None,
    acute_load_high: bool = False,
    skin_temp_high: bool = False,
    respiration_high: bool = False,
    sleep_debt_h: float = 0.0,
    has_alcohol_event: bool = False,
) -> QuadrantAssessment:
    """Perform full multi-day cross-analysis of HRV and RHR series.

    Returns the latest QuadrantAssessment with streaks, readiness modifiers,
    contextual flags, and seeds for AI.
    """
    length = max(len(hrv_values), len(rhr_values))
    if length == 0:
        return QuadrantAssessment(
            quadrant=QUADRANT_UNKNOWN,
            title=QUADRANT_TITLES[QUADRANT_UNKNOWN],
            emoji=QUADRANT_EMOJI[QUADRANT_UNKNOWN],
            description="Недостаточно данных для построения вегетативных квадрантов.",
            action_advice="Продолжайте регулярные замеры сна и пульса.",
            ascii_matrix=render_ascii_quadrant_matrix(QUADRANT_UNKNOWN),
        )

    # 1. Compute or use provided baselines and SWC
    calc_hrv_base, hrv_sd, hrv_swc = compute_baseline_and_swc(
        hrv_values[:-1] if len(hrv_values) > 1 else hrv_values,
        fallback_pct=0.10,
        min_swc_absolute=2.0,
    )
    calc_rhr_base, rhr_sd, rhr_swc = compute_baseline_and_swc(
        rhr_values[:-1] if len(rhr_values) > 1 else rhr_values,
        fallback_pct=0.06,
        min_swc_absolute=2.0,
    )

    effective_hrv_base = hrv_baseline if hrv_baseline is not None else calc_hrv_base
    effective_rhr_base = rhr_baseline if rhr_baseline is not None else calc_rhr_base

    # Latest non-None points
    latest_hrv = next((v for v in reversed(hrv_values) if v is not None), None)
    latest_rhr = next((v for v in reversed(rhr_values) if v is not None), None)

    has_missing_data = (
        latest_hrv is None
        or latest_rhr is None
        or effective_hrv_base is None
        or effective_rhr_base is None
    )
    if has_missing_data:
        return QuadrantAssessment(
            quadrant=QUADRANT_UNKNOWN,
            title=QUADRANT_TITLES[QUADRANT_UNKNOWN],
            emoji=QUADRANT_EMOJI[QUADRANT_UNKNOWN],
            description="Нет актуальных данных ночного HRV или пульса покоя.",
            action_advice="Убедитесь, что часы были на руке во время сна.",
            ascii_matrix=render_ascii_quadrant_matrix(QUADRANT_UNKNOWN),
        )

    # has_missing_data already guarantees all four values below are not None;
    # explicit asserts make that contract visible to type checkers.
    assert latest_hrv is not None
    assert latest_rhr is not None
    assert effective_hrv_base is not None
    assert effective_rhr_base is not None

    # 2. Daily classifications history
    daily_quadrants: list[str] = []
    min_len = min(len(hrv_values), len(rhr_values))
    for i in range(min_len):
        h = hrv_values[i]
        r = rhr_values[i]
        daily_quadrants.append(
            classify_single_day(h, r, effective_hrv_base, effective_rhr_base, hrv_swc, rhr_swc)
        )

    latest_quadrant = daily_quadrants[-1] if daily_quadrants else QUADRANT_UNKNOWN

    # 3. Streak calculation (consecutive days in current quadrant ending at latest)
    streak = 0
    for q in reversed(daily_quadrants):
        if q == latest_quadrant and q != QUADRANT_UNKNOWN:
            streak += 1
        else:
            break
    if streak == 0:
        streak = 1

    # 4. Weekly distribution (last 7 days)
    recent_7 = daily_quadrants[-7:] if len(daily_quadrants) >= 7 else daily_quadrants
    weekly_counts = {
        QUADRANT_Q1: recent_7.count(QUADRANT_Q1),
        QUADRANT_Q2: recent_7.count(QUADRANT_Q2),
        QUADRANT_Q3: recent_7.count(QUADRANT_Q3),
        QUADRANT_Q4: recent_7.count(QUADRANT_Q4),
    }

    # 5. Deltas and Z-scores
    hrv_delta_pct = (
        round((latest_hrv - effective_hrv_base) / effective_hrv_base * 100.0, 1)
        if effective_hrv_base
        else None
    )
    rhr_delta_bpm = round(latest_rhr - effective_rhr_base, 1)

    hrv_z = (
        round((latest_hrv - effective_hrv_base) / hrv_sd, 2)
        if (hrv_sd and hrv_sd > 0.01)
        else (round(hrv_delta_pct / 10.0, 2) if hrv_delta_pct is not None else None)
    )
    rhr_z = (
        round((latest_rhr - effective_rhr_base) / rhr_sd, 2)
        if (rhr_sd and rhr_sd > 0.01)
        else (round(rhr_delta_bpm / 3.0, 2) if rhr_delta_bpm is not None else None)
    )

    # 6. Context flags & descriptions
    flags: list[str] = []
    readiness_mod = "green"

    if has_alcohol_event:
        flags.append("алкоголь накануне")
    if sleep_debt_h >= 1.5:
        flags.append(f"долг сна {sleep_debt_h:.1f} ч")

    if latest_quadrant == QUADRANT_Q1:
        title = QUADRANT_TITLES[QUADRANT_Q1]
        emoji = QUADRANT_EMOJI[QUADRANT_Q1]
        description = (
            f"Высокий вагусный тонус (HRV {latest_hrv:.0f} мс, {hrv_delta_pct:+.0f}%) "
            f"при пульсе покоя ({latest_rhr:.0f} уд/мин, {rhr_delta_bpm:+.0f}). "
            "Организм отлично восстановился и готов к нагрузке."
        )
        action_advice = (
            "Зеленый день: отлично подходит для ключевых развивающих "
            "или интервальных тренировок."
        )
        readiness_mod = "green"

    elif latest_quadrant == QUADRANT_Q2:
        title = QUADRANT_TITLES[QUADRANT_Q2]
        emoji = QUADRANT_EMOJI[QUADRANT_Q2]
        readiness_mod = "amber" if streak <= 2 else "red"

        reasons = []
        if has_alcohol_event:
            reasons.append("алкоголь")
        if sleep_debt_h >= 1.5:
            reasons.append("недосып")
        reason_str = f" Возможные триггеры: {', '.join(reasons)}." if reasons else ""

        description = (
            f"Симпатическое доминирование {streak}-й день подряд "
            f"(HRV {latest_hrv:.0f} мс, {hrv_delta_pct:+.0f}%; "
            f"пульс покоя {latest_rhr:.0f} уд/мин, {rhr_delta_bpm:+.0f}).{reason_str}"
        )
        if streak >= 3:
            flags.append("3+ дня симпатического стресса")
            action_advice = (
                "Устойчивый стресс 3+ дня: необходим разгрузочный день (делид), "
                "легкая растяжка или полный отдых, чтобы не сорвать адаптацию."
            )
        elif streak == 2:
            action_advice = (
                "Стресс 2-й день подряд: снизьте объем и интенсивность на 30–40%, "
                "отдайте предпочтение спокойной Зоне 1-2."
            )
        else:
            action_advice = (
                "Снизьте интенсивность: замените жесткие интервалы на легкую базу или технику."
            )

    elif latest_quadrant == QUADRANT_Q3:
        title = QUADRANT_TITLES[QUADRANT_Q3]
        emoji = QUADRANT_EMOJI[QUADRANT_Q3]
        if acute_load_high:
            flags.append("подозрение на парасимпатическую сатурацию")
            description = (
                f"HRV снижена ({latest_hrv:.0f} мс, {hrv_delta_pct:+.0f}%) при низком пульсе "
                f"({latest_rhr:.0f} уд/мин) на фоне высокого тренировочного объема. "
                "Это признак глубокого утомления (парасимпатическая сатурация)."
            )
            action_advice = "Ограничьте объемы: требуется качественный пассивный отдых и сон."
            readiness_mod = "amber"
        else:
            description = (
                f"HRV ниже нормы ({latest_hrv:.0f} мс) при нормальном/низком пульсе "
                f"({latest_rhr:.0f} уд/мин). Усталость или артефакт единичного замера."
            )
            action_advice = "Тренировка по самочувствию, без форсирования интенсивности."
            readiness_mod = "amber"

    elif latest_quadrant == QUADRANT_Q4:
        title = QUADRANT_TITLES[QUADRANT_Q4]
        emoji = QUADRANT_EMOJI[QUADRANT_Q4]
        reasons_q4 = []
        if skin_temp_high:
            reasons_q4.append("повышена температура кожи")
            flags.append("повышенная температура кожи")
        if respiration_high:
            reasons_q4.append("учащенное дыхание во сне")
            flags.append("учащенное ночное дыхание")

        if skin_temp_high or respiration_high or streak >= 2:
            readiness_mod = "red"
            flags.append("риск продромальной фазы заболевания")
            description = (
                "Смешанная вегетативная картина: пульс покоя повышен "
                f"({latest_rhr:.0f} уд/мин, {rhr_delta_bpm:+.0f}), "
                f"а HRV нестабильна/повышена ({latest_hrv:.0f} мс). "
                + (f"Совпало с маркерами: {', '.join(reasons_q4)}. " if reasons_q4 else "")
                + "Высокий риск начала ОРВИ/воспаления или вегетативного рикошета."
            )
            action_advice = (
                "Не тренируйтесь на высокий HRV при высоком пульсе! "
                "Проверьте самочувствие и температуру тела, отмените интенсивную нагрузку."
            )
        else:
            readiness_mod = "amber"
            description = (
                "Смешанный сигнал: и HRV, и пульс покоя выше нормы "
                f"({latest_hrv:.0f} мс / {latest_rhr:.0f} уд/мин). "
                "Возможен рикошет после нагрузки, нестабильность ритма или ранняя реакция."
            )
            action_advice = (
                "Осторожность: ограничьтесь легкой разминкой или прогулкой, "
                "следите за самочувствием."
            )
    else:
        title = QUADRANT_TITLES[QUADRANT_UNKNOWN]
        emoji = QUADRANT_EMOJI[QUADRANT_UNKNOWN]
        description = "Неопределенный статус."
        action_advice = "Ориентируйтесь на субъективное самочувствие."
        readiness_mod = "green"

    ascii_matrix = render_ascii_quadrant_matrix(latest_quadrant, streak=streak)

    seeds: dict[str, Any] = {
        "code": "autonomic_quadrant",
        "quadrant": latest_quadrant,
        "title": title,
        "streak_days": streak,
        "hrv_latest": latest_hrv,
        "hrv_baseline": effective_hrv_base,
        "hrv_delta_pct": hrv_delta_pct,
        "hrv_z": hrv_z,
        "rhr_latest": latest_rhr,
        "rhr_baseline": effective_rhr_base,
        "rhr_delta_bpm": rhr_delta_bpm,
        "rhr_z": rhr_z,
        "weekly_counts": weekly_counts,
        "flags": flags,
        "readiness_modifier": readiness_mod,
    }

    return QuadrantAssessment(
        quadrant=latest_quadrant,
        title=title,
        emoji=emoji,
        description=description,
        action_advice=action_advice,
        hrv_latest=latest_hrv,
        hrv_baseline=effective_hrv_base,
        hrv_delta_pct=hrv_delta_pct,
        hrv_z_score=hrv_z,
        rhr_latest=latest_rhr,
        rhr_baseline=effective_rhr_base,
        rhr_delta_bpm=rhr_delta_bpm,
        rhr_z_score=rhr_z,
        streak_days=streak,
        weekly_counts=weekly_counts,
        flags=flags,
        readiness_modifier=readiness_mod,
        ascii_matrix=ascii_matrix,
        seeds=seeds,
    )
