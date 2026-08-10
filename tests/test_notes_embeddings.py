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
    with pytest.raises(ne.EmbeddingsError, match=r"^limit должен быть ≥ 1\.$"):
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


def test_call_embed_empty_inputs(monkeypatch):
    import urllib.error
    import urllib.request

    def fake_open(req, timeout=90.0):
        raise urllib.error.URLError("no network in tests")

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
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
    with pytest.raises(ne.EmbeddingsError, match=r"^Ollama вернул пустые эмбеддинги\.$"):
        ne._call_embed(["q"])


def test_call_embed_non_dict_data(monkeypatch):
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=90.0: FakeResp("[1, 2]"),
    )
    with pytest.raises(ne.EmbeddingsError, match=r"^Ollama вернул пустые эмбеддинги\.$"):
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


class _LogRec:
    def __init__(self):
        self.calls = []

    def warning(self, msg, *args):
        self.calls.append(("warning", msg, args))

    def info(self, msg, *args):
        self.calls.append(("info", msg, args))


def test_build_index_logs_unavailable_exact(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(ne, "is_model_available", lambda model=ne.EMBED_MODEL: False)
    rec = _LogRec()
    monkeypatch.setattr(ne, "logger", rec)
    assert ne.build_index() is False
    assert rec.calls == [
        ("warning", "[SEMANTIC] %s не скачана — семантический поиск выключен", ("bge-m3",)),
    ]


def test_build_index_logs_write_failed_exact(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Н", "folder": "Ф", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    monkeypatch.setattr(ne, "_connect", lambda: (_ for _ in ()).throw(
        sqlite3.Error("cannot open"),
    ))
    rec = _LogRec()
    monkeypatch.setattr(ne, "logger", rec)
    assert ne.build_index() is False
    assert rec.calls[0][0] == "warning"
    assert rec.calls[0][1] == "[SEMANTIC] index write failed: %s"
    assert isinstance(rec.calls[0][2][0], sqlite3.Error)


def test_build_index_logs_built_exact(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Н", "folder": "Ф", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    rec = _LogRec()
    monkeypatch.setattr(ne, "logger", rec)
    assert ne.build_index(force=True) is True
    assert rec.calls == [("info", "[SEMANTIC] index built: %d notes", (1,))]


def test_build_index_forwards_model_to_is_available(fake_ollama, tmp_index, monkeypatch):
    seen = []
    monkeypatch.setattr(
        ne, "is_model_available",
        lambda model=ne.EMBED_MODEL: seen.append(model) or False,
    )
    assert ne.build_index(model="custom") is False
    assert seen == ["custom"]


def test_search_semantic_forwards_model_to_is_available(fake_ollama, tmp_index, monkeypatch):
    seen = []
    monkeypatch.setattr(
        ne, "is_model_available",
        lambda model=ne.EMBED_MODEL: seen.append(model) or False,
    )
    assert ne.search_semantic("q", model="custom") == []
    assert seen == ["custom"]


def test_search_semantic_build_gets_model(fake_ollama, tmp_index, monkeypatch):
    seen = []
    monkeypatch.setattr(ne, "build_index", lambda model=ne.EMBED_MODEL: seen.append(model) or True)
    monkeypatch.setattr(ne, "_connect", lambda: _FakeEmptyConn())
    assert ne.search_semantic("q", model="custom") == []
    assert seen == ["custom"]


def test_build_index_index_matches_gets_model(fake_ollama, tmp_index, monkeypatch):
    seen = []
    monkeypatch.setattr(ne, "is_model_available", lambda model=ne.EMBED_MODEL: True)
    monkeypatch.setattr(
        ne, "_index_matches",
        lambda conn, model=ne.EMBED_MODEL: seen.append(model) or True,
    )
    monkeypatch.setattr(ne, "_connect", lambda: _FakeEmptyConn())
    assert ne.build_index(model="cold") is True
    assert seen == ["cold"]


def test_build_index_texts_missing_name_preview(fake_ollama, tmp_index, monkeypatch):
    payload = json.dumps([{"id": "id0"}])
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: payload)
    an.get_index(force_refresh=True)
    assert ne.build_index(force=True) is True
    assert fake_ollama[0][1] == ["\n"]


def test_build_index_insert_defaults_when_keys_missing(fake_ollama, tmp_index, monkeypatch):
    payload = json.dumps([{"id": "id0"}])
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: payload)
    an.get_index(force_refresh=True)
    assert ne.build_index(force=True) is True
    conn = ne._connect()
    try:
        row = conn.execute(
            "SELECT name, folder, preview FROM notes_embeddings WHERE note_id = 'id0'",
        ).fetchone()
    finally:
        conn.close()
    assert row == ("", "", "")


