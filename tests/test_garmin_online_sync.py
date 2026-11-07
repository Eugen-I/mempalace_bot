"""Contract and unit tests for Garmin Connect online auth, session store, and sync."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from services.garmin.auth import (
    restore_authenticated_client,
    start_login,
    submit_mfa_code,
)
from services.garmin.config import GarminConfig
from services.garmin.crypto import GarminCipher
from services.garmin.db import init_db
from services.garmin.errors import GarminAuthError, GarminRateLimitError
from services.garmin.raw_store import RawStore
from services.garmin.repository import get_daily, upsert_daily
from services.garmin.session_store import (
    disconnect_session,
    get_account_state,
    load_session,
    mask_email,
)
from services.garmin.sync import sync_online_days


@pytest.fixture
def cipher() -> GarminCipher:
    return GarminCipher(Fernet.generate_key())


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "garmin.sqlite")
    yield connection
    connection.close()


class _FakeGarminClient:
    def __init__(
        self,
        *,
        email: str | None = None,
        secret: str | None = None,
        return_on_mfa: bool = True,
        needs_mfa: bool = False,
        fail_exc: Exception | None = None,
    ) -> None:
        self.email = email
        self.secret = secret
        self.return_on_mfa = return_on_mfa
        self.needs_mfa = needs_mfa
        self.fail_exc = fail_exc
        self.session_data: dict[str, Any] = {"oauth1": "tok1", "oauth2": "tok2"}
        self.resumed_with: str | None = None

    def login(self) -> Any:
        if self.fail_exc is not None:
            raise self.fail_exc
        if self.needs_mfa:
            return ("needs_mfa", {"ticket": "mfa-ticket-1"})
        return True

    def resume_login(self, client_state: Any, mfa_code: str) -> Any:
        if mfa_code != "123456":
            raise RuntimeError("401 Invalid MFA code")
        self.resumed_with = mfa_code
        return True

    def dump_session(self) -> dict[str, Any]:
        return dict(self.session_data)

    def load_session(self, payload: dict[str, Any]) -> None:
        self.session_data = dict(payload)

    def get_user_summary(self, day: str) -> dict[str, Any]:
        if self.fail_exc is not None:
            raise self.fail_exc
        return {
            "totalSteps": 9450,
            "restingHeartRate": 51,
            "averageStressLevel": 28,
            "maxStressLevel": 72,
            "bodyBatteryChargedValue": 64,
            "bodyBatteryDrainedValue": 55,
            "bodyBatteryHighestValue": 88,
            "bodyBatteryLowestValue": 31,
            "averageSpo2": 96.5,
            "lowestSpo2": 93.0,
            "avgWakingRespirationValue": 14.2,
            "activeKilocalories": 520,
            "totalKilocalories": 2310,
        }

    def get_sleep_data(self, day: str) -> dict[str, Any]:
        return {
            "dailySleepDTO": {
                "sleepTimeSeconds": 27000,
                "deepSleepSeconds": 5400,
                "lightSleepSeconds": 14400,
                "remSleepSeconds": 7200,
                "awakeSleepSeconds": 900,
                "sleepScores": {"overall": {"value": 84}},
            }
        }

    def get_hrv_data(self, day: str) -> dict[str, Any]:
        return {
            "hrvSummary": {
                "lastNightAvg": 64,
                "weeklyAvg": 61,
                "status": "BALANCED",
                "baseline": {"balancedLow": 55, "balancedUpper": 69},
            }
        }

    def get_training_readiness(self, day: str) -> list[dict[str, Any]]:
        return [{"score": 79, "level": "HIGH", "recoveryTime": 360}]

    def get_body_composition(self, start: str, end: str) -> dict[str, Any]:
        return {"totalAverage": {"weight": 78400, "bodyFat": 16.2, "bmi": 23.4}}

    def get_activities_by_date(self, start: str, end: str) -> list[dict[str, Any]]:
        return [
            {
                "activityId": 998877,
                "startTimeLocal": f"{end} 17:30:00",
                "activityType": {"typeKey": "cycling"},
                "activityName": "Evening Ride",
                "duration": 2700.0,
                "distance": 18500.0,
                "calories": 480,
                "averageHR": 142,
                "maxHR": 168,
                "activityTrainingLoad": 95.0,
                "aerobicTrainingEffect": 3.2,
                "anaerobicTrainingEffect": 1.1,
            }
        ]


def test_direct_login_encrypts_session_and_never_stores_password(
    conn, cipher: GarminCipher
):
    secret_pw = "SuperSecretGarminPass!99"
    outcome = start_login(
        conn,
        1,
        email="runner@example.com",
        secret=secret_pw,
        cipher=cipher,
        client_factory=lambda **kw: _FakeGarminClient(**kw),
    )
    assert outcome.status == "connected"
    assert outcome.account.is_connected
    assert outcome.account.masked_email == "r***@example.com"
    assert mask_email("a@b.org") == "*@b.org"

    raw_row = conn.execute(
        "SELECT encrypted_session_json FROM garmin_accounts WHERE user_id = 1"
    ).fetchone()
    raw_bytes = bytes(raw_row["encrypted_session_json"])
    assert secret_pw.encode("utf-8") not in raw_bytes
    assert b"tok1" not in raw_bytes

    loaded = load_session(conn, 1, cipher=cipher)
    assert loaded == {"oauth1": "tok1", "oauth2": "tok2"}

    restored = restore_authenticated_client(
        conn,
        1,
        cipher=cipher,
        client_factory=lambda **kw: _FakeGarminClient(**kw),
    )
    assert restored.session_data["oauth1"] == "tok1"


def test_mfa_login_flow_and_attempt_limit(conn, cipher: GarminCipher):
    outcome = start_login(
        conn,
        1,
        email="athlete@example.com",
        secret="pw",
        cipher=cipher,
        client_factory=lambda **kw: _FakeGarminClient(needs_mfa=True, **kw),
    )
    assert outcome.status == "mfa_required"
    assert outcome.account.session_status == "mfa_pending"

    with pytest.raises(GarminAuthError):
        submit_mfa_code(conn, 1, mfa_code="000000", cipher=cipher)

    done = submit_mfa_code(conn, 1, mfa_code="123456", cipher=cipher)
    assert done.status == "connected"
    assert done.account.is_connected

    disconnect_session(conn, 1)
    state = get_account_state(conn, 1)
    assert not state.is_connected
    assert load_session(conn, 1, cipher=cipher) is None


def test_online_sync_populates_daily_and_activities_and_respects_source_priority(
    conn, tmp_path: Path, cipher: GarminCipher
):
    cfg = GarminConfig.from_env(data_dir=tmp_path / "garmin_data")
    cfg.ensure_dirs()
    raw_store = RawStore(cfg.raw_dir)

    start_login(
        conn,
        1,
        email="user@example.com",
        secret="pw",
        cipher=cipher,
        client_factory=lambda **kw: _FakeGarminClient(**kw),
    )

    # Seed a manual weight entry and a full_export HRV entry on 2026-10-10
    upsert_daily(
        conn,
        {"user_id": 1, "date": "2026-10-10", "weight_kg": 80.5},
        source="manual",
    )
    upsert_daily(
        conn,
        {"user_id": 1, "date": "2026-10-10", "hrv": 45},
        source="full_export",
    )

    res = sync_online_days(
        conn,
        1,
        days=2,
        end_date="2026-10-10",
        config=cfg,
        raw_store=raw_store,
        cipher=cipher,
        client=_FakeGarminClient(),
        sleep_fn=lambda _: None,
    )
    assert res.status == "ok"
    assert res.daily_upserted == 2
    assert res.activities_upserted == 1

    day_row = get_daily(conn, 1, "2026-10-10")
    assert day_row is not None
    # Online priority (3) overwrites full_export (1)
    assert day_row["hrv"] == 64
    assert day_row["sleep_hours"] == 7.5
    assert day_row["readiness_score"] == 79
    # Online priority (3) does NOT overwrite manual (4)
    assert day_row["weight_kg"] == 80.5

    # Immediate repeat sync without force is blocked by cooldown
    with pytest.raises(GarminRateLimitError):
        sync_online_days(
            conn,
            1,
            days=1,
            end_date="2026-10-10",
            config=cfg,
            raw_store=raw_store,
            cipher=cipher,
            client=_FakeGarminClient(),
            sleep_fn=lambda _: None,
        )


def test_three_rate_limit_errors_pause_online_session(
    conn, tmp_path: Path, cipher: GarminCipher
):
    cfg = GarminConfig.from_env(data_dir=tmp_path / "garmin_data")
    cfg.ensure_dirs()
    raw_store = RawStore(cfg.raw_dir)
    start_login(
        conn,
        1,
        email="user@example.com",
        secret="pw",
        cipher=cipher,
        client_factory=lambda **kw: _FakeGarminClient(**kw),
    )

    failing_client = _FakeGarminClient(fail_exc=RuntimeError("HTTP 429 Too Many Requests"))
    for _ in range(3):
        with pytest.raises(GarminRateLimitError):
            sync_online_days(
                conn,
                1,
                days=1,
                end_date="2026-10-10",
                config=cfg,
                raw_store=raw_store,
                cipher=cipher,
                client=failing_client,
                sleep_fn=lambda _: None,
                force=True,
            )

    state = get_account_state(conn, 1)
    assert state.session_status == "rate_limited"
    assert state.failed_fetch_attempts == 3
