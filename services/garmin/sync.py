"""Incremental Garmin Connect online sync with rate-limit protection.

Enforces:
- Maximum sync window of ``cfg.max_sync_days`` (1..7 days).
- Minimum cooldown between sync runs (default 15 minutes).
- Throttling between endpoint calls (``cfg.request_delay`` >= 1.0s).
- Raw JSON archiving via ``RawStore`` and source-precedence upserts
  (``source="online"``, priority 3).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable

from .auth import restore_authenticated_client
from .config import GarminConfig, get_config
from .crypto import GarminCipher
from .errors import GarminAuthError, GarminOnlineError, GarminRateLimitError
from .online import normalize_activity_item, normalize_daily_bundle
from .raw_store import RawStore
from .repository import (
    finish_run,
    record_raw_file,
    start_run,
    upsert_activity,
    upsert_daily,
)
from .session_store import (
    get_account_state,
    record_auth_failure,
    record_fetch_failure,
    record_sync_success,
)

logger = logging.getLogger(__name__)

SOURCE_ONLINE = "online"
DEFAULT_SYNC_COOLDOWN_SECONDS = 900  # 15 minutes


@dataclass
class OnlineSyncResult:
    status: str  # "ok" | "partial" | "failed"
    run_id: int | None = None
    days_synced: list[str] = field(default_factory=list)
    daily_upserted: int = 0
    activities_upserted: int = 0
    errors: list[str] = field(default_factory=list)


def _check_cooldown(last_sync_at: str | None, cooldown_seconds: int) -> None:
    if not last_sync_at or cooldown_seconds <= 0:
        return
    try:
        last_dt = datetime.fromisoformat(last_sync_at)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=UTC)
    except ValueError:
        return
    elapsed = (datetime.now(UTC) - last_dt).total_seconds()
    if elapsed < cooldown_seconds:
        remain_min = max(1, int(round((cooldown_seconds - elapsed) / 60.0)))
        raise GarminRateLimitError(
            f"Синхронизация недавно выполнялась. Повторите через ~{remain_min} мин "
            "(защита от блокировки Garmin Connect)."
        )


def _call_endpoint(
    fn: Callable[..., Any] | None,
    *args: Any,
    sleep_fn: Callable[[float], None],
    delay: float,
) -> Any:
    if fn is None or not callable(fn):
        return None
    result = fn(*args)
    if delay > 0:
        sleep_fn(delay)
    return result


def _handle_api_exception(
    conn: sqlite3.Connection,
    user_id: int,
    exc: Exception,
) -> None:
    msg = str(exc).lower()
    if "429" in msg or "too many requests" in msg or "rate limit" in msg:
        state = record_fetch_failure(
            conn, user_id, "HTTP 429 (rate limit)", rate_limited=True
        )
        if state.session_status == "rate_limited":
            raise GarminRateLimitError(
                "Получено 3 ответа HTTP 429 подряд. Онлайн-синхронизация "
                "приостановлена для защиты аккаунта; используйте ZIP-экспорт."
            ) from exc
        raise GarminRateLimitError(
            "Garmin Connect временно ограничил частоту запросов (HTTP 429). "
            "Попробуйте позже."
        ) from exc
    if "401" in msg or "unauthorized" in msg or "forbidden" in msg or "403" in msg:
        record_auth_failure(conn, user_id, "сессия истекла или отклонена (401/403)")
        raise GarminAuthError(
            "Онлайн-сессия Garmin Connect истекла или отозвана. "
            "Переподключите аккаунт в меню онлайн-синхронизации."
        ) from exc
    record_fetch_failure(conn, user_id, "ошибка запроса к API Garmin")
    raise GarminOnlineError("Ошибка при получении данных из Garmin Connect.") from exc


def sync_online_days(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    days: int | None = None,
    end_date: date | str | None = None,
    config: GarminConfig | None = None,
    raw_store: RawStore | None = None,
    cipher: GarminCipher | None = None,
    client: Any | None = None,
    client_factory: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    cooldown_seconds: int = DEFAULT_SYNC_COOLDOWN_SECONDS,
    force: bool = False,
) -> OnlineSyncResult:
    """Incrementally fetch up to ``max_sync_days`` of Garmin data via API."""
    cfg = config or get_config()
    account = get_account_state(conn, user_id)
    if not force:
        _check_cooldown(account.last_sync_at, cooldown_seconds)

    sync_days = min(max(int(days or cfg.max_sync_days), 1), cfg.max_sync_days)
    end_dt = (
        date.fromisoformat(end_date)
        if isinstance(end_date, str)
        else end_date
        if isinstance(end_date, date)
        else date.today()
    )
    start_dt = end_dt - timedelta(days=sync_days - 1)
    date_list = [
        (start_dt + timedelta(days=offset)).isoformat()
        for offset in range(sync_days)
    ]

    active_client = client or restore_authenticated_client(
        conn, user_id, cipher=cipher, client_factory=client_factory
    )
    store = raw_store or RawStore(cfg.raw_dir)
    delay = max(float(cfg.request_delay), 1.0) if sleep_fn is time.sleep else 0.0

    run_id = start_run(conn, user_id=user_id, kind=SOURCE_ONLINE)
    result = OnlineSyncResult(status="ok", run_id=run_id)
    files_ok = 0
    files_failed = 0

    try:
        for day_str in date_list:
            try:
                summary = _call_endpoint(
                    getattr(active_client, "get_user_summary", None),
                    day_str,
                    sleep_fn=sleep_fn,
                    delay=delay,
                )
                sleep_data = _call_endpoint(
                    getattr(active_client, "get_sleep_data", None),
                    day_str,
                    sleep_fn=sleep_fn,
                    delay=delay,
                )
                hrv_data = _call_endpoint(
                    getattr(active_client, "get_hrv_data", None),
                    day_str,
                    sleep_fn=sleep_fn,
                    delay=delay,
                )
                readiness_data = _call_endpoint(
                    getattr(active_client, "get_training_readiness", None),
                    day_str,
                    sleep_fn=sleep_fn,
                    delay=delay,
                )
                body_comp = _call_endpoint(
                    getattr(active_client, "get_body_composition", None),
                    day_str,
                    day_str,
                    sleep_fn=sleep_fn,
                    delay=delay,
                )
            except Exception as exc:  # noqa: BLE001
                files_failed += 1
                finish_run(
                    conn,
                    run_id,
                    status="failed",
                    files_total=len(date_list),
                    files_ok=files_ok,
                    files_failed=files_failed,
                    error_text="API error",
                )
                _handle_api_exception(conn, user_id, exc)

            raw_bundle = {
                "date": day_str,
                "summary": summary,
                "sleep": sleep_data,
                "hrv": hrv_data,
                "readiness": readiness_data,
                "body_composition": body_comp,
            }
            raw_bytes = json.dumps(
                raw_bundle, ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
            raw_info = store.save_bytes(
                user_id,
                raw_bytes,
                source=SOURCE_ONLINE,
                filename=f"online_{day_str}.json",
            )
            record_raw_file(
                conn,
                user_id=user_id,
                sha256=raw_info.sha256,
                source=SOURCE_ONLINE,
                filename=raw_info.filename,
                size_bytes=raw_info.size_bytes,
            )

            daily_row = normalize_daily_bundle(
                user_id=user_id,
                day=day_str,
                summary=summary if isinstance(summary, dict) else None,
                sleep=sleep_data if isinstance(sleep_data, dict) else None,
                hrv=hrv_data if isinstance(hrv_data, dict) else None,
                readiness=(
                    readiness_data
                    if isinstance(readiness_data, (dict, list))
                    else None
                ),
                body_composition=(
                    body_comp if isinstance(body_comp, dict) else None
                ),
            )
            if len(daily_row) > 2:
                status = upsert_daily(conn, daily_row, source=SOURCE_ONLINE)
                if status in {"inserted", "updated"}:
                    result.daily_upserted += 1
                result.days_synced.append(day_str)
            files_ok += 1

        try:
            activities_raw = _call_endpoint(
                getattr(active_client, "get_activities_by_date", None),
                start_dt.isoformat(),
                end_dt.isoformat(),
                sleep_fn=sleep_fn,
                delay=delay,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Online activities fetch failed: %s", type(exc).__name__)
            activities_raw = []
            result.errors.append("Не удалось загрузить список тренировок.")

        if isinstance(activities_raw, list):
            for item in activities_raw:
                norm_act = normalize_activity_item(item, user_id=user_id)
                if norm_act is None:
                    continue
                act_status = upsert_activity(conn, norm_act, source=SOURCE_ONLINE)
                if act_status in {"inserted", "updated"}:
                    result.activities_upserted += 1

        result.status = "partial" if result.errors else "ok"
        finish_run(
            conn,
            run_id,
            status=result.status,
            files_total=len(date_list),
            files_ok=files_ok,
            files_failed=files_failed,
        )
        record_sync_success(conn, user_id)
        return result
    except Exception:
        raise
