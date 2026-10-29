"""services/chat_store.py — единое чтение/запись JSON-файлов чатов.

Атомарная запись, резервные копии битых файлов и сериализованный
read-modify-write для добавления сообщений.
"""

import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime

logger = logging.getLogger("ChatStore")

_lock = threading.RLock()


def empty_chat() -> dict:
    return {"summary": "", "messages": []}


def _backup_corrupt_chat(filepath: str) -> str | None:
    """Копирует битый файл чата рядом с оригиналом, не удаляя его."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = f"{filepath}.corrupt.{timestamp}"
    try:
        shutil.copy2(filepath, backup_path)
    except OSError as exc:
        logger.error(
            "Не удалось создать резервную копию битого чата %s: %s",
            filepath, exc,
        )
        return None
    return backup_path


def load_chat(filepath: str) -> dict:
    """Читает чат, мигрирует list→dict и сохраняет копию битого JSON."""
    with _lock:
        if not os.path.exists(filepath):
            return empty_chat()

        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            backup_path = _backup_corrupt_chat(filepath)
            logger.error(
                "Битый JSON в чате %s: %s; резервная копия: %s",
                filepath, exc, backup_path or "не создана",
            )
            return empty_chat()
        except OSError as exc:
            logger.error("Не удалось прочитать чат %s: %s", filepath, exc)
            return empty_chat()

        if isinstance(data, list):
            data = {"summary": "", "messages": data}
            if not save_chat(filepath, data):
                logger.error("Не удалось мигрировать чат %s", filepath)
            return data

        if not isinstance(data, dict):
            backup_path = _backup_corrupt_chat(filepath)
            logger.error(
                "Некорректная структура чата %s (%s); резервная копия: %s",
                filepath, type(data).__name__, backup_path or "не создана",
            )
            return empty_chat()
        return data


def save_chat(filepath: str, data: dict) -> bool:
    """Атомарно сохраняет чат. Возвращает False, если запись не удалась."""
    tmp_path: str | None = None
    with _lock:
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=os.path.dirname(os.path.abspath(filepath)),
                delete=False, encoding="utf-8",
            ) as tmp:
                tmp_path = tmp.name
                json.dump(data, tmp, ensure_ascii=False, indent=2)
            os.replace(tmp_path, filepath)
            return True
        except Exception as exc:
            logger.error(
                "Не удалось сохранить чат %s: %s", filepath, exc, exc_info=True,
            )
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError as cleanup_exc:
                    logger.warning(
                        "Не удалось удалить временный файл %s: %s",
                        tmp_path, cleanup_exc,
                    )
            return False


def append_message(
    filepath: str,
    role: str,
    content: str,
    *,
    max_messages: int = 50,
    dedupe: bool = True,
) -> bool:
    """Добавляет сообщение под блокировкой (read-modify-write)."""
    with _lock:
        data = load_chat(filepath)
        messages = data.get("messages")
        if not isinstance(messages, list):
            messages = []

        if (
            dedupe
            and messages
            and isinstance(messages[-1], dict)
            and messages[-1].get("role") == role
            and messages[-1].get("content") == content
        ):
            return True

        messages.append({"role": role, "content": content})
        data["messages"] = messages[-max_messages:]
        return save_chat(filepath, data)
