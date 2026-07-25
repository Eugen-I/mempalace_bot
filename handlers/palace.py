import asyncio
import json
import logging
import os
import sqlite3
import sys
import time

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import DATA_DIR, allowed_callback, allowed_only
from services.ai_cache import _ai_msg_cache
from services.palace_bridge import (
    palace_compact,
    palace_compress,
    palace_instructions,
    palace_mcp,
    palace_repair,
    palace_status,
    palace_wake_up,
)
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format

router = Router()
logger = logging.getLogger("Palace")


class TtlDict(dict):
    __slots__ = ("_expires", "_ttl")

    def __init__(self, ttl: int = 1800):
        self._ttl = ttl
        self._expires: dict = {}
        super().__init__()

    def _prune(self, key):
        exp = self._expires.get(key)
        if exp is not None and time.monotonic() > exp:
            del self._expires[key]
            super().pop(key, None)

    def __setitem__(self, key, value):
        self._expires[key] = time.monotonic() + self._ttl
        super().__setitem__(key, value)

    def __getitem__(self, key):
        self._prune(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._prune(key)
        return super().get(key, default)

    def pop(self, key, *args):
        self._prune(key)
        val = super().pop(key, *args)
        self._expires.pop(key, None)
        return val

    def __contains__(self, key):
        self._prune(key)
        return super().__contains__(key)


# Pending MCP text inputs: {user_id: action_type}
_pending_mcp_input: TtlDict = TtlDict()

# Pagination state for KG query
_kg_page_data: TtlDict = TtlDict()
_kg_search_data: TtlDict = TtlDict()
_kg_add_state: TtlDict = TtlDict()
_save_state: TtlDict = TtlDict()
KG_PAGE_SIZE = 5

KG_PREDICATES = [
    ("topic", "📌 тема"),
    ("related_to", "🔗 связано с"),
    ("wrote", "✍️ написал"),
    ("contains_idea", "💡 идея"),
    ("contains_quote", "💬 цитата"),
    ("author", "👤 автор"),
    ("influenced_by", "🎯 под влиянием"),
]

# Caches for inline wing/room selection
_wing_cache: TtlDict = TtlDict()
_room_cache: TtlDict = TtlDict()
_tunnel_state: TtlDict = TtlDict()
_create_tunnel_state: TtlDict = TtlDict()
_drawer_state: TtlDict = TtlDict()
_read_state: TtlDict = TtlDict()
_room_session: TtlDict = TtlDict()
_tunnels_cache: TtlDict = TtlDict()

# Соответствие русских названий английским/немецким именам в базе
_LOCALE_ALIASES = {
    "мои заметки": "my_notes",
    "заметки": "my_notes",
    "сны": "сны_и_отрывки_снов",
    "сны и отрывки снов": "сны_и_отрывки_снов",
    "докторская": "заметки_для_докторской_диссертации",
    "идеи": "идеи",
    "философия": "философия",
    "архетипы": "проект_архитипы_юнга_социальная_маска",
    "фото": "названия_фото",
    "фотографии": "названия_фото",
    "разработка": "it_разработка",
    "it": "it_разработка",
    "общее": "general",
    "general": "general",
    "цитаты": "цитаты_юнга_по_архитирам",
    "юнг": "цитаты_юнга_по_архитирам",
    "тренировки": "тренировки",
    "стихи": "мои_стихи",
    "сценарии": "сценарии",
    "фотографы": "фотографы",
    "манифесты": "манифесты",
    "кураторский": "кураторский_текст",
    "психоанализ": "психоаналитическая_модель_опыта_в_творчестве_фотографа",
    "экспликации": "экспликации_к_фотографиям",
    "мысли из книг": "мысли_из_книг",
    "высказывания": "высказывание",
    "дневник": "визуальный_дневник_b_элементов_и_a_функций",
    "выставка": "расходы_на_выставку",
}


def _normalize_query(text: str) -> str:
    t = text.strip().lower()
    if t in _LOCALE_ALIASES:
        return _LOCALE_ALIASES[t]
    t = t.replace(" ", "_")
    return t


async def _send_kg_page(uid: int, edit_func):
    data = _kg_page_data.get(uid)
    if not data:
        return
    facts = data["facts"]
    page = data["page"]
    total = len(facts)
    start = page * KG_PAGE_SIZE
    end = min(start + KG_PAGE_SIZE, total)
    page_facts = facts[start:end]

    lines = [f"<b>🧠 Сущность: {data['entity']}</b>  <i>({total} фактов)</i>\n"]
    for i, f in enumerate(page_facts):
        if isinstance(f, dict):
            line = f"  • {safe_html_format(f.get('subject', '?'))} → {safe_html_format(f.get('predicate', '?'))} → {safe_html_format(f.get('object', '?'))}"  # noqa: E501
            src = f.get("source_closet", "")
            if src:
                short_src = src.rsplit("/", 1)[-1]  # just filename
                line += f"\n    📄 {safe_html_format(short_src)}"
            if f.get("valid_from"):
                line += f" (с {f['valid_from']})"
        else:
            line = f"  • {safe_html_format(str(f))}"
        lines.append(line)

    kb = InlineKeyboardBuilder()
    nav_buttons = []
    if end < total:
        more = total - end
        nav_buttons.append(
            types.InlineKeyboardButton(
                text=f"▶️ Продолжить ({more})", callback_data="p_kgc",
            ),
        )
    elif page > 0:
        nav_buttons.append(
            types.InlineKeyboardButton(text="◀️ Начать сначала", callback_data="p_kgs"),
        )
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.row(types.InlineKeyboardButton(text="📖 Читать записи", callback_data="p_kgr"))

    await edit_func(
        "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup() if kb else None,
    )


async def _format_mcp_result(raw: str) -> str:
    """Пытается распарсить JSON-ответ MCP и отформатировать красиво."""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            lines = []
            for k, v in data.items():
                if isinstance(v, dict):
                    sub = "\n".join(f"  • {sk}: {sv}" for sk, sv in v.items())
                    lines.append(f"**{k}:**\n{sub}")
                elif isinstance(v, list):
                    items = "\n".join(f"  • {i}" for i in v)
                    lines.append(f"**{k}:**\n{items}")
                else:
                    lines.append(f"**{k}:** {v}")
            return "\n".join(lines)
        return raw
    except (json.JSONDecodeError, TypeError):
        return raw


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
    await message.answer(
        "🏰 **MemPalace — управление**\nВыбери раздел:",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "palace_status")
@allowed_callback
async def cb_palace_status(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🔍 Получаю статус...")
    try:
        result = await palace_status()
        await msg.edit_text(result or "❌ Нет данных.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "palace_mcp")
@allowed_callback
async def cb_palace_mcp(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🔌 Получаю настройку MCP...")
    try:
        result = await palace_mcp()
        await msg.edit_text(result or "❌ Ошибка.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "palace_instructions")
@allowed_callback
async def cb_palace_instructions(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("📖 Загружаю инструкции...")
    try:
        result = await palace_instructions()
        await msg.edit_text(result or "❌ Нет инструкций.", parse_mode="HTML")
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

    async def _run():
        try:
            result = await palace_repair()
            await msg.edit_text(result or "❌ Ошибка.")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}")

    asyncio.create_task(_run())


@router.callback_query(F.data == "palace_compact")
@allowed_callback
async def cb_palace_compact(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer(
        "🗜️ Compact запущен в фоне. Освобождает место от старых сегментов БД.",
    )

    async def _run():
        try:
            result = await palace_compact()
            await msg.edit_text(result or "❌ Ошибка.")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}")

    asyncio.create_task(_run())


@router.callback_query(F.data == "palace_compress")
@allowed_callback
async def cb_palace_compress(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("📦 Compress запущен в фоне.")

    async def _run():
        try:
            result = await palace_compress()
            await msg.edit_text(result or "❌ Ошибка.")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}")

    asyncio.create_task(_run())


@router.callback_query(F.data == "palace_wakeup")
@allowed_callback
async def cb_palace_wakeup(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🌙 Wake-up запущен в фоне.")

    async def _run():
        try:
            result = await palace_wake_up()
            await msg.edit_text(result or "❌ Ошибка.")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}")

    asyncio.create_task(_run())


@router.callback_query(F.data == "palace_back")
@allowed_callback
async def cb_palace_back(cb: types.CallbackQuery):
    await cb.answer()
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
    await cb.message.edit_text(
        "🏰 **MemPalace — управление**",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )


# ─── NAVIGATION ───


@router.callback_query(F.data == "p_nav")
@allowed_callback
async def cb_nav_menu(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🕸️ Крылья", callback_data="p_wing"))
    kb.row(types.InlineKeyboardButton(text="🪪 Комнаты", callback_data="p_room"))
    kb.row(types.InlineKeyboardButton(text="🏛️ Таксономия", callback_data="p_tax"))
    kb.row(types.InlineKeyboardButton(text="📊 Граф связей", callback_data="p_grf"))
    kb.row(types.InlineKeyboardButton(text="🔄 Туннели", callback_data="p_tun"))
    kb.row(types.InlineKeyboardButton(text="🔀 Траверс", callback_data="p_trv"))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="palace_back"))
    await cb.message.edit_text(
        "🗺️ **Навигация по дворцу**", reply_markup=kb.as_markup(), parse_mode="Markdown",
    )


@router.callback_query(F.data == "p_wing")
@allowed_callback
async def cb_list_wings(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🕸️ Загружаю список крыльев...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = parsed.get("wings", {})
        lines = ["<b>🕸️ Крылья дворца:</b>\n"]
        for idx, (name, count) in enumerate(
            sorted(wings.items(), key=lambda x: -x[1]), 1,
        ):
            display = name.replace("mempalace_", "").replace("_", " ").title()
            lines.append(f"  {idx}. <b>{safe_html_format(display)}</b> — {count}")
        await msg.edit_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_room")
@allowed_callback
async def cb_rooms_menu(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = sorted(parsed.get("wings", {}).items(), key=lambda x: -x[1])
        _wing_cache[uid] = wings

        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="🌐 Все комнаты", callback_data="p_rs_*"),
        )
        for i, (name, count) in enumerate(wings):
            display = name.replace("mempalace_", "").replace("_", " ").title()
            short = display[:20] + "\u2026" if len(display) > 20 else display
            kb.row(
                types.InlineKeyboardButton(
                    text=f"{short} ({count})", callback_data=f"p_rs_{i}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_nav"),
        )
        await cb.message.edit_text(
            "🏰 **Выберите крыло для просмотра комнат:**",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown",
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_rs_"))
@allowed_callback
async def cb_rooms_select(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = cb.data[5:]
    items = _wing_cache.get(uid)
    if not items:
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return

    msg = await cb.message.answer("⏳ Загружаю комнаты...")
    try:
        mcp = get_mcp()
        if idx == "*":
            wing = None
        else:
            wing = items[int(idx)][0]
        args = {"wing": wing} if wing else {}
        raw = await mcp.call_tool("mempalace_list_rooms", args)
        parsed = json.loads(raw)
        rooms = parsed.get("rooms", {})
        wing_name = parsed.get("wing", wing or "все")
        sorted_rooms = sorted(rooms.items())
        _room_session[uid] = {"wing": wing_name, "rooms": sorted_rooms}
        lines = [f"<b>🪪 Комнаты крыла «{safe_html_format(wing_name)}»:</b>\n"]
        for room_idx, (room, count) in enumerate(sorted_rooms, 1):
            lines.append(f"  {room_idx}. <b>{safe_html_format(room)}</b> — {count}")
        kb = InlineKeyboardBuilder()
        for room_idx, (room, count) in enumerate(sorted_rooms):
            display = safe_html_format(room[:25] + ("\u2026" if len(room) > 25 else ""))
            kb.row(
                types.InlineKeyboardButton(
                    text=f"📂 {display} ({count})", callback_data=f"p_rdr:{room_idx}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(
                text="\u25c0\ufe0f К списку крыльев", callback_data="p_room",
            ),
        )
        kb.row(
            types.InlineKeyboardButton(
                text="🏰 Главное меню", callback_data="palace_back",
            ),
        )
        await msg.edit_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_rdr:"))
@allowed_callback
async def cb_room_drawers(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data.split(":", 1)[1])
    cache = _room_session.get(uid)
    if not cache:
        return await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
    rooms = cache.get("rooms", [])
    if idx >= len(rooms):
        return await cb.message.edit_text("❌ Комната не найдена.")
    room_name = rooms[idx][0]
    wing = cache["wing"]
    await _show_drawers_page(cb.message.edit_text, uid, wing, room_name, 0)


DRAWER_PAGE_SIZE = 5


async def _show_drawers_page(edit_func, uid: int, wing: str, room: str, offset: int):
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_list_drawers",
            {"wing": wing, "room": room, "limit": DRAWER_PAGE_SIZE, "offset": offset},
        )
        parsed = json.loads(raw)
        drawers = parsed.get("drawers", [])
        total = parsed.get("count", 0)

        _drawer_state[uid] = {
            "wing": wing,
            "room": room,
            "offset": offset,
            "total": total,
            "drawers": drawers,
        }

        if not drawers:
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(
                    text="\u25c0\ufe0f К комнатам", callback_data="p_room",
                ),
            )
            return await edit_func(
                "📭 В этой комнате пока нет записей.",
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )

        lines = [
            f"<b>📄 Записи в «{safe_html_format(wing)} / {safe_html_format(room)}»</b>  ({total})\n",
        ]
        for i, d in enumerate(drawers):
            preview = d.get("content_preview", "") or d.get("content", "")[:80]
            safe_p = safe_html_format(preview[:80])
            lines.append(f"{offset + i + 1}. <code>{safe_p}</code>")

        kb = InlineKeyboardBuilder()
        for i, d in enumerate(drawers):
            kb.row(
                types.InlineKeyboardButton(
                    text=f"📄 Получить запись {offset + i + 1}",
                    callback_data=f"p_gd:{i}",
                ),
            )
        nav_row = []
        if offset > 0:
            nav_row.append(
                types.InlineKeyboardButton(
                    text="\u25c0\ufe0f Назад",
                    callback_data=f"p_rdp:{max(0, offset - DRAWER_PAGE_SIZE)}",
                ),
            )
        if offset + DRAWER_PAGE_SIZE < total:
            nav_row.append(
                types.InlineKeyboardButton(
                    text="\u25b6\ufe0f Вперед",
                    callback_data=f"p_rdp:{offset + DRAWER_PAGE_SIZE}",
                ),
            )
        if nav_row:
            kb.row(*nav_row)
        kb.row(
            types.InlineKeyboardButton(
                text="📡 Читать с туннелями", callback_data=f"p_crr:{offset}",
            ),
        )
        kb.row(
            types.InlineKeyboardButton(
                text="\u25c0\ufe0f К комнатам", callback_data="p_room",
            ),
        )
        kb.row(
            types.InlineKeyboardButton(
                text="🏰 Главное меню", callback_data="palace_back",
            ),
        )
        await edit_func(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
        )

    except Exception as e:
        logger.error(f"Room drawers error: {e}", exc_info=True)
        await edit_func(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data.startswith("p_rdp:"))
@allowed_callback
async def cb_drawers_page(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    offset = int(cb.data.split(":", 1)[1])
    state = _drawer_state.get(uid)
    if not state:
        return await cb.message.edit_text("❌ Сессия истекла.")
    await _show_drawers_page(
        cb.message.edit_text, uid, state["wing"], state["room"], offset,
    )


@router.callback_query(F.data.startswith("p_gd:"))
@allowed_callback
async def cb_get_drawer(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data.split(":", 1)[1])
    state = _drawer_state.get(uid)
    if not state or idx >= len(state.get("drawers", [])):
        return await cb.message.edit_text("❌ Сессия истекла.")
    drawer_id = state["drawers"][idx]["drawer_id"]
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": drawer_id})
        parsed = json.loads(raw)
        content = parsed.get("content", "") or parsed.get("text", "")
        d_wing = parsed.get("wing", state["wing"])
        d_room = parsed.get("room", state["room"])
        _read_state[uid] = {
            "content": content,
            "page": 0,
            "wing": d_wing,
            "room": d_room,
            "idx": idx,
        }
        CHUNK = 3500
        if len(content) <= CHUNK:
            text = (
                f"<b>📄 Запись</b>\n"
                f"<code>{safe_html_format(d_wing)}/{safe_html_format(d_room)}</code>\n\n"
                f"{safe_html_format(content)}"
            )
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(
                    text="🔗 Связано", callback_data=f"p_ct:{idx}",
                ),
            )
            kb.row(
                types.InlineKeyboardButton(
                    text="\u25c0\ufe0f К списку", callback_data="p_bd",
                ),
            )
            await cb.message.edit_text(
                text, parse_mode="HTML", reply_markup=kb.as_markup(),
            )
        else:
            chunk = content[:CHUNK]
            text = (
                f"<b>📄 Запись</b>\n"
                f"<code>{safe_html_format(d_wing)}/{safe_html_format(d_room)}</code>\n\n"
                f"{safe_html_format(chunk)}"
            )
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(
                    text="📖 Продолжить чтение", callback_data="p_cr:1",
                ),
            )
            kb.row(
                types.InlineKeyboardButton(
                    text="🔗 Связано", callback_data=f"p_ct:{idx}",
                ),
            )
            kb.row(
                types.InlineKeyboardButton(
                    text="\u25c0\ufe0f К списку", callback_data="p_bd",
                ),
            )
            await cb.message.edit_text(
                text, parse_mode="HTML", reply_markup=kb.as_markup(),
            )
    except Exception as e:
        logger.error(f"Get drawer error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data.startswith("p_cr:"))
@allowed_callback
async def cb_read_more(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    page = int(cb.data.split(":", 1)[1])
    data = _read_state.get(uid)
    if not data:
        return await cb.message.edit_text("❌ Сессия истекла.")
    content = data["content"]
    CHUNK = 3500
    total_pages = max(1, (len(content) + CHUNK - 1) // CHUNK)
    if page >= total_pages:
        return await cb.answer("Это конец записи.", show_alert=False)
    start = page * CHUNK
    chunk = content[start : start + CHUNK]
    _read_state[uid] = {"content": content, "page": page}
    text = f"{safe_html_format(chunk)}"
    kb = InlineKeyboardBuilder()
    nav_row = []
    if page > 0:
        nav_row.append(
            types.InlineKeyboardButton(
                text="\u25c0\ufe0f Назад", callback_data=f"p_cr:{page - 1}",
            ),
        )
    if page + 1 < total_pages:
        nav_row.append(
            types.InlineKeyboardButton(
                text="\u25b6\ufe0f Вперед", callback_data=f"p_cr:{page + 1}",
            ),
        )
    if nav_row:
        kb.row(*nav_row)
    kb.row(
        types.InlineKeyboardButton(text="\u25c0\ufe0f К списку", callback_data="p_bd"),
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "p_bd")
@allowed_callback
async def cb_back_to_drawers(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _read_state.pop(uid, None)
    state = _drawer_state.get(uid)
    if state:
        await _show_drawers_page(
            cb.message.edit_text, uid, state["wing"], state["room"], state["offset"],
        )
    else:
        await cb.message.edit_text("❌ Сессия истекла.")


@router.callback_query(F.data.startswith("p_crr:"))
@allowed_callback
async def cb_cross_room_read(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _drawer_state.get(uid)
    if not state:
        return await cb.message.edit_text("❌ Сессия истекла.")
    wing, room = state["wing"], state["room"]
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_follow_tunnels", {"wing": wing, "room": room},
        )
        tunnels = json.loads(raw) if raw else []
        rooms = [(wing, room)]
        for t in tunnels:
            cw = t.get("connected_wing", "")
            cr = t.get("connected_room", "")
            if cw and cr:
                rooms.append((cw, cr))
        _drawer_state[uid] = {"tunnel_rooms": rooms}
        await _show_cross_rooms(cb.message.edit_text, uid, rooms, 0, back_cb="p_bd")
    except Exception as e:
        logger.error(f"Cross-room read error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data.startswith("p_crp:"))
@allowed_callback
async def cb_cross_room_page(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    offset = int(cb.data.split(":", 1)[1])
    state = _drawer_state.get(uid)
    if not state or "tunnel_rooms" not in state:
        return await cb.message.edit_text("❌ Сессия истекла.")
    back_cb = state.get("tunnel_back", "p_tl")
    await _show_cross_rooms(
        cb.message.edit_text, uid, state["tunnel_rooms"], offset, back_cb,
    )


@router.callback_query(F.data.startswith("p_crg:"))
@allowed_callback
async def cb_cross_get_drawer(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data.split(":", 1)[1])
    state = _drawer_state.get(uid)
    if (
        not state
        or "tunnel_drawers" not in state
        or idx >= len(state["tunnel_drawers"])
    ):
        return await cb.message.edit_text("❌ Сессия истекла.")
    d = state["tunnel_drawers"][idx]
    drawer_id = d.get("drawer_id") or d.get("id", "")
    if not drawer_id:
        return await cb.message.edit_text("❌ Нет ID записи.")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": drawer_id})
        parsed = json.loads(raw)
        content = parsed.get("content", "") or parsed.get("text", "")
        d_wing = parsed.get("wing", d.get("_wing", "?"))
        d_room = parsed.get("room", d.get("_room", "?"))
        _read_state[uid] = {
            "content": content,
            "page": 0,
            "wing": d_wing,
            "room": d_room,
        }
        CHUNK = 3500
        if len(content) <= CHUNK:
            text = (
                f"<b>📄 Запись</b>\n"
                f"<code>{safe_html_format(d_wing)}/{safe_html_format(d_room)}</code>\n\n"
                f"{safe_html_format(content)}"
            )
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(
                    text="◀️ К списку",
                    callback_data="p_crp:" + str(state.get("tunnel_offset", 0)),
                ),
            )
            await cb.message.edit_text(
                text, parse_mode="HTML", reply_markup=kb.as_markup(),
            )
        else:
            chunk = content[:CHUNK]
            text = (
                f"<b>📄 Запись</b>\n"
                f"<code>{safe_html_format(d_wing)}/{safe_html_format(d_room)}</code>\n\n"
                f"{safe_html_format(chunk)}"
            )
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(
                    text="📖 Продолжить чтение", callback_data="p_cr:1",
                ),
            )
            kb.row(
                types.InlineKeyboardButton(
                    text="◀️ К списку",
                    callback_data="p_crp:" + str(state.get("tunnel_offset", 0)),
                ),
            )
            await cb.message.edit_text(
                text, parse_mode="HTML", reply_markup=kb.as_markup(),
            )
    except Exception as e:
        logger.error(f"Cross get drawer error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data == "p_crai")
@allowed_callback
async def cb_cross_ai_article(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    msg = await cb.message.answer("🤖 Составляю статью из записей...")
    state = _drawer_state.get(uid)
    if not state or "tunnel_drawers" not in state:
        return await msg.edit_text("❌ Сессия истекла.")
    drawers = state["tunnel_drawers"]
    try:
        all_contents = []
        for d in drawers:
            drawer_id = d.get("drawer_id") or d.get("id", "")
            if not drawer_id:
                continue
            mcp = get_mcp()
            raw = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": drawer_id})
            parsed = json.loads(raw)
            content = parsed.get("content", "") or parsed.get("text", "")
            wing = parsed.get("wing", d.get("_wing", "?"))
            room = parsed.get("room", d.get("_room", "?"))
            if content:
                all_contents.append(f"--- {wing}/{room} ---\n{content}")

        if not all_contents:
            return await msg.edit_text("❌ Не удалось получить содержимое записей.")

        joined = "\n\n".join(all_contents)
        from services.ai_engine import get_ai_response_async, get_current_ai

        engine, model = get_current_ai()
        ai_msgs = [
            {
                "role": "system",
                "content": "Ты — редактор. Составь связную статью на основе предоставленных фрагментов записей. Сохрани все ключевые идеи, даты, имена, термины. Не добавляй отсебятину. Верни ТОЛЬКО статью, без вступлений.",  # noqa: E501
            },
            {
                "role": "user",
                "content": f"Вот фрагменты из моих заметок. Составь из них единую статью:\n\n{joined}",  # noqa: E501
            },
        ]
        response = await get_ai_response_async(engine, model, ai_msgs)

        _article_cache[uid] = response
        from services.text_formatter import split_message

        parts = split_message(f"<b>📝 Статья</b>\n\n{safe_html_format(response)}")
        for part in parts[:-1]:
            await cb.message.answer(part, parse_mode="HTML")
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💾 Сохранить", callback_data="p_cras"))
        kb.row(
            types.InlineKeyboardButton(
                text="◀️ К списку",
                callback_data="p_crp:" + str(state.get("tunnel_offset", 0)),
            ),
        )
        await msg.edit_text(parts[-1], parse_mode="HTML", reply_markup=kb.as_markup())

    except Exception as e:
        logger.error(f"AI article error: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")


_article_cache: TtlDict = TtlDict()


@router.callback_query(F.data == "p_cras")
@allowed_callback
async def cb_save_article(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    text = _article_cache.get(uid)
    if not text:
        return await cb.message.edit_text("❌ Сессия истекла. Статья не найдена.")
    wing = "my_notes"
    room = "ai_articles"
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_add_drawer",
            {"wing": wing, "room": room, "content": text, "added_by": "telegram_bot"},
        )
        result = json.loads(raw)
        drawer_id = result.get("drawer_id", "") or result.get("id", "")
        _article_cache.pop(uid, None)
        await cb.message.edit_text(
            f"✅ <b>Статья сохранена!</b>\n\n"
            f"🏛 <code>{wing}/{room}</code>\n"
            + (f"🆔 {drawer_id}\n" if drawer_id else ""),
            parse_mode="HTML",
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка сохранения: {e}")


_connections_cache: TtlDict = TtlDict()


@router.callback_query(F.data.startswith("p_ct:"))
@allowed_callback
async def cb_record_connections(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _read_state.get(uid)
    if not data:
        return await cb.message.edit_text("❌ Сессия истекла.")
    d_wing = data.get("wing", "")
    d_room = data.get("room", "")
    if not d_wing or not d_room:
        return await cb.message.edit_text("❌ Нет данных о расположении записи.")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_follow_tunnels", {"wing": d_wing, "room": d_room},
        )
        tunnels = json.loads(raw) if raw else []
        if not tunnels:
            kb = InlineKeyboardBuilder()
            kb.row(types.InlineKeyboardButton(text="◀️ К записи", callback_data="p_bd"))
            return await cb.message.edit_text(
                f"🔗 Нет связей у <code>{safe_html_format(d_wing)}/{safe_html_format(d_room)}</code>.",  # noqa: E501
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )

        _connections_cache[uid] = {"tunnels": tunnels, "wing": d_wing, "room": d_room}
        lines = [
            f"<b>🔗 Связано с «{safe_html_format(d_wing)}/{safe_html_format(d_room)}»:</b>\n",
        ]
        for i, t in enumerate(tunnels):
            cw = t.get("connected_wing", "?")
            cr = t.get("connected_room", "?")
            label = t.get("label", "")
            line = f"  {i + 1}. 📖 {cw}/{cr}"
            if label:
                line += f"\n     🏷️ {safe_html_format(label)}"
            lines.append(line)

        kb = InlineKeyboardBuilder()
        for i, t in enumerate(tunnels):
            cw = t.get("connected_wing", "?")
            cr = t.get("connected_room", "?")
            kb.row(
                types.InlineKeyboardButton(
                    text=f"📖 {cw}/{safe_html_format(cr[:15])}",
                    callback_data=f"p_ctr:{uid}:{i}",
                ),
            )
        kb.row(types.InlineKeyboardButton(text="◀️ К записи", callback_data="p_bd"))
        await cb.message.edit_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as e:
        logger.error(f"Record connections error: {e}", exc_info=True)
        await cb.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data.startswith("p_ctr:"))
@allowed_callback
async def cb_connection_room(cb: types.CallbackQuery):
    await cb.answer()
    parts = cb.data.split(":")
    conn_uid = int(parts[1])
    idx = int(parts[2])
    data = _connections_cache.get(conn_uid)
    if not data or idx >= len(data["tunnels"]):
        return await cb.message.edit_text("❌ Сессия истекла.")
    t = data["tunnels"][idx]
    cw = t.get("connected_wing", "")
    cr = t.get("connected_room", "")
    if not cw or not cr:
        return await cb.message.edit_text("❌ Ошибка данных туннеля.")
    room_data = [(cr, 0)]
    _room_session[conn_uid] = {"wing": cw, "rooms": room_data}
    await _show_drawers_page(cb.message.edit_text, conn_uid, cw, cr, 0)


@router.callback_query(F.data == "p_tax")
@allowed_callback
async def cb_taxonomy(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🏛️ Загружаю таксономию...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_get_taxonomy")
        parsed = json.loads(raw)
        tax = parsed.get("taxonomy", {})
        lines = ["<b>🏛️ Полная таксономия дворца:</b>\n"]
        for idx, (wing, rooms) in enumerate(sorted(tax.items()), 1):
            display = wing.replace("_", " ").title()
            total = sum(rooms.values())
            lines.append(f"  {idx}. <b>{safe_html_format(display)}</b> — {total}")
        await msg.edit_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_grf")
@allowed_callback
async def cb_graph_stats(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("📊 Загружаю статистику графа...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_graph_stats")
        parsed = json.loads(raw)
        lines = ["<b>📊 Статистика графа дворца:</b>\n"]
        lines.append(f"  • Комнат всего: {parsed.get('total_rooms', 0)}")
        lines.append(f"  • Комнат с туннелями: {parsed.get('tunnel_rooms', 0)}")
        lines.append(f"  • Связей между комнатами: {parsed.get('total_edges', 0)}")
        await msg.edit_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_trv")
@allowed_callback
async def cb_traverse_menu(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_rooms")
        parsed = json.loads(raw)
        rooms = sorted(parsed.get("rooms", {}).items(), key=lambda x: -x[1])
        _room_cache[uid] = rooms

        kb = InlineKeyboardBuilder()
        for i, (room, count) in enumerate(rooms[:30]):
            short = room[:20] + "\u2026" if len(room) > 20 else room
            kb.row(
                types.InlineKeyboardButton(
                    text=f"{short} ({count})", callback_data=f"p_tr_{i}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_nav"),
        )
        await cb.message.edit_text(
            "🔀 **Выберите комнату для траверса (2 шага):**",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown",
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tr_"))
@allowed_callback
async def cb_traverse_select(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[5:])
    items = _room_cache.get(uid)
    if not items or idx >= len(items):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    room = items[idx][0]
    msg = await cb.message.answer(f"🔀 Траверс из «{room}»...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_traverse", {"start_room": room, "max_hops": 2},
        )
        await msg.edit_text(raw or "❌ Нет результатов.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


# ─── KNOWLEDGE GRAPH ───


@router.callback_query(F.data == "p_kg")
@allowed_callback
async def cb_kg_menu(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📊 Статистика KG", callback_data="p_kgst"))
    kb.row(types.InlineKeyboardButton(text="🔍 Поиск сущности", callback_data="p_kgq"))
    kb.row(types.InlineKeyboardButton(text="➕ Добавить факт", callback_data="p_kga"))
    kb.row(types.InlineKeyboardButton(text="📖 Помощь", callback_data="p_kg_help"))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="palace_back"))
    await cb.message.edit_text(
        "🧠 **Граф знаний (Knowledge Graph)**\nВыбери действие:",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "p_kg_help")
@allowed_callback
async def cb_kg_help(cb: types.CallbackQuery):
    await cb.answer()
    help_text = (
        "<b>📖 Граф знаний (Knowledge Graph) — справка</b>\n\n"
        "<b>Что это такое?</b>\n"
        "KG — это база структурированных фактов в формате <i>субъект → предикат → объект</i>.\n"
        "Пример: <code>Max → wrote → MemPalace</code>.\n\n"
        "<b>Типы предикатов (связей):</b>\n"
        "• <b>topic</b> 📌 — тема, к которой относится сущность\n"
        "• <b>related_to</b> 🔗 — общая связь/ассоциация\n"
        "• <b>wrote</b> ✍️ — авторство (книга, статья, код)\n"
        "• <b>contains_idea</b> 💡 — сущность содержит идею/мысль\n"
        "• <b>contains_quote</b> 💬 — сущность содержит цитату\n"
        "• <b>author</b> 👤 — авторство (кто создал)\n"
        "• <b>influenced_by</b> 🎯 — на что/кого повлияло\n\n"
        "<b>Как пользоваться:</b>\n"
        "1. <b>📊 Статистика</b> — обзор размера графа\n"
        "2. <b>🔍 Поиск сущности</b> — введи имя (Max, MyProject, Alice) — получишь все факты с пагинацией и кнопкой «🔍 Поискать в заметках»\n"  # noqa: E501
        "3. <b>➕ Добавить факт</b> — 3 шага: субъект → выбор предиката → объект\n\n"
        "<b>Источники фактов:</b>\n"
        "• Автоматически из заметок через <code>/enrich</code> (CLI) или кнопку «🧠 В граф» в личных заметках\n"  # noqa: E501
        "• Ручная вставка через меню\n\n"
        "<b>Совет:</b> после добавления фактов запусти <code>mempalace repair</code> для переиндексации."  # noqa: E501
    )
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_kg"))
    await cb.message.edit_text(
        help_text, reply_markup=kb.as_markup(), parse_mode="HTML",
    )


@router.callback_query(F.data == "p_kgst")
@allowed_callback
async def cb_kg_stats(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("📊 Загружаю статистику KG...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_kg_stats")
        parsed = json.loads(raw)
        lines = ["<b>🧠 Статистика графа знаний:</b>\n"]
        lines.append(f"  • Сущностей: {parsed.get('entities', 0)}")
        lines.append(f"  • Связей (triples): {parsed.get('triples', 0)}")
        lines.append(f"  • Актуальных фактов: {parsed.get('current_facts', 0)}")
        lines.append(f"  • Устаревших фактов: {parsed.get('expired_facts', 0)}")
        rtypes = parsed.get("relationship_types", [])
        if rtypes:
            lines.append(f"  • Типов связей: {', '.join(rtypes)}")
        await msg.edit_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_kga")
@allowed_callback
async def cb_kg_add_start(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _kg_add_state[uid] = {"subject": "", "predicate": "", "object": ""}
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✏️ Ввести текст", callback_data="p_kga_s"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_kga_x"))
    await cb.message.edit_text(
        "🧠 **Добавление факта в граф знаний**\n\n"
        "Шаг 1/3: Введите **субъект** (о ком или о чём факт):\n"
        "Или нажмите «✏️ Ввести текст» и напишите название.",
        parse_mode="Markdown",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_kga_x")
@allowed_callback
async def cb_kg_add_cancel(cb: types.CallbackQuery):
    await cb.answer()
    _kg_add_state.pop(cb.from_user.id, None)
    await cb.message.edit_text("❌ Отменено.")


@router.callback_query(F.data == "p_kga_s")
@allowed_callback
async def cb_kg_add_subject_prompt(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _pending_mcp_input[uid] = "kg_add_subject"
    await cb.message.edit_text(
        "✏️ Введите **субъект** (сущность, о которой факт):\n"
        "Например: `Юнг`, `тень`, `фотография`",
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "p_kga_p")
@allowed_callback
async def cb_kg_add_predicate_menu(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _kg_add_state.get(uid)
    if not state:
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    kb = InlineKeyboardBuilder()
    for pred, label in KG_PREDICATES:
        kb.row(types.InlineKeyboardButton(text=label, callback_data=f"p_kga_pr:{pred}"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_kga_x"))
    await cb.message.edit_text(
        f"🧠 Шаг 2/3: выберите **тип связи**\n\nСубъект: <b>{state['subject']}</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_kga_pr:"))
@allowed_callback
async def cb_kg_add_predicate_chosen(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    predicate = cb.data.split(":", 1)[1]
    state = _kg_add_state.get(uid)
    if not state:
        return
    state["predicate"] = predicate
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✏️ Ввести текст", callback_data="p_kga_o"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_kga_x"))
    await cb.message.edit_text(
        f"🧠 Шаг 3/3: Введите <b>объект</b>\n\n"
        f"<b>{state['subject']}</b> → <b>{predicate}</b> → ?\n\n"
        "Нажмите «✏️ Ввести текст» и напишите объект:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_kga_o")
@allowed_callback
async def cb_kg_add_object_prompt(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _pending_mcp_input[uid] = "kg_add_object"
    state = _kg_add_state.get(uid, {})
    await cb.message.edit_text(
        f"✏️ Введите <b>объект</b> (значение связи):\n\n"
        f"{state.get('subject', '?')} → {state.get('predicate', '?')} → ?\n\n"
        f"Например: психология, Красная книга, аналитическая психология",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("p_kga_c"))
@allowed_callback
async def cb_kg_add_confirm(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _kg_add_state.pop(uid, None)
    if not state:
        return
    subj = state["subject"]
    pred = state["predicate"]
    obj = state["object"]
    if not subj or not pred or not obj:
        await cb.message.edit_text("❌ Не все поля заполнены.")
        return
    msg = await cb.message.edit_text("⏳ Добавляю в граф знаний...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_kg_add", {"subject": subj, "predicate": pred, "object": obj},
        )
        parsed = json.loads(raw)
        if parsed.get("success"):
            await msg.edit_text(
                f"✅ Факт добавлен в граф знаний!\n\n"
                f"<b>{subj}</b> → <b>{pred}</b> → <b>{obj}</b>",
                parse_mode="HTML",
            )
        else:
            await msg.edit_text(f"❌ Ошибка: {parsed}")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_kgq")
@allowed_callback
async def cb_kg_query_prompt(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "kg_query"
    await cb.message.edit_text(
        "✏️ Введите имя сущности для поиска в графе знаний\n"
        "(например: `Max`, `MyProject`, `Alice`):",
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "p_kgc")
@allowed_callback
async def cb_kg_continue(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _kg_page_data.get(uid)
    if not data:
        await cb.message.edit_text("❌ Сессия поиска истекла. Начните заново.")
        return
    data["page"] += 1
    await _send_kg_page(uid, cb.message.edit_text)


@router.callback_query(F.data == "p_kgs")
@allowed_callback
async def cb_kg_restart(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _kg_page_data.get(uid)
    if not data:
        await cb.message.edit_text("❌ Сессия поиска истекла. Начните заново.")
        return
    data["page"] = 0
    await _send_kg_page(uid, cb.message.edit_text)


@router.callback_query(F.data == "p_kgr")
@allowed_callback
async def cb_kg_read(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _kg_page_data.get(uid)
    if not data:
        await cb.message.edit_text("❌ Сессия поиска истекла. Начните заново.")
        return
    entity = data["entity"]
    await _kg_search_and_show(uid, cb.message.edit_text, entity, cb.message)


@router.callback_query(F.data.startswith("p_kgrs:"))
@allowed_callback
async def cb_kg_read_search(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    entity = cb.data.split(":", 1)[1]
    await _kg_search_and_show(uid, cb.message.edit_text, entity, cb.message)


async def _kg_search_and_show(uid: int, edit_func, entity: str, original_msg):
    msg = await original_msg.answer(f"🔍 Ищу записи по теме «{entity}»...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_search", {"query": entity, "results": 5})
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if parsed and isinstance(parsed, dict):
            results = parsed.get("results", [])
            if not results:
                results = parsed.get("drawers", [])
        elif isinstance(parsed, list):
            results = parsed
        else:
            results = []

        if not results:
            await msg.edit_text(f"📭 Нет записей по теме «{entity}».")
            return

        _kg_search_data[uid] = {"entity": entity, "results": results}

        lines = [f"<b>📖 Записи по теме «{entity}»:</b>\n"]
        kb = InlineKeyboardBuilder()
        for i, r in enumerate(results[:5], 1):
            if isinstance(r, dict):
                title = (
                    r.get("title")
                    or r.get("name")
                    or r.get("source_file")
                    or r.get("filename", "?")
                )
                snippet = (
                    r.get("snippet") or r.get("text") or r.get("content", "")[:120]
                )
            else:
                title = str(r)[:50]
                snippet = ""
            lines.append(f"  {i}. <b>{safe_html_format(title)}</b>")
            if snippet:
                lines.append(f"     {safe_html_format(snippet[:120])}")
            kb.row(
                types.InlineKeyboardButton(
                    text=f"📖 {i}", callback_data=f"p_krd:{i - 1}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(text="◀️ Назад к фактам", callback_data="p_kgs"),
        )
        await msg.edit_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_krd:"))
@allowed_callback
async def cb_kg_read_result(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _kg_search_data.get(uid)
    if not data:
        await cb.message.edit_text("❌ Данные устарели. Начните заново.")
        return
    try:
        parts = cb.data.split(":", 2)
        idx = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
    except (IndexError, ValueError):
        return
    results = data["results"]
    if idx < 0 or idx >= len(results):
        return
    r = results[idx]
    title = (
        r.get("title")
        or r.get("name")
        or r.get("source_file")
        or r.get("filename", "?")
    )
    source = r.get("source_file", "")
    wing = r.get("wing", "")
    room = r.get("room", "")

    full_text = _get_full_text_from_chroma(source, wing, room)
    if not full_text:
        full_text = r.get("text") or r.get("content") or r.get("snippet", "")

    data["_last_title"] = title
    data["_last_source"] = source
    data["_last_wing"] = wing
    data["_last_room"] = room

    header = f"<b>{safe_html_format(title)}</b>"
    if wing and room:
        header += f"\n<code>{wing}/{room}/{source}</code>"
    elif source:
        header += f"\n<code>{source}</code>"

    PAGE_SIZE = 3500
    total_pages = max(1, (len(full_text) + PAGE_SIZE - 1) // PAGE_SIZE)
    if page >= total_pages:
        page = total_pages - 1

    start = page * PAGE_SIZE
    body = safe_html_format(full_text[start : start + PAGE_SIZE])

    kb = InlineKeyboardBuilder()
    nav = []
    if page > 0:
        nav.append(
            types.InlineKeyboardButton(
                text="◀️", callback_data=f"p_krd:{idx}:{page - 1}",
            ),
        )
    if page < total_pages - 1:
        nav.append(
            types.InlineKeyboardButton(
                text="▶️", callback_data=f"p_krd:{idx}:{page + 1}",
            ),
        )
    if nav:
        kb.row(*nav)
    kb.row(
        types.InlineKeyboardButton(
            text="◀️ Назад к списку", callback_data=f"p_krb:{data['entity']}",
        ),
    )

    page_info = f" — {page + 1}/{total_pages}" if total_pages > 1 else ""
    text_content = f"{header}{page_info}\n\n{body}"
    await cb.message.edit_text(
        text_content, parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_krb:"))
@allowed_callback
async def cb_kg_read_back(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    entity = cb.data.split(":", 1)[1]
    data = _kg_search_data.get(uid)
    if data and data["entity"] == entity:
        msg = cb.message
        await _kg_search_and_show(uid, cb.message.edit_text, entity, msg)
    else:
        await cb.message.edit_text("❌ Данные устарели. Начните заново.")


# ─── SAVE AI RESPONSE TO MEMPALACE ───


@router.callback_query(F.data == "p_sv")
@allowed_callback
async def cb_save_start(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    chat_id = cb.message.chat.id
    msg_id = cb.message.message_id
    text = _ai_msg_cache.get(chat_id, {}).get(msg_id, "")
    if not text:
        await cb.message.edit_text("❌ Текст ответа не найден в кэше.")
        return
    _save_state[uid] = {"text": text, "mode": "", "wing": "", "room": ""}
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📄 Сохранить всё", callback_data="p_sv_a"))
    kb.row(
        types.InlineKeyboardButton(text="💬 Вставить цитату", callback_data="p_sv_q"),
    )
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_sv_x"))
    await cb.message.answer(
        "📥 **Сохранить в MemPalace**\n\nКак сохранить ответ ИИ?",
        parse_mode="Markdown",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_sv_x")
@allowed_callback
async def cb_save_cancel(cb: types.CallbackQuery):
    await cb.answer()
    _save_state.pop(cb.from_user.id, None)
    await cb.message.edit_text("❌ Отменено.")


@router.callback_query(F.data == "p_sv_a")
@allowed_callback
async def cb_save_all(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _save_state.get(uid)
    if not state:
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    state["mode"] = "full"
    await _show_save_wings(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_sv_q")
@allowed_callback
async def cb_save_quote_prompt(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _pending_mcp_input[uid] = "save_quote"
    await cb.message.edit_text(
        "💬 Отправьте <b>цитату</b> (скопируйте нужный фрагмент из ответа ИИ):",
        parse_mode="HTML",
    )


async def _show_save_wings(edit_func, uid: int):
    state = _save_state.get(uid)
    if not state:
        await edit_func("❌ Сессия истекла.")
        return
    mcp = get_mcp()
    raw = await mcp.call_tool("mempalace_list_wings")
    parsed = json.loads(raw)
    wings = sorted(parsed.get("wings", {}).items(), key=lambda x: -x[1])
    state["wings"] = wings
    kb = InlineKeyboardBuilder()
    for i, (name, count) in enumerate(wings):
        short = name.replace("mempalace_", "").replace("_", " ").title()[:18]
        kb.row(
            types.InlineKeyboardButton(
                text=f"{short} ({count})", callback_data=f"p_sw_{i}",
            ),
        )
    kb.row(types.InlineKeyboardButton(text="➕ Новое крыло", callback_data="p_sv_nw"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_sv_x"))
    mode_label = "всё" if state["mode"] == "full" else "цитату"
    await edit_func(
        f"📥 **Шаг 2/3 — выберите крыло**\n\nСохранить: {mode_label}",
        parse_mode="Markdown",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_sw_"))
@allowed_callback
async def cb_save_wing_chosen(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _save_state.get(uid)
    if not state:
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    idx = int(cb.data[5:])
    wings = state.get("wings", [])
    if idx >= len(wings):
        return
    wing = wings[idx][0]
    state["wing"] = wing
    await _show_save_rooms(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_sv_nw")
@allowed_callback
async def cb_save_new_wing_prompt(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _pending_mcp_input[uid] = "save_new_wing"
    await cb.message.edit_text(
        "✏️ Введите <b>название нового крыла</b> (латиницей, например: <code>my_notes</code>):",
        parse_mode="HTML",
    )


async def _show_save_rooms(edit_func, uid: int):
    state = _save_state.get(uid)
    if not state:
        await edit_func("❌ Сессия истекла.")
        return
    wing = state["wing"]
    mcp = get_mcp()
    raw = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
    parsed = json.loads(raw)
    rooms = sorted(parsed.get("rooms", {}).items(), key=lambda x: -x[1])
    state["rooms"] = rooms
    kb = InlineKeyboardBuilder()
    for i, (room, count) in enumerate(rooms):
        short = room[:20] + ("\u2026" if len(room) > 20 else "")
        kb.row(
            types.InlineKeyboardButton(
                text=f"{short} ({count})", callback_data=f"p_sr_{i}",
            ),
        )
    kb.row(types.InlineKeyboardButton(text="➕ Новая комната", callback_data="p_sv_nr"))
    kb.row(
        types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_sv_bw"),
    )
    await edit_func(
        f"📥 <b>Шаг 3/3 — выберите комнату</b>\n\nКрыло: <b>{wing}</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_sv_bw")
@allowed_callback
async def cb_save_back_to_wings(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _save_state.get(uid)
    if state:
        state["wing"] = ""
        state["rooms"] = []
    await _show_save_wings(cb.message.edit_text, uid)


@router.callback_query(F.data.startswith("p_sr_"))
@allowed_callback
async def cb_save_room_chosen(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _save_state.get(uid)
    if not state:
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    idx = int(cb.data[5:])
    rooms = state.get("rooms", [])
    if idx >= len(rooms):
        return
    state["room"] = rooms[idx][0]
    await _save_confirm(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_sv_nr")
@allowed_callback
async def cb_save_new_room_prompt(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _pending_mcp_input[uid] = "save_new_room"
    await cb.message.edit_text(
        "✏️ Введите <b>название новой комнаты</b> (латиницей или кириллицей, пробелы заменятся на _):",  # noqa: E501
        parse_mode="HTML",
    )


async def _save_confirm(edit_func, uid: int):
    state = _save_state.get(uid)
    if not state:
        await edit_func("❌ Сессия истекла.")
        return
    text_preview = state["text"][:100] + ("\u2026" if len(state["text"]) > 100 else "")
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Сохранить", callback_data="p_sv_c"))
    kb.row(
        types.InlineKeyboardButton(
            text="\u25c0\ufe0f К выбору комнаты", callback_data="p_sv_br",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="\u25c0\ufe0f К выбору крыла", callback_data="p_sv_bw",
        ),
    )
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_sv_x"))
    await edit_func(
        f"📥 <b>Подтверждение:</b>\n\n"
        f"Крыло: <b>{state['wing']}</b>\n"
        f"Комната: <b>{state['room']}</b>\n"
        f"Режим: {state['mode']}\n\n"
        f"<code>{safe_html_format(text_preview)}</code>\n\n"
        f"Сохранить?",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_sv_br")
@allowed_callback
async def cb_save_back_to_rooms(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _save_state.get(uid)
    if state:
        state["room"] = ""
    await _show_save_rooms(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_sv_c")
@allowed_callback
async def cb_save_confirm_execute(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _save_state.pop(uid, None)
    if not state:
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    msg = await cb.message.edit_text("⏳ Сохраняю...")
    try:
        wing = state["wing"]
        room = state.get("room") or "general"
        text = state["text"]
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_add_drawer",
            {"wing": wing, "room": room, "content": text, "added_by": "telegram_bot"},
        )
        result = json.loads(raw)
        drawer_id = result.get("drawer_id", "") or result.get("id", "")

        await msg.edit_text(
            f"✅ <b>Сохранено!</b>\n\n"
            f"🏛 <code>{wing}/{room}</code>\n"
            + (f"🆔 {drawer_id}\n" if drawer_id else "")
            + "➕ Добавить этот факт в граф знаний?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardBuilder()
            .row(types.InlineKeyboardButton(text="🧠 В граф", callback_data="p_kga"))
            .as_markup(),
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка сохранения: {e}")


# ─── TUNNELS ───


@router.callback_query(F.data == "p_tun")
@allowed_callback
async def cb_tunnel_menu(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📋 Список туннелей", callback_data="p_tl"))
    kb.row(
        types.InlineKeyboardButton(text="🤖 Анализ туннелей", callback_data="p_tun_ai"),
    )
    kb.row(types.InlineKeyboardButton(text="🔍 Между крыльями", callback_data="p_tf"))
    kb.row(types.InlineKeyboardButton(text="➡️ Пройти туннель", callback_data="p_to"))
    kb.row(types.InlineKeyboardButton(text="➕ Создать туннель", callback_data="p_tc"))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_nav"))
    await cb.message.edit_text(
        "🔄 **Туннели между комнатами**",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "p_tl")
@allowed_callback
async def cb_list_tunnels(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    msg = await cb.message.answer("📋 Загружаю список туннелей...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_tunnels")
        parsed = json.loads(raw)
        tunnels = parsed if isinstance(parsed, list) else parsed.get("tunnels", [])
        if not tunnels:
            kb = InlineKeyboardBuilder()
            kb.row(
                types.InlineKeyboardButton(
                    text="➕ Создать туннель", callback_data="p_tc",
                ),
            )
            kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tun"))
            return await msg.edit_text(
                "📋 Нет явных туннелей между комнатами.", reply_markup=kb.as_markup(),
            )

        _tunnels_cache[uid] = tunnels
        lines = ["<b>🔄 Явные туннели:</b>\n"]
        for i, t in enumerate(tunnels, 1):
            src = t.get("source", {})
            tgt = t.get("target", {})
            sw = src.get("wing", "?")
            sr = src.get("room", "?")
            tw = tgt.get("wing", "?")
            tr = tgt.get("room", "?")
            label = t.get("label", "")
            lines.append(f"{i}. {sw}/{sr} ⟷ {tw}/{tr}")
            if label:
                lines.append(f"   🏷️ {safe_html_format(label)}")

        kb = InlineKeyboardBuilder()
        for i, t in enumerate(tunnels):
            src = t.get("source", {})
            tgt = t.get("target", {})
            sw = src.get("wing", "?")
            sr = src.get("room", "?")
            tw = tgt.get("wing", "?")
            tr = tgt.get("room", "?")
            short = f"{sw}/{sr[:8]}… ⟷ {tw}/{tr[:8]}…"
            kb.row(
                types.InlineKeyboardButton(
                    text=f"🔗 {short}", callback_data=f"p_td:{i}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(
                text="🤖 Анализ туннелей", callback_data="p_tun_ai",
            ),
        )
        kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tun"))
        await msg.edit_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_td:"))
@allowed_callback
async def cb_tunnel_detail(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data.split(":", 1)[1])
    tunnels = _tunnels_cache.get(uid)
    if not tunnels or idx >= len(tunnels):
        return await cb.message.edit_text("❌ Сессия истекла.")
    t = tunnels[idx]
    src, tgt = t.get("source", {}), t.get("target", {})
    sw, sr = src.get("wing", "?"), src.get("room", "?")
    tw, tr = tgt.get("wing", "?"), tgt.get("room", "?")
    label = t.get("label", "")
    created = t.get("created_at", "")[:10]
    lines = [
        f"<b>🔗 {safe_html_format(label) if label else 'Туннель'}</b>\n",
        f"{safe_html_format(sw)}/{safe_html_format(sr)}",
        "  ⟷",
        f"{safe_html_format(tw)}/{safe_html_format(tr)}",
    ]
    if created:
        lines.append(f"\n🕐 {created}")
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text=f"📖 {sw}/{safe_html_format(sr[:15])}", callback_data=f"p_tdr:{idx}:s",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text=f"📖 {tw}/{safe_html_format(tr[:15])}", callback_data=f"p_tdr:{idx}:t",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="📡 Читать из обеих", callback_data=f"p_tdrb:{idx}",
        ),
    )
    kb.row(types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"p_tdd:{idx}"))
    kb.row(types.InlineKeyboardButton(text="◀️ К списку", callback_data="p_tl"))
    await cb.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_tdr:"))
@allowed_callback
async def cb_tunnel_read_side(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    parts = cb.data.split(":")
    idx = int(parts[1])
    side = parts[2]
    tunnels = _tunnels_cache.get(uid)
    if not tunnels or idx >= len(tunnels):
        return await cb.message.edit_text("❌ Сессия истекла.")
    t = tunnels[idx]
    if side == "s":
        wing = t["source"]["wing"]
        room = t["source"]["room"]
    else:
        wing = t["target"]["wing"]
        room = t["target"]["room"]
    room_data = [(room, 0)]
    _room_session[uid] = {"wing": wing, "rooms": room_data}
    await _show_drawers_page(cb.message.edit_text, uid, wing, room, 0)


@router.callback_query(F.data.startswith("p_tdrb:"))
@allowed_callback
async def cb_tunnel_read_both(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data.split(":", 1)[1])
    tunnels = _tunnels_cache.get(uid)
    if not tunnels or idx >= len(tunnels):
        return await cb.message.edit_text("❌ Сессия истекла.")
    t = tunnels[idx]
    rooms = [
        (t["source"]["wing"], t["source"]["room"]),
        (t["target"]["wing"], t["target"]["room"]),
    ]
    _drawer_state[uid] = {"tunnel_rooms": rooms}
    await _show_cross_rooms(cb.message.edit_text, uid, rooms, 0, back_cb="p_tl")


@router.callback_query(F.data.startswith("p_tdd:"))
@allowed_callback
async def cb_tunnel_delete(cb: types.CallbackQuery):
    await cb.answer()
    idx = int(cb.data.split(":", 1)[1])
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"p_tddc:{idx}"),
    )
    kb.row(types.InlineKeyboardButton(text="❌ Нет", callback_data="p_tl"))
    await cb.message.edit_text("🗑️ Удалить этот туннель?", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("p_tddc:"))
@allowed_callback
async def cb_tunnel_delete_confirm(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data.split(":", 1)[1])
    tunnels = _tunnels_cache.get(uid)
    if not tunnels or idx >= len(tunnels):
        return await cb.message.edit_text("❌ Сессия истекла.")
    tunnel_id = tunnels[idx].get("id", "")
    try:
        mcp = get_mcp()
        await mcp.call_tool("mempalace_delete_tunnel", {"tunnel_id": tunnel_id})
        _tunnels_cache.pop(uid, None)
        await cb.message.edit_text("✅ Туннель удалён.")
        await asyncio.sleep(0.5)
        await cb_list_tunnels(cb)
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка удаления: {e}")


async def _show_cross_rooms(
    edit_func, uid: int, rooms: list, offset: int, back_cb: str = "p_tl",
):
    """Show entries from multiple (wing, room) pairs, paginated, with Получить запись buttons and AI article."""  # noqa: E501
    try:
        mcp = get_mcp()
        all_drawers = []
        per_room = 10
        for wing, room in rooms:
            raw = await mcp.call_tool(
                "mempalace_list_drawers",
                {"wing": wing, "room": room, "limit": per_room, "offset": 0},
            )
            parsed = json.loads(raw)
            for d in parsed.get("drawers", []):
                d["_wing"] = wing
                d["_room"] = room
            all_drawers.extend(parsed.get("drawers", []))

        if not all_drawers:
            kb = InlineKeyboardBuilder()
            kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb))
            return await edit_func(
                "📭 Нет записей в этих комнатах.", reply_markup=kb.as_markup(),
            )

        _drawer_state[uid] = {
            "tunnel_rooms": rooms,
            "tunnel_drawers": all_drawers,
            "tunnel_offset": offset,
            "tunnel_back": back_cb,
        }

        CHUNK = 5
        total = len(all_drawers)
        page_drawers = all_drawers[offset : offset + CHUNK]
        room_labels = ", ".join(f"{w}/{r}" for w, r in rooms)
        lines = [f"<b>📡 Читаем:</b> {safe_html_format(room_labels)}\n"]
        for i, d in enumerate(page_drawers):
            preview = d.get("content_preview", "") or d.get("content", "")[:80]
            safe_p = safe_html_format(preview[:80])
            tag = f"📌 {d['_wing']}/{d['_room']}"
            lines.append(f"{offset + i + 1}. {tag}")
            lines.append(f"   <code>{safe_p}</code>")

        kb = InlineKeyboardBuilder()
        for i, d in enumerate(page_drawers):
            kb.row(
                types.InlineKeyboardButton(
                    text=f"📄 Получить запись {offset + i + 1}",
                    callback_data=f"p_crg:{offset + i}",
                ),
            )
        nav_row = []
        if offset > 0:
            nav_row.append(
                types.InlineKeyboardButton(
                    text="◀️", callback_data=f"p_crp:{max(0, offset - CHUNK)}",
                ),
            )
        if offset + CHUNK < total:
            nav_row.append(
                types.InlineKeyboardButton(
                    text="▶️", callback_data=f"p_crp:{offset + CHUNK}",
                ),
            )
        if nav_row:
            kb.row(*nav_row)
        kb.row(
            types.InlineKeyboardButton(
                text="🤖 Статья на основе этих записей", callback_data="p_crai",
            ),
        )
        kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb))
        await edit_func(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as e:
        logger.error(f"Cross-room read error: {e}", exc_info=True)
        await edit_func(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data == "p_tun_ai")
@allowed_callback
async def cb_tunnel_analysis(cb: types.CallbackQuery):
    await cb.answer()
    msg = await cb.message.answer("🤖 Анализирую туннели...")
    try:
        mcp = get_mcp()
        raw_stats = await mcp.call_tool("mempalace_graph_stats")
        stats = json.loads(raw_stats)
        raw_tunnels = await mcp.call_tool("mempalace_list_tunnels")
        tunnels = json.loads(raw_tunnels)
        if isinstance(tunnels, dict):
            tunnels = tunnels.get("tunnels", [])

        tunnel_lines = []
        for t in tunnels:
            src = t.get("source", {})
            tgt = t.get("target", {})
            label = t.get("label", "")
            line = f"{src.get('wing', '')}/{src.get('room', '')} ⟷ {tgt.get('wing', '')}/{tgt.get('room', '')}"  # noqa: E501
            if label:
                line += f" ({label})"
            tunnel_lines.append(line)

        prompt = (
            f"Проанализируй эти туннели между комнатами моих заметок.\n\n"
            f"Статистика графа: всего комнат {stats.get('total_rooms', '?')}, "
            f"комнат с туннелями {stats.get('tunnel_rooms', '?')}, "
            f"связей {stats.get('total_edges', '?')}.\n\n"
            f"Туннели:\n" + "\n".join(tunnel_lines) + "\n\n"
            "Напиши анализ 3-5 предложений: какие темы пересекаются, "
            "какие связи самые сильные, какие неожиданные. "
            "Если упоминаешь комнату — пиши как wing/room."
        )

        from services.ai_engine import get_ai_response_async, get_current_ai

        engine, model = get_current_ai()
        ai_msgs = [
            {
                "role": "system",
                "content": "Ты — аналитик знаний. Отвечай кратко и содержательно.",
            },
            {"role": "user", "content": prompt},
        ]
        response = await get_ai_response_async(engine, model, ai_msgs)
        await msg.edit_text(
            f"🧠 <b>Анализ туннелей</b>\n\n{safe_html_format(response)}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Tunnel analysis error: {e}", exc_info=True)
        await msg.edit_text(f"❌ Ошибка анализа: {str(e)[:200]}")
    await cb.answer()
    uid = cb.from_user.id
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = sorted(parsed.get("wings", {}).items(), key=lambda x: -x[1])
        _wing_cache[uid] = wings
        _tunnel_state[uid] = {"step": "wing_a"}

        kb = InlineKeyboardBuilder()
        for i, (name, count) in enumerate(wings):
            display = name.replace("mempalace_", "").replace("_", " ").title()
            short = display[:20] + "\u2026" if len(display) > 20 else display
            kb.row(
                types.InlineKeyboardButton(
                    text=f"{short} ({count})", callback_data=f"p_tfa_{i}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_tun"),
        )
        await cb.message.edit_text(
            "🔍 **Выберите ПЕРВОЕ крыло:**",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown",
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tfa_"))
@allowed_callback
async def cb_find_tunnels_wing_b(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[6:])
    items = _wing_cache.get(uid)
    if not items or idx >= len(items):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    wing_a = items[idx][0]
    _tunnel_state[uid] = {"step": "wing_b", "wing_a": wing_a}

    kb = InlineKeyboardBuilder()
    for i, (name, count) in enumerate(items):
        if name == wing_a:
            continue
        display = name.replace("mempalace_", "").replace("_", " ").title()
        short = display[:20] + "\u2026" if len(display) > 20 else display
        kb.row(
            types.InlineKeyboardButton(
                text=f"{short} ({count})", callback_data=f"p_tfb_{i}",
            ),
        )
    kb.row(types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_tf"))
    await cb.message.edit_text(
        f"🔍 <b>Выберите ВТОРОЕ крыло</b> (первое: {safe_html_format(items[idx][0])}):",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("p_tfb_"))
@allowed_callback
async def cb_find_tunnels_result(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[6:])
    items = _wing_cache.get(uid)
    state = _tunnel_state.get(uid)
    if not items or not state or idx >= len(items):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    wing_b = items[idx][0]
    wing_a = state["wing_a"]
    msg = await cb.message.answer("🔍 Ищу туннели...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_find_tunnels", {"wing_a": wing_a, "wing_b": wing_b},
        )
        tunnels = json.loads(raw) if raw else []
        if not tunnels:
            await msg.edit_text(
                "🔍 Туннелей между этими крыльями не найдено.", parse_mode="HTML",
            )
        else:
            lines = [f"<b>🔄 Найдено туннелей: {len(tunnels)}</b>\n"]
            for t in tunnels:
                lines.append(
                    f"  • <b>{safe_html_format(t.get('room', '?'))}</b> — "
                    f"{', '.join(safe_html_format(w) for w in t.get('wings', []))} "
                    f"({t.get('count', 0)} записей)",
                )
            await msg.edit_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_to")
@allowed_callback
async def cb_follow_tunnels_wing(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = sorted(parsed.get("wings", {}).items(), key=lambda x: -x[1])
        _wing_cache[uid] = wings

        kb = InlineKeyboardBuilder()
        for i, (name, count) in enumerate(wings):
            display = name.replace("mempalace_", "").replace("_", " ").title()
            short = display[:20] + "\u2026" if len(display) > 20 else display
            kb.row(
                types.InlineKeyboardButton(
                    text=f"{short} ({count})", callback_data=f"p_tow_{i}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_tun"),
        )
        await cb.message.edit_text(
            "➡️ **Выберите крыло для прохода туннеля:**",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown",
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tow_"))
@allowed_callback
async def cb_follow_tunnels_room(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[6:])
    items = _wing_cache.get(uid)
    if not items or idx >= len(items):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    wing = items[idx][0]
    _tunnel_state[uid] = {"step": "room", "wing": wing}

    msg = await cb.message.answer(f"⏳ Загружаю комнаты крыла «{wing}»...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
        parsed = json.loads(raw)
        rooms = sorted(parsed.get("rooms", {}).items(), key=lambda x: -x[1])
        _room_cache[uid] = rooms

        kb = InlineKeyboardBuilder()
        for i, (room, count) in enumerate(rooms):
            short = room[:20] + "\u2026" if len(room) > 20 else room
            kb.row(
                types.InlineKeyboardButton(
                    text=f"{short} ({count})", callback_data=f"p_tor_{i}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_to"),
        )
        await msg.edit_text(
            f"➡️ Выбрано крыло: {safe_html_format(wing)}\n<b>Выберите комнату:</b>",
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tor_"))
@allowed_callback
async def cb_follow_tunnels_result(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[6:])
    rooms = _room_cache.get(uid)
    state = _tunnel_state.get(uid)
    if not rooms or not state or idx >= len(rooms):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    wing = state["wing"]
    room = rooms[idx][0]
    msg = await cb.message.answer(f"➡️ Проход туннеля из «{wing}/{room}»...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_follow_tunnels", {"wing": wing, "room": room},
        )
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                lines = [f"<b>➡️ Туннели из {wing}/{room}:</b>\n"]
                for t in data:
                    cw = t.get("connected_wing", "?")
                    cr = t.get("connected_room", "?")
                    label = t.get("label", "")
                    direction = t.get("direction", "")
                    arrow = "←" if direction == "incoming" else "→"
                    line = f"  {arrow} <b>{cw}/{cr}</b>"
                    if label:
                        line += f" — {label}"
                    lines.append(line)
                await msg.edit_text("\n".join(lines), parse_mode="HTML")
            else:
                await msg.edit_text(raw[:2000])
        except (json.JSONDecodeError, TypeError):
            await msg.edit_text(raw[:2000] or "❌ Нет результатов.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


# ─── CREATE TUNNEL ───


async def _show_wing_buttons_for_tunnel(
    edit_func, uid, header, callback_prefix, back_data, exclude_wing=None,
):
    mcp = get_mcp()
    raw = await mcp.call_tool("mempalace_list_wings")
    parsed = json.loads(raw)
    wings = sorted(parsed.get("wings", {}).items(), key=lambda x: -x[1])
    _wing_cache[uid] = wings
    kb = InlineKeyboardBuilder()
    for i, (name, count) in enumerate(wings):
        if exclude_wing and name == exclude_wing:
            continue
        display = name.replace("mempalace_", "").replace("_", " ").title()
        short = display[:18] + "\u2026" if len(display) > 18 else display
        kb.row(
            types.InlineKeyboardButton(
                text=f"{short} ({count})", callback_data=f"{callback_prefix}{i}",
            ),
        )
    kb.row(
        types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data=back_data),
    )
    await edit_func(header, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "p_tc")
@allowed_callback
async def cb_create_tunnel_source_wing(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _create_tunnel_state[uid] = {}
    try:
        await _show_wing_buttons_for_tunnel(
            cb.message.edit_text,
            uid,
            "🏗️ <b>Создание туннеля — шаг 1/4</b>\nВыберите <b>исходное</b> крыло:",
            "p_tcs_",
            "p_tun",
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tcs_"))
@allowed_callback
async def cb_create_tunnel_source_room(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[6:])
    items = _wing_cache.get(uid)
    if not items or idx >= len(items):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    source_wing = items[idx][0]
    _create_tunnel_state[uid] = {"source_wing": source_wing}

    msg = await cb.message.answer(f"⏳ Загружаю комнаты «{source_wing}»...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_rooms", {"wing": source_wing})
        parsed = json.loads(raw)
        rooms = sorted(parsed.get("rooms", {}).items(), key=lambda x: -x[1])
        _room_cache[uid] = rooms
        kb = InlineKeyboardBuilder()
        for i, (room, count) in enumerate(rooms):
            short = room[:18] + "\u2026" if len(room) > 18 else room
            kb.row(
                types.InlineKeyboardButton(
                    text=f"{short} ({count})", callback_data=f"p_tcsr_{i}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_tc"),
        )
        await msg.edit_text(
            f"🏗️ <b>Шаг 2/4</b> — крыло: {safe_html_format(source_wing)}\nВыберите <b>исходную</b> комнату:",  # noqa: E501
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tcsr_"))
@allowed_callback
async def cb_create_tunnel_target_wing(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[7:])
    rooms = _room_cache.get(uid)
    state = _create_tunnel_state.get(uid)
    if not rooms or not state or idx >= len(rooms):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    state["source_room"] = rooms[idx][0]

    try:
        await _show_wing_buttons_for_tunnel(
            cb.message.edit_text,
            uid,
            f"🏗️ <b>Шаг 3/4</b> — исходная: {safe_html_format(state['source_wing'])}/{safe_html_format(state['source_room'])}\nВыберите <b>целевое</b> крыло:",  # noqa: E501
            "p_tctw_",
            "p_tc",
            exclude_wing=state["source_wing"],
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tctw_"))
@allowed_callback
async def cb_create_tunnel_target_room(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    idx = int(cb.data[7:])
    items = _wing_cache.get(uid)
    state = _create_tunnel_state.get(uid)
    if not items or not state or idx >= len(items):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    target_wing = items[idx][0]
    state["target_wing"] = target_wing

    msg = await cb.message.answer(f"⏳ Загружаю комнаты «{target_wing}»...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_rooms", {"wing": target_wing})
        parsed = json.loads(raw)
        rooms = sorted(parsed.get("rooms", {}).items(), key=lambda x: -x[1])
        _room_cache[uid] = rooms
        kb = InlineKeyboardBuilder()
        for i, (room, count) in enumerate(rooms):
            short = room[:18] + "\u2026" if len(room) > 18 else room
            kb.row(
                types.InlineKeyboardButton(
                    text=f"{short} ({count})", callback_data=f"p_tctr_{i}",
                ),
            )
        kb.row(
            types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_tc"),
        )
        await msg.edit_text(
            f"🏗️ <b>Шаг 4/4</b> — крыло: {safe_html_format(target_wing)}\nВыберите <b>целевую</b> комнату:",  # noqa: E501
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


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
    await cb.message.edit_text(
        f"🏗️ <b>Почти готово!</b>\n\n"
        f"Исходная: {safe_html_format(state['source_wing'])}/{safe_html_format(state['source_room'])}\n"  # noqa: E501
        f"Целевая:  {safe_html_format(state['target_wing'])}/{safe_html_format(state['target_room'])}\n\n"  # noqa: E501
        f"✏️ Введите описание связи (или «-» чтобы пропустить):",
        parse_mode="HTML",
    )


async def process_mcp_text_input(uid: int, text: str, answer_func):
    action = _pending_mcp_input.pop(uid, None)
    if not action:
        return False

    msg = await answer_func("⏳ Обрабатываю...")
    try:
        mcp = get_mcp()
        if action == "list_rooms":
            raw = text.strip()
            if raw == "*":
                wing = None
            else:
                wing = _normalize_query(raw)
            args = {"wing": wing} if wing else {}
            raw = await mcp.call_tool("mempalace_list_rooms", args)
            parsed = json.loads(raw)
            rooms = parsed.get("rooms", {})
            wing_name = parsed.get("wing", wing or "все")
            lines = [f"<b>🪪 Комнаты крыла «{wing_name}»:</b>\n"]
            for idx, (room, count) in enumerate(sorted(rooms.items()), 1):
                lines.append(f"  {idx}. <b>{room}</b> — {count}")
            await msg.edit_text("\n".join(lines), parse_mode="HTML")

        elif action == "traverse":
            parts = _normalize_query(text.strip()).split()
            room = parts[0]
            hops = int(parts[1]) if len(parts) > 1 else 2
            raw = await mcp.call_tool(
                "mempalace_traverse", {"start_room": room, "max_hops": hops},
            )
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
            # создаём новое крыло
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "mempalace",
                    "init",
                    wing,
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
            # переходим к выбору предиката
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
                # подтверждение
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
                        text="🔍 Поискать в заметках", callback_data=f"p_kgrs:{entity}",
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
            tunnels = json.loads(raw) if raw else []
            if not tunnels:
                await msg.edit_text(
                    "🔍 Туннелей между этими крыльями не найдено.\n\n"
                    "Туннель возникает, когда одна и та же комната (тема) "
                    "встречается в <b>разных</b> крыльях.\n"
                    "Пример: тема «интегралы» есть и в крыле «math», и в «physics» → туннель.\n\n"
                    "У вас сейчас одно крыло — <b>my_notes</b>.\n"
                    "Чтобы увидеть туннели, добавьте ещё одно крыло через майнинг.\n\n"
                    "Попробуйте: 🔀 <b>Траверс</b> — связи между комнатами внутри крыла.",
                    parse_mode="HTML",
                )
            else:
                lines = [f"<b>🔄 Найдено туннелей: {len(tunnels)}</b>\n"]
                for t in tunnels:
                    lines.append(
                        f"  • <b>{safe_html_format(t.get('room', '?'))}</b> — "
                        f"{', '.join(t.get('wings', []))} "
                        f"({t.get('count', 0)} записей)",
                    )
                await msg.edit_text("\n".join(lines), parse_mode="HTML")

        elif action == "follow_tunnels":
            parts = text.strip().split(maxsplit=1)
            if len(parts) < 2:
                await msg.edit_text(
                    "❌ Укажите крыло и комнату, например: `мои заметки сны`",
                )
                return True
            wing = _normalize_query(parts[0])
            room = _normalize_query(parts[1])
            raw = await mcp.call_tool(
                "mempalace_follow_tunnels", {"wing": wing, "room": room},
            )
            await msg.edit_text(raw or "❌ Нет результатов.")

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
                await msg.edit_text(
                    f"✅ <b>Туннель создан!</b>\n\n"
                    f"• {safe_html_format(state['source_wing'])}/{safe_html_format(state['source_room'])}\n"  # noqa: E501
                    f"  ⟷ {safe_html_format(state['target_wing'])}/{safe_html_format(state['target_room'])}\n"  # noqa: E501
                    + (f"• Описание: {label}\n" if label else "")
                    + (f"• ID: {tunnel_id}" if tunnel_id else ""),
                    parse_mode="HTML",
                )
            except (json.JSONDecodeError, TypeError):
                await msg.edit_text(raw or "✅ Туннель создан!")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")
    return True


# ─── TUNNEL HINTS ───

_hint_data: TtlDict = TtlDict()


async def suggest_tunnel_hint(message, query: str):
    if len(query) < 3:
        return
    try:
        mcp = get_mcp()
        rooms_raw = await mcp.call_tool("mempalace_list_rooms")
        rooms_data = json.loads(rooms_raw)
        all_rooms = rooms_data.get("rooms", {})

        from services.wing_classifier import classify_wing

        query_wing = classify_wing(query)

        query_lower = query.lower()
        best_room = None
        best_wing = query_wing or ""
        for room in sorted(all_rooms, key=lambda r: len(r), reverse=True):
            if query_lower in room.lower() or room.lower() in query_lower:
                best_room = room
                break

        if not best_room:
            return

        traverse_raw = await mcp.call_tool(
            "mempalace_traverse", {"start_room": best_room, "max_hops": 1},
        )
        traverse = json.loads(traverse_raw) if traverse_raw else []
        if not traverse:
            return

        uid = message.from_user.id
        _hint_data[uid] = {"room": best_room, "traverse": traverse, "wing": best_wing}
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="🔀 Показать связи", callback_data="p_hnt"),
        )
        kb.row(types.InlineKeyboardButton(text="➕ В граф", callback_data="p_kga"))
        await message.answer(
            f"🔗 <b>Найдена связь в MemPalace:</b> <code>{best_room}</code>",
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data == "p_hnt")
@allowed_callback
async def cb_hint_show(cb: types.CallbackQuery):
    uid = cb.from_user.id
    data = _hint_data.get(uid)
    if not data:
        await cb.answer("❌ Данные устарели", show_alert=True)
        return
    await cb.answer()
    room = data["room"]
    traverse = data["traverse"]
    lines = [f"<b>🔀 Связи для «{room}»:</b>\n"]
    for item in traverse[:10]:
        if isinstance(item, dict):
            cw = item.get("connected_wing") or item.get("wing", "?")
            cr = item.get("connected_room") or item.get("room", "?")
            label = item.get("label", "")
            line = f"  • <b>{cw}/{cr}</b>"
            if label:
                line += f" — {label}"
            lines.append(line)
        else:
            lines.append(f"  • {item}")
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📖 Читать записи", callback_data="p_hnt_r"))
    kb.row(
        types.InlineKeyboardButton(text="\u25c0\ufe0f Скрыть", callback_data="p_hnt_d"),
    )
    await cb.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_hnt_r")
@allowed_callback
async def cb_hint_read(cb: types.CallbackQuery):
    uid = cb.from_user.id
    data = _hint_data.get(uid)
    if not data:
        await cb.answer("❌ Данные устарели", show_alert=True)
        return
    await cb.answer()
    room = data["room"]
    msg = await cb.message.answer(f"🔍 Ищу записи по теме «{room}»...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_search", {"query": room, "results": 5})
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if parsed and isinstance(parsed, dict):
            results = parsed.get("results", [])
            if not results:
                results = parsed.get("drawers", [])
        elif isinstance(parsed, list):
            results = parsed
        else:
            results = []

        if not results:
            await msg.edit_text(f"📭 Нет записей по теме «{room}».")
            return

        lines = [f"<b>📖 Записи по теме «{room}»:</b>\n"]
        for i, r in enumerate(results[:5], 1):
            if isinstance(r, dict):
                title = r.get("title") or r.get("name") or r.get("filename", "?")
                snippet = r.get("snippet") or r.get("content", "")[:100]
            else:
                title = str(r)[:50]
                snippet = ""
            lines.append(f"  {i}. <b>{safe_html_format(title)}</b>")
            if snippet:
                lines.append(f"     {safe_html_format(snippet[:100])}")
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="p_hnt"),
        )
        await msg.edit_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_hnt_d")
@allowed_callback
async def cb_hint_dismiss(cb: types.CallbackQuery):
    await cb.answer()
    try:
        await cb.message.delete()
    except Exception:
        await cb.message.edit_text("✅")


def _get_full_text_from_chroma(source: str, wing: str = "", room: str = "") -> str:
    if not source:
        return ""
    db_path = os.path.expanduser("~/.mempalace/palace/chroma.sqlite3")
    if not os.path.exists(db_path):
        return ""
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        basename = os.path.basename(source.replace("\\", "/"))
        filename_like = f"%{basename}" if basename else f"%{source}"
        rows = cur.execute(
            """
            SELECT string_value FROM embedding_metadata
            WHERE key = 'source_file' AND string_value LIKE ?
            LIMIT 1
        """,
            (filename_like,),
        ).fetchall()
        if not rows:
            con.close()
            return ""
        source_file = rows[0][0]
        drawers = cur.execute(
            """
            SELECT e.id, emd.string_value as doc_text
            FROM embeddings e
            JOIN embedding_metadata emd ON emd.id = e.id AND emd.key = 'chroma:document'
            JOIN embedding_metadata sf ON sf.id = e.id AND sf.key = 'source_file'
            WHERE sf.string_value = ? AND e.embedding_id LIKE 'drawer_%'
            ORDER BY e.id ASC
        """,
            (source_file,),
        ).fetchall()
        parts = []
        seen = set()
        for _, doc_text in drawers:
            block = doc_text.strip()
            if block and block not in seen:
                seen.add(block)
                parts.append(block)
        con.close()
        return "\n\n".join(parts)
    except Exception:
        return ""
