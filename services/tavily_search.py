"""services/tavily_search.py — Tavily Search API integration for Telegram bot"""
import html
import logging

import httpx

logger = logging.getLogger("TavilySearch")

TAVILY_API_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_RESULTS = 5
DEFAULT_SEARCH_DEPTH = "advanced"


async def search_tavily(
    query: str,
    api_key: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    search_depth: str = DEFAULT_SEARCH_DEPTH,
    include_answer: bool = True,
    include_raw_content: bool = False,
    topic: str = "general",
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """
    Выполняет поиск через Tavily API.

    Args:
        query: Поисковый запрос
        api_key: Ключ API Tavily
        max_results: Максимальное количество результатов (по умолчанию 5)
        search_depth: Глубина поиска "basic" или "advanced"
        include_answer: Включить AI-ответ Tavily
        include_raw_content: Включить сырые контенты (обычно False для Telegram)
        topic: Тема поиска "general" или "news"
        timeout: Таймаут запроса в секундах

    Returns:
        dict с ключами: answer, results, error (если есть ошибка)
    """
    if not api_key:
        logger.error("TAVILY_API_KEY не найден в переменных окружения")
        return {
            "error": "❌ Ключ API Tavily не настроен. Установите TAVILY_API_KEY в .env"
        }

    if not query or not query.strip():
        return {"error": "❌ Пустой запрос для поиска"}

    query = query.strip()[:500]

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": min(max_results, 10),
        "search_depth": search_depth,
        "include_answer": include_answer,
        "include_raw_content": include_raw_content,
        "topic": topic,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(TAVILY_API_URL, json=payload)

            if response.status_code == 401:
                logger.error("Tavily API error: 401 Unauthorized - invalid API key")
                return {
                    "error": "❌ Ошибка аутентификации Tavily. Проверьте TAVILY_API_KEY"
                }

            if response.status_code == 429:
                logger.warning("Tavily API rate limit exceeded")
                return {
                    "error": "❌ Превышен лимит запросов к Tavily. Попробуйте позже."
                }

            response.raise_for_status()
            data = response.json()

            import secrets
            search_id = f"tvl_{secrets.token_hex(8)}"

            result = {
                "query": query,
                "answer": data.get("answer", ""),
                "results": data.get("results", []),
                "search_id": search_id,
            }

            logger.info(
                f"Tavily search completed for: {query}, "
                f"found {len(result['results'])} results"
            )
            return result

    except httpx.TimeoutException:
        logger.error(f"Tavily search timeout for query: {query}")
        return {"error": "❌ Превышен таймаут поиска. Попробуйте еще раз."}
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Tavily HTTP error: {e.response.status_code} - {e.response.text[:200]}"
        )
        return {"error": f"❌ Ошибка поиска: HTTP {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Tavily search error: {e}", exc_info=True)
        return {"error": f"❌ Ошибка поиска: {str(e)[:100]}"}


def format_results_for_telegram(
    answer: str,
    results: list[dict],
    max_results: int = 5,
) -> str:
    """
    Форматирует результаты поиска для отправки в Telegram (HTML).

    Args:
        answer: AI-ответ от Tavily
        results: Список результатов поиска
        max_results: Максимальное количество отображаемых результатов

    Returns:
        Отформатированный текст для Telegram
    """
    parts = []

    if answer:
        parts.append(f"🤖 <b>Ответ ИИ:</b>\n{html.escape(answer)}\n")

    if results:
        parts.append(
            f"🔍 <b>Результаты поиска "
            f"({len(results[:max_results])} из {len(results)}):</b>\n"
        )

        for i, result in enumerate(results[:max_results], 1):
            title = html.escape(result.get("title", "Без названия"))
            snippet = html.escape(result.get("snippet", result.get("content", ""))[:200])
            url = result.get("url", "")

            if url:
                parts.append(f"{i}. <b>{title}</b>")
                parts.append(f"   <a href=\"{html.escape(url)}\">🔗 Источник</a>")
                if snippet:
                    parts.append(f"   {snippet}...")
                parts.append("")
            else:
                parts.append(f"{i}. <b>{title}</b>")
                if snippet:
                    parts.append(f"   {snippet}...")
                parts.append("")

    if not parts:
        return "🤷 Ничего не найдено по запросу."

    return "\n".join(parts).strip()


async def search_with_fallback(
    query: str,
    tavily_api_key: str,
    max_results: int = 5,
) -> tuple[str, list[dict], str]:
    """
    Выполняет поиск с fallback на другие методы при ошибке Tavily.

    Возвращает:
        tuple: (formatted_text, sources_list, search_id)
    """
    from services.web_search_cache import save_web_search_with_id

    result = await search_tavily(query, tavily_api_key, max_results)

    if "error" in result:
        return result["error"], [], ""

    answer = result.get("answer", "")
    results = result.get("results", [])
    search_id = result.get("search_id", "")

    formatted = format_results_for_telegram(answer, results, max_results)

    sources = []
    for r in results:
        sources.append({
            "text": r.get("snippet", r.get("content", ""))[:200],
            "url": r.get("url", ""),
            "title": r.get("title", ""),
        })

    if search_id:
        save_web_search_with_id(search_id, query, sources, answer)

    return formatted, sources, search_id
