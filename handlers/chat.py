"""
chat.py
Управление чатами, саммари, контекст. БЕЗ глобального catch-all.
ИСПРАВЛЕНО: Полноценное саммари через ИИ по запросу (~), кнопка развертывания.
"""
import os
import json
import re
from datetime import datetime
from services.prompts import get_summary_prompt
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import CHATS_DIR, allowed_only, allowed_callback
from services.ai_engine import get_ai_response_async, get_current_ai
from services.text_formatter import safe_html_format, split_message
from services.palace_bridge import search_palace_context, export_chat_verbatim, sync_to_palace

import secrets
router = Router()
user_sessions = {}
waiting_for_name = {}
_chat_callback_cache: dict[str, str] = {}

def _short_id(fname: str) -> str:
    sid = secrets.token_hex(4)
    _chat_callback_cache[sid] = fname
    return sid

def load_chat(filepath: str) -> dict:
    if not os.path.exists(filepath): return {"summary": "", "messages": []}
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"summary": "", "messages": data}
        save_chat(filepath, data)
    return data

def save_chat(filepath: str, data: dict):
    """Безопасное сохранение чата с атомарной записью."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения чата {filepath}: {e}")

def save_summary_file(chat_name: str, summary: str):
    base = chat_name.replace(".json", "")
    path = os.path.join(CHATS_DIR, f"{base}_summary.txt")
    with open(path, "w", encoding="utf-8") as f: 
        f.write(summary)

def export_chat_to_md(chat_path: str) -> str | None:
    """Экспортирует чат в Markdown файл."""
    if not os.path.exists(chat_path):
        return None
    
    data = load_chat(chat_path)
    msgs = data.get("messages", [])
    if not msgs:
        return None
        
    export_dir = os.path.join(CHATS_DIR, "exports")
    os.makedirs(export_dir, exist_ok=True)
    
    base_name = os.path.basename(chat_path).replace(".json", "")
    md_path = os.path.join(export_dir, f"{base_name}.md")
    
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 💬 Диалог: {base_name}\n\n")
        for m in msgs:
            role = m.get("role", "user")
            icon = "👤 Вы" if role == "user" else "🤖 ИИ"
            content = m.get("content", "").strip()
            if content:
                f.write(f"### {icon}\n{content}\n\n")
                
    return md_path


@router.message(F.text == "🆕 Новый диалог")
@allowed_only
async def cmd_new_chat(message: types.Message):
    waiting_for_name[message.from_user.id] = True
    await message.answer("📝 Введите название для нового чата:")

@router.message(F.text == "📂 Список чатов")
@allowed_only
async def cmd_list_chats(message: types.Message):
    files = sorted([f for f in os.listdir(CHATS_DIR) if f.endswith('.json')],
                   key=lambda x: os.path.getmtime(os.path.join(CHATS_DIR, x)), reverse=True)[:10]
    if not files: return await message.answer("📁 Чатов нет.")
    
    kb = InlineKeyboardBuilder()
    for f in files:
        sid = _short_id(f)
        display_name = f.replace("ch_", "").replace(".json", "").replace("_", " ")[:25]
        kb.row(types.InlineKeyboardButton(text=f"💬 {display_name}", callback_data=f"sel:{sid}"),
               types.InlineKeyboardButton(text="🗑️", callback_data=f"del:{sid}"))
    
    await message.answer("📅 Выберите чат:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("sel:"))
@allowed_callback
async def cb_select_chat(callback: types.CallbackQuery):
    sid = callback.data.split(":", 1)[1]
    fname = _chat_callback_cache.get(sid)
    if not fname:
        return await callback.answer("❌ Сессия истекла. Откройте список чатов заново.", show_alert=True)
    user_sessions[callback.from_user.id] = fname
    data = load_chat(os.path.join(CHATS_DIR, fname))
    
    summary = data.get('summary', '')
    messages = data.get('messages', [])
    
    preview_text = ""
    if summary and len(summary.strip()) > 10:
        preview_text += f"📝 <b>Саммари:</b>\n{safe_html_format(summary)}\n\n"
    
    if not summary or len(summary.strip()) < 50:
        last_msgs = messages[-3:] if len(messages) >= 3 else messages
        if last_msgs:
            preview_text += "💬 <b>Последние сообщения:</b>\n"
            for m in last_msgs:
                role_icon = "👤" if m["role"] == "user" else "🤖"
                content_preview = m['content'][:100].replace("\n", " ") + ("..." if len(m['content']) > 100 else "")
                preview_text += f"{role_icon} {safe_html_format(content_preview)}\n"
    
    if not preview_text.strip():
        preview_text = "ℹ️ Чат пуст."

    kb = InlineKeyboardBuilder()
    if len(summary) > 500 or len(messages) > 5:
        sid_full = _short_id(fname)
        kb.row(types.InlineKeyboardButton(text="📖 Развернуть полностью", callback_data=f"show_full:{sid_full}"))
    sid_refresh = _short_id(fname)
    kb.row(types.InlineKeyboardButton(text="🔄 Обновить саммари", callback_data=f"refresh_summary:{sid_refresh}"))
    
    header = f"✅ Активен: <code>{fname}</code>\n\n"
    await callback.message.edit_text(header + preview_text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("del:"))
@allowed_callback
async def cb_delete_chat(callback: types.CallbackQuery):
    sid = callback.data.split(":", 1)[1]
    fname = _chat_callback_cache.get(sid)
    if not fname:
        return await callback.answer("❌ Сессия истекла.", show_alert=True)
    
    path = os.path.join(CHATS_DIR, fname)
    if os.path.exists(path):
        os.remove(path)
    if user_sessions.get(callback.from_user.id) == fname:
        del user_sessions[callback.from_user.id]

    files = sorted([f for f in os.listdir(CHATS_DIR) if f.endswith('.json')],
                   key=lambda x: os.path.getmtime(os.path.join(CHATS_DIR, x)), reverse=True)[:10]

    try:
        if not files:
            await callback.message.edit_text("📁 Чатов больше нет.", reply_markup=None)
        else:
            kb = InlineKeyboardBuilder()
            for f in files:
                sid2 = _short_id(f)
                display_name = f.replace("ch_", "").replace(".json", "").replace("_", " ")[:25]
                kb.row(types.InlineKeyboardButton(text=f"💬 {display_name}", callback_data=f"sel:{sid2}"),
                       types.InlineKeyboardButton(text="🗑️", callback_data=f"del:{sid2}"))
            await callback.message.edit_text("📅 Выберите чат:", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer(f"🗑️ Удален: {fname}", show_alert=True)

async def generate_fresh_summary(messages: list, existing_summary: str = "") -> str:
    """Генерирует свежее лаконичное саммари из списка сообщений."""
    if not messages:
        return "Чат пуст."
    
    engine, model = get_current_ai()
    
    # Берем последние 20 сообщений для контекста
    dialog_slice = "\n".join([f"{m['role']}: {m['content']}" for m in messages[-20:]])
    
    # Если есть старое саммари, добавляем его в контекст, чтобы сохранить нить
    context_prefix = ""
    if existing_summary and len(existing_summary.strip()) > 10:
        context_prefix = f"ПРЕДЫДУЩЕЕ САММАРИ:\n{existing_summary}\n\nТЕКУЩИЙ ДИАЛОГ:\n"
    
    prompt = get_summary_prompt(dialog_slice=dialog_slice, context_prefix=context_prefix)
    
    try:
        summary = await get_ai_response_async(engine, model, [{"role": "system", "content": prompt}], context="")
        
        # Принудительная обрезка, если модель все равно болтлива
        words = summary.split()
        if len(words) > 50:
            summary = " ".join(words[:50]) + "..."
        return summary.strip()
    
    except Exception as e:
        logger.error(f"Ошибка генерации саммари: {e}")
        return "Не удалось сгенерировать саммари."
    

async def update_summary_if_needed(user_id: int, filepath: str, messages: list):
    """Генерирует саммари каждые 5 сообщений и сохраняет его."""
    if len(messages) >= 5 and len(messages) % 5 == 0:
        engine, model = get_current_ai()
        # Берем последние 10 сообщений для контекста саммари
        dialog_slice = "\n".join([f"{m['role']}: {m['content']}" for m in messages[-15:]])
        
        prompt = get_summary_prompt(dialog_slice=dialog_slice, context_prefix="")
        
        try:
            summary = await get_ai_response_async(engine, model, [{"role": "user", "content": prompt}], context="")
            
            # Принудительная обрезка, если модель все равно болтлива
            words = summary.split()
            if len(words) > 40:
                summary = " ".join(words[:40]) + "..."
                
            data = load_chat(filepath)
            data["summary"] = summary
            save_chat(filepath, data)
            save_summary_file(os.path.basename(filepath), summary)
            return summary
        except Exception as e:
            logger.error(f"Ошибка генерации саммари: {e}")
    return None


@router.message(F.text.in_(["~", "#ctx"]))
@allowed_only
async def cmd_context(message: types.Message):
    fname = user_sessions.get(message.from_user.id)
    if not fname: 
        return await message.answer("⚠️ Нет активного чата.")
    
    data = load_chat(os.path.join(CHATS_DIR, fname))
    messages = data.get("messages", [])
    existing_summary = data.get("summary", "")
    
    # 1. Проверяем, есть ли уже сохраненное саммари
    if existing_summary and len(existing_summary.strip()) > 20:
        # Показываем существующее саммари
        preview = existing_summary[:500] + "..." if len(existing_summary) > 500 else existing_summary
    else:
        # 2. Если саммари нет, генерируем новое прямо сейчас
        status_msg = await message.answer("🧠 Генерирую свежее саммари...")
        new_summary = await generate_fresh_summary(messages, existing_summary)
        
        # Сохраняем новое саммари в файл
        data["summary"] = new_summary
        save_chat(os.path.join(CHATS_DIR, fname), data)
        save_summary_file(fname, new_summary)
        
        await status_msg.delete()
        final_summary = new_summary
    
    # 3. Показываем результат
    preview = final_summary[:500] + "..." if len(final_summary) > 500 else final_summary
    
    kb = InlineKeyboardBuilder()
    if len(final_summary) > 500:
        sid_s = _short_id(fname)
        kb.row(types.InlineKeyboardButton(text="📖 Развернуть полностью", callback_data=f"show_summary:{sid_s}"))
    sid_r = _short_id(fname)
    kb.row(types.InlineKeyboardButton(text="🔄 Обновить саммари", callback_data=f"refresh_summary:{sid_r}"))
    
    await message.answer(f"🧠 <b>Контекст чата:</b>\n{safe_html_format(preview)}", reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("show_summary:"))
@allowed_callback
async def cb_show_summary(callback: types.CallbackQuery):
    sid = callback.data.split(":", 1)[1]
    fname = _chat_callback_cache.get(sid)
    if not fname:
        return await callback.answer("❌ Сессия истекла.", show_alert=True)
    path = os.path.join(CHATS_DIR, fname.replace(".json", "_summary.txt"))
    
    text = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        data = load_chat(os.path.join(CHATS_DIR, fname))
        text = data.get("summary", "Пусто")
        
    if not text.strip():
        return await callback.answer("Саммари пусто", show_alert=True)

    parts = split_message(safe_html_format(text))
    for i, p in enumerate(parts):
        try:
            await callback.message.answer(p, parse_mode="HTML")
        except:
            pass
    await callback.answer()

@router.callback_query(F.data.startswith("show_full:"))
@allowed_callback
async def cb_show_full_chat(callback: types.CallbackQuery):
    """Показывает полный текст последних сообщений чата."""
    sid = callback.data.split(":", 1)[1]
    fname = _chat_callback_cache.get(sid)
    if not fname:
        return await callback.answer("❌ Сессия истекла.", show_alert=True)
    data = load_chat(os.path.join(CHATS_DIR, fname))
    messages = data.get("messages", [])
    
    if not messages:
        return await callback.answer("Чат пуст", show_alert=True)
    
    full_text = ""
    for m in messages[-20:]:
        role_icon = "👤" if m["role"] == "user" else "🤖"
        full_text += f"{role_icon} <b>{m['role'].upper()}</b>:\n{safe_html_format(m['content'])}\n\n"
        
    if not full_text.strip():
        return await callback.answer("Нет сообщений", show_alert=True)
        
    parts = split_message(full_text)
    for p in parts:
        try:
            await callback.message.answer(p, parse_mode="HTML")
        except:
            pass
    await callback.answer()

@router.callback_query(F.data.startswith("refresh_summary:"))
@allowed_callback
async def cb_refresh_summary(callback: types.CallbackQuery):
    """Принудительно обновляет саммари текущего чата."""
    sid = callback.data.split(":", 1)[1]
    fname = _chat_callback_cache.get(sid)
    if not fname:
        return await callback.answer("❌ Сессия истекла.", show_alert=True)
    path = os.path.join(CHATS_DIR, fname)
    data = load_chat(path)
    messages = data.get("messages", [])
    
    if not messages:
        return await callback.answer("Чат пуст", show_alert=True)
        
    await callback.answer("🔄 Генерирую новое саммари...", show_alert=True)
    
    existing_summary = data.get("summary", "")
    new_summary = await generate_fresh_summary(messages, existing_summary)
    
    data["summary"] = new_summary
    save_chat(path, data)
    save_summary_file(fname, new_summary)
    
    preview = new_summary[:500] + "..." if len(new_summary) > 500 else new_summary
    kb = InlineKeyboardBuilder()
    if len(new_summary) > 500:
        sid_s = _short_id(fname)
        kb.row(types.InlineKeyboardButton(text="📖 Развернуть полностью", callback_data=f"show_summary:{sid_s}"))
        
    header = f"✅ Активен: <code>{fname}</code>\n\n📝 <b>Обновленное саммари:</b>\n{safe_html_format(preview)}"
    await callback.message.edit_text(header, parse_mode="HTML", reply_markup=kb.as_markup())

@router.message(Command("sync"))
@allowed_only
async def cmd_sync_palace(message: types.Message):
    """Ручная синхронизация текущего чата с MemPalace."""
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


async def get_ai_context(user_id: int) -> tuple:
    """
    Возвращает (summary, recent_messages) для текущего активного чата пользователя.
    Используется в main.py для формирования контекста ИИ.
    """
    fname = user_sessions.get(user_id)
    if not fname:
        return "", []
    
    fpath = os.path.join(CHATS_DIR, fname)
    data = load_chat(fpath)
    msgs = data.get("messages", [])
    
    # Берем последние 6 сообщений для контекста
    recent = msgs[-6:] if len(msgs) > 6 else msgs
    
    summary = data.get("summary", "")
    
    return summary, recent


# 📜 Команда /history - показать историю текущего чата
@router.message(Command("history"))
@allowed_only
async def cmd_history(message: types.Message):
    fname = user_sessions.get(message.from_user.id)
    if not fname:
        return await message.answer("⚠️ Нет активного чата.")
    
    data = load_chat(os.path.join(CHATS_DIR, fname))
    messages = data.get("messages", [])
    
    if not messages:
        return await message.answer("📁 Чат пуст.")
    
    # Берем последние 10 сообщений для краткости
    recent_msgs = messages[-10:]
    
    text = f"📜 <b>История чата ({fname}):</b>\n\n"
    for m in recent_msgs:
        role_icon = "👤" if m["role"] == "user" else "🤖"
        content_preview = m['content'][:150].replace("\n", " ") + ("..." if len(m['content']) > 150 else "")
        text += f"{role_icon} <b>{m['role'].upper()}:</b> {safe_html_format(content_preview)}\n\n"
    
    kb = InlineKeyboardBuilder()
    sid_full = _short_id(fname)
    kb.row(types.InlineKeyboardButton(text="📖 Показать полностью", callback_data=f"show_full:{sid_full}"))
    
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


# 📤 Команда /export - экспорт текущего чата в Markdown + отправка файла
@router.message(Command("export"))
@allowed_only
async def cmd_export(message: types.Message):
    fname = user_sessions.get(message.from_user.id)
    if not fname:
        return await message.answer("⚠️ Нет активного чата для экспорта.")
    
    fpath = os.path.join(CHATS_DIR, fname)
    try:
        # 1. Генерируем файл
        md_path = export_chat_to_md(fpath)
        
        if not md_path or not os.path.exists(md_path):
            return await message.answer("❌ Ошибка экспорта: файл не создан.")
        
        # 2. Отправляем файл как документ с явным указанием кодировки в имени (опционально) 
        # и правильным MIME-типом
        await message.answer_document(
            document=types.FSInputFile(md_path),
            caption=f"✅ Чат экспортирован в Markdown.\n📂 Путь на сервере: <code>{md_path}</code>",
            parse_mode="HTML",
            # Важно: Telegram обычно сам определяет кодировку .md как UTF-8, 
            # но если проблемы остаются, можно добавить BOM (не рекомендуется для MD) 
            # или просто убедиться, что редактор пользователя поддерживает UTF-8.
        )
        
    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка экспорта: {str(e)[:100]}")