"""main.py | ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ
✅ Убраны дубликаты bot/dp/middleware
✅ Исправлена сигнатура middleware под aiogram 3.x
✅ ИСПРАВЛЕНИЕ ОШИБКИ: types.InlineKeyboardBuilder -> InlineKeyboardBuilder
"""

import asyncio
import os
import re
import secrets
import sys
import time
from datetime import datetime

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# 1. КОНФИГУРАЦИЯ
from config import (
    ADMIN_ID,
    API_TOKEN,
    CHATS_DIR,
    DATA_DIR,
    INSIGHTS_DIR,
    NOTES_DIR,
    PHOTOS_DIR,
    RESEARCH_DIR,
    allowed_only,
)
from handlers.chat import load_chat, save_chat, user_sessions, waiting_for_name
from handlers.palace import process_mcp_text_input, suggest_tunnel_hint
from handlers.personal_note import _waiting_for_note, process_note_input
from services.ai_cache import cache_ai_response

# 2. СЕРВИСЫ
from services.ai_engine import get_current_ai
from services.auto_sync import auto_sync_chat
from services.bot_setup import pending_wing_search as _pending_wing_search
from services.code_mode import (
    ensure_project_dir,
    is_coding_context,
    load_coding_prompt,
    read_project_files,
)
from services.event_bus import Event, get_bus
from services.memory import extract_and_store_facts, get_memory_context
from services.multimodal import (
    check_capability,
    encode_image_to_base64,
    list_photos,
)
from services.palace_bridge import (
    export_chat_verbatim,
    search_palace_context,
    search_with_kg,
    sync_to_palace,
)
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format
from services.tts_processor import get_voice_settings
from services.bot_setup import (
    bot,
    dp,
    init_bot,
    sync_counter as _sync_counter,
    sync_in_progress as _sync_in_progress,
    yt_audio_cache as _yt_audio_cache,
    yt_quality_url as _yt_quality_url,
    yt_waiting_url as _yt_waiting_url,
)
from services.sender import send_response_with_mode
from services.youtube import download_audio

FILE_LIMIT = 50 * 1024 * 1024  # 50 MB — Telegram limit for documents/video/audio


# 🔍 Sanity check: все ли пути импортированы?
assert "PHOTOS_DIR" in dir(), "❌ PHOTOS_DIR не импортирован из config!"

if API_TOKEN == "your_telegram_bot_token" or ADMIN_ID == 0:
    print("❌ Заполните TELEGRAM_BOT_TOKEN и ADMIN_ID в файле .env")
    print("📄 Скопируйте .env.example → .env и отредактируйте")
    sys.exit(1)

# 3. СТРУКТУРИРОВАННОЕ ЛОГИРОВАНИЕ
from services.logging_setup import setup_logging  # noqa: E402

logger = setup_logging(DATA_DIR)
init_bot(logger)

# 6. ПОДКЛЮЧЕНИЕ РОУТЕРОВ
from handlers import (  # noqa: E402
    chat, notes, palace, pdf, personal_note,
    reminder, settings, search,
)
from handlers import photos, reactions, voice, youtube_ui  # noqa: E402


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

fallback_router = Router()
dp.include_router(fallback_router)

# 7. ШИНА СОБЫТИЙ (Event Bus)
# Децентрализованная реакция на события без прямой связанности
bus = get_bus()


async def _on_ai_complete(**kwargs):
    answer = kwargs.get("answer", "")
    clean_q = kwargs.get("clean_q", "")
    uid = kwargs.get("uid", 0)
    if clean_q and answer:
        asyncio.create_task(extract_and_store_facts(uid, clean_q, answer))


