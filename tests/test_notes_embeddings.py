"""Unit-тесты для services.notes_embeddings — семантический поиск.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
HTTP и osascript замоканы; DB_FILE перенаправляется в tmp_path.
Векторы — детерминированные фейки (ортогональные единичные).
"""

import json
import sqlite3

import numpy as np
import pytest

from services import apple_notes as an
from services import notes_embeddings as ne
from services.apple_notes import AppleNotesError


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(ne, "DB_FILE", str(tmp_path / "emb.sqlite"))
    return tmp_path


@pytest.fixture
def fake_ollama(monkeypatch, tmp_db):
    """Мокает /api/embed: bag-of-words векторы (детерминированно).

    Слово w → компонент sum(ord(c)) % EMBED_DIM. Общие слова между
    запросом и заметкой дают ненулевой косинус, чужие — нулевой.
    """
    calls = []

    def _embed(inputs, model=ne.EMBED_MODEL):
        calls.append((model, inputs))
        out = []
        for t in inputs:
            v = np.zeros(ne.EMBED_DIM, dtype=np.float32)
            for w in set(t.lower().split()):
                v[sum(ord(c) for c in w) % ne.EMBED_DIM] += 1.0
            out.append(v.tolist())
        return out

    monkeypatch.setattr(ne, "_call_embed", _embed)
    monkeypatch.setattr(ne, "is_model_available", lambda model=ne.EMBED_MODEL: True)
    return calls


@pytest.fixture
def tmp_index(monkeypatch, tmp_path):
    index_file = tmp_path / "notes_index.json"
    monkeypatch.setattr(an, "INDEX_FILE", str(index_file))
    return index_file


def _seed_index(fake_ollama, tmp_index, monkeypatch, notes):
    """Классический путь: заметки в индексе apple_notes → build_index."""
    payload = json.dumps([
        {"id": f"id{i}", "name": n, "folder": f, "preview": p, "updated": ""}
        for i, (n, f, p) in enumerate(notes)
    ])
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: payload)
    an.get_index(force_refresh=True)
    assert ne.build_index(force=True) is True


# ─── build_index ───


def test_build_index_stores_vectors(fake_ollama, tmp_index, monkeypatch):
    _seed_index(
        fake_ollama, tmp_index, monkeypatch,
        [("О Шопенгауэре", "Философия", "Воля и представление")],
    )
    conn = ne._connect()
    try:
        row = conn.execute("SELECT name, model FROM notes_embeddings").fetchone()
    finally:
        conn.close()
    assert row == ("О Шопенгауэре", ne.EMBED_MODEL)


def test_build_index_skips_wrong_dim(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(ne, "_call_embed", lambda inputs, model=ne.EMBED_MODEL: [
        [1.0, 2.0],
    ])
    payload = json.dumps([{"id": "id0", "name": "Н", "folder": "Ф", "preview": "", "updated": ""}])
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: payload)
    an.get_index(force_refresh=True)
    ne.build_index(force=True)
    conn = ne._connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM notes_embeddings").fetchone()[0] == 0
    finally:
        conn.close()


def test_build_index_model_unavailable(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(ne, "is_model_available", lambda model=ne.EMBED_MODEL: False)
    payload = json.dumps([{"id": "id0", "name": "Н", "folder": "Ф", "preview": "", "updated": ""}])
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: payload)
    an.get_index(force_refresh=True)
    assert ne.build_index(force=True) is False


def test_build_index_skips_if_matches(fake_ollama, tmp_index, monkeypatch):
    _seed_index(fake_ollama, tmp_index, monkeypatch, [("А", "Ф", "")])
    calls_before = len(fake_ollama)
    assert ne.build_index() is True
    assert len(fake_ollama) == calls_before


