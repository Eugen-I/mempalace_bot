"""services/agent_mcp_tools.py — read-only инструменты MemPalace для агента.

Каждый инструмент — тонкая обёртка над MCP-сервером дворца
(services.palace_mcp.get_mcp().call_tool()). Только ЧТЕНИЕ: поиск, KG-запросы,
чтение ящиков и дневника, проверка дубликатов.

Инструменты записи (mp_add_drawer и т.п.) намеренно НЕ регистрируются —
агентный режим первого релиза строго read-only.
"""

import logging

from services.agent_tools import CAT_PALACE, register_tool
from services.palace_mcp import get_mcp

logger = logging.getLogger("AgentMCPTools")


async def _call(name: str, args: dict) -> str:
    """Вызывает инструмент MCP-сервера и возвращает текст результата."""
    try:
        return await get_mcp().call_tool(name, args)
    except Exception as exc:  # noqa: BLE001 — агент сам видит текст ошибки
        logger.warning("[AGENT] mcp tool %s failed: %s", name, exc)
        return f"Ошибка MCP-вызова {name}: {exc}"


@register_tool(
    "mp_search",
    "Семантический поиск по записям дворца. Возвращает дословное содержимое "
    "ящиков с оценками похожести. Используй вместо mp_drawer_read, когда нужно "
    "найти записи по смыслу, а не по ID. 'query' — только ключевые слова, "
    "максимум 250 символов.",
    schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Поисковый запрос — ключевые слова или вопрос",
            },
            "limit": {
                "type": "integer",
                "description": "Максимум результатов (по умолчанию 5, до 100)",
            },
            "wing": {
                "type": "string",
                "description": "Фильтр по крылу (необязательно)",
            },
            "room": {
                "type": "string",
                "description": "Фильтр по комнате (необязательно)",
            },
            "max_distance": {
                "type": "number",
                "description": (
                    "Порог похожести по косинусному расстоянию (0=идентично, "
                    "2=противоположно; по умолчанию 1.5; 0 — отключить фильтр)"
                ),
            },
        },
        "required": ["query"],
    },
    category=CAT_PALACE,
)
async def _mp_search(args: dict) -> str:
    return await _call("mempalace_search", args)


@register_tool(
    "mp_kg_query",
    "Запрос к графу знаний: отношения сущности с временной валидностью. "
    "Например 'Max' → любит_шахматы, дочь_Алисы. Аргумент as_of фильтрует факты, "
    "действовавшие на указанную дату (YYYY-MM-DD).",
    schema={
        "type": "object",
        "properties": {
            "entity": {
                "type": "string",
                "description": "Сущность для запроса (например 'Max', 'Проект', 'Алиса')",
            },
            "as_of": {
                "type": "string",
                "description": (
                    "Фильтр по дате — только факты, действовавшие "
                    "в этот день (YYYY-MM-DD)"
                ),
            },
            "direction": {
                "type": "string",
                "description": (
                    "outgoing (сущность→?), incoming (?→сущность) "
                    "или both (по умолчанию)"
                ),
            },
        },
        "required": ["entity"],
    },
    category=CAT_PALACE,
)
async def _mp_kg_query(args: dict) -> str:
    return await _call("mempalace_kg_query", args)


@register_tool(
    "mp_kg_timeline",
    "Хронологическая лента фактов графа знаний: история сущности (или всего "
    "графа, если entity не указана) в порядке времени. Используй для вопросов "
    "«как развивалось», «что было раньше».",
    schema={
        "type": "object",
        "properties": {
            "entity": {
                "type": "string",
                "description": "Сущность для ленты (необязательно — вся история)",
            },
        },
    },
    category=CAT_PALACE,
)
async def _mp_kg_timeline(args: dict) -> str:
    return await _call("mempalace_kg_timeline", args)


@register_tool(
    "mp_kg_stats",
    "Обзор графа знаний: количество сущностей, троек, действующих и завершённых "
    "фактов, типы отношений. Используй для общей картины памяти.",
    schema={"type": "object", "properties": {}},
    category=CAT_PALACE,
)
async def _mp_kg_stats(args: dict) -> str:
    return await _call("mempalace_kg_stats", args)


@register_tool(
    "mp_drawer_read",
    "Чтение одного ящика дворца по ID: полное содержимое и метаданные. "
    "Используй, когда уже знаешь ID ящика (например, из mp_search).",
    schema={
        "type": "object",
        "properties": {
            "drawer_id": {
                "type": "string",
                "description": "ID ящика для чтения",
            },
        },
        "required": ["drawer_id"],
    },
    category=CAT_PALACE,
)
async def _mp_drawer_read(args: dict) -> str:
    return await _call("mempalace_get_drawer", args)


@register_tool(
    "mp_diary_read",
    "Чтение последних записей дневника агента (в формате AAAK). Помогает "
    "вспомнить, что записано в прошлых сессиях.",
    schema={
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Имя агента — у каждого свой дневник",
            },
            "last_n": {
                "type": "integer",
                "description": "Сколько последних записей прочитать (по умолчанию 10)",
            },
        },
        "required": ["agent_name"],
    },
    category=CAT_PALACE,
)
async def _mp_diary_read(args: dict) -> str:
    return await _call("mempalace_diary_read", args)


@register_tool(
    "mp_check_duplicate",
    "Проверка, существует ли похожее содержимое во дворце (порог похожести 0-1, "
    "по умолчанию 0.9). Используй перед тем, как предлагать сохранить что-то "
    "новое.",
    schema={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Содержимое для проверки",
            },
            "threshold": {
                "type": "number",
                "description": "Порог похожести 0-1 (по умолчанию 0.9)",
            },
        },
        "required": ["content"],
    },
    category=CAT_PALACE,
)
async def _mp_check_duplicate(args: dict) -> str:
    return await _call("mempalace_check_duplicate", args)
