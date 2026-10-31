"""Unit tests for handlers.web_search_btn."""

import os
from types import SimpleNamespace

import pytest

from handlers import web_search_btn as wsb
from handlers.messages import _last_user_query


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeChat:
    def __init__(self, cid):
        self.id = cid


class FakeMessage:
    def __init__(self, uid=4242, chat_id=1, text="", html_text=None):
        self.from_user = FakeUser(uid)
        self.chat = FakeChat(chat_id)
        self.text = text
        self.html_text = html_text
        self.message_id = 1
        self.answers = []
        self.edited = []
        self.bot = SimpleNamespace()

    async def answer(self, text, parse_mode=None, reply_markup=None,
                     disable_web_page_preview=None):
        self.answers.append((text, parse_mode, reply_markup))
        return SimpleNamespace()

    async def edit_text(self, text, parse_mode=None):
        self.edited.append(text)


class FakeCb:
    def __init__(self, uid=4242, chat_id=1, data="", message=None, html_text=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid, chat_id=chat_id, html_text=html_text)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


def _enable(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    d = tmp_path / "notes"
    d.mkdir()
    monkeypatch.setattr(wsb, "NOTES_DIR", str(d))
    monkeypatch.setattr(wsb, "TAVILY_API_KEY", "")
    monkeypatch.delitem(_last_user_query, 1, raising=False)
    monkeypatch.delitem(_last_user_query, 99, raising=False)
    return d


# ---------- форматирование ----------


def test_format_free_search_results_basic():
    out = wsb._format_free_search_results(
        "query <x>",
        [{"text": "первый", "url": "http://a.ru"}, {"text": "второй", "url": ""}],
    )
    assert "Результаты поиска" in out
    assert "query &lt;x&gt;" in out
    assert "первый" in out
    assert '<a href="http://a.ru">' in out
    assert out.index("1. первый") < out.index("2. второй")


def test_format_free_search_results_empty_text_only_header():
    out = wsb._format_free_search_results("q", [{"text": "", "url": "u"}])
    assert out == "🤷 Ничего не найдено."


def test_format_tavily_results_with_answer():
    out = wsb._format_tavily_results(
        "Отв<ет",
        [{"title": "Т<а", "snippet": "снип", "url": "http://x"}],
    )
    assert "Ответ ИИ" in out
    assert "Отв&lt;ет" in out
    assert "Результаты поиска (1 из 5)" in out
    assert '<a href="http://x">' in out


def test_format_tavily_results_no_url():
    out = wsb._format_tavily_results("", [{"title": "т", "snippet": "с"}])
    assert "т" in out
    assert "🔗 Источник" not in out


def test_format_tavily_results_empty():
    assert wsb._format_tavily_results("", []) == "🤷 Ничего не найдено."


def test_format_tavily_results_many_results_truncated():
    results = [{"title": f"t{i}", "snippet": "s", "url": f"http://u{i}"} for i in range(10)]
    out = wsb._format_tavily_results("", results)
    assert "(10 из 5)" in out
    assert "t4" in out
    assert "t5" not in out


# ---------- search_with_ai_evaluation ----------


@pytest.mark.asyncio
async def test_search_with_ai_evaluation_free_engines(monkeypatch):
    calls = []

    async def fake_free(query, n):
        calls.append((query, n))
        return [{"text": "рез", "url": "http://r"}]

    monkeypatch.setattr("services.web_search._search_all_engines", fake_free)

    text, sources, sid = await wsb.search_with_ai_evaluation("q")
    assert "рез" in text
    assert sources == [{"text": "рез", "url": "http://r"}]
    assert sid.startswith("ws_")


@pytest.mark.asyncio
async def test_search_with_ai_evaluation_free_empty_tavily_ok(monkeypatch):
    async def fake_free(query, n):
        return []

    async def fake_tavily(query, key, n):
        return {
            "answer": "ответ",
            "results": [{"title": "т", "snippet": "с", "url": "http://u"}],
            "search_id": "ws_abc123",
        }

    monkeypatch.setattr("services.web_search._search_all_engines", fake_free)
    monkeypatch.setattr("services.tavily_search.search_tavily", fake_tavily)

    text, sources, sid = await wsb.search_with_ai_evaluation("q", "KEY")
    assert "ответ" in text
    assert sources[0]["url"] == "http://u"
    assert sid == "ws_abc123"


@pytest.mark.asyncio
async def test_search_with_ai_evaluation_tavily_error_result(monkeypatch):
    async def fake_free(query, n):
        return []

    async def fake_tavily(query, key, n):
        return {"error": "rate limit"}

    monkeypatch.setattr("services.web_search._search_all_engines", fake_free)
    monkeypatch.setattr("services.tavily_search.search_tavily", fake_tavily)

    text, sources, sid = await wsb.search_with_ai_evaluation("q", "KEY")
    assert text == "🤷 Ничего не найдено. Попробуйте другой запрос."
    assert sources == []
    assert sid == ""


@pytest.mark.asyncio
async def test_search_with_ai_evaluation_no_tavily_key(monkeypatch):
    async def fake_free(query, n):
        return []

    monkeypatch.setattr("services.web_search._search_all_engines", fake_free)

    text, sources, sid = await wsb.search_with_ai_evaluation("q", None)
    assert text == "🤷 Ничего не найдено. Попробуйте другой запрос."
    assert sources == []
    assert sid == ""


# ---------- cb_web_search ----------


@pytest.mark.asyncio
async def test_cb_web_search_uses_last_query(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _last_user_query[1] = "мой запрос"
    cb = FakeCb(4242, chat_id=1, data="web_search")

    async def fake_search(query, key):
        return "<b>итог</b>", [{"text": "s", "url": "u"}], "ws_1"

    monkeypatch.setattr(wsb, "search_with_ai_evaluation", fake_search)
    await wsb.cb_web_search(cb)
    assert cb.answered == [("🔍 Ищу в интернете...", None)]
    assert cb.message.answers[0][0] == "<b>итог</b>"
    assert cb.message.answers[0][1] == "HTML"


@pytest.mark.asyncio
async def test_cb_web_search_fallback_from_summary(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="web_search", html_text="Саммари:</b>\nтема из саммари\n\nдальше")

    async def fake_search(query, key):
        assert query == "тема из саммари"
        return "ок", [], ""

    monkeypatch.setattr(wsb, "search_with_ai_evaluation", fake_search)
    await wsb.cb_web_search(cb)
    assert cb.answered[0][0] == "🔍 Ищу в интернете..."


@pytest.mark.asyncio
async def test_cb_web_search_fallback_from_last_message(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="web_search", html_text="Последние сообщения:\n👤 один\n👤 два")

    async def fake_search(query, key):
        assert query == "два"
        return "ок", [], ""

    monkeypatch.setattr(wsb, "search_with_ai_evaluation", fake_search)
    await wsb.cb_web_search(cb)
    assert cb.answered[0][0] == "🔍 Ищу в интернете..."


@pytest.mark.asyncio
async def test_cb_web_search_fallback_from_lines(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="web_search", html_text="короткая\nвот эта длинная строка с текстом")

    async def fake_search(query, key):
        assert query == "вот эта длинная строка с текстом"
        return "ок", [], ""

    monkeypatch.setattr(wsb, "search_with_ai_evaluation", fake_search)
    await wsb.cb_web_search(cb)
    assert cb.answered[0][0] == "🔍 Ищу в интернете..."


@pytest.mark.asyncio
async def test_cb_web_search_no_query(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="web_search", html_text="")
    await wsb.cb_web_search(cb)
    assert cb.answered == [("Нет запроса для поиска", True)]


@pytest.mark.asyncio
async def test_cb_web_search_exception(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _last_user_query[1] = "q"
    cb = FakeCb(4242, chat_id=1, data="web_search")

    async def fake_search(query, key):
        raise RuntimeError("search down")

    monkeypatch.setattr(wsb, "search_with_ai_evaluation", fake_search)
    await wsb.cb_web_search(cb)
    assert cb.message.answers[0][0] == "❌ Ошибка поиска: search down"


@pytest.mark.asyncio
async def test_cb_web_search_no_message(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="web_search")
    cb.message = None
    await wsb.cb_web_search(cb)
    assert cb.answered == [("Ошибка: сообщение не найдено", True)]


@pytest.mark.asyncio
async def test_cb_web_search_long_text_chunked(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _last_user_query[1] = "q"
    cb = FakeCb(4242, chat_id=1, data="web_search")
    long_text = "слово " * 2000  # > 4000 символов

    async def fake_search(query, key):
        return long_text, [], ""

    monkeypatch.setattr(wsb, "search_with_ai_evaluation", fake_search)
    await wsb.cb_web_search(cb)
    assert len(cb.message.answers) == 3
    assert all(len(a[0]) <= 4000 for a in cb.message.answers)


# ---------- cb_ws_sources ----------


@pytest.mark.asyncio
async def test_cb_ws_sources_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="ws_sources:ws_1")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: {"query": "q", "sources": [{"title": "Заголок", "text": "текст", "url": "http://u"}]})
    await wsb.cb_ws_sources(cb)
    assert "Источники для" in cb.message.answers[0][0]
    assert "Заголок" in cb.message.answers[0][0]
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_ws_sources_no_search_id(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="ws_sources:")
    await wsb.cb_ws_sources(cb)
    assert cb.answered == [("Нет данных для отображения", True)]


@pytest.mark.asyncio
async def test_cb_ws_sources_missing_data(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="ws_sources:ws_ghost")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: None)
    await wsb.cb_ws_sources(cb)
    assert cb.answered == [("Результаты не найдены или устарели", True)]


@pytest.mark.asyncio
async def test_cb_ws_sources_empty_sources(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="ws_sources:ws_1")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: {"query": "q", "sources": []})
    await wsb.cb_ws_sources(cb)
    assert cb.answered == [("Источников нет", True)]


