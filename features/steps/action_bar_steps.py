"""Шаги BDD для features/palace_action_bar.feature.

Реализуют сценарии через реальный код action bar
(handlers/palace/action_bar.py) с фейковым Message/CallbackQuery.
"""
import asyncio
from types import SimpleNamespace

from behave import given, then, when

TEST_UID = 424242


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeMessage:
    """Повторяет контракт aiogram.Message: edit_text/answer возвращают self."""

    def __init__(self):
        self.calls = []

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.calls.append(("edit", text, reply_markup))
        return self

    async def answer(self, text=None, parse_mode=None, reply_markup=None):
        self.calls.append(("answer", text or "", reply_markup))
        return self


class FakeCb:
    """Минимальный CallbackQuery: data, message, from_user, answer()."""

    def __init__(self, data, msg):
        self.data = data
        self.message = msg
        self.answers = []
        self.from_user = SimpleNamespace(id=TEST_UID)

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))


def _kb_labels(msg, last=True):
    reply_markup = msg.calls[-1][2] if last else msg.calls[0][2]
    if reply_markup is None:
        return []
    return [b.text for row in reply_markup.inline_keyboard for b in row]


def _kb_callback(msg):
    reply_markup = msg.calls[-1][2]
    if reply_markup is None:
        return []
    return [b.callback_data for row in reply_markup.inline_keyboard for b in row]


def _latest_text(msg):
    return msg.calls[-1][1]


def _finalize(msg, text, ctx=None, title=""):
    from handlers.palace.action_bar import finalize_answer

    _run(finalize_answer(
        TEST_UID, msg.edit_text, text, ctx=ctx, title=title,
    ))
    sid = None
    for d in _kb_callback(msg):
        if d.startswith("ab_ai:"):
            sid = d.split(":", 1)[1]
            break
    return sid


# ─── Given ───


@given('I open a record in the Palace room "{room}"')
def step_open_record(context, room):
    context.wing, context.room = tuple(room.split("/"))


