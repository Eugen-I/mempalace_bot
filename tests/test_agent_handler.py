"""Unit-тесты для handlers.agent — агентный режим (команда, кнопки, скоуп).

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
run_agent замокан на всех тестах; проверяется маршрутизация и форматирование.
"""

from types import SimpleNamespace

import pytest

from handlers import agent as h
from services import agent_engine as ae


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeStatus:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


class FakeMessage:
    def __init__(self, uid=4242, text=""):
        self.from_user = FakeUser(uid)
        self.chat = SimpleNamespace(id=1)
        self.text = text
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        status = FakeStatus()
        self.last_status = status
        return status

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


class FakeCb:
    def __init__(self, uid=4242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answers = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


@pytest.fixture(autouse=True)
def allow_user(monkeypatch):
    """Разрешает uid 4242 (паттерн как в test_settings_handler)."""
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})


@pytest.fixture(autouse=True)
def mock_run_agent(monkeypatch):
    """Подменяет run_agent на запись аргументов + предсказуемый результат."""

    async def fake_run_agent(
        system_prompt, user_prompt, engine=None, model=None,
        include_write=False, allowed_categories=None, status_cb=None,
        max_iterations=5, tool_timeout=60.0,
        conversation_history=None,
    ):
        fake_run_agent.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "include_write": include_write,
            "conversation_history": conversation_history,
        })
        return fake_run_agent.result

    fake_run_agent.calls = []
    fake_run_agent.result = ae.AgentResult(final_answer="Итоговый ответ")
    monkeypatch.setattr(ae, "run_agent", fake_run_agent)
    return fake_run_agent


def _answer_ok(text="Готово"):
    return ae.AgentResult(final_answer=text)


# ─── /agent <вопрос> ───


async def test_cmd_agent_no_question_shows_usage():
    msg = FakeMessage(4242, text="/agent")
    await h.cmd_agent(msg)
    assert "Агентный режим" in msg.answers[0]
    assert msg.answers[0].startswith("🤖")


async def test_cmd_agent_runs_with_question(mock_run_agent):
    mock_run_agent.result = _answer_ok("Итоговый ответ")
    msg = FakeMessage(4242, text="/agent что я думал о шопенгауэре")
    await h.cmd_agent(msg)
    assert mock_run_agent.calls
    call = mock_run_agent.calls[0]
    assert "шопенгауэре" in call["user_prompt"]
    assert call["include_write"] is False
    assert "Итоговый ответ" in msg.last_status.edits[-1]


async def test_cmd_agent_question_with_leading_spaces(mock_run_agent):
    msg = FakeMessage(4242, text="/agent    вопрос с пробелами")
    await h.cmd_agent(msg)
    assert mock_run_agent.calls[0]["user_prompt"] == "вопрос с пробелами"


async def test_cmd_agent_error_result(mock_run_agent):
    mock_run_agent.result = ae.AgentResult(
        final_answer="", finished_reason="error", error="Модель вернула пустой ответ.",
    )
    msg = FakeMessage(4242, text="/agent вопрос")
    await h.cmd_agent(msg)
    assert "Модель вернула пустой ответ" in msg.last_status.edits[-1]


async def test_cmd_agent_max_iterations(mock_run_agent):
    mock_run_agent.result = ae.AgentResult(
        final_answer="", finished_reason="max_iterations",
        error="Достигнут лимит итераций агента (5).",
    )
    msg = FakeMessage(4242, text="/agent вопрос")
    await h.cmd_agent(msg)
    assert "лимит итераций" in msg.last_status.edits[-1]


async def test_cmd_agent_engine_error(monkeypatch, mock_run_agent):
    async def boom(system_prompt, user_prompt, **kwargs):
        raise ae.AgentEngineError("Агентный режим работает только с Ollama")

    monkeypatch.setattr(ae, "run_agent", boom)
    msg = FakeMessage(4242, text="/agent вопрос")
    await h.cmd_agent(msg)
    assert "только с Ollama" in msg.last_status.edits[-1]


async def test_cmd_agent_unexpected_exception(mock_run_agent, monkeypatch):
    async def boom(system_prompt, user_prompt, **kwargs):
        raise RuntimeError("поломка")

    monkeypatch.setattr(ae, "run_agent", boom)
    msg = FakeMessage(4242, text="/agent вопрос")
    await h.cmd_agent(msg)
    assert "поломка" in msg.last_status.edits[-1]


