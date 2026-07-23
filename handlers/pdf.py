"""
pdf.py
Обработка PDF: буфер, выбор анализа, сравнение 2 файлов с таймаутом.
ИСПРАВЛЕНО: 
1. Строгое разделение режимов: Текст / Голос / Вместе.
2. Разбиение длинных ответов на части с кнопками "Читать дальше" (новые сообщения).
3. Полная озвучка всего ответа, если включен голос.
4. Исправлена ошибка AttributeError при создании клавиатуры.
"""
import os
import re
import asyncio
import logging
import json
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import TEMP_DIR, PDF_ARCHIVE_DIR, allowed_only, allowed_callback, DATA_DIR
from services.pdf_engine import extract_pdf_async, load_prompts, estimate_tokens, build_comparison_prompt, analyze_large_document, save_pdf_original, list_archived_pdfs, remove_pdf_from_index
from services.ai_engine import get_ai_response_async, get_current_ai
from services.text_formatter import safe_html_format, split_message
from services.tts_processor import get_voice_settings, generate_voice_async, prepare_tts_text, split_tts_text

logger = logging.getLogger("PDF_Handler")
router = Router()
pdf_buffer = {}  # user_id: {"files": [(name, path)], "mode": "single"|"compare", "timer": Task}

# Директория для хранения частей длинных ответов
LONG_RESPONSES_DIR = os.path.join(DATA_DIR, "long_responses")
os.makedirs(LONG_RESPONSES_DIR, exist_ok=True)

def create_prompt_kb():
    prompts = load_prompts()
    kb = InlineKeyboardBuilder()
    for k, v in prompts.items():
        kb.row(types.InlineKeyboardButton(text=v["name"], callback_data=f"pdf_type:{k}"))
    return kb.as_markup()

@router.message(Command("compare"))
@allowed_only
async def cmd_compare(message: types.Message):
    uid = message.from_user.id
    pdf_buffer[uid] = {"files": [], "mode": "compare", "timer": None}
    await message.answer("⚖️ Режим сравнения активирован. Отправьте первый PDF.")

@router.message(F.document)
@allowed_only
async def handle_pdf(message: types.Message):
    doc = message.document
    if not doc.file_name.lower().endswith(".pdf"):
        return
    # Лимит 50MB
    if doc.file_size > 50 * 1024 * 1024:
        return await message.answer("❌ Лимит 50MB")

    status = await message.answer("📄 Загружаю PDF...")
    file_info = await message.bot.get_file(doc.file_id)

    # 🔥 Санитизация имени файла
    safe_name = re.sub(r'[^\w\.\-]', '_', doc.file_name)
    local_path = os.path.join(TEMP_DIR, f"tmp_{message.from_user.id}_{safe_name}")

    try:
        await message.bot.download_file(file_info.file_path, destination=local_path)
    except Exception as e:
        logger.error(f"Ошибка загрузки файла: {e}")
        return await status.edit_text("❌ Ошибка загрузки файла.")

    uid = message.from_user.id
    if uid not in pdf_buffer:
        pdf_buffer[uid] = {"files": [], "mode": "single", "timer": None}

    pdf_buffer[uid]["files"].append((safe_name, local_path))

    # Логика сравнения
    if pdf_buffer[uid]["mode"] == "compare":
        if len(pdf_buffer[uid]["files"]) == 1:
            await status.edit_text("⏳ PDF получен. Ожидание второго PDF...", parse_mode="HTML")
            return
        elif len(pdf_buffer[uid]["files"]) == 2:
            if pdf_buffer[uid]["timer"]:
                pdf_buffer[uid]["timer"].cancel()
            await status.edit_text("⚖️ Два файла получены. Запускаю сравнение...", parse_mode="HTML")
            await run_comparison(uid, status)
            return

    # 💾 Сохраняем оригинал для повторного анализа
    save_pdf_original(local_path, doc.file_name)

    # 🌐 Меню с кнопками
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🎯 Анализировать", callback_data="show_pdf_prompts"))
    kb.row(types.InlineKeyboardButton(text="⚖️ Сравнить с другим PDF", callback_data="activate_compare"))

    await status.edit_text("📄 PDF загружен и сохранён в архиве. Что сделать?", reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "show_pdf_prompts")
