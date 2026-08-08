"""services/agent_notes_tools.py — read-only инструменты Apple Notes для агента.

Обёртки над services.apple_notes: список/поиск по кэш-индексу и чтение
тела заметки (живой вызов). Только ЧТЕНИЕ.
"""

import logging

from services.agent_tools import CAT_NOTES, register_tool
from services.apple_notes import (
    AppleNotesError,
    list_notes,
    read_note,
    search_notes,
)

logger = logging.getLogger("AgentNotesTools")


def _error_text(exc: Exception) -> str:
    return f"Ошибка Apple Notes: {exc}"


@register_tool(
    "notes_list",
    "Список заметок Apple Notes из индекса (быстро, из кэша). Необязательно "
    "фильтр по папке. Используй перед notes_read, чтобы узнать ID заметки.",
    schema={
        "type": "object",
        "properties": {
            "folder": {
                "type": "string",
                "description": "Имя папки для фильтрации (необязательно)",
            },
            "force_refresh": {
                "type": "boolean",
                "description": "Принудительно обновить индекс (необязательно)",
            },
        },
    },
    category=CAT_NOTES,
)
def _notes_list(args: dict) -> str:
    try:
        notes = list_notes(
            folder=args.get("folder"),
            force_refresh=bool(args.get("force_refresh")),
        )
    except AppleNotesError as exc:
        return _error_text(exc)
    if not notes:
        return "Заметок не найдено."
    lines = [f"- {n.get('name', '?')} [id={n.get('id')}] (папка: {n.get('folder', '?')})"
             for n in notes[:50]]
    return "\n".join(lines)


@register_tool(
    "notes_search",
    "Поиск заметок Apple Notes по названию и папке (без учёта регистра, "
    "все слова запроса). Возвращает ID — их можно передать в notes_read.",
    schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Поисковый запрос — слова для поиска",
            },
            "limit": {
                "type": "integer",
                "description": "Максимум результатов (по умолчанию 10)",
            },
        },
        "required": ["query"],
    },
    category=CAT_NOTES,
)
def _notes_search(args: dict) -> str:
    try:
        found = search_notes(
            args["query"], limit=int(args.get("limit") or 10),
        )
    except (AppleNotesError, ValueError) as exc:
        return _error_text(exc) if isinstance(exc, AppleNotesError) else f"Ошибка: {exc}"
    if not found:
        return "По запросу ничего не найдено."
    lines = [f"- {n.get('name', '?')} [id={n.get('id')}] (папка: {n.get('folder', '?')})"
             for n in found]
    return "\n".join(lines)


@register_tool(
    "notes_read",
    "Чтение полного текста заметки Apple Notes по ID. ID можно получить из "
    "notes_list или notes_search. Вернёт название и содержимое заметки.",
    schema={
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "ID заметки",
            },
        },
        "required": ["note_id"],
    },
    category=CAT_NOTES,
)
def _notes_read(args: dict) -> str:
    try:
        data = read_note(args["note_id"])
    except AppleNotesError as exc:
        return _error_text(exc)
    return f"📝 {data.get('name', '')}\n\n{data.get('body', '')}"
