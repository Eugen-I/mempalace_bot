"""Тесты Шага 4 ТЗ: языковая директива «Отвечай на русском языке» в промптах Дворца.

Баг №1: _answer_room_ai (navigation.py) формировал system-промпты без
указания языка — модель могла ответить на китайском после русского текста.
"""
import json

import pytest

from handlers.palace import navigation
from tests.test_action_bar import FakeCallback, FakeMessage, TEST_UID

LANG_DIRECTIVE = "Отвечай на русском языке"


@pytest.fixture(autouse=True)
def _allow_test_user(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {TEST_UID})
    yield


class FakeMcp:
    """MCP с записями в комнате — чтобы _answer_room_ai дошла до вызова ИИ."""

    async def call_tool(self, name, args=None):
        if name == "mempalace_list_drawers":
            return json.dumps({
                "drawers": [
                    {"closet_name": "Запись 1", "drawer_id": "d1"},
                    {"closet_name": "Запись 2", "drawer_id": "d2"},
                ],
                "count": 2,
            })
        if name == "mempalace_get_drawer":
            return json.dumps({"content": "Содержимое записи."})
        return "{}"


class FakeMcpNoDrawers:
    async def call_tool(self, name, args=None):
        return '{"drawers": [], "count": 0}'


@pytest.fixture
def captured_calls(monkeypatch):
    """Перехватываем все вызовы ИИ и возвращаем список [(system, user)]."""
    calls = []

    def fake_call(engine, model, messages, **kwargs):
        calls.append(messages)
        return "Ответ на русском."

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_call)
    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMcp())
    return calls


async def _run_answer_room_ai(monkeypatch):
    """Полный прогон _answer_room_ai с фейковыми сообщениями."""
    calls = []

    def fake_call(engine, model, messages, **kwargs):
        calls.append(messages)
        return "Ответ на русском."

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_call)
    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMcp())

    async def fake_finalize(uid, edit_func, text, **kwargs):
        return None

    from handlers.palace import action_bar

    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    msg = FakeMessage()
    await navigation._answer_room_ai(msg, TEST_UID, "крыло", "комната", "Вопрос?")
    return calls


@pytest.mark.asyncio
async def test_all_system_prompts_contain_lang_directive(monkeypatch):
    """Счастливый путь: каждый system-промпт в _answer_room_ai требует русский."""
    calls = await _run_answer_room_ai(monkeypatch)
    assert len(calls) == 2, "ожидали step1 (саммари) + step2 (ответ)"
    for messages in calls:
        system = next(m for m in messages if m["role"] == "system")
        assert LANG_DIRECTIVE in system["content"], system["content"]


@pytest.mark.asyncio
async def test_with_web_prompt_contains_lang_directive(monkeypatch):
    """Негатив-регрессия: ветка with_web тоже требует русский язык."""
    ctx = {"_room_summary": "Краткое саммари."}
    monkeypatch.setattr(navigation, "_user_context", {TEST_UID: ctx})

    calls = []

    def fake_call(engine, model, messages, **kwargs):
        calls.append(messages)
        return "Ответ."

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_call)
    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMcp())

    async def fake_finalize(uid, edit_func, text, **kwargs):
        return None

    from handlers.palace import action_bar

    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    class FakeSearch:
        def __init__(self):
            self.called = False

        async def __call__(self, q):
            self.called = True
            return "Результаты поиска."

    fake_search = FakeSearch()
    monkeypatch.setattr("services.web_search.search_web", fake_search)

    msg = FakeMessage()
    await navigation._answer_room_ai(msg, TEST_UID, "крыло", "комната", "Вопрос?", with_web=True)

    assert fake_search.called
    assert len(calls) == 1
    system = next(m for m in calls[0] if m["role"] == "system")
    assert LANG_DIRECTIVE in system["content"]


@pytest.mark.asyncio
async def test_tunnels_ai_prompt_contains_lang_directive(monkeypatch):
    """Промпт анализа туннелей (cb_tunnels_ai) требует русский."""
    from handlers.palace import navigation as nav

    class FakeMcpTunnels:
        async def call_tool(self, name, args=None):
            return json.dumps([
                {"src_wing": "а", "src_room": "б", "dst_wing": "в", "dst_room": "г"},
            ])

    captured = {}

    def fake_call(engine, model, messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "Анализ."

    monkeypatch.setattr(nav, "get_mcp", lambda: FakeMcpTunnels())
    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_call)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("gemini", "g"))

    cb = FakeCallback("p_tun_ai")
    await nav.cb_tunnels_ai(cb)
    assert LANG_DIRECTIVE in captured["prompt"]


@pytest.mark.asyncio
async def test_article_prompt_contains_lang_directive(monkeypatch):
    """Промпт «🤖 Статья» тоже требует русский."""
    from handlers.palace import navigation as nav

    captured = {}

    def fake_call(engine, model, messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "Статья."

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_call)

    async def fake_finalize(uid, edit_func, text, **kwargs):
        return None

    from handlers.palace import action_bar

    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)
    monkeypatch.setattr(nav, "get_mcp", lambda: FakeMcp())
    monkeypatch.setattr(nav, "_room_session", {TEST_UID: {"wing": " крыло", "room": "комната"}})
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("gemini", "g"))
    cb = FakeCallback("p_rd_art")
    await nav.cb_cross_ai_article(cb)
    assert LANG_DIRECTIVE in captured["prompt"]


@pytest.mark.asyncio
async def test_empty_room_no_ai_call(monkeypatch):
    """Граничное: комната без записей — ИИ не вызывается, есть сообщение."""
    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMcpNoDrawers())
    msg = FakeMessage()
    await navigation._answer_room_ai(msg, TEST_UID, "крыло", "пусто", "Вопрос?")
    assert "нет записей" in msg.edited[-1]
