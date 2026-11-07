"""Unit-тесты для services.agent_web_tools."""

import pytest

from services import agent_tools as at
from services import agent_web_tools as awt  # noqa: F401


@pytest.mark.asyncio
async def test_web_search_tool_registered():
    tool = at.get_tool("web_search")
    assert tool is not None
    assert tool.category == at.CAT_WEB
    assert tool.is_write is False
    assert "query" in tool.schema["properties"]


@pytest.mark.asyncio
async def test_web_search_tool_execution(monkeypatch):
    async def fake_search(query, max_results=5):
        return f"<b>Результат</b> для {query}<br>Вторая строка"

    monkeypatch.setattr("services.agent_web_tools.search_web", fake_search)
    tool = at.get_tool("web_search")
    res = await at.execute_tool(tool, {"query": "тест"})
    assert "Результат для тест" in res
    assert "<br>" not in res
    assert "<b>" not in res


@pytest.mark.asyncio
async def test_web_search_empty_query():
    tool = at.get_tool("web_search")
    res = await at.execute_tool(tool, {"query": ""})
    assert "Ошибка" in res


@pytest.mark.asyncio
async def test_web_search_exception_handling(monkeypatch):
    async def failing_search(query, max_results=5):
        raise RuntimeError("сеть недоступна")

    monkeypatch.setattr("services.agent_web_tools.search_web", failing_search)
    tool = at.get_tool("web_search")
    res = await at.execute_tool(tool, {"query": "ошибка"})
    assert "Ошибка веб-поиска" in res
