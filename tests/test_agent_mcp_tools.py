"""Unit-тесты для services.agent_mcp_tools — read-only инструменты дворца.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
get_mcp() замокан: проверяется маршрутизация аргументов и обработка ошибок.
"""

import pytest

from services import agent_mcp_tools as amt
from services import agent_tools as at
from services import agent_engine as ae


class FakeMCP:
    """Фейковый MCP-клиент: записывает вызовы, отдаёт скрипт ответов."""

    def __init__(self, script=None):
        self.calls = []
        self.script = script or []

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments or {}))
        if self.script:
            return self.script.pop(0)
        return f"результат {name}"


PALACE_TOOLS = [
    "mp_search",
    "mp_kg_query",
    "mp_kg_timeline",
    "mp_kg_stats",
    "mp_drawer_read",
    "mp_diary_read",
    "mp_check_duplicate",
]


@pytest.fixture
def fake_mcp(monkeypatch):
    client = FakeMCP()
    monkeypatch.setattr(amt, "get_mcp", lambda: client)
    return client


# ─── Реестр ───


def test_all_palace_tools_registered_and_readonly():
    for name in PALACE_TOOLS:
        tool = at.get_tool(name)
        assert tool is not None, f"{name} не зарегистрирован"
        assert tool.category == at.CAT_PALACE
        assert tool.is_write is False


def test_no_write_tools_registered_by_mcp_module():
    registered = at.list_agent_tools(include_write=True)
    write_tools = [t.name for t in registered if t.is_write]
    assert all(not n.startswith("mp_") for n in write_tools)


def test_palace_tools_in_default_allowlist():
    names = [t.name for t in at.list_agent_tools()]
    for name in PALACE_TOOLS:
        assert name in names


# ─── Маршрутизация вызовов (happy path) ───


async def test_mp_search_routes_to_mcp(fake_mcp):
    out = await amt._mp_search({"query": "шопенгауэр", "limit": 3, "wing": "философия"})
    assert fake_mcp.calls == [("mempalace_search", {
        "query": "шопенгауэр", "limit": 3, "wing": "философия",
    })]
    assert "результат" in out


async def test_mp_kg_query_routes_to_mcp(fake_mcp):
    await amt._mp_kg_query({"entity": "Max", "as_of": "2026-01-01", "direction": "both"})
    assert fake_mcp.calls == [("mempalace_kg_query", {
        "entity": "Max", "as_of": "2026-01-01", "direction": "both",
    })]


async def test_mp_kg_stats_no_args(fake_mcp):
    await amt._mp_kg_stats({})
    assert fake_mcp.calls == [("mempalace_kg_stats", {})]


async def test_mp_drawer_read_routes_to_mcp(fake_mcp):
    await amt._mp_drawer_read({"drawer_id": "abc123"})
    assert fake_mcp.calls == [("mempalace_get_drawer", {"drawer_id": "abc123"})]


async def test_mp_diary_read_routes_to_mcp(fake_mcp):
    await amt._mp_diary_read({"agent_name": "qwen", "last_n": 5})
    assert fake_mcp.calls == [("mempalace_diary_read", {
        "agent_name": "qwen", "last_n": 5,
    })]


async def test_mp_check_duplicate_routes_to_mcp(fake_mcp):
    await amt._mp_check_duplicate({"content": "текст", "threshold": 0.8})
    assert fake_mcp.calls == [("mempalace_check_duplicate", {
        "content": "текст", "threshold": 0.8,
    })]


async def test_mp_kg_timeline_with_entity(fake_mcp):
    await amt._mp_kg_timeline({"entity": "Max"})
    assert fake_mcp.calls == [("mempalace_kg_timeline", {"entity": "Max"})]


# ─── Ошибки MCP ───


