"""
main.py | ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ
✅ Убраны дубликаты bot/dp/middleware
✅ Исправлена сигнатура middleware под aiogram 3.x
✅ ИСПРАВЛЕНИЕ ОШИБКИ: types.InlineKeyboardBuilder -> InlineKeyboardBuilder
"""
import asyncio
import logging
import os
import json
import sys
import hashlib
import re
from typing import Dict  # если ещё не импортировано
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
# 1. КОНФИГУРАЦИЯ
from config import (
    API_TOKEN, allowed_only, allowed_callback, ADMIN_ID, ALLOWED_IDS,
    CHATS_DIR, NOTES_DIR, INSIGHTS_DIR, RESEARCH_DIR, DATA_DIR, PHOTOS_DIR
)

# 2. СЕРВИСЫ
from services.ai_engine import get_current_ai, get_ai_response_async
from services.text_formatter import safe_html_format, split_message
from services.tts_processor import get_voice_settings, generate_voice_async, prepare_tts_text, split_tts_text
from services.palace_bridge import search_palace_context, export_chat_verbatim, sync_to_palace
from services.code_mode import is_coding_context, load_coding_prompt, ensure_project_dir, read_project_files
from services.multimodal import list_photos, encode_image_to_base64, check_capability, save_bot_photo, delete_photo
from handlers.chat import load_chat, save_chat, user_sessions, waiting_for_name
from services.auto_sync import auto_sync_chat
from services.memory import get_memory_context, extract_and_store_facts
from services.youtube import download_video, download_audio, transcribe_audio
import secrets

# 🔍 Sanity check: все ли пути импортированы?
assert 'PHOTOS_DIR' in dir(), "❌ PHOTOS_DIR не импортирован из config!"

if API_TOKEN == "your_telegram_bot_token" or ADMIN_ID == 0:
    print("❌ Заполните TELEGRAM_BOT_TOKEN и ADMIN_ID в файле .env")
    print("📄 Скопируйте .env.example → .env и отредактируйте")
    sys.exit(1)

# 3. ЛОГИРОВАНИЕ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(DATA_DIR, "bot_debug.log"), encoding='utf-8')
    ]
)
logger = logging.getLogger("MainHandler")
from aiogram.types import MessageReactionUpdated, ReactionTypeEmoji

# 🧠 Кэш последних ответов ИИ для реакций {chat_id: {message_id: text}}
_ai_msg_cache: dict[int, dict[int, str]] = {}

def cache_ai_response(chat_id: int, message_id: int, text: str):
    """Сохраняет текст ответа ИИ для последующей обработки реакций."""
    if chat_id not in _ai_msg_cache:
        _ai_msg_cache[chat_id] = {}
    _ai_msg_cache[chat_id][message_id] = text
    # Ограничиваем кэш 50 сообщениями на чат, чтобы не тратить память
    if len(_ai_msg_cache[chat_id]) > 50:
        oldest_id = min(_ai_msg_cache[chat_id].keys())
        del _ai_msg_cache[chat_id][oldest_id]

# 🗑️ Кэш для маппинга коротких ID -> полные имена файлов (для кнопок удаления)
_photo_delete_cache: Dict[str, str] = {}
_pending_wing_search: Dict[int, str] = {}
_sync_counter: Dict[int, int] = {}
_sync_in_progress: Dict[int, bool] = {}
_yt_waiting_url: Dict[int, str] = {}   # uid -> "video"/"audio"
_yt_quality_url: Dict[int, str] = {}   # uid -> URL (ожидание выбора качества)
_yt_audio_cache: Dict[str, str] = {}   # sid -> путь к mp3 (для транскрибации)

# 4. ИНИЦИАЛИЗАЦИЯ (СТРОГО ОДИН РАЗ)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# 5. MIDDLEWARE БЕЗОПАСНОСТИ (aiogram 3.x)
async def security_middleware(handler, event, data):
    uid = None
    if hasattr(event, 'from_user') and event.from_user: uid = event.from_user.id
    elif hasattr(event, 'message') and event.message and event.message.from_user: uid = event.message.from_user.id
    elif hasattr(event, 'callback_query') and event.callback_query and event.callback_query.from_user: uid = event.callback_query.from_user.id
    
    if uid and uid not in ALLOWED_IDS:
        logger.warning(f"[🔒 SECURITY] Blocked user: {uid}")
        return  # Блокируем, не передаём дальше
    return await handler(event, data)  # Передаём управление

dp.message.middleware(security_middleware)
dp.callback_query.middleware(security_middleware)

# 6. ПОДКЛЮЧЕНИЕ РОУТЕРОВ
from handlers import chat, settings, notes, pdf, voice
dp.include_router(chat.router)
dp.include_router(settings.router)
dp.include_router(notes.router)
dp.include_router(pdf.router)
dp.include_router(voice.router)

fallback_router = Router()
dp.include_router(fallback_router)

