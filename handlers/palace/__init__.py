"""handlers/palace/__init__.py — All palace handlers"""
import asyncio
import json
import logging
import os
from pathlib import Path
import sys

from aiogram import F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import DATA_DIR, NOTES_DIR, allowed_callback, allowed_only
from services.ai_engine import call_ai_async, get_current_ai
from services.conversation_fsm import ConversationState
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format

from . import action_bar, admin, hints, kg, navigation, save, tunnels, unfiled_notes  # noqa: F401
from ._utils import (  # noqa: F401
    safe_answer_voice,
    safe_delete,
    safe_edit_text,
    safe_send,
    sanitize_wing_name,
    set_error_logging,
)
from .hints import suggest_tunnel_hint  # noqa: F401
from .save import _save_confirm, _show_save_rooms, _show_save_wings
from .shared import (
    KG_PREDICATES,
    _create_tunnel_state,
    _kg_add_state,
    _kg_page_data,
    _normalize_query,
    _pending_mcp_input,
    _save_state,
    _send_kg_page,
    _user_context,
    _wing_cache,
    fsm,
    router,
)

router.include_router(action_bar.router)
router.include_router(unfiled_notes.router)

logger = logging.getLogger("PalaceInit")

# ─── MAIN PALACE MENU ───


@router.message(Command("palace"))
@allowed_only
async def cmd_palace(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🏰 Статус", callback_data="palace_status"))
    kb.row(types.InlineKeyboardButton(text="🗺️ Навигация", callback_data="p_nav"))
    kb.row(types.InlineKeyboardButton(text="📝 Неразобранные заметки", callback_data="p_unfiled"))
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
    kb.row(types.InlineKeyboardButton(text="📝 Неразобранные заметки", callback_data="p_unfiled"))
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


async def _fetch_room_content(mcp, wing: str, room: str) -> str:
    """Извлекает текстовое содержимое комнаты из MCP или с локального диска."""
    # 1. Попытка вызова mempalace_read_drawer (если поддержан сервером или моком)
    try:
        r = await mcp.call_tool("mempalace_read_drawer", {"wing": wing, "room": room})
        if r and r.strip():
            try:
                pj = json.loads(r)
                if isinstance(pj, dict):
                    if pj.get("error"):
                        r = ""
                    elif pj.get("content"):
                        return pj["content"].strip()
            except Exception:
                pass
            if r and r.strip() and "не удалось" not in r.lower():
                return r.strip()
    except Exception as e:
        logger.debug(
            "[PALACE_TUNNEL] mempalace_read_drawer не поддержан: %s", e,
        )

    # 2. Стандартные инструменты MCP: mempalace_list_drawers + mempalace_get_drawer
    collected: list[str] = []
    try:
        raw_list = await mcp.call_tool(
            "mempalace_list_drawers",
            {"wing": wing, "room": room, "limit": 25, "offset": 0},
        )
        parsed = json.loads(raw_list) if raw_list else {}
        drawers = parsed.get("drawers", []) if isinstance(parsed, dict) else []
        for d in drawers[:15]:
            did = d.get("drawer_id")
            title = d.get("title") or d.get("source_file") or did or "Запись"
            text = ""
            if did:
                try:
                    raw_d = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": did})
                    dp = json.loads(raw_d) if raw_d else {}
                    if isinstance(dp, dict):
                        text = dp.get("content", "")
                except Exception as ex_d:
                    logger.debug("Failed getting drawer %s: %s", did, ex_d)
            if not text:
                text = d.get("content_preview", "") or ""

            source_file = d.get("source_file")
            if source_file:
                for base in [NOTES_DIR, DATA_DIR, os.path.join(DATA_DIR, "my_notes")]:
                    cand = Path(base) / source_file
                    if cand.is_file():
                        try:
                            disk_txt = cand.read_text(
                                encoding="utf-8", errors="replace"
                            ).strip()
                            if disk_txt:
                                text = disk_txt
                                break
                        except Exception:
                            pass

            if text:
                collected.append(f"--- {title} ---\n{text.strip()}")
    except Exception as e:
        logger.warning(
            "[PALACE_TUNNEL] Ошибка mempalace_list_drawers для %s/%s: %s",
            wing, room, e,
        )

    # 3. Fallback: поиск заметок по названию комнаты на диске
    if not collected:
        clean_target = room.lower().replace("_", " ").strip()
        search_roots = [NOTES_DIR, os.path.join(DATA_DIR, "my_notes")]
        for root_dir in search_roots:
            if not os.path.isdir(root_dir):
                continue
            for r, _, files in os.walk(root_dir):
                for f in files:
                    if f.endswith((".txt", ".md")):
                        base = os.path.splitext(f)[0].lower().strip()
                        clean_base = base.replace("_", " ").strip()
                        if (
                            clean_target in clean_base
                            or clean_base in clean_target
                            or clean_target in base
                            or base in clean_target
                        ):
                            try:
                                fpath = os.path.join(r, f)
                                with open(
                                    fpath, "r", encoding="utf-8", errors="replace"
                                ) as fl:
                                    txt = fl.read().strip()
                                    if txt:
                                        collected.append(f"--- {f} ---\n{txt}")
                            except Exception:
                                pass

    if collected:
        full_text = "\n\n".join(collected)
        if len(full_text) > 25000:
            full_text = full_text[:25000] + "\n\n... (контент сокращён из-за лимита длины)"
        return full_text
    return "(комната пуста или не содержит текстовых записей)"


async def process_mcp_text_input(uid: int, text: str, answer_func):
    # Check for active button-mode agent session first
    from handlers.agent import AGENT_SYSTEM_PROMPT, _run_agent_reply
    from services.agent_context import get_agent_context_store

    ctx_store = get_agent_context_store()
    session_id = ctx_store.has_active_button_session(uid)
    if session_id:
        # User is in button-mode agent dialog
        # Add user message to history first
        ctx_store.append_button_context(session_id, "user", text)
        history = ctx_store.get_button_context(session_id)
        status = await answer_func("🤖 Агент думает…")
        prompt = (
            AGENT_SYSTEM_PROMPT
            + "\n\nПродолжай диалог с пользователем на основе истории выше."
        )
        agent_result = await _run_agent_reply(
            uid, status, prompt, text, ctx={}, conversation_history=history
        )

        # Save only a successful assistant response to button session
        if agent_result.ok and agent_result.final_answer:
            ctx_store.append_button_context(
                session_id, "assistant", agent_result.final_answer,
            )

        # Check for end dialog keywords
        end_keywords = ("закончить", "stop", "end", "выход", "завершить")
        if any(kw in text.lower() for kw in end_keywords):
            ctx_store.end_button_session(session_id)
            ctx_store.unbind_button_session_from_uid(uid)
            await status.edit_text(
                "⏹ Диалог с агентом завершён. Возвращаюсь в обычный режим."
            )
        return True

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
            try:
                wing = sanitize_wing_name(text.strip().lower().replace(" ", "_"))
            except ValueError:
                await msg.edit_text("❌ Некорректное имя крыла. Только латиница, цифры, _ и -")
                return True
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
            except Exception as e:
                logger.error(
                    "Не удалось инициализировать крыло %s: %s", wing, e, exc_info=True,
                )
            await _show_save_rooms(msg.edit_text, uid)
            return True

        elif action == "save_new_room":
            room = text.strip().replace(" ", "_")
            state = _save_state.get(uid)
            if state:
                state["room"] = room
            await _save_confirm(msg.edit_text, uid)
            return True

        elif action == "unfiled_new_wing":
            from .unfiled_notes import _unfiled_state, show_unfiled_rooms
            try:
                wing = sanitize_wing_name(text.strip().lower().replace(" ", "_"))
            except ValueError:
                await msg.edit_text("❌ Некорректное имя крыла. Только латиница, цифры, _ и -")
                return True
            st = _unfiled_state.get(uid)
            if st:
                st["wing"] = wing
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m", "mempalace", "init", wing,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=DATA_DIR,
                )
                await proc.communicate()
            except Exception as e:
                logger.error("Не удалось инициализировать крыло %s: %s", wing, e)
            await show_unfiled_rooms(msg.edit_text, uid)
            return True

        elif action == "unfiled_new_room":
            from .unfiled_notes import _unfiled_state, show_unfiled_confirm
            room = text.strip().replace(" ", "_")
            st = _unfiled_state.get(uid)
            if st:
                st["room"] = room
            await show_unfiled_confirm(msg.edit_text, uid)
            return True

        elif action == "pn_new_wing":
            from handlers.personal_note import _note_data, _show_pn_rooms
            try:
                wing = sanitize_wing_name(text.strip().lower().replace(" ", "_"))
            except ValueError:
                await msg.edit_text(
                    "❌ Некорректное имя крыла. Только латиница, цифры, _ и -",
                )
                return True
            if not wing:
                await msg.edit_text(
                    "❌ Название не может быть пустым. "
                    "Введите название крыла (латиницей, без пробелов):",
                )
                return True
            data = _note_data.get(uid)
            if data:
                data["wing"] = wing
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m", "mempalace", "init", wing,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=DATA_DIR,
                )
                await proc.communicate()
            except Exception as e:
                logger.warning("Не удалось создать крыло %s: %s", wing, e)
            await _show_pn_rooms(uid, msg.edit_text)
            return True

        elif action == "pn_new_room":
            from handlers.personal_note import _note_data, _show_pn_confirm
            room = text.strip()
            if not room:
                await msg.edit_text(
                    "❌ Название не может быть пустым. "
                    "Введите название комнаты:",
                )
                return True
            data = _note_data.get(uid)
            if data:
                data["room"] = room
            await _show_pn_confirm(uid, msg.edit_text)
            return True

        elif action == "kg_add_subject":
            entity = text.strip()
            kg_state = _kg_add_state.get(uid)
            if not kg_state:
                kg_state = {"subject": "", "predicate": "", "object": ""}
                _kg_add_state[uid] = kg_state
            kg_state["subject"] = entity
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
                f"🧠 Шаг 2/3: выберите <b>тип связи</b>\n\n"
                f"Субъект: <b>{safe_html_format(entity)}</b>",
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
                    f"🧠 <b>Подтверждение:</b>\n\n"
                    f"<b>{safe_html_format(subj)}</b> → "
                    f"<b>{safe_html_format(pred)}</b> → "
                    f"<b>{safe_html_format(obj)}</b>\n\n"
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
                from .kg import _build_kgrs_callback

                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(
                        text="🔍 Поискать в заметках",
                        callback_data=_build_kgrs_callback(entity, uid),
                    ),
                )
                await msg.edit_text(
                    f"<b>🧠 Сущность: {safe_html_format(entity)}</b>\n\nНет фактов в графе знаний.",
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
                return True

            _kg_page_data[uid] = {"entity": entity, "facts": facts, "page": 0}
            await _send_kg_page(uid, msg.edit_text)
            return True

        elif action == "find_tunnels":
            clean_text = text.strip()
            parts = _normalize_query(clean_text).split()
            wing_a = parts[0] if len(parts) > 0 else None
            wing_b = parts[1] if len(parts) > 1 else None
            args = {}
            if wing_a:
                args["wing_a"] = wing_a
            if wing_b:
                args["wing_b"] = wing_b
            raw = await mcp.call_tool("mempalace_find_tunnels", args)
            found_tunnels = json.loads(raw) if raw else []

            # Поиск явных туннелей между крыльями
            extra_explicit = []
            try:
                search_wa = wing_a
                search_wb = wing_b
                if search_wa and not search_wb and "_" in search_wa:
                    w_parts = search_wa.split("_", 1)
                    search_wa, search_wb = w_parts[0], w_parts[1]
                raw_t = await mcp.call_tool("mempalace_list_tunnels")
                all_t = json.loads(raw_t) if raw_t else []
                if isinstance(all_t, dict) and "tunnels" in all_t:
                    all_t = all_t["tunnels"]
                for t in (all_t or []):
                    s_w = t.get("source", {}).get("wing", "")
                    d_w = t.get("target", {}).get("wing", "")
                    m_match = False
                    if search_wa and search_wb:
                        m_match = (
                            (s_w == search_wa and d_w == search_wb)
                            or (s_w == search_wb and d_w == search_wa)
                        )
                    elif search_wa:
                        m_match = (s_w == search_wa or d_w == search_wa)
                    if m_match:
                        extra_explicit.append(t)
            except Exception:
                pass

            if not found_tunnels and not extra_explicit:
                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(
                        text="➕ Создать туннель", callback_data="p_tc",
                    ),
                    types.InlineKeyboardButton(
                        text="🔍 Между крыльями", callback_data="p_tb",
                    ),
                )
                kb.row(
                    types.InlineKeyboardButton(
                        text="◀️ В меню туннелей", callback_data="p_tun",
                    )
                )
                await msg.edit_text(
                    "🔍 Туннелей между этими крыльями не найдено.\n\n"
                    "Туннель возникает, когда одна и та же комната (тема) "
                    "встречается в <b>разных</b> крыльях.\n"
                    "Пример: тема «интегралы» есть и в крыле «math», "
                    "и в «physics» → туннель.\n\n"
                    "💡 <i>Вы можете связать любые комнаты между крыльями "
                    "вручную через кнопку «➕ Создать туннель» "
                    "или исследовать связи через 🔀 Траверс.</i>",
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            else:
                total_cnt = len(found_tunnels) + len(extra_explicit)
                lines = [f"<b>🔄 Найдено туннелей: {total_cnt}</b>\n"]
                extra_rows = []
                for t in found_tunnels:
                    r_name = t.get("room", "?")
                    w_list = ", ".join(t.get("wings", []))
                    cnt = t.get("count", 0)
                    lines.append(
                        f"  • <b>{safe_html_format(r_name)}</b> — "
                        f"{w_list} ({cnt} записей)"
                    )
                for et in extra_explicit:
                    src_w = et.get("source", {}).get("wing", "?")
                    src_r = et.get("source", {}).get("room", "?")
                    dst_w = et.get("target", {}).get("wing", "?")
                    dst_r = et.get("target", {}).get("room", "?")
                    lbl = f" — «{et['label']}»" if et.get("label") else ""
                    lines.append(
                        f"  • {safe_html_format(src_w)}/{safe_html_format(src_r)} "
                        f"⟷ {safe_html_format(dst_w)}/{safe_html_format(dst_r)}"
                        f"{safe_html_format(lbl)}"
                    )
                    tid = et.get("id")
                    if tid:
                        extra_rows.append([
                            types.InlineKeyboardButton(
                                text=f"🤖 Обсудить: {src_r} ↔ {dst_r}",
                                callback_data=f"p_towa:{tid}",
                            )
                        ])
                extra_rows.append([
                    types.InlineKeyboardButton(
                        text="🔍 Между крыльями", callback_data="p_tb",
                    ),
                    types.InlineKeyboardButton(
                        text="◀️ В меню туннелей", callback_data="p_tun",
                    ),
                ])
                from .action_bar import finalize_answer
                await finalize_answer(
                    uid, msg.edit_text, "\n".join(lines), is_html=True,
                    ctx={"parent_cb": "p_tun"},
                    extra_rows=extra_rows,
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
                src_w = safe_html_format(navigation.format_wing_label(state['source_wing']))
                src_r = safe_html_format(navigation.format_room_label(state['source_room']))
                tgt_w = safe_html_format(navigation.format_wing_label(state['target_wing']))
                tgt_r = safe_html_format(navigation.format_room_label(state['target_room']))
                text = (
                    f"✅ <b>Туннель создан!</b>\n\n"
                    f"• {src_w}/{src_r}\n"
                    f"  ⟷ {tgt_w}/{tgt_r}\n"
                    + (f"• Описание: {safe_html_format(label)}\n" if label else "")
                    + (f"• ID: {safe_html_format(str(tunnel_id))}" if tunnel_id else "")
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

        elif action and action.startswith("agent_room:"):
            from handlers.agent import run_room_agent
            await run_room_agent(uid, msg, action[len("agent_room:"):], text.strip())

        elif action and action.startswith("ab_web_query:"):
            sid = action.split(":", 1)[1]
            from .action_bar import run_web_search_with_query
            await run_web_search_with_query(uid, msg, sid, text.strip())

        elif action == "tunnel_discuss":
            ctx = _user_context.get(uid, {})
            tunnel_id = ctx.get("tunnel_id", "")
            if not tunnel_id:
                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(
                        text="🔍 Между крыльями", callback_data="p_tb"
                    ),
                    types.InlineKeyboardButton(
                        text="◀️ В меню туннелей", callback_data="p_tun"
                    ),
                )
                await msg.edit_text(
                    "❌ Сессия обсуждения туннеля истекла.", reply_markup=kb.as_markup()
                )
                return True
            raw_tunnels = await mcp.call_tool("mempalace_list_tunnels")
            all_tunnels = json.loads(raw_tunnels) if raw_tunnels else []
            if isinstance(all_tunnels, dict) and "tunnels" in all_tunnels:
                all_tunnels = all_tunnels["tunnels"]
            tunnel = next((t for t in all_tunnels if t.get("id") == tunnel_id), None)
            if not tunnel:
                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(
                        text="🔍 Между крыльями", callback_data="p_tb"
                    ),
                    types.InlineKeyboardButton(
                        text="◀️ В меню туннелей", callback_data="p_tun"
                    ),
                )
                await msg.edit_text(
                    "❌ Туннель не найден. Возможно, он был удалён.",
                    reply_markup=kb.as_markup(),
                )
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
                content = await _fetch_room_content(mcp, wing, room)
                ctx_parts.append(f"[{wing}/{room}]\n{content.strip()}")
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
            prompt = (
                f"Вопрос пользователя: {text}\n\n"
                "Проанализируй связь между этими комнатами."
            )
            try:
                result = await call_ai_async(engine, model, [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ])
                extra_rows = [
                    [
                        types.InlineKeyboardButton(
                            text="🔍 Между крыльями", callback_data="p_tb",
                        ),
                        types.InlineKeyboardButton(
                            text="◀️ В меню туннелей", callback_data="p_tun",
                        ),
                    ]
                ]
                from .action_bar import finalize_answer
                await finalize_answer(
                    uid, msg.edit_text, result or "❌ Пустой ответ.",
                    ctx={"parent_cb": "p_tun"},
                    title=(
                        f"<b>🤖 Анализ туннеля</b>\n"
                        f"{safe_html_format(src_wing)}/{safe_html_format(src_room)} "
                        f"⟷ {safe_html_format(dst_wing)}/{safe_html_format(dst_room)}"
                    ),
                    extra_rows=extra_rows,
                )
            except Exception as ai_e:
                logger.error("[PALACE_TUNNEL] Ошибка ИИ: %s", ai_e, exc_info=True)
                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(
                        text="🔍 Между крыльями", callback_data="p_tb"
                    ),
                    types.InlineKeyboardButton(
                        text="◀️ В меню туннелей", callback_data="p_tun"
                    ),
                )
                await msg.edit_text(f"❌ Ошибка ИИ: {ai_e}", reply_markup=kb.as_markup())

    except Exception as e:
        logger.error("[PALACE_TUNNEL] Ошибка анализа: %s", e, exc_info=True)
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(
                text="🔍 Между крыльями", callback_data="p_tb"
            ),
            types.InlineKeyboardButton(
                text="◀️ В меню туннелей", callback_data="p_tun"
            ),
        )
        await msg.edit_text(f"❌ Ошибка: {e}", reply_markup=kb.as_markup())
    return True
