"""handlers/brainstorm.py — 🧠 Штурм: генерация идей с контекстом базы знаний.

Точки входа:
  /штурм <тема>      — сразу генерация идей
  Кнопка «🧠 Штурм»  — бот просит ввести тему (ожидание в _storm_waiting)

Пайплайн: детерминированный сбор контекста (notes + дворец + KG) →
один вызов модели → JSON-парсинг (services.brainstorm) → кнопки выбора
идеи → мост в существующий save-флоу Дворца (handlers.palace.save).
"""

import html
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
_reflection_data: TtlDict = TtlDict(ttl=600)
_reflection_waiting: TtlDict = TtlDict(ttl=3600)


async def _status_edit(status_msg, text: str):
    try:
        await status_msg.edit_text(f"🧠 {safe_html_format(text)}", parse_mode="HTML")
    except Exception as e:  # noqa: BLE001 — edit может упасть (429 и т.п.)
        logger.warning("[STORM] status edit failed: %s", e)


async def run_storm(uid: int, status_msg, topic: str, mode: str = "standard"):
    """Основной пайплайн: контекст → модель → идеи → кнопки выбора."""
    topic = (topic or "").strip()
    if not topic:
        await _status_edit(status_msg, "Тема не задана. Используйте: /штурм <тема>")
        return

    try:
        if mode == "fusion":
            await _status_edit(status_msg, "🎨 Собираю триаду стилей, арсенал и фотомеханики…")
            context = await bs.collect_context(topic, mode="fusion")

            await _status_edit(status_msg, "💭 Синтезирую авторские фотопроекты…")
            engine, model = get_current_ai()
            fusion_prompt = context.get("fusion_prompt") or bs.build_storm_prompt(topic, context)
            msgs = [
                {"role": "system", "content": bs.storm_system_prompt("fusion")},
                {"role": "user", "content": fusion_prompt},
            ]
            sampling = bs.storm_sampling_params("fusion")
            raw = await get_ai_response_async(engine, model, msgs, sampling=sampling)

            # Авто-переключение на локальный Ollama при исчерпании квоты (429) или сетевой ошибке
            is_quota_or_err = (
                raw.startswith("❌")
                or "429" in raw
                or "quota" in raw.lower()
                or "resource_exhausted" in raw.lower()
            )
            if is_quota_or_err and engine != "qwen":
                logger.warning(
                    "[STORM] Engine %s failed: %s. Auto-fallback to local Ollama (qwen2.5:7b)...",
                    engine, raw[:100],
                )
                await _status_edit(
                    status_msg,
                    "⚠️ Лимит облачной модели исчерпан. Переключаюсь на локальный Qwen…",
                )
                engine, model = "qwen", "qwen2.5:7b"
                raw = await get_ai_response_async(engine, model, msgs, sampling=sampling)

            try:
                ideas = bs.parse_fusion_ideas(raw)
            except Exception as parse_err:
                if engine != "qwen":
                    logger.warning(
                        "[STORM] Parse failed on %s: %s. Retrying with local Ollama...",
                        engine, parse_err,
                    )
                    await _status_edit(
                        status_msg,
                        "🔄 Облачная модель дала неполный ответ. Повторяю через локальный Qwen…",
                    )
                    engine, model = "qwen", "qwen2.5:7b"
                    raw = await get_ai_response_async(engine, model, msgs, sampling=sampling)
                    ideas = bs.parse_fusion_ideas(raw)
                else:
                    raise
        else:
            await _status_edit(status_msg, "🔍 Собираю контекст базы знаний…")
            context = await bs.collect_context(topic)

            await _status_edit(status_msg, "💭 Генерирую идеи…")
            engine, model = get_current_ai()
            msgs = [
                {"role": "system", "content": bs.STORM_SYSTEM_PROMPT},
                {"role": "user", "content": bs.build_storm_prompt(topic, context)},
            ]
            raw = await get_ai_response_async(engine, model, msgs)

            is_quota_or_err = (
                raw.startswith("❌")
                or "429" in raw
                or "quota" in raw.lower()
                or "resource_exhausted" in raw.lower()
            )
            if is_quota_or_err and engine != "qwen":
                logger.warning(
                    "[STORM] Engine %s failed: %s. Auto-fallback to local Ollama (qwen2.5:7b)...",
                    engine, raw[:100],
                )
                await _status_edit(
                    status_msg,
                    "⚠️ Лимит облачной модели исчерпан. Переключаюсь на локальный Qwen…",
                )
                engine, model = "qwen", "qwen2.5:7b"
                raw = await get_ai_response_async(engine, model, msgs)

            try:
                ideas = bs.parse_ideas(raw)
            except Exception as parse_err:
                if engine != "qwen":
                    logger.warning(
                        "[STORM] Standard parse failed on %s: %s. Retrying with local Ollama...",
                        engine, parse_err,
                    )
                    await _status_edit(
                        status_msg,
                        "🔄 Облачная модель дала сбой. Повторяю через локальный Qwen…",
                    )
                    engine, model = "qwen", "qwen2.5:7b"
                    raw = await get_ai_response_async(engine, model, msgs)
                    ideas = bs.parse_ideas(raw)
                else:
                    raise
    except Exception as exc:
        logger.error("[STORM] run failed: %s", exc, exc_info=True)
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(
                text="🎨 Повторить штурм",
                callback_data="bs_start_fusion",
            ),
            types.InlineKeyboardButton(
                text="⚙️ Настройки моделей",
                callback_data="settings:models",
            ),
        )
        try:
            await status_msg.edit_text(
                f"❌ <b>Ошибка штурма:</b> {html.escape(str(exc))}\n\n"
                "Вы можете повторить попытку или переключить модель в /settings.",
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
        except Exception as edit_err:
            logger.debug("[STORM] status edit with kb failed: %s", edit_err)
            await _status_edit(status_msg, f"❌ Ошибка штурма: {exc}")
        return

    _storm_data[uid] = {
        "topic": topic,
        "context": context,
        "ideas": ideas,
        "mode": mode,
    }

    kb = InlineKeyboardBuilder()
    row = []
    for i in range(1, len(ideas) + 1):
        btn_label = f"🎨 {i}" if mode == "fusion" else f"💡 {i}"
        row.append(types.InlineKeyboardButton(
            text=btn_label, callback_data=f"bs_pick:{i}",
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

    if mode == "fusion":
        text = bs.format_fusion_ideas_text(topic, ideas)
    else:
        text = bs.format_ideas_text(topic, ideas)

    try:
        await status_msg.edit_text(
            text, parse_mode="HTML", reply_markup=kb.as_markup(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[STORM] show ideas failed: %s", exc)


def get_storm_menu_text_and_kb() -> tuple[str, InlineKeyboardBuilder]:
    """Возвращает канонический текст и клавиатуру главного меню Штурма."""
    text = (
        "🧠 <b>Штурм</b>\n\n"
        "Введите тему для генерации идей.\n"
        "Бот соберёт контекст из ваших заметок, записей Дворца и графа знаний."
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🎨 Лаборатория стилей (Триада)", callback_data="bs_start_fusion",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🎙 Арт-копайлот (Диалог)", callback_data="copilot_start",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(text="🎒 Арсенал", callback_data="bs_open_gear"),
        types.InlineKeyboardButton(text="📚 Фотомеханики", callback_data="bs_open_mechs"),
    )
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="bs_cancel"))
    return text, kb


def _clear_copilot_waiting(uid: int) -> None:
    """Очищает состояние ожидания темы копайлота во избежание взаимных блокировок."""
    try:
        from handlers.copilot import _copilot_waiting_topic
        _copilot_waiting_topic.pop(uid, None)
    except Exception as exc:
        logger.debug("[STORM] clear copilot waiting failed: %s", exc)


# ─── /штурм <тема> и /синтез ───


@router.message(Command("штурм", "storm", ignore_case=True))
@allowed_only
async def cmd_storm(message: types.Message):
    raw_text = message.text or ""
    parts = raw_text.split(maxsplit=1)
    topic = parts[1].strip() if len(parts) > 1 else ""
    if not topic:
        _storm_waiting[message.from_user.id] = True
        _clear_copilot_waiting(message.from_user.id)
        text, kb = get_storm_menu_text_and_kb()
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        return
    status = await message.answer("🧠 Запускаю штурм…")
    await run_storm(message.from_user.id, status, topic)


@router.message(Command("синтез", "fusion", "лаборатория", ignore_case=True))
@allowed_only
async def cmd_fusion_storm(message: types.Message):
    raw_text = message.text or ""
    parts = raw_text.split(maxsplit=1)
    topic = parts[1].strip() if len(parts) > 1 else ""
    if not topic:
        _storm_waiting[message.from_user.id] = "fusion"
        _clear_copilot_waiting(message.from_user.id)
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="🎒 Арсенал", callback_data="bs_open_gear"),
            types.InlineKeyboardButton(text="📚 Фотомеханики", callback_data="bs_open_mechs"),
        )
        kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="bs_cancel"))
        await message.answer(
            "🎨 <b>Творческая лаборатория: Стилистический синтез</b>\n\n"
            "Введите тему для синтеза авторского фотопроекта.\n"
            "Бот подберёт триаду стилей (Сюжет + Свет + Оптика), свяжет её с вашим "
            "арсеналом Fujifilm X-T4, банком фотомеханик и заметками.",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        return
    status = await message.answer("🎨 Запускаю творческую лабораторию стилей…")
    await run_storm(message.from_user.id, status, topic, mode="fusion")


@router.message(F.text == "🧠 Штурм")
@allowed_only
async def btn_storm(message: types.Message):
    _storm_waiting[message.from_user.id] = True
    _clear_copilot_waiting(message.from_user.id)
    text, kb = get_storm_menu_text_and_kb()
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.in_(["bs_menu", "storm_menu"]))
@allowed_callback
async def cb_storm_menu(cb: types.CallbackQuery):
    """Возвращает пользователя в главное меню Штурма (шаг назад) и активирует ожидание темы."""
    await cb.answer()
    uid = cb.from_user.id
    _storm_waiting[uid] = True
    _clear_copilot_waiting(uid)
    text, kb = get_storm_menu_text_and_kb()
    try:
        await cb.message.edit_text(
            text, parse_mode="HTML", reply_markup=kb.as_markup(), disable_web_page_preview=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[STORM] menu edit failed: %s", exc)
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "bs_start_fusion")
@allowed_callback
async def cb_start_fusion(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _storm_waiting[uid] = "fusion"
    _clear_copilot_waiting(uid)
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="bs_cancel"))
    await cb.message.edit_text(
        "🎨 <b>Творческая лаборатория (Синтез стилей)</b>\n\n"
        "Введите тему для синтеза авторского фотопроекта.\n"
        "Например: «осенний парк», «ночные тени», «акварельный портрет у окна».",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "bs_open_gear")
