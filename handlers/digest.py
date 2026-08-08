"""handlers/digest.py — команда /дайджест (ручной запрос утреннего дайджеста)."""

import logging

from aiogram import Router, types
from aiogram.filters import Command

from config import allowed_only
from services.digest import send_digest_to_chat

logger = logging.getLogger("DigestHandler")
router = Router()


@router.message(Command("дайджест", "digest"))
@allowed_only
async def cmd_digest(message: types.Message):
    try:
        sent = await send_digest_to_chat(message.bot, message.chat.id)
    except Exception as e:  # noqa: BLE001
        logger.error("[DIGEST] command failed: %s", e)
        return await message.answer("❌ Не удалось собрать дайджест.")
    if sent:
        return
    await message.answer("☀️ Всё чисто: напоминаний на сегодня и заметок вчера нет.")
