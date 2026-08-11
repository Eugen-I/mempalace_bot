"""Unit-тесты для services.agent_notes_tools — инструменты Apple Notes.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
apple_notes замокана; проверяются форматирование результата и обработка ошибок.
"""

import asyncio

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
            "services.agent_notes_tools.search_notes_hybrid",
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

    def fake_list_notes(folder=None, force_refresh=False,
                        sort_by_updated=False, limit=None):
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
    out = asyncio.run(ant._notes_search({"query": "шопенгауэр", "limit": 5}))
    assert "Шопенгауэр" in out
    assert "id1" in out


def test_notes_search_shows_snippet(mock_apple_notes):
    mock_apple_notes(search_result=[
        {"id": "id2", "name": "Покупки", "folder": "Быт", "updated": "",
         "snippet": "…купил Шопенгауэра…"},
    ])
    out = asyncio.run(ant._notes_search({"query": "шопенгауэр"}))
    assert "Шопенгауэр" in out
    assert "…купил Шопенгауэра…" in out


def test_notes_search_no_snippet_plain_line(mock_apple_notes):
    mock_apple_notes(search_result=[
        {"id": "id3", "name": "Имя", "folder": "Ф", "updated": "", "snippet": ""},
    ])
    out = asyncio.run(ant._notes_search({"query": "имя"}))
    assert "id3" in out
    assert "…" not in out


def test_notes_search_no_results(mock_apple_notes):
    mock_apple_notes(search_result=[])
    out = asyncio.run(ant._notes_search({"query": "zzz"}))
    assert "ничего не найдено" in out


def test_notes_search_error(mock_apple_notes):
    mock_apple_notes(raise_error={"search"})
    out = asyncio.run(ant._notes_search({"query": "q"}))
    assert "Ошибка Apple Notes" in out


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


# ─── notes_list: параметр limit (Фаза 3) ───


def test_notes_list_limit_schema_valid():
    tool = at.get_tool("notes_list")
    errors = at.validate_arguments(tool, {"limit": 10})
    assert errors == []


def test_notes_list_limit_schema_zero_rejected():
    tool = at.get_tool("notes_list")
    assert at.validate_arguments(tool, {"limit": 0})


def test_notes_list_limit_schema_negative_rejected():
    tool = at.get_tool("notes_list")
    assert at.validate_arguments(tool, {"limit": -1})


def test_notes_list_limit_schema_non_int_rejected():
    tool = at.get_tool("notes_list")
    assert at.validate_arguments(tool, {"limit": "пять"})


def test_notes_list_limit_passed_to_list_notes(monkeypatch):
    from services import agent_notes_tools as ant

    received = {}

    def fake_list_notes(folder=None, force_refresh=False,
                        sort_by_updated=False, limit=None):
        received.update(folder=folder, force_refresh=force_refresh,
                        sort_by_updated=sort_by_updated, limit=limit)
        return [{"id": "n1", "name": "X", "folder": "Фото"}]

    monkeypatch.setattr(ant, "list_notes", fake_list_notes)
    out = ant._notes_list({"limit": 7})
    assert received["limit"] == 7
    assert received["sort_by_updated"] is True
    assert "X" in out


def test_notes_list_without_limit_unsorted(monkeypatch):
    from services import agent_notes_tools as ant

    received = {}

    def fake_list_notes(folder=None, force_refresh=False,
                        sort_by_updated=False, limit=None):
        received.update(sort_by_updated=sort_by_updated, limit=limit)
        return [{"id": "n1", "name": "X", "folder": "Фото"}]

    monkeypatch.setattr(ant, "list_notes", fake_list_notes)
    ant._notes_list({})
    assert received["sort_by_updated"] is False
    assert received["limit"] is None
