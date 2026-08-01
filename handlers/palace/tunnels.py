"""handlers/palace/tunnels.py — Tunnel management handlers"""
import json

from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format

from .shared import (
    router,
    _pending_mcp_input, _tunnel_state, _create_tunnel_state,
    _room_cache,
)

# ─── TUNNELS (non‑conflicting handlers only) ───


async def _show_cross_rooms(edit_func, uid: int, src_wing: str, src_room: str):
    mcp = get_mcp()
    try:
        connected = json.loads(
            await mcp.call_tool(
                "mempalace_traverse", {"start_room": src_room, "max_hops": 1},
            ),
        )
    except Exception:
        connected = []
    if not connected:
        await edit_func(f"❌ Для комнаты «{src_room}» нет связанных комнат.")
        return
    rooms = []
    for node in connected if isinstance(connected, list) else [connected]:
        if isinstance(node, dict):
            r = node.get("room", "")
            w = node.get("wing", "")
            if r and r != src_room:
                rooms.append((w, r))
    if not rooms:
        await edit_func(f"❌ Для «{src_room}» нет связанных комнат.")
        return
    kb = InlineKeyboardBuilder()
    for w, r in rooms:
        kb.row(types.InlineKeyboardButton(
            text=f"📁 {w}/{r}", callback_data=f"p_crr:{r}",
        ))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tun"))
    await edit_func(
        f"<b>🔗 Связанные комнаты с «{src_room}»:</b>",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_tfa_"))
@allowed_callback
async def cb_find_tunnels_wing_b(cb: types.CallbackQuery):
    await cb.answer()
    wing_a = cb.data[6:]
    _pending_mcp_input[cb.from_user.id] = "find_tunnels"
    await cb.message.edit_text(
        f"🔍 Выбрано крыло A: <b>{wing_a}</b>\n"
        f"Введите название крыла B (или '-' для любого):",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("p_tfb_"))
@allowed_callback
async def cb_find_tunnels_result(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    wing_b = cb.data[6:]
    state = _tunnel_state.get(uid, {})
    wing_a = state.get("wing_a", "")
    await cb.message.edit_text(f"🔍 Ищу туннели между {wing_a} и {wing_b}...")
    mcp = get_mcp()
    args = {"wing_a": wing_a}
    if wing_b and wing_b != "-":
        args["wing_b"] = wing_b
    try:
        raw = await mcp.call_tool("mempalace_find_tunnels", args)
        tunnels = json.loads(raw) if raw else []
        if not tunnels:
            await cb.message.edit_text("🔗 Туннелей не найдено.")
            return
        lines = [f"<b>🔗 Туннели между {wing_a} и {wing_b}</b>\n"]
        for t in tunnels:
            lines.append(
                f"  • <b>{safe_html_format(t.get('room', '?'))}</b> — "
                f"{', '.join(t.get('wings', []))} ({t.get('count', 0)})",
            )
        from .action_bar import finalize_answer
        await finalize_answer(
            uid, cb.message.edit_text, "\n".join(lines), is_html=True,
            ctx={"parent_cb": "p_tun"},
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_to")
@allowed_callback
async def cb_follow_tunnels_wing(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "follow_tunnels"
    await cb.message.edit_text(
        "🔍 Введите <b>крыло</b> и <b>комнату</b> для поиска туннелей.\n"
        "Пример: <code>мои заметки сны</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("p_tow_"))
@allowed_callback
async def cb_follow_tunnels_room(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    wing = cb.data[6:]
    _tunnel_state[uid] = {"wing_a": wing}
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
        parsed = json.loads(raw)
        rooms = parsed.get("rooms", {})
    except Exception:
        rooms = {}
    if not rooms:
        await cb.message.edit_text(f"❌ В крыле «{wing}» нет комнат.")
        return
    kb = InlineKeyboardBuilder()
    for room in rooms:
        kb.row(types.InlineKeyboardButton(
            text=f"📁 {room}", callback_data=f"p_tor:{room}",
        ))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tun"))
    await cb.message.edit_text(
        f"🕸️ <b>Крыло: {wing}</b>\nВыберите комнату:",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_tor_"))
@allowed_callback
async def cb_follow_tunnels_result(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    room = cb.data[6:]
    state = _tunnel_state.get(uid, {})
    wing = state.get("wing_a", "")
    await cb.message.edit_text(f"🔍 Ищу туннели из {wing}/{room}...")
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool(
            "mempalace_follow_tunnels", {"wing": wing, "room": room},
        )
        from .action_bar import finalize_answer
        await finalize_answer(
            uid, cb.message.edit_text, raw or "❌ Нет результатов.",
            ctx={"wing": wing, "room": room, "parent_cb": "p_tun"},
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")


async def _show_wing_buttons_for_tunnel(edit_func, action: str, uid: int, exclude_wing: str = ""):
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = parsed.get("wings", parsed)
    except Exception:
        wings = {}
    wing_iter = wings.keys() if isinstance(wings, dict) else wings
    wing_names = [w for w in wing_iter if w != exclude_wing]
    if not wing_names:
        await edit_func("❌ Нет доступных крыльев.")
        return False
    kb = InlineKeyboardBuilder()
    for w in wing_names:
        kb.row(types.InlineKeyboardButton(
            text=f"🕸️ {w}", callback_data=f"p_{action}_{w}",
        ))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tun"))
    await edit_func("Выберите крыло:", reply_markup=kb.as_markup())
    return True


@router.callback_query(F.data == "p_tc")
@allowed_callback
async def cb_create_tunnel_source_wing(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _create_tunnel_state[uid] = {}
    await _show_wing_buttons_for_tunnel(
        cb.message.edit_text, "tcs", uid,
    )


@router.callback_query(F.data.startswith("p_tcs_"))
@allowed_callback
async def cb_create_tunnel_source_room(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    wing = cb.data[6:]
    _create_tunnel_state.setdefault(uid, {})["source_wing"] = wing
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
        parsed = json.loads(raw)
        rooms = parsed.get("rooms", {})
    except Exception:
        rooms = {}
    if not rooms:
        await cb.message.edit_text(f"❌ В крыле «{wing}» нет комнат.")
        return
    _room_cache[uid] = list(rooms.items())
    kb = InlineKeyboardBuilder()
    for i, (room, _) in enumerate(rooms.items()):
        kb.row(types.InlineKeyboardButton(
            text=f"📁 {room}", callback_data=f"p_tcsr_{i}",
        ))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tc"))
    await cb.message.edit_text(
        f"🕸️ <b>{wing}</b>\nВыберите исходную <b>комнату</b>:",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_tcsr_"))
@allowed_callback
async def cb_create_tunnel_target_wing(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[7:])
    rooms = _room_cache.get(uid)
    if not rooms or idx >= len(rooms):
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    state = _create_tunnel_state.get(uid, {})
    state["source_room"] = rooms[idx][0]
    state["source_idx"] = idx
    await _show_wing_buttons_for_tunnel(
        cb.message.edit_text, "tctw", uid, state.get("source_wing", ""),
    )


@router.callback_query(F.data.startswith("p_tctw_"))
@allowed_callback
async def cb_create_tunnel_target_room(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    wing = cb.data[7:]
    state = _create_tunnel_state.get(uid, {})
    state["target_wing"] = wing
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
        parsed = json.loads(raw)
        rooms = parsed.get("rooms", {})
    except Exception:
        rooms = {}
    if not rooms:
        await cb.message.edit_text(f"❌ В крыле «{wing}» нет комнат.")
        return
    _room_cache[uid] = list(rooms.items())
    kb = InlineKeyboardBuilder()
    for i, (room, _) in enumerate(rooms.items()):
        kb.row(types.InlineKeyboardButton(
            text=f"📁 {room}", callback_data=f"p_tctr:{i}",
        ))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tc"))
    await cb.message.edit_text(
        f"🕸️ <b>{wing}</b>\nВыберите целевую <b>комнату</b>:",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_tctr_"))
@allowed_callback
async def cb_create_tunnel_label_prompt(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[7:])
    rooms = _room_cache.get(uid)
    state = _create_tunnel_state.get(uid)
    if not rooms or not state or idx >= len(rooms):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    state["target_room"] = rooms[idx][0]
    _pending_mcp_input[uid] = "create_tunnel"
    src_w = safe_html_format(state['source_wing'])
    src_r = safe_html_format(state['source_room'])
    tgt_w = safe_html_format(state['target_wing'])
    tgt_r = safe_html_format(state['target_room'])
    await cb.message.edit_text(
        f"🏗️ <b>Почти готово!</b>\n\n"
        f"Исходная: {src_w}/{src_r}\n"
        f"Целевая:  {tgt_w}/{tgt_r}\n\n"
        "✏️ Введите описание связи (или «-» чтобы пропустить):",
        parse_mode="HTML",
    )
