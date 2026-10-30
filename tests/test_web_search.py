"""Unit tests for services.web_search.

Covers HTML result parsing, per-engine searches, multi-engine aggregation,
search_web formatting/fallbacks and deep search.
"""

import httpx
import pytest

import services.web_search as ws
import services.web_search_cache as wsc

SNIPPET_HTML = '<table><tr><td class="table-snippet">{}</td></tr></table>'


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(wsc, "WEB_SEARCH_CACHE_DIR", tmp_path / "cache")
    wsc.WEB_SEARCH_CACHE_DIR.mkdir(exist_ok=True)
    yield wsc.WEB_SEARCH_CACHE_DIR


# ---------- _parse_html_results ----------


@pytest.mark.asyncio
async def test_parse_html_table_snippets():
    html_text = (
        SNIPPET_HTML.format('Короткий текст из таблицы длиннее 20 символов')
        + SNIPPET_HTML.format('Второй сниппет длиннее двадцати символов')
    )
    out = await ws._parse_html_results(html_text, 5)
    assert len(out) >= 2
    assert out[0]["text"].startswith("Короткий текст")


@pytest.mark.asyncio
async def test_parse_html_result_snippets():
    html_text = (
        '<a class="result__snippet">Сниппет результата поиска очень длинный текст</a>'
    )
    out = await ws._parse_html_results(html_text, 5)
    texts = {r["text"] for r in out}
    assert len(out) >= 1
    assert texts == {"Сниппет результата поиска очень длинный текст"}


@pytest.mark.asyncio
async def test_parse_html_result_snippets_skips_short_and_stops_at_max():
    html_text = (
        '<a class="result__snippet">коротко</a>'
        '<a class="result__snippet">Первый длинный сниппет результата поиска</a>'
        '<a class="result__snippet">Второй длинный сниппет результата поиска</a>'
    )
    out = await ws._parse_html_results(html_text, 1)
    assert out == [{"text": "Первый длинный сниппет результата поиска", "url": ""}]


@pytest.mark.asyncio
async def test_parse_html_generic_class_skips_blank_and_stops_at_max():
    html_text = (
        '<div class="table-snippet">                              </div>'
        '<div class="result__snippet">Длинный сниппет из общего паттерна один</div>'
        '<div class="result__snippet">Длинный сниппет из общего паттерна два</div>'
    )
    out = await ws._parse_html_results(html_text, 1)
    assert out == [{"text": "Длинный сниппет из общего паттерна один", "url": ""}]


@pytest.mark.asyncio
async def test_parse_html_generic_class():
    html_text = '<div class="table-snippet">Длинный сниппет из общего паттерна</div>'
    out = await ws._parse_html_results(html_text, 5)
    assert len(out) >= 1


@pytest.mark.asyncio
async def test_parse_html_skips_short():
    html_text = SNIPPET_HTML.format('коротко')
    out = await ws._parse_html_results(html_text, 5)
    assert out == []


@pytest.mark.asyncio
async def test_parse_html_respects_max_results():
    html_text = (SNIPPET_HTML.format('Длинный сниппет таблицы номер ноль') * 10)
    out = await ws._parse_html_results(html_text, 2)
    assert len(out) <= 2


@pytest.mark.asyncio
async def test_parse_html_unescapes():
    html_text = SNIPPET_HTML.format('Текст &amp; &lt;b&gt;пример&lt;/b&gt; ещё')
    out = await ws._parse_html_results(html_text, 5)
    assert out and "&amp;" not in out[0]["text"]
    assert "&lt;" not in out[0]["text"]