# 7. ХЕНДЛЕРЫ
@dp.message(Command("start"))
@allowed_only
async def cmd_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="🆕 Новый диалог")],
        [types.KeyboardButton(text="📂 Список чатов"), types.KeyboardButton(text="⚙️ Настройки")],
        [types.KeyboardButton(text="🔍 Поиск по крылу"), types.KeyboardButton(text="🔄 Синхронизация")],
        [types.KeyboardButton(text="📹 Скачать видео"), types.KeyboardButton(text="🎵 Скачать MP3")],
    ], resize_keyboard=True)
    await message.answer("🦾 MemPalace запущен.", reply_markup=kb)
    logger.info(f"User {message.from_user.id} started.")

# ✅ ИСПРАВЛЕННЫЙ ХЕНДЛЕР ФОТО (TRY/EXCEPT + СОВРЕМЕННОЕ СКАЧИВАНИЕ)
# @fallback_router.message(F.photo)
# @allowed_only
# async def handle_photo(message: types.Message):
#     try:
#         photo = message.photo[-1]
#         tmp_path = f"/tmp/{message.from_user.id}_{photo.file_unique_id}.jpg"
#         await message.download(destination=tmp_path)  # ✅ Aiogram 3.x способ
        
#         saved_path = save_bot_photo(tmp_path, message.from_user.id)
#         if not saved_path:
#             return await message.answer("❌ Ошибка сохранения фото.")

#         photos = list_photos()
#         # ✅ Исправлено: InlineKeyboardBuilder() вместо InlineKeyboardBuilder()
#         kb = InlineKeyboardBuilder()
#         kb.row(types.InlineKeyboardButton(text="🔍 Анализ последнего", callback_data="photo_analyze_last"))
#         kb.row(types.InlineKeyboardButton(text="🗑 Удалить последнее", callback_data="photo_delete_last"))
#         await message.answer(f"📸 Фото сохранено. В папке {len(photos)} фото.", reply_markup=kb.as_markup())
#     except Exception as e:
#         logger.error(f"📷 Ошибка обработки фото: {e}", exc_info=True)
#         await message.answer("❌ Ошибка при обработке фото.")

@fallback_router.message(F.photo | F.document)
@allowed_only  # Если хотите убрать проверку доступа для тестов, закомментируйте эту строку
async def handle_photo(message: types.Message):
    logger.info(f"📸 [PHOTO_HANDLER] Сработал хендлер! Тип: {'Photo' if message.photo else 'Document'}")
    try:
        # 1. Определяем объект файла (Фото или Документ)
        if message.photo:
            file = message.photo[-1]
            logger.info(f"📸 [PHOTO] Получено фото. ID: {file.file_id}")
        elif message.document and message.document.mime_type.startswith('image/'):
            file = message.document
            logger.info(f"📄 [PHOTO] Получен документ-картинка. ID: {file.file_id}")
        else:
            return  # Игнорируем не-картинки

        # 2. Формируем путь
        tmp_path = f"/tmp/{message.from_user.id}_{file.file_unique_id}.jpg"
        logger.info(f"⬇️ [PHOTO] Скачиваю файл в: {tmp_path}")

        # 3. Скачиваем через bot (самый надежный метод в aiogram 3)
        file_info = await message.bot.get_file(file.file_id)
        await message.bot.download_file(file_info.file_path, destination=tmp_path)
        
        if not os.path.exists(tmp_path):
            raise FileNotFoundError(f"Файл не появился после скачивания: {tmp_path}")
        logger.info(f"✅ [PHOTO] Файл скачан. Размер: {os.path.getsize(tmp_path)} байт")

        # 4. Сохраняем в общую папку
        saved_path = save_bot_photo(tmp_path, message.from_user.id)
        if not saved_path:
            raise RuntimeError("save_bot_photo вернул пустой путь.")
        logger.info(f"💾 [PHOTO] Фото сохранено в базу: {saved_path}")

        # 5. Отправляем ответ с кнопками
        photos = list_photos()
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="🔍 Анализ последнего", callback_data="photo_analyze_last"))
        kb.row(types.InlineKeyboardButton(text="🗑 Удалить последнее", callback_data="photo_delete_last"))
        
        await message.answer(f"📸 Фото сохранено. В папке {len(photos)} фото.", reply_markup=kb.as_markup())
        logger.info(f"📤 [PHOTO] Ответ отправлен пользователю.")

    except Exception as e:
        logger.error(f"🚨 [PHOTO] Критическая ошибка: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка обработки: {str(e)[:100]}")