def test_build_index_batches(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(ne, "BATCH_SIZE", 2)
    notes = [(f"Н{i}", "Ф", "") for i in range(5)]
    _seed_index(fake_ollama, tmp_index, monkeypatch, notes)
    assert [m for m, _ in fake_ollama] == [ne.EMBED_MODEL] * 3


# ─── search_semantic ───


def test_search_semantic_returns_sorted(fake_ollama, tmp_index, monkeypatch):
    _seed_index(fake_ollama, tmp_index, monkeypatch, [
        ("Про кофе", "Быт", ""),
        ("Шопенгауэр и воля", "Философия", ""),
    ])
    result = ne.search_semantic("кофе")
    assert result[0]["name"] == "Про кофе"
    assert "id0" in result[0]["id"]
    assert result[0]["_score"] > 0


def test_search_semantic_limit(fake_ollama, tmp_index, monkeypatch):
    _seed_index(fake_ollama, tmp_index, monkeypatch, [
        ("Абв", "Ф", ""), ("Абв г", "Ф", ""), ("Абв д е", "Ф", ""),
    ])
    assert len(ne.search_semantic("абв", limit=2)) == 2


def test_search_semantic_limit_zero(fake_ollama, tmp_index):
    with pytest.raises(ne.EmbeddingsError, match="limit"):
        ne.search_semantic("q", limit=0)


def test_search_semantic_model_unavailable(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(ne, "is_model_available", lambda model=ne.EMBED_MODEL: False)
    assert ne.search_semantic("q") == []


def test_search_semantic_empty_index(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([]))
    an.get_index(force_refresh=True)
    assert ne.search_semantic("q") == []


def test_search_semantic_embed_failure(fake_ollama, tmp_index, monkeypatch):
    _seed_index(fake_ollama, tmp_index, monkeypatch, [("Н", "Ф", "")])
    monkeypatch.setattr(
        ne, "_call_embed",
        lambda inputs, model=ne.EMBED_MODEL: (_ for _ in ()).throw(
            ne.EmbeddingsError("down"),
        ),
    )
    assert ne.search_semantic("q") == []


def test_cosine_zero_vector():
    assert ne._cosine(np.zeros(4, dtype=np.float32), np.ones(4, dtype=np.float32)) == 0.0


def test_cosine_parallel_is_one():
    v = np.ones(8, dtype=np.float32)
    assert ne._cosine(v, v) == pytest.approx(1.0, abs=1e-6)


# ─── search_notes_hybrid ───


def test_hybrid_fulltext_first_then_semantic(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Идеи для отпуска", "folder": "Личное", "preview": "", "updated": ""},
        {"id": "id1", "name": "Планы", "folder": "Личное", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    ne.build_index(force=True)
    result = ne.search_notes_hybrid("идеи")
    ids = [r["id"] for r in result]
    assert ids[0] == "id0"  # полнотекстовое совпадение первым


def test_hybrid_dedup(fake_ollama, tmp_index, monkeypatch):
    """Заметка, найденная обоими путями, не дублируется."""
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Про кофе", "folder": "Быт", "preview": "", "updated": ""},
        {"id": "id1", "name": "Другое", "folder": "Быт", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    ne.build_index(force=True)
    result = ne.search_notes_hybrid("кофе", limit=10)
    ids = [r["id"] for r in result]
    assert len(ids) == len(set(ids))
    assert "id0" in ids


def test_hybrid_semantic_failure_falls_back(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Шопенгауэр", "folder": "Ф", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    monkeypatch.setattr(ne, "search_semantic", lambda q, limit=10: (
        (_ for _ in ()).throw(ne.EmbeddingsError("down"))
    ))
    result = ne.search_notes_hybrid("шопенгауэр")
    assert [r["id"] for r in result] == ["id0"]


def test_hybrid_limit_zero():
    with pytest.raises(AppleNotesError, match="limit"):
        ne.search_notes_hybrid("q", limit=0)


def test_hybrid_empty_query(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "А", "folder": "Ф", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    with pytest.raises(AppleNotesError, match="Пустой"):
        ne.search_notes_hybrid("   ")


# ─── HTTP-уровень (_call_embed, is_model_available) ───


def test_call_embed_ok(monkeypatch):
    import urllib.request

    def fake_open(req, timeout=90.0):
        assert ne.EMBED_URL == req.full_url
        return FakeResp(json.dumps({"embeddings": [[0.1] * ne.EMBED_DIM]}))

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    out = ne._call_embed(["текст"])
    assert len(out) == 1 and len(out[0]) == ne.EMBED_DIM


def test_call_embed_empty_inputs():
    assert ne._call_embed([]) == []


def test_call_embed_network_error(monkeypatch):
    import urllib.error
    import urllib.request

    def fake_open(req, timeout=90.0):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    with pytest.raises(ne.EmbeddingsError, match="недоступен"):
        ne._call_embed(["q"])


def test_call_embed_empty_embeddings(monkeypatch):
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=90.0: FakeResp('{"embeddings": []}'),
    )
    with pytest.raises(ne.EmbeddingsError, match="пустые"):
        ne._call_embed(["q"])


def test_call_embed_non_dict_data(monkeypatch):
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=90.0: FakeResp("[1, 2]"),
    )
    with pytest.raises(ne.EmbeddingsError, match="пустые"):
        ne._call_embed(["q"])


def test_is_model_available_true(monkeypatch):
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=10.0: FakeResp(json.dumps({"model": "bge-m3"})),
    )
    assert ne.is_model_available() is True


def test_is_model_available_via_model_info(monkeypatch):
    """Ollama отвечает model=None, но model_info заполнен (реальный кейс)."""
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=10.0: FakeResp(
            json.dumps({"model": None, "model_info": {"x": "y"}}),
        ),
    )
    assert ne.is_model_available() is True


def test_is_model_available_missing_model(monkeypatch):
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=10.0: FakeResp("{}"),
    )
    assert ne.is_model_available() is False


