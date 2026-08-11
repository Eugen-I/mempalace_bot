"""handlers/notes_agent.py — агент для работы с заметками Apple Notes.

Точки входа:
  notes_agent_start         — кнопка «📝 Apple Notes» в главном меню
  notes_confirm:<token>     — подтверждение write-инструмента
  notes_cancel:<token>      — отмена write-инструмента

Запись (create/update/delete/move) доступна агенту ТОЛЬКО через confirm_write
из services/agent_engine.py: каждый write-инструмент приостанавливает цикл
и ждёт явного подтверждения пользователя (для notes_delete — двойного).
"""

import asyncio
import logging
import re
import secrets

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback
from handlers.palace._utils import safe_edit_text
from services import agent_engine as ae
from services.agent_tools import CAT_NOTES
from services.text_formatter import safe_html_format
from services.ttl_dict import TtlDict

logger = logging.getLogger("NotesAgentHandler")

router = Router()

CONFIRM_TIMEOUT = 120  # секунд на подтверждение

SURREAL_TRIGGERS = ("творческий штурм", "сюрреалистичный штурм", "сюрштурм")

NOTES_AGENT_SYSTEM_PROMPT = (
    "Ты — агент для работы с заметками Apple Notes в MemPalace. "
    "Отвечай на русском языке.\n"
    "Правила:\n"
    "- Работай ТОЛЬКО с заметками Apple Notes (notes_search, notes_list, "
    "notes_read, notes_create, notes_update, notes_delete, notes_move, "
    "notes_list_folders). Дворец и другие базы знаний тебе недоступны.\n"
    "- Перед вызовом любого write-инструмента (notes_create, notes_update, "
    "notes_delete, notes_move) ВСЕГДА объясни пользователю, что собираешься "
    "сделать, и попроси подтверждения.\n"
    "- Для notes_update/notes_delete сначала получи note_id через "
    "notes_search или notes_list.\n"
    "- Определяй язык текста пользователя автоматически: русский или "
    "немецкий. Азиатские языки (китайский, японский, корейский) НЕ "
    "поддерживаются — вежливо откажись от создания заметки на таком языке.\n"
    "- Цитируй дословные фрагменты из заметок в кавычках и указывай "
    "название заметки — пользователь должен видеть, откуда взят ответ.\n"
    "- Не выдумывай факты: если данных нет — честно скажи об этом.\n"
    "- Если инструмент вернул ошибку — сообщи о ней и предложи альтернативу.\n"
    "- Отвечай структурированно и по делу, не более 500 слов."
)

# token -> {"uid", "event", "approved"}
_pending_confirm: TtlDict = TtlDict(ttl=300)
# uid -> True — пользователь в режиме ожидания ввода для агента заметок
_waiting_for_notes_input: TtlDict = TtlDict()


def _status_edit(status_msg, text: str):
    return safe_edit_text(status_msg, f"📝 {safe_html_format(text)}", parse_mode="HTML")


async def _note_title(note_id: str) -> str:
    """Лучший-effort поиск названия заметки по ID (из кэш-индекса)."""
    if not note_id:
        return ""
    try:
        from services import apple_notes

        notes = await asyncio.to_thread(apple_notes.list_notes)
        for note in notes:
            if note.get("id") == note_id:
                return str(note.get("name", ""))
    except Exception as exc:  # noqa: BLE001 — заголовок карточки не критичен
        logger.debug("[NOTES-AGENT] title lookup failed: %s", exc)
    return ""


def _describe_action(name: str, arguments: dict) -> str:
    """Текст карточки подтверждения для write-инструмента."""
    args = arguments or {}
    if name == "notes_create":
        title = safe_html_format(str(args.get("title", "")))
        body = safe_html_format(str(args.get("text", ""))[:120])
        return (
            f"📝 <b>Создать заметку</b>\n"
            f"Заголовок: <b>{title}</b>\nТекст: {body}"
        )
    if name == "notes_update":
        note_id = str(args.get("note_id", ""))
        snippet = safe_html_format(
            str(args.get("append_text") or args.get("replace_text") or "")[:120]
        )
        return (
            f"✏️ <b>Обновить заметку</b>\n"
            f"ID: <code>{note_id}</code>\n{snippet}"
        )
    if name == "notes_delete":
        note_id = str(args.get("note_id", ""))
        return f"🗑 <b>Удалить заметку</b>\nID: <code>{note_id}</code>"
    if name == "notes_move":
        note_id = str(args.get("note_id", ""))
        folder = safe_html_format(str(args.get("target_folder", "")))
        return (
            f"📂 <b>Переместить заметку</b>\n"
            f"ID: <code>{note_id}</code>\n→ Папка: <b>{folder}</b>"
        )
    return f"Инструмент <code>{name}</code>: {safe_html_format(str(arguments)[:200])}"


