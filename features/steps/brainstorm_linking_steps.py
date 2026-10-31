"""Шаги BDD для features/brainstorm_linking.feature.

Тестируют блок «Связано с:» в превью сохранения идеи. Реальный код
handlers.brainstorm (cb_pick_idea → _storm_confirm → bs.find_linked)
с фейковым CallbackQuery и контекстом.
"""
import asyncio

from behave import given, then, when

import config

config.ALLOWED_IDS = {424242}

from handlers import brainstorm as bh  # noqa: E402

UID = 424242


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeChat:
    id = 1


class FakeUser:
    id = UID


class FakeMessage:
    def __init__(self):
        self.chat = FakeChat()
        self.from_user = FakeUser()
        self.edits = []

    async def edit_text(self, text, **kw):
        self.edits.append(text)


class FakeCb:
    def __init__(self, data):
        self.from_user = FakeUser()
        self.data = data
        self.message = FakeMessage()
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


def _setup_session(idea_text, ctx):
    bh._storm_data.clear()
    bh._storm_data[UID] = {
        "topic": "Тема",
        "context": ctx,
        "ideas": [{"title": idea_text, "reason": "", "steps": ""}],
    }


def _pick_idea(n=1):
    cb = FakeCb(data=f"bs_pick:{n}")
    _run(bh.cb_pick_idea(cb))
    return cb


@given('сессия штурма с идеей "{idea}"')
def given_session(context, idea):
    context._session = {"idea": idea, "context": {"notes": "", "palace": "", "kg": ""}}
    _setup_session(idea, context._session["context"])


@given('контекст содержит заметку "{note}"')
def given_context_note(context, note):
    context._session["context"]["notes"] = f"- {note}"
    _setup_session(context._session["idea"], context._session["context"])


@given("контекст пустой")
def given_context_empty(context):
    context._session["context"] = {"notes": "", "palace": "", "kg": ""}
    _setup_session(context._session["idea"], context._session["context"])


@given("сессия штурма отсутствует")
def given_session_absent(context):
    bh._storm_data.clear()
    context._session = None


@given('контекст содержит {n:d} строк с общим словом "{word}"')
def given_context_n_lines(context, n, word):
    notes = "\n".join(f"- {word} строка {i}" for i in range(1, n + 1))
    context._session["context"]["notes"] = notes
    _setup_session(context._session["idea"], context._session["context"])


@given('контекст содержит строку "{line}"')
def given_context_line(context, line):
    prev = context._session["context"].get("notes", "")
    context._session["context"]["notes"] = (prev + f"\n- {line}").strip()
    _setup_session(context._session["idea"], context._session["context"])


@when("пользователь выбирает идею 1")
def when_pick_idea_1(context):
    context._cb = _pick_idea(1)


@then('превью содержит блок "{marker}"')
def then_has_linked(context, marker):
    text = context._cb.message.edits[-1]
    assert marker in text


@then('превью содержит источник "{label}"')
def then_has_source(context, label):
    assert label in context._cb.message.edits[-1]


@then('превью содержит текст "{snippet}"')
def then_has_snippet(context, snippet):
    assert snippet in context._cb.message.edits[-1]


@then('превью не содержит блок "Связано с"')
def then_no_linked(context):
    text = context._cb.message.edits[-1]
    assert "Связано с" not in text


@then('превью содержит "Сохранить в Дворец"')
def then_has_save(context):
    assert "Сохранить в Дворец" in context._cb.message.edits[-1]


@then('сообщение "Сессия истекла"')
def then_session_expired(context):
    assert "Сессия истекла" in context._cb.message.edits[-1]


@then("превью нет")
def then_no_preview(context):
    assert len(context._cb.message.edits) == 1
    assert "Связано с" not in context._cb.message.edits[-1]


@then('в блоке "Связано с" ровно {n:d} записей')
def then_linked_count(context, n):
    text = context._cb.message.edits[-1]
    count = text.count("• <b>")
    assert count == n, f"ожидалось {n}, получено {count}: {text[:300]}"


@then("строка с двумя совпадениями идёт первой")
def then_sorted_by_overlaps(context):
    text = context._cb.message.edits[-1]
    lines = [ln for ln in text.splitlines() if ln.startswith("•")]
    assert lines, "нет строк «Связано с»"
    assert "фотосерия и парке вместе" in lines[0]
