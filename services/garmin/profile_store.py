"""Encrypted profile, check-ins and events for the Garmin coach.

The profile contains health context, so it is encrypted with the same Fernet
key used for Garmin session tokens.  Nothing here is sent to a cloud service.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from .crypto import GarminCipher
from .errors import GarminCryptoError, GarminDatabaseError
from .models import Checkin, Event, UserProfile


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class StoredProfile:
    user_id: int
    profile: UserProfile
    version: int
    completeness: str
    updated_at: str


def save_profile(
    conn: sqlite3.Connection,
    user_id: int,
    profile: UserProfile,
    *,
    cipher: GarminCipher | None = None,
) -> StoredProfile:
    """Encrypt and upsert the profile, incrementing its version."""
    crypto = cipher or GarminCipher()
    row = conn.execute(
        "SELECT version FROM garmin_profile WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    version = int(row["version"]) + 1 if row is not None else max(1, profile.version)
    stored = profile.model_copy(update={"version": version})
    try:
        blob = crypto.encrypt_json(stored.model_dump(mode="json"))
        now = _utcnow()
        conn.execute(
            "INSERT INTO garmin_profile"
            " (user_id, profile_blob, version, completeness, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET"
            " profile_blob = excluded.profile_blob,"
            " version = excluded.version,"
            " completeness = excluded.completeness,"
            " updated_at = excluded.updated_at",
            (int(user_id), blob, version, stored.completeness, now),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - normalize storage failures
        conn.rollback()
        if isinstance(exc, (GarminCryptoError, GarminDatabaseError)):
            raise
        raise GarminDatabaseError("cannot save Garmin profile") from exc
    return StoredProfile(
        user_id=int(user_id),
        profile=stored,
        version=version,
        completeness=stored.completeness,
        updated_at=now,
    )


def load_profile(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cipher: GarminCipher | None = None,
) -> StoredProfile | None:
    row = conn.execute(
        "SELECT profile_blob, version, completeness, updated_at"
        " FROM garmin_profile WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    crypto = cipher or GarminCipher()
    try:
        payload = crypto.decrypt_json(row["profile_blob"])
        profile = UserProfile.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - corrupt blobs must not crash UI
        raise GarminCryptoError("cannot read Garmin profile") from exc
    return StoredProfile(
        user_id=int(user_id),
        profile=profile,
        version=int(row["version"]),
        completeness=str(row["completeness"]),
        updated_at=str(row["updated_at"]),
    )


def save_checkin(conn: sqlite3.Connection, user_id: int, checkin: Checkin) -> None:
    adherence = None if checkin.adherence is None else int(checkin.adherence)
    conn.execute(
        "INSERT INTO garmin_checkins"
        " (user_id, date, kind, sleep_h, sleep_quality, hrv, rhr, soreness,"
        "  pain_score, pain_location, mood, stress, adherence, notes, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id, date, kind) DO UPDATE SET"
        " sleep_h = excluded.sleep_h,"
        " sleep_quality = excluded.sleep_quality,"
        " hrv = excluded.hrv,"
        " rhr = excluded.rhr,"
        " soreness = excluded.soreness,"
        " pain_score = excluded.pain_score,"
        " pain_location = excluded.pain_location,"
        " mood = excluded.mood,"
        " stress = excluded.stress,"
        " adherence = excluded.adherence,"
        " notes = excluded.notes",
        (
            int(user_id),
            checkin.date,
            checkin.kind,
            checkin.sleep_h,
            checkin.sleep_quality,
            checkin.hrv,
            checkin.rhr,
            checkin.soreness,
            checkin.pain_score,
            checkin.pain_location,
            checkin.mood,
            checkin.stress,
            adherence,
            checkin.notes,
            _utcnow(),
        ),
    )
    conn.commit()


def recent_checkins(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    limit: int = 14,
) -> list[Checkin]:
    rows = conn.execute(
        "SELECT * FROM garmin_checkins WHERE user_id = ?"
        " ORDER BY date DESC, created_at DESC LIMIT ?",
        (int(user_id), int(limit)),
    ).fetchall()
    result: list[Checkin] = []
    for row in rows:
        adherence = row["adherence"]
        result.append(
            Checkin(
                date=str(row["date"]),
                kind=str(row["kind"]),
                sleep_h=row["sleep_h"],
                sleep_quality=row["sleep_quality"],
                hrv=row["hrv"],
                rhr=row["rhr"],
                soreness=row["soreness"],
                pain_score=row["pain_score"],
                pain_location=row["pain_location"],
                mood=row["mood"],
                stress=row["stress"],
                adherence=None if adherence is None else bool(adherence),
                notes=row["notes"],
            )
        )
    return result


def save_event(conn: sqlite3.Connection, user_id: int, event: Event) -> int:
    cursor = conn.execute(
        "INSERT INTO garmin_events"
        " (user_id, date, kind, title, notes, severity, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            int(user_id),
            event.date,
            event.kind,
            event.title,
            event.notes,
            event.severity,
            _utcnow(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def resolve_illness_events(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    resolved_date: str | None = None,
) -> int:
    """Mark active illness events as recovered ('info') while preserving history.

    Keeping the event row with ``severity='info'`` lets analytics and the AI
    coach still correlate historical HRV/RHR/sleep deviations with the illness
    dates, while unblocking daily readiness and enabling a gentle return plan.
    """
    stamp = resolved_date or _utcnow()[:10]
    rows = conn.execute(
        "SELECT id, title, notes FROM garmin_events"
        " WHERE user_id = ? AND kind = 'illness'"
        " AND severity IN ('critical', 'warning')",
        (int(user_id),),
    ).fetchall()
    if not rows:
        return 0
    for row in rows:
        existing_notes = str(row["notes"] or "").strip()
        marker = f"выздоровел {stamp}"
        if marker not in existing_notes:
            notes = f"{existing_notes}; {marker}".strip("; ")
        else:
            notes = existing_notes
        conn.execute(
            "UPDATE garmin_events SET severity = 'info', notes = ? WHERE id = ?",
            (notes[:500], int(row["id"])),
        )
    conn.commit()
    return len(rows)


def delete_last_event(conn: sqlite3.Connection, user_id: int) -> bool:
    """Delete the most recent event for a user; return True if one was deleted."""
    row = conn.execute(
        "SELECT id FROM garmin_events WHERE user_id = ?"
        " ORDER BY date DESC, id DESC LIMIT 1",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return False
    conn.execute(
        "DELETE FROM garmin_events WHERE id = ? AND user_id = ?",
        (int(row["id"]), int(user_id)),
    )
    conn.commit()
    return True
