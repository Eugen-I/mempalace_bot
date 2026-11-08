"""handlers/palace/navigation.py — Wings, rooms, drawers, taxonomy, graph, traverse"""
import base64
import binascii
import json
import logging
import os
import secrets

from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback
from services.ai_engine import AITimeoutError, call_ai_async, get_current_ai
from services.palace_mcp import get_mcp
from services.summary_service import SummaryMode, generate_summary
from services.text_formatter import safe_html_format
from services.ttl_dict import TtlDict
from services.ui_cache import UICallbackCache

from ._utils import safe_edit_text
from .shared import (
    _create_tunnel_state,
    _pending_mcp_input,
    _read_state,
    _room_session,
    _user_context,
    _wing_cache,
    router,
)

PAGE_SIZE = 5

logger = logging.getLogger(__name__)

_drawer_list_state: TtlDict = TtlDict()
_active_drawer: TtlDict = TtlDict()
_room_callback_map: UICallbackCache = UICallbackCache(namespace="palace_rooms")
_wing_callback_map: UICallbackCache = UICallbackCache(namespace="palace_wings")


def _encode_callback_part(value: str) -> str:
    if not value:
        return ""
    payload = json.dumps({"v": value}, ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_callback_part(value: str) -> str:
    if not value:
        return ""
    try:
        payload = base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, binascii.Error):
        return value
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return value
    if isinstance(decoded, dict) and "v" in decoded and isinstance(decoded["v"], str):
        return decoded["v"]
    return value


def _build_room_callback_data(wing: str, room: str) -> str:
    key = secrets.token_hex(4)
    _room_callback_map[key] = (wing, room)
    return f"p_rd_room:{key}"


def _build_wing_callback_data(wing: str) -> str:
    key = secrets.token_hex(4)
    _wing_callback_map[key] = wing
    return f"p_rs_:{key}"


def _decode_wing_callback_data(data: str) -> str:
    key = data[len("p_rs_:"):]
    wing = _wing_callback_map.get(key)
    if wing:
        return wing
    return _decode_callback_part(key)


def _decode_room_callback_data(data: str):
    if not data:
        return "", ""
    prefix = "p_rd_room:"
    if data.startswith(prefix):
        key = data[len(prefix):]
        pair = _room_callback_map.get(key)
        if pair and len(pair) == 2:
            return pair[0], pair[1]
        return _legacy_decode_room(data)
    return "", ""


def _legacy_decode_room(data: str):
    """Fallback: decode from base64-encoded payload (for callbacks from old messages)."""
    prefix = "p_rd_room:"
    payload = data[len(prefix):]
    if ":" in payload:
        wing_payload, room_payload = payload.split(":", 1)
        return _decode_callback_part(wing_payload), _decode_callback_part(room_payload)
    return _decode_callback_part(payload), ""


WING_RUSSIAN_LABELS = {
    "philosophy": "Философия",
    "psychology": "Психология",
    "photography": "Фотография",
    "creative": "Творчество",
    "personal": "Личные мысли",
    "projects": "Проекты",
    "dreams": "Сны и сновидения",
    "health": "Здоровье и спорт",
    "insights": "Инсайты",
    "research": "Исследования",
    "my_notes": "Мои заметки",
    "general": "Общее",
}

ROOM_RUSSIAN_LABELS = {
    # Философия
    "cioran": "Эмиль Чоран",
    "thinking": "Методы мышления",
    "phenomenology": "Феноменология",
    "stoicism": "Стоицизм",
    "nietzsche": "Ницше",
    # Психология
    "archetypes": "Архетипы и Маска",
    "jung": "Юнг и цитаты",
    "psychoanalysis": "Психоанализ и Бион",
    "frankl": "Виктор Франкл",
    "lacan": "Жак Лакан",
    # Фотография
    "curator_texts": "Кураторские тексты",
    "explications": "Экспликации к фото",
    "photographers": "Фотографы",
    "therapy": "Фототрансцендентная арт-терапия",
    # Творчество
    "poetry": "Мои стихи",
    "scripts": "Сценарии и манифесты",
    "ideas": "Креативные идеи",
    # Личное
    "reflections": "Мои мысли и размышления",
    "aphorisms": "Высказывания",
    "books": "Мысли из книг",
    # Проекты
    "project_mask": "Project Mask",
    "gemini_ai": "Gemini & AI",
    "tech": "IT и разработка",
    # Служебные
    "general": "Общие записи",
    "_registry": "Реестр",
}


def format_wing_label(wing: str) -> str:
    """Возвращает русское название крыла."""
    if not wing:
        return ""
    norm = wing.lower().strip()
    return WING_RUSSIAN_LABELS.get(norm, wing)


def format_room_label(room: str) -> str:
    """Возвращает человекочитаемое русское название комнаты."""
    if not room:
        return ""
    norm = room.lower().strip()
    if norm in ROOM_RUSSIAN_LABELS:
        return ROOM_RUSSIAN_LABELS[norm]
    return room


def _extract_drawer_note_title(d: dict, fallback_idx: int) -> tuple[str, int]:
    """Извлекает красивое название заметки и номер части (чанка)."""
    title = d.get("title") or d.get("name") or d.get("closet_name") or ""
    chunk_index = d.get("chunk_index")
    if chunk_index is None:
        chunk_index = 0

    source_file = d.get("source_file", "")
    if not title and source_file:
        base = os.path.basename(source_file)
        title = os.path.splitext(base)[0]

    # Если название шаблонное или отсутствует, берём первую строку текста
    if not title or title.startswith("Запись "):
        preview = (d.get("content_preview") or d.get("content") or "").strip()
        if preview:
            first_line = preview.split("\n")[0].strip()
            first_line = first_line.lstrip("#* \t").strip()
            if first_line and len(first_line) > 3:
                title = first_line[:40]

    if not title:
        title = f"Заметка {fallback_idx}"

    return title.strip(), int(chunk_index)


def render_breadcrumbs(
    wing: str = "", room: str = "", drawer: str = "", section: str = ""
) -> str:
    """Формирует строку «хлебных крошек» для ориентации в Telegram UI."""
    parts = ["🏰 <b>Дворец</b>"]
    if section:
        parts.append(f"<b>{safe_html_format(section)}</b>")
    if wing:
        w_lbl = format_wing_label(wing)
        tag_w = (
            f"🕸️ <b>{safe_html_format(w_lbl)}</b>"
            if not room
            else f"🕸️ {safe_html_format(w_lbl)}"
        )
        parts.append(tag_w)
    if room:
        r_lbl = format_room_label(room)
        tag_r = (
            f"📁 <b>{safe_html_format(r_lbl)}</b>"
            if not drawer
            else f"📁 {safe_html_format(r_lbl)}"
        )
        parts.append(tag_r)
    if drawer:
        parts.append(f"📄 <b>{safe_html_format(drawer)}</b>")
    return " › ".join(parts) + "\n\n"


async def _report_ai_error(msg, exc: Exception) -> None:
    """Показывает ошибку ИИ вместо «вечного» статус-сообщения."""
    if isinstance(exc, AITimeoutError):
        logger.warning("AI timeout in palace navigation: %s", exc)
        await msg.edit_text("⏱️ ИИ не ответил вовремя. Попробуйте ещё раз.")
        return
    logger.exception("AI error in palace navigation: %s", exc)
    await msg.edit_text(f"❌ Ошибка ИИ: {exc}")


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
    kb.row(types.InlineKeyboardButton(text="🔀 Траверс", callback_data="p_trv"))
    kb.row(types.InlineKeyboardButton(text="🔄 Туннели", callback_data="p_tun"))
    kb.row(
        types.InlineKeyboardButton(text="◀️ Назад", callback_data="palace_back"),
        types.InlineKeyboardButton(text="🏠 Меню", callback_data="palace_main_menu"),
    )
    await safe_edit_text(
        cb.message,
        "🗺️ **Навигация**\nВыберите раздел:",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "p_wing")
