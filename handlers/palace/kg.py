"""handlers/palace/kg.py — Knowledge Graph handlers"""
import json

from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format

from .shared import (
    router,
    _pending_mcp_input, _kg_page_data, _kg_search_data, _kg_add_state,
    KG_PAGE_SIZE, KG_PREDICATES,
    _read_state,
    _send_kg_page,
)
from .hints import _get_full_text_from_chroma


# ─── KNOWLEDGE GRAPH ───


@router.callback_query(F.data == "p_kg")
@allowed_callback
async def cb_kg_menu(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📊 Статистика", callback_data="p_kgst"))
    kb.row(types.InlineKeyboardButton(text="🔍 Поиск сущности", callback_data="p_kgq"))
    kb.row(types.InlineKeyboardButton(text="➕ Добавить факт", callback_data="p_kga"))
    kb.row(types.InlineKeyboardButton(text="❓ Помощь", callback_data="p_kg_help"))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="palace_back"))
    await cb.message.edit_text(
        "🧠 <b>Граф Знаний (Knowledge Graph)</b>\nВыберите действие:",
        reply_markup=kb.as_markup(), parse_mode="HTML",
    )


@router.callback_query(F.data == "p_kg_help")
@allowed_callback
async def cb_kg_help(cb: types.CallbackQuery):
    await cb.answer()
    help_text = (
        "🧠 <b>Граф Знаний — справка</b>\n\n"
        "Граф знаний хранит факты вида:\n"
        "  <b>Субъект → Предикат → Объект</b>\n\n"
        "<b>Примеры:</b>\n"
        "  Платон → wrote → Государство\n"
        "  Юнг → influenced_by → Фрейд\n"
        "  Сон_20240301 → contains_idea → лабиринт\n\n"
        "<b>📊 Статистика</b> — сколько всего сущностей, фактов, типов связей\n"
        "<b>🔍 Поиск</b> — показать все факты о сущности\n"
        "<b>➕ Добавить факт</b> — создать новый факт\n\n"
        "<i>Факты автоматически связываются с заметками из MemPalace.</i>"
    )
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_kg"))
    await cb.message.edit_text(help_text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "p_kgst")
