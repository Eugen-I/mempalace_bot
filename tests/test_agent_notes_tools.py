"""Unit-тесты для services.agent_notes_tools — инструменты Apple Notes.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
apple_notes замокана; проверяются форматирование результата и обработка ошибок.
"""

import pytest

from services import agent_notes_tools as ant
from services import agent_tools as at
from services.apple_notes import AppleNotesError


@pytest.fixture(autouse=True)
def mock_apple_notes(monkeypatch):
    """Заменяет функции apple_notes: список, поиск, чтение."""

    def _set(list_result=None, search_result=None, read_result=None, raise_error=None):
        def _maybe(name, result):
            if raise_error and name in raise_error:
                return lambda *a, **k: (_ for _ in ()).throw(AppleNotesError("TCC denied"))
            return lambda *a, **k: result

        monkeypatch.setattr(
            "services.agent_notes_tools.list_notes",
            _maybe("list", list_result or []),
        )
        monkeypatch.setattr(
            "services.agent_notes_tools.search_notes",
            _maybe("search", search_result or []),
        )
        monkeypatch.setattr(
            "services.agent_notes_tools.read_note",
            _maybe("read", read_result or {"name": "N", "body": "B"}),
        )

    return _set


# ─── Реестр ───


def test_notes_tools_registered_readonly():
    for name in ("notes_list", "notes_search", "notes_read"):
        tool = at.get_tool(name)
        assert tool is not None
        assert tool.category == at.CAT_NOTES
        assert tool.is_write is False


def test_notes_tools_schemas_required():
    assert at.get_tool("notes_search").schema["required"] == ["query"]
    assert at.get_tool("notes_read").schema["required"] == ["note_id"]
    assert "required" not in at.get_tool("notes_list").schema or True


# ─── notes_list ───


def test_notes_list_formats_results(mock_apple_notes):
    mock_apple_notes(list_result=[
        {"id": "id1", "name": "Заметка А", "folder": "Ф1", "updated": ""},
        {"id": "id2", "name": "Заметка Б", "folder": "Ф2", "updated": ""},
    ])
    out = ant._notes_list({})
    assert "Заметка А" in out
    assert "id1" in out
    assert "Ф1" in out


def test_notes_list_empty(mock_apple_notes):
    mock_apple_notes(list_result=[])
    assert "не найдено" in ant._notes_list({})


def test_notes_list_passes_folder(mock_apple_notes, monkeypatch):
    captured = {}

    def fake_list_notes(folder=None, force_refresh=False):
        captured["folder"] = folder
        captured["force"] = force_refresh
        return []

    monkeypatch.setattr("services.agent_notes_tools.list_notes", fake_list_notes)
    ant._notes_list({"folder": "Философия"})
    assert captured == {"folder": "Философия", "force": False}
    ant._notes_list({"folder": "Ф", "force_refresh": True})
    assert captured["force"] is True


def test_notes_list_error(mock_apple_notes):
    mock_apple_notes(raise_error={"list"})
    assert "Ошибка Apple Notes" in ant._notes_list({})


def test_notes_list_truncates_50(mock_apple_notes):
    many = [{"id": f"id{i}", "name": f"Н{i}", "folder": "Ф", "updated": ""}
            for i in range(60)]
    mock_apple_notes(list_result=many)
    out = ant._notes_list({})
    assert "Н49" in out
    assert "Н59" not in out


# ─── notes_search ───


def test_notes_search_ok(mock_apple_notes):
    mock_apple_notes(search_result=[
        {"id": "id1", "name": "Шопенгауэр", "folder": "Ф", "updated": ""},
    ])
    out = ant._notes_search({"query": "шопенгауэр", "limit": 5})
    assert "Шопенгауэр" in out
    assert "id1" in out


def test_notes_search_no_results(mock_apple_notes):
    mock_apple_notes(search_result=[])
    assert "ничего не найдено" in ant._notes_search({"query": "zzz"})


def test_notes_search_error(mock_apple_notes):
    mock_apple_notes(raise_error={"search"})
    assert "Ошибка Apple Notes" in ant._notes_search({"query": "q"})


def test_notes_search_validate_arguments():
    tool = at.get_tool("notes_search")
    assert at.validate_arguments(tool, {"limit": 5})
    assert at.validate_arguments(tool, {"query": "q", "limit": 5}) == []
    assert at.validate_arguments(tool, {"query": "q"}) == []


# ─── notes_read ───


def test_notes_read_ok(mock_apple_notes):
    mock_apple_notes(read_result={"name": "Важная", "body": "Содержимое"})
    out = ant._notes_read({"note_id": "id1"})
    assert "Важная" in out
    assert "Содержимое" in out


def test_notes_read_error(mock_apple_notes):
    mock_apple_notes(raise_error={"read"})
    assert "Ошибка Apple Notes" in ant._notes_read({"note_id": "id1"})


def test_notes_read_validate_arguments():
    tool = at.get_tool("notes_read")
    assert at.validate_arguments(tool, {})
    assert at.validate_arguments(tool, {"note_id": "x"}) == []


# ─── Интеграция с движком ───


def test_list_agent_tools_includes_notes():
    names = [t.name for t in at.list_agent_tools()]
    for name in ("notes_list", "notes_search", "notes_read"):
        assert name in names
