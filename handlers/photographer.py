"""handlers/photographer.py — арсенал техники и банк фотомеханик в Telegram UI."""

import html
import logging
import os
import tempfile
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback, allowed_only
from services.photo_mechanics import (
    VisualMechanic,
    add_user_mechanic,
    extract_text_from_image,
    format_mechanic_card,
    format_mechanics_list,
    load_mechanics,
    parse_mechanic_from_text,
)
from services.photographer_gear import (
    GearProfile,
    categorize_gear_name,
    enrich_gear_item,
    enrich_gear_profile,
    format_gear_card,
    format_safe_gear_card,
    get_default_gear_profile,
    is_gear_description,
    load_gear_profile,
    parse_gear_description,
    save_gear_profile,
)
from services.ttl_dict import TtlDict

logger = logging.getLogger("PhotographerHandler")

router = Router()

_gear_waiting: TtlDict = TtlDict(ttl=300)
_mech_waiting: TtlDict = TtlDict(ttl=300)
_pending_mechanic: TtlDict = TtlDict(ttl=600)


def _is_gear_waiting(message: types.Message) -> bool:
    uid = getattr(message.from_user, "id", None)
    return bool(uid and uid in _gear_waiting)


def _is_mech_waiting(message: types.Message) -> bool:
    uid = getattr(message.from_user, "id", None)
    return bool(uid and uid in _mech_waiting)


def _gear_menu_kb(profile: GearProfile | None = None) -> InlineKeyboardBuilder:
    prof = profile or load_gear_profile()
    kb = InlineKeyboardBuilder()

    cat_row1 = []
    if prof.cameras:
        cat_row1.append(types.InlineKeyboardButton(
            text=f"📷 Камеры ({len(prof.cameras)})", callback_data="gear_cat_camera"
        ))
    if prof.lenses:
        cat_row1.append(types.InlineKeyboardButton(
            text=f"🔍 Объективы ({len(prof.lenses)})", callback_data="gear_cat_lens"
        ))
    if cat_row1:
        kb.row(*cat_row1)

    cat_row2 = []
    if prof.filters:
        cat_row2.append(types.InlineKeyboardButton(
            text=f"🎞 Фильтры ({len(prof.filters)})", callback_data="gear_cat_filter"
        ))
    if prof.lighting:
        cat_row2.append(types.InlineKeyboardButton(
            text=f"💡 Свет ({len(prof.lighting)})", callback_data="gear_cat_lighting"
        ))
    if prof.accessories:
        cat_row2.append(types.InlineKeyboardButton(
            text=f"🔮 Аксессуары ({len(prof.accessories)})", callback_data="gear_cat_accessory"
        ))
    if cat_row2:
        kb.row(*cat_row2)

    kb.row(
        types.InlineKeyboardButton(text="➕ Добавить технику", callback_data="gear_add"),
        types.InlineKeyboardButton(text="📝 Заполнить списком", callback_data="gear_add_list"),
    )
    kb.row(
        types.InlineKeyboardButton(text="📚 Фотомеханики", callback_data="gear_to_mechanics"),
        types.InlineKeyboardButton(text="🔄 Сброс", callback_data="gear_reset_default"),
    )
    kb.row(
        types.InlineKeyboardButton(text="🔙 В меню Штурма", callback_data="gear_to_storm"),
        types.InlineKeyboardButton(text="❌ Закрыть", callback_data="gear_close"),
    )
    return kb


def _gear_category_kb(category: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="🎒 Все категории", callback_data="gear_open"),
        types.InlineKeyboardButton(text="📚 Фотомеханики", callback_data="gear_to_mechanics"),
    )
    kb.row(
        types.InlineKeyboardButton(text="🔙 В меню Штурма", callback_data="gear_to_storm"),
        types.InlineKeyboardButton(text="❌ Закрыть", callback_data="gear_close"),
    )
    return kb


def _mechanics_menu_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="➕ Добавить фотоприём", callback_data="mech_add"))
    kb.row(
        types.InlineKeyboardButton(text="🎒 Мой арсенал", callback_data="mech_to_gear"),
        types.InlineKeyboardButton(text="🔙 В меню Штурма", callback_data="mech_to_storm"),
    )
    kb.row(types.InlineKeyboardButton(text="❌ Закрыть", callback_data="mech_close"))
    return kb


def _mechanic_preview_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="✅ Сохранить в базу", callback_data="mech_confirm_save"
    ))
    kb.row(types.InlineKeyboardButton(
        text="❌ Отмена", callback_data="mech_cancel"
    ))
    return kb


# ─── Команды и меню арсенала ───


@router.message(Command("gear", "арсенал", ignore_case=True))
@allowed_only
async def cmd_gear(message: types.Message):
    """Показывает карточку арсенала техники пользователя."""
    prof = load_gear_profile()
    text = format_safe_gear_card(prof)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=_gear_menu_kb(prof).as_markup(),
    )


@router.callback_query(F.data == "gear_open")
@allowed_callback
async def cb_gear_open(cb: types.CallbackQuery):
    await cb.answer()
    prof = load_gear_profile()
    text = format_safe_gear_card(prof)
    try:
        await cb.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_gear_menu_kb(prof).as_markup(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GEAR] edit card failed: %s", exc)


@router.callback_query(F.data.startswith("gear_cat_"))
@allowed_callback
async def cb_gear_category(cb: types.CallbackQuery):
    """Показывает подробные карточки техники выбранной категории."""
    await cb.answer()
    cat = (cb.data or "").replace("gear_cat_", "")
    prof = load_gear_profile()
    text = format_safe_gear_card(prof, category=cat)
    try:
        await cb.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_gear_category_kb(cat).as_markup(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GEAR] edit category card failed: %s", exc)


@router.callback_query(F.data == "gear_add")
@allowed_callback
async def cb_gear_add(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _gear_waiting[uid] = True
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="gear_cancel_input"))
    prompt_text = (
        "🎒 <b>Добавление техники в арсенал</b>\n\n"
        "Напишите название камеры, объектива, фильтра или аксессуара.\n"
        "<i>Например: «Гелиос 44-2 58mm f/2» или «Black Pro-Mist 1/4»</i>\n\n"
        "ИИ исследует оптический характер и сохранит технику."
    )
    await cb.message.answer(
        prompt_text,
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "gear_add_list")
@allowed_callback
async def cb_gear_add_list(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _gear_waiting[uid] = "list"
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="gear_cancel_input"))
    prompt_text = (
        "🎒 <b>Заполнение арсенала фотографа списком</b>\n\n"
        "Отправьте полный список вашего оборудования одним сообщением.\n\n"
        "<i>Например:\n"
        "Фотокамера Fujifilm X-T4. Объективы: 1. Pentacon 2.8/29, 2. Kamlan 50mm F1.1...\n"
        "Светофильтр: K&F ND 2-400nd.\n"
        "Фотовспышка Godox V1F.\n"
        "Штатив трёхногий.</i>\n\n"
        "ИИ распознает технику, проведет отдельное исследование для каждого предмета "
        "и заполнит профиль приёмами и ожидаемыми эффектами."
    )
    await cb.message.answer(
        prompt_text,
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "gear_cancel_input")
@allowed_callback
async def cb_gear_cancel_input(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _gear_waiting.pop(uid, None)
    try:
        await cb.message.edit_text("❌ Добавление техники отменено.")
    except Exception as exc:  # noqa: BLE001
        logger.debug("[GEAR] cancel input edit failed: %s", exc)


@router.callback_query(F.data == "gear_reset_default")
@allowed_callback
async def cb_gear_reset_default(cb: types.CallbackQuery):
    await cb.answer("Сброшено к базовому набору")
    prof = get_default_gear_profile()
    save_gear_profile(prof)
    text = format_safe_gear_card(prof)
    try:
        await cb.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_gear_menu_kb(prof).as_markup(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GEAR] reset default failed: %s", exc)


@router.callback_query(F.data.in_(["gear_to_storm", "mech_to_storm"]))
@allowed_callback
async def cb_photographer_back_to_storm(cb: types.CallbackQuery):
    """Возвращает пользователя в главное меню Штурма (шаг назад)."""
    from handlers.brainstorm import cb_storm_menu
    await cb_storm_menu(cb)


@router.callback_query(F.data == "gear_close")
@allowed_callback
async def cb_gear_close(cb: types.CallbackQuery):
    """Шаг назад к меню Штурма при нажатии 'Закрыть' в арсенале."""
    await cb_photographer_back_to_storm(cb)


# ─── Команды и меню фотомеханик ───


@router.message(Command("mechanics", "приемы", ignore_case=True))
@allowed_only
async def cmd_mechanics(message: types.Message):
    """Показывает список доступных фотомеханик."""
    mechs = load_mechanics()
    text = format_mechanics_list(mechs)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=_mechanics_menu_kb().as_markup(),
    )