# ---------- engine helpers ----------


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("GET", "http://x"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self._json


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self._responses.pop(0)

    async def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_google_search_no_key(monkeypatch):
    monkeypatch.setattr(ws, "GOOGLE_CSE_API_KEY", None)
    monkeypatch.setattr(ws, "GOOGLE_CSE_ID", None)
    assert await ws._google_search(FakeClient([]), "q", 5) == []


@pytest.mark.asyncio
async def test_google_search_success(monkeypatch):
    monkeypatch.setattr(ws, "GOOGLE_CSE_API_KEY", "key")
    monkeypatch.setattr(ws, "GOOGLE_CSE_ID", "cx")
    client = FakeClient([FakeResponse(json_data={
        "items": [
            {"snippet": "сниппет", "link": "http://a"},
            {"snippet": "два", "link": "http://b"},
        ],
    })])
    out = await ws._google_search(client, "запрос", 5)
    assert len(out) == 2
    assert out[0]["url"] == "http://a"
    assert client.calls[0][1] == ws.GOOGLE_CSE_URL


@pytest.mark.asyncio
async def test_google_search_error(monkeypatch):
    monkeypatch.setattr(ws, "GOOGLE_CSE_API_KEY", "key")
    monkeypatch.setattr(ws, "GOOGLE_CSE_ID", "cx")
    client = FakeClient([FakeResponse(status_code=500)])
    assert await ws._google_search(client, "q", 5) == []


@pytest.mark.asyncio
async def test_bing_search_no_key(monkeypatch):
    monkeypatch.setattr(ws, "BING_SEARCH_API_KEY", None)
    assert await ws._bing_search(FakeClient([]), "q", 5) == []


@pytest.mark.asyncio
async def test_bing_search_success(monkeypatch):
    monkeypatch.setattr(ws, "BING_SEARCH_API_KEY", "bkey")
    client = FakeClient([FakeResponse(json_data={
        "webPages": {"value": [{"snippet": "снип", "url": "http://b1"}]},
    })])
    out = await ws._bing_search(client, "q", 5)
    assert out == [{"text": "снип", "url": "http://b1"}]


@pytest.mark.asyncio
async def test_bing_search_error(monkeypatch):
    monkeypatch.setattr(ws, "BING_SEARCH_API_KEY", "bkey")
    client = FakeClient([FakeResponse(status_code=429)])
    assert await ws._bing_search(client, "q", 5) == []


@pytest.mark.asyncio
async def test_yahoo_search_success():
    html_text = (
        '<div class="compText">Длинный текст результата яндекса длиннее тридцати</div>'
        '<div class="compText">Ещё один сниппет яндекса длинный текст</div>'
    )
    client = FakeClient([FakeResponse(text=html_text)])
    out = await ws._yahoo_search(client, "q", 5)
    assert len(out) == 2
    assert "compText" not in out[0]["text"]


@pytest.mark.asyncio
async def test_yahoo_search_short_skipped():
    client = FakeClient([FakeResponse(text='<div class="compText">короткий</div>')])
    assert await ws._yahoo_search(client, "q", 5) == []


@pytest.mark.asyncio
async def test_yahoo_search_error():
    client = FakeClient([FakeResponse(status_code=403)])
    assert await ws._yahoo_search(client, "q", 5) == []


@pytest.mark.asyncio
async def test_yahoo_search_skips_blank_and_stops_at_max():
    html_text = (
        '<div class="compText">                                          </div>'
        '<div class="compText">Первый длинный текст результата яндекса более тридцати</div>'
        '<div class="compText">Второй длинный текст результата яндекса более тридцати</div>'
    )
    client = FakeClient([FakeResponse(text=html_text)])
    out = await ws._yahoo_search(client, "q", 1)
    assert out == [{"text": "Первый длинный текст результата яндекса более тридцати", "url": ""}]


@pytest.mark.asyncio
async def test_ddg_search_success():
    client = FakeClient([FakeResponse(json_data={
        "Results": [{"Text": "первый", "FirstURL": "http://d1"}],
        "RelatedTopics": [{"Text": "второй", "FirstURL": "http://d2"}],
    })])
    out = await ws._ddg_search(client, "q", 5)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_ddg_search_retry_on_202(monkeypatch):

    async def fake_sleep(x):
        return None

    monkeypatch.setattr(ws.asyncio, "sleep", fake_sleep)
    client = FakeClient([
        FakeResponse(status_code=202, json_data={}),
        FakeResponse(json_data={"Results": [{"Text": "после ретрая", "FirstURL": "http://r"}]}),
    ])
    out = await ws._ddg_search(client, "q", 5)
    assert out[0]["text"] == "после ретрая"
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_ddg_search_error():
    client = FakeClient([FakeResponse(status_code=500)])
    assert await ws._ddg_search(client, "q", 5) == []


@pytest.mark.asyncio
async def test_ddg_search_filters_non_dict():
    client = FakeClient([FakeResponse(json_data={
        "Results": [{"Text": "ок", "FirstURL": "http://x"}],
        "RelatedTopics": ["not a dict", {"Topics": []}],
    })])
    out = await ws._ddg_search(client, "q", 5)
    assert out == [{"text": "ок", "url": "http://x"}]


# ---------- _search_all_engines ----------


@pytest.mark.asyncio
async def test_search_all_engines_dedups(monkeypatch):
    async def fake_ddg(client, q, n):
        return [{"text": "текст", "url": "http://same"}]

    async def fake_yahoo(client, q, n):
        return [{"text": "текст", "url": "http://same"}, {"text": "текст2", "url": "http://other"}]

    async def fake_google(client, q, n):
        return []

    monkeypatch.setattr(ws, "GOOGLE_CSE_API_KEY", None)
    monkeypatch.setattr(ws, "BING_SEARCH_API_KEY", None)
    monkeypatch.setattr(ws, "_ddg_search", fake_ddg)
    monkeypatch.setattr(ws, "_yahoo_search", fake_yahoo)
    monkeypatch.setattr(ws, "_google_search", fake_google)
    out = await ws._search_all_engines("q", 5)
    assert len(out) == 2
    urls = [s["url"] for s in out]
    assert urls.count("http://same") == 1


@pytest.mark.asyncio
async def test_search_all_engines_skips_empty_text(monkeypatch):
    async def fake_ddg(client, q, n):
        return [{"text": "   ", "url": "http://a"}]

    async def fake_yahoo(client, q, n):
        return []

    monkeypatch.setattr(ws, "GOOGLE_CSE_API_KEY", None)
    monkeypatch.setattr(ws, "BING_SEARCH_API_KEY", None)
    monkeypatch.setattr(ws, "_ddg_search", fake_ddg)
    monkeypatch.setattr(ws, "_yahoo_search", fake_yahoo)
    assert await ws._search_all_engines("q", 5) == []


@pytest.mark.asyncio
async def test_search_all_engines_with_keys(monkeypatch):
    async def fake_google(client, q, n):
        return [{"text": "гугл", "url": "http://g"}]

    async def fake_bing(client, q, n):
        return [{"text": "бинг", "url": "http://b"}]

    async def fake_ddg(client, q, n):
        return []

    async def fake_yahoo(client, q, n):
        return []

    monkeypatch.setattr(ws, "GOOGLE_CSE_API_KEY", "k")
    monkeypatch.setattr(ws, "GOOGLE_CSE_ID", "cx")
    monkeypatch.setattr(ws, "BING_SEARCH_API_KEY", "b")
    monkeypatch.setattr(ws, "_google_search", fake_google)
    monkeypatch.setattr(ws, "_bing_search", fake_bing)
    monkeypatch.setattr(ws, "_ddg_search", fake_ddg)
    monkeypatch.setattr(ws, "_yahoo_search", fake_yahoo)
    out = await ws._search_all_engines("q", 5)
    assert len(out) == 2
    assert out[0]["url"] == "http://g"


# ---------- search_web ----------


@pytest.mark.asyncio
async def test_search_web_retry_on_202(monkeypatch):
    async def fake_sleep(x):
        return None

    client = FakeClient([
        FakeResponse(status_code=202, json_data={}),
        FakeResponse(json_data={
            "AbstractText": "после ретрая",
            "Results": [],
            "RelatedTopics": [],
        }),
    ])
    monkeypatch.setattr(ws.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("q")
    assert "после ретрая" in out
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_search_web_abstract(monkeypatch):
    client = FakeClient([FakeResponse(json_data={
        "AbstractText": "Текст абстракта",
        "AbstractSource": "Википедия",
        "Results": [],
        "RelatedTopics": [],
    })])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("вопрос")
    assert "🌐" in out
    assert "Текст абстракта" in out
    assert "Википедия" in out


@pytest.mark.asyncio
async def test_search_web_definition(monkeypatch):
    client = FakeClient([FakeResponse(json_data={
        "Definition": "Определение термина",
        "Results": [],
        "RelatedTopics": [],
    })])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("термин")
    assert "Определение термина" in out


@pytest.mark.asyncio
async def test_search_web_heading_without_abstract(monkeypatch):
    client = FakeClient([FakeResponse(json_data={
        "Heading": "Заголовок",
        "Results": [],
        "RelatedTopics": [],
    })])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("x")
    assert "Заголовок" in out


@pytest.mark.asyncio
async def test_search_web_results_and_related(monkeypatch):
    client = FakeClient([FakeResponse(json_data={
        "Results": [{"Text": "результат 1", "FirstURL": "http://r1"}],
        "RelatedTopics": [
            {"Text": "связанный", "FirstURL": "http://r2"},
            {"Topics": [{"Text": "вложенный", "FirstURL": "http://r3"}]},
        ],
    })])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("q")
    assert "результат 1" in out
    assert "связанный" in out
    assert "вложенный" in out
    assert "http://r1" in out


@pytest.mark.asyncio
async def test_search_web_related_skips_non_standard_and_empty_fields(monkeypatch):
    client = FakeClient([FakeResponse(json_data={
        "Results": [
            {"Text": "", "FirstURL": "http://no-text"},
            {"Text": "текст без ссылки"},
            {"Text": "полный результат", "FirstURL": "http://ok"},
        ],
        "RelatedTopics": [
            {"x": 1},
            {"Topics": [{"Text": "вложенный нормальный", "FirstURL": "http://v"}]},
        ],
    })])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("q")
    assert "полный результат" in out
    assert "вложенный нормальный" in out
    assert "http://no-text" not in out
    assert "2. текст без ссылки" in out


@pytest.mark.asyncio
async def test_search_web_escapes_html(monkeypatch):
    client = FakeClient([FakeResponse(json_data={
        "AbstractText": "текст <b>тега</b>",
        "Results": [],
        "RelatedTopics": [],
    })])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("<script>")
    assert "<b>тега</b>" not in out
    assert "&lt;b&gt;" in out


@pytest.mark.asyncio
async def test_search_web_empty_then_lite_fallback(monkeypatch):
    client = FakeClient([
        FakeResponse(json_data={"Results": [], "RelatedTopics": []}),
        FakeResponse(text=SNIPPET_HTML.format('Сниппет из лайта длинный текст')),
    ])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("q")
    assert "Lite" in out
    assert "Сниппет из лайта" in out
    assert client.calls[1][0] == "post"


@pytest.mark.asyncio
async def test_search_web_lite_empty_then_html(monkeypatch):
    client = FakeClient([
        FakeResponse(json_data={"Results": [], "RelatedTopics": []}),
        FakeResponse(text=SNIPPET_HTML.format('нет результатов')),
        FakeResponse(text=SNIPPET_HTML.format('Полный html сниппет длинный текст')),
    ])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("q")
    assert "HTML" in out
    assert "Полный html сниппет" in out


@pytest.mark.asyncio
async def test_search_web_nothing_found(monkeypatch):
    client = FakeClient([
        FakeResponse(json_data={"Results": [], "RelatedTopics": []}),
        FakeResponse(text="<table><tr><td class=\"table-snippet\">нет</td></tr></table>"),
        FakeResponse(text="<table><tr><td class=\"table-snippet\">нет</td></tr></table>"),
    ])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("q")
    assert "Ничего не найдено" in out


@pytest.mark.asyncio
async def test_search_web_http_error(monkeypatch):
    client = FakeClient([FakeResponse(status_code=429)])
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(client))
    out = await ws.search_web("q")
    assert "HTTP 429" in out


@pytest.mark.asyncio
async def test_search_web_generic_error(monkeypatch):
    class BoomClient(FakeClient):
        async def get(self, url, **kwargs):
            raise RuntimeError("сеть упала")

    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *a, **k: _CtxManager(BoomClient([])))
    out = await ws.search_web("q")
    assert "Ошибка поиска" in out
    assert "сеть упала" in out


