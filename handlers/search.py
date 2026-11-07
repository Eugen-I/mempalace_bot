import json
import logging
import re

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback, allowed_only
from services.bot_setup import pending_wing_search as _pending_wing_search
from services.error_formatter import format_user_error
from services.palace_bridge import search_palace_with_sources
from services.palace_mcp import get_mcp
from services.sender import send_text_only
from services.text_formatter import split_message
from services.wing_registry import (
    WING_KEYS,
    get_wing_display_name,
    normalize_wing,
)

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
    for wing in WING_KEYS:
        kb.row(types.InlineKeyboardButton(
            text=get_wing_display_name(wing), callback_data=f"wing_search:{wing}",
        ))
    await message.answer("🔍 Выберите крыло для поиска:", reply_markup=kb.as_markup())


@router.callback_query(F.data == "search:wing")
@allowed_callback
async def cb_search_wing(callback: types.CallbackQuery):
    await cmd_wing_search_prompt(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("wing_search:"))
@allowed_callback
async def cb_wing_search_select(callback: types.CallbackQuery):
    raw_wing = callback.data.split(":", 1)[1]
    wing = normalize_wing(raw_wing) or raw_wing
    uid = callback.from_user.id
    _pending_wing_search[uid] = wing
    await callback.message.edit_text(
        f"✏️ Введите текст для поиска в крыле {get_wing_display_name(wing)}:",
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
        wing = normalize_wing(wing_match.group(1))
        search_text = wing_match.group(2)
    wing_info = f" (крыло: {wing})" if wing else ""
    st = await message.answer(f"🔍 Ищу в MemPalace{wing_info}...")
    try:
        from services.omni_search import omni_search
        import services.palace_bridge as pb

        if search_palace_with_sources is not pb.search_palace_with_sources and not wing:
            result_text, sources = await search_palace_with_sources(
                search_text, limit=5, wing=wing,
            )
        else:
            result_text, sources = await omni_search(
                search_text, limit=5, wing=wing, palace_searcher=search_palace_with_sources,
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
            stype = s.get("source_type", "palace")
            sid = str(s.get("id", ""))
            if stype == "notes":
                title = s.get("title") or s.get("location") or "Заметка"
                kb.row(types.InlineKeyboardButton(
                    text=f"📝 Читать [{sid}] {title[:28]}",
                    callback_data=f"p_notesrc:{sid}",
                ))
            elif stype == "files":
                title = s.get("title") or s.get("location") or "Файл"
                kb.row(types.InlineKeyboardButton(
                    text=f"📁 Читать [{sid}] {title[:28]}",
                    callback_data=f"p_filesrc:{sid}",
                ))
            else:
                loc = (
                    f"{s['wing']}/{s['room']}"
                    if s.get("wing") or s.get("room")
                    else s.get("file", "")
                )
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
        await st.edit_text(format_user_error(e, "search"))
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


@router.callback_query(F.data.startswith("p_notesrc:"))
@allowed_callback
async def cb_search_source_note(callback: types.CallbackQuery):
    """Открыть Apple Note из результатов поиска."""
    await callback.answer()
    if not callback.data:
        return
    note_id = callback.data.split(":", 1)[1]
    try:
        import asyncio
        from services.apple_notes import read_note
        from services.notes_sync import get_backlinks_by_source
        loop = asyncio.get_running_loop()
        note = await loop.run_in_executor(None, read_note, note_id)
        if not note:
            await callback.message.edit_text("❌ Заметка не найдена.")
            return
        title = note.get("name") or "Заметка"
        folder = note.get("folder") or "Заметки"
        body = note.get("body") or note.get("snippet") or "(пустая заметка)"

        backlinks = get_backlinks_by_source("apple_notes", note_id)
        link_info = ""
        if backlinks:
            link_lines = [f"• <code>{b['wing']}/{b['room']}</code>" for b in backlinks[:3]]
            link_info = "\n\n🔗 <b>Связано с Дворцом:</b>\n" + "\n".join(link_lines)

        text = f"📝 <b>{title}</b>\n📁 Папка: <code>{folder}</code>{link_info}\n\n{body[:3500]}"

        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(
                text="🔗 Связать с Дворцом",
                callback_data=f"p_link_note:{note_id}",
            )
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except TypeError:
            await callback.message.edit_text(text, parse_mode="HTML")
    except Exception as exc:
        logger.warning("[Search] Ошибка чтения заметки %s: %s", note_id, exc)
        await callback.message.edit_text(f"❌ Не удалось открыть заметку: {exc}")


@router.callback_query(F.data.startswith("p_link_note:"))
@allowed_callback
async def cb_search_link_note(callback: types.CallbackQuery):
    """Автоматическое связывание открытой заметки с Дворцом."""
    await callback.answer()
    if not callback.data:
        return
    note_id = callback.data.split(":", 1)[1]
    await callback.message.edit_text("⏳ Анализирую заметку и таксономию Дворца...")
    try:
        import asyncio
        from services.apple_notes import read_note
        from services.notes_sync import recommend_room_for_note, record_backlink
        loop = asyncio.get_running_loop()
        note = await loop.run_in_executor(None, read_note, note_id)
        if not note:
            await callback.message.edit_text("❌ Заметка не найдена.")
            return

        title = note.get("name") or "Заметка"
        body = note.get("body") or note.get("snippet") or ""
        rec = await recommend_room_for_note(title, body)
        wing = rec.get("wing", "my_notes")
        room = rec.get("room", "inbox")

        full_content = f"📄 {title}\n\n{body}"
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_add_drawer",
            {
                "wing": wing,
                "room": room,
                "content": full_content,
                "source_id": str(note_id),
                "source_type": "apple_notes",
                "source_file": f"notes://showNote?identifier={note_id}",
            },
        )
        parsed = json.loads(raw or "{}")
        drawer_id = parsed.get("drawer_id", "")
        if drawer_id:
            record_backlink(
                drawer_id=drawer_id,
                source_type="apple_notes",
                source_id=str(note_id),
                wing=wing,
                room=room,
                content=full_content,
                title=title,
            )

        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(
                text="📄 Вернуться к заметке",
                callback_data=f"p_notesrc:{note_id}",
            )
        )
        await callback.message.edit_text(
            f"✅ <b>Заметка успешно связана с Дворцом!</b>\n\n"
            f"📄 <b>{title}</b>\n"
            f"🏛 Локация: <code>{wing}/{room}</code>\n"
            f"🆔 Ящик: <code>{drawer_id}</code>",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
    except Exception as exc:
        logger.error("[Search] Link note error: %s", exc, exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка связывания: {exc}")


@router.callback_query(F.data.startswith("p_filesrc:"))
@allowed_callback
async def cb_search_source_file(callback: types.CallbackQuery):
    """Открыть файл из результатов поиска."""
    await callback.answer()
    if not callback.data:
        return
    file_id = callback.data.split(":", 1)[1]
    try:
        import asyncio
        from services.file_index import get_file
        loop = asyncio.get_running_loop()
        file_doc = await loop.run_in_executor(None, get_file, file_id)
        if not file_doc:
            await callback.message.edit_text("❌ Файл не найден.")
            return
        filename = file_doc.get("filename") or "Файл"
        folder = file_doc.get("folder") or "Документы"
        content = file_doc.get("extracted_text") or "(пустой файл)"
        text = f"📁 <b>{filename}</b>\nКаталог: <code>{folder}</code>\n\n{content[:3500]}"
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception as exc:
        logger.warning("[Search] Ошибка чтения файла %s: %s", file_id, exc)
        await callback.message.edit_text(f"❌ Не удалось открыть файл: {exc}")
