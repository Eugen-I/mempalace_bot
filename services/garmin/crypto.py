"""Encryption helpers for Garmin session tokens and private profile data.

Production keys live in the macOS Keychain.  ``GARMIN_ENCRYPTION_KEY`` is an
explicit test/CI escape hatch; there is intentionally no plaintext file
fallback.  The Fernet key is never logged.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .errors import GarminCryptoError

KEYCHAIN_SERVICE = "mempalace-garmin"
KEYCHAIN_ACCOUNT = "garmin-fernet"
ENV_KEY = "GARMIN_ENCRYPTION_KEY"


def _validate_key(key: str | bytes) -> bytes:
    raw = key.encode("utf-8") if isinstance(key, str) else key
    raw = raw.strip()
    if not raw:
        raise GarminCryptoError("empty encryption key")
    try:
        Fernet(raw)
    except (ValueError, TypeError) as exc:
        raise GarminCryptoError("invalid Fernet key") from exc
    return raw


def _run_security(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # nosec
            ["security", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GarminCryptoError(
            "macOS Keychain tool 'security' is not available"
        ) from exc


def keychain_get() -> str | None:
    """Read the Fernet key from the macOS Keychain, if present."""
    if sys.platform != "darwin":
        return None
    result = _run_security(
        [
            "find-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            KEYCHAIN_ACCOUNT,
            "-w",
        ]
    )
    if result.returncode == 0:
        return result.stdout.strip() or None
    # 44 is security's "item not found" status on macOS.
    if result.returncode == 44:
        return None
    raise GarminCryptoError("cannot read Garmin key from Keychain")


def keychain_set(key: str) -> None:
    """Store/replace the Fernet key in the macOS Keychain."""
    if sys.platform != "darwin":
        raise GarminCryptoError("Keychain is only available on macOS")
    result = _run_security(
        [
            "add-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            KEYCHAIN_ACCOUNT,
            "-w",
            key,
            "-U",
        ]
    )
    if result.returncode != 0:
        raise GarminCryptoError("cannot store Garmin key in Keychain")


def keychain_delete() -> bool:
    """Delete the Keychain item; return True when something was removed."""
    if sys.platform != "darwin":
        return False
    result = _run_security(
        [
            "delete-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            KEYCHAIN_ACCOUNT,
        ]
    )
    return result.returncode == 0


def resolve_key() -> bytes:
    """Resolve a Fernet key from env or Keychain, creating one if needed."""
    env_key = (os.getenv(ENV_KEY) or "").strip()
    if env_key:
        return _validate_key(env_key)

    if sys.platform != "darwin":
        raise GarminCryptoError(
            "GARMIN_ENCRYPTION_KEY is required outside macOS (tests/CI only)"
        )

    existing = keychain_get()
    if existing:
        return _validate_key(existing)

    generated = Fernet.generate_key()
    keychain_set(generated.decode("ascii"))
    return generated


class GarminCipher:
    """Small Fernet wrapper with JSON/text helpers."""

    def __init__(self, key: str | bytes | None = None) -> None:
        self._key = _validate_key(key) if key is not None else resolve_key()
        self._fernet = Fernet(self._key)

    def encrypt_bytes(self, value: bytes) -> str:
        return self._fernet.encrypt(value).decode("ascii")

    def decrypt_bytes(self, token: str | bytes) -> bytes:
        raw = token.encode("ascii") if isinstance(token, str) else token
        try:
            return self._fernet.decrypt(raw)
        except InvalidToken as exc:
            raise GarminCryptoError("invalid or tampered ciphertext") from exc

    def encrypt_text(self, value: str) -> str:
        return self.encrypt_bytes(value.encode("utf-8"))

    def decrypt_text(self, token: str | bytes) -> str:
        try:
            return self.decrypt_bytes(token).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GarminCryptoError("decrypted payload is not UTF-8") from exc

    def encrypt_json(self, value: Any) -> str:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self.encrypt_text(payload)

    def decrypt_json(self, token: str | bytes) -> Any:
        try:
            return json.loads(self.decrypt_text(token))
        except json.JSONDecodeError as exc:
            raise GarminCryptoError("decrypted payload is not valid JSON") from exc

    @property
    def key(self) -> bytes:
        """Return the key for rotation/re-encryption only; never log it."""
        return self._key
