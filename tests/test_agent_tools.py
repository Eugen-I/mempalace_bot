"""Unit-тесты для services.agent_tools — реестр инструментов агента.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
"""

import asyncio
import json
from datetime import datetime

import pytest

from services import agent_tools as at


# ─── Фикстура: чистый реестр без тестовых инструментов ───


@pytest.fixture
def cleanup():
    """Удаляет тестовые инструменты после каждого теста."""
    yield
    for name in ("test_tool", "test_write", "test_async_tool", "test_dup"):
        at.unregister_tool(name)


def _register_test_tool(name="test_tool", category=at.CAT_SYSTEM, is_write=False):
    """Регистрирует простой тестовый инструмент (идемпотентно)."""
    at.unregister_tool(name)
    at.register_tool(
        name,
        "Тестовый инструмент",
        schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        category=category,
        is_write=is_write,
    )(lambda args: f"got:{args['value']}")
    return name


# ─── register_tool / unregister_tool / get_tool ───


def test_register_and_get(cleanup):
    name = _register_test_tool()
    tool = at.get_tool(name)
    assert tool is not None
    assert tool.name == name
    assert tool.description == "Тестовый инструмент"
    assert tool.category == at.CAT_SYSTEM
    assert tool.is_write is False
    assert tool.schema["required"] == ["value"]


def test_register_duplicate_raises(cleanup):
    at.unregister_tool("test_tool")
    at.register_tool(
        "test_tool",
        "Тест",
        schema={"type": "object", "properties": {}},
    )(lambda a: "")
    with pytest.raises(ValueError):
        at.register_tool(
            "test_tool",
            "Тест 2",
            schema={"type": "object", "properties": {}},
        )(lambda a: "")


def test_get_tool_unknown_returns_none():
    assert at.get_tool("no_such_tool") is None


def test_unregister_returns_flag(cleanup):
    _register_test_tool()
    assert at.unregister_tool("test_tool") is True
    assert at.unregister_tool("test_tool") is False
    assert at.get_tool("test_tool") is None


def test_default_tools_registered():
    assert at.get_tool("agent_now") is not None
    assert at.get_tool("agent_list_tools") is not None
    assert at._agent_loop_ready() is True


# ─── list_agent_tools (allowlist-фильтр) ───


def test_list_tools_default_excludes_write(cleanup):
    _register_test_tool(name="test_write", category=at.CAT_PALACE, is_write=True)
    names = [t.name for t in at.list_agent_tools()]
    assert "test_write" not in names
    assert "agent_now" in names


def test_list_tools_include_write(cleanup):
    _register_test_tool(name="test_write", category=at.CAT_PALACE, is_write=True)
    names = [t.name for t in at.list_agent_tools(include_write=True)]
    assert "test_write" in names


def test_list_tools_category_filter(cleanup):
    _register_test_tool(name="test_write", category=at.CAT_PALACE, is_write=False)
    names = [t.name for t in at.list_agent_tools(allowed_categories=(at.CAT_SYSTEM,))]
    assert "test_write" not in names


def test_list_tools_empty_categories(cleanup):
    _register_test_tool()
    assert at.list_agent_tools(allowed_categories=()) == []


# ─── to_openai_tools ───


def test_to_openai_tools_format(cleanup):
    _register_test_tool()
    tools = at.to_openai_tools(at.list_agent_tools())
    test = next(t for t in tools if t["function"]["name"] == "test_tool")
    assert test["type"] == "function"
    assert test["function"]["parameters"]["required"] == ["value"]
    assert "description" in test["function"]


def test_to_openai_tools_empty():
    assert at.to_openai_tools([]) == []


# ─── validate_arguments ───


def test_validate_arguments_happy(cleanup):
    _register_test_tool()
    tool = at.get_tool("test_tool")
    assert at.validate_arguments(tool, {"value": "x"}) == []


def test_validate_missing_required(cleanup):
    _register_test_tool()
    tool = at.get_tool("test_tool")
    errors = at.validate_arguments(tool, {})
    assert "value" in errors[0]


def test_validate_unknown_argument(cleanup):
    _register_test_tool()
    tool = at.get_tool("test_tool")
    errors = at.validate_arguments(tool, {"value": "x", "extra": 1})
    assert any("extra" in e for e in errors)


