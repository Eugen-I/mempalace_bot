"""photos.py
Обработка фото: сохранение, анализ, удаление, список.
"""

import asyncio
import hashlib
import os
import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cachetools import TTLCache

from config import NOTES_DIR, PHOTOS_DIR, allowed_callback, allowed_only

from services.ai_engine import get_current_ai
from services.multimodal import (
    check_capability,
    delete_photo,
    encode_image_to_base64,
    list_photos,
    save_bot_photo,
)
from services.palace_bridge import search_palace_context
from services.prompts import get_smart_prompt
from services.text_formatter import safe_html_format, split_message

router = Router()
logger = logging.getLogger("PhotosHandler")

FILE_LIMIT = 50 * 1024 * 1024

_photo_delete_cache: TTLCache[str, str] = TTLCache(maxsize=500, ttl=300)


def get_ai_response_sync_wrapper(
    engine: str,
    model: str,
    messages: list,
    context: str = "",
    user_query: str = "",
    has_images: bool = False,
    **kwargs,
) -> str:
    from services.ai_engine import _sync_ai_call

    return _sync_ai_call(
        engine, model, messages, context, user_query, has_images, **kwargs,
    )


@router.message(F.photo | F.document)
@allowed_only
async def handle_photo(message: types.Message):
    logger.info(
        f"📸 [PHOTO_HANDLER] Сработал хендлер! Тип: {'Photo' if message.photo else 'Document'}",
    )
    try:
        if message.photo:
            file = message.photo[-1]
            logger.info(f"📸 [PHOTO] Получено фото. ID: {file.file_id}")
        elif message.document and message.document.mime_type.startswith("image/"):
            file = message.document
            logger.info(f"📄 [PHOTO] Получен документ-картинка. ID: {file.file_id}")
        else:
            return

        tmp_path = f"/tmp/{message.from_user.id}_{file.file_unique_id}.jpg"
        logger.info(f"⬇️ [PHOTO] Скачиваю файл в: {tmp_path}")

        file_info = await message.bot.get_file(file.file_id)
        await message.bot.download_file(file_info.file_path, destination=tmp_path)

        if not os.path.exists(tmp_path):
            raise FileNotFoundError(f"Файл не появился после скачивания: {tmp_path}")
        logger.info(f"✅ [PHOTO] Файл скачан. Размер: {os.path.getsize(tmp_path)} байт")

        saved_path = save_bot_photo(tmp_path, message.from_user.id)
        if not saved_path:
            raise RuntimeError("save_bot_photo вернул пустой путь.")
        logger.info(f"💾 [PHOTO] Фото сохранено в базу: {saved_path}")

        photos = list_photos()
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(
                text="🔍 Анализ последнего", callback_data="photo_analyze_last",
            ),
        )
        kb.row(
            types.InlineKeyboardButton(
                text="🗑 Удалить последнее", callback_data="photo_delete_last",
            ),
        )

        await message.answer(
            f"📸 Фото сохранено. В папке {len(photos)} фото.",
            reply_markup=kb.as_markup(),
        )
        logger.info("📤 [PHOTO] Ответ отправлен пользователю.")

    except Exception as e:
        logger.error(f"🚨 [PHOTO] Критическая ошибка: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка обработки: {str(e)[:100]}")