@pytest.mark.asyncio
async def test_cb_ws_sources_no_data_attr(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="ws_sources:ws_1")
    cb.data = None
    await wsb.cb_ws_sources(cb)
    assert cb.answered == []


@pytest.mark.asyncio
async def test_cb_ws_sources_clean_text(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="ws_sources:ws_1")
    monkeypatch.setattr(
        wsb, "load_web_search",
        lambda sid: {"query": "q", "sources": [{"title": "  титул..  ", "text": "текст...текст"}]},
    )
    await wsb.cb_ws_sources(cb)
    body = cb.message.answers[0][0]
    assert "титул" in body
    assert ".." not in body.replace("...", "")


# ---------- cb_ws_save ----------


@pytest.mark.asyncio
async def test_cb_ws_save_from_cache(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="ws_save:ws_1")
    monkeypatch.setattr(
        wsb, "load_web_search",
        lambda sid: {"query": "q", "ai_summary": "саммари", "sources": [{"title": "т", "text": "с", "url": "http://u"}]},
    )
    await wsb.cb_ws_save(cb)
    files = os.listdir(d)
    assert len(files) == 1
    with open(os.path.join(d, files[0]), encoding="utf-8") as f:
        body = f.read()
    assert "# Веб-поиск: q" in body
    assert "## ИИ-саммари" in body
    assert cb.message.edited
    assert cb.answered == [("✅ Сохранено", False)]


