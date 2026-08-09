"""handlers/brainstorm.py — 🧠 Штурм: генерация идей с контекстом базы знаний.

Точки входа:
  /штурм <тема>      — сразу генерация идей
  Кнопка «🧠 Штурм»  — бот просит ввести тему (ожидание в _storm_waiting)

Пайплайн: детерминированный сбор контекста (notes + дворец + KG) →
один вызов модели → JSON-парсинг (services.brainstorm) → кнопки выбора
идеи → мост в существующий save-флоу Дворца (handlers.palace.save).
"""

import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback, allowed_only
from services import brainstorm as bs
from services.ai_engine import get_ai_response_async, get_current_ai
from services.text_formatter import safe_html_format
from services.ttl_dict import TtlDict

logger = logging.getLogger("BrainstormHandler")

router = Router()

_storm_waiting: TtlDict = TtlDict()
_storm_data: TtlDict = TtlDict()


async def _status_edit(status_msg, text: str):
    try:
        await status_msg.edit_text(f"🧠 {safe_html_format(text)}", parse_mode="HTML")
    except Exception as e:  # noqa: BLE001 — edit может упасть (429 и т.п.)
        logger.warning("[STORM] status edit failed: %s", e)


async def run_storm(uid: int, status_msg, topic: str):
    """Основной пайплайн: контекст → модель → идеи → кнопки выбора."""
    topic = (topic or "").strip()
    if not topic:
        await _status_edit(status_msg, "Тема не задана. Используйте: /штурм <тема>")
        return

    try:
        await _status_edit(status_msg, "🔍 Собираю контекст базы знаний…")
        context = await bs.collect_context(topic)

        await _status_edit(status_msg, "💭 Генерирую идеи…")
        engine, model = get_current_ai()
        msgs = [
            {"role": "system", "content": bs.STORM_SYSTEM_PROMPT},
            {"role": "user", "content": bs.build_storm_prompt(topic, context)},
        ]
        raw = await get_ai_response_async(engine, model, msgs)

        ideas = bs.parse_ideas(raw)
    except Exception as exc:  # noqa: BLE001 — показываем пользователю текст ошибки
        logger.error("[STORM] run failed: %s", exc, exc_info=True)
        await _status_edit(status_msg, f"❌ Ошибка штурма: {exc}")
        return

    _storm_data[uid] = {
        "topic": topic,
        "context": context,
        "ideas": ideas,
    }

    kb = InlineKeyboardBuilder()
    row = []
    for i in range(1, len(ideas) + 1):
        row.append(types.InlineKeyboardButton(
            text=f"💡 {i}", callback_data=f"bs_pick:{i}",
        ))
        if len(row) == 3:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    if len(ideas) > 1:
        kb.row(types.InlineKeyboardButton(
            text="💾 Сохранить все", callback_data="bs_all",
        ))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="bs_cancel"))

    text = bs.format_ideas_text(topic, ideas)
    try:
        await status_msg.edit_text(
            text, parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[STORM] show ideas failed: %s", exc)


# ─── /штурм <тема> ───


@router.message(Command("штурм"))
@allowed_only
async def cmd_storm(message: types.Message):
    topic = ((message.text or "")[len("/штурм"):]).lstrip()
    if not topic:
        _storm_waiting[message.from_user.id] = True
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="bs_cancel"))
        await message.answer(
            "🧠 <b>Штурм</b>\n\n"
            "Введите тему для генерации идей.\n"
            "Бот соберёт контекст из ваших заметок, записей Дворца и графа знаний.",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        return
    status = await message.answer("🧠 Запускаю штурм…")
    await run_storm(message.from_user.id, status, topic)


@router.message(F.text == "🧠 Штурм")
@allowed_only
async def btn_storm(message: types.Message):
    _storm_waiting[message.from_user.id] = True
    await message.answer(
        "🧠 <b>Штурм</b>\n\nВведите тему для генерации идей.",
        parse_mode="HTML",
    )


# ─── Выбор идеи / сохранение ───


async def _storm_confirm(uid: int, edit_func, selected: list[dict], label: str):
    """Показывает превью выбранных идей и уводит в save-флоу Дворца."""
    text = bs.ideas_to_text(selected)
    preview = (
        f"💾 <b>Сохранить в Дворец?</b>\n\n"
        f"{safe_html_format(text)}"
    )
    data = _storm_data.get(uid) or {}
    linked = bs.find_linked(text, data.get("context", {}))
    if linked:
        preview += "\n\n" + bs.format_linked(linked)
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Сохранить", callback_data="bs_save"))
    kb.row(
        types.InlineKeyboardButton(
            text="\u25c0\ufe0f К идеям", callback_data="bs_back",
        ),
    )
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="bs_cancel"))
    _storm_data[uid]["pending"] = {"text": text, "label": label}
    await edit_func(preview, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("bs_pick:"))
@allowed_callback
async def cb_pick_idea(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    if not data:
        return await cb.message.edit_text("❌ Сессия истекла. Начните /штурм заново.")
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        idx = 0
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        return await cb.message.edit_text("❌ Идея не найдена. Начните /штурм заново.")
    await _storm_confirm(uid, cb.message.edit_text, [ideas[idx - 1]], f"Идея {idx}")


@router.callback_query(F.data == "bs_all")
@allowed_callback
async def cb_save_all(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    if not data:
        return await cb.message.edit_text("❌ Сессия истекла. Начните /штурм заново.")
    await _storm_confirm(uid, cb.message.edit_text, data.get("ideas", []), "Все идеи")


@router.callback_query(F.data == "bs_back")
@allowed_callback
async def cb_back_to_ideas(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    if not data:
        return await cb.message.edit_text("❌ Сессия истекла. Начните /штурм заново.")
    ideas = data.get("ideas", [])
    kb = InlineKeyboardBuilder()
    row = []
    for i in range(1, len(ideas) + 1):
        row.append(types.InlineKeyboardButton(
            text=f"💡 {i}", callback_data=f"bs_pick:{i}",
        ))
        if len(row) == 3:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    if len(ideas) > 1:
        kb.row(types.InlineKeyboardButton(
            text="💾 Сохранить все", callback_data="bs_all",
        ))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="bs_cancel"))
    await cb.message.edit_text(
        bs.format_ideas_text(data.get("topic", ""), ideas),
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "bs_save")
@allowed_callback
async def cb_confirm_save(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    pending = (data or {}).get("pending")
    if not data or not pending:
        return await cb.message.edit_text("❌ Сессия истекла. Начните /штурм заново.")
    _storm_data.pop(uid, None)
    _storm_waiting.pop(uid, None)

    from handlers.palace import _save_state, _show_save_wings

    _save_state[uid] = {
        "text": pending["text"],
        "mode": "full",
        "wing": "",
        "room": "",
        "wings": [],
        "rooms": [],
    }
    await cb.message.edit_text("⏳ Загружаю крылья…")
    await _show_save_wings(cb.message.edit_text, uid)


@router.callback_query(F.data == "bs_cancel")
@allowed_callback
async def cb_cancel(cb: types.CallbackQuery):
    await cb.answer()
    _storm_data.pop(cb.from_user.id, None)
    _storm_waiting.pop(cb.from_user.id, None)
    try:
        await cb.message.edit_text("❌ Отменено.")
    except Exception:  # noqa: BLE001 — сообщение может быть удалено
        pass
