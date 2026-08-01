import json
import logging

import pydub
from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from faster_whisper import WhisperModel

from config import allowed_callback, allowed_only
from services.ttl_dict import TtlDict
from services.ai_engine import get_ai_response_async, get_current_ai
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format

logger = logging.getLogger("PersonalNote")
router = Router()
_whisper = None


def get_whisper():
    global _whisper
    if not _whisper:
        _whisper = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper


def _transcribe_sync(ogg_path: str, wav_path: str) -> str:
    pydub.AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")
    segs, _ = get_whisper().transcribe(wav_path, language="ru", beam_size=5)
    return " ".join(s.text for s in segs).strip()


_waiting_for_note: TtlDict = TtlDict()
_note_data: TtlDict = TtlDict()

FORMAT_PROMPT = """Ты — ТОЛЬКО редактор текста. Твоя задача — привести речь в читаемый вид, НЕ МЕНЯЯ СМЫСЛ.  # noqa: E501

СТРОГИЕ ПРАВИЛА:
1. Исправь пунктуацию и орфографию.
2. Удали слова-паразиты («э-э-э», «ну», «как бы», «короче», «типа», «собственно», «вообще»), стоп-слова, повторы слов.  # noqa: E501
3. Разбей на логические абзацы.
4. ЗАПРЕЩЕНО (если нарушишь — текст будет отклонён):
   - Любая интерпретация: «автор хочет сказать...», «главная мысль...», «вывод...»
   - Любые советы, рекомендации, мораль, оценки
   - Суммаризация, сокращение, перефразирование смыслов
   - Добавление заголовков, маркированных списков, которых не было
   - Любое изменение лексики автора (кроме исправления ошибок)
5. Верни ТОЛЬКО отформатированный текст. Никаких вступлений («Вот отформатированный текст:»), пояснений, комментариев.  # noqa: E501

ПРИМЕР ЧЕГО ДЕЛАТЬ НЕЛЬЗЯ:
❌ Ввод: "ну короче вчера был стресс на работе начальник заругала"
❌ Твой ответ: "Вчера был стресс на работе: начальник ругала. Главная мысль — конфликт с руководством." ← ЭТО ИНТЕРПРЕТАЦИЯ  # noqa: E501

ПРИМЕР ЧЕГО НУЖНО ДЕЛАТЬ:
✅ Ввод: "ну короче вчера был стресс на работе начальник заругала"
✅ Твой ответ: "Вчера был стресс на работе — начальник заругала." ← ТОЛЬКО ПУНКТУАЦИЯ И УБРАНО «НУ КОРОЧЕ»  # noqa: E501

Ещё пример:
✅ Ввод: "думаю что мне стоит заняться спортом типа бегать по утрам это полезно"
✅ Твой ответ: "Думаю, что мне стоит заняться спортом — бегать по утрам. Это полезно." ← ТОЛЬКО ЗНАКИ ПРЕПИНАНИЯ"""  # noqa: E501

CLASSIFY_PROMPT = """Ниже — заметка пользователя. Определи, к какому крылу и комнате Дворца знаний её отнести.  # noqa: E501

Доступные крылья и комнаты:
{taxonomy}

Правила:
- Если заметка подходит под существующее крыло/комнату — укажи их.
- Если не подходит ни под одно — укажи wing="личные_мысли", room="inbox".
- Верни ТОЛЬКО JSON: {{"wing": "...", "room": "...", "reason": "..."}}
- wing и room — в точности как в списке выше (регистр и написание сохраняй)."""


def _taxonomy_for_prompt(taxonomy: dict) -> str:
    lines = []
    for wing, rooms in taxonomy.items():
        room_names = list(rooms.keys()) if isinstance(rooms, dict) else []
        lines.append(f"- {wing}: {', '.join(room_names[:6])}")
    return "\n".join(lines)