@allowed_callback
async def cb_bs_open_gear(cb: types.CallbackQuery):
    await cb.answer()
    from handlers.photographer import cb_gear_open
    await cb_gear_open(cb)


@router.callback_query(F.data == "bs_open_mechs")
@allowed_callback
async def cb_bs_open_mechs(cb: types.CallbackQuery):
    await cb.answer()
    from handlers.photographer import cb_mech_open
    await cb_mech_open(cb)


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
    kb.row(types.InlineKeyboardButton(text="✅ Сохранить во Дворец", callback_data="bs_save"))
    kb.row(
        types.InlineKeyboardButton(
            text="📝 В Apple Notes [В планах]",
            callback_data="bs_export_notes",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="\u25c0\ufe0f К идеям", callback_data="bs_back",
        ),
    )
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="bs_cancel"))
    _storm_data[uid]["pending"] = {"text": text, "label": label, "ideas": selected}
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

    selected_idea = ideas[idx - 1]
    from services.style_fusion import (
        FusedPhotoConcept,
        build_concept_navigation_kb,
        format_concept_page,
    )
    if isinstance(selected_idea, FusedPhotoConcept):
        text = format_concept_page(selected_idea, page=1)
        kb = build_concept_navigation_kb(concept_idx=idx, page=1)
        _storm_data[uid]["pending"] = {
            "text": bs.ideas_to_text([selected_idea]),
            "label": f"Проект {idx}",
            "ideas": [selected_idea],
            "active_concept_idx": idx,
        }
        await cb.message.edit_text(
            text, parse_mode="HTML", reply_markup=kb.as_markup(), disable_web_page_preview=True,
        )
    else:
        await _storm_confirm(uid, cb.message.edit_text, [selected_idea], f"Идея {idx}")


