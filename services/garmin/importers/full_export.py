"""Import activities from Garmin's full "Export Your Data" archive.

A full export is a large tree with many unrelated files.  This importer only
looks for activity representations and ignores everything else, so unknown
files cannot break the run.  Supported activity sources:

* ``Activities*.csv`` (Garmin Connect CSV export)
* ``*summarizedActivities*.json``
* activity FIT files with a ``session`` message
* TCX activity files
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET  # nosec B405

from fitparse import FitFile
from fitparse.utils import FitParseError

from ..errors import GarminImportError
from ..raw_store import RawStore
from ..repository import (
    finish_run,
    record_raw_file,
    start_run,
    upsert_activity,
    upsert_daily,
)
from ..zip_safety import ZipLimits, extract
from .activities_csv import (
    import_csv_into,
    normalize_activity_type,
    parse_activity_datetime,
)
from .wellness_fit import ImportIssue, ImportResult

SOURCE = "full_export"

_JSON_LIST_KEYS = (
    "summarizedActivitiesExport",
    "activities",
    "activityList",
    "activityListExport",
)


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _float(value)
    return round(number) if number is not None else None


def _clean_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _synthetic_id(
    prefix: str,
    start_time: str,
    activity_type: str,
    duration_min: float | None,
    distance_m: float | None,
) -> str:
    seed = "|".join(
        [
            start_time,
            activity_type,
            f"{duration_min or 0:.3f}",
            f"{distance_m or 0:.1f}",
        ]
    )
    return prefix + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e11:
            ts /= 1000.0
        if 1e8 < ts < 2.5e10:
            try:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                return dt.replace(tzinfo=None, microsecond=0).isoformat()
            except (ValueError, OverflowError, OSError):
                return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return value.replace(microsecond=0).isoformat()
    return parse_activity_datetime(value)


def _type_value(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("typeKey") or value.get("typeId") or "other"
    return normalize_activity_type(value)


def _json_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        first = data[0]
        if any(key in first for key in _JSON_LIST_KEYS):
            data = first
    if isinstance(data, dict):
        for key in _JSON_LIST_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                data = value
                break
        else:
            values = [value for value in data.values() if isinstance(value, dict)]
            if values and any(
                "startTimeLocal" in value or "startTimeGmt" in value
                for value in values
            ):
                data = values
            else:
                return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _from_json_item(item: dict[str, Any], user_id: int) -> dict[str, Any] | None:
    start_val = (
        item.get("startTimeLocal")
        or item.get("startTimeGmt")
        or item.get("startTime")
        or item.get("beginTimestamp")
    )
    start_time = _iso(start_val)
    if start_time is None:
        return None
    activity_type = _type_value(item.get("activityType") or item.get("sport"))

    is_garmin_json_units = isinstance(start_val, (int, float)) or (
        isinstance(item.get("beginTimestamp"), (int, float))
    )

    duration_raw = _float(item.get("duration") or item.get("elapsedDuration"))
    if duration_raw is not None:
        if is_garmin_json_units or duration_raw > 100000:
            duration_min = duration_raw / 60000.0
        else:
            duration_min = duration_raw / 60.0
    else:
        duration_min = None

    distance_raw = _float(item.get("distance"))
    if distance_raw is not None:
        if is_garmin_json_units:
            distance_m = distance_raw / 100.0
        else:
            distance_m = distance_raw
    else:
        distance_m = None

    elev_raw = _float(item.get("elevationGain") or item.get("totalAscent"))
    if elev_raw is not None:
        if is_garmin_json_units:
            elevation_gain_m = elev_raw / 100.0
        else:
            elevation_gain_m = elev_raw
    else:
        elevation_gain_m = None

    activity_id = _clean_id(
        item.get("activityId")
        or item.get("activityIdStr")
        or item.get("id")
    )
    if not activity_id:
        activity_id = _synthetic_id(
            "full_", start_time, activity_type, duration_min, distance_m
        )
    training_load = _float(
        item.get("activityTrainingLoad")
        or item.get("trainingStressScore")
        or item.get("trainingLoad")
    )
    return {
        "user_id": int(user_id),
        "activity_id": activity_id,
        "start_time": start_time,
        "activity_type": activity_type,
        "name": item.get("activityName") or item.get("name"),
        "duration_min": round(duration_min, 2) if duration_min is not None else None,
        "distance_m": round(distance_m, 1) if distance_m is not None else None,
        "calories": _int(item.get("calories")),
        "avg_hr": _int(item.get("averageHR") or item.get("avgHR")),
        "max_hr": _int(item.get("maxHR")),
        "training_load": training_load,
        "aerobic_te": _float(item.get("aerobicTrainingEffect")),
        "anaerobic_te": _float(item.get("anaerobicTrainingEffect")),
        "avg_pace_s_per_km": None,
        "elevation_gain_m": round(elevation_gain_m, 1) if elevation_gain_m is not None else None,
        "raw_json": json.dumps(item, ensure_ascii=False, sort_keys=True),
    }


def _from_fit_session(
    values: dict[str, Any], *, path: Path, user_id: int
) -> dict[str, Any] | None:
    start_time = _iso(values.get("start_time"))
    if start_time is None:
        return None
    sport = str(values.get("sport") or "").strip()
    sub_sport = str(values.get("sub_sport") or "").strip()
    # Garmin uses sport="training" for gym work and puts the real type into
    # sub_sport ("strength_training").  Prefer the specific value when present.
    if sub_sport.lower() not in {"", "generic", "other"}:
        raw_type = sub_sport
    else:
        raw_type = sport or sub_sport or "other"
    activity_type = normalize_activity_type(raw_type)
    duration_s = _float(values.get("total_timer_time"))
    if duration_s is None:
        duration_s = _float(values.get("total_elapsed_time"))
    duration_min = duration_s / 60.0 if duration_s is not None else None
    distance_m = _float(values.get("total_distance"))
    activity_id = _synthetic_id(
        "fit_", start_time, activity_type, duration_min, distance_m
    )
    return {
        "user_id": int(user_id),
        "activity_id": activity_id,
        "start_time": start_time,
        "activity_type": activity_type,
        "name": path.stem,
        "duration_min": round(duration_min, 2) if duration_min is not None else None,
        "distance_m": round(distance_m, 1) if distance_m is not None else None,
        "calories": _int(values.get("total_calories")),
        "avg_hr": _int(values.get("avg_heart_rate")),
        "max_hr": _int(values.get("max_heart_rate")),
        "training_load": _float(values.get("training_stress_score")),
        "aerobic_te": _float(values.get("total_training_effect")),
        "anaerobic_te": _float(values.get("total_anaerobic_training_effect")),
        "avg_pace_s_per_km": None,
        "elevation_gain_m": _float(values.get("total_ascent")),
        "raw_json": json.dumps(
            {key: str(value) for key, value in values.items()},
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def _activity_from_fit(path: Path, user_id: int) -> dict[str, Any] | None:
    try:
        for message in FitFile(str(path)).get_messages("session"):
            activity = _from_fit_session(
                message.get_values(), path=path, user_id=user_id
            )
            if activity is not None:
                return activity
    except FitParseError as exc:
        raise GarminImportError(f"cannot parse FIT activity: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - fitparse may raise other errors
        raise GarminImportError(f"cannot read FIT activity: {exc}") from exc
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _tcx_value(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if _local(child.tag) != name:
            continue
        if child.text and child.text.strip():
            return child.text.strip()
        for nested in child.iter():
            if _local(nested.tag) == "Value" and nested.text:
                return nested.text.strip()
    return None


def _activities_from_tcx(path: Path, user_id: int) -> list[dict[str, Any]]:
    try:
        root = ET.parse(path).getroot()  # nosec B314
    except (ET.ParseError, OSError) as exc:
        raise GarminImportError(f"cannot parse TCX: {exc}") from exc

    activities = []
    for element in root.iter():
        if _local(element.tag) != "Activity":
            continue
        start_time = _iso(_tcx_value(element, "Id"))
        if start_time is None:
            continue
        activity_type = normalize_activity_type(element.attrib.get("Sport", "other"))
        laps = [lap for lap in element.iter() if _local(lap.tag) == "Lap"]
        duration_s = sum(
            _float(_tcx_value(lap, "TotalTimeSeconds")) or 0.0 for lap in laps
        )
        distance_m = sum(
            _float(_tcx_value(lap, "DistanceMeters")) or 0.0 for lap in laps
        )
        calories = sum(_int(_tcx_value(lap, "Calories")) or 0 for lap in laps)
        avg_hr_values: list[int] = [
            value
            for value in (
                _int(_tcx_value(lap, "AverageHeartRateBpm")) for lap in laps
            )
            if value is not None
        ]
        max_hr_values: list[int] = [
            value
            for value in (
                _int(_tcx_value(lap, "MaximumHeartRateBpm")) for lap in laps
            )
            if value is not None
        ]
        duration_min = duration_s / 60.0 if duration_s else None
        distance = distance_m or None
        activities.append(
            {
                "user_id": int(user_id),
                "activity_id": _synthetic_id(
                    "tcx_", start_time, activity_type, duration_min, distance
                ),
                "start_time": start_time,
                "activity_type": activity_type,
                "name": _tcx_value(element, "Notes") or path.stem,
                "duration_min": (
                    round(duration_min, 2) if duration_min is not None else None
                ),
                "distance_m": round(distance, 1) if distance is not None else None,
                "calories": calories or None,
                "avg_hr": (
                    round(sum(avg_hr_values) / len(avg_hr_values))
                    if avg_hr_values
                    else None
                ),
                "max_hr": max(max_hr_values) if max_hr_values else None,
                "training_load": None,
                "aerobic_te": None,
                "anaerobic_te": None,
                "avg_pace_s_per_km": (
                    round(duration_min * 60.0 / (distance / 1000.0), 1)
                    if duration_min and distance
                    else None
                ),
                "elevation_gain_m": None,
                "raw_json": json.dumps(
                    {
                        "sport": element.attrib.get("Sport"),
                        "start": start_time,
                    },
                    ensure_ascii=False,
                ),
            }
        )
    return activities


def _save_raw(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
) -> None:
    info = raw_store.save_file(user_id, path, source=SOURCE, filename=path.name)
    record_raw_file(
        conn,
        user_id=user_id,
        sha256=info.sha256,
        source=SOURCE,
        filename=info.filename,
        size_bytes=info.size_bytes,
    )
    result.raw_sha256.append(info.sha256)


def _store_activity(
    conn,
    activity: dict[str, Any],
    result: ImportResult,
    *,
    file: str,
) -> None:
    result.rows_total += 1
    try:
        status = upsert_activity(conn, activity, source=SOURCE)
    except Exception as exc:  # noqa: BLE001 - one row must not stop the file
        result.rows_failed += 1
        result.issues.append(ImportIssue(file=file, error=str(exc)))
        return
    if status == "skipped":
        result.rows_skipped += 1
    else:
        result.rows_ok += 1
        result.days.append(str(activity["start_time"])[:10])


def _store_daily(
    conn,
    row: dict[str, Any],
    result: ImportResult,
    *,
    file: str,
) -> None:
    result.rows_total += 1
    try:
        status = upsert_daily(conn, row, source=SOURCE)
    except Exception as exc:  # noqa: BLE001 - one row must not stop the file
        result.rows_failed += 1
        result.issues.append(ImportIssue(file=file, error=str(exc)))
        return
    if status == "skipped":
        result.rows_skipped += 1
    else:
        result.rows_ok += 1
        result.days.append(str(row["date"])[:10])


def _to_list_of_dicts(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for val in data.values():
            if isinstance(val, list):
                items = [item for item in val if isinstance(item, dict)]
                if items:
                    return items
    return []


def _import_uds_file(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    record_raw: bool,
) -> None:
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(conn, raw_store, user_id=user_id, path=path, result=result)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items = _to_list_of_dicts(data)
        if not items:
            raise GarminImportError("no UDS records in JSON")
        for item in items:
            date_str = str(item.get("calendarDate") or "")[:10]
            if not date_str or len(date_str) < 10:
                continue
            row: dict[str, Any] = {
                "user_id": user_id,
                "date": date_str,
                "steps": _int(item.get("totalSteps")),
                "resting_hr": _float(item.get("restingHeartRate")),
                "active_calories": _float(item.get("activeKilocalories")),
                "total_calories": _float(item.get("totalKilocalories")),
                "spo2_avg": _float(item.get("averageSpo2Value")),
                "spo2_min": _float(item.get("lowestSpo2Value")),
            }
            stress_agg = (item.get("allDayStress") or {}).get("aggregatorList") or []
            total_stress = next(
                (a for a in stress_agg if a.get("type") == "TOTAL"), None
            )
            if total_stress:
                row["stress_avg"] = _float(total_stress.get("averageStressLevel"))
                row["stress_max"] = _float(total_stress.get("maxStressLevel"))
                high_dur = _float(total_stress.get("highDuration"))
                if high_dur is not None:
                    row["stress_high_min"] = round(high_dur / 60.0, 1)

            bb = item.get("bodyBattery") or {}
            row["body_battery_charged"] = _int(bb.get("chargedValue"))
            row["body_battery_spent"] = _int(bb.get("drainedValue"))
            for stat in bb.get("bodyBatteryStatList") or []:
                st_type = stat.get("bodyBatteryStatType")
                if st_type == "STARTOFDAY":
                    row["body_battery_morning"] = _int(stat.get("statsValue"))
                elif st_type == "ENDOFDAY":
                    row["body_battery_evening"] = _int(stat.get("statsValue"))

            resp = item.get("respiration") or {}
            row["respiration_avg"] = _float(resp.get("avgWakingRespirationValue"))
            row["respiration_min"] = _float(resp.get("lowestRespirationValue"))
            row["respiration_max"] = _float(resp.get("highestRespirationValue"))

            _store_daily(conn, row, result, file=path.name)
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def _import_sleep_file(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    record_raw: bool,
) -> None:
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(conn, raw_store, user_id=user_id, path=path, result=result)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items = _to_list_of_dicts(data)
        if not items:
            raise GarminImportError("no sleep records in JSON")
        for item in items:
            date_str = str(item.get("calendarDate") or "")[:10]
            if not date_str or len(date_str) < 10:
                ts = _iso(
                    item.get("sleepStartTimestampGMT")
                    or item.get("sleepEndTimestampGMT")
                )
                if ts:
                    date_str = ts[:10]
                else:
                    continue
            deep = _float(item.get("deepSleepSeconds")) or 0.0
            light = _float(item.get("lightSleepSeconds")) or 0.0
            rem = _float(item.get("remSleepSeconds")) or 0.0
            awake = _float(item.get("awakeSleepSeconds")) or 0.0
            total_s = deep + light + rem
            scores = item.get("sleepScores") or {}
            overall_score = _int(scores.get("overallScore"))
            if total_s <= 0 and overall_score is None:
                continue

            row: dict[str, Any] = {
                "user_id": user_id,
                "date": date_str,
            }
            if total_s > 0:
                row["sleep_hours"] = round(total_s / 3600.0, 2)
                row["sleep_stages_json"] = json.dumps(
                    {
                        "deep": round(deep / 60.0, 1),
                        "light": round(light / 60.0, 1),
                        "rem": round(rem / 60.0, 1),
                        "awake": round(awake / 60.0, 1),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            if overall_score is not None:
                row["sleep_score"] = overall_score

            _store_daily(conn, row, result, file=path.name)
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def _import_health_status_file(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    record_raw: bool,
) -> None:
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(conn, raw_store, user_id=user_id, path=path, result=result)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items = _to_list_of_dicts(data)
        if not items:
            raise GarminImportError("no health status records in JSON")
        for item in items:
            date_str = str(item.get("calendarDate") or "")[:10]
            if not date_str or len(date_str) < 10:
                continue
            row: dict[str, Any] = {
                "user_id": user_id,
                "date": date_str,
            }
            for m in item.get("metrics") or []:
                m_type = m.get("type")
                val = _float(m.get("value"))
                if m_type == "HRV" and val is not None:
                    row["hrv"] = round(val, 1)
                    if m.get("status"):
                        row["hrv_status"] = str(m["status"])
                    upper = _float(m.get("baselineUpperLimit"))
                    lower = _float(m.get("baselineLowerLimit"))
                    if upper is not None and lower is not None:
                        row["hrv_baseline_7d"] = round((upper + lower) / 2.0, 1)
                elif m_type == "HR" and val is not None:
                    row["resting_hr"] = round(val, 1)
                elif m_type == "SPO2" and val is not None:
                    row["spo2_avg"] = round(val, 1)
                elif m_type == "RESPIRATION" and val is not None:
                    row["respiration_avg"] = round(val, 1)

            if len(row) > 2:
                _store_daily(conn, row, result, file=path.name)
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def _import_training_readiness_file(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    record_raw: bool,
) -> None:
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(conn, raw_store, user_id=user_id, path=path, result=result)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items = _to_list_of_dicts(data)
        if not items:
            raise GarminImportError("no training readiness records in JSON")
        for item in items:
            date_str = str(item.get("calendarDate") or "")[:10]
            if not date_str or len(date_str) < 10:
                continue
            row: dict[str, Any] = {
                "user_id": user_id,
                "date": date_str,
            }
            if item.get("score") is not None:
                row["readiness_score"] = _int(item["score"])
            if item.get("level"):
                row["readiness_level"] = str(item["level"])
            recovery = _float(item.get("recoveryTime"))
            if recovery is not None:
                row["recovery_time_h"] = round(recovery, 1)
            hrv_avg = _float(item.get("hrvWeeklyAverage"))
            if hrv_avg is not None:
                row["hrv_baseline_28d"] = round(hrv_avg, 1)

            if len(row) > 2:
                _store_daily(conn, row, result, file=path.name)
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def _import_biometrics_file(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    record_raw: bool,
) -> None:
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(conn, raw_store, user_id=user_id, path=path, result=result)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items = _to_list_of_dicts(data)
        if not items:
            raise GarminImportError("no biometrics records in JSON")
        for item in items:
            meta = item.get("metaData") or {}
            dt_str = str(meta.get("calendarDate") or "")
            if not dt_str or len(dt_str) < 10:
                continue
            date_str = dt_str[:10]
            w_raw = _float((item.get("weight") or {}).get("weight"))
            if w_raw is not None:
                weight_kg = round(w_raw / 1000.0 if w_raw > 1000 else w_raw, 2)
                row = {
                    "user_id": user_id,
                    "date": date_str,
                    "weight_kg": weight_kg,
                }
                _store_daily(conn, row, result, file=path.name)
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def _import_fitness_age_file(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    record_raw: bool,
) -> None:
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(conn, raw_store, user_id=user_id, path=path, result=result)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items = _to_list_of_dicts(data)
        if not items:
            raise GarminImportError("no fitness age records in JSON")
        for item in items:
            date_str = str(item.get("calendarDate") or "")[:10]
            if not date_str or len(date_str) < 10:
                continue
            row: dict[str, Any] = {
                "user_id": user_id,
                "date": date_str,
            }
            if item.get("fitnessAge") is not None:
                row["fitness_age"] = _float(item["fitnessAge"])
            if item.get("vo2Max") is not None:
                row["vo2max"] = _float(item["vo2Max"])
            if len(row) > 2:
                _store_daily(conn, row, result, file=path.name)
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def _import_json_file(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    record_raw: bool,
) -> None:
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(conn, raw_store, user_id=user_id, path=path, result=result)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items = _json_items(data)
        if not items:
            raise GarminImportError("no activities in JSON")
        for item in items:
            activity = _from_json_item(item, user_id)
            if activity is None:
                result.rows_total += 1
                result.rows_failed += 1
                result.issues.append(
                    ImportIssue(file=path.name, error="activity without start time")
                )
                continue
            _store_activity(conn, activity, result, file=path.name)
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def _import_fit_file(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    record_raw: bool,
    strict: bool,
) -> None:
    try:
        activity = _activity_from_fit(path, user_id)
    except GarminImportError as exc:
        result.files_total += 1
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))
        return
    if activity is None:
        if strict:
            result.files_total += 1
            result.files_failed += 1
            result.issues.append(
                ImportIssue(file=path.name, error="no activity session in FIT")
            )
        return
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(conn, raw_store, user_id=user_id, path=path, result=result)
        _store_activity(conn, activity, result, file=path.name)
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def _import_tcx_file(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    record_raw: bool,
) -> None:
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(conn, raw_store, user_id=user_id, path=path, result=result)
        activities = _activities_from_tcx(path, user_id)
        if not activities:
            raise GarminImportError("no activities in TCX")
        for activity in activities:
            _store_activity(conn, activity, result, file=path.name)
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def _collect(root: Path) -> dict[str, list[Path]]:
    files_by_type: dict[str, list[Path]] = {
        "activities_csv": [],
        "activities_json": [],
        "fit": [],
        "tcx": [],
        "uds": [],
        "sleep": [],
        "health": [],
        "readiness": [],
        "biometrics": [],
        "fitness_age": [],
    }
    for current, _dirs, files in os.walk(root):
        for name in files:
            path = Path(current) / name
            lower = name.lower()
            suffix = path.suffix.lower()
            if suffix == ".csv" and lower.startswith("activities"):
                files_by_type["activities_csv"].append(path)
            elif suffix == ".json":
                if "summarizedactivities" in lower:
                    files_by_type["activities_json"].append(path)
                elif "udsfile" in lower:
                    files_by_type["uds"].append(path)
                elif "sleepdata" in lower:
                    files_by_type["sleep"].append(path)
                elif "healthstatusdata" in lower:
                    files_by_type["health"].append(path)
                elif "trainingreadiness" in lower:
                    files_by_type["readiness"].append(path)
                elif "userbiometrics" in lower:
                    files_by_type["biometrics"].append(path)
                elif "fitnessagedata" in lower:
                    files_by_type["fitness_age"].append(path)
            elif suffix == ".fit":
                files_by_type["fit"].append(path)
            elif suffix == ".tcx":
                files_by_type["tcx"].append(path)
    return {k: sorted(v) for k, v in files_by_type.items()}


def _import_tree(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    root: Path,
    result: ImportResult,
    record_raw: bool,
) -> None:
    collected = _collect(root)
    if not any(collected.values()):
        result.issues.append(
            ImportIssue(file=str(root), error="no activity files found")
        )
        return
    for path in collected["activities_csv"]:
        import_csv_into(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            source="activities_csv",
            record_raw=record_raw,
        )
    for path in collected["activities_json"]:
        _import_json_file(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            record_raw=record_raw,
        )
    for path in collected["fit"]:
        _import_fit_file(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            record_raw=record_raw,
            strict=False,
        )
    for path in collected["tcx"]:
        _import_tcx_file(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            record_raw=record_raw,
        )
    for path in collected["uds"]:
        _import_uds_file(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            record_raw=record_raw,
        )
    for path in collected["sleep"]:
        _import_sleep_file(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            record_raw=record_raw,
        )
    for path in collected["health"]:
        _import_health_status_file(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            record_raw=record_raw,
        )
    for path in collected["readiness"]:
        _import_training_readiness_file(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            record_raw=record_raw,
        )
    for path in collected["biometrics"]:
        _import_biometrics_file(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            record_raw=record_raw,
        )
    for path in collected["fitness_age"]:
        _import_fitness_age_file(
            conn,
            raw_store,
            user_id=user_id,
            path=path,
            result=result,
            record_raw=record_raw,
        )


def _status(result: ImportResult) -> str:
    if not result.issues and (result.files_ok or result.rows_skipped):
        return "ok"
    if result.files_ok or result.rows_ok or result.rows_skipped:
        return "partial"
    return "failed"


def looks_like_full_export(path: str | Path) -> bool:
    """Return True when a path is a full export rather than a wellness ZIP."""
    candidate = Path(path).expanduser()
    if candidate.is_file():
        suffix = candidate.suffix.lower()
        if suffix in {".csv", ".json", ".tcx"}:
            return True
        if suffix == ".fit":
            return "activity" in candidate.name.lower()
        if suffix != ".zip":
            return False
        try:
            with zipfile.ZipFile(candidate) as archive:
                for name in archive.namelist():
                    lower = name.lower()
                    base = lower.rsplit("/", 1)[-1]
                    if (
                        "di_connect" in lower
                        or "di-connect" in lower
                        or "summarizedactivities" in lower
                        or "udsfile" in lower
                        or "sleepdata" in lower
                        or "healthstatusdata" in lower
                        or "trainingreadiness" in lower
                        or base.startswith("activities")
                        or (base.endswith(".fit") and "activity" in base)
                    ):
                        return True
        except (OSError, zipfile.BadZipFile):
            return False
        return False

    if candidate.is_dir():
        for current, dirs, files in os.walk(candidate):
            if any("di_connect" in name.lower() or "di-connect" in name.lower() for name in dirs):
                return True
            for name in files:
                lower = name.lower()
                if (
                    (lower.startswith("activities") and lower.endswith(".csv"))
                    or ("summarizedactivities" in lower and lower.endswith(".json"))
                    or ("udsfile" in lower and lower.endswith(".json"))
                    or ("sleepdata" in lower and lower.endswith(".json"))
                ):
                    return True
    return False


def import_full_export_path(
    path: str | Path,
    *,
    conn,
    raw_store: RawStore,
    user_id: int,
    tmp_dir: str | Path,
    limits: ZipLimits | None = None,
) -> ImportResult:
    """Import activities from a full-export ZIP, extracted folder or file."""
    source_path = Path(path).expanduser()
    if not source_path.exists():
        raise GarminImportError("full export path does not exist")

    run_id = start_run(conn, user_id=user_id, kind="full_export")
    result = ImportResult(status="running", run_id=run_id)
    try:
        suffix = source_path.suffix.lower()
        if source_path.is_dir():
            _import_tree(
                conn,
                raw_store,
                user_id=user_id,
                root=source_path,
                result=result,
                record_raw=True,
            )
        elif suffix == ".zip":
            _save_raw(conn, raw_store, user_id=user_id, path=source_path, result=result)
            tmp_root = Path(tmp_dir).expanduser().resolve()
            tmp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.TemporaryDirectory(
                prefix="garmin-full-", dir=str(tmp_root)
            ) as tmp:
                bundle_root = Path(tmp) / source_path.stem
                extract(source_path, bundle_root, limits=limits)
                _import_tree(
                    conn,
                    raw_store,
                    user_id=user_id,
                    root=bundle_root,
                    result=result,
                    record_raw=False,
                )
        elif suffix == ".csv":
            import_csv_into(
                conn,
                raw_store,
                user_id=user_id,
                path=source_path,
                result=result,
                source=SOURCE,
            )
        elif suffix == ".json":
            lower = source_path.name.lower()
            if "udsfile" in lower:
                _import_uds_file(
                    conn,
                    raw_store,
                    user_id=user_id,
                    path=source_path,
                    result=result,
                    record_raw=True,
                )
            elif "sleepdata" in lower:
                _import_sleep_file(
                    conn,
                    raw_store,
                    user_id=user_id,
                    path=source_path,
                    result=result,
                    record_raw=True,
                )
            elif "healthstatusdata" in lower:
                _import_health_status_file(
                    conn,
                    raw_store,
                    user_id=user_id,
                    path=source_path,
                    result=result,
                    record_raw=True,
                )
            elif "trainingreadiness" in lower:
                _import_training_readiness_file(
                    conn,
                    raw_store,
                    user_id=user_id,
                    path=source_path,
                    result=result,
                    record_raw=True,
                )
            elif "userbiometrics" in lower:
                _import_biometrics_file(
                    conn,
                    raw_store,
                    user_id=user_id,
                    path=source_path,
                    result=result,
                    record_raw=True,
                )
            elif "fitnessagedata" in lower:
                _import_fitness_age_file(
                    conn,
                    raw_store,
                    user_id=user_id,
                    path=source_path,
                    result=result,
                    record_raw=True,
                )
            else:
                _import_json_file(
                    conn,
                    raw_store,
                    user_id=user_id,
                    path=source_path,
                    result=result,
                    record_raw=True,
                )
        elif suffix == ".tcx":
            _import_tcx_file(
                conn,
                raw_store,
                user_id=user_id,
                path=source_path,
                result=result,
                record_raw=True,
            )
        elif suffix == ".fit":
            _import_fit_file(
                conn,
                raw_store,
                user_id=user_id,
                path=source_path,
                result=result,
                record_raw=True,
                strict=True,
            )
        else:
            raise GarminImportError("unsupported full export file type")

        result.status = _status(result)
    except Exception as exc:  # noqa: BLE001 - always close the run
        result.issues.append(ImportIssue(file=str(source_path), error=str(exc)))
        result.status = "failed"
    finally:
        finish_run(
            conn,
            run_id,
            status=result.status,
            files_total=result.files_total,
            files_ok=result.files_ok,
            files_failed=result.files_failed,
            error_text="; ".join(issue.error for issue in result.issues) or None,
        )
    return result