async def _format_note(raw_text: str) -> str:
    engine, model = get_current_ai()
    msgs = [
        {"role": "system", "content": FORMAT_PROMPT},
        {"role": "user", "content": raw_text},
    ]
    return await get_ai_response_async(engine, model, msgs)


async def _classify_note(formatted: str, taxonomy: dict) -> dict:
    engine, model = get_current_ai()
    tax = _taxonomy_for_prompt(taxonomy)
    msgs = [
        {"role": "system", "content": CLASSIFY_PROMPT.format(taxonomy=tax)},
        {"role": "user", "content": formatted},
    ]
    raw = await get_ai_response_async(engine, model, msgs)
    try:
        cleaned = raw.strip()
        for prefix in ("```json", "```"):
            cleaned = cleaned.removeprefix(prefix)
        for suffix in ("```",):
            cleaned = cleaned.removesuffix(suffix)
        cleaned = cleaned.strip()
        return json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        return {
            "wing": "личные_мысли",
            "room": "inbox",
            "reason": "автоопределение не удалось",
        }


async def process_note_input(uid: int, raw_text: str, answer_func):
    _waiting_for_note.pop(uid, None)
    status = await answer_func("✍️ Форматирую...")

    try:
        formatted = await _format_note(raw_text)

        await status.edit_text("🔍 Определяю тематику...")
        mcp = get_mcp()
        tax_raw = await mcp.call_tool("mempalace_get_taxonomy")
        taxonomy = json.loads(tax_raw).get("taxonomy", {})
        classification = await _classify_note(formatted, taxonomy)

        suggested_wing = classification.get("wing", "личные_мысли")
        suggested_room = classification.get("room", "inbox")
        reason = classification.get("reason", "")

        preview = (
            f"<b>📝 Заметка:</b>\n\n"
            f"{safe_html_format(formatted)}\n\n"
            f"<b>🏛 Предложено:</b>\n"
            f"Крыло: <code>{safe_html_format(suggested_wing)}</code>\n"
            f"Комната: <code>{safe_html_format(suggested_room)}</code>\n"
        )
        if reason:
            preview += f"<i>→ {safe_html_format(reason)}</i>\n\n"
        preview += "Сохранить?"

        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="✅ Сохранить", callback_data="pn_cf"),
            types.InlineKeyboardButton(
                text="✏️ Другая комната", callback_data="pn_reclass",
            ),
        )
        kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="pn_cancel"))

        await status.edit_text(preview, parse_mode="HTML", reply_markup=kb.as_markup())

        _note_data[uid] = {
            "text": formatted,
            "raw": raw_text,
            "wing": suggested_wing,
            "room": suggested_room,
            "taxonomy": taxonomy,
        }

    except Exception as e:
        logger.error(f"Personal note error: {e}", exc_info=True)
        try:
            await status.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        except Exception:
            pass


@router.message(F.text == "📝 Личная заметка")
@allowed_only
async def cmd_personal_note(message: types.Message):
    _waiting_for_note[message.from_user.id] = True
    kb = ReplyKeyboardBuilder()
    kb.button(text="❌ Отмена")
    await message.answer(
        "📝 <b>Личная заметка</b>\n\n"
        "Отправьте текст или голосовое сообщение.\n"
        "Бот отформатирует, определит тему и предложит сохранить в Дворец.",
        parse_mode="HTML",
        reply_markup=kb.as_markup(resize_keyboard=True),
    )


@router.callback_query(F.data == "pn_cf")
@allowed_callback
async def cb_pn_save(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    data = _note_data.pop(uid, None)
    if not data:
        return await callback.message.edit_text("❌ Сессия истекла.")

    wing = data.get("wing", "личные_мысли")
    room = data.get("room", "inbox")
    text = data["text"]

    await callback.message.edit_text("⏳ Сохраняю...")

    mcp = get_mcp()
    results = []

    try:
        raw = await mcp.call_tool(
            "mempalace_add_drawer",
            {
                "wing": wing,
                "room": room,
                "content": text,
                "added_by": "telegram_bot",
                "source_file": "personal_note",
            },
        )
        json.loads(raw)
        results.append(f"✅ <code>{wing}/{room}</code>")

        if wing != "личные_мысли" or room != "inbox":
            await mcp.call_tool(
                "mempalace_add_drawer",
                {
                    "wing": "личные_мысли",
                    "room": "inbox",
                    "content": text,
                    "added_by": "telegram_bot",
                    "source_file": "personal_note",
                },
            )
            results.append("📋 копия в <code>личные_мысли/inbox</code>")

        await callback.message.edit_text(
            "✅ <b>Сохранено!</b>\n" + "\n".join(results), parse_mode="HTML",
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "pn_reclass")
@allowed_callback
async def cb_pn_reclass(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    data = _note_data.get(uid)
    if not data:
        return await callback.message.edit_text("❌ Сессия истекла.")

    taxonomy = data.get("taxonomy", {})
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="💭 личные_мысли", callback_data="pn_wing:личные_мысли",
        ),
    )
    for wing, rooms in taxonomy.items():
        if wing != "личные_мысли":
            kb.row(
                types.InlineKeyboardButton(
                    text=f"🕸️ {wing}", callback_data=f"pn_wing:{wing}",
                ),
            )
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="pn_cancel"))

    await callback.message.edit_text(
        "<b>Выберите крыло:</b>", parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("pn_wing:"))
@allowed_callback
async def cb_pn_wing(callback: types.CallbackQuery):
    await callback.answer()
    if not callback.data:
        return
    uid = callback.from_user.id
    wing = callback.data.split(":", 1)[1]
    data = _note_data.get(uid)
    if not data:
        return await callback.message.edit_text("❌ Сессия истекла.")

    taxonomy = data.get("taxonomy", {})
    rooms = taxonomy.get(wing, {})
    room_list = sorted(rooms.keys()) if isinstance(rooms, dict) else []
    if not room_list:
        room_list = ["inbox"]

    _note_data[uid]["room_list"] = room_list

    kb = InlineKeyboardBuilder()
    for i, room in enumerate(room_list[:15]):
        kb.row(
            types.InlineKeyboardButton(text=f"🪪 {room}", callback_data=f"pn_room:{i}"),
        )
    kb.row(types.InlineKeyboardButton(text="🆕 inbox", callback_data="pn_room:-1"))
    kb.row(
        types.InlineKeyboardButton(
            text="\u25c0\ufe0f Назад", callback_data="pn_reclass",
        ),
    )

    _note_data[uid]["wing"] = wing
    await callback.message.edit_text(
        f"<b>Крыло:</b> {safe_html_format(wing)}\n<b>Выберите комнату:</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("pn_room:"))
@allowed_callback
async def cb_pn_room(callback: types.CallbackQuery):
    await callback.answer()
    if not callback.data:
        return
    uid = callback.from_user.id
    idx_str = callback.data.split(":", 1)[1]
    data = _note_data.get(uid)
    if not data:
        return await callback.message.edit_text("❌ Сессия истекла.")

    room_list = data.get("room_list", [])
    if idx_str == "-1":
        room = "inbox"
    else:
        try:
            idx = int(idx_str)
            room = room_list[idx] if 0 <= idx < len(room_list) else "inbox"
        except (ValueError, IndexError):
            room = "inbox"

    wing = data.get("wing", "личные_мысли")
    data["room"] = room
    text = data["text"]

    preview = (
        f"<b>📝 Заметка:</b>\n\n"
        f"{safe_html_format(text)}\n\n"
        f"<b>🏛 Куда:</b> <code>{safe_html_format(wing)}/{safe_html_format(room)}</code>\n\n"
        f"Сохранить?"
    )
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Сохранить", callback_data="pn_cf"))
    kb.row(
        types.InlineKeyboardButton(
            text="\u25c0\ufe0f К выбору крыла", callback_data="pn_reclass",
        ),
    )
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="pn_cancel"))
    await callback.message.edit_text(
        preview, parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "pn_cancel")
@allowed_callback
async def cb_pn_cancel(callback: types.CallbackQuery):
    await callback.answer()
    _note_data.pop(callback.from_user.id, None)
    _waiting_for_note.pop(callback.from_user.id, None)
    await callback.message.edit_text("❌ Отменено.")


@router.message(F.text == "❌ Отмена")
@allowed_only
async def cmd_cancel_note(message: types.Message):
    uid = message.from_user.id
    _waiting_for_note.pop(uid, None)
    _note_data.pop(uid, None)
    import sys

    mod = sys.modules.get("__main__") or sys.modules.get("main")
    if mod and hasattr(mod, "cmd_start"):
        await mod.cmd_start(message)


# ─── LIST PERSONAL NOTES ───

PAGE_SIZE = 5
_list_state: TtlDict = TtlDict()
_active_drawer: TtlDict = TtlDict()


@router.message(F.text == "📖 Личные мысли")
@allowed_only
async def cmd_list_personal_notes(message: types.Message):
    await _show_pn_page(
        message, message.answer, wing="личные_мысли", room="inbox", offset=0,
    )


async def _show_pn_page(msg_or_cb, edit_func, wing: str, room: str, offset: int):
    uid = msg_or_cb.from_user.id if hasattr(msg_or_cb, "from_user") else msg_or_cb
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_list_drawers",
            {"wing": wing, "room": room, "limit": PAGE_SIZE, "offset": offset},
        )
        parsed = json.loads(raw)
        drawers = parsed.get("drawers", [])
        total = parsed.get("count", 0)

        _list_state[uid] = {
            "wing": wing,
            "room": room,
            "offset": offset,
            "total": total,
            "drawers": drawers,
        }

        if not drawers:
            kb = InlineKeyboardBuilder()
            kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="pn_b"))
            return await edit_func(
                "📖 Пока нет личных заметок.",
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )

        lines = [f"<b>📖 Личные мысли</b>  ({total} записей)\n"]
        for i, d in enumerate(drawers):
            preview = d.get("content_preview", "") or d.get("content", "")[:80]
            safe_p = safe_html_format(preview[:80])
            lines.append(f"{offset + i + 1}. <code>{safe_p}</code>")

        kb = InlineKeyboardBuilder()
        for i, d in enumerate(drawers):
            kb.row(
                types.InlineKeyboardButton(
                    text=f"📄 {offset + i + 1}", callback_data=f"pn_v:{i}",
                ),
            )
        nav_row = []
        if offset > 0:
            nav_row.append(
                types.InlineKeyboardButton(
                    text="\u25c0\ufe0f Назад",
                    callback_data=f"pn_p:{max(0, offset - PAGE_SIZE)}",
                ),
            )
        if offset + PAGE_SIZE < total:
            nav_row.append(
                types.InlineKeyboardButton(
                    text="\u25b6\ufe0f Вперед",
                    callback_data=f"pn_p:{offset + PAGE_SIZE}",
                ),
            )
        if nav_row:
            kb.row(*nav_row)
        kb.row(types.InlineKeyboardButton(text="🏠 В меню", callback_data="pn_b"))

        await edit_func(
            "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
        )

    except Exception as e:
        logger.error(f"List personal notes error: {e}", exc_info=True)
        await edit_func(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data.startswith("pn_p:"))
@allowed_callback
async def cb_pn_page(callback: types.CallbackQuery):
    await callback.answer()
    if not callback.data:
        return
    uid = callback.from_user.id
    offset = int(callback.data.split(":", 1)[1])
    state = _list_state.get(uid)
    wing = state["wing"] if state else "личные_мысли"
    room = state["room"] if state else "inbox"
    await _show_pn_page(callback, callback.message.edit_text, wing, room, offset)


