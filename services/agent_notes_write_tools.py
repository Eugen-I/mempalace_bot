"""services/agent_notes_write_tools.py — write-инструменты Apple Notes для агента.

Обёртки над services.apple_notes: создание, дозапись, удаление (перемещение
в «Recently Deleted»), перемещение между папками. Каждое описание требует
от модели СНАЧАЛА узнать note_id через notes_search/notes_list.

Безопасность: инструменты зарегистрированы с is_write=True — по умолчанию
модель их не видит (include_write=False). Реальное выполнение никогда не
происходит напрямую из цикла run_agent: хендлер перехватывает вызов и
показывает пользователю карточку подтверждения (см. handlers/notes_agent.py
и параметр confirm_write в services/agent_engine.py).
"""

import logging

from services.agent_tools import CAT_NOTES, register_tool
from services.apple_notes import (
    AppleNotesError,
    create_note,
    delete_note,
    list_folders,
    move_note,
    update_note,
)

logger = logging.getLogger("AgentNotesWriteTools")


def _error_text(exc: Exception) -> str:
    return f"Ошибка Apple Notes: {exc}"


@register_tool(
    "notes_create",
    "Создать НОВУЮ заметку в Apple Notes. title — заголовок (обязательно), "
    "body — текст (необязательно), folder — имя папки (необязательно; "
    "узнай доступные папки через notes_list_folders). Перед вызовом сообщи "
    "пользователю, что собираешься создать. Язык заметки: русский или "
    "немецкий; китайский/японский/корейский запрещён.",
    schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Заголовок заметки"},
            "body": {"type": "string", "description": "Текст заметки (необязательно)"},
            "folder": {"type": "string", "description": "Имя папки (необязательно)"},
        },
        "required": ["title"],
    },
    category=CAT_NOTES,
    is_write=True,
)
def _notes_create(args: dict) -> str:
    try:
        note_id = create_note(
            title=args["title"],
            body=args.get("body", ""),
            folder=args.get("folder"),
        )
    except AppleNotesError as exc:
        return _error_text(exc)
    return f"✅ Заметка создана. id={note_id}"


@register_tool(
    "notes_update",
    "Дописать текст В КОНЕЦ существующей заметки Apple Notes (дозапись). "
    "note_id узнай СНАЧАЛА через notes_search или notes_list. Перед вызовом "
    "покажи пользователю, что именно будешь дописывать.",
    schema={
        "type": "object",
        "properties": {
            "note_id": {"type": "string", "description": "ID заметки"},
            "append_text": {"type": "string", "description": "Текст для дозаписи"},
        },
        "required": ["note_id", "append_text"],
    },
    category=CAT_NOTES,
    is_write=True,
)
def _notes_update(args: dict) -> str:
    try:
        result = update_note(args["note_id"], append_text=args["append_text"])
    except AppleNotesError as exc:
        return _error_text(exc)
    tail = (result.get("body") or "")[-300:]
    return f"✅ Заметка обновлена. id={result['id']}\n…{tail}"


@register_tool(
    "notes_delete",
    "Удалить заметку Apple Notes по ID — она перемещается в «Recently "
    "Deleted» (восстановима 30 дней). note_id узнай СНАЧАЛА через "
    "notes_search или notes_list. Обязательно назови пользователю заметку, "
    "которую собираешься удалить, ДО вызова. Пользователь подтвердит "
    "удаление отдельно.",
    schema={
        "type": "object",
        "properties": {
            "note_id": {"type": "string", "description": "ID заметки"},
        },
        "required": ["note_id"],
    },
    category=CAT_NOTES,
    is_write=True,
)
def _notes_delete(args: dict) -> str:
    try:
        ok = delete_note(args["note_id"])
    except AppleNotesError as exc:
        return _error_text(exc)
    if ok:
        return "✅ Заметка удалена (перемещена в «Recently Deleted»)."
    return "❌ Не удалось удалить заметку."


@register_tool(
    "notes_list_folders",
    "Список имён папок Apple Notes (без «Recently Deleted»). Вызови перед "
    "notes_create с folder или notes_move, чтобы узнать точные имена папок.",
    schema={"type": "object", "properties": {}},
    category=CAT_NOTES,
)
def _notes_list_folders(_args: dict) -> str:
    try:
        folders = list_folders()
    except AppleNotesError as exc:
        return _error_text(exc)
    if not folders:
        return "Папок не найдено."
    return "\n".join(f"- {name}" for name in folders)


@register_tool(
    "notes_move",
    "Переместить заметку Apple Notes в другую папку. note_id узнай СНАЧАЛА "
    "через notes_search или notes_list, имя папки — через notes_list_folders. "
    "Перед вызовом сообщи пользователю, куда перемещаешь.",
    schema={
        "type": "object",
        "properties": {
            "note_id": {"type": "string", "description": "ID заметки"},
            "target_folder": {"type": "string", "description": "Имя папки назначения"},
        },
        "required": ["note_id", "target_folder"],
    },
    category=CAT_NOTES,
    is_write=True,
)
def _notes_move(args: dict) -> str:
    try:
        result = move_note(args["note_id"], args["target_folder"])
    except AppleNotesError as exc:
        return _error_text(exc)
    return f"✅ Заметка перемещена в «{result['folder']}». id={result['id']}"