def test_is_model_available_error(monkeypatch):
    import urllib.error
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=10.0: (_ for _ in ()).throw(
            urllib.error.URLError("down"),
        ),
    )
    assert ne.is_model_available() is False


# ─── Ветки ошибок ───


def test_index_matches_sqlite_error(tmp_db, monkeypatch):
    conn = _BrokenConn()
    assert ne._index_matches(conn) is False


def test_build_index_sqlite_error_on_check(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(ne, "_connect", _BrokenConn)
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Н", "folder": "Ф", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    assert ne.build_index() is False


def test_build_index_no_notes(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(ne, "_connect", _FakeEmptyConn)
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([]))
    an.get_index(force_refresh=True)
    assert ne.build_index() is False


def test_search_semantic_build_failure(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Н", "folder": "Ф", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    monkeypatch.setattr(
        ne, "_call_embed",
        lambda inputs, model=ne.EMBED_MODEL: (_ for _ in ()).throw(
            ne.EmbeddingsError("model gone"),
        ),
    )
    assert ne.search_semantic("q") == []


def test_search_semantic_bad_vector_rows(fake_ollama, tmp_index, monkeypatch):
    """Векторы неверной размерности в БД пропускаются."""
    _seed_index(fake_ollama, tmp_index, monkeypatch, [("А", "Ф", "")])
    conn = ne._connect()
    try:
        conn.execute("UPDATE notes_embeddings SET vector = ?", (b"\x00\x00\x00\x00",))
        conn.commit()
    finally:
        conn.close()
    assert ne.search_semantic("а") == []


def test_hybrid_break_at_limit(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Про кофе", "folder": "Быт", "preview": "", "updated": ""},
        {"id": "id1", "name": "Кофе дома", "folder": "Быт", "preview": "", "updated": ""},
        {"id": "id2", "name": "", "folder": "Быт", "preview": "кофе", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    ne.build_index(force=True)
    result = ne.search_notes_hybrid("кофе", limit=2)
    assert [r["id"] for r in result] == ["id0", "id1", "id2"]


def test_build_index_connect_error(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Н", "folder": "Ф", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    monkeypatch.setattr(ne, "_connect", lambda: (_ for _ in ()).throw(
        sqlite3.Error("cannot open"),
    ))
    assert ne.build_index() is False


class FakeResp:
    def __init__(self, body):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _BrokenConn:
    def execute(self, *a, **k):
        raise sqlite3.Error("corrupt")

    def close(self):
        pass


class _FakeEmptyConn:
    def __init__(self):
        self._rows = []

    def execute(self, query, params=None):
        if query.startswith("SELECT COUNT(*)"):
            return _CountResult(5)  # count != 0 → не совпадает с пустым индексом
        return _RowsResult(self._rows)

    def close(self):
        pass


class _CountResult:
    def __init__(self, n):
        self._n = n

    def fetchone(self):
        return (self._n,)


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows
