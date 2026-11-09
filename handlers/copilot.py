"""handlers/copilot.py — Telegram-интерфейс арт-копайлота (Creative Co-Pilot).

Управляет:
- Командами /copilot и /копайлот
- Сократическим диалогом арт-директора с пользователем
- Инлайн-кнопками управления сессией (Переход к стилям, Пауза, Сброс)
- Перехватом текстовых и голосовых сообщений внутри сессии
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback, allowed_only
from services.copilot_engine import (
    COPILOT_STYLES,
    append_styles_to_summary,
    consult_tech_parameters,
    export_copilot_project_to_apple_notes,
    format_copilot_recipe_card,
    format_manifesto_card,
    format_single_variant_card,
    format_styles_selection_card,
    format_tech_card,
    generate_contrast_variants,
    generate_field_assistant_checklist,
    generate_initial_manifesto,
    generate_midjourney_prompt,
    generate_socratic_reply,
    get_or_create_fuji_recipe,
    get_random_style_synergy,
    init_tech_preferences,
    refine_active_variant,
    refine_manifesto,
    start_copilot_discussion,
    summarize_creative_dialogue,
    update_tech_preference,
)
from services.fuji_recipes import (
    export_fuji_recipe_to_apple_notes,
    format_fuji_recipe_card,
    generate_surreal_stochastic_recipe,
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


def build_tech_kb(session: CopilotSession) -> types.InlineKeyboardMarkup:
    """Интерактивная клавиатура технического сетапа и арсенала."""
    tech = session.tech_preferences or {}
    support = tech.get("support", "")
    lens = tech.get("lens", "")
    filter_acc = tech.get("filter_accessory", "")
    lighting = tech.get("lighting", "")

    builder = InlineKeyboardBuilder()

    # Ряд 1: Метод съемки (С рук vs Штатив)
    is_handheld = "рук" in support.lower()
    builder.row(
        types.InlineKeyboardButton(
            text=f"{'✅' if is_handheld else '▫️'} 👐 С рук (ICM)",
            callback_data="cp_tech:support:handheld",
        ),
        types.InlineKeyboardButton(
            text=f"{'✅' if not is_handheld else '▫️'} 🔭 Штатив",
            callback_data="cp_tech:support:tripod",
        ),
    )

    # Ряд 2: Объектив (Гелиос vs Fuji)
    is_helios = "гелиос" in lens.lower() or "helios" in lens.lower()
    builder.row(
        types.InlineKeyboardButton(
            text=f"{'✅' if is_helios else '▫️'} 🌀 Гелиос 44-2",
            callback_data="cp_tech:lens:helios",
        ),
        types.InlineKeyboardButton(
            text=f"{'✅' if not is_helios else '▫️'} 📷 XF 18-55mm",
            callback_data="cp_tech:lens:fuji",
        ),
    )

    # Ряд 3: Фильтр / Призма
    is_mist = "mist" in filter_acc.lower()
    is_prism = "призм" in filter_acc.lower()
    builder.row(
        types.InlineKeyboardButton(
            text=f"{'✅' if is_mist else '▫️'} 🔮 Pro-Mist",
            callback_data="cp_tech:filter:mist",
        ),
        types.InlineKeyboardButton(
            text=f"{'✅' if is_prism else '▫️'} 💎 Призма",
            callback_data="cp_tech:filter:prism",
        ),
        types.InlineKeyboardButton(
            text=f"{'✅' if not is_mist and not is_prism else '▫️'} 🚫 Без",
            callback_data="cp_tech:filter:none",
        ),
    )

    # Ряд 4: Свет
    is_backlight = "контровой" in lighting.lower()
    is_flash = "импульс" in lighting.lower() or "лезвие" in lighting.lower()
    builder.row(
        types.InlineKeyboardButton(
            text=f"{'✅' if is_backlight else '▫️'} 💡 Контровой",
            callback_data="cp_tech:light:backlight",
        ),
        types.InlineKeyboardButton(
            text=f"{'✅' if is_flash else '▫️'} ⚡️ Импульс",
            callback_data="cp_tech:light:flash",
        ),
        types.InlineKeyboardButton(
            text=f"{'✅' if not is_backlight and not is_flash else '▫️'} 🕯 Рассеянный",
            callback_data="cp_tech:light:ambient",
        ),
    )

    # Ряд 5: Переход к генерации вариантов проектов (CP-5)
    builder.row(
        types.InlineKeyboardButton(
            text="🚀 Сгенерировать варианты проектов (CP-5) ➡️",
            callback_data="cp_confirm_tech",
        ),
    )

    # Ряд 6: Навигация
    builder.row(
        types.InlineKeyboardButton(
            text="↩️ К манифесту", callback_data="cp_to_manifesto",
        ),
        types.InlineKeyboardButton(text="❌ Сбросить", callback_data="cp_reset"),
    )

    return builder.as_markup()


def build_variants_kb(
    session: CopilotSession, active_idx: int = 0,
) -> types.InlineKeyboardMarkup:
    """Клавиатура просмотра и выбора из 2-3 вариантов проектов."""
    projects = session.candidate_projects or []
    total = len(projects)
    builder = InlineKeyboardBuilder()

    # Ряд 1: Вкладки проектов
    tabs = []
    for i in range(total):
        is_active = (i == active_idx)
        is_picked = (session.selected_project_idx == i)
        prefix = "⭐️ " if is_picked else ("🔹 " if is_active else "▫️ ")
        tabs.append(types.InlineKeyboardButton(
            text=f"{prefix}Вариант {i + 1}",
            callback_data=f"cp_view_var:{i}",
        ))
    if tabs:
        builder.row(*tabs)

    # Ряд 2: Кнопка выбора активного варианта
    is_already_picked = (session.selected_project_idx == active_idx)
    pick_text = (
        "✅ Этот проект уже выбран 🎯"
        if is_already_picked
        else f"⭐️ Выбрать Проект №{active_idx + 1} как главный 🎯"
    )
    builder.row(
        types.InlineKeyboardButton(
            text=pick_text,
            callback_data=f"cp_pick_var:{active_idx}",
        ),
    )

    # Ряд 3: Реролл / генерация новых вариантов
    builder.row(
        types.InlineKeyboardButton(
            text="🔄 Сгенерировать другие 3 варианта",
            callback_data="cp_reroll_var",
        ),
    )

    # Ряд 4: Навигация
    builder.row(
        types.InlineKeyboardButton(text="↩️ К параметрам съемки", callback_data="cp_to_tech"),
        types.InlineKeyboardButton(text="❌ Сбросить", callback_data="cp_reset"),
    )

    return builder.as_markup()


def build_field_assistant_kb(session: CopilotSession) -> types.InlineKeyboardMarkup:
    """Клавиатура полевого ассистента: рецепт камеры, промпт, экспорт в Apple Notes, завершение."""
    builder = InlineKeyboardBuilder()

    builder.row(
        types.InlineKeyboardButton(
            text="🎛 Внутрикамерный рецепт (слот C1)",
            callback_data="cp_recipe_view:C1",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🎨 Промпт для Midjourney / Flux",
            callback_data="cp_gen_mj_prompt",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🍏 Экспорт в Apple Notes [К съемке]",
            callback_data="cp_export_apple_notes",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="↩️ К вариантам проектов", callback_data="cp_to_variants",
        ),
        types.InlineKeyboardButton(
            text="🏁 Завершить сессию", callback_data="cp_finish",
        ),
    )
    return builder.as_markup()


def build_fuji_recipe_kb(slot_name: str = "C1") -> types.InlineKeyboardMarkup:
    """Клавиатура рецепта камеры: слоты C1-C7, Cadavre Exquis, сброс, экспорт."""
    builder = InlineKeyboardBuilder()

    clean_slot = slot_name.upper().strip() if slot_name else "C1"
    if clean_slot not in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
        clean_slot = "C1"

    # Ряд 1: Слоты C1 - C4
    slot_btns_1 = []
    for s in ("C1", "C2", "C3", "C4"):
        label = f"• {s} •" if s == clean_slot else s
        slot_btns_1.append(
            types.InlineKeyboardButton(text=label, callback_data=f"cp_recipe_slot:{s}")
        )
    builder.row(*slot_btns_1)

    # Ряд 2: Слоты C5 - C7
    slot_btns_2 = []
    for s in ("C5", "C6", "C7"):
        label = f"• {s} •" if s == clean_slot else s
        slot_btns_2.append(
            types.InlineKeyboardButton(text=label, callback_data=f"cp_recipe_slot:{s}")
        )
    builder.row(*slot_btns_2)

    # Ряд 3: Роллер сюрреализма Cadavre Exquis
    builder.row(
        types.InlineKeyboardButton(
            text="🎲 Сюрреалистический Cadavre Exquis",
            callback_data=f"cp_recipe_stochastic:{clean_slot}",
        ),
    )

    # Ряд 4: Рецепт проекта, Сохранение в книгу, Экспорт в Apple Notes
    builder.row(
        types.InlineKeyboardButton(
            text="🎯 Рецепт проекта",
            callback_data=f"cp_recipe_reset:{clean_slot}",
        ),
        types.InlineKeyboardButton(
            text="💾 В книгу",
            callback_data=f"cp_recipe_save_book:{clean_slot}",
        ),
        types.InlineKeyboardButton(
            text="🍏 В Apple Notes",
            callback_data=f"cp_recipe_export:{clean_slot}",
        ),
    )

    # Ряд 5: Возврат к полевому чек-листу
    builder.row(
        types.InlineKeyboardButton(
            text="📋 К полевому чек-листу",
            callback_data="cp_to_field_assistant",
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
        if existing:
            builder = InlineKeyboardBuilder()
            if existing.stage == "completed":
                builder.row(
                    types.InlineKeyboardButton(
                        text="📋 Полевой ассистент", callback_data="cp_to_field_assistant",
                    ),
                    types.InlineKeyboardButton(
                        text="🔄 Начать новый", callback_data="cp_new_prompt",
                    ),
                )
                stage_ru = "Финализирован [К съемке]"
            else:
                builder.row(
                    types.InlineKeyboardButton(
                        text="▶️ Продолжить проект", callback_data="cp_resume",
                    ),
                    types.InlineKeyboardButton(
                        text="🔄 Начать новый", callback_data="cp_new_prompt",
                    ),
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
                f"У вас есть проект: «<b>{safe_html_format(existing.topic)}</b>»\n"
                f"Текущий статус: <i>{stage_ru}</i>\n\n"
                "Хотите открыть материалы или начать новый проект?",
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


# ─── Шаг 10: Обработчики технического сетапа и арсенала ───

@router.callback_query(F.data == "cp_to_tech", allowed_callback)
async def cb_copilot_to_tech(cb: types.CallbackQuery):
    """Открытие экрана съемочных параметров и арсенала X-T4."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    session.stage = "tech"
    if not session.tech_preferences:
        init_tech_preferences(session)
    manager.save_session(session)

    text = format_tech_card(session)
    kb = build_tech_kb(session)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] to tech edit failed: %s", e)