@router.callback_query(F.data.startswith("bs_page:"))
@allowed_callback
async def cb_concept_page(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    if not data:
        return await cb.message.edit_text("❌ Сессия истекла. Начните /штурм заново.")
    parts = cb.data.split(":")
    if len(parts) < 3:
        return
    try:
        idx = int(parts[1])
        page = int(parts[2])
    except ValueError:
        return
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        return await cb.message.edit_text("❌ Проект не найден.")
    concept = ideas[idx - 1]
    from services.style_fusion import (
        FusedPhotoConcept,
        build_concept_navigation_kb,
        format_concept_page,
    )
    if not isinstance(concept, FusedPhotoConcept):
        return
    text = format_concept_page(concept, page=page)
    kb = build_concept_navigation_kb(concept_idx=idx, page=page)
    await cb.message.edit_text(
        text, parse_mode="HTML", reply_markup=kb.as_markup(), disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("bs_prompt:"))
@allowed_callback
async def cb_concept_prompt(cb: types.CallbackQuery):
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
        return
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        return await cb.message.edit_text("❌ Проект не найден.")
    concept = ideas[idx - 1]
    from services.style_fusion import FusedPhotoConcept, build_midjourney_prompt
    if not isinstance(concept, FusedPhotoConcept):
        return
    prompt_text = build_midjourney_prompt(concept)
    concept.midjourney_prompt = prompt_text
    title_esc = safe_html_format(concept.title)
    text = (
        f"🎨 <b>Промпт Midjourney / Flux.1</b>\n"
        f"Проект: «{title_esc}»\n\n"
        f"<code>{safe_html_format(prompt_text)}</code>\n\n"
        "💡 <i>Нажмите на блок кода, чтобы скопировать промпт. "
        "Вставьте его в Midjourney (/imagine) или Flux.</i>"
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="📝 В Apple Notes", callback_data=f"bs_export_concept:{idx}",
        ),
        types.InlineKeyboardButton(
            text="🏛 Во Дворец", callback_data=f"bs_save_concept:{idx}",
        ),
    )
    kb.row(types.InlineKeyboardButton(text="◀️ Назад к проекту", callback_data=f"bs_page:{idx}:1"))
    await cb.message.edit_text(
        text, parse_mode="HTML", reply_markup=kb.as_markup(), disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("bs_refs:"))
