"""handlers/palace/admin.py — Palace admin, MCP, instructions, maintenance"""
import asyncio

from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback
from services.palace_bridge import (
    palace_compact, palace_compress, palace_instructions,
    palace_mcp, palace_repair, palace_status, palace_wake_up,
)

from .shared import router


async def _finalize_admin_result(uid: int, edit_func, text: str, parent_cb: str):
    from .action_bar import finalize_answer
    await finalize_answer(
        uid, edit_func, text or "❌ Нет данных.",
        ctx={"parent_cb": parent_cb},
    )


@router.callback_query(F.data == "palace_status")
@allowed_callback
async def cb_palace_status(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🔍 Получаю статус...")
    try:
        result = await palace_status()
        await _finalize_admin_result(cb.from_user.id, msg.edit_text, result, "palace_back")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "palace_mcp")
@allowed_callback
async def cb_palace_mcp(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🔌 Получаю настройку MCP...")
    try:
        result = await palace_mcp()
        await _finalize_admin_result(cb.from_user.id, msg.edit_text, result, "palace_admin")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "palace_instructions")
@allowed_callback
async def cb_palace_instructions(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("📖 Загружаю инструкции...")
    try:
        result = await palace_instructions()
        await _finalize_admin_result(
            cb.from_user.id, msg.edit_text, result, "palace_back",
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "palace_admin")
@allowed_callback
async def cb_palace_admin(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🔁 Перестроить индекс", callback_data="palace_repair",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🗜️ Сжать БД (compact)", callback_data="palace_compact",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="📦 Сжать текст", callback_data="palace_compress",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🌙 Загрузить в контекст", callback_data="palace_wakeup",
        ),
    )
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="palace_back"))
    await cb.message.edit_text(
        "🔧 **Обслуживание дворца**", reply_markup=kb.as_markup(), parse_mode="Markdown",
    )


@router.callback_query(F.data == "palace_repair")
@allowed_callback
async def cb_palace_repair(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🔁 Repair запущен в фоне. Бот не блокируется.")
    uid = cb.from_user.id

    async def _run():
        try:
            result = await palace_repair()
            await _finalize_admin_result(uid, msg.edit_text, result, "palace_admin")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}")

    asyncio.create_task(_run())


@router.callback_query(F.data == "palace_compact")
@allowed_callback
async def cb_palace_compact(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🗜️ Compact запущен в фоне...")
    uid = cb.from_user.id

    async def _run():
        try:
            result = await palace_compact()
            await _finalize_admin_result(uid, msg.edit_text, result, "palace_admin")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}")

    asyncio.create_task(_run())


@router.callback_query(F.data == "palace_compress")
@allowed_callback
async def cb_palace_compress(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("📦 Компрессия в фоне...")
    uid = cb.from_user.id

    async def _run():
        try:
            result = await palace_compress()
            await _finalize_admin_result(uid, msg.edit_text, result, "palace_admin")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}")

    asyncio.create_task(_run())


@router.callback_query(F.data == "palace_wakeup")
@allowed_callback
async def cb_palace_wakeup(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🌙 Загружаю в контекст...")
    uid = cb.from_user.id

    async def _run():
        try:
            result = await palace_wake_up()
            await _finalize_admin_result(uid, msg.edit_text, result, "palace_admin")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}")

    asyncio.create_task(_run())
