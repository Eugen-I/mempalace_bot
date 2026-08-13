"""Unit-тесты для services.memory_embeddings — семантический поиск фактов памяти.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
HTTP и osascript замоканы; DB_FILE и memory_dir перенаправляются в tmp_path.
Векторы — детерминированные фейки (ортогональные единичные, bag-of-words).
"""

import json
import sqlite3

import numpy as np
import pytest

import services.memory as mem
from services import memory_embeddings as me
from services.notes_embeddings import EmbeddingsError


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(me, "DB_FILE", str(tmp_path / "memory_emb.sqlite"))
    return tmp_path


@pytest.fixture
def tmp_mem_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(mem, "_memory_dir", lambda: str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_ollama(monkeypatch, tmp_db, tmp_mem_dir):
    """Мокает /api/embed: bag-of-words векторы (детерминированно).

    Слово w → компонент sum(ord(c)) % EMBED_DIM. Общие слова между
    запросом и фактом дают ненулевой косинус, чужие — нулевой.
    """
    calls = []

    def _embed(inputs, model=me.EMBED_MODEL):
        calls.append((model, inputs))
        out = []
        for t in inputs:
            v = np.zeros(me.EMBED_DIM, dtype=np.float32)
            for w in set(t.lower().split()):
                v[sum(ord(c) for c in w) % me.EMBED_DIM] += 1.0
            out.append(v.tolist())
        return out

    monkeypatch.setattr(me, "_call_embed", _embed)
    monkeypatch.setattr(me, "is_model_available", lambda model=me.EMBED_MODEL: True)
    return calls


def _write_facts(tmp_path, user_id, facts):
    (tmp_path / f"mem_{user_id}.json").write_text(
        json.dumps([{"fact": f} for f in facts], ensure_ascii=False),
        encoding="utf-8",
    )


# ─── build_index ───


def test_build_index_stores_vectors(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["Люблю Python"])
    assert me.build_index(1) is True
    conn = me._connect()
    try:
        row = conn.execute(
            "SELECT user_id, fact, model FROM memory_embeddings",
        ).fetchone()
    finally:
        conn.close()
    assert row == (1, "Люблю Python", me.EMBED_MODEL)


def test_build_index_skips_wrong_dim(fake_ollama, tmp_mem_dir, monkeypatch):
    monkeypatch.setattr(me, "_call_embed", lambda inputs, model=me.EMBED_MODEL: [
        [1.0, 2.0],
    ])
    _write_facts(tmp_mem_dir, 1, ["факт"])
    me.build_index(1)
    conn = me._connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0] == 0
    finally:
        conn.close()


def test_build_index_model_unavailable(fake_ollama, tmp_mem_dir, monkeypatch):
    monkeypatch.setattr(me, "is_model_available", lambda model=me.EMBED_MODEL: False)
    _write_facts(tmp_mem_dir, 1, ["факт"])
    assert me.build_index(1) is False


def test_build_index_empty_facts(fake_ollama, tmp_mem_dir):
    assert me.build_index(1) is False


def test_build_index_skips_if_matches(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["факт A"])
    me.build_index(1)
    calls_before = len(fake_ollama)
    assert me.build_index(1) is True
    assert len(fake_ollama) == calls_before


def test_build_index_rebuilds_when_facts_changed(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["факт A"])
    me.build_index(1)
    _write_facts(tmp_mem_dir, 1, ["факт A", "факт B"])
    assert me.build_index(1) is True
    conn = me._connect()
    try:
        rows = conn.execute("SELECT fact FROM memory_embeddings").fetchall()
    finally:
        conn.close()
    assert {r[0] for r in rows} == {"факт A", "факт B"}


def test_build_index_batches(fake_ollama, tmp_mem_dir, monkeypatch):
    monkeypatch.setattr(me, "BATCH_SIZE", 2)
    _write_facts(tmp_mem_dir, 1, [str(i) for i in range(5)])
    me.build_index(1)
    assert [model for model, _ in fake_ollama] == [me.EMBED_MODEL] * 3


def test_build_index_isolates_users(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["факт юзера одного"])
    _write_facts(tmp_mem_dir, 2, ["факт юзера двух"])
    me.build_index(1)
    me.build_index(2)
    conn = me._connect()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings WHERE user_id = 1",
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings WHERE user_id = 2",
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_build_index_index_matches_uses_same_model(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["факт"])
    me.build_index(1, model="bge-m3")
    monkeypatch_conn = me._connect()
    try:
        assert me._index_matches(monkeypatch_conn, 1, "bge-m3") is True
        assert me._index_matches(monkeypatch_conn, 1, "other-model") is False
    finally:
        monkeypatch_conn.close()


