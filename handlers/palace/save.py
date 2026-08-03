"""handlers/palace/save.py — Save/quote handlers for palace notes"""
import json

from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback
from services.ai_cache import _ai_msg_cache
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format

from .shared import (
    router,
    _pending_mcp_input, _save_state, _wing_cache, _room_cache,
)


# ─── SAVE / QUOTE ───


@router.callback_query(F.data == "p_sv")
@allowed_callback
async def cb_save_start(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    msg = cb.message
    original = msg.html_text or msg.text or ""
    if not original:
        if msg.reply_to_message:
            rtm = msg.reply_to_message
            original = rtm.html_text or rtm.text or rtm.caption or ""
        elif _ai_msg_cache:
            for chat_msgs in _ai_msg_cache.values():
                if chat_msgs:
                    last_id = max(chat_msgs.keys())
                    original = chat_msgs[last_id]
                    break
    if not original:
        await cb.message.answer("❌ Нет текста для сохранения.")
        return
    _save_state[uid] = {"text": original, "mode": "full"}
    new_msg = await cb.message.answer("⏳ Загружаю крылья...")
    await _show_save_wings(new_msg.edit_text, uid)


@router.callback_query(F.data == "p_sv_x")
@allowed_callback
async def cb_save_cancel(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _save_state.pop(uid, None)
    await cb.message.answer("❌ Сохранение отменено.")


@router.callback_query(F.data == "p_sv_a")
@allowed_callback
async def cb_save_all(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _save_state.get(uid)
    if state:
        state["mode"] = "full"
    await _show_save_wings(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_sv_q")
@allowed_callback
async def cb_save_quote_prompt(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "save_quote"
    await cb.message.edit_text(
        "💬 Введите цитату (фрагмент текста для сохранения):",
    )


async def _show_save_wings(edit_func, uid: int):
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = parsed.get("wings", parsed)
    except Exception:
        wings = {}
    if not wings:
        await edit_func("❌ Не удалось загрузить крылья.")
        return
    wing_names = list(wings.keys()) if isinstance(wings, dict) else list(wings)
    _wing_cache[uid] = wing_names
    kb = InlineKeyboardBuilder()
    for i, w in enumerate(wing_names):
        kb.row(types.InlineKeyboardButton(
            text=f"🕸️ {w}", callback_data=f"p_sw_{i}",
        ))
    kb.row(types.InlineKeyboardButton(text="➕ Новое крыло", callback_data="p_sv_nw"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_sv_x"))
    await edit_func(
        "📂 Выберите **крыло** для сохранения:",
        parse_mode="Markdown", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_sw_"))
@allowed_callback
async def cb_save_wing_chosen(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        idx = int(cb.data[5:])
    except ValueError:
        return
    wings = _wing_cache.get(uid)
    if not wings or idx >= len(wings):
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    state = _save_state.get(uid)
    if state:
        state["wing"] = wings[idx]
    await _show_save_rooms(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_sv_nw")
@allowed_callback
async def cb_save_new_wing_prompt(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "save_new_wing"
    await cb.message.edit_text(
        "🕸️ Введите название нового крыла (латиницей, без пробелов):",
    )


async def _show_save_rooms(edit_func, uid: int):
    state = _save_state.get(uid)
    if not state:
        await edit_func("❌ Сессия истекла.")
        return
    wing = state.get("wing", "")
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
        parsed = json.loads(raw)
        rooms = parsed.get("rooms", {})
    except Exception:
        rooms = {}
    if not rooms:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(
            text="➕ Создать комнату", callback_data="p_sv_nr",
        ))
        kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_sv_x"))
        await edit_func(
            f"📁 В крыле «{wing}» нет комнат. Создать?",
            reply_markup=kb.as_markup(),
        )
        return
    room_names = list(rooms.keys())
    _room_cache[uid] = [(r, rooms[r]) for r in room_names]
    kb = InlineKeyboardBuilder()
    for i, r in enumerate(room_names):
        kb.row(types.InlineKeyboardButton(
            text=f"📁 {r}", callback_data=f"p_sr_{i}",
        ))
    kb.row(types.InlineKeyboardButton(text="➕ Новая комната", callback_data="p_sv_nr"))
    kb.row(types.InlineKeyboardButton(text="◀️ К выбору крыла", callback_data="p_sv_bw"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_sv_x"))
    await edit_func(
        f"📂 Крыло: <b>{wing}</b>\nВыберите <b>комнату</b>:",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_sv_bw")
@allowed_callback
async def cb_save_back_to_wings(cb: types.CallbackQuery):
    await cb.answer()
    await _show_save_wings(cb.message.edit_text, cb.from_user.id)


@router.callback_query(F.data.startswith("p_sr_"))
@allowed_callback
async def cb_save_room_chosen(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        idx = int(cb.data[5:])
    except ValueError:
        return
    rooms = _room_cache.get(uid)
    if not rooms or idx >= len(rooms):
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    state = _save_state.get(uid)
    if state:
        state["room"] = rooms[idx][0]
    await _save_confirm(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_sv_nr")
@allowed_callback
async def cb_save_new_room_prompt(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "save_new_room"
    await cb.message.edit_text(
        "📁 Введите название новой комнаты (можно с пробелами):",
    )


async def _save_confirm(edit_func, uid: int):
    state = _save_state.get(uid)
    if not state:
        await edit_func("❌ Сессия истекла.")
        return
    mode_label = "Цитата" if state.get("mode") == "quote" else "Полный текст"
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="💾 Сохранить", callback_data="p_sv_c"))
    kb.row(types.InlineKeyboardButton(text="◀️ Другая комната", callback_data="p_sv_br"))
    kb.row(types.InlineKeyboardButton(text="◀️ Другое крыло", callback_data="p_sv_bw"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_sv_x"))
    await edit_func(
        f"📂 <b>Подтверждение сохранения</b>\n\n"
        f"🕸️ Крыло: {safe_html_format(state.get('wing', '?'))}\n"
        f"📁 Комната: {safe_html_format(state.get('room', '?'))}\n"
        f"📝 Режим: {mode_label}\n\n"
        f"Текст: {safe_html_format(state.get('text', '')[:200])}...\n\n"
        f"Сохранить?",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_sv_br")
@allowed_callback
async def cb_save_back_to_rooms(cb: types.CallbackQuery):
    await cb.answer()
    await _show_save_rooms(cb.message.edit_text, cb.from_user.id)


@router.callback_query(F.data == "p_sv_c")
@allowed_callback
async def cb_save_confirm_execute(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _save_state.pop(uid, None)
    if not state:
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    wing = state.get("wing", "my_notes")
    room = state.get("room", "inbox")
    text = state.get("text", "")
    mode = state.get("mode", "full")
    if mode == "quote":
        content = f"> {text}\n\n— из диалога с ИИ"
    else:
        content = text
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_add_drawer", {
            "wing": wing, "room": room, "content": content,
        })
        await cb.message.edit_text(
            _format_save_result(raw, wing, room),
            parse_mode="HTML",
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка сохранения: {e}")


def _format_save_result(raw: str, wing: str, room: str) -> str:
    """Превращает сырой JSON-ответ mempalace_add_drawer в человекочитаемое сообщение."""
    header = f"✅ Сохранено в <b>{safe_html_format(wing)}/{safe_html_format(room)}</b>!"
    try:
        data = json.loads(raw or "")
    except (json.JSONDecodeError, ValueError):
        return header
    if isinstance(data, dict) and data.get("success") is False:
        detail = data.get("error") or "не удалось сохранить"
        failed = (
            f"❌ Ошибка сохранения в "
            f"<b>{safe_html_format(wing)}/{safe_html_format(room)}</b>: "
            f"{safe_html_format(str(detail))}"
        )
        return failed
    if isinstance(data, dict) and data.get("drawer_id"):
        return f"{header}\n📎 <code>{safe_html_format(data['drawer_id'])}</code>"
    return header