@allowed_callback
async def cb_concept_refs(cb: types.CallbackQuery):
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
        return
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        return await cb.message.edit_text("❌ Проект не найден.")
    concept = ideas[idx - 1]
    from services.style_fusion import FusedPhotoConcept, format_references_card
    if not isinstance(concept, FusedPhotoConcept):
        return

    web_snippets = ""
    try:
        from services.web_search import search_web
        q = f"{concept.triad.narrative.style} {concept.triad.optics.style} photography"
        web_snippets = await search_web(q, max_results=2)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[STORM] Web search for refs failed: %s", exc)

    text = format_references_card(concept, web_snippets=web_snippets)
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="📝 В Apple Notes", callback_data=f"bs_export_concept:{idx}",
        ),
        types.InlineKeyboardButton(
            text="🏛 Во Дворец", callback_data=f"bs_save_concept:{idx}",
        ),
    )
    kb.row(types.InlineKeyboardButton(text="◀️ Назад к проекту", callback_data=f"bs_page:{idx}:1"))
    await cb.message.edit_text(
        text, parse_mode="HTML", reply_markup=kb.as_markup(), disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("bs_deepen:"))
@allowed_callback
async def cb_concept_deepen(cb: types.CallbackQuery):
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
        return
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        return await cb.message.edit_text("❌ Проект не найден.")
    concept = ideas[idx - 1]
    from services.style_fusion import (
        FusedPhotoConcept,
        build_deepen_system_prompt,
        build_deepen_user_prompt,
        format_deepen_card,
    )
    if not isinstance(concept, FusedPhotoConcept):
        return

    try:
        await cb.message.edit_text(
            f"🔍 <b>Углубляю образ проекта «{safe_html_format(concept.title)}»…</b>\n"
            "Анализирую скрытый символизм, колористику и режиссуру модели…",
            parse_mode="HTML",
        )
        engine, model = get_current_ai()
        msgs = [
            {"role": "system", "content": build_deepen_system_prompt()},
            {"role": "user", "content": build_deepen_user_prompt(concept)},
        ]
        analysis = await get_ai_response_async(engine, model, msgs)
        if not analysis.startswith("❌"):
            concept.deepened_analysis = analysis
        text = format_deepen_card(concept, analysis)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[STORM] Deepen analysis failed: %s", exc)
        text = f"❌ Не удалось углубить образ: {exc}"

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="📝 В Apple Notes", callback_data=f"bs_export_concept:{idx}",
        ),
        types.InlineKeyboardButton(
            text="🏛 Во Дворец", callback_data=f"bs_save_concept:{idx}",
        ),
    )
    kb.row(types.InlineKeyboardButton(text="◀️ Назад к проекту", callback_data=f"bs_page:{idx}:1"))
    await cb.message.edit_text(
        text, parse_mode="HTML", reply_markup=kb.as_markup(), disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("bs_fuji_recipe:"))
