"""Encrypted Garmin Connect session and MFA state storage in SQLite.

All tokens and intermediate 2FA states are encrypted via ``GarminCipher``
(macOS Keychain or ``GARMIN_ENCRYPTION_KEY`` in tests).  Plaintext passwords
are never stored anywhere.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .crypto import GarminCipher
from .errors import GarminAuthError, GarminCryptoError

MFA_TTL_SECONDS = 600
MAX_MFA_ATTEMPTS = 3
MAX_RATE_LIMIT_STRIKES = 3


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def mask_email(email: str | None) -> str:
    """Return a privacy-safe masked email (e.g. 'u***@example.com')."""
    raw = (email or "").strip()
    if not raw or "@" not in raw:
        return "—"
    local, domain = raw.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "***"
    return f"{masked_local}@{domain}"


@dataclass(frozen=True)
class AccountState:
    user_id: int
    garmin_email: str = ""
    account_timezone: str | None = None
    last_login_at: str | None = None
    last_sync_at: str | None = None
    session_status: str = "disconnected"
    session_state_updated_at: str | None = None
    last_auth_error: str | None = None
    failed_auth_attempts: int = 0
    failed_fetch_attempts: int = 0
    has_session: bool = False

    @property
    def masked_email(self) -> str:
        return mask_email(self.garmin_email)

    @property
    def is_connected(self) -> bool:
        return self.session_status == "connected" and self.has_session


def get_account_state(conn: sqlite3.Connection, user_id: int) -> AccountState:
    row = conn.execute(
        "SELECT * FROM garmin_accounts WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return AccountState(user_id=int(user_id))
    return AccountState(
        user_id=int(row["user_id"]),
        garmin_email=str(row["garmin_email"] or ""),
        account_timezone=(
            str(row["account_timezone"]) if row["account_timezone"] else None
        ),
        last_login_at=str(row["last_login_at"]) if row["last_login_at"] else None,
        last_sync_at=str(row["last_sync_at"]) if row["last_sync_at"] else None,
        session_status=str(row["session_status"] or "disconnected"),
        session_state_updated_at=(
            str(row["session_state_updated_at"])
            if row["session_state_updated_at"]
            else None
        ),
        last_auth_error=(
            str(row["last_auth_error"]) if row["last_auth_error"] else None
        ),
        failed_auth_attempts=int(row["failed_auth_attempts"] or 0),
        failed_fetch_attempts=int(row["failed_fetch_attempts"] or 0),
        has_session=bool(row["encrypted_session_json"]),
    )


def save_session(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    session_payload: dict[str, Any],
    email: str | None = None,
    timezone: str | None = None,
    cipher: GarminCipher | None = None,
) -> AccountState:
    """Encrypt and store OAuth1/OAuth2 session tokens in ``garmin_accounts``."""
    active_cipher = cipher or GarminCipher()
    blob = active_cipher.encrypt_json(session_payload).encode("ascii")
    now = _utcnow_iso()
    existing = get_account_state(conn, user_id)
    email_val = email if email is not None else existing.garmin_email
    tz_val = timezone if timezone is not None else existing.account_timezone

    conn.execute(
        "INSERT INTO garmin_accounts ("
        " user_id, garmin_email, encrypted_session_json, account_timezone,"
        " last_login_at, last_sync_at, session_status, session_state_updated_at,"
        " last_auth_error, failed_auth_attempts, failed_fetch_attempts,"
        " created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, 'connected', ?, NULL, 0, 0, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        " garmin_email = excluded.garmin_email,"
        " encrypted_session_json = excluded.encrypted_session_json,"
        " account_timezone = COALESCE(excluded.account_timezone, garmin_accounts.account_timezone),"
        " last_login_at = excluded.last_login_at,"
        " session_status = 'connected',"
        " session_state_updated_at = excluded.session_state_updated_at,"
        " last_auth_error = NULL,"
        " failed_auth_attempts = 0,"
        " failed_fetch_attempts = 0,"
        " updated_at = excluded.updated_at",
        (
            int(user_id),
            email_val,
            blob,
            tz_val,
            now,
            existing.last_sync_at,
            now,
            now,
            now,
        ),
    )
    clear_mfa_state(conn, user_id, commit=False)
    conn.commit()
    return get_account_state(conn, user_id)


def load_session(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cipher: GarminCipher | None = None,
) -> dict[str, Any] | None:
    """Decrypt and return the stored session dict, or None if not connected."""
    row = conn.execute(
        "SELECT encrypted_session_json FROM garmin_accounts WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None or not row["encrypted_session_json"]:
        return None
    active_cipher = cipher or GarminCipher()
    raw_blob = row["encrypted_session_json"]
    token = (
        bytes(raw_blob).decode("ascii")
        if isinstance(raw_blob, (bytes, bytearray, memoryview))
        else str(raw_blob)
    )
    data = active_cipher.decrypt_json(token)
    if not isinstance(data, dict):
        raise GarminCryptoError("stored Garmin session is not a JSON object")
    return data


def record_auth_failure(
    conn: sqlite3.Connection,
    user_id: int,
    error_message: str,
    *,
    status: str = "auth_error",
) -> AccountState:
    now = _utcnow_iso()
    safe_error = (error_message or "ошибка авторизации")[:240]
    conn.execute(
        "INSERT INTO garmin_accounts ("
        " user_id, garmin_email, session_status, session_state_updated_at,"
        " last_auth_error, failed_auth_attempts, failed_fetch_attempts,"
        " created_at, updated_at"
        ") VALUES (?, '', ?, ?, ?, 1, 0, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        " session_status = excluded.session_status,"
        " session_state_updated_at = excluded.session_state_updated_at,"
        " last_auth_error = excluded.last_auth_error,"
        " failed_auth_attempts = garmin_accounts.failed_auth_attempts + 1,"
        " updated_at = excluded.updated_at",
        (int(user_id), status, now, safe_error, now, now),
    )
    conn.commit()
    return get_account_state(conn, user_id)


def record_fetch_failure(
    conn: sqlite3.Connection,
    user_id: int,
    error_message: str,
    *,
    rate_limited: bool = False,
) -> AccountState:
    now = _utcnow_iso()
    state = get_account_state(conn, user_id)
    new_strikes = state.failed_fetch_attempts + 1
    new_status = state.session_status
    if rate_limited and new_strikes >= MAX_RATE_LIMIT_STRIKES:
        new_status = "rate_limited"
    safe_error = (error_message or "ошибка синхронизации")[:240]
    conn.execute(
        "INSERT INTO garmin_accounts ("
        " user_id, garmin_email, session_status, session_state_updated_at,"
        " last_auth_error, failed_auth_attempts, failed_fetch_attempts,"
        " created_at, updated_at"
        ") VALUES (?, '', ?, ?, ?, 0, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        " session_status = excluded.session_status,"
        " session_state_updated_at = excluded.session_state_updated_at,"
        " last_auth_error = excluded.last_auth_error,"
        " failed_fetch_attempts = excluded.failed_fetch_attempts,"
        " updated_at = excluded.updated_at",
        (int(user_id), new_status, now, safe_error, new_strikes, now, now),
    )
    conn.commit()
    return get_account_state(conn, user_id)


def record_sync_success(conn: sqlite3.Connection, user_id: int) -> AccountState:
    now = _utcnow_iso()
    conn.execute(
        "UPDATE garmin_accounts SET"
        " last_sync_at = ?,"
        " failed_fetch_attempts = 0,"
        " last_auth_error = NULL,"
        " updated_at = ?"
        " WHERE user_id = ?",
        (now, now, int(user_id)),
    )
    conn.commit()
    return get_account_state(conn, user_id)


def disconnect_session(conn: sqlite3.Connection, user_id: int) -> AccountState:
    """Wipe encrypted session tokens and pending MFA state for ``user_id``."""
    now = _utcnow_iso()
    conn.execute(
        "INSERT INTO garmin_accounts ("
        " user_id, garmin_email, encrypted_session_json, session_status,"
        " session_state_updated_at, last_auth_error, failed_auth_attempts,"
        " failed_fetch_attempts, created_at, updated_at"
        ") VALUES (?, '', NULL, 'disconnected', ?, NULL, 0, 0, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        " encrypted_session_json = NULL,"
        " session_status = 'disconnected',"
        " session_state_updated_at = excluded.session_state_updated_at,"
        " last_auth_error = NULL,"
        " failed_auth_attempts = 0,"
        " failed_fetch_attempts = 0,"
        " updated_at = excluded.updated_at",
        (int(user_id), now, now, now),
    )
    clear_mfa_state(conn, user_id, commit=False)
    conn.commit()
    return get_account_state(conn, user_id)


def save_mfa_state(
    conn: sqlite3.Connection,
    user_id: int,
    state_payload: dict[str, Any],
    *,
    email: str = "",
    ttl_seconds: int = MFA_TTL_SECONDS,
    cipher: GarminCipher | None = None,
) -> None:
    """Store encrypted 2FA client state with a strict TTL (default 10 minutes)."""
    active_cipher = cipher or GarminCipher()
    blob = active_cipher.encrypt_json(state_payload).encode("ascii")
    now_dt = _utcnow()
    now = now_dt.isoformat()
    expires = (now_dt + timedelta(seconds=max(ttl_seconds, 60))).isoformat()

    conn.execute(
        "INSERT INTO garmin_mfa_state (user_id, state_blob, expires_at, attempts, created_at)"
        " VALUES (?, ?, ?, 0, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        " state_blob = excluded.state_blob,"
        " expires_at = excluded.expires_at,"
        " attempts = 0,"
        " created_at = excluded.created_at",
        (int(user_id), blob, expires, now),
    )
    conn.execute(
        "INSERT INTO garmin_accounts ("
        " user_id, garmin_email, session_status, session_state_updated_at,"
        " created_at, updated_at"
        ") VALUES (?, ?, 'mfa_pending', ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        " garmin_email = CASE WHEN excluded.garmin_email != '' THEN excluded.garmin_email"
        " ELSE garmin_accounts.garmin_email END,"
        " session_status = 'mfa_pending',"
        " session_state_updated_at = excluded.session_state_updated_at,"
        " updated_at = excluded.updated_at",
        (int(user_id), email, now, now, now),
    )
    conn.commit()


def load_mfa_state(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cipher: GarminCipher | None = None,
) -> dict[str, Any] | None:
    """Load pending MFA state if not expired and attempts < MAX_MFA_ATTEMPTS."""
    row = conn.execute(
        "SELECT state_blob, expires_at, attempts FROM garmin_mfa_state WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    attempts = int(row["attempts"] or 0)
    if attempts >= MAX_MFA_ATTEMPTS:
        clear_mfa_state(conn, user_id)
        raise GarminAuthError("Превышено число попыток ввода 2FA-кода. Начните вход заново.")
    try:
        expires_dt = datetime.fromisoformat(str(row["expires_at"]))
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=UTC)
    except ValueError:
        clear_mfa_state(conn, user_id)
        return None
    if _utcnow() > expires_dt:
        clear_mfa_state(conn, user_id)
        raise GarminAuthError("Срок действия 2FA-сессии истёк (10 мин). Начните вход заново.")

    active_cipher = cipher or GarminCipher()
    raw_blob = row["state_blob"]
    token = (
        bytes(raw_blob).decode("ascii")
        if isinstance(raw_blob, (bytes, bytearray, memoryview))
        else str(raw_blob)
    )
    data = active_cipher.decrypt_json(token)
    if not isinstance(data, dict):
        clear_mfa_state(conn, user_id)
        raise GarminCryptoError("invalid MFA state payload")
    return data


def increment_mfa_attempts(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT attempts FROM garmin_mfa_state WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return 0
    new_attempts = int(row["attempts"] or 0) + 1
    if new_attempts >= MAX_MFA_ATTEMPTS:
        clear_mfa_state(conn, user_id)
    else:
        conn.execute(
            "UPDATE garmin_mfa_state SET attempts = ? WHERE user_id = ?",
            (new_attempts, int(user_id)),
        )
        conn.commit()
    return new_attempts


def clear_mfa_state(
    conn: sqlite3.Connection, user_id: int, *, commit: bool = True
) -> None:
    conn.execute("DELETE FROM garmin_mfa_state WHERE user_id = ?", (int(user_id),))
    if commit:
        conn.commit()
