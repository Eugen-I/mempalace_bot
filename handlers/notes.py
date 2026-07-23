"""
notes.py
Обработка префиксов !, !!, ???, чтение архива, команда /help
ИСПРАВЛЕНО: Автоматическое разбиение длинных заметок на части ≤4000 символов.
"""
import os
from datetime import datetime
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import NOTES_DIR, INSIGHTS_DIR, RESEARCH_DIR, allowed_only, allowed_callback
from services.text_formatter import safe_html_format, split_message

router = Router()
READ_MAP = {"#!": NOTES_DIR, "#!!": INSIGHTS_DIR, "#??": RESEARCH_DIR}

HELP_TEXT = """
🦾 <b>MemPalace: Справка</b>

📝 <b>ЗАПИСЬ:</b>
• <code>! текст</code> — Быстрая заметка в my_notes
• <code>!!</code> — Сохранить последний ответ ИИ в Insights
• <code>???</code> — Сохранить в Research

📚 <b>АРХИВ:</b>
• <code>#!</code>, <code>#!!</code>, <code>#??</code> — Чтение заметок
• <code>ГГГГ-ММ-ДД</code> — Поиск по дате

💬 <b>ЧАТЫ:</b>
• <code>~</code> или <code>#ctx</code> — Показать саммари текущего чата
• Кнопки меню для управления диалогами

🌐 <b>Фотографии:</b>
• <code>/photos</code> - список фото
• <code>/analyze_photo</code> - Анализ фото ИИ

🎙️ <b>ГОЛОС:</b>
• Отправьте голосовое сообщение — бот транскрибирует и ответит.
• Настройте режим и скорость в ⚙️ Настройки.

💻 <b>MAC:</b>
• <code>Уснуть</code>, <code>Заблокировать</code> — Управление системой
"""

@router.message(Command("help"))
@allowed_only
async def cmd_help(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="❓ Справка", callback_data="show_help"))
    await message.answer(HELP_TEXT, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "show_help")
@allowed_callback
async def cb_help(cb: types.CallbackQuery):
    await cb.message.answer(HELP_TEXT, parse_mode="HTML")
    await cb.answer()

@router.message(F.text.startswith("#"))
@allowed_only
async def cmd_read_archive(message: types.Message):
    prefix = message.text.strip()
    if prefix not in READ_MAP: return
    target = READ_MAP[prefix]
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="Последняя", callback_data=f"read|{prefix}|1"),
           types.InlineKeyboardButton(text="3 шт", callback_data=f"read|{prefix}|3"),
           types.InlineKeyboardButton(text="5 шт", callback_data=f"read|{prefix}|5"))
    await message.answer(f"📂 Архив: <code>{os.path.basename(target)}</code>", reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("read|"))
@allowed_callback
async def cb_read(cb: types.CallbackQuery):
    _, prefix, count = cb.data.split("|")
    target = READ_MAP.get(prefix)
    if not target: return await cb.answer("Папка не найдена")
    
    files = sorted([f for f in os.listdir(target) if not f.startswith('.')],
                   key=lambda x: os.path.getmtime(os.path.join(target, x)), reverse=True)[:int(count)]
    if not files: return await cb.answer("Пусто")
    
    for f in files:
        with open(os.path.join(target, f), "r", encoding="utf-8") as fh: 
            txt = fh.read()
        dt = datetime.fromtimestamp(os.path.getmtime(os.path.join(target, f))).strftime('%d.%m.%Y %H:%M')
        
        # 🔧 Разбиваем длинные заметки на части ≤4000 символов
        header = f"📅 <b>{dt}</b>\n"
        formatted_txt = safe_html_format(txt)
        parts = split_message(formatted_txt)
        
        for i, part in enumerate(parts):
            # Добавляем заголовок с датой только к первой части
            msg_text = f"{header}{part}" if i == 0 else part
            await cb.message.answer(msg_text, parse_mode="HTML")
            
    await cb.answer()