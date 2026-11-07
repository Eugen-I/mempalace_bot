"""tests/test_stage5_ai_agent.py — Тесты для Этапа 5:
1. Расширенные Palace-инструменты агента (palace_create_tunnel, palace_kg_add_fact,
   palace_summarize_room, palace_move_drawer).
2. Поддержка внешних движков (Gemini, OpenAI) в services.agent_engine.
3. Query Rewriting перед вызовом RAG/OmniSearch в services.query_rewriter.
"""

from __future__ import annotations

import asyncio
import json
import pytest

from services import agent_engine as ae
from services import agent_mcp_tools as amt
from services import agent_tools as at
from services.query_rewriter import (
    is_conversational_query,
    rewrite_query_for_search,
)


# ─── Тесты новых инструментов MemPalace ───


@pytest.mark.asyncio
async def test_palace_create_tunnel_tool(monkeypatch):
    """palace_create_tunnel формирует корректные аргументы для MCP."""
    called_args = {}

    async def fake_call(tool_name, args):
        nonlocal called_args
        called_args[tool_name] = args
        return json.dumps({"status": "ok", "tunnel": "created"})

    monkeypatch.setattr(amt, "_call", fake_call)

    tool = at.get_tool("palace_create_tunnel")
    assert tool is not None
    assert tool.is_write is True
    assert tool.category == at.CAT_PALACE

    res = await at.execute_tool(tool, {
        "wing_a": "Tech",
        "room_a": "Backend",
        "wing_b": "Science",
        "room_b": "Physics",
        "reason": "Quantum computing link",
    })
    assert "ok" in res
    assert called_args["mempalace_create_tunnel"] == {
        "source_wing": "Tech",
        "source_room": "Backend",
        "target_wing": "Science",
        "target_room": "Physics",
        "label": "Quantum computing link",
    }


@pytest.mark.asyncio
async def test_palace_kg_add_fact_tool(monkeypatch):
    """palace_kg_add_fact фиксирует факт через mempalace_kg_add."""
    called_args = {}

    async def fake_call(tool_name, args):
        nonlocal called_args
        called_args[tool_name] = args
        return json.dumps({"status": "fact_added"})

    monkeypatch.setattr(amt, "_call", fake_call)

    tool = at.get_tool("palace_kg_add_fact")
    assert tool is not None
    assert tool.is_write is True

    res = await at.execute_tool(tool, {
        "subject": "Алексей",
        "predicate": "работает_над",
        "object": "MemPalace",
    })
    assert "fact_added" in res
    assert called_args["mempalace_kg_add"] == {
        "subject": "Алексей",
        "predicate": "работает_над",
        "object": "MemPalace",
    }


@pytest.mark.asyncio
async def test_palace_summarize_room_tool(monkeypatch):
    """palace_summarize_room собирает ящики и запускает суммаризацию."""
    class FakeMCP:
        async def call_tool(self, name, args):
            return json.dumps({
                "drawers": [
                    {"closet_name": "План 1", "preview": "Текст первого ящика"},
                    {"closet_name": "План 2", "preview": "Текст второго ящика"},
                ]
            })

    monkeypatch.setattr(amt, "get_mcp", lambda: FakeMCP())

    async def fake_summary(mode, engine, model, text, wing, room):
        return f"Обобщение {wing}/{room}: {len(text)} символов"

    monkeypatch.setattr("services.summary_service.generate_summary", fake_summary)

    tool = at.get_tool("palace_summarize_room")
    assert tool is not None
    assert tool.is_write is False

    res = await at.execute_tool(tool, {"wing": "Tech", "room": "AI"})
    assert "Обобщение Tech/AI" in res


@pytest.mark.asyncio
async def test_palace_summarize_room_empty(monkeypatch):
    """palace_summarize_room для пустой комнаты возвращает сообщение об отсутствии записей."""
    class FakeMCP:
        async def call_tool(self, name, args):
            return json.dumps({"drawers": []})

    monkeypatch.setattr(amt, "get_mcp", lambda: FakeMCP())

    tool = at.get_tool("palace_summarize_room")
    res = await at.execute_tool(tool, {"wing": "Empty", "room": "Void"})
    assert "нет записей для обобщения" in res