def test_build_index_stores_exact_preview(fake_ollama, tmp_index, monkeypatch):
    payload = json.dumps([
        {"id": "id0", "name": "Н", "folder": "Ф", "preview": "Воля и представление", "updated": ""},
    ])
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: payload)
    an.get_index(force_refresh=True)
    assert ne.build_index(force=True) is True
    conn = ne._connect()
    try:
        row = conn.execute(
            "SELECT preview FROM notes_embeddings WHERE note_id = 'id0'",
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Воля и представление",)


def test_build_index_truncates_preview_to_500(fake_ollama, tmp_index, monkeypatch):
    payload = json.dumps([
        {"id": "id0", "name": "Н", "folder": "Ф", "preview": "x" * 550, "updated": ""},
    ])
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: payload)
    an.get_index(force_refresh=True)
    assert ne.build_index(force=True) is True
    conn = ne._connect()
    try:
        row = conn.execute(
            "SELECT length(preview) FROM notes_embeddings WHERE note_id = 'id0'",
        ).fetchone()
    finally:
        conn.close()
    assert row == (500,)


def test_build_index_continues_after_wrong_dim(fake_ollama, tmp_index, monkeypatch):
    def _embed(inputs, model=ne.EMBED_MODEL):
        return [[0.0] * (5 if "bad" in t else ne.EMBED_DIM) for t in inputs]

    monkeypatch.setattr(ne, "_call_embed", _embed)
    payload = json.dumps([
        {"id": "id0", "name": "good1", "folder": "Ф", "preview": "", "updated": ""},
        {"id": "id1", "name": "bad", "folder": "Ф", "preview": "", "updated": ""},
        {"id": "id2", "name": "good2", "folder": "Ф", "preview": "", "updated": ""},
    ])
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: payload)
    an.get_index(force_refresh=True)
    assert ne.build_index(force=True) is True
    conn = ne._connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM notes_embeddings").fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def _qvec():
    q = np.zeros(ne.EMBED_DIM, dtype=np.float32)
    q[0] = 1.0
    return q


def _ones_blob():
    return np.ones(ne.EMBED_DIM, dtype=np.float32).tobytes()


def _insert_rows(monkeypatch, tmp_db, rows):
    conn = ne._connect()
    try:
        conn.execute("DELETE FROM notes_embeddings")
        for row in rows:
            conn.execute(
                "INSERT INTO notes_embeddings "
                "(note_id, name, folder, preview, vector, model) VALUES (?,?,?,?,?,?)",
                row,
            )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(ne, "is_model_available", lambda model=ne.EMBED_MODEL: True)
    monkeypatch.setattr(ne, "build_index", lambda model=ne.EMBED_MODEL: True)
    monkeypatch.setattr(ne, "_call_embed", lambda inputs, model=ne.EMBED_MODEL: [_qvec().tolist()])


def test_search_semantic_skips_bad_dim_and_zero_score(fake_ollama, tmp_index, monkeypatch):
    zero_blob = np.zeros(ne.EMBED_DIM, dtype=np.float32).tobytes()
    import os
    os.makedirs(os.path.dirname(ne.DB_FILE), exist_ok=True)
    _insert_rows(monkeypatch, tmp_index, [
        ("a", "Про кофе", "Быт", "", _ones_blob(), ne.EMBED_MODEL),
        ("b", "Плохо", "Быт", "", b"\x00\x00\x00\x00", ne.EMBED_MODEL),
        ("c", "Кофе снова", "Быт", "", _ones_blob(), ne.EMBED_MODEL),
        ("d", "Ортогонально", "Быт", "", zero_blob, ne.EMBED_MODEL),
    ])
    monkeypatch.setattr(ne, "_cosine", lambda a, b: (1.0 if b[0] else 0.0))
    result = ne.search_semantic("кофе", limit=10)
    assert len(result) == 2


def test_search_semantic_null_fields_defaults(fake_ollama, tmp_index, monkeypatch):
    import os
    os.makedirs(os.path.dirname(ne.DB_FILE), exist_ok=True)
    _insert_rows(monkeypatch, tmp_index, [
        ("x", None, None, None, _ones_blob(), ne.EMBED_MODEL),
    ])
    result = ne.search_semantic("кофе", limit=10)
    assert result[0]["name"] == "?"
    assert result[0]["folder"] == "?"
    assert result[0]["snippet"] == ""
    assert set(result[0].keys()) == {"id", "name", "folder", "snippet", "_score"}