class _CtxManager:
    def __init__(self, client):
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *a):
        return False


# ---------- deep_search_web ----------


@pytest.mark.asyncio
async def test_deep_search_web_no_sources(monkeypatch):
    import config

    async def fake_all(query, n):
        return []

    monkeypatch.setattr(ws, "_search_all_engines", fake_all)
    monkeypatch.setattr(config, "TAVILY_API_KEY", None)
    out = await ws.deep_search_web("запрос")
    assert out == {"error": "🤷 Не удалось найти источники для глубокого поиска."}


@pytest.mark.asyncio
async def test_deep_search_web_with_sources_and_ai(monkeypatch, cache_dir):
    async def fake_all(query, n):
        if "цена" in query:
            return [{"text": "источник о цене", "url": "http://price"}]
        return [{"text": "источник", "url": "http://src"}]

    async def fake_sleep(x):
        return None

    async def fake_ai(engine, model, messages, **kwargs):
        return "ИИ-сумаризация готова"

    def fake_current_ai():
        return "gemini", "gemini-pro"

    monkeypatch.setattr(ws, "_search_all_engines", fake_all)
    monkeypatch.setattr(ws.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    monkeypatch.setattr("services.ai_engine.get_current_ai", fake_current_ai)
    out = await ws.deep_search_web("запрос")
    assert out["ai_summary"] == "ИИ-сумаризация готова"
    assert out["total_sources"] >= 2
    assert out["search_id"]
    # кэш сохранён
    assert (cache_dir / f"{out['search_id']}.json").exists()


@pytest.mark.asyncio
async def test_deep_search_web_breaks_at_15_sources(monkeypatch, cache_dir):
    async def fake_all(query, n):
        return [
            {"text": f"источник {i}", "url": f"http://s{i}"}
            for i in range(16)
        ]

    async def fake_sleep(x):
        return None

    async def fake_ai(engine, model, messages, **kwargs):
        return "обзор"

    def fake_current_ai():
        return "gemini", "g"

    monkeypatch.setattr(ws, "_search_all_engines", fake_all)
    monkeypatch.setattr(ws.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    monkeypatch.setattr("services.ai_engine.get_current_ai", fake_current_ai)
    out = await ws.deep_search_web("запрос")
    assert out["total_sources"] == 15


@pytest.mark.asyncio
async def test_deep_search_web_ai_failure(monkeypatch, cache_dir):
    async def fake_all(query, n):
        return [{"text": "только источник", "url": "http://one"}]

    async def fake_sleep(x):
        return None

    async def fake_ai(engine, model, messages, **kwargs):
        raise RuntimeError("ИИ упал")

    def fake_current_ai():
        return "gemini", "gemini-pro"

    monkeypatch.setattr(ws, "_search_all_engines", fake_all)
    monkeypatch.setattr(ws.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    monkeypatch.setattr("services.ai_engine.get_current_ai", fake_current_ai)
    out = await ws.deep_search_web("запрос")
    assert out["ai_summary"] == ""
    # deep_search_web возвращает "Ошибка ИИ" в error при неудаче
    assert "ИИ" in out["error"]


@pytest.mark.asyncio
async def test_deep_search_web_tavily_fallback(monkeypatch, cache_dir):
    import config

    async def fake_all(query, n):
        return []

    async def fake_sleep(x):
        return None

    async def fake_tavily(q, key, n):
        return {"results": [
            {"url": "http://t1", "snippet": "тайвили сниппет", "title": "Тайв"},
        ]}

    async def fake_ai(engine, model, messages, **kwargs):
        return "обзор"

    def fake_current_ai():
        return "gemini", "g"

    monkeypatch.setattr(ws, "_search_all_engines", fake_all)
    monkeypatch.setattr(ws.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "tvkey")
    monkeypatch.setattr("services.tavily_search.search_tavily", fake_tavily)
    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    monkeypatch.setattr("services.ai_engine.get_current_ai", fake_current_ai)
    out = await ws.deep_search_web("запрос")
    assert out["total_sources"] == 1
    assert out["sources"][0]["url"] == "http://t1"
    cached = wsc.load_web_search(out["search_id"])
    assert cached["sources"][0]["title"] == "Тайв"


@pytest.mark.asyncio
async def test_deep_search_web_tavily_error_result(monkeypatch, cache_dir):
    import config

    async def fake_all(query, n):
        return []

    async def fake_sleep(x):
        return None

    async def fake_tavily(q, key, n):
        return {"error": "лимит исчерпан"}

    monkeypatch.setattr(ws, "_search_all_engines", fake_all)
    monkeypatch.setattr(ws.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "tvkey")
    monkeypatch.setattr("services.tavily_search.search_tavily", fake_tavily)
    out = await ws.deep_search_web("запрос")
    assert "error" in out
    assert "Не удалось найти источники" in out["error"]


@pytest.mark.asyncio
async def test_deep_search_web_tavily_skips_blank_and_stops_at_15(monkeypatch, cache_dir):
    import config

    async def fake_all(query, n):
        return []

    async def fake_sleep(x):
        return None

    async def fake_tavily(q, key, n):
        return {"results": [
            {"url": "", "snippet": "пустой url", "title": "skip"},
        ] + [
            {"url": f"http://t{i}", "snippet": f"сниппет {i}", "title": f"Т{i}"}
            for i in range(16)
        ]}

    async def fake_ai(engine, model, messages, **kwargs):
        return "обзор"

    def fake_current_ai():
        return "gemini", "g"

    monkeypatch.setattr(ws, "_search_all_engines", fake_all)
    monkeypatch.setattr(ws.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "tvkey")
    monkeypatch.setattr("services.tavily_search.search_tavily", fake_tavily)
    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    monkeypatch.setattr("services.ai_engine.get_current_ai", fake_current_ai)
    out = await ws.deep_search_web("запрос")
    assert out["total_sources"] == 15
    assert all(s["url"] for s in out["sources"])
