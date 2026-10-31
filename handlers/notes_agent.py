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
from aiogram.types import InaccessibleMessage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback
from handlers.palace._utils import safe_edit_text, safe_send
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
# uid -> {"items": [{"id", "name"}], "text": "..."} — список найденных заметок
_notes_list_store: TtlDict = TtlDict(ttl=1800)
# uid -> {"note_id", "name"} — заметка, выбранная для обсуждения с агентом
_notes_discuss_ctx: TtlDict = TtlDict(ttl=900)
# uid -> {"idx", "name", "folder", "pages": [...], "page"} — открытая заметка
_notes_view_store: TtlDict = TtlDict(ttl=900)

_NOTE_ROW_RE = re.compile(
    r"^-\s*(.*?)\s*\[id=([^\]]+)\](?:\s*\(папка:\s*([^)]*)\))?"
)
_ID_MARKER_RE = re.compile(r"\s*\[id=[^\]]+\]")
MAX_LIST_OPEN_BUTTONS = 10
NOTE_PAGE_SIZE = 1500  # символов в одной странице просмотра заметки (1500 ± 200)


def _collect_notes_from_result(result) -> list[dict]:
    """Заметки из результатов инструментов notes_search/notes_list.

    Агент получает output вида «- Название [id=...] (папка: ...)» — парсим
    их из шагов в порядке появления, дедуплицируем по id.
    """
    notes: list[dict] = []
    seen: set[str] = set()
    for step in getattr(result, "steps", []) or []:
        for call, res in zip(getattr(step, "calls", []), getattr(step, "results", [])):
            if call.get("name") not in ("notes_search", "notes_list"):
                continue
            output = res.get("output", "") or ""
            for line in output.splitlines():
                m = _NOTE_ROW_RE.match(line)
                if not m:
                    continue
                nid = m.group(2)
                if nid in seen:
                    continue
                seen.add(nid)
                notes.append({
                    "id": nid,
                    "name": m.group(1).strip() or "Заметка",
                    "folder": (m.group(3) or "").strip(),
                })
    return notes


def _clean_notes_text(text: str) -> str:
    """Убирает технические маркеры [id=...] из ответа, показываемого пользователю.

    ID нужны агенту внутри цикла (инструменты возвращают «- Название [id=...]»),
    но в тексте для пользователя они не нужны — открытие идёт кнопками «📄 N».
    """
    if not text:
        return text
    return _ID_MARKER_RE.sub("", text)


def _notes_list_key(uid: int) -> dict | None:
    """Актуальный кэш списка заметок пользователя или None."""
    if uid in _notes_list_store:
        return _notes_list_store.get(uid)
    return None


def _current_discuss(uid: int) -> dict | None:
    if uid in _notes_discuss_ctx:
        return _notes_discuss_ctx.get(uid)
    return None


def _note_by_index(uid: int, idx: int) -> dict | None:
    """Заметка по индексу из кэша списка (idx — 0-based)."""
    data = _notes_list_key(uid)
    if not data:
        return None
    if not isinstance(idx, int) or not 0 <= idx < len(data["items"]):
        return None
    return data["items"][idx]


def _build_open_rows(uid: int) -> list[list[types.InlineKeyboardButton]]:
    """Ряды кнопок «📄 N. Название» для открытия найденных заметок."""
    data = _notes_list_key(uid)
    if not data or not data["items"]:
        return []
    rows: list[list[types.InlineKeyboardButton]] = []
    buttons = []
    for i, item in enumerate(data["items"][:MAX_LIST_OPEN_BUTTONS], start=1):
        label = f"📄 {i}. {item['name'][:18]}"
        buttons.append(types.InlineKeyboardButton(
            text=label, callback_data=f"notes_view:{i - 1}",
        ))
        if len(buttons) == 5:
            rows.append(buttons)
            buttons = []
    if buttons:
        rows.append(buttons)
    return rows


def _chunk_text(text: str, limit: int = NOTE_PAGE_SIZE) -> list[str]:
    """Разбивает текст на страницы ≤ limit символов (предпочитая переносы строк).

    Строки длиннее limit режутся по лимиту без потери текста; переносы строк
    сохраняются (keepends), поэтому склейка страниц даёт исходный текст.
    Пустой текст → пустой список.
    """
    if not text:
        return []
    chunks: list[str] = []
    buf = ""
    for line in text.splitlines(keepends=True):
        if buf and len(buf) + len(line) > limit:
            chunks.append(buf)
            buf = ""
        if len(line) > limit:
            rest = line
            while len(rest) > limit:
                chunks.append(rest[:limit])
                rest = rest[limit:]
            buf = rest
        else:
            buf += line
    if buf:
        chunks.append(buf)
    return chunks


