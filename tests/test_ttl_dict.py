"""Unit tests for services.ttl_dict (dict with per-key expiry)."""

import time

import pytest

from services.ttl_dict import TtlDict


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


def test_set_get_roundtrip():
    d = TtlDict(ttl=100)
    d["a"] = 1
    assert d["a"] == 1
    assert d.get("a") == 1
    assert "a" in d


def test_expired_key_removed():
    clock = _FakeClock()
    orig = time.monotonic
    time.monotonic = clock
    try:
        d = TtlDict(ttl=10)
        d["a"] = 1
        clock.now += 20
        with pytest.raises(KeyError):
            d["a"]
    finally:
        time.monotonic = orig


def test_get_expired_returns_default():
    clock = _FakeClock()
    orig = time.monotonic
    time.monotonic = clock
    try:
        d = TtlDict(ttl=10)
        d["a"] = 1
        clock.now += 20
        assert d.get("a") is None
        assert d.get("a", "def") == "def"
    finally:
        time.monotonic = orig


def test_contains_expired_false():
    clock = _FakeClock()
    orig = time.monotonic
    time.monotonic = clock
    try:
        d = TtlDict(ttl=10)
        d["a"] = 1
        clock.now += 20
        assert "a" not in d
    finally:
        time.monotonic = orig


def test_not_expired_from_different_clock():
    """Если вручную переопределить time — поведение можно проконтролировать."""
    clock = _FakeClock()
    orig = time.monotonic
    time.monotonic = clock
    try:
        d = TtlDict(ttl=5)
        d["k"] = "v"
        assert d.get("k") == "v"
        clock.now += 6
        assert d.get("k") is None
    finally:
        time.monotonic = orig


def test_expired_key_removed_from_storage():
    clock = _FakeClock()
    orig = time.monotonic
    time.monotonic = clock
    try:
        d = TtlDict(ttl=5)
        d["k"] = "v"
        clock.now += 6
        d.get("k")
        assert "k" not in d._expires
        assert d.peek("k") if hasattr(d, "peek") else True
        with pytest.raises(KeyError):
            d["k"]
    finally:
        time.monotonic = orig


def test_pop_returns_and_removes():
    d = TtlDict(ttl=100)
    d["a"] = 1
    assert d.pop("a") == 1
    assert "a" not in d
    assert d.pop("a", "def") == "def"


def test_pop_expired_returns_default():
    clock = _FakeClock()
    orig = time.monotonic
    time.monotonic = clock
    try:
        d = TtlDict(ttl=5)
        d["a"] = 1
        clock.now += 6
        assert d.pop("a", "def") == "def"
    finally:
        time.monotonic = orig


def test_len_and_iteration():
    d = TtlDict(ttl=100)
    d["a"] = 1
    d["b"] = 2
    assert len(d) == 2
    assert set(d.keys()) == {"a", "b"}


def test_default_ttl_is_86400():
    d = TtlDict()
    assert d._ttl == 86400
