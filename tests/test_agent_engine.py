"""Unit-тесты для services.agent_engine — агентный цикл tool-calling.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
Все вызовы модели замоканы фейковым OpenAI-клиентом со скриптом ответов.
"""

import asyncio
from dataclasses import dataclass, field

import pytest

from services import agent_engine as ae
from services import agent_tools as at

# ─── Фейковый OpenAI-клиент ───


class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class FakeChoice:
    def __init__(self, message, finish_reason="stop"):
        self.message = message
        self.finish_reason = finish_reason


class FakeResponse:
    def __init__(self, message, finish_reason="stop"):
        self.choices = [FakeChoice(message, finish_reason)]


@dataclass
class ModelHarness:
    """Скрипт ответов модели + перехваченные kwargs вызовов."""

    script: list = field(default_factory=list)
    kwargs: list = field(default_factory=list)


class FakeCompletions:
    def __init__(self, harness: ModelHarness):
        self.harness = harness

    def create(self, **kwargs):
        self.harness.kwargs.append(kwargs)
        if self.harness.script:
            return self.harness.script.pop(0)
        raise AssertionError("No scripted responses left")


class FakeChat:
    def __init__(self, harness: ModelHarness):
        self.completions = FakeCompletions(harness)


class FakeClient:
    def __init__(self, harness: ModelHarness):
        self.chat = FakeChat(harness)


def _tool_call(name, arguments="{}", call_id="call_1"):
    return FakeResponse(FakeMessage(None, [FakeToolCall(call_id, name, arguments)]))


def _content(text):
    return FakeResponse(FakeMessage(text))


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    """Подменяет OpenAI-клиент и ensure_ollama_running на всём модуле тестов."""
    harness = ModelHarness()

    def factory(base_url, api_key):
        return FakeClient(harness)

    monkeypatch.setattr(ae, "OpenAI", factory)
    monkeypatch.setattr(ae, "ensure_ollama_running", lambda model: None)
    yield harness


@pytest.fixture
def cleanup():
    """Удаляет тестовые инструменты после каждого теста."""
    yield
    for name in ("test_tool", "test_write", "test_fail", "test_slow"):
        at.unregister_tool(name)


def _register_test_tool(name="test_tool", is_write=False, handler=None):
    if handler is None:
        def handler(args):
            return f"got:{args['value']}"

    at.unregister_tool(name)  # идемпотентность между тестами
    at.register_tool(
        name,
        "Тестовый инструмент",
        schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        category=at.CAT_SYSTEM,
        is_write=is_write,
    )(handler)


# ─── Happy path ───


async def test_happy_path_two_steps(fake_model):
    _register_test_tool()
    fake_model.script.append(_tool_call("test_tool", '{"value": "abc"}'))
    fake_model.script.append(_content("Готово"))

    result = await ae.run_agent(
        system_prompt="Ты агент", user_prompt="Сделай",
        engine="qwen", model="qwen2.5:7b",
    )
    assert result.finished_reason == "answer"
    assert result.final_answer == "Готово"
    assert result.iterations == 2
    assert len(result.steps) == 1
    assert result.steps[0].calls[0]["name"] == "test_tool"
    assert result.steps[0].results[0]["ok"] is True
    assert result.steps[0].results[0]["output"] == "got:abc"


async def test_single_shot_no_tools(fake_model):
    fake_model.script.append(_content("Ответ без инструментов"))
    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "answer"
    assert result.final_answer == "Ответ без инструментов"
    assert result.iterations == 1
    assert result.steps == []


async def test_agent_now_tool_executed(fake_model):
    fake_model.script.append(_tool_call("agent_now", "{}"))
    fake_model.script.append(_content("Итог"))
    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "answer"
    out = result.steps[0].results[0]["output"]
    assert "20" in out


# ─── Негативные сценарии ───