@router.callback_query(F.data == "mech_open")
@allowed_callback
async def cb_mech_open(cb: types.CallbackQuery):
    await cb.answer()
    mechs = load_mechanics()
    text = format_mechanics_list(mechs)
    try:
        await cb.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_mechanics_menu_kb().as_markup(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[MECH] edit list failed: %s", exc)


@router.callback_query(F.data == "gear_to_mechanics")
@allowed_callback
async def cb_gear_to_mechanics(cb: types.CallbackQuery):
    await cb_mech_open(cb)


@router.callback_query(F.data == "mech_to_gear")
@allowed_callback
async def cb_mech_to_gear(cb: types.CallbackQuery):
    await cb_gear_open(cb)


@router.callback_query(F.data == "mech_add")
@allowed_callback
async def cb_mech_add(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _mech_waiting[uid] = True
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="mech_cancel_input"))
    prompt_text = (
        "🎨 <b>Добавление фотомеханики в базу</b>\n\n"
        "Отправьте <b>текстовое описание</b> приёма с настройками или "
        "<b>скриншот/фотографию</b> настроек съёмки (OCR).\n\n"
        "<i>Бот структурирует выдержку, режим мультиэкспозиции, компенсацию EV "
        "и физику съёмки для использования в штурме.</i>"
    )
    await cb.message.answer(
        prompt_text,
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "mech_cancel_input")
@allowed_callback
async def cb_mech_cancel_input(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _mech_waiting.pop(uid, None)
    try:
        await cb.message.edit_text("❌ Добавление приёма отменено.")
    except Exception as exc:  # noqa: BLE001
        logger.debug("[MECH] cancel input edit failed: %s", exc)


@router.callback_query(F.data == "mech_close")
@allowed_callback
async def cb_mech_close(cb: types.CallbackQuery):
    """Шаг назад к меню Штурма при нажатии 'Закрыть' в фотомеханиках."""
    await cb_photographer_back_to_storm(cb)


# ─── Ввод данных пользователем: текст или фото ───


async def process_bulk_gear_input(message: types.Message, raw_text: str) -> None:
    """Обрабатывает список техники: парсинг, исследование и сохранение."""
    parsed_items = parse_gear_description(raw_text)
    items_to_process = (
        parsed_items or [{"name": raw_text, "category": categorize_gear_name(raw_text)}]
    )

    status = await message.answer(
        f"🔍 Распознано предметов: <b>{len(items_to_process)}</b>.\n"
        "Начинаю индивидуальное исследование каждого через веб-поиск…",
        parse_mode="HTML",
    )

    async def _update_progress(idx: int, total: int, current_name: str) -> None:
        try:
            await status.edit_text(
                f"🔍 Исследую ({idx}/{total}): <b>{html.escape(current_name)}</b>…\n"
                "<i>Поиск оптических свойств, приёмов и ожидаемого результата</i>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug("[GEAR] status edit failed: %s", e)

    try:
        new_profile = await enrich_gear_profile(items_to_process, status_cb=_update_progress)
        save_gear_profile(new_profile)

        card_preview = format_gear_card(new_profile)
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="🎒 Посмотреть арсенал", callback_data="gear_open"))
        kb.row(types.InlineKeyboardButton(
            text="🎨 Лаборатория стилей", callback_data="bs_start_fusion"
        ))

        if len(card_preview) > 3800:
            await status.edit_text(
                f"✅ <b>Арсенал успешно сформирован ({len(items_to_process)} предм.)!</b>\n\n"
                "Все предметы сохранены на постоянной основе в профиль.",
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
        else:
            header = f"✅ <b>Арсенал успешно сформирован ({len(items_to_process)} предм.)!</b>\n\n"
            await status.edit_text(
                f"{header}{card_preview}",
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
    except Exception as exc:
        logger.error("[GEAR] bulk enrich failed: %s", exc, exc_info=True)
        await status.edit_text(
            f"❌ Ошибка при формировании арсенала: {html.escape(str(exc))}",
            parse_mode="HTML",
        )


@router.message(F.text, _is_gear_waiting)
@allowed_only
async def handle_gear_text_input(message: types.Message):
    """Обработка названия техники от пользователя."""
    uid = message.from_user.id
    mode = _gear_waiting.pop(uid, None)
    gear_name = (message.text or "").strip()
    if not gear_name or gear_name.startswith("/"):
        return

    parsed = parse_gear_description(gear_name)
    if len(parsed) > 1 or mode == "list" or is_gear_description(gear_name):
        await process_bulk_gear_input(message, gear_name)
        return

    status = await message.answer(
        f"🔍 Исследую технику «{html.escape(gear_name)}» через веб-поиск…",
        parse_mode="HTML",
    )
    try:
        item = await enrich_gear_item(gear_name)
        prof = load_gear_profile()
        prof.add_item(item)
        save_gear_profile(prof)

        styles_info = ""
        if item.best_styles:
            styles_info = f"\n🎭 <b>Стили:</b> {html.escape(', '.join(item.best_styles))}"
        traits_info = ""
        if item.optical_traits:
            traits_info = f"\n✨ <b>Оптика:</b> {html.escape(item.optical_traits)}"
        todo_info = ""
        if getattr(item, "what_to_do", ""):
            todo_info = f"\n🎯 <b>Что делать:</b> {html.escape(item.what_to_do)}"
        result_info = ""
        if getattr(item, "expected_result", ""):
            result_info = f"\n🔮 <b>Результат:</b> {html.escape(item.expected_result)}"

        reply_text = (
            f"✅ <b>Техника добавлена в арсенал!</b>\n\n"
            f"📷 <b>{html.escape(item.name)}</b> (категория: <i>{item.category}</i>)"
            f"{traits_info}{todo_info}{result_info}{styles_info}"
        )
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(
            text="🎒 Посмотреть арсенал", callback_data="gear_open"
        ))
        await status.edit_text(reply_text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as exc:
        logger.error("[GEAR] add item failed: %s", exc, exc_info=True)
        await status.edit_text(
            f"❌ Ошибка добавления техники: {html.escape(str(exc))}",
            parse_mode="HTML",
        )


@router.message(
    (F.photo | (F.document & F.document.mime_type.startswith("image/"))),
    _is_mech_waiting,
)
@allowed_only
async def handle_mech_photo_input(message: types.Message):
    """Обработка скриншота настроек через OCR и LLM-парсер."""
    uid = message.from_user.id
    _mech_waiting.pop(uid, None)

    status = await message.answer("📸 Считываю текст со скриншота через OCR…")
    tmp_path = ""
    try:
        if message.photo:
            file_obj: Any = message.photo[-1]
        elif message.document:
            file_obj = message.document
        else:
            await status.edit_text("❌ Формат не поддерживается.")
            return

        file_info = await message.bot.get_file(file_obj.file_id)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(tmp_fd)

        await message.bot.download_file(
            file_info.file_path, destination=tmp_path
        )
        ocr_text = extract_text_from_image(tmp_path)

        if not ocr_text or len(ocr_text.strip()) < 10:
            await status.edit_text(
                "❌ Не удалось распознать читаемый текст на скриншоте. "
                "Попробуйте прислать более чёткое изображение или введите параметры текстом.",
            )
            return

        await status.edit_text("🧠 Извлекаю параметры фотоприёма из распознанного текста…")
        mech = await parse_mechanic_from_text(ocr_text)
        if not mech:
            await status.edit_text(
                "❌ Не удалось структурировать фотоприём из текста скриншота. "
                "Попробуйте описать параметры сообщением.",
            )
            return

        _pending_mechanic[uid] = mech
        preview_text = format_mechanic_card(mech)
        await status.edit_text(
            preview_text,
            parse_mode="HTML",
            reply_markup=_mechanic_preview_kb().as_markup(),
        )
    except Exception as exc:
        logger.error("[MECH] photo OCR failed: %s", exc, exc_info=True)
        await status.edit_text(f"❌ Ошибка распознавания: {html.escape(str(exc))}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@router.message(F.text, _is_mech_waiting)
@allowed_only
async def handle_mech_text_input(message: types.Message):
    """Обработка текстового описания фотоприёма."""
    uid = message.from_user.id
    _mech_waiting.pop(uid, None)
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    status = await message.answer("🧠 Анализирую описание фотоприёма…")
    try:
        mech = await parse_mechanic_from_text(text)
        if not mech:
            await status.edit_text(
                "❌ Не удалось структурировать фотоприём. "
                "Укажите название, выдержку, стиль или физическое действие.",
            )
            return

        _pending_mechanic[uid] = mech
        preview_text = format_mechanic_card(mech)
        await status.edit_text(
            preview_text,
            parse_mode="HTML",
            reply_markup=_mechanic_preview_kb().as_markup(),
        )
    except Exception as exc:
        logger.error("[MECH] parse text failed: %s", exc, exc_info=True)
        await status.edit_text(f"❌ Ошибка анализа приёма: {html.escape(str(exc))}")


@router.callback_query(F.data == "mech_confirm_save")
@allowed_callback
async def cb_mech_confirm_save(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    mech: VisualMechanic | None = _pending_mechanic.pop(uid, None)
    if not mech:
        try:
            await cb.message.edit_text(
                "❌ Время ожидания подтверждения истекло."
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[MECH] expired edit failed: %s", exc)
        return

    add_user_mechanic(mech)
    title_esc = html.escape(mech.title)
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📚 Все фотомеханики", callback_data="mech_open"))
    try:
        await cb.message.edit_text(
            f"✅ <b>Фотоприём «{title_esc}» успешно сохранён!</b>\n\n"
            f"Теперь он находится в банке фотомеханик и будет учитываться "
            f"при генерации творческих идей в Штурме.",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[MECH] confirm save failed: %s", exc)


@router.callback_query(F.data == "mech_cancel")
@allowed_callback
async def cb_mech_cancel(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _pending_mechanic.pop(uid, None)
    try:
        await cb.message.edit_text("❌ Сохранение приёма отменено.")
    except Exception as exc:  # noqa: BLE001
        logger.debug("[MECH] cancel save edit failed: %s", exc)
