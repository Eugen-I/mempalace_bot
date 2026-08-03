import json
import re
import logging

from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F

from config import allowed_only, allowed_callback
from services.bot_setup import pending_wing_search as _pending_wing_search
from services.palace_bridge import search_palace_with_sources
from services.palace_mcp import get_mcp
from services.sender import send_text_only
from services.text_formatter import split_message

logger = logging.getLogger(__name__)

router = Router()

# Cache search results for inline source buttons
search_result_cache: dict[int, list] = {}

# Cache drawer chunks opened from search sources (for p_srcdrpg: pagination)
source_drawer_cache: dict[int, dict] = {}


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
        result_text, sources = await search_palace_with_sources(
            search_text, limit=5, wing=wing,
        )
        await st.delete()
        if not result_text:
            await send_text_only(message, "Ничего не найдено.")
            return None

        # Сохраняем источники для кнопок «📄 Читать [N]»
        uid = message.from_user.id
        search_result_cache[uid] = sources

        kb = InlineKeyboardBuilder()
        for s in sources:
            loc = f"{s['wing']}/{s['room']}" if s["wing"] or s["room"] else s["file"]
            kb.row(types.InlineKeyboardButton(
                text=f"📄 Читать [{s['id']}] {loc}",
                callback_data=f"p_src:{s['id']}",
            ))
        if sources:
            kb.row(types.InlineKeyboardButton(
                text="🔍 Новый поиск", callback_data="search:wing",
            ))

        # Разбиваем длинный результат на части, кнопки — в первую
        parts = split_message(result_text)
        await message.answer(
            parts[0], parse_mode="HTML",
            reply_markup=kb.as_markup() if kb else None,
        )
        for p in parts[1:]:
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
        chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)]
        if not chunks:
            chunks = [""]
        uid = callback.from_user.id
        source_drawer_cache[uid] = {"chunks": chunks, "wing": wing, "room": room}
        await _render_source_drawer_page(callback.message.edit_text, uid, 0)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")


async def _render_source_drawer_page(edit_func, uid: int, idx: int):
    data = source_drawer_cache.get(uid)
    if not data or idx < 0 or idx >= len(data["chunks"]):
        await edit_func("❌ Данные устарели. Откройте запись заново.")
        return
    chunk = data["chunks"][idx]
    kb = InlineKeyboardBuilder()
    nav_row = []
    if idx > 0:
        nav_row.append(types.InlineKeyboardButton(
            text="◀️ Назад", callback_data=f"p_srcdrpg:{idx - 1}",
        ))
    if idx < len(data["chunks"]) - 1:
        nav_row.append(types.InlineKeyboardButton(
            text="▶️ Далее", callback_data=f"p_srcdrpg:{idx + 1}",
        ))
    if nav_row:
        kb.row(*nav_row)
    kb.row(types.InlineKeyboardButton(
        text=f"📄 {idx + 1}/{len(data['chunks'])}", callback_data="p_srcdrpg_noop",
    ))
    kb.row(types.InlineKeyboardButton(
        text="◀️ Назад к списку",
        callback_data=f"p_srcback:{data['wing']}:{data['room']}",
    ))
    await edit_func(
        chunk, parse_mode="HTML",
        reply_markup=kb.as_markup() if kb else None,
    )


@router.callback_query(F.data.startswith("p_srcdrpg:"))
@allowed_callback
async def cb_search_source_drawer_page(callback: types.CallbackQuery):
    """Navigate between chunks of a drawer opened from search."""
    await callback.answer()
    if not callback.data:
        return
    idx = int(callback.data.split(":", 1)[1])
    uid = callback.from_user.id
    await _render_source_drawer_page(callback.message.edit_text, uid, idx)


@router.callback_query(F.data == "p_srcdrpg_noop")
@allowed_callback
async def cb_search_source_drawer_page_noop(callback: types.CallbackQuery):
    await callback.answer()


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