def _build_note_view_kb(
    uid: int, idx: int, total: int = 1, page: int = 0,
) -> InlineKeyboardBuilder:
    """Клавиатура просмотра заметки: листание ◀️/📍/▶️, действия, «← К списку»."""
    kb = InlineKeyboardBuilder()
    if total > 1:
        row = []
        if page > 0:
            row.append(types.InlineKeyboardButton(
                text="◀️", callback_data=f"notes_page:{idx}:{page - 1}",
            ))
        row.append(types.InlineKeyboardButton(
            text=f"📍 {page + 1}/{total}",
            callback_data=f"notes_page:{idx}:{page}",
        ))
        if page < total - 1:
            row.append(types.InlineKeyboardButton(
                text="▶️", callback_data=f"notes_page:{idx}:{page + 1}",
            ))
        kb.row(*row)
    kb.row(
        types.InlineKeyboardButton(
            text="💬 Обсудить с агентом", callback_data=f"notes_discuss:{idx}",
        ),
        types.InlineKeyboardButton(
            text="💡 Штурм", callback_data=f"notes_storm:{idx}",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="💾 В MemPalace", callback_data=f"notes_save:{idx}",
        ),
        types.InlineKeyboardButton(
            text="← К списку", callback_data=f"notes_back:{idx}",
        ),
    )
    if _current_discuss(uid):
        kb.row(types.InlineKeyboardButton(
            text="⏹ Завершить обсуждение", callback_data=f"notes_stop:{idx}",
        ))
    return kb


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
                secrets.token_hex(16),
            )
            if not first:
                return False
            return await _ask_once(
                uid, status_msg,
                "⚠️ <b>Двойное подтверждение.</b>\n"
                "Заметка будет перемещена в «Recently Deleted» (восстановимо "
                "30 дней). Продолжить?",
                secrets.token_hex(16),
            )
        return await _ask_once(uid, status_msg, card, secrets.token_hex(16))

    return confirm_write


async def _run_notes_agent_reply(
    uid: int, status_msg, question: str,
) -> ae.AgentResult:
    """Статус → run_agent (CAT_NOTES, confirm_write) → finalize_answer.

    Всегда возвращает AgentResult, включая ошибки (``ok=False``).
    """
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
        return ae.AgentResult.failure(str(exc))
    except Exception as exc:
        logger.error("[NOTES-AGENT] run failed: %s", exc, exc_info=True)
        message = f"Ошибка агента: {exc}"
        await _status_edit(status_msg, f"❌ {message}")
        return ae.AgentResult.failure(message)

    if result.finished_reason == "error":
        await _status_edit(status_msg, f"❌ {result.error or 'Неизвестная ошибка'}")
        return result
    if result.finished_reason == "max_iterations":
        await _status_edit(status_msg, f"⚠️ {result.error or 'Лимит итераций'}")
        return result

    notes = _collect_notes_from_result(result)
    if notes:
        display_text = _clean_notes_text(result.final_answer)
        _notes_list_store[uid] = {"items": notes, "text": display_text}
        extra_rows = _build_open_rows(uid)
    else:
        _notes_list_store.pop(uid, None)
        display_text = result.final_answer
        extra_rows = None

    await finalize_answer(
        uid,
        status_msg.edit_text,
        display_text,
        ctx={},
        title="<b>📝 Apple Notes</b>",
        extra_rows=extra_rows,
    )
    return result


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


