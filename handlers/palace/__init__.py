"""handlers/palace/__init__.py — All palace handlers"""
from . import admin, navigation, kg, save, tunnels, hints, action_bar  # noqa: F401
from ._utils import (  # noqa: F401
    safe_edit_text,
    safe_answer,
    safe_delete,
    safe_answer_voice,
    safe_send,
    set_error_logging,
)

import asyncio
import json
import sys

from aiogram import F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import DATA_DIR, allowed_callback, allowed_only
from services.ai_engine import get_current_ai
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format

from .save import _show_save_wings, _show_save_rooms, _save_confirm  # noqa: F401
from .hints import suggest_tunnel_hint  # noqa: F401

from services.conversation_fsm import ConversationState
from .shared import (
    router, fsm,
    _pending_mcp_input, _kg_page_data, _kg_add_state,
    _save_state, KG_PREDICATES, _create_tunnel_state,
    _normalize_query, _send_kg_page, _wing_cache, _user_context,
)

router.include_router(action_bar.router)

# ─── MAIN PALACE MENU ───


@router.message(Command("palace"))
@allowed_only
async def cmd_palace(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🏰 Статус", callback_data="palace_status"))
    kb.row(types.InlineKeyboardButton(text="🗺️ Навигация", callback_data="p_nav"))
    kb.row(types.InlineKeyboardButton(text="🧠 Знания (KG)", callback_data="p_kg"))
    kb.row(
        types.InlineKeyboardButton(text="🔧 Обслуживание", callback_data="palace_admin"),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="📖 Инструкции", callback_data="palace_instructions",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🏠 Главное меню", callback_data="palace_main_menu",
        ),
    )
    await message.answer(
        "🏰 **MemPalace — управление**\nВыбери раздел:",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "palace_back")
@allowed_callback
async def cb_palace_back(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🏰 Статус", callback_data="palace_status"))
    kb.row(types.InlineKeyboardButton(text="🗺️ Навигация", callback_data="p_nav"))
    kb.row(types.InlineKeyboardButton(text="🧠 Знания (KG)", callback_data="p_kg"))
    kb.row(types.InlineKeyboardButton(text="🔧 Обслуживание", callback_data="palace_admin"))
    kb.row(types.InlineKeyboardButton(text="📖 Инструкции", callback_data="palace_instructions"))
    kb.row(types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="palace_main_menu"))
    await cb.message.edit_text(
        "🏰 <b>MemPalace — управление</b>\nВыбери раздел:",
        reply_markup=kb.as_markup(), parse_mode="HTML",
    )


@router.callback_query(F.data == "palace_main_menu")
@allowed_callback
async def cb_palace_main_menu(cb: types.CallbackQuery):
    await cb.answer()
    import sys
    mod = sys.modules.get("__main__") or sys.modules.get("main")
    if mod and hasattr(mod, "cmd_start"):
        await mod.cmd_start(cb.message)
    else:
        from main import cmd_start
        await cmd_start(cb.message)


# ─── MCP TEXT INPUT ───


