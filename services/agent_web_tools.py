"""services/agent_web_tools.py — инструмент веб-поиска для агента."""

import html
import logging
import re

from services.agent_tools import CAT_WEB, register_tool
from services.web_search import search_web

logger = logging.getLogger("AgentWebTools")


@register_tool(
    "web_search",
    "Поиск актуальной информации в интернете (новости, статьи, документация, факты). "
    "Используй, когда данных нет во Дворце памяти или заметках, либо вопрос требует "
    "свежей информации из внешнего мира.",
    schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Поисковый запрос (ключевые слова на русском или английском)",
            },
            "limit": {
                "type": "integer",
                "description": "Количество результатов (по умолчанию 5)",
            },
        },
        "required": ["query"],
    },
    category=CAT_WEB,
)
async def _web_search(args: dict) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return "Ошибка: пустой поисковый запрос."
    limit = args.get("limit", 5)
    try:
        raw_res = await search_web(query, max_results=limit)
        text = re.sub(r"<br\s*/?>", "\n", raw_res)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text).strip()
        return text or "Ничего не найдено в интернете по этому запросу."
    except Exception as exc:
        logger.warning("[AGENT] web_search failed: %s", exc)
        return f"Ошибка веб-поиска: {exc}"
