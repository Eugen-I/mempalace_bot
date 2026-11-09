"""handlers/copilot.py — Telegram-интерфейс арт-копайлота (Creative Co-Pilot).

Управляет:
- Командами /copilot и /копайлот
- Сократическим диалогом арт-директора с пользователем
- Инлайн-кнопками управления сессией (Переход к стилям, Пауза, Сброс)
- Перехватом текстовых и голосовых сообщений внутри сессии
"""

from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback, allowed_only
from services.copilot_engine import (
    generate_socratic_reply,
    start_copilot_discussion,
    summarize_creative_dialogue,
)
from services.copilot_session import CopilotSession, get_copilot_manager
from services.text_formatter import safe_html_format

logger = logging.getLogger("CopilotHandler")

router = Router()


def build_copilot_dialogue_kb(session: CopilotSession) -> types.InlineKeyboardMarkup:
    """Клавиатура управления Сократическим диалогом."""
    builder = InlineKeyboardBuilder()

    # Если было хотя бы 2 реплики, можно перейти к выбору стилей
    user_turns = sum(1 for m in session.dialogue_history if m.get("role") == "user")
    if user_turns >= 1:
        builder.row(
            types.InlineKeyboardButton(
                text="🎨 Перейти к выбору стилей ➡️",
                callback_data="cp_to_styles",
            ),
        )

    builder.row(
        types.InlineKeyboardButton(
            text="⏸ Пауза",
            callback_data="cp_pause",
        ),
        types.InlineKeyboardButton(
            text="❌ Сбросить",
            callback_data="cp_reset",
        ),
    )
    return builder.as_markup()


@router.message(Command("copilot", "копайлот"))
@allowed_only
async def cmd_copilot(message: types.Message):
    """Точка входа: /copilot <тема проекта>."""
    uid = message.from_user.id
    manager = get_copilot_manager()
    args = (message.text or "").partition(" ")[2].strip()

    # Проверяем, есть ли уже активная или приостановленная сессия
    existing = manager.get_session(uid)

    if not args:
        if existing and not existing.stage == "completed":
            builder = InlineKeyboardBuilder()
            builder.row(
                types.InlineKeyboardButton(text="▶️ Продолжить проект", callback_data="cp_resume"),
                types.InlineKeyboardButton(text="🔄 Начать новый", callback_data="cp_new_prompt"),
            )
            stage_ru = {
                "discuss": "Осмысление темы",
                "styles": "Выбор стилей",
                "manifesto": "Манифест",
                "tech": "Параметры съемки",
                "variants": "Выбор концепта",
            }.get(existing.stage, existing.stage)

            await message.answer(
                f"🎙 <b>Арт-копайлот</b>\n\n"
                f"У вас есть незавершенный проект: «<b>{safe_html_format(existing.topic)}</b>»\n"
                f"Текущий этап: <i>{stage_ru}</i>\n\n"
                "Хотите продолжить или начать новый проект?",
                parse_mode="HTML",
                reply_markup=builder.as_markup(),
            )
            return

        await message.answer(
            "🎙 <b>Арт-копайлот: Соавторство фотопроекта</b>\n\n"
            "Задайте тему или художественный замысел проекта:\n"
            "<code>/copilot Архитипы Юнга в обычной жизни</code>\n\n"
            "<i>Вы сможете обсудить идею с арт-директором, подобрать стили "
            "и параметры съемки X-T4.</i>",
            parse_mode="HTML",
        )
        return

    # Запуск новой сессии с заданной темой
    session = manager.create_or_replace_session(uid, args)
    status_msg = await message.answer("🧠 <i>Арт-директор изучает тему…</i>", parse_mode="HTML")

    opening = await start_copilot_discussion(session)
    kb = build_copilot_dialogue_kb(session)

    header = f"🎙 <b>Арт-копайлот | Тема: «{safe_html_format(session.topic)}»</b>\n\n"
    text = f"{header}{safe_html_format(opening)}"

    try:
        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.warning("[COPILOT] edit status failed: %s", e)
        await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "copilot_start", allowed_callback)
async def cb_copilot_start(cb: types.CallbackQuery):
    """Быстрый запуск копайлота из меню Штурма."""
    await cb.answer()
    if cb.message:
        await cb.message.answer(
            "🎙 <b>Арт-копайлот (Диалоговая лаборатория)</b>\n\n"
            "Введите команду с вашей темой:\n"
            "<code>/copilot Ваша тема</code>\n\n"
            "Или напишите тему прямо в ответ на это сообщение.",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "cp_resume", allowed_callback)
