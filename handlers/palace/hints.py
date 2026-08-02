"""handlers/palace/hints.py — Tunnel hints and utility functions"""
import contextlib
import json
import os
import sqlite3

from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format

from services.ttl_dict import TtlDict
from .shared import router
from .navigation import _show_drawers_page


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
    await cb.answer()
    uid = cb.from_user.id
    data = _hint_data.get(uid)
    if not data:
        await cb.message.edit_text("❌ Нет данных подсказки.")
        return
    lines = [f"🔗 <b>Связи комнаты «{data['room']}»</b>\n"]
    for node in data["traverse"]:
        if isinstance(node, dict):
            r = node.get("room", "?")
            w = node.get("wing", "?")
            lines.append(f"  • <b>{safe_html_format(r)}</b> ({safe_html_format(w)})")
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="📖 Читать записи", callback_data="p_hnt_r",
    ))
    kb.row(types.InlineKeyboardButton(
        text="✅ Понятно", callback_data="p_hnt_d",
    ))
    await cb.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_hnt_r")
@allowed_callback
async def cb_hint_read(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _hint_data.get(uid)
    if not data:
        await cb.message.edit_text("❌ Нет данных.")
        return
    room = data["room"]
    wing = data.get("wing", "")
    await _show_drawers_page(cb.message.edit_text, uid, wing, room, 0)


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
        with contextlib.closing(sqlite3.connect(db_path)) as con:
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
            return "\n\n".join(parts)
    except Exception:
        return ""