async def process_mcp_text_input(uid: int, text: str, answer_func):
    state = fsm.get_state(uid)

    # Try action from FSM data first (MCP_INPUT state)
    data = fsm.get_data(uid)
    action = data.get("_pending_mcp_input")

    # If IDLE but has pending_mcp_input in data (set via _FsmDict), try that
    if not action:
        action = _pending_mcp_input.pop(uid, None)

    # Fallback: check save_state for resumed flow
    if not action:
        save_state = _save_state.get(uid)
        if save_state and save_state.get("wing") and not save_state.get("room"):
            action = "save_new_room"

    if not action:
        return False

    # Consume the action from FSM data if present
    if action == data.get("_pending_mcp_input"):
        fsm.pop_data(uid, "_pending_mcp_input")

    # Reset state to IDLE after consuming — handler may set new state
    if state != ConversationState.IDLE:
        fsm.clear(uid)

    msg = await answer_func("⏳ Обрабатываю...")
    try:
        mcp = get_mcp()
        if action == "list_rooms":
            raw = text.strip()
            if raw == "*":
                mcp = get_mcp()
                raw_wings = await mcp.call_tool("mempalace_list_wings")
                parsed_w = json.loads(raw_wings)
                wdata = parsed_w.get("wings", parsed_w)
                if isinstance(wdata, dict):
                    wing_names = sorted(wdata.keys(), key=lambda x: wdata[x], reverse=True)
                else:
                    wing_names = list(wdata)
                lines = ["<b>🕸️ Все крылья:</b>\n"]
                extra_rows = []
                for w in wing_names:
                    cnt = wdata.get(w, "") if isinstance(wdata, dict) else ""
                    lines.append(f"  • <b>{safe_html_format(w)}</b> {cnt}")
                    extra_rows.append([
                        types.InlineKeyboardButton(
                            text=f"🪪 {w}",
                            callback_data=navigation._build_wing_callback_data(w),
                        ),
                    ])
                _wing_cache[uid] = wing_names
                from .action_bar import finalize_answer
                await finalize_answer(
                    uid, msg.edit_text, "\n".join(lines), is_html=True,
                    ctx={"parent_cb": "p_wing"},
                    extra_rows=extra_rows,
                )
            else:
                wing = _normalize_query(raw)
                raw_rooms = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
                parsed = json.loads(raw_rooms)
                rooms = parsed.get("rooms", {})
                wing_name = parsed.get("wing", wing)
                sorted_rooms = sorted(rooms.items(), key=lambda x: x[1], reverse=True)
                room_limit = 50
                truncated = len(sorted_rooms) > room_limit
                if truncated:
                    sorted_rooms = sorted_rooms[:room_limit]
                lines = [f"<b>🪪 Комнаты крыла «{safe_html_format(wing_name)}»:</b>\n"]
                extra_rows = []
                for idx, (room, count) in enumerate(sorted_rooms, 1):
                    lines.append(f"  {idx}. <b>{safe_html_format(room)}</b> — {count}")
                    extra_rows.append([
                        types.InlineKeyboardButton(
                            text=f"📖 {room}",
                            callback_data=navigation._build_room_callback_data(wing, room),
                        ),
                    ])
                if truncated:
                    lines.append(f"\n... и ещё {len(rooms) - room_limit} комнат.")
                from .action_bar import finalize_answer
                await finalize_answer(
                    uid, msg.edit_text, "\n".join(lines), is_html=True,
                    ctx={"parent_cb": "p_nav"},
                    extra_rows=extra_rows,
                )

        elif action in ("traverse", "traverse_start"):
            parts = text.strip().split()
            room = parts[-1] if len(parts) >= 1 else text.strip()
            hops = int(parts[0]) if len(parts) > 1 and parts[0].isdigit() else (
                int(parts[-2]) if len(parts) >= 2 and parts[-2].isdigit() else 2
            )
            if room.isdigit():
                room = parts[1] if len(parts) > 1 else ""
            room = _normalize_query(room)
            raw = await mcp.call_tool(
                "mempalace_traverse", {"start_room": room, "max_hops": hops},
            )
            parsed = json.loads(raw) if raw else {}
            if isinstance(parsed, dict) and "error" in parsed:
                suggestions = parsed.get("suggestions", [])
                text = f"❌ {parsed['error']}"
                if suggestions:
                    text += "\n\nВозможно, вы искали:\n" + "\n".join(
                        f"  • {s}" for s in suggestions[:5]
                    )
                await msg.edit_text(text, parse_mode="HTML")
            elif isinstance(parsed, list) and parsed:
                lines = [f"<b>🔀 Траверс от комнаты «{room}»:</b>\n"]
                for item in parsed:
                    r = item.get("room", "?")
                    wings = ", ".join(item.get("wings", []))
                    hop = item.get("hop", 0)
                    count = item.get("count", 0)
                    lines.append(
                        f"  {hop} hop: <b>{safe_html_format(r)}</b> — {wings} ({count} зап.)"
                    )
                from .action_bar import finalize_answer
                await finalize_answer(
                    uid, msg.edit_text, "\n".join(lines), is_html=True,
                    ctx={"parent_cb": "p_nav"},
                )
            else:
                await msg.edit_text(raw or "❌ Нет результатов.")

        elif action == "save_quote":
            state = _save_state.get(uid)
            if state:
                state["text"] = text.strip()
                state["mode"] = "quote"
            await _show_save_wings(msg.edit_text, uid)
            return True

        elif action == "save_new_wing":
            wing = text.strip().lower().replace(" ", "_")
            state = _save_state.get(uid)
            if state:
                state["wing"] = wing
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m", "mempalace", "init", wing,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=DATA_DIR,
                )
                await proc.communicate()
            except Exception:
                pass
            await _show_save_rooms(msg.edit_text, uid)
            return True

        elif action == "save_new_room":
            room = text.strip().replace(" ", "_")
            state = _save_state.get(uid)
            if state:
                state["room"] = room
            await _save_confirm(msg.edit_text, uid)
            return True

        elif action == "kg_add_subject":
            entity = text.strip()
            state = _kg_add_state.get(uid)
            if state:
                state["subject"] = entity
            kb = InlineKeyboardBuilder()
            for pred, label in KG_PREDICATES:
                kb.row(
                    types.InlineKeyboardButton(
                        text=label, callback_data=f"p_kga_pr:{pred}",
                    ),
                )
            kb.row(
                types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_kga_x"),
            )
            await msg.edit_text(
                f"🧠 Шаг 2/3: выберите **тип связи**\n\nСубъект: <b>{entity}</b>",
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
            return True

        elif action == "kg_add_object":
            obj = text.strip()
            state = _kg_add_state.get(uid)
            if state:
                state["object"] = obj
                subj = state["subject"]
                pred = state["predicate"]
                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(
                        text="✅ Добавить", callback_data="p_kga_c",
                    ),
                )
                kb.row(
                    types.InlineKeyboardButton(
                        text="❌ Отмена", callback_data="p_kga_x",
                    ),
                )
                await msg.edit_text(
                    f"🧠 **Подтверждение:**\n\n"
                    f"<b>{subj}</b> → <b>{pred}</b> → <b>{obj}</b>\n\n"
                    f"Добавить этот факт в граф знаний?",
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            else:
                await msg.edit_text("❌ Сессия истекла.")
            return True

        elif action == "kg_query":
            entity = text.strip().lower().replace(" ", "_")
            raw = await mcp.call_tool(
                "mempalace_kg_query", {"entity": entity, "direction": "both"},
            )
            parsed = json.loads(raw)
            facts = parsed if isinstance(parsed, list) else parsed.get("facts", [])
            if not facts:
                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(
                        text="🔍 Поискать в заметках",
                        callback_data=f"p_kgrs:{entity}",
                    ),
                )
                await msg.edit_text(
                    f"<b>🧠 Сущность: {entity}</b>\n\nНет фактов в графе знаний.",
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
                return True

            _kg_page_data[uid] = {"entity": entity, "facts": facts, "page": 0}
            await _send_kg_page(uid, msg.edit_text)
            return True

        elif action == "find_tunnels":
            parts = _normalize_query(text.strip()).split()
            wing_a = parts[0] if len(parts) > 0 else None
            wing_b = parts[1] if len(parts) > 1 else None
            args = {}
            if wing_a:
                args["wing_a"] = wing_a
            if wing_b:
                args["wing_b"] = wing_b
            raw = await mcp.call_tool("mempalace_find_tunnels", args)
            found_tunnels = json.loads(raw) if raw else []
            if not found_tunnels:
                await msg.edit_text(
                    "🔍 Туннелей между этими крыльями не найдено.\n\n"
                    "Туннель возникает, когда одна и та же комната (тема) "
                    "встречается в <b>разных</b> крыльях.\n"
                    "Пример: тема «интегралы» есть и в крыле «math», "
                    "и в «physics» → туннель.\n\n"
                    "У вас сейчас одно крыло — <b>my_notes</b>.\n"
                    "Чтобы увидеть туннели, добавьте ещё одно крыло "
                    "через майнинг.\n\n"
                    "Попробуйте: 🔀 <b>Траверс</b> — связи между "
                    "комнатами внутри крыла.",
                    parse_mode="HTML",
                )
            else:
                lines = [f"<b>🔄 Найдено туннелей: {len(found_tunnels)}</b>\n"]
                for t in found_tunnels:
                    lines.append(
                        f"  • <b>{safe_html_format(t.get('room', '?'))}</b> — "
                        f"{', '.join(t.get('wings', []))} "
                        f"({t.get('count', 0)} записей)",
                    )
                from .action_bar import finalize_answer
                await finalize_answer(
                    uid, msg.edit_text, "\n".join(lines), is_html=True,
                    ctx={"parent_cb": "p_tun"},
                )

        elif action == "follow_tunnels":
            parts = text.strip().split(maxsplit=1)
            if len(parts) < 2:
                await msg.edit_text(
                    "❌ Укажите крыло и комнату, "
                    "например: `мои заметки сны`",
                )
                return True
            wing = _normalize_query(parts[0])
            room = _normalize_query(parts[1])
            raw = await mcp.call_tool(
                "mempalace_follow_tunnels", {"wing": wing, "room": room},
            )
            from .action_bar import finalize_answer
            await finalize_answer(
                uid, msg.edit_text, raw or "❌ Нет результатов.",
                ctx={"wing": wing, "room": room, "parent_cb": "p_tun"},
            )

        elif action == "create_tunnel":
            state = _create_tunnel_state.pop(uid, None)
            if not state:
                await msg.edit_text(
                    "❌ Сессия создания туннеля истекла. Начните заново.",
                )
                return True
            label = text.strip()
            if label == "-" or not label:
                label = None
            args = {
                "source_wing": state["source_wing"],
                "source_room": state["source_room"],
                "target_wing": state["target_wing"],
                "target_room": state["target_room"],
            }
            if label:
                args["label"] = label
            raw = await mcp.call_tool("mempalace_create_tunnel", args)
            try:
                result = json.loads(raw)
                tunnel_id = result.get("tunnel_id", "")
                text = (
                    f"✅ <b>Туннель создан!</b>\n\n"
                    f"• {safe_html_format(state['source_wing'])}"
                    f"/{safe_html_format(state['source_room'])}\n"
                    f"  ⟷ {safe_html_format(state['target_wing'])}"
                    f"/{safe_html_format(state['target_room'])}\n"
                    + (f"• Описание: {label}\n" if label else "")
                    + (f"• ID: {tunnel_id}" if tunnel_id else "")
                )
            except (json.JSONDecodeError, TypeError):
                text = raw or "✅ Туннель создан!"
            from .action_bar import finalize_answer
            await finalize_answer(
                uid, msg.edit_text, text, is_html=True,
                ctx={
                    "source_wing": state.get("source_wing", ""),
                    "target_wing": state.get("target_wing", ""),
                    "parent_cb": "p_tun",
                },
            )

        elif action and action.startswith("ask_room_ai:"):
            parts = action.split(":", 2)
            if len(parts) >= 3:
                _, wing, room = parts
                from .navigation import _answer_room_ai
                await _answer_room_ai(msg, uid, wing, room, text.strip())

        elif action == "tunnel_discuss":
            ctx = _user_context.get(uid, {})
            tunnel_id = ctx.get("tunnel_id", "")
            if not tunnel_id:
                await msg.edit_text("❌ Сессия обсуждения туннеля истекла.")
                return True
            raw_tunnels = await mcp.call_tool("mempalace_list_tunnels")
            all_tunnels = json.loads(raw_tunnels) if raw_tunnels else []
            if isinstance(all_tunnels, dict) and "tunnels" in all_tunnels:
                all_tunnels = all_tunnels["tunnels"]
            tunnel = next((t for t in all_tunnels if t.get("id") == tunnel_id), None)
            if not tunnel:
                await msg.edit_text("❌ Туннель не найден. Возможно, он был удалён.")
                return True
            src = tunnel.get("source", {})
            dst = tunnel.get("target", {})
            src_wing = src.get("wing", "?")
            src_room = src.get("room", "?")
            dst_wing = dst.get("wing", "?")
            dst_room = dst.get("room", "?")
            tunnel_label = tunnel.get("label", "")
            ctx_parts = []
            for wing, room in [(src_wing, src_room), (dst_wing, dst_room)]:
                try:
                    r = await mcp.call_tool(
                        "mempalace_read_drawer", {"wing": wing, "room": room},
                    )
                    ctx_parts.append(f"[{wing}/{room}]\n{r.strip()}")
                except Exception:
                    ctx_parts.append(f"[{wing}/{room}]\n(не удалось прочитать)")
            from services.ai_engine import _sync_ai_call
            engine, model = get_current_ai()
            system = (
                "Ты анализируешь связь между двумя комнатами знаний. "
                "Используй ТОЛЬКО данные из этих комнат. "
                "Отвечай на русском языке.\n\n"
                f"Туннель: {src_wing}/{src_room} "
                f"⟷ {dst_wing}/{dst_room}"
            )
            if tunnel_label:
                system += f"\nОписание: {tunnel_label}"
            system += "\n\n" + "\n\n".join(ctx_parts)
            prompt = f"Вопрос пользователя: {text}\n\nПроанализируй связь между этими комнатами."
            try:
                result = _sync_ai_call(engine, model, [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ])
                from .action_bar import finalize_answer
                await finalize_answer(
                    uid, msg.edit_text, result or "❌ Пустой ответ.",
                    ctx={"parent_cb": "p_tun"},
                    title=(
                        f"<b>🤖 Анализ туннеля</b>\n"
                        f"{safe_html_format(src_wing)}/{safe_html_format(src_room)} "
                        f"⟷ {safe_html_format(dst_wing)}/{safe_html_format(dst_room)}"
                    ),
                )
            except Exception as ai_e:
                await msg.edit_text(f"❌ Ошибка ИИ: {ai_e}")

    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")
    return True
