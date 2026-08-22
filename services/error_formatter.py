"""error_formatter.py
Централизованное форматирование ошибок для безопасного отображения пользователю.

Проблема: во многих местах кода используются `f"❌ Ошибка: {e}"` или `str(e)[:100]`,
что утекает внутренние детали (пути, stack traces, системная информация).

Решение: единая функция format_user_error, которая:
- Логирует полную ошибку с traceback (для разработчика)
- Возвращает пользователю безопасное, локализованное сообщение
- Маппит известные типы исключений на понятные сообщения
"""

import logging
from typing import Optional

logger = logging.getLogger("ErrorFormatter")


# Маппинг типов исключений на пользовательские сообщения
ERROR_MESSAGES = {
    FileNotFoundError: "❌ Файл не найден",
    PermissionError: "❌ Нет прав доступа",
    TimeoutError: "❌ Превышено время ожидания",
    ConnectionError: "❌ Ошибка соединения",
    ValueError: "❌ Некорректные данные",
    KeyError: "❌ Данные не найдены",
    OSError: "❌ Системная ошибка",
    RuntimeError: "❌ Ошибка выполнения",
    ImportError: "❌ Недоступная функция",
}


def format_user_error(
    e: Exception,
    context: str = "",
    default: str = "❌ Произошла ошибка. Попробуйте позже.",
) -> str:
    """Возвращает безопасное сообщение об ошибке для пользователя.

    Полная ошибка логируется для разработчика. Пользователь видит
    только обобщённое сообщение без путей, stack traces и деталей.

    Args:
        e: Исключение.
        context: Контекст вызова (для логов), например "voice_processing".
        default: Сообщение по умолчанию для неизвестных типов ошибок.

    Returns:
        Безопасная строка для отправки пользователю.
    """
    # Логируем полную ошибку для отладки
    log_context = f" [{context}]" if context else ""
    logger.error(f"Error{log_context}: {type(e).__name__}: {e}", exc_info=True)

    # Маппим известные типы
    for exc_type, msg in ERROR_MESSAGES.items():
        if isinstance(e, exc_type):
            return msg

    # Для остальных — безопасное общее сообщение
    return default


def format_user_error_with_detail(
    e: Exception,
    context: str = "",
    detail_map: Optional[dict[type[Exception], str]] = None,
    default: str = "❌ Произошла ошибка. Попробуйте позже.",
) -> str:
    """Расширенная версия с кастомным маппингом для конкретного контекста.

    Args:
        e: Исключение.
        context: Контекст для логов.
        detail_map: Дополнительный маппинг типов ошибок -> сообщений.
        default: Сообщение по умолчанию.

    Returns:
        Безопасная строка для пользователя.
    """
    log_context = f" [{context}]" if context else ""
    logger.error(f"Error{log_context}: {type(e).__name__}: {e}", exc_info=True)

    # Сначала проверяем кастомный маппинг
    if detail_map:
        for exc_type, msg in detail_map.items():
            if isinstance(e, exc_type):
                return msg

    # Затем глобальный маппинг
    return format_user_error(e, context, default)
