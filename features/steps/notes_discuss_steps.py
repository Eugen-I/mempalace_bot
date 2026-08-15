"""Шаги BDD для features/notes_discuss.feature.

Выполняются через реальные хендлеры handlers.notes_agent (cb_notes_view,
cb_notes_discuss, cb_notes_storm, cb_notes_save, cb_notes_stop, run_notes_agent)
с фейковыми источниками: кэш списка заметок, read_note, run_agent/finalize_answer.
"""
import asyncio

from behave import given, then, when

from handlers import notes_agent as na

TEST_UID = 424242


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _reset():
    na._notes_list_store.clear()
    na._notes_discuss_ctx.clear()
    na._waiting_for_notes_input.clear()
    na._notes_view_store.clear()


class FakeMessage:
    def __init__(self):
        self.answers = []
        self.edits = []
        self.reply_markup = None
        self.last_answer = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        sent = FakeMessage()
        self.last_answer = sent
        return sent

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.reply_markup = reply_markup


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeCb:
    def __init__(self, data):
        self.from_user = FakeUser(TEST_UID)
        self.data = data
        self.message = FakeMessage()

    async def answer(self, text=None, show_alert=None):
        pass


def _parse_row(row: str) -> dict:
    row = row.strip().strip('"')
    name, rest = row.split(" [id=")
    if "] (папка: " in rest:
        note_id, _, folder = rest.partition("] (папка: ")
        folder = folder.rstrip(")")
    else:
        note_id = rest.rstrip("]")
        folder = ""
    return {"id": note_id, "name": name, "folder": folder}


def _seed_list(context, rows: str):
    items = [_parse_row(r) for r in rows.split(",")]
    _reset()
    na._notes_list_store[TEST_UID] = {"items": items, "text": ""}
    context.notes = items


def _seed_read(context, body="Снимать на рассвете"):
    def fake_read(note_id):
        if getattr(context, "read_fail", False):
            raise RuntimeError("osascript down")
        note = next(n for n in context.notes if n["id"] == note_id)
        return {"name": note["name"], "body": body}

    import services.apple_notes as an

    context.orig_read = an.read_note
    an.read_note = fake_read


def _restore_read(context):
    import services.apple_notes as an

    if getattr(context, "orig_read", None) is not None:
        an.read_note = context.orig_read
        context.orig_read = None


def _patch_storm(context):
    """Мокает штурм: модель отвечает валидным JSON по тексту из prompt."""
    from services import ai_engine
    from services import brainstorm as bs

    context.orig_response = ai_engine.get_ai_response_async
    context.orig_collect = bs.collect_context
    context.orig_current_ai = ai_engine.get_current_ai

    def fake_collect(topic, mode="standard", folder=None):
        return _run(_coro({"notes": "", "guide": "гайд"}))

    async def fake_response(engine, model, msgs, **kwargs):
        for m in msgs:
            if m.get("role") == "user":
                context.storm_prompt = m.get("content", "")
        return ('{"ideas": [{"title": "Т", "camera_setup": "Имитация плёнки ACROS, '
                'тени -2", "reason": "р", "steps": "s"}]}')

    ai_engine.get_ai_response_async = fake_response
    ai_engine.get_current_ai = lambda: ("fake", "model")


def _restore_storm(context):
    from services import ai_engine
    from services import brainstorm as bs

    if getattr(context, "orig_response", None) is not None:
        ai_engine.get_ai_response_async = context.orig_response
        bs.collect_context = context.orig_collect
        ai_engine.get_current_ai = context.orig_current_ai
        context.orig_response = None


def _coro(value):
    async def _inner():
        return value

    return _inner()


# ─── Given ───


@given('the notes agent found notes [{rows}]')
def step_notes_found(context, rows):
    _seed_list(context, rows)
    _seed_read(context)


@given("no notes list is cached")
def step_no_notes_list(context):
    _reset()
    context.notes = []


@given('reading note "{note_id}" fails')
def step_reading_fails(context, note_id):
    context.read_fail = True


@given('note "{note_id}" body is empty')
def step_note_body_empty(context, note_id):
    _seed_read(context, body="   ")


@given('note "{note_id}" body is long')
def step_note_body_long(context, note_id):
    _seed_read(context, body="слово " * 400)  # 2000 символов → 2 страницы