def _build_confirm_kb(token: str, confirm_text: str = "✅ Да"):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text=confirm_text, callback_data=f"notes_confirm:{token}",
    ))
    kb.row(types.InlineKeyboardButton(
        text="❌ Нет", callback_data=f"notes_cancel:{token}",
    ))
    return kb


async def _ask_once(uid: int, status_msg, text: str, token: str) -> bool:
    """Один раунд подтверждения: карточка → ждём нажатия → результат."""
    event = asyncio.Event()
    pending = {"uid": uid, "event": event, "approved": False}
    _pending_confirm[token] = pending
    msg = await status_msg.answer(
        text, parse_mode="HTML",
        reply_markup=_build_confirm_kb(token).as_markup(),
    )
    try:
        await asyncio.wait_for(event.wait(), timeout=CONFIRM_TIMEOUT)
    except asyncio.TimeoutError:
        await safe_edit_text(
            msg,
            "⏰ Время ожидания подтверждения истекло — действие отменено.",
        )
        return False
    finally:
        _pending_confirm.pop(token, None)
    return bool(pending["approved"])


def _make_confirm_write(uid: int, status_msg):
    """Фабрика confirm_write для run_agent (замыкание на uid и статус-сообщение)."""

    async def confirm_write(name: str, arguments: dict) -> bool:
        card = _describe_action(name, arguments)
        if name == "notes_delete":
            note_id = str((arguments or {}).get("note_id", ""))
            title = await _note_title(note_id)
            who = f"<b>{safe_html_format(title)}</b>" if title else f"<code>{note_id}</code>"
            first = await _ask_once(
                uid, status_msg,
                f"{card}\n\nУдалить заметку {who}?",
                secrets.token_hex(8),
            )
            if not first:
                return False
            return await _ask_once(
                uid, status_msg,
                "⚠️ <b>Двойное подтверждение.</b>\n"
                "Заметка будет перемещена в «Recently Deleted» (восстановимо "
                "30 дней). Продолжить?",
                secrets.token_hex(8),
            )
        return await _ask_once(uid, status_msg, card, secrets.token_hex(8))

    return confirm_write


async def _run_notes_agent_reply(uid: int, status_msg, question: str):
    """Статус → run_agent (CAT_NOTES, confirm_write) → finalize_answer."""
    from handlers.palace.action_bar import finalize_answer

    async def status_cb(text: str):
        await _status_edit(status_msg, text)

    try:
        result = await ae.run_agent(
            NOTES_AGENT_SYSTEM_PROMPT,
            question,
            allowed_categories=(CAT_NOTES,),
            include_write=True,
            confirm_write=_make_confirm_write(uid, status_msg),
            status_cb=status_cb,
        )
    except ae.AgentEngineError as exc:
        await _status_edit(status_msg, f"⚠️ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.error("[NOTES-AGENT] run failed: %s", exc, exc_info=True)
        await _status_edit(status_msg, f"❌ Ошибка агента: {exc}")
        return

    if result.finished_reason == "error":
        await _status_edit(status_msg, f"❌ {result.error or 'Неизвестная ошибка'}")
        return
    if result.finished_reason == "max_iterations":
        await _status_edit(status_msg, f"⚠️ {result.error or 'Лимит итераций'}")
        return

    await finalize_answer(
        uid,
        status_msg.edit_text,
        result.final_answer,
        ctx={},
        title="<b>📝 Apple Notes</b>",
    )


# ─── 💡 Творческий штурм (сюрреалистичный, с настройками X-T4) ───


def _extract_storm_topic(text: str) -> str | None:
    """Извлекает тему сюрреалистичного штурма из текста.

    Возвращает тему (может быть пустой строкой) или None, если текст
    не является запросом «💡 Творческий штурм».
    """
    t = (text or "").strip()
    low = t.lower()
    for trigger in SURREAL_TRIGGERS:
        pos = low.find(trigger)
        if pos == -1:
            continue
        topic = t[pos + len(trigger):]
        topic = re.sub(r"^[\s:：—-]+", "", topic)
        return topic.strip()
    return None


async def run_surreal_storm(uid: int, status_msg, topic: str):
    """Сюрреалистичный штурм: контекст notes+гайд → SURREAL промпт → карточки."""
    from services import brainstorm as bs
    from services.ai_engine import get_ai_response_async, get_current_ai

    topic = (topic or "").strip()
    if not topic:
        await _status_edit(
            status_msg,
            "Укажите тему после команды. Например: «💡 Творческий штурм: ночные сны»",
        )
        return

    try:
        await _status_edit(status_msg, "🔍 Собираю контекст из заметок…")
        context = await bs.collect_context(topic, mode="surreal")

        await _status_edit(status_msg, "💭 Генерирую сюрреалистичные идеи…")
        engine, model = get_current_ai()
        msgs = [
            {"role": "system", "content": bs.storm_system_prompt("surreal")},
            {"role": "user", "content": bs.build_storm_prompt(topic, context)},
        ]
        raw = await get_ai_response_async(engine, model, msgs)

        ideas = bs.parse_ideas(raw, require_camera_setup=True)
    except Exception as exc:  # noqa: BLE001 — показываем пользователю текст ошибки
        logger.error("[SURREAL] run failed: %s", exc, exc_info=True)
        await _status_edit(status_msg, f"❌ Ошибка штурма: {exc}")
        return

    text = bs.format_surreal_ideas_text(topic, ideas)
    try:
        await status_msg.edit_text(text, parse_mode="HTML")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SURREAL] show ideas failed: %s", exc)


