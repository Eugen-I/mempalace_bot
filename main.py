"""main.py | Bootstraps bot, registers routers, entry point.
   Message handlers extracted to handlers/messages.py"""

import asyncio
import os
import sys

from aiogram import F, Router, types
from aiogram.filters import Command

from config import API_TOKEN, ADMIN_ID, CHATS_DIR, DATA_DIR, allowed_only
from handlers.chat import user_sessions
from services.palace_bridge import export_chat_verbatim, sync_to_palace
from services.palace_mcp import get_mcp
from services.logging_setup import setup_logging

from services.bot_setup import bot, dp, init_bot

if API_TOKEN == "your_telegram_bot_token" or ADMIN_ID == 0:
    print("❌ Заполните TELEGRAM_BOT_TOKEN и ADMIN_ID в файле .env")
    print("📄 Скопируйте .env.example → .env и отредактируйте")
    sys.exit(1)

logger = setup_logging(DATA_DIR)
init_bot(logger)

from handlers import (  # noqa: E402
    chat, notes, palace, pdf, personal_note,
    reminder, settings, search,
)
from handlers import photos, reactions, transkript, voice, youtube_ui  # noqa: E402
from handlers.messages import process_user_message  # noqa: E402


def _safe_include(router):
    try:
        dp.include_router(router)
    except RuntimeError:
        pass


_safe_include(chat.router)
_safe_include(settings.router)
_safe_include(photos.router)
_safe_include(notes.router)
_safe_include(pdf.router)
_safe_include(voice.router)
_safe_include(palace.router)
_safe_include(personal_note.router)
_safe_include(reminder.router)
_safe_include(youtube_ui.router)
_safe_include(search.router)
_safe_include(reactions.router)
_safe_include(transkript.router)

fallback_router = Router()
dp.include_router(fallback_router)


@dp.message(Command("start"))
@allowed_only
async def cmd_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="📝 Личная заметка"),
                types.KeyboardButton(text="📖 Личные мысли"),
            ],
            [types.KeyboardButton(text="🆕 Новый диалог")],
            [
                types.KeyboardButton(text="📂 Список чатов"),
                types.KeyboardButton(text="⚙️ Настройки"),
            ],
            [
                types.KeyboardButton(text="🔍 Поиск по крылу"),
                types.KeyboardButton(text="🔄 Синхронизация"),
            ],
            [
                types.KeyboardButton(text="📹 Скачать видео"),
                types.KeyboardButton(text="🎵 Скачать MP3"),
            ],
            [
                types.KeyboardButton(text="🏰 Дворец"),
                types.KeyboardButton(text="📜 Транскрипты"),
            ],
        ],
        resize_keyboard=True,
    )
    await message.answer("🦾 MemPalace запущен.", reply_markup=kb)
    logger.info(f"User {message.from_user.id} started.")


@fallback_router.message(F.text == "🏰 Дворец")
@allowed_only
async def cmd_palace_button(message: types.Message):
    from handlers.palace import cmd_palace

    await cmd_palace(message)


@fallback_router.message(F.text == "🔄 Синхронизация")
@allowed_only
async def cmd_sync_button(message: types.Message):
    fname = user_sessions.get(message.from_user.id)
    if not fname:
        return await message.answer("⚠️ Нет активного чата для синхронизации.")
    fpath = os.path.join(CHATS_DIR, fname)
    exported = export_chat_verbatim(fpath, fname)
    if not exported:
        return await message.answer("ℹ️ Чат пуст или не найден.")
    status = await message.answer("🔄 Синхронизирую с MemPalace (verbatim)...")
    result = await sync_to_palace(exported)
    await status.edit_text(result)


fallback_router.message()(allowed_only(process_user_message))


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        mcp = get_mcp()
        await mcp.start()
        logger.info("MCP client started.")
    except Exception as e:
        logger.warning(f"MCP client failed to start: {e}")

    try:
        from services.whisper_service import prewarm

        prewarm()
        logger.info("Whisper model pre-warmed.")
    except Exception as e:
        logger.warning(f"Whisper pre-warm failed: {e}")

    logger.info("Bot polling started.")

    from services.reminder_scheduler import start_scheduler

    start_scheduler(bot)

    await dp.start_polling(
        bot, allowed_updates=["message", "callback_query", "message_reaction"],
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Bot stopped.")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}", exc_info=True)
