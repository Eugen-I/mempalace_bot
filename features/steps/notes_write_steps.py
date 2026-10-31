"""Шаги BDD для features/notes_write.feature.

Сценарии выполняются через реальный движок (services/agent_engine) с фейковым
OpenAI-клиентом и реальным confirm_write из handlers/notes_agent.py;
нажатия кнопок подтверждения имитируются вызовом cb-хендлеров.
"""
import asyncio

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


def _tool_call(name, arguments="{}"):
    return FakeResponse(FakeMessage(None, [FakeToolCall("c1", name, arguments)]))


def _text_reply(text):
    return FakeResponse(FakeMessage(text))


class FakeStatus:
    """Статус-сообщение агента: answer (карточки) + edit_text."""

    def __init__(self):
        self.edits = []
        self.cards = []
        self.reply_markup = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.cards.append(text)
        self.reply_markup = reply_markup
        return self

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeCb:
    def __init__(self, uid, data):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeStatus()

    async def answer(self, text=None, show_alert=None):
        pass


def _button_token(status, prefix):
    for row in status.reply_markup.inline_keyboard:
        for btn in row:
            if btn.callback_data.startswith(prefix):
                return btn.callback_data.split(":", 1)[1]
    raise AssertionError(f"Кнопка {prefix} не найдена")


async def _wait_card(status, timeout=5.0):
    """Ждёт появления карточки подтверждения (на случай гонки с движком)."""
    import time

    deadline = time.monotonic() + timeout
    while status.reply_markup is None:
        if time.monotonic() > deadline:
            raise AssertionError("Карточка подтверждения не появилась")
        await asyncio.sleep(0.01)


async def _wait_cards(status, n, timeout=5.0):
    """Ждёт, пока появится n-я карточка (для двойного подтверждения)."""
    import time

    deadline = time.monotonic() + timeout
    while len(status.cards) < n:
        if time.monotonic() > deadline:
            raise AssertionError(f"Карточка {n} не появилась: {status.cards}")
        await asyncio.sleep(0.01)


def _click(status, prefix, handler, uid=TEST_UID):
    token = _button_token(status, prefix)
    return handler(FakeCb(uid, f"{prefix}{token}"))


# ─── Given ───


@given('the notes agent is ready for writes')
def step_notes_agent_ready(context):
    from handlers import notes_agent as na
    from services import agent_engine as ae
    from services import agent_notes_write_tools as anwt

    class FakeCompletions:
        def create(self, **kwargs):
            script = getattr(context, "script", None) or []
            if script:
                return script.pop(0)
            raise AssertionError("No scripted responses left")

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    context.orig_openai = ae.OpenAI
    context.orig_ensure = ae.ensure_ollama_running
    ae.OpenAI = lambda *a, **k: FakeClient()
    ae.ensure_ollama_running = lambda model: None

    context.calls = []
    context.anwt = anwt
    context.na = na
    context.orig_create = anwt.create_note
    context.orig_delete = anwt.delete_note
    anwt.create_note = (
        lambda title, body="", folder=None: context.calls.append(("create", title)) or "n1"
    )
    anwt.delete_note = lambda note_id: context.calls.append(("delete", note_id)) or True
    context.status = FakeStatus()


@given('the model script returns a tool call "notes_create" and then a final text')
def step_script_create(context):
    context.script = [
        _tool_call("notes_create", '{"title": "Тест"}'),
        _text_reply("✅ Заметка создана"),
    ]


@given('the model script returns a tool call "notes_delete" and then a final text')
def step_script_delete(context):
    context.script = [
        _tool_call("notes_delete", '{"note_id": "B2"}'),
        _text_reply("Заметка удалена"),
    ]


# ─── When ───


def _run_agent_with_confirm(context, decide):
    """Запускает движок с реальным confirm_write; decide(status) — имитация кликов."""

    async def flow():
        from services import agent_engine as ae

        status = context.status
        confirm = context.na._make_confirm_write(TEST_UID, status)
        context.approved = None

        async def clicker():
            await asyncio.sleep(0.05)
            await decide(status)

        click = asyncio.create_task(clicker())
        try:
            context.result = await ae.run_agent(
                context.na.NOTES_AGENT_SYSTEM_PROMPT,
                "сохрани тест",
                engine="qwen",
                model="qwen2.5:7b",
                allowed_categories=(context.na.CAT_NOTES,),
                include_write=True,
                confirm_write=confirm,
                max_iterations=3,
            )
        finally:
            click.cancel()

    _run(flow())


@when('I run the notes agent and approve the confirmation')
def step_run_and_approve(context):
    async def decide(status):
        await _wait_card(status)
        await _click(status, "notes_confirm:", context.na.cb_notes_confirm)

    _run_agent_with_confirm(context, decide)


@when('I run the notes agent and cancel the confirmation')
def step_run_and_cancel(context):
    async def decide(status):
        await _wait_card(status)
        await _click(status, "notes_cancel:", context.na.cb_notes_cancel)

    _run_agent_with_confirm(context, decide)


@when('I run the notes agent and approve the first confirmation only')
def step_run_approve_first_only(context):
    async def decide(status):
        await _wait_card(status)
        await _click(status, "notes_confirm:", context.na.cb_notes_confirm)
        await _wait_cards(status, 2)
        context.second_card = status.cards[-1]
        await _click(status, "notes_cancel:", context.na.cb_notes_cancel)

    _run_agent_with_confirm(context, decide)


@when('I run the engine without a confirmation callback')
def step_run_engine_without_confirm(context):
    from services import agent_engine as ae

    async def flow():
        context.result = await ae.run_agent(
            "s", "u", engine="qwen", model="qwen2.5:7b",
            include_write=True, max_iterations=2,
        )

    _run(flow())


@when('I run the notes agent and the confirmation times out')
def step_run_and_timeout(context):
    orig_timeout = context.na.CONFIRM_TIMEOUT
    context.na.CONFIRM_TIMEOUT = 0.05

    async def decide(status):
        await asyncio.sleep(0.1)  # просто не нажимаем — ждём таймаут

    try:
        _run_agent_with_confirm(context, decide)
    finally:
        context.na.CONFIRM_TIMEOUT = orig_timeout


@when('I run the notes agent with writes disabled')
def step_run_writes_disabled(context):
    from services import agent_engine as ae

    async def flow():
        context.result = await ae.run_agent(
            "s", "u", engine="qwen", model="qwen2.5:7b",
            include_write=False, max_iterations=2,
        )

    _run(flow())


# ─── Then ───


@then('the note is created with title "Тест"')
def step_note_created(context):
    assert ("create", "Тест") in context.calls, context.calls


@then('the notes agent final answer contains the tool output')
def step_final_answer(context):
    assert context.result.final_answer, "Нет финального ответа"
    assert "Заметка создана" in context.result.final_answer


@then('no note is created')
def step_no_note_created(context):
    assert not any(c[0] == "create" for c in context.calls), context.calls


@then('the model sees "Пользователь отклонил действие"')
def step_model_sees_rejected(context):
    assert context.result.steps
    out = context.result.steps[0].results[0]["output"]
    assert "отклонил" in out, out


@then('the note is not deleted')
def step_note_not_deleted(context):
    assert not any(c[0] == "delete" for c in context.calls), context.calls


@then('a second confirmation card is shown')
def step_second_card(context):
    assert "Двойное подтверждение" in context.second_card


@then('the write tool is reported as unknown')
def step_write_tool_unknown(context):
    assert context.result.steps
    out = context.result.steps[0].results[0]["output"]
    assert "не существует" in out, out
