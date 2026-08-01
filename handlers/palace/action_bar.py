"""handlers/palace/action_bar.py — универсальная панель действий «Action Bar».

Единая панель под каждым ответом внутри раздела Дворец:
  🤖 Анализ ИИ | 🌐 Поиск в интернете | 💾 Сохранить
  ◀️/▶️ пагинация (если текст > PAGE_LIMIT)
  🔙 Вернуться к списку

Контракт:
  finalize_answer(uid, edit_func, text, ctx=None, title="", is_html=False)
    — единственная точка отрисовки ответа с панелью.
  text — сырой текст (будет прогнан через safe_html_format),
        если is_html=True — текст уже содержит HTML-разметку.
  title — HTML-заголовок, показывается только на первой странице.
  ctx   — dict: {"wing", "room", "drawer", "parent_cb"}
        parent_cb — callback_data родительского экрана для кнопки «🔙».
"""

import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import NOTES_DIR, allowed_callback
from services.ai_engine import _sync_ai_call, get_current_ai
from services.text_formatter import safe_html_format, split_message
from services.ttl_dict import TtlDict

logger = logging.getLogger("ActionBar")

PAGE_LIMIT = 1500

router = Router()

answer_store: TtlDict = TtlDict(ttl=1800)


# ─── Данные ───


@dataclass
class Answer:
    sid: str
    text: str
    title: str = ""
    ctx: dict = field(default_factory=dict)
    pages: list = field(default_factory=list)
    page: int = 0
    is_html: bool = False
    extra_rows: list = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return len(self.pages)


# ─── Пагинация (чистая логика) ───


def _find_cut(text: str, limit: int) -> int:
    """Ищет позицию разреза внутри первых `limit` символов.

    Приоритет: конец абзаца, перенос строки, пробел.
    Не режет ближе, чем limit*0.5 — иначе страницы слишком мелкие.
    """
    for sep in ("\n\n", "\n", " "):
        idx = text.rfind(sep, 0, limit)
        if idx >= limit * 0.5:
            return idx + len(sep)
    return limit


def paginate(text: str, limit: int = PAGE_LIMIT) -> list:
    """Разбивает текст на страницы по границам абзацев/строк/слов.

    Returns:
        Список страниц. Пустой текст → [""]. Текст ≤ limit → [text].
    """
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]
    pages = []
    remaining = text
    while len(remaining) > limit:
        cut = _find_cut(remaining, limit)
        pages.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        pages.append(remaining)
    return pages


# ─── Рендер ───


def _render_page(answer: Answer, idx: int) -> str:
    """Возвращает HTML-текст страницы (с заголовком на первой)."""
    page = answer.pages[idx]
    if not answer.is_html:
        page = safe_html_format(page)
    if idx == 0 and answer.title:
        page = answer.title + "\n\n" + page
    return page


def build_action_bar(answer: Answer, page_idx: int) -> InlineKeyboardBuilder:
    """Собирает клавиатуру панели действий для указанной страницы."""
    kb = InlineKeyboardBuilder()
    for row in answer.extra_rows:
        kb.row(*row)
    kb.row(
        types.InlineKeyboardButton(text="🤖 Анализ ИИ", callback_data=f"ab_ai:{answer.sid}"),
        types.InlineKeyboardButton(
            text="🌐 Поиск в интернете", callback_data=f"ab_web:{answer.sid}",
        ),
        types.InlineKeyboardButton(text="💾 Сохранить", callback_data=f"ab_sv:{answer.sid}"),
    )
    if answer.total_pages > 1:
        nav_row = []
        if page_idx > 0:
            nav_row.append(types.InlineKeyboardButton(
                text="◀️ Назад", callback_data=f"ab_pg:{answer.sid}:{page_idx - 1}",
            ))
        nav_row.append(types.InlineKeyboardButton(
            text=f"📄 {page_idx + 1}/{answer.total_pages}",
            callback_data="ab_pg_noop",
        ))
        if page_idx < answer.total_pages - 1:
            nav_row.append(types.InlineKeyboardButton(
                text="▶️ Вперёд", callback_data=f"ab_pg:{answer.sid}:{page_idx + 1}",
            ))
        kb.row(*nav_row)
    if answer.ctx.get("parent_cb"):
        kb.row(types.InlineKeyboardButton(
            text="🔙 Вернуться к списку", callback_data=f"ab_back:{answer.sid}",
        ))
    return kb


