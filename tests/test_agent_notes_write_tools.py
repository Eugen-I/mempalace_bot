"""Unit-тесты для services.agent_notes_write_tools — write-инструменты Apple Notes.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
apple_notes замокана; проверяются реестр (allowlist), схемы, форматирование
результата и обработка ошибок.
"""

import json

import pytest

from services import agent_notes_write_tools as anwt
from services import agent_tools as at
from services.apple_notes import AppleNotesError


@pytest.fixture(autouse=True)
def mock_apple_notes(monkeypatch):
    """Заменяет функции apple_notes: create/update/delete/folders/move."""

    def _set(create=None, update=None, delete=None, folders=None, move=None,
             raise_error=None):
        def _maybe(name, result):
            if raise_error and name in raise_error:
                return lambda *a, **k: (_ for _ in ()).throw(
                    AppleNotesError("TCC denied"),
                )
            return lambda *a, **k: result

        monkeypatch.setattr(
            "services.agent_notes_write_tools.create_note",
            _maybe("create", create or "new_id"),
        )
        monkeypatch.setattr(
            "services.agent_notes_write_tools.update_note",
            _maybe("update", update or {"id": "n1", "body": "текст"}),
        )
        monkeypatch.setattr(
            "services.agent_notes_write_tools.delete_note",
            _maybe("delete", delete if delete is not None else True),
        )
        monkeypatch.setattr(
            "services.agent_notes_write_tools.list_folders",
            _maybe("folders", folders if folders is not None else ["Философия", "Личное"]),
        )
        monkeypatch.setattr(
            "services.agent_notes_write_tools.move_note",
            _maybe("move", move or {"id": "n1", "folder": "Личное"}),
        )

    return _set


# ─── Реестр и allowlist ───


def test_write_tools_registered():
    for name in ("notes_create", "notes_update", "notes_delete",
                 "notes_list_folders", "notes_move"):
        assert at.get_tool(name) is not None


def test_write_tools_flags():
    for name in ("notes_create", "notes_update", "notes_delete", "notes_move"):
        assert at.get_tool(name).is_write is True
        assert at.get_tool(name).category == at.CAT_NOTES
    assert at.get_tool("notes_list_folders").is_write is False


def test_write_tools_hidden_by_default():
    names = [t.name for t in at.list_agent_tools(include_write=False)]
    for name in ("notes_create", "notes_update", "notes_delete", "notes_move"):
        assert name not in names
    assert "notes_list_folders" in names


def test_write_tools_visible_with_flag():
    names = [t.name for t in at.list_agent_tools(include_write=True)]
    for name in ("notes_create", "notes_update", "notes_delete",
                 "notes_list_folders", "notes_move"):
        assert name in names


def test_write_tools_visible_with_notes_category():
    names = [t.name for t in at.list_agent_tools(
        allowed_categories=(at.CAT_NOTES,), include_write=True,
    )]
    assert "notes_create" in names
    assert "mp_search" not in names


# ─── Схемы (BVA) ───


def test_schemas_required_fields():
    assert at.get_tool("notes_create").schema["required"] == ["title"]
    assert at.get_tool("notes_update").schema["required"] == ["note_id", "append_text"]
    assert at.get_tool("notes_delete").schema["required"] == ["note_id"]
    assert at.get_tool("notes_move").schema["required"] == ["note_id", "target_folder"]
    assert "required" not in at.get_tool("notes_list_folders").schema


def test_validate_arguments_ok():
    assert at.validate_arguments(at.get_tool("notes_create"), {"title": "T"}) == []
    assert at.validate_arguments(
        at.get_tool("notes_create"), {"title": "T", "body": "B", "folder": "Ф"},
    ) == []
    assert at.validate_arguments(
        at.get_tool("notes_update"), {"note_id": "n1", "append_text": "x"},
    ) == []
    assert at.validate_arguments(at.get_tool("notes_delete"), {"note_id": "n1"}) == []
    assert at.validate_arguments(
        at.get_tool("notes_move"), {"note_id": "n1", "target_folder": "Ф"},
    ) == []


def test_validate_arguments_missing_required():
    assert at.validate_arguments(at.get_tool("notes_create"), {})
    assert at.validate_arguments(at.get_tool("notes_update"), {"note_id": "n1"})
    assert at.validate_arguments(at.get_tool("notes_delete"), {})
    assert at.validate_arguments(at.get_tool("notes_move"), {"note_id": "n1"})


def test_validate_arguments_wrong_types():
    assert at.validate_arguments(at.get_tool("notes_create"), {"title": 5})
    assert at.validate_arguments(at.get_tool("notes_update"), {"note_id": 1, "append_text": "x"})
    assert at.validate_arguments(at.get_tool("notes_move"), {"note_id": "n", "target_folder": []})


def test_validate_arguments_unknown_key():
    errors = at.validate_arguments(
        at.get_tool("notes_delete"), {"note_id": "n1", "force": True},
    )
    assert any("Неизвестный аргумент" in e for e in errors)


# ─── notes_create ───


def test_notes_create_ok(mock_apple_notes, monkeypatch):
    captured = {}

    def fake_create(title, body="", folder=None):
        captured.update(title=title, body=body, folder=folder)
        return "new42"

    monkeypatch.setattr("services.agent_notes_write_tools.create_note", fake_create)
    out = anwt._notes_create({"title": "Заголовок", "body": "Текст", "folder": "Ф"})
    assert captured == {"title": "Заголовок", "body": "Текст", "folder": "Ф"}
    assert "new42" in out


