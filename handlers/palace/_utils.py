"""_utils.py
Утилитарные обёртки для безопасной работы с Telegram-сообщениями.

Проблема:
  В aiogram 3.x CallbackQuery.message имеет тип Message | InaccessibleMessage | None.
  Обращение к .edit_text(), .answer(), .delete() и другим методам без проверки
  на None или InaccessibleMessage вызывает AttributeError в рантайме.

Решение:
  Данный модуль предоставляет функции-обёртки, которые безопасно проверяют
  тип сообщения перед вызовом метода. Если сообщение недоступно (None или
  InaccessibleMessage), вызов просто пропускается.

Логирование ошибок:
  По умолчанию ошибки логируются через стандартный logging-модуль проекта.
  Поведение можно отключить, вызвав set_error_logging(False).
  Это позволяет запускать бот как с логированием ошибок, так и без него —
  аналогично настройке PalaceManager_TelegrammBot.command, где есть
  интерактивный режим (логи в консоль) и фоновый режим (логи в файл).
"""

import logging
import re
from typing import Literal, overload

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InaccessibleMessage, Message

logger = logging.getLogger("PalaceUtils")

_error_logging_enabled = True


def set_error_logging(enabled: bool) -> None:
    """Включает или выключает логирование ошибок в утилитарных функциях.

    Args:
        enabled: True — ошибки будут логироваться, False — молча пропускать.

    Пример:
        >>> from handlers.palace._utils import set_error_logging
        >>> set_error_logging(False)  # отключить логирование
        >>> set_error_logging(True)   # включить логирование
    """
    global _error_logging_enabled
    _error_logging_enabled = enabled


def _log_error(context: str, error: Exception) -> None:
    """Логирует ошибку, если логирование включено.

    Args:
        context: Описание контекста, где произошла ошибка (например, "edit_text").
        error: Исключение, которое было поймано.
    """
    if _error_logging_enabled:
        logger.error("[PALACE_UTILS] Ошибка в %s: %s", context, error, exc_info=True)


async def safe_edit_text(
    message: Message | InaccessibleMessage | None,
    text: str,
    **kwargs,
) -> bool:
    """Безопасно редактирует сообщение.

    Проверяет, что message не None и не InaccessibleMessage перед вызовом
    edit_text(). Если сообщение недоступно — молча возвращает False.
    Если сообщение не содержит текста (например, документ/медиа с кнопками),
    отправляет новый ответ через answer().
    Ошибку "message is not modified" считает успешным завершением.
    При неожиданной ошибке логирует её и возвращает False.

    Args:
        message: Сообщение для редактирования.
        text: Новый текст сообщения.
        **kwargs: Дополнительные аргументы (parse_mode, reply_markup и т.д.).

    Returns:
        True, если сообщение было успешно отредактировано или отправлено заново, False иначе.
    """
    if message is None or isinstance(message, InaccessibleMessage):
        return False
    try:
        await message.edit_text(text, **kwargs)
        return True
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "message is not modified" in err_msg:
            return True
        if "there is no text in the message to edit" in err_msg:
            try:
                if hasattr(message, "edit_reply_markup"):
                    try:
                        await message.edit_reply_markup(reply_markup=None)
                    except Exception:
                        pass
                await message.answer(text, **kwargs)
                return True
            except Exception as answer_err:
                _log_error("safe_edit_text_fallback", answer_err)
                return False
        _log_error("safe_edit_text", e)
        return False
    except Exception as e:
        _log_error("safe_edit_text", e)
        return False


async def safe_delete(
    message: Message | InaccessibleMessage | None,
    **kwargs,
) -> bool:
    """Безопасно удаляет сообщение.

    Проверяет, что message не None и не InaccessibleMessage перед вызовом
    delete(). Если сообщение недоступно — молча возвращает False.
    При неожиданной ошибке логирует её и возвращает False.

    Args:
        message: Сообщение для удаления.
        **kwargs: Дополнительные аргументы.

    Returns:
        True, если сообщение было успешно удалено, False иначе.
    """
    if message is None or isinstance(message, InaccessibleMessage):
        return False
    try:
        await message.delete(**kwargs)
        return True
    except Exception as e:
        _log_error("safe_delete", e)
        return False


async def safe_answer_voice(
    message: Message | InaccessibleMessage | None,
    voice,
    **kwargs,
) -> bool:
    """Безопасно отправляет голосовое сообщение.

    Проверяет, что message не None и не InaccessibleMessage перед вызовом
    answer_voice(). Если сообщение недоступно — молча возвращает False.
    При неожиданной ошибке логирует её и возвращает False.

    Args:
        message: Сообщение, на которое нужно ответить голосом.
        voice: Аудиофайл для отправки.
        **kwargs: Дополнительные аргументы.

    Returns:
        True, если голосовое сообщение было успешно отправлено, False иначе.
    """
    if message is None or isinstance(message, InaccessibleMessage):
        return False
    try:
        await message.answer_voice(voice, **kwargs)
        return True
    except Exception as e:
        _log_error("safe_answer_voice", e)
        return False


@overload
async def safe_send(
    message: Message | InaccessibleMessage | None,
    text: str,
    *,
    return_message: Literal[False] = False,
    **kwargs,
) -> bool: ...


@overload
async def safe_send(
    message: Message | InaccessibleMessage | None,
    text: str,
    *,
    return_message: Literal[True],
    **kwargs,
) -> Message | None: ...


async def safe_send(
    message: Message | InaccessibleMessage | None,
    text: str,
    *,
    return_message: bool = False,
    **kwargs,
) -> Message | bool | None:
    """Безопасно отправляет сообщение через ``answer``.

    Единый helper для двух вариантов:
    - по умолчанию возвращает ``True``/``False``;
    - ``return_message=True`` возвращает отправленное сообщение или ``None``.

    Args:
        message: Сообщение, через которое отправить ответ.
        text: Текст сообщения.
        return_message: Вернуть отправленное сообщение вместо bool.
        **kwargs: Дополнительные аргументы (parse_mode, reply_markup и т.д.).

    Returns:
        bool или Message | None в зависимости от ``return_message``.
    """
    if message is None or isinstance(message, InaccessibleMessage):
        return None if return_message else False
    try:
        sent_message = await message.answer(text, **kwargs)
        return sent_message if return_message else True
    except Exception as e:
        _log_error("safe_send", e)
        return None if return_message else False


WING_NAME_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")


def sanitize_wing_name(name: str) -> str:
    """Санитизирует имя крыла: убирает path traversal (.., /, \\) и argument injection (-flag).

    Args:
        name: Сырое имя крыла от пользователя.

    Returns:
        Санитизированное имя крыла (сохраняет unicode буквы, цифры, _, -, пробелы -> _).

    Raises:
        ValueError: Если имя невалидно (пустое, начинается с -, содержит .. или / или \\).
    """
    if not name or not isinstance(name, str):
        raise ValueError("Wing name cannot be empty")
    # Приводим к нижнему регистру, заменяем пробелы на _
    sanitized = name.strip().lower().replace(" ", "_")
    # Проверяем на path traversal и argument injection
    if sanitized.startswith("-") or ".." in sanitized or "/" in sanitized or "\\" in sanitized:
        raise ValueError("Invalid wing name")
    if not sanitized or len(sanitized) > 64:
        raise ValueError("Wing name contains no valid characters or too long")
    return sanitized