@router.callback_query(F.data.startswith("cp_tech:"), allowed_callback)
async def cb_copilot_tech_toggle(cb: types.CallbackQuery):
    """Быстрое переключение параметров съемки (поддержка, объектив, фильтр, свет)."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    parts = cb.data.split(":", 2)
    if len(parts) == 3:
        _, key, val = parts
        update_tech_preference(session, key, val)

    await cb.answer("Параметры обновлены")
    text = format_tech_card(session)
    kb = build_tech_kb(session)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] tech toggle edit failed: %s", e)


@router.callback_query(F.data == "cp_confirm_tech", allowed_callback)
async def cb_copilot_confirm_tech(cb: types.CallbackQuery):
    """Утверждение технических параметров и переход к генерации вариантов проектов."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    session.stage = "variants"
    manager.save_session(session)
    await cb.answer("Съемочный сетап зафиксирован!")

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="🎲 Создать 2–3 контрастных проекта (CP-5) ➡️",
            callback_data="cp_to_variants",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="↩️ К параметрам съемки", callback_data="cp_to_tech",
        ),
        types.InlineKeyboardButton(text="❌ Сбросить", callback_data="cp_reset"),
    )

    tech = session.tech_preferences or {}
    text = (
        f"⚙️ <b>Съемочный сетап утвержден!</b>\n\n"
        f"📷 Камера: <b>{safe_html_format(tech.get('camera', 'Fujifilm X-T4'))}</b>\n"
        f"🔍 Стекло: <b>{safe_html_format(tech.get('lens', ''))}</b>\n"
        f"👐 Метод: <b>{safe_html_format(tech.get('support', ''))}</b>\n"
        f"⏱ Выдержка/диафрагма: <code>{safe_html_format(tech.get('shutter_speed', ''))}</code>, "
        f"<code>{safe_html_format(tech.get('aperture', ''))}</code>, "
        f"<code>{safe_html_format(tech.get('film_sim', ''))}</code>\n\n"
        "<i>Следующий этап: контрастная дивергенция 2–3 вариантов проектов (Шаг 11 / CP-5).</i>"
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())


