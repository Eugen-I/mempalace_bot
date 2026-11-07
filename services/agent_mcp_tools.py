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


@register_tool(
    "palace_create_tunnel",
    "Создать туннель (смысловую связь) между двумя комнатами во Дворце памяти. "
    "Например, связать концепцию из проекта А с архитектурой из проекта Б.",
    schema={
        "type": "object",
        "properties": {
            "wing_a": {"type": "string", "description": "Крыло источника"},
            "room_a": {"type": "string", "description": "Комната источника"},
            "wing_b": {"type": "string", "description": "Крыло назначения"},
            "room_b": {"type": "string", "description": "Комната назначения"},
            "reason": {
                "type": "string",
                "description": "Причина связи или описание туннеля (необязательно)",
            },
        },
        "required": ["wing_a", "room_a", "wing_b", "room_b"],
    },
    category=CAT_PALACE,
    is_write=True,
)
async def _palace_create_tunnel(args: dict) -> str:
    mcp_args = {
        "source_wing": args.get("wing_a", ""),
        "source_room": args.get("room_a", ""),
        "target_wing": args.get("wing_b", ""),
        "target_room": args.get("room_b", ""),
        "label": args.get("reason", ""),
    }
    return await _call("mempalace_create_tunnel", mcp_args)


@register_tool(
    "palace_kg_add_fact",
    "Зафиксировать новый факт в графе знаний (KG). Например: "
    "субъект='Алексей', предикат='работает_над', объект='проектом_Х'.",
    schema={
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Субъект (сущность)"},
            "predicate": {
                "type": "string",
                "description": "Предикат (связь, например 'работает_над', 'создал')",
            },
            "object": {"type": "string", "description": "Объект (целевая сущность или значение)"},
        },
        "required": ["subject", "predicate", "object"],
    },
    category=CAT_PALACE,
    is_write=True,
)
async def _palace_kg_add_fact(args: dict) -> str:
    mcp_args = {
        "subject": args.get("subject", ""),
        "predicate": args.get("predicate", ""),
        "object": args.get("object", ""),
    }
    return await _call("mempalace_kg_add", mcp_args)


@register_tool(
    "palace_summarize_room",
    "Синтезировать и обобщить всё содержание комнаты во Дворце памяти.",
    schema={
        "type": "object",
        "properties": {
            "wing": {"type": "string", "description": "Крыло Дворца"},
            "room": {"type": "string", "description": "Комната в крыле"},
        },
        "required": ["wing", "room"],
    },
    category=CAT_PALACE,
    is_write=False,
)
async def _palace_summarize_room(args: dict) -> str:
    wing = args.get("wing", "")
    room = args.get("room", "")
    try:
        raw_list = await get_mcp().call_tool(
            "mempalace_list_drawers",
            {"wing": wing, "room": room, "limit": 100, "offset": 0},
        )
        import json
        data = json.loads(raw_list) if raw_list else {}
        drawers = data.get("drawers", [])
        if not drawers:
            return f"В комнате {wing}/{room} нет записей для обобщения."

        texts = []
        for d in drawers:
            name = d.get("closet_name") or d.get("title") or d.get("name") or d.get("drawer_id")
            preview = d.get("content") or d.get("snippet") or d.get("preview") or ""
            texts.append(f"Запись «{name}»:\n{preview[:600]}")
        notes_text = "\n\n---\n\n".join(texts)

        from services.summary_service import SummaryMode, generate_summary
        from services.ai_engine import get_current_ai
        engine, model = get_current_ai()
        summary = await generate_summary(
            SummaryMode.ROOM,
            engine=engine,
            model=model,
            text=notes_text,
            wing=wing,
            room=room,
        )
        return summary
    except Exception as exc:
        logger.warning("[AGENT] palace_summarize_room failed: %s", exc)
        return f"Не удалось обобщить комнату {wing}/{room}: {exc}"


@register_tool(
    "palace_move_drawer",
    "Переместить ящик (запись) в другое крыло или комнату во Дворце.",
    schema={
        "type": "object",
        "properties": {
            "drawer_id": {"type": "string", "description": "ID перемещаемого ящика"},
            "target_wing": {"type": "string", "description": "Новое крыло"},
            "target_room": {"type": "string", "description": "Новая комната"},
        },
        "required": ["drawer_id", "target_wing", "target_room"],
    },
    category=CAT_PALACE,
    is_write=True,
)
async def _palace_move_drawer(args: dict) -> str:
    did = args.get("drawer_id", "")
    t_wing = args.get("target_wing", "")
    t_room = args.get("target_room", "")
    res = await _call("mempalace_update_drawer", {"drawer_id": did, "wing": t_wing, "room": t_room})
    try:
        from services.notes_sync import get_backlink_by_drawer, record_backlink
        bl = get_backlink_by_drawer(did)
        if bl:
            record_backlink(
                drawer_id=did,
                source_type=bl["source_type"],
                source_id=bl["source_id"],
                wing=t_wing,
                room=t_room,
                content="",
                title=bl.get("source_title", ""),
            )
    except Exception as exc:
        logger.debug("[AGENT] failed updating backlink for moved drawer: %s", exc)
    return res
