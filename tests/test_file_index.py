import ast
import datetime
import logging
import os
import sqlite3
from pathlib import Path

import numpy as np
import pytest

import services.file_index as fi


@pytest.fixture(autouse=True)
def clean_db(monkeypatch, tmp_path):
    db = str(tmp_path / "file_index.sqlite")
    monkeypatch.setattr(fi, "DB_FILE", db)
    monkeypatch.setattr(fi, "DATA_DIR", str(tmp_path))
    yield


# ---------- chunk_text ----------


def test_chunk_text_empty():
    assert fi.chunk_text("") == []


def test_chunk_text_single():
    assert fi.chunk_text("короткий текст") == ["короткий текст"]


def test_chunk_text_exact_size():
    text = "а" * fi.CHUNK_CHARS
    assert fi.chunk_text(text) == [text]


def test_chunk_text_exact_plus_one():
    text = "а" * (fi.CHUNK_CHARS + 1)
    chunks = fi.chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0] == text[:fi.CHUNK_CHARS]
    assert chunks[1] == text[fi.CHUNK_CHARS - fi.CHUNK_OVERLAP:]


def test_chunk_text_long():
    text = "абв" * 1000
    chunks = fi.chunk_text(text, chunk_chars=100, overlap=10)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    covered = "".join(chunks)
    assert all(ch in covered for ch in ("а", "б", "в"))
    assert len(covered) >= len(text)


def test_chunk_text_bad_args():
    with pytest.raises(ValueError) as excinfo:
        fi.chunk_text("x", chunk_chars=0)
    assert str(excinfo.value) == "chunk_chars должен быть >= 1"
    with pytest.raises(ValueError) as excinfo:
        fi.chunk_text("x", overlap=10, chunk_chars=5)
    assert str(excinfo.value) == "overlap должен быть в [0, chunk_chars)"


def test_chunk_text_min_chunk_chars_bva():
    text = "абв"
    chunks = fi.chunk_text(text, chunk_chars=1, overlap=0)
    assert chunks == ["а", "б", "в"]


def test_chunk_text_min_overlap_bva():
    assert fi.chunk_text("абв", chunk_chars=3, overlap=0) == ["абв"]


def test_chunk_text_overlap_equal_chunk_chars_rejected():
    with pytest.raises(ValueError, match="overlap должен быть в \\[0, chunk_chars\\)"):
        fi.chunk_text("абв", chunk_chars=3, overlap=3)


# ---------- index_document ----------


