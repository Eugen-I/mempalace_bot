import json
import re
import logging

from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F

from config import allowed_only, allowed_callback
from services.bot_setup import pending_wing_search as _pending_wing_search
from services.palace_bridge import search_palace_context
from services.palace_mcp import get_mcp
from services.sender import send_text_only
from services.text_formatter import split_message

logger = logging.getLogger(__name__)

router = Router()

# Cache search results for inline source buttons
search_result_cache: dict[int, list] = {}


async def _open_room_view(edit_func, uid: int, wing: str, room: str):
    """Open a room's file listing."""
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool(
            "mempalace_list_drawers",
            {"wing": wing, "room": room, "limit": 5, "offset": 0},
        )
        parsed = json.loads(raw)
        drawers = parsed.get("drawers", [])
        total = parsed.get("count", 0)

        if not drawers:
            await edit_func(
                f"📖 В комнате <b>{wing}/{room}</b> пока нет записей.",
                parse_mode="HTML",
            )
            return

        lines = [f"<b>📖 Записи в {wing}/{room}</b>  ({total} записей)\n"]
        for i, d in enumerate(drawers):
            preview = d.get("content_preview", "") or d.get("content", "")[:60]
            lines.append(f"{i + 1}. <code>{preview[:60]}</code>")

        kb = InlineKeyboardBuilder()
        for i, d in enumerate(drawers):
            drawer_id = d.get("drawer_id", "")
            dn = d.get("closet_name") or d.get("title") or d.get("name", "")
            kb.row(types.InlineKeyboardButton(
                text=f"📄 {i + 1}. {dn or preview[:40]}",
                callback_data=f"p_srcdr:{wing}:{room}:{drawer_id}",
            ))
        if total > 5:
            kb.row(types.InlineKeyboardButton(
                text="📂 Все записи", callback_data=f"p_srcroom:{wing}:{room}",
            ))

        await edit_func("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        await edit_func(f"❌ Ошибка: {e}")


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


@router.callback_query(F.data == "search:wing")
@allowed_callback
async def cb_search_wing(callback: types.CallbackQuery):
    await cmd_wing_search_prompt(callback.message)
    await callback.answer()


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
        await st.delete()
        # Разбиваем длинный результат на части
        parts = split_message(res or "Ничего не найдено.")
        for p in parts:
            await send_text_only(message, p)
    except Exception as e:
        await st.edit_text(f"❌ Ошибка поиска: {str(e)[:100]}")
    return None


@router.callback_query(F.data.startswith("p_src:"))
@allowed_callback
async def cb_search_source_open(callback: types.CallbackQuery):
    """Open a source from search results."""
    await callback.answer()
    if not callback.data:
        return
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
    try:
        src_id = int(parts[1])
    except ValueError:
        return
    uid = callback.from_user.id
    sources = search_result_cache.get(uid, [])
    src = next((s for s in sources if s["id"] == src_id), None)
    if not src:
        await callback.message.edit_text("❌ Результаты поиска устарели.")
        return
    wing = src.get("wing", "")
    room = src.get("room", "")
    if not wing or not room:
        await callback.message.edit_text("❌ Источник не содержит wing/room.")
        return
    await _open_room_view(callback.message.edit_text, uid, wing, room)


@router.callback_query(F.data.startswith("p_srcdr:"))
@allowed_callback
async def cb_search_source_drawer(callback: types.CallbackQuery):
    """Open a specific drawer from search source room view."""
    await callback.answer()
    if not callback.data:
        return
    parts = callback.data.split(":", 3)
    if len(parts) < 4:
        return
    _, wing, room, drawer_id = parts
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": drawer_id})
        parsed = json.loads(raw) if raw else {}
        text = parsed.get("content", "") if isinstance(parsed, dict) else raw or ""
        chunk = text[:3500]
        kb = InlineKeyboardBuilder()
        if len(text) > 3500:
            kb.row(types.InlineKeyboardButton(
                text="Далее", callback_data=f"p_cr:{0}",
            ))
        kb.row(types.InlineKeyboardButton(
            text="◀️ Назад", callback_data=f"p_srcback:{wing}:{room}",
        ))
        await callback.message.edit_text(
            chunk, parse_mode="HTML",
            reply_markup=kb.as_markup() if kb else None,
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_srcroom:"))
@allowed_callback
async def cb_search_source_all_drawers(callback: types.CallbackQuery):
    """Show all drawers in a source room (paginated)."""
    await callback.answer()
    if not callback.data:
        return
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        return
    _, wing, room = parts
    uid = callback.from_user.id
    await _open_room_view(callback.message.edit_text, uid, wing, room)


@router.callback_query(F.data.startswith("p_srcback:"))
@allowed_callback
async def cb_search_source_back(callback: types.CallbackQuery):
    """Back to source room view."""
    await callback.answer()
    if not callback.data:
        return
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        return
    _, wing, room = parts
    uid = callback.from_user.id
    await _open_room_view(callback.message.edit_text, uid, wing, room)