@allowed_callback
async def cb_concept_fuji_recipe(cb: types.CallbackQuery):
    """Показывает карточку внутрикамерного рецепта Fujifilm X-T4 для концепта."""
    if not cb.data or not cb.message:
        return
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    if not data:
        await cb.answer("❌ Сессия истекла.", show_alert=True)
        return
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        return
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        await cb.answer("❌ Проект не найден.", show_alert=True)
        return
    concept = ideas[idx - 1]
    from services.fuji_recipes import (
        build_fuji_recipe_for_concept,
        format_fuji_recipe_card,
    )

    recipe = build_fuji_recipe_for_concept(concept)
    card_text = format_fuji_recipe_card(recipe, slot_name="C1")

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="💾 В книгу рецептов",
            callback_data=f"bs_recipe_save:{idx}",
        ),
        types.InlineKeyboardButton(
            text="🍏 В Apple Notes",
            callback_data=f"bs_recipe_export:{idx}",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="◀️ Назад к проекту",
            callback_data=f"bs_page:{idx}:3",
        )
    )

    await cb.message.edit_text(
        card_text,
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("bs_recipe_save:"))
@allowed_callback
async def cb_concept_recipe_save(cb: types.CallbackQuery):
    """Сохраняет рецепт концепта в постоянную «Книгу рецептов фотографа»."""
    if not cb.data:
        return
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    if not data:
        await cb.answer("❌ Сессия истекла.", show_alert=True)
        return
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        return
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        await cb.answer("❌ Проект не найден.", show_alert=True)
        return
    concept = ideas[idx - 1]
    from services.fuji_recipes import (
        build_fuji_recipe_for_concept,
        save_recipe_to_book,
    )

    recipe = build_fuji_recipe_for_concept(concept)
    ok = save_recipe_to_book(recipe, user_id=uid, slot_hint="C1")
    if ok:
        await cb.answer(
            f"✅ Рецепт «{recipe.recipe_name}» сохранён в книгу рецептов!",
            show_alert=True,
        )
    else:
        await cb.answer("❌ Не удалось сохранить рецепт в книгу.", show_alert=True)


