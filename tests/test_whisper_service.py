"""Тесты services/whisper_service.py — singleton сервис Whisper.

Покрытие: кэш модели, prewarm, границы размеров модели.
"""
import sys
import types

import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    import services.whisper_service as ws

    ws._load_model.cache_clear()
    yield
    ws._load_model.cache_clear()


def test_get_whisper_caches_model(monkeypatch):
    import sys

    import services.whisper_service as ws

    class FakeWhisper:
        def __init__(self, size, device, compute_type):
            self.size = size
            self.device = device
            self.compute_type = compute_type

    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = FakeWhisper
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)

    model1 = ws.get_whisper("base")
    model2 = ws.get_whisper("base")
    assert model1 is model2
    assert isinstance(model1, FakeWhisper)


def test_get_whisper_different_sizes_separate(monkeypatch):
    import services.whisper_service as ws

    class FakeWhisper:
        def __init__(self, size, device, compute_type):
            self.size = size

    import types

    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = FakeWhisper
    monkeypatch.setitem(
        __import__("sys").modules, "faster_whisper", fake_mod
    )

    base = ws.get_whisper("base")
    small = ws.get_whisper("small")
    assert base is not small
    assert base.size == "base"
    assert small.size == "small"


def test_prewarm_loads_base(monkeypatch):
    import services.whisper_service as ws

    loaded = []

    class FakeWhisper:
        def __init__(self, size, device, compute_type):
            loaded.append(size)

    import types

    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = FakeWhisper
    monkeypatch.setitem(
        __import__("sys").modules, "faster_whisper", fake_mod
    )

    ws.prewarm()
    assert loaded == ["base"]


def test_prewarm_idempotent(monkeypatch):
    import services.whisper_service as ws

    ws._load_model.cache_clear()
    ws.prewarm()
    ws.prewarm()
    assert ws._load_model.cache_info().currsize == 1
