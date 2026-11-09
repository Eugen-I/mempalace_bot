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
    COPILOT_STYLES,
    append_styles_to_summary,
    format_manifesto_card,
    format_styles_selection_card,
    generate_initial_manifesto,
    generate_socratic_reply,
    get_random_style_synergy,
    refine_manifesto,
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


def build_styles_selection_kb(session: CopilotSession) -> types.InlineKeyboardMarkup:
    """Интерактивная клавиатура стилистического конструктора."""
    builder = InlineKeyboardBuilder()

    style_btns = []
    for name, info in COPILOT_STYLES.items():
        is_sel = name in session.selected_styles
        mark = "✅ " if is_sel else ""
        btn_text = f"{mark}{info['icon']} {name}"
        style_btns.append(types.InlineKeyboardButton(
            text=btn_text, callback_data=f"cp_toggle_style:{name}",
        ))

    for i in range(0, len(style_btns), 2):
        builder.row(*style_btns[i:i + 2])

    builder.row(
        types.InlineKeyboardButton(text="🎭 Драма", callback_data="cp_preset:preset_drama"),
        types.InlineKeyboardButton(text="🌫 Живопись", callback_data="cp_preset:preset_pictorial"),
        types.InlineKeyboardButton(text="🏛 Триада", callback_data="cp_preset:preset_triad"),
    )
    builder.row(
        types.InlineKeyboardButton(text="🎲 Синергия", callback_data="cp_preset:random"),
        types.InlineKeyboardButton(text="🧹 Очистить", callback_data="cp_clear_styles"),
    )

    sel_count = len(session.selected_styles)
    if 1 <= sel_count <= 3:
        confirm_text = f"🚀 Подтвердить стили ({sel_count}/3) ➡️"
    else:
        confirm_text = "⚠️ Выберите стили (от 1 до 3)"

    builder.row(
        types.InlineKeyboardButton(text=confirm_text, callback_data="cp_confirm_styles"),
    )
    builder.row(
        types.InlineKeyboardButton(text="↩️ Назад к диалогу", callback_data="cp_back_to_discuss"),
        types.InlineKeyboardButton(text="❌ Сбросить", callback_data="cp_reset"),
    )
    return builder.as_markup()


def build_manifesto_kb(session: CopilotSession) -> types.InlineKeyboardMarkup:
    """Клавиатура соавторства и тональной коррекции манифеста."""
    builder = InlineKeyboardBuilder()

    builder.row(
        types.InlineKeyboardButton(text="🌑 Мрачнее", callback_data="cp_manif_mod:darker"),
        types.InlineKeyboardButton(
            text="🕊 Метафоричнее", callback_data="cp_manif_mod:metaphoric",
        ),
        types.InlineKeyboardButton(text="✂️ Короче", callback_data="cp_manif_mod:shorter"),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🔄 Другой ракурс", callback_data="cp_manif_mod:reroll",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="✅ Утвердить манифест ➡️", callback_data="cp_confirm_manifesto",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(text="↩️ К выбору стилей", callback_data="cp_select_styles"),
        types.InlineKeyboardButton(text="❌ Сбросить", callback_data="cp_reset"),
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

    text = format_styles_selection_card(session)
    kb = build_styles_selection_kb(session)
    await status.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "cp_select_styles", allowed_callback)
async def cb_copilot_select_styles(cb: types.CallbackQuery):
    """Отображение стилистического конструктора."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    session.stage = "styles"
    manager.save_session(session)
    await cb.answer()
    text = format_styles_selection_card(session)
    kb = build_styles_selection_kb(session)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] edit styles card failed: %s", e)


@router.callback_query(F.data.startswith("cp_toggle_style:"), allowed_callback)
async def cb_copilot_toggle_style(cb: types.CallbackQuery):
    """Переключение выбора стиля (чекбокс)."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    style_name = cb.data.split(":", 1)[1].strip()
    if style_name in session.selected_styles:
        session.selected_styles.remove(style_name)
        await cb.answer(f"Снят стиль: {style_name}")
    else:
        if len(session.selected_styles) >= 3:
            await cb.answer("⚠️ Можно выбрать максимум 3 стиля!", show_alert=True)
            return
        session.selected_styles.append(style_name)
        await cb.answer(f"Добавлен: {style_name}")

    manager.save_session(session)
    text = format_styles_selection_card(session)
    kb = build_styles_selection_kb(session)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] toggle style edit failed: %s", e)


@router.callback_query(F.data.startswith("cp_preset:"), allowed_callback)
async def cb_copilot_preset(cb: types.CallbackQuery):
    """Применение готового пресета или случайной синергии стилей."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    preset_key = cb.data.split(":", 1)[1].strip()
    if preset_key == "random":
        session.selected_styles = get_random_style_synergy(count=3)
        await cb.answer("🎲 Сгенерирована случайная синергия!")
    elif preset_key == "preset_drama":
        session.selected_styles = ["Сюрреализм", "Экспрессионизм"]
        await cb.answer("Применен пресет: Драма и тайна")
    elif preset_key == "preset_pictorial":
        session.selected_styles = ["Пиктореализм", "Импрессионизм"]
        await cb.answer("Применен пресет: Живописная элегия")
    elif preset_key == "preset_triad":
        session.selected_styles = ["Сюрреализм", "Экспрессионизм", "Пиктореализм"]
        await cb.answer("Применен пресет: Классическая триада")

    manager.save_session(session)
    text = format_styles_selection_card(session)
    kb = build_styles_selection_kb(session)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] preset edit failed: %s", e)


@router.callback_query(F.data == "cp_clear_styles", allowed_callback)
async def cb_copilot_clear_styles(cb: types.CallbackQuery):
    """Сброс выбора стилей."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    session.selected_styles.clear()
    manager.save_session(session)
    await cb.answer("Выбор стилей очищен")
    text = format_styles_selection_card(session)
    kb = build_styles_selection_kb(session)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] clear styles edit failed: %s", e)


