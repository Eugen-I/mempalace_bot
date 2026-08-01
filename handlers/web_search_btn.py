from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
import os
import html

from config import NOTES_DIR, TAVILY_API_KEY
from handlers.messages import _last_user_query
from services.web_search_cache import load_web_search, save_web_search_with_id

router = Router()


async def search_with_ai_evaluation(
    query: str, tavily_key: str | None = None,
) -> tuple[str, list[dict], str]:
    """
    Поиск: сначала бесплатные движки, затем AI оценка, затем Tavily при необходимости.
    """
    import secrets
    from services.web_search import _search_all_engines
    from services.tavily_search import search_tavily

    search_id = f"ws_{secrets.token_hex(8)}"

    free_sources = await _search_all_engines(query, 5)

    if free_sources:
        text = _format_free_search_results(query, free_sources)
        sources = [{"text": s["text"], "url": s["url"]} for s in free_sources]
        save_web_search_with_id(search_id, query, sources, text)
        return text, sources, search_id

    if tavily_key:
        result = await search_tavily(query, tavily_key, 5)
        if "error" not in result:
            answer = result.get("answer", "")
            results = result.get("results", [])
            search_id = result.get("search_id", f"ws_{secrets.token_hex(8)}")

            formatted = _format_tavily_results(answer, results)
            sources = []
            for r in results:
                sources.append({
                    "text": r.get("snippet", r.get("content", ""))[:200],
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                })

            save_web_search_with_id(search_id, query, sources, formatted)
            return formatted, sources, search_id

    return "🤷 Ничего не найдено. Попробуйте другой запрос.", [], ""


def _format_free_search_results(query: str, sources: list[dict]) -> str:
    parts = [f"🌐 <b>Результаты поиска по запросу «{html.escape(query)}»:</b>"]
    for i, src in enumerate(sources, 1):
        text = html.escape(src.get("text", "")[:200])
        url = html.escape(src.get("url", ""))
        if text:
            parts.append(f"{i}. {text}")
            if url:
                parts.append(f"   <a href=\"{url}\">🔗 {url}</a>")
    if len(parts) == 1:
        return "🤷 Ничего не найдено."
    return "\n".join(parts)


def _format_tavily_results(answer: str, results: list[dict]) -> str:
    import html as html_module
    parts = []
    if answer:
        parts.append(f"🤖 <b>Ответ ИИ:</b>\n{html_module.escape(answer)}")
    if results:
        parts.append(f"🔍 <b>Результаты поиска ({len(results)} из 5):</b>")
        for i, result in enumerate(results[:5], 1):
            title = html_module.escape(result.get("title", "Без названия"))
            snippet = html_module.escape(result.get("snippet", result.get("content", ""))[:200])
            url = result.get("url", "")
            if url:
                parts.append(f"{i}. <b>{title}</b>")
                parts.append(f"   <a href=\"{html_module.escape(url)}\">🔗 Источник</a>")
                if snippet:
                    parts.append(f"   {snippet}...")
            else:
                parts.append(f"{i}. <b>{title}</b>")
                if snippet:
                    parts.append(f"   {snippet}...")
            parts.append("")
    if not parts:
        return "🤷 Ничего не найдено."
    return "\n".join(parts)


@router.callback_query(F.data == "web_search")
async def cb_web_search(callback: types.CallbackQuery):
    if not callback.message:
        await callback.answer("Ошибка: сообщение не найдено", show_alert=True)
        return
    chat_id = callback.message.chat.id
    query = _last_user_query.get(chat_id, "")

    if not query:
        preview_text = callback.message.html_text or callback.message.text or ""
        import re
        if "Саммари:" in preview_text:
            match = re.search(r"Саммари:</b>\n(.*?)(?:\n\n|$)", preview_text)
            if match:
                query = match.group(1).strip()[:200]
        elif "Последние сообщения:" in preview_text:
            msgs = re.findall(r"👤 (.*?)\n", preview_text)
            if msgs:
                query = msgs[-1].strip()[:200]

    if not query:
        msg_text = callback.message.html_text or callback.message.text or ""
        msg_lines = [ln for ln in msg_text.split("\n") if ln.strip() and len(ln.strip()) > 10]
        if msg_lines:
            query = msg_lines[-1].strip()[:200]

    if not query:
        await callback.answer("Нет запроса для поиска", show_alert=True)
        return

    await callback.answer("🔍 Ищу в интернете...")
    try:
        text, sources, search_id = await search_with_ai_evaluation(query, TAVILY_API_KEY)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка поиска: {e}")
        return

    kb = InlineKeyboardBuilder()
    if search_id and sources:
        kb.row(types.InlineKeyboardButton(
            text="📄 Источники", callback_data=f"ws_sources:{search_id}",
        ))
    kb.row(types.InlineKeyboardButton(
        text="💾 Сохранить в заметки",
        callback_data=f"ws_save:{search_id}" if search_id else "ws_save:",
    ))

    for chunk in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
        await callback.message.answer(
            chunk, parse_mode="HTML", disable_web_page_preview=True,
            reply_markup=kb.as_markup() if len(kb.buttons) > 0 else None,
        )
        kb = InlineKeyboardBuilder()