# ─── ab_agent:sid (action bar) ───


async def test_cb_ab_agent_expired_session():
    cb = FakeCb(4242, data="ab_agent:no_such_sid")
    await h.cb_ab_agent(cb)
    assert cb.answers[-1] == ("Сессия истекла. Откройте заново.", True)


async def test_cb_ab_agent_scoped_prompt(mock_run_agent, monkeypatch):
    from handlers.palace.action_bar import Answer, answer_store

    sid = "test_sid"
    answer_store[sid] = Answer(
        sid=sid, text="Текст ответа", ctx={"wing": "Философия", "room": "Шопенгауэр"},
    )
    try:
        cb = FakeCb(4242, data=f"ab_agent:{sid}")
        await h.cb_ab_agent(cb)
        assert mock_run_agent.calls
        system = mock_run_agent.calls[0]["system_prompt"]
        assert "Философия" in system
        assert "Шопенгауэр" in system
        assert "Текст ответа" in mock_run_agent.calls[0]["user_prompt"]
    finally:
        answer_store.pop(sid, None)


async def test_cb_ab_agent_no_scope_uses_base_prompt(mock_run_agent):
    from handlers.palace.action_bar import Answer, answer_store

    sid = "test_sid2"
    answer_store[sid] = Answer(sid=sid, text="Просто ответ", ctx={})
    try:
        cb = FakeCb(4242, data=f"ab_agent:{sid}")
        await h.cb_ab_agent(cb)
        system = mock_run_agent.calls[0]["system_prompt"]
        assert "Комната" not in system
    finally:
        answer_store.pop(sid, None)


# ─── p_agent_room:{key} (кнопка комнаты) ───


async def test_build_room_agent_callback_roundtrip():
    key_cb = h.build_room_agent_callback("Крыло А", "Комната Б")
    assert key_cb.startswith("p_agent_room:")
    key = key_cb[len("p_agent_room:"):]
    assert h._agent_room_map.get(key) == ("Крыло А", "Комната Б")


async def test_cb_room_agent_sets_pending_input():
    from handlers.palace.shared import _pending_mcp_input

    key_cb = h.build_room_agent_callback("Крыло", "Комната")
    cb = FakeCb(4242, data=key_cb)
    await h.cb_room_agent(cb)
    key = key_cb[len("p_agent_room:"):]
    assert _pending_mcp_input.pop(4242, None) == f"agent_room:{key}"
    assert "Комната" in cb.message.answers[0]


async def test_cb_room_agent_expired_key():
    cb = FakeCb(4242, data="p_agent_room:deadbeef")
    await h.cb_room_agent(cb)
    assert "истекла" in cb.message.edits[0]


async def test_run_room_agent_scoped(mock_run_agent):
    key_cb = h.build_room_agent_callback("Крыло", "Комната")
    key = key_cb[len("p_agent_room:"):]
    status = FakeStatus()
    await h.run_room_agent(4242, status, key, "Какие там идеи?")
    system = mock_run_agent.calls[0]["system_prompt"]
    assert "Крыло" in system
    assert "Комната" in system
    assert "Какие там идеи?" in mock_run_agent.calls[0]["user_prompt"]


async def test_run_room_agent_expired_key(mock_run_agent):
    status = FakeStatus()
    await h.run_room_agent(4242, status, "deadbeef", "вопрос")
    assert mock_run_agent.calls == []
    assert "истекла" in status.edits[0]


# ─── Справка ───


async def test_cb_agent_explain():
    cb = FakeCb(4242, data="agent_explain")
    await h.cb_agent_explain(cb)
    assert "Агентный режим" in cb.message.edits[0]
    assert "/agent" in cb.message.edits[0]


# ─── Защитные ветки ───


async def test_status_edit_edit_failure_logs_warning(caplog):
    class BoomStatus:
        async def edit_text(self, text, parse_mode=None, reply_markup=None):
            raise RuntimeError("429 Too Many Requests")

    with caplog.at_level("WARNING", logger="handlers.agent"):
        await h._status_edit(BoomStatus(), "текст")
    assert any("[AGENT] status edit failed" in r.message for r in caplog.records)


