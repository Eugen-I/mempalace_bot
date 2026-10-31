"""Шаги BDD для features/agent_mode.feature.

Реализуют сценарии через реальный код агента (services/agent_engine,
services/agent_tools, handlers/agent) с фейковым OpenAI-клиентом
и временным каталогом настроек.
"""
import asyncio
import json

from behave import given, then, when

TEST_UID = 424242


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


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


def _tool_call(name, arguments="{}", call_id="call_1"):
    return FakeResponse(FakeMessage(None, [FakeToolCall(call_id, name, arguments)]))


def _text_reply(text):
    return FakeResponse(FakeMessage(text))


class FakeMCP:
    """Фейковый MCP-клиент: отдаёт фиксированный ответ и записывает вызовы."""

    def __init__(self, output):
        self.output = output
        self.calls = []

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments or {}))
        return self.output


def _register_fake_model(context):
    """Подменяет OpenAI-клиент и ensure_ollama_running на services.agent_engine."""
    from services import agent_engine as ae

    script = context.script or []
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if script:
                return script.pop(0)
            raise AssertionError("No scripted responses left")

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    orig_openai = ae.OpenAI
    orig_ensure = ae.ensure_ollama_running
    ae.OpenAI = lambda *a, **k: FakeClient()
    ae.ensure_ollama_running = lambda model: None
    context.model_calls = calls
    context.orig_openai = orig_openai
    context.orig_ensure = orig_ensure


def _restore_fake_model(context):
    from services import agent_engine as ae

    ae.OpenAI = context.orig_openai
    ae.ensure_ollama_running = context.orig_ensure


# ─── Given ───


@given('the agent is enabled in my settings')
def step_agent_enabled(context):
    from services import agent_settings as a_settings

    a_settings.set_agent_enabled(TEST_UID, True)
    context.settings_dirty = True


@given('the agent is disabled in my settings')
def step_agent_disabled(context):
    from services import agent_settings as a_settings

    a_settings.set_agent_enabled(TEST_UID, False)
    context.settings_dirty = True


@given('the model script returns a tool call "mp_kg_stats" and then a final text')
def step_script_tool_then_text(context):
    context.script = [
        _tool_call("mp_kg_stats", '{"scope": "all"}'),
        _text_reply("Комнат в дворце: 7"),
    ]


@given('the model script returns only a plain text without tool calls')
def step_script_plain_text(context):
    context.script = [_text_reply("привет, я qwen2.5")]


@given("the model writes the tool call as text '{text}' and then returns \"{answer}\"")
def step_script_text_tool_call(context, text, answer):
    """qwen иногда пишет JSON вызова инструмента прямо в content."""
    context.script = [_text_reply(text), _text_reply(answer)]


@given('the model script calls the unknown tool "no_such_tool"')
def step_script_unknown_tool(context):
    context.script = [
        _tool_call("no_such_tool", "{}"),
        _text_reply("Инструмент 'no_such_tool' не существует."),
    ]


@given('a tool "mp_boom" is registered that raises an exception')
def step_register_raising_tool(context):
    import services.agent_engine  # noqa: F401 — сначала регистрируются реальные mp-инструменты
    from services import agent_tools as at

    at.unregister_tool("mp_boom")

    @at.register_tool("mp_boom", "Тестовый падающий инструмент")
    def boom(args):
        raise RuntimeError("boom")

    context.registered_tools = getattr(context, "registered_tools", []) + ["mp_boom"]


@given('the model script calls "mp_boom" and then returns a final text')
def step_script_boom(context):
    context.script = [
        _tool_call("mp_boom", "{}"),
        _text_reply("Ошибка инструмента: boom"),
    ]


@given('the model script requests a tool on every iteration')
def step_script_loop(context):
    context.script = [
        _tool_call("mp_kg_stats", '{"scope": "all"}') for _ in range(5)
    ]


@given('the MCP server returns "{output}"')
def step_mcp_returns(context, output):
    from services import agent_mcp_tools as amt

    client = FakeMCP(output)
    context.agent_mcp_orig = amt.get_mcp
    amt.get_mcp = lambda: client
    context.mcp_client = client


