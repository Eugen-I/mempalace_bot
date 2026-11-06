"""Compatibility exports for Garmin contracts.

The canonical models live in :mod:`services.garmin.models`.  This module keeps
the historical import path working while removing the old password/cookie
fields: only an encrypted session token may ever be persisted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from services.garmin.models import (
    AdaptationLogEntry,
    AvailabilitySlot,
    Checkin,
    DeltaMetric,
    DeltaReport,
    Event,
    MedicationEntry,
    PlanSession,
    PlanWeek,
    SafetyFlag,
    SessionStructure,
    TrainingPlan,
    UserProfile,
)


class GarminSessionState(str):
    """Garmin session lifecycle states."""

    DISCONNECTED = "disconnected"
    AWAITING_EMAIL_CODE = "awaiting_email_code"
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"
    RATE_LIMITED = "rate_limited"
    PARTIAL_ACCESS = "partial_access"


class GarminAccountRecord(BaseModel):
    """Persistent Garmin account record without credentials.

    Passwords are never stored.  ``encrypted_session_json`` is the only
    persisted authentication material and must be produced by
    :class:`services.garmin.crypto.GarminCipher`.
    """

    user_id: int
    garmin_email: str = ""
    encrypted_session_json: str | None = None
    account_timezone: str | None = None
    last_login_at: str | None = None
    last_sync_at: str | None = None
    session_status: str = GarminSessionState.DISCONNECTED
    session_state_updated_at: str | None = None
    last_auth_error: str | None = None
    failed_auth_attempts: int = 0
    failed_fetch_attempts: int = 0


class GarminJobState(str):
    """Garmin analysis job states."""

    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_AUTH = "waiting_auth"
    COMPLETED = "completed"
    PARTIAL_COMPLETED = "partial_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


class GarminJobLock(BaseModel):
    """Active Garmin analysis job lock."""

    user_id: int
    analysis_type: str
    job_id: str
    state: str = GarminJobState.RUNNING
    started_at: float = Field(default_factory=lambda: datetime.now(UTC).timestamp())
    updated_at: float = Field(default_factory=lambda: datetime.now(UTC).timestamp())
    error_text: str | None = None


class GarminCacheSnapshot(BaseModel):
    """Cached Garmin data snapshot."""

    user_id: int
    snapshot_type: str
    snapshot_date: str
    payload_json: str
    created_at: str
    expires_at: str


class GarminAnalysisResult(BaseModel):
    """Result of Garmin analysis sent to the local LLM."""

    payload: Any
    prompt: str


__all__ = [
    "AdaptationLogEntry",
    "AvailabilitySlot",
    "Checkin",
    "DeltaMetric",
    "DeltaReport",
    "Event",
    "GarminAccountRecord",
    "GarminAnalysisResult",
    "GarminCacheSnapshot",
    "GarminJobLock",
    "GarminJobState",
    "GarminSessionState",
    "MedicationEntry",
    "PlanSession",
    "PlanWeek",
    "SafetyFlag",
    "SessionStructure",
    "TrainingPlan",
    "UserProfile",
]
