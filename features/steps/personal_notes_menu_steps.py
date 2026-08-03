"""Шаги BDD для features/personal_notes_menu.feature."""
import config

from behave import given, then, when

from services import menu

config.ALLOWED_IDS = {424242}

_calls = []
_target = None


class _Target:
    def __init__(self):
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


@given("пользователь открыл список «📖 Личные мысли»")
def step_opened_list(context):
    context.opened_list = True


@given("у пользователя есть состояние списка и активный drawer")
def step_has_state(context):
    import handlers.personal_note as pn

    pn._list_state[424242] = {"wing": "личные_мысли"}
    pn._active_drawer[424242] = "drawer_x"


@when("в личных заметках нажимают «🏠 В меню»")
async def step_press_menu(context):
    import handlers.personal_note as pn

    class User:
        id = 424242

    class Callback:
        from_user = User()
        message = None
        answered = False

        async def answer(self, *a, **k):
            self.answered = True

    global _calls
    _calls = []

    async def fake_go(_t):
        _calls.append("menu")

    original = pn.go_main_menu
    pn.go_main_menu = fake_go
    try:
        await pn.cb_pn_list_back(Callback())
    finally:
        pn.go_main_menu = original


@then("состояние списка очищается")
def step_state_cleared(context):
    import handlers.personal_note as pn

    assert pn._list_state.pop(424242, None) is None


@then("активный drawer очищается")
def step_drawer_cleared(context):
    import handlers.personal_note as pn

    assert pn._active_drawer.pop(424242, None) is None


@then("вызывается открытие главного меню")
def step_menu_called(context):
    assert _calls == ["menu"]


@given("пользователь начал создание заметки")
def step_started_note(context):
    import handlers.personal_note as pn

    pn._waiting_for_note[424242] = True
    pn._note_data[424242] = {"text": "черновик"}


@when("пользователь отправляет «❌ Отмена»")
async def step_send_cancel(context):
    import handlers.personal_note as pn

    class User:
        id = 424242

    class Message:
        from_user = User()

    global _calls
    _calls = []

    async def fake_go(_t):
        _calls.append("menu")

    original = pn.go_main_menu
    pn.go_main_menu = fake_go
    try:
        await pn.cmd_cancel_note(Message())
    finally:
        pn.go_main_menu = original


@then("ожидание заметки очищается")
def step_waiting_cleared(context):
    import handlers.personal_note as pn

    assert pn._waiting_for_note.pop(424242, None) is None


@then("черновик заметки очищается")
def step_draft_cleared(context):
    import handlers.personal_note as pn

    assert pn._note_data.pop(424242, None) is None


@given("команда открытия меню недоступна")
def step_menu_unavailable(context):
    _target = _Target()
    context.menu_target = _target


@when("вызывается возврат в меню")
async def step_call_menu(context):
    context.menu_result = await menu.go_main_menu(context.menu_target)


@then("пользователю показывается сообщение «{text}»")
def step_error_shown(context, text):
    assert context.menu_target.answers
    assert text in context.menu_target.answers[0]


@given("открытие меню бросает исключение")
def step_menu_raises(context):
    import types

    def boom(_t):
        raise RuntimeError("crash")

    fake = types.ModuleType("__main__")
    fake.cmd_start = boom
    _target = _Target()
    context.menu_target = _target
    context.menu_raises_fixture = fake


@then("исключение обработано и пользователь не видит трейсбек")
def step_no_traceback(context):
    assert context.menu_target.answers
    assert "Traceback" not in context.menu_target.answers[0]