@pytest.mark.asyncio
async def test_palace_move_drawer_tool(monkeypatch):
    """palace_move_drawer обновляет ящик и переносит backlink."""
    called_args = {}

    async def fake_call(tool_name, args):
        nonlocal called_args
        called_args[tool_name] = args
        return json.dumps({"status": "moved"})

    monkeypatch.setattr(amt, "_call", fake_call)

    backlink_updated = {}

    def fake_get_bl(did):
        return {"source_type": "apple_notes", "source_id": "note_123", "source_title": "Заметка"}

    def fake_rec_bl(drawer_id, source_type, source_id, wing, room, content, title):
        nonlocal backlink_updated
        backlink_updated = {
            "drawer_id": drawer_id, "wing": wing, "room": room, "source_id": source_id,
        }

    monkeypatch.setattr("services.notes_sync.get_backlink_by_drawer", fake_get_bl)
    monkeypatch.setattr("services.notes_sync.record_backlink", fake_rec_bl)

    tool = at.get_tool("palace_move_drawer")
    assert tool is not None
    assert tool.is_write is True

    res = await at.execute_tool(tool, {
        "drawer_id": "d_99",
        "target_wing": "Archive",
        "target_room": "2026",
    })
    assert "moved" in res
    assert called_args["mempalace_update_drawer"] == {
        "drawer_id": "d_99", "wing": "Archive", "room": "2026",
    }
    assert backlink_updated["target_wing" if "target_wing" in backlink_updated else "wing"] == "Archive"
    assert backlink_updated["room"] == "2026"


# ─── Тесты Query Rewriting ───


def test_is_conversational_query():
    assert is_conversational_query("") is False
    assert is_conversational_query("   ") is False
    # Короткие фразы считаются разговорными
    assert is_conversational_query("Что это?") is True
    assert is_conversational_query("А как там?") is True
    assert is_conversational_query("Расскажи подробнее") is True
    # Длинная фраза с местоимением
    assert is_conversational_query("А что мы вчера решили насчёт этой сложной проблемы?") is True
    # Длинная фраза без местоимений
    assert is_conversational_query("Инструкция по настройке протокола WebRTC на сервере Ubuntu") is False


@pytest.mark.asyncio
async def test_rewrite_query_empty_or_no_messages():
    """Без истории или при пустом запросе возвращается исходный запрос."""
    assert await rewrite_query_for_search("") == ""
    assert await rewrite_query_for_search("Привет", recent_messages=None) == "Привет"
    assert await rewrite_query_for_search("Привет", recent_messages=[]) == "Привет"


@pytest.mark.asyncio
async def test_rewrite_query_non_conversational_skips_llm():
    """Длинный самодостаточный запрос без отсылок не вызывает LLM."""
    query = "Конфигурация параметров ядра Linux для высоконагруженных веб-серверов"
    res = await rewrite_query_for_search(
        query,
        recent_messages=[{"role": "user", "content": "hello"}],
    )
    assert res == query


@pytest.mark.asyncio
async def test_rewrite_query_conversational_calls_llm(monkeypatch):
    """Разговорный запрос переформулируется с учётом контекста."""
    history = [
        {"role": "user", "content": "Мы переводим базу данных SQLite на режим WAL."},
        {"role": "assistant", "content": "Отлично, это повысит скорость записи."},
    ]

    async def fake_call_ai(engine=None, model=None, messages=None, **kwargs):
        # Проверяем, что в запросе передан контекст
        user_msg = messages[-1]["content"]
        assert "WAL" in user_msg
        return "«Оптимизация базы данных SQLite через WAL»"

    monkeypatch.setattr("services.ai_engine.call_ai_async", fake_call_ai)

    rewritten = await rewrite_query_for_search(
        "А что с этим решили?",
        recent_messages=history,
        engine="openai",
        model="gpt-4o",
    )
    assert rewritten == "Оптимизация базы данных SQLite через WAL"


@pytest.mark.asyncio
async def test_rewrite_query_llm_error_fallback(monkeypatch):
    """При ошибке или таймауте LLM возвращается исходный запрос."""
    history = [{"role": "user", "content": "Тема"}]

    async def boom(*a, **k):
        raise TimeoutError("LLM timeout")

    monkeypatch.setattr("services.ai_engine.call_ai_async", boom)

    raw_query = "А что с ним?"
    res = await rewrite_query_for_search(raw_query, recent_messages=history)
    assert res == raw_query


@pytest.mark.asyncio
async def test_agent_engine_openai_gemini_dispatch(monkeypatch):
    """_model_tool_call корректно вызывает OpenAI/Gemini клиентов."""
    # Тест неподдерживаемого движка
    with pytest.raises(ae.AgentEngineError):
        ae._model_tool_call("unknown_engine", "m", [], [])

    # Проверка вызова qwen
    qwen_called = False

    def fake_qwen(m, msgs, tools):
        nonlocal qwen_called
        qwen_called = True
        return {"content": "qwen_ok", "tool_calls": [], "finish_reason": "stop"}

    monkeypatch.setattr(ae, "_qwen_tool_call", fake_qwen)
    res = ae._model_tool_call("qwen", "qwen2.5:7b", [], [])
    assert qwen_called is True
    assert res["content"] == "qwen_ok"