# ─── Шаг 11: Обработчики вариантов проектов (дивергенция и выбор) ───

@router.callback_query(F.data == "cp_to_variants", allowed_callback)
async def cb_copilot_to_variants(cb: types.CallbackQuery):
    """Генерация или переход к экрану 2-3 контрастных вариантов проектов."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    session.stage = "variants"
    manager.save_session(session)

    if not session.candidate_projects:
        await cb.answer("Генерирую контрастные проекты...")
        try:
            await cb.message.edit_text(
                "🎨 <i>Арт-директор формирует 3 контрастных вектора реализации…</i>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug("[COPILOT] variants status edit failed: %s", e)
        await generate_contrast_variants(session)

    active_idx = (
        session.selected_project_idx
        if session.selected_project_idx is not None
        else 0
    )
    text = format_single_variant_card(session, idx=active_idx)
    kb = build_variants_kb(session, active_idx=active_idx)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] to variants edit failed: %s", e)


@router.callback_query(F.data.startswith("cp_view_var:"), allowed_callback)
async def cb_copilot_view_variant(cb: types.CallbackQuery):
    """Переключение просмотра между вариантами проектов."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    idx_str = cb.data.split(":", 1)[1]
    try:
        idx = int(idx_str)
    except ValueError:
        idx = 0

    text = format_single_variant_card(session, idx=idx)
    kb = build_variants_kb(session, active_idx=idx)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] view variant edit failed: %s", e)
    await cb.answer()