@router.callback_query(F.data == "photo_analyze_last")
@allowed_callback
async def cb_analyze_last_photo(cb: types.CallbackQuery):
    await cb.answer()

    photos = list_photos()
    if not photos:
        return await cb.message.answer("❌ Нет фото для анализа")

    last_photo = photos[0]
    photo_path = os.path.join(PHOTOS_DIR, last_photo)

    engine, model = get_current_ai()
    if not check_capability(model, "multimodal"):
        return await cb.message.answer(f"⚠️ {model} не поддерживает фото")

    status_msg = await cb.message.answer(
        f"🔍 Анализирую: `{last_photo}`...", parse_mode="Markdown",
    )

    try:
        b64 = encode_image_to_base64(photo_path)
        if not b64:
            raise ValueError("Base64 пуст")
        palace_context = await search_palace_context(
            "фото сон сюрреализм пиктореализм психология арихитипы идеи образы", limit=7,
        )

        system_instruction = get_smart_prompt(
            context=palace_context,
            query="анализ фотографии, символика, связь с заметками",
            has_images=True,
        )

        msgs = [
            {"role": "system", "content": system_instruction},
            {
                "role": "user",
                "content": (
                    "Опиши фото, символику, атмосферу. "
                    "Найди связи с моими личными записями или снами. "
                    "Придумай метафору или название."
                ),
            },
        ]

        answer = await asyncio.to_thread(
            lambda: get_ai_response_sync_wrapper(
                engine, model, msgs, context="", images=[b64],
            ),
        )

        safe_answer = safe_html_format(answer)
        full_text = f"📸 **Анализ `{last_photo}`:**\n\n{safe_answer}"
        parts = split_message(full_text)

        for part in parts:
            if part and part.strip():
                try:
                    await cb.message.answer(part, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Ошибка отправки с HTML: {e}")
                    await cb.message.answer(part, parse_mode=None)

    except Exception as e:
        logger.error(f"Ошибка анализа фото: {e}", exc_info=True)
        await cb.message.answer(f"❌ Ошибка: {str(e)[:200]}")
    finally:
        try:
            await status_msg.delete()
        except Exception:
            pass


@router.callback_query(F.data.startswith("show_links:"))
@allowed_callback
async def cb_show_links(cb: types.CallbackQuery):
    await cb.answer()
    fn = cb.data.split(":")[1]
    note_path = os.path.join(NOTES_DIR, fn)

    if not os.path.exists(note_path):
        return await cb.message.answer("❌ Файл не найден.")

    try:
        with open(note_path, encoding="utf-8") as f:
            content = f.read()

        if "## 🔗 Связанные записи" in content:
            links_section = content.split("## 🔗 Связанные записи")[1].strip()
            await cb.message.answer(
                f"🔗 Связанные записи:\n{links_section}", parse_mode=None,
            )
        else:
            await cb.message.answer(
                "⏳ Связи еще формируются или не найдены. Попробуйте через пару секунд.",
            )

    except Exception as e:
        logger.error(f"Ошибка показа связей: {e}")
        await cb.message.answer("❌ Не удалось загрузить связи.")


@router.callback_query(F.data == "photo_delete_last")
@allowed_callback
async def cb_delete_photo(cb: types.CallbackQuery):
    photos = list_photos()
    if photos and delete_photo(photos[0]):
        await cb.answer(f"🗑 Удалено: {photos[0]}", show_alert=True)
        await cb.message.edit_text(f"📸 Удалено. Осталось: {len(list_photos())}")
    else:
        await cb.answer("❌ Не удалось удалить", show_alert=True)


@router.message(Command("photos"))
@allowed_only
async def cmd_photos(message: types.Message):
    photos = list_photos()
    if not photos:
        return await message.answer("📁 Папка photos пуста.")

    text = f"📸 <b>Фото в базе ({len(photos)}):</b>\n\n"
    for i, p in enumerate(photos, 1):
        text += f"{i}) {p}\n"

    kb = InlineKeyboardBuilder()
    uid = str(message.from_user.id)

    for p in photos:
        short_id = hashlib.md5(f"{uid}:{p}".encode()).hexdigest()[:8]
        _photo_delete_cache[f"{uid}:{short_id}"] = p

        btn_text = p[:20] + ("..." if len(p) > 20 else "")
        kb.row(
            types.InlineKeyboardButton(
                text=f"🗑 {btn_text}",
                callback_data=f"del_photo:{uid}:{short_id}",
            ),
        )

    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("del_photo:"))
@allowed_callback
async def cb_del_photo(cb: types.CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) < 3:
        return await cb.answer("❌ Неверный формат запроса", show_alert=True)

    uid = parts[1]
    short_id = parts[2]
    cache_key = f"{uid}:{short_id}"

    fname = _photo_delete_cache.get(cache_key)
    if not fname:
        return await cb.answer(
            "❌ Сессия истекла. Откройте /photos заново", show_alert=True,
        )

    _photo_delete_cache.pop(cache_key, None)

    photos = list_photos()
    if fname not in photos:
        return await cb.answer("❌ Файл уже удален", show_alert=True)

    if delete_photo(fname):
        await cb.answer(f"🗑 Удалено: {fname}", show_alert=True)

        new_photos = list_photos()
        if not new_photos:
            await cb.message.edit_text("📁 Папка photos пуста.", reply_markup=None)
        else:
            text = f"📸 <b>Фото в базе ({len(new_photos)}):</b>\n\n"
            for i, p in enumerate(new_photos, 1):
                text += f"{i}) {p}\n"

            kb = InlineKeyboardBuilder()
            for p in new_photos:
                short_id = hashlib.md5(f"{uid}:{p}".encode()).hexdigest()[:8]
                _photo_delete_cache[f"{uid}:{short_id}"] = p
                btn_text = p[:20] + ("..." if len(p) > 20 else "")
                kb.row(
                    types.InlineKeyboardButton(
                        text=f"🗑 {btn_text}",
                        callback_data=f"del_photo:{uid}:{short_id}",
                    ),
                )

            await cb.message.edit_text(
                text, reply_markup=kb.as_markup(), parse_mode="HTML",
            )
    else:
        await cb.answer(f"❌ Не удалось удалить: {fname}", show_alert=True)
