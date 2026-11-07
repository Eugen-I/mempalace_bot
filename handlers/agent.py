"""handlers/agent.py — агентный режим (qwen2.5 + инструменты).

Точки входа:
  /agent <вопрос>            — агент в обычном чате (без скоупа)
  ab_agent:sid               — кнопка «🤖 Агент» в action bar (скоуп из answer.ctx)
  p_agent_room:{key}         — кнопка «🤖 Агент» на странице комнаты (скоуп крыло/комната)

Кнопки запуска доступны ВСЕГДА, независимо от переключателя agent_enabled.
"""

import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback, allowed_only
from services import agent_engine as ae
from services.agent_context import get_agent_context_store
from services.text_formatter import safe_html_format
from services.ttl_dict import TtlDict

logger = logging.getLogger("AgentHandler")

router = Router()

AGENT_SYSTEM_PROMPT = (
    "Ты — автономный ИИ-ассистент и агент базы знаний MemPalace и Apple Notes.\n"
    "Отвечай на русском языке.\n\n"
    "Твои инструменты:\n"
    "• Дворец памяти: mempalace_list_wings, mempalace_list_rooms, mempalace_list_tunnels, "
    "mp_search, mp_drawer_read, mp_kg_query, mp_kg_timeline, mp_kg_stats.\n"
    "• Apple Notes: notes_search, notes_list, notes_read.\n"
    "• Интернет: web_search — для актуальных новостей, фактов и данных из сети.\n"
    "• Системные: agent_now (дата/время), agent_list_tools.\n\n"
    "Правила:\n"
    "- Думай пошагово: вызови нужные инструменты перед ответом.\n"
    "- Если вопрос о проектах, идеях или личных записях — ищи во Дворце и Apple Notes.\n"
    "- Если вопрос о событиях в мире или внешней информации — используй web_search.\n"
    "- При использовании заметок (notes_read) обязательно цитируй дословные фрагменты "
    "в кавычках и указывай название заметки.\n"
    "- Не выдумывай факты: если информации нет — честно сообщи об этом.\n"
    "- Отвечай структурированно и по делу."
)

# Ключ -> (wing, room) для кнопки агента на странице комнаты
_agent_room_map: TtlDict = TtlDict()


async def _status_edit(status_msg, text: str):
    """Безопасное обновление статус-сообщения (edit может упасть на 429 и т.п.)."""
    try:
        await status_msg.edit_text(f"🤖 {safe_html_format(text)}", parse_mode="HTML")
    except Exception as e:  # noqa: BLE001
        logger.warning("[AGENT] status edit failed: %s", e)


async def _run_agent_reply(
    uid: int,
    status_msg,
    system_prompt: str,
    question: str,
    ctx: dict | None = None,
    include_write: bool = False,
    conversation_history: list[dict] | None = None,
) -> ae.AgentResult:
    """Общая логика: статус → run_agent → finalize_answer.

    Всегда возвращает AgentResult: ошибки представлены безопасным
    результатом с ``ok=False``, ``final_answer=""`` и текстом в ``error``.
    """
    from handlers.palace.action_bar import finalize_answer

    async def status_cb(text: str):
        await _status_edit(status_msg, text)

    try:
        result = await ae.run_agent(
            system_prompt, question,
            include_write=include_write,
            status_cb=status_cb,
            conversation_history=conversation_history,
        )
    except ae.AgentEngineError as exc:
        await _status_edit(status_msg, f"⚠️ {exc}")
        return ae.AgentResult.failure(str(exc))
    except Exception as exc:
        logger.error("[AGENT] run failed: %s", exc, exc_info=True)
        message = f"Ошибка агента: {exc}"
        await _status_edit(status_msg, f"❌ {message}")
        return ae.AgentResult.failure(message)

    if result.finished_reason == "error":
        await _status_edit(status_msg, f"❌ {result.error or 'Неизвестная ошибка'}")
        return result
    if result.finished_reason == "max_iterations":
        await _status_edit(status_msg, f"⚠️ {result.error or 'Лимит итераций'}")
        return result

    from services.ai_engine import get_current_ai
    _, active_model = get_current_ai()

    await finalize_answer(
        uid,
        status_msg.edit_text,
        result.final_answer,
        ctx=ctx or {},
        title=f"<b>🤖 Агент ({active_model})</b>",
    )
    return result


def _build_scope_prompt(wing: str, room: str) -> str:
    """Системная инструкция для скоуп-агента (крыло/комната)."""
    return (
        f"{AGENT_SYSTEM_PROMPT}\n"
        f"Контекст: ты работаешь с комнатой «{room}» крыла «{wing}». "
        f"Отвечай на вопросы в рамках этой комнаты."
    )


# ─── /agent <вопрос> ───