@given('the model script calls "mp_search" with the query "{query}" and then returns "{text}"')
def step_script_mp_search(context, query, text):
    context.script = [
        _tool_call("mp_search", json.dumps({"query": query}, ensure_ascii=False)),
        _text_reply(text),
    ]


@given('the Apple Notes index contains the note "{name}" with id "{note_id}"')
def step_notes_index(context, name, note_id):
    from services import agent_notes_tools as ant

    context.notes_orig_search = ant.search_notes_hybrid
    context.notes_orig_read = ant.read_note
    context.notes_read_calls = []

    def fake_search(query, limit=10, force_refresh=False):
        return [{"id": note_id, "name": name, "folder": "Философия", "updated": ""}]

    def fake_read(nid):
        context.notes_read_calls.append(nid)
        return {"name": name, "body": f"Содержимое: {name}"}

    ant.search_notes_hybrid = fake_search
    ant.read_note = fake_read


@given('a note "{name}" with id "{note_id}" and text "{body}" is in the Apple Notes index')
def step_notes_index_with_body(context, name, note_id, body):
    """Заметка с текстом: поиск находит слово из текста и возвращает сниппет."""
    from services import agent_notes_tools as ant

    context.notes_orig_search = ant.search_notes_hybrid
    context.notes_orig_read = ant.read_note
    context.notes_read_calls = []

    def fake_search(query, limit=10, force_refresh=False):
        words = [w.lower() for w in query.split()]
        low = body.lower()
        if not all(w in low for w in words):
            return []
        return [{
            "id": note_id, "name": name, "folder": "Философия",
            "updated": "", "snippet": f"…{body[:60]}…",
        }]

    def fake_read(nid):
        context.notes_read_calls.append(nid)
        return {"name": name, "body": body}

    ant.search_notes_hybrid = fake_search
    ant.read_note = fake_read


@given('semantic search returns the note "{name}" with id "{note_id}" for the query "{query}"')
def step_semantic_notes_index(context, name, note_id, query):
    """Семантика находит заметку по смыслу: слово запроса отсутствует
    в названии, но заметка найдена (эмуляция семантического дополнения)."""
    from services import agent_notes_tools as ant

    context.notes_orig_search = ant.search_notes_hybrid
    context.notes_orig_read = ant.read_note
    context.notes_read_calls = []

    def fake_search(q, limit=10, force_refresh=False):
        if q != query:
            return []
        return [{
            "id": note_id, "name": name, "folder": "Личное",
            "updated": "", "snippet": f"…{name}: по смыслу…",
        }]

    def fake_read(nid):
        context.notes_read_calls.append(nid)
        return {"name": name, "body": "поехать на море"}

    ant.search_notes_hybrid = fake_search
    ant.read_note = fake_read


@given('the semantic search is unavailable')
def step_semantic_unavailable(context):
    """Семантическая модель недоступна — гибрид возвращает пусто."""
    from services import agent_notes_tools as ant

    context.notes_orig_search = ant.search_notes_hybrid
    context.notes_orig_read = ant.read_note

    def fake_search(q, limit=10, force_refresh=False):
        return []

    def fake_read(nid):
        return {"name": "?", "body": ""}

    ant.search_notes_hybrid = fake_search
    ant.read_note = fake_read


@given('the model script calls "notes_search" and then "notes_read" and then returns "{text}"')
def step_script_notes(context, text):
    context.script = [
        _tool_call("notes_search", json.dumps({"query": "воля"}, ensure_ascii=False)),
        _tool_call("notes_read", json.dumps({"note_id": "note1"})),
        _text_reply(text),
    ]


@given(
    'the model script calls "notes_search" with the query "{query}" and then '
    '"notes_read" with id "{note_id}" and then returns "{text}"',
)
def step_script_notes_with_ids(context, query, note_id, text):
    context.script = [
        _tool_call("notes_search", json.dumps({"query": query}, ensure_ascii=False)),
        _tool_call("notes_read", json.dumps({"note_id": note_id})),
        _text_reply(text),
    ]