async def run_surreal_storm(
    uid: int,
    status_msg,
    topic: str,
    context: dict | None = None,
):
    """Сюрреалистичный штурм: контекст notes+гайд → SURREAL промпт → карточки.

    context — готовый контекст ({"notes": ..., "guide": ...}); если задан,
    сбор контекста пропускается (используется для штурма по тексту заметки).
    """
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
        if context is None:
            await _status_edit(status_msg, "🔍 Собираю контекст из заметок…")
            context = await bs.collect_context(topic, mode="surreal")

        await _status_edit(status_msg, "💭 Генерирую сюрреалистичные идеи…")
        engine, model = get_current_ai()
        msgs = [
            {"role": "system", "content": bs.storm_system_prompt("surreal")},
            {"role": "user", "content": bs.build_storm_prompt(topic, context)},
        ]
        sampling = bs.storm_sampling_params("surreal")
        raw = await get_ai_response_async(engine, model, msgs, sampling=sampling)

        try:
            ideas = bs.parse_ideas(
                raw, require_camera_setup=True, require_camera_keywords=True,
            )
        except ValueError:
            logger.warning(
                "[SURREAL] первый ответ не прошёл парсинг, повторяем: %r", raw[:300],
            )
            await _status_edit(status_msg, "💭 Ответ не подошёл, пробую ещё раз…")
            raw = await get_ai_response_async(engine, model, msgs, sampling=sampling)
            ideas = bs.parse_ideas(
                raw, require_camera_setup=True, require_camera_keywords=True,
            )
    except Exception as exc:
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
    "📄 Найденные заметки открываются по кнопкам «📄 N». Под текстом заметки:\n"
    "• ◀️/▶️ — листание длинных заметок (страница ≈1500 символов);\n"
    "• «← К списку» — вернуться к списку найденных заметок;\n"
    "• 💬 <b>Обсудить с агентом</b> — агент ждёт ваш вопрос и отвечает по "
    "заметке (или всей папке), пока не нажата «⏹ Завершить»;\n"
    "• 💡 <b>Штурм</b> — сюрреалистичные фотоидеи с настройками Fujifilm X-T4 "
    "по тексту заметки;\n"
    "• 💾 <b>В MemPalace</b> — сохранить текст заметки во Дворец "
    "(с выбором крыла/комнаты).\n\n"
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


# ─── Открытие найденной заметки ───


async def _render_note_view(msg, uid: int, idx: int) -> bool:
    """Рисует текущую страницу открытой заметки одним edit (страница ≤1500 симв.)."""
    state = _notes_view_store.get(uid)
    if not state or state["idx"] != idx:
        return False
    total = len(state["pages"])
    page = state["page"]
    lines = [f"📄 <b>{safe_html_format(state['name'])}</b>"]
    if state.get("folder"):
        lines.append(f"📂 {safe_html_format(state['folder'])}")
    lines.append("")
    body = state["pages"][page]
    lines.append(safe_html_format(body) if body else "<i>Текст недоступен.</i>")
    lines.append("")
    hint = f"Страница {page + 1}/{total} · " if total > 1 else ""
    hint += "💬 Обсуждение включено — задайте вопрос или выберите действие:"
    lines.append(hint)
    kb = _build_note_view_kb(uid, idx, total, page)
    return await safe_edit_text(
        msg, "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup(),
    )


async def _show_note_content(cb: types.CallbackQuery, note: dict, idx: int = 0):
    """Открывает заметку одной постраничной страницей (≈1500 симв.) + клавиатура.

    Длинные заметки листаются стрелками ◀️/▶️ и никогда не отправляются
    несколькими сообщениями подряд.
    """
    from services import apple_notes

    name = note.get("name") or "Заметка"
    try:
        data = await asyncio.to_thread(apple_notes.read_note, note["id"])
        body = str(data.get("body") or "")
    except Exception as exc:  # noqa: BLE001 — показ заметки не критичен
        logger.warning("[NOTES-AGENT] view note %s failed: %s", note.get("id"), exc)
        body = ""

    uid = cb.from_user.id
    _notes_discuss_ctx[uid] = {
        "note_id": note["id"], "name": name,
        "folder": note.get("folder") or "",
    }
    _waiting_for_notes_input[uid] = True

    pages = _chunk_text(body)
    if not pages:
        pages = [""]
    _notes_view_store[uid] = {
        "idx": idx,
        "name": name,
        "folder": note.get("folder") or "",
        "pages": pages,
        "page": 0,
    }
    await _render_note_view(cb.message, uid, idx)