async def cb_copilot_resume(cb: types.CallbackQuery):
    """Возобновление сессии после паузы."""
    await cb.answer("Возобновляем проект")
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.resume_session(uid)

    if not session or not cb.message:
        return

    kb = build_copilot_dialogue_kb(session)
    last_bot_msg = next(
        (m["content"] for m in reversed(session.dialogue_history) if m.get("role") == "assistant"),
        "",
    )
    text = (
        f"🎙 <b>Арт-копайлот | Тема: «{safe_html_format(session.topic)}»</b>\n\n"
        f"<i>На чем мы остановились:</i>\n{safe_html_format(last_bot_msg)}\n\n"
        "Отправьте реплику текстом или голосом:"
    )
    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "cp_pause", allowed_callback)
async def cb_copilot_pause(cb: types.CallbackQuery):
    """Постановка сессии на паузу."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    manager.pause_session(uid)
    await cb.answer("Сессия приостановлена")
    if cb.message:
        await cb.message.answer(
            "⏸ <b>Диалог с арт-директором приостановлен.</b>\n\n"
            "Ваш проект сохранен. Чтобы вернуться к нему позже, введите <code>/copilot</code>.",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "cp_reset", allowed_callback)
async def cb_copilot_reset(cb: types.CallbackQuery):
    """Сброс сессии."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    manager.clear_session(uid)
    await cb.answer("Сессия сброшена")
    if cb.message:
        await cb.message.answer(
            "❌ <b>Сессия арт-копайлота сброшена.</b>\n"
            "Вы можете начать заново: <code>/copilot</code>",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "cp_to_styles", allowed_callback)
async def cb_copilot_to_styles(cb: types.CallbackQuery):
    """Завершение Сократического диалога, суммаризация и переход к этапу стилей."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)

    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    await cb.answer("Формирую концепт...")
    status = await cb.message.answer(
        "✍️ <i>Арт-директор формирует концептуальное резюме…</i>", parse_mode="HTML",
    )

    summary = await summarize_creative_dialogue(session)
    session.summary = summary
    session.stage = "styles"
    manager.save_session(session)

    # Заготовка для следующего шага: вывод саммари и переход к стилям
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🎨 Стилистический конструктор ➡️", callback_data="cp_select_styles",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="↩️ Вернуться к обсуждению", callback_data="cp_back_to_discuss",
        ),
        types.InlineKeyboardButton(text="❌ Сбросить", callback_data="cp_reset"),
    )

    text = (
        f"📋 <b>Концептуальное резюме проекта</b>\n"
        f"Тема: «<b>{safe_html_format(session.topic)}</b>»\n\n"
        f"{summary}\n\n"
        "<i>Следующий шаг: выбор стилей визуального синтеза (1–3 стиля).</i>"
    )
    await status.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "cp_back_to_discuss", allowed_callback)
async def cb_copilot_back_to_discuss(cb: types.CallbackQuery):
    """Возврат к этапу обсуждения темы."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        return
    session.stage = "discuss"
    manager.save_session(session)
    await cb.answer("Возвращаемся к диалогу")
    kb = build_copilot_dialogue_kb(session)
    await cb.message.answer(
        "💬 <b>Продолжаем обсуждение темы.</b> Что еще важно учесть в этом замысле?",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def handle_copilot_text_message(message: types.Message) -> bool:
    """Обработчик входящего текста/голоса, если пользователь находится в активном диалоге копайлота.

    Возвращает True, если сообщение было обработано копайлотом, иначе False.
    """
    uid = message.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)

    if not session or session.is_paused or session.stage != "discuss":
        return False

    user_text = (message.text or "").strip()
    if not user_text:
        return False

    status_msg = await message.answer("💭 <i>Арт-директор обдумывает мысль…</i>", parse_mode="HTML")
    reply = await generate_socratic_reply(session, user_text)
    kb = build_copilot_dialogue_kb(session)

    text = f"🎙 <b>Арт-директор:</b>\n\n{safe_html_format(reply)}"
    try:
        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.warning("[COPILOT] edit reply failed: %s", e)
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

    return True
