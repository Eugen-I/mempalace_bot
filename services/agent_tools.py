"""services/agent_tools.py — реестр инструментов агентного режима.

Каждый инструмент описывается JSON-схемой в формате OpenAI (совместим с
tool-calling Ollama/qwen2.5), имеет категорию и флаг is_write.

Фаза 0: только «системные» инструменты (дата/время, список инструментов).
Фаза 1 добавит read-only инструменты MemPalace (MCP), Фаза 2 — Apple Notes.

Безопасность: инструменты ЗАПИСИ (is_write=True) по умолчанию НЕ доступны —
фильтруются функцией list_agent_tools(). Это и есть allowlist-механизм.
"""

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger("AgentTools")

# Категории инструментов
CAT_SYSTEM = "system"
CAT_PALACE = "palace"
CAT_NOTES = "notes"

# Все категории, разрешённые агенту по умолчанию (read-only набор)
DEFAULT_ALLOWED_CATEGORIES = (CAT_SYSTEM, CAT_PALACE, CAT_NOTES)

# Лимит символов результата инструмента, возвращаемого модели
TOOL_RESULT_LIMIT = 8000

WEEKDAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


@dataclass(frozen=True)
class AgentTool:
    """Описание инструмента агента."""

    name: str
    description: str
    schema: dict = field(default_factory=dict)
    category: str = CAT_SYSTEM
    is_write: bool = False
    handler: Any = None  # Callable[[dict], str | Awaitable[str]]


# Реестр: name -> AgentTool
_TOOLS: dict[str, AgentTool] = {}


def register_tool(
    name: str,
    description: str,
    schema: dict | None = None,
    category: str = CAT_SYSTEM,
    is_write: bool = False,
):
    """Декоратор регистрации инструмента.

    Пример:
        @register_tool("agent_now", "Текущая дата и время")
        async def _now(args: dict) -> str:
            return "2026-08-07"
    """

    def decorator(fn):
        if name in _TOOLS:
            raise ValueError(f"Tool already registered: {name}")
        _TOOLS[name] = AgentTool(
            name=name,
            description=description,
            schema=schema or {"type": "object", "properties": {}},
            category=category,
            is_write=is_write,
            handler=fn,
        )
        return fn

    return decorator


def unregister_tool(name: str) -> bool:
    """Удаляет инструмент из реестра (для тестов и перерегистрации)."""
    return _TOOLS.pop(name, None) is not None


def get_tool(name: str) -> AgentTool | None:
    """Возвращает инструмент по имени или None."""
    return _TOOLS.get(name)


def list_agent_tools(
    allowed_categories: tuple | None = None,
    include_write: bool = False,
) -> list[AgentTool]:
    """Allowlist-фильтр: возвращает инструменты доступных категорий.

    Инструменты записи (is_write=True) возвращаются только при
    include_write=True. По умолчанию — read-only набор.
    """
    cats = allowed_categories if allowed_categories is not None else DEFAULT_ALLOWED_CATEGORIES
    return [
        t for t in _TOOLS.values()
        if t.category in cats and (include_write or not t.is_write)
    ]


def to_openai_tools(tools: list[AgentTool]) -> list[dict]:
    """Конвертирует инструменты в OpenAI-формат (для Ollama tool-calling)."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.schema,
            },
        }
        for t in tools
    ]


def validate_arguments(tool: AgentTool, args: dict) -> list[str]:
    """Валидация аргументов по схеме. Возвращает список ошибок (пусто — ок)."""
    errors: list[str] = []
    props = (tool.schema or {}).get("properties", {})
    required = (tool.schema or {}).get("required", [])
    if not isinstance(args, dict):
        return [f"Аргументы должны быть объектом JSON, получено: {type(args).__name__}"]
    for key in required:
        if key not in args:
            errors.append(f"Отсутствует обязательный аргумент: {key}")
    for key, value in args.items():
        prop = props.get(key)
        if not prop:
            errors.append(f"Неизвестный аргумент: {key}")
            continue
        expected = prop.get("type")
        if expected == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"Аргумент '{key}' должен быть целым числом")
        elif expected == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"Аргумент '{key}' должен быть числом")
        elif expected == "string":
            if not isinstance(value, str):
                errors.append(f"Аргумент '{key}' должен быть строкой")
        elif expected == "boolean":
            if not isinstance(value, bool):
                errors.append(f"Аргумент '{key}' должен быть boolean")
        elif expected == "array":
            if not isinstance(value, list):
                errors.append(f"Аргумент '{key}' должен быть массивом")
        if expected in ("integer", "number") and isinstance(value, (int, float)) \
                and not isinstance(value, bool):
            minimum = prop.get("minimum")
            maximum = prop.get("maximum")
            if minimum is not None and value < minimum:
                errors.append(f"Аргумент '{key}' не может быть меньше {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"Аргумент '{key}' не может быть больше {maximum}")
    return errors


async def execute_tool(tool: AgentTool, args: dict) -> str:
    """Выполняет инструмент и возвращает строку результата."""
    result = tool.handler(args)
    if inspect.isawaitable(result):
        result = await result
    return format_tool_result(tool.name, result)


def format_tool_result(name: str, raw: Any, limit: int | None = None) -> str:
    """Приводит результат инструмента к строке с обрезкой для модели."""
    if limit is None:
        limit = TOOL_RESULT_LIMIT
    if raw is None:
        text = ""
    elif isinstance(raw, str):
        text = raw
    else:
        try:
            text = json.dumps(raw, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(raw)
    if len(text) > limit:
        text = text[:limit] + "\n...(результат обрезан)"
    return text


# ─── Системные инструменты ───


@register_tool(
    "agent_now",
    "Текущие дата, время и день недели. Используй для расчёта сроков, "
    "напоминаний и планирования.",
    schema={"type": "object", "properties": {}},
    category=CAT_SYSTEM,
)
def _tool_now(_args: dict) -> str:
    now = datetime.now()
    return (
        f"{now.strftime('%Y-%m-%d')} {now.strftime('%H:%M')}, "
        f"{WEEKDAYS_RU[now.weekday()]} "
        f"{now.day} {MONTHS_RU[now.month - 1]} {now.year}"
    )


@register_tool(
    "agent_list_tools",
    "Список доступных тебе инструментов с описаниями. Вызови, если не уверен, "
    "какие инструменты доступны для решения задачи.",
    schema={"type": "object", "properties": {}},
    category=CAT_SYSTEM,
)
def _tool_list_tools(_args: dict) -> str:
    tools = list_agent_tools()
    lines = [f"- {t.name}: {t.description}" for t in tools]
    return "\n".join(lines) or "Инструменты недоступны."


def _agent_loop_ready() -> bool:
    """Проверка целостности реестра (для быстрого smoke-теста)."""
    return "agent_now" in _TOOLS and "agent_list_tools" in _TOOLS


def force_tool_execute(name: str, args: dict) -> str:
    """Синхронное выполнение инструмента по имени (для тестов и CLI)."""
    tool = get_tool(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    return asyncio.run(execute_tool(tool, args))
