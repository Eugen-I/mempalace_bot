"""Unit tests for config.py — токен, .env-пути, валидация, декораторы доступа."""

import asyncio
import importlib
import os

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


# ─── token resolution ───


def test_resolve_api_token_strips_env_value():
    assert config._resolve_api_token("  real-token  ") == "real-token"


def test_resolve_api_token_no_fallback_outside_test_environment():
    assert config._resolve_api_token("", test_environment=False) == ""


def test_resolve_api_token_fallback_in_test_environment():
    assert config._resolve_api_token("", test_environment=True) == "test-token"


def test_resolve_api_token_uses_detected_test_environment(monkeypatch):
    monkeypatch.setattr(config, "_is_test_environment", lambda: True)
    assert config._resolve_api_token("") == "test-token"


def test_is_test_environment_detects_pytest(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.delenv("MEMPALACE_ALLOW_TEST_TOKEN", raising=False)
    assert config._is_test_environment() is False
    monkeypatch.setenv("PYTEST_VERSION", "8.0")
    assert config._is_test_environment() is True


def test_is_test_environment_detects_explicit_flag(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.setenv("MEMPALACE_ALLOW_TEST_TOKEN", "yes")
    assert config._is_test_environment() is True


# ─── validate_config ───


def test_validate_config_requires_token(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_ID", 4242)
    with pytest.raises(RuntimeError) as exc:
        config.validate_config()
    message = str(exc.value)
    assert "TELEGRAM_BOT_TOKEN" in message
    assert config.PROJECT_ENV_PATH in message
    assert config.LEGACY_ENV_PATH in message


def test_validate_config_rejects_example_token(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "your_telegram_bot_token")
    monkeypatch.setattr(config, "ADMIN_ID", 4242)
    with pytest.raises(RuntimeError, match="пример значения"):
        config.validate_config()


def test_validate_config_rejects_test_token_outside_tests(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "test-token")
    monkeypatch.setattr(config, "ADMIN_ID", 4242)
    monkeypatch.setattr(config, "_is_test_environment", lambda: False)
    with pytest.raises(RuntimeError, match="тестовый fallback"):
        config.validate_config()


def test_validate_config_allows_test_token_in_tests(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "test-token")
    monkeypatch.setattr(config, "ADMIN_ID", 4242)
    monkeypatch.setattr(config, "_is_test_environment", lambda: True)
    config.validate_config()


def test_validate_config_requires_admin(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "123:real-token")
    monkeypatch.setattr(config, "ADMIN_ID", 0)
    with pytest.raises(RuntimeError, match="ADMIN_ID"):
        config.validate_config()


def test_validate_config_accepts_valid_settings(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "123:real-token")
    monkeypatch.setattr(config, "ADMIN_ID", 4242)
    config.validate_config()


# ─── .env paths ───


def test_env_paths_order_root_then_legacy():
    assert config.ENV_PATHS == (
        config.PROJECT_ENV_PATH,
        config.LEGACY_ENV_PATH,
    )
    assert config.PROJECT_ENV_PATH == os.path.join(
        os.path.dirname(os.path.abspath(config.__file__)), ".env",
    )
    assert config.LEGACY_ENV_PATH == os.path.expanduser(
        "~/Documents/mempalace/.env",
    )


def test_load_env_files_root_wins_and_legacy_fills(monkeypatch, tmp_path):
    keys = [
        "MEMPALACE_TEST_SHARED",
        "MEMPALACE_TEST_ROOT_ONLY",
        "MEMPALACE_TEST_LEGACY_ONLY",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)

    root_env = tmp_path / "root.env"
    legacy_env = tmp_path / "legacy.env"
    root_env.write_text(
        "MEMPALACE_TEST_SHARED=root\nMEMPALACE_TEST_ROOT_ONLY=1\n",
        encoding="utf-8",
    )
    legacy_env.write_text(
        "MEMPALACE_TEST_SHARED=legacy\nMEMPALACE_TEST_LEGACY_ONLY=1\n",
        encoding="utf-8",
    )

    loaded = config._load_env_files((str(root_env), str(legacy_env)))

    assert loaded == [str(root_env), str(legacy_env)]
    assert os.environ["MEMPALACE_TEST_SHARED"] == "root"
    assert os.environ["MEMPALACE_TEST_ROOT_ONLY"] == "1"
    assert os.environ["MEMPALACE_TEST_LEGACY_ONLY"] == "1"


def test_load_env_files_respects_existing_environment(monkeypatch, tmp_path):
    key = "MEMPALACE_TEST_ENV_PRIORITY"
    monkeypatch.setenv(key, "from-environment")
    root_env = tmp_path / "root.env"
    legacy_env = tmp_path / "legacy.env"
    root_env.write_text(f"{key}=root\n", encoding="utf-8")
    legacy_env.write_text(f"{key}=legacy\n", encoding="utf-8")

    config._load_env_files((str(root_env), str(legacy_env)))

    assert os.environ[key] == "from-environment"


def test_load_env_files_legacy_only(monkeypatch, tmp_path):
    key = "MEMPALACE_TEST_LEGACY_ONLY_VALUE"
    monkeypatch.delenv(key, raising=False)
    missing_root = tmp_path / "missing.env"
    legacy_env = tmp_path / "legacy.env"
    legacy_env.write_text(f"{key}=legacy\n", encoding="utf-8")

    loaded = config._load_env_files((str(missing_root), str(legacy_env)))

    assert loaded == [str(legacy_env)]
    assert os.environ[key] == "legacy"


def test_load_env_files_warns_when_none_exist(tmp_path, capsys):
    missing_root = tmp_path / "missing-root.env"
    missing_legacy = tmp_path / "missing-legacy.env"

    loaded = config._load_env_files((str(missing_root), str(missing_legacy)))

    assert loaded == []
    output = capsys.readouterr().out
    assert str(missing_root) in output
    assert str(missing_legacy) in output


# ─── DATA_DIR reload-ветки ───


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