@pytest.mark.asyncio
async def test_cb_ws_save_fallback_search(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(wsb, "TAVILY_API_KEY", "KEY")
    _last_user_query[1] = "новый запрос"
    cb = FakeCb(4242, chat_id=1, data="ws_save:")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: None)

    async def fake_fallback(query, key, n):
        return "текст", [{"text": "с", "url": "http://u", "title": "т"}], "ws_new1234"

    monkeypatch.setattr("services.tavily_search.search_with_fallback", fake_fallback)
    await wsb.cb_ws_save(cb)
    files = os.listdir(d)
    assert len(files) == 1
    assert cb.answered == [("✅ Сохранено", False)]


@pytest.mark.asyncio
async def test_cb_ws_save_no_data_anywhere(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="ws_save:")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: None)
    await wsb.cb_ws_save(cb)
    assert os.listdir(d) == []
    assert cb.answered == [("❌ Нет результатов для сохранения. Попробуйте поиск заново.", True)]


@pytest.mark.asyncio
async def test_cb_ws_save_data_without_summary_and_sources(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="ws_save:ws_1")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: {"query": "q"})
    await wsb.cb_ws_save(cb)
    assert cb.answered == [("❌ Нет текста для сохранения.", True)]


@pytest.mark.asyncio
async def test_cb_ws_save_no_query_no_summary(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="ws_save:ws_1")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: {"sources": [{"text": "x"}]})
    await wsb.cb_ws_save(cb)
    assert cb.answered == [("❌ Нет текста для сохранения.", True)]


@pytest.mark.asyncio
async def test_cb_ws_save_source_without_url(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="ws_save:ws_1")
    monkeypatch.setattr(
        wsb, "load_web_search",
        lambda sid: {"query": "q", "ai_summary": "с", "sources": [{"title": "т", "text": "х"}]},
    )
    await wsb.cb_ws_save(cb)
    files = os.listdir(d)
    assert len(files) == 1
    assert cb.answered == [("✅ Сохранено", False)]


@pytest.mark.asyncio
async def test_cb_ws_save_no_data_attr(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="ws_save:")
    cb.data = None
    await wsb.cb_ws_save(cb)
    assert cb.answered == []


@pytest.mark.asyncio
async def test_format_tavily_results_url_without_snippet():
    out = wsb._format_tavily_results("", [{"title": "т", "url": "http://u"}])
    assert "🔗 Источник" in out
    assert "snippet" not in out


@pytest.mark.asyncio
async def test_format_tavily_results_no_url_no_snippet():
    out = wsb._format_tavily_results("", [{"title": "т"}])
    assert "🔗 Источник" not in out
    assert "т" in out