@router.callback_query(F.data.startswith("notes_view:"))
@allowed_callback
async def cb_notes_view(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        await safe_edit_text(cb.message, "❌ Неверный запрос.")
        return
    note = _note_by_index(cb.from_user.id, idx)
    if not note:
        await safe_edit_text(
            cb.message,
            "⏰ Список заметок устарел — повторите поиск в агентном режиме.",
        )
        return
    await _show_note_content(cb, note, idx=idx)


# ─── Действия с открытой заметкой: штурм / обсуждение / сохранение ───


async def _note_action_guard(cb: types.CallbackQuery) -> tuple[int, dict] | None:
    """Общий guard действий: idx из callback, заметка из кэша списка.

    Возвращает (idx, note) или None (уже отредактировано сообщение с ошибкой).
    """
    if not cb.data:
        return None
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        await safe_edit_text(cb.message, "❌ Неверный запрос.")
        return None
    note = _note_by_index(cb.from_user.id, idx)
    if not note:
        await safe_edit_text(
            cb.message,
            "⏰ Список заметок устарел — повторите поиск в агентном режиме.",
        )
        return None
    return idx, note


@router.callback_query(F.data.startswith("notes_storm:"))
@allowed_callback
async def cb_notes_storm(cb: types.CallbackQuery):
    """💡 Сюрреалистичный штурм по тексту открытой заметки (тема = название)."""
    await cb.answer()
    guard = await _note_action_guard(cb)
    if guard is None:
        return
    idx, note = guard
    from services import apple_notes

    try:
        data = await asyncio.to_thread(apple_notes.read_note, note["id"])
        body = str(data.get("body") or "")
    except Exception as exc:  # noqa: BLE001 — штурм по названию без текста
        logger.warning("[NOTES-AGENT] storm note %s read failed: %s", note["id"], exc)
        body = ""
    if not body.strip():
        await safe_edit_text(
            cb.message,
            "❌ Текст заметки недоступен — штурм невозможен.",
        )
        return

    from services import brainstorm as bs

    topic = note.get("name") or "без названия"
    context = {
        "notes": f"- {note.get('name', '?')}: {body}",
        "guide": bs._load_fuji_guide(),
    }
    # Заметка остаётся на месте: штурм уходит в отдельное сообщение,
    # чтобы пользователь не потерял текст открытой заметки.
    storm_msg = await safe_send(
        cb.message, "💭 Запускаю сюрреалистичный штурм…", return_message=True,
    )
    if storm_msg is None:
        await safe_edit_text(cb.message, "💭 Запускаю сюрреалистичный штурм…")
        if isinstance(cb.message, InaccessibleMessage):
            return
        storm_msg = cb.message
    if storm_msg is None:
        return
    await run_surreal_storm(cb.from_user.id, storm_msg, topic, context=context)


@router.callback_query(F.data.startswith("notes_page:"))
@allowed_callback
async def cb_notes_page(cb: types.CallbackQuery):
    """◀️/▶️ Листание страниц открытой заметки (одна страница ≈1500 символов)."""
    await cb.answer()
    if not cb.data:
        return
    parts = cb.data.split(":")
    if len(parts) != 3:
        await safe_edit_text(cb.message, "❌ Неверный запрос.")
        return
    try:
        idx, page = int(parts[1]), int(parts[2])
    except ValueError:
        await safe_edit_text(cb.message, "❌ Неверный запрос.")
        return
    uid = cb.from_user.id
    state = _notes_view_store.get(uid)
    if not state or state["idx"] != idx or not 0 <= page < len(state["pages"]):
        await safe_edit_text(
            cb.message,
            "⏰ Сессия заметки истекла — откройте её заново из списка.",
        )
        return
    state["page"] = page
    await _render_note_view(cb.message, uid, idx)


@router.callback_query(F.data.startswith("notes_back:"))
@allowed_callback
async def cb_notes_back(cb: types.CallbackQuery):
    """← К списку: возвращает сообщение со списком найденных заметок."""
    await cb.answer()
    uid = cb.from_user.id
    data = _notes_list_key(uid)
    if not data or not data["items"]:
        await safe_edit_text(
            cb.message,
            "⏰ Список заметок устарел — повторите поиск в агентном режиме.",
        )
        return
    _notes_view_store.pop(uid, None)
    from handlers.palace.action_bar import finalize_answer

    rows = _build_open_rows(uid)
    if _current_discuss(uid):
        rows.append([types.InlineKeyboardButton(
            text="⏹ Завершить обсуждение", callback_data="notes_stop:0",
        )])
    await finalize_answer(
        uid,
        cb.message.edit_text,
        data["text"],
        ctx={},
        title="<b>📝 Apple Notes</b>",
        extra_rows=rows,
    )


@router.callback_query(F.data.startswith("notes_discuss:"))
@allowed_callback
async def cb_notes_discuss(cb: types.CallbackQuery):
    """💬 Включает режим обсуждения заметки с агентом (ждёт вопрос в чате)."""
    await cb.answer()
    guard = await _note_action_guard(cb)
    if guard is None:
        return
    idx, note = guard
    uid = cb.from_user.id
    _notes_discuss_ctx[uid] = {
        "note_id": note["id"],
        "name": note.get("name") or "Заметка",
        "folder": note.get("folder") or "",
    }
    _waiting_for_notes_input[uid] = True

    state = _notes_view_store.get(uid)
    if state and state["idx"] == idx:
        await _render_note_view(cb.message, uid, idx)
        return

    folder = note.get("folder") or ""
    where = f" (папка: {safe_html_format(folder)})" if folder else ""
    kb = _build_note_view_kb(uid, idx)
    await safe_edit_text(
        cb.message,
        f"💬 <b>Обсуждение включено:</b> заметка "
        f"«{safe_html_format(note.get('name') or 'Заметка')}»{where}.\n\n"
        "Напишите вопрос в чат — агент ответит по содержанию заметки "
        "(можно спрашивать и про всю папку). Чтобы выйти — нажмите "
        "«⏹ Завершить обсуждение».",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("notes_save:"))
@allowed_callback
async def cb_notes_save(cb: types.CallbackQuery):
    """💾 Сохранение текста заметки в MemPalace (выбор крыла/комнаты)."""
    await cb.answer()
    guard = await _note_action_guard(cb)
    if guard is None:
        return
    idx, note = guard
    from services import apple_notes

    try:
        data = await asyncio.to_thread(apple_notes.read_note, note["id"])
        body = str(data.get("body") or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[NOTES-AGENT] save note %s read failed: %s", note["id"], exc)
        body = ""
    if not body.strip():
        await safe_edit_text(
            cb.message,
            "❌ Текст заметки недоступен — сохранить нечего.",
        )
        return

    from handlers.palace import _save_state, _show_save_wings

    header = f"📄 {note.get('name') or 'Заметка'}\n\n"
    _save_state[cb.from_user.id] = {
        "text": header + body,
        "mode": "full",
        "wing": "",
        "room": "",
        "wings": [],
        "rooms": [],
    }
    # Заметка остаётся на месте: выбор крыла/комнаты идёт в новом сообщении.
    wings_msg = await safe_send(
        cb.message, "⏳ Загружаю крылья…", return_message=True,
    )
    if wings_msg is None:
        await safe_edit_text(cb.message, "⏳ Загружаю крылья…")
        if isinstance(cb.message, InaccessibleMessage):
            return
        wings_msg = cb.message
    if wings_msg is None:
        return
    await _show_save_wings(wings_msg.edit_text, cb.from_user.id)


@router.callback_query(F.data.startswith("notes_stop:"))
@allowed_callback
async def cb_notes_stop(cb: types.CallbackQuery):
    """⏹ Завершает режим обсуждения заметки с агентом."""
    await cb.answer()
    uid = cb.from_user.id
    _notes_discuss_ctx.pop(uid, None)
    _waiting_for_notes_input.pop(uid, None)
    await safe_edit_text(
        cb.message,
        "⏹ Обсуждение завершено. Дальнейшие вопросы пойдут в обычный чат.",
    )


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
    сюрреалистичный штурм вместо обычного агента. Если пользователь
    открыл заметку (кнопки «📄 N» / «💬 Обсудить»), вопрос уходит агенту
    с контекстом обсуждаемой заметки — контекст держится на последующие
    сообщения, пока не нажата «⏹ Завершить обсуждение».
    """
    topic = _extract_storm_topic(question)
    if topic is not None:
        await run_surreal_storm(uid, status_msg, topic)
        return
    discuss = _current_discuss(uid)
    if discuss:
        note_id = str(discuss.get("note_id", ""))
        name = str(discuss.get("name") or "заметка")
        folder = str(discuss.get("folder") or "")
        folder_hint = (
            f" Заметка находится в папке «{folder}»: если вопрос про всю "
            f"папку — перечитай список через notes_list(folder=\"{folder}\")."
            if folder else ""
        )
        question = (
            f"Пользователь обсуждает заметку «{name}» (id={note_id})."
            f"{folder_hint}\n"
            f"Прочитай её через notes_read и отвечай по содержанию заметки.\n\n"
            f"Вопрос пользователя: {question}"
        )
    await _run_notes_agent_reply(uid, status_msg, question)
    if _current_discuss(uid) and not _extract_storm_topic(question):
        _waiting_for_notes_input[uid] = True
