"""handlers/messages.py — Main message handler extracted from main.py"""
import asyncio
import os
import re
import secrets
import time
from datetime import datetime

from aiogram import types

from config import (
    ADMIN_ID, CHATS_DIR, DATA_DIR,
    INSIGHTS_DIR, NOTES_DIR, PHOTOS_DIR, RESEARCH_DIR,
)
from handlers.chat import load_chat, save_chat, user_sessions, waiting_for_name
from handlers.palace import process_mcp_text_input, suggest_tunnel_hint
from handlers.palace.shared import _user_context
from services.palace_mcp import get_mcp as _get_mcp
import json
from handlers.personal_note import (
    _waiting_for_note, process_note_input, _quote_waiting, _save_quote_to_palace,
)
from handlers.reminder import handle_reminder_text
from handlers.search import search_result_cache as _search_result_cache
from services.ai_cache import cache_ai_response
from services.ai_engine import get_current_ai, stream_ai_response_async, _sync_ai_call
from services.auto_sync import auto_sync_chat
from services.bot_setup import (
    bot,
    pending_wing_search as _pending_wing_search,
    pending_web_search as _pending_web_search,
    sync_counter as _sync_counter,
    sync_in_progress as _sync_in_progress,
    yt_audio_cache as _yt_audio_cache,
    yt_quality_url as _yt_quality_url,
    yt_waiting_url as _yt_waiting_url,
)
from services.code_mode import (
    ensure_project_dir, is_coding_context, load_coding_prompt, read_project_files,
)
from services.event_bus import Event, get_bus
from services.graceful_degradation import get_degradation_manager, report_failure, report_success
from services.memory import extract_and_store_facts, get_memory_context
from services.multimodal import check_capability, encode_image_to_base64, list_photos
from services.note_linker import schedule_linking
from services.palace_bridge import search_with_kg
from services.prompts import get_smart_prompt
from services.semantic_cache import get_cache
from services.sender import send_response_with_mode
from services.text_formatter import safe_html_format
from services.tts_processor import get_voice_settings
from services.wing_classifier import classify_wing
from services.youtube import download_audio

from services.logging_setup import setup_logging

logger = setup_logging(DATA_DIR)

FILE_LIMIT = 50 * 1024 * 1024

_last_user_query: dict[int, str] = {}

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

    if clean_q:
        _last_user_query[chat_id] = clean_q

    _sync_counter[uid] = _sync_counter.get(uid, 0) + 1
    if _sync_counter[uid] % 5 == 0 and not _sync_in_progress.get(uid):
        _sync_in_progress[uid] = True
        asyncio.create_task(_auto_sync_wrapper(uid, fname, fpath))

    if clean_q:
        asyncio.create_task(suggest_tunnel_hint(message, clean_q))


bus.subscribe(Event.AI_RESPONSE_COMPLETE, _on_ai_complete)
bus.subscribe(Event.AI_RESPONSE_SENT, _on_ai_sent)


async def _auto_sync_wrapper(uid: int, fname: str, fpath: str):
    try:
        await auto_sync_chat(uid, fname, fpath)
    finally:
        _sync_in_progress[uid] = False