async def test_mcp_failure_returns_error_text(monkeypatch):
    class BoomMCP:
        async def call_tool(self, name, arguments=None):
            raise RuntimeError("connection lost")

    monkeypatch.setattr(amt, "get_mcp", lambda: BoomMCP())
    out = await amt._mp_search({"query": "вопрос"})
    assert "Ошибка MCP-вызова mempalace_search" in out
    assert "connection lost" in out


async def test_mcp_failure_does_not_raise(monkeypatch):
    class BoomMCP:
        async def call_tool(self, name, arguments=None):
            raise OSError("dead")

    monkeypatch.setattr(amt, "get_mcp", lambda: BoomMCP())
    out = await amt._mp_drawer_read({"drawer_id": "x"})
    assert "Ошибка MCP-вызова" in out


# ─── Валидация схем (BVA) ───


def test_mp_search_requires_query():
    tool = at.get_tool("mp_search")
    errors = at.validate_arguments(tool, {"limit": 5})
    assert any("query" in e for e in errors)


def test_mp_search_accepts_only_known_args():
    tool = at.get_tool("mp_search")
    errors = at.validate_arguments(tool, {"query": "q", "hack": 1})
    assert any("hack" in e for e in errors)


def test_mp_search_limit_must_be_integer():
    tool = at.get_tool("mp_search")
    errors = at.validate_arguments(tool, {"query": "q", "limit": "5"})
    assert any("limit" in e for e in errors)
    assert at.validate_arguments(tool, {"query": "q", "limit": 1}) == []


def test_mp_kg_query_requires_entity():
    tool = at.get_tool("mp_kg_query")
    assert at.validate_arguments(tool, {})
    assert at.validate_arguments(tool, {"entity": "Max"}) == []


def test_mp_drawer_read_requires_drawer_id():
    tool = at.get_tool("mp_drawer_read")
    assert at.validate_arguments(tool, {})
    assert at.validate_arguments(tool, {"drawer_id": "id1"}) == []


def test_mp_diary_read_requires_agent_name():
    tool = at.get_tool("mp_diary_read")
    assert at.validate_arguments(tool, {"last_n": 10})
    assert at.validate_arguments(tool, {"agent_name": "qwen"}) == []


def test_mp_check_duplicate_requires_content():
    tool = at.get_tool("mp_check_duplicate")
    assert at.validate_arguments(tool, {"threshold": 0.5})
    assert at.validate_arguments(tool, {"content": "текст"}) == []


def test_mp_kg_stats_schema_empty():
    tool = at.get_tool("mp_kg_stats")
    assert at.validate_arguments(tool, {}) == []
    assert at.validate_arguments(tool, {"any": 1})


# ─── Интеграция с agent_engine ───


async def test_engine_executes_mp_tool_via_mcp(monkeypatch, fake_mcp):
    """run_agent выполняет mp_kg_stats через замоканный MCP и отдаёт результат."""
    fake_mcp.script = ["сущностей: 42"]

    from tests.test_agent_engine import (
        FakeClient,
        FakeMessage,
        FakeResponse,
        FakeToolCall,
    )

    script = [
        FakeResponse(FakeMessage(None, [
            FakeToolCall("c1", "mp_kg_stats", "{}"),
        ]), finish_reason="tool_calls"),
        FakeResponse(FakeMessage("Сущностей: 42")),
    ]
    harness = _make_harness(script)
    monkeypatch.setattr(ae, "OpenAI", lambda *a, **k: FakeClient(harness))
    monkeypatch.setattr(ae, "ensure_ollama_running", lambda model: None)

    result = await ae.run_agent(
        "sys", "сколько сущностей", engine="qwen", model="qwen2.5:7b",
    )
    assert result.finished_reason == "answer"
    assert result.final_answer == "Сущностей: 42"
    assert fake_mcp.calls == [("mempalace_kg_stats", {})]
    assert result.iterations == 2


def _make_harness(script):
    """Обёртка над ModelHarness из test_agent_engine для задания скрипта."""
    from tests.test_agent_engine import ModelHarness

    harness = ModelHarness(script=script)
    return harness
