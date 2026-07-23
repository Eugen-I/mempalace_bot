"""
settings.py
Меню настроек: выбор ИИ, режим голоса, скорость, справка.
ИСПРАВЛЕНО: Убран импорт set_current_ai, используется прямая запись в конфиг.
"""
import os
import json
from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import CONFIG_AI_FILE, MODELS_CONFIG_PATH, allowed_only, allowed_callback
from services.ai_engine import invalidate_ai_cache, get_current_ai
from services.tts_processor import get_voice_settings, set_voice_setting

router = Router()

def build_settings_kb(user_id: int):
    curr = "gemini-flash-latest"
    if os.path.exists(CONFIG_AI_FILE):
        with open(CONFIG_AI_FILE, "r") as f:
            curr = f.read().strip() or curr
    vs = get_voice_settings(user_id)
    mode_txt = {"text": "📝 Текст", "voice": "🎤 Голос", "both": "📝+🎤 Вместе"}.get(vs["mode"], "📝 Текст")

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✨ Gemini", callback_data="set_ai:gemini-flash-latest"))
    kb.row(types.InlineKeyboardButton(text="🏠 Ollama модели", callback_data="list_ollama"))
    kb.row(types.InlineKeyboardButton(text=f"🔊 Режим: {mode_txt}", callback_data="voice_toggle"))
    kb.row(types.InlineKeyboardButton(text="🐢 -10", callback_data="spd:-10"),
           types.InlineKeyboardButton(text=f"⚙️ {vs['speed']} wpm", callback_data="ignore"),
           types.InlineKeyboardButton(text="🐇 +10", callback_data="spd:+10"))
    kb.row(types.InlineKeyboardButton(text="❓ Справка", callback_data="show_help"))
    return kb.as_markup(), curr

@router.callback_query(F.data == "show_help")
@allowed_callback
async def cb_show_help(callback: types.CallbackQuery):
    help_text = (
        "<b>🦾 MemPalace Bot | Справка</b>\n\n"
        
        "<b>🔊 Управление озвучкой:</b>\n"
        "Звук — Вкл/Выкл озвучку\n"
        "Звук-150 — Скорость (100-300)\n\n"

        "🎭 <b>РЕАКЦИИ НА ОТВЕТЫ ИИ:</b>\n"
        "• 👍 — Быстрая заметка (аналог <code>!текст</code>) → папка <code>my_notes/</code>\n"
        "• ❤️ — Сохранить инсайт (аналог <code>!!</code>) → папка <code>insights/</code>\n"
        "• 🤷‍♂️ / 🤷 — Сохранить исследование (аналог <code>?</code>) → папка <code>research/</code>\n"
        "<i>ℹ️ Работает только на сообщениях бота с ответом ИИ (кэш хранит последние 50 ответов).</i>\n\n"
        
        "<b>📝 Заметки:</b>\n"
        "! текст — Быстрая заметка\n"
        "!! — Сохранить в Insights\n"
        "??? — Сохранить в Research\n\n"
        
        "<b>💬 Чаты:</b>\n"
        "/history — История чата\n"
        "/export — Экспорт в .md\n"
        "~ или #ctx — Контекст чата\n\n"
        
        "<b>🔍 Поиск:</b>\n"
        "/search запрос — Поиск по базе\n"
        "sync — Синхронизация\n\n"
        
        "<b>📸 Фотографии:</b>\n"
        "/photos — Список фото\n"
        "/analyze_photo — Анализ фото\n\n"
        
        "<b>⚙️ Системные:</b>\n"
        "/settings — Настройки\n"
        "уснуть, заблокировать — отправляет в сон, выходит из аккаунта\n"
    )
    
    # ✅ Создаем inline keyboard с кликабельными командами
    kb = InlineKeyboardBuilder()
    
    # Кнопки для фото-команд
    #kb.row(types.InlineKeyboardButton(text="📸 Список фото", callback_data="cmd:photos"))
    #kb.row(types.InlineKeyboardButton(text="🔍 Анализ фото", callback_data="cmd:analyze_photo"))
    
    # Кнопки для чатов
    #kb.row(types.InlineKeyboardButton(text="📜 История", callback_data="cmd:history"))
    #kb.row(types.InlineKeyboardButton(text="📤 Экспорт", callback_data="cmd:export"))
    
    # Кнопки для заметок
    #kb.row(types.InlineKeyboardButton(text="!! Insights", callback_data="cmd:insights"))
    #kb.row(types.InlineKeyboardButton(text="??? Research", callback_data="cmd:research"))
    
    # Кнопка назад
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="back_settings"))
    
    await callback.message.edit_text(help_text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("cmd:"))