@router.callback_query(F.data == "cp_confirm_styles", allowed_callback)
async def cb_copilot_confirm_styles(cb: types.CallbackQuery):
    """Подтверждение выбора стилей и переход к этапу манифеста."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    if not session.selected_styles:
        await cb.answer("⚠️ Выберите хотя бы 1 стиль для продолжения!", show_alert=True)
        return

    append_styles_to_summary(session)
    session.stage = "manifesto"
    manager.save_session(session)

    await cb.answer("Стили зафиксированы!")
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="✍️ Написать манифест проекта ➡️", callback_data="cp_to_manifesto",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="↩️ Изменить выбор стилей", callback_data="cp_select_styles",
        ),
        types.InlineKeyboardButton(text="❌ Сбросить", callback_data="cp_reset"),
    )

    styles_list_ru = ", ".join(f"<b>{s}</b>" for s in session.selected_styles)
    text = (
        f"🎨 <b>Стилистический синтез утвержден!</b>\n\n"
        f"Выбранные направления: {styles_list_ru}\n\n"
        f"📋 <b>Обновленное концептуальное резюме:</b>\n"
        f"{session.summary}\n\n"
        "<i>Следующий этап: создание и шлифовка художественного манифеста проекта.</i>"
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())


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


# ─── Шаг 9: Обработчики манифеста ───

@router.callback_query(F.data == "cp_to_manifesto", allowed_callback)
async def cb_copilot_to_manifesto(cb: types.CallbackQuery):
    """Генерация или открытие карточки манифеста."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    session.stage = "manifesto"
    manager.save_session(session)

    if not session.manifesto:
        await cb.answer("Формирую манифест...")
        try:
            await cb.message.edit_text(
                "✍️ <i>Арт-директор формулирует авторский манифест проекта…</i>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug("[COPILOT] status edit failed: %s", e)
        await generate_initial_manifesto(session)

    text = format_manifesto_card(session)
    kb = build_manifesto_kb(session)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] to manifesto edit failed: %s", e)


@router.callback_query(F.data.startswith("cp_manif_mod:"), allowed_callback)
async def cb_copilot_manif_mod(cb: types.CallbackQuery):
    """Коррекция тональности манифеста (darker, metaphoric, shorter, reroll)."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    instruction = cb.data.split(":", 1)[1].strip()
    await cb.answer("Переписываю манифест…")
    try:
        await cb.message.edit_text(
            "✍️ <i>Шлифую манифест проекта…</i>", parse_mode="HTML",
        )
    except Exception as e:
        logger.debug("[COPILOT] refine status edit failed: %s", e)

    await refine_manifesto(session, instruction)
    text = format_manifesto_card(session)
    kb = build_manifesto_kb(session)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] refine manifesto edit failed: %s", e)


@router.callback_query(F.data == "cp_confirm_manifesto", allowed_callback)
async def cb_copilot_confirm_manifesto(cb: types.CallbackQuery):
    """Утверждение манифеста и переход к этапу технического сетапа."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    session.stage = "tech"
    manager.save_session(session)
    await cb.answer("Манифест утвержден!")

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="📷 Параметры съемки и арсенал X-T4 ➡️", callback_data="cp_to_tech",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="↩️ Редактировать манифест", callback_data="cp_to_manifesto",
        ),
        types.InlineKeyboardButton(text="❌ Сбросить", callback_data="cp_reset"),
    )

    text = (
        f"📜 <b>Манифест успешно утвержден!</b>\n\n"
        f"<blockquote>{safe_html_format(session.manifesto)}</blockquote>\n\n"
        "<i>Следующий этап: выбор оптики, расчет выдержки/диафрагмы "
        "и учет условий съемки под Fujifilm X-T4.</i>"
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())


async def handle_copilot_text_message(message: types.Message) -> bool:
    """Обработчик входящего текста/голоса внутри активных этапов копайлота."""
    uid = message.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)

    if not session or session.is_paused:
        return False

    user_text = (message.text or "").strip()
    if not user_text:
        return False

    if session.stage == "discuss":
        status_msg = await message.answer(
            "💭 <i>Арт-директор обдумывает мысль…</i>", parse_mode="HTML",
        )
        reply = await generate_socratic_reply(session, user_text)
        kb = build_copilot_dialogue_kb(session)

        text = f"🎙 <b>Арт-директор:</b>\n\n{safe_html_format(reply)}"
        try:
            await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning("[COPILOT] edit reply failed: %s", e)
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return True

    if session.stage == "manifesto":
        status_msg = await message.answer(
            "✍️ <i>Переписываю манифест с учетом ваших пожеланий…</i>", parse_mode="HTML",
        )
        await refine_manifesto(session, user_text)
        text = format_manifesto_card(session)
        kb = build_manifesto_kb(session)
        try:
            await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning("[COPILOT] edit manifesto failed: %s", e)
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return True

    return False
