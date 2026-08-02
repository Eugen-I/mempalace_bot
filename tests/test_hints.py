"""Тесты handlers/palace/hints.py — чтение полного текста записи из ChromaDB.

Покрывают _get_full_text_from_chroma: happy path, негативы, границы.
Соединение с SQLite закрывается всегда (contextlib.closing) — без ResourceWarning.
"""
import sqlite3
import warnings

import pytest


def _make_chroma_db(path: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE embeddings (id INTEGER PRIMARY KEY, embedding_id TEXT);
            CREATE TABLE embedding_metadata (
                id INTEGER, key TEXT, string_value TEXT
            );
            """
        )
        con.execute(
            "INSERT INTO embeddings (id, embedding_id) VALUES (1, 'drawer_a')"
        )
        con.execute(
            "INSERT INTO embeddings (id, embedding_id) VALUES (2, 'drawer_b')"
        )
        con.execute(
            "INSERT INTO embeddings (id, embedding_id) VALUES (3, 'drawer_c')"
        )
        con.execute(
            "INSERT INTO embedding_metadata VALUES "
            "(1, 'source_file', '/palace/w1/r1/note.md'), "
            "(1, 'chroma:document', 'Первый блок текста'), "
            "(2, 'source_file', '/palace/w1/r1/note.md'), "
            "(2, 'chroma:document', 'Второй блок текста'), "
            "(3, 'source_file', '/palace/w1/r1/other.md'), "
            "(3, 'chroma:document', 'Чужая запись')"
        )
        con.commit()
    finally:
        con.close()


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch, tmp_path):
    db = tmp_path / "chroma.sqlite3"
    _make_chroma_db(str(db))
    monkeypatch.setattr(
        "handlers.palace.hints.os.path.expanduser", lambda _: str(db),
    )
    return db


def test_get_full_text_happy_path():
    from handlers.palace.hints import _get_full_text_from_chroma

    text = _get_full_text_from_chroma("/palace/w1/r1/note.md")
    assert "Первый блок текста" in text
    assert "Второй блок текста" in text
    assert "Чужая запись" not in text


def test_get_full_text_unknown_source():
    from handlers.palace.hints import _get_full_text_from_chroma

    assert _get_full_text_from_chroma("/no/such/file.md") == ""


def test_get_full_text_empty_source():
    from handlers.palace.hints import _get_full_text_from_chroma

    assert _get_full_text_from_chroma("") == ""


def test_get_full_text_missing_db(tmp_path, monkeypatch):
    from handlers.palace.hints import _get_full_text_from_chroma

    monkeypatch.setattr(
        "handlers.palace.hints.os.path.expanduser",
        lambda _: str(tmp_path / "absent.sqlite3"),
    )
    assert _get_full_text_from_chroma("any.md") == ""


def test_get_full_text_corrupt_db(tmp_path, monkeypatch):
    from handlers.palace.hints import _get_full_text_from_chroma

    bad = tmp_path / "bad.sqlite3"
    bad.write_text("не sqlite")
    monkeypatch.setattr(
        "handlers.palace.hints.os.path.expanduser", lambda _: str(bad),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        assert _get_full_text_from_chroma("any.md") == ""


def test_get_full_text_duplicates_deduped():
    from handlers.palace.hints import _get_full_text_from_chroma

    con = sqlite3.connect(
        __import__("handlers.palace.hints", fromlist=[""]).os.path.expanduser("~"),
    )
    try:
        con.execute(
            "INSERT INTO embeddings (id, embedding_id) VALUES (4, 'drawer_a')"
        )
        con.execute(
            "INSERT INTO embedding_metadata VALUES "
            "(4, 'source_file', '/palace/w1/r1/note.md'), "
            "(4, 'chroma:document', 'Первый блок текста')"
        )
        con.commit()
    finally:
        con.close()
    text = _get_full_text_from_chroma("/palace/w1/r1/note.md")
    assert text.count("Первый блок текста") == 1