async def _on_ai_sent(**kwargs):
    sent_msg = kwargs.get("sent_msg")
    answer = kwargs.get("answer", "")
    chat_id = kwargs.get("chat_id", 0)
    uid = kwargs.get("uid", 0)
    fname = kwargs.get("fname", "")
    fpath = kwargs.get("fpath", "")
    message = kwargs.get("message")
    clean_q = kwargs.get("clean_q", "")

    if answer.startswith("❌"):
        return

    if sent_msg and hasattr(sent_msg, "message_id"):
        cache_ai_response(chat_id, sent_msg.message_id, answer)

    if sent_msg and hasattr(sent_msg, "edit_reply_markup"):
        try:
            from aiogram.utils.keyboard import InlineKeyboardBuilder

            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(text="📥 В заметки", callback_data="p_sv"),
            )
            await sent_msg.edit_reply_markup(reply_markup=kb.as_markup())
        except Exception:
            pass

    _sync_counter[uid] = _sync_counter.get(uid, 0) + 1
    if _sync_counter[uid] % 5 == 0 and not _sync_in_progress.get(uid):
        _sync_in_progress[uid] = True
        asyncio.create_task(_auto_sync_wrapper(uid, fname, fpath))

    if clean_q:
        asyncio.create_task(suggest_tunnel_hint(message, clean_q))


bus.subscribe(Event.AI_RESPONSE_COMPLETE, _on_ai_complete)
bus.subscribe(Event.AI_RESPONSE_SENT, _on_ai_sent)


# 8. ХЕНДЛЕРЫ
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
            [types.KeyboardButton(text="🏰 Дворец")],
        ],
        resize_keyboard=True,
    )
    await message.answer("🦾 MemPalace запущен.", reply_markup=kb)
    logger.info(f"User {message.from_user.id} started.")


# КНОПКА: Дворец
@fallback_router.message(F.text == "🏰 Дворец")
@allowed_only
async def cmd_palace_button(message: types.Message):
    from handlers.palace import cmd_palace

    await cmd_palace(message)


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


# ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ
@fallback_router.message()
@allowed_only
async def process_user_message(message: types.Message):
    if not message.text:
        logger.debug(
            f"⚠️ [TEXT_HANDLER] Пропущено не-текстовое сообщение. Type: {type(message)}",
        )
        return None

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
            return await message.answer(
                "🎥 Выберите качество:", reply_markup=kb.as_markup(),
            )
        st = await message.answer("⏬ Скачиваю аудио...")
        try:
            path, raw_title = await download_audio(text)
            size = os.path.getsize(path)
            if size > FILE_LIMIT:
                os.remove(path)
                return await st.edit_text(
                    f"❌ Аудио слишком большое ({size // 1024 // 1024} MB). "
                    f"Лимит Telegram — 50 MB."
                )
            await st.edit_text("✅ Аудио готово. Отправляю...")
            await message.answer_audio(types.FSInputFile(path))
            sid = secrets.token_hex(4)
            _yt_audio_cache[sid] = {"path": path, "title": raw_title}
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(
                    text="✅ Да", callback_data=f"yt_tr:{sid}:yes",
                ),
                types.InlineKeyboardButton(
                    text="❌ Нет", callback_data=f"yt_tr:{sid}:no",
                ),
            )
            await message.answer(
                "📝 Транскрибировать и сохранить в /transkript?",
                reply_markup=kb.as_markup(),
            )
        except Exception as e:
            await st.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        return None

    # 0a. Ожидание текстового ввода для MCP-инструментов
    handled = await process_mcp_text_input(uid, text, lambda t: message.answer(t))
    if handled:
        return None

    # 0ab. Ожидание ответа на wizard напоминания
    from handlers.reminder import handle_reminder_text

    if await handle_reminder_text(uid, text, message.answer):
        return None

    # 0b. Ожидание цитаты из личной заметки
    from handlers.personal_note import _quote_waiting, _save_quote_to_palace

    if uid in _quote_waiting:
        return await _save_quote_to_palace(uid, text, lambda t: message.answer(t))

    # 0c. Ожидание личной заметки (текст)
    if uid in _waiting_for_note:
        return await process_note_input(uid, text, lambda t: message.answer(t))

    # 0d. Ожидание текста для поиска по крылу
    if uid in _pending_wing_search:
        wing = _pending_wing_search.pop(uid)
        wing_info = f" (крыло: {wing})" if wing else ""
        st = await message.answer(f"🔍 Ищу в MemPalace{wing_info}...")
        try:
            res = await search_palace_context(text, limit=5, wing=wing)
            await st.edit_text(res or "Ничего не найдено.")
        except Exception as e:
            await st.edit_text(f"❌ Ошибка поиска: {str(e)[:100]}")
        return None

    # 1. 💻 Mac команды
    if text.lower() in ["уснуть", "заблокировать"]:
        if uid != ADMIN_ID:
            return await message.answer("❌ Доступ запрещен.")
        try:
            import subprocess

            if "уснуть" in text.lower():
                subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to sleep'],
                    check=False,
                )
            else:
                subprocess.run(
                    [
                        "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession",  # noqa: E501
                        "-suspend",
                    ],
                    check=False,
                )
            await message.answer("✅ Выполнено.")
        except Exception:
            await message.answer("❌ Ошибка выполнения команды.")
        return None

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
                        logger.warning(
                            f"[LINKER] Ошибка запуска связывания: {link_err}",
                        )

                    # ✅ КНОПКА (должна быть ВНУТРИ try, после сохранения)
                    kb = InlineKeyboardBuilder()
                    kb.row(
                        types.InlineKeyboardButton(
                            text="🔗 Показать связанные",
                            callback_data=f"show_links:{fn}",
                        ),
                    )

                    return await message.answer(
                        "💾 Сохранено в my_notes.", reply_markup=kb.as_markup(),
                    )
            except Exception as e:
                return await message.answer(f"❌ Ошибка: {e}")

    # 4. 🆕 Ввод имени чата
    if waiting_for_name.get(uid):
        name = "".join(c for c in text if c.isalnum() or c in (" ", "_")).replace(
            " ", "_",
        )
        if not name:
            name = f"auto_{datetime.now().strftime('%Y%m%d_%H%M')}"
        fname = f"ch_{name}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        user_sessions[uid] = fname
        waiting_for_name[uid] = False
        try:
            save_chat(os.path.join(CHATS_DIR, fname), {"summary": "", "messages": []})
            return await message.answer(
                f"✅ Чат создан: <code>{fname}</code>", parse_mode="HTML",
            )
        except Exception:
            pass
        return await message.answer("❌ Ошибка создания чата.")

    # 5. Проверка/Авто-создание чата
    if uid not in user_sessions:
        files = sorted(
            [f for f in os.listdir(CHATS_DIR) if f.endswith(".json")],
            key=lambda x: os.path.getmtime(os.path.join(CHATS_DIR, x)),
            reverse=True,
        )
        if files:
            user_sessions[uid] = files[0]
            await message.answer(
                f"🔄 Активирован: <code>{files[0]}</code>", parse_mode="HTML",
            )
        else:
            fname = f"ch_auto_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            user_sessions[uid] = fname
            save_chat(os.path.join(CHATS_DIR, fname), {"summary": "", "messages": []})
            await message.answer(
                f"🆕 Создан чат: <code>{fname}</code>", parse_mode="HTML",
            )

    fname = user_sessions[uid]
    fpath = os.path.join(CHATS_DIR, fname)
    try:
        data = load_chat(fpath)
    except Exception:
        return await message.answer("❌ Ошибка загрузки чата.")

    msgs = data.get("messages", [])
    prefix = next(
        (p for p in ["!!!", "!!", "!", "???", "??", "?"] if text.startswith(p)), "",
    )
    clean_q = text[len(prefix) :].strip() if prefix else text

    # 6. Обработка префиксов !! / ??? (Сохранение инсайтов/исследований)
    if prefix and len(msgs) >= 2:
        st = await message.answer("🎨 Анализирую заметку...")
        engine, model = get_current_ai()
        last_bot_msg = next(
            (m for m in reversed(msgs) if m["role"] in ["model", "assistant"]), None,
        )
        content = last_bot_msg["content"] if last_bot_msg else "Нет ответа"

        try:
            summary = await asyncio.to_thread(
                lambda: get_ai_response_sync_wrapper(
                    engine,
                    model,
                    [{"role": "user", "content": f"Суммаризируй: {content}"}],
                ),
            )
            target = RESEARCH_DIR if "?" in prefix else INSIGHTS_DIR
            fn = f"ext_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            with open(os.path.join(target, fn), "w", encoding="utf-8") as f:
                f.write(
                    f"{prefix.upper()}\nИсточник: {fname}\nВОПРОС: {msgs[-2]['content'] if len(msgs) >= 2 else ''}\nИТОГ: {summary}\n",  # noqa: E501
                )
                from services.note_linker import schedule_linking

                schedule_linking(os.path.join(target, fn), summary, prefix=prefix)

            await st.edit_text(
                f"✅ Сохранено в {os.path.basename(target)}:\n{safe_html_format(summary)}",
                parse_mode="HTML",
            )

            # Если после префикса был текст вопроса, продолжаем диалог. Если нет — выходим.
            if not clean_q:
                return None
        except Exception as e:
            await st.edit_text(f"❌ Ошибка: {str(e)[:100]}")
            return None

    # === 🧠 ЯДРО ИИ (со стримингом) ===
    status = await message.answer(
        f"⏳ <code>{get_current_ai()[1]}</code> думает...", parse_mode="HTML",
    )

    try:
        target_wing = ""
        explicit_wing_match = re.match(r"^/(\w+):\s*(.+)", clean_q)
        if explicit_wing_match:
            possible_wing = explicit_wing_match.group(1).lower()
            if possible_wing in ["dreams", "projects", "philosophy", "creative"]:
                target_wing = possible_wing
                clean_q = explicit_wing_match.group(2)
                logger.info(f"[WING] Явно указано крыло: {target_wing}")

        if not target_wing:
            from services.wing_classifier import classify_wing

            auto_wing = classify_wing(clean_q)
            if auto_wing:
                target_wing = auto_wing

        if target_wing:
            logger.info(f"[PALACE_SEARCH] 🔍 Поиск в крыле: {target_wing}")
        else:
            logger.info("[PALACE_SEARCH] 🔍 Глобальный поиск (крыло не определено)")

        wing_info = ""
        if target_wing:
            wing_names = {
                "dreams": "🌙 Сны",
                "projects": "💻 Проекты",
                "philosophy": "🏛 Философия",
                "creative": "🎨 Творчество",
                "psychology": "🧠 Психология",
            }
            wing_display = wing_names.get(target_wing, target_wing)
            wing_info = f" | 🔍 Крыло: {wing_display}"
            try:
                await status.edit_text(
                    f"⏳ <code>{get_current_ai()[1]}</code> думает{wing_info}...",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        palace_context = ""
        from services.graceful_degradation import (
            get_degradation_manager,
            report_failure,
            report_success,
        )

        deg = get_degradation_manager()

        if deg.should_use_palace():
            palace_context = await search_with_kg(clean_q, limit=5, wing=target_wing)
            if not palace_context:
                report_failure("palace_search")
            else:
                report_success("palace_search")
        else:
            logger.info("[DEGRADE] Palace search skipped")

        summaries_list = data.get("summaries", [])
        active_summary = (
            summaries_list[-1] if summaries_list else data.get("summary", "").strip()
        )

        is_code = is_coding_context(clean_q, msgs)
        if is_code and not data.get("is_coding_mode"):
            data["is_coding_mode"] = True
            data["project_dir"] = ensure_project_dir(fname)
            save_chat(fpath, data)

        _engine, _model = get_current_ai()

        images_b64 = []
        has_images_in_query = False
        photo_keywords = [
            "фото",
            "фотку",
            "картинк",
            "изображен",
            "снимок",
            "визуал",
            "проанализируй фото",
            "что на фото",
            "опиши фото",
            "разбор фото",
            "photo",
            "image",
            "picture",
            "analyze photo",
        ]
        wants_photo_analysis = any(kw in clean_q.lower() for kw in photo_keywords)
        if wants_photo_analysis and check_capability(_model, "multimodal"):
            recent_photos = list_photos()[:2]
            for p in recent_photos:
                b64 = encode_image_to_base64(os.path.join(PHOTOS_DIR, p))
                if b64:
                    images_b64.append(b64)
            has_images_in_query = len(images_b64) > 0
            if has_images_in_query:
                logger.info(
                    f"[MULTIMODAL] 📷 Прикреплено {len(images_b64)} фото по запросу пользователя",
                )

        from services.prompts import get_smart_prompt

        system_instruction = get_smart_prompt(
            context=palace_context, query=clean_q, has_images=has_images_in_query,
        )

        # 📎 Инструкция по цитированию источников
        if palace_context and "[1]" in palace_context:
            system_instruction += (
                "\n📎 ПРАВИЛА ЦИТИРОВАНИЯ: "
                "В контексте выше есть блок '--- ИСТОЧНИКИ ---' с номерами источников в квадратных скобках. "  # noqa: E501
                "При ответе ОБЯЗАТЕЛЬНО ссылайся на источники в формате [1], [2] и т.д. "
                "Не выдумывай факты — опирайся только на предоставленные источники."
            )

        if active_summary:
            system_instruction += f"\n📜 Контекст текущего диалога:\n{active_summary}"

        if deg.should_use_memory():
            try:
                memory_ctx = get_memory_context(clean_q, uid)
                if memory_ctx:
                    system_instruction += "\n" + memory_ctx
            except Exception:
                pass
        else:
            logger.info("[DEGRADE] Memory context skipped")

        if data.get("is_coding_mode"):
            system_instruction += (
                f"\n👨‍💻 СПЕЦИАЛИЗАЦИЯ: РАЗРАБОТКА\n{load_coding_prompt()}"
            )
            proj_files = read_project_files(data.get("project_dir"))
            if proj_files:
                system_instruction += f"\n📂 Файлы проекта:\n{proj_files}"

        context_msgs = [{"role": "system", "content": system_instruction}]
        context_msgs.extend(msgs[-10:] if len(msgs) > 10 else msgs)
        context_msgs.append({"role": "user", "content": clean_q})

        await bus.publish(
            Event.AI_RESPONSE_START,
            uid=uid,
            query=clean_q,
            engine=_engine,
            model=_model,
        )

        # 💾 СЕМАНТИЧЕСКИЙ КЭШ: проверяем, не отвечали ли на похожий вопрос
        from services.semantic_cache import get_cache

        _sem_cache = get_cache()
        cached_answer = _sem_cache.get(clean_q)

        answer = ""
        stream_buffer = ""
        last_update = time.time()
        stream_msg = None

        if cached_answer is not None:
            answer = cached_answer
            status_text = f"💾 <code>{get_current_ai()[1]}</code> (из кэша)"
            try:
                await status.edit_text(status_text, parse_mode="HTML")
            except Exception:
                pass
        else:
            # ⚡ СТРИМИНГ: собираем чанки и показываем прогресс
            from services.ai_engine import stream_ai_response_async

            async for chunk in stream_ai_response_async(
                _engine,
                _model,
                context_msgs,
                context=palace_context,
                user_query=clean_q,
                has_images=has_images_in_query,
                images=images_b64,
            ):
                answer += chunk
                stream_buffer += chunk

                MIN_STREAM_INTERVAL = 1.0
                MIN_CHARS_FOR_UPDATE = 30

                if (
                    len(stream_buffer) >= MIN_CHARS_FOR_UPDATE
                    and time.time() - last_update >= MIN_STREAM_INTERVAL
                ):
                    preview = answer[:3000]
                    try:
                        if stream_msg is None:
                            stream_msg = await message.answer(preview)
                        else:
                            await stream_msg.edit_text(preview)
                        last_update = time.time()
                        stream_buffer = ""
                    except Exception:
                        pass

            # Сохраняем в кэш
            if answer and not answer.startswith("❌"):
                _sem_cache.set(clean_q, answer)

        # Если стриминг был — удаляем промежуточное сообщение
        if stream_msg is not None:
            try:
                await bot.delete_message(message.chat.id, stream_msg.message_id)
            except Exception:
                pass

        if not answer or answer.startswith("❌"):
            answer = answer or "❌ Пустой ответ от ИИ."

        # Сохранение истории
        msgs.append({"role": "user", "content": clean_q})
        msgs.append({"role": "assistant", "content": answer})
        data["messages"] = msgs[-50:]
        try:
            save_chat(fpath, data)
        except Exception as e:
            logger.warning(f"Не удалось сохранить чат: {e}")

        # Публикация события AI_RESPONSE_COMPLETE (факты и т.д.)
        await bus.publish(
            Event.AI_RESPONSE_COMPLETE,
            answer=answer,
            clean_q=clean_q,
            uid=uid,
            fname=fname,
            fpath=fpath,
            data=data,
        )

        # Отправка ответа пользователю
        vs = get_voice_settings(uid)
        sent_msg = None

        try:
            if answer.startswith("❌"):
                sent_msg = await message.answer(
                    safe_html_format(f"❌ ИИ вернул ошибку: {answer[:200]}"),
                    parse_mode="HTML",
                )
            else:
                sent_msg = await send_response_with_mode(message, answer, vs["mode"])
        except Exception as e:
            logger.error(f"Ошибка отправки ответа: {e}", exc_info=True)
            sent_msg = await message.answer("❌ Не удалось доставить ответ ИИ.")

        # Публикация события AI_RESPONSE_SENT (кэш, кнопки, автосинх, туннели)
        await bus.publish(
            Event.AI_RESPONSE_SENT,
            sent_msg=sent_msg,
            answer=answer,
            chat_id=message.chat.id,
            uid=uid,
            fname=fname,
            fpath=fpath,
            message=message,
            clean_q=clean_q,
        )

    except Exception as e:
        logger.error(f"❌ Ошибка процесса ИИ: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {str(e)[:100]}", parse_mode="HTML")
    finally:
        try:
            await bot.delete_message(message.chat.id, status.message_id)
        except Exception:
            pass


# ВСПОМОГАТЕЛЬНАЯ ОБЁРТКА
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


# Вставьте это в main.py перед строкой async def main():
from config import DEFAULT_DATA_DIR  # noqa: E402

print(f"🔍 Отладка: Путь к .env должен быть: {os.path.join(DEFAULT_DATA_DIR, '.env')}")
from config import ALLOWED_IDS  # noqa: E402
print(f"🔍 Отладка: Текущие ALLOWED_IDS: {ALLOWED_IDS}")


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        mcp = get_mcp()
        await mcp.start()
        logger.info("MCP client started.")
    except Exception as e:
        logger.warning(f"MCP client failed to start: {e}")

    # Предзагрузка Whisper
    try:
        from services.whisper_service import prewarm

        prewarm()
        logger.info("Whisper model pre-warmed.")
    except Exception as e:
        logger.warning(f"Whisper pre-warm failed: {e}")

    logger.info("Bot polling started.")

    # Запуск планировщика напоминаний
    from services.reminder_scheduler import start_scheduler

    start_scheduler(bot)

    await dp.start_polling(
        bot, allowed_updates=["message", "callback_query", "message_reaction"],
    )
    # await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Bot stopped.")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}", exc_info=True)
