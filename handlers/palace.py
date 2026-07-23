import os, json, secrets
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import allowed_only, allowed_callback
from services.palace_bridge import (
    search_palace_context, palace_status, palace_list_wings, palace_list_rooms,
    palace_get_taxonomy, palace_traverse, palace_find_tunnels, palace_wake_up,
    palace_split, palace_compress, palace_repair, palace_instructions
)
from services.text_formatter import safe_html_format, split_message

router = Router()
_palace_wing_cache: dict[str, str] = {}

@router.message(Command("palace"))
@allowed_only
async def cmd_palace(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🏰 Статус", callback_data="palace_status"))
    kb.row(types.InlineKeyboardButton(text="📂 Крылья", callback_data="palace_wings"))
    kb.row(types.InlineKeyboardButton(text="🌐 Полная иерархия", callback_data="palace_taxonomy"))
    kb.row(types.InlineKeyboardButton(text="🔧 Обслуживание", callback_data="palace_admin"))
    kb.row(types.InlineKeyboardButton(text="📖 Инструкции", callback_data="palace_instructions"))
    await message.answer("🏰 **MemPalace — управление дворцом**\nВыберите действие:", reply_markup=kb.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data == "palace_status")
@allowed_callback
async def cb_palace_status(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🔍 Получаю статус...")
    result = await palace_status()
    await msg.edit_text(result or "❌ Не удалось получить статус.")

@router.callback_query(F.data == "palace_wings")
@allowed_callback
async def cb_palace_wings(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("📂 Загружаю список крыльев...")
    result = await palace_list_wings()
    await msg.edit_text(result or "❌ Нет данных о крыльях.")

@router.callback_query(F.data == "palace_taxonomy")
@allowed_callback
async def cb_palace_taxonomy(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🌐 Загружаю иерархию...")
    result = await palace_get_taxonomy()
    parts = split_message(result or "❌ Нет данных.")
    await msg.edit_text(parts[0])
    for p in parts[1:]:
        await cb.message.answer(p)

@router.callback_query(F.data == "palace_instructions")
@allowed_callback
async def cb_palace_instructions(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("📖 Загружаю инструкции...")
    result = await palace_instructions()
    await msg.edit_text(result or "❌ Нет инструкций.")

@router.callback_query(F.data == "palace_admin")
@allowed_callback
async def cb_palace_admin(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🔁 Перестроить индекс", callback_data="palace_repair"))
    kb.row(types.InlineKeyboardButton(text="🗜 Сжать хранилище", callback_data="palace_compress"))
    kb.row(types.InlineKeyboardButton(text="🌙 Загрузить в контекст", callback_data="palace_wakeup"))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="palace_back"))
    await cb.message.edit_text("🔧 **Обслуживание дворца**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data == "palace_repair")
@allowed_callback
async def cb_palace_repair(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🔁 Перестраиваю векторный индекс...")
    result = await palace_repair()
    await msg.edit_text(result or "❌ Ошибка.")

@router.callback_query(F.data == "palace_compress")
@allowed_callback
async def cb_palace_compress(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🗜 Сжимаю хранилище...")
    result = await palace_compress()
    await msg.edit_text(result or "❌ Ошибка.")

@router.callback_query(F.data == "palace_wakeup")
@allowed_callback
async def cb_palace_wakeup(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🌙 Загружаю дворец в контекст...")
    result = await palace_wake_up()
    await msg.edit_text(result or "❌ Ошибка.")

@router.callback_query(F.data == "palace_back")
@allowed_callback
async def cb_palace_back(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🏰 Статус", callback_data="palace_status"))
    kb.row(types.InlineKeyboardButton(text="📂 Крылья", callback_data="palace_wings"))
    kb.row(types.InlineKeyboardButton(text="🌐 Полная иерархия", callback_data="palace_taxonomy"))
    kb.row(types.InlineKeyboardButton(text="🔧 Обслуживание", callback_data="palace_admin"))
    kb.row(types.InlineKeyboardButton(text="📖 Инструкции", callback_data="palace_instructions"))
    await cb.message.edit_text("🏰 **MemPalace — управление дворцом**", reply_markup=kb.as_markup(), parse_mode="Markdown")