@router.message(Command("agent"))
@allowed_only
async def cmd_agent(message: types.Message):
    text = (message.text or "").strip()
    question = text[len("/agent"):].lstrip()
    if not question:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(
            text="🤖 Агент", callback_data="agent_explain",
        ))
        await message.answer(
            "🤖 <b>Агентный режим</b>\n\n"
            "Использование:\n"
            "• <code>/agent ваш вопрос</code> — агент ищет по базе знаний "
            "и собирает ответ\n"
            "• Кнопка «🤖 Агент» под ответом — агент для этого ответа\n"
            "• Кнопка «🤖 Агент» в комнате Дворца — агент с контекстом комнаты",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        return
    status = await message.answer("🤖 Запускаю агента…")
    await _run_agent_reply(message.from_user.id, status, AGENT_SYSTEM_PROMPT, question)


# ─── 🤖 Агент в action bar (скоуп из answer.ctx) ───


@router.callback_query(F.data.startswith("ab_agent:"))
@allowed_callback
async def cb_ab_agent(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    from handlers.palace.action_bar import get_answer

    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return

    # Create button-mode session
    ctx_store = get_agent_context_store()
    session_id = ctx_store.create_button_session()
    ctx_store.bind_button_session_to_uid(cb.from_user.id, session_id)

    # Store session_id in answer.ctx for follow-up routing
    answer.ctx["_agent_session_id"] = session_id
    answer.ctx["_is_button_mode"] = True

    wing = (answer.ctx or {}).get("wing", "")
    room = (answer.ctx or {}).get("room", "")
    status = await cb.message.answer("🤖 Запускаю агента…")
    prompt = _build_scope_prompt(wing, room) if wing and room else AGENT_SYSTEM_PROMPT
    question = (
        f"Проанализируй следующий ответ и, если нужно, дополни его "
        f"из своей базы знаний:\n\n{answer.text[:8000]}"
    )
    ctx = dict(answer.ctx or {})
    ctx["_origin_sid"] = answer.sid
    ctx["_agent_session_id"] = session_id
    ctx["_is_button_mode"] = True

    result = await _run_agent_reply(
        cb.from_user.id, status, prompt, question, ctx=ctx, conversation_history=[]
    )

    # Save only a successful agent response to button session history
    if result.ok and result.final_answer:
        ctx_store.append_button_context(session_id, "assistant", result.final_answer)


# ─── 🤖 Агент на странице комнаты (скоуп крыло/комната) ───


def build_room_agent_callback(wing: str, room: str) -> str:
    """Создаёт callback_data кнопки агента комнаты (через key-карту)."""
    import secrets

    key = secrets.token_hex(4)
    _agent_room_map[key] = (wing, room)
    return f"p_agent_room:{key}"


@router.callback_query(F.data.startswith("p_agent_room:"))
@allowed_callback
async def cb_room_agent(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    key = cb.data[len("p_agent_room:"):]
    pair = _agent_room_map.get(key)
    if not pair:
        await cb.message.edit_text(
            "❌ Сессия истекла. Откройте комнату заново.",
        )
        return
    wing, room = pair
    await cb.message.answer(
        f"🤖 Агент для комнаты <b>{safe_html_format(wing)}/{safe_html_format(room)}</b>\n"
        "Напишите ваш вопрос.",
        parse_mode="HTML",
    )
    from handlers.palace.shared import _pending_mcp_input

    _pending_mcp_input[cb.from_user.id] = f"agent_room:{key}"


def should_route_to_agent(uid: int, text: str) -> bool:
    """True, если сообщение должно обрабатывать агентом, а не обычным ИИ."""
    if text.startswith(("/", "~", "#")):
        return False
    from services.agent_settings import get_agent_enabled

    return get_agent_enabled(uid)


async def run_room_agent(uid: int, status_msg, key: str, question: str):
    """Запускает скоуп-агента комнаты (вызывается из process_mcp_text_input)."""
    pair = _agent_room_map.get(key)
    if not pair:
        await _status_edit(status_msg, "❌ Сессия истекла. Откройте комнату заново.")
        return
    wing, room = pair
    prompt = _build_scope_prompt(wing, room)
    ctx = {"wing": wing, "room": room, "parent_cb": "p_rdb"}
    await _run_agent_reply(uid, status_msg, prompt, question, ctx=ctx)


# ─── ⏹ Завершить диалог с агентом (button mode) ───


@router.callback_query(F.data.startswith("ab_agent_stop:"))
@allowed_callback
async def cb_ab_agent_stop(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    from handlers.palace.action_bar import get_answer

    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла.", show_alert=True)
        return
    session_id = answer.ctx.get("_agent_session_id")
    if session_id:
        ctx_store = get_agent_context_store()
        ctx_store.end_button_session(session_id)
        ctx_store.unbind_button_session_from_uid(cb.from_user.id)
    await cb.message.edit_text("⏹ Диалог с агентом завершён. Возвращаюсь в обычный режим.")


# ─── Справка ───


@router.callback_query(F.data == "agent_explain")
@allowed_callback
async def cb_agent_explain(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "🤖 <b>Агентный режим</b>\n\n"
        "Агент — это ИИ, который сам решает, какие инструменты использовать:\n"
        "• <code>/agent вопрос</code> — запуск в чате\n"
        "• «🤖 Агент» под ответом — анализ с контекстом ответа\n"
        "• «🤖 Агент» в комнате — ответ по записям комнаты\n\n"
        "Режим доступен с локальной моделью Ollama (qwen2.5).\n"
        "Включить автоматический режим (агент на каждое сообщение): /settings → «🤖 Агент».",
        parse_mode="HTML",
    )
