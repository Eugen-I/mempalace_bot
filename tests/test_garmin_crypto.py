"""Tests for services.garmin.crypto."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from services.garmin.crypto import GarminCipher, resolve_key
from services.garmin.errors import GarminCryptoError


@pytest.fixture
def key() -> str:
    return Fernet.generate_key().decode("ascii")


def test_roundtrip_text(key):
    cipher = GarminCipher(key)
    token = cipher.encrypt_text("секрет")
    assert token != "секрет"
    assert cipher.decrypt_text(token) == "секрет"


def test_roundtrip_json(key):
    cipher = GarminCipher(key)
    value = {"email": "a@example.com", "meds": ["миртазапин"]}
    token = cipher.encrypt_json(value)
    assert cipher.decrypt_json(token) == value


def test_roundtrip_bytes(key):
    cipher = GarminCipher(key)
    token = cipher.encrypt_bytes(b"\x00\x01\x02")
    assert cipher.decrypt_bytes(token) == b"\x00\x01\x02"


def test_wrong_key_raises(key):
    token = GarminCipher(key).encrypt_text("x")
    other = GarminCipher(Fernet.generate_key().decode("ascii"))
    with pytest.raises(GarminCryptoError):
        other.decrypt_text(token)


def test_tampered_token_raises(key):
    cipher = GarminCipher(key)
    token = cipher.encrypt_text("x")
    with pytest.raises(GarminCryptoError):
        cipher.decrypt_text(token[:-2] + "AA")


def test_invalid_key_raises():
    with pytest.raises(GarminCryptoError):
        GarminCipher("not-a-key")


def test_resolve_key_from_env(monkeypatch, key):
    monkeypatch.setenv("GARMIN_ENCRYPTION_KEY", key)
    assert resolve_key() == key.encode("ascii")


def test_resolve_key_rejects_bad_env(monkeypatch):
    monkeypatch.setenv("GARMIN_ENCRYPTION_KEY", "bad")
    with pytest.raises(GarminCryptoError):
        resolve_key()


def test_json_is_deterministic(key):
    cipher = GarminCipher(key)
    a = cipher.encrypt_json({"b": 2, "a": 1})
    b = cipher.encrypt_json({"a": 1, "b": 2})
    # Fernet includes a random IV, so tokens differ; plaintext must match.
    assert cipher.decrypt_json(a) == cipher.decrypt_json(b) == {"a": 1, "b": 2}