def test_search_semantic_snippet_truncated(fake_ollama, tmp_index, monkeypatch):
    import os
    os.makedirs(os.path.dirname(ne.DB_FILE), exist_ok=True)
    long_preview = "абвгд" * 60
    _insert_rows(monkeypatch, tmp_index, [
        ("x", "Имя", "Папка", long_preview, _ones_blob(), ne.EMBED_MODEL),
    ])
    result = ne.search_semantic("кофе", limit=10)
    assert result[0]["snippet"] == long_preview[:ne.SNIPPET_CHARS]


def test_search_semantic_limit_one_works(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps([
        {"id": "id0", "name": "Про кофе", "folder": "Быт", "preview": "", "updated": ""},
        {"id": "id1", "name": "Про чай", "folder": "Быт", "preview": "", "updated": ""},
    ]))
    an.get_index(force_refresh=True)
    assert len(ne.search_semantic("кофе", limit=1)) == 1


def test_search_semantic_logs_build_failed_exact(fake_ollama, tmp_index, monkeypatch):
    monkeypatch.setattr(ne, "build_index", lambda model=ne.EMBED_MODEL: (_ for _ in ()).throw(
        ne.EmbeddingsError("boom"),
    ))
    monkeypatch.setattr(ne, "_connect", lambda: _FakeEmptyConn())
    rec = _LogRec()
    monkeypatch.setattr(ne, "logger", rec)
    assert ne.search_semantic("q") == []
    assert rec.calls[0][0] == "warning"
    assert rec.calls[0][1] == "[SEMANTIC] build failed: %s"
    assert isinstance(rec.calls[0][2][0], ne.EmbeddingsError)


def test_search_semantic_logs_embed_failed_exact(fake_ollama, tmp_index, monkeypatch):
    import os
    os.makedirs(os.path.dirname(ne.DB_FILE), exist_ok=True)
    _insert_rows(monkeypatch, tmp_index, [
        ("x", "Имя", "Папка", "",
         _ones_blob(), ne.EMBED_MODEL),
    ])
    monkeypatch.setattr(
        ne, "_call_embed",
        lambda inputs, model=ne.EMBED_MODEL: (_ for _ in ()).throw(
            ne.EmbeddingsError("down"),
        ))
    rec = _LogRec()
    monkeypatch.setattr(ne, "logger", rec)
    assert ne.search_semantic("кофе") == []
    assert rec.calls[0][0] == "warning"
    assert rec.calls[0][1] == "[SEMANTIC] query embed failed: %s"
    assert isinstance(rec.calls[0][2][0], ne.EmbeddingsError)


def test_hybrid_limit_one_works(monkeypatch):
    monkeypatch.setattr(an, "search_notes", lambda q, limit=10: [])
    monkeypatch.setattr(ne, "search_semantic", lambda q, limit=10: [])
    assert ne.search_notes_hybrid("x", limit=1) == []


def test_hybrid_passes_limit_down(monkeypatch):
    caps = {}

    def _ft(q, limit=10):
        caps["ft"] = limit
        return []

    def _sem(q, limit=10):
        caps["sem"] = limit
        return []

    monkeypatch.setattr(an, "search_notes", _ft)
    monkeypatch.setattr(ne, "search_semantic", _sem)
    ne.search_notes_hybrid("x", limit=4)
    assert caps == {"ft": 4, "sem": 4}