@router.callback_query(F.data.startswith("cp_pick_var:"), allowed_callback)
async def cb_copilot_pick_variant(cb: types.CallbackQuery):
    """Утверждение одного из проектов как главного (переход к финализации)."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    idx_str = cb.data.split(":", 1)[1]
    try:
        idx = int(idx_str)
    except ValueError:
        idx = 0

    session.selected_project_idx = idx
    session.stage = "completed"
    manager.save_session(session)
    await cb.answer(f"Проект №{idx + 1} выбран!")

    projects = session.candidate_projects or []
    chosen = projects[idx] if idx < len(projects) else {}

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="📋 Полевой ассистент и экспорт (CP-6) ➡️",
            callback_data="cp_to_field_assistant",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="↩️ К списку вариантов", callback_data=f"cp_view_var:{idx}",
        ),
        types.InlineKeyboardButton(text="❌ Сбросить", callback_data="cp_reset"),
    )

    text = (
        f"🎉 <b>Проект №{idx + 1} «{safe_html_format(chosen.get('title', ''))}» утвержден!</b>\n\n"
        f"🎯 <b>Вектор:</b> <i>{safe_html_format(chosen.get('vector', ''))}</i>\n"
        f"📷 <b>Сетап:</b> <code>{safe_html_format(chosen.get('camera_setup', ''))}</code>\n\n"
        f"🖼 <b>Главный кадр:</b>\n"
        f"<blockquote>{safe_html_format(chosen.get('visual_hook', ''))}</blockquote>\n\n"
        "<i>Проект готов к финализации: полевой шпаргалке, Midjourney-эскизам "
        "и выгрузке в Apple Notes (Шаг 12).</i>"
    )
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        logger.debug("[COPILOT] pick variant edit failed: %s", e)


@router.callback_query(F.data == "cp_reroll_var", allowed_callback)
async def cb_copilot_reroll_variants(cb: types.CallbackQuery):
    """Повторная генерация других вариантов проектов."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    await cb.answer("Перегенерирую проекты...")
    try:
        await cb.message.edit_text(
            "🔄 <i>Генерирую новые контрастные векторы проектов…</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.debug("[COPILOT] reroll edit status failed: %s", e)

    session.candidate_projects = []
    session.selected_project_idx = None
    await generate_contrast_variants(session)

    text = format_single_variant_card(session, idx=0)
    kb = build_variants_kb(session, active_idx=0)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] reroll variants view failed: %s", e)


