import re
import logging

from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F

from config import allowed_only, allowed_callback
from services.bot_setup import pending_wing_search as _pending_wing_search
from services.palace_bridge import search_palace_context

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.text == "🔍 Поиск по крылу")
@allowed_only
async def cmd_wing_search_prompt(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="🌙 Сны", callback_data="wing_search:dreams"),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="💻 Проекты", callback_data="wing_search:projects",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🏛 Философия", callback_data="wing_search:philosophy",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🎨 Творчество", callback_data="wing_search:creative",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🧠 Психология", callback_data="wing_search:psychology",
        ),
    )
    await message.answer("🔍 Выберите крыло для поиска:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("wing_search:"))
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
        f"✏️ Введите текст для поиска в крыле {wing_names.get(wing, wing)}:",
    )
    await callback.answer()


@router.message(F.text.regex(r"^/search\b.*"))
@allowed_only
async def cmd_search(message: types.Message):
    text = message.text
    query_raw = text[8:].strip()
    if not query_raw:
        return await message.answer(
            "❌ Укажите запрос: /search <текст> или /search --wing dreams <текст>",
        )
    wing = ""
    search_text = query_raw
    wing_match = re.match(r"^--wing\s+(\w+)\s+(.*)", query_raw)
    if wing_match:
        wing = wing_match.group(1).lower()
        search_text = wing_match.group(2)
        if wing not in [
            "dreams",
            "projects",
            "philosophy",
            "creative",
            "psychology",
        ]:
            wing = ""
    wing_info = f" (крыло: {wing})" if wing else ""
    st = await message.answer(f"🔍 Ищу в MemPalace{wing_info}...")
    try:
        res = await search_palace_context(search_text, limit=5, wing=wing)
        await st.edit_text(res or "Ничего не найдено.")
    except Exception as e:
        await st.edit_text(f"❌ Ошибка поиска: {str(e)[:100]}")
    return None