def test_validate_wrong_type_string_vs_int():
    tool = at.AgentTool(
        name="t",
        description="d",
        schema={"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]},
        handler=lambda a: "",
    )
    assert at.validate_arguments(tool, {"n": "not-int"}) != []
    assert at.validate_arguments(tool, {"n": 5}) == []


def test_validate_string_type_wrong():
    tool = at.AgentTool(
        name="t",
        description="d",
        schema={"type": "object", "properties": {"s": {"type": "string"}}},
        handler=lambda a: "",
    )
    assert at.validate_arguments(tool, {"s": "ок"}) == []
    assert at.validate_arguments(tool, {"s": 42}) != []


def test_validate_bool_is_not_integer():
    tool = at.AgentTool(
        name="t",
        description="d",
        schema={"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]},
        handler=lambda a: "",
    )
    errors = at.validate_arguments(tool, {"n": True})
    assert errors != []


def test_validate_not_a_dict():
    tool = at.get_tool("agent_now")
    errors = at.validate_arguments(tool, [1, 2])
    assert errors != []


def test_validate_array_type():
    tool = at.AgentTool(
        name="t",
        description="d",
        schema={"type": "object", "properties": {"a": {"type": "array"}}},
        handler=lambda a: "",
    )
    assert at.validate_arguments(tool, {"a": [1, 2]}) == []
    assert at.validate_arguments(tool, {"a": "x"}) != []
    assert at.validate_arguments(tool, {"a": True}) != []


def test_validate_number_type():
    tool = at.AgentTool(
        name="t",
        description="d",
        schema={"type": "object", "properties": {"n": {"type": "number"}}},
        handler=lambda a: "",
    )
    assert at.validate_arguments(tool, {"n": 3.14}) == []
    assert at.validate_arguments(tool, {"n": 5}) == []
    assert at.validate_arguments(tool, {"n": "x"}) != []
    assert at.validate_arguments(tool, {"n": True}) != []


def test_validate_boolean_type():
    tool = at.AgentTool(
        name="t",
        description="d",
        schema={"type": "object", "properties": {"b": {"type": "boolean"}}},
        handler=lambda a: "",
    )
    assert at.validate_arguments(tool, {"b": True}) == []
    assert at.validate_arguments(tool, {"b": False}) == []
    assert at.validate_arguments(tool, {"b": 1}) != []


# ─── execute_tool / format_tool_result ───


def test_execute_sync_handler(cleanup):
    _register_test_tool()
    tool = at.get_tool("test_tool")
    out = asyncio.run(at.execute_tool(tool, {"value": "abc"}))
    assert out == "got:abc"


def test_execute_async_handler(cleanup):
    async def handler(args):
        return f"async:{args['value']}"

    at.register_tool(
        "test_async_tool",
        "Асинхронный тестовый инструмент",
        schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )(handler)
    tool = at.get_tool("test_async_tool")
    out = asyncio.run(at.execute_tool(tool, {"value": "x"}))
    assert out == "async:x"


def test_format_result_none_is_empty():
    assert at.format_tool_result("t", None) == ""


def test_format_result_dict_to_json():
    out = at.format_tool_result("t", {"a": 1, "b": "текст"})
    assert json.loads(out) == {"a": 1, "b": "текст"}


def test_format_result_truncation_boundary():
    at.TOOL_RESULT_LIMIT = 10
    try:
        assert at.format_tool_result("t", "x" * 10) == "x" * 10
        out = at.format_tool_result("t", "y" * 11)
        assert out.startswith("y" * 10)
        assert "обрезан" in out
    finally:
        at.TOOL_RESULT_LIMIT = 8000


def test_format_result_string():
    assert at.format_tool_result("t", "просто строка") == "просто строка"


def test_format_result_json_fallback():
    class Broken:
        def __str__(self):
            raise ValueError("no string")

    out = at.format_tool_result("t", {"bad": Broken()})
    assert "Broken" in out


# ─── Системные инструменты ───


def test_agent_now_format(monkeypatch):
    class FakeDatetime:
        @staticmethod
        def now():
            return datetime(2026, 8, 7, 10, 30)

    monkeypatch.setattr(at, "datetime", FakeDatetime)
    out = at.force_tool_execute("agent_now", {})
    assert out == "2026-08-07 10:30, пт 7 августа 2026"


def test_agent_list_tools_contains_system_tools():
    out = at.force_tool_execute("agent_list_tools", {})
    assert "agent_now" in out
    assert "agent_list_tools" in out


def test_force_execute_unknown_tool_raises():
    with pytest.raises(KeyError):
        at.force_tool_execute("no_such_tool", {})