@allowed_callback
async def cb_list_wings(cb: types.CallbackQuery):
    await cb.answer()
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = parsed.get("wings", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(wings, dict):
            wing_names = sorted(wings.keys(), key=lambda x: wings[x], reverse=True)
        else:
            wing_names = list(wings)
        uid = cb.from_user.id
        _wing_cache[uid] = wing_names
        lines = [
            render_breadcrumbs(section="Крылья") + "<b>🕸️ Крылья MemPalace:</b>\n",
            "Выберите крыло для перехода к комнатам:",
        ]

        kb = InlineKeyboardBuilder()
        for w in wing_names:
            w_text = format_wing_label(w)
            kb.button(
                text=f"🪪 {w_text}", callback_data=_build_wing_callback_data(w),
            )
        kb.adjust(2)
        kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_nav"))

        await safe_edit_text(
            cb.message, "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
        )
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


@router.callback_query(F.data == "p_room")
@allowed_callback
async def cb_rooms_menu(cb: types.CallbackQuery):
    await cb.answer()
    try:
        mcp = get_mcp()
        raw_wings = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw_wings)
        wdata = parsed.get("wings", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(wdata, dict):
            wing_names = sorted(wdata.keys(), key=lambda x: wdata[x], reverse=True)
        else:
            wing_names = list(wdata)

        lines = [
            f"<b>🪪 Все комнаты:</b>\n<i>{render_breadcrumbs(section='Комнаты').strip()}</i>\n",
        ]
        kb = InlineKeyboardBuilder()
        for w in wing_names:
            raw_rooms = await mcp.call_tool("mempalace_list_rooms", {"wing": w})
            rp = json.loads(raw_rooms)
            rooms = rp.get("rooms", {})
            if rooms:
                lines.append(f"├ <b>{safe_html_format(w)}</b>")
                sorted_rooms = sorted(rooms.items(), key=lambda x: x[1], reverse=True)
                for r, cnt in sorted_rooms[:5]:
                    lines.append(f"│  • {safe_html_format(r)} ({cnt})")
                    r_text = format_room_label(r)
                    kb.row(types.InlineKeyboardButton(
                        text=f"🚪 {r_text}", callback_data=_build_room_callback_data(w, r),
                    ))
                if len(sorted_rooms) > 5:
                    lines.append(f"│  … ещё {len(sorted_rooms) - 5}")
            else:
                lines.append(f"├ <b>{safe_html_format(w)}</b> — (пусто)")

        kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_nav"))
        ok = await safe_edit_text(
            cb.message, "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
        )
        if not ok:
            await cb.message.answer(
                "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
            )
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка загрузки комнат: {e}")


@router.callback_query(F.data.startswith("p_rs_:"))
@allowed_callback
async def cb_rooms_select(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data or len(cb.data) < 7:
        return
    uid = cb.from_user.id
    wing = _decode_wing_callback_data(cb.data)
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
        parsed = json.loads(raw)
        rooms = parsed.get("rooms", {})
    except Exception as e:
        if not await safe_edit_text(cb.message, f"❌ Ошибка загрузки комнат: {e}"):
            await cb.message.answer(f"❌ Ошибка загрузки комнат: {e}")
        return
    if not rooms:
        if not await safe_edit_text(cb.message, f"❌ В крыле «{wing}» нет комнат."):
            await cb.message.answer(f"❌ В крыле «{wing}» нет комнат.")
        return
    _user_context[uid] = {"wing": wing, "room": None, "drawer": None}

    sorted_rooms = sorted(rooms.items(), key=lambda x: x[1], reverse=True)
    room_limit = 50
    truncated = len(sorted_rooms) > room_limit
    if truncated:
        sorted_rooms = sorted_rooms[:room_limit]

    total_records = sum(rooms.values())
    w_label = format_wing_label(wing)
    lines = [
        f"🪪 <b>Комнаты крыла {w_label}:</b>\n<i>{render_breadcrumbs(wing=wing).strip()}</i>\n",
        f"<i>Всего комнат: {len(rooms)} | Записей: {total_records:,}</i>\n",
        "Выберите комнату для чтения записей:",
    ]
    kb = InlineKeyboardBuilder()
    for r, count in sorted_rooms:
        r_label = format_room_label(r)
        kb.button(
            text=f"🚪 {r_label}", callback_data=_build_room_callback_data(wing, r),
        )
    kb.adjust(2)
    if truncated:
        lines.append(f"\n... и ещё {len(rooms) - room_limit} комнат.")
    kb.row(types.InlineKeyboardButton(text="🔎 Фильтр комнат", callback_data=f"p_rmsrch:{wing}"))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_wing"))
    ok = await safe_edit_text(
        cb.message, "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
    )
    if not ok:
        await cb.message.answer(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup()
        )


@router.callback_query(F.data.startswith("p_rmsrch:"))
@allowed_callback
async def cb_room_search_prompt(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    wing = cb.data.split(":", 1)[1]
    from services.bot_setup import pending_room_filter
    uid = cb.from_user.id
    pending_room_filter[uid] = wing
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="◀️ Назад к комнатам", callback_data=_build_wing_callback_data(wing),
    ))
    await safe_edit_text(
        cb.message,
        render_breadcrumbs(wing=wing)
        + f"🔎 <b>Поиск комнаты в крыле «{safe_html_format(wing)}»</b>\n\n"
        "Введите текст или часть названия комнаты в чат:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_rd_room:"))
