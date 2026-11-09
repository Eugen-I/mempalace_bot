import asyncio
import html
import logging

import httpx

from config import (
    BING_SEARCH_API_KEY,
    GOOGLE_CSE_API_KEY,
    GOOGLE_CSE_ID,
)
from services.web_search_cache import save_web_search

logger = logging.getLogger("WebSearch")

# API URLs
DDG_API_URL = "https://api.duckduckgo.com/"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"
BING_SEARCH_URL = "https://api.bing.microsoft.com/v7.0/search"
YAHOO_SEARCH_URL = "https://search.yahoo.com/search"


# --- Парсинг HTML ---
_SNIPPET_SELECTORS = ".table-snippet, .result__snippet, .compText"


def _extract_href(node) -> str:
    """Извлекает и очищает URL ссылки из узла или его контекста."""
    import urllib.parse

    raw = ""
    if getattr(node, "tag", None) == "a":
        raw = node.attributes.get("href") or ""
    if not raw:
        child_a = node.css_first("a")
        if child_a:
            raw = child_a.attributes.get("href") or ""
    if not raw and getattr(node, "parent", None):
        if node.parent.tag == "a":
            raw = node.parent.attributes.get("href") or ""
        else:
            parent_a = node.parent.css_first("a")
            if parent_a:
                raw = parent_a.attributes.get("href") or ""
            elif getattr(node.parent, "parent", None):
                gp_a = node.parent.parent.css_first("a.result__url, a.result-link, a")
                if gp_a:
                    raw = gp_a.attributes.get("href") or ""

    if not raw:
        return ""

    if "uddg=" in raw:
        try:
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            uddg = qs.get("uddg")
            if uddg and uddg[0]:
                return uddg[0]
        except Exception as exc:
            logger.debug("[WebSearch] Failed to parse uddg redirect: %s", exc)

    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return ""


def _collect_snippets(html_text: str, selectors: str, min_len: int,
                      max_results: int) -> list[dict]:
    """Извлекает сниппеты через selectolax (вместо regex-парсинга HTML)."""
    from selectolax.parser import HTMLParser

    results = []
    tree = HTMLParser(html_text)
    for node in tree.css(selectors):
        text = node.text(strip=True)
        if len(text) > min_len:
            url = _extract_href(node)
            results.append({"text": text, "url": url})
            if len(results) >= max_results:
                break
    return results


async def _parse_html_results(html_text: str, max_results: int) -> list[dict]:
    return _collect_snippets(html_text, _SNIPPET_SELECTORS, 20, max_results)


