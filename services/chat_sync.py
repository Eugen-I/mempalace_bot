"""services/chat_sync.py — единый сценарий ручной синхронизации чата.

Экспорт активного чата и вызов palace sync собраны здесь, чтобы команда
`/sync`, кнопка «Синхронизация» и callback настроек не дублировали сценарий.
UI-тексты и способ показа результата остаются в handler'ах.
"""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from config import CHATS_DIR
from services.palace_bridge import export_chat_verbatim, sync_to_palace

logger = logging.getLogger("ChatSync")

NO_ACTIVE_CHAT_MESSAGE = "⚠️ Нет активного чата для синхронизации."
EMPTY_CHAT_MESSAGE = "ℹ️ Чат пуст или не найден."


class ChatSyncStatus(Enum):
    NO_ACTIVE_CHAT = "no_active_chat"
    EMPTY_CHAT = "empty_chat"
    RESULT = "result"


@dataclass(frozen=True)
class ChatSyncResult:
    status: ChatSyncStatus
    message: str


async def sync_chat_file(chat_path: str, chat_name: str) -> str | None:
    """Экспортирует чат и синхронизирует его с дворцом.

    Возвращает `None`, если экспорт пуст, иначе текст результата синхронизации.
    Ошибки экспорта/синхронизации превращаются в пользовательское сообщение,
    как это уже делает `sync_to_palace`.
    """
    try:
        exported = export_chat_verbatim(chat_path, chat_name)
        if not exported:
            return None
        return await sync_to_palace(exported)
    except Exception as exc:
        logger.error(
            "Не удалось синхронизировать чат %s: %s",
            chat_path, exc, exc_info=True,
        )
        return f"❌ Ошибка синхронизации: {exc}"


async def sync_active_chat(
    uid: int, sessions: Mapping[int, str],
) -> ChatSyncResult:
    """Синхронизирует активный чат пользователя из переданного session-map."""
    fname = sessions.get(uid)
    if not fname:
        return ChatSyncResult(
            ChatSyncStatus.NO_ACTIVE_CHAT, NO_ACTIVE_CHAT_MESSAGE,
        )

    result = await sync_chat_file(os.path.join(CHATS_DIR, fname), fname)
    if result is None:
        return ChatSyncResult(ChatSyncStatus.EMPTY_CHAT, EMPTY_CHAT_MESSAGE)
    return ChatSyncResult(ChatSyncStatus.RESULT, result)