@router.callback_query(F.data == "cp_to_field_assistant", allowed_callback)
async def cb_copilot_to_field_assistant(cb: types.CallbackQuery):
    """Экран полевого ассистента (карманная шпаргалка на съемку)."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    session.stage = "completed"
    manager.save_session(session)
    await cb.answer()

    text = generate_field_assistant_checklist(session)
    kb = build_field_assistant_kb(session)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] field assistant edit failed: %s", e)


@router.callback_query(F.data == "cp_gen_mj_prompt", allowed_callback)
async def cb_copilot_gen_mj_prompt(cb: types.CallbackQuery):
    """Генерация и отображение промпта для Midjourney / Flux."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    await cb.answer("Генерирую эскизный промпт...")
    text = generate_midjourney_prompt(session)

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="📋 К полевому чек-листу", callback_data="cp_to_field_assistant",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🍏 Экспорт в Apple Notes [К съемке]",
            callback_data="cp_export_apple_notes",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="↩️ К вариантам проектов", callback_data="cp_to_variants",
        ),
    )

    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        logger.debug("[COPILOT] mj prompt edit failed: %s", e)


@router.callback_query(F.data == "cp_export_apple_notes", allowed_callback)
async def cb_copilot_export_apple_notes(cb: types.CallbackQuery):
    """Экспорт утвержденного проекта в Apple Notes в папку «Фотопроекты»."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    try:
        note_id = export_copilot_project_to_apple_notes(session, folder="Фотопроекты")
        logger.info("[COPILOT] Заметка создана: %s", note_id)
        await cb.answer(
            "✅ Проект успешно экспортирован в Apple Notes "
            "(папка «Фотопроекты», статус [К съемке])!",
            show_alert=True,
        )
    except Exception as exc:
        logger.error("[COPILOT] Ошибка экспорта в Apple Notes: %s", exc)
        await cb.answer(
            "⚠️ Не удалось создать заметку в Apple Notes. "
            "Убедитесь, что приложение запущено на macOS.",
            show_alert=True,
        )


@router.callback_query(F.data == "cp_finish", allowed_callback)
async def cb_copilot_finish(cb: types.CallbackQuery):
    """Завершение сессии арт-копайлота с поздравлением и очисткой."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия уже завершена")
        return

    topic = session.topic
    manager.clear_session(uid)
    await cb.answer("Сессия успешно завершена!")

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="🎙 Новый арт-копайлот", callback_data="copilot_start",
        ),
    )

    farewell = (
        f"🎉 <b>Творческая разработка проекта «{safe_html_format(topic)}» завершена!</b>\n\n"
        "Все идеи, манифест, световые схемы и рецепты для Fujifilm X-T4 "
        "готовы к реализации на локации.\n\n"
        "<i>Удачных кадров и чистого визуального выражения!</i>\n\n"
        "Чтобы запустить новый проект, введите:\n"
        "<code>/copilot &lt;ваша тема&gt;</code>"
    )
    try:
        await cb.message.edit_text(farewell, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        logger.debug("[COPILOT] finish edit failed: %s", e)


@router.callback_query(F.data.startswith("cp_recipe_view:"), allowed_callback)
async def cb_copilot_recipe_view(cb: types.CallbackQuery):
    """Отображение карточки внутрикамерного рецепта камеры в выбранном слоте C1-C7."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    slot = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else "C1"
    text = format_copilot_recipe_card(session, slot_name=slot)
    kb = build_fuji_recipe_kb(slot_name=slot)

    await cb.answer()
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] recipe view edit failed: %s", e)


@router.callback_query(F.data.startswith("cp_recipe_slot:"), allowed_callback)
async def cb_copilot_recipe_slot(cb: types.CallbackQuery):
    """Переключение целевого пользовательского слота камеры (C1–C7)."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    slot = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else "C1"
    text = format_copilot_recipe_card(session, slot_name=slot)
    kb = build_fuji_recipe_kb(slot_name=slot)

    await cb.answer(f"Слот {slot}")
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] recipe slot edit failed: %s", e)


