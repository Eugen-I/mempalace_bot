"""Unit-тесты для services.agent_settings — per-user настройки агента.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
"""

import json

import pytest

from services import agent_settings as ag


@pytest.fixture(autouse=True)
def settings_file(tmp_path, monkeypatch):
    """Подменяет путь файла настроек на временный."""
    target = tmp_path / "agent_settings.json"
    monkeypatch.setattr(ag, "AGENT_SETTINGS_FILE", str(target))
    yield target


# ─── get_agent_enabled ───


def test_default_disabled_when_no_file(settings_file):
    assert ag.get_agent_enabled(1) is False
    assert not settings_file.exists()


def test_set_enabled_and_read_back(settings_file):
    ag.set_agent_enabled(1, True)
    assert ag.get_agent_enabled(1) is True
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert data["1"]["enabled"] is True


def test_set_disabled(settings_file):
    ag.set_agent_enabled(1, True)
    ag.set_agent_enabled(1, False)
    assert ag.get_agent_enabled(1) is False


def test_users_isolated(settings_file):
    ag.set_agent_enabled(1, True)
    assert ag.get_agent_enabled(2) is False
    assert ag.get_agent_enabled(1) is True


def test_unknown_value_falls_back_to_default(settings_file):
    settings_file.write_text(json.dumps({"7": {"enabled": "да"}}), encoding="utf-8")
    assert ag.get_agent_enabled(7) is False


def test_malformed_json_falls_back(settings_file):
    settings_file.write_text("{broken", encoding="utf-8")
    assert ag.get_agent_enabled(1) is False


def test_non_dict_root_falls_back(settings_file):
    settings_file.write_text("[1, 2, 3]", encoding="utf-8")
    assert ag.get_agent_enabled(1) is False


def test_settings_dir_created(settings_file, tmp_path):
    nested = tmp_path / "sub" / "dir" / "agent_settings.json"
    ag.AGENT_SETTINGS_FILE = str(nested)
    ag.set_agent_enabled(1, True)
    assert nested.exists()


# ─── set_agent_enabled ───


def test_set_non_bool_raises(settings_file):
    with pytest.raises(TypeError):
        ag.set_agent_enabled(1, "yes")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ag.set_agent_enabled(1, 1)  # type: ignore[arg-type]


# ─── toggle_agent_enabled ───


def test_toggle_off_to_on(settings_file):
    assert ag.get_agent_enabled(1) is False
    assert ag.toggle_agent_enabled(1) is True
    assert ag.get_agent_enabled(1) is True


def test_toggle_on_to_off(settings_file):
    ag.set_agent_enabled(1, True)
    assert ag.toggle_agent_enabled(1) is False
    assert ag.get_agent_enabled(1) is False