@allowed_callback
async def cb_open_room_drawer(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    wing, room = _decode_room_callback_data(cb.data)
    if not wing and not room:
        return
    uid = cb.from_user.id
    _user_context[uid] = {"wing": wing, "room": room, "drawer": None}
    await _show_drawers_page(cb.message.edit_text, uid, wing, room, 0)


@router.callback_query(F.data.startswith("p_gd:"))
@allowed_callback
async def cb_get_drawer(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    parts = cb.data.split(":", 3)
    if len(parts) < 4:
        return
    _, wing, room, drawer_name = parts
    uid = cb.from_user.id
    _user_context[uid] = {"wing": wing, "room": room, "drawer": drawer_name}
    mcp = get_mcp()
    try:
        # First find the drawer_id by listing drawers in the room
        list_raw = await mcp.call_tool("mempalace_list_drawers", {
            "wing": wing, "room": room, "limit": 100, "offset": 0,
        })
        list_parsed = json.loads(list_raw) if list_raw else {}
        drawers_list = list_parsed.get("drawers", [])
        drawer_id = ""
        for d in drawers_list:
            dn = d.get("closet_name") or d.get("title") or d.get("name", "")
            if dn == drawer_name:
                drawer_id = d.get("drawer_id", "")
                break
        if not drawer_id:
            # Fallback: use searched drawer content directly
            search_raw = await mcp.call_tool("mempalace_search", {
                "query": drawer_name, "wing": wing, "room": room, "limit": 1,
            })
            await safe_edit_text(cb.message, f"📄 {search_raw or 'Нет данных'}", parse_mode="HTML")
            return
        raw = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": drawer_id})
        parsed = json.loads(raw) if raw else {}
        text = parsed.get("content", "") if isinstance(parsed, dict) else raw or ""
        _read_state[uid] = {
            "room": room, "wing": wing, "drawer": drawer_name,
            "drawer_id": drawer_id, "source": "", "full_content": text,
            "offset": 0, "idx": 0,
        }
        await _show_drawer_content(cb, uid, text, drawer_name, wing, room, 0)
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


@allowed_callback
async def cb_cross_ai_article(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    session = _room_session.get(uid)
    if not session:
        await safe_edit_text(cb.message, "❌ Сессия не найдена.")
        return
    try:
        wing = session["wing"]
        room = session["room"]
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_drawers", {
            "wing": wing, "room": room, "limit": 50, "offset": 0,
        })
        parsed = json.loads(raw) if raw else {}
        drawers = parsed.get("drawers", [])
        if not drawers:
            await safe_edit_text(cb.message, "❌ Нет записей для создания статьи.")
            return
        content = "\n\n".join(
            d.get("content_preview", "") or d.get("content", "")[:200] for d in drawers[:20]
        )
        prompt = (
            f"Составь связную статью на основе следующих записей "
            f"из комнаты {wing}/{room}. "
            f"Отвечай на русском языке.\n\n{content}"
        )
        try:
            engine, model = get_current_ai()
        except Exception as exc:
            logger.error("[CROSS_AI] model resolution failed: %s", exc, exc_info=True)
            await safe_edit_text(
                cb.message,
                "❌ Не удалось определить модель ИИ. Выберите модель в /settings.",
            )
            return
        if not engine or not model:
            await safe_edit_text(
                cb.message,
                "❌ Модель ИИ не настроена. Выберите модель в /settings.",
            )
            return
        result = await call_ai_async(
            engine, model, [{"role": "user", "content": prompt}],
        )
        from .action_bar import finalize_answer

        async def _edit_article(content: str, **kwargs):
            await safe_edit_text(cb.message, content, **kwargs)
            return cb.message

        await finalize_answer(
            uid, _edit_article, result or "❌ Пустой ответ.",
            ctx={"parent_cb": "p_rdb"},
            title="<b>🤖 Статья</b>",
        )
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_cr:"))
@allowed_callback
async def cb_continue_read(cb: types.CallbackQuery):
    await cb.answer(
        "Пагинация обновлена: откройте запись заново (◀️/▶️ под ответом).",
        show_alert=True,
    )


@router.callback_query(F.data == "p_cr_noop")
@allowed_callback
async def cb_continue_read_noop(cb: types.CallbackQuery):
    await cb.answer()


@router.callback_query(F.data == "p_tax")
@allowed_callback
async def cb_taxonomy(cb: types.CallbackQuery):
    await cb.answer()
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = parsed.get("wings", {})
        if isinstance(wings, dict):
            wing_list = sorted(wings.items(), key=lambda x: -x[1])
            uid = cb.from_user.id
            wing_names = [w[0] for w in wing_list]
            _wing_cache[uid] = wing_names
            lines = ["<b>🏛️ Полная таксономия:</b>\n"]
            for wing, count in wing_list:
                lines.append(f"  🔹 <b>{safe_html_format(wing)}</b> ({count} записей)")
            kb = InlineKeyboardBuilder()
            for i, w in enumerate(wing_names):
                kb.row(types.InlineKeyboardButton(
                    text=f"🕸️ {w}", callback_data=f"p_tw_{i}",
                ))
            kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_nav"))
            await safe_edit_text(
                cb.message, "\n".join(lines),
                parse_mode="HTML", reply_markup=kb.as_markup(),
            )
        else:
            joined = "\n".join(f"  • {w}" for w in wings)
            await safe_edit_text(cb.message, joined)
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tw_"))
@allowed_callback
async def cb_taxonomy_wing(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        idx = int(cb.data[5:])
    except ValueError:
        return
    wings = _wing_cache.get(uid)
    if not wings or idx >= len(wings):
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wdata = parsed.get("wings", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(wdata, dict):
            wings = sorted(wdata.keys(), key=lambda x: wdata[x], reverse=True)
        else:
            wings = list(wdata)
        _wing_cache[uid] = wings
    if idx >= len(wings):
        await cb.message.edit_text("❌ Сессия истекла. Начните заново.")
        return
    wing = wings[idx]
    mcp = get_mcp()
    raw = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
    parsed = json.loads(raw)
    rooms = parsed.get("rooms", {})
    if not rooms:
        await cb.message.edit_text(f"❌ В крыле «{wing}» нет комнат.")
        return
    total_records = sum(rooms.values())
    lines = [
        f"🪪 <b>Комнаты крыла {wing}:</b>\n<i>{render_breadcrumbs(wing=wing).strip()}</i>\n",
        f"<i>Всего комнат: {len(rooms)} | Записей: {total_records:,}</i>\n",
        "Выберите комнату для чтения записей:",
    ]
    kb = InlineKeyboardBuilder()
    for room, count in sorted(rooms.items(), key=lambda x: x[1], reverse=True):
        kb.button(
            text=f"📖 {room}",
            callback_data=_build_room_callback_data(wing, room),
        )
    kb.adjust(2)
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tax"))
    await safe_edit_text(
        cb.message, "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_grf")
@allowed_callback
async def cb_graph(cb: types.CallbackQuery):
    await cb.answer()
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_graph_stats")
        parsed = json.loads(raw)
        total_rooms = parsed.get("total_rooms", 0)
        tunnel_rooms = parsed.get("tunnel_rooms", 0)
        total_edges = parsed.get("total_edges", 0)
        rooms_per_wing = parsed.get("rooms_per_wing", {})

        total_wings = len(rooms_per_wing)
        total_records = sum(rooms_per_wing.values()) if rooms_per_wing else 0

        lines = [
            render_breadcrumbs(section="Граф связей") + "<b>📊 Статистика графа:</b>",
            f"  • Крыльев: {total_wings}",
            f"  • Комнат: {total_rooms}",
            f"  • Записей: {total_records}",
            f"  • Туннелей: {tunnel_rooms}",
            f"  • Связей: {total_edges}",
        ]
        if rooms_per_wing:
            lines.append("\n<b>Комнат по крыльям:</b>")
            for w, cnt in sorted(rooms_per_wing.items(), key=lambda x: -x[1])[:8]:
                lines.append(f"  • {safe_html_format(w)}: {cnt}")
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")
        return
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="🗺️ Скачать карту (.html)", callback_data="p_export_map",
    ))
    if tunnel_rooms:
        kb.row(types.InlineKeyboardButton(text="🔗 Туннели", callback_data="p_tl"))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_nav"))
    await safe_edit_text(
        cb.message, "\n".join(lines),
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_export_map")
@allowed_callback
async def cb_export_map(cb: types.CallbackQuery):
    await cb.answer("Генерирую интерактивную карту...")
    try:
        from services.palace_visualizer import generate_palace_map_html
        mcp = get_mcp()
        raw_wings = await mcp.call_tool("mempalace_list_wings")
        parsed_w = json.loads(raw_wings) if raw_wings else {}
        wdata = parsed_w.get("wings", parsed_w) if isinstance(parsed_w, dict) else parsed_w

        raw_tunnels = await mcp.call_tool("mempalace_list_tunnels")
        parsed_t = json.loads(raw_tunnels) if raw_tunnels else []
        if isinstance(parsed_t, dict) and "tunnels" in parsed_t:
            parsed_t = parsed_t["tunnels"]

        rooms_by_wing = {}
        for w in (wdata.keys() if isinstance(wdata, dict) else wdata):
            try:
                raw_r = await mcp.call_tool("mempalace_list_rooms", {"wing": w})
                rp = json.loads(raw_r) if raw_r else {}
                rooms_by_wing[w] = rp.get("rooms", {})
            except Exception:
                rooms_by_wing[w] = {}

        html_content = generate_palace_map_html(wdata, rooms_by_wing, parsed_t)
        html_bytes = html_content.encode("utf-8")

        # Сохраняем во временный файл для мгновенного открытия в браузере на Mac
        try:
            with open("/tmp/palace-graph.html", "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception:
            pass

        total_rooms_count = sum(len(r) for r in rooms_by_wing.values())
        caption = (
            "🌌 <b>Интерактивная карта — Граф знаний «Созвездия»</b>\n\n"
            f"📊 <b>Объекты:</b> {len(wdata)} крыльев, "
            f"{total_rooms_count} комнат, "
            f"{len(parsed_t)} туннелей.\n\n"
            "✨ <b>Возможности:</b>\n"
            "• <b>Слой «Созвездия»:</b> интерактивный граф на Canvas с физикой и зумом.\n"
            "• <b>Слой «Атлас»:</b> круговая Sunburst-миникарта в левом углу.\n"
            "• <b>Раскрытие ящиков:</b> кликните на комнату и нажмите «Раскрыть ящики» "
            "для просмотра названий заметок!\n"
            "• <b>Офлайн 100%:</b> работает без интернета в Chrome, Safari и Telegram.\n\n"
            "💡 <i>Нажмите кнопку ниже, чтобы мгновенно открыть граф в браузере на Mac!</i>"
        )
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(
            text="🖥️ Открыть в браузере (Chrome / Safari)",
            callback_data="p_open_browser",
        ))
        kb.row(types.InlineKeyboardButton(
            text="◀️ Назад во Дворец",
            callback_data="p_nav",
        ))
        doc_file = types.BufferedInputFile(html_bytes, filename="palace_map.html")
        try:
            await cb.message.answer_document(
                doc_file,
                caption=caption,
                reply_markup=kb.as_markup(),
                parse_mode="HTML",
            )
        except TypeError:
            await cb.message.answer_document(
                doc_file,
                caption=caption,
                parse_mode="HTML",
            )
    except Exception as e:
        logger.warning("[MAP_EXPORT] Ошибка экспорта карты: %s", e, exc_info=True)
        await cb.message.answer(f"❌ Ошибка экспорта карты: {e}")


@router.callback_query(F.data == "p_open_browser")
@allowed_callback
async def cb_open_browser(cb: types.CallbackQuery):
    try:
        import subprocess
        tmp_path = "/tmp/palace-graph.html"
        repo_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "palace-graph.html"
        )
        target = repo_path if os.path.exists(repo_path) else tmp_path
        subprocess.Popen(["open", target])
        await cb.answer("🚀 Граф открыт в вашем браузере!")
    except Exception as e:
        logger.warning("[MAP] Ошибка открытия в браузере: %s", e)
        await cb.answer(f"❌ Не удалось открыть: {e}", show_alert=True)


# ─── DRAWERS ───


async def _show_drawers_page(edit_func, uid: int, wing: str, room: str, offset: int):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool(
            "mempalace_list_drawers",
            {"wing": wing, "room": room, "limit": PAGE_SIZE, "offset": offset},
        )
        parsed = json.loads(raw)
        drawers = parsed.get("drawers", [])
        total = parsed.get("total") or parsed.get("count", 0)

        _drawer_list_state[uid] = {
            "wing": wing,
            "room": room,
            "offset": offset,
            "total": total,
            "drawers": drawers,
        }

        if not drawers:
            kb = InlineKeyboardBuilder()
            kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_nav"))
            return await edit_func(
                f"📖 В комнате <b>{wing}/{room}</b> пока нет записей.",
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )

        w_label = format_wing_label(wing)
        r_label = format_room_label(room)
        lines = [
            f"<b>📖 Записи в {w_label}/{r_label}</b>  ({total} записей)\n"
            f"<i>{render_breadcrumbs(wing=wing, room=room).strip()}</i>\n",
        ]
        for i, d in enumerate(drawers):
            note_title, chunk_idx = _extract_drawer_note_title(d, offset + i + 1)
            preview = d.get("content_preview", "") or d.get("content", "")[:300]
            date_val = d.get("created_at") or d.get("date") or d.get("timestamp") or ""
            tags = d.get("tags") or d.get("keywords") or []
            chunk_suffix = f" [часть {chunk_idx + 1}]" if chunk_idx > 0 else ""
            display_title = f"{note_title}{chunk_suffix}"
            safe_n = safe_html_format(display_title)
            lines.append(f"{offset + i + 1}. 📄 <b>{safe_n}</b>")
            meta_chips = []
            if date_val:
                meta_chips.append(f"📅 {safe_html_format(str(date_val)[:10])}")
            if tags:
                tag_str = ", ".join(tags[:3]) if isinstance(tags, list) else str(tags)
                meta_chips.append(f"🏷️ {safe_html_format(tag_str)}")
            if meta_chips:
                lines.append(f"   <i>{' · '.join(meta_chips)}</i>")
            if preview:
                clean_prev = preview.strip().replace("\n", " ")
                lines.append(f"   {safe_html_format(clean_prev[:250])}")

        extra_rows = []
        for i, d in enumerate(drawers):
            note_title, chunk_idx = _extract_drawer_note_title(d, offset + i + 1)
            chunk_suffix = f" [ч.{chunk_idx + 1}]" if chunk_idx > 0 else ""
            max_btn_len = 20 if chunk_idx > 0 else 24
            short_t = (
                note_title[:max_btn_len] + "…"
                if len(note_title) > max_btn_len
                else note_title
            )
            btn_title = f"📄 Полный текст: {short_t}{chunk_suffix}"
            extra_rows.append([
                types.InlineKeyboardButton(
                    text=btn_title, callback_data=f"p_rd:{i}",
                ),
            ])
        nav_row = []
        if offset > 0:
            nav_row.append(
                types.InlineKeyboardButton(
                    text="◀️ Пред.", callback_data=f"p_rdp:{offset - PAGE_SIZE}",
                ),
            )
        if offset + PAGE_SIZE < total:
            nav_row.append(
                types.InlineKeyboardButton(
                    text="▶️ След.", callback_data=f"p_rdp:{offset + PAGE_SIZE}",
                ),
            )
        if nav_row:
            extra_rows.append(nav_row)
        extra_rows.append([types.InlineKeyboardButton(
            text="🤖 Спросить ИИ по комнате", callback_data="p_room_ai",
        )])
        from handlers.agent import build_room_agent_callback
        extra_rows.append([types.InlineKeyboardButton(
            text="🤖 Агент", callback_data=build_room_agent_callback(wing, room),
        )])

        from .action_bar import finalize_answer
        await finalize_answer(
            uid, edit_func, "\n".join(lines), is_html=True,
            ctx={"wing": wing, "room": room, "parent_cb": "p_nav"},
            extra_rows=extra_rows,
        )
    except Exception as e:
        await edit_func(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_rd:"))
@allowed_callback
async def cb_read_drawer(cb: types.CallbackQuery):
    await cb.answer()
    try:
        if not cb.data:
            return
        parts = cb.data.split(":")
        if len(parts) < 2:
            return
        idx = int(parts[1])
        uid = cb.from_user.id
        state = _drawer_list_state.get(uid)
        if not state or idx >= len(state.get("drawers", [])):
            ctx = _user_context.get(uid) or {}
            if ctx.get("wing") and ctx.get("room"):
                raw = await get_mcp().call_tool(
                    "mempalace_list_drawers",
                    {"wing": ctx["wing"], "room": ctx["room"], "limit": 100, "offset": 0},
                )
                parsed = json.loads(raw)
                drawers = parsed.get("drawers", [])
                if drawers and idx < len(drawers):
                    _drawer_list_state[uid] = {
                        "wing": ctx["wing"], "room": ctx["room"],
                        "offset": 0, "total": parsed.get("total") or parsed.get("count", 0),
                        "drawers": drawers,
                    }
                    state = _drawer_list_state.get(uid)
            if not state or idx >= len(state.get("drawers", [])):
                msg = "❌ Данные не найдены. Откройте комнату заново."
                if not await safe_edit_text(cb.message, msg):
                    await cb.message.answer(msg)
                return

        drawer = state["drawers"][idx]
        drawer_id = drawer.get("drawer_id", "")
        drawer_name = drawer.get("closet_name") or drawer.get("title") or drawer.get("name", "")
        wing = state["wing"]
        room = state["room"]

        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_get_drawer",
            {"drawer_id": drawer_id} if drawer_id else {"drawer_id": ""},
        )
        parsed = json.loads(raw) if raw else {}
        text = ""
        meta = {}
        if isinstance(parsed, dict) and "content" in parsed:
            text = parsed["content"]
            meta = parsed.get("metadata") or {}
        elif isinstance(parsed, str):
            text = parsed

        source_id = str(meta.get("source_id") or "")
        source_type = str(meta.get("source_type") or "")
        source_title = str(meta.get("source_title") or "")
        if not source_id and drawer_id:
            try:
                from services.notes_sync import get_backlink_by_drawer
                bl = get_backlink_by_drawer(drawer_id)
                if bl:
                    source_id = bl.get("source_id", "")
                    source_type = bl.get("source_type", "")
                    source_title = bl.get("source_title", "")
            except Exception:
                pass

        _read_state[uid] = {
            "room": room, "wing": wing, "drawer": drawer_name,
            "drawer_id": drawer_id, "source": "", "full_content": text,
            "offset": 0, "idx": idx,
            "source_id": source_id, "source_type": source_type, "source_title": source_title,
        }
        _user_context[uid] = {"wing": wing, "room": room, "drawer": drawer_name}

        await _show_drawer_content(cb, uid, text, drawer_name, wing, room, idx)
    except Exception as e:
        err = f"❌ Ошибка: {e}"

        if not await safe_edit_text(cb.message, err):
            await cb.message.answer(err)


async def _show_drawer_content(
    cb, uid: int, text: str, drawer_name: str, wing: str, room: str, idx: int,
):
    """Показывает полный текст записи с панелью действий и кнопкой удаления."""
    from .action_bar import finalize_answer

    async def _edit_or_answer(content: str, **kwargs):
        ok = await safe_edit_text(cb.message, content, **kwargs)
        if not ok:
            await cb.message.answer(content, **kwargs)
        return cb.message

    st = _read_state.get(uid) or {}
    source_id = st.get("source_id", "")
    source_type = st.get("source_type", "")

    extra_rows = []
    if source_id and source_type == "apple_notes":
        extra_rows.append([
            types.InlineKeyboardButton(
                text="📝 Открыть в Apple Notes", callback_data=f"p_notesrc:{source_id}",
            ),
        ])
    extra_rows.append([
        types.InlineKeyboardButton(
            text="🗑️ Удалить запись", callback_data=f"p_drdel:{idx}",
        ),
    ])
    await finalize_answer(
        uid, _edit_or_answer, text or "📄 (пустая запись)",
        ctx={
            "wing": wing,
            "room": room,
            "drawer": drawer_name,
            "parent_cb": "p_rdb",
            "breadcrumbs": render_breadcrumbs(wing=wing, room=room, drawer=drawer_name).strip(),
        },
        title=f"📄 {safe_html_format(drawer_name or 'Запись')}",
        extra_rows=extra_rows,
    )


@router.callback_query(F.data == "p_rdb")
@allowed_callback
async def cb_read_drawer_back(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    state = _drawer_list_state.get(uid)
    if not state:
        ctx = _user_context.get(uid) or {}
        if ctx.get("wing") and ctx.get("room"):
            await _show_drawers_page(cb.message.edit_text, uid, ctx["wing"], ctx["room"], 0)
            return
    if not state:
        if not await safe_edit_text(cb.message, "❌ Данные не найдены. Откройте комнату заново."):
            await cb.message.answer("❌ Данные не найдены. Откройте комнату заново.")
        return

    wing = state.get("wing", "")
    room = state.get("room", "")
    offset = state.get("offset", 0)
    await _show_drawers_page(cb.message.edit_text, uid, wing, room, offset)


# ─── DELETE DRAWER ───


@router.callback_query(F.data.startswith("p_drdel:"))
@allowed_callback
async def cb_drawer_delete(cb: types.CallbackQuery):
    """Подтверждение удаления записи."""
    await cb.answer()
    if not cb.data:
        return
    idx = int(cb.data.split(":", 1)[1])
    uid = cb.from_user.id
    st = _read_state.get(uid)
    if not st:
        if not await safe_edit_text(cb.message, "❌ Сессия истекла. Откройте запись заново."):
            await cb.message.answer("❌ Сессия истекла. Откройте запись заново.")
        return
    name = st.get("drawer") or "эту запись"
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="✅ Удалить", callback_data=f"p_drdel_c:{idx}",
        ),
        types.InlineKeyboardButton(
            text="❌ Отмена", callback_data=f"p_drdel_x:{idx}",
        ),
    )
    if not await safe_edit_text(
        cb.message,
        f"🗑️ <b>Удалить запись</b> «{safe_html_format(name)}»?\n\n"
        "Запись будет удалена из Дворца безвозвратно.",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    ):
        await cb.message.answer("❌ Не удалось обновить сообщение.")


