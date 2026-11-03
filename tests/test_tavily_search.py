"""Тесты services/tavily_search.py — интеграция Tavily API.

Покрытие: валидация ключа/запроса, HTTP-коды, таймаут, форматирование, fallback.
"""
import asyncio

import httpx

import services.tavily_search as tavily

# ─── search_tavily: валидация ───


def test_search_no_api_key():
    result = asyncio.run(tavily.search_tavily("запрос", ""))
    assert "error" in result
    assert "TAVILY_API_KEY" in result["error"]


def test_search_empty_query():
    result = asyncio.run(tavily.search_tavily("  ", "key123"))
    assert "error" in result


def test_search_query_trimmed_to_500(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"answer": "", "results": []}

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            captured["payload"] = json
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    long_query = "x" * 700
    result = asyncio.run(tavily.search_tavily(long_query, "key123"))
    assert "error" not in result
    assert len(captured["payload"]["query"]) == 500
    assert captured["payload"]["max_results"] == 5


def test_search_success(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"answer": "краткий ответ", "results": [{"title": "T1"}]}

    class FakeClient:
        def __init__(self, **kw):
            captured["timeout"] = kw.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(tavily.search_tavily("вопрос", "key123", timeout=7.5))
    assert result["answer"] == "краткий ответ"
    assert result["results"] == [{"title": "T1"}]
    assert result["search_id"].startswith("tvl_")
    assert captured["timeout"] == 7.5
    assert captured["url"] == tavily.TAVILY_API_URL


def test_search_401(monkeypatch):
    class FakeResp:
        status_code = 401

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(tavily.search_tavily("вопрос", "badkey"))
    assert "аутентификации" in result["error"]


def test_search_429(monkeypatch):
    class FakeResp:
        status_code = 429

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(tavily.search_tavily("вопрос", "key123"))
    assert "лимит" in result["error"]


def test_search_timeout(monkeypatch):
    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(tavily.search_tavily("вопрос", "key123"))
    assert "таймаут" in result["error"]


def test_search_http_error(monkeypatch):
    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            resp = httpx.Response(500, request=httpx.Request("POST", url))
            raise httpx.HTTPStatusError(
                "boom", request=resp.request, response=resp
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(tavily.search_tavily("вопрос", "key123"))
    assert "HTTP 500" in result["error"]


def test_search_generic_exception(monkeypatch):
    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            raise ValueError("сломалось")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(tavily.search_tavily("вопрос", "key123"))
    # Generic exception returns generic error message
    assert "Ошибка поиска" in result["error"]


def test_search_max_results_capped_at_10(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"answer": "", "results": []}

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            captured["payload"] = json
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    asyncio.run(tavily.search_tavily("q", "k", max_results=50))
    assert captured["payload"]["max_results"] == 10


# ─── format_results_for_telegram ───


def test_format_empty():
    assert tavily.format_results_for_telegram("", []) == "🤷 Ничего не найдено по запросу."


def test_format_with_answer_and_results():
    out = tavily.format_results_for_telegram(
        "Ответ <b>AI</b>",
        [{"title": "Заголовок", "snippet": "текст", "url": "https://x.ru"}],
    )
    assert "Ответ ИИ" in out
    assert "Ответ &lt;b&gt;AI&lt;/b&gt;" in out
    assert "Заголовок" in out
    assert "x.ru" in out


def test_format_result_without_url():
    out = tavily.format_results_for_telegram(
        "", [{"title": "Т1", "snippet": "сниппет"}]
    )
    assert "Т1" in out
    assert "сниппет" in out
    assert "Источник" not in out


def test_format_snippet_fallback_to_content():
    out = tavily.format_results_for_telegram(
        "", [{"title": "Т2", "content": "контент", "url": "https://y.ru"}]
    )
    assert "контент" in out


def test_format_snippet_truncated_to_200():
    long_snippet = "s" * 500
    out = tavily.format_results_for_telegram(
        "", [{"title": "Т3", "snippet": long_snippet, "url": "https://z.ru"}]
    )
    assert "..." in out
    snippet_line = [l.strip() for l in out.split("\n") if l.strip().startswith("s")][0]
    assert snippet_line.count("s") == 200


def test_format_max_results_limit():
    results = [{"title": f"T{i}"} for i in range(10)]
    out = tavily.format_results_for_telegram("", results, max_results=3)
    assert "3 из 10" in out
    assert out.count("T") == 3


def test_format_escapes_html_in_snippet():
    out = tavily.format_results_for_telegram(
        "", [{"title": "T", "snippet": "<script>alert(1)</script>", "url": "https://a.ru"}]
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


# ─── search_with_fallback ───


def test_fallback_error(monkeypatch):
    async def fake_search(query, api_key, max_results):
        return {"error": "❌ Что-то сломалось"}

    monkeypatch.setattr(tavily, "search_tavily", fake_search)
    formatted, sources, search_id = asyncio.run(
        tavily.search_with_fallback("q", "k")
    )
    assert sources == []
    assert search_id == ""
    assert "сломалось" in formatted


def test_fallback_success(monkeypatch):
    async def fake_search(query, api_key, max_results):
        return {
            "query": query,
            "answer": "ответ",
            "results": [{"title": "T", "snippet": "s", "url": "https://a.ru"}],
            "search_id": "tvl_abc",
        }

    saved = {}

    def fake_save(search_id, query, sources, answer):
        saved.update(search_id=search_id, query=query, sources=sources, answer=answer)

    monkeypatch.setattr(tavily, "search_tavily", fake_search)
    monkeypatch.setattr(
        "services.web_search_cache.save_web_search_with_id", fake_save
    )

    formatted, sources, search_id = asyncio.run(
        tavily.search_with_fallback("вопрос", "k", max_results=3)
    )
    assert search_id == "tvl_abc"
    assert len(sources) == 1
    assert saved["query"] == "вопрос"
    assert saved["answer"] == "ответ"
    assert "Ответ ИИ" in formatted


def test_format_url_without_snippet():
    out = tavily.format_results_for_telegram(
        "", [{"title": "Т3", "url": "https://z.ru"}]
    )
    assert "Т3" in out
    assert "Источник" in out


def test_fallback_success_without_search_id(monkeypatch):
    async def fake_search(query, api_key, max_results):
        return {
            "answer": "ответ",
            "results": [{"title": "T", "snippet": "s", "url": "https://a.ru"}],
        }

    monkeypatch.setattr(tavily, "search_tavily", fake_search)
    formatted, sources, search_id = asyncio.run(
        tavily.search_with_fallback("вопрос", "k")
    )
    assert search_id == ""
    assert len(sources) == 1
    assert "ответ" in formatted