@given('a tool "mp_kg_stats" is registered that returns "{output}"')
def step_register_stats_tool(context, output):
    import services.agent_engine  # noqa: F401 — сначала регистрируются реальные mp-инструменты
    from services import agent_tools as at

    at.unregister_tool("mp_kg_stats")

    @at.register_tool("mp_kg_stats", "Статистика дворца", schema={
        "type": "object",
        "properties": {"scope": {"type": "string"}},
    })
    def stats(args):
        return output

    context.registered_tools = getattr(context, "registered_tools", []) + ["mp_kg_stats"]


# ─── When ───


@when('I run the agent with the user prompt "{prompt}"')
def step_run_agent(context, prompt):
    _register_fake_model(context)
    context.statuses = []

    async def status_cb(text):
        context.statuses.append(text)

    from services import agent_engine as ae

    context.result = _run(ae.run_agent(
        "Тестовая системная инструкция.",
        prompt,
        engine="qwen",
        model="qwen2.5:7b",
        status_cb=status_cb,
    ))
    _restore_fake_model(context)
    if getattr(context, "agent_mcp_orig", None):
        from services import agent_mcp_tools as amt

        amt.get_mcp = context.agent_mcp_orig
        context.agent_mcp_orig = None
    if getattr(context, "notes_orig_search", None):
        from services import agent_notes_tools as ant

        ant.search_notes_hybrid = context.notes_orig_search
        ant.read_note = context.notes_orig_read
        context.notes_orig_search = None


@when('I ask the routing gate about the message "{text}"')
def step_ask_gate(context, text):
    from handlers.agent import should_route_to_agent

    context.gate_result = should_route_to_agent(TEST_UID, text)


# ─── Then ───


@then('I see the step status "{status}"')
def step_see_status(context, status):
    assert status in context.statuses, f"{status!r} not in {context.statuses}"


@then('the tool "mp_kg_stats" is executed with valid arguments')
def step_tool_executed(context):
    assert any(
        kw.get("messages") and any(
            m.get("role") == "tool" and "Комнат" in str(m.get("content"))
            for m in kw.get("messages", [])
        )
        for kw in context.model_calls
    )


@then("the final answer contains the tool output")
def step_answer_contains_tool_output(context):
    assert context.result.final_answer == "Комнат в дворце: 7"


@then("the agent finished in 2 iterations without error")
def step_finished_2(context):
    assert context.result.iterations == 2
    assert context.result.finished_reason == "answer"
    assert context.result.error is None


@then("the routing gate returns False")
def step_gate_false(context):
    assert context.gate_result is False


@then("the agent is not started")
def step_agent_not_started(context):
    assert not getattr(context, "result", None) or context.result.iterations == 0


@then("the final answer equals the model text")
def step_answer_equals_text(context):
    assert context.result.final_answer == "привет, я qwen2.5"


@then('the agent finished with reason "answer" without error')
def step_finished_answer(context):
    assert context.result.finished_reason == "answer"
    assert context.result.error is None


@then('the final answer contains the text "{text}"')
def step_answer_contains_text(context, text):
    assert text in context.result.final_answer


@then("the agent finished in 2 iterations without crash")
def step_finished_2_no_crash(context):
    assert context.result.iterations == 2
    assert context.result.finished_reason == "answer"
    assert context.result.error is None


@then("the agent finished without crash")
def step_no_crash(context):
    assert context.result.error is None


@then("the MCP tool \"{name}\" was called with the query \"{query}\"")
def step_mcp_called(context, name, query):
    assert context.mcp_client.calls == [(name, {"query": query})]


@then('the tool "notes_read" was called with the id "{note_id}"')
def step_notes_read_called(context, note_id):
    assert context.notes_read_calls == [note_id]


@then('the result error contains the word "лимит"')
def step_result_limit(context):
    assert context.result.finished_reason == "max_iterations"
    assert context.result.error and "лимит" in context.result.error