async def _google_search(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict]:
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        return []
    try:
        resp = await client.get(
            GOOGLE_CSE_URL,
            params={
                "key": GOOGLE_CSE_API_KEY,
                "cx": GOOGLE_CSE_ID,
                "q": query,
                "num": min(max_results, 10),
                "lr": "lang_ru|lang_en|lang_de",
                "safe": "off",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        return [
            {"text": item.get("snippet", ""), "url": item.get("link", "")}
            for item in items[:max_results]
        ]
    except Exception as e:
        logger.warning(f"Google CSE search failed: {e}")
        return []


async def _bing_search(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict]:
    if not BING_SEARCH_API_KEY:
        return []
    try:
        headers = {"Ocp-Apim-Subscription-Key": BING_SEARCH_API_KEY}
        resp = await client.get(
            BING_SEARCH_URL,
            params={"q": query, "count": max_results, "mkt": "ru-RU", "safeSearch": "Off"},
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("webPages", {}).get("value", [])
        return [
            {"text": page.get("snippet", ""), "url": page.get("url", "")}
            for page in pages[:max_results]
        ]
    except Exception as e:
        logger.warning(f"Bing search failed: {e}")
        return []


async def _yahoo_search(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict]:
    try:
        resp = await client.get(
            YAHOO_SEARCH_URL,
            params={"p": query, "n": max_results, "lang": "ru"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15.0,
        )
        resp.raise_for_status()
        return _collect_snippets(resp.text, ".compText", 30, max_results)
    except Exception as e:
        logger.warning(f"Yahoo search failed: {e}")
        return []


async def _ddg_search(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict]:
    try:
        resp = await client.get(
            DDG_API_URL,
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        if resp.status_code == 202:
            await asyncio.sleep(0.5)
            resp = await client.get(
                DDG_API_URL,
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=15.0,
            )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("Results", []) + data.get("RelatedTopics", [])
        return [
            {"text": r.get("Text", ""), "url": r.get("FirstURL", "")}
            for r in results if isinstance(r, dict) and r.get("Text")
        ][:max_results]
    except Exception:
        return []


async def _search_all_engines(query: str, max_per_engine: int) -> list[dict]:
    all_sources = []
    seen_urls = set()

    async with httpx.AsyncClient(timeout=15.0) as client:
        tasks = []

        tasks.append(_ddg_search(client, query, max_per_engine))

        if GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID:
            tasks.append(_google_search(client, query, max_per_engine))

        if BING_SEARCH_API_KEY:
            tasks.append(_bing_search(client, query, max_per_engine))

        tasks.append(_yahoo_search(client, query, max_per_engine))

        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in all_results:
            if isinstance(result, Exception) or not result:
                continue
            for item in result:
                url = item.get("url", "")
                text = item.get("text", "").strip()
                if text and url and url not in seen_urls:
                    seen_urls.add(url)
                    all_sources.append({"text": text, "url": url})

    return all_sources


async def search_web(query: str, max_results: int = 5) -> str:
    """Быстрый поиск через DDG Instant Answer + fallback."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                DDG_API_URL,
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                    "t": "mempalace_bot",
                },
            )
            if resp.status_code == 202:
                await asyncio.sleep(0.5)
                resp = await client.get(
                    DDG_API_URL,
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1,
                        "t": "mempalace_bot",
                    },
                )
            resp.raise_for_status()
            data = resp.json()

        parts = []

        abstract = data.get("AbstractText", "")
        if abstract:
            source = data.get("AbstractSource", "")
            abstract_url = data.get("AbstractURL", "")
            line = f"📖 {html.escape(abstract)}"
            if source:
                if abstract_url:
                    line += (
                        f'\n   Источник: <a href="{html.escape(abstract_url)}">'
                        f'{html.escape(source)}</a>'
                    )
                else:
                    line += f"\n   Источник: {html.escape(source)}"
            elif abstract_url:
                line += f'\n   <a href="{html.escape(abstract_url)}">Источник</a>'
            parts.append(line)
            parts.append("")

        definition = data.get("Definition", "")
        if definition:
            parts.append(f"📝 {html.escape(definition)}")
            parts.append("")

        heading = data.get("Heading", "")
        if heading and not abstract:
            parts.append(f"🏷 {html.escape(heading)}")
            parts.append("")

        results = data.get("Results", []) or []
        related = data.get("RelatedTopics", []) or []

        all_results = list(results)
        for item in related:
            if isinstance(item, dict) and "Text" in item:
                all_results.append(item)
            elif isinstance(item, dict) and "Topics" in item:
                all_results.extend(item["Topics"])

        if all_results:
            parts.append(f"🔍 Результаты по «{html.escape(query)}»:")
            for i, r in enumerate(all_results[:max_results], 1):
                text = r.get("Text", "") or r.get("Result", "")
                url = r.get("FirstURL", "")
                if text:
                    text_esc = html.escape(text)
                    if url:
                        parts.append(f'{i}. <a href="{html.escape(url)}">{text_esc}</a>')
                    else:
                        parts.append(f"{i}. {text_esc}")
            parts.append("")

        result = "\n".join(parts).strip()
        if result:
            return f"🌐 <b>Результаты поиска</b>\n\n{result}"

        # 2. Fallback: Lite
        logger.info(f"[WebSearch] Instant Answer пустой, пробуем Lite для: {query}")
        async with httpx.AsyncClient(timeout=15.0) as client:
            html_resp = await client.post(
                DDG_LITE_URL,
                data={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            html_resp.raise_for_status()
            html_results = await _parse_html_results(html_resp.text, max_results)

        if html_results:
            parts = [f"🔍 Результаты по «{html.escape(query)}» (Lite):"]
            for i, r in enumerate(html_results, 1):
                text_esc = html.escape(r["text"])
                url = r.get("url", "")
                if url:
                    parts.append(f'{i}. <a href="{html.escape(url)}">{text_esc}</a>')
                else:
                    parts.append(f"{i}. {text_esc}")
            return "🌐 <b>Результаты поиска</b>\n\n" + "\n".join(parts)

        # 3. Последний fallback: полный HTML
        logger.info(f"[WebSearch] Lite пустой, пробуем полный HTML для: {query}")
        async with httpx.AsyncClient(timeout=15.0) as client:
            html_resp = await client.post(
                DDG_HTML_URL,
                data={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            html_resp.raise_for_status()
            html_results = await _parse_html_results(html_resp.text, max_results)

        if html_results:
            parts = [f"🔍 Результаты по «{html.escape(query)}» (HTML):"]
            for i, r in enumerate(html_results, 1):
                text_esc = html.escape(r["text"])
                url = r.get("url", "")
                if url:
                    parts.append(f'{i}. <a href="{html.escape(url)}">{text_esc}</a>')
                else:
                    parts.append(f"{i}. {text_esc}")
            return "🌐 <b>Результаты поиска</b>\n\n" + "\n".join(parts)

        return f"🤷 Ничего не найдено по запросу «{html.escape(query)}»."

    except httpx.HTTPStatusError as e:
        logger.error(f"Web search HTTP error: {e.response.status_code} - {e.response.text[:200]}")
        return f"❌ Ошибка поиска: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error(f"Web search error: {e}", exc_info=True)
        return f"❌ Ошибка поиска: {e!s}"


async def deep_search_web(query: str) -> dict:
    """Глубокий поиск: несколько запросов с разных ракурсов, проверка ИИ, сумаризация."""
    from config import TAVILY_API_KEY
    from services.tavily_search import search_tavily

    subqueries = [
        query,
        f"{query} обзор",
        f"{query} сравнение",
        f"{query} характеристики",
        f"{query} отзывы",
        f"{query} цена",
        f"{query} плюсы минусы",
        f"{query} альтернативы",
        f"лучшие {query}",
        f"{query} 2024",
    ]

    all_sources = []
    seen_urls = set()

    for sq in subqueries:
        sources = await _search_all_engines(sq, 3)
        for src in sources:
            url = src.get("url", "")
            text = src.get("text", "").strip()
            if text and url and url not in seen_urls:
                seen_urls.add(url)
                all_sources.append({"text": text, "url": url})
                if len(all_sources) >= 15:
                    break

        await asyncio.sleep(0.2)

        if len(all_sources) >= 15:
            break

    # Если бесплатные движки не дали результатов, используем Tavily
    if not all_sources and TAVILY_API_KEY:
        result = await search_tavily(query, TAVILY_API_KEY, 5)
        if "error" not in result:
            for r in result.get("results", []):
                url = r.get("url", "")
                text = r.get("snippet", r.get("content", ""))[:500].strip()
                if text and url and url not in seen_urls:
                    seen_urls.add(url)
                    all_sources.append({"text": text, "url": url, "title": r.get("title", "")})
                    if len(all_sources) >= 15:
                        break

    if not all_sources:
        return {"error": "🤷 Не удалось найти источники для глубокого поиска."}

    # Формируем контекст для ИИ
    sources_text = ""
    for i, src in enumerate(all_sources, 1):
        sources_text += f"[{i}] {src['text']}\nИсточник: {src['url']}\n\n"

    # Промпт для ИИ-сумаризации
    ai_prompt = (
        "Ты — исследователь. Проанализируй найденные источники и напиши подробный, "
        "объективный обзор по запросу пользователя.\n\n"
        f"Запрос: {query}\n\n"
        f"Источники ({len(all_sources)}):\n{sources_text}\n"
        "КРИТИЧЕСКИ ВАЖНО:\n"
        "— ВСЁ содержание источников (на английском, китайском, "
        "немецком и др.) ОБЯЗАТЕЛЬНО переведи на русский перед использованием.\n"
        "— НИКОГДА не цитируй исходный текст на иностранном языке — "
        "только русский перевод.\n"
        "— Если источник на китайском/английском — переведи его смысл на русский.\n\n"
        "Требования:\n"
        "1. Пиши ТОЛЬКО на русском кириллицей\n"
        "2. Структурируй: Введение, Основные факты, Сравнение/Альтернативы, Вывод\n"
        "3. Ссылайся на источники в квадратных скобках [1], [2]...\n"
        "4. Указывай активные ссылки в конце\n"
        "5. Будь объективен, отмечай противоречия между источниками\n"
        "6. Укажи достоверность: высоко/средне/низко для ключевых фактов"
    )

    try:
        from services.ai_engine import get_ai_response_async, get_current_ai
        engine, model = get_current_ai()
        ai_response = await get_ai_response_async(
            engine, model,
            [{"role": "user", "content": ai_prompt}],
            context="",
            user_query=query,
        )

        # Сохраняем в кэш
        search_id = save_web_search(query, all_sources, ai_response)

        return {
            "search_id": search_id,
            "query": query,
            "sources": all_sources,
            "ai_summary": ai_response,
            "total_sources": len(all_sources),
        }

    except Exception as e:
        logger.error("Deep search AI failed: %s", e)
        search_id = save_web_search(query, all_sources, "")
        return {
            "search_id": search_id,
            "query": query,
            "sources": all_sources,
            "ai_summary": "",
            "total_sources": len(all_sources),
            "error": "Ошибка ИИ при глубоком поиске",
        }