async def test_run_agent_reply_status_cb_uses_status_edit(monkeypatch):
    status = FakeStatus()

    async def fake_run_agent(
        system_prompt, user_prompt, engine=None, model=None,
        include_write=False, allowed_categories=None, status_cb=None,
        max_iterations=5, tool_timeout=60.0,
        conversation_history=None,
    ):
        await status_cb("🔧 Шаг 1/5: test…")
        return ae.AgentResult(final_answer="Готово")

    monkeypatch.setattr(ae, "run_agent", fake_run_agent)
    status = FakeStatus()
    result = await h._run_agent_reply(4242, status, "sys", "вопрос")
    assert result.ok is True
    assert result.final_answer == "Готово"
    assert status.edits
    assert any("Шаг 1/5" in e for e in status.edits)


async def test_run_agent_reply_engine_error_returns_safe_result(monkeypatch):
    async def boom(system_prompt, user_prompt, **kwargs):
        raise ae.AgentEngineError("Агентный режим работает только с Ollama")

    monkeypatch.setattr(ae, "run_agent", boom)
    status = FakeStatus()

    result = await h._run_agent_reply(4242, status, "sys", "вопрос")

    assert isinstance(result, ae.AgentResult)
    assert result.ok is False
    assert result.final_answer == ""
    assert "Ollama" in (result.error or "")
    assert "Ollama" in status.edits[-1]


async def test_run_agent_reply_unexpected_error_returns_safe_result(monkeypatch):
    async def boom(system_prompt, user_prompt, **kwargs):
        raise RuntimeError("поломка")

    monkeypatch.setattr(ae, "run_agent", boom)
    status = FakeStatus()

    result = await h._run_agent_reply(4242, status, "sys", "вопрос")

    assert isinstance(result, ae.AgentResult)
    assert result.ok is False
    assert result.final_answer == ""
    assert result.error == "Ошибка агента: поломка"
    assert "поломка" in status.edits[-1]


async def test_run_agent_reply_error_result_returns_safe_result(monkeypatch):
    async def fake_run_agent(system_prompt, user_prompt, **kwargs):
        return ae.AgentResult(
            final_answer="", finished_reason="error", error="Модель вернула пустой ответ.",
        )

    monkeypatch.setattr(ae, "run_agent", fake_run_agent)
    status = FakeStatus()

    result = await h._run_agent_reply(4242, status, "sys", "вопрос")

    assert result.ok is False
    assert result.final_answer == ""
    assert result.error == "Модель вернула пустой ответ."
    assert "Модель вернула пустой ответ" in status.edits[-1]


async def test_cb_ab_agent_engine_error_does_not_crash(monkeypatch):
    from handlers.palace.action_bar import Answer, answer_store

    class FakeCtxStore:
        def __init__(self):
            self.appended = []

        def create_button_session(self, answer_sid):
            return "button-sid"

        def bind_button_session_to_uid(self, uid, session_id):
            return None

        def append_button_context(self, session_id, role, content):
            self.appended.append((role, content))

    store = FakeCtxStore()
    monkeypatch.setattr(h, "get_agent_context_store", lambda: store)

    async def boom(system_prompt, user_prompt, **kwargs):
        raise RuntimeError("поломка агента")

    monkeypatch.setattr(ae, "run_agent", boom)

    sid = "test_agent_error"
    answer_store[sid] = Answer(sid=sid, text="Ответ", ctx={})
    try:
        cb = FakeCb(4242, data=f"ab_agent:{sid}")
        await h.cb_ab_agent(cb)
    finally:
        answer_store.pop(sid, None)

    assert store.appended == []
    assert "поломка агента" in cb.message.last_status.edits[-1]


async def test_cb_ab_agent_no_data_returns():
    cb = FakeCb(4242, data=None)
    await h.cb_ab_agent(cb)
    assert cb.answers == [(None, None)]


async def test_cb_room_agent_no_data_returns():
    cb = FakeCb(4242, data=None)
    await h.cb_room_agent(cb)
    assert cb.answers == [(None, None)]


# ─── Промпт агента: обязательное цитирование заметок ───


def test_agent_system_prompt_requires_citations():
    from handlers.agent import AGENT_SYSTEM_PROMPT
    assert "цитируй" in AGENT_SYSTEM_PROMPT
    assert "название заметки" in AGENT_SYSTEM_PROMPT