@pytest.mark.asyncio
async def test_cb_web_search_summary_header_without_newline(monkeypatch, tmp_path):
    """'Саммари:' есть, но без переноса строки → regex не срабатывает (109->116)."""
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="web_search", html_text="Саммари:</b> без новой строки")

    searched = []

    async def fake_search(query, key):
        searched.append(query)
        return "ок", [], ""

    monkeypatch.setattr(wsb, "search_with_ai_evaluation", fake_search)
    await wsb.cb_web_search(cb)
    assert searched and searched[0] == "Саммари:</b> без новой строки"


@pytest.mark.asyncio
async def test_cb_web_search_last_messages_without_users(monkeypatch, tmp_path):
    """'Последние сообщения:' есть, но нет 👤 → не парсится (113->116)."""
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="web_search", html_text="Последние сообщения:\nнет пользователей")

    searched = []

    async def fake_search(query, key):
        searched.append(query)
        return "ок", [], ""

    monkeypatch.setattr(wsb, "search_with_ai_evaluation", fake_search)
    await wsb.cb_web_search(cb)
    assert searched and searched[0] == "нет пользователей"


@pytest.mark.asyncio
async def test_clean_text_empty_and_dirty(monkeypatch, tmp_path):
    """clean_text: пусто → '', спецсимволы и пробелы чистятся (172)."""
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="ws_sources:ws_1")
    monkeypatch.setattr(
        wsb, "load_web_search",
        lambda sid: {"query": "q", "sources": [{"title": "т", "text": ""}]},
    )
    await wsb.cb_ws_sources(cb)
    body = cb.message.answers[0][0]
    assert "т" in body


@pytest.mark.asyncio
async def test_cb_ws_sources_url_without_snippet(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="ws_sources:ws_1")
    monkeypatch.setattr(
        wsb, "load_web_search",
        lambda sid: {"query": "q", "sources": [{"title": "т", "url": "http://u", "text": ""}]},
    )
    await wsb.cb_ws_sources(cb)
    assert "Открыть источник" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cb_ws_sources_no_url_no_snippet(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="ws_sources:ws_1")
    monkeypatch.setattr(
        wsb, "load_web_search",
        lambda sid: {"query": "q", "sources": [{"title": "т", "text": ""}]},
    )
    await wsb.cb_ws_sources(cb)
    assert "Открыть источник" not in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cb_ws_save_fallback_no_query(monkeypatch, tmp_path):
    """Fallback поиск, но _last_user_query пуст → нет данных (221->231)."""
    d = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(wsb, "TAVILY_API_KEY", "KEY")
    cb = FakeCb(4242, chat_id=1, data="ws_save:")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: None)
    await wsb.cb_ws_save(cb)
    assert os.listdir(d) == []
    assert cb.answered[0][0].startswith("❌ Нет результатов")


@pytest.mark.asyncio
async def test_cb_ws_save_fallback_empty_sources(monkeypatch, tmp_path):
    """Fallback поиск без sources/text → не сохраняем (228->231)."""
    d = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(wsb, "TAVILY_API_KEY", "KEY")
    _last_user_query[1] = "q"
    cb = FakeCb(4242, chat_id=1, data="ws_save:")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: None)

    async def fake_fallback(query, key, n):
        return "", [], "ws_no"

    monkeypatch.setattr("services.tavily_search.search_with_fallback", fake_fallback)
    await wsb.cb_ws_save(cb)
    assert os.listdir(d) == []
    assert cb.answered == [("❌ Нет текста для сохранения.", True)]
    assert wsb.load_web_search is not None


@pytest.mark.asyncio
async def test_cb_ws_save_no_ai_summary_no_sources(monkeypatch, tmp_path):
    """data есть, но ни summary ни sources → 'Нет текста для сохранения' (238)."""
    d = _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="ws_save:ws_1")
    monkeypatch.setattr(wsb, "load_web_search", lambda sid: {"query": "q", "ai_summary": "", "sources": []})
    await wsb.cb_ws_save(cb)
    assert os.listdir(d) == []
    assert cb.answered == [("❌ Нет текста для сохранения.", True)]


@pytest.mark.asyncio
async def test_cb_ws_save_sources_only_no_summary(monkeypatch, tmp_path):
    """Без ai_summary → контент без секции ИИ-саммари (251->253)."""
    d = _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, chat_id=1, data="ws_save:ws_1")
    monkeypatch.setattr(
        wsb, "load_web_search",
        lambda sid: {"query": "q", "sources": [{"title": "т", "text": "х", "url": "http://u"}]},
    )
    await wsb.cb_ws_save(cb)
    files = os.listdir(d)
    assert len(files) == 1
    with open(os.path.join(d, files[0]), encoding="utf-8") as f:
        body = f.read()
    assert "# Веб-поиск: q" in body
    assert "## ИИ-саммари" not in body
    assert cb.answered == [("✅ Сохранено", False)]