@allowed_callback
async def cb_show_prompts(cb: types.CallbackQuery):
    await cb.message.edit_text("🎯 Выберите тип анализа:", reply_markup=create_prompt_kb(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data == "activate_compare")
@allowed_callback
async def cb_activate_compare(cb: types.CallbackQuery):
    uid = cb.from_user.id
    if uid not in pdf_buffer:
        pdf_buffer[uid] = {"files": [], "mode": "single", "timer": None}
    pdf_buffer[uid]["mode"] = "compare"

    await cb.message.edit_text("⚖️ Режим сравнения. Жду второй PDF...", parse_mode="HTML")
    await cb.answer()

    TIMEOUT_SECONDS = 120
    timer_msg = await cb.message.answer(
        f"⚖️ Отправьте второй PDF\n⏳ Осталось: {TIMEOUT_SECONDS // 60}:00",
        parse_mode="HTML"
    )

    async def timeout_compare():
        try:
            for remaining in range(TIMEOUT_SECONDS - 5, 0, -5):
                await asyncio.sleep(5)
                buf = pdf_buffer.get(uid, {})
                if buf.get("mode") != "compare":
                    return
                if len(buf.get("files", [])) >= 2:
                    return
                mins, secs = divmod(remaining, 60)
                try:
                    await timer_msg.edit_text(
                        f"⚖️ Отправьте второй PDF\n⏳ Осталось: {mins}:{secs:02d}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"[TIMER] edit: {e}")

            if pdf_buffer.get(uid, {}).get("mode") == "compare" and len(pdf_buffer.get(uid, {}).get("files", [])) == 1:
                pdf_buffer[uid]["mode"] = "single"
                try:
                    await timer_msg.edit_text(
                        "⏱️ Время вышло. Второй PDF не получен.",
                        reply_markup=create_prompt_kb(), parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"[TIMER] timeout: {e}")
        except asyncio.CancelledError:
            pass

    if pdf_buffer[uid].get("timer"):
        pdf_buffer[uid]["timer"].cancel()
    pdf_buffer[uid]["timer"] = asyncio.create_task(timeout_compare())

@router.callback_query(F.data.startswith("pdf_type:"))
@allowed_callback
async def cb_pdf_type(cb: types.CallbackQuery):
    uid = cb.from_user.id
    ptype = cb.data.split(":")[1]
    buf = pdf_buffer.get(uid, {})
    if not buf.get("files"):
        return await cb.answer("Буфер пуст")

    await cb.message.edit_text("🔍 Извлекаю текст и анализирую...", parse_mode="HTML")
    await run_analysis(uid, ptype, cb.message)

async def send_long_response_parts(message: types.Message, text: str, base_filename: str, voice_mode: str):
    """
    Отправляет ответ в зависимости от режима:
    - 'text': Только текст (с кнопками, если длинный).
    - 'voice': Только голос (текст не отправляется в чат).
    - 'both': И текст (с кнопками), и голос.
    """
    parts = split_message(safe_html_format(text), limit=4000)
    
    if not parts:
        return

    # Сохраняем все части в файл для навигации
    response_file = os.path.join(LONG_RESPONSES_DIR, f"{base_filename}.json")
    with open(response_file, "w", encoding="utf-8") as f:
        json.dump(parts, f, ensure_ascii=False)

    is_voice_enabled = voice_mode in ["voice", "both"]
    is_text_enabled = voice_mode in ["text", "both"]

    # 1. Если нужен ТЕКСТ (режимы text или both)
    if is_text_enabled:
        for i, part in enumerate(parts):
            # Формируем клавиатуру для этой части
            kb = InlineKeyboardBuilder()
            if i < len(parts) - 1:
                # Кнопка "Далее" ведет к следующей части
                kb.row(types.InlineKeyboardButton(text=f"➡️ Читать дальше ({i+2}/{len(parts)})", callback_data=f"read_next:{base_filename}:{i+1}"))
            
            # Отправляем текст
            await message.answer(part, reply_markup=kb.as_markup(), parse_mode="HTML")

    # 2. Если нужен ГОЛОС (режимы voice или both)
    if is_voice_enabled:
        try:
            # Готовим весь текст для TTS
            tts_text = prepare_tts_text(text)
            if tts_text:
                # Разбиваем на чанки для say (лимит ~1800 символов)
                tts_chunks = split_tts_text(tts_text, max_chars=1800)
                
                if tts_chunks:
                    # Уведомление о начале генерации голоса (только если не было текста, чтобы не спамить)
                    if not is_text_enabled:
                        await message.answer("🎤 Генерирую полный голосовой ответ...", parse_mode="HTML")
                    
                    for chunk in tts_chunks:
                        ogg_files = await generate_voice_async(message.from_user.id, chunk)
                        for ogg in ogg_files:
                            try:
                                await message.answer_voice(types.FSInputFile(ogg))
                            except Exception as e:
                                logger.error(f"Ошибка отправки голоса: {e}")
                            finally:
                                try:
                                    os.remove(ogg)
                                except:
                                    pass
        except Exception as e:
            logger.error(f"Ошибка озвучки: {e}", exc_info=True)
            if not is_text_enabled:
                await message.answer("❌ Не удалось сгенерировать голос.", parse_mode="HTML")

@router.callback_query(F.data.startswith("read_next:"))
@allowed_callback
async def cb_read_next(cb: types.CallbackQuery):
    _, base_filename, current_idx_str = cb.data.split(":")
    current_idx = int(current_idx_str)
    
    response_file = os.path.join(LONG_RESPONSES_DIR, f"{base_filename}.json")
    if not os.path.exists(response_file):
        await cb.answer("❌ Файл ответа не найден", show_alert=True)
        return

    with open(response_file, "r", encoding="utf-8") as f:
        parts = json.load(f)

    if current_idx >= len(parts):
        await cb.answer("Это последняя часть.", show_alert=True)
        return

    next_part = parts[current_idx]
    
    # Формируем клавиатуру для следующей части
    kb = InlineKeyboardBuilder()
    if current_idx < len(parts) - 1:
        kb.row(types.InlineKeyboardButton(text=f"➡️ Далее ({current_idx+2}/{len(parts)})", callback_data=f"read_next:{base_filename}:{current_idx+1}"))
    else:
        kb.row(types.InlineKeyboardButton(text="✅ Конец", callback_data="ignore"))

    # Отправляем НОВОЕ сообщение с текстом
    await cb.message.answer(next_part, reply_markup=kb.as_markup(), parse_mode="HTML")
    
    # Озвучка этой части, если у пользователя включен голос
    vs = get_voice_settings(cb.from_user.id)
    if vs["mode"] in ["voice", "both"]:
        try:
            tts_text = prepare_tts_text(next_part)
            if tts_text:
                tts_chunks = split_tts_text(tts_text, max_chars=1800)
                for chunk in tts_chunks:
                    ogg_files = await generate_voice_async(cb.from_user.id, chunk)
                    for ogg in ogg_files:
                        try:
                            await cb.message.answer_voice(types.FSInputFile(ogg))
                        except:
                            pass
                        finally:
                            try:
                                os.remove(ogg)
                            except:
                                pass
        except Exception as e:
            logger.error(f"Ошибка озвучки при чтении далее: {e}")

    await cb.answer()

@router.message(Command("pdfs"))
@allowed_only
async def cmd_pdfs(message: types.Message):
    pdfs = list_archived_pdfs()
    if not pdfs:
        return await message.answer("📭 В архиве нет PDF. Отправь файл в чат, он сохранится автоматически.")

    kb = InlineKeyboardBuilder()
    for entry in pdfs[-20:]:
        display = entry.get("original_name", entry["id"])[:40]
        kb.row(types.InlineKeyboardButton(
            text=f"📄 {display}",
            callback_data=f"pdf_archive:{entry['id']}"
        ))
    await message.answer(f"📚 PDF в архиве ({len(pdfs)}):", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("pdf_archive:"))
@allowed_callback
async def cb_select_archived_pdf(cb: types.CallbackQuery):
    pdf_id = cb.data.split(":", 1)[1]
    uid = cb.from_user.id
    pdfs = list_archived_pdfs()
    entry = next((e for e in pdfs if e["id"] == pdf_id), None)
    if not entry or not os.path.exists(entry["path"]):
        await cb.answer("❌ Файл не найден", show_alert=True)
        return

    pdf_buffer[uid] = {"files": [(entry["original_name"], entry["path"])], "mode": "single", "timer": None}
    await cb.message.edit_text(
        f"📄 {entry['original_name']}\n\nВыбери тип анализа:",
        reply_markup=create_prompt_kb()
    )
    await cb.answer()

async def run_analysis(uid: int, ptype: str, msg: types.Message):
    """
    Выполняет анализ PDF.
    """
    buf = pdf_buffer.pop(uid, None)
    if not buf or not buf.get("files"):
        return await msg.edit_text("❌ Буфер PDF пуст.", parse_mode="HTML")
    
    files = buf["files"]
    combined_text = ""

    # 1. ЕДИНЫЙ ЦИКЛ ИЗВЛЕЧЕНИЯ ТЕКСТА
    for name, path in files:
        try:
            txt, method = await extract_pdf_async(path)
            if txt:
                combined_text += f"\n\n📄 [{name}]\n{txt}"
        except Exception as e:
            logger.error(f"Ошибка извлечения из {name}: {e}")
            
    # Удаляем временные файлы сразу после извлечения
    for name, path in files:
        try:
            os.remove(path)
        except:
            pass
        
    if not combined_text.strip():
        return await msg.edit_text("❌ Не удалось извлечь текст.", parse_mode="HTML")

    vs = get_voice_settings(uid)
    final_answer = ""

    engine, model = get_current_ai()
    prompt_tpl = load_prompts().get(ptype, {}).get("prompt", "Проанализируй документ.")
    final_answer = await analyze_large_document(engine, model, combined_text, prompt_tpl, msg)

    ts = __import__('datetime').datetime.now().strftime("%Y%m%d%H%M")
    arch = os.path.join(PDF_ARCHIVE_DIR, f"pdf_{ts}_{ptype}.txt")
    with open(arch, "w", encoding="utf-8") as f:
        f.write(f"🎯 {ptype}\n\n{final_answer}")

    # 📤 ОТПРАВКА ОТВЕТА С УЧЕТОМ РЕЖИМА
    if final_answer.strip() and not final_answer.startswith("❌"):
        base_filename = f"pdf_resp_{uid}_{ts}"
        # Передаем текущий режим голоса ('text', 'voice', 'both')
        await send_long_response_parts(msg, final_answer, base_filename, vs["mode"])
            
    elif final_answer.startswith("❌"):
        try:
            await msg.answer(final_answer, parse_mode="HTML")
        except:
            pass

async def run_comparison(uid: int, msg: types.Message):
    buf = pdf_buffer.pop(uid, None)
    if not buf:
        return await msg.edit_text("❌ Ошибка буфера сравнения.")
    
    files = buf["files"]
    texts = []
    for name, path in files:
        txt, _ = await extract_pdf_async(path)
        texts.append(txt or "Текст не извлечен")
        try:
            os.remove(path)
        except:
            pass
            
    prompt = build_comparison_prompt(texts[0], texts[1])
    engine, model = get_current_ai()

    await msg.edit_text(f"⚖️ <code>{model}</code> сравнивает документы...", parse_mode="HTML")
    answer = await get_ai_response_async(engine, model, [{"role": "user", "content": prompt}])

    # Для сравнения тоже используем длинный ответ с учетом режима
    ts = __import__('datetime').datetime.now().strftime("%Y%m%d%H%M")
    base_filename = f"pdf_comp_{uid}_{ts}"
    vs = get_voice_settings(uid)
    
    await send_long_response_parts(msg, answer, base_filename, vs["mode"])