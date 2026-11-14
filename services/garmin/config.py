"""Configuration for the Garmin integration.

The module intentionally does not read the bot's global ``config`` at import
time.  Tests can construct a config with an explicit ``data_dir`` and the bot
can later wire it to the global configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import GarminConfigError

DEFAULT_DATA_DIR = "~/Documents/mempalace/garmin"
DEFAULT_AI_MODEL = "qwen3.6-12b-uncensored:latest"
DEFAULT_AI_FALLBACK_MODEL = "qwen2.5:7b"
DEFAULT_AI_FALLBACK_TIMEOUT = 60.0
DEFAULT_PLAN_HORIZON_WEEKS = 6
DEFAULT_RETENTION_DAYS = 365
DEFAULT_MAX_SYNC_DAYS = 7
DEFAULT_REQUEST_DELAY = 2.0
DEFAULT_CHART_DPI = 200
DEFAULT_PDF_MAX_MB = 45
DEFAULT_SLEEP_TARGET_H = 7.5


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise GarminConfigError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise GarminConfigError(f"{name} must be a number") from exc


def _path_from_env(name: str, default: Path, base: Path | None = None) -> Path:
    raw = (os.getenv(name) or "").strip()
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute() and base is not None:
        path = base / path
    return path


@dataclass(frozen=True)
class GarminConfig:
    """Resolved, filesystem-safe Garmin configuration."""

    data_dir: Path
    db_path: Path
    import_dir: Path
    report_dir: Path
    raw_dir: Path
    quarantine_dir: Path
    tmp_dir: Path
    charts_dir: Path
    ai_model: str = DEFAULT_AI_MODEL
    ai_timeout: float = 120.0
    ai_fallback_model: str = DEFAULT_AI_FALLBACK_MODEL
    ai_fallback_timeout: float = DEFAULT_AI_FALLBACK_TIMEOUT
    ai_enabled: bool = True
    plan_horizon_weeks: int = DEFAULT_PLAN_HORIZON_WEEKS
    retention_days: int = DEFAULT_RETENTION_DAYS
    online_enabled: bool = False
    max_sync_days: int = DEFAULT_MAX_SYNC_DAYS
    request_delay: float = DEFAULT_REQUEST_DELAY
    chart_dpi: int = DEFAULT_CHART_DPI
    pdf_max_mb: int = DEFAULT_PDF_MAX_MB
    sleep_target_h: float = DEFAULT_SLEEP_TARGET_H

    @classmethod
    def from_env(cls, data_dir: str | Path | None = None) -> "GarminConfig":
        """Build config from environment variables.

        ``data_dir`` is useful for tests and for wiring the bot's own data
        directory.  Relative paths are resolved under ``data_dir``.
        """
        base = Path(
            data_dir
            or os.getenv("GARMIN_DATA_DIR")
            or DEFAULT_DATA_DIR
        ).expanduser()
        base = base.resolve()

        db_path = _path_from_env("GARMIN_DB_PATH", base / "garmin.sqlite", base)
        import_dir = _path_from_env("GARMIN_IMPORT_DIR", base / "import", base)
        report_dir = _path_from_env("GARMIN_REPORT_DIR", base / "reports", base)
        raw_dir = _path_from_env("GARMIN_RAW_DIR", base / "raw", base)
        quarantine_dir = _path_from_env(
            "GARMIN_QUARANTINE_DIR", base / "quarantine", base
        )
        tmp_dir = _path_from_env("GARMIN_TMP_DIR", base / "tmp", base)
        charts_dir = _path_from_env("GARMIN_CHARTS_DIR", base / "charts", base)

        cfg = cls(
            data_dir=base,
            db_path=db_path,
            import_dir=import_dir,
            report_dir=report_dir,
            raw_dir=raw_dir,
            quarantine_dir=quarantine_dir,
            tmp_dir=tmp_dir,
            charts_dir=charts_dir,
            ai_model=(os.getenv("GARMIN_AI_MODEL") or DEFAULT_AI_MODEL).strip(),
            ai_timeout=_env_float("GARMIN_AI_TIMEOUT", 120.0),
            ai_fallback_model=(
                os.getenv("GARMIN_AI_FALLBACK_MODEL") or DEFAULT_AI_FALLBACK_MODEL
            ).strip(),
            ai_fallback_timeout=_env_float(
                "GARMIN_AI_FALLBACK_TIMEOUT", DEFAULT_AI_FALLBACK_TIMEOUT
            ),
            ai_enabled=_env_bool("GARMIN_AI_ENABLED", True),
            plan_horizon_weeks=_env_int(
                "GARMIN_PLAN_HORIZON_WEEKS", DEFAULT_PLAN_HORIZON_WEEKS
            ),
            retention_days=_env_int(
                "GARMIN_DATA_RETENTION_DAYS", DEFAULT_RETENTION_DAYS
            ),
            online_enabled=_env_bool("GARMIN_ONLINE_ENABLED", False),
            max_sync_days=_env_int("GARMIN_MAX_SYNC_DAYS", DEFAULT_MAX_SYNC_DAYS),
            request_delay=_env_float(
                "GARMIN_REQUEST_DELAY", DEFAULT_REQUEST_DELAY
            ),
            chart_dpi=_env_int("GARMIN_CHART_DPI", DEFAULT_CHART_DPI),
            pdf_max_mb=_env_int("GARMIN_PDF_MAX_MB", DEFAULT_PDF_MAX_MB),
            sleep_target_h=_env_float(
                "GARMIN_SLEEP_TARGET_H", DEFAULT_SLEEP_TARGET_H
            ),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.plan_horizon_weeks < 1 or self.plan_horizon_weeks > 52:
            raise GarminConfigError("GARMIN_PLAN_HORIZON_WEEKS must be 1..52")
        if self.retention_days < 1:
            raise GarminConfigError("GARMIN_DATA_RETENTION_DAYS must be positive")
        if not 1 <= self.max_sync_days <= 7:
            raise GarminConfigError("GARMIN_MAX_SYNC_DAYS must be 1..7")
        if self.request_delay < 1.0:
            raise GarminConfigError("GARMIN_REQUEST_DELAY must be >= 1.0")
        if not 1 <= self.chart_dpi <= 600:
            raise GarminConfigError("GARMIN_CHART_DPI must be 1..600")
        if self.pdf_max_mb < 1:
            raise GarminConfigError("GARMIN_PDF_MAX_MB must be positive")
        if not 4.0 <= self.sleep_target_h <= 12.0:
            raise GarminConfigError("GARMIN_SLEEP_TARGET_H must be 4..12")
        if self.ai_timeout <= 0:
            raise GarminConfigError("GARMIN_AI_TIMEOUT must be positive")
        if self.ai_fallback_timeout <= 0:
            raise GarminConfigError("GARMIN_AI_FALLBACK_TIMEOUT must be positive")

    def ensure_dirs(self) -> None:
        """Create the private directory tree with restrictive permissions."""
        for directory in (
            self.data_dir,
            self.import_dir,
            self.report_dir,
            self.raw_dir,
            self.quarantine_dir,
            self.tmp_dir,
            self.charts_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)


def get_config(data_dir: str | Path | None = None) -> GarminConfig:
    """Return a fresh config; tests should pass an explicit directory."""
    return GarminConfig.from_env(data_dir=data_dir)
