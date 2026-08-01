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
    При неожиданной ошибке логирует её и возвращает False.

    Args:
        message: Сообщение для редактирования.
        text: Новый текст сообщения.
        **kwargs: Дополнительные аргументы (parse_mode, reply_markup и т.д.).

    Returns:
        True, если сообщение было успешно отредактировано, False иначе.
    """
    if message is None or isinstance(message, InaccessibleMessage):
        return False
    try:
        await message.edit_text(text, **kwargs)
        return True
    except Exception as e:
        _log_error("safe_edit_text", e)
        return False


async def safe_answer(
    message: Message | InaccessibleMessage | None,
    text: str,
    **kwargs,
) -> bool:
    """Безопасно отправляет ответ на сообщение.

    Проверяет, что message не None и не InaccessibleMessage перед вызовом
    answer(). Если сообщение недоступно — молча возвращает False.
    При неожиданной ошибке логирует её и возвращает False.

    Args:
        message: Сообщение, на которое нужно ответить.
        text: Текст ответа.
        **kwargs: Дополнительные аргументы (parse_mode, reply_markup и т.д.).

    Returns:
        True, если ответ был успешно отправлен, False иначе.
    """
    if message is None or isinstance(message, InaccessibleMessage):
        return False
    try:
        await message.answer(text, **kwargs)
        return True
    except Exception as e:
        _log_error("safe_answer", e)
        return False


async def safe_answer_returning_message(
    message: Message | InaccessibleMessage | None,
    text: str,
    **kwargs,
) -> Message | None:
    """Безопасно отправляет ответ на сообщение и возвращает отправленное сообщение.

    Проверяет, что message не None и не InaccessibleMessage перед вызовом
    answer(). Если сообщение недоступно — возвращает None.
    При неожиданной ошибке логирует её и возвращает None.

    Args:
        message: Сообщение, на которое нужно ответить.
        text: Текст ответа.
        **kwargs: Дополнительные аргументы (parse_mode, reply_markup и т.д.).

    Returns:
        Отправленное сообщение, или None если отправка не удалась.
    """
    if message is None or isinstance(message, InaccessibleMessage):
        return None
    try:
        sent_message = await message.answer(text, **kwargs)
        return sent_message
    except Exception as e:
        _log_error("safe_answer_returning_message", e)
        return None


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


async def safe_send(
    message: Message | InaccessibleMessage | None,
    text: str,
    **kwargs,
) -> bool:
    """Безопасно отправляет новое сообщение (answer).

    Аналог safe_answer, но семантически для отправки нового сообщения
    в чат (не ответ на конкретное сообщение).

    Args:
        message: Сообщение, через которое отправить ответ.
        text: Текст сообщения.
        **kwargs: Дополнительные аргументы.

    Returns:
        True, если сообщение было успешно отправлено, False иначе.
    """
    if message is None or isinstance(message, InaccessibleMessage):
        return False
    try:
        await message.answer(text, **kwargs)
        return True
    except Exception as e:
        _log_error("safe_send", e)
        return False