@router.callback_query(F.data == "pn_b")
@allowed_callback
async def cb_pn_list_back(callback: types.CallbackQuery):
    await callback.answer()
    _list_state.pop(callback.from_user.id, None)
    _active_drawer.pop(callback.from_user.id, None)
    import sys

    mod = sys.modules.get("__main__") or sys.modules.get("main")
    if mod and hasattr(mod, "cmd_start"):
        await mod.cmd_start(callback.message)


@router.callback_query(F.data.startswith("pn_v:"))
@allowed_callback
async def cb_pn_view(callback: types.CallbackQuery):
    await callback.answer()
    if not callback.data:
        return
    uid = callback.from_user.id
    idx = int(callback.data.split(":", 1)[1])
    state = _list_state.get(uid)
    if not state or idx >= len(state.get("drawers", [])):
        return await callback.message.edit_text("❌ Сессия истекла.")

    drawer_id = state["drawers"][idx]["drawer_id"]
    _active_drawer[uid] = drawer_id

    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": drawer_id})
        parsed = json.loads(raw)
        content = parsed.get("content", "") or parsed.get("text", "")
        wing = parsed.get("wing", "личные_мысли")
        room = parsed.get("room", "inbox")

        preview = content[:300] + ("\u2026" if len(content) > 300 else "")
        text = (
            f"<b>📝 Заметка</b>\n"
            f"<code>{safe_html_format(wing)}/{safe_html_format(room)}</code>\n\n"
            f"{safe_html_format(preview)}"
        )
        if len(content) > 300:
            text += "\n\n<i>полный текст — после кнопки «📖 Читать»</i>"

        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📖 Читать", callback_data="pn_r"))
        kb.row(
            types.InlineKeyboardButton(text="💾 В Дворец", callback_data="pn_tp"),
            types.InlineKeyboardButton(text="💬 Цитату", callback_data="pn_q"),
        )
        kb.row(
            types.InlineKeyboardButton(text="🗑️ Удалить", callback_data="pn_del"),
            types.InlineKeyboardButton(
                text="\u25c0\ufe0f К списку", callback_data="pn_bl",
            ),
        )
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=kb.as_markup(),
        )

    except Exception as e:
        logger.error(f"View note error: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data == "pn_r")
@allowed_callback
async def cb_pn_read_full(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    drawer_id = _active_drawer.get(uid)
    if not drawer_id:
        return await callback.message.edit_text("❌ Сессия истекла.")

    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": drawer_id})
        parsed = json.loads(raw)
        content = parsed.get("content", "") or parsed.get("text", "")
        wing = parsed.get("wing", "личные_мысли")
        room = parsed.get("room", "inbox")

        text = (
            f"<b>📝 Заметка</b>\n"
            f"<code>{safe_html_format(wing)}/{safe_html_format(room)}</code>\n\n"
            f"{safe_html_format(content)}"
        )

        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="💾 В Дворец", callback_data="pn_tp"),
            types.InlineKeyboardButton(text="💬 Цитату", callback_data="pn_q"),
        )
        kb.row(
            types.InlineKeyboardButton(text="🗑️ Удалить", callback_data="pn_del"),
            types.InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="pn_v"),
        )

        from services.text_formatter import split_message

        parts = split_message(text)
        for part in parts[:-1]:
            await callback.message.answer(part, parse_mode="HTML")
        await callback.message.edit_text(
            parts[-1], parse_mode="HTML", reply_markup=kb.as_markup(),
        )

    except Exception as e:
        logger.error(f"Read full note error: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data == "pn_bl")
@allowed_callback
async def cb_pn_back_to_list(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    _active_drawer.pop(uid, None)
    state = _list_state.get(uid)
    if state:
        await _show_pn_page(
            callback,
            callback.message.edit_text,
            state["wing"],
            state["room"],
            state["offset"],
        )
    else:
        await _show_pn_page(
            callback, callback.message.edit_text, "личные_мысли", "inbox", 0,
        )


@router.callback_query(F.data == "pn_v")
@allowed_callback
async def cb_pn_back_to_view(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    state = _list_state.get(uid)
    if state:
        offset = state.get("offset", 0)
        await _show_pn_page(
            callback, callback.message.edit_text, state["wing"], state["room"], offset,
        )
    else:
        await _show_pn_page(
            callback, callback.message.edit_text, "личные_мысли", "inbox", 0,
        )


@router.callback_query(F.data == "pn_tp")
@allowed_callback
async def cb_pn_to_palace(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    drawer_id = _active_drawer.get(uid)
    if not drawer_id:
        return await callback.message.edit_text("❌ Сессия истекла.")

    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": drawer_id})
        parsed = json.loads(raw)
        content = parsed.get("content", "") or parsed.get("text", "")

        from handlers.palace import _save_state

        _save_state[uid] = {
            "text": content,
            "mode": "full",
            "wing": "",
            "room": "",
            "wings": [],
            "rooms": [],
        }
        from handlers.palace import _show_save_wings

        await _show_save_wings(callback.message.edit_text, uid)

    except Exception as e:
        logger.error(f"Save to palace error: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")


_quote_waiting: TtlDict = TtlDict()


@router.callback_query(F.data == "pn_q")
@allowed_callback
async def cb_pn_quote_prompt(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    drawer_id = _active_drawer.get(uid)
    if not drawer_id:
        return await callback.message.edit_text("❌ Сессия истекла.")

    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_get_drawer", {"drawer_id": drawer_id})
        parsed = json.loads(raw)
        content = parsed.get("content", "") or parsed.get("text", "")

        _quote_waiting[uid] = {"content": content, "drawer_id": drawer_id}

        await callback.message.edit_text(
            f"<b>💬 Отправьте цитату</b>\n\n"
            f"Скопируйте нужный фрагмент из заметки ниже и отправьте его сообщением:\n\n"
            f"{safe_html_format(content[:500])}"
            + ("\u2026" if len(content) > 500 else ""),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Quote prompt error: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data == "pn_del")
@allowed_callback
async def cb_pn_delete_confirm(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    drawer_id = _active_drawer.get(uid)
    if not drawer_id:
        return await callback.message.edit_text("❌ Сессия истекла.")

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Да, удалить", callback_data="pn_del_yes"),
        types.InlineKeyboardButton(text="❌ Нет", callback_data="pn_v"),
    )
    await callback.message.edit_text(
        "🗑️ <b>Удалить заметку?</b>\n\nЭто действие необратимо.",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "pn_del_yes")
@allowed_callback
async def cb_pn_delete_execute(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    drawer_id = _active_drawer.pop(uid, None)
    if not drawer_id:
        return await callback.message.edit_text("❌ Сессия истекла.")

    await callback.message.edit_text("🗑️ Удаляю...")
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_delete_drawer", {"drawer_id": drawer_id})
        result = json.loads(raw) if raw else {}
        if result.get("success"):
            _list_state.pop(uid, None)
            await callback.message.edit_text("✅ Заметка удалена.", reply_markup=None)
        else:
            await callback.message.edit_text(f"❌ Ошибка: {raw[:200]}")
    except Exception as e:
        logger.error(f"Delete note error: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")


async def _save_quote_to_palace(uid: int, quote_text: str, answer_func):
    data = _quote_waiting.pop(uid, None)
    if not data:
        return
    from handlers.palace import _save_state, _show_save_wings

    _save_state[uid] = {
        "text": quote_text.strip(),
        "mode": "full",
        "wing": "",
        "room": "",
        "wings": [],
        "rooms": [],
    }
    status = await answer_func("💬 Цитата получена. Выберите куда сохранить...")
    await _show_save_wings(status.edit_text, uid)
