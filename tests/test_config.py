"""Unit tests for config.py — декораторы доступа, get_allowed_ids, reload-ветки."""

import asyncio
import importlib

import pytest

import config


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242):
        self.from_user = FakeUser(uid)
        self.called = False

    async def answer(self, text, show_alert=None):
        self.answered = text


class FakeCallback:
    def __init__(self, uid=4242):
        self.from_user = FakeUser(uid)
        self.answered = None

    async def answer(self, text, show_alert=None):
        self.answered = text


@pytest.fixture(autouse=True)
def _isolated_allowed(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_IDS", {4242, 4243})
    yield


# ─── allowed_only ───


async def _decorated_fn(msg, *args, **kwargs):
    msg.called = True
    return "ok"


def test_allowed_only_blocks_unauthorized():
    wrapped = config.allowed_only(_decorated_fn)
    msg = FakeMessage(uid=1)
    assert asyncio.run(wrapped(msg)) is None
    assert msg.called is False


def test_allowed_only_passes_authorized():
    wrapped = config.allowed_only(_decorated_fn)
    msg = FakeMessage(uid=4242)
    assert asyncio.run(wrapped(msg)) == "ok"
    assert msg.called is True


def test_allowed_only_preserves_wrapped_name():
    wrapped = config.allowed_only(_decorated_fn)
    assert wrapped.__name__ == "_decorated_fn"


# ─── allowed_callback ───


def test_allowed_callback_blocks_unauthorized():
    wrapped = config.allowed_callback(_decorated_fn)
    cb = FakeCallback(uid=1)
    assert asyncio.run(wrapped(cb)) is None
    assert cb.answered == "❌ Нет доступа"


def test_allowed_callback_passes_authorized():
    wrapped = config.allowed_callback(_decorated_fn)
    cb = FakeCallback(uid=4243)
    assert asyncio.run(wrapped(cb)) == "ok"
    assert cb.answered is None


# ─── get_allowed_ids ───


def test_get_allowed_ids_parses_env(monkeypatch):
    monkeypatch.setenv("ADMIN_ID", "10")
    monkeypatch.setenv("ALLOWED_USERS", "1, 2, 3")
    assert config.get_allowed_ids() == {1, 2, 3, 10}


def test_get_allowed_ids_ignores_non_digits(monkeypatch):
    monkeypatch.setenv("ADMIN_ID", "1")
    monkeypatch.setenv("ALLOWED_USERS", "5, ,x7")
    assert config.get_allowed_ids() == {1, 5}


# ─── reload-ветки (fallback token вне pytest) ───


def test_config_api_token_fallback_outside_pytest(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    importlib.reload(config)
    assert config.API_TOKEN == "test-token"
    assert "fallback" in capsys.readouterr().out


def test_config_api_token_fallback_in_pytest(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_config.py::x")
    importlib.reload(config)
    assert config.API_TOKEN == "test-token"
    assert "для тестов" in capsys.readouterr().out


def test_config_data_dir_without_equals(monkeypatch):
    monkeypatch.setenv("MEMPALACE_DATA_DIR", "~/configtest_dir")
    monkeypatch.setattr(config.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(config.os.path, "expanduser", lambda p: p)
    importlib.reload(config)
    assert config.DATA_DIR == "~/configtest_dir"


def test_config_cleans_key_value_data_dir(monkeypatch):
    monkeypatch.setenv("MEMPALACE_DATA_DIR", "PATH=/tmp/configtest")
    monkeypatch.setattr(config.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(config.os.path, "expanduser", lambda p: p)
    importlib.reload(config)
    assert config.DATA_DIR == "/tmp/configtest"
