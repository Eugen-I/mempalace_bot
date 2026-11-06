"""Route a Garmin export path to the right importer."""

from __future__ import annotations

from pathlib import Path

from ..errors import GarminImportError
from ..raw_store import RawStore
from ..zip_safety import ZipLimits
from .activities_csv import import_activities_csv
from .full_export import import_full_export_path, looks_like_full_export
from .wellness_fit import ImportResult, import_wellness_path

WELLNESS = "wellness"
ACTIVITIES_CSV = "activities_csv"
FULL_EXPORT = "full_export"


def detect_import_kind(path: str | Path) -> str:
    """Detect wellness ZIP/FIT, activities CSV or a full export."""
    candidate = Path(path).expanduser()
    suffix = candidate.suffix.lower()
    if candidate.is_dir():
        return FULL_EXPORT if looks_like_full_export(candidate) else WELLNESS
    if suffix == ".csv":
        return ACTIVITIES_CSV
    if suffix in {".json", ".tcx"}:
        return FULL_EXPORT
    if suffix == ".zip":
        return FULL_EXPORT if looks_like_full_export(candidate) else WELLNESS
    if suffix == ".fit":
        return FULL_EXPORT if looks_like_full_export(candidate) else WELLNESS
    return "unsupported"


def import_any_path(
    path: str | Path,
    *,
    conn,
    raw_store: RawStore,
    user_id: int,
    tmp_dir: str | Path,
    limits: ZipLimits | None = None,
) -> ImportResult:
    """Import any supported Garmin export without user input."""
    kind = detect_import_kind(path)
    if kind == ACTIVITIES_CSV:
        return import_activities_csv(
            path,
            conn=conn,
            raw_store=raw_store,
            user_id=user_id,
        )
    if kind == FULL_EXPORT:
        return import_full_export_path(
            path,
            conn=conn,
            raw_store=raw_store,
            user_id=user_id,
            tmp_dir=tmp_dir,
            limits=limits,
        )
    if kind == WELLNESS:
        return import_wellness_path(
            path,
            conn=conn,
            raw_store=raw_store,
            user_id=user_id,
            tmp_dir=tmp_dir,
            limits=limits,
        )
    raise GarminImportError("unsupported Garmin export file type")
