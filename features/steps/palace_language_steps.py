"""Шаги BDD для features/palace_language.feature."""
import json
from unittest import mock

from behave import given, then, when

from handlers.palace import navigation
from tests.test_action_bar import FakeCallback

LANG = "Отвечай на русском языке"
_captured = []


class _FakeMcp:
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
            return json.dumps({"content": "Содержимое."})
        return "{}"


class _EmptyMcp:
    async def call_tool(self, name, args=None):
        return '{"drawers": [], "count": 0}'


class _TunnelsMcp:
    async def call_tool(self, name, args=None):
        return json.dumps([{"src_wing": "а", "src_room": "б"}])


class _FakeMsg:
    def __init__(self):
        self.edited = []
        self.answered = None

    async def edit_text(self, text, **kwargs):
        self.edited.append(text)
        return self

    async def answer(self, text=None, **kwargs):
        self.answered = text
        return self


def _fake_ai_call(engine, model, messages, **kwargs):
    _captured.append(messages)
    return "Ответ на русском."


def _reset_captured():
    _captured.clear()


@given("пользователь задал вопрос по комнате «{room}»")
def step_ask_room(context, room):
    context.wing, context.room = room.split("/")
    context.mcp = _FakeMcp()
    _reset_captured()


@given("у пользователя есть кэш саммари комнаты")
def step_has_cache(context):
    navigation._user_context[1] = {"_room_summary": "Саммари."}
    context.mcp = _FakeMcp()
    _reset_captured()


@given("в базе есть туннели между комнатами")
def step_has_tunnels(context):
    context.mcp = _TunnelsMcp()
    _reset_captured()


@given("в комнате есть записи")
def step_has_drawers(context):
    context.mcp = _FakeMcp()
    _reset_captured()


@given("в комнате «{room}» нет записей")
def step_empty_room(context, room):
    context.wing, context.room = room.split("/")
    context.mcp = _EmptyMcp()
    _reset_captured()


@when("ИИ формирует системный промпт шага ответа")
async def step_prompt_answer(context):
    with mock.patch(
        "services.ai_engine._sync_ai_call", _fake_ai_call
    ), mock.patch.object(navigation, "get_mcp", lambda: context.mcp):
        await navigation._answer_room_ai(
            _FakeMsg(), 1, context.wing, context.room, "Вопрос?",
        )
    context.answer_system = _captured[-1][0]["content"]
    context.summary_prompt = _captured[0][1]["content"]


@when("ИИ формирует системный промпт саммари")
async def step_prompt_summary(context):
    with mock.patch(
        "services.ai_engine._sync_ai_call", _fake_ai_call
    ), mock.patch.object(navigation, "get_mcp", lambda: context.mcp):
        await navigation._answer_room_ai(
            _FakeMsg(), 1, context.wing, context.room, "Вопрос?",
        )
    context.summary_system = _captured[0][0]["content"]


@when("ИИ формирует промпт с результатами поиска в интернете")
async def step_prompt_web(context):
    from handlers.palace import action_bar

    async def fake_finalize(uid, edit_func, text, **kwargs):
        return None

    async def fake_search(q):
        return "Результаты."

    with mock.patch(
        "services.ai_engine._sync_ai_call", _fake_ai_call
    ), mock.patch.object(
        navigation, "get_mcp", lambda: context.mcp
    ), mock.patch.object(action_bar, "finalize_answer", fake_finalize), mock.patch(
        "services.web_search.search_web", fake_search
    ):
        await navigation._answer_room_ai(
            _FakeMsg(), 1, "крыло", "комната", "Вопрос?", with_web=True,
        )
    context.web_prompt = _captured[-1][0]["content"]


@when("ИИ формирует промпт анализа туннелей")
async def step_prompt_tunnels(context):
    with mock.patch(
        "services.ai_engine._sync_ai_call", _fake_ai_call
    ), mock.patch.object(navigation, "get_mcp", lambda: context.mcp), mock.patch(
        "services.ai_engine.get_current_ai", lambda: ("gemini", "g")
    ):
        await navigation.cb_tunnels_ai(FakeCallback("p_tun_ai"))
    context.tunnels_prompt = _captured[-1][0]["content"]


@when("ИИ формирует промпт статьи")
async def step_prompt_article(context):
    from handlers.palace import action_bar

    async def fake_finalize(uid, edit_func, text, **kwargs):
        return None

    navigation._room_session[424242] = {"wing": "крыло", "room": "комната"}
    with mock.patch(
        "services.ai_engine._sync_ai_call", _fake_ai_call
    ), mock.patch.object(
        action_bar, "finalize_answer", fake_finalize
    ), mock.patch.object(navigation, "get_mcp", lambda: context.mcp), mock.patch(
        "services.ai_engine.get_current_ai", lambda: ("gemini", "g")
    ), mock.patch.object(
        navigation, "_room_session", {424242: {"wing": "крыло", "room": "комната"}}
    ):
        await navigation.cb_cross_ai_article(FakeCallback("p_rd_art"))
    context.article_prompt = _captured[-1][0]["content"]


@when("пользователь задаёт вопрос по этой комнате")
async def step_ask_empty(context):
    context.msg = _FakeMsg()
    with mock.patch.object(navigation, "get_mcp", lambda: context.mcp):
        await navigation._answer_room_ai(
            context.msg, 1, context.wing, context.room, "Вопрос?",
        )


@then("промпт содержит «{directive}»")
def step_has_directive(context, directive):
    assert directive in _captured[-1][0]["content"]


@then("промпт содержит саммари комнаты")
def step_has_summary(context):
    assert "Структурированная саммари комнаты" in context.answer_system


@then("показывается сообщение «{text}»")
def step_msg_shown(context, text):
    assert text in context.msg.edited[-1]


@then("ИИ не вызывается")
def step_ai_not_called(context):
    assert not _captured
