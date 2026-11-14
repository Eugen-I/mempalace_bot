"""Import Garmin "Export Wellness Data" bundles.

The official export is a ZIP with one or more daily folders of FIT files.  The
importer saves every raw object, decodes the FIT bundle, and performs partial
upserts so an import cannot erase online or manually entered values.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import GarminImportError
from ..fit_wellness import decode_bundle, to_daily_row, to_extra_metrics
from ..raw_store import RawStore
from ..repository import (
    finish_run,
    record_raw_file,
    start_run,
    upsert_daily,
    upsert_extra_metric,
)
from ..zip_safety import ZipLimits, extract, fit_files

SOURCE_ZIP = "wellness_zip"
SOURCE_FIT = "wellness_fit"


@dataclass(frozen=True)
class ImportIssue:
    file: str
    error: str


@dataclass
class ImportResult:
    status: str
    run_id: int | None = None
    days: list[str] = field(default_factory=list)
    files_total: int = 0
    files_ok: int = 0
    files_failed: int = 0
    rows_total: int = 0
    rows_ok: int = 0
    rows_failed: int = 0
    rows_skipped: int = 0
    raw_sha256: list[str] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "days": sorted(set(self.days)),
            "files_total": self.files_total,
            "files_ok": self.files_ok,
            "files_failed": self.files_failed,
            "rows_total": self.rows_total,
            "rows_ok": self.rows_ok,
            "rows_failed": self.rows_failed,
            "rows_skipped": self.rows_skipped,
            "raw_sha256": self.raw_sha256,
            "issues": [{"file": issue.file, "error": issue.error} for issue in self.issues],
        }


def _record_raw(
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


def _count_daily_row(result: ImportResult, status: str) -> None:
    result.rows_total += 1
    if status == "skipped":
        result.rows_skipped += 1
    elif status in {"inserted", "updated"}:
        result.rows_ok += 1
    else:
        result.rows_failed += 1


def _import_fits(
    conn,
    raw_store: RawStore,
    *,
    user_id: int,
    root: Path,
    date_hint: str | None,
    result: ImportResult,
) -> None:
    paths = fit_files(root)
    result.files_total = len(paths)
    if not paths:
        result.issues.append(ImportIssue(file=str(root), error="no FIT files found"))
        return

    parents: dict[Path, list[Path]] = {}
    for path in paths:
        parents.setdefault(path.parent, []).append(path)

    for parent, parent_paths in sorted(parents.items()):
        for path in parent_paths:
            try:
                _record_raw(
                    conn,
                    raw_store,
                    user_id=user_id,
                    path=path,
                    source=SOURCE_FIT,
                    result=result,
                )
                result.files_ok += 1
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
                result.files_failed += 1
                result.issues.append(ImportIssue(file=str(path), error=str(exc)))

        try:
            decoded = decode_bundle(parent, date_hint=date_hint)
            if not _has_data(decoded):
                result.files_failed += 1
                result.issues.append(
                    ImportIssue(file=str(parent), error="no wellness data in bundle")
                )
                continue
            row = to_daily_row(decoded, user_id=user_id)
            status = upsert_daily(conn, row, source=SOURCE_FIT)
            _count_daily_row(result, status)
            for metric in to_extra_metrics(decoded, user_id=user_id):
                upsert_extra_metric(conn, metric)
            result.days.append(str(row["date"]))
        except Exception as exc:  # noqa: BLE001 - malformed bundles are quarantined
            result.files_failed += 1
            result.issues.append(ImportIssue(file=str(parent), error=str(exc)))


def _has_data(decoded: dict) -> bool:
    keys = (
        "heart_rate",
        "stress",
        "sleep",
        "sleep_stages",
        "hrv",
        "skin_temp",
        "steps",
        "distance_m",
        "naps",
    )
    return any(decoded.get(key) for key in keys)


def _status(result: ImportResult) -> str:
    if result.days and not result.issues:
        return "ok"
    if result.days:
        return "partial"
    return "failed"


def import_wellness_path(
    path: str | Path,
    *,
    conn,
    raw_store: RawStore,
    user_id: int,
    tmp_dir: str | Path,
    limits: ZipLimits | None = None,
) -> ImportResult:
    """Import a wellness ZIP, a single FIT file, or an extracted folder."""
    source_path = Path(path).expanduser()
    if not source_path.exists():
        raise GarminImportError("wellness import path does not exist")

    run_id = start_run(conn, user_id=user_id, kind="wellness")
    result = ImportResult(status="running", run_id=run_id)
    try:
        if source_path.is_dir():
            _import_fits(
                conn,
                raw_store,
                user_id=user_id,
                root=source_path,
                date_hint=source_path.name,
                result=result,
            )
        elif source_path.suffix.lower() == ".zip":
            _record_raw(
                conn,
                raw_store,
                user_id=user_id,
                path=source_path,
                source=SOURCE_ZIP,
                result=result,
            )
            tmp_root = Path(tmp_dir).expanduser().resolve()
            tmp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.TemporaryDirectory(
                prefix="garmin-wellness-", dir=str(tmp_root)
            ) as tmp:
                bundle_root = Path(tmp) / source_path.stem
                extract(source_path, bundle_root, limits=limits)
                _import_fits(
                    conn,
                    raw_store,
                    user_id=user_id,
                    root=bundle_root,
                    date_hint=source_path.stem,
                    result=result,
                )
        elif source_path.suffix.lower() == ".fit":
            _record_raw(
                conn,
                raw_store,
                user_id=user_id,
                path=source_path,
                source=SOURCE_FIT,
                result=result,
            )
            result.files_total = 1
            result.files_ok = 1
            tmp_root = Path(tmp_dir).expanduser().resolve()
            tmp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.TemporaryDirectory(
                prefix="garmin-fit-", dir=str(tmp_root)
            ) as tmp:
                bundle = Path(tmp) / source_path.stem
                bundle.mkdir(mode=0o700)
                shutil.copy2(source_path, bundle / source_path.name)
                decoded = decode_bundle(bundle, date_hint=source_path.stem)
                if not _has_data(decoded):
                    raise GarminImportError("no wellness data in bundle")
                row = to_daily_row(decoded, user_id=user_id)
                status = upsert_daily(conn, row, source=SOURCE_FIT)
                _count_daily_row(result, status)
                for metric in to_extra_metrics(decoded, user_id=user_id):
                    upsert_extra_metric(conn, metric)
                result.days.append(str(row["date"]))
        else:
            raise GarminImportError("unsupported wellness file type")

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
