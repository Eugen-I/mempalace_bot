"""Шаги BDD для features/notes_discuss.feature.

Выполняются через реальные хендлеры handlers.notes_agent (cb_notes_view,
run_notes_agent) с фейковыми источниками: кэш списка заметок, read_note,
run_agent/finalize_answer.
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


class FakeMessage:
    def __init__(self):
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


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
    name, note_id = row.split(" [id=")
    return {"id": note_id.rstrip("]"), "name": name}


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


@given('discussion of note "{note_id}" is enabled')
def step_discussion_enabled(context, note_id):
    _reset()
    na._notes_discuss_ctx[TEST_UID] = {"note_id": note_id, "name": "Идеи"}
    context.question = None


# ─── When ───


@when('I click the "{data}" button')
def step_click_button(context, data):
    context.last_cb = FakeCb(data)
    _run(na.cb_notes_view(context.last_cb))


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


# ─── Then ───


@then('the note "{name}" body is shown')
def step_note_body_shown(context, name):
    joined = "\n".join(context.last_cb.message.edits + context.last_cb.message.answers)
    assert name in joined, joined
    assert "рассвете" in joined, joined


@then('discussion of note "{note_id}" is enabled')
def step_discussion_on(context, note_id):
    ctx = na._current_discuss(TEST_UID)
    assert ctx and ctx["note_id"] == note_id, ctx
    assert na.is_waiting_for_notes_input(TEST_UID)
    _restore_read(context)


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