@given("the record text is {n} characters long")
def step_record_text_len(context, n):
    target = int(n)
    context.record_text = "слово " * (target // 6)
    while len(context.record_text) < target:
        context.record_text += " "


@given('the answer text is exactly {n} characters')
def step_answer_text_exact(context, n):
    context.answer_text = "а" * int(n)


@given("the answer text is {n} characters")
def step_answer_text_len(context, n):
    context.answer_text = "а" * int(n)


@given("a Palace answer without a parent screen context")
def step_answer_no_parent(context):
    context.msg = FakeMessage()
    context.sid = _finalize(context.msg, "просто текст", ctx={})


@given("I press a pagination button of an answer older than 30 minutes")
def step_press_stale_pagination(context):
    from handlers.palace.action_bar import answer_store

    answer_store.clear()
    context.msg = FakeMessage()
    context.cb = FakeCb("ab_pg:deadbeef:1", context.msg)


@given('I press [{button}] and choose "{choice}"')
def step_press_ai_menu(context, button, choice):
    context.msg = FakeMessage()
    sid = _finalize(
        context.msg, "ответ для анализа",
        ctx={"parent_cb": "p_rdb", "wing": "w", "room": "r"},
    )
    choice_map = {"Анализ ответа": "ab_ai_m:a", "С контекстом комнаты": "ab_ai_m:c"}
    context.cb = FakeCb(f"{choice_map[choice]}:{sid}", context.msg)


@given("I press [{button}]")
def step_press_web_button(context, button):
    context.msg = FakeMessage()
    sid = _finalize(
        context.msg, "текст для поиска",
        ctx={"parent_cb": "p_rdb", "wing": "w", "room": "r"},
    )
    context.cb = FakeCb(f"ab_web:{sid}", context.msg)


# ─── When ───


@when("the record is rendered with the action bar")
def step_render_record(context):
    context.msg = FakeMessage()
    text = getattr(context, "record_text", None) or getattr(context, "answer_text", "а" * 1500)
    context.sid = _finalize(
        context.msg, text,
        ctx={"parent_cb": "p_rdb", "wing": context.wing, "room": context.room},
        title=f"<b>📄 {context.room}</b>",
    )


@when("the action bar is rendered")
def step_render_bar(context):
    from handlers.palace.action_bar import build_action_bar

    if not hasattr(context, "msg"):
        context.msg = FakeMessage()
    text = getattr(context, "answer_text", "а" * 1500)
    if not hasattr(context, "sid"):
        context.sid = _finalize(
            context.msg, text,
            ctx={"parent_cb": "p_rdb", "wing": "w", "room": "r"},
        )
    else:
        from handlers.palace.action_bar import get_answer

        answer = get_answer(context.sid)
        kb = build_action_bar(answer, 0)
        _run(context.msg.edit_text(answer.pages[0], parse_mode="HTML", reply_markup=kb.as_markup()))


@when("the AI call raises an exception")
def step_ai_call_raises(context):
    import handlers.palace.action_bar as ab

    _sync = ab._sync_ai_call

    def boom(*args, **kwargs):
        raise RuntimeError("ИИ упал")

    ab._sync_ai_call = boom
    try:
        _run(ab.cb_ab_ai_run(context.cb))
    finally:
        ab._sync_ai_call = _sync


@when("the AI returns an empty or whitespace-only query")
def step_ai_empty_query(context):
    import handlers.palace.action_bar as ab

    _sync = ab._sync_ai_call
    ab._sync_ai_call = lambda *a, **k: "   "
    try:
        _run(ab.cb_ab_web(context.cb))
    finally:
        ab._sync_ai_call = _sync


@when("the handler receives the callback")
def step_handler_receives_callback(context):
    from handlers.palace.action_bar import cb_ab_page

    _run(cb_ab_page(context.cb))


@when("I press [{button}]")
def step_press_nav(context, button):
    from handlers.palace.action_bar import cb_ab_page

    if button == "🔙 Вернуться к списку":
        _press_back(context)
        return
    if button == "▶️ Вперёд":
        data = _kb_callback(context.msg)
        nxt = [d for d in data if d.startswith("ab_pg:") and "noop" not in d
               and int(d.split(":")[2]) > 0]
        assert nxt, f"нет кнопки «▶️» на {_kb_labels(context.msg)}"
        parts = nxt[0].split(":")
        context.cb = FakeCb(f"ab_pg:{parts[1]}:{parts[2]}", context.msg)
        _run(cb_ab_page(context.cb))


def _press_back(context):
    import handlers.palace.navigation as navigation
    import json

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return json.dumps({
                "drawers": [{"id": "d1", "closet_name": "Запись 1"}],
                "count": 1,
            })

    _real_get_mcp = navigation.get_mcp
    _real_ctx = navigation._user_context
    navigation.get_mcp = lambda: FakeMCP()
    navigation._user_context = {
        TEST_UID: {"wing": context.wing, "room": context.room},
    }
    try:
        from handlers.palace.action_bar import cb_ab_back

        context.cb = FakeCb(f"ab_back:{context.sid}", context.msg)
        _run(cb_ab_back(context.cb))
    finally:
        navigation.get_mcp = _real_get_mcp
        navigation._user_context = _real_ctx


# ─── Then ───


@then('I see one message with the action bar buttons [{b1}] [{b2}] [{b3}]')
def step_see_action_buttons(context, b1, b2, b3):
    labels = _kb_labels(context.msg)
    for b in (b1, b2, b3):
        assert b in labels, f"{b} not in {labels}"


@then('I see pagination indicator [{indicator}] with the next button [{next_button}]')
def step_see_pagination(context, indicator, next_button):
    labels = _kb_labels(context.msg)
    assert indicator in labels, f"{indicator} not in {labels}"
    assert next_button in labels, f"{next_button} not in {labels}"


@then('I see the button [{button}]')
def step_see_button(context, button):
    assert button in _kb_labels(context.msg), _kb_labels(context.msg)


@then("the same message shows page 2 with indicator [{indicator}]")
def step_same_message_page2(context, indicator):
    assert indicator in _kb_labels(context.msg), _kb_labels(context.msg)
    assert len(context.msg.calls) == 2, "сообщение пересоздано, а не отредактировано"


@then('I see the record list of the room "{room}"')
def step_see_record_list(context, room):
    text = _latest_text(context.msg)
    assert "запис" in text.lower(), text


@then("there is no [{button}] button")
def step_no_button(context, button):
    assert button not in _kb_labels(context.msg), _kb_labels(context.msg)


@then('I get an alert "{text}"')
def step_get_alert(context, text):
    alerts = [a[0] for a in context.cb.answers if a[1] is True]
    assert text in alerts, alerts


@then("the message is not modified")
def step_message_not_modified(context):
    assert len(context.msg.calls) == 0, context.msg.calls


@then('I see an error message with the word "{word}"')
def step_see_error(context, word):
    text = _latest_text(context.msg)
    assert word in text, text


@then("the bot does not crash")
def step_bot_not_crash(context):
    assert True


@then("pagination buttons are not shown")
def step_no_pagination(context):
    labels = _kb_labels(context.msg)
    assert "◀️" not in labels and "▶️" not in labels, labels


@then("indicator [{indicator}] is not shown")
def step_no_indicator(context, indicator):
    assert indicator not in _kb_labels(context.msg), _kb_labels(context.msg)


@then('pressing [{button}] twice shows [{indicator}] without a next button')
def step_press_twice(context, button, indicator):
    from handlers.palace.action_bar import cb_ab_page

    for _ in range(2):
        data = _kb_callback(context.msg)
        nxt = [d for d in data if d.startswith("ab_pg:") and "noop" not in d
               and int(d.split(":")[2]) > 0]
        assert nxt, "нет кнопки «▶️»"
        parts = nxt[0].split(":")
        context.cb = FakeCb(f"ab_pg:{parts[1]}:{parts[2]}", context.msg)
        _run(cb_ab_page(context.cb))
    labels = _kb_labels(context.msg)
    assert indicator in labels, labels
    assert "▶️" not in labels, labels