# ─── Кнопка «📝 Apple Notes» в главном меню ───

SESSION_INVITE = (
    "📝 <b>Работа с заметками Apple Notes</b>\n\n"
    "Напишите, что сделать с заметками — свободным текстом. Например:\n"
    "• «Сохрани в заметку: купить капучино»\n"
    "• «Найди мою заметку про Фудзи»\n"
    "• «Что там в заметках про поездку?»\n\n"
    "💡 <b>Творческий штурм:</b> «💡 Творческий штурм: ночные сны» — "
    "сюрреалистичные фотоидеи с точными настройками Fujifilm X-T4."
)


def start_notes_agent_session(message: types.Message):
    """Включает режим ожидания ввода для агента заметок (кнопка меню)."""
    _waiting_for_notes_input[message.from_user.id] = True
    return message.answer(SESSION_INVITE, parse_mode="HTML")


@router.callback_query(F.data == "notes_agent_start")
@allowed_callback
async def cb_notes_agent_start(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(SESSION_INVITE, parse_mode="HTML")
    _waiting_for_notes_input[cb.from_user.id] = True


# ─── Подтверждения write-инструментов ───


async def _resolve_confirmation(cb: types.CallbackQuery, approved: bool):
    token = (cb.data or "").split(":", 1)[-1]
    pending = _pending_confirm.get(token)
    if not pending or pending.get("uid") != cb.from_user.id:
        await cb.answer("Подтверждение истекло или недоступно.", show_alert=True)
        return
    pending["approved"] = approved
    pending["event"].set()
    await cb.answer("Подтверждено ✅" if approved else "Отменено ❌")
    await safe_edit_text(
        cb.message,
        "✅ Подтверждено." if approved else "❌ Действие отменено.",
    )


@router.callback_query(F.data.startswith("notes_confirm:"))
@allowed_callback
async def cb_notes_confirm(cb: types.CallbackQuery):
    await cb.answer()
    await _resolve_confirmation(cb, True)


@router.callback_query(F.data.startswith("notes_cancel:"))
@allowed_callback
async def cb_notes_cancel(cb: types.CallbackQuery):
    await cb.answer()
    await _resolve_confirmation(cb, False)


# ─── Вход из обычного диалога ───


def maybe_suggest_note_action(text: str) -> str | None:
    """Лёгкая эвристика: похоже ли сообщение на работу с заметками.

    Возвращает текст предложения для кнопки или None. Команды
    (/, ~, #, !-префиксы) не анализируются.
    """
    t = (text or "").strip().lower()
    if not t or t.startswith(("/", "~", "#", "!")):
        return None
    note_words = ("заметк", "apple notes")
    save_words = ("сохрани", "запиши", "запомни", "добавь в заметки")
    if any(w in t for w in save_words) or any(w in t for w in note_words):
        return "📝 Работать с заметками?"
    return None


def is_waiting_for_notes_input(uid: int) -> bool:
    return uid in _waiting_for_notes_input


def consume_notes_input(uid: int) -> bool:
    return _waiting_for_notes_input.pop(uid, None) is not None


async def run_notes_agent(uid: int, status_msg, question: str):
    """Запуск агента заметок (из кнопки меню или авто-предложения).

    Сообщение «💡 Творческий штурм: <тема>» маршрутизируется в
    сюрреалистичный штурм вместо обычного агента.
    """
    topic = _extract_storm_topic(question)
    if topic is not None:
        await run_surreal_storm(uid, status_msg, topic)
        return
    await _run_notes_agent_reply(uid, status_msg, question)
