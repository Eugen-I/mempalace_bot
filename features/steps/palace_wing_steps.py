"""Шаги BDD для features/palace_wing_select.feature."""
import json
from urllib.parse import parse_qs

from behave import given, then, when

from handlers.palace import navigation

LONG_WING = "ПСИХОАНАЛИТИЧЕСКАЯ МОДЕЛЬ ОПЫТА В ТВОРЧЕСТВЕ ФОТОГРАФА"
UID = 424242


class _FakeMcp:
    def __init__(self, wings):
        self._wings = wings

    async def call_tool(self, tool, args=None):
        if tool == "mempalace_list_wings":
            return json.dumps({"wings": self._wings})
        if tool == "mempalace_list_rooms":
            wing = (args or {}).get("wing", "")
            return json.dumps({"rooms": {"Комната": 3} if wing == LONG_WING else {}})
        raise AssertionError(f"unexpected tool: {tool}")


class _FakeMessage:
    def __init__(self):
        self.edited = []
        self.answers = []

    async def edit_text(self, text, **kwargs):
        self.edited.append((text, kwargs))

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class _FakeCb:
    def __init__(self, data):
        self.data = data
        self.message = _FakeMessage()
        self.from_user = type("U", (), {"id": UID})()

    async def answer(self, *a, **k):
        pass


def _install_wings(context, wings):
    mcp = _FakeMcp(wings)
    navigation._wing_callback_map.clear()
    import config

    config.ALLOWED_IDS = {UID}
    navigation.get_mcp = lambda: mcp
    context.mcp = mcp


def _last_text(context):
    cb = context.cb
    if cb.message.edited:
        return cb.message.edited[-1][0]
    if cb.message.answers:
        return cb.message.answers[-1][0]
    return ""


@given('MCP возвращает крылья с длинным именем «{wing}»')
def step_wings_with_long(context, wing):
    _install_wings(context, {"проекты": 10, wing: 3})


@given('MCP возвращает крыла «{w1}» и «{w2}»')
def step_wings_two(context, w1, w2):
    _install_wings(context, {w1: 5, w2: 1})


@when('пользователь нажимает кнопку «{btn}»')
def step_press_menu(context, btn):
    context.cb = _FakeCb("p_wing")
    import asyncio

    asyncio.run(navigation.cb_list_wings(context.cb))


@when('пользователь нажимает кнопку выбора длинного крыла')
def step_press_long_wing(context):
    context.cb = _FakeCb(navigation._build_wing_callback_data(LONG_WING))
    import asyncio

    asyncio.run(navigation.cb_rooms_select(context.cb))


@then('бот показывает все крылья в списке')
def step_show_all(context):
    text = _last_text(context)
    assert "Крылья MemPalace" in text
    assert LONG_WING in text


@then('каждая кнопка выбора крыла короче 64 байт')
def step_buttons_short(context):
    markup = context.cb.message.edited[-1][1].get("reply_markup")
    for row in markup.inline_keyboard:
        for b in row:
            if b.callback_data.startswith("p_rs_:"):
                assert len(b.callback_data.encode("utf-8")) <= 64, b.callback_data


@then('бот показывает оба крыла в списке')
def step_show_both(context):
    text = _last_text(context)
    assert "проекты" in text
    assert "личные_мысли" in text


@then('бот показывает комнаты выбранного крыла')
def step_show_rooms(context):
    text = _last_text(context)
    assert f"Комнаты крыла {LONG_WING}" in text
    assert "Комната" in text