# КОЛЛБЭКИ ДЛЯ ФОТО
@fallback_router.callback_query(F.data == "photo_analyze_last")
@allowed_callback
async def cb_analyze_last_photo(cb: types.CallbackQuery):
    # ✅ 1. СРАЗУ отвечаем на callback (до долгой обработки!)
    await cb.answer()
    
    photos = list_photos()
    if not photos: 
        return await cb.message.answer("❌ Нет фото для анализа")
    
    last_photo = photos[0]
    photo_path = os.path.join(PHOTOS_DIR, last_photo)
    
    engine, model = get_current_ai()
    if not check_capability(model, "multimodal"):
        return await cb.message.answer(f"⚠️ {model} не поддерживает фото")
    
    # ✅ 2. Отправляем НОВОЕ сообщение о статусе
    status_msg = await cb.message.answer(f"🔍 Анализирую: `{last_photo}`...", parse_mode="Markdown")
    
    try:
        b64 = encode_image_to_base64(photo_path)
        if not b64: 
            raise ValueError("Base64 пуст")
        # ✅ 1. Ищем контекст для анализа (сны, идеи, психология)
        palace_context = await search_palace_context("фото сон сюрреализм пиктореализм психология арихитипы идеи образы", limit=7)
        
        # ✅ 2. Используем умный промпт вместо удаленной константы
        from services.prompts import get_smart_prompt
        system_instruction = get_smart_prompt(
            context=palace_context,
            query="анализ фотографии, символика, связь с заметками",
            has_images=True
        )

        msgs = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": "Опиши фото, символику, атмосферу. Найди связи с моими личными записями или снами. Придумай метафору или название."}
    ]
        
        answer = await asyncio.to_thread(
            lambda: get_ai_response_sync_wrapper(engine, model, msgs, context="", images=[b64])
        )
        
        # ✅ 4. БЕЗОПАСНАЯ отправка: экранируем HTML + разбиваем на части
        safe_answer = safe_html_format(answer)
        full_text = f"📸 **Анализ `{last_photo}`:**\n\n{safe_answer}"
        parts = split_message(full_text)
        
        for part in parts:
            if part and part.strip():
                try:
                    # Пробуем отправить с форматированием
                    await cb.message.answer(part, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Ошибка отправки с HTML: {e}")
                    # Fallback: отправляем как простой текст
                    await cb.message.answer(part, parse_mode=None)
                    
    except Exception as e:
        logger.error(f"Ошибка анализа фото: {e}", exc_info=True)
        await cb.message.answer(f"❌ Ошибка: {str(e)[:200]}")
    finally:
        # ✅ 5. Удаляем статус-сообщение
        try:
            await status_msg.delete()
        except:
            pass

@fallback_router.callback_query(F.data.startswith("show_links:"))
@allowed_callback
async def cb_show_links(cb: types.CallbackQuery):
    await cb.answer()
    fn = cb.data.split(":")[1]
    note_path = os.path.join(NOTES_DIR, fn)
    
    if not os.path.exists(note_path):
        return await cb.message.answer("❌ Файл не найден.")
   
    try:
        with open(note_path, "r", encoding="utf-8") as f:
            content = f.read()
    
        if "## 🔗 Связанные записи" in content:
            links_section = content.split("## 🔗 Связанные записи")[1].strip()
            await cb.message.answer(f"🔗 Связанные записи:\n{links_section}", parse_mode=None)
        else:
            await cb.message.answer("⏳ Связи еще формируются или не найдены. Попробуйте через пару секунд.")
    
    except Exception as e:
        logger.error(f"Ошибка показа связей: {e}")
        await cb.message.answer("❌ Не удалось загрузить связи.")


@fallback_router.callback_query(F.data == "photo_delete_last")
@allowed_callback
async def cb_delete_photo(cb: types.CallbackQuery):
    photos = list_photos()
    if photos and delete_photo(photos[0]):
        await cb.answer(f"🗑 Удалено: {photos[0]}", show_alert=True)
        await cb.message.edit_text(f"📸 Удалено. Осталось: {len(list_photos())}")
    else:
        await cb.answer("❌ Не удалось удалить", show_alert=True)

# 📸 КОМАНДА /photos - показать список фото
@fallback_router.message(Command("photos"))
@allowed_only
async def cmd_photos(message: types.Message):
    from services.multimodal import list_photos
    
    photos = list_photos()
    if not photos:
        return await message.answer("📁 Папка photos пуста.")
    
    text = f"📸 <b>Фото в базе ({len(photos)}):</b>\n\n"
    for i, p in enumerate(photos, 1):
        text += f"{i}) {p}\n"
    
    kb = InlineKeyboardBuilder()
    uid = str(message.from_user.id)  # ✅ Преобразуем в строку для кэша
    
    for p in photos:
        # Генерируем короткий уникальный ID (8 символов) на основе хэша + user_id
        short_id = hashlib.md5(f"{uid}:{p}".encode()).hexdigest()[:8]
        _photo_delete_cache[f"{uid}:{short_id}"] = p
        
        # Обрезаем текст кнопки для красоты
        btn_text = p[:20] + ('...' if len(p) > 20 else '')
        kb.row(types.InlineKeyboardButton(
            text=f"🗑 {btn_text}", 
            callback_data=f"del_photo:{uid}:{short_id}"  # Формат: del_photo:USER_ID:SHORT_ID
        ))
    
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@fallback_router.callback_query(F.data.startswith("del_photo:"))
@allowed_callback
async def cb_del_photo(cb: types.CallbackQuery):
    from services.multimodal import delete_photo, list_photos
    
    # Парсим callback_data: del_photo:USER_ID:SHORT_ID
    parts = cb.data.split(":")
    if len(parts) < 3:
        return await cb.answer("❌ Неверный формат запроса", show_alert=True)
    
    uid = parts[1]
    short_id = parts[2]
    cache_key = f"{uid}:{short_id}"
    
    # Восстанавливаем полное имя файла из кэша
    fname = _photo_delete_cache.get(cache_key)
    if not fname:
        return await cb.answer("❌ Сессия истекла. Откройте /photos заново", show_alert=True)
    
    # Удаляем из кэша после использования (защита от повторного нажатия)
    del _photo_delete_cache[cache_key]
    
    # Проверяем, что файл ещё существует в папке
    photos = list_photos()
    if fname not in photos:
        return await cb.answer("❌ Файл уже удален", show_alert=True)
    
    # Выполняем удаление
    if delete_photo(fname):
        await cb.answer(f"🗑 Удалено: {fname}", show_alert=True)
        
        # ✅ Обновляем сообщение со списком фото
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
                btn_text = p[:20] + ('...' if len(p) > 20 else '')
                kb.row(types.InlineKeyboardButton(
                    text=f"🗑 {btn_text}", 
                    callback_data=f"del_photo:{uid}:{short_id}"
                ))
            
            await cb.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await cb.answer(f"❌ Не удалось удалить: {fname}", show_alert=True)


# 🎭 Роутер для обработки реакций
reaction_router = Router()
dp.include_router(reaction_router)

@reaction_router.message_reaction()
async def handle_ai_reaction(event: MessageReactionUpdated):
    """Обрабатывает реакции на сообщения бота и сохраняет контент в папки."""
    if not event.user or event.user.id not in ALLOWED_IDS:
        return
    if not event.new_reaction:
        return

    # 🔍 Нормализация эмодзи (удаляем селекторы вариантов, ZWJ и гендерные модификаторы)
    def normalize_emoji(e: str) -> str:
        return e.replace("\uFE0F", "").replace("\u200D", "").replace("\u2642", "").replace("\u2640", "").strip()

    # Маппинг базовых эмодзи на действия
    action_map = {
        "👍": "note",
        "❤": "insight",   # ❤️ без FE0F становится ❤
        "🤷": "research"  # 🤷‍♂️/🤷‍♀️ нормализуется до 🤷
    }

    action = None
    for react in event.new_reaction:
        if isinstance(react, ReactionTypeEmoji):
            norm = normalize_emoji(react.emoji)
            if norm in action_map:
                action = action_map[norm]
                logger.info(f"[REACTION] Detected {react.emoji} -> normalized: {norm} -> action: {action}")
                break

    if not action:
        return  # Не наша реакция

    chat_id = event.chat.id
    msg_id = event.message_id
    ai_text = _ai_msg_cache.get(chat_id, {}).get(msg_id)

    if not ai_text:
        await event.bot.send_message(chat_id, "⚠️ Сообщение не найдено в кэше. Используйте !! или ? вручную.")
        return

    try:
        ts = datetime.now().strftime('%Y%m%d_%H%M')
        if action == "note":
            fn = f"nt_react_{ts}.txt"
            path = os.path.join(NOTES_DIR, fn)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"[Реакция 👍]\n{ai_text}")
            await event.bot.send_message(chat_id, f"💾 Сохранено в `my_notes`: `{fn}`", parse_mode="Markdown")

        elif action == "insight":
            fn = f"ext_react_{ts}.txt"
            path = os.path.join(INSIGHTS_DIR, fn)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"!! [Реакция ❤️]\nИсточник: msg_{msg_id}\nИТОГ:\n{ai_text}")
            await event.bot.send_message(chat_id, f"💡 Сохранено в `Insights`: `{fn}`", parse_mode="Markdown")

        elif action == "research":
            fn = f"ext_react_{ts}.txt"
            path = os.path.join(RESEARCH_DIR, fn)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"? [Реакция 🤷‍♂️]\nИсточник: msg_{msg_id}\nИТОГ:\n{ai_text}")
            await event.bot.send_message(chat_id, f"🔍 Сохранено в `Research`: `{fn}`", parse_mode="Markdown")

    except Exception as e:
        logger.error(f"[REACTION_SAVE] Error: {e}", exc_info=True)
        await event.bot.send_message(chat_id, f"❌ Ошибка сохранения: {str(e)[:100]}")