def test_index_document_happy(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("Привет, мир. Это заметка про python.", encoding="utf-8")
    out = fi.index_document(str(path))
    assert out["status"] == "indexed"
    assert out["added"] is True
    assert out["chunks"] == 1
    meta = fi.get_file(out["file_id"])
    assert meta["file_id"] == out["file_id"]
    assert meta["filename"] == "note.txt"
    assert meta["mime"] == "text/plain"
    assert meta["folder"] == ""
    assert meta["size"] == len("Привет, мир. Это заметка про python.".encode())
    assert meta["status"] == "indexed"
    assert meta["note_id"] is None
    assert meta["extra"] == {"path": str(path), "mime": "text/plain"}
    assert "python" in meta["extracted_text"]
    stats = fi.file_stats()
    assert stats["total_files"] == 1
    assert stats["indexed"] == 1
    assert stats["total_chunks"] == 1
    assert stats["size_bytes"] == len("Привет, мир. Это заметка про python.".encode())


def test_index_document_same_content_not_duplicated(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("один и тот же контент", encoding="utf-8")
    first = fi.index_document(str(path))
    second = fi.index_document(str(path))
    assert first["file_id"] == second["file_id"]
    assert second["added"] is False
    assert fi.file_stats()["total_files"] == 1


def test_index_document_updated_content(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("версия 1", encoding="utf-8")
    first = fi.index_document(str(path))
    path.write_text("версия 2 длиннее и содержит чанк номер раз", encoding="utf-8")
    second = fi.index_document(str(path))
    assert first["file_id"] != second["file_id"]
    assert second["added"] is True
    assert fi.get_file(second["file_id"])["extracted_text"].startswith("версия 2")
    assert fi.file_stats()["total_files"] == 2


def test_index_document_missing_file(tmp_path):
    with pytest.raises(OSError):
        fi.index_document(str(tmp_path / "нет.txt"))


def test_index_document_markdown_mime(tmp_path):
    path = tmp_path / "readme.md"
    path.write_text("# Заголовок", encoding="utf-8")
    out = fi.index_document(str(path))
    assert fi.get_file(out["file_id"])["mime"] == "text/markdown"


def test_index_document_invalid_utf8(tmp_path):
    path = tmp_path / "bin.txt"
    path.write_bytes(b"\xff\xfe\x00\x01")
    out = fi.index_document(str(path))
    assert out["status"] == "indexed"


def test_index_document_sqlite_error_marks_failed(tmp_path, monkeypatch):
    path = tmp_path / "note.txt"
    path.write_text("контент", encoding="utf-8")

    connect_count = {"n": 0}

    class BoomConn:
        def __init__(self, real):
            self._real = real
            self._idx = connect_count["n"]
            connect_count["n"] += 1

        def __getattr__(self, name):
            return getattr(self._real, name)

        def commit(self):
            if self._idx % 2 == 0:
                raise sqlite3.OperationalError("database is locked")
            return self._real.commit()

    real_factory = fi._connect
    monkeypatch.setattr(fi, "_connect", lambda: BoomConn(real_factory()))
    out = fi.index_document(str(path))
    assert out["status"] == "failed"
    expected_failed = {"file_id": fi._sha256("контент".encode("utf-8")),
                       "status": "failed",
                       "chunks": 0, "added": True}
    assert out == expected_failed

    def _row():
        conn = sqlite3.connect(fi.DB_FILE)
        try:
            return conn.execute(
                "SELECT status, error FROM files WHERE file_id = ?",
                (out["file_id"],),
            ).fetchone()
        finally:
            conn.close()

    assert _row() == ("failed", "database is locked")
    again = fi.index_document(str(path))
    assert again == expected_failed
    assert _row() == ("failed", "database is locked")
    assert fi.file_stats()["failed"] == 1


def test_index_document_too_big(tmp_path, monkeypatch):
    monkeypatch.setattr(fi, "MAX_TEXT", 10)
    path = tmp_path / "big.txt"
    path.write_text("x" * 20, encoding="utf-8")
    with pytest.raises(ValueError, match="Файл слишком большой"):
        fi.index_document(str(path))


def test_index_document_size_exact_max_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(fi, "MAX_TEXT", 10)
    path = tmp_path / "exact.txt"
    path.write_text("x" * 10, encoding="utf-8")
    out = fi.index_document(str(path))
    assert out["status"] == "indexed"
    assert out["added"] is True


def test_index_document_same_id_differs_text_reindexes(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("контент", encoding="utf-8")
    out = fi.index_document(str(path))
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        conn.execute(
            "UPDATE files SET extracted_text = 'старый текст' WHERE file_id = ?",
            (out["file_id"],),
        )
        conn.commit()
    finally:
        conn.close()
    again = fi.index_document(str(path))
    assert again["added"] is False
    assert fi.get_file(out["file_id"])["extracted_text"] == "контент"


# ---------- index_directory ----------


def test_index_directory_happy(tmp_path):
    (tmp_path / "a.txt").write_text("первый файл", encoding="utf-8")
    (tmp_path / "b.md").write_text("# второй файл", encoding="utf-8")
    (tmp_path / "skip.pdf").write_bytes(b"%PDF")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.txt").write_text("вложенный", encoding="utf-8")
    rep = fi.index_directory(str(tmp_path))
    assert rep["total"] == 2
    assert len(rep["added"]) == 2
    assert all(isinstance(fid, str) and len(fid) == 64 for fid in rep["added"])
    assert rep["failed"] == []
    assert fi.file_stats()["total_files"] == 2
    for fid in rep["added"]:
        meta = fi.get_file(fid)
        assert meta["folder"] == os.path.basename(str(tmp_path))


def test_index_directory_stops_at_dir_break_mutant(tmp_path):
    (tmp_path / "aaa_dir").mkdir()
    (tmp_path / "zzz.txt").write_text("текст", encoding="utf-8")
    rep = fi.index_directory(str(tmp_path))
    assert rep["total"] == 1
    assert len(rep["added"]) == 1


def test_index_directory_stops_at_skipped_ext_break_mutant(tmp_path):
    (tmp_path / "aaa.pdf").write_bytes(b"%PDF")
    (tmp_path / "zzz.txt").write_text("текст", encoding="utf-8")
    rep = fi.index_directory(str(tmp_path))
    assert rep["total"] == 1
    assert len(rep["added"]) == 1


def test_index_directory_os_error_marks_failed_and_continues(tmp_path, monkeypatch):
    real = fi.index_document
    calls = []

    def fake(path, note_id=None, folder=""):
        calls.append(path)
        if path.endswith("a.txt"):
            raise OSError("boom")
        return real(path, note_id=note_id, folder=folder)

    monkeypatch.setattr(fi, "index_document", fake)
    (tmp_path / "a.txt").write_text("падает", encoding="utf-8")
    (tmp_path / "b.txt").write_text("работает", encoding="utf-8")
    rep = fi.index_directory(str(tmp_path))
    assert rep["total"] == 2
    assert len(rep["failed"]) == 1
    assert len(rep["added"]) == 1
    failed = rep["failed"][0]
    assert failed == {"path": str(tmp_path / "a.txt"), "error": "boom"}


def test_index_directory_status_failed_recorded(tmp_path, monkeypatch):
    def fake(path, note_id=None, folder=""):
        return {"file_id": "f" * 64, "status": "failed",
                "chunks": 0, "added": True}

    monkeypatch.setattr(fi, "index_document", fake)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    rep = fi.index_directory(str(tmp_path))
    assert rep["failed"] == [{"path": str(tmp_path / "a.txt"), "error": "failed"}]
    assert rep["added"] == []


def test_index_directory_no_dir(tmp_path):
    with pytest.raises(FileNotFoundError) as excinfo:
        fi.index_directory(str(tmp_path / "нет"))
    assert str(excinfo.value) == f"Директория не найдена: {tmp_path / 'нет'}"


def test_index_directory_empty(tmp_path):
    rep = fi.index_directory(str(tmp_path))
    assert rep == {"total": 0, "added": [], "failed": []}


# ---------- search ----------


def test_search_files_happy(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("уникальный термин дирижабль в тексте", encoding="utf-8")
    out = fi.index_document(str(path))
    res = fi.search_files("дирижабль")
    assert len(res) == 1
    assert res[0]["file_id"] == out["file_id"]
    assert res[0]["filename"] == "note.txt"
    assert "дирижабль" in res[0]["snippet"]


def test_search_files_no_match(tmp_path):
    (tmp_path / "a.txt").write_text("ничего интересного", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.search_files("зелёный") == []


def test_search_files_fallback_like(tmp_path):
    (tmp_path / "a.txt").write_text("абвгд ежзик", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    res = fi.search_files("ежзик")
    assert len(res) == 1


def test_search_files_bad_query(tmp_path):
    with pytest.raises(ValueError) as excinfo:
        fi.search_files("x", limit=0)
    assert str(excinfo.value) == "limit должен быть >= 1"
    assert fi.search_files("   ") == []


def test_search_files_bm25_matches_tokens_not_substring(tmp_path):
    (tmp_path / "a.txt").write_text("привет, мир", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    res = fi.search_files("привет мир")
    assert len(res) == 1
    assert res[0]["filename"] == "a.txt"


def test_search_files_score_and_folder_exact(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("дирижабль летит над городом", encoding="utf-8")
    fi.index_document(str(path), folder="папка")
    for i in range(4):
        (tmp_path / f"other{i}.txt").write_text(
            f"обычный текст файла номер {i} совсем разные слова апельсин груша",
            encoding="utf-8")
        fi.index_document(str(tmp_path / f"other{i}.txt"))
    res = fi.search_files("дирижабль")
    assert len(res) == 1
    assert res[0]["folder"] == "папка"
    assert res[0]["_score"] != 4
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        bm = conn.execute(
            "SELECT bm25(search_index) FROM search_index s"
            " JOIN files f ON f.file_id = s.file_id"
            " WHERE search_index MATCH ?",
            ("дирижабль",),
        ).fetchone()[0]
    finally:
        conn.close()
    assert res[0]["_score"] == round(float(bm), 4)
    assert isinstance(res[0]["_score"], float)


def test_search_files_limit(tmp_path):
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text(f"общий токен номер {i}", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    res = fi.search_files("общий", limit=2)
    assert len(res) == 2


def test_search_files_limit_one_allowed(tmp_path):
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text(f"общий токен номер {i}", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    res = fi.search_files("общий", limit=1)
    assert len(res) == 1
    assert res[0]["_score"] == round(res[0]["_score"], 4)


def test_search_files_fallback_case_sensitive_lower(tmp_path):
    (tmp_path / "a.txt").write_text('абвгд "незакрытая ежзик', encoding="utf-8")
    fi.index_directory(str(tmp_path))
    res = fi.search_files('"незакрытая')
    assert len(res) == 1
    assert res[0]["filename"] == "a.txt"


def test_search_files_fallback_case_sensitive_upper(tmp_path):
    (tmp_path / "a.txt").write_text('абвгд "незакрытая ежзик', encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.search_files('"НЕЗАКРЫТАЯ') == []


def test_search_files_empty_text_snippet_fallback(tmp_path):
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    res = fi.search_files("%")
    assert len(res) == 1
    assert res[0]["snippet"] == ""


def test_search_similar_graceful_no_model(tmp_path, monkeypatch):
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": False)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [[1.0, 0.0, 0.0, 0.0]] * len(inputs))
    (tmp_path / "a.txt").write_text("слово для поиска", encoding="utf-8")
    (tmp_path / "b.txt").write_text("совсем другое содержимое", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    _insert_embedding(fi._sha256("совсем другое содержимое".encode("utf-8")),
                      [1.0, 0.0, 0.0, 0.0])
    res = fi.search_similar("слово")
    assert len(res) == 1
    assert res[0]["filename"] == "a.txt"


def _embed_vec(values):
    return np.asarray(values, dtype=np.float32)


def _insert_embedding(file_id, values, model=None):
    vec = _embed_vec(values).tobytes()
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO embeddings"
            " (file_id, chunk_index, vector, model) VALUES (?,?,?,?)",
            (file_id, 0, vec, model or fi.EMBED_MODEL),
        )
        conn.commit()
    finally:
        conn.close()


def test_search_similar_uses_models_in_order(tmp_path, monkeypatch):
    """score A > score B, limit=1 → берётся A (sorted desc)."""
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)

    def fake_embed(inputs, model):
        if inputs == ["зовун"]:
            return [q]
        return [q] * len(inputs)

    monkeypatch.setattr(fi, "_call_embed", fake_embed)
    (tmp_path / "a.txt").write_text("только альфа слова", encoding="utf-8")
    (tmp_path / "b.txt").write_text("только бета слова", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        conn.execute(
            "UPDATE embeddings SET vector = ? WHERE file_id = ?",
            (_embed_vec([0.6, 0.8, 0.0, 0.0]).tobytes(),
             fi._sha256("только бета слова".encode("utf-8"))),
        )
        conn.commit()
    finally:
        conn.close()
    res = fi.search_similar("зовун", limit=1)
    assert len(res) == 1
    assert res[0]["filename"] == "a.txt"
    assert res[0]["_score"] == pytest.approx(1.0, abs=1e-4)


def test_search_similar_zero_vector_skipped(tmp_path, monkeypatch):
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("альфа", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        conn.execute("DELETE FROM embeddings")
        conn.commit()
    finally:
        conn.close()
    _insert_embedding("z" * 64, [0.0, 0.0, 0.0, 0.0])
    _insert_embedding(fi._sha256("альфа".encode("utf-8")),
                      [1.0, 0.0, 0.0, 0.0])
    res = fi.search_similar("зовун", limit=2)
    assert [r["filename"] for r in res] == ["a.txt"]


def test_search_similar_qnorm_one_and_norm_one(tmp_path, monkeypatch):
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("альфа", encoding="utf-8")
    (tmp_path / "b.txt").write_text("бета", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    _insert_embedding(fi._sha256("бета".encode("utf-8")), [0.5, 0.5, 0.0, 0.0])
    res = fi.search_similar("зовун", limit=2)
    assert {r["filename"] for r in res} == {"a.txt", "b.txt"}


def test_search_similar_score_boundary_half(tmp_path, monkeypatch):
    """score ровно 0.5 не проходит порог > 0.5."""
    q = [2.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("альфа", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    _insert_embedding(fi._sha256("альфа".encode("utf-8")), [0.5, 0.5, 0.5, 0.5])
    assert fi.search_similar("зовун", limit=2) == []


def test_search_similar_score_multiplication_mutant(tmp_path, monkeypatch):
    q = [0.8, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("альфа", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    _insert_embedding(fi._sha256("альфа".encode("utf-8")), [0.6, 0.8, 0.0, 0.0])
    res = fi.search_similar("зовун", limit=2)
    assert len(res) == 1


def test_search_similar_score_division_mutant(tmp_path, monkeypatch):
    q = [0.3, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("альфа", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    _insert_embedding(fi._sha256("альфа".encode("utf-8")), [0.6666667, 1.885618, 0.0, 0.0])
    assert fi.search_similar("зовун", limit=2) == []


def test_search_similar_semantic_merges_after_fulltext_hit(tmp_path, monkeypatch):
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("зовун и другие слова", encoding="utf-8")
    (tmp_path / "b.txt").write_text("бета файл" + "а" * (fi.CHUNK_CHARS + 1),
                                    encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    res = fi.search_similar("зовун", limit=3)
    assert len(res) == 2
    assert {r["filename"] for r in res} == {"a.txt", "b.txt"}


def test_search_similar_seen_file_not_duplicated(tmp_path, monkeypatch):
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    text = "зовун и другие слова" + "а" * (fi.CHUNK_CHARS + 1)
    (tmp_path / "a.txt").write_text(text, encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    res = fi.search_similar("зовун", limit=3)
    assert len(res) == 1


def test_search_similar_fulltext_at_limit_not_extended(tmp_path, monkeypatch):
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("зовун раз", encoding="utf-8")
    (tmp_path / "b.txt").write_text("зовун два", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    res = fi.search_similar("зовун", limit=2)
    assert len(res) == 2
    assert {r["filename"] for r in res} == {"a.txt", "b.txt"}


def test_search_similar_break_mutant(tmp_path, monkeypatch):
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("зовун альфа", encoding="utf-8")
    (tmp_path / "b.txt").write_text("бета слова", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        conn.execute(
            "UPDATE embeddings SET vector = ? WHERE file_id = ?",
            (_embed_vec([0.9, 0.0, 0.0, 0.0]).tobytes(),
             fi._sha256("бета слова".encode("utf-8"))),
        )
        conn.commit()
    finally:
        conn.close()
    res = fi.search_similar("зовун", limit=3)
    assert {r["filename"] for r in res} == {"a.txt", "b.txt"}


def test_search_similar_meta_fields(tmp_path, monkeypatch):
    q = [0.7, 0.7, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("только альфа и больше ничего",
                                    encoding="utf-8")
    out = fi.index_document(str(tmp_path / "a.txt"), folder="папка")
    fi.build_embeddings()
    _insert_embedding(out["file_id"], [0.6, 0.8, 0.0, 0.0])
    res = fi.search_similar("зовун", limit=2)
    assert len(res) == 1
    r = res[0]
    assert r["filename"] == "a.txt"
    assert r["folder"] == "папка"
    assert r["snippet"] == "только альфа и больше ничего"
    vec = np.asarray([0.6, 0.8, 0.0, 0.0], dtype=np.float32)
    qnorm = np.linalg.norm(np.asarray(q, dtype=np.float32))
    score = float(np.dot(np.asarray(q, dtype=np.float32), vec)) / (qnorm * np.linalg.norm(vec))
    assert r["_score"] == round(score, 4)
    assert r["_score"] == 0.9899


def test_search_similar_empty_text_snippet(tmp_path, monkeypatch):
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    out = fi.index_document(str(tmp_path / "empty.txt"))
    _insert_embedding(out["file_id"], [1.0, 0.0, 0.0, 0.0])
    res = fi.search_similar("зовун", limit=2)
    assert len(res) == 1
    assert res[0]["snippet"] == ""


def test_search_similar_default_limit_mutant(tmp_path, monkeypatch):
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": False)
    (tmp_path / "a.txt").write_text("общий токен альфа", encoding="utf-8")
    (tmp_path / "b.txt").write_text("общий токен бета", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    res = fi.search_similar("общий", limit=1)
    assert len(res) == 1


def test_search_similar_model_args_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    called = []

    def fake_embed(inputs, model):
        called.append((inputs, model))
        assert model == fi.EMBED_MODEL
        assert inputs == ["зовун"]
        return [[1.0, 0.0, 0.0, 0.0]]

    monkeypatch.setattr(fi, "_call_embed", fake_embed)
    (tmp_path / "a.txt").write_text("альфа", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.search_similar("зовун", limit=1)
    assert called


def test_search_similar_embeddings_error_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: (_ for _ in ()).throw(
                            fi.EmbeddingsError("down")))
    (tmp_path / "a.txt").write_text("альфа", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    res = fi.search_similar("альфа", limit=1)
    assert len(res) == 1


# ---------- delete / get ----------


def test_delete_file_happy(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("контент", encoding="utf-8")
    out = fi.index_document(str(path))
    assert fi.delete_file(out["file_id"]) is True
    assert fi.get_file(out["file_id"]) is None
    assert fi.file_stats()["total_files"] == 0


def test_delete_missing():
    assert fi.delete_file("nonexistent") is False


def test_get_file_missing():
    assert fi.get_file("nonexistent") is None


# ---------- kg_log ----------


def test_kg_log_accumulates():
    fi.log_kg_facts("f1", 3)
    fi.log_kg_facts("f1", 2)
    log = fi.get_kg_log("f1")
    assert log == {"file_id": "f1", "added": 5, "error": None,
                   "created_at": log["created_at"]}
    datetime.datetime.fromisoformat(log["created_at"])
    assert log["created_at"].endswith("+00:00")
    assert fi.get_kg_log("нет") is None


# ---------- embeddings ----------


def test_build_embeddings_model_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": False)
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.build_embeddings() is False
    assert fi.file_stats()["embedded_files"] == 0


def test_build_embeddings_happy(tmp_path, monkeypatch):
    fake_vec = [0.1] * 1024
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(
        fi, "_call_embed",
        lambda inputs, model="bge-m3": [fake_vec] * len(inputs),
    )
    (tmp_path / "a.txt").write_text("текст для эмбеддингов", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.build_embeddings() is True
    stats = fi.file_stats()
    assert stats["embedded_files"] == 1
    assert stats["total_chunks"] == 1


def test_search_similar_semantic_fills(tmp_path, monkeypatch):
    fake_vec = [0.1] * 1024
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(
        fi, "_call_embed",
        lambda inputs, model="bge-m3": [fake_vec] * len(inputs),
    )
    (tmp_path / "a.txt").write_text("файл для семантики", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.build_embeddings() is True
    res = fi.search_similar("совсем другое", limit=1)
    assert len(res) == 1
    assert res[0]["file_id"] is not None


# ---------- misc ----------


def test_now_iso():
    value = fi._now()
    datetime.datetime.fromisoformat(value)
    assert value.endswith("+00:00")


def test_snippet_cuts_middle():
    text = "а" * 100 + "слово" + "б" * 100
    res = fi._snippet(text, "слово", chars=160)
    assert res == "…" + text[20:179]


def test_snippet_no_cut_when_near_start():
    text = "а" * 40 + "слово" + "б" * 100
    assert fi._snippet(text, "слово", chars=160) == text[:160]


def test_snippet_boundary_at_half():
    text = "а" * 80 + "слово" + "б" * 100
    assert fi._snippet(text, "слово", chars=160) == text[:160]


def test_snippet_no_cut_when_missing():
    text = "а" * 300
    assert fi._snippet(text, "нет", chars=160) == text[:160]


def test_snippet_short_text():
    assert fi._snippet("короткий", "короткий") == "короткий"


def test_snippet_replaces_newlines():
    text = "слово\nвторая\nстрока"
    assert fi._snippet(text, "слово") == "слово вторая строка"


def test_snippet_text_case_insensitive():
    text = "а" * 100 + "ПОИСК" + "б" * 100
    assert fi._snippet(text, "поиск", chars=160).startswith("…")


def test_snippet_query_case_insensitive():
    text = "а" * 100 + "ПОИСК" + "б" * 100
    assert fi._snippet(text, "Поиск", chars=160).startswith("…")


def test_snippet_uses_first_match():
    text = "слово" + "а" * 200 + "слово"
    assert fi._snippet(text, "слово", chars=160) == text[:160]


def test_guess_mime():
    assert fi._guess_mime("a.txt") == "text/plain"
    assert fi._guess_mime("a.md") == "text/markdown"
    assert fi._guess_mime("a.pdf") == "application/pdf"
    assert fi._guess_mime("a.xyz") == "application/octet-stream"
    assert fi._guess_mime("A.TXT") == "text/plain"
    assert fi._guess_mime("README") == "application/octet-stream"
    assert fi._guess_mime("") == "application/octet-stream"


def test_connect_sets_wal(tmp_path, monkeypatch):
    db = str(tmp_path / "wal.sqlite")
    monkeypatch.setattr(fi, "DB_FILE", db)
    real_connect = sqlite3.connect

    class SpyConn:
        def __init__(self, real):
            self.real = real
            self.seen = []

        def __getattr__(self, name):
            return getattr(self.real, name)

        def execute(self, sql, *args):
            self.seen.append(sql)
            return self.real.execute(sql, *args)

    monkeypatch.setattr(fi.sqlite3, "connect", lambda path: SpyConn(real_connect(path)))
    conn = fi._connect()
    try:
        assert any("PRAGMA journal_mode=WAL" in s for s in conn.seen)
    finally:
        conn.close()


def _canonical_sql_set():
    root = Path(__file__).resolve().parent
    if "mutants" in root.parts:
        root = root.parent.parent
    else:
        root = root.parent
    tree = ast.parse((root / "services" / "file_index.py")
                     .read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            if any(k in val for k in ("SELECT ", "INSERT ", "UPDATE ",
                                      "DELETE ", "PRAGMA ", "CREATE ")):
                found.add(val)
    for stmt in [s for s in fi.CREATE_SQL.split(";") if s.strip()]:
        found.add(stmt)
    return found


def test_executed_sql_keeps_canonical_keywords(tmp_path, monkeypatch):
    fake_vec = [0.1] * 1024
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [fake_vec] * len(inputs))
    seen = []

    class SpyConn(sqlite3.Connection):
        def execute(self, sql, *args):
            seen.append(sql)
            return super().execute(sql, *args)

        def executemany(self, sql, *args):
            seen.append(sql)
            return super().executemany(sql, *args)

    real_connect = sqlite3.connect
    monkeypatch.setattr(
        fi.sqlite3, "connect",
        lambda path: real_connect(path, factory=SpyConn),
    )
    path = tmp_path / "a.txt"
    path.write_text("некоторое слово в тексте", encoding="utf-8")
    out = fi.index_document(str(path), folder="папка")
    fi.index_document(str(path), folder="папка")
    fi.search_files("слово")
    fi.search_files("несуществующий запрос")
    fi.search_similar("слово")
    fi.build_embeddings()
    fi.build_embeddings(force=True)
    fi.get_file(out["file_id"])
    fi.delete_file(out["file_id"])
    fi.log_kg_facts("x" * 64, 1)
    fi.get_kg_log("x" * 64)
    fi.file_stats()
    canonical = _canonical_sql_set()
    assert canonical, "canonical SQL set не должен быть пустым"
    assert set(seen) <= canonical

    class FailConn:
        def __init__(self):
            self.real = real_connect(fi.DB_FILE)

        def __getattr__(self, name):
            return getattr(self.real, name)

        def execute(self, sql, *args):
            seen.append(sql)
            return self.real.execute(sql, *args)

        def executemany(self, sql, *args):
            seen.append(sql)
            return self.real.executemany(sql, *args)

        def commit(self):
            raise sqlite3.OperationalError("commit boom")

    monkeypatch.setattr(fi, "_connect", FailConn)
    fi.index_document(str(path))
    assert set(seen) <= canonical


def test_build_embeddings_empty_index(tmp_path, monkeypatch):
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    assert fi.build_embeddings() is False


def test_build_embeddings_embed_failed(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: (_ for _ in ()).throw(
                            fi.EmbeddingsError("embed boom")))
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        assert fi.build_embeddings() is False
    assert caplog.messages == ["[FILE_INDEX] embed failed: embed boom"]


def test_build_embeddings_mismatch_count(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed", lambda inputs, model: [])
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        assert fi.build_embeddings() is False
    assert caplog.messages == ["[FILE_INDEX] размер ответа не совпал: 0 != 1"]


def test_build_embeddings_write_failed(tmp_path, monkeypatch, caplog):
    fake_vec = [0.1] * 1024
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [fake_vec] * len(inputs))

    class BoomConn:
        def __init__(self):
            self.real = sqlite3.connect(fi.DB_FILE)
            for stmt in fi.CREATE_SQL.split(";"):
                if stmt.strip():
                    self.real.execute(stmt)

        def __getattr__(self, name):
            return getattr(self.real, name)

        def executemany(self, sql, *args):
            if "embeddings" in sql:
                raise sqlite3.OperationalError("write lock")
            return self.real.executemany(sql, *args)

    monkeypatch.setattr(fi, "_connect", BoomConn)
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        assert fi.build_embeddings() is False
    assert caplog.messages == ["[FILE_INDEX] embeddings write failed: write lock"]


def test_build_embeddings_force_replaces(tmp_path, monkeypatch):
    state = {"calls": 0}

    def fake_embed(inputs, model):
        state["calls"] += 1
        vec = [float(state["calls"])] + [0.0] * 1023
        return [vec] * len(inputs)

    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed", fake_embed)
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.build_embeddings() is True
    assert fi.build_embeddings(force=True) is True
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        blob = conn.execute("SELECT vector FROM embeddings").fetchone()[0]
    finally:
        conn.close()
    assert float(np.frombuffer(blob, dtype=np.float32)[0]) == 2.0


def test_build_embeddings_default_does_not_replace_vectors(tmp_path, monkeypatch):
    state = {"v": 0.5}

    def fake_embed(inputs, model):
        vec = [state["v"]] + [0.0] * 1023
        return [vec] * len(inputs)

    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed", fake_embed)
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.build_embeddings() is True
    state["v"] = 0.75
    assert fi.build_embeddings() is True
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        blob = conn.execute("SELECT vector FROM embeddings").fetchone()[0]
    finally:
        conn.close()
    assert float(np.frombuffer(blob, dtype=np.float32)[0]) == 0.5


def test_build_embeddings_chunk_indexes(tmp_path, monkeypatch):
    fake_vec = [0.1] * 1024
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [fake_vec] * len(inputs))
    text = "а" * (fi.CHUNK_CHARS + 1)
    (tmp_path / "big.txt").write_text(text, encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.build_embeddings() is True
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        idxs = [r[0] for r in conn.execute(
            "SELECT chunk_index FROM embeddings")]
    finally:
        conn.close()
    assert sorted(idxs) == [0, 1]


def test_build_embeddings_many_chunks(tmp_path, monkeypatch):
    fake_vec = [0.1] * 1024
    calls = []

    def fake_embed(inputs, model):
        calls.append(len(inputs))
        return [fake_vec] * len(inputs)

    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed", fake_embed)
    (tmp_path / "big.txt").write_text("аб" * 16000, encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.build_embeddings() is True
    assert calls == [40, 5]


def test_build_embeddings_passes_model(tmp_path, monkeypatch):
    seen = []

    def fake_embed(inputs, model):
        seen.append((inputs, model))
        assert model == fi.EMBED_MODEL
        assert isinstance(inputs, list)
        return [[0.1] * 1024] * len(inputs)

    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed", fake_embed)
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.build_embeddings() is True
    assert seen


def test_build_embeddings_unavailable_logs(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": False)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [[0.1] * 1024] * len(inputs))
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        assert fi.build_embeddings() is False
    assert caplog.messages == [
        f"[FILE_INDEX] {fi.EMBED_MODEL} недоступна — эмбеддинги файлов выключены"]


def test_build_embeddings_success_log(tmp_path, monkeypatch, caplog):
    fake_vec = [0.1] * 1024
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [fake_vec] * len(inputs))
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    with caplog.at_level(logging.INFO):
        assert fi.build_embeddings() is True
    assert caplog.messages == ["[FILE_INDEX] embeddings built: 1 chunks"]
    assert caplog.records[0].levelno == logging.INFO


def test_search_similar_dedups_chunks(tmp_path, monkeypatch):
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "big.txt").write_text("а" * (fi.CHUNK_CHARS + 1),
                                      encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    res = fi.search_similar("зовун", limit=2)
    assert len(res) == 1


def test_search_similar_skips_orphan_embedding(tmp_path, monkeypatch):
    q = [1.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(fi, "is_model_available", lambda model="x": model is not None)
    monkeypatch.setattr(fi, "_call_embed",
                        lambda inputs, model: [q] * len(inputs))
    (tmp_path / "a.txt").write_text("альфа", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    fi.build_embeddings()
    _insert_embedding("f" * 64, [1.0, 0.0, 0.0, 0.0])
    res = fi.search_similar("зовун", limit=2)
    assert [r["filename"] for r in res] == ["a.txt"]


def test_search_files_malformed_query_falls_back(tmp_path):
    (tmp_path / "a.txt").write_text("обычный текст", encoding="utf-8")
    fi.index_directory(str(tmp_path))
    assert fi.search_files('"незакрытая') == []


def test_get_file_null_extra(tmp_path):
    conn = fi._connect()
    try:
        conn.execute(
            "INSERT INTO files (file_id, filename, size, status,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?)",
            ("f" * 64, "x.txt", 0, "pending", "t", "t"),
        )
        conn.commit()
    finally:
        conn.close()
    meta = fi.get_file("f" * 64)
    assert meta["extra"] == {}
    assert meta["folder"] == ""
    assert meta["size"] == 0
    assert meta["mime"] is None


def test_index_document_timestamps_from_now(tmp_path, monkeypatch):
    counter = iter(["t1", "t2"])
    monkeypatch.setattr(fi, "_now", lambda: next(counter))
    path = tmp_path / "a.txt"
    path.write_text("контент", encoding="utf-8")
    out = fi.index_document(str(path))
    meta = fi.get_file(out["file_id"])
    assert meta["created_at"] == "t1"
    assert meta["updated_at"] == "t2"


def test_index_document_extra_keeps_unicode_unescaped(tmp_path):
    path = tmp_path / "заметка.txt"
    path.write_text("контент", encoding="utf-8")
    out = fi.index_document(str(path))
    meta = fi.get_file(out["file_id"])
    assert "заметка.txt" in meta["extra"]["path"]
    conn = sqlite3.connect(fi.DB_FILE)
    try:
        raw = conn.execute(
            "SELECT extra FROM files WHERE file_id = ?", (out["file_id"],)
        ).fetchone()[0]
    finally:
        conn.close()
    assert "\\u" not in raw


def test_index_document_write_failed_logs(tmp_path, monkeypatch, caplog):
    class BoomConn:
        def __init__(self):
            self.real = sqlite3.connect(fi.DB_FILE)
            for stmt in fi.CREATE_SQL.split(";"):
                if stmt.strip():
                    self.real.execute(stmt)

        def __getattr__(self, name):
            return getattr(self.real, name)

        def execute(self, *args, **kwargs):
            raise sqlite3.OperationalError("write lock")

    monkeypatch.setattr(fi, "_connect", BoomConn)
    path = tmp_path / "a.txt"
    path.write_text("контент", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        out = fi.index_document(str(path))
    assert out["status"] == "failed"
    assert caplog.messages == ["[FILE_INDEX] не удалось записать failed-статус: write lock"]


def test_kg_log_error_updated():
    fi.log_kg_facts("f1", 1, error="boom")
    fi.log_kg_facts("f1", 2, error="второй")
    log = fi.get_kg_log("f1")
    assert log["added"] == 3
    assert log["error"] == "второй"
    assert log["created_at"] is not None