@allowed_callback
async def cmd_callback_handler(callback: types.CallbackQuery):
    """Обработчик кликабельных команд из справки"""
    # ✅ 1. СРАЗУ отвечаем на callback, чтобы Telegram не ждал
    await callback.answer()
    
    command = callback.data.split(":", 1)[1]
    
    # Эмулируем выполнение команды через отправку сообщения пользователю
    if command == "photos":
        await callback.message.answer("📸 Открываю список фото...")
        from services.multimodal import list_photos
        photos = list_photos()
        if photos:
            msg = "📸 Фото в базе:\n" + "\n".join(f"{i}) {p}" for i, p in enumerate(photos, 1))
            await callback.message.answer(msg)
        else:
            await callback.message.answer("📁 Папка photos пуста.")
            
    elif command == "analyze_photo":
        status_msg = await callback.message.answer("🔍 Запускаю анализ последнего фото...")
        # Здесь можно вызвать логику анализа, как в handle_photo
        from services.multimodal import list_photos, encode_image_to_base64, check_capability
        from services.ai_engine import get_current_ai, _sync_ai_call
        from services.text_formatter import safe_html_format, split_message
        import asyncio, os
        from config import PHOTOS_DIR
        
        photos = list_photos()
        if not photos:
            return await status_msg.edit_text("❌ Нет фото для анализа.")
        
        engine, model = get_current_ai()
        if not check_capability(model, "multimodal"):
            return await status_msg.edit_text(f"⚠️ {model} не поддерживает фото.")
        
        b64 = encode_image_to_base64(os.path.join(PHOTOS_DIR, photos[0]))
        if b64:
            msgs = [{"role": "user", "content": "Опиши это фото на русском."}]
            try:
                answer = await asyncio.to_thread(
                    lambda: _sync_ai_call(engine, model, msgs, context="", images=[b64])
                )
                
                # ✅ Безопасная отправка: экранируем ответ и разбиваем на части
                safe_answer = safe_html_format(answer)
                full_text = f"📸 **Анализ:**\n\n{safe_answer}"
                parts = split_message(full_text)

                for part in parts:
                    if part and part.strip():
                        try:
                            # Пробуем отправить с форматированием
                            await callback.message.answer(part, parse_mode="HTML")
                        except Exception as e:
                            # Fallback: отправляем как простой текст, если парсер сломался
                            await callback.message.answer(part, parse_mode=None)
                            
            except Exception as e:
                await status_msg.edit_text(f"❌ Ошибка анализа: {str(e)[:200]}")
        else:
            await status_msg.edit_text("❌ Ошибка кодирования фото.")
            
    elif command == "history":
        await callback.message.answer("📜 Загружаю историю текущего чата...")
        # Здесь можно вызвать логику показа истории из chat.py
        
    elif command == "export":
        await callback.message.answer("📤 Экспортирую чат в Markdown...")
        # Здесь можно вызвать export_chat_to_md()
        
    elif command in ["insights", "research"]:
        target = "research" if command == "research" else "insights"
        await callback.message.answer(f"📌 Показываю последние записи из {target}/...")
        # Здесь можно показать последние файлы из папки


async def render_ollama_list(cb: types.CallbackQuery):
    """Отрисовывает список Ollama моделей с подсветкой активной."""
    current_tag = "gemini-flash-latest"
    if os.path.exists(CONFIG_AI_FILE):
        with open(CONFIG_AI_FILE, "r") as f:
            current_tag = f.read().strip() or current_tag
            
    try:
        with open(MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"ollama": []}

    kb = InlineKeyboardBuilder()
    for m in data.get("ollama", []):
        tag = m.get("tag", "")
        name = m.get("name", tag)
        is_active = tag == current_tag
        btn_text = f"✅ {name} ({tag})" if is_active else f"🦙 {name}"
        kb.row(types.InlineKeyboardButton(text=btn_text, callback_data=f"set_ai:{tag}"))

    kb.row(types.InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="back_settings"))

    header = f"🤖 <b>Активная модель:</b> <code>{current_tag}</code>\n\n📋 Выберите модель Ollama:"
    await cb.message.edit_text(header, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.message(F.text == "⚙️ Настройки")
@allowed_only
async def cmd_settings(message: types.Message):
    kb, curr = build_settings_kb(message.from_user.id)
    await message.answer(f"🤖 Текущая модель: <code>{curr}</code>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "voice_toggle")
@allowed_callback
async def cb_voice_toggle(cb: types.CallbackQuery):
    modes = ["text", "voice", "both"]
    cur = get_voice_settings(cb.from_user.id)["mode"]
    nxt = modes[(modes.index(cur)+1)%3]
    set_voice_setting(cb.from_user.id, "mode", nxt)
    kb, curr = build_settings_kb(cb.from_user.id)
    await cb.message.edit_text(f"🤖 Модель: <code>{curr}</code>", reply_markup=kb, parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("spd:"))
@allowed_callback
async def cb_speed(cb: types.CallbackQuery):
    delta = int(cb.data.split(":")[1])
    cur = get_voice_settings(cb.from_user.id)["speed"]
    set_voice_setting(cb.from_user.id, "speed", max(100, min(300, cur+delta)))
    kb, curr = build_settings_kb(cb.from_user.id)
    await cb.message.edit_text(f"🤖 Модель: <code>{curr}</code>", reply_markup=kb, parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data == "list_ollama")
@allowed_callback
async def cb_list_ollama(cb: types.CallbackQuery):
    await render_ollama_list(cb)
    await cb.answer()

@router.callback_query(F.data.startswith("set_ai:"))
@allowed_callback
async def cb_set_ai(cb: types.CallbackQuery):
    # 🔧 Прямая запись тега модели в файл конфигурации
    tag = cb.data.split(":", 1)[1]
    try:
        with open(CONFIG_AI_FILE, "w", encoding="utf-8") as f:
            f.write(tag)
        invalidate_ai_cache()
    except Exception as e:
        logger.error(f"Ошибка сохранения модели AI: {e}")

    # 🔄 Обновляем список прямо здесь, чтобы галочка переместилась мгновенно
    await render_ollama_list(cb)
    await cb.answer(f"✅ Выбрана: {tag}", show_alert=True)

@router.callback_query(F.data == "back_settings")
@allowed_callback
async def cb_back(cb: types.CallbackQuery):
    kb, curr = build_settings_kb(cb.from_user.id)
    await cb.message.edit_text(f"🤖 Модель: <code>{curr}</code>", reply_markup=kb, parse_mode="HTML")
    await cb.answer()