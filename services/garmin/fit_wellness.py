"""Decoder for Garmin Connect "Export Wellness Data" daily FIT bundles.

Adapted from ``anup-shesh/garmin-local-mcp`` (MIT License,
Copyright (c) 2026 Anup Shesh).  See ``THIRD_PARTY_NOTICES.md`` for the full
license text.  The adaptation keeps the upstream message layouts and quality
heuristics, but maps the result onto this project's ``garmin_daily`` schema.

Garmin's wellness export keeps several nightly metrics in FIT message types
that the public profile does not name, so ``fitparse`` exposes them as
``unknown_<N>``.  Missing files/messages are normal: they produce ``None``
rather than an exception.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fitparse import FitFile
from fitparse.utils import FitParseError

from .errors import GarminImportError

FIT_EPOCH = dt.datetime(1989, 12, 31)
SLEEP_STAGES = {1: "awake", 2: "light", 3: "deep", 4: "rem"}
HRV_STATUS = {0: "none", 1: "poor", 2: "low", 3: "unbalanced", 4: "balanced"}
SOURCE = "wellness_fit"

RHR_HR_FLOOR_MARGIN_BPM = 10
SPARSE_STAGE_GAP_MIN = 45
_PLAUSIBLE_HR = range(30, 121)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso(ts: dt.datetime) -> str:
    return ts.replace(microsecond=0).isoformat()


def _hrv_ms(values: dict[str, Any], key: str) -> int | None:
    value = values.get(key)
    return round(value / 128) if isinstance(value, (int, float)) else None


def _round(value: Any, digits: int) -> float | None:
    return round(value, digits) if isinstance(value, (int, float)) else None


def decode_bundle(folder: str | Path, *, date_hint: str | None = None) -> dict[str, Any]:
    """Decode every ``*.fit`` file in one daily wellness export folder."""
    folder = Path(folder)

    hr_samples: list[int] = []
    step_max: dict[Any, int] = defaultdict(int)
    dist_max: dict[Any, float] = defaultdict(float)
    stress_vals: list[int] = []
    sleep_starts: list[dt.datetime] = []
    sleep_stops: list[dt.datetime] = []
    stage_records: list[tuple[int, int]] = []
    sleep_scores: Counter[int] = Counter()
    rhr_votes: Counter[int] = Counter()
    hrv_summary: dict[str, Any] | None = None
    skin_raw: dict[str, Any] | None = None
    naps_raw: list[tuple[int, int, int | None]] = []
    tz_offset: dt.timedelta | None = None
    last_seen: dt.datetime | None = None

    for path in sorted(folder.glob("*.fit")):
        try:
            for msg in FitFile(str(path)).get_messages():
                name = msg.name
                if name == "monitoring":
                    values = msg.get_values()
                    hr = values.get("heart_rate")
                    if isinstance(hr, int) and hr > 0:
                        hr_samples.append(hr)
                    activity = values.get("activity_type")
                    steps = values.get("steps")
                    if isinstance(steps, int):
                        step_max[activity] = max(step_max[activity], steps)
                    distance = values.get("distance")
                    if isinstance(distance, (int, float)):
                        dist_max[activity] = max(dist_max[activity], distance)
                    ts = values.get("timestamp")
                    if isinstance(ts, dt.datetime) and (last_seen is None or ts > last_seen):
                        last_seen = ts
                elif name == "stress_level":
                    value = msg.get_values().get("stress_level_value")
                    if isinstance(value, int) and 0 <= value <= 100:
                        stress_vals.append(value)
                elif name == "event":
                    values = msg.get_values()
                    if values.get("event") == 74 and isinstance(
                        values.get("timestamp"), dt.datetime
                    ):
                        target = (
                            sleep_starts if values.get("event_type") == "start" else sleep_stops
                        )
                        target.append(values["timestamp"])
                elif name == "timestamp_correlation" and tz_offset is None:
                    values = msg.get_values()
                    local, utc = values.get("local_timestamp"), values.get("timestamp")
                    if isinstance(local, dt.datetime) and isinstance(utc, dt.datetime):
                        tz_offset = dt.timedelta(
                            minutes=round((local - utc).total_seconds() / 60)
                        )
                elif name == "unknown_275":
                    values = msg.get_values()
                    ts, stage = values.get("unknown_253"), values.get("unknown_0")
                    if isinstance(ts, int) and isinstance(stage, int):
                        stage_records.append((ts, stage))
                elif name == "unknown_281":
                    value = msg.get_values().get("unknown_9")
                    if isinstance(value, int) and value in _PLAUSIBLE_HR:
                        rhr_votes[value] += 1
                elif name == "unknown_370":
                    hrv_summary = {
                        key: value
                        for key, value in msg.get_values().items()
                        if value is not None
                    }
                elif name == "unknown_398":
                    skin_raw = {
                        key: value
                        for key, value in msg.get_values().items()
                        if value is not None
                    }
                elif name == "unknown_412":
                    values = msg.get_values()
                    start, end, offset = (
                        values.get("unknown_0"),
                        values.get("unknown_2"),
                        values.get("unknown_1"),
                    )
                    if isinstance(start, int) and isinstance(end, int) and end > start:
                        naps_raw.append(
                            (start, end, offset if isinstance(offset, int) else None)
                        )
                elif name == "unknown_521":
                    value = msg.get_values().get("unknown_1")
                    if isinstance(value, int) and 0 <= value <= 100:
                        sleep_scores[value] += 1
        except (FitParseError, OSError, ValueError):
            continue

    offset = tz_offset if tz_offset is not None else dt.timedelta(0)

    heart_rate = None
    if hr_samples:
        heart_rate = {
            "min": min(hr_samples),
            "avg": round(sum(hr_samples) / len(hr_samples)),
            "max": max(hr_samples),
            "samples": len(hr_samples),
        }

    stress = None
    if stress_vals:
        stress = {"avg": round(sum(stress_vals) / len(stress_vals)), "max": max(stress_vals)}

    sleep = None
    if sleep_starts and sleep_stops:
        start, end = min(sleep_starts), max(sleep_stops)
        if end > start:
            sleep = {
                "start": _iso(start + offset),
                "end": _iso(end + offset),
                "duration_min": round((end - start).total_seconds() / 60),
            }

    sleep_stages = None
    if len(stage_records) >= 2:
        stage_records.sort()
        durations: dict[str, int] = defaultdict(int)
        max_gap = 0
        for (ts, stage), (next_ts, _) in zip(stage_records, stage_records[1:], strict=False):
            segment = next_ts - ts
            durations[SLEEP_STAGES.get(stage, "other")] += segment
            max_gap = max(max_gap, segment)
        sleep_stages = {
            "deep_min": durations.get("deep", 0) // 60,
            "light_min": durations.get("light", 0) // 60,
            "rem_min": durations.get("rem", 0) // 60,
            "awake_min": durations.get("awake", 0) // 60,
            "max_logging_gap_min": round(max_gap / 60),
        }

    hrv = None
    if hrv_summary:
        raw_status = hrv_summary.get("unknown_6")
        status = HRV_STATUS.get(raw_status, str(raw_status) if raw_status is not None else None)
        hrv = {
            "weekly_avg": _hrv_ms(hrv_summary, "unknown_0"),
            "last_night_avg": _hrv_ms(hrv_summary, "unknown_1"),
            "high_5min": _hrv_ms(hrv_summary, "unknown_2"),
            "baseline_low": _hrv_ms(hrv_summary, "unknown_4"),
            "baseline_high": _hrv_ms(hrv_summary, "unknown_5"),
            "status": status,
        }

    skin_temp = None
    if skin_raw:
        nightly, deviation, deviation_7d = (
            skin_raw.get("unknown_4"),
            skin_raw.get("unknown_1"),
            skin_raw.get("unknown_2"),
        )
        skin_temp = {
            "nightly_c": _round(nightly, 1),
            "deviation_c": _round(deviation, 2),
            "avg_dev_7d": _round(deviation_7d, 3),
        }

    naps = []
    for start_s, end_s, offset_min in sorted(naps_raw):
        nap_offset = dt.timedelta(minutes=offset_min) if offset_min is not None else offset
        naps.append(
            {
                "start": _iso(FIT_EPOCH + dt.timedelta(seconds=start_s) + nap_offset),
                "end": _iso(FIT_EPOCH + dt.timedelta(seconds=end_s) + nap_offset),
                "duration_min": round((end_s - start_s) / 60),
            }
        )

    date = None
    if match := _DATE_RE.search(folder.name):
        date = match.group(0)
    elif date_hint and (match := _DATE_RE.search(date_hint)):
        date = match.group(0)
    elif sleep is not None:
        date = sleep["end"][:10]
    elif last_seen is not None:
        date = (last_seen + offset).date().isoformat()

    total_distance = sum(dist_max.values())
    return {
        "date": date,
        "heart_rate": heart_rate,
        "steps": sum(step_max.values()) if step_max else None,
        "distance_m": round(total_distance, 1) if dist_max else None,
        "stress": stress,
        "sleep": sleep,
        "sleep_stages": sleep_stages,
        "sleep_score": sleep_scores.most_common(1)[0][0] if sleep_scores else None,
        "hrv": hrv,
        "skin_temp": skin_temp,
        "rhr_on_device": rhr_votes.most_common(1)[0][0] if rhr_votes else None,
        "naps": naps,
    }


def quality_flags(decoded: dict[str, Any]) -> list[str]:
    """Return generic data-quality flags for one decoded bundle."""
    flags: list[str] = []
    rhr = decoded.get("rhr_on_device")
    hr_min = (decoded.get("heart_rate") or {}).get("min")
    if rhr is not None and hr_min is not None and rhr > hr_min + RHR_HR_FLOOR_MARGIN_BPM:
        flags.append("rhr_far_above_hr_floor")
    gap = (decoded.get("sleep_stages") or {}).get("max_logging_gap_min")
    if gap is not None and gap >= SPARSE_STAGE_GAP_MIN:
        flags.append("sparse_sleep_stage_logging")
    return flags


def _sleep_midpoint_min(sleep: dict[str, Any]) -> int | None:
    start_raw, end_raw = sleep.get("start"), sleep.get("end")
    if not isinstance(start_raw, str) or not isinstance(end_raw, str):
        return None
    try:
        start = dt.datetime.fromisoformat(start_raw)
        end = dt.datetime.fromisoformat(end_raw)
    except ValueError:
        return None
    if end <= start:
        return None
    midpoint = start + (end - start) / 2
    return (midpoint.hour * 60 + midpoint.minute) % (24 * 60)


def _sleep_efficiency(decoded: dict[str, Any]) -> float | None:
    sleep = decoded.get("sleep") or {}
    stages = decoded.get("sleep_stages") or {}
    duration = sleep.get("duration_min")
    awake = stages.get("awake_min")
    if not isinstance(duration, (int, float)) or duration <= 0:
        return None
    if not isinstance(awake, (int, float)):
        return None
    asleep = max(duration - awake, 0)
    return round(asleep / duration * 100, 1)


def to_daily_row(decoded: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    """Map a decoded bundle to a partial ``garmin_daily`` row."""
    date = decoded.get("date")
    if not date:
        raise GarminImportError("cannot determine date for wellness bundle")

    flags = quality_flags(decoded)
    sleep = decoded.get("sleep") or {}
    stages = decoded.get("sleep_stages") or {}
    hrv = decoded.get("hrv") or {}
    stress = decoded.get("stress") or {}
    skin_temp = decoded.get("skin_temp") or {}
    naps = decoded.get("naps") or []
    duration_min = sleep.get("duration_min")

    resting_hr = decoded.get("rhr_on_device")
    if "rhr_far_above_hr_floor" in flags:
        resting_hr = None

    efficiency = _sleep_efficiency(decoded)
    midpoint = _sleep_midpoint_min(sleep) if sleep else None
    stages_payload = None
    if sleep or stages or naps or skin_temp or hrv:
        stages_json = {
            **stages,
            "start": sleep.get("start"),
            "end": sleep.get("end"),
            "duration_min": duration_min,
            "nap_min": sum(nap["duration_min"] for nap in naps) if naps else None,
            "naps": naps,
            "skin_temp": skin_temp,
            "hrv_weekly_avg": hrv.get("weekly_avg"),
            "hrv_high_5min": hrv.get("high_5min"),
            "hrv_baseline_low": hrv.get("baseline_low"),
            "hrv_baseline_high": hrv.get("baseline_high"),
        }
        stages_payload = json.dumps(stages_json, ensure_ascii=False, sort_keys=True)

    sleep_hours = (
        round(duration_min / 60, 2) if isinstance(duration_min, (int, float)) else None
    )
    values = {
        "sleep_hours": sleep_hours,
        "sleep_score": decoded.get("sleep_score"),
        "sleep_stages_json": stages_payload,
        "sleep_efficiency": efficiency,
        "sleep_midpoint_min": midpoint,
        "hrv": hrv.get("last_night_avg"),
        "hrv_baseline_7d": hrv.get("weekly_avg"),
        "hrv_status": hrv.get("status"),
        "resting_hr": resting_hr,
        "stress_avg": stress.get("avg"),
        "stress_max": stress.get("max"),
        "steps": decoded.get("steps"),
    }
    row: dict[str, Any] = {
        "user_id": int(user_id),
        "date": date,
        **values,
        "data_sources_json": json.dumps(
            {key: SOURCE for key, value in values.items() if value is not None},
            ensure_ascii=False,
            sort_keys=True,
        ),
        "quality_flags_json": json.dumps(flags, ensure_ascii=False),
    }
    return row


def to_extra_metrics(decoded: dict[str, Any], *, user_id: int) -> list[dict[str, Any]]:
    """Return optional metrics that do not fit first-class daily columns."""
    date = decoded.get("date")
    if not date:
        raise GarminImportError("cannot determine date for wellness bundle")
    heart_rate = decoded.get("heart_rate") or {}
    skin_temp = decoded.get("skin_temp") or {}
    hrv = decoded.get("hrv") or {}
    stages = decoded.get("sleep_stages") or {}
    naps = decoded.get("naps") or []
    values = {
        "distance_m": (decoded.get("distance_m"), "m"),
        "min_hr": (heart_rate.get("min"), "bpm"),
        "max_hr": (heart_rate.get("max"), "bpm"),
        "skin_temp_nightly_c": (skin_temp.get("nightly_c"), "C"),
        "skin_temp_dev_c": (skin_temp.get("deviation_c"), "C"),
        "skin_temp_avg_dev_7d": (skin_temp.get("avg_dev_7d"), "C"),
        "hrv_weekly_avg": (hrv.get("weekly_avg"), "ms"),
        "hrv_high_5min": (hrv.get("high_5min"), "ms"),
        "hrv_baseline_low": (hrv.get("baseline_low"), "ms"),
        "hrv_baseline_high": (hrv.get("baseline_high"), "ms"),
        "nap_min": (sum(n["duration_min"] for n in naps) if naps else None, "min"),
        "sleep_deep_min": (stages.get("deep_min"), "min"),
        "sleep_light_min": (stages.get("light_min"), "min"),
        "sleep_rem_min": (stages.get("rem_min"), "min"),
        "sleep_awake_min": (stages.get("awake_min"), "min"),
        "sleep_max_logging_gap_min": (stages.get("max_logging_gap_min"), "min"),
    }
    return [
        {
            "user_id": int(user_id),
            "date": date,
            "metric": metric,
            "value": value,
            "unit": unit,
            "source": SOURCE,
        }
        for metric, (value, unit) in values.items()
        if value is not None
    ]