async def test_unknown_tool(fake_model, cleanup):
    _register_test_tool()
    fake_model.script.append(_tool_call("no_such_tool", "{}"))
    fake_model.script.append(_content("Понял, не буду"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "answer"
    assert result.steps[0].results[0]["ok"] is False
    assert "не существует" in result.steps[0].results[0]["output"]


async def test_write_tool_excluded_by_default(fake_model, cleanup):
    _register_test_tool(name="test_write", is_write=True)
    fake_model.script.append(_tool_call("test_write", '{"value": "x"}'))
    fake_model.script.append(_content("Ок"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.steps[0].results[0]["ok"] is False
    assert "не существует" in result.steps[0].results[0]["output"]


async def test_include_write_without_confirm_write_still_excluded(fake_model, cleanup):
    """Без confirm_write запись невозможна даже при include_write=True."""
    _register_test_tool(name="test_write", is_write=True)
    fake_model.script.append(_tool_call("test_write", '{"value": "x"}'))
    fake_model.script.append(_content("Ок"))

    result = await ae.run_agent(
        "sys", "user", engine="qwen", model="m", include_write=True,
    )
    assert result.steps[0].results[0]["ok"] is False
    assert "не существует" in result.steps[0].results[0]["output"]


async def test_confirm_write_approved_executes(fake_model, cleanup):
    _register_test_tool(name="test_write", is_write=True)
    fake_model.script.append(_tool_call("test_write", '{"value": "x"}'))
    fake_model.script.append(_content("Ок"))
    confirmations = []

    async def approve(name, arguments):
        confirmations.append((name, arguments))
        return True

    result = await ae.run_agent(
        "sys", "user", engine="qwen", model="m",
        include_write=True, confirm_write=approve,
    )
    assert result.steps[0].results[0]["ok"] is True
    assert result.steps[0].results[0]["output"] == "got:x"
    assert confirmations == [("test_write", {"value": "x"})]


async def test_confirm_write_rejected_skips_execution(fake_model, cleanup):
    _register_test_tool(name="test_write", is_write=True)
    fake_model.script.append(_tool_call("test_write", '{"value": "x"}'))
    fake_model.script.append(_content("Понял, отменяю"))

    async def reject(name, arguments):
        return False

    result = await ae.run_agent(
        "sys", "user", engine="qwen", model="m",
        include_write=True, confirm_write=reject,
    )
    assert result.steps[0].results[0]["ok"] is False
    assert "отклонил" in result.steps[0].results[0]["output"]
    assert result.final_answer == "Понял, отменяю"


async def test_confirm_write_not_called_for_read_tool(fake_model, cleanup):
    _register_test_tool()
    fake_model.script.append(_tool_call("test_tool", '{"value": "abc"}'))
    fake_model.script.append(_content("Готово"))
    confirmations = []

    async def approve(name, arguments):
        confirmations.append(name)
        return True

    result = await ae.run_agent(
        "sys", "user", engine="qwen", model="m",
        include_write=True, confirm_write=approve,
    )
    assert result.steps[0].results[0]["ok"] is True
    assert confirmations == []


async def test_tool_validation_error(fake_model, cleanup):
    _register_test_tool()
    fake_model.script.append(_tool_call("test_tool", "{}"))  # нет required value
    fake_model.script.append(_content("Исправил"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.steps[0].results[0]["ok"] is False
    assert "Ошибка аргументов" in result.steps[0].results[0]["output"]
    assert result.final_answer == "Исправил"


async def test_tool_bad_json_arguments(fake_model, cleanup):
    _register_test_tool()
    fake_model.script.append(_tool_call("test_tool", "not-json{{"))
    fake_model.script.append(_content("Ок"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.steps[0].results[0]["ok"] is False
    assert "Ошибка аргументов" in result.steps[0].results[0]["output"]


async def test_tool_raises_exception(fake_model, cleanup):
    def boom(args):
        raise ValueError("сломался")

    _register_test_tool(name="test_fail", handler=boom)
    fake_model.script.append(_tool_call("test_fail", '{"value": "x"}'))
    fake_model.script.append(_content("Всё починил"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.steps[0].results[0]["ok"] is False
    assert "Ошибка инструмента" in result.steps[0].results[0]["output"]
    assert result.final_answer == "Всё починил"


async def test_tool_timeout(fake_model, cleanup):
    async def slow(args):
        await asyncio.sleep(0.1)

    _register_test_tool(name="test_slow", handler=slow)
    fake_model.script.append(_tool_call("test_slow", '{"value": "x"}'))
    fake_model.script.append(_content("Готово"))

    result = await ae.run_agent(
        "sys", "user", engine="qwen", model="m", tool_timeout=0.01,
    )
    assert result.steps[0].results[0]["ok"] is False
    assert "таймаут" in result.steps[0].results[0]["output"]


async def test_max_iterations(fake_model):
    for _ in range(5):
        fake_model.script.append(_tool_call("agent_now", "{}"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "max_iterations"
    assert result.iterations == 5
    assert len(result.steps) == 5
    assert "лимит итераций" in result.error


async def test_max_iterations_bva_one(fake_model):
    fake_model.script.append(_tool_call("agent_now", "{}"))

    result = await ae.run_agent(
        "sys", "user", engine="qwen", model="m", max_iterations=1,
    )
    assert result.finished_reason == "max_iterations"
    assert len(result.steps) == 1


async def test_empty_answer_no_tools(fake_model):
    fake_model.script.append(FakeResponse(FakeMessage("")))
    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "error"
    assert "пустой ответ" in result.error


# ─── Ошибки модели / движка ───


async def test_ollama_unreachable_runtime_error(monkeypatch):
    def boom(model):
        raise RuntimeError("Ollama is not running")

    monkeypatch.setattr(ae, "ensure_ollama_running", boom)
    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "error"
    assert "Не удалось подключиться к Ollama" in result.error


async def test_ollama_apiconnection_error(monkeypatch):
    class APIConnectionError(Exception):
        pass

    def factory(base_url, api_key):
        class C:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        raise APIConnectionError("connection refused")

        return C()

    monkeypatch.setattr(ae, "OpenAI", factory)
    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "error"
    assert "Не удалось подключиться к Ollama" in result.error


async def test_generic_model_failure(monkeypatch):
    class Boom(Exception):
        pass

    def factory(base_url, api_key):
        class C:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        raise Boom("всё сломалось")

        return C()

    monkeypatch.setattr(ae, "OpenAI", factory)
    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "error"
    assert "Ошибка вызова модели" in result.error
    assert result.iterations == 0


async def test_unsupported_engine_raises():
    with pytest.raises(ae.AgentEngineError):
        await ae.run_agent("sys", "user", engine="gemini", model="gemini-flash")


# ─── Прочее ───


async def test_status_cb_receives_steps(fake_model):
    _register_test_tool()
    fake_model.script.append(_tool_call("test_tool", '{"value": "x"}'))
    fake_model.script.append(_content("Готово"))

    statuses = []

    async def cb(text):
        statuses.append(text)

    await ae.run_agent(
        "sys", "user", engine="qwen", model="m", status_cb=cb,
    )
    assert any("Шаг 1/5" in s for s in statuses)
    assert any("test_tool" in s for s in statuses)


async def test_engine_from_get_current_ai(monkeypatch, fake_model):
    monkeypatch.setattr(ae, "get_current_ai", lambda: ("qwen", "qwen2.5:7b"))
    fake_model.script.append(_content("Авто"))
    result = await ae.run_agent("sys", "user")
    assert result.final_answer == "Авто"


async def test_ollama_engine_alias_accepted(fake_model):
    fake_model.script.append(_content("Ок"))
    result = await ae.run_agent("sys", "user", engine="ollama", model="m")
    assert result.finished_reason == "answer"


async def test_tool_result_visible_to_next_call(fake_model):
    _register_test_tool()
    fake_model.script.append(_tool_call("test_tool", '{"value": "первый"}'))
    fake_model.script.append(_tool_call("test_tool", '{"value": "второй"}'))
    fake_model.script.append(_content("Итог"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.iterations == 3
    assert result.steps[1].results[0]["output"] == "got:второй"
    assert fake_model.script == []


async def test_assistant_and_tool_messages_protocol(fake_model):
    fake_model.script.append(_tool_call("agent_now", "{}", call_id="call_xyz"))
    fake_model.script.append(_content("Готово"))

    await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert len(fake_model.kwargs) == 2
    second = fake_model.kwargs[1]["messages"]
    assistant = second[-2]
    tool = second[-1]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["id"] == "call_xyz"
    assert assistant["tool_calls"][0]["function"]["name"] == "agent_now"
    assert tool["role"] == "tool"
    assert tool["tool_call_id"] == "call_xyz"
    assert "20" in tool["content"]


# ─── Вызов инструмента, написанный текстом (content вместо tool_calls) ───


async def test_text_embedded_tool_call_is_executed(fake_model, cleanup):
    """qwen иногда пишет «søker {"name": ..., "arguments": ...}» в content —
    такой вызов должен выполняться, а не показываться пользователю сырым."""
    _register_test_tool()
    fake_model.script.append(
        _content('søker {"name": "test_tool", "arguments": {"value": "abc"}}'),
    )
    fake_model.script.append(_content("Готово"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.final_answer == "Готово"
    assert len(result.steps) == 1
    assert result.steps[0].calls[0]["name"] == "test_tool"
    assert result.steps[0].results[0]["ok"] is True
    assert result.steps[0].results[0]["output"] == "got:abc"


async def test_text_embedded_tool_call_name_json_form(fake_model, cleanup):
    """qwen пишет «)&&(notes_search {"query": ...}» — имя инструмента + JSON."""
    _register_test_tool()
    fake_model.script.append(
        _content(')&&(test_tool {"value": "abc"})'),
    )
    fake_model.script.append(_content("Готово"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.final_answer == "Готово"
    assert len(result.steps) == 1
    assert result.steps[0].calls[0]["name"] == "test_tool"
    assert result.steps[0].calls[0]["arguments"] == {"value": "abc"}
    assert result.steps[0].results[0]["output"] == "got:abc"


async def test_text_embedded_tool_call_parenthesized_json(fake_model, cleanup):
    _register_test_tool()
    fake_model.script.append(_content('test_tool({"value": "x"})'))
    fake_model.script.append(_content("Готово"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.steps[0].results[0]["ok"] is True
    assert result.steps[0].results[0]["output"] == "got:x"
    assert result.final_answer == "Готово"


async def test_text_embedded_tool_name_without_json_is_plain_answer(
    fake_model, cleanup,
):
    """Имя инструмента в прозе без JSON после него — обычный ответ."""
    _register_test_tool()
    text = "могу вызвать test_tool, но не сейчас"
    fake_model.script.append(_content(text))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "answer"
    assert result.steps == []
    assert result.final_answer == text


async def test_text_embedded_tool_call_string_arguments(fake_model, cleanup):
    """arguments строкой (JSON внутри) — проходит тот же путь, что и обычный вызов."""
    _register_test_tool()
    fake_model.script.append(
        _content('{"name": "test_tool", "arguments": "{\\"value\\": \\"x\\"}"}'),
    )
    fake_model.script.append(_content("Готово"))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.steps[0].results[0]["ok"] is True
    assert result.steps[0].results[0]["output"] == "got:x"
    assert result.final_answer == "Готово"


async def test_text_embedded_unknown_tool_is_plain_answer(fake_model, cleanup):
    """Неизвестный инструмент в JSON текста — обычный ответ, без выполнения."""
    _register_test_tool()
    text = 'хочу так: {"name": "no_such_tool", "arguments": {}}'
    fake_model.script.append(_content(text))

    result = await ae.run_agent("sys", "user", engine="qwen", model="m")
    assert result.finished_reason == "answer"
    assert result.steps == []
    assert result.final_answer == text


async def test_text_embedded_not_a_tool_call_is_plain_answer(fake_model, cleanup):
    """JSON без name/arguments (или с аргументами не того типа) — не вызов."""
    _register_test_tool()
    cases = [
        '{"result": "ok"}',
        '{"name": "test_tool", "arguments": 42}',
        '{"name": 7, "arguments": {}}',
        "просто текст без json",
        "[]",
    ]
    for text in cases:
        fake_model.script.append(_content(text))
        result = await ae.run_agent("sys", "user", engine="qwen", model="m")
        assert result.finished_reason == "answer"
        assert result.steps == [], text
        assert result.final_answer == text
        assert fake_model.script == []


# ─── _extract_tool_call_from_content: BVA ───


def test_extract_tool_call_from_content_happy(fake_model):
    _register_test_tool()
    tool_map = {"test_tool": object()}
    call = ae._extract_tool_call_from_content(
        'søker {"name": "test_tool", "arguments": {"value": "abc"}}', tool_map,
    )
    assert call["name"] == "test_tool"
    assert call["arguments"] == {"value": "abc"}
    assert call["id"] == "call_text"


def test_extract_tool_call_from_content_bva(fake_model):
    _register_test_tool()
    tool_map = {"test_tool": object()}
    assert ae._extract_tool_call_from_content("", tool_map) is None
    assert ae._extract_tool_call_from_content(None, tool_map) is None
    assert ae._extract_tool_call_from_content("   ", tool_map) is None
    assert ae._extract_tool_call_from_content(
        '{"name": "nope", "arguments": {}}', tool_map,
    ) is None
    assert ae._extract_tool_call_from_content(
        '{"name": "test_tool"}', tool_map,
    ) is None
    assert ae._extract_tool_call_from_content(
        '{"arguments": {}}', tool_map,
    ) is None
    assert ae._extract_tool_call_from_content(
        '{"name": "test_tool", "arguments": "{\\"value\\": \\"x\\"}"}', tool_map,
    )["arguments"] == '{"value": "x"}'


def test_extract_tool_call_from_content_name_json_form_bva(fake_model):
    _register_test_tool()
    tool_map = {"test_tool": object(), "notes_search": object()}
    call = ae._extract_tool_call_from_content(
        ')&&(notes_search {"query": "Признания и проклятия"})', tool_map,
    )
    assert call["name"] == "notes_search"
    assert call["arguments"] == {"query": "Признания и проклятия"}
    assert ae._extract_tool_call_from_content(
        'notes_search {"query": "x"}', tool_map,
    )["name"] == "notes_search"
    assert ae._extract_tool_call_from_content(
        "notes_search", tool_map,
    ) is None
    assert ae._extract_tool_call_from_content(
        'в тексте notes_search но json далеко {"a": 1}', tool_map,
    ) is None
    assert ae._extract_tool_call_from_content(
        "notes_search {bad", tool_map,
    ) is None
    assert ae._extract_tool_call_from_content(
        'xnotes_search {"a": 1}', tool_map,
    ) is None
    assert ae._extract_tool_call_from_content(
        'notes_search [1, 2]', tool_map,
    ) is None