@given('the note "{note_id}" is open on the first page')
def step_note_open_first_page(context, note_id):
    cb = FakeCb("notes_view:0")
    _run(na.cb_notes_view(cb))


@given('note "{note_id}" body is "{body}"')
def step_note_body_is(context, note_id, body):
    _seed_read(context, body=body)


@given('discussion of note "{note_id}" is enabled')
def step_discussion_enabled(context, note_id):
    _reset()
    na._notes_discuss_ctx[TEST_UID] = {
        "note_id": note_id, "name": "Идеи", "folder": "",
    }
    context.question = None


# ─── When ───


@when('I click the "{data}" button')
def step_click_button(context, data):
    context.last_cb = FakeCb(data)
    if data.startswith("notes_view:"):
        context.last_note_message = context.last_cb.message
        _run(na.cb_notes_view(context.last_cb))
    elif data.startswith("notes_discuss:"):
        _run(na.cb_notes_discuss(context.last_cb))
    elif data.startswith("notes_storm:"):
        _patch_storm(context)
        try:
            _run(na.cb_notes_storm(context.last_cb))
        finally:
            _restore_storm(context)
    elif data.startswith("notes_save:"):
        from handlers.palace import _save_state, _show_save_wings

        context.orig_save_wings = _show_save_wings

        async def fake_save_wings(edit_func, uid):
            await edit_func("выбери крыло", parse_mode="HTML")

        _show_save_wings = fake_save_wings
        try:
            _run(na.cb_notes_save(context.last_cb))
        finally:
            _show_save_wings = context.orig_save_wings
            _save_state.pop(TEST_UID, None)
    elif data.startswith("notes_stop:"):
        _run(na.cb_notes_stop(context.last_cb))
    elif data.startswith("notes_page:"):
        _run(na.cb_notes_page(context.last_cb))
    elif data.startswith("notes_back:"):
        from handlers.palace import action_bar

        context.orig_finalize = action_bar.finalize_answer

        async def fake_finalize(uid, edit_func, text, **kwargs):
            context.back_answer = text
            context.back_rows = kwargs.get("extra_rows")

        action_bar.finalize_answer = fake_finalize
        try:
            _run(na.cb_notes_back(context.last_cb))
        finally:
            action_bar.finalize_answer = context.orig_finalize


@when('I click the "{data}" button and the model answers')
def step_click_button_with_model(context, data):
    step_click_button(context, data)


@when('I send "{question}"')
def step_send_question(context, question):
    from handlers.palace import action_bar

    async def fake_finalize(uid, edit_func, text, **kwargs):
        pass

    async def fake_run_agent(system, question_text, **kwargs):
        context.question = question_text
        return na.ae.AgentResult(final_answer="Ответ", finished_reason="done")

    orig_run_agent = na.ae.run_agent
    orig_finalize = action_bar.finalize_answer
    na.ae.run_agent = fake_run_agent
    action_bar.finalize_answer = fake_finalize
    try:
        status = FakeMessage()
        _run(na.run_notes_agent(TEST_UID, status, question))
    finally:
        na.ae.run_agent = orig_run_agent
        action_bar.finalize_answer = orig_finalize


@when("the notes agent finalizes the list answer with ids")
def step_finalize_list_with_ids(context):
    from types import SimpleNamespace

    from handlers.palace import action_bar

    rows = (
        "- Идеи для фото [id=AAA] (папка: Notes)\n"
        "- Покупки [id=BBB] (папка: Дом)"
    )
    step = SimpleNamespace(
        calls=[{"id": "c1", "name": "notes_search", "arguments": "{}"}],
        results=[{"name": "notes_search", "ok": True, "output": rows}],
    )
    result = na.ae.AgentResult(
        final_answer=f"Нашёл заметки:\n{rows}", finished_reason="done", steps=[step],
    )

    async def fake_run_agent(*args, **kwargs):
        return result

    async def fake_finalize(uid, edit_func, text, **kwargs):
        context.list_answer = text
        context.list_rows = kwargs.get("extra_rows")

    orig_run_agent = na.ae.run_agent
    orig_finalize = action_bar.finalize_answer
    na.ae.run_agent = fake_run_agent
    action_bar.finalize_answer = fake_finalize
    try:
        status = FakeMessage()
        _run(na._run_notes_agent_reply(TEST_UID, status, "найди заметки"))
    finally:
        na.ae.run_agent = orig_run_agent
        action_bar.finalize_answer = orig_finalize


