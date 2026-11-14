"""tests/test_cascade_delete.py — Тесты для сервиса cascade_delete."""
import json
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from services.cascade_delete import (
    cascade_delete_note,
    delete_from_disk,
    delete_from_notes_index,
    delete_from_sqlite_embeddings,
)


def test_delete_from_disk_safe(tmp_path, monkeypatch):
    notes_dir = tmp_path / "my_notes"
    notes_dir.mkdir()
    monkeypatch.setattr("services.cascade_delete.NOTES_DIR", str(notes_dir))

    test_file = notes_dir / "note_1.txt"
    test_file.write_text("Hello world", encoding="utf-8")
    assert test_file.exists()

    ok, deleted_path = delete_from_disk(file_path=str(test_file))
    assert ok is True
    assert not test_file.exists()


def test_delete_from_disk_forbidden_outside_notes_dir(tmp_path, monkeypatch):
    notes_dir = tmp_path / "my_notes"
    notes_dir.mkdir()
    monkeypatch.setattr("services.cascade_delete.NOTES_DIR", str(notes_dir))

    outside_file = tmp_path / "system.txt"
    outside_file.write_text("critical", encoding="utf-8")

    ok, msg = delete_from_disk(file_path=str(outside_file))
    assert ok is False
    assert msg == "forbidden_path"
    assert outside_file.exists()


def test_delete_from_sqlite_embeddings(tmp_path, monkeypatch):
    monkeypatch.setattr("services.cascade_delete.DATA_DIR", str(tmp_path))
    db_path = tmp_path / "notes_embeddings.sqlite"

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE notes_embeddings (note_id TEXT, name TEXT, "
        "folder TEXT, preview TEXT, vector BLOB, model TEXT)"
    )
    conn.execute(
        "INSERT INTO notes_embeddings VALUES "
        "('p123', 'Secret Note', 'Folder', 'secret', X'00', 'm')"
    )
    conn.execute(
        "INSERT INTO notes_embeddings VALUES "
        "('p456', 'Other Note', 'Folder', 'normal', X'00', 'm')"
    )
    conn.commit()
    conn.close()

    deleted = delete_from_sqlite_embeddings(source_id="p123")
    assert deleted == 1

    conn = sqlite3.connect(db_path)
    cnt = conn.execute("SELECT count(*) FROM notes_embeddings").fetchone()[0]
    conn.close()
    assert cnt == 1


def test_delete_from_notes_index(tmp_path, monkeypatch):
    monkeypatch.setattr("services.cascade_delete.DATA_DIR", str(tmp_path))
    idx_path = tmp_path / "notes_index.json"

    data = {
        "notes": [
            {"id": "p123", "name": "Secret Note"},
            {"id": "p456", "name": "Normal Note"},
        ]
    }
    idx_path.write_text(json.dumps(data), encoding="utf-8")

    deleted = delete_from_notes_index(source_id="p123")
    assert deleted == 1

    with open(idx_path, encoding="utf-8") as f:
        res = json.load(f)
    assert len(res["notes"]) == 1
    assert res["notes"][0]["id"] == "p456"


@pytest.mark.asyncio
async def test_cascade_delete_graceful_missing_chroma(tmp_path, monkeypatch):
    notes_dir = tmp_path / "my_notes"
    notes_dir.mkdir()
    monkeypatch.setattr("services.cascade_delete.NOTES_DIR", str(notes_dir))
    monkeypatch.setattr("services.cascade_delete.DATA_DIR", str(tmp_path))

    test_file = notes_dir / "secret.txt"
    test_file.write_text("secret payload", encoding="utf-8")

    mock_mcp = AsyncMock()
    mock_mcp.call_tool.return_value = json.dumps(
        {"success": False, "error": "Drawer not found: d123"}
    )

    with patch("services.cascade_delete.get_mcp", return_value=mock_mcp):
        with patch("services.cascade_delete.delete_backlink"):
            res = await cascade_delete_note(
                drawer_id="d123",
                file_path=str(test_file),
                source_file="secret.txt",
                title="secret",
            )

    assert res["success"] is True
    assert res["file_deleted"] is True
    assert not test_file.exists()
