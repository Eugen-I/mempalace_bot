"""Normalizer for Garmin Connect online API responses.

Maps JSON payloads returned by ``garminconnect.Garmin`` endpoints into the
canonical ``garmin_daily`` and ``garmin_activities`` contracts used by
``repository.upsert_daily`` and ``repository.upsert_activity`` with
``source="online"``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .importers.activities_csv import normalize_activity_type


def _num(val: Any) -> float | None:
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.strip())
        except ValueError:
            return None
    return None


def _int_opt(val: Any) -> int | None:
    fval = _num(val)
    return int(round(fval)) if fval is not None else None


def _midpoint_from_timestamps(start_val: Any, end_val: Any) -> int | None:
    """Compute sleep midpoint in minutes from midnight (0..1439)."""
    s_num = _num(start_val)
    e_num = _num(end_val)
    if s_num is not None and e_num is not None and e_num > s_num:
        if s_num > 1e11:
            s_num /= 1000.0
        if e_num > 1e11:
            e_num /= 1000.0
        try:
            mid_ts = (s_num + e_num) / 2.0
            mid_dt = datetime.fromtimestamp(mid_ts, tz=timezone.utc)
            return (mid_dt.hour * 60 + mid_dt.minute) % 1440
        except (ValueError, OSError, OverflowError):
            return None
    return None


def normalize_daily_bundle(
    *,
    user_id: int,
    day: str,
    summary: dict[str, Any] | None = None,
    sleep: dict[str, Any] | None = None,
    hrv: dict[str, Any] | None = None,
    readiness: dict[str, Any] | list[Any] | None = None,
    body_composition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge online endpoint payloads for a single date into a ``garmin_daily`` row."""
    row: dict[str, Any] = {
        "user_id": int(user_id),
        "date": str(day)[:10],
    }

    if isinstance(summary, dict):
        steps = _int_opt(summary.get("totalSteps"))
        if steps is not None:
            row["steps"] = steps
        rhr = _int_opt(
            summary.get("restingHeartRate")
            or summary.get("currentDayRestingHeartRate")
        )
        if rhr is not None and rhr > 0:
            row["resting_hr"] = rhr
        rhr_base = _int_opt(summary.get("lastSevenDaysAvgRestingHeartRate"))
        if rhr_base is not None and rhr_base > 0:
            row["resting_hr_baseline"] = rhr_base

        stress_avg = _int_opt(summary.get("averageStressLevel"))
        if stress_avg is not None and stress_avg >= 0:
            row["stress_avg"] = stress_avg
        stress_max = _int_opt(summary.get("maxStressLevel"))
        if stress_max is not None and stress_max >= 0:
            row["stress_max"] = stress_max
        high_stress_sec = _num(summary.get("highStressDuration"))
        if high_stress_sec is not None and high_stress_sec >= 0:
            row["stress_high_min"] = int(round(high_stress_sec / 60.0))

        bb_charged = _int_opt(summary.get("bodyBatteryChargedValue"))
        if bb_charged is not None:
            row["body_battery_charged"] = bb_charged
        bb_spent = _int_opt(summary.get("bodyBatteryDrainedValue"))
        if bb_spent is not None:
            row["body_battery_spent"] = bb_spent
        bb_high = _int_opt(
            summary.get("bodyBatteryHighestValue")
            or summary.get("bodyBatteryWakeTimeValue")
        )
        if bb_high is not None:
            row["body_battery_morning"] = bb_high
        bb_low = _int_opt(
            summary.get("bodyBatteryLowestValue")
            or summary.get("bodyBatteryMostRecentValue")
        )
        if bb_low is not None:
            row["body_battery_evening"] = bb_low

        spo2 = _num(summary.get("averageSpo2"))
        if spo2 is not None and spo2 > 0:
            row["spo2_avg"] = round(spo2, 1)
        spo2_min = _num(summary.get("lowestSpo2"))
        if spo2_min is not None and spo2_min > 0:
            row["spo2_min"] = round(spo2_min, 1)

        resp = _num(summary.get("avgWakingRespirationValue"))
        if resp is not None and resp > 0:
            row["respiration_avg"] = round(resp, 1)
        resp_min = _num(summary.get("lowestRespirationValue"))
        if resp_min is not None and resp_min > 0:
            row["respiration_min"] = round(resp_min, 1)
        resp_max = _num(summary.get("highestRespirationValue"))
        if resp_max is not None and resp_max > 0:
            row["respiration_max"] = round(resp_max, 1)

        act_cal = _int_opt(summary.get("activeKilocalories"))
        if act_cal is not None:
            row["active_calories"] = act_cal
        tot_cal = _int_opt(summary.get("totalKilocalories"))
        if tot_cal is not None:
            row["total_calories"] = tot_cal

    if isinstance(sleep, dict):
        dto = sleep.get("dailySleepDTO") if isinstance(sleep.get("dailySleepDTO"), dict) else sleep
        if isinstance(dto, dict):
            deep_s = _num(dto.get("deepSleepSeconds")) or 0.0
            light_s = _num(dto.get("lightSleepSeconds")) or 0.0
            rem_s = _num(dto.get("remSleepSeconds")) or 0.0
            awake_s = _num(dto.get("awakeSleepSeconds")) or 0.0
            sleep_s = _num(dto.get("sleepTimeSeconds")) or (deep_s + light_s + rem_s)
            if sleep_s > 0:
                row["sleep_hours"] = round(sleep_s / 3600.0, 2)
                total_bed = sleep_s + max(awake_s, 0.0)
                if total_bed > 0:
                    row["sleep_efficiency"] = round(sleep_s / total_bed * 100.0, 1)
            if deep_s + light_s + rem_s > 0 or awake_s > 0:
                row["sleep_stages_json"] = json.dumps(
                    {
                        "deep": round(deep_s / 60.0, 1),
                        "light": round(light_s / 60.0, 1),
                        "rem": round(rem_s / 60.0, 1),
                        "awake": round(awake_s / 60.0, 1),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            scores = dto.get("sleepScores")
            if isinstance(scores, dict):
                overall = scores.get("overall")
                if isinstance(overall, dict):
                    score_val = _int_opt(overall.get("value"))
                else:
                    score_val = _int_opt(scores.get("overallScore") or overall)
                if score_val is not None:
                    row["sleep_score"] = score_val

            midpoint = _midpoint_from_timestamps(
                dto.get("sleepStartTimestampLocal") or dto.get("sleepStartTimestampGMT"),
                dto.get("sleepEndTimestampLocal") or dto.get("sleepEndTimestampGMT"),
            )
            if midpoint is not None:
                row["sleep_midpoint_min"] = midpoint

    if isinstance(hrv, dict):
        hrv_sum = hrv.get("hrvSummary") if isinstance(hrv.get("hrvSummary"), dict) else hrv
        if isinstance(hrv_sum, dict):
            last_night = _int_opt(
                hrv_sum.get("lastNightAvg") or hrv_sum.get("weeklyAvg")
            )
            if last_night is not None and last_night > 0:
                row["hrv"] = last_night
            weekly_avg = _int_opt(hrv_sum.get("weeklyAvg"))
            if weekly_avg is not None and weekly_avg > 0:
                row["hrv_baseline_7d"] = weekly_avg
            status = hrv_sum.get("status")
            if isinstance(status, str) and status.strip():
                row["hrv_status"] = status.strip()
            baseline = hrv_sum.get("baseline")
            if isinstance(baseline, dict):
                low = _num(baseline.get("balancedLow"))
                high = _num(baseline.get("balancedUpper"))
                if low is not None and high is not None:
                    row["hrv_baseline_28d"] = int(round((low + high) / 2.0))

    readiness_item: dict[str, Any] | None = None
    if isinstance(readiness, list) and readiness:
        first_r = readiness[0]
        if isinstance(first_r, dict):
            readiness_item = first_r
    elif isinstance(readiness, dict):
        readiness_item = readiness

    if isinstance(readiness_item, dict):
        r_score = _int_opt(readiness_item.get("score"))
        if r_score is not None:
            row["readiness_score"] = r_score
        r_level = readiness_item.get("level")
        if isinstance(r_level, str) and r_level.strip():
            row["readiness_level"] = r_level.strip()
        rec_time = _num(readiness_item.get("recoveryTime"))
        if rec_time is not None and rec_time >= 0:
            # Garmin reports recoveryTime in minutes in Training Readiness DTO
            row["recovery_time_h"] = (
                round(rec_time / 60.0, 1) if rec_time > 72 else round(rec_time, 1)
            )

    if isinstance(body_composition, dict):
        total_avg = (
            body_composition.get("totalAverage")
            if isinstance(body_composition.get("totalAverage"), dict)
            else body_composition
        )
        if isinstance(total_avg, dict):
            w_raw = _num(total_avg.get("weight"))
            if w_raw is not None and w_raw > 0:
                row["weight_kg"] = round(
                    w_raw / 1000.0 if w_raw > 500 else w_raw, 2
                )
            fat = _num(total_avg.get("bodyFat"))
            if fat is not None and 0 < fat < 80:
                row["body_fat_pct"] = round(fat, 1)
            muscle_raw = _num(total_avg.get("muscleMass"))
            if muscle_raw is not None and muscle_raw > 0:
                row["muscle_mass_kg"] = round(
                    muscle_raw / 1000.0 if muscle_raw > 500 else muscle_raw, 2
                )
            water = _num(total_avg.get("bodyWater"))
            if water is not None and 0 < water < 90:
                row["body_water_pct"] = round(water, 1)
            bmi = _num(total_avg.get("bmi"))
            if bmi is not None and 10 <= bmi <= 70:
                row["bmi"] = round(bmi, 1)

    return row


def normalize_activity_item(
    item: dict[str, Any],
    *,
    user_id: int,
) -> dict[str, Any] | None:
    """Normalize a single activity dict from ``get_activities_by_date``."""
    if not isinstance(item, dict):
        return None
    raw_id = item.get("activityId") or item.get("id")
    if raw_id is None:
        return None
    start_raw = str(
        item.get("startTimeLocal")
        or item.get("startTimeGMT")
        or item.get("startTime")
        or ""
    ).strip()
    if len(start_raw) < 10:
        return None
    start_iso = start_raw.replace(" ", "T")[:19]

    act_type_obj = item.get("activityType")
    if isinstance(act_type_obj, dict):
        raw_type = act_type_obj.get("typeKey") or "other"
    else:
        raw_type = act_type_obj or "other"
    activity_type = normalize_activity_type(str(raw_type))

    dur_sec = _num(item.get("duration") or item.get("movingDuration"))
    duration_min = round(dur_sec / 60.0, 2) if dur_sec is not None else None
    dist_m = _num(item.get("distance"))
    distance_m = round(dist_m, 1) if dist_m is not None else None

    avg_pace = (
        round((duration_min * 60.0) / (distance_m / 1000.0), 1)
        if duration_min and distance_m and distance_m > 0
        else None
    )

    return {
        "user_id": int(user_id),
        "activity_id": str(raw_id),
        "start_time": start_iso,
        "activity_type": activity_type,
        "name": str(item.get("activityName") or activity_type),
        "duration_min": duration_min,
        "distance_m": distance_m,
        "calories": _int_opt(item.get("calories")),
        "avg_hr": _int_opt(item.get("averageHR")),
        "max_hr": _int_opt(item.get("maxHR")),
        "training_load": _num(item.get("activityTrainingLoad")),
        "aerobic_te": _num(item.get("aerobicTrainingEffect")),
        "anaerobic_te": _num(item.get("anaerobicTrainingEffect")),
        "avg_pace_s_per_km": avg_pace,
        "elevation_gain_m": _num(item.get("elevationGain")),
        "raw_json": json.dumps(item, ensure_ascii=False, sort_keys=True),
    }
