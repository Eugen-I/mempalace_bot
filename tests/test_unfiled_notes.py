"""tests/test_unfiled_notes.py — Тесты для неразобранных заметок."""
from unittest.mock import AsyncMock

import pytest

from handlers.palace.unfiled_notes import (
    _format_size,
    list_unfiled_notes,
    show_unfiled_content,
    show_unfiled_list,
)


def test_format_size():
    assert _format_size(500) == "500 B"
    assert _format_size(2048) == "2.0 KB"
    assert _format_size(1048576 * 2) == "2.0 MB"


def test_list_unfiled_notes(tmp_path, monkeypatch):
    notes_dir = tmp_path / "my_notes"
    notes_dir.mkdir()
    monkeypatch.setattr("handlers.palace.unfiled_notes.NOTES_DIR", str(notes_dir))

    # Regular unfiled files in root
    f1 = notes_dir / "notes_20261108_1717.md"
    f1.write_text("Note 1 content", encoding="utf-8")
    f2 = notes_dir / "note_quick.txt"
    f2.write_text("Note 2 content", encoding="utf-8")

    # Subdirectory and file inside it (should be ignored)
    sub = notes_dir / "Philosophy"
    sub.mkdir()
    f3 = sub / "archived.md"
    f3.write_text("Archived", encoding="utf-8")

    # Hidden file (should be ignored)
    hidden = notes_dir / ".DS_Store"
    hidden.write_text("binary", encoding="utf-8")

    files = list_unfiled_notes()
    assert len(files) == 2
    filenames = [item["filename"] for item in files]
    assert "notes_20261108_1717.md" in filenames
    assert "note_quick.txt" in filenames
    assert "archived.md" not in filenames


@pytest.mark.asyncio
async def test_show_unfiled_list(tmp_path, monkeypatch):
    notes_dir = tmp_path / "my_notes"
    notes_dir.mkdir()
    monkeypatch.setattr("handlers.palace.unfiled_notes.NOTES_DIR", str(notes_dir))

    f1 = notes_dir / "test_note.md"
    f1.write_text("Test content", encoding="utf-8")

    edit_mock = AsyncMock()
    await show_unfiled_list(edit_mock, uid=1001, page=0)

    edit_mock.assert_called_once()
    msg = edit_mock.call_args[0][0]
    assert "test_note.md" in msg
    assert "Неразобранные заметки" in msg


@pytest.mark.asyncio
async def test_show_unfiled_content(tmp_path, monkeypatch):
    notes_dir = tmp_path / "my_notes"
    notes_dir.mkdir()
    monkeypatch.setattr("handlers.palace.unfiled_notes.NOTES_DIR", str(notes_dir))

    f1 = notes_dir / "my_long_note.md"
    f1.write_text("A" * 5000, encoding="utf-8")

    from handlers.palace.unfiled_notes import _unfiled_state
    _unfiled_state[1002] = {
        "filename": "my_long_note.md",
        "selected_path": str(f1),
    }

    edit_mock = AsyncMock()
    await show_unfiled_content(edit_mock, uid=1002, file_page=0)

    edit_mock.assert_called_once()
    msg = edit_mock.call_args[0][0]
    assert "my_long_note.md" in msg
    assert "Страница 1/2" in msg