async def finalize_answer(
    uid: int,
    edit_func: Callable[..., Awaitable],
    text: str,
    ctx: dict | None = None,
    title: str = "",
    is_html: bool = False,
    extra_rows: list | None = None,
) -> Answer | None:
    """Отрисовывает ответ с панелью действий и сохраняет его в store.

    edit_func — callable (message.edit_text / message.answer / safe_edit_text).
    extra_rows — дополнительные ряды кнопок перед панелью (список из списков
    InlineKeyboardButton, сохраняются в Answer и воспроизводятся при пагинации).
    Returns: Answer из store или None при ошибке.
    """
    try:
        sid = secrets.token_hex(4)
        answer = Answer(
            sid=sid, text=text, title=title,
            ctx=ctx or {}, is_html=is_html, extra_rows=list(extra_rows or []),
        )
        if is_html:
            answer.pages = split_message(text, limit=PAGE_LIMIT) or [""]
        else:
            answer.pages = paginate(text, PAGE_LIMIT)
        answer_store[sid] = answer
        kb = build_action_bar(answer, 0)
        await edit_func(
            _render_page(answer, 0),
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        return answer
    except Exception as e:
        logger.error("[ACTION_BAR] finalize_answer error: %s", e, exc_info=True)
        return None


def get_answer(sid: str) -> Answer | None:
    return answer_store.get(sid)


# ─── Навигация «🔙 Вернуться к списку» ───


def _get_parent_handler(parent_cb: str) -> Callable | None:
    """Возвращает обработчик родительского экрана по его callback_data."""
    from . import admin, kg, navigation

    handlers = {
        "p_rdb": navigation.cb_read_drawer_back,
        "p_nav": navigation.cb_nav_menu,
        "p_wing": navigation.cb_list_wings,
        "p_tax": navigation.cb_taxonomy,
        "p_tun": navigation.cb_tunnels_menu,
        "p_kg": kg.cb_kg_menu,
        "p_kgr": kg.cb_kg_read,
        "p_kgsr": kg.cb_kg_back_to_search,
        "palace_back": _palace_back_cb,
        "palace_status": admin.cb_palace_status,
        "palace_admin": admin.cb_palace_admin,
        "palace_instructions": admin.cb_palace_instructions,
    }
    return handlers.get(parent_cb)


async def _palace_back_cb(cb: types.CallbackQuery):
    from . import cb_palace_back

    await cb_palace_back(cb)


async def _dispatch_parent(cb: types.CallbackQuery, parent_cb: str) -> bool:
    """Вызывает родительский экран. Returns True, если экран найден."""
    handler = _get_parent_handler(parent_cb)
    if not handler:
        return False
    try:
        await handler(cb)
    except Exception as e:
        logger.error("[ACTION_BAR] parent dispatch error: %s", e, exc_info=True)
        return False
    return True


# ─── Колбэки ───


@router.callback_query(F.data == "ab_pg_noop")
@allowed_callback
async def cb_ab_pg_noop(cb: types.CallbackQuery):
    await cb.answer()


@router.callback_query(F.data.startswith("ab_pg:"))
@allowed_callback
async def cb_ab_page(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    parts = cb.data.split(":")
    if len(parts) != 3:
        return
    _, sid, idx_str = parts
    try:
        idx = int(idx_str)
    except ValueError:
        return
    answer = get_answer(sid)
    if not answer or idx < 0 or idx >= answer.total_pages:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    answer.page = idx
    kb = build_action_bar(answer, idx)
    try:
        await cb.message.edit_text(
            _render_page(answer, idx),
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
    except Exception as e:
        logger.error("[ACTION_BAR] page edit error: %s", e)


@router.callback_query(F.data.startswith("ab_back:"))
@allowed_callback
async def cb_ab_back(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    parent_cb = answer.ctx.get("parent_cb", "")
    if not parent_cb:
        await cb.answer("Нет родительского экрана.", show_alert=True)
        return
    await _dispatch_parent(cb, parent_cb)


# ─── 🤖 Анализ ИИ ───


@router.callback_query(F.data.startswith("ab_ai:"))
@allowed_callback
async def cb_ab_ai(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="📝 Анализ ответа", callback_data=f"ab_ai_m:a:{sid}",
    ))
    kb.row(types.InlineKeyboardButton(
        text="🏰 С контекстом комнаты", callback_data=f"ab_ai_m:c:{sid}",
    ))
    kb.row(types.InlineKeyboardButton(
        text="◀️ Назад к ответу", callback_data=f"ab_back:{sid}",
    ))
    await cb.message.edit_text(
        "🤖 <b>Режим анализа:</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


async def _build_ai_context(answer: Answer, uid: int) -> str:
    """Собирает контекст комнаты для режима «с контекстом».

    Сначала берёт кэш _room_summary (если была сгенерирована саммари комнаты),
    иначе читает превью записей через MCP.
    """
    wing = answer.ctx.get("wing", "")
    room = answer.ctx.get("room", "")
    if not wing or not room:
        return ""
    try:
        from .shared import _user_context

        cached = _user_context.get(uid, {})
        summary = cached.get("_room_summary")
        if summary:
            return f"Контекст комнаты {wing}/{room} (саммари):\n{summary[:12000]}"

        import json

        from services.palace_mcp import get_mcp

        mcp = get_mcp()
        raw = await mcp.call_tool("mempalace_list_drawers", {
            "wing": wing, "room": room, "limit": 15, "offset": 0,
        })
        parsed = json.loads(raw) if raw else {}
        drawers = parsed.get("drawers", [])
        if not drawers:
            return ""
        parts = []
        for d in drawers:
            name = d.get("closet_name") or d.get("title") or d.get("name", "")
            preview = d.get("content_preview", "") or d.get("content", "")[:300]
            parts.append(f"--- {name} ---\n{preview}")
        ctx_text = "\n\n".join(parts)
        if len(ctx_text) > 12000:
            ctx_text = ctx_text[:12000] + "\n...(сокращено)"
        return f"Контекст комнаты {wing}/{room}:\n{ctx_text}"
    except Exception as e:
        logger.error("[ACTION_BAR] ai context error: %s", e)
        return ""


@router.callback_query(F.data.startswith("ab_ai_m:"))
@allowed_callback
async def cb_ab_ai_run(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    parts = cb.data.split(":")
    if len(parts) < 3:
        return
    mode, sid = parts[1], parts[2]
    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    uid = cb.from_user.id
    status = await cb.message.answer("🧠 Анализирую...")
    try:
        engine, model = get_current_ai()
        if mode == "c":
            room_ctx = await _build_ai_context(answer, uid)
            prompt = (
                f"Проанализируй следующий ответ, используя контекст комнаты:\n\n"
                f"Ответ:\n{answer.text[:8000]}\n\n{room_ctx}"
            )
            system = (
                "Ты — аналитик. Анализируешь ответ с учётом контекста записей. "
                "Отвечай на русском языке."
            )
        else:
            prompt = (
                f"Проанализируй следующий текст: выдели ключевые мысли, "
                f"выводы и связи с другими темами.\n\n{answer.text[:8000]}"
            )
            system = (
                "Ты — аналитик. Отвечай на русском языке, структурированно."
            )
        result = _sync_ai_call(engine, model, [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ])
        ctx = dict(answer.ctx)
        ctx["_origin_sid"] = answer.sid
        await finalize_answer(
            uid,
            status.edit_text,
            result or "❌ Пустой ответ.",
            ctx=ctx,
            title="<b>🤖 Анализ</b>",
            is_html=False,
        )
    except Exception as e:
        await status.edit_text(f"❌ Ошибка анализа: {str(e)[:200]}")


# ─── 🌐 Поиск в интернете ───


@router.callback_query(F.data.startswith("ab_web:"))
@allowed_callback
async def cb_ab_web(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    status = await cb.message.answer("🔎 Готовлю запрос...")
    try:
        engine, model = get_current_ai()
        prompt = (
            "Сформулируй короткий поисковый запрос (до 10 слов, без кавычек) "
            "для уточнения следующего текста в интернете. Верни только запрос.\n\n"
            f"Текст:\n{answer.text[:3000]}"
        )
        query = _sync_ai_call(engine, model, [{"role": "user", "content": prompt}])
        query = (query or "").strip().strip('"').strip("«»")
        if not query:
            raise ValueError("ИИ не смог сформулировать запрос")
        answer.ctx["web_query"] = query
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(
            text="✅ Искать", callback_data=f"ab_web_go:{sid}",
        ))
        kb.row(types.InlineKeyboardButton(
            text="✏️ Исправить запрос", callback_data=f"ab_web_edit:{sid}",
        ))
        kb.row(types.InlineKeyboardButton(
            text="◀️ Назад к ответу", callback_data=f"ab_back:{sid}",
        ))
        await status.edit_text(
            f"🔎 <b>Запрос:</b> «{safe_html_format(query)}»\n\nИскать в интернете?",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data.startswith("ab_web_go:"))
@allowed_callback
async def cb_ab_web_go(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    query = answer.ctx.get("web_query", "")
    if not query:
        await cb.answer("Нет запроса. Начните поиск заново.", show_alert=True)
        return
    uid = cb.from_user.id
    status = await cb.message.answer("🌐 Ищу в интернете...")
    await _run_web_search_finalize(uid, status.edit_text, answer, query)


async def _run_web_search_finalize(
    uid: int, edit_func, answer: Answer, query: str,
):
    """Общая логика web-поиска: поиск + ИИ-ответ с контекстом."""
    try:
        from services.web_search import search_web

        web_results = await search_web(query)
        engine, model = get_current_ai()
        system = (
            "Ты отвечаешь на запрос пользователя, используя результаты "
            "поиска в интернете и контекст ответа, из которого возник запрос.\n\n"
            f"Контекст ответа:\n{answer.text[:6000]}\n\n"
            f"Результаты поиска:\n{web_results}"
        )
        result = _sync_ai_call(engine, model, [
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ])
        ctx = dict(answer.ctx)
        ctx["_origin_sid"] = answer.sid
        await finalize_answer(
            uid,
            edit_func,
            result or "❌ Пустой ответ.",
            ctx=ctx,
            title=f"<b>🌐 Поиск: {safe_html_format(query[:80])}</b>",
            is_html=False,
        )
    except Exception as e:
        try:
            await edit_func(f"❌ Ошибка поиска: {str(e)[:200]}")
        except Exception as edit_e:
            logger.error(
                "[ACTION_BAR] web search error: %s (render failed: %s)", e, edit_e,
            )


@router.callback_query(F.data.startswith("ab_web_edit:"))
@allowed_callback
async def cb_ab_web_edit(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    uid = cb.from_user.id
    answer.ctx["_await_query"] = True
    from .shared import _pending_mcp_input

    _pending_mcp_input[uid] = f"ab_web_query:{sid}"
    await cb.message.edit_text("✏️ Введите свой запрос для поиска:")


async def run_web_search_with_query(
    uid: int, msg, sid: str, query: str,
):
    """Запускает web-поиск с пользовательским запросом (вызывается
    из process_mcp_text_input при действии ab_web_query:{sid})."""
    answer = get_answer(sid)
    if not answer:
        await msg.edit_text("❌ Сессия поиска истекла. Начните заново.")
        return
    query = query.strip()
    answer.ctx["web_query"] = query
    status = await msg.edit_text("🌐 Ищу в интернете...")
    await _run_web_search_finalize(uid, status.edit_text, answer, query)


# ─── 💾 Сохранить ───


@router.callback_query(F.data.startswith("ab_sv:"))
@allowed_callback
async def cb_ab_sv(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="🏰 В Дворец", callback_data=f"ab_sv_p:{sid}",
    ))
    kb.row(types.InlineKeyboardButton(
        text="📝 В my_notes", callback_data=f"ab_sv_n:{sid}",
    ))
    kb.row(types.InlineKeyboardButton(
        text="◀️ Назад к ответу", callback_data=f"ab_back:{sid}",
    ))
    await cb.message.edit_text(
        "💾 <b>Куда сохранить?</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("ab_sv_p:"))
@allowed_callback
async def cb_ab_sv_palace(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    uid = cb.from_user.id
    from .save import _show_save_wings
    from .shared import _save_state

    _save_state[uid] = {"text": answer.text, "mode": "full"}
    await _show_save_wings(cb.message.edit_text, uid)


@router.callback_query(F.data.startswith("ab_sv_n:"))
@allowed_callback
async def cb_ab_sv_notes(cb: types.CallbackQuery):
    await cb.answer()
    if not cb.data:
        return
    sid = cb.data.split(":", 1)[1]
    answer = get_answer(sid)
    if not answer:
        await cb.answer("Сессия истекла. Откройте заново.", show_alert=True)
        return
    try:
        os.makedirs(NOTES_DIR, exist_ok=True)
        fn = f"notes_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        path = os.path.join(NOTES_DIR, fn)
        with open(path, "w", encoding="utf-8") as f:
            f.write(answer.text)
        await cb.message.edit_text(
            f"✅ Сохранено в <code>my_notes/{fn}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ Ошибка сохранения: {str(e)[:200]}")