@router.callback_query(F.data.startswith("cp_recipe_stochastic:"), allowed_callback)
async def cb_copilot_recipe_stochastic(cb: types.CallbackQuery):
    """Генерация стохастического сюрреалистического рецепта Cadavre Exquis."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    slot = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else "C1"
    recipe = get_or_create_fuji_recipe(session, stochastic=True, intensity="wild")
    text = format_fuji_recipe_card(recipe, slot_name=slot)
    kb = build_fuji_recipe_kb(slot_name=slot)

    await cb.answer(f"🎲 Cadavre Exquis: {recipe.recipe_name[:30]}")
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] recipe stochastic edit failed: %s", e)


@router.callback_query(F.data.startswith("cp_recipe_reset:"), allowed_callback)
async def cb_copilot_recipe_reset(cb: types.CallbackQuery):
    """Сброс к каноническому рецепту под выбранную стилистику проекта."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    slot = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else "C1"
    tech = session.tech_preferences or {}
    tech.pop("fuji_recipe", None)
    session.tech_preferences = tech
    manager.save_session(session)

    recipe = get_or_create_fuji_recipe(session, stochastic=False)
    text = format_fuji_recipe_card(recipe, slot_name=slot)
    kb = build_fuji_recipe_kb(slot_name=slot)

    await cb.answer("🎯 Рецепт сброшен к стилистике проекта")
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.debug("[COPILOT] recipe reset edit failed: %s", e)