@allowed_callback
async def cb_kg_stats(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("📊 Загружаю статистику KG...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_kg_stats")
        parsed = json.loads(raw)
        lines = ["<b>📊 Статистика графа знаний</b>\n"]
        if isinstance(parsed, dict):
            for k, v in parsed.items():
                if isinstance(v, dict):
                    lines.append(f"\n<b>{k}:</b>")
                    for sk, sv in v.items():
                        lines.append(f"  • {sk}: {sv}")
                else:
                    lines.append(f"\n<b>{k}:</b> {v}")
        else:
            lines.append(str(parsed))
        await msg.edit_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_kga")
@allowed_callback
async def cb_kg_add_start(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "kg_add_subject"
    await cb.message.edit_text(
        "🧠 <b>Добавление факта в граф знаний</b>\n\n"
        "Шаг 1/3: введите <b>субъект</b> (о ком или о чём факт):",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "p_kga_x")
@allowed_callback
async def cb_kg_add_cancel(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _kg_add_state.pop(uid, None)
    _pending_mcp_input.pop(uid, None)
    await cb.message.edit_text("❌ Добавление факта отменено.")


@router.callback_query(F.data == "p_kga_s")
@allowed_callback
async def cb_kg_add_subject_prompt(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "kg_add_subject"
    await cb.message.edit_text("🧠 Введите субъект факта:")


@router.callback_query(F.data == "p_kga_p")
@allowed_callback
async def cb_kg_add_predicate_menu(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _kg_add_state.get(uid)
    if not state:
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    kb = InlineKeyboardBuilder()
    for pred, label in KG_PREDICATES:
        kb.row(types.InlineKeyboardButton(
            text=label, callback_data=f"p_kga_pr:{pred}",
        ))
    kb.row(types.InlineKeyboardButton(
        text="❌ Отмена", callback_data="p_kga_x",
    ))
    await cb.message.edit_text(
        f"🧠 Шаг 2/3: выберите <b>тип связи</b>\n\n"
        f"Субъект: <b>{state.get('subject', '?')}</b>",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_kga_pr:"))
@allowed_callback
async def cb_kg_add_predicate_chosen(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    pred = cb.data[10:]
    state = _kg_add_state.get(uid)
    if state:
        state["predicate"] = pred
    _pending_mcp_input[uid] = "kg_add_object"
    await cb.message.edit_text(
        "🧠 Шаг 3/3: введите <b>объект</b> (на что указывает связь):",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "p_kga_o")
@allowed_callback
async def cb_kg_add_object_prompt(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "kg_add_object"
    await cb.message.edit_text("🧠 Введите объект факта:")


@router.callback_query(F.data.startswith("p_kga_c"))
@allowed_callback
async def cb_kg_add_confirm(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _kg_add_state.pop(uid, None)
    if not state:
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    await cb.message.edit_text("⏳ Добавляю факт в граф знаний...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_kg_add", {
            "subject": state["subject"],
            "predicate": state["predicate"],
            "object": state["object"],
        })
        await cb.message.edit_text(raw or "✅ Факт сохранён!")
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_kgq")
@allowed_callback
async def cb_kg_query_prompt(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "kg_query"
    await cb.message.edit_text(
        "🔍 Введите имя сущности для поиска в графе знаний:",
    )


@router.callback_query(F.data == "p_kgc")
@allowed_callback
async def cb_kg_continue(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _kg_page_data.get(uid)
    if data:
        data["page"] += 1
    await _send_kg_page(uid, cb.message.edit_text)


@router.callback_query(F.data == "p_kgs")
@allowed_callback
async def cb_kg_restart(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _kg_page_data.get(uid)
    if data:
        data["page"] = 0
    await _send_kg_page(uid, cb.message.edit_text)


@router.callback_query(F.data == "p_kgr")
@allowed_callback
async def cb_kg_read(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _kg_page_data.get(uid)
    if not data:
        await cb.message.edit_text("❌ Нет данных для чтения.")
        return
    entity = data.get("entity", "")
    await _kg_search_and_show(uid, cb.message.edit_text, entity, None)


@router.callback_query(F.data.startswith("p_kgrs:"))
@allowed_callback
async def cb_kg_read_search(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    entity = cb.data[8:]
    await _kg_search_and_show(uid, cb.message.edit_text, entity, cb.message)


async def _kg_search_and_show(uid: int, edit_func, entity: str, original_msg):
    mcp = get_mcp()
    try:
        search_raw = await mcp.call_tool("mempalace_search", {"query": entity, "limit": 10})
        search_results = json.loads(search_raw) if search_raw else []
    except Exception:
        search_results = []
    if not search_results:
        await edit_func(f"❌ По запросу «{entity}» ничего не найдено.")
        return
    _kg_search_data[uid] = {"entity": entity, "results": search_results, "page": 0}
    await _send_kg_search_page(uid, edit_func)


async def _send_kg_search_page(uid: int, edit_func):
    data = _kg_search_data.get(uid)
    if not data:
        return
    results = data["results"]
    page = data["page"]
    start = page * KG_PAGE_SIZE
    end = min(start + KG_PAGE_SIZE, len(results))
    page_results = results[start:end]
    lines = [
        f"<b>🔍 Результаты поиска: {data['entity']}</b>  "
        f"({len(results)} всего)\n",
    ]
    for i, r in enumerate(page_results, start + 1):
        if isinstance(r, dict):
            content = (r.get("content", r.get("text", str(r))) or "")[:200]
            source = r.get("source", r.get("closet", ""))
            line = f"  {i}. {safe_html_format(content)}"
            if source:
                line += f"\n     📄 {safe_html_format(source)}"
        else:
            line = f"  {i}. {safe_html_format(str(r)[:200])}"
        lines.append(line)
    kb = InlineKeyboardBuilder()
    nav = []
    if end < len(results):
        nav.append(types.InlineKeyboardButton(
            text=f"▶️ Далее ({len(results) - end})", callback_data="p_krd:n",
        ))
    if page > 0:
        nav.append(types.InlineKeyboardButton(
            text="◀️ Назад", callback_data="p_krd:p",
        ))
    if nav:
        kb.row(*nav)
    for i in range(start, end):
        kb.row(types.InlineKeyboardButton(
            text=f"📄 {i + 1}", callback_data=f"p_krd:{i}",
        ))
    await edit_func("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("p_krd:"))
@allowed_callback
async def cb_kg_read_result(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    param = cb.data[6:]
    data = _kg_search_data.get(uid)
    if not data:
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    if param == "n":
        data["page"] += 1
        await _send_kg_search_page(uid, cb.message.edit_text)
        return
    if param == "p":
        data["page"] = max(0, data["page"] - 1)
        await _send_kg_search_page(uid, cb.message.edit_text)
        return
    try:
        idx = int(param)
    except ValueError:
        return
    results = data["results"]
    if idx < 0 or idx >= len(results):
        return
    r = results[idx]
    if isinstance(r, dict):
        content = r.get("content", r.get("text", str(r))) or ""
        source = r.get("source", r.get("closet", ""))
        wing = r.get("wing", "")
        room = r.get("room", "")
    else:
        content = str(r)
        source = ""
        wing = ""
        room = ""
    pure_text = content
    _read_state[uid] = {"room": room, "wing": wing, "drawer": source, "source": ""}
    msg_len = len(pure_text)
    if msg_len > 3500:
        lines_out = [safe_html_format(pure_text[:3500])]
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(
            text=f"📄 Далее ({msg_len - 3500} символов)",
            callback_data="p_krb:0",
        ))
        if source:
            full_text = _get_full_text_from_chroma(source, wing, room)
            if full_text and len(full_text) > msg_len:
                _read_state[uid]["source"] = full_text
                kb.row(types.InlineKeyboardButton(
                    text="📖 Читать полный текст", callback_data="p_krb:f",
                ))
        await cb.message.edit_text(
            "\n".join(lines_out), parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
    else:
        await cb.message.edit_text(
            safe_html_format(pure_text), parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("p_krb:"))
@allowed_callback
async def cb_kg_read_back(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    param = cb.data[6:]
    state = _read_state.get(uid)
    if param == "f" and state:
        full = state.get("source", "")
        if full:
            lines = [safe_html_format(full[:3500])]
            kb = InlineKeyboardBuilder()
            if len(full) > 3500:
                kb.row(types.InlineKeyboardButton(
                    text="📄 Далее", callback_data="p_cr:3500",
                ))
            await cb.message.edit_text(
                "\n".join(lines), parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
            return
    await cb.message.edit_text("📖 Конец записи.")