# ─── Then ───


@then('the note "{name}" body is shown')
def step_note_body_shown(context, name):
    joined = "\n".join(context.last_cb.message.edits + context.last_cb.message.answers)
    assert name in joined, joined
    assert "рассвете" in joined, joined


@then('the action buttons include "{data}"')
def step_action_buttons_include(context, data):
    markup = context.last_cb.message.reply_markup
    assert markup is not None, "клавиатура действий не прикреплена"
    buttons = [
        b.callback_data
        for row in markup.inline_keyboard for b in row
    ]
    assert data in buttons, buttons


@then('discussion of note "{note_id}" is enabled')
def step_discussion_on(context, note_id):
    ctx = na._current_discuss(TEST_UID)
    assert ctx and ctx["note_id"] == note_id, ctx
    assert na.is_waiting_for_notes_input(TEST_UID)
    _restore_read(context)


@then('discussion of note "{note_id}" is still enabled')
def step_discussion_still_on(context, note_id):
    step_discussion_on(context, note_id)


@then('discussion of note "{note_id}" is disabled')
def step_discussion_off(context, note_id):
    assert na._current_discuss(TEST_UID) is None
    assert not na.is_waiting_for_notes_input(TEST_UID)


@then('I see the "{fragment}" error')
def step_error_seen(context, fragment):
    joined = "\n".join(context.last_cb.message.edits)
    assert fragment.lower() in joined.lower(), joined
    assert na._current_discuss(TEST_UID) is None
    _restore_read(context)


@then('I see the "{fragment}" hint')
def step_hint_seen(context, fragment):
    joined = "\n".join(context.last_cb.message.edits)
    assert fragment.lower() in joined.lower(), joined
    _restore_read(context)


@then('the agent question mentions "{note_id}" and "{name}"')
def step_question_mentions(context, note_id, name):
    assert context.question, "вопрос не дошёл до агента"
    assert note_id in context.question, context.question
    assert name in context.question, context.question
    _restore_read(context)


@then('I do not see several messages')
def step_no_multiple_messages(context):
    assert not context.last_cb.message.answers, context.last_cb.message.answers
    assert len(context.last_cb.message.edits) == 1, context.last_cb.message.edits


@then('the notes list is shown again with "{first}" and "{second}"')
def step_back_to_list(context, first, second):
    assert getattr(context, "back_answer", None) is not None, \
        "возврат к списку не отрисовал список"
    rows = context.back_rows or []
    cbs = [b.callback_data for row in rows for b in row]
    assert first in cbs and second in cbs, cbs
    _restore_read(context)


@then("the shown notes list has no ids and only button rows")
def step_list_has_no_ids(context):
    answer = getattr(context, "list_answer", None)
    assert answer is not None, "финальный список не отрисован"
    assert "id=" not in answer and "[id=" not in answer, answer
    assert "- Идеи для фото (папка: Notes)" in answer, answer
    assert "- Покупки (папка: Дом)" in answer, answer
    rows = context.list_rows or []
    cbs = [b.callback_data for row in rows for b in row]
    assert "notes_view:0" in cbs and "notes_view:1" in cbs, cbs
    _restore_read(context)


@then('the storm prompt contains "{body}"')
def step_storm_prompt_contains(context, body):
    assert getattr(context, "storm_prompt", None), "промпт штурма не перехвачен"
    assert body in context.storm_prompt, context.storm_prompt
    _restore_read(context)


@then('the storm arrives as a new message and the note "{name}" body is still shown')
def step_storm_new_message_and_note_stays(context, name):
    assert context.last_cb.message.answers, "штурм должен прийти новым сообщением"
    storm_view = "\n".join(context.last_cb.message.last_answer.edits)
    assert "Сюрреалистичный штурм" in storm_view, storm_view
    note_msg = getattr(context, "last_note_message", None)
    assert note_msg is not None, "заметка не была открыта"
    note_view = "\n".join(note_msg.edits)
    assert name in note_view, "заметка не должна заменяться штурмом"
    assert "Сюрреалистичный штурм" not in note_view, \
        "штурм не должен попадать в сообщение заметки"
    assert note_msg.reply_markup is not None, \
        "клавиатура заметки должна остаться на месте"
    _restore_read(context)