async def process_user_message(message: types.Message):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
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
            if size == 0:
                os.remove(path)
                return await st.edit_text(
                    "❌ Аудио пустое. Возможно, видео недоступно или "
                    "требуется обновление yt-dlp (pip install -U yt-dlp)."
                )
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
    if await handle_reminder_text(uid, text, message.answer):
        return None

    # 0b. Ожидание цитаты из личной заметки
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
            from services.palace_bridge import search_palace_with_sources
            result_text, sources = await search_palace_with_sources(text, limit=5, wing=wing)
            if not result_text:
                await st.edit_text("Ничего не найдено.")
                return None

            _search_result_cache[uid] = sources

            kb = InlineKeyboardBuilder()
            for s in sources:
                loc = f"{s['wing']}/{s['room']}"
                kb.row(types.InlineKeyboardButton(
                    text=f"📄 [{s['id']}] {loc}",
                    callback_data=f"p_src:{s['id']}",
                ))
            kb.row(types.InlineKeyboardButton(
                text="🔍 Новый поиск", callback_data="search:wing",
            ))

            await st.edit_text(
                result_text, parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
        except Exception as e:
            await st.edit_text(f"❌ Ошибка поиска: {str(e)[:100]}")
        return None

# 0e. Ожидание текста для поиска в интернете
    if uid in _pending_web_search:
        _pending_web_search.pop(uid, None)
        from services.web_search import deep_search_web
        from services.sender import send_text_only
        from services.text_formatter import split_message
        st = await message.answer("🌐 Глубокий поиск в интернете...")
        try:
            result = await deep_search_web(text)
            await st.delete()
            if isinstance(result, dict):
                search_id = result.get("search_id")
                ai_summary = result.get("ai_summary", "")
                sources = result.get("sources", [])

                # Отправляем ИИ-саммари или fallback
                if ai_summary:
                    for part in split_message(ai_summary):
                        await send_text_only(message, part)
                elif sources:
                    # Fallback: если ИИ не ответил, показываем источники
                    parts = [f"🔍 <b>Результаты по: {result.get('query', text)}</b>\n"]
                    for i, src in enumerate(sources, 1):
                        parts.append(f"\n[{i}] {src['text'][:200]}...")
                        parts.append(f"    🔗 {src['url']}\n")
                    for part in split_message("".join(parts)):
                        await send_text_only(message, part)
                else:
                    await message.answer("🤷 Ничего не найдено. Попробуйте другой запрос.")

                # Кнопки для источников и сохранения
                if sources:
                    kb = InlineKeyboardBuilder()
                    kb.row(
                        types.InlineKeyboardButton(
                            text="📄 Источники", callback_data=f"ws_sources:{search_id}"
                        ),
                        types.InlineKeyboardButton(
                            text="💾 В базу", callback_data=f"ws_save:{search_id}"
                        ),
                    )
                    await message.answer("🔗 Действия:", reply_markup=kb.as_markup())
            else:
                await message.answer("❌ Ошибка: неожиданный формат ответа поиска")
        except Exception as e:
            await st.edit_text(f"❌ Ошибка поиска: {str(e)[:200]}")
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
                        "/System/Library/CoreServices/Menu Extras"
                        "/User.menu/Contents/Resources/CGSession",
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
                with open(note_path, "w", encoding="utf-8") as f:
                    f.write(note)

                    try:
                        schedule_linking(note_path, note, prefix="!")
                    except Exception as link_err:
                        logger.warning(
                            f"[LINKER] Ошибка запуска связывания: {link_err}",
                        )

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
    clean_q = text[len(prefix):].strip() if prefix else text

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
                source = msgs[-2]["content"] if len(msgs) >= 2 else ""
                f.write(
                    f"{prefix.upper()}\nИсточник: {fname}\nВОПРОС: {source}\nИТОГ: {summary}\n",
                )
                schedule_linking(os.path.join(target, fn), summary, prefix=prefix)

            await st.edit_text(
                f"✅ Сохранено в {os.path.basename(target)}:\n{safe_html_format(summary)}",
                parse_mode="HTML",
            )

            if not clean_q:
                return None
        except Exception as e:
            await st.edit_text(f"❌ Ошибка: {str(e)[:100]}")
            return None

    # 6.5 🌐 Поиск в интернете
    if clean_q.lower().startswith("/web"):
        query = clean_q[4:].strip()
        if not query:
            return await message.answer("Использование: /web <запрос>")
        from services.web_search import search_web
        from services.sender import send_text_only
        st = await message.answer("🔍 Ищу в интернете...")
        try:
            results = await search_web(query)
            await st.delete()
            await send_text_only(message, results)
        except Exception as e:
            await st.edit_text(f"❌ Ошибка: {e}")
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
        deg = get_degradation_manager()

        ctx = _user_context.get(uid)
        if ctx and ctx.get("wing") and ctx.get("room"):
            wing_room = f"{ctx['wing']}/{ctx['room']}"
            logger.info(f"[USER_CONTEXT] User in {wing_room} drawer={ctx.get('drawer')}")
            try:
                mcp = _get_mcp()
                if ctx.get("drawer"):
                    drawer_raw = await mcp.call_tool("mempalace_get_drawer", {
                        "drawer": ctx["drawer"], "room": ctx["room"], "wing": ctx["wing"],
                    })
                    if drawer_raw:
                        palace_context = (
                            "\n--- ТЕКУЩАЯ ЗАПИСЬ "
                            "(Пользователь сейчас читает эту запись) ---\n"
                            f"Крыло: {ctx['wing']}, Комната: {ctx['room']}, "
                            f"Запись: {ctx['drawer']}\n\n"
                            f"{drawer_raw}\n--- КОНЕЦ ЗАПИСИ ---\n"
                        )
                else:
                    list_raw = await mcp.call_tool("mempalace_list_drawers", {
                        "wing": ctx["wing"], "room": ctx["room"], "limit": 20, "offset": 0,
                    })
                    parsed_drawers = json.loads(list_raw) if list_raw else {}
                    drawers = parsed_drawers.get("drawers", [])
                    if drawers:
                        texts = []
                        for d in drawers[:10]:
                            content = d.get("content_preview", "") or d.get("content", "")[:500]
                            dn = d.get("closet_name", d.get("title", d.get("name", "")))
                            if dn:
                                texts.append(f"--- {dn} ---\n{content}")
                        if texts:
                            header = (
                                "\n--- ЗАПИСИ ИЗ ТЕКУЩЕЙ КОМНАТЫ "
                                "(Пользователь сейчас в этой комнате) ---\n"
                            )
                            palace_context = (
                                header
                                + f"Крыло: {ctx['wing']}, Комната: {ctx['room']}\n\n"
                                + "\n\n".join(texts)
                                + "\n--- КОНЕЦ ЗАПИСЕЙ КОМНАТЫ ---\n"
                            )
            except Exception as e:
                logger.warning(f"[USER_CONTEXT] Error loading context: {e}")
        else:
            logger.info("[USER_CONTEXT] No user context, using regular search")

        if not palace_context and deg.should_use_palace():
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
            "фото", "фотку", "картинк", "изображен", "снимок",
            "визуал", "проанализируй фото", "что на фото",
            "опиши фото", "разбор фото", "photo", "image",
            "picture", "analyze photo",
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
                                f"[MULTIMODAL] 📷 Прикреплено {len(images_b64)} фото"
                                " по запросу пользователя",
                )

        system_instruction = get_smart_prompt(
            context=palace_context, query=clean_q, has_images=has_images_in_query,
        )

        if ctx and ctx.get("wing") and (ctx.get("room") or ctx.get("drawer")):
            system_instruction += (
                "\n📎 КРИТИЧЕСКИ ВАЖНО: Пользователь сейчас просматривает свои личные записи. "
                "Ты должен отвечать ИСКЛЮЧИТЕЛЬНО на основании предоставленных выше записей. "
                "Не используй свои общие знания — только текст из '--- ТЕКУЩАЯ ЗАПИСЬ ---' "
                "или '--- ЗАПИСИ ИЗ ТЕКУЩЕЙ КОМНАТЫ ---'. "
                "Можешь форматировать, суммаризировать, пересказывать, "
                "вычленять факты и детали из этих записей. "
                "Если нужны дополнительные факты (даты, имена, события) — "
                "используй команду SEARCH_WEB: <запрос> для поиска в интернете."
            )
        elif palace_context and "[1]" in palace_context:
            system_instruction += (
                "\n📎 ПРАВИЛА ЦИТИРОВАНИЯ: "
                "В контексте выше есть блок '--- ИСТОЧНИКИ ---' "
                "с номерами источников в квадратных скобках. "
                "При ответе ОБЯЗАТЕЛЬНО ссылайся на источники "
                "в формате [1], [2] и т.д. "
                "Не выдумывай факты — опирайся "
                "только на предоставленные источники."
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

            if answer and not answer.startswith("❌"):
                _sem_cache.set(clean_q, answer)

        # 🌐 SEARCH pattern: если ИИ запросил поиск
        search_match = re.search(
            r"(?:SEARCH|ПОИСК|SEARCH_WEB):\s*(.+)", answer, re.IGNORECASE,
        )
        if search_match and not answer.startswith("❌"):
            search_query = search_match.group(1).strip()
            logger.info(f"[WEB_SEARCH] AI requested search: {search_query}")
            try:
                from services.web_search import search_web
                web_results = await search_web(search_query)
                context_msgs.append({"role": "assistant", "content": answer})
                context_msgs.append({
                    "role": "user",
                    "content": (
                        f"Вот результаты поиска по запросу «{search_query}»:\n\n"
                        f"{web_results}\n\n"
                        "Ответь на мой исходный вопрос с учётом этой информации."
                    ),
                })
                if stream_msg is not None:
                    try:
                        await bot.delete_message(message.chat.id, stream_msg.message_id)
                    except Exception:
                        pass
                answer = ""
                async for chunk in stream_ai_response_async(
                    _engine, _model, context_msgs,
                    context=palace_context, user_query=clean_q,
                    has_images=has_images_in_query, images=images_b64,
                ):
                    answer += chunk
                if not answer.startswith("❌"):
                    msg_text = answer[:200] if len(answer) > 200 else answer
                    await status.edit_text(
                        f"🌐 <code>{get_current_ai()[1]}</code> (с поиском): "
                        f"{safe_html_format(msg_text)}",
                        parse_mode="HTML",
                    )
            except Exception as e:
                logger.error(f"[WEB_SEARCH] Failed: {e}", exc_info=True)

        if stream_msg is not None:
            try:
                await bot.delete_message(message.chat.id, stream_msg.message_id)
            except Exception:
                pass

        if not answer or answer.startswith("❌"):
            answer = answer or "❌ Пустой ответ от ИИ."

        msgs.append({"role": "user", "content": clean_q})
        msgs.append({"role": "assistant", "content": answer})
        data["messages"] = msgs[-50:]
        try:
            save_chat(fpath, data)
        except Exception as e:
            logger.warning(f"Не удалось сохранить чат: {e}")

        await bus.publish(
            Event.AI_RESPONSE_COMPLETE,
            answer=answer,
            clean_q=clean_q,
            uid=uid,
            fname=fname,
            fpath=fpath,
            data=data,
        )

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


def get_ai_response_sync_wrapper(
    engine: str,
    model: str,
    messages: list,
    context: str = "",
    user_query: str = "",
    has_images: bool = False,
    **kwargs,
) -> str:
    return _sync_ai_call(
        engine, model, messages, context, user_query, has_images, **kwargs,
    )