def test_hybrid_dedup_and_break_with_mocks(monkeypatch):
    def _ft(q, limit=10):
        return [{"id": "a", "name": "n", "folder": "f", "snippet": "s"}]

    def _sem(q, limit=10):
        return [
            {"id": "a", "name": "n", "folder": "f", "snippet": "s"},
            {"id": "b", "name": "n", "folder": "f", "snippet": "s"},
            {"id": "c", "name": "n", "folder": "f", "snippet": "s"},
        ]

    monkeypatch.setattr(an, "search_notes", _ft)
    monkeypatch.setattr(ne, "search_semantic", _sem)
    result = ne.search_notes_hybrid("x", limit=2)
    assert [r["id"] for r in result] == ["a", "b"]


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


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestCallEmbedHTTPPayloadMutants:
    def test_call_embed_sends_exact_payload(self, monkeypatch):
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["data"] = req.data
            captured["timeout"] = timeout
            captured["headers"] = req.headers
            return _FakeResp(
                json.dumps({"embeddings": [[0.1] * ne.EMBED_DIM]}).encode("utf-8"),
            )

        monkeypatch.setattr(ne.urllib.request, "urlopen", fake_urlopen)
        result = ne._call_embed(["Привет мир"], model="bge-m3")
        assert len(result) == 1
        payload = json.loads(captured["data"].decode("utf-8"))
        assert payload == {"model": "bge-m3", "input": ["Привет мир"]}
        assert captured["url"] == ne.EMBED_URL
        assert captured["timeout"] == 90.0
        assert "\\u041f" not in captured["data"].decode("utf-8")
        headers = {k.lower(): v for k, v in captured["headers"].items()}
        assert headers.get("content-type") == "application/json"

    def test_call_embed_raises_when_embeddings_missing(self, monkeypatch):
        def fake_urlopen(req, timeout=90.0):
            return _FakeResp(b"{}")

        monkeypatch.setattr(ne.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(ne.EmbeddingsError):
            ne._call_embed(["q"])


class TestIsModelAvailableHTTPPayloadMutants:
    def test_show_sends_exact_payload_and_url(self, monkeypatch):
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["data"] = req.data
            captured["timeout"] = timeout
            captured["headers"] = req.headers
            return _FakeResp(b'{"model": "bge-m3"}')

        monkeypatch.setattr(ne.urllib.request, "urlopen", fake_urlopen)
        assert ne.is_model_available("bge-m3") is True
        assert captured["url"] == "http://localhost:11434/api/show"
        assert json.loads(captured["data"]) == {"model": "bge-m3"}
        assert captured["timeout"] == 10.0
        headers = {k.lower(): v for k, v in captured["headers"].items()}
        assert headers.get("content-type") == "application/json"

    def test_show_returns_false_on_http_error(self, monkeypatch):
        def fake_urlopen(req, timeout=10.0):
            raise ne.urllib.error.URLError("boom")

        monkeypatch.setattr(ne.urllib.request, "urlopen", fake_urlopen)
        assert ne.is_model_available("bge-m3") is False


class TestConnectSQLLiterals:
    def test_connect_creates_table_exact_sql(self, monkeypatch, tmp_db):
        sqls = []

        class _FakeSqliteConn:
            def execute(self, sql, params=None):
                sqls.append(sql)
                return self

            def close(self):
                pass

        monkeypatch.setattr(ne.sqlite3, "connect", lambda path: _FakeSqliteConn())
        conn = ne._connect()
        conn.close()
        assert sqls == [
            "CREATE TABLE IF NOT EXISTS notes_embeddings ("
            "note_id TEXT PRIMARY KEY, name TEXT, folder TEXT, preview TEXT, "
            "vector BLOB NOT NULL, model TEXT NOT NULL)",
        ]


def test_build_index_passes_model_and_texts(fake_ollama, tmp_index, monkeypatch):
    """В build_index сохраняется кастомная модель и дефолты '' вместо None/мусора."""
    payload = json.dumps([
        {"id": "id0", "name": "Н", "folder": "Ф"},
        {"id": "id1", "name": "Б", "folder": "Ф"},
        {"id": "id2"},
    ])
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: payload)
    an.get_index(force_refresh=True)
    seen = {}

    def fake_embed(inputs, model=ne.EMBED_MODEL):
        seen["model"] = model
        seen["texts"] = list(inputs)
        return [[0.1] * ne.EMBED_DIM] * len(inputs)

    monkeypatch.setattr(ne, "_call_embed", fake_embed)
    assert ne.build_index(force=True, model="custom-model") is True
    assert seen["model"] == "custom-model"
    assert seen["texts"] == ["Н\n", "Б\n", "\n"]


def test_search_semantic_score_model(fake_ollama, tmp_index, monkeypatch):
    """_score округляется до 4 знаков, запрос идёт кастомной моделью."""
    _seed_index(fake_ollama, tmp_index, monkeypatch, [("Заметка", "Ф", "")])
    seen = {}

    def fake_embed(inputs, model=ne.EMBED_MODEL):
        seen["model"] = model
        return [[0.3] * ne.EMBED_DIM]

    monkeypatch.setattr(ne, "_call_embed", fake_embed)
    result = ne.search_semantic("q", model="custom-model")
    assert seen["model"] == "custom-model"
    assert len(result) == 1
    assert result[0]["_score"] == round(result[0]["_score"], 4)