@router.callback_query(F.data.startswith("cp_recipe_export:"), allowed_callback)
async def cb_copilot_recipe_export(cb: types.CallbackQuery):
    """Экспорт рецепта камеры в Apple Notes в папку «Фотопроекты»."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session or not cb.message:
        await cb.answer("Сессия не найдена")
        return

    slot = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else "C1"
    recipe = get_or_create_fuji_recipe(session)

    try:
        note_id = export_fuji_recipe_to_apple_notes(
            recipe, slot_name=slot, project_title=session.topic, folder="Фотопроекты",
        )
        logger.info("[COPILOT] Рецепт экспортирован в заметку: %s", note_id)
        await cb.answer(
            f"✅ Рецепт для слота {slot} успешно сохранен в Apple Notes (папка «Фотопроекты»)!",
            show_alert=True,
        )
    except Exception as exc:
        logger.error("[COPILOT] Ошибка экспорта рецепта в Apple Notes: %s", exc)
        await cb.answer(
            "⚠️ Не удалось создать заметку с рецептом в Apple Notes.",
            show_alert=True,
        )


@router.callback_query(F.data.startswith("cp_recipe_save_book:"), allowed_callback)
async def cb_copilot_recipe_save_book(cb: types.CallbackQuery):
    """Сохраняет текущий активный рецепт сессии в персистентную книгу рецептов."""
    uid = cb.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)
    if not session:
        await cb.answer("Сессия не найдена", show_alert=True)
        return

    slot = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else "C1"
    recipe = get_or_create_fuji_recipe(session)
    from services.fuji_recipes import save_recipe_to_book

    ok = save_recipe_to_book(recipe, user_id=uid, slot_hint=slot)
    if ok:
        await cb.answer(
            f"✅ Рецепт «{recipe.recipe_name}» сохранён в книгу рецептов!",
            show_alert=True,
        )
    else:
        await cb.answer("❌ Не удалось сохранить рецепт в книгу.", show_alert=True)


def _format_recipe_book_list(
    entries: list[dict[str, Any]],
) -> tuple[str, types.InlineKeyboardMarkup]:
    """Форматирует список сохранённых рецептов книги с интерактивной клавиатурой."""
    builder = InlineKeyboardBuilder()

    if not entries:
        text = (
            "📖 <b>Книга рецептов Fujifilm X-T4 пуста.</b>\n\n"
            "Вы можете сохранять рецепты прямо из «Штурма» или диалогового "
            "копайлота по кнопке «💾 В книгу», а также генерировать "
            "новые сюрреалистические формулы через /cadavre."
        )
        builder.row(
            types.InlineKeyboardButton(
                text="🎲 Сгенерировать Cadavre Exquis",
                callback_data="cp_recipe_standalone_roll:C1",
            ),
        )
        builder.row(
            types.InlineKeyboardButton(
                text="🎙 Начать арт-проект (/copilot)",
                callback_data="copilot_start",
            ),
        )
        return text, builder.as_markup()

    lines = [
        f"📖 <b>Книга рецептов Fujifilm X-T4</b> (сохранено: {len(entries)}):\n"
    ]

    choice_btns: list[types.InlineKeyboardButton] = []
    for idx, entry in enumerate(entries, start=1):
        name = safe_html_format(str(entry.get("recipe_name", f"Рецепт {idx}")))
        film = safe_html_format(str(entry.get("film_simulation", "Classic Chrome")))
        dr = str(entry.get("dynamic_range", "DR200"))
        slot = str(entry.get("slot_hint", "C1"))
        lines.append(f"{idx}. <b>{name}</b> [<code>{slot}</code>]")
        lines.append(f"   <i>{film} | {dr}</i>\n")

        btn_title = f"{idx}. {str(entry.get('recipe_name', f'#{idx}'))[:18]}"
        choice_btns.append(
            types.InlineKeyboardButton(
                text=btn_title,
                callback_data=f"fbook_view:{idx}",
            )
        )

    for i in range(0, len(choice_btns), 2):
        builder.row(*choice_btns[i : i + 2])

    builder.row(
        types.InlineKeyboardButton(
            text="🍏 Экспорт всей книги в Apple Notes",
            callback_data="fbook_export_all",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🎲 Сгенерировать Cadavre Exquis",
            callback_data="cp_recipe_standalone_roll:C1",
        ),
    )
    return "\n".join(lines), builder.as_markup()


@router.message(Command("myrecipes", "книга_рецептов", "recipes"))
@allowed_only
async def cmd_myrecipes(message: types.Message):
    """Точка входа в постоянную «Книгу рецептов фотографа»."""
    uid = message.from_user.id
    from services.fuji_recipes import load_saved_recipe_entries

    entries = load_saved_recipe_entries(user_id=uid)
    text, kb = _format_recipe_book_list(entries)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("fbook_view:"), allowed_callback)
async def cb_fbook_view(cb: types.CallbackQuery):
    """Отображение карточки конкретного рецепта из книги."""
    if not cb.message:
        return
    uid = cb.from_user.id
    idx_str = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else ""
    try:
        idx = int(idx_str)
    except ValueError:
        return

    from services.fuji_recipes import format_fuji_recipe_card, load_saved_recipes

    recipes = load_saved_recipes(user_id=uid)
    if idx < 1 or idx > len(recipes):
        await cb.answer("Рецепт не найден", show_alert=True)
        return

    recipe = recipes[idx - 1]
    slot = f"C{idx}" if idx <= 7 else "C1"
    text = format_fuji_recipe_card(recipe, slot_name=slot)

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="🍏 В Apple Notes",
            callback_data=f"fbook_export_one:{idx}",
        ),
        types.InlineKeyboardButton(
            text="🗑 Удалить из книги",
            callback_data=f"fbook_del:{idx}",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="◀️ К списку рецептов",
            callback_data="fbook_list",
        ),
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("fbook_del:"), allowed_callback)
async def cb_fbook_del(cb: types.CallbackQuery):
    """Удаление рецепта из книги фотографа."""
    if not cb.message:
        return
    uid = cb.from_user.id
    idx_str = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else ""
    try:
        idx = int(idx_str)
    except ValueError:
        return

    from services.fuji_recipes import (
        delete_saved_recipe,
        load_saved_recipe_entries,
        load_saved_recipes,
    )

    recipes = load_saved_recipes(user_id=uid)
    if idx < 1 or idx > len(recipes):
        await cb.answer("Рецепт не найден", show_alert=True)
        return

    recipe = recipes[idx - 1]
    ok = delete_saved_recipe(recipe.recipe_name, user_id=uid)
    if ok:
        await cb.answer(f"🗑 Рецепт «{recipe.recipe_name}» удалён!", show_alert=True)
    else:
        await cb.answer("❌ Ошибка при удалении", show_alert=True)

    entries = load_saved_recipe_entries(user_id=uid)
    text, kb = _format_recipe_book_list(entries)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("fbook_export_one:"), allowed_callback)
async def cb_fbook_export_one(cb: types.CallbackQuery):
    """Экспорт одного рецепта из книги в Apple Notes."""
    uid = cb.from_user.id
    idx_str = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else ""
    try:
        idx = int(idx_str)
    except ValueError:
        return

    from services.fuji_recipes import export_fuji_recipe_to_apple_notes, load_saved_recipes

    recipes = load_saved_recipes(user_id=uid)
    if idx < 1 or idx > len(recipes):
        await cb.answer("Рецепт не найден", show_alert=True)
        return

    recipe = recipes[idx - 1]
    try:
        export_fuji_recipe_to_apple_notes(
            recipe,
            slot_name=f"C{idx}" if idx <= 7 else "C1",
            project_title=recipe.recipe_name,
            folder="Фотопроекты",
        )
        await cb.answer(
            f"✅ Рецепт «{recipe.recipe_name}» экспортирован в Apple Notes (папка «Фотопроекты»)!",
            show_alert=True,
        )
    except Exception as exc:
        logger.warning("[FUJI] Book single export failed: %s", exc)
        await cb.answer("❌ Ошибка экспорта в Apple Notes", show_alert=True)


@router.callback_query(F.data == "fbook_export_all", allowed_callback)
async def cb_fbook_export_all(cb: types.CallbackQuery):
    """Экспорт всей книги рецептов фотографа в Apple Notes."""
    uid = cb.from_user.id
    from services.fuji_recipes import export_recipe_book_to_apple_notes

    ok, note_or_err = export_recipe_book_to_apple_notes(
        user_id=uid, folder="Фотопроекты",
    )
    if ok:
        await cb.answer(
            "✅ Вся книга рецептов экспортирована в Apple Notes (папка «Фотопроекты»)!",
            show_alert=True,
        )
    else:
        await cb.answer(f"❌ {note_or_err}", show_alert=True)


@router.callback_query(F.data == "fbook_list", allowed_callback)
async def cb_fbook_list(cb: types.CallbackQuery):
    """Возврат к полному списку книги рецептов."""
    if not cb.message:
        return
    uid = cb.from_user.id
    from services.fuji_recipes import load_saved_recipe_entries

    entries = load_saved_recipe_entries(user_id=uid)
    text, kb = _format_recipe_book_list(entries)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("cp_recipe_standalone_roll:"), allowed_callback)
async def cb_copilot_recipe_standalone_roll(cb: types.CallbackQuery):
    """Повторный стохастический бросок кубиков Cadavre Exquis вне сессии копайлота."""
    if not cb.message:
        return

    slot = (cb.data or "").split(":")[1] if ":" in (cb.data or "") else "C1"
    recipe = generate_surreal_stochastic_recipe(intensity="wild")
    text = format_fuji_recipe_card(recipe, slot_name=slot)

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="🎲 Еще сюрреалистический рецепт",
            callback_data=f"cp_recipe_standalone_roll:{slot}",
        ),
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🎙 Начать арт-проект (/copilot)", callback_data="copilot_start",
        ),
    )

    await cb.answer(f"🎲 {recipe.recipe_name[:30]}...")
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        logger.debug("[COPILOT] standalone roll edit failed: %s", e)


@router.message(Command("recipe", "рецепт", "fuji", "cadavre"))
@allowed_only
async def cmd_recipe(message: types.Message):
    """Точка входа в рецепты Fujifilm X-T4: вывод рецепта проекта или роллер сюрреализма."""
    uid = message.from_user.id
    manager = get_copilot_manager()
    session = manager.get_session(uid)

    if session:
        slot = "C1"
        text = format_copilot_recipe_card(session, slot_name=slot)
        kb = build_fuji_recipe_kb(slot_name=slot)
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        slot = "C1"
        recipe = generate_surreal_stochastic_recipe(intensity="wild")
        text = format_fuji_recipe_card(recipe, slot_name=slot)

        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(
                text="🎲 Еще сюрреалистический рецепт",
                callback_data=f"cp_recipe_standalone_roll:{slot}",
            ),
        )
        builder.row(
            types.InlineKeyboardButton(
                text="🎙 Начать арт-проект (/copilot)", callback_data="copilot_start",
            ),
        )
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


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

    if session.stage == "tech":
        status_msg = await message.answer(
            "⚙️ <i>Консультируюсь с технологом съемки…</i>", parse_mode="HTML",
        )
        advice = await consult_tech_parameters(session, user_text)
        text = format_tech_card(session, advice=advice)
        kb = build_tech_kb(session)
        try:
            await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning("[COPILOT] edit tech failed: %s", e)
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return True

    if session.stage == "variants":
        status_msg = await message.answer(
            "✍️ <i>Дорабатываю концепцию кадра по вашему пожеланию…</i>",
            parse_mode="HTML",
        )
        active_idx = (
            session.selected_project_idx
            if session.selected_project_idx is not None
            else 0
        )
        await refine_active_variant(session, user_text, idx=active_idx)
        text = format_single_variant_card(session, idx=active_idx)
        kb = build_variants_kb(session, active_idx=active_idx)
        try:
            await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning("[COPILOT] edit variant failed: %s", e)
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return True

    return False