#ФУНКЦИЯ ОТПРАВКИ (ТЕКСТ/ГОЛОС)
async def send_response_with_mode(message: types.Message, text: str, voice_mode: str):
    is_voice_enabled = voice_mode in ["voice", "both"]
    is_text_enabled = voice_mode in ["text", "both"]
    first_msg = None  # ✅ Запоминаем первое сообщение

    if is_text_enabled:
        parts = split_message(safe_html_format(text))
        for i, p in enumerate(parts):
            if p and p.strip():
                try:
                    msg = await message.answer(p, parse_mode="HTML")
                    if i == 0: first_msg = msg  # ✅ Сохраняем только первое
                except: pass

    if is_voice_enabled:
        try:
            tts_text = prepare_tts_text(text)
            if tts_text:
                tts_chunks = split_tts_text(tts_text, max_chars=1800)
                for chunk in tts_chunks:
                    ogg_files = await generate_voice_async(message.from_user.id, chunk)
                    for ogg in ogg_files:
                        try: await message.answer_voice(types.FSInputFile(ogg))
                        except: pass
                        finally:
                            try: os.remove(ogg)
                            except: pass
        except Exception as e:
            logger.error(f"Ошибка генерации голоса: {e}")

    return first_msg


# КНОПКА: Поиск по крылу
@fallback_router.message(F.text == "🔍 Поиск по крылу")
@allowed_only
async def cmd_wing_search_prompt(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🌙 Сны", callback_data="wing_search:dreams"))
    kb.row(types.InlineKeyboardButton(text="💻 Проекты", callback_data="wing_search:projects"))
    kb.row(types.InlineKeyboardButton(text="🏛 Философия", callback_data="wing_search:philosophy"))
    kb.row(types.InlineKeyboardButton(text="🎨 Творчество", callback_data="wing_search:creative"))
    kb.row(types.InlineKeyboardButton(text="🧠 Психология", callback_data="wing_search:psychology"))
    await message.answer("🔍 Выберите крыло для поиска:", reply_markup=kb.as_markup())


@fallback_router.callback_query(F.data.startswith("wing_search:"))
@allowed_callback
async def cb_wing_search_select(callback: types.CallbackQuery):
    wing = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    _pending_wing_search[uid] = wing
    wing_names = {
        "dreams": "🌙 Сны",
        "projects": "💻 Проекты",
        "philosophy": "🏛 Философия",
        "creative": "🎨 Творчество",
        "psychology": "🧠 Психология",
    }
    await callback.message.edit_text(
        f"✏️ Введите текст для поиска в крыле {wing_names.get(wing, wing)}:"
    )
    await callback.answer()


# КНОПКА: Синхронизация
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


async def _auto_sync_wrapper(uid: int, fname: str, fpath: str):
    try:
        await auto_sync_chat(uid, fname, fpath)
    finally:
        _sync_in_progress[uid] = False


# КНОПКА: Скачать видео
@fallback_router.message(F.text == "📹 Скачать видео")
@allowed_only
async def cmd_yt_video(message: types.Message):
    _yt_waiting_url[message.from_user.id] = "video"
    await message.answer("📹 Введите ссылку на YouTube видео:")


@fallback_router.message(F.text == "🎵 Скачать MP3")
@allowed_only
async def cmd_yt_audio(message: types.Message):
    _yt_waiting_url[message.from_user.id] = "audio"
    await message.answer("🎵 Введите ссылку на YouTube видео:")


@fallback_router.callback_query(F.data.startswith("yt_q:"))
@allowed_callback
async def cb_yt_quality(callback: types.CallbackQuery):
    quality = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    url = _yt_quality_url.pop(uid, "")
    if not url:
        return await callback.answer("❌ Сессия истекла. Начните заново.", show_alert=True)
    await callback.message.edit_text(f"⏬ Скачиваю {quality}p...")
    await callback.answer()
    try:
        path = await download_video(url, quality)
        await callback.message.answer_video(types.FSInputFile(path))
        os.remove(path)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)[:200]}")


