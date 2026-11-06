"""Import Garmin Connect "Activities -> Export CSV".

Garmin's CSV export uses human-readable headers and local timestamps.  Header
names and units vary between locales, so the importer normalizes headers,
accepts EN/RU aliases and treats missing optional columns as ``None``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ..errors import GarminImportError
from ..raw_store import RawStore
from ..repository import (
    finish_run,
    record_raw_file,
    start_run,
    upsert_activity,
)
from .wellness_fit import ImportIssue, ImportResult

SOURCE = "activities_csv"

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "activity_id": (
        "activity id", "activityid", "id", "id активности",
        "идентификатор активности",
    ),
    "activity_type": (
        "activity type", "type", "sport", "activitytype",
        "тип активности", "вид активности", "спорт",
        "тип занятия", "тип тренировки",
    ),
    "start_time": (
        "date", "start time", "start time local", "begin timestamp",
        "starttime", "дата", "дата начала", "время начала",
    ),
    "name": ("title", "name", "activity name", "название", "заголовок"),
    "duration": (
        "time", "duration", "elapsed time", "moving time", "total time",
        "время", "длительность", "общее время",
    ),
    "distance": (
        "distance", "distance km", "дистанция", "дистанция км",
        "расстояние", "расстояние км",
    ),
    "distance_m": (
        "distance m", "distance meters", "distance (m)", "дистанция м",
        "дистанция (м)",
    ),
    "calories": ("calories", "kcal", "калории", "ккал"),
    "avg_hr": (
        "avg hr", "average hr", "average heart rate", "avg heart rate",
        "средний пульс", "ср пульс", "средняя чп", "средняя чсс",
        "средняя частота пульса",
    ),
    "max_hr": (
        "max hr", "maximum hr", "maximum heart rate", "макс пульс",
        "максимальный пульс", "максимальная чп", "максимальная чсс",
        "максимальная частота пульса",
    ),
    "training_load": (
        "activity training load", "training load", "training stress score",
        "tss", "тренировочная нагрузка",
    ),
    "aerobic_te": (
        "aerobic te", "aerobic training effect", "аэробный эффект",
        "аэробный те", "аэробный тренировочный эффект",
    ),
    "anaerobic_te": (
        "anaerobic te", "anaerobic training effect", "анаэробный эффект",
        "анаэробный те", "анаэробный тренировочный эффект",
    ),
    "pace": ("average pace", "avg pace", "pace", "средний темп", "темп"),
    "speed": ("avg speed", "average speed", "средняя скорость"),
    "elevation_gain": (
        "total ascent", "elevation gain", "набор высоты", "общий подъём",
        "общий подъем",
    ),
}

_TYPE_MAP = (
    ("indoor cycling", "cycling"),
    ("virtual ride", "cycling"),
    ("road biking", "cycling"),
    ("mountain biking", "cycling"),
    ("e-bike", "cycling"),
    ("cycling", "cycling"),
    ("biking", "cycling"),
    ("велосипед", "cycling"),
    ("trail running", "running"),
    ("treadmill running", "running"),
    ("indoor running", "running"),
    ("running", "running"),
    ("бег", "running"),
    ("strength training", "strength"),
    ("weight training", "strength"),
    ("strength", "strength"),
    ("силовая", "strength"),
    ("силовые", "strength"),
    ("кроссфит", "strength"),
    ("функциональный тренинг", "strength"),
    ("walking", "walking"),
    ("ходьба", "walking"),
    ("hiking", "hiking"),
    ("поход", "hiking"),
    ("lap swimming", "swimming"),
    ("open water swimming", "swimming"),
    ("swimming", "swimming"),
    ("плавание", "swimming"),
    ("yoga", "mobility"),
    ("pilates", "mobility"),
    ("stretching", "mobility"),
    ("mobility", "mobility"),
    ("йога", "mobility"),
    ("медитация", "mobility"),
    ("дыхание", "mobility"),
    ("coherence", "mobility"),
    ("растяжка", "mobility"),
    ("rowing", "cardio"),
    ("elliptical", "cardio"),
    ("stair climbing", "cardio"),
    ("cardio", "cardio"),
    ("кардио", "cardio"),
    ("гребля", "cardio"),
    ("эллиптический", "cardio"),
    ("лестница", "cardio"),
)

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)

_EMPTY_VALUES = {"", "-", "—", "–", "n/a", "na", "none", "null"}


def _norm_header(value: str) -> str:
    text = (value or "").replace("\ufeff", "").strip().lower()
    text = re.sub(r"[_\-/]+", " ", text)
    text = re.sub(r"[^\w ]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _clean(value: Any) -> str:
    text = str(value or "").strip().strip('"').strip()
    return "" if text.lower() in _EMPTY_VALUES else text


def _to_float(value: Any) -> float | None:
    text = _clean(value)
    if not text:
        return None
    text = text.replace("\u00a0", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return round(number) if number is not None else None


def parse_activity_datetime(value: Any) -> str | None:
    """Public alias for ISO/local timestamp normalization."""
    return _parse_datetime(value)


def _parse_datetime(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed.replace(microsecond=0).isoformat()


def _parse_duration_min(value: Any) -> float | None:
    text = _clean(value).lower().replace(",", ".")
    if not text:
        return None
    unit = "seconds"
    if "min" in text or "мин" in text:
        unit = "minutes"
        text = re.sub(r"(min|мин)[a-zа-я.]*", "", text)
    elif re.search(r"(^|\d)\s*h", text) or "час" in text:
        unit = "hours"
        text = re.sub(r"(h|час)[a-zа-я.]*", "", text)
    elif re.search(r"(^|\d)\s*s", text) or "сек" in text:
        text = re.sub(r"(s|сек)[a-zа-я.]*", "", text)
    text = text.strip()

    if ":" in text:
        parts = text.split(":")
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            return None
        if len(numbers) == 3:
            return (numbers[0] * 3600 + numbers[1] * 60 + numbers[2]) / 60.0
        if len(numbers) == 2:
            return (numbers[0] * 60 + numbers[1]) / 60.0
        return None

    number = _to_float(text)
    if number is None:
        return None
    if unit == "minutes":
        return number
    if unit == "hours":
        return number * 60.0
    # Bare numbers in Garmin CSV/JSON are seconds.
    return number / 60.0


def _distance_m(value: Any, header: str) -> float | None:
    text = _clean(value).lower().replace(",", ".")
    if not text:
        return None
    number = _to_float(text)
    if number is None:
        return None
    if "km" in text or "км" in text:
        return number * 1000.0
    if re.search(r"\bmi\b", text):
        return number * 1609.344
    if re.search(r"\bm\b", text) or re.search(r"\bм\b", text):
        return number
    header = header.lower()
    if ("km" in header or "км" in header) and " m" not in header:
        return number * 1000.0
    if " m" in header or "meter" in header or "мет" in header:
        return number
    # Garmin's "Distance" column is kilometres.
    return number * 1000.0


def _pace_seconds(value: Any) -> float | None:
    text = _clean(value).lower()
    if not text:
        return None
    text = re.sub(r"(min|мин)\s*/\s*(km|км)", "", text)
    text = re.sub(r"/\s*(km|км)", "", text)
    text = text.replace(",", ".").strip()
    if ":" in text:
        parts = text.split(":")
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            return None
        if len(numbers) == 2:
            return numbers[0] * 60 + numbers[1]
        if len(numbers) == 3:
            return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
        return None
    number = _to_float(text)
    if number is None:
        return None
    # Values like "5.5" mean minutes per kilometre; large values are seconds.
    return number * 60 if number <= 30 else number


def _normalize_type(value: Any) -> str:
    text = _clean(value).lower()
    if not text:
        return "other"
    compact = re.sub(r"[_\-\s]+", " ", text)
    for needle, canonical in _TYPE_MAP:
        if needle in compact:
            return canonical
    return compact.replace(" ", "_") or "other"


def normalize_activity_type(value: Any) -> str:
    """Public alias used by the FIT/TCX/JSON parsers."""
    return _normalize_type(value)


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise GarminImportError("cannot decode activities CSV")


def _delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


def _header_index(fieldnames: Iterable[str] | None) -> dict[str, str]:
    index: dict[str, str] = {}
    for name in fieldnames or []:
        normalized = _norm_header(name)
        if normalized and normalized not in index:
            index[normalized] = name
    return index


def _pick(row: dict[str, Any], index: dict[str, str], field: str) -> tuple[str, str]:
    for alias in _HEADER_ALIASES[field]:
        actual = index.get(alias)
        if actual is not None:
            return actual, _clean(row.get(actual))
    return "", ""


def _row_to_activity(
    row: dict[str, Any], index: dict[str, str], user_id: int
) -> tuple[dict[str, Any] | None, str | None]:
    start_header, start_value = _pick(row, index, "start_time")
    start_time = _parse_datetime(start_value)
    if start_time is None:
        return None, f"bad start time: {start_value or 'missing'}"

    _, type_value = _pick(row, index, "activity_type")
    activity_type = _normalize_type(type_value)

    _, duration_value = _pick(row, index, "duration")
    duration_min = _parse_duration_min(duration_value)

    distance_header, distance_value = _pick(row, index, "distance")
    if distance_value:
        distance_m = _distance_m(distance_value, distance_header)
    else:
        meter_header, meter_value = _pick(row, index, "distance_m")
        distance_m = _distance_m(meter_value, meter_header) if meter_value else None

    _, speed_value = _pick(row, index, "speed")
    speed_kmh = _to_float(speed_value)
    if duration_min is None and distance_m and speed_kmh:
        duration_min = (distance_m / 1000.0) / speed_kmh * 60.0

    _, pace_value = _pick(row, index, "pace")
    pace = _pace_seconds(pace_value)
    if pace is None and speed_kmh:
        pace = 3600.0 / speed_kmh
    if pace is None and duration_min and distance_m:
        pace = duration_min * 60.0 / (distance_m / 1000.0)

    _, elevation_value = _pick(row, index, "elevation_gain")
    elevation = _to_float(elevation_value)

    _, calories_value = _pick(row, index, "calories")
    _, avg_hr_value = _pick(row, index, "avg_hr")
    _, max_hr_value = _pick(row, index, "max_hr")
    _, load_value = _pick(row, index, "training_load")
    _, aerobic_value = _pick(row, index, "aerobic_te")
    _, anaerobic_value = _pick(row, index, "anaerobic_te")
    _, name_value = _pick(row, index, "name")
    _, id_value = _pick(row, index, "activity_id")

    if id_value:
        activity_id = id_value
        if id_value.endswith(".0") and id_value[:-2].isdigit():
            activity_id = id_value[:-2]
    else:
        seed = "|".join(
            [
                start_time,
                activity_type,
                f"{duration_min or 0:.3f}",
                f"{distance_m or 0:.1f}",
            ]
        )
        activity_id = "csv_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

    activity: dict[str, Any] = {
        "user_id": int(user_id),
        "activity_id": activity_id,
        "start_time": start_time,
        "activity_type": activity_type,
        "name": name_value or None,
        "duration_min": round(duration_min, 2) if duration_min is not None else None,
        "distance_m": round(distance_m, 1) if distance_m is not None else None,
        "calories": _to_int(calories_value),
        "avg_hr": _to_int(avg_hr_value),
        "max_hr": _to_int(max_hr_value),
        "training_load": _to_float(load_value),
        "aerobic_te": _to_float(aerobic_value),
        "anaerobic_te": _to_float(anaerobic_value),
        "avg_pace_s_per_km": round(pace, 1) if pace is not None else None,
        "elevation_gain_m": round(elevation, 1) if elevation is not None else None,
        "raw_json": json.dumps(row, ensure_ascii=False, sort_keys=True),
    }
    return activity, None


def _save_raw(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    source: str,
    result: ImportResult,
) -> None:
    info = raw_store.save_file(user_id, path, source=source, filename=path.name)
    record_raw_file(
        conn,
        user_id=user_id,
        sha256=info.sha256,
        source=source,
        filename=info.filename,
        size_bytes=info.size_bytes,
    )
    result.raw_sha256.append(info.sha256)


def import_csv_into(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    path: Path,
    result: ImportResult,
    source: str = SOURCE,
    record_raw: bool = True,
) -> None:
    """Import one CSV file into an existing result (no run lifecycle)."""
    result.files_total += 1
    try:
        if record_raw:
            _save_raw(
                conn,
                raw_store,
                user_id=user_id,
                path=path,
                source=source,
                result=result,
            )
        text = _read_text(path)
        reader = csv.DictReader(io.StringIO(text), delimiter=_delimiter(text))
        index = _header_index(reader.fieldnames)
        has_start = any(index.get(alias) for alias in _HEADER_ALIASES["start_time"])
        if not index or not has_start:
            raise GarminImportError("activities CSV has no start date column")

        rows = 0
        imported = 0
        for row in reader:
            if not any(_clean(value) for value in row.values()):
                continue
            rows += 1
            result.rows_total += 1
            activity, error = _row_to_activity(row, index, user_id)
            if activity is None:
                result.rows_failed += 1
                result.issues.append(
                    ImportIssue(file=path.name, error=error or "bad row")
                )
                continue
            status = upsert_activity(conn, activity, source=source)
            if status == "skipped":
                result.rows_skipped += 1
            else:
                imported += 1
                result.rows_ok += 1
                result.days.append(str(activity["start_time"])[:10])

        if rows == 0:
            raise GarminImportError("activities CSV has no rows")
        if imported == 0 and result.rows_skipped == 0:
            raise GarminImportError("activities CSV has no valid activities")
        result.files_ok += 1
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
        result.files_failed += 1
        result.issues.append(ImportIssue(file=path.name, error=str(exc)))


def import_activities_csv(
    path: str | Path,
    *,
    conn,
    raw_store: RawStore,
    user_id: int,
) -> ImportResult:
    """Import one Garmin activities CSV as a standalone run."""
    source_path = Path(path).expanduser()
    if not source_path.exists():
        raise GarminImportError("activities CSV path does not exist")
    if source_path.suffix.lower() != ".csv":
        raise GarminImportError("unsupported activities file type")

    run_id = start_run(conn, user_id=user_id, kind="activities")
    result = ImportResult(status="running", run_id=run_id)
    try:
        import_csv_into(
            conn,
            raw_store,
            user_id=user_id,
            path=source_path,
            result=result,
        )
        if result.files_ok and not result.issues:
            result.status = "ok"
        elif result.files_ok:
            result.status = "partial"
        else:
            result.status = "failed"
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
