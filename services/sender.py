"""sender.py
Отправка сообщений (текст/голос) в Telegram.
Вынесено из main.py для переиспользования.
"""

import logging
import os

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.text_formatter import safe_html_format, split_message
from services.tts_processor import (
    generate_voice_async,
    prepare_tts_text,
    split_tts_text,
)

logger = logging.getLogger("Sender")


async def _add_web_search_button(sent_msg: types.Message) -> None:
    """Добавить кнопку 'В интернет' к сообщению."""
    if sent_msg and hasattr(sent_msg, "edit_reply_markup"):
        try:
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(text="📥 В заметки", callback_data="p_sv"),
                types.InlineKeyboardButton(text="🌐 В интернет", callback_data="web_search"),
            )
            await sent_msg.edit_reply_markup(reply_markup=kb.as_markup())
        except Exception:
            pass


async def send_response_with_mode(message: types.Message, text: str, voice_mode: str):
    is_voice_enabled = voice_mode in ["voice", "both"]
    is_text_enabled = voice_mode in ["text", "both"]
    first_msg = None

    if is_text_enabled:
        parts = split_message(safe_html_format(text))
        for i, p in enumerate(parts):
            if p and p.strip():
                try:
                    msg = await message.answer(p, parse_mode="HTML")
                    if i == 0:
                        first_msg = msg
                except Exception:
                    pass

    if is_voice_enabled:
        try:
            tts_text = prepare_tts_text(text)
            if tts_text:
                tts_chunks = split_tts_text(tts_text, max_chars=1800)
                for chunk in tts_chunks:
                    ogg_files = await generate_voice_async(message.from_user.id, chunk)
                    for ogg in ogg_files:
                        try:
                            await message.answer_voice(types.FSInputFile(ogg))
                        except Exception:
                            pass
                        finally:
                            try:
                                os.remove(ogg)
                            except Exception:
                                pass
        except Exception as e:
            logger.error(f"Ошибка генерации голоса: {e}")

    if first_msg:
        await _add_web_search_button(first_msg)

    return first_msg


async def send_text_only(message: types.Message, text: str):
    parts = split_message(safe_html_format(text))
    last_msg = None
    for p in parts:
        if p and p.strip():
            try:
                last_msg = await message.answer(p, parse_mode="HTML")
            except Exception:
                pass
    if last_msg:
        await _add_web_search_button(last_msg)