def test_build_index_force_rebuilds_even_when_matches(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["факт"])
    me.build_index(1)
    calls_before = len(fake_ollama)
    assert me.build_index(1, force=True) is True
    assert len(fake_ollama) == calls_before + 1


def test_index_matches_returns_false_on_db_error(fake_ollama, tmp_mem_dir):
    class BoomConn:
        def execute(self, *a, **k):
            raise sqlite3.Error("locked")

    assert me._index_matches(BoomConn(), 1) is False


def test_build_index_db_failure_returns_false(fake_ollama, tmp_mem_dir, caplog):
    _write_facts(tmp_mem_dir, 1, ["факт"])

    def boom(*a, **k):
        raise sqlite3.Error("disk full")

    monkeypatch_orig = me._connect
    me._connect = boom
    try:
        assert me.build_index(1) is False
    finally:
        me._connect = monkeypatch_orig
    assert "index write failed" in caplog.text


# ─── search_similar ───


def test_search_similar_returns_sorted(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["Про кофе", "Шопенгауэр и воля"])
    result = me.search_similar("кофе", 1)
    assert result[0]["fact"] == "Про кофе"
    assert result[0]["_score"] > 0


def test_search_similar_limit(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["Абв", "Абв г", "Абв д е"])
    assert len(me.search_similar("абв", 1, limit=2)) == 2


def test_search_similar_limit_zero(fake_ollama, tmp_mem_dir):
    with pytest.raises(EmbeddingsError, match=r"^limit должен быть ≥ 1\.$"):
        me.search_similar("q", 1, limit=0)


def test_search_similar_model_unavailable(fake_ollama, tmp_mem_dir, monkeypatch):
    monkeypatch.setattr(me, "is_model_available", lambda model=me.EMBED_MODEL: False)
    assert me.search_similar("q", 1) == []


def test_search_similar_empty_index(fake_ollama, tmp_mem_dir):
    assert me.search_similar("q", 1) == []


def test_search_similar_empty_query(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["факт"])
    assert me.search_similar("   ", 1) == []


def test_search_similar_embed_failure(fake_ollama, tmp_mem_dir, monkeypatch):
    _write_facts(tmp_mem_dir, 1, ["факт"])
    monkeypatch.setattr(
        me, "_call_embed",
        lambda inputs, model=me.EMBED_MODEL: (_ for _ in ()).throw(
            EmbeddingsError("down"),
        ),
    )
    assert me.search_similar("q", 1) == []


def test_search_similar_query_embed_failure_after_build(fake_ollama, tmp_mem_dir,
                                                        monkeypatch):
    """Индекс построен, но эмбеддинг запроса падает — graceful []."""
    _write_facts(tmp_mem_dir, 1, ["факт"])
    me.build_index(1)
    orig = me._call_embed

    def failing_query(inputs, model=me.EMBED_MODEL):
        if len(inputs) == 1:
            raise EmbeddingsError("query down")
        return orig(inputs, model)

    monkeypatch.setattr(me, "_call_embed", failing_query)
    assert me.search_similar("q", 1) == []


def test_search_similar_skips_wrong_dim_row(fake_ollama, tmp_mem_dir, monkeypatch):
    """Строки с кривым размером/битым BLOB пропускаются при поиске."""
    _write_facts(tmp_mem_dir, 1, ["нормальный факт"])
    me.build_index(1)
    conn = me._connect()
    try:
        conn.execute(
            "INSERT INTO memory_embeddings (user_id, fact, vector, model) "
            "VALUES (?,?,?,?)",
            (1, "кривой", b"\x00\x01\x02", me.EMBED_MODEL),
        )
        conn.execute(
            "INSERT INTO memory_embeddings (user_id, fact, vector, model) "
            "VALUES (?,?,?,?)",
            (1, "короткий", b"\x00" * 8, me.EMBED_MODEL),
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(me, "_index_matches", lambda conn, uid, model=None: True)
    result = me.search_similar("кривой", 1)
    assert "кривой" not in [r["fact"] for r in result]
    assert "короткий" not in [r["fact"] for r in result]


def test_search_similar_does_not_leak_other_users(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["Секрет единицы"])
    _write_facts(tmp_mem_dir, 2, ["Секрет двойки"])
    result = me.search_similar("секрет", 1)
    assert [r["fact"] for r in result] == ["Секрет единицы"]


def test_search_similar_negative_or_zero_score_excluded(fake_ollama, tmp_mem_dir):
    _write_facts(tmp_mem_dir, 1, ["Совсем другое содержание"])
    result = me.search_similar("кофе", 1)
    assert result == []