@router.callback_query(F.data.startswith("p_drdel_c:"))
@allowed_callback
async def cb_drawer_delete_confirm(cb: types.CallbackQuery):
    """Выполняет удаление записи через MCP."""
    await cb.answer()
    if not cb.data:
        return
    uid = cb.from_user.id
    st = _read_state.get(uid)
    if not st or not st.get("drawer_id"):
        if not await safe_edit_text(cb.message, "❌ Сессия истекла. Откройте запись заново."):
            await cb.message.answer("❌ Сессия истекла. Откройте запись заново.")
        return
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_delete_drawer", {"drawer_id": st["drawer_id"]})
        parsed = json.loads(raw) if raw else {}
        if not parsed.get("success"):
            err = parsed.get("error", "неизвестная ошибка")
            if not await safe_edit_text(cb.message, f"❌ Не удалось удалить запись: {err}"):
                await cb.message.answer(f"❌ Не удалось удалить запись: {err}")
            return
    except Exception as e:
        if not await safe_edit_text(cb.message, f"❌ Не удалось удалить запись: {e}"):
            await cb.message.answer(f"❌ Не удалось удалить запись: {e}")
        return
    did = st["drawer_id"]
    _read_state.pop(uid, None)
    try:
        from services.notes_sync import delete_backlink
        delete_backlink(did)
    except Exception:
        pass
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="◀️ К списку записей", callback_data="p_rdb"))
    if not await safe_edit_text(
        cb.message,
        "🗑️ <b>Запись удалена.</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    ):
        await cb.message.answer("🗑️ Запись удалена.")


@router.callback_query(F.data.startswith("p_drdel_x:"))
@allowed_callback
async def cb_drawer_delete_cancel(cb: types.CallbackQuery):
    """Отмена удаления — возвращает просмотр записи."""
    await cb.answer()
    if not cb.data:
        return
    idx = int(cb.data.split(":", 1)[1])
    uid = cb.from_user.id
    st = _read_state.get(uid)
    if not st:
        if not await safe_edit_text(cb.message, "❌ Сессия истекла. Откройте запись заново."):
            await cb.message.answer("❌ Сессия истекла. Откройте запись заново.")
        return
    await _show_drawer_content(
        cb, uid, st.get("full_content") or "", st.get("drawer") or "",
        st.get("wing", ""), st.get("room", ""), idx,
    )


@router.callback_query(F.data.startswith("p_rdp:"))
@allowed_callback
async def cb_read_drawer_page(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    offset = int(cb.data.split(":")[1])
    uid = cb.from_user.id
    state = _drawer_list_state.get(uid)
    if not state:
        ctx = _user_context.get(uid) or {}
        if ctx.get("wing") and ctx.get("room"):
            raw = await get_mcp().call_tool(
                "mempalace_list_drawers",
                {"wing": ctx["wing"], "room": ctx["room"], "limit": 100, "offset": 0},
            )
            parsed = json.loads(raw)
            drawers = parsed.get("drawers", [])
            if drawers:
                _drawer_list_state[uid] = {
                    "wing": ctx["wing"], "room": ctx["room"],
                    "offset": 0, "total": parsed.get("count", 0),
                    "drawers": drawers,
                }
                state = _drawer_list_state.get(uid)
    if not state:
        if not await safe_edit_text(cb.message, "❌ Данные не найдены. Откройте комнату заново."):
            await cb.message.answer("❌ Данные не найдены. Откройте комнату заново.")
        return

    wing = state["wing"]
    room = state["room"]
    await _show_drawers_page(cb.message.edit_text, uid, wing, room, offset)


# ─── ROOM AI QUESTION ───


@router.callback_query(F.data == "p_room_ai")
@allowed_callback
async def cb_ask_room_ai(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    ctx = _user_context.get(uid) or {}
    if not ctx.get("wing") or not ctx.get("room"):
        await cb.message.edit_text("❌ Комната не выбрана. Откройте комнату заново.")
        return
    _pending_mcp_input[uid] = f"ask_room_ai:{ctx['wing']}:{ctx['room']}"
    await cb.message.answer(
        f"🤖 **Вопрос по комнате** {ctx['wing']}/{ctx['room']}\n\n"
        "Напишите ваш вопрос, и ИИ ответит на основе записей в этой комнате.",
        parse_mode="Markdown",
    )


async def _answer_room_ai(
    msg, uid: int, wing: str, room: str, question: str, with_web: bool = False,
):
    ctx = _user_context.setdefault(uid, {})

    # ── if with_web, skip step 1 (reuse cached summary) ──
    if with_web:
        combined_summary = ctx.get("_room_summary")
        if combined_summary:
            await msg.edit_text("🌐 Ищу в интернете и уточняю ответ...")
            engine, model = get_current_ai()
            from services.web_search import search_web
            web_results = await search_web(question)
            system = (
                f"Ты отвечаешь на вопрос пользователя, используя:\n"
                f"1) Структурированную саммари записей из комнаты {wing}/{room}\n"
                f"2) Результаты поиска в интернете\n"
                f"Отвечай на русском языке.\n\n"
                f"Структурированная саммари комнаты:\n{combined_summary}\n\n"
                f"Результаты поиска:\n{web_results}"
            )
            try:
                result = await call_ai_async(engine, model, [
                    {"role": "system", "content": system},
                    {"role": "user", "content": question},
                ])
            except Exception as exc:
                await _report_ai_error(msg, exc)
                return
            _user_context[uid]["_last_ai_answer"] = result
            from .action_bar import finalize_answer
            await finalize_answer(
                uid, msg.edit_text, result or "❌ Пустой ответ.",
                ctx={"wing": wing, "room": room, "parent_cb": "p_rdb"},
                title=(
                    f"<b>🌐 Ответ по комнате "
                    f"{safe_html_format(wing)}/{safe_html_format(room)}</b>"
                ),
            )
            return

    # ── Fresh run: fetch, summarise, answer ──
    mcp = get_mcp()
    raw = await mcp.call_tool(
        "mempalace_list_drawers",
        {"wing": wing, "room": room, "limit": 100, "offset": 0},
    )
    parsed = json.loads(raw) if raw else {}
    drawers = parsed.get("drawers", [])
    if not drawers:
        await msg.edit_text(f"❌ В комнате {wing}/{room} нет записей.")
        return

    # Fetch full content for each drawer (up to 15)
    max_full = 15
    full_texts = []
    for i, d in enumerate(drawers[:max_full]):
        did = d.get("drawer_id", "")
        name = d.get("closet_name") or d.get("title") or d.get("name", "")
        if did:
            try:
                raw_d = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": did})
                dp = json.loads(raw_d) if raw_d else {}
                content = dp.get("content", "") if isinstance(dp, dict) else str(dp)
            except Exception:
                content = d.get("content_preview", "") or ""
        else:
            content = d.get("content_preview", "") or ""
        full_texts.append(f"--- {name} ---\n{content}")

    ctx_text = "\n\n".join(full_texts)
    if len(drawers) > max_full:
        ctx_text += f"\n\n... и ещё {len(drawers) - max_full} записей (не показаны)."

    if len(ctx_text) > 35000:
        ctx_text = ctx_text[:35000] + "\n\n... (контент сокращён из-за длины)"

    # Step 1: generate per-note summaries + combined overview
    engine, model = get_current_ai()
    await msg.edit_text("🧠 Составляю саммари по каждой записи комнаты...")
    try:
        combined_summary = await generate_summary(
            SummaryMode.ROOM,
            engine=engine,
            model=model,
            text=ctx_text,
            wing=wing,
            room=room,
        )
    except Exception as exc:
        await _report_ai_error(msg, exc)
        return
    if not combined_summary:
        combined_summary = ctx_text

    # Cache summary for with_web re-run
    _user_context[uid]["_room_summary"] = combined_summary

    # Step 2: answer question based ONLY on the combined summary
    await msg.edit_text("🤔 Анализирую саммари и готовлю ответ...")
    system = (
        f"Ты отвечаешь на вопрос пользователя ИСКЛЮЧИТЕЛЬНО на основе "
        f"структурированной саммари записей из комнаты {wing}/{room}. "
        f"Если в саммари нет нужной информации — так и скажи. "
        f"Отвечай на русском языке."
        f"\n\nСтруктурированная саммари комнаты:\n{combined_summary}"
    )

    try:
        result = await call_ai_async(engine, model, [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ])
    except Exception as exc:
        await _report_ai_error(msg, exc)
        return

    _user_context[uid]["_last_ai_question"] = question
    _user_context[uid]["_last_ai_answer"] = result

    from .action_bar import finalize_answer
    await finalize_answer(
        uid, msg.edit_text, result or "❌ Пустой ответ.",
        ctx={"wing": wing, "room": room, "parent_cb": "p_rdb"},
        title=(
            f"<b>🤖 Ответ по комнате "
            f"{safe_html_format(wing)}/{safe_html_format(room)}</b>"
        ),
    )


@router.callback_query(F.data == "p_room_ai_web")
@allowed_callback
async def cb_room_ai_web(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    ctx = _user_context.get(uid) or {}
    question = ctx.get("_last_ai_question", "")
    if not question:
        await cb.message.answer("❌ Нет сохранённого вопроса. Задайте вопрос заново.")
        return
    wing = ctx.get("wing", "")
    room = ctx.get("room", "")
    status = await cb.message.answer("🌐 Ищу в интернете и уточняю ответ...")
    await _answer_room_ai(status, uid, wing, room, question, with_web=True)


# ─── TRAVERSE ───

@router.callback_query(F.data == "p_trv")
@allowed_callback
async def cb_traverse_menu(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="⌨️ Ввести вручную", callback_data="p_trv_manual",
    ))
    kb.row(types.InlineKeyboardButton(
        text="🕸️ Выбрать из крыльев", callback_data="p_wing",
    ))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_nav"))
    await safe_edit_text(
        cb.message,
        "🔀 <b>Траверс</b> — обход графа от комнаты\n\n"
        "Выберите способ ввода:",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_trv_manual")
@allowed_callback
async def cb_traverse_manual(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "traverse_start"
    await safe_edit_text(
        cb.message,
        "🔀 Введите <b>крыло</b> и <b>комнату</b> для старта траверса.\n"
        "Пример: <code>философия шопенгауэр</code>\n"
        "Или: <code>* сны_и_отрывки_снов</code> (крыло='*' = все)",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("p_tr_"))
@allowed_callback
async def cb_traverse_step(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    step = int(cb.data.split(":", 1)[1])
    await cb.answer(f"🔀 Шаг {step}")


# ─── TUNNELS MENU ───

@router.callback_query(F.data == "p_tun")
@allowed_callback
async def cb_tunnels_menu(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📋 Список", callback_data="p_tl"))
    kb.row(types.InlineKeyboardButton(text="🔍 Между крыльями", callback_data="p_tb"))
    kb.row(types.InlineKeyboardButton(text="➡️ Пройти", callback_data="p_to"))
    kb.row(types.InlineKeyboardButton(text="➕ Создать", callback_data="p_tc"))
    kb.row(types.InlineKeyboardButton(text="🤖 ИИ-анализ", callback_data="p_tun_ai"))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_nav"))
    await safe_edit_text(
        cb.message, "🔄 <b>Туннели</b>\nВыберите действие:",
        parse_mode="HTML", reply_markup=kb.as_markup()
    )


# ─── TUNNELS LIST ───

@router.callback_query(F.data == "p_tl")
@allowed_callback
async def cb_tunnels_list(cb: types.CallbackQuery):
    await cb.answer()
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_tunnels")
        tunnels = json.loads(raw) if raw else []
        if isinstance(tunnels, dict) and "tunnels" in tunnels:
            tunnels = tunnels["tunnels"]
        if not tunnels:
            await safe_edit_text(cb.message, "🔗 Туннелей нет.")
            return

        text_limit = 30
        truncated_text = len(tunnels) > text_limit

        lines = [f"<b>🔗 Туннели ({len(tunnels)}):</b>\n"]
        for t in (tunnels[:text_limit] if truncated_text else tunnels):
            src = t.get("source", {})
            dst = t.get("target", {})
            src_w = src.get("wing", "?")
            src_r = src.get("room", "?")
            dst_w = dst.get("wing", "?")
            dst_r = dst.get("room", "?")
            label = t.get("label", "")
            tid = t.get("id", "")
            line = (
                f"  • {safe_html_format(src_w)}/{safe_html_format(src_r)}"
                f" ⟷ {safe_html_format(dst_w)}/{safe_html_format(dst_r)}"
            )
            if label:
                line += f" — {safe_html_format(label)}"
            if tid:
                line += f" <code>[{tid[:8]}]</code>"
            lines.append(line)
        if truncated_text:
            lines.append(f"\n... и ещё {len(tunnels) - text_limit} туннелей.")

        kb = InlineKeyboardBuilder()
        for t in tunnels[:20]:
            tid = t.get("id", "")
            src = t.get("source", {})
            dst = t.get("target", {})
            src_w = src.get("wing", "?")
            src_r = src.get("room", "?")
            dst_w = dst.get("wing", "?")
            dst_r = dst.get("room", "?")
            kb.row(types.InlineKeyboardButton(
                text=f"{src_w}/{src_r} ↔ {dst_w}/{dst_r}",
                callback_data=f"p_tdr:{tid}",
            ))
        kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tun"))
        await safe_edit_text(
            cb.message, "\n".join(lines),
            parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


# ─── TUNNELS BETWEEN WINGS ───

@router.callback_query(F.data == "p_tb")
@allowed_callback
async def cb_tunnels_between(cb: types.CallbackQuery):
    await cb.answer()
    _pending_mcp_input[cb.from_user.id] = "find_tunnels"
    await safe_edit_text(
        cb.message,
        "🔍 Введите два крыла через пробел для поиска общих комнат.\n"
        "Пример: <code>philosophy psychology</code>",
        parse_mode="HTML",
    )


# ─── TRAVERSE TUNNEL ───

@router.callback_query(F.data == "p_to")
@allowed_callback
async def cb_traverse_tunnel(cb: types.CallbackQuery):
    await cb.answer()
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_tunnels")
        tunnels = json.loads(raw) if raw else []
        if isinstance(tunnels, dict) and "tunnels" in tunnels:
            tunnels = tunnels["tunnels"]
        if not tunnels:
            await safe_edit_text(cb.message, "🔗 Туннелей нет для прохода.")
            return
        kb = InlineKeyboardBuilder()
        for t in tunnels[:20]:
            tid = t.get("id", "")
            src = t.get("source", {})
            dst = t.get("target", {})
            src_w = src.get("wing", "?")
            src_r = src.get("room", "?")
            dst_w = dst.get("wing", "?")
            dst_r = dst.get("room", "?")
            kb.row(types.InlineKeyboardButton(
                text=f"{src_w}/{src_r} ➡ {dst_w}/{dst_r}",
                callback_data=f"p_tow:{tid}",
            ))
        kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tun"))
        await safe_edit_text(
            cb.message,
            "➡️ <b>Выберите туннель для прохода:</b>",
            parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tow:"))
@allowed_callback
async def cb_tow_step(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    tunnel_id = cb.data.split(":", 1)[1]
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_tunnels")
        tunnels = json.loads(raw) if raw else []
        if isinstance(tunnels, dict) and "tunnels" in tunnels:
            tunnels = tunnels["tunnels"]
        t = next((x for x in tunnels if x.get("id") == tunnel_id), None)
        if not t:
            await safe_edit_text(cb.message, "❌ Туннель не найден.")
            return
        src = t.get("source", {})
        dst = t.get("target", {})
        label = t.get("label", "")
        lines = [
            "<b>➡️ Проход по туннелю</b>\n",
            "  От: {}/{}".format(
                safe_html_format(src.get('wing', '?')),
                safe_html_format(src.get('room', '?')),
            ),
            "  До: {}/{}".format(
                safe_html_format(dst.get('wing', '?')),
                safe_html_format(dst.get('room', '?')),
            ),
        ]
        if label:
            lines.append(f"  📝 {safe_html_format(label)}")
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(
            text="🤖 Обсудить с ИИ", callback_data=f"p_towa:{tunnel_id}",
        ))
        kb.row(types.InlineKeyboardButton(text="◀️ Назад к списку", callback_data="p_to"))
        await safe_edit_text(
            cb.message, "\n".join(lines), parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_towa:"))
@allowed_callback
async def cb_tunnel_ai_discuss(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    tunnel_id = cb.data.split(":", 1)[1]
    uid = cb.from_user.id
    _user_context[uid] = {"tunnel_id": tunnel_id}
    _pending_mcp_input[uid] = "tunnel_discuss"
    await cb.message.answer(
        "💬 Напишите ваш вопрос об этой связи.\n"
        "ИИ проанализирует оба конца туннеля и ответит, используя только данные этого соединения.",
    )


# ─── TUNNELS CREATE ───

@router.callback_query(F.data == "p_tc")
@allowed_callback
async def cb_tunnel_create(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _create_tunnel_state[uid] = {}
    kb = InlineKeyboardBuilder()
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = parsed.get("wings", parsed)
        if isinstance(wings, dict):
            wing_names = sorted(wings.keys(), key=lambda x: wings[x], reverse=True)
        else:
            wing_names = list(wings)
        for w in wing_names:
            kb.row(types.InlineKeyboardButton(
                text=f"🕸️ {w}", callback_data=f"p_tcs_{w}",
            ))
        kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tun"))
        await safe_edit_text(
            cb.message, "➕ <b>Создание туннеля</b>\nВыберите исходное крыло:",
            parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


# ─── TUNNELS AI ───

@router.callback_query(F.data == "p_tun_ai")
@allowed_callback
async def cb_tunnels_ai(cb: types.CallbackQuery):
    await cb.answer()
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_tunnels")
        tunnels = json.loads(raw) if raw else []
        if isinstance(tunnels, dict) and "tunnels" in tunnels:
            tunnels = tunnels["tunnels"]
        if not tunnels:
            await safe_edit_text(cb.message, "🔗 Нет туннелей для анализа.")
            return
        prompt = (
            "Проанализируй эти туннели (связи между комнатами знаний). "
            "Выдели сильные связи, неожиданные пересечения, "
            "и предложи новые темы для туннелей. "
            "Отвечай на русском языке.\n\n"
            + json.dumps(tunnels, ensure_ascii=False, indent=2)
        )
        engine, model = get_current_ai()
        result = await call_ai_async(
            engine, model, [{"role": "user", "content": prompt}],
        )
        await safe_edit_text(cb.message, result or "❌ Пустой ответ.", parse_mode="HTML")
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


# ─── TUNNEL DETAIL ───

@router.callback_query(F.data.startswith("p_tdr:"))
@allowed_callback
async def cb_tunnel_detail(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    tunnel_id = cb.data.split(":", 1)[1]
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_tunnels")
        tunnels = json.loads(raw) if raw else []
        if isinstance(tunnels, dict) and "tunnels" in tunnels:
            tunnels = tunnels["tunnels"]
        t = next((x for x in tunnels if x.get("id") == tunnel_id), None)
        if not t:
            await safe_edit_text(cb.message, "❌ Туннель не найден.")
            return
        src = t.get("source", {})
        dst = t.get("target", {})
        label = t.get("label", "")
        lines = [
            f"<b>🔗 Туннель: {tunnel_id[:12]}...</b>",
            "  От: {}/{}".format(
                safe_html_format(src.get('wing', '?')),
                safe_html_format(src.get('room', '?')),
            ),
            "  До: {}/{}".format(
                safe_html_format(dst.get('wing', '?')),
                safe_html_format(dst.get('room', '?')),
            ),
        ]
        if label:
            lines.append(f"  📝 {safe_html_format(label)}")
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="🤖 Обсудить с ИИ", callback_data=f"p_towa:{tunnel_id}"),
        )
        kb.row(types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"p_tdd:{tunnel_id}"))
        kb.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="p_tl"))
        await safe_edit_text(
            cb.message,
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tdrb:"))
@allowed_callback
async def cb_tunnel_detail_both(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    tunnel_id = cb.data.split(":", 1)[1]
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_tunnels")
        tunnels = json.loads(raw) if raw else []
        if isinstance(tunnels, dict) and "tunnels" in tunnels:
            tunnels = tunnels["tunnels"]
        t = next((x for x in tunnels if x.get("id") == tunnel_id), None)
        if not t:
            await safe_edit_text(cb.message, "❌ Туннель не найден.")
            return
        src = t.get("source", {})
        dst = t.get("target", {})
        lines = [
            f"<b>🔗 Туннель: {tunnel_id[:12]}...</b>",
            "  От: {}/{}".format(
                safe_html_format(src.get('wing', '?')),
                safe_html_format(src.get('room', '?')),
            ),
            "  До: {}/{}".format(
                safe_html_format(dst.get('wing', '?')),
                safe_html_format(dst.get('room', '?')),
            ),
        ]
        await safe_edit_text(cb.message, "\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tdd:"))
@allowed_callback
async def cb_tunnel_delete(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    tunnel_id = cb.data.split(":", 1)[1]
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="🗑️ Да, удалить", callback_data=f"p_tddc:{tunnel_id}",
    ))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_tl"))
    await safe_edit_text(
        cb.message, "🗑️ <b>Удалить туннель?</b>",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_tddc:"))
@allowed_callback
async def cb_tunnel_delete_confirm(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    tunnel_id = cb.data.split(":", 1)[1]
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_delete_tunnel", {"tunnel_id": tunnel_id})
        await safe_edit_text(cb.message, raw or "✅ Туннель удалён.", parse_mode="HTML")
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


# ─── TUNNELS FOLLOW ───

@router.callback_query(F.data.startswith("p_tfa_"))
@allowed_callback
async def cb_tunnel_follow_a(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    tunnel_id = cb.data.split(":", 1)[1]
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_tunnels")
        tunnels = json.loads(raw) if raw else []
        if isinstance(tunnels, dict) and "tunnels" in tunnels:
            tunnels = tunnels["tunnels"]
        t = next((x for x in tunnels if x.get("id") == tunnel_id), None)
        if not t:
            await safe_edit_text(cb.message, "❌ Туннель не найден.")
            return
        src = t.get("source", {})
        text = (
            f"<b>📖 Сторона A:</b> "
            f"{safe_html_format(src.get('wing', '?'))}/{safe_html_format(src.get('room', '?'))}"
        )
        await safe_edit_text(cb.message, text, parse_mode="HTML")
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("p_tfb_"))
@allowed_callback
async def cb_tunnel_follow_b(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    tunnel_id = cb.data.split(":", 1)[1]
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_tunnels")
        tunnels = json.loads(raw) if raw else []
        if isinstance(tunnels, dict) and "tunnels" in tunnels:
            tunnels = tunnels["tunnels"]
        t = next((x for x in tunnels if x.get("id") == tunnel_id), None)
        if not t:
            await safe_edit_text(cb.message, "❌ Туннель не найден.")
            return
        dst = t.get("target", {})
        text = (
            f"<b>📖 Сторона B:</b> "
            f"{safe_html_format(dst.get('wing', '?'))}/{safe_html_format(dst.get('room', '?'))}"
        )
        await safe_edit_text(cb.message, text, parse_mode="HTML")
    except Exception as e:
        await safe_edit_text(cb.message, f"❌ Ошибка: {e}")