@fallback_router.callback_query(F.data.startswith("yt_tr:"))
@allowed_callback
async def cb_yt_transcribe(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer()
    sid, answer = parts[1], parts[2]
    uid = callback.from_user.id
    audio_data = _yt_audio_cache.pop(sid, None)
    if not audio_data or not os.path.exists(audio_data["path"]):
        return await callback.answer("❌ Файл не найден.", show_alert=True)
    audio_path = audio_data["path"]
    audio_title = audio_data.get("title", "")
    if answer == "no":
        try:
            os.remove(audio_path)
        except:
            pass
        return await callback.answer("👍 Отменено")
    await callback.message.edit_text("📝 Транскрибирую аудио...")
    await callback.answer()
    try:
        txt_path = await transcribe_audio(audio_path, audio_title)
        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()
        await callback.message.answer(
            f"✅ Транскрипт сохранён в `{os.path.basename(txt_path)}`:\n\n{text[:3000]}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка транскрибации: {str(e)[:200]}")
    finally:
        try:
            os.remove(audio_path)
        except:
            pass


#ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ
@fallback_router.message()
@allowed_only
async def process_user_message(message: types.Message):
    if not message.text:
        logger.debug(f"⚠️ [TEXT_HANDLER] Пропущено не-текстовое сообщение. Type: {type(message)}")
        return
    
    text = message.text.strip()
    uid = message.from_user.id
    logger.info(f"[USER_MSG] User {uid}: {text[:50]}...")

    # 0a. Ожидание ссылки для YouTube
    if uid in _yt_waiting_url:
        mode = _yt_waiting_url.pop(uid)
        if mode == "video":
            _yt_quality_url[uid] = text
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(text="480p", callback_data="yt_q:480"),
                types.InlineKeyboardButton(text="720p", callback_data="yt_q:720"),
            )
            return await message.answer("🎥 Выберите качество:", reply_markup=kb.as_markup())
        else:
            st = await message.answer("⏬ Скачиваю аудио...")
            try:
                path, raw_title = await download_audio(text)
                await st.edit_text("✅ Аудио готово. Отправляю...")
                await message.answer_audio(types.FSInputFile(path))
                sid = secrets.token_hex(4)
                _yt_audio_cache[sid] = {"path": path, "title": raw_title}
                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(text="✅ Да", callback_data=f"yt_tr:{sid}:yes"),
                    types.InlineKeyboardButton(text="❌ Нет", callback_data=f"yt_tr:{sid}:no"),
                )
                await message.answer("📝 Транскрибировать и сохранить в /transkript?", reply_markup=kb.as_markup())
            except Exception as e:
                await st.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        return

    # 0. Ожидание текста для поиска по крылу
    if uid in _pending_wing_search:
        wing = _pending_wing_search.pop(uid)
        wing_info = f" (крыло: {wing})" if wing else ""
        st = await message.answer(f"🔍 Ищу в MemPalace{wing_info}...")
        try:
            res = await search_palace_context(text, limit=5, wing=wing)
            await st.edit_text(res if res else "Ничего не найдено.")
        except Exception as e:
            await st.edit_text(f"❌ Ошибка поиска: {str(e)[:100]}")
        return

    # 1. 💻 Mac команды
    if text.lower() in ["уснуть", "заблокировать"]:
        if uid != ADMIN_ID: 
            return await message.answer("❌ Доступ запрещен.")
        try:
            import subprocess
            if "уснуть" in text.lower():
                subprocess.run(["osascript", "-e", 'tell application "System Events" to sleep'], check=False)
            else:
                subprocess.run(["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"], check=False)
            await message.answer("✅ Выполнено.")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
        return

    # 2. 📝 Быстрая заметка (!)
    if text.startswith("!") and not text.startswith("!!"):
        note = text[1:].strip()
        if note:
            fn = f"nt_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            note_path = os.path.join(NOTES_DIR, fn)
            try:
                with open(os.path.join(NOTES_DIR, fn), "w", encoding="utf-8") as f: 
                    f.write(note)

                    # ✅ Фоновое связывание (безопасный вызов)
                    try:
                        from services.note_linker import schedule_linking
                        schedule_linking(note_path, note, prefix="!")
                    except Exception as link_err:
                        logger.warning(f"[LINKER] Ошибка запуска связывания: {link_err}")
                
                    # ✅ КНОПКА (должна быть ВНУТРИ try, после сохранения)
                    kb = InlineKeyboardBuilder()
                    kb.row(types.InlineKeyboardButton(
                        text="🔗 Показать связанные", 
                        callback_data=f"show_links:{fn}"
                    ))

                    return await message.answer(
                    "💾 Сохранено в my_notes.", 
                    reply_markup=kb.as_markup()
                    )
            except Exception as e:
                    return await message.answer(f"❌ Ошибка: {e}")

    # 3. 🔍 Поиск
    if text.lower().startswith("/search "):
        query_raw = text[8:].strip()
        if not query_raw: 
            return await message.answer("❌ Укажите запрос: /search <текст> или /search --wing dreams <текст>")
        wing = ""
        search_text = query_raw
        wing_match = re.match(r'^--wing\s+(\w+)\s+(.*)', query_raw)
        if wing_match:
            wing = wing_match.group(1).lower()
            search_text = wing_match.group(2)
            if wing not in ["dreams", "projects", "philosophy", "creative", "psychology"]:
                wing = ""
        wing_info = f" (крыло: {wing})" if wing else ""
        st = await message.answer(f"🔍 Ищу в MemPalace{wing_info}...")
        try:
            res = await search_palace_context(search_text, limit=5, wing=wing)
            await st.edit_text(res if res else "Ничего не найдено.")
        except Exception as e:
            await st.edit_text(f"❌ Ошибка поиска: {str(e)[:100]}")
        return

    # 4. 🆕 Ввод имени чата
    if waiting_for_name.get(uid):
        name = "".join(c for c in text if c.isalnum() or c in (' ','_')).replace(' ','_')
        if not name: 
            name = f"auto_{datetime.now().strftime('%Y%m%d_%H%M')}"
        fname = f"ch_{name}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        user_sessions[uid] = fname
        waiting_for_name[uid] = False
        try:
            save_chat(os.path.join(CHATS_DIR, fname), {"summary": "", "messages": []})
            return await message.answer(f"✅ Чат создан: <code>{fname}</code>", parse_mode="HTML")
        except: 
            pass
        return await message.answer("❌ Ошибка создания чата.")

    # 5. Проверка/Авто-создание чата
    if uid not in user_sessions:
        files = sorted([f for f in os.listdir(CHATS_DIR) if f.endswith('.json')], key=lambda x: os.path.getmtime(os.path.join(CHATS_DIR, x)), reverse=True)
        if files: 
            user_sessions[uid] = files[0]
            await message.answer(f"🔄 Активирован: <code>{files[0]}</code>", parse_mode="HTML")
        else: 
            fname = f"ch_auto_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            user_sessions[uid] = fname
            save_chat(os.path.join(CHATS_DIR, fname), {"summary": "", "messages": []})
            await message.answer(f"🆕 Создан чат: <code>{fname}</code>", parse_mode="HTML")

    fname = user_sessions[uid]
    fpath = os.path.join(CHATS_DIR, fname)
    try: 
        data = load_chat(fpath)
    except: 
        return await message.answer("❌ Ошибка загрузки чата.")

    msgs = data.get("messages", [])
    prefix = next((p for p in ["!!!", "!!", "!", "???", "??", "?"] if text.startswith(p)), "")
    clean_q = text[len(prefix):].strip() if prefix else text

    # 6. Обработка префиксов !! / ??? (Сохранение инсайтов/исследований)
    if prefix and len(msgs) >= 2:
        st = await message.answer("🎨 Анализирую заметку...")
        engine, model = get_current_ai()
        last_bot_msg = next((m for m in reversed(msgs) if m["role"] in ["model", "assistant"]), None)
        content = last_bot_msg['content'] if last_bot_msg else "Нет ответа"
        
        try:
            summary = await asyncio.to_thread(lambda: get_ai_response_sync_wrapper(engine, model, [{"role": "user", "content": f"Суммаризируй: {content}"}]))
            target = RESEARCH_DIR if "?" in prefix else INSIGHTS_DIR
            fn = f"ext_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            with open(os.path.join(target, fn), "w", encoding="utf-8") as f:
                f.write(f"{prefix.upper()}\nИсточник: {fname}\nВОПРОС: {msgs[-2]['content'] if len(msgs)>=2 else ''}\nИТОГ: {summary}\n")
                from services.note_linker import schedule_linking
                schedule_linking(os.path.join(target, fn), summary, prefix=prefix)
            
            await st.edit_text(f"✅ Сохранено в {os.path.basename(target)}:\n{safe_html_format(summary)}", parse_mode="HTML")
            
            # Если после префикса был текст вопроса, продолжаем диалог. Если нет — выходим.
            if not clean_q: 
                return
        except Exception as e:
            await st.edit_text(f"❌ Ошибка: {str(e)[:100]}")
            return

    # === 🧠 ЯДРО ИИ ===
    status = await message.answer(f"⏳ <code>{get_current_ai()[1]}</code> думает...", parse_mode="HTML")
    
    try:
        # Определяем крыло (Wing) для поиска
        target_wing = ""
        # 1. Проверяем, не указано ли крыло явно в запросе (например, "/search dreams: ...")
        explicit_wing_match = re.match(r'^/(\w+):\s*(.+)', clean_q)
        if explicit_wing_match:
            possible_wing = explicit_wing_match.group(1).lower()
            if possible_wing in ["dreams", "projects", "philosophy", "creative"]:
                target_wing = possible_wing
                clean_q = explicit_wing_match.group(2)  # Убираем префикс из запроса
                logger.info(f"[WING] Явно указано крыло: {target_wing}")
        
        # используем автоклассификатор
        if not target_wing:
            from services.wing_classifier import classify_wing
            auto_wing = classify_wing(clean_q)
            if auto_wing:
                target_wing = auto_wing
        
        # Логирование итогового выбора
        if target_wing:
            logger.info(f"[PALACE_SEARCH] 🔍 Поиск в крыле: {target_wing}")
        else:
            logger.info(f"[PALACE_SEARCH] 🔍 Глобальный поиск (крыло не определено)")
        
        # ✅ УВЕДОМЛЕНИЕ ПОЛЬЗОВАТЕЛЯ О ВЫБРАННОМ КРЫЛЕ
        wing_info = ""
        if target_wing:
            wing_names = {
                "dreams": "🌙 Сны",
                "projects": "💻 Проекты", 
                "philosophy": "🏛 Философия",
                "creative": "🎨 Творчество",
                "psychology": "🧠 Психология"
            }
            wing_display = wing_names.get(target_wing, target_wing)
            wing_info = f" | 🔍 Крыло: {wing_display}"
            try:
                await status.edit_text(f"⏳ <code>{get_current_ai()[1]}</code> думает{wing_info}...", parse_mode="HTML")
            except Exception:
                pass

        # 2. Ищем контекст в MemPalace
        palace_context = await search_palace_context(clean_q, limit=5, wing=target_wing)
        
        # 3. Получаем саммари текущего чата
        summaries_list = data.get("summaries", [])
        active_summary = summaries_list[-1] if summaries_list else data.get("summary", "").strip()

        # 4. Проверяем режим кодинга
        is_code = is_coding_context(clean_q, msgs)
        if is_code and not data.get("is_coding_mode"):
            data["is_coding_mode"] = True
            data["project_dir"] = ensure_project_dir(fname)
            save_chat(fpath, data)

        _engine, _model = get_current_ai()
        
        
        # 5. Подготовка изображений (ТОЛЬКО ПРИ ЯВНОМ ЗАПРОСЕ)
        images_b64 = []
        has_images_in_query = False
    
        # Ключевые слова, указывающие на желание анализировать фото
        photo_keywords = [
            "фото", "фотку", "картинк", "изображен", "снимок", "визуал",
            "проанализируй фото", "что на фото", "опиши фото", "разбор фото",
            "photo", "image", "picture", "analyze photo"
        ]
    
        # Проверяем, хочет ли пользователь работать с фото
        wants_photo_analysis = any(kw in clean_q.lower() for kw in photo_keywords)
    
        if wants_photo_analysis and check_capability(_model, "multimodal"):
            recent_photos = list_photos()[:2]
            for p in recent_photos:
                b64 = encode_image_to_base64(os.path.join(PHOTOS_DIR, p))
                if b64: 
                    images_b64.append(b64)
            has_images_in_query = len(images_b64) > 0
            if has_images_in_query:
                logger.info(f"[MULTIMODAL] 📷 Прикреплено {len(images_b64)} фото по запросу пользователя")
        else:
            logger.debug("[MULTIMODAL] ℹ️ Фото не прикреплены (нет явного запроса)")

        # 6. Генерация УМНОГО ПРОМПТА (Единая точка сборки)
        from services.prompts import get_smart_prompt
        
        system_instruction = get_smart_prompt(
            context=palace_context, 
            query=clean_q, 
            has_images=has_images_in_query
        )
        
        # Добавляем саммари диалога, если есть
        if active_summary:
            system_instruction += f"\n📜 Контекст текущего диалога:\n{active_summary}"

        # 📌 Долговременная память (релевантные факты из прошлых диалогов)
        try:
            memory_ctx = get_memory_context(clean_q, uid)
            if memory_ctx:
                system_instruction += "\n" + memory_ctx
        except Exception:
            pass

        # Добавляем специфику кодинга, если активен режим
        if data.get("is_coding_mode"):
            system_instruction += f"\n👨‍💻 СПЕЦИАЛИЗАЦИЯ: РАЗРАБОТКА\n{load_coding_prompt()}"
            proj_files = read_project_files(data.get("project_dir"))
            if proj_files: 
                system_instruction += f"\n📂 Файлы проекта:\n{proj_files}"

        # 7. Формирование сообщений для ИИ
        context_msgs = [{"role": "system", "content": system_instruction}]
        # Берем последние 10 сообщений истории
        context_msgs.extend(msgs[-10:] if len(msgs) > 10 else msgs)
        context_msgs.append({"role": "user", "content": clean_q})

        # 8. Вызов ИИ
        # Передаем clean_q как user_query и флаг has_images_in_query
        answer = await asyncio.to_thread(
            lambda: get_ai_response_sync_wrapper(
                _engine, 
                _model, 
                context_msgs, 
                context=palace_context,       # Контекст из MemPalace
                user_query=clean_q,           # Исходный текст пользователя
                has_images=has_images_in_query, # Есть ли фото
                images=images_b64             # Сами фото в base64
            )
        )

        # 9. Сохранение истории
        msgs.append({"role": "user", "content": clean_q})
        msgs.append({"role": "assistant", "content": answer})
        data["messages"] = msgs[-50:]
        try: 
            save_chat(fpath, data)
        except: 
            pass

        # Авто-синхронизация с MemPalace (каждые 5 сообщений)
        _sync_counter[uid] = _sync_counter.get(uid, 0) + 1
        if _sync_counter[uid] % 5 == 0 and not _sync_in_progress.get(uid):
            _sync_in_progress[uid] = True
            asyncio.create_task(_auto_sync_wrapper(uid, fname, fpath))

        # 📌 Фоновое извлечение фактов в долговременную память
        if clean_q and answer:
            asyncio.create_task(extract_and_store_facts(uid, clean_q, answer))

        # 10. Отправка ответа пользователю
        vs = get_voice_settings(uid)
        sent_msg = None
        
        try:
            if not answer or not answer.strip() or answer.startswith("❌"):
                sent_msg = await message.answer(safe_html_format(f"❌ ИИ вернул ошибку: {answer[:200]}"), parse_mode="HTML")
            else:
                sent_msg = await send_response_with_mode(message, answer, vs["mode"])
        except Exception as e:
            logger.error(f"Ошибка отправки ответа: {e}", exc_info=True)
            sent_msg = await message.answer("❌ Не удалось доставить ответ ИИ.")
        
        # Кэширование для реакций
        if sent_msg and hasattr(sent_msg, "message_id"):
            cache_ai_response(message.chat.id, sent_msg.message_id, answer)

    except Exception as e:
        logger.error(f"❌ Ошибка процесса ИИ: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {str(e)[:100]}", parse_mode="HTML")
    finally:
        try: 
            await bot.delete_message(message.chat.id, status.message_id)
        except: 
            pass

#ВСПОМОГАТЕЛЬНАЯ ОБЁРТКА
def get_ai_response_sync_wrapper(engine: str, model: str, messages: list, context: str = "", user_query: str = "", has_images: bool = False, **kwargs) -> str:
    from services.ai_engine import _sync_ai_call
    return _sync_ai_call(engine, model, messages, context, user_query, has_images, **kwargs)


# Вставьте это в main.py перед строкой async def main():
from config import ALLOWED_IDS, DEFAULT_DATA_DIR
print(f"🔍 Отладка: Путь к .env должен быть: {os.path.join(DEFAULT_DATA_DIR, '.env')}")
print(f"🔍 Отладка: Текущие ALLOWED_IDS: {ALLOWED_IDS}")


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot polling started.")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "message_reaction"])
    #await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("👋 Bot stopped.")
    except Exception as e: logger.critical(f"Bot crashed: {e}", exc_info=True)