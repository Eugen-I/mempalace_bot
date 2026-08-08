"""Тесты services/memory.py — долговременная память.

Покрытие: хранение фактов, поиск, извлечение, границы.
"""
import asyncio
import json
import os

import pytest

import services.memory as memory


@pytest.fixture
def mem_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "_memory_dir", lambda: str(tmp_path))
    return tmp_path


def _write_memories(tmp_path, user_id, memories):
    path = tmp_path / f"mem_{user_id}.json"
    path.write_text(json.dumps(memories, ensure_ascii=False), encoding="utf-8")
    return path


# ─── _load_memories / _save_memories ───


def test_load_memories_missing_file(mem_dir):
    assert memory._load_memories(999) == []


def test_load_memories_corrupt_file(mem_dir):
    (mem_dir / "mem_1.json").write_text("{не json", encoding="utf-8")
    assert memory._load_memories(1) == []


def test_load_memories_ok(mem_dir):
    _write_memories(mem_dir, 1, [{"fact": "f1"}])
    assert memory._load_memories(1) == [{"fact": "f1"}]


def test_save_memories_roundtrip(mem_dir):
    memory._save_memories(1, [{"fact": "hello"}])
    assert json.loads((mem_dir / "mem_1.json").read_text(encoding="utf-8")) == [
        {"fact": "hello"}
    ]


def test_save_memories_unwritable_dir_logs_error(mem_dir, caplog):
    memory._save_memories(1, [{"fact": "x"}])
    assert (mem_dir / "mem_1.json").exists()


def test_save_memories_replace_error_logged(mem_dir, caplog, monkeypatch):
    def boom(*a, **k):
        raise OSError("busy")

    monkeypatch.setattr(memory.os, "replace", boom)
    memory._save_memories(1, [{"fact": "x"}])
    assert "Save error" in caplog.text


def test_memory_dir_creates_under_data_dir(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    d = memory._memory_dir()
    assert d == str(tmp_path / "memory_store")
    assert os.path.isdir(d)


# ─── retrieve_facts ───


def test_retrieve_facts_empty_memory(mem_dir):
    assert memory.retrieve_facts("query", 1) == []


def test_retrieve_facts_empty_query(mem_dir):
    _write_memories(mem_dir, 1, [{"fact": "Люблю Python"}])
    assert memory.retrieve_facts("", 1) == []


def test_retrieve_facts_query_only_symbols(mem_dir):
    _write_memories(mem_dir, 1, [{"fact": "Люблю Python"}])
    assert memory.retrieve_facts("!!!", 1) == []


def test_retrieve_facts_word_match(mem_dir):
    _write_memories(
        mem_dir, 1, [{"fact": "Люблю Python"}, {"fact": "Люблю coffee"}]
    )
    result = memory.retrieve_facts("python", 1)
    assert result == ["Люблю Python"]


def test_retrieve_facts_case_insensitive(mem_dir):
    _write_memories(mem_dir, 1, [{"fact": "Люблю PYTHON"}])
    assert memory.retrieve_facts("python", 1) == ["Люблю PYTHON"]


def test_retrieve_facts_priority_and_access_ordering(mem_dir):
    _write_memories(
        mem_dir,
        1,
        [
            {"fact": "питон один", "priority": 0, "access_count": 0},
            {"fact": "питон два", "priority": 5, "access_count": 0},
            {"fact": "питон три", "priority": 0, "access_count": 9},
        ],
    )
    result = memory.retrieve_facts("питон", 1)
    assert result == ["питон два", "питон три", "питон один"]


def test_retrieve_facts_max_results(mem_dir):
    facts = [{"fact": f"факт {i}", "priority": 0, "access_count": 0} for i in range(10)]
    _write_memories(mem_dir, 1, facts)
    assert len(memory.retrieve_facts("факт", 1, max_results=3)) == 3


def test_retrieve_facts_fact_missing_key_skipped(mem_dir):
    _write_memories(mem_dir, 1, [{"other": "x"}, {"fact": "реальный факт"}])
    result = memory.retrieve_facts("реальный", 1)
    assert result == ["реальный факт"]


# ─── get_memory_context ───


def test_get_memory_context_empty(mem_dir):
    assert memory.get_memory_context("что-то", 1) == ""


def test_get_memory_context_has_facts(mem_dir):
    _write_memories(mem_dir, 1, [{"fact": "питон факт", "priority": 0}])
    result = memory.get_memory_context("питон", 1)
    assert "Долговременные факты" in result
    assert "• питон факт" in result


# ─── extract_and_store_facts ───


def test_extract_and_store_facts_happy_path(mem_dir, monkeypatch):
    async def fake_extract(query, answer):
        return ["факт один", "факт два"]

    monkeypatch.setattr(memory, "_extract_facts", fake_extract)
    asyncio.run(memory.extract_and_store_facts(1, "вопрос", "ответ"))
    loaded = memory._load_memories(1)
    assert len(loaded) == 2
    assert loaded[0]["fact"] == "факт один"
    assert loaded[0]["source_query"] == "вопрос"
    assert loaded[0]["access_count"] == 0


def test_extract_and_store_facts_no_facts(mem_dir, monkeypatch):
    async def fake_extract(query, answer):
        return []

    monkeypatch.setattr(memory, "_extract_facts", fake_extract)
    asyncio.run(memory.extract_and_store_facts(1, "q", "a"))
    assert memory._load_memories(1) == []


def test_extract_and_store_facts_keeps_last_500(mem_dir, monkeypatch):
    async def fake_extract(query, answer):
        return [f"факт {query}"]

    monkeypatch.setattr(memory, "_extract_facts", fake_extract)
    for i in range(520):
        asyncio.run(memory.extract_and_store_facts(1, str(i), "a"))
    loaded = memory._load_memories(1)
    assert len(loaded) == 500


def test_extract_and_store_facts_extract_exception(mem_dir, monkeypatch):
    async def fake_extract(query, answer):
        raise RuntimeError("ai down")

    monkeypatch.setattr(memory, "_extract_facts", fake_extract)
    asyncio.run(memory.extract_and_store_facts(1, "q", "a"))
    assert memory._load_memories(1) == []


# ─── _extract_facts ───


def test_extract_facts_parses_json_array(monkeypatch):
    import services.ai_engine as ai_engine

    async def fake_ai(engine, model, messages, **kwargs):
        return '["факт A", "факт B"]'

    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("gemini", "flash"))
    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_ai)
    result = asyncio.run(memory._extract_facts("вопрос", "ответ"))
    assert result == ["факт A", "факт B"]


def test_extract_facts_unparseable_returns_empty(monkeypatch):
    import services.ai_engine as ai_engine

    async def fake_ai(engine, model, messages, **kwargs):
        return "не json"

    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("gemini", "flash"))
    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_ai)
    result = asyncio.run(memory._extract_facts("вопрос", "ответ"))
    assert result == []


def test_extract_facts_malformed_json_returns_empty(monkeypatch):
    import services.ai_engine as ai_engine

    async def fake_ai(engine, model, messages, **kwargs):
        return '[{"broken": ]'

    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("gemini", "flash"))
    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_ai)
    result = asyncio.run(memory._extract_facts("вопрос", "ответ"))
    assert result == []