def test_notes_create_without_optional(mock_apple_notes, monkeypatch):
    captured = {}

    def fake_create(title, body="", folder=None):
        captured.update(title=title, body=body, folder=folder)
        return "n1"

    monkeypatch.setattr("services.agent_notes_write_tools.create_note", fake_create)
    anwt._notes_create({"title": "Только заголовок"})
    assert captured == {"title": "Только заголовок", "body": "", "folder": None}


def test_notes_create_error(mock_apple_notes):
    mock_apple_notes(raise_error={"create"})
    out = anwt._notes_create({"title": "T"})
    assert "Ошибка Apple Notes" in out


# ─── notes_update ───


def test_notes_update_ok(mock_apple_notes, monkeypatch):
    captured = {}

    def fake_update(note_id, append_text=None, replace_text=None):
        captured.update(note_id=note_id, append_text=append_text, replace_text=replace_text)
        return {"id": "n1", "body": "старое\nновое"}

    monkeypatch.setattr("services.agent_notes_write_tools.update_note", fake_update)
    out = anwt._notes_update({"note_id": "n1", "append_text": "новое"})
    assert captured == {"note_id": "n1", "append_text": "новое", "replace_text": None}
    assert "n1" in out
    assert "старое\nновое" in out


def test_notes_update_error(mock_apple_notes):
    mock_apple_notes(raise_error={"update"})
    assert "Ошибка Apple Notes" in anwt._notes_update({"note_id": "n1", "append_text": "x"})


# ─── notes_delete ───


def test_notes_delete_ok(mock_apple_notes, monkeypatch):
    captured = {}

    def fake_delete(note_id):
        captured["note_id"] = note_id
        return True

    monkeypatch.setattr("services.agent_notes_write_tools.delete_note", fake_delete)
    out = anwt._notes_delete({"note_id": "n1"})
    assert captured == {"note_id": "n1"}
    assert "Recently Deleted" in out


def test_notes_delete_false_result(mock_apple_notes):
    mock_apple_notes(delete=False)
    out = anwt._notes_delete({"note_id": "n1"})
    assert "Не удалось удалить" in out


def test_notes_delete_error(mock_apple_notes):
    mock_apple_notes(raise_error={"delete"})
    assert "Ошибка Apple Notes" in anwt._notes_delete({"note_id": "n1"})


# ─── notes_list_folders ───


def test_notes_list_folders_ok(mock_apple_notes):
    mock_apple_notes(folders=["Философия", "Личное"])
    out = anwt._notes_list_folders({})
    assert "Философия" in out
    assert "Личное" in out


def test_notes_list_folders_empty(mock_apple_notes):
    mock_apple_notes(folders=[])
    assert "не найдено" in anwt._notes_list_folders({})


def test_notes_list_folders_error(mock_apple_notes):
    mock_apple_notes(raise_error={"folders"})
    assert "Ошибка Apple Notes" in anwt._notes_list_folders({})


# ─── notes_move ───


def test_notes_move_ok(mock_apple_notes, monkeypatch):
    captured = {}

    def fake_move(note_id, target_folder):
        captured.update(note_id=note_id, target_folder=target_folder)
        return {"id": "n1", "folder": "Личное"}

    monkeypatch.setattr("services.agent_notes_write_tools.move_note", fake_move)
    out = anwt._notes_move({"note_id": "n1", "target_folder": "Личное"})
    assert captured == {"note_id": "n1", "target_folder": "Личное"}
    assert "Личное" in out
    assert "n1" in out


def test_notes_move_error(mock_apple_notes):
    mock_apple_notes(raise_error={"move"})
    assert "Ошибка Apple Notes" in anwt._notes_move({"note_id": "n1", "target_folder": "Ф"})


# ─── Интеграция с движком ───


def test_engine_include_write_executes_write_tool(monkeypatch):
    """run_agent с include_write=True выполняет notes_create (мок)."""
    from services import agent_engine as ae

    def fake_call(model, messages, tools):
        return {
            "content": None,
            "finish_reason": "tool_calls",
            "tool_calls": [{
                "id": "c1",
                "name": "notes_create",
                "arguments": json.dumps({"title": "Т"}) or "{}",
            }],
        }

    calls = []
    original = anwt.create_note
    monkeypatch.setattr(
        anwt, "create_note",
        lambda title, body="", folder=None: calls.append(title) or "n99",
    )
    monkeypatch.setattr(ae, "_qwen_tool_call", fake_call)
    result = asyncio_run(ae.run_agent(
        system_prompt="s",
        user_prompt="u",
        engine="qwen",
        model="qwen2.5:7b",
        include_write=True,
        max_iterations=1,
    ))
    assert calls == ["Т"]
    assert result.steps[0].results[0]["ok"] is True
    monkeypatch.setattr(anwt, "create_note", original)


def test_engine_without_write_unknown_tool(monkeypatch):
    """include_write=False: notes_create не виден → «не существует»."""
    from services import agent_engine as ae

    def fake_call(model, messages, tools):
        return {
            "content": None,
            "finish_reason": "tool_calls",
            "tool_calls": [{
                "id": "c1",
                "name": "notes_create",
                "arguments": '{"title": "Т"}',
            }],
        }

    monkeypatch.setattr(ae, "_qwen_tool_call", fake_call)
    result = asyncio_run(ae.run_agent(
        system_prompt="s",
        user_prompt="u",
        engine="qwen",
        model="qwen2.5:7b",
        include_write=False,
        max_iterations=1,
    ))
    assert result.steps[0].results[0]["ok"] is False
    assert "не существует" in result.steps[0].results[0]["output"]


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