@router.callback_query(F.data.startswith("ws_sources:"))
async def cb_ws_sources(callback: types.CallbackQuery):
    if not callback.data:
        return
    search_id = callback.data.split(":", 1)[1]
    if not search_id:
        await callback.answer("Нет данных для отображения", show_alert=True)
        return
    data = load_web_search(search_id)
    if not data:
        await callback.answer("Результаты не найдены или устарели", show_alert=True)
        return

    sources = data.get("sources", [])
    if not sources:
        await callback.answer("Источников нет", show_alert=True)
        return

    def clean_text(text: str, max_len: int = 150) -> str:
        import re
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s\u0400-\u04FF\u0600-\u06FF\u0400-\u04FF.,!?;:()\-–—]', '', text)
        text = re.sub(r'\.{2,}', '.', text)
        text = re.sub(r'\s*\.\s*', '. ', text)
        return text.strip()[:max_len]

    parts = [f"📄 <b>Источники для: {html.escape(data['query'])}</b>"]
    for i, src in enumerate(sources, 1):
        raw_title = src.get("title", f"Источник {i}")
        title = html.escape(clean_text(raw_title, 80))
        url = src.get("url", "")
        raw_text = src.get("text", "")
        snippet = html.escape(clean_text(raw_text, 120))

        if url:
            parts.append(f"[{i}] <b>{title}</b>")
            parts.append(f"    <a href=\"{html.escape(url)}\">🔗 Открыть источник</a>")
            if snippet:
                parts.append(f"    {snippet}...")
            parts.append("")
        else:
            parts.append(f"[{i}] <b>{title}</b>")
            if snippet:
                parts.append(f"    {snippet}...")
            parts.append("")

    text = "\n".join(parts)
    for chunk in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
        await callback.message.answer(
            chunk, parse_mode="HTML", disable_web_page_preview=True
        )
    await callback.answer()


@router.callback_query(F.data.startswith("ws_save:"))
async def cb_ws_save(callback: types.CallbackQuery):
    if not callback.data:
        return
    search_id = callback.data.split(":", 1)[1]

    data = None
    if search_id:
        data = load_web_search(search_id)

    if not data:
        if TAVILY_API_KEY:
            from services.tavily_search import search_with_fallback
            query = _last_user_query.get(callback.message.chat.id, "")
            if query:
                text, sources, sid = await search_with_fallback(query, TAVILY_API_KEY, 5)
                data = {
                    "query": query,
                    "sources": sources,
                    "ai_summary": text,
                }
                if sources and text:
                    save_web_search_with_id(sid, query, sources, text)

    if not data:
        await callback.answer(
            "❌ Нет результатов для сохранения. Попробуйте поиск заново.",
            show_alert=True,
        )
        return

    if not data.get("ai_summary") and not data.get("sources"):
        await callback.answer("❌ Нет текста для сохранения.", show_alert=True)
        return

    sources = data.get("sources", [])
    ai_summary = data.get("ai_summary", "")
    query = data.get("query", "")

    if not query and not ai_summary:
        await callback.answer("❌ Нет текста для сохранения.", show_alert=True)
        return

    content = f"# Веб-поиск: {html.escape(query)}\n\n"
    if ai_summary:
        content += f"## ИИ-саммари\n{ai_summary}\n\n"
    content += "## Источники\n"
    for i, src in enumerate(sources, 1):
        url = html.escape(src.get("url", ""))
        title = html.escape(src.get("title", "")[:100])
        text_preview = html.escape(src.get("text", "")[:200])
        if url:
            content += f"{i}. <a href=\"{url}\">{title}</a>\n"
            content += f"   {text_preview}...\n"
        else:
            content += f"{i}. {title}\n"
            content += f"   {text_preview}...\n"

    fn = f"ws_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    path = os.path.join(NOTES_DIR, fn)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    await callback.message.edit_text(
        f"✅ Сохранено в <code>my_notes/{fn}</code>\n\n"
        f"📝 {html.escape(query[:100])}",
        parse_mode="HTML",
    )
    await callback.answer("✅ Сохранено", show_alert=False)