@router.callback_query(F.data.startswith("bs_recipe_export:"))
@allowed_callback
async def cb_concept_recipe_export(cb: types.CallbackQuery):
    """Экспортирует рецепт концепта в Apple Notes (папка «Фотопроекты»)."""
    if not cb.data:
        return
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    if not data:
        await cb.answer("❌ Сессия истекла.", show_alert=True)
        return
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        return
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        await cb.answer("❌ Проект не найден.", show_alert=True)
        return
    concept = ideas[idx - 1]
    from services.apple_notes import AppleNotesError
    from services.fuji_recipes import (
        build_fuji_recipe_for_concept,
        export_fuji_recipe_to_apple_notes,
    )

    recipe = build_fuji_recipe_for_concept(concept)
    project_title = getattr(concept, "title", "")
    try:
        export_fuji_recipe_to_apple_notes(
            recipe,
            slot_name="C1",
            project_title=project_title,
            folder="Фотопроекты",
        )
        await cb.answer(
            f"✅ Рецепт «{recipe.recipe_name}» экспортирован в Apple Notes (папка «Фотопроекты»)!",
            show_alert=True,
        )
    except AppleNotesError as exc:
        await cb.answer(f"❌ Ошибка Apple Notes: {exc}", show_alert=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[STORM] Recipe export failed: %s", exc)
        await cb.answer("❌ Сбой сохранения рецепта в Apple Notes.", show_alert=True)


@router.callback_query(F.data.startswith("bs_export_concept:"))
@allowed_callback
async def cb_concept_export_single(cb: types.CallbackQuery):
    if not cb.data:
        return
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    if not data:
        await cb.answer("❌ Сессия истекла.", show_alert=True)
        return
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        return
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        await cb.answer("❌ Проект не найден.", show_alert=True)
        return
    concept = ideas[idx - 1]
    from services.apple_notes import AppleNotesError
    from services.style_fusion import FusedPhotoConcept, export_concept_to_apple_notes

    if not isinstance(concept, FusedPhotoConcept):
        return
    try:
        export_concept_to_apple_notes(concept, folder="Фотопроекты")
        await cb.answer(
            f"✅ Проект «{concept.title}» сохранён в Apple Notes "
            "(папка «Фотопроекты», статус [В планах])!",
            show_alert=True,
        )
    except AppleNotesError as exc:
        await cb.answer(f"❌ Ошибка Apple Notes: {exc}", show_alert=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[STORM] Single export failed: %s", exc)
        await cb.answer("❌ Сбой сохранения в Apple Notes.", show_alert=True)


@router.callback_query(F.data.startswith("bs_save_concept:"))
@allowed_callback
async def cb_concept_save_palace(cb: types.CallbackQuery):
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
        return
    ideas = data.get("ideas", [])
    if idx < 1 or idx > len(ideas):
        return await cb.message.edit_text("❌ Проект не найден.")
    concept = ideas[idx - 1]
    from handlers.palace import _save_state, _show_save_wings

    text = bs.ideas_to_text([concept])
    _save_state[uid] = {
        "text": text,
        "mode": "full",
        "wing": "",
        "room": "",
        "wings": [],
        "rooms": [],
    }
    await cb.message.edit_text("⏳ Загружаю крылья…")
    await _show_save_wings(cb.message.edit_text, uid)


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
    mode = data.get("mode", "standard")
    kb = InlineKeyboardBuilder()
    row = []
    for i in range(1, len(ideas) + 1):
        btn_label = f"🎨 {i}" if mode == "fusion" else f"💡 {i}"
        row.append(types.InlineKeyboardButton(
            text=btn_label, callback_data=f"bs_pick:{i}",
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

    if mode == "fusion":
        text = bs.format_fusion_ideas_text(data.get("topic", ""), ideas)
    else:
        text = bs.format_ideas_text(data.get("topic", ""), ideas)

    await cb.message.edit_text(
        text,
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
    _reflection_data[uid] = {
        "theme": (data.get("topic") or "")[:80],
        "ideas_count": len(data.get("ideas", [])),
    }

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


@router.callback_query(F.data == "bs_export_notes")
@allowed_callback
async def cb_export_notes(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _storm_data.get(uid)
    pending = (data or {}).get("pending")
    if not data or not pending:
        return await cb.message.edit_text("❌ Сессия истекла. Начните /штурм заново.")
    ideas = pending.get("ideas", [])
    if not ideas:
        return await cb.message.edit_text("❌ Нет идей для экспорта.")

    from services.apple_notes import AppleNotesError
    from services.style_fusion import (
        FusedPhotoConcept,
        export_concept_to_apple_notes,
    )

    exported_titles: list[str] = []
    try:
        for idea in ideas:
            if isinstance(idea, FusedPhotoConcept):
                export_concept_to_apple_notes(idea, folder="Фотопроекты")
                exported_titles.append(idea.title)
            elif isinstance(idea, dict):
                try:
                    concept = FusedPhotoConcept.from_dict(idea)
                    export_concept_to_apple_notes(concept, folder="Фотопроекты")
                    exported_titles.append(concept.title)
                except Exception:
                    from services.apple_notes import create_note, ensure_folder
                    ensure_folder("Фотопроекты")
                    t = f"[В планах] {idea.get('title', 'Фотопроект')}"
                    b = (
                        f"# {t}\n\n**Обоснование:** {idea.get('reason', '')}\n\n"
                        f"**Шаги:** {idea.get('steps', '')}"
                    )
                    create_note(title=t, body=b, folder="Фотопроекты")
                    exported_titles.append(idea.get("title", "Фотопроект"))
    except AppleNotesError as exc:
        logger.warning("[STORM] Export to Apple Notes failed: %s", exc)
        return await cb.message.answer(f"❌ Ошибка Apple Notes: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[STORM] Unexpected export failure: %s", exc)
        return await cb.message.answer("❌ Не удалось экспортировать в Apple Notes.")

    titles_str = ", ".join(f"«{t}»" for t in exported_titles)
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🏛 Сохранить во Дворец", callback_data="bs_save"))
    kb.row(types.InlineKeyboardButton(text="\u25c0\ufe0f К идеям", callback_data="bs_back"))
    await cb.message.edit_text(
        f"✅ <b>Проект сохранён в Apple Notes!</b>\n\n"
        f"📁 Папка: <code>Фотопроекты</code>\n"
        f"🏷 Статус: <code>[В планах]</code>\n"
        f"Проекты: {safe_html_format(titles_str)}",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "bs_cancel")
@allowed_callback
async def cb_cancel(cb: types.CallbackQuery):
    await cb.answer()
    _storm_data.pop(cb.from_user.id, None)
    _storm_waiting.pop(cb.from_user.id, None)
    _clear_copilot_waiting(cb.from_user.id)
    try:
        await cb.message.edit_text("❌ Отменено.")
    except Exception as exc:  # noqa: BLE001 — сообщение может быть удалено
        logger.debug("[STORM] Cancel edit ignored: %s", exc)


# ─── Рефлексия после сохранения идей ───


async def maybe_ask_reflection(uid: int, answer_func) -> bool:
    """Задаёт вопрос рефлексии после успешного сохранения идей штурма.

    Возвращает True, если вопрос задан (для юзера был активный штурм).
    """
    data = _reflection_data.pop(uid, None)
    if not data:
        return False
    from services.reflection import build_reflection_question

    _reflection_waiting[uid] = {
        "theme": data.get("theme", ""),
        "ideas_count": data.get("ideas_count", 0),
    }
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="⏭ Пропустить", callback_data="bs_reflect_skip",
    ))
    await answer_func(
        build_reflection_question(data.get("theme", "")),
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    return True


@router.callback_query(F.data == "bs_reflect_skip")
@allowed_callback
async def cb_reflect_skip(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _reflection_data.pop(uid, None)
    _reflection_waiting.pop(uid, None)
    try:
        await cb.message.edit_text("⏭ Рефлексия пропущена.")
    except Exception as exc:  # noqa: BLE001 — сообщение может быть удалено
        logger.warning("[STORM] reflect skip edit failed: %s", exc)
