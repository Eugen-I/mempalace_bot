"""Безопасный возврат в главное меню из любых хендлеров.

Баг №5: personal_note искал cmd_start через sys.modules без fallback —
кнопка «🏠 В меню» молча не срабатывала, когда модуль main не был в
sys.modules под ожидаемыми именами. Паттерн из handlers/palace/__init__.py:
try/except + `from main import cmd_start` + logger.error.
"""
import logging
import sys

logger = logging.getLogger("Menu")


async def go_main_menu(target):
    """Открыть главное меню бота для сообщения/callback.message.

    target: Message или CallbackQuery.message (имеет .answer / .edit_text).
    """
    if target is None:
        return
    try:
        mod = sys.modules.get("__main__") or sys.modules.get("main")
        if mod and hasattr(mod, "cmd_start"):
            await mod.cmd_start(target)
            return
        from main import cmd_start

        await cmd_start(target)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Не удалось открыть главное меню: {exc}", exc_info=True)
        try:
            await target.answer("❌ Не удалось открыть меню.")
        except Exception as exc2:  # noqa: BLE001
            logger.error(f"Не удалось уведомить об ошибке: {exc2}", exc_info=True)
